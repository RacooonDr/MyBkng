import os
import logging
import asyncio
import json
import random
import string
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# ============================================
# НАСТРОЙКИ
# ============================================
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 775020198  # ← ТВОЙ ID
# ADMIN_ID = 1478927844  # ← еще один ID (закомментировано)
REVIEWS_CHANNEL_ID = int(os.environ.get('REVIEWS_CHANNEL_ID', 0))
WELCOME_PHOTO_LINK = os.environ.get('WELCOME_PHOTO_LINK')
PORT = int(os.environ.get('PORT', 8080))

# Логи
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Flask ===
app = Flask(__name__)

# === Инициализация бота ===
storage = MemoryStorage()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=storage)

# ============================================
# БАЗА ДАННЫХ (JSON-файлы)
# ============================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def load_json(filename):
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_json(filename, data):
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# === Услуги ===
def get_services():
    return load_json('services.json')

def save_services(services):
    save_json('services.json', services)

# === Записи ===
def get_bookings():
    return load_json('bookings.json')

def save_bookings(bookings):
    save_json('bookings.json', bookings)

# === Отзывы ===
def get_reviews():
    return load_json('reviews.json')

def save_reviews(reviews):
    save_json('reviews.json', reviews)

# === Промокоды ===
def get_promocodes():
    return load_json('promocodes.json')

def save_promocodes(promocodes):
    save_json('promocodes.json', promocodes)

# === Функция генерации промокода ===
def generate_promo_code(user_id, length=8):
    letters = string.ascii_uppercase + string.digits
    code = ''.join(random.choice(letters) for i in range(length))
    return f"DISCOUNT{code}"

# ============================================
# СОСТОЯНИЯ ДЛЯ FSM
# ============================================
class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    confirming = State()

class ReviewStates(StatesGroup):
    waiting_text = State()
    waiting_rating = State()
    waiting_photo = State()

class AdminStates(StatesGroup):
    adding_service_name = State()
    adding_service_price = State()
    adding_service_duration = State()
    adding_service_desc = State()
    broadcast_message = State()
    broadcast_confirm = State()
    waiting_promo_user_id = State()
    waiting_promo_discount = State()
    waiting_promo_confirm = State()

# ============================================
# ПРОВЕРКА НА АДМИНА
# ============================================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# ============================================
# ФУНКЦИЯ ДЛЯ ЗАГРУЗКИ ФОТО ИЗ TELEGRAM
# ============================================
async def get_photo_from_link(link: str):
    try:
        parts = link.split('/')
        chat_id = '-100' + parts[-2]
        message_id = int(parts[-1])
        
        message = await bot.forward_message(
            chat_id=chat_id,
            from_chat_id=chat_id,
            message_id=message_id
        )
        
        if message.photo:
            file_id = message.photo[-1].file_id
            return file_id
    except Exception as e:
        logger.error(f"Ошибка получения фото из канала: {e}")
        return None

# ============================================
# ФУНКЦИЯ УВЕДОМЛЕНИЙ
# ============================================
async def notify_admin(message: str):
    """Отправляет уведомление админу"""
    try:
        await bot.send_message(ADMIN_ID, f"👑 <b>Админ:</b>\n{message}")
    except Exception as e:
        logger.error(f"Ошибка уведомления админа: {e}")

async def notify_user(user_id: int, message: str):
    """Отправляет уведомление пользователю"""
    try:
        await bot.send_message(user_id, f"📢 <b>Уведомление:</b>\n{message}")
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователя {user_id}: {e}")

# ============================================
# ПЛАНИРОВЩИК НАПОМИНАНИЙ
# ============================================
async def check_reminders():
    """Проверяет записи и отправляет напоминания за 24 часа"""
    while True:
        try:
            bookings = get_bookings()
            now = datetime.now()
            
            for booking in bookings:
                if booking['status'] != 'confirmed':
                    continue
                
                booking_date = datetime.strptime(f"{booking['date']} {booking['time']}", "%Y-%m-%d %H:%M")
                time_diff = booking_date - now
                
                if timedelta(hours=23) < time_diff < timedelta(hours=25) and not booking.get('reminded'):
                    await notify_user(
                        booking['user_id'],
                        f"⏰ <b>Напоминание о записи!</b>\n\n"
                        f"Завтра в {booking['time']} у вас запись на <b>{booking['service_name']}</b>.\n"
                        f"Ждем вас!"
                    )
                    
                    booking['reminded'] = True
                    save_bookings(bookings)
                    
                    await notify_admin(
                        f"⏰ Отправлено напоминание клиенту @{booking['username']}\n"
                        f"Запись завтра в {booking['time']}"
                    )
            
            await asyncio.sleep(1800)  # 30 минут
            
        except Exception as e:
            logger.error(f"Ошибка в планировщике: {e}")
            await asyncio.sleep(60)

# ============================================
# КЛАВИАТУРЫ
# ============================================
def main_menu():
    kb = [
        [InlineKeyboardButton(text="🛠 Услуги и цены", callback_data="services")],
        [InlineKeyboardButton(text="📅 Мои записи", callback_data="my_bookings")],
        [InlineKeyboardButton(text="⭐️ Отзывы", callback_data="reviews")],
        [InlineKeyboardButton(text="🎟 Мои промокоды", callback_data="my_promocodes")],
        [InlineKeyboardButton(text="ℹ️ Информация", callback_data="info")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_menu():
    kb = [
        [InlineKeyboardButton(text="📦 Управление услугами", callback_data="admin_services")],
        [InlineKeyboardButton(text="📋 Все записи", callback_data="admin_bookings")],
        [InlineKeyboardButton(text="⭐️ Модерация отзывов", callback_data="admin_reviews")],
        [InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin_promocodes")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Выход", callback_data="back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def services_keyboard():
    services = get_services()
    kb = []
    for service in services:
        if service.get('active', True):
            kb.append([InlineKeyboardButton(
                text=f"{service['name']} - {service['price']}₽",
                callback_data=f"service_{service['id']}"
            )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def service_actions_keyboard(service_id):
    kb = [
        [InlineKeyboardButton(text="📝 Записаться", callback_data=f"book_{service_id}")],
        [InlineKeyboardButton(text="🔙 К услугам", callback_data="services")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def date_keyboard():
    kb = []
    today = datetime.now()
    for i in range(7):
        date = today + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        display = date.strftime("%d.%m (%a)")
        kb.append([InlineKeyboardButton(
            text=display,
            callback_data=f"date_{date_str}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="services")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def time_keyboard():
    kb = []
    for hour in range(10, 21):
        time_str = f"{hour:02d}:00"
        kb.append([InlineKeyboardButton(
            text=time_str,
            callback_data=f"time_{time_str}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 К датам", callback_data="back_to_dates")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def confirm_keyboard():
    kb = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_booking"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="services")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def reviews_menu_keyboard():
    kb = [
        [InlineKeyboardButton(text="👀 Посмотреть отзывы", callback_data="show_reviews")],
        [InlineKeyboardButton(text="✏️ Оставить отзыв (скидка 10%)", callback_data="leave_review")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def rating_keyboard():
    kb = []
    for i in range(1, 6):
        kb.append([InlineKeyboardButton(
            text="⭐️" * i,
            callback_data=f"rating_{i}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def photo_options_keyboard():
    kb = [
        [
            InlineKeyboardButton(text="📸 Добавить фото", callback_data="add_photo"),
            InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_photo")
        ],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_services_keyboard():
    services = get_services()
    kb = [
        [InlineKeyboardButton(text="➕ Добавить услугу", callback_data="admin_add_service")]
    ]
    for service in services:
        status = "✅" if service.get('active', True) else "❌"
        kb.append([InlineKeyboardButton(
            text=f"{status} {service['name']} - {service['price']}₽",
            callback_data=f"admin_edit_service_{service['id']}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 В админку", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_bookings_keyboard():
    kb = [
        [InlineKeyboardButton(text="⏳ Ожидают", callback_data="admin_bookings_pending")],
        [InlineKeyboardButton(text="✅ Подтверждены", callback_data="admin_bookings_confirmed")],
        [InlineKeyboardButton(text="✔️ Выполнены", callback_data="admin_bookings_completed")],
        [InlineKeyboardButton(text="❌ Отменены", callback_data="admin_bookings_cancelled")],
        [InlineKeyboardButton(text="📋 Все", callback_data="admin_bookings_all")],
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def booking_actions_keyboard(booking_id, current_status):
    kb = []
    if current_status == 'pending':
        kb.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"booking_confirm_{booking_id}")])
        kb.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"booking_cancel_{booking_id}")])
    elif current_status == 'confirmed':
        kb.append([InlineKeyboardButton(text="✔️ Выполнено", callback_data=f"booking_complete_{booking_id}")])
        kb.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"booking_cancel_{booking_id}")])
    kb.append([InlineKeyboardButton(text="🔙 К записям", callback_data="admin_bookings")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def reviews_moderation_keyboard():
    reviews = get_reviews()
    pending = [r for r in reviews if not r.get('approved', False)]
    kb = []
    for review in pending[:5]:
        kb.append([InlineKeyboardButton(
            text=f"⭐️ {review['rating']} - {review['username']}",
            callback_data=f"moderate_review_{review['id']}"
        )])
    if not pending:
        kb.append([InlineKeyboardButton(text="✅ Нет новых отзывов", callback_data="noop")])
    kb.append([InlineKeyboardButton(text="🔙 В админку", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def review_moderate_keyboard(review_id):
    kb = [
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_review_{review_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_review_{review_id}")
        ],
        [InlineKeyboardButton(text="🔙 К модерации", callback_data="admin_reviews")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_keyboard():
    kb = [[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def cancel_keyboard():
    kb = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ============================================
# Flask МАРШРУТЫ
# ============================================
@app.route('/', methods=['GET'])
def home():
    return "Бот работает! 🤖"

@app.route('/health', methods=['GET'])
def health():
    """Эндпоинт для проверки здоровья Render"""
    return "OK", 200

@app.route(f'/webhook/{TOKEN}', methods=['POST'])
async def webhook():
    """Главный эндпоинт для Telegram"""
    try:
        update = types.Update(**request.json)
        await dp.feed_update(bot, update)
        return 'ok', 200
    except Exception as e:
        logger.error(f"Ошибка вебхука: {e}")
        return 'error', 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook_route():
    """Вызови этот URL один раз, чтобы настроить вебхук"""
    webhook_url = f"https://{request.host}/webhook/{TOKEN}"
    asyncio.run(set_webhook(webhook_url))
    return f"✅ Webhook установлен на {webhook_url}", 200

async def set_webhook(url):
    await bot.set_webhook(url, allowed_updates=['message', 'callback_query'])
    logger.info(f"Вебхук установлен: {url}")

# ============================================
# ОБРАБОТЧИКИ
# ============================================

# ---------- СТАРТ ----------
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    logger.info(f"Пользователь {user.full_name} запустил бота")
    
    welcome_text = (
        f"🔥 <b>Привет, {user.first_name}!</b>\n\n"
        f"Я <b>демо-бот</b>, созданный чтобы показать, что умеют мои боты!\n\n"
        f"Вот что я умею:\n"
        f"✅ Показывать услуги с ценами и фото\n"
        f"✅ Записывать на удобное время\n"
        f"✅ Хранить историю записей\n"
        f"✅ Отзывы с фотографиями (скидка 10% за отзыв!)\n"
        f"✅ Промокоды на скидку\n"
        f"✅ Напоминания о записи\n"
        f"✅ Админ-панель с управлением\n\n"
        f"👇 <b>Выбери, что хочешь посмотреть:</b>"
    )
    
    if WELCOME_PHOTO_LINK:
        try:
            file_id = await get_photo_from_link(WELCOME_PHOTO_LINK)
            if file_id:
                await message.answer_photo(
                    photo=file_id,
                    caption=welcome_text,
                    reply_markup=main_menu()
                )
                return
            else:
                await message.answer_photo(
                    photo=WELCOME_PHOTO_LINK,
                    caption=welcome_text,
                    reply_markup=main_menu()
                )
                return
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
    
    await message.answer(welcome_text, reply_markup=main_menu())

# ---------- ОБРАБОТКА КНОПОК ----------
@dp.callback_query(F.data == "back")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text(
            "🔥 <b>Главное меню:</b>",
            reply_markup=main_menu()
        )
    except:
        await callback.message.answer(
            "🔥 <b>Главное меню:</b>",
            reply_markup=main_menu()
        )

@dp.callback_query(F.data == "cancel")
async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text(
            "❌ Действие отменено.\n\nГлавное меню:",
            reply_markup=main_menu()
        )
    except:
        await callback.message.answer(
            "❌ Действие отменено.\n\nГлавное меню:",
            reply_markup=main_menu()
        )

# ---------- ПРОМОКОДЫ ----------
@dp.callback_query(F.data == "my_promocodes")
async def my_promocodes(callback: types.CallbackQuery):
    promocodes = get_promocodes()
    user_promos = [p for p in promocodes if p['user_id'] == callback.from_user.id and not p.get('used', False)]
    
    if not user_promos:
        try:
            await callback.message.edit_text(
                "🎟 <b>У вас нет активных промокодов.</b>\n\n"
                "Оставьте отзыв после сеанса и получите промокод на 10% скидку!",
                reply_markup=back_keyboard()
            )
        except:
            await callback.message.answer(
                "🎟 <b>У вас нет активных промокодов.</b>\n\n"
                "Оставьте отзыв после сеанса и получите промокод на 10% скидку!",
                reply_markup=back_keyboard()
            )
        return
    
    text = "🎟 <b>Ваши промокоды:</b>\n\n"
    for promo in user_promos:
        text += f"🔹 <code>{promo['code']}</code> - скидка {promo['discount']}%\n"
        text += f"   Действует до: {promo.get('expires', 'бессрочно')}\n\n"
    
    kb = [[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
    
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ---------- УСЛУГИ ----------
@dp.callback_query(F.data == "services")
async def show_services(callback: types.CallbackQuery):
    services = get_services()
    
    if not services:
        services = [
            {"id": 1, "name": "Тату", "price": 5000, "duration": 120, 
             "desc": "Индивидуальный дизайн, любой сложности", "active": True},
            {"id": 2, "name": "Маникюр", "price": 1500, "duration": 60, 
             "desc": "Гель-лак, укрепление, дизайн", "active": True},
            {"id": 3, "name": "Барберинг", "price": 2000, "duration": 90, 
             "desc": "Стрижка + борода + уход", "active": True},
        ]
        save_services(services)
    
    text = "🛠 <b>Наши услуги:</b>\n\n"
    for service in services:
        if service.get('active', True):
            text += f"💎 <b>{service['name']}</b>\n"
            text += f"💰 {service['price']} руб.\n"
            text += f"⏱ {service['duration']} мин.\n"
            text += f"📝 {service['desc']}\n\n"
    
    try:
        await callback.message.edit_text(text, reply_markup=services_keyboard())
    except:
        await callback.message.answer(text, reply_markup=services_keyboard())

@dp.callback_query(F.data.startswith("service_"))
async def service_detail(callback: types.CallbackQuery, state: FSMContext):
    service_id = int(callback.data.replace("service_", ""))
    services = get_services()
    service = next((s for s in services if s['id'] == service_id), None)
    
    if not service:
        await callback.answer("❌ Услуга не найдена")
        return
    
    await state.update_data(
        service_id=service_id,
        service_name=service['name'],
        service_price=service['price'],
        service_duration=service['duration']
    )
    
    text = (
        f"💎 <b>{service['name']}</b>\n\n"
        f"💰 Цена: {service['price']} руб.\n"
        f"⏱ Длительность: {service['duration']} мин.\n\n"
        f"📝 {service['desc']}"
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=service_actions_keyboard(service_id))
    except:
        await callback.message.answer(text, reply_markup=service_actions_keyboard(service_id))

# ---------- ЗАПИСЬ ----------
@dp.callback_query(F.data.startswith("book_"))
async def start_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_date)
    try:
        await callback.message.edit_text(
            "📅 Выберите дату:",
            reply_markup=date_keyboard()
        )
    except:
        await callback.message.answer(
            "📅 Выберите дату:",
            reply_markup=date_keyboard()
        )

@dp.callback_query(BookingStates.choosing_date, F.data.startswith("date_"))
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.replace("date_", "")
    await state.update_data(booking_date=date_str)
    await state.set_state(BookingStates.choosing_time)
    
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    display_date = date_obj.strftime("%d.%m.%Y")
    
    try:
        await callback.message.edit_text(
            f"📅 Дата: {display_date}\n\n⏰ Выберите время:",
            reply_markup=time_keyboard()
        )
    except:
        await callback.message.answer(
            f"📅 Дата: {display_date}\n\n⏰ Выберите время:",
            reply_markup=time_keyboard()
        )

@dp.callback_query(BookingStates.choosing_time, F.data.startswith("time_"))
async def choose_time(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.replace("time_", "")
    await state.update_data(booking_time=time_str)
    
    data = await state.get_data()
    
    text = (
        f"✅ <b>Подтверждение записи</b>\n\n"
        f"💎 Услуга: {data['service_name']}\n"
        f"💰 Цена: {data['service_price']} руб.\n"
        f"📅 Дата: {data['booking_date']}\n"
        f"⏰ Время: {time_str}\n\n"
        f"Всё верно?"
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=confirm_keyboard())
    except:
        await callback.message.answer(text, reply_markup=confirm_keyboard())
    await state.set_state(BookingStates.confirming)

@dp.callback_query(BookingStates.confirming, F.data == "confirm_booking")
async def confirm_booking(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    bookings = get_bookings()
    new_booking = {
        "id": len(bookings) + 1,
        "user_id": callback.from_user.id,
        "username": callback.from_user.username or callback.from_user.full_name,
        "service_name": data['service_name'],
        "price": data['service_price'],
        "date": data['booking_date'],
        "time": data['booking_time'],
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "reminded": False
    }
    bookings.append(new_booking)
    save_bookings(bookings)
    
    admin_msg = (
        f"🔥 <b>НОВАЯ ЗАПИСЬ!</b>\n\n"
        f"👤 Клиент: @{callback.from_user.username or callback.from_user.full_name}\n"
        f"💎 Услуга: {data['service_name']}\n"
        f"📅 Дата: {data['booking_date']}\n"
        f"⏰ Время: {data['booking_time']}\n"
        f"💰 Цена: {data['service_price']} руб.\n\n"
        f"⚡️ Требуется подтверждение!"
    )
    await notify_admin(admin_msg)
    
    client_msg = (
        f"✅ <b>Запись создана!</b>\n\n"
        f"💎 Услуга: {data['service_name']}\n"
        f"📅 Дата: {data['booking_date']}\n"
        f"⏰ Время: {data['booking_time']}\n\n"
        f"Я отправил уведомление мастеру. Как только он подтвердит запись, вы получите уведомление. Пока можете внести предоплату мастеру - @x40vef4yX, БЕЗ ПРЕДОПЛАТЫ, ЗАПИСЬ НЕ ПОДТВЕРДИТСЯ!"
    )
    try:
        await callback.message.edit_text(client_msg, reply_markup=None)
    except:
        await callback.message.answer(client_msg, reply_markup=None)
    
    await asyncio.sleep(3)
    await callback.message.answer("🔥 Главное меню:", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data == "back_to_dates")
async def back_to_dates(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_date)
    try:
        await callback.message.edit_text(
            "📅 Выберите дату:",
            reply_markup=date_keyboard()
        )
    except:
        await callback.message.answer(
            "📅 Выберите дату:",
            reply_markup=date_keyboard()
        )

# ---------- МОИ ЗАПИСИ ----------
@dp.callback_query(F.data == "my_bookings")
async def my_bookings(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bookings = get_bookings()
    user_bookings = [b for b in bookings if b['user_id'] == user_id]
    
    if not user_bookings:
        try:
            await callback.message.edit_text(
                "😕 У вас пока нет записей.\n\nХотите записаться? Перейдите в «🛠 Услуги».",
                reply_markup=back_keyboard()
            )
        except:
            await callback.message.answer(
                "😕 У вас пока нет записей.\n\nХотите записаться? Перейдите в «🛠 Услуги».",
                reply_markup=back_keyboard()
            )
        return
    
    text = "📋 <b>Ваши записи:</b>\n\n"
    for booking in sorted(user_bookings, key=lambda x: x['date'])[-5:]:
        status_emoji = {
            'pending': '⏳',
            'confirmed': '✅',
            'completed': '✔️',
            'cancelled': '❌'
        }.get(booking['status'], '❓')
        
        text += f"{status_emoji} <b>{booking['service_name']}</b>\n"
        text += f"   📅 {booking['date']} в {booking['time']}\n"
        text += f"   💰 {booking['price']} руб.\n"
        text += f"   Статус: {booking['status']}\n\n"
    
    kb = [[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
    pending_bookings = [b for b in user_bookings if b['status'] == 'pending']
    if pending_bookings:
        kb.insert(0, [InlineKeyboardButton(text="❌ Отменить запись", callback_data="cancel_booking_menu")])
    
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "cancel_booking_menu")
async def cancel_booking_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bookings = get_bookings()
    user_bookings = [b for b in bookings if b['user_id'] == user_id and b['status'] == 'pending']
    
    if not user_bookings:
        await callback.answer("Нет записей, которые можно отменить")
        return
    
    kb = []
    for booking in user_bookings:
        kb.append([InlineKeyboardButton(
            text=f"{booking['service_name']} - {booking['date']} {booking['time']}",
            callback_data=f"cancel_booking_{booking['id']}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="my_bookings")])
    
    try:
        await callback.message.edit_text(
            "❌ Выберите запись для отмены:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
    except:
        await callback.message.answer(
            "❌ Выберите запись для отмены:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )

@dp.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery):
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    bookings = get_bookings()
    
    booking = None
    for b in bookings:
        if b['id'] == booking_id:
            booking = b
            b['status'] = 'cancelled'
            break
    
    save_bookings(bookings)
    
    if booking:
        await notify_admin(
            f"❌ Клиент @{booking['username']} отменил запись:\n"
            f"{booking['service_name']} - {booking['date']} {booking['time']}"
        )
        
        await notify_user(
            booking['user_id'],
            f"❌ Запись на <b>{booking['service_name']}</b> "
            f"{booking['date']} в {booking['time']} отменена."
        )
    
    await callback.answer("✅ Запись отменена")
    await my_bookings(callback)

# ---------- ОТЗЫВЫ ----------
@dp.callback_query(F.data == "reviews")
async def reviews_menu(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            "⭐️ <b>Отзывы</b>\n\n"
            "Здесь вы можете посмотреть отзывы других клиентов или оставить свой.\n\n"
            "🎁 <b>Бонус:</b> за каждый отзыв вы получаете промокод на 10% скидку!",
            reply_markup=reviews_menu_keyboard()
        )
    except:
        await callback.message.answer(
            "⭐️ <b>Отзывы</b>\n\n"
            "Здесь вы можете посмотреть отзывы других клиентов или оставить свой.\n\n"
            "🎁 <b>Бонус:</b> за каждый отзыв вы получаете промокод на 10% скидку!",
            reply_markup=reviews_menu_keyboard()
        )

@dp.callback_query(F.data == "show_reviews")
async def show_reviews(callback: types.CallbackQuery):
    reviews = get_reviews()
    approved = [r for r in reviews if r.get('approved', False)]
    
    if not approved:
        try:
            await callback.message.edit_text(
                "😕 Пока нет отзывов. Будьте первым!",
                reply_markup=reviews_menu_keyboard()
            )
        except:
            await callback.message.answer(
                "😕 Пока нет отзывов. Будьте первым!",
                reply_markup=reviews_menu_keyboard()
            )
        return
    
    kb = []
    for review in approved[-5:]:
        if review.get('photo_link'):
            kb.append([InlineKeyboardButton(
                text=f"⭐️ {review['username']} - {review['rating']}⭐️ (с фото)",
                url=review['photo_link']
            )])
        else:
            kb.append([InlineKeyboardButton(
                text=f"⭐️ {review['username']} - {review['rating']}⭐️",
                callback_data="noop"
            )])
    
    kb.append([InlineKeyboardButton(text="✏️ Оставить отзыв", callback_data="leave_review")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="reviews")])
    
    text = "⭐️ <b>Отзывы наших клиентов:</b>\n\n"
    for review in approved[-3:]:
        text += f"👤 <b>{review['username']}</b>  {'⭐️' * review['rating']}\n"
        text += f"📝 {review['text'][:100]}...\n\n"
    
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "leave_review")
async def leave_review(callback: types.CallbackQuery, state: FSMContext):
    bookings = get_bookings()
    user_bookings = [b for b in bookings if b['user_id'] == callback.from_user.id and b['status'] == 'completed']
    
    if not user_bookings:
        await callback.answer(
            "❌ Оставлять отзывы могут только клиенты, которые уже посетили мастера.",
            show_alert=True
        )
        return
    
    await state.set_state(ReviewStates.waiting_text)
    try:
        await callback.message.edit_text(
            "📝 Напишите ваш отзыв:",
            reply_markup=cancel_keyboard()
        )
    except:
        await callback.message.answer(
            "📝 Напишите ваш отзыв:",
            reply_markup=cancel_keyboard()
        )

@dp.message(ReviewStates.waiting_text)
async def process_review_text(message: types.Message, state: FSMContext):
    if len(message.text) > 1000:
        await message.answer("❌ Слишком длинный отзыв. Максимум 1000 символов.")
        return
    
    await state.update_data(review_text=message.text)
    await state.set_state(ReviewStates.waiting_rating)
    
    await message.answer(
        "⭐️ Оцените работу от 1 до 5:",
        reply_markup=rating_keyboard()
    )

@dp.callback_query(ReviewStates.waiting_rating, F.data.startswith("rating_"))
async def process_review_rating(callback: types.CallbackQuery, state: FSMContext):
    rating = int(callback.data.replace("rating_", ""))
    await state.update_data(rating=rating)
    await state.set_state(ReviewStates.waiting_photo)
    
    try:
        await callback.message.edit_text(
            "📸 Теперь можете добавить фото к отзыву (или пропустите):",
            reply_markup=photo_options_keyboard()
        )
    except:
        await callback.message.answer(
            "📸 Теперь можете добавить фото к отзыву (или пропустите):",
            reply_markup=photo_options_keyboard()
        )

@dp.callback_query(ReviewStates.waiting_photo, F.data == "add_photo")
async def add_photo_prompt(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            "📸 Отправьте фото:",
            reply_markup=cancel_keyboard()
        )
    except:
        await callback.message.answer(
            "📸 Отправьте фото:",
            reply_markup=cancel_keyboard()
        )

@dp.message(ReviewStates.waiting_photo, F.photo)
async def process_review_photo(message: types.Message, state: FSMContext):
    try:
        if REVIEWS_CHANNEL_ID == 0:
            raise Exception("REVIEWS_CHANNEL_ID не настроен")
        
        sent_message = await bot.send_photo(
            chat_id=REVIEWS_CHANNEL_ID,
            photo=message.photo[-1].file_id,
            caption=f"📸 Отзыв от @{message.from_user.username or message.from_user.full_name}"
        )
        
        channel_link = f"https://t.me/c/{str(REVIEWS_CHANNEL_ID)[4:]}/{sent_message.message_id}"
        data = await state.get_data()
        
        reviews = get_reviews()
        new_review = {
            "id": len(reviews) + 1,
            "user_id": message.from_user.id,
            "username": message.from_user.username or message.from_user.full_name,
            "text": data['review_text'],
            "rating": data['rating'],
            "photo_link": channel_link,
            "approved": False,
            "created_at": datetime.now().isoformat()
        }
        reviews.append(new_review)
        save_reviews(reviews)
        
        promocode = generate_promo_code(message.from_user.id)
        promocodes = get_promocodes()
        new_promo = {
            "id": len(promocodes) + 1,
            "user_id": message.from_user.id,
            "code": promocode,
            "discount": 10,
            "used": False,
            "created_at": datetime.now().isoformat(),
            "expires": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        }
        promocodes.append(new_promo)
        save_promocodes(promocodes)
        
        await message.answer(
            f"✅ Спасибо за отзыв с фото!\n\n"
            f"🎁 <b>Ваш промокод на 10% скидку:</b>\n"
            f"<code>{promocode}</code>\n\n"
            f"Действителен 30 дней.",
            reply_markup=main_menu()
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения фото: {e}")
        await message.answer(
            "❌ Не удалось сохранить фото. Отзыв сохранен без фото.",
            reply_markup=main_menu()
        )
        await state.clear()

@dp.callback_query(ReviewStates.waiting_photo, F.data == "skip_photo")
async def skip_photo(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    reviews = get_reviews()
    new_review = {
        "id": len(reviews) + 1,
        "user_id": callback.from_user.id,
        "username": callback.from_user.username or callback.from_user.full_name,
        "text": data['review_text'],
        "rating": data['rating'],
        "approved": False,
        "created_at": datetime.now().isoformat()
    }
    reviews.append(new_review)
    save_reviews(reviews)
    
    promocode = generate_promo_code(callback.from_user.id)
    promocodes = get_promocodes()
    new_promo = {
        "id": len(promocodes) + 1,
        "user_id": callback.from_user.id,
        "code": promocode,
        "discount": 10,
        "used": False,
        "created_at": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    }
    promocodes.append(new_promo)
    save_promocodes(promocodes)
    
    try:
        await callback.message.edit_text(
            f"✅ Спасибо за отзыв!\n\n"
            f"🎁 <b>Ваш промокод на 10% скидку:</b>\n"
            f"<code>{promocode}</code>\n\n"
            f"Действителен 30 дней.",
            reply_markup=main_menu()
        )
    except:
        await callback.message.answer(
            f"✅ Спасибо за отзыв!\n\n"
            f"🎁 <b>Ваш промокод на 10% скидку:</b>\n"
            f"<code>{promocode}</code>\n\n"
            f"Действителен 30 дней.",
            reply_markup=main_menu()
        )
    await state.clear()

# ---------- ИНФО ----------
@dp.callback_query(F.data == "info")
async def show_info(callback: types.CallbackQuery):
    text = (
        "ℹ️ <b>Информация</b>\n\n"
        "📍 <b>Адрес:</b> ул. Примерная, д. 123\n"
        "⏰ <b>Режим работы:</b> 10:00 - 22:00 ежедневно\n"
        "📞 <b>Телефон:</b> +7 (999) 123-45-67\n"
        "💳 <b>Оплата:</b> наличные, перевод\n\n"
        "⚠️ <b>Важно:</b>\n"
        "• Отмена записи возможна не позднее, чем за 2 часа\n"
        "• При опоздании более 15 минут запись может быть отменена\n"
        "• За отзыв вы получаете промокод на 10% скидку!"
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=back_keyboard())
    except:
        await callback.message.answer(text, reply_markup=back_keyboard())

# ============================================
# АДМИН-ПАНЕЛЬ
# ============================================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return
    
    await message.answer(
        "👑 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=admin_menu()
    )

@dp.callback_query(F.data == "admin")
async def admin_panel_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен")
        return
    
    try:
        await callback.message.edit_text(
            "👑 <b>Админ-панель</b>\n\nВыберите действие:",
            reply_markup=admin_menu()
        )
    except:
        await callback.message.answer(
            "👑 <b>Админ-панель</b>\n\nВыберите действие:",
            reply_markup=admin_menu()
        )

# ---------- УПРАВЛЕНИЕ УСЛУГАМИ ----------
@dp.callback_query(F.data == "admin_services")
async def admin_services(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    try:
        await callback.message.edit_text(
            "📦 <b>Управление услугами</b>\n\nВыберите услугу для редактирования или добавьте новую:",
            reply_markup=admin_services_keyboard()
        )
    except:
        await callback.message.answer(
            "📦 <b>Управление услугами</b>\n\nВыберите услугу для редактирования или добавьте новую:",
            reply_markup=admin_services_keyboard()
        )

@dp.callback_query(F.data == "admin_add_service")
async def admin_add_service_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminStates.adding_service_name)
    try:
        await callback.message.edit_text(
            "➕ <b>Добавление новой услуги</b>\n\nВведите название услуги:",
            reply_markup=cancel_keyboard()
        )
    except:
        await callback.message.answer(
            "➕ <b>Добавление новой услуги</b>\n\nВведите название услуги:",
            reply_markup=cancel_keyboard()
        )

@dp.message(AdminStates.adding_service_name)
async def admin_add_service_name(message: types.Message, state: FSMContext):
    await state.update_data(service_name=message.text)
    await state.set_state(AdminStates.adding_service_price)
    await message.answer(
        "💰 Введите цену в рублях (только число):",
        reply_markup=cancel_keyboard()
    )

@dp.message(AdminStates.adding_service_price)
async def admin_add_service_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите число!")
        return
    
    await state.update_data(service_price=int(message.text))
    await state.set_state(AdminStates.adding_service_duration)
    await message.answer(
        "⏱ Введите длительность в минутах:",
        reply_markup=cancel_keyboard()
    )

@dp.message(AdminStates.adding_service_duration)
async def admin_add_service_duration(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите число!")
        return
    
    await state.update_data(service_duration=int(message.text))
    await state.set_state(AdminStates.adding_service_desc)
    await message.answer(
        "📝 Введите описание услуги:",
        reply_markup=cancel_keyboard()
    )

@dp.message(AdminStates.adding_service_desc)
async def admin_add_service_desc(message: types.Message, state: FSMContext):
    await state.update_data(service_desc=message.text)
    
    data = await state.get_data()
    services = get_services()
    new_service = {
        "id": len(services) + 1,
        "name": data['service_name'],
        "price": data['service_price'],
        "duration": data['service_duration'],
        "desc": data['service_desc'],
        "active": True
    }
    services.append(new_service)
    save_services(services)
    
    await message.answer(
        f"✅ Услуга <b>{data['service_name']}</b> успешно добавлена!",
        reply_markup=admin_services_keyboard()
    )
    await state.clear()

@dp.callback_query(F.data.startswith("admin_edit_service_"))
async def admin_edit_service(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    service_id = int(callback.data.replace("admin_edit_service_", ""))
    services = get_services()
    service = next((s for s in services if s['id'] == service_id), None)
    
    if not service:
        await callback.answer("❌ Услуга не найдена")
        return
    
    text = (
        f"📦 <b>Редактирование услуги</b>\n\n"
        f"<b>ID:</b> {service['id']}\n"
        f"<b>Название:</b> {service['name']}\n"
        f"<b>Цена:</b> {service['price']} руб.\n"
        f"<b>Длительность:</b> {service['duration']} мин.\n"
        f"<b>Описание:</b> {service['desc']}\n"
        f"<b>Активна:</b> {'✅' if service.get('active', True) else '❌'}"
    )
    
    kb = [
        [InlineKeyboardButton(text="🔄 Активировать/Деактивировать", callback_data=f"admin_toggle_{service_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_{service_id}")],
        [InlineKeyboardButton(text="🔙 К услугам", callback_data="admin_services")]
    ]
    
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("admin_toggle_"))
async def admin_toggle_service(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    service_id = int(callback.data.replace("admin_toggle_", ""))
    services = get_services()
    
    for service in services:
        if service['id'] == service_id:
            service['active'] = not service.get('active', True)
            break
    
    save_services(services)
    await callback.answer("✅ Статус изменен")
    await admin_services(callback)

@dp.callback_query(F.data.startswith("admin_delete_"))
async def admin_delete_service(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    service_id = int(callback.data.replace("admin_delete_", ""))
    services = get_services()
    services = [s for s in services if s['id'] != service_id]
    save_services(services)
    
    await callback.answer("✅ Услуга удалена")
    await admin_services(callback)

# ---------- ПРОСМОТР ЗАПИСЕЙ ----------
@dp.callback_query(F.data == "admin_bookings")
async def admin_bookings_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    try:
        await callback.message.edit_text(
            "📋 <b>Просмотр записей</b>\n\nВыберите фильтр:",
            reply_markup=admin_bookings_keyboard()
        )
    except:
        await callback.message.answer(
            "📋 <b>Просмотр записей</b>\n\nВыберите фильтр:",
            reply_markup=admin_bookings_keyboard()
        )

@dp.callback_query(F.data.startswith("admin_bookings_"))
async def admin_bookings_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    filter_type = callback.data.replace("admin_bookings_", "")
    bookings = get_bookings()
    
    if filter_type != "all":
        bookings = [b for b in bookings if b['status'] == filter_type]
    
    bookings = sorted(bookings, key=lambda x: x['date'], reverse=True)
    
    if not bookings:
        try:
            await callback.message.edit_text(
                "📋 Нет записей",
                reply_markup=admin_bookings_keyboard()
            )
        except:
            await callback.message.answer(
                "📋 Нет записей",
                reply_markup=admin_bookings_keyboard()
            )
        return
    
    text = f"📋 <b>Записи: {filter_type}</b>\n\n"
    
    for booking in bookings[:10]:
        status_emoji = {
            'pending': '⏳',
            'confirmed': '✅',
            'completed': '✔️',
            'cancelled': '❌'
        }.get(booking['status'], '❓')
        
        text += f"{status_emoji} <b>#{booking['id']}</b>\n"
        text += f"   👤 {booking['username']}\n"
        text += f"   💎 {booking['service_name']}\n"
        text += f"   📅 {booking['date']} в {booking['time']}\n"
        text += f"   💰 {booking['price']} руб.\n\n"
    
    kb = []
    for booking in bookings[:5]:
        kb.append([InlineKeyboardButton(
            text=f"#{booking['id']} - {booking['service_name']}",
            callback_data=f"admin_booking_{booking['id']}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_bookings")])
    
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("admin_booking_"))
async def admin_booking_detail(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    booking_id = int(callback.data.replace("admin_booking_", ""))
    bookings = get_bookings()
    booking = next((b for b in bookings if b['id'] == booking_id), None)
    
    if not booking:
        await callback.answer("❌ Запись не найдена")
        return
    
    status_text = {
        'pending': '⏳ Ожидает',
        'confirmed': '✅ Подтверждена',
        'completed': '✔️ Выполнена',
        'cancelled': '❌ Отменена'
    }.get(booking['status'], booking['status'])
    
    text = (
        f"📋 <b>Запись #{booking['id']}</b>\n\n"
        f"👤 Клиент: {booking['username']} (ID: {booking['user_id']})\n"
        f"💎 Услуга: {booking['service_name']}\n"
        f"💰 Цена: {booking['price']} руб.\n"
        f"📅 Дата: {booking['date']}\n"
        f"⏰ Время: {booking['time']}\n"
        f"📊 Статус: {status_text}\n"
        f"🕐 Создано: {booking.get('created_at', 'неизвестно')}"
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=booking_actions_keyboard(booking_id, booking['status']))
    except:
        await callback.message.answer(text, reply_markup=booking_actions_keyboard(booking_id, booking['status']))

@dp.callback_query(F.data.startswith("booking_"))
async def admin_booking_action(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    parts = callback.data.replace("booking_", "").rsplit("_", 1)
    if len(parts) != 2:
        await callback.answer("❌ Неверный формат данных")
        return
    
    action, booking_id_str = parts
    booking_id = int(booking_id_str)
    
    bookings = get_bookings()
    booking = None
    for b in bookings:
        if b['id'] == booking_id:
            booking = b
            old_status = b['status']
            
            if action == "confirm":
                b['status'] = 'confirmed'
                await notify_user(
                    b['user_id'],
                    f"✅ <b>Запись подтверждена!</b>\n\n"
                    f"💎 {b['service_name']}\n"
                    f"📅 {b['date']} в {b['time']}\n\n"
                    f"Ждём вас!"
                )
                
            elif action == "cancel":
                b['status'] = 'cancelled'
                await notify_user(
                    b['user_id'],
                    f"❌ <b>Запись отменена</b>\n\n"
                    f"💎 {b['service_name']}\n"
                    f"📅 {b['date']} в {b['time']}\n\n"
                    f"По вопросам: @admin"
                )
                
            elif action == "complete":
                b['status'] = 'completed'
                await notify_user(
                    b['user_id'],
                    f"✔️ <b>Запись выполнена!</b>\n\n"
                    f"💎 {b['service_name']}\n"
                    f"📅 {b['date']} в {b['time']}\n\n"
                    f"Будем рады видеть вас снова! ⭐️\n\n"
                    f"🎁 <b>Оставьте отзыв и получите промокод на 10% скидку!</b>"
                )
                
                await notify_admin(
                    f"✔️ Запись #{booking_id} отмечена как выполненная.\n"
                    f"Клиенту отправлено предложение оставить отзыв."
                )
            
            if old_status != b['status']:
                await notify_admin(
                    f"📊 Статус записи #{booking_id} изменен:\n"
                    f"{old_status} → {b['status']}\n"
                    f"Клиент: @{b['username']}"
                )
            
            break
    
    save_bookings(bookings)
    await callback.answer(f"✅ Статус изменен")
    
    callback.data = f"admin_booking_{booking_id}"
    await admin_booking_detail(callback)

# ---------- МОДЕРАЦИЯ ОТЗЫВОВ ----------
@dp.callback_query(F.data == "admin_reviews")
async def admin_reviews(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    try:
        await callback.message.edit_text(
            "⭐️ <b>Модерация отзывов</b>\n\nВыберите отзыв для проверки:",
            reply_markup=reviews_moderation_keyboard()
        )
    except:
        await callback.message.answer(
            "⭐️ <b>Модерация отзывов</b>\n\nВыберите отзыв для проверки:",
            reply_markup=reviews_moderation_keyboard()
        )

@dp.callback_query(F.data.startswith("moderate_review_"))
async def moderate_review(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    review_id = int(callback.data.replace("moderate_review_", ""))
    reviews = get_reviews()
    review = next((r for r in reviews if r['id'] == review_id), None)
    
    if not review:
        await callback.answer("❌ Отзыв не найдена")
        return
    
    text = (
        f"⭐️ <b>Отзыв #{review['id']}</b>\n\n"
        f"👤 Пользователь: {review['username']}\n"
        f"⭐️ Оценка: {'⭐️' * review['rating']}\n"
        f"📝 Текст: {review['text']}\n"
        f"🕐 Дата: {review.get('created_at', 'неизвестно')}\n\n"
        f"Фото: {'✅ есть' if review.get('photo_link') else '❌ нет'}"
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=review_moderate_keyboard(review_id))
    except:
        await callback.message.answer(text, reply_markup=review_moderate_keyboard(review_id))

@dp.callback_query(F.data.startswith("approve_review_"))
async def approve_review(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    review_id = int(callback.data.replace("approve_review_", ""))
    reviews = get_reviews()
    
    review = None
    for r in reviews:
        if r['id'] == review_id:
            r['approved'] = True
            review = r
            break
    
    save_reviews(reviews)
    
    if review:
        await notify_user(
            review['user_id'],
            f"✅ <b>Ваш отзыв одобрен!</b>\n\n"
            f"Спасибо, что поделились мнением! ⭐️"
        )
    
    await callback.answer("✅ Отзыв одобрен")
    await admin_reviews(callback)

@dp.callback_query(F.data.startswith("reject_review_"))
async def reject_review(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    review_id = int(callback.data.replace("reject_review_", ""))
    reviews = get_reviews()
    
    review = next((r for r in reviews if r['id'] == review_id), None)
    
    reviews = [r for r in reviews if r['id'] != review_id]
    save_reviews(reviews)
    
    if review:
        await notify_user(
            review['user_id'],
            f"❌ <b>Ваш отзыв не прошел модерацию.</b>\n\n"
            f"Пожалуйста, ознакомьтесь с правилами публикации отзывов и попробуйте снова."
        )
    
    await callback.answer("❌ Отзыв отклонен и удален")
    await admin_reviews(callback)

# ---------- ПРОМОКОДЫ (АДМИНКА) ----------
@dp.callback_query(F.data == "admin_promocodes")
async def admin_promocodes(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    promocodes = get_promocodes()
    active = [p for p in promocodes if not p.get('used', False)]
    used = [p for p in promocodes if p.get('used', False)]
    
    text = (
        f"🎟 <b>Управление промокодами</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего промокодов: {len(promocodes)}\n"
        f"• Активных: {len(active)}\n"
        f"• Использовано: {len(used)}\n\n"
    )
    
    if active[:5]:
        text += "📋 <b>Последние активные:</b>\n"
        for promo in active[:5]:
            user_info = "Для всех" if promo['user_id'] == 'all' else f"ID: {promo['user_id']}"
            text += f"• <code>{promo['code']}</code> - {promo['discount']}% ({user_info})\n"
    
    kb = [
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin")]
    ]
    
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ---------- СОЗДАНИЕ ПРОМОКОДА АДМИНОМ ----------
@dp.callback_query(F.data == "admin_create_promo")
async def admin_create_promo(callback: types.CallbackQuery, state: FSMContext):
    """Создание промокода админом"""
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminStates.waiting_promo_user_id)
    try:
        await callback.message.edit_text(
            "🎟 <b>Создание промокода</b>\n\n"
            "Введите ID пользователя (можно узнать через @userinfobot),\n"
            "или отправьте 'all' для создания общего промокода:",
            reply_markup=cancel_keyboard()
        )
    except:
        await callback.message.answer(
            "🎟 <b>Создание промокода</b>\n\n"
            "Введите ID пользователя (можно узнать через @userinfobot),\n"
            "или отправьте 'all' для создания общего промокода:",
            reply_markup=cancel_keyboard()
        )

@dp.message(AdminStates.waiting_promo_user_id)
async def admin_promo_user_id(message: types.Message, state: FSMContext):
    """Получение ID пользователя для промокода"""
    user_input = message.text.strip()
    
    if user_input.lower() == 'all':
        await state.update_data(promo_user_id='all')
    else:
        try:
            user_id = int(user_input)
            await state.update_data(promo_user_id=user_id)
        except ValueError:
            await message.answer("❌ Введите корректный ID пользователя или 'all'")
            return
    
    await state.set_state(AdminStates.waiting_promo_discount)
    await message.answer(
        "🎟 Введите размер скидки в процентах (например: 10, 15, 20):",
        reply_markup=cancel_keyboard()
    )

@dp.message(AdminStates.waiting_promo_discount)
async def admin_promo_discount(message: types.Message, state: FSMContext):
    """Получение размера скидки"""
    try:
        discount = int(message.text)
        if discount < 1 or discount > 100:
            await message.answer("❌ Скидка должна быть от 1 до 100%")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    await state.update_data(promo_discount=discount)
    await state.set_state(AdminStates.waiting_promo_confirm)
    
    data = await state.get_data()
    user_text = "ВСЕМ пользователям" if data['promo_user_id'] == 'all' else f"пользователю ID: {data['promo_user_id']}"
    
    await message.answer(
        f"🎟 <b>Подтверждение промокода</b>\n\n"
        f"Скидка: {discount}%\n"
        f"Для: {user_text}\n\n"
        f"Подтвердите создание:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Создать", callback_data="confirm_create_promo")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_promocodes")]
        ])
    )

@dp.callback_query(AdminStates.waiting_promo_confirm, F.data == "confirm_create_promo")
async def admin_confirm_create_promo(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение создания промокода"""
    data = await state.get_data()
    
    promocodes = get_promocodes()
    
    promo_code = generate_promo_code(0)
    
    new_promo = {
        "id": len(promocodes) + 1,
        "user_id": data['promo_user_id'],
        "code": promo_code,
        "discount": data['promo_discount'],
        "used": False,
        "created_at": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "created_by": "admin"
    }
    promocodes.append(new_promo)
    save_promocodes(promocodes)
    
    if data['promo_user_id'] != 'all':
        try:
            await bot.send_message(
                data['promo_user_id'],
                f"🎁 <b>Вам выдан промокод!</b>\n\n"
                f"Код: <code>{promo_code}</code>\n"
                f"Скидка: {data['promo_discount']}%\n"
                f"Действителен 30 дней"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {data['promo_user_id']}: {e}")
    
    try:
        await callback.message.edit_text(
            f"✅ <b>Промокод успешно создан!</b>\n\n"
            f"Код: <code>{promo_code}</code>\n"
            f"Скидка: {data['promo_discount']}%\n"
            f"Для: {'всех пользователей' if data['promo_user_id'] == 'all' else 'пользователя ' + str(data['promo_user_id'])}\n\n"
            f"Промокод действителен 30 дней.",
            reply_markup=back_keyboard()
        )
    except:
        await callback.message.answer(
            f"✅ <b>Промокод успешно создан!</b>\n\n"
            f"Код: <code>{promo_code}</code>\n"
            f"Скидка: {data['promo_discount']}%\n"
            f"Для: {'всех пользователей' if data['promo_user_id'] == 'all' else 'пользователя ' + str(data['promo_user_id'])}\n\n"
            f"Промокод действителен 30 дней.",
            reply_markup=back_keyboard()
        )
    await state.clear()

# ---------- СТАТИСТИКА ----------
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    bookings = get_bookings()
    reviews = get_reviews()
    promocodes = get_promocodes()
    
    total = len(bookings)
    pending = len([b for b in bookings if b['status'] == 'pending'])
    confirmed = len([b for b in bookings if b['status'] == 'confirmed'])
    completed = len([b for b in bookings if b['status'] == 'completed'])
    cancelled = len([b for b in bookings if b['status'] == 'cancelled'])
    
    total_revenue = sum(b['price'] for b in bookings if b['status'] == 'completed')
    unique_clients = len(set(b['user_id'] for b in bookings))
    
    today = datetime.now().strftime("%Y-%m-%d")
    today_bookings = [b for b in bookings if b['date'] == today]
    
    total_reviews = len(reviews)
    approved_reviews = len([r for r in reviews if r.get('approved', False)])
    
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"📅 <b>Сегодня:</b> {len(today_bookings)} записей\n\n"
        f"📋 <b>Всего записей:</b> {total}\n"
        f"⏳ Ожидают: {pending}\n"
        f"✅ Подтверждено: {confirmed}\n"
        f"✔️ Выполнено: {completed}\n"
        f"❌ Отменено: {cancelled}\n\n"
        f"💰 <b>Выручка:</b> {total_revenue} руб.\n"
        f"👥 <b>Клиентов:</b> {unique_clients}\n\n"
        f"⭐️ <b>Отзывы:</b> {approved_reviews}/{total_reviews} одобрено\n"
        f"🎟 <b>Промокодов:</b> {len(promocodes)} выдано\n\n"
    )
    
    services = get_services()
    text += "📦 <b>По услугам:</b>\n"
    for service in services:
        service_bookings = [b for b in bookings if b['service_name'] == service['name']]
        service_completed = [b for b in service_bookings if b['status'] == 'completed']
        if service_bookings:
            revenue = sum(b['price'] for b in service_completed)
            text += f"• {service['name']}: {len(service_bookings)} записей, {revenue} руб.\n"
    
    try:
        await callback.message.edit_text(text, reply_markup=back_keyboard())
    except:
        await callback.message.answer(text, reply_markup=back_keyboard())

# ---------- РАССЫЛКА ----------
@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminStates.broadcast_message)
    try:
        await callback.message.edit_text(
            "📢 <b>Рассылка клиентам</b>\n\n"
            "Отправьте сообщение для рассылки (текст, фото или видео):\n\n"
            "⚠️ Будет отправлено ВСЕМ клиентам, которые хоть раз записывались!",
            reply_markup=cancel_keyboard()
        )
    except:
        await callback.message.answer(
            "📢 <b>Рассылка клиентам</b>\n\n"
            "Отправьте сообщение для рассылки (текст, фото или видео):\n\n"
            "⚠️ Будет отправлено ВСЕМ клиентам, которые хоть раз записывались!",
            reply_markup=cancel_keyboard()
        )

@dp.message(AdminStates.broadcast_message)
async def broadcast_get_message(message: types.Message, state: FSMContext):
    broadcast_data = {
        'type': message.content_type,
        'text': message.text or message.caption,
    }
    
    if message.photo:
        broadcast_data['photo'] = message.photo[-1].file_id
    if message.video:
        broadcast_data['video'] = message.video.file_id
    
    await state.update_data(broadcast=broadcast_data)
    await state.set_state(AdminStates.broadcast_confirm)
    
    bookings = get_bookings()
    users = set(b['user_id'] for b in bookings)
    
    preview = f"📢 <b>Предпросмотр рассылки:</b>\n\n{message.text or message.caption}\n\n"
    
    if message.photo:
        await message.answer_photo(
            photo=message.photo[-1].file_id,
            caption=preview + f"Будет отправлено <b>{len(users)}</b> пользователям.\n\nПодтвердите отправку:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin")]
            ])
        )
    else:
        await message.answer(
            preview + f"Будет отправлено <b>{len(users)}</b> пользователям.\n\nПодтвердите отправку:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin")]
            ])
        )

@dp.callback_query(AdminStates.broadcast_confirm, F.data == "broadcast_confirm")
async def broadcast_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    broadcast = data['broadcast']
    
    bookings = get_bookings()
    users = set(b['user_id'] for b in bookings)
    
    await callback.message.edit_text(f"📢 Начинаю рассылку {len(users)} пользователям...")
    
    success = 0
    failed = 0
    
    for user_id in users:
        try:
            if broadcast['type'] == 'text':
                await bot.send_message(user_id, broadcast['text'])
            elif broadcast['type'] == 'photo':
                await bot.send_photo(user_id, broadcast['photo'], caption=broadcast['text'])
            elif broadcast['type'] == 'video':
                await bot.send_video(user_id, broadcast['video'], caption=broadcast['text'])
            success += 1
            
            if success % 10 == 0:
                await asyncio.sleep(1)
                
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
    
    await callback.message.answer(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📨 Отправлено: {success}\n"
        f"❌ Ошибок: {failed}",
        reply_markup=admin_menu()
    )
    
    await notify_admin(
        f"📊 <b>Отчет о рассылке:</b>\n"
        f"Успешно: {success}\n"
        f"Ошибок: {failed}"
    )
    
    await state.clear()

# ============================================
# ЗАПУСК ПЛАНИРОВЩИКА
# ============================================
async def scheduler():
    await check_reminders()

# ============================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================
async def on_startup():
    """Действия при запуске"""
    logger.info("Бот запускается...")
    asyncio.create_task(scheduler())

async def main():
    await on_startup()
    logger.info("Бот готов к работе через вебхуки!")

# ============================================
# ЗАПУСК
# ============================================
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(main())
    
    logger.info("Flask запускается...")
    app.run(host="0.0.0.0", port=PORT)
