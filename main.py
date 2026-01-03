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

MOD_CHAT_ID = -1003496458501
OWNER_ID = 277565921
TARGET_CHANNELS = [-1003517837342]

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


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


async def publish_to_channels(content: str) -> tuple[int, list[tuple[int, str]]]:
    """
    Возвращает:
    - ok_count
    - failed: список (channel_id, error_text)
    """
    ok = 0
    failed: list[tuple[int, str]] = []

    for ch in TARGET_CHANNELS:
        try:
            await bot.send_message(ch, content)
            ok += 1
        except Exception as e:
            failed.append((ch, f"{type(e).__name__}: {e}"))

    return ok, failed


@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Бот запущен ✅\n\n"
        "Пиши мне сообщение — оно уйдёт в модерацию.\n"
        "После ✅ Одобрить публикуется в канал(ы) без автора.\n\n"
        "Команды:\n"
        "/chatid — chat_id текущего чата\n"
        "/testpub — тест публикации (только владелец)"
    )


@dp.message(Command("chatid"))
async def chatid(m: Message):
    await m.answer(f"chat_id = {m.chat.id}")


@dp.message(Command("testpub"))
async def testpub(m: Message):
    if not (m.from_user and m.from_user.id == OWNER_ID):
        await m.answer("Нет доступа.")
        return

    ok, failed = await publish_to_channels("✅ Тест публикации из бота")
    if not failed:
        await m.answer(f"✅ Успех: {ok}/{len(TARGET_CHANNELS)}")
    else:
        text = f"⚠️ Успех: {ok}/{len(TARGET_CHANNELS)}\nОшибки:\n"
        for ch, err in failed:
            text += f"- {ch}: {err}\n"
        await m.answer(text)


@dp.message(F.forward_from_chat)
async def debug_forwarded(m: Message):
    if not (m.from_user and m.from_user.id == OWNER_ID):
        return

    title = m.forward_from_chat.title or "—"
    chat_id = m.forward_from_chat.id
    await m.answer(
        "✅ forward_from_chat найден\n"
        f"title: {title}\n"
        f"chat_id: {chat_id}"
    )


@dp.message()
async def incoming(m: Message):
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


@dp.callback_query(F.data.startswith("approve:"))
async def approve(cq: CallbackQuery):
    if not await is_chat_admin(cq.from_user.id, MOD_CHAT_ID):
        await cq.answer("Нет доступа (только админы чата модерации).", show_alert=True)
        return

    request_id = int(cq.data.split(":")[1])
    moderation_text = cq.message.text or ""

    user_id, content = extract_user_id_and_content(moderation_text)

    ok_count, failed = await publish_to_channels(content)

    status_line = f"✅ Одобрено. Публикация: {ok_count}/{len(TARGET_CHANNELS)}"
    if failed:
        status_line += "\n\n⚠️ Ошибки публикации:\n"
        for ch, err in failed:
            status_line += f"- {ch}: {err}\n"

    await cq.message.edit_text(
        f"{status_line}\n(заявка #{request_id})\n\n{moderation_text}"
    )
    await cq.answer("Готово.")

    if user_id:
        try:
            if failed:
                await bot.send_message(user_id, "⚠️ Заявка одобрена, но публикация в канал не удалась. Модератор уже видит причину.")
            else:
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


# ---- HTTP for Render ----
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
