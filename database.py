# -*- coding: utf-8 -*-

import sqlite3
import logging

# Настройка логирования для отслеживания работы с базой данных
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def init_db():
    """
    Инициализирует базу данных и создает таблицы, если их нет.
    """
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0,
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_banned INTEGER NOT NULL DEFAULT 0
            )
        ''')
        
        # Таблица товаров
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                photo_id TEXT,
                price INTEGER NOT NULL,
                post_message_id INTEGER,
                is_sold INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (owner_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        logging.info("База данных успешно инициализирована.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при инициализации базы данных: {e}")
    finally:
        if conn:
            conn.close()

def add_user(user_id: int, username: str):
    """Добавляет нового пользователя в базу данных."""
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        logging.info(f"Пользователь {username} (ID: {user_id}) добавлен в базу.")
    except sqlite3.IntegrityError:
        logging.warning(f"Попытка добавить уже существующего пользователя {user_id}.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при добавлении пользователя {user_id}: {e}")
    finally:
        if conn:
            conn.close()

def user_exists(user_id: int) -> bool:
    """Проверяет, существует ли пользователь в базе."""
    exists = False
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            exists = True
    except sqlite3.Error as e:
        logging.error(f"Ошибка при проверке пользователя {user_id}: {e}")
    finally:
        if conn:
            conn.close()
    return exists

def get_user_balance(user_id: int) -> int:
    """Возвращает баланс пользователя."""
    balance = 0
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            balance = result[0]
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении баланса для {user_id}: {e}")
    finally:
        if conn:
            conn.close()
    return balance

def update_user_balance(user_id: int, amount: int):
    """Обновляет баланс пользователя (может быть положительным и отрицательным)."""
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        logging.info(f"Баланс пользователя {user_id} изменен на {amount}.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении баланса для {user_id}: {e}")
    finally:
        if conn:
            conn.close()

def add_item(owner_id: int, name: str, description: str, photo_id: str, price: int) -> int:
    """Добавляет новый товар в базу и возвращает его ID."""
    item_id = -1
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO items (owner_id, name, description, photo_id, price) VALUES (?, ?, ?, ?, ?)",
            (owner_id, name, description, photo_id, price)
        )
        conn.commit()
        item_id = cursor.lastrowid
        logging.info(f"Товар '{name}' (ID: {item_id}) добавлен пользователем {owner_id}.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при добавлении товара от {owner_id}: {e}")
    finally:
        if conn:
            conn.close()
    return item_id

def add_post_message_id_to_item(item_id: int, message_id: int):
    """Добавляет ID сообщения из канала к товару."""
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE items SET post_message_id = ? WHERE item_id = ?", (message_id, item_id))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при добавлении message_id к товару {item_id}: {e}")
    finally:
        if conn:
            conn.close()

def get_item_details(item_id: int) -> dict:
    """Возвращает детали товара по его ID."""
    details = None
    try:
        conn = sqlite3.connect('shop.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM items WHERE item_id = ?", (item_id,))
        row = cursor.fetchone()
        if row:
            details = dict(row)
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении деталей товара {item_id}: {e}")
    finally:
        if conn:
            conn.close()
    return details

def mark_item_as_sold(item_id: int):
    """Помечает товар как проданный."""
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE items SET is_sold = 1 WHERE item_id = ?", (item_id,))
        conn.commit()
        logging.info(f"Товар {item_id} помечен как проданный.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении статуса товара {item_id}: {e}")
    finally:
        if conn:
            conn.close()

def get_user_items(user_id: int) -> list:
    """Возвращает список всех товаров пользователя."""
    items = []
    try:
        conn = sqlite3.connect('shop.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT item_id, name, price, is_sold FROM items WHERE owner_id = ? ORDER BY item_id DESC", (user_id,))
        items = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении товаров для {user_id}: {e}")
    finally:
        if conn:
            conn.close()
    return items

def remove_item(item_id: int):
    """Удаляет товар из базы данных."""
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM items WHERE item_id = ?", (item_id,))
        conn.commit()
        logging.info(f"Товар {item_id} удален из базы.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при удалении товара {item_id}: {e}")
    finally:
        if conn:
            conn.close()

def count_active_user_items(user_id: int) -> int:
    """Считает количество активных (не проданных) товаров у пользователя."""
    count = 0
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(item_id) FROM items WHERE owner_id = ? AND is_sold = 0", (user_id,))
        result = cursor.fetchone()
        if result:
            count = result[0]
    except sqlite3.Error as e:
        logging.error(f"Ошибка при подсчете активных товаров для {user_id}: {e}")
    finally:
        if conn:
            conn.close()
    return count

def set_admin(user_id: int):
    """Назначает пользователя администратором."""
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        logging.info(f"Пользователь {user_id} назначен администратором.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при назначении админа {user_id}: {e}")
    finally:
        if conn:
            conn.close()

def remove_admin(user_id: int):
    """Снимает с пользователя права администратора."""
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        logging.info(f"Пользователь {user_id} снят с поста администратора.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при снятии админа {user_id}: {e}")
    finally:
        if conn:
            conn.close()

def is_user_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    is_admin = False
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result and result[0] == 1:
            is_admin = True
    except sqlite3.Error as e:
        logging.error(f"Ошибка при проверке админ-статуса для {user_id}: {e}")
    finally:
        if conn:
            conn.close()
    return is_admin

def get_all_admins() -> list:
    """Возвращает список ID всех администраторов."""
    admins = []
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE is_admin = 1")
        rows = cursor.fetchall()
        admins = [row[0] for row in rows]
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении списка админов: {e}")
    finally:
        if conn:
            conn.close()
    return admins

def set_user_ban_status(user_id: int, is_banned: bool):
    """Устанавливает или снимает бан с пользователя."""
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (int(is_banned), user_id))
        conn.commit()
        status = "забанен" if is_banned else "разбанен"
        logging.info(f"Пользователь {user_id} был {status}.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при изменении статуса бана для {user_id}: {e}")
    finally:
        if conn:
            conn.close()

def is_user_banned(user_id: int) -> bool:
    """Проверяет, забанен ли пользователь."""
    is_banned = False
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result and result[0] == 1:
            is_banned = True
    except sqlite3.Error as e:
        logging.error(f"Ошибка при проверке статуса бана для {user_id}: {e}")
    finally:
        if conn:
            conn.close()
    return is_banned
