import os
import logging
import threading
import asyncio
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============================================
# НАСТРОЙКИ
# ============================================
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 775020198
PORT = int(os.environ.get('PORT', 8080))

# Логи
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Flask ===
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает! 🤖"

@app.route('/health')
def health():
    return "OK", 200

# === ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие"""
    user = update.effective_user
    logger.info(f"Пользователь {user.first_name} запустил бота")
    
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
    """Запуск Telegram бота в отдельном потоке"""
    try:
        logger.info("Запускаем бота...")
        
        # Создаём приложение
        app_bot = Application.builder().token(TOKEN).build()
        
        # Добавляем обработчики
        app_bot.add_handler(CommandHandler("start", start))
        app_bot.add_handler(CallbackQueryHandler(button_handler))
        
        logger.info("Бот настроен, начинаем polling...")
        
        # Запускаем бота (этот метод блокирует поток)
        app_bot.run_polling(
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"Ошибка бота: {e}", exc_info=True)

# === ТОЧКА ВХОДА ===
if __name__ == "__main__":
    try:
        # Запускаем бота в отдельном потоке
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        logger.info("Бот запущен в фоновом потоке")
        
        # Запускаем Flask
        logger.info("Flask запускается...")
        app.run(host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")
