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

# ✅ чат модерации
MOD_CHAT_ID = -1003496458501

# ✅ владелец (может узнавать chat_id пересылкой)
OWNER_ID = 277565921

# ✅ каналы публикации (можно несколько)
TARGET_CHANNELS = [-1003517837342]

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

def extract_user_id_and_content(moderation_text: str) -> tuple[int | None, str]:
    """
    Разбираем сообщение в модерации:
    🛡 Новая заявка
    Отправитель ID: 123
    ...
    Текст (как будет опубликован):
    <контент>
    """
    txt = moderation_text or ""
    user_id = None

    for line in txt.splitlines():
        if line.startswith("Отправитель ID:"):
            try:
                user_id = int(line.replace("Отправитель ID:", "").strip())
            except Exception:
                user_id = None
            break

    marker = "Текст (как будет опубликован):"
    content = txt.split(marker, 1)[1].strip() if marker in txt else txt
    return user_id, content

async def publish_to_channels(content: str) -> tuple[int, list[int]]:
    ok = 0
    failed = []
    for ch in TARGET_CHANNELS:
        try:
            await bot.send_message(ch, content)
            ok += 1
        except Exception:
            failed.append(ch)
    return ok, failed


# ---------- commands ----------
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Бот запущен ✅\n\n"
        "Схема: пользователь → модерация → публикация в канал.\n"
        "Отправь мне сообщение в личку — оно уйдет в модерацию.\n"
        "После одобрения модератором будет опубликовано в канал(ы) без автора.\n\n"
        "Команда: /chatid — узнать chat_id текущего чата."
    )

@dp.message(Command("chatid"))
async def chatid(m: Message):
    await m.answer(f"chat_id = {m.chat.id}")


# ---------- DEBUG: forwarded posts to get channel id ----------
@dp.message()
async def debug_forwarded(m: Message):
    if not (m.from_user and m.from_user.id == OWNER_ID):
        return

    if m.forward_from_chat:
        title = m.forward_from_chat.title or "—"
        chat_id = m.forward_from_chat.id
        await m.answer(
            "✅ forward_from_chat найден\n"
            f"title: {title}\n"
            f"chat_id: {chat_id}"
        )
        return


# ---------- user flow ----------
@dp.message()
async def incoming(m: Message):
    # не создаём заявки из сообщений модераторского чата
    if m.chat.id == MOD_CHAT_ID:
        return

    text = (m.text or "").strip()
    if not text:
        await m.answer("Пришли текстовое сообщение 🙂")
        return

    mod_text = (
        "🛡 Новая заявка\n"
        f"Отправитель ID: {m.from_user.id}\n\n"
        "Текст (как будет опубликован):\n"
        f"{text}"
    )

    msg = await bot.send_message(MOD_CHAT_ID, mod_text, reply_markup=mod_kb(request_id=0))
    request_id = msg.message_id

    await bot.edit_message_reply_markup(
        chat_id=MOD_CHAT_ID,
        message_id=request_id,
        reply_markup=mod_kb(request_id=request_id)
    )

    await m.answer("✅ Принято. Отправлено на модерацию.")


# ---------- moderation actions ----------
@dp.callback_query(F.data.startswith("approve:"))
async def approve(cq: CallbackQuery):
    if not await is_chat_admin(cq.from_user.id, MOD_CHAT_ID):
        await cq.answer("Нет доступа (только админы чата модерации).", show_alert=True)
        return

    request_id = int(cq.data.split(":")[1])
    moderation_text = cq.message.text or ""

    user_id, content = extract_user_id_and_content(moderation_text)

    # публикуем в канал(ы)
    ok_count, failed = await publish_to_channels(content)

    # обновляем сообщение модерации
    status_line = f"✅ Одобрено и опубликовано: {ok_count}/{len(TARGET_CHANNELS)} канал(ов)"
    if failed:
        status_line += f"\n⚠️ Не удалось в: {', '.join(map(str, failed))}"

    await cq.message.edit_text(
        f"{status_line}\n"
        f"(заявка #{request_id})\n\n"
        f"{moderation_text}"
    )
    await cq.answer("Опубликовано.")

    # уведомляем пользователя
    if user_id:
        try:
            await bot.send_message(user_id, "✅ Ваша заявка одобрена и опубликована.")
        except Exception:
            pass


@dp.callback_query(F.data.startswith("reject:"))
async def reject(cq: CallbackQuery):
    if not await is_chat_admin(cq.from_user.id, MOD_CHAT_ID):
        await cq.answer("Нет доступа (только админы чата модерации).", show_alert=True)
        return

    request_id = int(cq.data.split(":")[1])
    moderation_text = cq.message.text or ""

    user_id, _ = extract_user_id_and_content(moderation_text)

    await cq.message.edit_text(f"❌ Отклонено (заявка #{request_id})\n\n{moderation_text}")
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
