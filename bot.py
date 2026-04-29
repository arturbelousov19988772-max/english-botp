import asyncio
import random
import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv

# Загружаем токен из .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Словарь слов (можешь дополнять)
words = {
    "apple": "яблоко",
    "dog": "собака",
    "cat": "кот",
    "car": "машина"
}

# Состояния пользователей
user_state = {}


def get_user(user_id):
    if user_id not in user_state:
        user_state[user_id] = {
            "current_word": None,
            "waiting_answer": False,
            "auto_mode": False
        }
    return user_state[user_id]


async def ask_word(user_id):
    user = get_user(user_id)

    word = random.choice(list(words.keys()))
    user["current_word"] = word
    user["waiting_answer"] = True

    await bot.send_message(user_id, f"Переведи: {word}")


# --- Команды ---

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Привет!\n\n"
        "/quiz — начать тест\n"
        "/start_auto — авто режим (каждые 3 минуты)\n"
        "/stop_auto — остановить авто режим"
    )


@dp.message(Command("quiz"))
async def quiz(message: Message):
    await ask_word(message.from_user.id)


@dp.message(Command("start_auto"))
async def start_auto(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)

    if user["auto_mode"]:
        await message.answer("Авто режим уже включён")
        return

    user["auto_mode"] = True
    await message.answer("Авто режим включён ✅")

    asyncio.create_task(auto_quiz(user_id))


@dp.message(Command("stop_auto"))
async def stop_auto(message: Message):
    user = get_user(message.from_user.id)
    user["auto_mode"] = False

    await message.answer("Авто режим выключен ❌")


# --- Проверка ответа ---

@dp.message()
async def check_answer(message: Message):
    user = get_user(message.from_user.id)

    if not user["waiting_answer"]:
        return

    correct = words[user["current_word"]]

    if message.text.lower().strip() == correct:
        await message.answer("Правильно ✅")
        user["waiting_answer"] = False

        if user["auto_mode"]:
            await asyncio.sleep(1)
            await ask_word(message.from_user.id)
    else:
        await message.answer("Неправильно ❌ Попробуй ещё раз")


# --- Авто режим ---

async def auto_quiz(user_id):
    while True:
        user = get_user(user_id)

        if not user["auto_mode"]:
            break

        if not user["waiting_answer"]:
            await ask_word(user_id)

        await asyncio.sleep(180) # 3 минуты


# --- Запуск ---

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())