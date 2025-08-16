# -*- coding: utf-8 -*-
# Файл: database.py (ИСПРАВЛЕННАЯ И ПОЛНАЯ ВЕРСИЯ)

import sqlite3
import logging
import hashlib

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _hash_password(password: str) -> str:
    """Хэширует пароль для безопасного хранения."""
    return hashlib.sha256(password.encode()).hexdigest()

def _execute_query(query: str, params: tuple = (), fetchone=False, fetchall=False, commit=False):
    """Универсальная функция для выполнения запросов к БД."""
    conn = None
    try:
        conn = sqlite3.connect('shop.db')
        conn.row_factory = sqlite3.Row # Позволяет обращаться к столбцам по имени
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        if commit:
            conn.commit()
            return cursor.lastrowid
        
        if fetchone:
            return cursor.fetchone()
        
        if fetchall:
            return cursor.fetchall()

    except sqlite3.Error as e:
        logging.error(f"Ошибка базы данных: {e}\nЗапрос: {query}\nПараметры: {params}")
        return None
    finally:
        if conn:
            conn.close()

def init_db():
    """Инициализирует базу данных и создает/обновляет таблицы."""
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
                is_banned INTEGER NOT NULL DEFAULT 0,
                anketa_chat_id INTEGER,
                anketa_message_id INTEGER,
                admin_password_hash TEXT,
                admin_panel_active INTEGER NOT NULL DEFAULT 0
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
                is_sold INTEGER NOT NULL DEFAULT 0,
                post_message_id INTEGER,
                FOREIGN KEY (owner_id) REFERENCES users (user_id)
            )
        ''')

        user_columns = [desc[1] for desc in cursor.execute("PRAGMA table_info(users)").fetchall()]
        if 'admin_password_hash' not in user_columns:
            logging.info("Добавляю столбец 'admin_password_hash'...")
            cursor.execute("ALTER TABLE users ADD COLUMN admin_password_hash TEXT")
        if 'admin_panel_active' not in user_columns:
            logging.info("Добавляю столбец 'admin_panel_active'...")
            cursor.execute("ALTER TABLE users ADD COLUMN admin_panel_active INTEGER NOT NULL DEFAULT 0")

        conn.commit()
        logging.info("База данных успешно инициализирована.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при инициализации базы данных: {e}")
    finally:
        if conn:
            conn.close()

# --- Функции для паролей и сессий админов ---

def set_admin_password(user_id: int, password: str):
    password_hash = _hash_password(password)
    _execute_query("UPDATE users SET admin_password_hash = ? WHERE user_id = ?", (password_hash, user_id), commit=True)
    logging.info(f"Пароль для админа {user_id} установлен/обновлен.")

def check_admin_password(user_id: int, password: str) -> bool:
    password_hash = _hash_password(password)
    result = _execute_query("SELECT admin_password_hash FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return result and result['admin_password_hash'] == password_hash

def has_admin_password(user_id: int) -> bool:
    result = _execute_query("SELECT admin_password_hash FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return result and result['admin_password_hash'] is not None

def activate_admin_panel(user_id: int):
    _execute_query("UPDATE users SET admin_panel_active = 1 WHERE user_id = ?", (user_id,), commit=True)
    logging.info(f"Админ-панель для {user_id} активирована.")

def deactivate_admin_panel(user_id: int):
    _execute_query("UPDATE users SET admin_panel_active = 0 WHERE user_id = ?", (user_id,), commit=True)
    logging.info(f"Админ-панель для {user_id} деактивирована.")

def is_admin_panel_active(user_id: int) -> bool:
    result = _execute_query("SELECT admin_panel_active FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return result and result['admin_panel_active'] == 1

# --- Функции для пользователей ---

def get_user_id_by_username(username: str) -> int | None:
    """Находит user_id по его username (без символа @)."""
    clean_username = username.lstrip('@')
    result = _execute_query("SELECT user_id FROM users WHERE username = ?", (clean_username,), fetchone=True)
    return result['user_id'] if result else None

def add_user(user_id: int, username: str):
    _execute_query("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username), commit=True)
    logging.info(f"Пользователь {username} (ID: {user_id}) добавлен в базу (если не существовал).")

def user_exists(user_id: int) -> bool:
    """Проверяет, существует ли пользователь в базе."""
    return _execute_query("SELECT 1 FROM users WHERE user_id = ?", (user_id,), fetchone=True) is not None

def update_username(user_id: int, new_username: str):
    """Обновляет юзернейм пользователя."""
    _execute_query("UPDATE users SET username = ? WHERE user_id = ?", (new_username, user_id), commit=True)

def set_user_anketa(user_id: int, chat_id: int, message_id: int):
    _execute_query("UPDATE users SET anketa_chat_id = ?, anketa_message_id = ? WHERE user_id = ?", (chat_id, message_id, user_id), commit=True)

def get_user_anketa(user_id: int) -> tuple | None:
    result = _execute_query("SELECT anketa_chat_id, anketa_message_id FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return (result['anketa_chat_id'], result['anketa_message_id']) if result and result['anketa_chat_id'] else None

def get_user_balance(user_id: int) -> int:
    result = _execute_query("SELECT balance FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return result['balance'] if result else 0

def update_user_balance(user_id: int, amount: int):
    _execute_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id), commit=True)
    logging.info(f"Баланс пользователя {user_id} изменен на {amount}.")

def get_user_full_profile(user_id: int) -> dict | None:
    """Возвращает полный профиль пользователя в виде словаря."""
    result = _execute_query("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return dict(result) if result else None

# --- Функции для товаров ---

def add_item(owner_id: int, name: str, description: str, photo_id: str, price: int, post_message_id: int) -> int:
    item_id = _execute_query(
        "INSERT INTO items (owner_id, name, description, photo_id, price, post_message_id) VALUES (?, ?, ?, ?, ?, ?)",
        (owner_id, name, description, photo_id, price, post_message_id), commit=True
    )
    logging.info(f"Товар '{name}' (ID: {item_id}) добавлен пользователем {owner_id}.")
    return item_id

def get_item_details(item_id: int) -> dict | None:
    result = _execute_query("SELECT * FROM items WHERE item_id = ?", (item_id,), fetchone=True)
    return dict(result) if result else None

def mark_item_as_sold(item_id: int):
    _execute_query("UPDATE items SET is_sold = 1 WHERE item_id = ?", (item_id,), commit=True)
    logging.info(f"Товар {item_id} помечен как проданный.")

def get_user_items(user_id: int, limit: int, offset: int) -> list:
    query = "SELECT item_id, name, price, is_sold FROM items WHERE owner_id = ? ORDER BY item_id DESC LIMIT ? OFFSET ?"
    results = _execute_query(query, (user_id, limit, offset), fetchall=True)
    return [dict(row) for row in results] if results else []

def count_user_items(user_id: int) -> int:
    result = _execute_query("SELECT COUNT(item_id) as count FROM items WHERE owner_id = ?", (user_id,), fetchone=True)
    return result['count'] if result else 0

def remove_item(item_id: int):
    _execute_query("DELETE FROM items WHERE item_id = ?", (item_id,), commit=True)
    logging.info(f"Товар {item_id} удален из базы.")

def count_active_user_items(user_id: int) -> int:
    result = _execute_query("SELECT COUNT(item_id) as count FROM items WHERE owner_id = ? AND is_sold = 0", (user_id,), fetchone=True)
    return result['count'] if result else 0

# --- Функции для администрирования ---

def set_admin(user_id: int):
    _execute_query("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,), commit=True)
    logging.info(f"Пользователь {user_id} назначен администратором.")

def remove_admin(user_id: int):
    _execute_query("UPDATE users SET is_admin = 0, admin_panel_active = 0, admin_password_hash = NULL WHERE user_id = ?", (user_id,), commit=True)
    logging.info(f"Пользователь {user_id} снят с поста администратора. Пароль и сессия сброшены.")

def is_user_admin(user_id: int) -> bool:
    result = _execute_query("SELECT is_admin FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return result and result['is_admin'] == 1

def get_all_admins() -> list:
    results = _execute_query("SELECT user_id FROM users WHERE is_admin = 1", fetchall=True)
    return [row['user_id'] for row in results] if results else []

def set_user_ban_status(user_id: int, is_banned: bool):
    _execute_query("UPDATE users SET is_banned = ? WHERE user_id = ?", (int(is_banned), user_id), commit=True)
    status = "забанен" if is_banned else "разбанен"
    logging.info(f"Пользователь {user_id} был {status}.")

def is_user_banned(user_id: int) -> bool:
    result = _execute_query("SELECT is_banned FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return result and result['is_banned'] == 1
