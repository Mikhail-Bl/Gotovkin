import os
import json
import random
import asyncio
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# chat_id -> {"menu_id": int|None, "answer_id": int|None}
ui_state: dict[int, dict[str, int | None]] = defaultdict(lambda: {"menu_id": None, "answer_id": None})


# ---------------- UI helpers ----------------
def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Random", callback_data="act:random")],
            [InlineKeyboardButton(text="Pick", callback_data="act:pick")],
        ]
    )


def kb_categories() -> InlineKeyboardMarkup:
    rows = []
    for cat in CATEGORIES:
        rows.append([InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}")])
    rows.append([InlineKeyboardButton(text="Main menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_count(cat: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1", callback_data=f"cnt:{cat}:1"),
                InlineKeyboardButton(text="3", callback_data=f"cnt:{cat}:3"),
                InlineKeyboardButton(text="6", callback_data=f"cnt:{cat}:6"),
            ],
            [InlineKeyboardButton(text="Main menu", callback_data="menu:main")],
        ]
    )


async def safe_delete(chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass


async def ensure_menu_message(chat_id: int) -> None:
    """
    Гарантирует наличие одного сообщения-меню.
    Если меню уже есть — обновляет текст/кнопки через edit.
    Если меню нет — отправляет новое.
    """
    menu_id = ui_state[chat_id]["menu_id"]
    if menu_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=menu_id,
                text="Main menu",
                reply_markup=kb_main_menu(),
            )
            return
        except TelegramBadRequest:
            ui_state[chat_id]["menu_id"] = None

    msg = await bot.send_message(chat_id, "Main menu", reply_markup=kb_main_menu())
    ui_state[chat_id]["menu_id"] = msg.message_id


async def set_menu_to_categories(chat_id: int) -> None:
    await ensure_menu_message(chat_id)
    menu_id = ui_state[chat_id]["menu_id"]
    if not menu_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=menu_id,
            text="Choose category",
            reply_markup=kb_categories(),
        )
    except TelegramBadRequest:
        ui_state[chat_id]["menu_id"] = None
        await ensure_menu_message(chat_id)
        await set_menu_to_categories(chat_id)


async def set_menu_to_count(chat_id: int, cat: str) -> None:
    await ensure_menu_message(chat_id)
    menu_id = ui_state[chat_id]["menu_id"]
    if not menu_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=menu_id,
            text=f"Category: {cat}\nHow many dishes?",
            reply_markup=kb_count(cat),
        )
    except TelegramBadRequest:
        ui_state[chat_id]["menu_id"] = None
        await ensure_menu_message(chat_id)
        await set_menu_to_count(chat_id, cat)


async def replace_answer(chat_id: int, text: str) -> None:
    """
    Держит в чате только два сообщения от бота:
    1) answer (последний ответ)
    2) menu (сообщение с выбором)
    """
    await safe_delete(chat_id, ui_state[chat_id]["answer_id"])
    msg = await bot.send_message(chat_id, text)
    ui_state[chat_id]["answer_id"] = msg.message_id


def pick_random_one() -> dict:
    return random.choice(DISHES)


def pick_many(cat: str, n: int) -> list[dict]:
    pool = BY_CAT.get(cat, [])
    if not pool:
        return []
    return random.sample(pool, min(n, len(pool)))


# ---------------- Handlers ----------------
@dp.message(CommandStart())
async def on_start(message: Message):
    chat_id = message.chat.id
    # Чистка бот-сообщений при старте
    await safe_delete(chat_id, ui_state[chat_id]["answer_id"])
    await safe_delete(chat_id, ui_state[chat_id]["menu_id"])
    ui_state[chat_id]["answer_id"] = None
    ui_state[chat_id]["menu_id"] = None

    await replace_answer(chat_id, "Gotovkin online")
    await ensure_menu_message(chat_id)


@dp.callback_query(F.data == "menu:main")
async def on_menu_main(cq: CallbackQuery):
    chat_id = cq.message.chat.id
    await ensure_menu_message(chat_id)
    await cq.answer()


@dp.callback_query(F.data == "act:random")
async def on_random(cq: CallbackQuery):
    chat_id = cq.message.chat.id
    d = pick_random_one()
    await replace_answer(chat_id, f"{d['name']} — {d['category']}")
    await ensure_menu_message(chat_id)
    await cq.answer()


@dp.callback_query(F.data == "act:pick")
async def on_pick(cq: CallbackQuery):
    chat_id = cq.message.chat.id
    await set_menu_to_categories(chat_id)
    await cq.answer()


@dp.callback_query(F.data.startswith("cat:"))
async def on_category(cq: CallbackQuery):
    chat_id = cq.message.chat.id
    cat = cq.data.split(":", 1)[1]
    await set_menu_to_count(chat_id, cat)
    await cq.answer()


@dp.callback_query(F.data.startswith("cnt:"))
async def on_count(cq: CallbackQuery):
    chat_id = cq.message.chat.id
    _, cat, n_str = cq.data.split(":", 2)
    n = int(n_str)

    dishes = pick_many(cat, n)
    if not dishes:
        await replace_answer(chat_id, f"No dishes in category: {cat}")
    else:
        lines = [f"Category: {cat}", ""]
        for i, d in enumerate(dishes, 1):
            lines.append(f"{i}. {d['name']}")
        await replace_answer(chat_id, "\n".join(lines))

    await ensure_menu_message(chat_id)
    await cq.answer()


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
