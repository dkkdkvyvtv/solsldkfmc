import os
import json
from datetime import datetime
from config import Config
import psycopg2
from urllib.parse import urlparse
import sqlite3

class Database:
    def __init__(self):
        self.database_url = Config.DATABASE_URL
        self.is_postgres = False
        
        # Проверяем, это PostgreSQL или SQLite
        if self.database_url and self.database_url.startswith('postgres://'):
            self.is_postgres = True
            # Конвертируем postgres:// в postgresql:// если нужно
            if self.database_url.startswith('postgres://'):
                self.database_url = self.database_url.replace('postgres://', 'postgresql://', 1)
        else:
            # SQLite для локальной разработки
            self.db_path = Config.DATABASE_PATH
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self.init_db()
    
    def get_connection(self):
        """Возвращает соединение с базой данных"""
        if self.is_postgres:
            # PostgreSQL для Render
            result = urlparse(self.database_url)
            conn = psycopg2.connect(
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port,
                sslmode='require'
            )
            return conn
        else:
            # SQLite для локальной разработки
            import sqlite3
            return sqlite3.connect(self.db_path)
    
    def execute(self, cursor, query, params=None):
        """Универсальный метод выполнения SQL запросов"""
        if params is None:
            params = []
        
        if self.is_postgres:
            # Для PostgreSQL заменяем ? на %s
            query = query.replace('?', '%s')
        
        cursor.execute(query, params)
    
    def fetchone(self, cursor):
        """Универсальный метод получения одной строки"""
        return cursor.fetchone()
    
    def fetchall(self, cursor):
        """Универсальный метод получения всех строк"""
        return cursor.fetchall()
    
    def lastrowid(self, cursor):
        """Получение ID последней вставленной записи"""
        if self.is_postgres:
            cursor.execute("SELECT LASTVAL()")
            return cursor.fetchone()[0]
        else:
            return cursor.lastrowid
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Создаем таблицы с учетом типа БД
            self._create_tables(cursor)
            
            # Добавляем начальные данные
            self._seed_initial_data(cursor)
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Ошибка инициализации БД: {e}")
        finally:
            cursor.close()
            conn.close()
    
    def _create_tables(self, cursor):
        """Создание таблиц"""
        
        if self.is_postgres:
            # PostgreSQL схемы
            # Пользователи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    photo_url TEXT,
                    balance DECIMAL(10, 2) DEFAULT 0,
                    cashback_balance DECIMAL(10, 2) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Разделы (суперкатегории)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sections (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    display_name VARCHAR(255) NOT NULL,
                    icon VARCHAR(50),
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            
            # Категории товаров
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    display_name VARCHAR(255) NOT NULL,
                    icon VARCHAR(50),
                    section_id INTEGER,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            
            # Товары
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    price DECIMAL(10, 2) NOT NULL,
                    image_path TEXT,
                    specifications TEXT,
                    category VARCHAR(255) DEFAULT 'pods',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Заказы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    total_amount DECIMAL(10, 2),
                    cashback_earned DECIMAL(10, 2),
                    customer_name VARCHAR(255),
                    customer_phone VARCHAR(50),
                    pickup_location TEXT,
                    delivery_type VARCHAR(50) DEFAULT 'pickup',
                    delivery_city VARCHAR(100),
                    delivery_address TEXT,
                    delivery_price DECIMAL(10, 2) DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
                )
            ''')
            
            # Пункты выдачи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pickup_locations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    address TEXT NOT NULL,
                    city VARCHAR(100),
                    location_type VARCHAR(50) DEFAULT 'pickup',
                    delivery_price DECIMAL(10, 2) DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            
            # Корзина
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cart_items (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    product_id INTEGER,
                    quantity INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
                )
            ''')
            
            # Создаем индексы для производительности
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cart_items_user ON cart_items(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')
            
            # Проверяем и добавляем колонку photo_url в users если её нет
            try:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='photo_url'")
                if not cursor.fetchone():
                    cursor.execute('ALTER TABLE users ADD COLUMN photo_url TEXT')
            except:
                pass
            
        else:
            # SQLite схемы
            # Пользователи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    photo_url TEXT,
                    balance REAL DEFAULT 0,
                    cashback_balance REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Разделы (суперкатегории)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    icon TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Категории товаров
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    icon TEXT,
                    section_id INTEGER,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Проверяем есть ли колонка section_id, если нет - добавляем
            cursor.execute("PRAGMA table_info(categories)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'section_id' not in columns:
                cursor.execute('ALTER TABLE categories ADD COLUMN section_id INTEGER')
            
            # Товары
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    price REAL NOT NULL,
                    image_path TEXT,
                    specifications TEXT,
                    category TEXT DEFAULT 'pods',
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Заказы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    total_amount REAL,
                    cashback_earned REAL,
                    customer_name TEXT,
                    customer_phone TEXT,
                    pickup_location TEXT,
                    delivery_type TEXT DEFAULT 'pickup',
                    delivery_city TEXT,
                    delivery_address TEXT,
                    delivery_price REAL DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Проверяем есть ли новые колонки в orders, если нет - добавляем
            cursor.execute("PRAGMA table_info(orders)")
            order_columns = [column[1] for column in cursor.fetchall()]
            
            new_order_columns = [
                ('delivery_type', 'TEXT DEFAULT "pickup"'),
                ('delivery_city', 'TEXT'),
                ('delivery_address', 'TEXT'),
                ('delivery_price', 'REAL DEFAULT 0')
            ]
            
            for col_name, col_type in new_order_columns:
                if col_name not in order_columns:
                    cursor.execute(f'ALTER TABLE orders ADD COLUMN {col_name} {col_type}')
            
            # Пункты выдачи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pickup_locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    address TEXT NOT NULL,
                    city TEXT,
                    location_type TEXT DEFAULT 'pickup',
                    delivery_price REAL DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Проверяем есть ли новые колонки в pickup_locations
            cursor.execute("PRAGMA table_info(pickup_locations)")
            location_columns = [column[1] for column in cursor.fetchall()]
            
            new_location_columns = [
                ('city', 'TEXT'),
                ('location_type', 'TEXT DEFAULT "pickup"'),
                ('delivery_price', 'REAL DEFAULT 0')
            ]
            
            for col_name, col_type in new_location_columns:
                if col_name not in location_columns:
                    cursor.execute(f'ALTER TABLE pickup_locations ADD COLUMN {col_name} {col_type}')
            
            # Корзина
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cart_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    product_id INTEGER,
                    quantity INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (product_id) REFERENCES products (id)
                )
            ''')
    
    def _seed_initial_data(self, cursor):
        """Добавление начальных данных"""
        
        if self.is_postgres:
            # Добавляем стандартные разделы если их нет
            default_sections = [
                ('devices', 'Устройства', '📱', 1),
                ('consumables', 'Расходники', '🧴', 2),
                ('accessories', 'Аксессуары', '🧰', 3)
            ]
            
            for name, display_name, icon, order in default_sections:
                cursor.execute('''
                    INSERT INTO sections (name, display_name, icon, sort_order)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    icon = EXCLUDED.icon,
                    sort_order = EXCLUDED.sort_order
                ''', (name, display_name, icon, order))
            
            # Получаем ID разделов для привязки категорий
            cursor.execute('SELECT id, name FROM sections')
            sections = {name: id for id, name in cursor.fetchall()}
            
            # Добавляем стандартные категории если их нет
            default_categories = [
                ('pods', 'Поды', '🎯', 1, sections.get('devices')),
                ('mods', 'Моды', '⚡', 2, sections.get('devices')),
                ('disposable', 'Одноразовые', '🚬', 3, sections.get('devices')),
                ('liquids', 'Жидкости', '💧', 4, sections.get('consumables')),
                ('coils', 'Испарители', '🔥', 5, sections.get('consumables')),
                ('batteries', 'Батареи', '🔋', 6, sections.get('accessories')),
                ('cases', 'Чехлы', '🎒', 7, sections.get('accessories'))
            ]
            
            for cat_id, name, icon, order, section_id in default_categories:
                cursor.execute('''
                    INSERT INTO categories (name, display_name, icon, section_id, sort_order)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    icon = EXCLUDED.icon,
                    section_id = EXCLUDED.section_id,
                    sort_order = EXCLUDED.sort_order
                ''', (cat_id, name, icon, section_id, order))
            
            # Добавляем стандартные города и пункты выдачи
            # Проверяем, есть ли уже пункты выдачи
            cursor.execute('SELECT COUNT(*) FROM pickup_locations')
            location_count = cursor.fetchone()[0]
            
            if location_count == 0:
                # Добавляем тестовые пункты выдачи для самовывоза
                pickup_locations = [
                    ('Пункт выдачи 1', 'ул. Ленина, д. 10', 'Москва', 'pickup', 0),
                    ('Пункт выдачи 2', 'пр. Мира, д. 25', 'Санкт-Петербург', 'pickup', 0),
                    ('Пункт выдачи 3', 'ул. Советская, д. 5', 'Новосибирск', 'pickup', 0),
                ]
                
                for name, address, city, location_type, delivery_price in pickup_locations:
                    cursor.execute('''
                        INSERT INTO pickup_locations (name, address, city, location_type, delivery_price)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (name, address, city, location_type, delivery_price))
                
                # Добавляем тестовые пункты для доставки
                delivery_locations = [
                    ('Доставка по городу', 'Доставка курьером', 'Москва', 'delivery', 300),
                    ('Доставка по городу', 'Доставка курьером', 'Санкт-Петербург', 'delivery', 250),
                    ('Доставка по городу', 'Доставка курьером', 'Новосибирск', 'delivery', 200),
                ]
                
                for name, address, city, location_type, delivery_price in delivery_locations:
                    cursor.execute('''
                        INSERT INTO pickup_locations (name, address, city, location_type, delivery_price)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (name, address, city, location_type, delivery_price))
        else:
            # SQLite начальные данные
            # Добавляем стандартные разделы если их нет
            default_sections = [
                ('devices', 'Устройства', '📱', 1),
                ('consumables', 'Расходники', '🧴', 2),
                ('accessories', 'Аксессуары', '🧰', 3)
            ]
            
            for section_id, name, icon, order in default_sections:
                cursor.execute('''
                    INSERT OR IGNORE INTO sections (name, display_name, icon, sort_order)
                    VALUES (?, ?, ?, ?)
                ''', (name, name, icon, order))
            
            # Получаем ID разделов для привязки категорий
            cursor.execute('SELECT id, name FROM sections')
            sections = {name: id for id, name in cursor.fetchall()}
            
            # Добавляем стандартные категории если их нет
            default_categories = [
                ('pods', 'Поды', '🎯', 1, sections.get('devices')),
                ('mods', 'Моды', '⚡', 2, sections.get('devices')),
                ('disposable', 'Одноразовые', '🚬', 3, sections.get('devices')),
                ('liquids', 'Жидкости', '💧', 4, sections.get('consumables')),
                ('coils', 'Испарители', '🔥', 5, sections.get('consumables')),
                ('batteries', 'Батареи', '🔋', 6, sections.get('accessories')),
                ('cases', 'Чехлы', '🎒', 7, sections.get('accessories'))
            ]
            
            for cat_id, name, icon, order, section_id in default_categories:
                # Проверяем, существует ли уже категория
                cursor.execute('SELECT id FROM categories WHERE name = ?', (cat_id,))
                existing = cursor.fetchone()
                
                if not existing:
                    cursor.execute('''
                        INSERT INTO categories (name, display_name, icon, section_id, sort_order)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (cat_id, name, icon, section_id, order))
                else:
                    # Обновляем существующую категорию
                    cursor.execute('''
                        UPDATE categories 
                        SET display_name = ?, icon = ?, section_id = ?, sort_order = ?
                        WHERE name = ?
                    ''', (name, icon, section_id, order, cat_id))
            
            # Добавляем стандартные города и пункты выдачи
            # Проверяем, есть ли уже пункты выдачи
            cursor.execute('SELECT COUNT(*) FROM pickup_locations')
            location_count = cursor.fetchone()[0]
            
            if location_count == 0:
                # Добавляем тестовые пункты выдачи для самовывоза
                pickup_locations = [
                    ('Пункт выдачи 1', 'ул. Ленина, д. 10', 'Москва', 'pickup', 0),
                    ('Пункт выдачи 2', 'пр. Мира, д. 25', 'Санкт-Петербург', 'pickup', 0),
                    ('Пункт выдачи 3', 'ул. Советская, д. 5', 'Новосибирск', 'pickup', 0),
                ]
                
                for name, address, city, location_type, delivery_price in pickup_locations:
                    cursor.execute('''
                        INSERT INTO pickup_locations (name, address, city, location_type, delivery_price)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (name, address, city, location_type, delivery_price))
                
                # Добавляем тестовые пункты для доставки
                delivery_locations = [
                    ('Доставка по городу', 'Доставка курьером', 'Москва', 'delivery', 300),
                    ('Доставка по городу', 'Доставка курьером', 'Санкт-Петербург', 'delivery', 250),
                    ('Доставка по городу', 'Доставка курьером', 'Новосибирск', 'delivery', 200),
                ]
                
                for name, address, city, location_type, delivery_price in delivery_locations:
                    cursor.execute('''
                        INSERT INTO pickup_locations (name, address, city, location_type, delivery_price)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (name, address, city, location_type, delivery_price))
```

Ключевое исправление: я добавил метод execute в класс Database:

```python
def execute(self, cursor, query, params=None):
    """Универсальный метод выполнения SQL запросов"""
    if params is None:
        params = []
    
    if self.is_postgres:
        # Для PostgreSQL заменяем ? на %s
        query = query.replace('?', '%s')
    
    cursor.execute(query, params)
          