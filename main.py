import os
import asyncio
import sqlite3
from datetime import datetime

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

# =========================
# Настройки
# =========================
BOT_TOKEN = os.environ["BOT_TOKEN"]
DB_PATH = "requests.db"  # временно локально (на Render free может пропасть при перезапуске)

# =========================
# SQLite (пока для теста)
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

db = init_db()

# =========================
# Telegram bot
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Бот запущен (Web + polling) ✅\n\n"
        "Команды:\n"
        "/chatid — узнать chat_id текущего чата (полезно в группе модерации)\n\n"
        "Также можно отправить любое сообщение — я временно сохраню его в SQLite и верну ID."
    )

# ✅ ВОТ ТВОЁ ДОБАВЛЕНИЕ: команда /chatid
@dp.message(Command("chatid"))
async def chatid(m: Message):
    await m.answer(f"chat_id = {m.chat.id}")

# временный тестовый обработчик: сохраняем любое сообщение в SQLite
@dp.message()
async def save_any(m: Message):
    text = (m.text or "").strip()
    if not text:
        await m.answer("Пришли текстом 🙂")
        return

    cur = db.cursor()
    cur.execute(
        "INSERT INTO requests (text, user_id, status, created_at) VALUES (?, ?, ?, ?)",
        (text, m.from_user.id, "pending", datetime.utcnow().isoformat())
    )
    db.commit()
    rid = cur.lastrowid

    await m.answer(f"✅ Сохранила в SQLite. ID заявки: {rid}")

# =========================
# HTTP для Render (чтобы сервис считался живым)
# =========================
async def handle(request):
    return web.Response(text="OK")

async def start_web():
    app = web.Application()
    app.router.add_get("/", handle)

    port = int(os.environ.get("PORT", "10000"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# =========================
# Main
# =========================
async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
