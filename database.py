import sqlite3
import json
from datetime import datetime
from config import Config

class Database:
    def __init__(self):
        self.db_path = Config.DATABASE_PATH
        self.init_db()
    
    def init_db(self):
        # Создаем папку data если её нет
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Пользователи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                first_name TEXT,
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
            ('pods', 'Поды', '🎯', 1, sections.get('Устройства')),
            ('mods', 'Моды', '⚡', 2, sections.get('Устройства')),
            ('disposable', 'Одноразовые', '🚬', 3, sections.get('Устройства')),
            ('liquids', 'Жидкости', '💧', 4, sections.get('Расходники')),
            ('coils', 'Испарители', '🔥', 5, sections.get('Расходники')),
            ('batteries', 'Батареи', '🔋', 6, sections.get('Аксессуары')),
            ('cases', 'Чехлы', '🎒', 7, sections.get('Аксессуары'))
        ]
        
        for cat_id, name, icon, order, section_id in default_categories:
            # Проверяем, существует ли уже категория
            cursor.execute('SELECT id FROM categories WHERE name = ?', (cat_id,))
            existing = cursor.fetchone()
            
            if not existing:
                cursor.execute('''
                    INSERT INTO categories (name, display_name, icon, section_id, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                ''', (cat_id, name, section_id, icon, order))
            else:
                # Обновляем существующую категорию
                cursor.execute('''
                    UPDATE categories 
                    SET display_name = ?, icon = ?, section_id = ?, sort_order = ?
                    WHERE name = ?
                ''', (name, icon, section_id, order, cat_id))
        
        # Добавляем стандартные города и пункты выдачи
        default_cities = [
            'Москва',
            'Санкт-Петербург',
            'Новосибирск',
            'Екатеринбург',
            'Казань'
        ]
        
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
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)