# -*- coding: utf-8 -*-

import asyncio
import logging

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
from flask import Flask
from threading import Thread
import os 

# --- НАСТРОЙКИ БОТА (КОНФИГУРАЦИЯ) ---
BOT_TOKEN = "8468997703:AAGuhe11JhsTrn0XMb-kHHz1QcRq837IP0M"
OWNER_ID = 5272076117  # ЗАМЕНИТЕ НА СВОЙ ID
MARKET_CHANNEL_ID = -1002558702431  # ЗАМЕНИТЕ НА ID КАНАЛА
CANCELLATION_FEE = 0.125
MAX_ITEMS_PER_USER = 5

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)


# --- ФИЛЬТРЫ ---
class IsAdminFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return db.is_user_admin(message.from_user.id)

class IsNotBannedFilter(BaseFilter):
    async def __call__(self, event: types.Update) -> bool:
        user_id = event.from_user.id
        if db.is_user_banned(user_id):
            logging.warning(f"Заблокированный пользователь {user_id} попытался выполнить действие.")
            return False
        return True
# --- КЛАССЫ ДЛЯ CALLBACK'ОВ И СОСТОЯНИЙ ---
class RegistrationCallback(CallbackData, prefix="register"):
    action: str; user_id: int; username: str
class BuyItemCallback(CallbackData, prefix="buy"):
    item_id: int
class ManageItemCallback(CallbackData, prefix="manage"):
    action: str; item_id: int
class AddItemFSM(StatesGroup):
    waiting_for_name = State(); waiting_for_description = State(); waiting_for_photo = State(); waiting_for_price = State()


# --- КЛАВИАТУРЫ ---
def get_main_menu_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Мой кошелек"); builder.button(text="🛍️ Мои товары"); builder.button(text="➕ Добавить товар")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)
def get_cancel_keyboard():
    builder = ReplyKeyboardBuilder(); builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)
def get_buy_button(item_id: int):
    builder = InlineKeyboardBuilder(); builder.button(text="💰 Купить", callback_data=BuyItemCallback(item_id=item_id).pack())
    return builder.as_markup()
# --- ГЛАВНЫЕ ОБРАБОТЧИКИ (ДОСТУПНЫ ВСЕМ) ---

@dp.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext):
    await state.clear()
    if db.is_user_banned(message.from_user.id):
        await message.answer("Вы заблокированы и не можете использовать этого бота.")
        return
    if db.user_exists(message.from_user.id):
        await message.answer(f"С возвращением, <b>{message.from_user.full_name}</b>!", reply_markup=get_main_menu_keyboard())
    else:
        await message.answer(
            f"Здравствуйте, <b>{message.from_user.full_name}</b>!\n\n"
            "Я торговый бот для вашей ролевой игры.\n"
            "Для регистрации, пожалуйста, <b>перешлите мне сообщение с вашей анкетой</b> из канала анкет."
        )

@dp.message(Command("help"))
async def handle_help(message: types.Message):
    text = "<b>Справка по боту</b>\n\nИспользуйте кнопки в меню для взаимодействия."
    if db.is_user_admin(message.from_user.id):
        text += (
            "\n\n<b>Команды администратора:</b>\n"
            "<code>/give [ID] [сумма]</code> - выдать золото.\n"
            "<code>/take [ID] [сумма]</code> - забрать золото.\n"
            "<code>/ban [ID]</code> - заблокировать.\n"
            "<code>/unban [ID]</code> - разблокировать."
        )
    if message.from_user.id == OWNER_ID:
        text += (
            "\n\n<b>Команды владельца:</b>\n"
            "<code>/addadmin [ID]</code> - назначить админа.\n"
            "<code>/deladmin [ID]</code> - снять админа."
        )
    await message.answer(text)

@dp.message(F.forward_from_chat)
async def handle_forwarded_anketa(message: types.Message):
    user = message.from_user
    if db.user_exists(user.id):
        await message.answer("Вы уже зарегистрированы в системе.")
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=RegistrationCallback(action="approve", user_id=user.id, username=user.username or "user").pack())
    builder.button(text="❌ Отклонить", callback_data=RegistrationCallback(action="decline", user_id=user.id, username=user.username or "user").pack())
    builder.adjust(2)
    confirmation_request_text = (f"⚠️ <b>Запрос на регистрацию</b> ⚠️\n\nПользователь: @{user.username} (ID: <code>{user.id}</code>)")
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

@dp.callback_query(RegistrationCallback.filter(F.action == "approve"))
async def handle_approve_callback(query: types.CallbackQuery, callback_data: RegistrationCallback):
    admin_username = query.from_user.username or "Администратор"
    if not db.user_exists(callback_data.user_id):
        db.add_user(user_id=callback_data.user_id, username=callback_data.username)
        try:
            await bot.send_message(chat_id=callback_data.user_id, text="🎉 <b>Поздравляем!</b>\n\nВаша регистрация была одобрена.")
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление об одобрении пользователю {callback_data.user_id}: {e}")
        await query.message.edit_text(f"✅ Заявка для @{callback_data.username} <b>ОДОБРЕНА</b>\nАдминистратор: @{admin_username}")
        await query.answer("Заявка одобрена!")
    else:
        await query.message.edit_text(f"⚠️ Заявка для @{callback_data.username} уже была обработана.")
        await query.answer("Пользователь уже зарегистрирован.", show_alert=True)

@dp.callback_query(RegistrationCallback.filter(F.action == "decline"))
async def handle_decline_callback(query: types.CallbackQuery, callback_data: RegistrationCallback):
    admin_username = query.from_user.username or "Администратор"
    try:
        await bot.send_message(chat_id=callback_data.user_id, text="😔 <b>К сожалению...</b>\n\nВаша заявка на регистрацию была отклонена.")
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление об отклонении пользователю {callback_data.user_id}: {e}")
    await query.message.edit_text(f"❌ Заявка для @{callback_data.username} <b>ОТКЛОНЕНА</b>\nАдминистратор: @{admin_username}")
    await query.answer("Заявка отклонена.")
# --- ОСНОВНОЙ ФУНКЦИОНАЛ (ЗАЩИЩЕН ФИЛЬТРОМ ОТ БАНА) ---

# Применяем фильтр ко всем последующим обработчикам
dp.message.filter(IsNotBannedFilter())
dp.callback_query.filter(IsNotBannedFilter())

@dp.message(F.text == "❌ Отмена")
async def cancel_dialog(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None: return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_main_menu_keyboard())

@dp.message(F.text == "💰 Мой кошелек")
async def handle_wallet_button(message: types.Message):
    user_balance = db.get_user_balance(message.from_user.id)
    await message.answer(f"<b>Ваш кошелек</b>\n\n💰 Текущий баланс: <b>{user_balance}</b> золотых монет.")

@dp.message(F.text == "🛍️ Мои товары")
async def handle_my_items_button(message: types.Message):
    user_items = db.get_user_items(message.from_user.id)
    if not user_items:
        await message.answer("У вас пока нет выставленных или проданных товаров.")
        return
    await message.answer("<b>Ваши товары:</b>")
    for item in user_items:
        status = "✅ Продан" if item['is_sold'] else "⏳ На продаже"
        text = f"<b>{item['name']}</b>\nЦена: {item['price']} золотых\nСтатус: {status}"
        if not item['is_sold']:
            builder = InlineKeyboardBuilder()
            builder.button(text="❌ Снять с продажи", callback_data=ManageItemCallback(action="delete", item_id=item['item_id']).pack())
            await message.answer(text, reply_markup=builder.as_markup())
        else:
            await message.answer(text)
        await asyncio.sleep(0.3)

@dp.callback_query(ManageItemCallback.filter(F.action == "delete"))
async def handle_delete_item_callback(query: types.CallbackQuery, callback_data: ManageItemCallback):
    item_id = callback_data.item_id
    user_id = query.from_user.id
    item_details = db.get_item_details(item_id)
    if not item_details or item_details['owner_id'] != user_id:
        await query.answer("❗️ Товар не найден или принадлежит не вам.", show_alert=True)
        return
    if item_details['is_sold']:
        await query.answer("❗️ Этот товар уже продан.", show_alert=True)
        return
    price = item_details['price']
    fee = int(price * CANCELLATION_FEE)
    db.update_user_balance(user_id, -fee)
    db.remove_item(item_id)
    try:
        await bot.delete_message(chat_id=MARKET_CHANNEL_ID, message_id=item_details['post_message_id'])
    except Exception as e:
        logging.error(f"Не удалось удалить пост о товаре {item_id}: {e}")
    await query.message.edit_text(
        query.message.text + f"\n\n<b>❌ Товар снят с продажи.</b>\nВзыскан штраф: <b>{fee}</b> золотых."
    )
    await query.answer("Товар успешно снят с продажи.")

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
    item_caption = (f"🛍 <b>{user_data['name']}</b>\n\n📋 {user_data['description']}\n\n💰 Цена: <b>{price}</b> золотых монет\n👤 Продавец: {message.from_user.full_name}")
    try:
        item_id = db.add_item(owner_id=message.from_user.id, name=user_data['name'], description=user_data['description'], photo_id=user_data['photo'], price=price)
        sent_message = await bot.send_photo(chat_id=MARKET_CHANNEL_ID, photo=user_data['photo'], caption=item_caption, reply_markup=get_buy_button(item_id))
        db.add_post_message_id_to_item(item_id, sent_message.message_id)
        await message.answer("✅ <b>Отлично!</b> Ваш товар успешно выставлен на рынок.", reply_markup=get_main_menu_keyboard())
    except Exception as e:
        logging.error(f"Не удалось опубликовать товар в канале {MARKET_CHANNEL_ID}: {e}")
        await message.answer("❌ <b>Произошла ошибка!</b>\nНе удалось опубликовать товар. Проверьте настройки и права бота в канале.", reply_markup=get_main_menu_keyboard())
    await state.clear()

@dp.callback_query(BuyItemCallback.filter())
async def handle_buy_callback(query: types.CallbackQuery, callback_data: BuyItemCallback):
    buyer_id = query.from_user.id
    item_id = callback_data.item_id
    item = db.get_item_details(item_id)
    if not item:
        await query.answer("❗️ Товар не найден.", show_alert=True)
        return
    seller_id, price, is_sold, message_id = item['owner_id'], item['price'], item['is_sold'], item['post_message_id']
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
        new_caption = query.message.caption + f"\n\n<b>✅ ПРОДАНО</b>\nПокупатель: {query.from_user.full_name}"
        await bot.edit_message_caption(chat_id=MARKET_CHANNEL_ID, message_id=message_id, caption=new_caption, reply_markup=None)
        await query.answer("✅ Покупка совершена успешно!", show_alert=True)
        await bot.send_message(buyer_id, f"Вы успешно приобрели товар! {price} золотых списано с вашего счета.")
        await bot.send_message(seller_id, f"Ваш товар был куплен! {price} золотых зачислено на ваш счет.")
    except TelegramBadRequest as e:
        logging.warning(f"Не удалось отредактировать сообщение: {e}")
        await query.answer("✅ Покупка совершена успешно!", show_alert=True)
    except Exception as e:
        logging.error(f"Критическая ошибка во время транзакции для товара {item_id}: {e}")
        await query.answer("❗️ Произошла критическая ошибка.", show_alert=True)
# --- АДМИНИСТРАТИВНЫЕ КОМАНДЫ ---

@dp.message(Command("give"), IsAdminFilter())
async def give_money_command(message: types.Message):
    try:
        args = message.text.split()
        if len(args) != 3: raise ValueError("Неверное количество аргументов")
        user_id = int(args[1])
        amount = int(args[2])
        if not db.user_exists(user_id):
            await message.answer(f"❌ Пользователь с ID <code>{user_id}</code> не найден в базе.")
            return
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
        await message.answer("❌ Неверный формат. Используйте:\n<code>/give [ID_пользователя] [сумма]</code>")

@dp.message(Command("take"), IsAdminFilter())
async def take_money_command(message: types.Message):
    try:
        args = message.text.split()
        if len(args) != 3: raise ValueError("Неверное количество аргументов")
        user_id = int(args[1])
        amount = int(args[2])
        if not db.user_exists(user_id):
            await message.answer(f"❌ Пользователь с ID <code>{user_id}</code> не найден в базе.")
            return
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
        await message.answer("❌ Неверный формат. Используйте:\n<code>/take [ID_пользователя] [сумма]</code>")

@dp.message(Command("ban"), IsAdminFilter())
async def ban_user_command(message: types.Message):
    try:
        args = message.text.split()
        if len(args) != 2: raise ValueError
        user_id = int(args[1])
        if user_id == message.from_user.id:
            await message.answer("❌ Вы не можете забанить самого себя.")
            return
        if not db.user_exists(user_id):
            await message.answer(f"❌ Пользователь с ID <code>{user_id}</code> не найден в базе.")
            return
        db.set_user_ban_status(user_id, is_banned=True)
        await message.answer(f"✅ Пользователь <code>{user_id}</code> был заблокирован.")
        try:
            await bot.send_message(user_id, "<b>Вы были заблокированы администрацией.</b>")
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя {user_id} о бане: {e}")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/ban [ID_пользователя]</code>")

@dp.message(Command("unban"), IsAdminFilter())
async def unban_user_command(message: types.Message):
    try:
        args = message.text.split()
        if len(args) != 2: raise ValueError
        user_id = int(args[1])
        if not db.user_exists(user_id):
            await message.answer(f"❌ Пользователь с ID <code>{user_id}</code> не найден в базе.")
            return
        db.set_user_ban_status(user_id, is_banned=False)
        await message.answer(f"✅ Пользователь <code>{user_id}</code> был разблокирован.")
        try:
            await bot.send_message(user_id, "<b>Вы были разблокированы администрацией.</b>")
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя {user_id} о разбане: {e}")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте:\n<code>/unban [ID_пользователя]</code>")

@dp.message(Command("addadmin"), F.from_user.id == OWNER_ID)
async def add_admin_command(message: types.Message):
    try:
        user_id = int(message.text.split()[1])
        if not db.user_exists(user_id):
            await message.answer(f"Пользователь {user_id} не найден.")
            return
        db.set_admin(user_id)
        await message.answer(f"Пользователь {user_id} назначен администратором.")
    except (IndexError, ValueError):
        await message.answer("Используйте: /addadmin [ID]")

@dp.message(Command("deladmin"), F.from_user.id == OWNER_ID)
async def remove_admin_command(message: types.Message):
    try:
        user_id = int(message.text.split()[1])
        if user_id == OWNER_ID:
            await message.answer("Вы не можете снять с себя права владельца.")
            return
        if not db.user_exists(user_id):
            await message.answer(f"Пользователь {user_id} не найден.")
            return
        db.remove_admin(user_id)
        await message.answer(f"Пользователь {user_id} больше не администратор.")
    except (IndexError, ValueError):
        await message.answer("Используйте: /deladmin [ID]")


# --- ЗАПУСК БОТА ---
async def main():
    db.init_db()
    # Убедимся, что владелец существует в базе и является админом
    if not db.user_exists(OWNER_ID):
        db.add_user(OWNER_ID, "Owner")
    if not db.is_user_admin(OWNER_ID):
        db.set_admin(OWNER_ID)
    
    logging.info("Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# --- Старый код ---
# if __name__ == "__main__":
#     try:
#         asyncio.run(main())
#     except KeyboardInterrupt:
#         logging.info("Бот остановлен вручную.")

# --- НОВЫЙ КОД ---
app = Flask(__name__)

@app.route('/')
def index():
    return "I am alive!"

def run_flask():
  # Render предоставляет порт в переменной окружения PORT
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
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    
    # Запускаем бота
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную.")


