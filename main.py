# -*- coding: utf-8 -*-
# Файл: main.py (Часть 1/4)

import asyncio
import logging
from flask import Flask
from threading import Thread
import os
import math # Для округления страниц

# Решение проблемы с EventLoop в Windows
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command, BaseFilter
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

import database as db

# --- НАСТРОЙКИ БОТА (КОНФИГУРАЦИЯ) ---
BOT_TOKEN = "8468997703:AAGuhe11JhsTrn0XMb-kHHz1QcRq837IP0M"
OWNER_ID = 5272076117  # ID Владельца
MARKET_CHANNEL_ID = -1002757279589  # ID Канала
CANCELLATION_FEE = 0.125
MAX_ITEMS_PER_USER = 5
ITEMS_PER_PAGE = 3 # Количество товаров на одной странице в списке

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)


# --- ФИЛЬТРЫ ---
class IsAdminFilter(BaseFilter):
    """
    Проверяет, является ли пользователь администратором И активна ли у него админ-панель.
    """
    async def __call__(self, message: types.Message) -> bool:
        is_admin = db.is_user_admin(message.from_user.id)
        is_panel_active = db.is_admin_panel_active(message.from_user.id)
        return is_admin and is_panel_active

class IsNotBannedFilter(BaseFilter):
    """
    Проверяет, не заблокирован ли пользователь.
    """
    async def __call__(self, event: types.Update) -> bool:
        user = getattr(event, 'from_user', None)
        if user is None:
            return True
        
        user_id = user.id
        if db.is_user_banned(user_id):
            logging.warning(f"Заблокированный пользователь {user_id} попытался выполнить действие.")
            if isinstance(event, types.Message):
                 await event.answer("Вы заблокированы и не можете использовать этого бота.")
            elif isinstance(event, types.CallbackQuery):
                 await event.answer("Вы заблокированы.", show_alert=True)
            return False
        return True

# --- КЛАССЫ ДЛЯ CALLBACK'ОВ И СОСТОЯНИЙ ---
class RegistrationCallback(CallbackData, prefix="register"):
    action: str
    user_id: int
    username: str
    chat_id: int
    msg_id: int

class BuyItemCallback(CallbackData, prefix="buy"):
    item_id: int

class ManageItemCallback(CallbackData, prefix="manage"):
    action: str
    item_id: int

class MyItemsPaginator(CallbackData, prefix="my_items"):
    action: str # 'page'
    page: int

class AddItemFSM(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_photo = State()
    waiting_for_price = State()

class AdminLoginFSM(StatesGroup):
    waiting_for_password = State()

# -*- coding: utf-8 -*-
# Файл: main.py (Часть 2/4)

# --- КЛАВИАТУРЫ ---
def get_main_menu_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Мой кошелек"); builder.button(text="🛍️ Мои товары")
    builder.button(text="👤 Моя анкета"); builder.button(text="➕ Добавить товар")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Памятка по командам") 
    builder.button(text="⬅️ Выйти из админ-панели")
    builder.adjust(1, 1)
    return builder.as_markup(resize_keyboard=True)

def get_cancel_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)

def get_buy_button(item_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Купить", callback_data=BuyItemCallback(item_id=item_id).pack())
    return builder.as_markup()

# --- ФУНКЦИЯ-ПОМОЩНИК ДЛЯ АДМИН-КОМАНД ---
async def resolve_user_id(message: types.Message, target_identifier: str) -> int | None:
    """
    Определяет user_id по ID или юзернейму.
    Отправляет сообщение об ошибке, если пользователь не найден.
    Возвращает ID или None.
    """
    target_user_id = None
    if target_identifier.isdigit():
        target_user_id = int(target_identifier)
    else:
        clean_username = target_identifier.lstrip('@')
        target_user_id = db.get_user_id_by_username(clean_username)

    if target_user_id is None or not db.user_exists(target_user_id):
        await message.answer(f"❌ Пользователь с идентификатором «{target_identifier}» не найден в базе данных.")
        return None
    
    return target_user_id


# --- ГЛАВНЫЕ ОБРАБОТЧИКИ (ДОСТУПНЫ ВСЕМ) ---
@dp.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext):
    await state.clear()
    if db.is_user_banned(message.from_user.id):
        await message.answer("Вы заблокированы и не можете использовать этого бота.")
        return
    
    if not db.user_exists(message.from_user.id):
        db.add_user(message.from_user.id, message.from_user.username or "user")
        await message.answer(
            f"Здравствуйте, <b>{message.from_user.full_name}</b>!\n\n"
            "Я торговый бот для вашей ролевой игры.\n"
            "Для полной регистрации, пожалуйста, <b>перешлите мне сообщение с вашей анкетой</b> из канала анкет."
        )
    else:
        db.update_username(message.from_user.id, message.from_user.username or "user")
        await message.answer(f"С возвращением, <b>{message.from_user.full_name}</b>!", reply_markup=get_main_menu_keyboard())


@dp.message(Command("help"))
async def handle_help(message: types.Message):
    text = (
        "<b>Справка по боту</b>\n\n"
        "Используйте кнопки в меню для взаимодействия с ботом.\n\n"
        "• <b>Мой кошелек</b> - проверить баланс.\n"
        "• <b>Мои товары</b> - посмотреть ваши товары.\n"
        "• <b>Моя анкета</b> - посмотреть вашу анкету.\n"
        "• <b>Добавить товар</b> - выставить товар на продажу."
    )
    if db.is_user_admin(message.from_user.id):
        text += "\n\nДля доступа к командам администратора введите <code>/admin</code>."
        
    await message.answer(text)

@dp.message(F.forward_from_chat)
async def handle_forwarded_anketa(message: types.Message):
    user = message.from_user
    if not db.user_exists(user.id):
        await message.answer("Пожалуйста, сначала напишите /start, чтобы начать.")
        return
    
    if not message.forward_from_chat or not message.forward_from_message_id:
        await message.answer("Пожалуйста, перешлите сообщение именно из канала, а не от пользователя или из закрытой группы.")
        return

    builder = InlineKeyboardBuilder()
    chat_id = message.forward_from_chat.id
    msg_id = message.forward_from_message_id
    
    builder.button(text="✅ Подтвердить", callback_data=RegistrationCallback(action="approve", user_id=user.id, username=user.username or "user", chat_id=chat_id, msg_id=msg_id).pack())
    builder.button(text="❌ Отклонить", callback_data=RegistrationCallback(action="decline", user_id=user.id, username=user.username or "user", chat_id=chat_id, msg_id=msg_id).pack())
    builder.adjust(2)
    
    confirmation_request_text = (f"⚠️ <b>Запрос на привязку анкеты</b> ⚠️\n\nПользователь: @{user.username} (ID: <code>{user.id}</code>)")
    admin_ids_from_db = db.get_all_admins()
    
    if not admin_ids_from_db:
        logging.warning("Нет администраторов для отправки запроса на регистрацию!")
        await message.answer("Не удалось найти администраторов для проверки. Обратитесь к владельцу бота.")
        return
        
    for admin_id in admin_ids_from_db:
        try:
            await bot.forward_message(chat_id=admin_id, from_chat_id=message.chat.id, message_id=message.message_id)
            await bot.send_message(chat_id=admin_id, text=confirmation_request_text, reply_markup=builder.as_markup())
        except Exception as e:
            logging.error(f"Не удалось отправить запрос администратору {admin_id}: {e}")
            
    await message.answer("✅ <b>Спасибо!</b>\nВаша анкета отправлена на проверку.")

# --- ОБРАБОТЧИКИ РЕГИСТРАЦИИ (ДО ГЛОБАЛЬНЫХ ФИЛЬТРОВ) ---
@dp.callback_query(RegistrationCallback.filter(F.action == "approve"))
async def handle_approve_callback(query: types.CallbackQuery, callback_data: RegistrationCallback):
    admin_username = query.from_user.username or "Администратор"
    
    db.set_user_anketa(user_id=callback_data.user_id, chat_id=callback_data.chat_id, message_id=callback_data.msg_id)
    try:
        await bot.send_message(chat_id=callback_data.user_id, text="🎉 <b>Поздравляем!</b>\n\nВаша анкета была одобрена и привязана к профилю.", reply_markup=get_main_menu_keyboard())
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление об одобрении пользователю {callback_data.user_id}: {e}")
    
    await query.message.edit_text(f"✅ Анкета для @{callback_data.username} <b>ОДОБРЕНА</b>\nАдминистратор: @{admin_username}")
    await query.answer("Анкета одобрена!")


@dp.callback_query(RegistrationCallback.filter(F.action == "decline"))
async def handle_decline_callback(query: types.CallbackQuery, callback_data: RegistrationCallback):
    admin_username = query.from_user.username or "Администратор"
    try:
        await bot.send_message(chat_id=callback_data.user_id, text="😔 <b>К сожалению...</b>\n\nВаша заявка на привязку анкеты была отклонена.")
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление об отклонении пользователю {callback_data.user_id}: {e}")
    await query.message.edit_text(f"❌ Анкета для @{callback_data.username} <b>ОТКЛОНЕНА</b>\nАдминистратор: @{admin_username}")
    await query.answer("Анкета отклонена.")

# -*- coding: utf-8 -*-
# Файл: main.py (Часть 3/4)

# --- ОСНОВНОЙ ФУНКЦИОНАЛ (ЗАЩИЩЕН ФИЛЬТРОМ ОТ БАНА) ---
dp.message.filter(IsNotBannedFilter())
dp.callback_query.filter(IsNotBannedFilter())

@dp.message(F.text == "❌ Отмена")
async def cancel_dialog(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None: return
    await state.clear()
    if db.is_admin_panel_active(message.from_user.id):
        await message.answer("Действие отменено.", reply_markup=get_admin_keyboard())
    else:
        await message.answer("Действие отменено.", reply_markup=get_main_menu_keyboard())

@dp.message(F.text == "💰 Мой кошелек")
async def handle_wallet_button(message: types.Message):
    user_balance = db.get_user_balance(message.from_user.id)
    await message.answer(f"<b>Ваш кошелек</b>\n\n💰 Текущий баланс: <b>{user_balance}</b> золотых монет.")

@dp.message(F.text == "👤 Моя анкета")
async def handle_my_profile_button(message: types.Message):
    anketa_data = db.get_user_anketa(message.from_user.id)
    if anketa_data:
        chat_id, message_id = anketa_data
        try:
            await bot.forward_message(chat_id=message.chat.id, from_chat_id=chat_id, message_id=message_id)
        except Exception as e:
            await message.answer("Не удалось найти вашу анкету. Возможно, она была удалена из канала.")
            logging.error(f"Ошибка пересылки анкеты для {message.from_user.id}: {e}")
    else:
        await message.answer("У вас еще нет привязанной анкеты. Перешлите ее из канала, чтобы завершить регистрацию.")

async def format_items_page(user_id: int, page: int = 1):
    """Формирует текст и клавиатуру для страницы со списком товаров."""
    offset = (page - 1) * ITEMS_PER_PAGE
    total_items = db.count_user_items(user_id)
    
    if total_items == 0:
        return "У вас пока нет выставленных или проданных товаров.", None

    user_items = db.get_user_items(user_id, limit=ITEMS_PER_PAGE, offset=offset)
    
    if not user_items and page > 1:
        return "Здесь пусто.", None

    text = "<b>Ваши товары:</b>\n\n"
    builder = InlineKeyboardBuilder()
    for item in user_items:
        status = "✅ Продан" if item['is_sold'] else "⏳ На продаже"
        item_text = f"<b>{item['name']}</b>\nЦена: {item['price']} золотых\nСтатус: {status}\n"
        if not item['is_sold']:
            builder.button(text=f"❌ Снять «{item['name']}»", callback_data=ManageItemCallback(action="delete", item_id=item['item_id']).pack())
        text += item_text + "──────────────\n"
    
    builder.adjust(1)
    
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE)
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ Назад", callback_data=MyItemsPaginator(action="page", page=page-1).pack()))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton(text="Вперёд ▶️", callback_data=MyItemsPaginator(action="page", page=page+1).pack()))
    
    builder.row(*nav_buttons)
    
    return text, builder.as_markup()

@dp.message(F.text == "🛍️ Мои товары")
async def handle_my_items_button(message: types.Message):
    text, reply_markup = await format_items_page(message.from_user.id, page=1)
    await message.answer(text, reply_markup=reply_markup)

@dp.callback_query(MyItemsPaginator.filter(F.action == "page"))
async def handle_my_items_page_switch(query: types.CallbackQuery, callback_data: MyItemsPaginator):
    text, reply_markup = await format_items_page(query.from_user.id, page=callback_data.page)
    try:
        await query.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e): await query.answer()
        else:
            logging.error(f"Ошибка при переключении страницы товаров: {e}")
            await query.answer("Произошла ошибка.", show_alert=True)
    await query.answer()

@dp.callback_query(ManageItemCallback.filter(F.action == "delete"))
async def handle_delete_item_callback(query: types.CallbackQuery, callback_data: ManageItemCallback):
    item_id = callback_data.item_id
    item_details = db.get_item_details(item_id)
    if not item_details or item_details['owner_id'] != query.from_user.id or item_details['is_sold']:
        await query.answer("❗️ Действие невозможно.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, снять", callback_data=ManageItemCallback(action="confirm_delete", item_id=item_id).pack())
    builder.button(text="Отмена", callback_data=ManageItemCallback(action="cancel_delete", item_id=item_id).pack())
    builder.adjust(2)
    
    fee = int(item_details['price'] * CANCELLATION_FEE)
    await query.message.edit_text(
        f"Вы уверены, что хотите снять товар «<b>{item_details['name']}</b>» с продажи?\n\n"
        f"Будет взыскан штраф: <b>{fee}</b> золотых.",
        reply_markup=builder.as_markup()
    )
    await query.answer()

@dp.callback_query(ManageItemCallback.filter(F.action == "cancel_delete"))
async def handle_cancel_delete_callback(query: types.CallbackQuery):
    text, reply_markup = await format_items_page(query.from_user.id, page=1)
    await query.message.edit_text(text, reply_markup=reply_markup)
    await query.answer("Действие отменено.")

@dp.callback_query(ManageItemCallback.filter(F.action == "confirm_delete"))
async def handle_confirm_delete_item_callback(query: types.CallbackQuery, callback_data: ManageItemCallback):
    item_id = callback_data.item_id
    user_id = query.from_user.id
    item_details = db.get_item_details(item_id)

    if not item_details or item_details['owner_id'] != user_id or item_details['is_sold']:
        await query.answer("❗️ Не удалось выполнить действие.", show_alert=True)
        text, reply_markup = await format_items_page(user_id, page=1)
        await query.message.edit_text(text, reply_markup=reply_markup)
        return

    price = item_details['price']
    fee = int(price * CANCELLATION_FEE)
    
    db.update_user_balance(user_id, -fee)
    db.remove_item(item_id)
    
    try:
        if item_details['post_message_id']:
            await bot.delete_message(chat_id=MARKET_CHANNEL_ID, message_id=item_details['post_message_id'])
    except Exception as e:
        logging.error(f"Не удалось удалить пост о товаре {item_id} из канала: {e}")
    
    await query.answer("Товар успешно снят с продажи.", show_alert=True)
    
    text, reply_markup = await format_items_page(user_id, page=1)
    await query.message.edit_text(
        f"✅ Товар «<b>{item_details['name']}</b>» снят с продажи.\nВзыскан штраф: <b>{fee}</b> золотых.\n\n" + text,
        reply_markup=reply_markup
    )

@dp.message(F.text == "➕ Добавить товар", ~F.state)
async def start_add_item(message: types.Message, state: FSMContext):
    active_items_count = db.count_active_user_items(message.from_user.id)
    if active_items_count >= MAX_ITEMS_PER_USER:
        await message.answer(f"❌ <b>Достигнут лимит!</b> У вас уже {active_items_count} активных товаров.")
        return
    await message.answer(f"Отлично! (Активных: {active_items_count}/{MAX_ITEMS_PER_USER})\n\n<b>Шаг 1/4: Введите название товара.</b>", reply_markup=get_cancel_keyboard())
    await state.set_state(AddItemFSM.waiting_for_name)

@dp.message(AddItemFSM.waiting_for_name, F.text)
async def process_item_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("<b>Шаг 2/4: Теперь введите описание товара.</b>")
    await state.set_state(AddItemFSM.waiting_for_description)

@dp.message(AddItemFSM.waiting_for_description, F.text)
async def process_item_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("<b>Шаг 3/4: Отлично! Теперь отправьте фотографию товара.</b>")
    await state.set_state(AddItemFSM.waiting_for_photo)

@dp.message(AddItemFSM.waiting_for_photo, F.photo)
async def process_item_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)
    await message.answer("<b>Шаг 4/4: И последнее. Укажите цену товара в золотых монетах.</b>")
    await state.set_state(AddItemFSM.waiting_for_price)

@dp.message(AddItemFSM.waiting_for_photo)
async def process_item_photo_invalid(message: types.Message):
    await message.answer("Пожалуйста, отправьте именно фотографию товара.")

@dp.message(AddItemFSM.waiting_for_price, F.text)
async def process_item_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("Цена должна быть целым положительным числом.")
        return
    price = int(message.text)
    user_data = await state.get_data()
    item_caption = (f"🛍 <b>{user_data['name']}</b>\n\n"
                    f"📋 {user_data['description']}\n\n"
                    f"💰 Цена: <b>{price}</b> золотых монет\n"
                    f"👤 Продавец: @{message.from_user.username or message.from_user.full_name}")
    try:
        sent_message = await bot.send_photo(chat_id=MARKET_CHANNEL_ID, photo=user_data['photo'], caption=item_caption)
        item_id = db.add_item(owner_id=message.from_user.id, name=user_data['name'], description=user_data['description'], photo_id=user_data['photo'], price=price, post_message_id=sent_message.message_id)
        await sent_message.edit_reply_markup(reply_markup=get_buy_button(item_id))
        await message.answer("✅ <b>Отлично!</b> Ваш товар успешно выставлен на рынок.", reply_markup=get_main_menu_keyboard())
    except Exception as e:
        logging.error(f"Не удалось опубликовать товар в канале {MARKET_CHANNEL_ID}: {e}")
        await message.answer("❌ <b>Произошла ошибка!</b>\nНе удалось опубликовать товар. Проверьте, что бот добавлен в канал и имеет права на публикацию.", reply_markup=get_main_menu_keyboard())
    await state.clear()

@dp.callback_query(BuyItemCallback.filter())
async def handle_buy_callback(query: types.CallbackQuery, callback_data: BuyItemCallback):
    buyer_id = query.from_user.id
    item_id = callback_data.item_id
    
    if not db.user_exists(buyer_id):
        await query.answer("Пожалуйста, сначала запустите бота командой /start, чтобы совершать покупки.", show_alert=True)
        return

    item = db.get_item_details(item_id)
    if not item:
        await query.answer("❗️ Товар не найден или уже снят с продажи.", show_alert=True)
        return
        
    seller_id, price, is_sold = item['owner_id'], item['price'], item['is_sold']
    
    if is_sold:
        await query.answer("❗️ Этот товар уже продан.", show_alert=True)
        return
    if buyer_id == seller_id:
        await query.answer("❗️ Вы не можете купить товар у самого себя.", show_alert=True)
        return
        
    buyer_balance = db.get_user_balance(buyer_id)
    if buyer_balance < price:
        await query.answer(f"❗️ У вас недостаточно средств. Нужно {price}, а у вас {buyer_balance}.", show_alert=True)
        return
        
    try:
        db.update_user_balance(buyer_id, -price)
        db.update_user_balance(seller_id, price)
        db.mark_item_as_sold(item_id)
        
        new_caption = query.message.caption + f"\n\n<b>✅ ПРОДАНО</b>\nПокупатель: @{query.from_user.username or query.from_user.full_name}"
        await bot.edit_message_caption(chat_id=MARKET_CHANNEL_ID, message_id=item['post_message_id'], caption=new_caption, reply_markup=None)
        
        await query.answer("✅ Покупка совершена успешно!", show_alert=True)
        await bot.send_message(buyer_id, f"Вы успешно приобрели товар «{item['name']}»! {price} золотых списано с вашего счета.")
        await bot.send_message(seller_id, f"Ваш товар «{item['name']}» был куплен! {price} золотых зачислено на ваш счет.")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e): pass
        else: logging.warning(f"Не удалось отредактировать сообщение о продаже товара {item_id}: {e}")
        await query.answer("✅ Покупка совершена успешно!", show_alert=True)
    except Exception as e:
        logging.error(f"Критическая ошибка во время транзакции для товара {item_id}: {e}")
        await query.answer("❗️ Произошла критическая ошибка во время покупки.", show_alert=True)

# -*- coding: utf-8 -*-
# Файл: main.py (Часть 4/4)

# --- АДМИНИСТРАТИВНЫЙ БЛОК ---

@dp.message(Command("admin"))
async def admin_login_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not db.is_user_admin(user_id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    if not db.has_admin_password(user_id):
        await message.answer("🔐 Для вашего аккаунта не установлен пароль администратора. Обратитесь к владельцу бота, чтобы он установил его командой:\n<code>/setpassword [Ваш ID или @username] [пароль]</code>")
        return

    await message.answer("🔑 Введите пароль для входа в панель администратора:", reply_markup=get_cancel_keyboard())
    await state.set_state(AdminLoginFSM.waiting_for_password)

@dp.message(AdminLoginFSM.waiting_for_password, F.text)
async def process_admin_password(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Не удалось удалить сообщение с паролем: {e}")

    if db.check_admin_password(user_id, message.text):
        db.activate_admin_panel(user_id)
        await message.answer("✅ Вход выполнен успешно! Добро пожаловать в панель администратора.", reply_markup=get_admin_keyboard())
        await state.clear()
    else:
        await message.answer("⛔️ Неверный пароль. Попробуйте еще раз.", reply_markup=get_cancel_keyboard())

@dp.message(F.text == "⬅️ Выйти из админ-панели", IsAdminFilter())
async def admin_logout(message: types.Message):
    db.deactivate_admin_panel(message.from_user.id)
    await message.answer("Вы вышли из панели администратора.", reply_markup=get_main_menu_keyboard())

@dp.message(F.text == "📋 Памятка по командам", IsAdminFilter())
async def admin_commands_memo(message: types.Message):
    admin_text = (
        "<b>📋 Памятка по командам администратора</b>\n\n"
        "<i>Все команды принимают как ID, так и @username.</i>\n\n"
        "<b>Финансы:</b>\n"
        "<code>/give [цель] [сумма]</code>\n"
        "└ Выдать золото пользователю.\n\n"
        "<code>/take [цель] [сумма]</code>\n"
        "└ Забрать золото у пользователя.\n\n"
        "<b>Управление пользователями:</b>\n"
        "<code>/ban [цель]</code>\n"
        "└ Заблокировать пользователя.\n\n"
        "<code>/unban [цель]</code>\n"
        "└ Разблокировать пользователя.\n\n"
        "<code>/profile [цель]</code>\n"
        "└ Посмотреть профиль (баланс, статус, анкету)."
    )
    
    if message.from_user.id == OWNER_ID:
        admin_text += (
            "\n\n"
            "------------------------------------\n"
            "<b>👑 Команды владельца:</b>\n\n"
            "<code>/addadmin [цель]</code>\n"
            "└ Назначить пользователя админом.\n\n"
            "<code>/deladmin [цель]</code>\n"
            "└ Снять пользователя с поста админа.\n\n"
            "<code>/setpassword [цель] [пароль]</code>\n"
            "└ Установить/изменить пароль админу."
        )
    await message.answer(admin_text)

@dp.message(Command("give"), IsAdminFilter())
async def give_money_command(message: types.Message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) != 3: raise ValueError
        
        target_identifier = args[1]
        amount = int(args[2])

        user_id = await resolve_user_id(message, target_identifier)
        if user_id is None: return

        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительным числом.")
            return
            
        db.update_user_balance(user_id, amount)
        await message.answer(f"✅ Успешно! Начислено <b>{amount}</b> золотых пользователю <code>{user_id}</code>.")
        try:
            await bot.send_message(user_id, f"💰 Вам было начислено <b>{amount}</b> золотых от администрации.")
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя {user_id} о начислении: {e}")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/give [ID или @username] [сумма]</code>")

@dp.message(Command("take"), IsAdminFilter())
async def take_money_command(message: types.Message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) != 3: raise ValueError
        
        target_identifier = args[1]
        amount = int(args[2])

        user_id = await resolve_user_id(message, target_identifier)
        if user_id is None: return

        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительным числом.")
            return
            
        db.update_user_balance(user_id, -amount)
        await message.answer(f"✅ Успешно! Списано <b>{amount}</b> золотых у пользователя <code>{user_id}</code>.")
        try:
            await bot.send_message(user_id, f"💰 У вас было списано <b>{amount}</b> золотых администрацией.")
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя {user_id} о списании: {e}")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/take [ID или @username] [сумма]</code>")

@dp.message(Command("ban"), IsAdminFilter())
async def ban_user_command(message: types.Message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) != 2: raise ValueError
        
        target_identifier = args[1]
        user_id = await resolve_user_id(message, target_identifier)
        if user_id is None: return

        if user_id == message.from_user.id:
            await message.answer("❌ Вы не можете забанить самого себя.")
            return
            
        db.set_user_ban_status(user_id, is_banned=True)
        await message.answer(f"✅ Пользователь <code>{user_id}</code> был заблокирован.")
        try:
            await bot.send_message(user_id, "<b>Вы были заблокированы администрацией.</b>")
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя {user_id} о бане: {e}")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/ban [ID или @username]</code>")

@dp.message(Command("unban"), IsAdminFilter())
async def unban_user_command(message: types.Message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) != 2: raise ValueError
        
        target_identifier = args[1]
        user_id = await resolve_user_id(message, target_identifier)
        if user_id is None: return
            
        db.set_user_ban_status(user_id, is_banned=False)
        await message.answer(f"✅ Пользователь <code>{user_id}</code> был разблокирован.")
        try:
            await bot.send_message(user_id, "<b>Вы были разблокированы администрацией.</b>")
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя {user_id} о разбане: {e}")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/unban [ID или @username]</code>")

@dp.message(Command("profile"), IsAdminFilter())
async def admin_view_profile(message: types.Message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) != 2: raise ValueError
            
        target_identifier = args[1]
        target_user_id = await resolve_user_id(message, target_identifier)
        if target_user_id is None: return

        user_data = db.get_user_full_profile(target_user_id)

        status_ban = "🚫 <b>ДА</b>" if user_data['is_banned'] else "✅ Нет"
        status_admin = "👑 <b>ДА</b>" if user_data['is_admin'] else "❌ Нет"
        
        profile_text = (
            f"<b>👤 Профиль пользователя @{user_data['username']} (<code>{target_user_id}</code>)</b>\n\n"
            f"💰 Баланс: <b>{user_data['balance']}</b> золотых\n"
            f"👑 Админ: {status_admin}\n"
            f"⛔️ Заблокирован: {status_ban}"
        )
        await message.answer(profile_text)

        if user_data['anketa_chat_id']:
            try:
                await bot.forward_message(
                    chat_id=message.chat.id,
                    from_chat_id=user_data['anketa_chat_id'],
                    message_id=user_data['anketa_message_id']
                )
            except Exception as e:
                await message.answer("<i>Не удалось переслать анкету (возможно, она удалена из канала).</i>")
        else:
            await message.answer("<i>У пользователя не найдена привязанная анкета.</i>")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/profile [ID или @username]</code>")

# --- КОМАНДЫ ВЛАДЕЛЬЦА ---
@dp.message(Command("addadmin"), F.from_user.id == OWNER_ID)
async def add_admin_command(message: types.Message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) != 2: raise ValueError
        
        target_identifier = args[1]
        user_id = await resolve_user_id(message, target_identifier)
        if user_id is None: return
            
        db.set_admin(user_id)
        await message.answer(f"✅ Пользователь <code>{user_id}</code> назначен администратором. Не забудьте установить ему пароль командой <code>/setpassword</code>.")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/addadmin [ID или @username]</code>")

@dp.message(Command("deladmin"), F.from_user.id == OWNER_ID)
async def remove_admin_command(message: types.Message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) != 2: raise ValueError
        
        target_identifier = args[1]
        user_id = await resolve_user_id(message, target_identifier)
        if user_id is None: return

        if user_id == OWNER_ID:
            await message.answer("❌ Вы не можете снять с себя права владельца.")
            return
            
        db.remove_admin(user_id)
        await message.answer(f"✅ Пользователь <code>{user_id}</code> больше не администратор.")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/deladmin [ID или @username]</code>")

@dp.message(Command("setpassword"), F.from_user.id == OWNER_ID)
async def set_admin_password_command(message: types.Message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) != 3: raise ValueError
        
        target_identifier = args[1]
        password = args[2]
        
        user_id = await resolve_user_id(message, target_identifier)
        if user_id is None: return

        if not db.is_user_admin(user_id):
            await message.answer(f"❌ Пользователь <code>{user_id}</code> не является администратором. Сначала назначьте его.")
            return
            
        db.set_admin_password(user_id, password)
        await message.answer(f"✅ Пароль для администратора <code>{user_id}</code> успешно установлен.")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/setpassword [ID или @username] [пароль]</code>")


# --- ЗАПУСК БОТА ---
app = Flask(__name__)

@app.route('/')
def index():
    return "I am alive!"

def run_flask():
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port=port)

async def main_async():
    db.init_db()
    if not db.user_exists(OWNER_ID):
        db.add_user(OWNER_ID, "Owner")
    if not db.is_user_admin(OWNER_ID):
        db.set_admin(OWNER_ID)
    
    logging.info("Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную.")
    