from aiogram import Bot
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
bot = Bot(token=os.getenv("API_TOKEN"))

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook deleted.")

asyncio.run(main())
