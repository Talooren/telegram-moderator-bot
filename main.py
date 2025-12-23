import os
import asyncio
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

# === Telegram ===
BOT_TOKEN = os.environ["BOT_TOKEN"]

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Бот запущен (Web + polling) ✅")

@dp.message()
async def echo(m: Message):
    await m.answer(f"Эхо: {m.text}")

# === HTTP server for Render ===
async def handle(request):
    return web.Response(text="OK")

async def start_web():
    app = web.Application()
    app.router.add_get("/", handle)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# === Main ===
async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
