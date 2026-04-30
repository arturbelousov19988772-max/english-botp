import asyncio
import random
import os
import sqlite3
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from dotenv import load_dotenv
from contextlib import contextmanager

# Пытаемся импортировать дополнительные библиотеки
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ PIL не установлен. Функция распознавания фото будет недоступна.")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    print("⚠️ pytesseract не установлен. Функция распознавания фото будет недоступна.")

try:
    from googletrans import Translator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    print("⚠️ googletrans не установлен. Автоперевод будет недоступен.")

# Инициализация переводчика если доступен
translator = Translator() if TRANSLATOR_AVAILABLE else None

# ---------------- INIT ----------------

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("Ошибка: BOT_TOKEN не найден в .env файле")
    exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB = "bot.db"

# ---------------- DB ----------------

@contextmanager
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def migrate_db():
    with get_db() as db:
        existing_columns = [col[1] for col in db.execute("PRAGMA table_info(users)")]
        
        columns_to_add = [
            ("add_mode", "TEXT DEFAULT 'none'"),
            ("temp_eng", "TEXT"),
            ("temp_ru", "TEXT"),
            ("quiz_mode", "TEXT DEFAULT 'multiple'"),
            ("correct", "INTEGER DEFAULT 0"),
            ("wrong", "INTEGER DEFAULT 0"),
            ("username", "TEXT"),
            ("first_name", "TEXT"),
            ("auto_mode", "INTEGER DEFAULT 0")
        ]
        
        for col_name, col_type in columns_to_add:
            if col_name not in existing_columns:
                try:
                    db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass
        
        # Добавляем колонку для транскрипции
        try:
            db.execute("ALTER TABLE user_words ADD COLUMN transcription TEXT")
        except sqlite3.OperationalError:
            pass
        
        db.commit()

def init_db():
    with get_db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            wrong INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0
        )
        """)
        
        db.execute("""
        CREATE TABLE IF NOT EXISTS user_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            eng TEXT,
            ru TEXT,
            transcription TEXT,
            word_type TEXT DEFAULT 'word',
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(user_id, eng, ru)
        )
        """)
        
        db.commit()
    
    migrate_db()
    print("База данных готова")

# ---------------- ФУНКЦИИ ДЛЯ ТРАНСКРИПЦИИ ----------------

def get_transcription(word):
    """Получает транскрипцию слова используя простые правила"""
    transcription_rules = {
        'a': 'ə', 'e': 'e', 'i': 'ɪ', 'o': 'ɒ', 'u': 'ʌ',
        'apple': 'ˈæp.əl', 'cat': 'kæt', 'dog': 'dɒg', 'car': 'kɑː',
        'house': 'haʊs', 'hello': 'həˈləʊ', 'world': 'wɜːld',
        'time': 'taɪm', 'day': 'deɪ', 'night': 'naɪt',
        'good': 'ɡʊd', 'bad': 'bæd', 'big': 'bɪɡ', 'small': 'smɔːl',
        'book': 'bʊk', 'pen': 'pen', 'school': 'skuːl', 'teacher': 'ˈtiːtʃə',
        'student': 'ˈstjuːdənt', 'friend': 'frend', 'love': 'lʌv', 'happy': 'ˈhæpi'
    }
    
    word_lower = word.lower()
    if word_lower in transcription_rules:
        return transcription_rules[word_lower]
    elif len(word) < 6:
        return f"[{word_lower}]"
    else:
        return f"/{word_lower}/"

def add_transcription_to_word(word):
    return get_transcription(word)

# ---------------- ФУНКЦИИ ДЛЯ РАСПОЗНАВАНИЯ ТЕКСТА С ФОТО ----------------

async def extract_text_from_image(photo_data):
    """Извлекает текст из изображения если доступны библиотеки"""
    if not PIL_AVAILABLE or not TESSERACT_AVAILABLE:
        return None
    
    try:
        image = Image.open(io.BytesIO(photo_data))
        image = image.convert('L')
        image = image.point(lambda x: 0 if x < 128 else 255)
        text = pytesseract.image_to_string(image, lang='eng+rus')
        text = ' '.join(text.split())
        return text.strip()
    except Exception as e:
        print(f"Ошибка OCR: {e}")
        return None

async def parse_words_from_text(text):
    """Парсит слова и переводы из текста"""
    words = []
    
    patterns = [
        r'([a-zA-Z\s]+)\s*[-=:]\s*([а-яА-ЯёЁ\s,]+)',
        r'([a-zA-Z\s]+)\s*[-=:]\s*([a-zA-Z\s]+)'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.MULTILINE)
        for eng, ru in matches:
            eng = eng.strip().lower()
            ru = ru.strip()
            if eng and ru and len(eng) < 50 and len(ru) < 100:
                words.append((eng, ru))
    
    # Пытаемся перевести слова если нет пар
    if not words and translator and TRANSLATOR_AVAILABLE:
        words_en = re.findall(r'\b[a-zA-Z]{3,}\b', text)
        for eng in words_en[:5]:
            try:
                translated = await translator.translate(eng, src='en', dest='ru')
                words.append((eng.lower(), translated.text))
            except:
                words.append((eng.lower(), "???"))
    
    return words

# ---------------- CRUD операции ----------------

def add_user(user_id, username=None, first_name=None):
    with get_db() as db:
        try:
            db.execute("""
                INSERT OR IGNORE INTO users (user_id, username, first_name, wrong, correct, auto_mode) 
                VALUES (?, ?, ?, 0, 0, 0)
            """, (user_id, username, first_name))
            db.commit()
        except:
            db.execute("""
                INSERT OR IGNORE INTO users (user_id, wrong, correct, auto_mode) 
                VALUES (?, 0, 0, 0)
            """, (user_id,))
            db.commit()

def add_word_to_user(user_id, eng, ru, word_type='word'):
    with get_db() as db:
        try:
            transcription = add_transcription_to_word(eng)
            db.execute("""
                INSERT INTO user_words (user_id, eng, ru, transcription, word_type) 
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, eng.lower().strip(), ru.strip(), transcription, word_type))
            db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def get_word_transcriptions(user_id, eng):
    with get_db() as db:
        cur = db.execute("""
            SELECT transcription FROM user_words 
            WHERE user_id = ? AND eng = ?
            LIMIT 1
        """, (user_id, eng.lower().strip()))
        result = cur.fetchone()
        return result['transcription'] if result else None

def get_word_translations(user_id, eng):
    with get_db() as db:
        cur = db.execute("""
            SELECT ru, transcription FROM user_words 
            WHERE user_id = ? AND eng = ?
        """, (user_id, eng.lower().strip()))
        return [(row['ru'], row['transcription']) for row in cur.fetchall()]

def add_batch_words_to_user(user_id, words_list):
    added = 0
    with get_db() as db:
        for eng, ru in words_list:
            try:
                transcription = add_transcription_to_word(eng)
                db.execute("""
                    INSERT INTO user_words (user_id, eng, ru, transcription, word_type) 
                    VALUES (?, ?, ?, ?, 'word')
                """, (user_id, eng.lower().strip(), ru.strip(), transcription))
                added += 1
            except:
                pass
        db.commit()
    return added

def get_user_words(user_id):
    with get_db() as db:
        cur = db.execute("""
            SELECT DISTINCT eng FROM user_words 
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        words = []
        for row in cur.fetchall():
            translations = get_word_translations(user_id, row['eng'])
            words.append((row['eng'], [t[0] for t in translations]))
        return words

def get_random_user_word(user_id):
    words = get_user_words(user_id)
    if not words:
        return None
    eng, translations = random.choice(words)
    transcription = get_word_transcriptions(user_id, eng)
    return (eng, translations, transcription)

def count_user_words(user_id):
    with get_db() as db:
        cur = db.execute("SELECT COUNT(DISTINCT eng) as count FROM user_words WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
        return result['count'] if result else 0

def update_word_stats(user_id, eng, is_correct):
    with get_db() as db:
        if is_correct:
            db.execute("""
                UPDATE user_words 
                SET correct_count = correct_count + 1 
                WHERE user_id = ? AND eng = ?
            """, (user_id, eng))
        else:
            db.execute("""
                UPDATE user_words 
                SET wrong_count = wrong_count + 1 
                WHERE user_id = ? AND eng = ?
            """, (user_id, eng))
        db.commit()

def update_user_stats(user_id, is_correct):
    with get_db() as db:
        if is_correct:
            db.execute("UPDATE users SET correct = correct + 1 WHERE user_id = ?", (user_id,))
        else:
            db.execute("UPDATE users SET wrong = wrong + 1 WHERE user_id = ?", (user_id,))
        db.commit()

def get_user_stats(user_id):
    with get_db() as db:
        cur = db.execute("SELECT wrong, correct FROM users WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
        if not result:
            return {'wrong': 0, 'correct': 0}
        return result

def update_user_mode(user_id, mode, temp_eng=None):
    with get_db() as db:
        try:
            if temp_eng:
                db.execute("UPDATE users SET add_mode = ?, temp_eng = ? WHERE user_id = ?", (mode, temp_eng, user_id))
            else:
                db.execute("UPDATE users SET add_mode = ? WHERE user_id = ?", (mode, user_id))
            db.commit()
        except:
            if temp_eng:
                db.execute("UPDATE users SET add_mode = ?, temp_eng = ? WHERE user_id = ?", (mode, temp_eng, user_id))
            else:
                db.execute("UPDATE users SET add_mode = ? WHERE user_id = ?", (mode, user_id))
            db.commit()

def get_user_mode(user_id):
    with get_db() as db:
        try:
            cur = db.execute("SELECT add_mode, temp_eng, quiz_mode, auto_mode FROM users WHERE user_id = ?", (user_id,))
            result = cur.fetchone()
            if not result:
                add_user(user_id)
                return {'add_mode': 'none', 'temp_eng': None, 'quiz_mode': 'multiple', 'auto_mode': 0}
            return result
        except:
            add_user(user_id)
            return {'add_mode': 'none', 'temp_eng': None, 'quiz_mode': 'multiple', 'auto_mode': 0}

def update_quiz_mode(user_id, mode):
    with get_db() as db:
        try:
            db.execute("UPDATE users SET quiz_mode = ? WHERE user_id = ?", (mode, user_id))
            db.commit()
        except:
            db.execute("UPDATE users SET quiz_mode = ? WHERE user_id = ?", (mode, user_id))
            db.commit()

def update_auto_mode(user_id, enabled):
    with get_db() as db:
        try:
            db.execute("UPDATE users SET auto_mode = ? WHERE user_id = ?", (1 if enabled else 0, user_id))
            db.commit()
        except:
            db.execute("UPDATE users SET auto_mode = ? WHERE user_id = ?", (1 if enabled else 0, user_id))
            db.commit()

def get_auto_mode(user_id):
    with get_db() as db:
        try:
            cur = db.execute("SELECT auto_mode FROM users WHERE user_id = ?", (user_id,))
            result = cur.fetchone()
            return result['auto_mode'] == 1 if result else False
        except:
            return False

def delete_word(user_id, eng):
    with get_db() as db:
        db.execute("DELETE FROM user_words WHERE user_id = ? AND eng = ?", (user_id, eng.lower().strip()))
        db.commit()
        return db.total_changes > 0

# ---------------- STATE ----------------

state = {}

def get_state(uid):
    if uid not in state:
        state[uid] = {
            "current": None,
            "current_eng": None,
            "current_translations": None,
            "current_transcription": None,
            "waiting": False,
            "waiting_for_answer": False
        }
    return state[uid]

# ---------------- AUTO MODE ----------------

auto_tasks = {}

async def auto_quiz(user_id):
    while True:
        try:
            if not get_auto_mode(user_id):
                break
            
            word_data = get_random_user_word(user_id)
            
            if word_data:
                eng, translations, transcription = word_data
                translations_text = ", ".join(translations)
                
                if transcription:
                    await bot.send_message(
                        user_id,
                        f"📖 *{eng}*\n`{transcription}`\n\n||{translations_text}||",
                        parse_mode="MarkdownV2"
                    )
                else:
                    await bot.send_message(
                        user_id,
                        f"📖 *{eng}*\n\n||{translations_text}||",
                        parse_mode="MarkdownV2"
                    )
            else:
                await bot.send_message(user_id, "📚 Словарь пуст. Добавьте слова через '➕ Добавить'")
                update_auto_mode(user_id, False)
                break
            
            await asyncio.sleep(120)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Ошибка в авторежиме: {e}")
            await asyncio.sleep(120)

def start_auto_mode(user_id):
    if user_id in auto_tasks:
        try:
            auto_tasks[user_id].cancel()
        except:
            pass
    
    task = asyncio.create_task(auto_quiz(user_id))
    auto_tasks[user_id] = task

def stop_auto_mode(user_id):
    if user_id in auto_tasks:
        try:
            auto_tasks[user_id].cancel()
        except:
            pass
        finally:
            if user_id in auto_tasks:
                del auto_tasks[user_id]

# ---------------- QUIZ ----------------

def keyboard(correct, wrongs):
    buttons = [correct] + wrongs
    random.shuffle(buttons)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=b[:40], callback_data=f"ans:{b[:40]}")]
        for b in buttons
    ])

async def ask_multiple(uid):
    word_data = get_random_user_word(uid)
    if not word_data:
        await bot.send_message(uid, "📚 Словарь пуст")
        return False

    eng, translations, transcription = word_data
    correct_ru = random.choice(translations)
    
    st = get_state(uid)
    st["current"] = (eng, correct_ru)
    st["current_eng"] = eng
    st["current_translations"] = translations
    st["current_transcription"] = transcription
    st["waiting"] = True
    st["waiting_for_answer"] = False

    user_words = get_user_words(uid)
    all_translations = []
    for w, trans in user_words:
        all_translations.extend(trans)
    
    wrongs = [t for t in all_translations if t != correct_ru]
    wrongs = list(set(wrongs))
    
    if len(wrongs) < 2:
        wrongs = ["Не знаю", "Затрудняюсь"]
    else:
        wrongs = random.sample(wrongs, min(2, len(wrongs)))

    msg = f"📖 *{eng}*"
    if transcription:
        msg += f"\n`{transcription}`"
    
    await bot.send_message(
        uid,
        msg,
        parse_mode="Markdown",
        reply_markup=keyboard(correct_ru, wrongs)
    )
    return True

async def ask_typing(uid):
    word_data = get_random_user_word(uid)
    if not word_data:
        await bot.send_message(uid, "📚 Словарь пуст")
        return False

    eng, translations, transcription = word_data
    
    st = get_state(uid)
    st["current"] = (eng, translations)
    st["current_eng"] = eng
    st["current_translations"] = translations
    st["current_transcription"] = transcription
    st["waiting_for_answer"] = True
    st["waiting"] = False

    msg = f"✏️ *{eng}*"
    if transcription:
        msg += f"\n`{transcription}`"
    
    await bot.send_message(uid, msg, parse_mode="Markdown")
    return True

async def ask(uid):
    user_data = get_user_mode(uid)
    quiz_mode = user_data['quiz_mode']
    
    if quiz_mode == "multiple":
        return await ask_multiple(uid)
    else:
        return await ask_typing(uid)

# ---------------- СПИСОК СЛОВ С ПАГИНАЦИЕЙ ----------------

words_per_page = 8

def get_words_page(user_id, page):
    words = get_user_words(user_id)
    total_pages = (len(words) + words_per_page - 1) // words_per_page
    
    start = (page - 1) * words_per_page
    end = start + words_per_page
    page_words = words[start:end]
    
    return page_words, total_pages

def create_list_keyboard(user_id, page, total_pages):
    keyboard = []
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"list_page:{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="list_none"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"list_page:{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="list_close")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def show_words_list(user_id, page=1):
    words = get_user_words(user_id)
    if not words:
        await bot.send_message(user_id, "📚 Словарь пуст. Добавьте слова через '➕ Добавить'")
        return
    
    total_pages = (len(words) + words_per_page - 1) // words_per_page
    
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    
    page_words, _ = get_words_page(user_id, page)
    start_num = (page - 1) * words_per_page + 1
    
    msg = f"📚 *Мои слова* • {len(words)}\n\n"
    
    for i, (eng, translations) in enumerate(page_words, start_num):
        trans = ", ".join(translations[:3])
        if len(translations) > 3:
            trans += f" (+{len(translations)-3})"
        transcription = get_word_transcriptions(user_id, eng)
        if transcription:
            msg += f"`{i}.` *{eng}* `{transcription}` → {trans}\n"
        else:
            msg += f"`{i}.` *{eng}* → {trans}\n"
    
    keyboard = create_list_keyboard(user_id, page, total_pages)
    await bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=keyboard)

# ---------------- КОМАНДЫ И МЕНЮ ----------------

async def set_commands():
    commands = [
        BotCommand(command="start", description="🌱 Главное меню"),
        BotCommand(command="quiz", description="🎯 Начать викторину"),
        BotCommand(command="auto", description="🔄 Авто-режим"),
        BotCommand(command="stop", description="⏹️ Остановить"),
        BotCommand(command="add", description="➕ Добавить слово"),
        BotCommand(command="addbatch", description="📦 Добавить список"),
        BotCommand(command="mode", description="🎮 Сменить режим"),
        BotCommand(command="stats", description="📊 Моя статистика"),
        BotCommand(command="list", description="📚 Список слов"),
        BotCommand(command="delete", description="🗑️ Удалить слово"),
        BotCommand(command="cancel", description="❌ Отмена")
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

@dp.message(Command("start"))
async def start(m: Message):
    user_id = m.from_user.id
    add_user(user_id, m.from_user.username, m.from_user.first_name)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎯 Учить"), KeyboardButton(text="🔄 Авто"), KeyboardButton(text="⏹️ Стоп")],
            [KeyboardButton(text="➕ Добавить"), KeyboardButton(text="📦 Список"), KeyboardButton(text="📚 Слова")],
            [KeyboardButton(text="🗑️ Удалить"), KeyboardButton(text="🎮 Регим"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    
    word_count = count_user_words(user_id)
    
    photo_status = "✅" if (PIL_AVAILABLE and TESSERACT_AVAILABLE) else "❌"
    
    await m.answer(
        f"👋 *{m.from_user.first_name}*\n\n"
        f"📚 Слов в словаре: *{word_count}*\n\n"
        f"🎯 *Учить* — викторина\n"
        f"🔄 *Авто* — каждые 2 минуты\n"
        f"➕ *Добавить* — новое слово\n"
        f"📚 *Слова* — посмотреть все\n"
        f"📷 *Фото* — распознать с картинки {photo_status}\n\n"
        f"💡 *Совет:* При добавлении слов можно указывать несколько переводов через запятую\n"
        f"📝 *Транскрипция* добавляется автоматически",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ---------------- ОБРАБОТКА ФОТО ----------------

@dp.message(Command("photo"))
async def photo_mode(m: Message):
    if not PIL_AVAILABLE or not TESSERACT_AVAILABLE:
        await m.answer(
            "❌ *Функция распознавания фото недоступна*\n\n"
            "Необходимо установить библиотеки:\n"
            "```\npip install pillow pytesseract\n```\n"
            "И установить Tesseract OCR на сервер",
            parse_mode="Markdown"
        )
        return
    
    await m.answer(
        "📷 *Распознавание текста с фото*\n\n"
        "Отправьте фото с текстом на английском\n\n"
        "Поддерживаемые форматы:\n"
        "• `apple - яблоко`\n"
        "• `cat = кошка, кот`\n"
        "• `hello : привет`\n\n"
        "Бот добавит слова с транскрипцией",
        parse_mode="Markdown"
    )

@dp.message(F.photo)
async def handle_photo(m: Message):
    if not PIL_AVAILABLE or not TESSERACT_AVAILABLE:
        await m.answer("❌ Распознавание фото недоступно. Библиотеки не установлены.")
        return
    
    user_id = m.from_user.id
    await m.answer("🔄 Обрабатываю фото...")
    
    try:
        photo = m.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_data = await bot.download_file(file.file_path)
        
        text = await extract_text_from_image(file_data.read())
        
        if not text:
            await m.answer("❌ Не удалось распознать текст на фото.\nПопробуйте фото с более четким текстом")
            return
        
        words = await parse_words_from_text(text)
        
        if not words:
            await m.answer(f"🔍 Распознанный текст:\n`{text[:200]}`\n\n❌ Не удалось найти слова в формате 'слово - перевод'", parse_mode="Markdown")
            return
        
        added = 0
        added_words = []
        for eng, ru in words:
            if add_word_to_user(user_id, eng, ru):
                added += 1
                added_words.append(f"*{eng}* → {ru}")
        
        if added > 0:
            await m.answer(
                f"✅ *Добавлено слов:* {added}\n\n" +
                "\n".join(added_words[:5]) +
                ("\n..." if len(added_words) > 5 else "") +
                f"\n\n📝 Транскрипция добавлена автоматически",
                parse_mode="Markdown"
            )
        else:
            await m.answer("❌ Не удалось добавить слова (возможно, они уже есть в словаре)")
            
    except Exception as e:
        print(f"Ошибка при обработке фото: {e}")
        await m.answer("❌ Произошла ошибка при обработке фото")

@dp.message(F.text == "➕ Добавить")
@dp.message(Command("add"))
async def add_word_start(m: Message):
    uid = m.from_user.id
    update_user_mode(uid, "word_eng")
    await m.answer("✏️ Введите слово на английском:", parse_mode="Markdown")

@dp.message(F.text == "📦 Список")
@dp.message(Command("addbatch"))
async def add_batch_start(m: Message):
    uid = m.from_user.id
    update_user_mode(uid, "batch")
    await m.answer(
        "📦 *Добавление списка слов*\n\n"
        "Отправьте список в формате:\n"
        "`apple - яблоко`\n"
        "`cat - кошка, кот`\n"
        "`hello - привет, здравствуй`\n\n"
        "Транскрипция добавится автоматически\n\n"
        "❌ Отмена: /cancel",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📚 Слова")
@dp.message(Command("list"))
async def list_words(m: Message):
    uid = m.from_user.id
    await show_words_list(uid, 1)

@dp.message(F.text == "🗑️ Удалить")
@dp.message(Command("delete"))
async def delete_word_start(m: Message):
    uid = m.from_user.id
    update_user_mode(uid, "delete")
    await m.answer("🗑️ Введите слово, которое хотите удалить:", parse_mode="Markdown")

@dp.message(F.text == "🎮 Регим")
@dp.message(Command("mode"))
async def mode_menu(m: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Выбор ответа", callback_data="mode_multiple")],
        [InlineKeyboardButton(text="✏️ Ввод ответа", callback_data="mode_typing")]
    ])
    await m.answer("🎮 *Выбери режим обучения:*", parse_mode="Markdown", reply_markup=keyboard)

@dp.message(F.text == "🎯 Учить")
@dp.message(Command("quiz"))
async def quiz(m: Message):
    uid = m.from_user.id
    st = get_state(uid)
    st["waiting"] = False
    st["waiting_for_answer"] = False
    
    if count_user_words(uid) == 0:
        await m.answer("📚 Словарь пуст. Добавьте слова через '➕ Добавить'")
        return
    
    await m.answer("🎯 *Начинаем!*", parse_mode="Markdown")
    await ask(uid)

@dp.message(F.text == "🔄 Авто")
@dp.message(Command("auto"))
async def auto_mode(m: Message):
    uid = m.from_user.id
    
    if count_user_words(uid) == 0:
        await m.answer("📚 Словарь пуст. Добавьте слова через '➕ Добавить'")
        return
    
    update_auto_mode(uid, True)
    start_auto_mode(uid)
    await m.answer(
        "🔄 *Авто-режим включён*\n\n"
        "Каждые 2 минуты новое слово с транскрипцией\n"
        "Перевод скрыт под спойлером\n\n"
        "⏹️ Стоп — выключить",
        parse_mode="Markdown"
    )

@dp.message(F.text == "⏹️ Стоп")
@dp.message(Command("stop"))
async def stop(m: Message):
    uid = m.from_user.id
    st = get_state(uid)
    st["waiting"] = False
    st["waiting_for_answer"] = False
    
    update_auto_mode(uid, False)
    stop_auto_mode(uid)
    await m.answer("⏹️ *Авто-режим выключен*", parse_mode="Markdown")

@dp.message(F.text == "📊 Статистика")
@dp.message(Command("stats"))
async def stats(m: Message):
    uid = m.from_user.id
    stats_data = get_user_stats(uid)
    word_count = count_user_words(uid)
    
    wrong = stats_data['wrong']
    correct = stats_data['correct']
    total = wrong + correct
    accuracy = (correct / total * 100) if total > 0 else 0
    
    user_data = get_user_mode(uid)
    mode = "Выбор" if user_data['quiz_mode'] == "multiple" else "Ввод"
    auto_status = "Вкл" if get_auto_mode(uid) else "Выкл"
    
    await m.answer(
        f"📊 *Статистика*\n\n"
        f"📚 Слов в словаре: *{word_count}*\n"
        f"✅ Верно: *{correct}*\n"
        f"❌ Ошибок: *{wrong}*\n"
        f"🎯 Точность: *{accuracy:.0f}%*\n\n"
        f"🎮 Режим: {mode}\n"
        f"🔄 Авто: {auto_status}",
        parse_mode="Markdown"
    )

@dp.message(F.text == "❌ Отмена")
@dp.message(Command("cancel"))
async def cancel(m: Message):
    uid = m.from_user.id
    update_user_mode(uid, "none")
    st = get_state(uid)
    st["waiting_for_answer"] = False
    st["waiting"] = False
    await m.answer("❌ Отменено", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("list_page:"))
async def list_page_callback(c: CallbackQuery):
    page = int(c.data.split(":")[1])
    uid = c.from_user.id
    await c.message.delete()
    await show_words_list(uid, page)
    await c.answer()

@dp.callback_query(F.data == "list_close")
async def list_close_callback(c: CallbackQuery):
    await c.message.delete()
    await c.answer()

@dp.callback_query(F.data == "list_none")
async def list_none_callback(c: CallbackQuery):
    await c.answer()

@dp.callback_query(F.data.startswith("mode_"))
async def mode_callback(c: CallbackQuery):
    mode = c.data.split("_")[1]
    uid = c.from_user.id
    
    if mode == "multiple":
        update_quiz_mode(uid, "multiple")
        await c.message.edit_text("🎮 Режим: *Выбор ответа*", parse_mode="Markdown")
    else:
        update_quiz_mode(uid, "typing")
        await c.message.edit_text("✏️ Режим: *Ввод ответа*", parse_mode="Markdown")
    
    await c.answer()

@dp.callback_query(F.data.startswith("ans:"))
async def answer_callback(c: CallbackQuery):
    uid = c.from_user.id
    st = get_state(uid)

    if not st.get("waiting", False):
        await c.answer("Нет активного вопроса")
        return

    chosen = c.data.split(":")[1]
    eng, correct_ru = st["current"]
    current_eng = st.get("current_eng", eng)
    all_translations = st.get("current_translations", [correct_ru])

    if chosen == correct_ru:
        update_word_stats(uid, current_eng, True)
        update_user_stats(uid, True)
        trans_text = ", ".join(all_translations)
        await c.message.edit_text(f"✅ *{eng}* → {trans_text}", parse_mode="Markdown")
        st["waiting"] = False
        await asyncio.sleep(0.5)
        await ask(uid)
    else:
        update_word_stats(uid, current_eng, False)
        update_user_stats(uid, False)
        trans_text = ", ".join(all_translations)
        await c.message.edit_text(f"❌ *{eng}* → {trans_text}", parse_mode="Markdown")
        st["waiting"] = False
        await asyncio.sleep(0.5)
        await ask(uid)

# ---------------- ОСНОВНЫЕ ОБРАБОТЧИКИ ----------------

@dp.message(F.text & ~F.text.startswith('/') & ~F.text.in_([
    "🎯 Учить", "🔄 Авто", "➕ Добавить", "📦 Список", "📚 Слова",
    "📊 Статистика", "🎮 Регим", "🗑️ Удалить", "⏹️ Стоп", "❌ Отмена"
]))
async def handle_messages(m: Message):
    uid = m.from_user.id
    user_mode = get_user_mode(uid)
    st = get_state(uid)
    
    # Режим ввода ответа
    if st.get("waiting_for_answer", False):
        eng, correct_translations = st["current"]
        user_answer = m.text.strip().lower()
        
        is_correct = user_answer in [t.lower() for t in correct_translations]
        
        if is_correct:
            update_word_stats(uid, eng, True)
            update_user_stats(uid, True)
            trans_text = ", ".join(correct_translations)
            await m.answer(f"✅ *{eng}* → {trans_text}", parse_mode="Markdown")
            st["waiting_for_answer"] = False
            await asyncio.sleep(0.5)
            await ask(uid)
        else:
            update_word_stats(uid, eng, False)
            update_user_stats(uid, False)
            trans_text = ", ".join(correct_translations)
            await m.answer(f"❌ *{eng}* → {trans_text}\nТвой ответ: {m.text}", parse_mode="Markdown")
        return
    
    # Режим удаления
    if user_mode['add_mode'] == "delete":
        eng = m.text.strip()
        if delete_word(uid, eng):
            await m.answer(f"🗑️ *{eng}* удалено из словаря", parse_mode="Markdown")
        else:
            await m.answer(f"❌ Слово *{eng}* не найдено", parse_mode="Markdown")
        update_user_mode(uid, "none")
        return
    
    # Массовое добавление
    if user_mode['add_mode'] == "batch":
        lines = m.text.strip().split('\n')
        added = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            for sep in [' - ', '=', ':', '—', '-']:
                if sep in line:
                    parts = line.split(sep, 1)
                    eng = parts[0].strip()
                    ru_part = parts[1].strip()
                    
                    translations = [t.strip() for t in ru_part.split(',')]
                    
                    for ru in translations:
                        if add_word_to_user(uid, eng, ru):
                            added += 1
                    break
        
        if added > 0:
            await m.answer(f"✅ Добавлено переводов: *{added}*\n📝 Транскрипция добавлена автоматически", parse_mode="Markdown")
        else:
            await m.answer("❌ Неверный формат. Используйте: `слово - перевод`", parse_mode="Markdown")
        update_user_mode(uid, "none")
        return
    
    # Пошаговое добавление
    elif user_mode['add_mode'] == "word_eng":
        update_user_mode(uid, "word_ru", m.text)
        await m.answer("✏️ Введите перевод (можно несколько через запятую):", parse_mode="Markdown")
    
    elif user_mode['add_mode'] == "word_ru":
        temp_eng = user_mode['temp_eng']
        if temp_eng:
            translations = [t.strip() for t in m.text.split(',')]
            added = 0
            for ru in translations:
                if add_word_to_user(uid, temp_eng, ru):
                    added += 1
            
            if added > 0:
                trans_text = ", ".join(translations)
                transcription = add_transcription_to_word(temp_eng)
                await m.answer(f"✅ *{temp_eng}* → {trans_text}\n📝 Транскрипция: `{transcription}`", parse_mode="Markdown")
            else:
                await m.answer(f"❌ Не удалось добавить *{temp_eng}*", parse_mode="Markdown")
            update_user_mode(uid, "none")

# ---------------- RUN ----------------

async def main():
    init_db()
    await set_commands()
    print("\n" + "="*50)
    print("🤖 БОТ ЗАПУЩЕН")
    bot_info = await bot.get_me()
    print(f"📌 {bot_info.full_name}")
    print(f"🆔 @{bot_info.username}")
    print("\n📦 СТАТУС БИБЛИОТЕК:")
    print(f"📷 PIL: {'✅' if PIL_AVAILABLE else '❌'}")
    print(f"🔍 Tesseract: {'✅' if TESSERACT_AVAILABLE else '❌'}")
    print(f"🌐 Translator: {'✅' if TRANSLATOR_AVAILABLE else '❌'}")
    print("="*50 + "\n")
    await dp.start_polling(bot)

if __name__ == "__main__":
    print("🚀 Запуск...")
    asyncio.run(main())
