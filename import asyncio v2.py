import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from PIL import Image
import google.generativeai as genai
import re 
from io import BytesIO
import sqlite3

# Загружаем переменные из .env файла
load_dotenv("GEMINI_API_KEY.env")

# ================== НАСТРОЙКИ ==================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8545287407:AAEyBuYTc8eaZIWJkhc2mfS8jcciauTuKbI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY не найден! Проверьте файл GEMINI_API_KEY.env")

print(f"✅ API ключ загружен: {GEMINI_API_KEY[:20]}...")
# ==============================================

logging.basicConfig(level=logging.INFO)

genai.configure(api_key=GEMINI_API_KEY)

text_model = genai.GenerativeModel("gemini-2.5-flash")
vision_model = genai.GenerativeModel("gemini-2.5-flash")


# ====== БД ДЛЯ БАНОВ ======
conn = sqlite3.connect("bans.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS bans (
    user_id INTEGER PRIMARY KEY
)
""")
conn.commit()


def is_banned(user_id: int) -> bool:
    cur.execute("SELECT 1 FROM bans WHERE user_id = ?", (user_id,))
    return cur.fetchone() is not None




# ====== БЛОКИРОВКА ПОЛЬЗОВАТЕЛЕЙ ======
ADMIN_IDS = {8405974684}  # ← ЗАМЕНИ на свой Telegram user_id
BANNED_USERS = set()

async def ban_guard(update: Update) -> bool:
    user_id = update.effective_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("🚫 Вы заблокированы в боте.")
        return True
    return False


#================== /ban /unban ==================

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Использование: /ban <user_id>")
        return

    try:
        user_id = int(context.args[0])
        cur.execute("INSERT OR IGNORE INTO bans (user_id) VALUES (?)", (user_id,))
        conn.commit()
        await update.message.reply_text(f"✅ Пользователь {user_id} заблокирован.")
    except ValueError:
        await update.message.reply_text("❌ user_id должен быть числом")


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Использование: /unban <user_id>")
        return

    try:
        user_id = int(context.args[0])
        cur.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
        conn.commit()
        await update.message.reply_text(f"🔓 Пользователь {user_id} разблокирован.")
    except ValueError:
        await update.message.reply_text("❌ user_id должен быть числом")



#================== форматирование ==================

import re

SUPERSCRIPTS = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
SUBSCRIPTS   = str.maketrans("0123456789+-=()n", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₙ")

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "theta": "θ", "lambda": "λ", "mu": "μ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ",
    "phi": "φ", "omega": "ω"
}

SYMBOLS = {
    r"\\cdot": "·",
    r"\\times": "×",
    r"\\pm": "±",
    r"\\le": "≤",
    r"\\ge": "≥",
    r"\\neq": "≠",
    r"\\approx": "≈"
}


def latex_to_unicode(text: str) -> str:
    # Убираем $
    text = text.replace("$", "")

    # Греческие буквы
    for k, v in GREEK.items():
        text = re.sub(rf"\\{k}\b", v, text)

    # Символы
    for k, v in SYMBOLS.items():
        text = re.sub(k, v, text)

    # sqrt
    text = re.sub(r"(\\sqrt|/sqrt)\s*\{([^}]+)\}", r"√(\2)", text)
    text = re.sub(r"(\\sqrt|/sqrt)\s*\(([^)]+)\)", r"√(\2)", text)

    # дроби \frac{a}{b}
    def frac_replacer(m):
        return f"({m.group(1)})⁄({m.group(2)})"

    text = re.sub(r"\\frac\s*\{([^}]+)\}\s*\{([^}]+)\}", frac_replacer, text)

    # степени x^{...}
    def power_block(m):
        return m.group(1) + m.group(2).translate(SUPERSCRIPTS)

    text = re.sub(r"([a-zA-Z0-9]+)\^\{([^}]+)\}", power_block, text)
    text = re.sub(r"([a-zA-Z0-9]+)\^([a-zA-Z0-9]+)",
                  lambda m: m.group(1) + m.group(2).translate(SUPERSCRIPTS),
                  text)

    # нижние индексы
    text = re.sub(r"([a-zA-Z]+)_\{([^}]+)\}",
                  lambda m: m.group(1) + m.group(2).translate(SUBSCRIPTS),
                  text)

    # умножение
    text = re.sub(r"(\d)\s*\*\s*(\d)", r"\1×\2", text)

    # чистка скобок
    text = text.replace("{", "").replace("}", "")

    return text
#===========MarckMarkdownV2=============


def escape_markdown_v2(text: str) -> str:
    """
    Экранирует символы для MarkdownV2 Telegram.
    """
    escape_chars = r"_*[]()~>#+-=|{}.!\\"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)











# ===== СИСТЕМНЫЙ ПРОМТ (можно менять) =====
SYSTEM_PROMPT = "Отвечай кратко не но слишком"


# ---------- Команды ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 бот разработан @Fruzv\n\n"
        f"Рабатает на базе генеративной модели gemini 2.5\n\n"
        f"Больше команд /help"
    )
#info
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Бот разработан @Fruzv!\n\n"
        "Работает на базе gemini 2.5 flash.\n\n"
        f"Обрабатывает фото уро"
    )
#bug
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Если нашел баг, ошибку пиши сюда @Fruzv\n"
                                    f"Команды:\n\n"
                                    f"/list расписание\n"
                                    f"/Glist секрет\n"
                                    f"/ask спросить ии\n"
                                    f"/prompt новый промт — установить новый\n\n"
                                    f"/prompt — показать текущий промт\n")

#спец
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #фото
    await update.message.reply_photo(photo="AgACAgIAAxkBAAEK_sFpb9-DGe9874vw2f2qnCwC0Xk9YQACQhFrG11icUt6qUrt_C9AiQEAAwIAA3kAAzgE")


async def prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SYSTEM_PROMPT

    text = update.message.text.replace("/prompt", "", 1).strip()

    if not text:
        await update.message.reply_text(
            f"Текущий промт:\n\n{SYSTEM_PROMPT}"
        )
        return

    SYSTEM_PROMPT = text
    await update.message.reply_text("✅ Промт обновлён!")

#славик глист
async def glist(updade: Update, context: ContextTypes.DEFAULT_TYPE):
    await updade.message.reply_photo(photo="AgACAgIAAxkBAAEK_p9pb9p2JweQqeXVmM3OqunfBXYHOQACYhJrG11ieUv4WONuy0ejuQEAAwIAA3cAAzgE")


# ---------- Текст ----------

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if not text.startswith("/ask"):
        return

    if is_banned(user_id):
        await update.message.reply_text("🚫 Вы заблокированы в боте.")
        return

    user_prompt = text.replace("/ask", "", 1).strip()
    if not user_prompt:
        await update.message.reply_text("❗ Напиши вопрос после /ask")
        return

    full_prompt = f"{SYSTEM_PROMPT}\n\nВопрос пользователя:\n{user_prompt}"

    try:
        logging.info(f"Отправка запроса в Gemini: {user_prompt[:50]}...")
        response = text_model.generate_content(full_prompt)
        logging.info(f"Получен ответ от Gemini: {response.text[:100]}...")

        formatted = latex_to_unicode(response.text)
        formatted = escape_markdown_v2(formatted)
        formatted = f"*{formatted}*"

        await update.message.reply_text(formatted, parse_mode="MarkdownV2")

    except Exception as e:
        logging.error(f"Ошибка при запросе к Gemini: {e}")
        await update.message.reply_text(f"Ошибка: {e}")

# ---------- Фото ----------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.caption or ""
    user_id = update.effective_user.id

    if not caption.startswith("/ask"):
        return

    if is_banned(user_id):
        await update.message.reply_text("🚫 Вы заблокированы в боте.")
        return

    user_prompt = caption.replace("/ask", "", 1).strip()
    if not user_prompt:
        user_prompt = "Реши предоставленные задачи"

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        bio = BytesIO()
        await file.download_to_memory(bio)
        bio.seek(0)

        image = Image.open(bio)

        full_prompt = f"{SYSTEM_PROMPT}\n\nЗапрос пользователя:\n{user_prompt}"

        logging.info(f"Отправка запроса с фото в Gemini: {user_prompt[:50]}...")
        response = vision_model.generate_content([full_prompt, image])
        logging.info(f"Получен ответ от Gemini: {response.text[:100]}...")

        formatted = latex_to_unicode(response.text)
        formatted = escape_markdown_v2(formatted)
        formatted = f"*{formatted}*"

        await update.message.reply_text(formatted, parse_mode="MarkdownV2")

    except Exception as e:
        logging.error(f"Ошибка при запросе к Gemini с фото: {e}")
        await update.message.reply_text(f"Ошибка обработки фото: {e}")



# ---------- Запуск ----------
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))

    
    
    app.add_handler(CommandHandler("Glist", glist))
    app.add_handler(CommandHandler("list", photo))
    app.add_handler(CommandHandler("help", support))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("prompt", prompt_command))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🤖 Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
