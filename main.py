import os
import re
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

# ✅ канал публикации (один)
TARGET_CHANNEL_ID = -1003517837342

ALLOWED_TAGS = {"#Задача", "#Вопрос", "#Ответ", "#Предложение"}

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ----------------- UI texts -----------------
TEMPLATE_TEXT = (
    "Сообщение должно быть строго по шаблону:\n\n"
    "Кому: <отдел>\n"
    "От кого: <отдел>\n\n"
    "#Задача | #Вопрос | #Ответ | #Предложение\n\n"
    "Текст сообщения (можно в несколько строк)\n\n"
    "Пример:\n"
    "Кому: CFO\n"
    "От кого: IT\n\n"
    "#Задача\n\n"
    "Подготовить модель финансирования рассылок.\n"
    "Срок: сегодня 15:00"
)

def mod_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{request_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{request_id}"),
        ]
    ])


# ----------------- helpers -----------------
async def is_chat_admin(user_id: int, chat_id: int) -> bool:
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ("administrator", "creator")


def parse_user_message(text: str) -> tuple[bool, str, dict]:
    """
    Возвращает:
      ok: bool
      error: str (если ok=False)
      data: dict (если ok=True) {to, from, tag, body, formatted}
    """
    raw = (text or "").strip()
    if not raw:
        return False, "Пустое сообщение.", {}

    # Нормализуем переносы
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    # Ищем строки Кому и От кого
    # Требуем в начале строки: "Кому:" и "От кого:"
    to_match = re.search(r"(?im)^\s*Кому\s*:\s*(.+?)\s*$", raw)
    from_match = re.search(r"(?im)^\s*От\s+кого\s*:\s*(.+?)\s*$", raw)

    if not to_match or not from_match:
        return False, "Не найдены строки 'Кому:' и/или 'От кого:'.", {}

    to_dep = to_match.group(1).strip()
    from_dep = from_match.group(1).strip()

    if not to_dep or not from_dep:
        return False, "Поля 'Кому:' и 'От кого:' не могут быть пустыми.", {}

    # Ищем теги (строки содержащие #...)
    found_tags = re.findall(r"(?im)^\s*(#\S+)\s*$", raw)
    found_tags = [t.strip() for t in found_tags]

    # Отбираем только разрешённые
    allowed_found = [t for t in found_tags if t in ALLOWED_TAGS]

    if len(allowed_found) == 0:
        return False, "Не найден тег (#Задача / #Вопрос / #Ответ / #Предложение).", {}
    if len(allowed_found) > 1:
        return False, "Можно указать только ОДИН тег (#Задача или #Вопрос или #Ответ или #Предложение).", {}

    tag = allowed_found[0]

    # Тело сообщения: всё, что после строки с тегом (первое вхождение)
    # Найдём позицию строки тега
    lines = raw.split("\n")
    body_lines = []
    tag_seen = False
    for line in lines:
        if not tag_seen and line.strip() == tag:
            tag_seen = True
            continue
        if tag_seen:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not body:
        return False, "После тега должен быть текст сообщения.", {}

    # Финальный формат, который уйдёт в канал (анонимно)
    formatted = (
        f"Кому: {to_dep}\n"
        f"От кого: {from_dep}\n\n"
        f"{tag}\n\n"
        f"{body}"
    )

    return True, "", {"to": to_dep, "from": from_dep, "tag": tag, "body": body, "formatted": formatted}


def extract_sender_id(moderation_text: str) -> int | None:
    """
    В модерации храним тех. строку "sender_id: <число>"
    """
    txt = moderation_text or ""
    m = re.search(r"(?im)^\s*sender_id\s*:\s*(\d+)\s*$", txt)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def extract_formatted_block(moderation_text: str) -> str:
    """
    В модерации сообщение содержит блок:
    ===CONTENT===
    <formatted>
    ===/CONTENT===
    """
    txt = moderation_text or ""
    m = re.search(r"(?s)===CONTENT===\n(.*?)\n===/CONTENT===", txt)
    if not m:
        return txt
    return m.group(1).strip()


async def publish_to_channel(content: str) -> tuple[bool, str]:
    """
    Публикуем в один канал. Возвращаем (ok, error_text)
    """
    try:
        await bot.send_message(TARGET_CHANNEL_ID, content)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ----------------- commands -----------------
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Бот запущен ✅\n\n"
        "Отправляй сообщение по шаблону — оно уйдёт на модерацию.\n"
        "После одобрения будет опубликовано в канале.\n\n"
        f"{TEMPLATE_TEXT}"
    )


@dp.message(Command("chatid"))
async def chatid(m: Message):
    await m.answer(f"chat_id = {m.chat.id}")


# Узнать chat_id канала/группы через пересланный пост — только OWNER
@dp.message(F.forward_from_chat)
async def debug_forwarded(m: Message):
    if not (m.from_user and m.from_user.id == OWNER_ID):
        return
    title = m.forward_from_chat.title or "—"
    chat_id = m.forward_from_chat.id
    await m.answer(f"✅ forward_from_chat найден\ntitle: {title}\nchat_id: {chat_id}")


# ----------------- user flow -----------------
@dp.message()
async def incoming(m: Message):
    # игнорируем сообщения в модераторской группе (чтобы не создавать заявки)
    if m.chat.id == MOD_CHAT_ID:
        return

    # принимаем только текст
    text = (m.text or "").strip()
    if not text:
        await m.answer("Пришли текстовое сообщение 🙂\n\n" + TEMPLATE_TEXT)
        return

    ok, err, data = parse_user_message(text)
    if not ok:
        await m.answer(f"❌ Формат неверный: {err}\n\n{TEMPLATE_TEXT}")
        return

    formatted = data["formatted"]

    # В модерацию кладём:
    # - sender_id (служебно)
    # - блок контента (то, что пойдёт в канал)
    # - кнопки
    mod_text = (
        "🛡 Заявка на публикацию (проверка пройдена)\n"
        f"sender_id: {m.from_user.id}\n\n"
        "===CONTENT===\n"
        f"{formatted}\n"
        "===/CONTENT===\n"
    )

    msg = await bot.send_message(MOD_CHAT_ID, mod_text, reply_markup=mod_kb(request_id=0))
    request_id = msg.message_id

    # обновляем кнопки с правильным request_id
    await bot.edit_message_reply_markup(
        chat_id=MOD_CHAT_ID,
        message_id=request_id,
        reply_markup=mod_kb(request_id=request_id)
    )

    await m.answer("✅ Принято. Отправлено на модерацию.")


# ----------------- moderation actions -----------------
@dp.callback_query(F.data.startswith("approve:"))
async def approve(cq: CallbackQuery):
    if not await is_chat_admin(cq.from_user.id, MOD_CHAT_ID):
        await cq.answer("Нет доступа (только админы чата модерации).", show_alert=True)
        return

    request_id = int(cq.data.split(":")[1])
    moderation_text = cq.message.text or ""

    sender_id = extract_sender_id(moderation_text)
    content = extract_formatted_block(moderation_text)

    ok, err = await publish_to_channel(content)

    if ok:
        await cq.message.edit_text(
            f"✅ ОДОБРЕНО и ОПУБЛИКОВАНО (заявка #{request_id})\n\n"
            f"{moderation_text}"
        )
        await cq.answer("Опубликовано ✅")
        if sender_id:
            try:
                await bot.send_message(sender_id, "✅ Ваша заявка одобрена и опубликована.")
            except Exception:
                pass
    else:
        await cq.message.edit_text(
            f"✅ ОДОБРЕНО, но ПУБЛИКАЦИЯ НЕ УДАЛАСЬ (заявка #{request_id})\n"
            f"⚠️ Ошибка: {err}\n\n"
            f"{moderation_text}"
        )
        await cq.answer("Одобрено, но ошибка публикации ⚠️", show_alert=True)
        if sender_id:
            try:
                await bot.send_message(sender_id, "⚠️ Заявка одобрена, но публикация в канал не удалась. Модератор видит причину.")
            except Exception:
                pass


@dp.callback_query(F.data.startswith("reject:"))
async def reject(cq: CallbackQuery):
    if not await is_chat_admin(cq.from_user.id, MOD_CHAT_ID):
        await cq.answer("Нет доступа (только админы чата модерации).", show_alert=True)
        return

    request_id = int(cq.data.split(":")[1])
    moderation_text = cq.message.text or ""
    sender_id = extract_sender_id(moderation_text)

    await cq.message.edit_text(f"❌ ОТКЛОНЕНО (заявка #{request_id})\n\n{moderation_text}")
    await cq.answer("Отклонено ❌")

    if sender_id:
        try:
            await bot.send_message(sender_id, "❌ Ваша заявка отклонена модератором.")
        except Exception:
            pass


# ----------------- HTTP for Render -----------------
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
