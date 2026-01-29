import os
import json
from datetime import datetime
from config import Config
import psycopg2
from urllib.parse import urlparse
import sqlite3

class Database:
    def __init__(self):
        # Получаем URL базы данных из переменной окружения или из Config
        self.database_url = os.environ.get('DATABASE_URL') or getattr(Config, 'DATABASE_URL', None)
        self.is_postgres = False
        
        print("=" * 50)
        print(f"DATABASE_URL из окружения: {os.environ.get('DATABASE_URL')}")
        print(f"DATABASE_URL из Config: {getattr(Config, 'DATABASE_URL', None)}")
        print(f"Итоговый DATABASE_URL: {self.database_url[:50] + '...' if self.database_url and len(str(self.database_url)) > 50 else self.database_url}")
        
        if self.database_url:
            # ЯВНАЯ проверка на PostgreSQL
            database_url_str = str(self.database_url).lower()
            if 'postgres' in database_url_str:
                self.is_postgres = True
                if database_url_str.startswith('postgres://'):
                    self.database_url = str(self.database_url).replace('postgres://', 'postgresql://', 1)
                print(f"✅ Определено: PostgreSQL")
            else:
                # Если это путь к файлу SQLite
                self.db_path = str(self.database_url)
                print(f"ℹ️ Определено: SQLite (путь: {self.db_path})")
        else:
            # Если нет DATABASE_URL, используем SQLite в рабочей директории
            self.db_path = 'database.db'
            print(f"⚠️ DATABASE_URL не найден, используем SQLite: {self.db_path}")
        
        print(f"is_postgres = {self.is_postgres}")
        if self.is_postgres:
            print(f"PostgreSQL URL: {str(self.database_url)[:50]}...")
        elif hasattr(self, 'db_path'):
            print(f"SQLite path: {self.db_path}")
        print("=" * 50)
        
        # Инициализируем базу данных
        self.init_db()
    
    def get_connection(self):
        """Возвращает соединение с базой данных"""
        if self.is_postgres and self.database_url:
            # PostgreSQL для Render
            try:
                print(f"🔗 Подключаемся к PostgreSQL...")
                
                # Упрощенное подключение для psycopg2
                conn = psycopg2.connect(self.database_url, sslmode='require')
                
                print("✅ Успешное подключение к PostgreSQL")
                return conn
            except Exception as e:
                print(f"❌ Ошибка подключения к PostgreSQL: {e}")
                import traceback
                traceback.print_exc()
                # Возвращаем SQLite соединение как запасной вариант
                print("🔄 Используем SQLite как запасной вариант")
                return sqlite3.connect('database.db')
        else:
            # SQLite для локальной разработки
            try:
                db_path = self.db_path if hasattr(self, 'db_path') else 'database.db'
                # Убедимся, что это не URL PostgreSQL
                if 'postgres' in db_path.lower():
                    print(f"⚠️ Обнаружен PostgreSQL URL в пути SQLite, используем database.db")
                    db_path = 'database.db'
                
                conn = sqlite3.connect(db_path)
                print(f"✅ Успешное подключение к SQLite: {db_path}")
                return conn
            except Exception as e:
                print(f"❌ Ошибка подключения к SQLite: {e}")
                # Пробуем создать новую базу
                return sqlite3.connect('database.db')
    
    def execute_query(self, cursor, query, params=None):
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
        print(f"Инициализация базы данных...")
        print(f"Используется: {'PostgreSQL' if self.is_postgres else f'SQLite ({self.db_path if hasattr(self, "db_path") else "database.db"})'}")
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Создаем таблицы с учетом типа БД
            print("Создание таблиц...")
            self._create_tables(cursor)
            
            # Добавляем начальные данные
            print("Добавление начальных данных...")
            self._seed_initial_data(cursor)
            
            conn.commit()
            print("База данных успешно инициализирована!")
            
        except Exception as e:
            conn.rollback()
            print(f"Ошибка инициализации БД: {e}")
            import traceback
            traceback.print_exc()
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
                    is_verified BOOLEAN DEFAULT FALSE,
                    referral_code VARCHAR(32) UNIQUE,
                    invited_by INTEGER,
                    total_spent DECIMAL(10, 2) DEFAULT 0,
                    total_orders INTEGER DEFAULT 0,
                    total_invited INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("Таблица 'users' проверена/создана")
            
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
            print("Таблица 'sections' проверена/создана")
            
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
            print("Таблица 'categories' проверена/создана")
            
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
            print("Таблица 'products' проверена/создана")
            
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("Таблица 'orders' проверена/создана")
            
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
            print("Таблица 'pickup_locations' проверена/создана")
            
            # Корзина
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cart_items (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    product_id INTEGER,
                    quantity INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("Таблица 'cart_items' проверена/создана")
            
            # Реферальные бонусы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS referral_bonuses (
                    id SERIAL PRIMARY KEY,
                    referrer_id INTEGER NOT NULL,
                    referred_id INTEGER NOT NULL,
                    amount DECIMAL(10, 2) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("Таблица 'referral_bonuses' проверена/создана")
            
            # Создаем индексы для производительности
            try:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_is_verified ON users(is_verified)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_invited_by ON users(invited_by)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_cart_items_user ON cart_items(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_bonuses_referrer ON referral_bonuses(referrer_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_bonuses_referred ON referral_bonuses(referred_id)')
                print("Индексы проверены/созданы")
            except Exception as e:
                print(f"Ошибка создания индексов (можно игнорировать): {e}")
            
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
                    is_verified BOOLEAN DEFAULT 0,
                    referral_code TEXT UNIQUE,
                    invited_by INTEGER,
                    total_spent REAL DEFAULT 0,
                    total_orders INTEGER DEFAULT 0,
                    total_invited INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (invited_by) REFERENCES users (id) ON DELETE SET NULL
                )
            ''')
            print("Таблица 'users' проверена/создана")
            
            # Проверяем наличие новых колонок и добавляем их если нужно
            try:
                cursor.execute("PRAGMA table_info(users)")
                user_columns = [column[1] for column in cursor.fetchall()]
                
                new_user_columns = [
                    ('is_verified', 'BOOLEAN DEFAULT 0'),
                    ('referral_code', 'TEXT UNIQUE'),
                    ('invited_by', 'INTEGER'),
                    ('total_spent', 'REAL DEFAULT 0'),
                    ('total_orders', 'INTEGER DEFAULT 0'),
                    ('total_invited', 'INTEGER DEFAULT 0')
                ]
                
                for col_name, col_type in new_user_columns:
                    if col_name not in user_columns:
                        cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')
                        print(f"Колонка '{col_name}' добавлена в таблицу 'users'")
            except:
                pass
            
            # Разделы (суперкатегории)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    icon TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            print("Таблица 'sections' проверена/создана")
            
            # Категории товаров
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    icon TEXT,
                    section_id INTEGER,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (section_id) REFERENCES sections (id) ON DELETE SET NULL
                )
            ''')
            print("Таблица 'categories' проверена/создана")
            
            # Проверяем есть ли колонка section_id, если нет - добавляем
            try:
                cursor.execute("PRAGMA table_info(categories)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'section_id' not in columns:
                    cursor.execute('ALTER TABLE categories ADD COLUMN section_id INTEGER')
                    print("Колонка 'section_id' добавлена в таблицу 'categories'")
            except:
                pass
            
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
            print("Таблица 'products' проверена/создана")
            
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
            print("Таблица 'orders' проверена/создана")
            
            # Проверяем есть ли новые колонки в orders, если нет - добавляем
            try:
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
                        print(f"Колонка '{col_name}' добавлена в таблицу 'orders'")
            except:
                pass
            
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
            print("Таблица 'pickup_locations' проверена/создана")
            
            # Проверяем есть ли новые колонки в pickup_locations
            try:
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
                        print(f"Колонка '{col_name}' добавлена в таблицу 'pickup_locations'")
            except:
                pass
            
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
            print("Таблица 'cart_items' проверена/создана")
            
            # Реферальные бонусы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS referral_bonuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    referred_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referrer_id) REFERENCES users (id),
                    FOREIGN KEY (referred_id) REFERENCES users (id)
                )
            ''')
            print("Таблица 'referral_bonuses' проверена/создана")
            
            # Создаем индексы для производительности
            try:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_is_verified ON users(is_verified)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_invited_by ON users(invited_by)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_cart_items_user ON cart_items(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_bonuses_referrer ON referral_bonuses(referrer_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_bonuses_referred ON referral_bonuses(referred_id)')
                print("Индексы проверены/созданы")
            except Exception as e:
                print(f"Ошибка создания индексов: {e}")
    
    def _seed_initial_data(self, cursor):
        """Добавление начальных данных"""
        print("Начало добавления начальных данных...")
        
        try:
            if self.is_postgres:
                # PostgreSQL начальные данные
                # Добавляем стандартные разделы если их нет
                default_sections = [
                    ('devices', 'Устройства', '📱', 1),
                    ('consumables', 'Расходники', '🧴', 2),
                    ('accessories', 'Аксессуары', '🧰', 3)
                ]
                
                for name, display_name, icon, order in default_sections:
                    cursor.execute('''
                        INSERT INTO sections (name, display_name, icon, sort_order, is_active)
                        VALUES (%s, %s, %s, %s, true)
                        ON CONFLICT (name) DO NOTHING
                    ''', (name, display_name, icon, order))
                print("Разделы добавлены")
                
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
                        INSERT INTO categories (name, display_name, icon, section_id, sort_order, is_active)
                        VALUES (%s, %s, %s, %s, %s, true)
                        ON CONFLICT (name) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        icon = EXCLUDED.icon,
                        section_id = EXCLUDED.section_id,
                        sort_order = EXCLUDED.sort_order
                    ''', (cat_id, name, icon, section_id, order))
                print("Категории добавлены")
                
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
                            INSERT INTO pickup_locations (name, address, city, location_type, delivery_price, is_active)
                            VALUES (%s, %s, %s, %s, %s, true)
                        ''', (name, address, city, location_type, delivery_price))
                    
                    # Добавляем тестовые пункты для доставки
                    delivery_locations = [
                        ('Доставка по городу', 'Доставка курьером', 'Москва', 'delivery', 300),
                        ('Доставка по городу', 'Доставка курьером', 'Санкт-Петербург', 'delivery', 250),
                        ('Доставка по городу', 'Доставка курьером', 'Новосибирск', 'delivery', 200),
                    ]
                    
                    for name, address, city, location_type, delivery_price in delivery_locations:
                        cursor.execute('''
                            INSERT INTO pickup_locations (name, address, city, location_type, delivery_price, is_active)
                            VALUES (%s, %s, %s, %s, %s, true)
                        ''', (name, address, city, location_type, delivery_price))
                    print("Пункты выдачи добавлены")
                    
            else:
                # SQLite начальные данные
                # Добавляем стандартные разделы если их нет
                default_sections = [
                    ('devices', 'Устройства', '📱', 1),
                    ('consumables', 'Расходники', '🧴', 2),
                    ('accessories', 'Аксессуары', '🧰', 3)
                ]
                
                for name, display_name, icon, order in default_sections:
                    cursor.execute('''
                        INSERT OR IGNORE INTO sections (name, display_name, icon, sort_order, is_active)
                        VALUES (?, ?, ?, ?, 1)
                    ''', (name, display_name, icon, order))
                print("Разделы добавлены")
                
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
                            INSERT INTO categories (name, display_name, icon, section_id, sort_order, is_active)
                            VALUES (?, ?, ?, ?, ?, 1)
                        ''', (cat_id, name, icon, section_id, order))
                    else:
                        # Обновляем существующую категорию
                        cursor.execute('''
                            UPDATE categories 
                            SET display_name = ?, icon = ?, section_id = ?, sort_order = ?
                            WHERE name = ?
                        ''', (name, icon, section_id, order, cat_id))
                print("Категории добавлены")
                
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
                            INSERT INTO pickup_locations (name, address, city, location_type, delivery_price, is_active)
                            VALUES (?, ?, ?, ?, ?, 1)
                        ''', (name, address, city, location_type, delivery_price))
                    
                    # Добавляем тестовые пункты для доставки
                    delivery_locations = [
                        ('Доставка по городу', 'Доставка курьером', 'Москва', 'delivery', 300),
                        ('Доставка по городу', 'Доставка курьером', 'Санкт-Петербург', 'delivery', 250),
                        ('Доставка по городу', 'Доставка курьером', 'Новосибирск', 'delivery', 200),
                    ]
                    
                    for name, address, city, location_type, delivery_price in delivery_locations:
                        cursor.execute('''
                            INSERT INTO pickup_locations (name, address, city, location_type, delivery_price, is_active)
                            VALUES (?, ?, ?, ?, ?, 1)
                        ''', (name, address, city, location_type, delivery_price))
                    print("Пункты выдачи добавлены")
            
            print("Начальные данные успешно добавлены!")
            
        except Exception as e:
            print(f"Ошибка при добавлении начальных данных: {e}")
            import traceback
            traceback.print_exc()

# Для проверки работы базы данных
if __name__ == '__main__':
    print("=" * 50)
    print("Проверка подключения к базе данных...")
    print("=" * 50)
    
    db = Database()
    
    # Проверяем соединение
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        if db.is_postgres:
            print(f"Используется PostgreSQL")
            cursor.execute("SELECT version()")
            version = cursor.fetchone()
            print(f"PostgreSQL версия: {version[0]}")
        else:
            print(f"Используется SQLite")
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()
            print(f"SQLite версия: {version[0]}")
        
        # Проверяем таблицы
        print("\nПроверка таблиц...")
        if db.is_postgres:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        
        tables = cursor.fetchall()
        print(f"Найдено таблиц: {len(tables)}")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Проверяем количество записей в основных таблицах
        print("\nКоличество записей в таблицах:")
        for table in ['users', 'sections', 'categories', 'products', 'pickup_locations']:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  - {table}: {count} записей")
            except:
                print(f"  - {table}: таблица не существует")
        
        cursor.close()
        conn.close()
        print("\nПроверка завершена успешно!")
        
    except Exception as e:
        print(f"Ошибка при проверке базы данных: {e}")
        import traceback
        traceback.print_exc()
