import os
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = int(os.environ["API_ID"])
api_hash = os.environ["API_HASH"]

async def main():
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        print("\nاین کد نشست محرمانه است؛ آن را برای هیچ‌کس نفرست.")
        print("\nSESSION_STRING=\n")
        print(client.session.save())
        print("\nاین مقدار را در بخش Secrets هاست با نام SESSION_STRING ذخیره کن.")

import asyncio
asyncio.run(main())
