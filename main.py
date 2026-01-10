import os
import json
import random
import asyncio
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

DISHES_PATH = "dishes.json"

with open(DISHES_PATH, "r", encoding="utf-8") as f:
    DISHES = json.load(f)

BY_CAT = defaultdict(list)
for d in DISHES:
    BY_CAT[d["category"]].append(d)

CATEGORIES = sorted(BY_CAT.keys())

# ====== Хранилище истории message_id для удаления ======
# Храним только последние N message_id на чат, чтобы не раздувать память.
MAX_TRACKED_PER_CHAT = 400
tracked_ids: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=MAX_TRACKED_PER_CHAT))

def track(chat_id: int, message_id: int) -> None:
    tracked_ids[chat_id].append(message_id)

# ====== Клавиатуры ======
def kb_main_menu():
    rows = [[InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}")]
            for cat in CATEGORIES]
    rows.append([InlineKeyboardButton(text="Случайное из всех", callback_data="cat:__ALL__")])
    rows.append([InlineKeyboardButton(text="Удалить историю", callback_data="hist:clear")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_count(cat: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data=f"cnt:{cat}:1"),
            InlineKeyboardButton(text="3", callback_data=f"cnt:{cat}:3"),
            InlineKeyboardButton(text="6", callback_data=f"cnt:{cat}:6"),
        ],
        [InlineKeyboardButton(text="Главное меню", callback_data="menu:main")]
    ])

def kb_after_results():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Главное меню", callback_data="menu:main")],
        [InlineKeyboardButton(text="Удалить историю", callback_data="hist:clear")]
    ])

def pick(cat: str, n: int):
    pool = DISHES if cat == "__ALL__" else BY_CAT.get(cat, [])
    if not pool:
        return []
    return random.sample(pool, min(n, len(pool)))

# ====== Бот ======
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def show_main_menu(chat_id: int):
    text = (
        "Я Готовкин.\n"
        "Главное меню:\n"
        "1) Выбери категорию\n"
        "2) Или возьми случайное из всех\n"
        "3) Или удали историю сообщений"
    )
    msg = await bot.send_message(chat_id, text, reply_markup=kb_main_menu())
    track(chat_id, msg.message_id)

@dp.message(CommandStart())
async def start(message: Message):
    track(message.chat.id, message.message_id)
    msg = await message.answer(
        "Я Готовкин.\n"
        "Помогаю выбрать, что приготовить.\n"
        "Команды:\n"
        "/menu — главное меню\n"
        "/random — одно случайное блюдо"
    )
    track(message.chat.id, msg.message_id)
    await show_main_menu(message.chat.id)

@dp.message(Command("menu"))
async def menu_cmd(message: Message):
    track(message.chat.id, message.message_id)
    await show_main_menu(message.chat.id)

@dp.message(Command("random"))
async def random_one(message: Message):
    track(message.chat.id, message.message_id)
    d = random.choice(DISHES)
    msg = await message.answer(f"Готовим: {d['name']} ({d['category']})", reply_markup=kb_after_results())
    track(message.chat.id, msg.message_id)

@dp.callback_query(F.data == "menu:main")
async def on_main_menu(cq: CallbackQuery):
    track(cq.message.chat.id, cq.message.message_id)
    await show_main_menu(cq.message.chat.id)
    await cq.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def on_category(cq: CallbackQuery):
    chat_id = cq.message.chat.id
    track(chat_id, cq.message.message_id)

    cat = cq.data.split(":", 1)[1]
    title = "всех категорий" if cat == "__ALL__" else f"категории «{cat}»"

    msg = await cq.message.answer(
        f"Сколько блюд показать из {title}?",
        reply_markup=kb_count(cat)
    )
    track(chat_id, msg.message_id)
    await cq.answer()

@dp.callback_query(F.data.startswith("cnt:"))
async def on_count(cq: CallbackQuery):
    chat_id = cq.message.chat.id
    track(chat_id, cq.message.message_id)

    _, cat, n_str = cq.data.split(":", 2)
    n = int(n_str)
    dishes = pick(cat, n)

    if cat == "__ALL__":
        header = f"Подборка ({n}) из всех категорий:"
    else:
        header = f"Подборка ({n}) из категории «{cat}»:"

    lines = [header]
    for i, d in enumerate(dishes, 1):
        lines.append(f"{i}. {d['name']}")

    msg = await cq.message.answer("\n".join(lines), reply_markup=kb_after_results())
    track(chat_id, msg.message_id)
    await cq.answer()

# ====== Удаление истории ======
async def delete_tracked_history(chat_id: int) -> int:
    """
    Пытается удалить все message_id, которые бот успел записать для chat_id.
    Telegram накладывает ограничения (например, ~48 часов и типы сообщений).
    deleteMessages пропускает несуществующие/недоступные сообщения. :contentReference[oaicite:2]{index=2}
    """
    ids = list(tracked_ids.get(chat_id, []))
    if not ids:
        return 0

    deleted_attempted = 0

    # На практике безопасно удалять чанками (типичные лимиты на размер списка).
    CHUNK = 100
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=chunk)
            deleted_attempted += len(chunk)
        except TelegramBadRequest:
            # Часть сообщений может быть неудаляемой (старые, сервисные и т.д.). :contentReference[oaicite:3]{index=3}
            # Падающие чанки режем на одиночные, чтобы удалить то, что можно.
            for mid in chunk:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=mid)
                    deleted_attempted += 1
                except TelegramBadRequest:
                    pass

    tracked_ids[chat_id].clear()
    return deleted_attempted

@dp.callback_query(F.data == "hist:clear")
async def on_clear_history(cq: CallbackQuery):
    chat_id = cq.message.chat.id
    # Текущий message_id тоже добавляем, чтобы он попал в удаление
    track(chat_id, cq.message.message_id)

    await cq.answer()
    await delete_tracked_history(chat_id)

    # После удаления истории — новое “чистое” сообщение и меню
    await show_main_menu(chat_id)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
