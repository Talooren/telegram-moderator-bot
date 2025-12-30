import os
import asyncio
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton


BOT_TOKEN = os.environ["BOT_TOKEN"]

# ✅ ТВОЙ chat_id группы модерации
MOD_CHAT_ID = -1003496458501

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
        "Сейчас режим: премодерация.\n"
        "Отправь сообщение мне в личку — я перешлю его в чат модерации с кнопками."
    )

@dp.message(Command("chatid"))
async def chatid(m: Message):
    await m.answer(f"chat_id = {m.chat.id}")


# ---------- user flow ----------
@dp.message()
async def incoming(m: Message):
    # чтобы пользователи не писали в модераторской группе (не обязательно, но удобно)
    if m.chat.id == MOD_CHAT_ID:
        return

    text = (m.text or "").strip()
    if not text:
        await m.answer("Пришли текстом 🙂")
        return

    # request_id сделаем как message_id в чате модерации (удобно: хранение = Telegram)
    mod_text = (
        "🛡 Новая заявка\n"
        f"Отправитель ID: {m.from_user.id}\n\n"
        "Текст (как будет опубликован):\n"
        f"{text}"
    )

    msg = await bot.send_message(MOD_CHAT_ID, mod_text, reply_markup=mod_kb(request_id=0))
    request_id = msg.message_id

    # обновим кнопки с правильным request_id
    await bot.edit_message_reply_markup(
        chat_id=MOD_CHAT_ID,
        message_id=request_id,
        reply_markup=mod_kb(request_id=request_id)
    )

    await m.answer("✅ Принято. Отправлено на модерацию.")


# ---------- moderation actions ----------
@dp.callback_query(F.data.startswith("approve:"))
async def approve(cq: CallbackQuery):
    # доступ: только админы группы модерации
    if not await is_chat_admin(cq.from_user.id, MOD_CHAT_ID):
        await cq.answer("Нет доступа (только админы чата модерации).", show_alert=True)
        return

    request_id = int(cq.data.split(":")[1])

    # достаём из текста ID автора и контент
    # cq.message.text содержит "Отправитель ID: ..."
    txt = cq.message.text or ""
    lines = txt.splitlines()

    user_id = None
    for line in lines:
        if line.startswith("Отправитель ID:"):
            try:
                user_id = int(line.replace("Отправитель ID:", "").strip())
            except Exception:
                user_id = None

    # контент начинается после строки "Текст (как будет опубликован):"
    marker = "Текст (как будет опубликован):"
    if marker in txt:
        content = txt.split(marker, 1)[1].strip()
    else:
        content = txt

    # ПОКА ЧТО: на этом этапе мы не публикуем в каналы (сделаем следующим этапом),
    # просто подтверждаем решение и уведомляем пользователя.
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
