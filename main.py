import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

BOT_TOKEN = os.getenv("8327321881:AAGxajMRvCluTZQrKLgM5finfPaJwsozQIo")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add it to environment variables.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привет! Я Готовкин 👨‍🍳\n"
        "Помогу выбрать, что приготовить 🍽️"
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
