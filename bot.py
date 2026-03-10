import os
import logging
import threading
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# ============================================
# НАСТРОЙКИ
# ============================================
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 775020198  # ← ЗАМЕНИ НА СВОЙ ID (узнай у @userinfobot)
PORT = int(os.environ.get('PORT', 8080))

# Логи
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Flask ===
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает! 🤖"

@app.route('/health')
def health():
    return "OK", 200

# === ПРОСТЕЙШИЙ ОБРАБОТЧИК ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие"""
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("🛠 Услуги", callback_data="services")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🔥 Привет, {user.first_name}! Я жив!",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Скоро тут будут услуги!")

# === ФУНКЦИЯ ЗАПУСКА БОТА ===
def run_bot():
    """Запуск Telegram бота"""
    try:
        logger.info("Запускаем бота...")
        app_bot = Application.builder().token(TOKEN).build()
        app_bot.add_handler(CommandHandler("start", start))
        app_bot.add_handler(CallbackQueryHandler(button_handler))
        logger.info("Бот запущен и слушает...")
        app_bot.run_polling()
    except Exception as e:
        logger.error(f"Ошибка бота: {e}")

# === ТОЧКА ВХОДА ===
if __name__ == "__main__":
    # Запускаем бота в фоне
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Flask запускается...")
    app.run(host="0.0.0.0", port=PORT)
