import os
import asyncio
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]

# ✅ чат модерации (твой)
MOD_CHAT_ID = -1003496458501

# ✅ владелец (твой user_id) — только он сможет узнавать chat_id каналов/групп
OWNER_ID = 277565921

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ---------- helpers ----------
def mod_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{request_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{request_id}"),
        ]
    ])

async def is_chat_admin(user_id: int, chat_id: int) -> bool:
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ("administrator", "creator")


# ---------- commands ----------
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Бот запущен ✅\n\n"
        "Схема: пользователь → модерация → (дальше подключим публикацию в канал)\n\n"
        "Команды:\n"
        "/chatid — узнать chat_id текущего чата (пиши в нужной группе/канале, где есть бот)\n\n"
        "Чтобы узнать chat_id канала без добавления бота — просто перешли мне пост из канала."
    )

@dp.message(Command("chatid"))
async def chatid(m: Message):
    await m.answer(f"chat_id = {m.chat.id}")


# ---------- DEBUG: forwarded posts to get channel id ----------
# Важно: этот хэндлер должен стоять ВЫШЕ общего incoming(),
# чтобы успеть обработать пересланный пост.
@dp.message()
async def debug_forwarded(m: Message):
    # Разрешаем только владельцу
    if not (m.from_user and m.from_user.id == OWNER_ID):
        return

    # Если сообщение переслано из канала/группы, здесь будет объект forward_from_chat
    if m.forward_from_chat:
        title = m.forward_from_chat.title or "—"
        chat_id = m.forward_from_chat.id
        await m.answer(
            "✅ forward_from_chat найден\n"
            f"title: {title}\n"
            f"chat_id: {chat_id}\n\n"
            "Скопируй chat_id и пришли мне сюда — подключим публикацию в канал."
        )
        return


# ---------- user flow ----------
@dp.message()
async def incoming(m: Message):
    # Игнорируем сообщения внутри модераторской группы (чтобы не плодить заявки)
    if m.chat.id == MOD_CHAT_ID:
        return

    # Принимаем только текст (пока)
    text = (m.text or "").strip()
    if not text:
        await m.answer("Пришли текстовое сообщение 🙂")
        return

    # request_id будем хранить как message_id в чате модерации (это и есть наша «БД»)
    mod_text = (
        "🛡 Новая заявка\n"
        f"Отправитель ID: {m.from_user.id}\n\n"
        "Текст (как будет опубликован):\n"
        f"{text}"
    )

    msg = await bot.send_message(MOD_CHAT_ID, mod_text, reply_markup=mod_kb(request_id=0))
    request_id = msg.message_id

    # обновим кнопки, чтобы в callback_data был правильный request_id
    await bot.edit_message_reply_markup(
        chat_id=MOD_CHAT_ID,
        message_id=request_id,
        reply_markup=mod_kb(request_id=request_id)
    )

    await m.answer("✅ Принято. Отправлено на модерацию.")


# ---------- moderation actions ----------
@dp.callback_query(F.data.startswith("approve:"))
async def approve(cq: CallbackQuery):
    # Доступ: только админы группы модерации
    if not await is_chat_admin(cq.from_user.id, MOD_CHAT_ID):
        await cq.answer("Нет доступа (только админы чата модерации).", show_alert=True)
        return

    request_id = int(cq.data.split(":")[1])

    txt = cq.message.text or ""
    lines = txt.splitlines()

    # достаём user_id отправителя
    user_id = None
    for line in lines:
        if line.startswith("Отправитель ID:"):
            try:
                user_id = int(line.replace("Отправитель ID:", "").strip())
            except Exception:
                user_id = None

    # достаём контент (после маркера)
    marker = "Текст (как будет опубликован):"
    content = txt.split(marker, 1)[1].strip() if marker in txt else txt

    # ПОКА: просто отмечаем одобрение, публикацию в канал подключим следующим шагом
    await cq.message.edit_text(f"✅ Одобрено (заявка #{request_id})\n\n{txt}")
    await cq.answer("Одобрено.")

    if user_id:
        try:
            await bot.send_message(user_id, "✅ Ваша заявка одобрена модератором.")
        except Exception:
            pass


@dp.callback_query(F.data.startswith("reject:"))
async def reject(cq: CallbackQuery):
    if not await is_chat_admin(cq.from_user.id, MOD_CHAT_ID):
        await cq.answer("Нет доступа (только админы чата модерации).", show_alert=True)
        return

    request_id = int(cq.data.split(":")[1])

    txt = cq.message.text or ""
    lines = txt.splitlines()

    user_id = None
    for line in lines:
        if line.startswith("Отправитель ID:"):
            try:
                user_id = int(line.replace("Отправитель ID:", "").strip())
            except Exception:
                user_id = None

    await cq.message.edit_text(f"❌ Отклонено (заявка #{request_id})\n\n{txt}")
    await cq.answer("Отклонено.")

    if user_id:
        try:
            await bot.send_message(user_id, "❌ Ваша заявка отклонена модератором.")
        except Exception:
            pass


# ---------- HTTP for Render ----------
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


async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
