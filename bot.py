import os
import logging
import asyncio
import json
from datetime import datetime, timedelta
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    FSInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ============================================
# НАСТРОЙКИ
# ============================================
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 775020198  # ← ТВОЙ ID
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
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

# ============================================
# БАЗА ДАННЫХ (JSON-файлы, пока нет MongoDB)
# ============================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def load_json(filename):
    """Загрузить данные из JSON"""
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_json(filename, data):
    """Сохранить данные в JSON"""
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
    adding_service_photo = State()
    broadcast_message = State()
    broadcast_confirm = State()

# ============================================
# ПРОВЕРКА НА АДМИНА
# ============================================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# ============================================
# КЛАВИАТУРЫ
# ============================================
def main_menu():
    """Главное меню"""
    kb = [
        [InlineKeyboardButton(text="🛠 Услуги и цены", callback_data="services")],
        [InlineKeyboardButton(text="📅 Мои записи", callback_data="my_bookings")],
        [InlineKeyboardButton(text="⭐️ Отзывы", callback_data="reviews")],
        [InlineKeyboardButton(text="ℹ️ Информация", callback_data="info")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_menu():
    """Админ-меню"""
    kb = [
        [InlineKeyboardButton(text="📦 Управление услугами", callback_data="admin_services")],
        [InlineKeyboardButton(text="📋 Все записи", callback_data="admin_bookings")],
        [InlineKeyboardButton(text="⭐️ Модерация отзывов", callback_data="admin_reviews")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Выход", callback_data="back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def services_keyboard():
    """Клавиатура услуг"""
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
    """Действия с услугой"""
    kb = [
        [InlineKeyboardButton(text="📝 Записаться", callback_data=f"book_{service_id}")],
        [InlineKeyboardButton(text="🔙 К услугам", callback_data="services")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def date_keyboard():
    """Клавиатура с датами"""
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
    """Клавиатура с временем"""
    kb = []
    # С 10 до 20 каждый час
    for hour in range(10, 21):
        time_str = f"{hour:02d}:00"
        kb.append([InlineKeyboardButton(
            text=time_str,
            callback_data=f"time_{time_str}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 К датам", callback_data="back_to_dates")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def confirm_keyboard():
    """Подтверждение"""
    kb = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_booking"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="services")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def reviews_menu_keyboard():
    """Меню отзывов"""
    kb = [
        [InlineKeyboardButton(text="👀 Посмотреть отзывы", callback_data="show_reviews")],
        [InlineKeyboardButton(text="✏️ Оставить отзыв", callback_data="leave_review")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def rating_keyboard():
    """Клавиатура с оценками"""
    kb = []
    for i in range(1, 6):
        kb.append([InlineKeyboardButton(
            text="⭐️" * i,
            callback_data=f"rating_{i}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def photo_options_keyboard():
    """Опции фото"""
    kb = [
        [
            InlineKeyboardButton(text="📸 Добавить фото", callback_data="add_photo"),
            InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_photo")
        ],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_services_keyboard():
    """Админка - услуги"""
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

def admin_edit_service_keyboard(service_id):
    """Админка - редактирование услуги"""
    kb = [
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_edit_{service_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_{service_id}")],
        [InlineKeyboardButton(text="🔄 Активировать/Деактивировать", callback_data=f"admin_toggle_{service_id}")],
        [InlineKeyboardButton(text="🔙 К услугам", callback_data="admin_services")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_bookings_keyboard():
    """Админка - фильтры записей"""
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
    """Кнопки для конкретной записи"""
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
    """Модерация отзывов"""
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
    """Кнопки для конкретного отзыва"""
    kb = [
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_review_{review_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_review_{review_id}")
        ],
        [InlineKeyboardButton(text="🔙 К модерации", callback_data="admin_reviews")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_keyboard():
    """Простая кнопка назад"""
    kb = [[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def cancel_keyboard():
    """Кнопка отмены"""
    kb = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ============================================
# ОБРАБОТЧИКИ
# ============================================

# ---------- СТАРТ ----------
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Приветствие с картинкой"""
    user = message.from_user
    logger.info(f"Пользователь {user.full_name} запустил бота")
    
    # Текст приветствия
    welcome_text = (
        f"🔥 *Привет, {user.first_name}!*\n\n"
        f"Я *демо-бот*, созданный чтобы показать, что умеют мои боты!\n\n"
        f"Вот что я умею:\n"
        f"✅ Показывать услуги с ценами и фото\n"
        f"✅ Записывать на удобное время\n"
        f"✅ Хранить историю записей\n"
        f"✅ Отзывы с фотографиями\n"
        f"✅ Уведомления и напоминания\n"
        f"✅ Админ-панель с управлением\n\n"
        f"👇 <b>Выбери, что хочешь посмотреть:</b>"
    )
    
    # Отправляем фото (сначала нужно загрузить картинку в бота)
    # Если картинки нет - отправляем без фото
    try:
        # Пробуем отправить фото (если файл есть)
        photo = FSInputFile("welcome.jpg")  # Загрузи эту картинку в репозиторий!
        await message.answer_photo(
            photo=photo,
            caption=welcome_text,
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    except:
        # Если фото нет - просто текст
        await message.answer(
            welcome_text,
            parse_mode="HTML",
            reply_markup=main_menu()
        )

# ---------- ОБРАБОТКА КНОПОК ----------
@dp.callback_query(F.data == "back")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    """Назад в главное меню"""
    await state.clear()
    await callback.message.edit_text(
        "🔥 *Главное меню:*",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "cancel")
async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
    """Отмена действия"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено.\n\nГлавное меню:",
        reply_markup=main_menu()
    )

# ---------- УСЛУГИ ----------
@dp.callback_query(F.data == "services")
async def show_services(callback: types.CallbackQuery):
    """Показать услуги"""
    services = get_services()
    
    if not services:
        # Если услуг нет, создаем демо-услуги
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
            text += f"💎 *{service['name']}*\n"
            text += f"💰 {service['price']} руб.\n"
            text += f"⏱ {service['duration']} мин.\n"
            text += f"📝 {service['desc']}\n\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=services_keyboard()
    )

@dp.callback_query(F.data.startswith("service_"))
async def service_detail(callback: types.CallbackQuery, state: FSMContext):
    """Детали конкретной услуги"""
    service_id = int(callback.data.replace("service_", ""))
    services = get_services()
    service = next((s for s in services if s['id'] == service_id), None)
    
    if not service:
        await callback.answer("❌ Услуга не найдена")
        return
    
    # Сохраняем в состояние
    await state.update_data(
        service_id=service_id,
        service_name=service['name'],
        service_price=service['price'],
        service_duration=service['duration']
    )
    
    text = (
        f"💎 *{service['name']}*\n\n"
        f"💰 Цена: {service['price']} руб.\n"
        f"⏱ Длительность: {service['duration']} мин.\n\n"
        f"📝 {service['desc']}"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=service_actions_keyboard(service_id)
    )

# ---------- ЗАПИСЬ ----------
@dp.callback_query(F.data.startswith("book_"))
async def start_booking(callback: types.CallbackQuery, state: FSMContext):
    """Начать запись"""
    await state.set_state(BookingStates.choosing_date)
    
    await callback.message.edit_text(
        "📅 Выберите дату:",
        reply_markup=date_keyboard()
    )

@dp.callback_query(BookingStates.choosing_date, F.data.startswith("date_"))
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
    """Выбор даты"""
    date_str = callback.data.replace("date_", "")
    await state.update_data(booking_date=date_str)
    await state.set_state(BookingStates.choosing_time)
    
    # Форматируем дату для красоты
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    display_date = date_obj.strftime("%d.%m.%Y")
    
    await callback.message.edit_text(
        f"📅 Дата: {display_date}\n\n⏰ Выберите время:",
        reply_markup=time_keyboard()
    )

@dp.callback_query(BookingStates.choosing_time, F.data.startswith("time_"))
async def choose_time(callback: types.CallbackQuery, state: FSMContext):
    """Выбор времени"""
    time_str = callback.data.replace("time_", "")
    await state.update_data(booking_time=time_str)
    
    data = await state.get_data()
    
    text = (
        f"✅ *Подтверждение записи*\n\n"
        f"💎 Услуга: {data['service_name']}\n"
        f"💰 Цена: {data['service_price']} руб.\n"
        f"📅 Дата: {data['booking_date']}\n"
        f"⏰ Время: {time_str}\n\n"
        f"Всё верно?"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=confirm_keyboard()
    )
    await state.set_state(BookingStates.confirming)

@dp.callback_query(BookingStates.confirming, F.data == "confirm_booking")
async def confirm_booking(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение записи"""
    data = await state.get_data()
    
    # Создаем запись
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
        "created_at": datetime.now().isoformat()
    }
    bookings.append(new_booking)
    save_bookings(bookings)
    
    # Уведомление админу
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔔 *НОВАЯ ЗАПИСЬ!*\n\n"
            f"👤 Клиент: @{callback.from_user.username or callback.from_user.full_name}\n"
            f"💎 Услуга: {data['service_name']}\n"
            f"📅 Дата: {data['booking_date']}\n"
            f"⏰ Время: {data['booking_time']}\n"
            f"💰 Цена: {data['service_price']} руб."
        )
    except:
        pass
    
    await callback.message.edit_text(
        f"✅ *Запись подтверждена!*\n\n"
        f"Я отправил уведомление мастеру. Вы получите подтверждение в ближайшее время.\n\n"
        f"Посмотреть свои записи можно в разделе «📅 Мои записи».",
        parse_mode="HTML"
    )
    
    # Возвращаем в главное меню через 3 секунды
    await asyncio.sleep(3)
    await callback.message.answer(
        "🔥 Главное меню:",
        reply_markup=main_menu()
    )
    await state.clear()

@dp.callback_query(F.data == "back_to_dates")
async def back_to_dates(callback: types.CallbackQuery, state: FSMContext):
    """Назад к выбору даты"""
    await state.set_state(BookingStates.choosing_date)
    await callback.message.edit_text(
        "📅 Выберите дату:",
        reply_markup=date_keyboard()
    )

# ---------- МОИ ЗАПИСИ ----------
@dp.callback_query(F.data == "my_bookings")
async def my_bookings(callback: types.CallbackQuery):
    """Показать записи пользователя"""
    user_id = callback.from_user.id
    bookings = get_bookings()
    user_bookings = [b for b in bookings if b['user_id'] == user_id]
    
    if not user_bookings:
        await callback.message.edit_text(
            "😕 У вас пока нет записей.\n\n"
            "Хотите записаться? Перейдите в «🛠 Услуги».",
            reply_markup=back_keyboard()
        )
        return
    
    text = "📋 *Ваши записи:*\n\n"
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
        
        if booking['status'] == 'pending':
            text += f"   ⏳ Ожидает подтверждения\n"
        elif booking['status'] == 'confirmed':
            text += f"   ✅ Подтверждено\n"
        elif booking['status'] == 'completed':
            text += f"   ✔️ Выполнено\n"
        elif booking['status'] == 'cancelled':
            text += f"   ❌ Отменено\n"
        text += "\n"
    
    # Добавляем кнопку отмены для ожидающих записей
    kb = [[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
    pending_bookings = [b for b in user_bookings if b['status'] == 'pending']
    if pending_bookings:
        kb.insert(0, [InlineKeyboardButton(text="❌ Отменить запись", callback_data="cancel_booking_menu")])
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data == "cancel_booking_menu")
async def cancel_booking_menu(callback: types.CallbackQuery):
    """Меню отмены записи"""
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
    
    await callback.message.edit_text(
        "❌ Выберите запись для отмены:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery):
    """Отмена конкретной записи"""
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    bookings = get_bookings()
    
    for booking in bookings:
        if booking['id'] == booking_id:
            booking['status'] = 'cancelled'
            break
    
    save_bookings(bookings)
    await callback.answer("✅ Запись отменена")
    
    # Возвращаем к списку записей
    await my_bookings(callback)

# ---------- ОТЗЫВЫ ----------
@dp.callback_query(F.data == "reviews")
async def reviews_menu(callback: types.CallbackQuery):
    """Меню отзывов"""
    await callback.message.edit_text(
        "⭐️ *Отзывы*\n\n"
        "Здесь вы можете посмотреть отзывы других клиентов или оставить свой.",
        parse_mode="HTML",
        reply_markup=reviews_menu_keyboard()
    )

@dp.callback_query(F.data == "show_reviews")
async def show_reviews(callback: types.CallbackQuery):
    """Показать одобренные отзывы"""
    reviews = get_reviews()
    approved = [r for r in reviews if r.get('approved', False)]
    
    if not approved:
        await callback.message.edit_text(
            "😕 Пока нет отзывов. Будьте первым!",
            reply_markup=reviews_menu_keyboard()
        )
        return
    
    text = "⭐️ *Отзывы наших клиентов:*\n\n"
    for review in approved[-5:]:
        text += f"👤 <b>{review['username']}</b>\n"
        text += f"⭐️ {'⭐️' * review['rating']}\n"
        text += f"📝 {review['text']}\n\n"
    
    kb = [[InlineKeyboardButton(text="✏️ Оставить отзыв", callback_data="leave_review")],
          [InlineKeyboardButton(text="🔙 Назад", callback_data="reviews")]]
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data == "leave_review")
async def leave_review(callback: types.CallbackQuery, state: FSMContext):
    """Начать оставление отзыва"""
    # Проверяем, был ли клиент
    bookings = get_bookings()
    user_bookings = [b for b in bookings if b['user_id'] == callback.from_user.id and b['status'] == 'completed']
    
    if not user_bookings:
        await callback.answer(
            "❌ Оставлять отзывы могут только клиенты, которые уже посетили мастера.",
            show_alert=True
        )
        return
    
    await state.set_state(ReviewStates.waiting_text)
    await callback.message.edit_text(
        "📝 Напишите ваш отзыв:",
        reply_markup=cancel_keyboard()
    )

@dp.message(ReviewStates.waiting_text)
async def process_review_text(message: types.Message, state: FSMContext):
    """Обработка текста отзыва"""
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
    """Обработка оценки"""
    rating = int(callback.data.replace("rating_", ""))
    await state.update_data(rating=rating)
    await state.set_state(ReviewStates.waiting_photo)
    
    await callback.message.edit_text(
        "📸 Теперь можете добавить фото к отзыву (или пропустите):",
        reply_markup=photo_options_keyboard()
    )

@dp.callback_query(ReviewStates.waiting_photo, F.data == "add_photo")
async def add_photo_prompt(callback: types.CallbackQuery):
    """Запрос фото"""
    await callback.message.edit_text(
        "📸 Отправьте фото:",
        reply_markup=cancel_keyboard()
    )

@dp.message(ReviewStates.waiting_photo, F.photo)
async def process_review_photo(message: types.Message, state: FSMContext):
    """Сохранение отзыва с фото"""
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    reviews = get_reviews()
    new_review = {
        "id": len(reviews) + 1,
        "user_id": message.from_user.id,
        "username": message.from_user.username or message.from_user.full_name,
        "text": data['review_text'],
        "rating": data['rating'],
        "photo_id": photo_id,
        "approved": False,
        "created_at": datetime.now().isoformat()
    }
    reviews.append(new_review)
    save_reviews(reviews)
    
    await message.answer(
        "✅ Спасибо за отзыв! Он появится после проверки администратором.",
        reply_markup=main_menu()
    )
    await state.clear()

@dp.callback_query(ReviewStates.waiting_photo, F.data == "skip_photo")
async def skip_photo(callback: types.CallbackQuery, state: FSMContext):
    """Пропуск фото"""
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
    
    await callback.message.edit_text(
        "✅ Спасибо за отзыв! Он появится после проверки администратором.",
        reply_markup=main_menu()
    )
    await state.clear()

# ---------- ИНФО ----------
@dp.callback_query(F.data == "info")
async def show_info(callback: types.CallbackQuery):
    """Показать информацию"""
    text = (
        "ℹ️ *Информация*\n\n"
        "📍 *Адрес:* ул. Примерная, д. 123\n"
        "⏰ *Режим работы:* 10:00 - 22:00 ежедневно\n"
        "📞 *Телефон:* +7 (999) 123-45-67\n"
        "💳 *Оплата:* наличные, перевод\n\n"
        "⚠️ *Важно:*\n"
        "• Отмена записи возможна не позднее, чем за 2 часа\n"
        "• При опоздании более 15 минут запись может быть отменена\n"
        "• По всем вопросам пишите @x40vef4yX"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )

# ============================================
# АДМИН-ПАНЕЛЬ
# ============================================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    """Вход в админку"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return
    
    await message.answer(
        "👑 *Админ-панель*\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=admin_menu()
    )

@dp.callback_query(F.data == "admin")
async def admin_panel_callback(callback: types.CallbackQuery):
    """Админка из callback"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен")
        return
    
    await callback.message.edit_text(
        "👑 *Админ-панель*\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=admin_menu()
    )

# ---------- УПРАВЛЕНИЕ УСЛУГАМИ ----------
@dp.callback_query(F.data == "admin_services")
async def admin_services(callback: types.CallbackQuery):
    """Управление услугами"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.edit_text(
        "📦 *Управление услугами*\n\n"
        "Выберите услугу для редактирования или добавьте новую:",
        parse_mode="HTML",
        reply_markup=admin_services_keyboard()
    )

@dp.callback_query(F.data == "admin_add_service")
async def admin_add_service_start(callback: types.CallbackQuery, state: FSMContext):
    """Добавление услуги - название"""
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminStates.adding_service_name)
    await callback.message.edit_text(
        "➕ *Добавление новой услуги*\n\n"
        "Введите название услуги:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )

@dp.message(AdminStates.adding_service_name)
async def admin_add_service_name(message: types.Message, state: FSMContext):
    """Добавление услуги - сохранение названия"""
    await state.update_data(service_name=message.text)
    await state.set_state(AdminStates.adding_service_price)
    
    await message.answer(
        "💰 Введите цену в рублях (только число):",
        reply_markup=cancel_keyboard()
    )

@dp.message(AdminStates.adding_service_price)
async def admin_add_service_price(message: types.Message, state: FSMContext):
    """Добавление услуги - цена"""
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
    """Добавление услуги - длительность"""
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
    """Добавление услуги - описание"""
    await state.update_data(service_desc=message.text)
    
    data = await state.get_data()
    
    # Создаем новую услугу
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
        f"✅ Услуга *{data['service_name']}* успешно добавлена!",
        parse_mode="HTML"
    )
    
    await admin_services_callback(message)
    await state.clear()

async def admin_services_callback(message: types.Message):
    """Вспомогательная функция для возврата к админке"""
    await message.answer(
        "📦 *Управление услугами*",
        parse_mode="HTML",
        reply_markup=admin_services_keyboard()
    )

# ---------- ПРОСМОТР ЗАПИСЕЙ ----------
@dp.callback_query(F.data == "admin_bookings")
async def admin_bookings_menu(callback: types.CallbackQuery):
    """Меню просмотра записей"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.edit_text(
        "📋 *Просмотр записей*\n\n"
        "Выберите фильтр:",
        parse_mode="HTML",
        reply_markup=admin_bookings_keyboard()
    )

@dp.callback_query(F.data.startswith("admin_bookings_"))
async def admin_bookings_list(callback: types.CallbackQuery):
    """Список записей по фильтру"""
    if not is_admin(callback.from_user.id):
        return
    
    filter_type = callback.data.replace("admin_bookings_", "")
    bookings = get_bookings()
    
    if filter_type != "all":
        bookings = [b for b in bookings if b['status'] == filter_type]
    
    bookings = sorted(bookings, key=lambda x: x['date'], reverse=True)
    
    if not bookings:
        await callback.message.edit_text(
            "📋 Нет записей",
            reply_markup=admin_bookings_keyboard()
        )
        return
    
    text = f"📋 *Записи: {filter_type}*\n\n"
    
    for booking in bookings[:10]:
        status_emoji = {
            'pending': '⏳',
            'confirmed': '✅',
            'completed': '✔️',
            'cancelled': '❌'
        }.get(booking['status'], '❓')
        
        text += f"{status_emoji} *#{booking['id']}*\n"
        text += f"   👤 {booking['username']}\n"
        text += f"   💎 {booking['service_name']}\n"
        text += f"   📅 {booking['date']} в {booking['time']}\n"
        text += f"   💰 {booking['price']} руб.\n"
        text += f"   [Подробнее](booking_{booking['id']})\n\n"
    
    # Добавляем кнопки для перехода к конкретным записям
    kb = []
    for booking in bookings[:5]:
        kb.append([InlineKeyboardButton(
            text=f"#{booking['id']} - {booking['service_name']}",
            callback_data=f"admin_booking_{booking['id']}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_bookings")])
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("admin_booking_"))
async def admin_booking_detail(callback: types.CallbackQuery):
    """Детали конкретной записи"""
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
        f"📋 *Запись #{booking['id']}*\n\n"
        f"👤 Клиент: {booking['username']} (ID: {booking['user_id']})\n"
        f"💎 Услуга: {booking['service_name']}\n"
        f"💰 Цена: {booking['price']} руб.\n"
        f"📅 Дата: {booking['date']}\n"
        f"⏰ Время: {booking['time']}\n"
        f"📊 Статус: {status_text}\n"
        f"🕐 Создано: {booking.get('created_at', 'неизвестно')}"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=booking_actions_keyboard(booking_id, booking['status'])
    )

@dp.callback_query(F.data.startswith("booking_"))
async def admin_booking_action(callback: types.CallbackQuery):
    """Действия с записью"""
    if not is_admin(callback.from_user.id):
        return
    
    action, booking_id = callback.data.replace("booking_", "").split("_", 1)
    booking_id = int(booking_id)
    
    bookings = get_bookings()
    booking = None
    for b in bookings:
        if b['id'] == booking_id:
            booking = b
            if action == "confirm":
                b['status'] = 'confirmed'
                # Уведомление клиенту
                try:
                    await bot.send_message(
                        b['user_id'],
                        f"✅ *Запись подтверждена!*\n\n"
                        f"💎 {b['service_name']}\n"
                        f"📅 {b['date']} в {b['time']}\n\n"
                        f"Ждём вас!"
                    )
                except:
                    pass
            elif action == "cancel":
                b['status'] = 'cancelled'
                try:
                    await bot.send_message(
                        b['user_id'],
                        f"❌ *Запись отменена*\n\n"
                        f"💎 {b['service_name']}\n"
                        f"📅 {b['date']} в {b['time']}\n\n"
                        f"По вопросам: @admin"
                    )
                except:
                    pass
            elif action == "complete":
                b['status'] = 'completed'
                try:
                    await bot.send_message(
                        b['user_id'],
                        f"✔️ *Запись выполнена!*\n\n"
                        f"💎 {b['service_name']}\n"
                        f"📅 {b['date']} в {b['time']}\n\n"
                        f"Будем рады видеть вас снова! ⭐️"
                    )
                except:
                    pass
            break
    
    save_bookings(bookings)
    await callback.answer(f"✅ Статус изменен")
    await admin_booking_detail(callback)

# ---------- МОДЕРАЦИЯ ОТЗЫВОВ ----------
@dp.callback_query(F.data == "admin_reviews")
async def admin_reviews(callback: types.CallbackQuery):
    """Модерация отзывов"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.edit_text(
        "⭐️ *Модерация отзывов*\n\n"
        "Выберите отзыв для проверки:",
        parse_mode="HTML",
        reply_markup=reviews_moderation_keyboard()
    )

@dp.callback_query(F.data.startswith("moderate_review_"))
async def moderate_review(callback: types.CallbackQuery):
    """Модерация конкретного отзыва"""
    if not is_admin(callback.from_user.id):
        return
    
    review_id = int(callback.data.replace("moderate_review_", ""))
    reviews = get_reviews()
    review = next((r for r in reviews if r['id'] == review_id), None)
    
    if not review:
        await callback.answer("❌ Отзыв не найден")
        return
    
    text = (
        f"⭐️ *Отзыв #{review['id']}*\n\n"
        f"👤 Пользователь: {review['username']}\n"
        f"⭐️ Оценка: {'⭐️' * review['rating']}\n"
        f"📝 Текст: {review['text']}\n"
        f"🕐 Дата: {review.get('created_at', 'неизвестно')}\n\n"
        f"Фото: {'есть' if review.get('photo_id') else 'нет'}"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=review_moderate_keyboard(review_id)
    )

@dp.callback_query(F.data.startswith("approve_review_"))
async def approve_review(callback: types.CallbackQuery):
    """Одобрить отзыв"""
    if not is_admin(callback.from_user.id):
        return
    
    review_id = int(callback.data.replace("approve_review_", ""))
    reviews = get_reviews()
    
    for review in reviews:
        if review['id'] == review_id:
            review['approved'] = True
            break
    
    save_reviews(reviews)
    await callback.answer("✅ Отзыв одобрен")
    await admin_reviews(callback)

@dp.callback_query(F.data.startswith("reject_review_"))
async def reject_review(callback: types.CallbackQuery):
    """Отклонить отзыв"""
    if not is_admin(callback.from_user.id):
        return
    
    review_id = int(callback.data.replace("reject_review_", ""))
    reviews = get_reviews()
    reviews = [r for r in reviews if r['id'] != review_id]
    save_reviews(reviews)
    
    await callback.answer("❌ Отзыв отклонен и удален")
    await admin_reviews(callback)

# ---------- СТАТИСТИКА ----------
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    """Статистика"""
    if not is_admin(callback.from_user.id):
        return
    
    bookings = get_bookings()
    
    total = len(bookings)
    pending = len([b for b in bookings if b['status'] == 'pending'])
    confirmed = len([b for b in bookings if b['status'] == 'confirmed'])
    completed = len([b for b in bookings if b['status'] == 'completed'])
    cancelled = len([b for b in bookings if b['status'] == 'cancelled'])
    
    total_revenue = sum(b['price'] for b in bookings if b['status'] == 'completed')
    
    # Уникальные клиенты
    unique_clients = len(set(b['user_id'] for b in bookings))
    
    text = (
        f"📊 *Статистика*\n\n"
        f"📋 *Всего записей:* {total}\n"
        f"⏳ Ожидают: {pending}\n"
        f"✅ Подтверждено: {confirmed}\n"
        f"✔️ Выполнено: {completed}\n"
        f"❌ Отменено: {cancelled}\n\n"
        f"💰 <b>Выручка:</b> {total_revenue} руб.\n"
        f"👥 <b>Клиентов:</b> {unique_clients}\n\n"
    )
    
    # Статистика по услугам
    services = get_services()
    text += "📦 <b>По услугам:</b>\n"
    for service in services:
        service_bookings = [b for b in bookings if b['service_name'] == service['name']]
        service_completed = [b for b in service_bookings if b['status'] == 'completed']
        if service_bookings:
            text += f"• {service['name']}: {len(service_bookings)} записей, {len(service_completed)} выполнено\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )

# ---------- РАССЫЛКА ----------
@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """Начать рассылку"""
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminStates.broadcast_message)
    await callback.message.edit_text(
        "📢 *Рассылка клиентам*\n\n"
        "Отправьте сообщение для рассылки (текст, фото или видео):",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )

@dp.message(AdminStates.broadcast_message)
async def broadcast_get_message(message: types.Message, state: FSMContext):
    """Получение сообщения для рассылки"""
    # Сохраняем тип и содержимое
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
    
    # Получаем всех уникальных пользователей
    bookings = get_bookings()
    users = set(b['user_id'] for b in bookings)
    
    await message.answer(
        f"📢 *Предпросмотр рассылки:*\n\n"
        f"{message.text or message.caption}\n\n"
        f"Будет отправлено <b>{len(users)}</b> пользователям.\n\n"
        f"Подтвердите отправку:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin")]
        ])
    )

@dp.callback_query(AdminStates.broadcast_confirm, F.data == "broadcast_confirm")
async def broadcast_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение и отправка рассылки"""
    data = await state.get_data()
    broadcast = data['broadcast']
    
    # Получаем всех уникальных пользователей
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
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
    
    await callback.message.answer(
        f"✅ *Рассылка завершена!*\n\n"
        f"📨 Отправлено: {success}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="HTML",
        reply_markup=admin_menu()
    )
    await state.clear()

# ============================================
# ЗАПУСК
# ============================================

async def start_bot():
    """Запуск бота"""
    try:
        logger.info("Запускаем бота через aiogram...")
        await dp.start_polling(bot, handle_signals=False)
    except Exception as e:
        logger.error(f"Ошибка бота: {e}", exc_info=True)

def run_bot():
    """Запуск асинхронной функции"""
    asyncio.run(start_bot())

if __name__ == "__main__":
    # Запускаем бота в отдельном процессе
    import multiprocessing
    bot_process = multiprocessing.Process(target=run_bot)
    bot_process.daemon = True
    bot_process.start()
    logger.info("Бот запущен в отдельном процессе")
    
    # Запускаем Flask
    logger.info("Flask запускается...")
    app.run(host="0.0.0.0", port=PORT)
