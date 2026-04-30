import asyncio
import random
import os
import sqlite3
import re
import requests
import base64
import sqlite3
from contextlib import contextmanager

DB = "bot.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Инициализация базы данных"""
    with get_db() as db:
        # Таблица пользователей
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            wrong INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0,
            add_mode TEXT DEFAULT 'none',
            temp_eng TEXT,
            quiz_mode TEXT DEFAULT 'multiple',
            auto_mode INTEGER DEFAULT 0,
            quiz_active INTEGER DEFAULT 0
        )
        """)
        
        # Таблица слов пользователя
        db.execute("""
        CREATE TABLE IF NOT EXISTS user_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            eng TEXT,
            ru TEXT,
            transcription TEXT,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, eng, ru)
        )
        """)
        
        db.commit()
    print("✅ База данных готова")
    DB = "bot.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def migrate_db():
    """Обновление структуры базы данных"""
    with get_db() as db:
        # Колонки для user_words
        try:
            db.execute("ALTER TABLE user_words ADD COLUMN word_type TEXT DEFAULT 'word'")
            print("✅ Добавлена колонка word_type")
        except sqlite3.OperationalError:
            pass
        
        try:
            db.execute("ALTER TABLE user_words ADD COLUMN transcription TEXT")
            print("✅ Добавлена колонка transcription")
        except sqlite3.OperationalError:
            pass
        
        # Колонки для users
        columns = [
            ("username", "TEXT"),
            ("first_name", "TEXT"),
            ("add_mode", "TEXT DEFAULT 'none'"),
            ("temp_eng", "TEXT"),
            ("quiz_mode", "TEXT DEFAULT 'multiple'"),
            ("auto_mode", "INTEGER DEFAULT 0"),
            ("quiz_active", "INTEGER DEFAULT 0"),
            ("wrong", "INTEGER DEFAULT 0"),
            ("correct", "INTEGER DEFAULT 0")
        ]
        
        for col_name, col_type in columns:
            try:
                db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                print(f"✅ Добавлена колонка {col_name}")
            except sqlite3.OperationalError:
                pass
        
        db.commit()

def init_db():
    with get_db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
        """)
        
        db.execute("""
        CREATE TABLE IF NOT EXISTS user_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            eng TEXT,
            ru TEXT,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, eng, ru)
        )
        """)
        
        db.commit()
    
    migrate_db()
    print("✅ База данных готова")
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

# ---------------- ФУНКЦИИ ДЛЯ ТРАНСКРИПЦИИ ----------------

import epitran

# Инициализация для английского языка (США)
epi = epitran.Epitran('eng-Latn')

def get_transcription(word):
    """Получает точную IPA транскрипцию слова с помощью epitran"""
    try:
        # Получаем транскрипцию
        transcription = epi.transliterate(word.lower())
        
        # Очищаем от лишних символов
        transcription = transcription.strip()
        
        # Добавляем ударение если его нет
        if word.lower() in ['a', 'an', 'the', 'and', 'of', 'to', 'in', 'for', 'on', 'with']:
            pass  # Короткие слова без ударения
        elif len(word) > 1 and "'" not in transcription and 'ˈ' not in transcription:
            # Примерное ударение для длинных слов
            if len(word) > 5:
                transcription = 'ˈ' + transcription
        
        return transcription
    except Exception as e:
        print(f"Ошибка транскрипции для {word}: {e}")
        # Возвращаем упрощенную транскрипцию
        return simple_transcription(word)

def simple_transcription(word):
    """Упрощенная транскрипция для неизвестных слов"""
    word_lower = word.lower()
    
    # Базовые правила
    result = []
    i = 0
    while i < len(word_lower):
        ch = word_lower[i]
        
        # Гласные
        if ch == 'a':
            if i + 1 < len(word_lower) and word_lower[i+1] in 'aeiou':
                result.append('eɪ')
                i += 1
            else:
                result.append('æ')
        elif ch == 'e':
            if i + 1 < len(word_lower) and word_lower[i+1] == 'e':
                result.append('iː')
                i += 1
            else:
                result.append('e')
        elif ch == 'i':
            if i + 1 < len(word_lower) and word_lower[i+1] in 'aeiou':
                result.append('aɪ')
                i += 1
            else:
                result.append('ɪ')
        elif ch == 'o':
            if i + 1 < len(word_lower) and word_lower[i+1] == 'o':
                result.append('uː')
                i += 1
            else:
                result.append('ɒ')
        elif ch == 'u':
            result.append('ʌ')
        # Согласные
        elif ch == 'c':
            if i + 1 < len(word_lower) and word_lower[i+1] == 'h':
                result.append('tʃ')
                i += 1
            elif i + 1 < len(word_lower) and word_lower[i+1] == 'k':
                result.append('k')
                i += 1
            else:
                result.append('k')
        elif ch == 's':
            if i + 1 < len(word_lower) and word_lower[i+1] == 'h':
                result.append('ʃ')
                i += 1
            else:
                result.append('s')
        elif ch == 't':
            if i + 1 < len(word_lower) and word_lower[i+1] == 'h':
                result.append('θ')
                i += 1
            elif i + 1 < len(word_lower) and word_lower[i+1] == 'i' and i + 2 < len(word_lower) and word_lower[i+2] == 'o':
                result.append('ʃ')
                i += 2
            else:
                result.append('t')
        elif ch == 'p':
            result.append('p')
        elif ch == 'b':
            result.append('b')
        elif ch == 'd':
            result.append('d')
        elif ch == 'f':
            result.append('f')
        elif ch == 'g':
            if i + 1 < len(word_lower) and word_lower[i+1] == 'e':
                result.append('dʒ')
            else:
                result.append('ɡ')
        elif ch == 'h':
            result.append('h')
        elif ch == 'j':
            result.append('dʒ')
        elif ch == 'k':
            result.append('k')
        elif ch == 'l':
            result.append('l')
        elif ch == 'm':
            result.append('m')
        elif ch == 'n':
            result.append('n')
        elif ch == 'q':
            result.append('kw')
            if i + 1 < len(word_lower) and word_lower[i+1] == 'u':
                i += 1
        elif ch == 'r':
            result.append('r')
        elif ch == 'v':
            result.append('v')
        elif ch == 'w':
            result.append('w')
        elif ch == 'x':
            result.append('ks')
        elif ch == 'y':
            if i + 1 < len(word_lower) and word_lower[i+1] in 'aeiou':
                result.append('j')
            else:
                result.append('ɪ')
        elif ch == 'z':
            result.append('z')
        else:
            result.append(ch)
        
        i += 1
    
    # Добавляем ударение для длинных слов (больше 2 слогов)
    if len(word) > 5:
        return 'ˈ' + ''.join(result)
    return ''.join(result)

def add_transcription_to_word(word):
    return get_transcription(word)
# ---------------- ФУНКЦИИ ДЛЯ РАСПОЗНАВАНИЯ ТЕКСТА С ФОТО ----------------

async def extract_text_from_image(photo_data):
    """Извлекает текст из изображения через OCR.space API (работает без установки Tesseract)"""
    try:
        # Используем бесплатный OCR API
        response = requests.post(
            'https://api.ocr.space/parse/image',
            files={'file': ('image.jpg', photo_data, 'image/jpeg')},
            data={'apikey': 'helloworld', 'language': 'eng', 'isOverlayRequired': False},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ParsedResults') and len(result['ParsedResults']) > 0:
                text = result['ParsedResults'][0].get('ParsedText', '')
                if text:
                    text = ' '.join(text.split())
                    return text.strip()
        return None
    except Exception as e:
        print(f"Ошибка OCR API: {e}")
        return None

async def parse_words_from_text(text):
    """Парсит слова и переводы из текста, переводит их"""
    words = []
    
    # Ищем все английские слова (от 2 до 20 букв)
    english_words = re.findall(r'\b[a-zA-Z]{2,20}\b', text)
    
    # Удаляем дубликаты и сортируем по длине (сначала длинные)
    unique_words = list(set([w.lower() for w in english_words]))
    unique_words.sort(key=len, reverse=True)
    
    # Берем первые 15 слов
    for eng in unique_words[:15]:
        ru = eng  # Временное значение
        
        # Пробуем перевести через Google Translate если доступен
        if translator and TRANSLATOR_AVAILABLE:
            try:
                translated = await translator.translate(eng, src='en', dest='ru')
                ru = translated.text
            except:
                pass
        
        words.append((eng, ru))
    
    return words

async def translate_and_add_words(user_id, words):
    """Переводит слова и добавляет в словарь с транскрипцией"""
    added = 0
    added_words = []
    
    for eng, ru in words:
        # Если перевод не получен, пробуем перевести
        if ru == eng and translator and TRANSLATOR_AVAILABLE:
            try:
                translated = await translator.translate(eng, src='en', dest='ru')
                ru = translated.text
            except:
                ru = "???"
        
        if add_word_to_user(user_id, eng, ru):
            added += 1
            transcription = get_transcription(eng)
            added_words.append(f"*{eng}* → {ru} `{transcription}`")
    
    return added, added_words

# ---------------- CRUD операции (остаются без изменений) ----------------

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

# ---------------- КОМАНДЫ И МЕНЮ (ДОБАВЛЕНА КНОПКА ФОТО) ----------------

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
        BotCommand(command="cancel", description="❌ Отмена"),
        BotCommand(command="photo", description="📸 Распознать фото")
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

@dp.message(Command("start"))
async def start(m: Message):
    user_id = m.from_user.id
    add_user(user_id, m.from_user.username, m.from_user.first_name)
    
    # Обновленное меню со всеми кнопками
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎯 Учить"), KeyboardButton(text="🔄 Авто"), KeyboardButton(text="⏹️ Стоп")],
            [KeyboardButton(text="➕ Добавить"), KeyboardButton(text="📦 Список"), KeyboardButton(text="📚 Слова")],
            [KeyboardButton(text="📸 Фото"), KeyboardButton(text="🗑️ Удалить"), KeyboardButton(text="🎮 Режим")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    
    word_count = count_user_words(user_id)
    
    photo_status = "✅" if (PIL_AVAILABLE and TESSERACT_AVAILABLE) else "✅ (OCR.space API)"
    
    await m.answer(
        f"👋 *{m.from_user.first_name}*\n\n"
        f"📚 Слов в словаре: *{word_count}*\n\n"
        f"🎯 *Учить* — викторина\n"
        f"🔄 *Авто* — каждые 2 минуты\n"
        f"➕ *Добавить* — новое слово\n"
        f"📦 *Список* — массовое добавление\n"
        f"📚 *Слова* — посмотреть все\n"
        f"📸 *Фото* — распознать текст с фото\n"
        f"🗑️ *Удалить* — удалить слово\n"
        f"🎮 *Режим* — выбор или ввод\n"
        f"📊 *Статистика* — прогресс\n"
        f"⏹️ *Стоп* — остановить\n"
        f"❌ *Отмена* — отменить действие\n\n"
        f"💡 *Совет:* При добавлении слов можно указывать несколько переводов через запятую\n"
        f"📝 *Транскрипция* добавляется автоматически",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ---------------- ОБРАБОТКА ФОТО (УЛУЧШЕННАЯ) ----------------

@dp.message(Command("photo"))
@dp.message(F.text == "📸 Фото")
async def photo_mode(m: Message):
    await m.answer(
        "📸 *Распознавание текста с фото*\n\n"
        "Отправьте фото с текстом на английском\n\n"
        "Бот выполнит:\n"
        "1️⃣ Распознает текст с фото\n"
        "2️⃣ Найдет все английские слова\n"
        "3️⃣ Переведет их на русский\n"
        "4️⃣ Добавит точную транскрипцию\n"
        "5️⃣ Сохранит в ваш словарь\n\n"
        "📌 *Совет:* Используйте четкое фото с хорошим освещением",
        parse_mode="Markdown"
    )

@dp.message(F.photo)
async def handle_photo(m: Message):
    user_id = m.from_user.id
    await m.answer("🔄 *Обрабатываю фото...*\n\n📍 Распознаю текст...", parse_mode="Markdown")
    
    try:
        photo = m.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_data = await bot.download_file(file.file_path)
        
        # Распознаем текст
        text = await extract_text_from_image(file_data.read())
        
        if not text:
            await m.answer("❌ *Не удалось распознать текст*\n\nПопробуйте:\n• Сделать фото четче\n• Улучшить освещение\n• Использовать контрастный фон", parse_mode="Markdown")
            return
        
        await m.answer(f"🔍 *Распознанный текст:*\n`{text[:300]}{'...' if len(text) > 300 else ''}`\n\n📍 Извлекаю слова...", parse_mode="Markdown")
        
        # Парсим слова
        words = await parse_words_from_text(text)
        
        if not words:
            await m.answer("❌ *Английские слова не найдены*", parse_mode="Markdown")
            return
        
        await m.answer(f"📝 *Найдено слов:* {len(words)}\n\n📍 Перевожу и добавляю в словарь...", parse_mode="Markdown")
        
        # Переводим и добавляем слова
        added, added_words = await translate_and_add_words(user_id, words)
        
        if added > 0:
            word_list = "\n".join(added_words[:10])
            await m.answer(
                f"✅ *Добавлено слов:* {added}\n\n{word_list}\n\n"
                f"📝 *Транскрипция добавлена автоматически*\n"
                f"🎯 Нажми '🎯 Учить' чтобы начать викторину!",
                parse_mode="Markdown"
            )
        else:
            await m.answer("❌ *Не удалось добавить слова*\nВозможно, они уже есть в словаре", parse_mode="Markdown")
            
    except Exception as e:
        print(f"Ошибка при обработке фото: {e}")
        await m.answer("❌ *Произошла ошибка при обработке фото*\nПопробуйте еще раз", parse_mode="Markdown")

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

@dp.message(F.text == "🎮 Режим")
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
        await m.answer("📚 Словарь пуст. Добавьте слова через '➕ Добавить' или '📸 Фото'")
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
    "📊 Статистика", "🎮 Режим", "🗑️ Удалить", "⏹️ Стоп", "❌ Отмена", "📸 Фото"
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
    print(f"📡 OCR.space API: ✅ (резервный вариант)")
    print("="*50 + "\n")
    await dp.start_polling(bot)

if __name__ == "__main__":
    print("🚀 Запуск...")
    asyncio.run(main())

