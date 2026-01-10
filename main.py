import os
import json
import random
import asyncio
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

BOT_TOKEN = os.getenv("8327321881:AAGxajMRvCluTZQrKLgM5finfPaJwsozQIo")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

DISHES_PATH = "dishes.json"

with open(DISHES_PATH, "r", encoding="utf-8") as f:
    DISHES = json.load(f)

BY_CAT = defaultdict(list)
for d in DISHES:
    BY_CAT[d["category"]].append(d)

CATEGORIES = sorted(BY_CAT.keys())

def kb_categories():
    rows = [[InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}")]
            for cat in CATEGORIES]
    rows.append([InlineKeyboardButton(
        text="🍀 Случайное из всего",
        callback_data="cat:__ALL__"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_count(cat: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="1", callback_data=f"cnt:{cat}:1"),
        InlineKeyboardButton(text="3", callback_data=f"cnt:{cat}:3"),
        InlineKeyboardButton(text="6", callback_data=f"cnt:{cat}:6"),
    ]])

def pick(cat: str, n: int):
    pool = DISHES if cat == "__ALL__" else BY_CAT.get(cat, [])
    return random.sample(pool, min(n, len(pool))) if pool else []

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Я Готовкин 👨‍🍳\n"
        "Твой кухонный навигатор.\n\n"
        "Команды:\n"
        "/random — что-нибудь приготовить без раздумий\n"
        "/pick — выбрать блюда по категории"
    )

@dp.message(Command("random"))
async def random_one(message: Message):
    d = random.choice(DISHES)
    await message.answer(
        "Готовкин подумал 🤔\n\n"
        f"Сегодня готовим:\n{d['name']} — {d['category']}"
    )

@dp.message(Command("pick"))
async def choose_category(message: Message):
    await message.answer(
        "Готовкин открывает книгу рецептов 📖\n"
        "Выбери категорию:",
        reply_markup=kb_categories()
    )

@dp.callback_query(F.data.startswith("cat:"))
async def on_category(cq: CallbackQuery):
    cat = cq.data.split(":", 1)[1]
    text = "из всех категорий" if cat == "__ALL__" else f"из категории «{cat}»"
    await cq.message.answer(
        f"Сколько вариантов показать {text}?",
        reply_markup=kb_count(cat)
    )
    await cq.answer()

@dp.callback_query(F.data.startswith("cnt:"))
async def on_count(cq: CallbackQuery):
    _, cat, n_str = cq.data.split(":", 2)
    n = int(n_str)
    dishes = pick(cat, n)

    header = (
        "Готовкин бросил кости 🎲\n"
        "Вот что можно приготовить:"
        if cat == "__ALL__"
        else f"Готовкин подобрал варианты 🎯\nКатегория: {cat}"
    )

    lines = [header, ""]
    for i, d in enumerate(dishes, 1):
        lines.append(f"{i}. {d['name']}")

    await cq.message.answer("\n".join(lines))
    await cq.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
