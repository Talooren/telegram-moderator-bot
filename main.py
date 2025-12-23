import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

BOT_TOKEN = os.environ["BOT_TOKEN"]

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Бот на Render запущен ✅ Напиши любое сообщение.")

@dp.message()
async def echo(m: Message):
    await m.answer(f"Эхо: {m.text}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
