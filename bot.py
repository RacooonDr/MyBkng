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
ADMIN_ID = 123456789  # ← ЗАМЕНИ НА СВОЙ ID (узнай у @userinfobot)
PORT = int(os.environ.get('PORT', 8080))

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================
# Flask-сервер (чтобы Render не ругался)
# ============================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает! 🤖"

@app.route('/health')
def health():
    return "OK", 200

# ============================================
# ДАННЫЕ (в памяти, для старта)
# ============================================
services = [
    {"id": 1, "name": "Тату", "price": 5000, "desc": "Индивидуальный дизайн"},
    {"id": 2, "name": "Маникюр", "price": 1500, "desc": "Гель-лак + дизайн"},
    {"id": 3, "name": "Барберинг", "price": 2000, "desc": "Стрижка + борода"},
]

# Хранилище записей (потом заменим на БД)
bookings = []
user_sessions = {}

# ============================================
# ФУНКЦИИ БОТА
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start"""
    user = update.effective_user
    
    # Клавиатура главного меню
    keyboard = [
        [InlineKeyboardButton("🛠 Услуги", callback_data="services")],
        [InlineKeyboardButton("📅 Мои записи", callback_data="my_bookings")],
        [InlineKeyboardButton("ℹ️ Инфо", callback_data="info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔥 Привет, {user.first_name}!\n\n"
        f"Я бот для записи к мастеру. Выбери действие:",
        reply_markup=reply_markup
    )

async def services_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список услуг"""
    query = update.callback_query
    await query.answer()
    
    text = "🛠 <b>Наши услуги:</b>\n\n"
    keyboard = []
    
    for service in services:
        text += f"💎 <b>{service['name']}</b>\n"
        text += f"💰 {service['price']} руб.\n"
        text += f"📝 {service['desc']}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"📝 Записаться на {service['name']}", 
                callback_data=f"book_{service['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать запись на услугу"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.replace("book_", ""))
    service = next((s for s in services if s["id"] == service_id), None)
    
    if not service:
        await query.edit_message_text("❌ Услуга не найдена")
        return
    
    # Сохраняем в сессию
    user_id = query.from_user.id
    user_sessions[user_id] = {
        "service": service,
        "step": "choosing_date"
    }
    
    # Клавиатура с датами
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="date_today")],
        [InlineKeyboardButton("📅 Завтра", callback_data="date_tomorrow")],
        [InlineKeyboardButton("📅 Послезавтра", callback_data="date_dayafter")],
        [InlineKeyboardButton("🔙 Назад", callback_data="services")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📝 Запись на <b>{service['name']}</b>\n\nВыбери дату:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор даты"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    if not session:
        await query.edit_message_text("❌ Сессия истекла. Начни заново.")
        return
    
    # Определяем выбранную дату
    from datetime import datetime, timedelta
    today = datetime.now()
    
    if query.data == "date_today":
        selected_date = today.strftime("%d.%m.%Y")
    elif query.data == "date_tomorrow":
        selected_date = (today + timedelta(days=1)).strftime("%d.%m.%Y")
    elif query.data == "date_dayafter":
        selected_date = (today + timedelta(days=2)).strftime("%d.%m.%Y")
    else:
        return
    
    session["date"] = selected_date
    session["step"] = "choosing_time"
    
    # Клавиатура с временем
    keyboard = [
        [InlineKeyboardButton("⏰ 10:00", callback_data="time_10:00")],
        [InlineKeyboardButton("⏰ 12:00", callback_data="time_12:00")],
        [InlineKeyboardButton("⏰ 14:00", callback_data="time_14:00")],
        [InlineKeyboardButton("⏰ 16:00", callback_data="time_16:00")],
        [InlineKeyboardButton("⏰ 18:00", callback_data="time_18:00")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_dates")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📅 Дата: {selected_date}\n\nВыбери время:",
        reply_markup=reply_markup
    )

async def select_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор времени"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    if not session:
        await query.edit_message_text("❌ Сессия истекла. Начни заново.")
        return
    
    time = query.data.replace("time_", "")
    session["time"] = time
    session["step"] = "confirming"
    
    # Кнопки подтверждения
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="services")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    service = session["service"]
    text = (
        f"✅ <b>Подтверждение записи</b>\n\n"
        f"💎 Услуга: {service['name']}\n"
        f"💰 Цена: {service['price']} руб.\n"
        f"📅 Дата: {session['date']}\n"
        f"⏰ Время: {time}\n\n"
        f"Всё верно?"
    )
    
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение записи"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    if not session:
        await query.edit_message_text("❌ Сессия истекла. Начни заново.")
        return
    
    # Создаем запись
    booking = {
        "id": len(bookings) + 1,
        "user_id": user_id,
        "username": query.from_user.username or query.from_user.first_name,
        "service": session["service"]["name"],
        "price": session["service"]["price"],
        "date": session["date"],
        "time": session["time"],
        "status": "pending"
    }
    bookings.append(booking)
    
    # Уведомление админу
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Новая запись!</b>\n\n"
            f"👤 Клиент: @{query.from_user.username or query.from_user.first_name}\n"
            f"💎 Услуга: {session['service']['name']}\n"
            f"📅 Дата: {session['date']}\n"
            f"⏰ Время: {session['time']}"
        )
    except:
        pass
    
    # Очищаем сессию
    del user_sessions[user_id]
    
    await query.edit_message_text(
        "✅ <b>Запись подтверждена!</b>\n\n"
        "Я отправил уведомление мастеру.",
        parse_mode="HTML"
    )
    
    # Показываем главное меню
    keyboard = [
        [InlineKeyboardButton("🛠 Услуги", callback_data="services")],
        [InlineKeyboardButton("📅 Мои записи", callback_data="my_bookings")],
        [InlineKeyboardButton("ℹ️ Инфо", callback_data="info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        user_id,
        "Выбери действие:",
        reply_markup=reply_markup
    )

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать записи пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_bookings = [b for b in bookings if b["user_id"] == user_id]
    
    if not user_bookings:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "😕 У тебя пока нет записей.",
            reply_markup=reply_markup
        )
        return
    
    text = "📋 <b>Твои записи:</b>\n\n"
    for booking in user_bookings[-5:]:
        status_emoji = "⏳" if booking["status"] == "pending" else "✅"
        text += f"{status_emoji} <b>{booking['service']}</b>\n"
        text += f"   📅 {booking['date']} в {booking['time']}\n"
        text += f"   💰 {booking['price']} руб.\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полезная информация"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "ℹ️ <b>Информация</b>\n\n"
        "📍 Адрес: ул. Примерная, д. 123\n"
        "⏰ Работаем: 10:00 - 22:00\n"
        "📞 Телефон: +7 (999) 123-45-67\n\n"
        "⚠️ Отмена записи возможна не позднее, чем за 2 часа."
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться в главное меню"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🛠 Услуги", callback_data="services")],
        [InlineKeyboardButton("📅 Мои записи", callback_data="my_bookings")],
        [InlineKeyboardButton("ℹ️ Инфо", callback_data="info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔥 Выбери действие:",
        reply_markup=reply_markup
    )

async def handle_back_to_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к выбору даты"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    if session:
        session["step"] = "choosing_date"
    
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="date_today")],
        [InlineKeyboardButton("📅 Завтра", callback_data="date_tomorrow")],
        [InlineKeyboardButton("📅 Послезавтра", callback_data="date_dayafter")],
        [InlineKeyboardButton("🔙 Назад", callback_data="services")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📝 Выбери дату:",
        reply_markup=reply_markup
    )

# ============================================
# ЗАПУСК БОТА
# ============================================
def run_bot():
    """Запуск Telegram бота в отдельном потоке"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    
    # Добавляем обработчики callback'ов
    application.add_handler(CallbackQueryHandler(services_menu, pattern="^services$"))
    application.add_handler(CallbackQueryHandler(my_bookings, pattern="^my_bookings$"))
    application.add_handler(CallbackQueryHandler(info, pattern="^info$"))
    application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back$"))
    application.add_handler(CallbackQueryHandler(start_booking, pattern="^book_"))
    application.add_handler(CallbackQueryHandler(select_date, pattern="^date_"))
    application.add_handler(CallbackQueryHandler(select_time, pattern="^time_"))
    application.add_handler(CallbackQueryHandler(confirm_booking, pattern="^confirm$"))
    application.add_handler(CallbackQueryHandler(handle_back_to_dates, pattern="^back_to_dates$"))
    
    # Запускаем бота (polling)
    logger.info("Бот запускается...")
    application.run_polling()

# ============================================
# ТОЧКА ВХОДА
# ============================================
if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем Flask сервер (для Render)
    app.run(host="0.0.0.0", port=PORT)
