import os
import json
from datetime import datetime
from config import Config
import psycopg2
from urllib.parse import urlparse
import sqlite3
import traceback

class Database:
    def __init__(self):
        # Получаем URL базы данных из переменной окружения или из Config
        self.database_url = os.environ.get('DATABASE_URL') or getattr(Config, 'DATABASE_URL', None)
        self.is_postgres = False
        
        # Проверяем, это PostgreSQL или SQLite
        if self.database_url and (self.database_url.startswith('postgres://') or self.database_url.startswith('postgresql://')):
            self.is_postgres = True
            # Конвертируем postgres:// в postgresql:// если нужно
            if self.database_url.startswith('postgres://'):
                self.database_url = self.database_url.replace('postgres://', 'postgresql://', 1)
            print(f"Используется PostgreSQL: {self.database_url[:50]}...")
        else:
            # SQLite для локальной разработки
            self.db_path = getattr(Config, 'DATABASE_PATH', 'data/database.db')
            
            # Создаем папку для базы данных если она указана в пути
            db_dir = os.path.dirname(self.db_path)
            if db_dir:  # Если путь содержит папку (например, 'data/database.db')
                os.makedirs(db_dir, exist_ok=True)
                print(f"Создана папка для базы данных: {db_dir}")
            
            # Проверяем, существует ли файл базы данных
            if not os.path.exists(self.db_path):
                print(f"Файл базы данных не найден: {self.db_path}")
                print("Создаем новую базу данных...")
                # Создаем пустой файл
                try:
                    open(self.db_path, 'w').close()
                    print(f"Файл базы данных создан: {self.db_path}")
                except Exception as e:
                    print(f"Ошибка создания файла базы данных: {e}")
                    # Попробуем создать в текущей директории
                    self.db_path = 'database.db'
                    print(f"Пробуем создать в текущей директории: {self.db_path}")
                    open(self.db_path, 'w').close()
            else:
                print(f"Файл базы данных найден: {self.db_path}, размер: {os.path.getsize(self.db_path)} байт")
        
        self.init_db()
    
    def get_connection(self):
        """Возвращает соединение с базой данных"""
        if self.is_postgres:
            # PostgreSQL для Render
            try:
                result = urlparse(self.database_url)
                conn = psycopg2.connect(
                    database=result.path[1:],
                    user=result.username,
                    password=result.password,
                    host=result.hostname,
                    port=result.port,
                    sslmode='require'
                )
                print("Успешное подключение к PostgreSQL")
                return conn
            except Exception as e:
                print(f"Ошибка подключения к PostgreSQL: {e}")
                # Возвращаем SQLite соединение как запасной вариант
                print("Используем SQLite как запасной вариант")
                return sqlite3.connect(self.db_path)
        else:
            # SQLite для локальной разработки
            try:
                conn = sqlite3.connect(self.db_path)
                print(f"Успешное подключение к SQLite: {self.db_path}")
                return conn
            except Exception as e:
                print(f"Ошибка подключения к SQLite: {e}")
                # Пробуем создать новую базу
                return sqlite3.connect('database.db')
    
    def execute_query(self, cursor, query, params=None):
        """Универсальный метод выполнения SQL запросов"""
        if params is None:
            params = []
        
        if self.is_postgres:
            # Для PostgreSQL заменяем ? на %s
            query = query.replace('?', '%s')
        
        try:
            cursor.execute(query, params)
            return True
        except Exception as e:
            print(f"Ошибка выполнения запроса: {e}")
            print(f"Запрос: {query}")
            print(f"Параметры: {params}")
            traceback.print_exc()
            raise
    
    def fetchone(self, cursor):
        """Универсальный метод получения одной строки"""
        try:
            return cursor.fetchone()
        except:
            return None
    
    def fetchall(self, cursor):
        """Универсальный метод получения всех строк"""
        try:
            return cursor.fetchall()
        except:
            return []
    
    def lastrowid(self, cursor):
        """Получение ID последней вставленной записи"""
        try:
            if self.is_postgres:
                cursor.execute("SELECT LASTVAL()")
                result = cursor.fetchone()
                return result[0] if result else None
            else:
                return cursor.lastrowid
        except Exception as e:
            print(f"Ошибка получения lastrowid: {e}")
            return None
    
    def rowcount(self, cursor):
        """Получение количества затронутых строк"""
        try:
            return cursor.rowcount
        except:
            return 0
    
    def init_db(self):
        """Инициализация базы данных"""
        print(f"Инициализация базы данных...")
        print(f"Используется: {'PostgreSQL' if self.is_postgres else f'SQLite ({self.db_path})'}")
        
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
                    cashback_balance DECIMAL(10, 2) DEFAULT 0,
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
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (section_id) REFERENCES sections (id) ON DELETE SET NULL
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
                )
            ''')
            print("Таблица 'cart_items' проверена/создана")
            
            # Создаем индексы для производительности
            try:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_cart_items_user ON cart_items(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_categories_section ON categories(section_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_sections_active ON sections(is_active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_categories_active ON categories(is_active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_locations_city ON pickup_locations(city)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_locations_active ON pickup_locations(is_active)')
                print("Индексы проверены/созданы")
            except Exception as e:
                print(f"Ошибка создания индексов: {e}")
            
            # Проверяем и добавляем колонку photo_url в users если её нет
            try:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='photo_url'")
                if not cursor.fetchone():
                    cursor.execute('ALTER TABLE users ADD COLUMN photo_url TEXT')
                    print("Колонка 'photo_url' добавлена в таблицу 'users'")
            except:
                pass
            
            # Проверяем и добавляем колонку cashback_balance в users если её нет
            try:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='cashback_balance'")
                if not cursor.fetchone():
                    cursor.execute('ALTER TABLE users ADD COLUMN cashback_balance DECIMAL(10, 2) DEFAULT 0')
                    print("Колонка 'cashback_balance' добавлена в таблицу 'users'")
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
            print("Таблица 'users' проверена/создана")
            
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
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            print("Таблица 'categories' проверена/создана")
            
            # Проверяем есть ли колонка section_id, если нет - добавляем
            cursor.execute("PRAGMA table_info(categories)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'section_id' not in columns:
                cursor.execute('ALTER TABLE categories ADD COLUMN section_id INTEGER')
                print("Колонка 'section_id' добавлена в таблицу 'categories'")
            
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
            
            # Проверяем есть ли колонка cashback_balance в users, если нет - добавляем
            cursor.execute("PRAGMA table_info(users)")
            user_columns = [column[1] for column in cursor.fetchall()]
            
            if 'cashback_balance' not in user_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN cashback_balance REAL DEFAULT 0')
                print("Колонка 'cashback_balance' добавлена в таблицу 'users'")
            
            if 'photo_url' not in user_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN photo_url TEXT')
                print("Колонка 'photo_url' добавлена в таблицу 'users'")
    
    def _seed_initial_data(self, cursor):
        """Добавление начальных данных"""
        print("Начало добавления начальных данных...")
        
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
                    INSERT INTO categories (name, display_name, icon, section_id, sort_order)
                    VALUES (%s, %s, %s, %s, %s)
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
                print("Пункты выдачи добавлены")
                
            # Добавляем тестовые товары если их нет
            cursor.execute('SELECT COUNT(*) FROM products')
            product_count = cursor.fetchone()[0]
            
            if product_count == 0:
                print("Добавление тестовых товаров...")
                
                test_products = [
                    ('Voopoo Drag X', 'Мощный под-система с воздушным потоком', 2999.99, 'pods', '["Мощность: 5-80W", "Аккумулятор: 18650", "Тип: Под-система"]'),
                    ('GeekVape Aegis Legend', 'Водонепроницаемый и ударопрочный мод', 4599.99, 'mods', '["Мощность: 200W", "Аккумуляторы: 2x18650", "Защита: IP67"]'),
                    ('HQD Cuvie Plus', 'Одноразовая электронная сигарета', 699.99, 'disposable', '["Количество затяжек: 1500", "Вкус: Мята", "Никотин: 2%"]'),
                    ('Jam Monster', 'Жидкость со вкусом бутерброда с джемом', 899.99, 'liquids', '["Крепость: 3mg", "Объем: 100ml", "Вкус: Клубничный джем"]'),
                    ('GeekVape Z Coils', 'Испарители для GeekVape Z Series', 499.99, 'coils', '["Сопротивление: 0.2Ω", "Количество: 5 шт", "Серия: Z"]'),
                    ('Samsung 30Q', 'Высокотоковый аккумулятор', 699.99, 'batteries', '["Емкость: 3000mAh", "Ток: 15A", "Тип: 18650"]'),
                    ('Voopoo Drag Case', 'Чехол для Voopoo Drag', 399.99, 'cases', '["Материал: Силикон", "Цвет: Черный", "Модель: Drag X/S"]'),
                ]
                
                for name, description, price, category, specs in test_products:
                    cursor.execute('''
                        INSERT INTO products (name, description, price, category, specifications, is_active)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                    ''', (name, description, price, category, specs))
                
                print(f"Добавлено {len(test_products)} тестовых товаров")
                
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
                    INSERT OR IGNORE INTO sections (name, display_name, icon, sort_order)
                    VALUES (?, ?, ?, ?)
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
                print("Пункты выдачи добавлены")
                
            # Добавляем тестовые товары если их нет
            cursor.execute('SELECT COUNT(*) FROM products')
            product_count = cursor.fetchone()[0]
            
            if product_count == 0:
                print("Добавление тестовых товаров...")
                
                test_products = [
                    ('Voopoo Drag X', 'Мощный под-система с воздушным потоком', 2999.99, 'pods', '["Мощность: 5-80W", "Аккумулятор: 18650", "Тип: Под-система"]'),
                    ('GeekVape Aegis Legend', 'Водонепроницаемый и ударопрочный мод', 4599.99, 'mods', '["Мощность: 200W", "Аккумуляторы: 2x18650", "Защита: IP67"]'),
                    ('HQD Cuvie Plus', 'Одноразовая электронная сигарета', 699.99, 'disposable', '["Количество затяжек: 1500", "Вкус: Мята", "Никотин: 2%"]'),
                    ('Jam Monster', 'Жидкость со вкусом бутерброда с джемом', 899.99, 'liquids', '["Крепость: 3mg", "Объем: 100ml", "Вкус: Клубничный джем"]'),
                    ('GeekVape Z Coils', 'Испарители для GeekVape Z Series', 499.99, 'coils', '["Сопротивление: 0.2Ω", "Количество: 5 шт", "Серия: Z"]'),
                    ('Samsung 30Q', 'Высокотоковый аккумулятор', 699.99, 'batteries', '["Емкость: 3000mAh", "Ток: 15A", "Тип: 18650"]'),
                    ('Voopoo Drag Case', 'Чехол для Voopoo Drag', 399.99, 'cases', '["Материал: Силикон", "Цвет: Черный", "Модель: Drag X/S"]'),
                ]
                
                for name, description, price, category, specs in test_products:
                    cursor.execute('''
                        INSERT INTO products (name, description, price, category, specifications, is_active)
                        VALUES (?, ?, ?, ?, ?, 1)
                    ''', (name, description, price, category, specs))
                
                print(f"Добавлено {len(test_products)} тестовых товаров")
        
        print("Начальные данные успешно добавлены!")
    
    # Дополнительные методы для удобства работы с БД
    
    def get_user_by_telegram_id(self, telegram_id):
        """Получение пользователя по telegram_id"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            self.execute_query(cursor, 'SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
            user = self.fetchone(cursor)
            return user
        except Exception as e:
            print(f"Ошибка получения пользователя: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def get_active_products(self, category=None, limit=None):
        """Получение активных товаров"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            query = 'SELECT * FROM products WHERE is_active = 1'
            params = []
            
            if category:
                query += ' AND category = ?'
                params.append(category)
            
            query += ' ORDER BY created_at DESC'
            
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
            
            self.execute_query(cursor, query, params)
            products = self.fetchall(cursor)
            return products
        except Exception as e:
            print(f"Ошибка получения товаров: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_categories_with_sections(self):
        """Получение категорий с информацией о разделах"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            query = '''
                SELECT c.id, c.name, c.display_name, c.icon, c.sort_order, 
                       s.id as section_id, s.name as section_name, s.display_name as section_display_name
                FROM categories c
                LEFT JOIN sections s ON c.section_id = s.id
                WHERE c.is_active = 1
                ORDER BY c.sort_order
            '''
            
            self.execute_query(cursor, query)
            categories = self.fetchall(cursor)
            
            result = []
            for cat in categories:
                result.append({
                    'id': cat[0],
                    'name': cat[1],
                    'display_name': cat[2],
                    'icon': cat[3],
                    'sort_order': cat[4],
                    'section_id': cat[5],
                    'section_name': cat[6],
                    'section_display_name': cat[7]
                })
            
            return result
        except Exception as e:
            print(f"Ошибка получения категорий: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_active_sections(self):
        """Получение активных разделов"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            query = '''
                SELECT s.*, 
                       COUNT(DISTINCT c.id) as category_count,
                       COUNT(DISTINCT p.id) as product_count
                FROM sections s
                LEFT JOIN categories c ON s.id = c.section_id AND c.is_active = 1
                LEFT JOIN products p ON c.name = p.category AND p.is_active = 1
                WHERE s.is_active = 1
                GROUP BY s.id
                ORDER BY s.sort_order
            '''
            
            self.execute_query(cursor, query)
            sections = self.fetchall(cursor)
            
            result = []
            for sec in sections:
                result.append({
                    'id': sec[0],
                    'name': sec[1],
                    'display_name': sec[2],
                    'icon': sec[3],
                    'sort_order': sec[4],
                    'is_active': bool(sec[5]),
                    'category_count': sec[6],
                    'product_count': sec[7]
                })
            
            return result
        except Exception as e:
            print(f"Ошибка получения разделов: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_cities_with_locations(self):
        """Получение городов с количеством пунктов"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            query = '''
                SELECT city, 
                       COUNT(CASE WHEN location_type = 'pickup' THEN 1 END) as pickup_count,
                       COUNT(CASE WHEN location_type = 'delivery' THEN 1 END) as delivery_count
                FROM pickup_locations 
                WHERE city IS NOT NULL AND is_active = 1
                GROUP BY city
                ORDER BY city
            '''
            
            self.execute_query(cursor, query)
            cities = self.fetchall(cursor)
            
            result = {}
            for city_data in cities:
                city = city_data[0]
                result[city] = {
                    'pickup': city_data[1] or 0,
                    'delivery': city_data[2] or 0
                }
            
            return result
        except Exception as e:
            print(f"Ошибка получения городов: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()

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
            print(f"Используется SQLite: {db.db_path}")
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()
            print(f"SQLite версия: {version[0]}")
        
        # Проверяем таблицы
        print("\nПроверка таблиц...")
        if db.is_postgres:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        
        tables = cursor.fetchall()
        print(f"Найдено таблиц: {len(tables)}")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Проверяем данные в таблицах
        print("\nПроверка данных в таблицах...")
        test_tables = ['sections', 'categories', 'pickup_locations', 'products', 'users']
        for table in test_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  - {table}: {count} записей")
        
        # Проверяем дополнительные методы
        print("\nПроверка дополнительных методов...")
        
        # Активные разделы
        sections = db.get_active_sections()
        print(f"Активных разделов: {len(sections)}")
        
        # Категории с разделами
        categories = db.get_categories_with_sections()
        print(f"Категорий с разделами: {len(categories)}")
        
        # Города
        cities = db.get_cities_with_locations()
        print(f"Городов с пунктами выдачи: {len(cities)}")
        
        # Активные товары
        products = db.get_active_products(limit=5)
        print(f"Активных товаров (первые 5): {len(products)}")
        
    except Exception as e:
        print(f"Ошибка при проверке базы данных: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()
        print("\n" + "=" * 50)
        print("Проверка завершена!")
        print("=" * 50)