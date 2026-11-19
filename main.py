import os, csv, json, asyncio, zipfile, tempfile
from datetime import timezone
from telethon import TelegramClient
from telethon.sessions import StringSession
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
ADMIN_ID = int(os.environ["ADMIN_ID"])

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
export_lock = asyncio.Lock()

def media_kind(msg):
    if msg.photo:
        return "photo"
    if msg.video:
        return "video"
    if msg.document:
        return "document"
    if msg.audio:
        return "audio"
    if msg.voice:
        return "voice"
    if msg.sticker:
        return "sticker"
    return ""

def message_row(msg, channel_username):
    date = msg.date.astimezone(timezone.utc).isoformat() if msg.date else ""
    reactions = []
    if msg.reactions and msg.reactions.results:
        for r in msg.reactions.results:
            reactions.append({
                "reaction": getattr(r.reaction, "emoticon", None) or str(r.reaction),
                "count": r.count
            })
    return {
        "id": msg.id,
        "date_utc": date,
        "text": msg.message or "",
        "views": msg.views,
        "forwards": msg.forwards,
        "replies": msg.replies.replies if msg.replies else None,
        "media_type": media_kind(msg),
        "media_size": getattr(getattr(msg, "file", None), "size", None),
        "post_url": f"https://t.me/{channel_username}/{msg.id}" if channel_username else "",
        "reactions": reactions
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "ربات تحلیل کانال آماده است.\n"
        "برای استخراج:\n/export sc6rn 500\n"
        "عدد را تعداد پست‌های آخر قرار بده. برای کل تاریخچه از 0 استفاده کن.\n"
        "/help برای راهنما"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "دستورها:\n"
        "/export sc6rn 500 — استخراج ۵۰۰ پست آخر\n"
        "/export sc6rn 0 — استخراج کل تاریخچه (ممکن است طول بکشد)\n"
        "/status — وضعیت اتصال\n\n"
        "خروجی شامل متن، تاریخ، بازدید، فوروارد، پاسخ‌ها، نوع رسانه، واکنش‌ها و لینک پست است.\n"
        "این نسخه فایل رسانه‌ها را دانلود نمی‌کند؛ فقط مشخصات و نوع آن‌ها را ثبت می‌کند."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("اتصال تلگرام برقرار است." if client.is_connected() else "اتصال تلگرام برقرار نیست.")

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) < 1:
        await update.message.reply_text("فرمت دستور: /export sc6rn 500")
        return
    username = context.args[0].lstrip("@").replace("https://t.me/", "").strip("/")
    try:
        limit = int(context.args[1]) if len(context.args) > 1 else 200
        if limit < 0 or limit > 100000:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("تعداد باید عددی بین 0 تا 100000 باشد. صفر یعنی کل تاریخچه.")
        return
    if export_lock.locked():
        await update.message.reply_text("یک استخراج دیگر در حال انجام است؛ کمی صبر کن.")
        return

    async with export_lock:
        status_msg = await update.message.reply_text(f"در حال بررسی کانال @{username} ...")
        try:
            entity = await client.get_entity(username)
            rows = []
            async for msg in client.iter_messages(entity, limit=limit or None):
                if msg.action:
                    continue
                rows.append(message_row(msg, username))
            rows.reverse()
            if not rows:
                await status_msg.edit_text("هیچ پستی پیدا نشد یا دسترسی به کانال ممکن نیست.")
                return

            os.makedirs("exports", exist_ok=True)
            stem = f"{username}_export"
            json_path = os.path.join("exports", stem + ".json")
            csv_path = os.path.join("exports", stem + ".csv")
            zip_path = os.path.join("exports", stem + ".zip")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                for row in rows:
                    out = dict(row)
                    out["reactions"] = json.dumps(row["reactions"], ensure_ascii=False)
                    writer.writerow(out)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(json_path, arcname=os.path.basename(json_path))
                z.write(csv_path, arcname=os.path.basename(csv_path))

            await status_msg.edit_text(f"استخراج تمام شد: {len(rows)} پست. در حال ارسال فایل‌ها...")
            for path in (zip_path, json_path, csv_path):
                with open(path, "rb") as f:
                    await update.message.reply_document(document=f, filename=os.path.basename(path))
            await status_msg.edit_text(f"تمام شد؛ {len(rows)} پست از @{username} استخراج شد.")
        except Exception as e:
            await status_msg.edit_text(
                "استخراج انجام نشد. نام کانال را بررسی کن و مطمئن شو حساب متصل‌شده به کانال دسترسی دارد.\n"
                f"جزئیات خطا: {type(e).__name__}: {str(e)[:500]}"
            )

async def main():
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("SESSION_STRING معتبر یا مجاز نیست. ابتدا auth.py را اجرا کن.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("export", export_cmd))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("Bot is running.")
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
