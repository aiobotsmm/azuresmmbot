import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

API_TOKEN = "7960194771:AAFJAndZCpDUEbwisV3ruW8GLVt6xU1eTp8"  # Replace this with your real token

# Create bot and dispatcher
bot = Bot(token=API_TOKEN, parse_mode=ParseMode.MARKDOWN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

@router.message(F.text == "/start")
async def start_handler(m: Message):
    print(f"[TEST] /start received from {m.from_user.id}")
    await m.answer("👋 Hello! Bot is working ✅")

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
