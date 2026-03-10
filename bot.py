import os
import logging
import asyncio
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============================================
# НАСТРОЙКИ
# ============================================
TOKEN = os.environ.get('BOT_TOKEN')
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

# === Инициализация бота ===
bot = Bot(token=TOKEN)
dp = Dispatcher()

# === Обработчики команд ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик /start"""
    user = message.from_user
    logger.info(f"Пользователь {user.full_name} запустил бота")
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🛠 Услуги", callback_data="services")
        ]]
    )
    
    await message.answer(
        f"🔥 Привет, {user.first_name}! Я жив!",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "services")
async def process_callback(callback_query: types.CallbackQuery):
    """Обработчик кнопок"""
    await callback_query.answer()
    await callback_query.message.edit_text("Скоро тут будут услуги!")

# === Функция запуска бота ===
async def start_bot():
    """Запуск бота"""
    try:
        logger.info("Запускаем бота через aiogram...")
        # Отключаем обработку сигналов
        await dp.start_polling(bot, handle_signals=False)
    except Exception as e:
        logger.error(f"Ошибка бота: {e}", exc_info=True)

def run_bot():
    """Запуск асинхронной функции"""
    asyncio.run(start_bot())

# === ТОЧКА ВХОДА ===
if __name__ == "__main__":
    # Запускаем бота в отдельном процессе, а не потоке
    import multiprocessing
    bot_process = multiprocessing.Process(target=run_bot)
    bot_process.daemon = True
    bot_process.start()
    logger.info("Бот запущен в отдельном процессе")
    
    # Запускаем Flask
    logger.info("Flask запускается...")
    app.run(host="0.0.0.0", port=PORT)
