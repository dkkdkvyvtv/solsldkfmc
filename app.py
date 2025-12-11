import os
import json
import sqlite3
import hmac
import hashlib
import base64
from datetime import datetime
from urllib.parse import parse_qs, unquote
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from config import Config
from database import Database
from PIL import Image
import io

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
db = Database()

IMAGE_SIZES = {
    'catalog': (400, 300),
    'product': (600, 450),
    'cart': (120, 90)
}

# Telegram Bot API секрет для проверки подписи
BOT_TOKEN = Config.TELEGRAM_BOT_TOKEN

def verify_telegram_webapp_data(init_data_str):
    """Проверка подписи данных Telegram Web App"""
    try:
        if not BOT_TOKEN:
            print("BOT_TOKEN не установлен, пропускаем проверку подписи")
            return True
            
        if not init_data_str:
            print("Нет init_data для проверки")
            return False
        
        # Парсим данные
        parsed_data = parse_qs(unquote(init_data_str))
        
        # Извлекаем хеш
        hash_value = parsed_data.get('hash', [''])[0]
        if not hash_value:
            print("Нет хеша в данных")
            return False
        
        # Удаляем хеш из данных для проверки
        parsed_data.pop('hash', None)
        
        # Сортируем ключи
        data_check_arr = []
        for key in sorted(parsed_data.keys()):
            value = parsed_data[key][0]
            if value:
                data_check_arr.append(f"{key}={value}")
        
        # Формируем строку для проверки
        data_check_string = "\n".join(data_check_arr)
        
        # Вычисляем секретный ключ
        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()
        
        # Вычисляем хеш
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Сравниваем хеши
        if calculated_hash == hash_value:
            print("Подпись Telegram Web App проверена успешно")
            return True
        else:
            print(f"Неверная подпись! Полученный: {hash_value[:10]}..., Вычисленный: {calculated_hash[:10]}...")
            return False
            
    except Exception as e:
        print(f"Ошибка проверки подписи Telegram: {e}")
        return False

def parse_telegram_user_data(init_data_str):
    """Извлечение данных пользователя из initData Telegram Web App"""
    try:
        if not init_data_str:
            print("Нет init_data для парсинга")
            return None
        
        # Парсим данные
        parsed_data = parse_qs(unquote(init_data_str))
        
        # Извлекаем данные пользователя
        user_json = parsed_data.get('user', [''])[0]
        if not user_json:
            print("Нет данных пользователя в init_data")
            return None
        
        user_data = json.loads(user_json)
        
        return {
            'id': user_data.get('id'),
            'first_name': user_data.get('first_name', 'Пользователь'),
            'last_name': user_data.get('last_name'),
            'username': user_data.get('username'),
            'language_code': user_data.get('language_code'),
            'is_premium': user_data.get('is_premium', False),
            'photo_url': user_data.get('photo_url')
        }
        
    except Exception as e:
        print(f"Ошибка парсинга данных Telegram пользователя: {e}")
        return None

def get_telegram_user_data():
    """Получение данных пользователя из Telegram Web App или запроса"""
    try:
        # Пытаемся получить данные из Telegram Web App
        init_data = request.headers.get('X-Telegram-Init-Data') or request.args.get('tgWebAppData')
        
        if init_data and verify_telegram_webapp_data(init_data):
            user_data = parse_telegram_user_data(init_data)
            if user_data:
                return user_data
        
        # Проверяем наличие init_data в JSON теле запроса
        if request.is_json:
            data = request.get_json()
            init_data = data.get('initData')
            if init_data and verify_telegram_webapp_data(init_data):
                user_data = parse_telegram_user_data(init_data)
                if user_data:
                    return user_data
        
        # Если данные Telegram не получены, используем данные из сессии или тестовые данные
        user_id = request.cookies.get('user_id')
        if user_id:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT telegram_id, first_name, username, photo_url FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            conn.close()
            
            if user:
                return {
                    'id': user[0],
                    'first_name': user[1],
                    'username': user[2],
                    'photo_url': user[3] or '/static/images/default-avatar.png'
                }
        
        # Возвращаем тестовые данные для разработки
        return {
            'id': 1,
            'first_name': 'Тестовый Пользователь',
            'username': 'test_user',
            'photo_url': '/static/images/default-avatar.png'
        }
        
    except Exception as e:
        print(f"Ошибка получения данных пользователя: {e}")
        return {
            'id': 1,
            'first_name': 'Ошибка',
            'username': 'error_user',
            'photo_url': '/static/images/default-avatar.png'
        }

def get_or_create_user(telegram_user_data):
    """Получить или создать пользователя в базе данных"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь
        cursor.execute('SELECT id, balance FROM users WHERE telegram_id = ?', (telegram_user_data['id'],))
        user = cursor.fetchone()
        
        if user:
            user_id = user[0]
            balance = user[1]
            # Обновляем данные пользователя
            cursor.execute('''
                UPDATE users 
                SET first_name = ?, username = ?, photo_url = ?
                WHERE id = ?
            ''', (
                telegram_user_data.get('first_name', 'Пользователь'),
                telegram_user_data.get('username'),
                telegram_user_data.get('photo_url', '/static/images/default-avatar.png'),
                user_id
            ))
        else:
            # Создаем нового пользователя
            cursor.execute('''
                INSERT INTO users (telegram_id, username, first_name, photo_url, balance)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                telegram_user_data['id'],
                telegram_user_data.get('username'),
                telegram_user_data.get('first_name', 'Пользователь'),
                telegram_user_data.get('photo_url', '/static/images/default-avatar.png'),
                0.0
            ))
            user_id = cursor.lastrowid
            balance = 0.0
        
        conn.commit()
        conn.close()
        
        return {
            'id': user_id,
            'telegram_id': telegram_user_data['id'],
            'first_name': telegram_user_data.get('first_name', 'Пользователь'),
            'username': telegram_user_data.get('username'),
            'photo_url': telegram_user_data.get('photo_url', '/static/images/default-avatar.png'),
            'balance': balance
        }
        
    except Exception as e:
        print(f"Ошибка при получении/создании пользователя: {e}")
        raise

def process_and_save_image(image_data, filename, product_name):
    """Обработка и сохранение изображения товара"""
    try:
        os.makedirs('static/images/products/original', exist_ok=True)
        os.makedirs('static/images/products/catalog', exist_ok=True)
        os.makedirs('static/images/products/product', exist_ok=True)
        os.makedirs('static/images/products/cart', exist_ok=True)
        
        # Открываем изображение
        image = Image.open(io.BytesIO(image_data))
        
        # Сохраняем оригинал
        original_path = f'static/images/products/original/{filename}'
        image.save(original_path, 'JPEG', quality=85)
        
        # Создаем уменьшенные версии
        for size_name, (width, height) in IMAGE_SIZES.items():
            resized_image = image.copy()
            resized_image.thumbnail((width, height), Image.Resampling.LANCZOS)
            
            size_path = f'static/images/products/{size_name}/{filename}'
            resized_image.save(size_path, 'JPEG', quality=90)
        
        return f'/static/images/products/catalog/{filename}'
        
    except Exception as e:
        print(f"Ошибка обработки изображения: {e}")
        return '/static/images/default-product.png'

def get_image_paths(product_id, image_path):
    """Получение путей к изображениям разных размеров"""
    if not image_path or image_path == '/static/images/default-product.png':
        return {
            'catalog': '/static/images/default-product.png',
            'product': '/static/images/default-product.png',
            'cart': '/static/images/default-product.png'
        }
    
    try:
        filename = os.path.basename(image_path)
        
        # Проверяем существование файлов
        catalog_path = f'static/images/products/catalog/{filename}'
        product_path = f'static/images/products/product/{filename}'
        cart_path = f'static/images/products/cart/{filename}'
        
        return {
            'catalog': f'/static/images/products/catalog/{filename}' if os.path.exists(catalog_path) else '/static/images/default-product.png',
            'product': f'/static/images/products/product/{filename}' if os.path.exists(product_path) else '/static/images/default-product.png',
            'cart': f'/static/images/products/cart/{filename}' if os.path.exists(cart_path) else '/static/images/default-product.png'
        }
    except Exception as e:
        print(f"Ошибка получения путей изображений: {e}")
        return {
            'catalog': '/static/images/default-product.png',
            'product': '/static/images/default-product.png',
            'cart': '/static/images/default-avatar.png'
        }

@app.before_request
def before_request():
    """Действия перед каждым запросом"""
    # Устанавливаем заголовки CORS для Telegram Web App
    if request.method == 'OPTIONS':
        return '', 200
    
    # Проверяем, является ли запрос из Telegram Web App
    is_telegram = request.headers.get('X-Telegram-Init-Data') or request.args.get('tgWebAppData')
    if is_telegram:
        app.logger.info(f"Запрос из Telegram Web App: {request.path}")

@app.after_request
def after_request(response):
    """Действия после каждого запроса"""
    # Добавляем заголовки CORS
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Telegram-Init-Data')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/catalog')
def catalog():
    """Страница каталога"""
    category = request.args.get('category', 'all')
    section = request.args.get('section', 'all')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Получаем разделы для фильтра
    cursor.execute('''
        SELECT id, name, display_name, icon, sort_order
        FROM sections 
        WHERE is_active = 1
        ORDER BY sort_order
    ''')
    sections_data = cursor.fetchall()
    
    sections_list = []
    for section_data in sections_data:
        sections_list.append({
            'id': section_data[0],
            'name': section_data[1],
            'display_name': section_data[2],
            'icon': section_data[3],
            'sort_order': section_data[4]
        })
    
    # Формируем запрос для товаров
    query = '''
        SELECT p.*, c.display_name as category_display_name, s.name as section_name
        FROM products p
        LEFT JOIN categories c ON p.category = c.name
        LEFT JOIN sections s ON c.section_id = s.id
        WHERE p.is_active = 1
    '''
    params = []
    
    if category != 'all':
        query += ' AND p.category = ?'
        params.append(category)
    
    if section != 'all':
        # Получаем ID раздела
        cursor.execute('SELECT id FROM sections WHERE name = ?', (section,))
        section_row = cursor.fetchone()
        if section_row:
            section_id = section_row[0]
            # Получаем категории в этом разделе
            cursor.execute('SELECT name FROM categories WHERE section_id = ?', (section_id,))
            section_categories = [row[0] for row in cursor.fetchall()]
            
            if section_categories:
                if category != 'all' and category not in section_categories:
                    # Если выбрана категория не из этого раздела, показываем пустой список
                    conn.close()
                    return render_template('catalog.html', 
                                         products=[], 
                                         sections=sections_list,
                                         current_category=category,
                                         current_section=section,
                                         has_products=False)
                elif category == 'all':
                    # Если выбраны все категории в разделе
                    placeholders = ','.join(['?'] * len(section_categories))
                    query += f' AND p.category IN ({placeholders})'
                    params.extend(section_categories)
    
    query += ' ORDER BY p.created_at DESC'
    
    cursor.execute(query, params)
    products_data = cursor.fetchall()
    conn.close()
    
    # Формируем список товаров
    products_list = []
    for product in products_data:
        image_paths = get_image_paths(product[0], product[4])
        
        products_list.append({
            'id': product[0],
            'name': product[1],
            'description': product[2],
            'price': product[3],
            'image_path': image_paths['catalog'],
            'specifications': json.loads(product[5]) if product[5] else [],
            'category': product[6],
            'category_display_name': product[8] if len(product) > 8 else product[6],
            'section_name': product[9] if len(product) > 9 else None
        })
    
    return render_template('catalog.html', 
                         products=products_list, 
                         sections=sections_list,
                         current_category=category,
                         current_section=section,
                         has_products=len(products_list) > 0)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Страница товара"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM products WHERE id = ? AND is_active = 1', (product_id,))
    product_data = cursor.fetchone()
    conn.close()
    
    if not product_data:
        return render_template('404.html'), 404
    
    image_paths = get_image_paths(product_data[0], product_data[4])
    
    product = {
        'id': product_data[0],
        'name': product_data[1],
        'description': product_data[2],
        'price': product_data[3],
        'image_path': image_paths['product'],
        'specifications': json.loads(product_data[5]) if product_data[5] else [],
        'category': product_data[6]
    }
    
    return render_template('product.html', product=product)

@app.route('/cart')
def cart():
    """Страница корзины"""
    return render_template('cart.html')

@app.route('/profile')
def profile():
    """Страница профиля"""
    return render_template('profile.html')

@app.route('/api/init', methods=['POST'])
def api_init():
    """Инициализация приложения - получение данных пользователя"""
    try:
        data = request.get_json(silent=True) or {}
        init_data = data.get('initData')
        
        # Проверяем подпись Telegram Web App
        is_telegram = False
        telegram_user_data = None
        
        if init_data and verify_telegram_webapp_data(init_data):
            is_telegram = True
            telegram_user_data = parse_telegram_user_data(init_data)
        
        if not telegram_user_data:
            # Используем данные из запроса или создаем тестового пользователя
            user_data = data.get('user')
            if user_data and user_data.get('id'):
                telegram_user_data = user_data
            else:
                # Создаем тестового пользователя
                telegram_user_data = {
                    'id': 1,
                    'first_name': 'Тестовый Пользователь',
                    'username': 'test_user',
                    'photo_url': '/static/images/default-avatar.png'
                }
        
        # Получаем или создаем пользователя в базе
        user = get_or_create_user(telegram_user_data)
        
        # Создаем ответ
        response_data = {
            'success': True,
            'user': {
                'id': user['telegram_id'],
                'first_name': user['first_name'],
                'username': user['username'],
                'photo_url': user['photo_url']
            },
            'balance': user['balance'],
            'is_telegram': is_telegram
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Ошибка в api_init: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'user': {
                'id': 1,
                'first_name': 'Ошибка',
                'username': 'error',
                'photo_url': '/static/images/default-avatar.png'
            },
            'balance': 0,
            'is_telegram': False
        }), 500

@app.route('/api/sections')
def api_sections():
    """Получение списка разделов"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT s.id, s.name, s.display_name, s.icon, s.sort_order,
                   COUNT(DISTINCT c.id) as category_count,
                   COUNT(DISTINCT p.id) as product_count
            FROM sections s
            LEFT JOIN categories c ON s.id = c.section_id AND c.is_active = 1
            LEFT JOIN products p ON c.name = p.category AND p.is_active = 1
            WHERE s.is_active = 1
            GROUP BY s.id
            ORDER BY s.sort_order
        ''')
        
        sections_data = cursor.fetchall()
        conn.close()
        
        sections_list = []
        for section in sections_data:
            sections_list.append({
                'id': section[0],
                'name': section[1],
                'display_name': section[2],
                'icon': section[3],
                'sort_order': section[4],
                'category_count': section[5],
                'product_count': section[6]
            })
        
        return jsonify(sections_list)
        
    except Exception as e:
        print(f"Ошибка получения разделов: {e}")
        return jsonify([])

@app.route('/api/categories')
def api_categories():
    """Получение списка всех категорий"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.name, c.display_name, c.icon, s.display_name as section_name
            FROM categories c
            LEFT JOIN sections s ON c.section_id = s.id
            WHERE c.is_active = 1 
            ORDER BY c.sort_order
        ''')
        
        categories_data = cursor.fetchall()
        conn.close()
        
        categories_list = []
        for cat in categories_data:
            categories_list.append({
                'id': cat[0],
                'name': cat[1],
                'icon': cat[2] or '📦',
                'section_name': cat[3]
            })
        
        return jsonify(categories_list)
        
    except Exception as e:
        print(f"Ошибка получения категорий: {e}")
        return jsonify([])

@app.route('/api/categories/section/<section_name>')
def api_categories_by_section(section_name):
    """Получение категорий по разделу"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        if section_name == 'all':
            cursor.execute('''
                SELECT c.name, c.display_name, c.icon
                FROM categories c
                WHERE c.is_active = 1
                ORDER BY c.sort_order
            ''')
        else:
            cursor.execute('''
                SELECT c.name, c.display_name, c.icon
                FROM categories c
                JOIN sections s ON c.section_id = s.id
                WHERE s.name = ? AND c.is_active = 1
                ORDER BY c.sort_order
            ''', (section_name,))
        
        categories_data = cursor.fetchall()
        conn.close()
        
        categories_list = []
        for cat in categories_data:
            categories_list.append({
                'id': cat[0],
                'name': cat[1] if cat[1] else cat[0],
                'icon': cat[2] or '📦'
            })
        
        return jsonify(categories_list)
        
    except Exception as e:
        print(f"Ошибка получения категорий по разделу: {e}")
        return jsonify([])

@app.route('/api/products/featured')
def api_featured_products():
    """Получение популярных товаров по разделам"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Получаем активные разделы
        cursor.execute('''
            SELECT s.id, s.name, s.display_name, s.icon
            FROM sections s
            WHERE s.is_active = 1
            ORDER BY s.sort_order
            LIMIT 3
        ''')
        
        sections_data = cursor.fetchall()
        
        result = {}
        
        for section in sections_data:
            section_id, section_name, display_name, icon = section
            
            # Получаем товары из этого раздела
            cursor.execute('''
                SELECT p.id, p.name, p.description, p.price, p.image_path, p.category
                FROM products p
                JOIN categories c ON p.category = c.name
                WHERE c.section_id = ? AND p.is_active = 1
                ORDER BY p.created_at DESC
                LIMIT 6
            ''', (section_id,))
            
            products_data = cursor.fetchall()
            
            if products_data:
                products_list = []
                for product in products_data:
                    image_paths = get_image_paths(product[0], product[4])
                    
                    products_list.append({
                        'id': product[0],
                        'name': product[1],
                        'description': product[2],
                        'price': product[3],
                        'image_path': image_paths['catalog'],
                        'category': product[5]
                    })
                
                result[section_name] = {
                    'id': section_id,
                    'display_name': display_name,
                    'icon': icon,
                    'products': products_list
                }
        
        conn.close()
        
        # Если нет товаров в разделах, возвращаем любые товары
        if not result:
            conn = db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT p.id, p.name, p.description, p.price, p.image_path, p.category
                FROM products p
                WHERE p.is_active = 1
                ORDER BY p.created_at DESC
                LIMIT 6
            ''')
            
            products_data = cursor.fetchall()
            conn.close()
            
            if products_data:
                products_list = []
                for product in products_data:
                    image_paths = get_image_paths(product[0], product[4])
                    
                    products_list.append({
                        'id': product[0],
                        'name': product[1],
                        'description': product[2],
                        'price': product[3],
                        'image_path': image_paths['catalog'],
                        'category': product[5]
                    })
                
                result['featured'] = {
                    'id': 0,
                    'display_name': 'Популярное',
                    'icon': '🔥',
                    'products': products_list
                }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Ошибка получения популярных товаров: {e}")
        return jsonify({})

@app.route('/api/cart/add', methods=['POST'])
def api_cart_add():
    """Добавление товара в корзину"""
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        
        if not product_id:
            return jsonify({'success': False, 'error': 'Не указан ID товара'})
        
        # Получаем данные пользователя
        user_data = get_telegram_user_data()
        user_id = user_data['id']
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование товара
        cursor.execute('SELECT id, name, price FROM products WHERE id = ? AND is_active = 1', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'error': 'Товар не найден'})
        
        # Проверяем, есть ли пользователь в базе
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            # Создаем пользователя если его нет
            cursor.execute('''
                INSERT INTO users (telegram_id, first_name, username, photo_url, balance)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                user_data['id'],
                user_data.get('first_name', 'Пользователь'),
                user_data.get('username'),
                user_data.get('photo_url', '/static/images/default-avatar.png'),
                0.0
            ))
            user_db_id = cursor.lastrowid
        else:
            user_db_id = user[0]
        
        # Проверяем, есть ли товар уже в корзине
        cursor.execute('''
            SELECT id, quantity FROM cart_items 
            WHERE user_id = ? AND product_id = ?
        ''', (user_db_id, product_id))
        
        existing_item = cursor.fetchone()
        
        if existing_item:
            # Увеличиваем количество
            cursor.execute('''
                UPDATE cart_items SET quantity = quantity + 1 
                WHERE id = ?
            ''', (existing_item[0],))
        else:
            # Добавляем новый товар
            cursor.execute('''
                INSERT INTO cart_items (user_id, product_id, quantity)
                VALUES (?, ?, 1)
            ''', (user_db_id, product_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Ошибка добавления в корзину: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cart/items')
def api_cart_items():
    """Получение содержимого корзины"""
    try:
        user_data = get_telegram_user_data()
        user_id = user_data['id']
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Получаем ID пользователя в базе
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'items': [], 'total': 0})
        
        user_db_id = user[0]
        
        # Получаем товары в корзине
        cursor.execute('''
            SELECT p.id, p.name, p.price, p.image_path, ci.quantity
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            WHERE ci.user_id = ? AND p.is_active = 1
            ORDER BY ci.created_at DESC
        ''', (user_db_id,))
        
        cart_items_data = cursor.fetchall()
        conn.close()
        
        items = []
        total = 0
        
        for item in cart_items_data:
            image_paths = get_image_paths(item[0], item[3])
            
            item_total = item[2] * item[4]
            total += item_total
            
            items.append({
                'id': item[0],
                'name': item[1],
                'price': item[2],
                'image': image_paths['cart'],
                'quantity': item[4],
                'total': item_total
            })
        
        return jsonify({'items': items, 'total': total})
        
    except Exception as e:
        print(f"Ошибка получения корзины: {e}")
        return jsonify({'items': [], 'total': 0})

@app.route('/api/cart/update', methods=['POST'])
def api_cart_update():
    """Обновление количества товара в корзине"""
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = data.get('quantity')
        
        if not product_id or quantity is None:
            return jsonify({'success': False, 'error': 'Не указаны параметры'})
        
        user_data = get_telegram_user_data()
        user_id = user_data['id']
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Получаем ID пользователя в базе
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        user_db_id = user[0]
        
        if quantity == 0:
            # Удаляем товар из корзины
            cursor.execute('DELETE FROM cart_items WHERE user_id = ? AND product_id = ?', 
                          (user_db_id, product_id))
        else:
            # Обновляем количество
            cursor.execute('''
                UPDATE cart_items SET quantity = ? 
                WHERE user_id = ? AND product_id = ?
            ''', (quantity, user_db_id, product_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Ошибка обновления корзины: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cart/remove', methods=['POST'])
def api_cart_remove():
    """Удаление товара из корзины"""
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        
        if not product_id:
            return jsonify({'success': False, 'error': 'Не указан ID товара'})
        
        user_data = get_telegram_user_data()
        user_id = user_data['id']
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Получаем ID пользователя в базе
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        user_db_id = user[0]
        
        cursor.execute('DELETE FROM cart_items WHERE user_id = ? AND product_id = ?', 
                      (user_db_id, product_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Ошибка удаления из корзины: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cities')
def api_cities():
    """Получение списка городов"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT city 
            FROM pickup_locations 
            WHERE city IS NOT NULL AND is_active = 1
            ORDER BY city
        ''')
        
        cities_data = cursor.fetchall()
        conn.close()
        
        cities_list = [city[0] for city in cities_data]
        
        return jsonify(cities_list)
        
    except Exception as e:
        print(f"Ошибка получения городов: {e}")
        return jsonify([])

@app.route('/api/pickup-locations')
def api_pickup_locations():
    """Получение пунктов выдачи или доставки"""
    try:
        location_type = request.args.get('type', 'pickup')
        city = request.args.get('city', None)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT id, name, address, city, location_type, delivery_price 
            FROM pickup_locations 
            WHERE is_active = 1 AND location_type = ?
        '''
        params = [location_type]
        
        if city:
            query += ' AND city = ?'
            params.append(city)
        
        query += ' ORDER BY city, name'
        
        cursor.execute(query, params)
        locations_data = cursor.fetchall()
        conn.close()
        
        locations_list = []
        for loc in locations_data:
            locations_list.append({
                'id': loc[0],
                'name': loc[1],
                'address': loc[2],
                'city': loc[3],
                'location_type': loc[4],
                'delivery_price': loc[5]
            })
        
        return jsonify(locations_list)
        
    except Exception as e:
        print(f"Ошибка получения пунктов выдачи: {e}")
        return jsonify([])

@app.route('/api/order/create', methods=['POST'])
def api_order_create():
    """Создание заказа"""
    try:
        data = request.get_json()
        
        # Проверяем обязательные поля
        required_fields = ['customer_name', 'customer_phone', 'delivery_type', 'delivery_city']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Не заполнено поле: {field}'})
        
        customer_name = data['customer_name']
        customer_phone = data['customer_phone']
        delivery_type = data['delivery_type']
        delivery_city = data['delivery_city']
        pickup_location_id = data.get('pickup_location_id')
        delivery_address = data.get('delivery_address', '')
        
        # Получаем данные пользователя
        user_data = get_telegram_user_data()
        user_id = user_data['id']
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Получаем ID пользователя в базе
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        user_db_id = user[0]
        
        # Получаем товары из корзины
        cursor.execute('''
            SELECT p.id, p.price, ci.quantity
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            WHERE ci.user_id = ?
        ''', (user_db_id,))
        
        cart_items = cursor.fetchall()
        
        if not cart_items:
            conn.close()
            return jsonify({'success': False, 'error': 'Корзина пуста'})
        
        # Рассчитываем стоимость товаров
        items_total = sum(item[1] * item[2] for item in cart_items)
        
        # Получаем стоимость доставки
        delivery_price = 0
        delivery_info = ''
        
        if delivery_type == 'pickup':
            if pickup_location_id:
                cursor.execute('SELECT name, address FROM pickup_locations WHERE id = ? AND location_type = "pickup"', 
                             (pickup_location_id,))
                location = cursor.fetchone()
                if location:
                    delivery_info = f"{location[0]} - {location[1]}"
            else:
                delivery_info = "Самовывоз"
                
        elif delivery_type == 'delivery':
            cursor.execute('SELECT delivery_price FROM pickup_locations WHERE city = ? AND location_type = "delivery" LIMIT 1', 
                         (delivery_city,))
            delivery_data = cursor.fetchone()
            
            if delivery_data:
                delivery_price = delivery_data[0]
                delivery_info = f"Доставка в {delivery_city} - {delivery_address}"
            else:
                conn.close()
                return jsonify({'success': False, 'error': 'Доставка в этот город недоступна'})
        
        # Рассчитываем итоговую сумму
        total_amount = items_total + delivery_price
        
        # Рассчитываем кешбек
        cashback_earned = total_amount * Config.CASHBACK_RATE
        
        try:
            # Создаем заказ
            cursor.execute('''
                INSERT INTO orders (user_id, total_amount, cashback_earned, customer_name, customer_phone, 
                                  pickup_location, delivery_type, delivery_city, delivery_address, delivery_price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''', (user_db_id, total_amount, cashback_earned, customer_name, customer_phone, 
                  delivery_info, delivery_type, delivery_city, delivery_address, delivery_price))
            
            order_id = cursor.lastrowid
            
            # Начисляем кешбек пользователю
            cursor.execute('''
                UPDATE users SET balance = balance + ? 
                WHERE id = ?
            ''', (cashback_earned, user_db_id))
            
            # Очищаем корзину
            cursor.execute('DELETE FROM cart_items WHERE user_id = ?', (user_db_id,))
            
            conn.commit()
            
            # Отправляем уведомление администратору
            send_order_notification_to_admin(order_id, customer_name, customer_phone, total_amount, delivery_info, delivery_type)
            
            # Отправляем подтверждение пользователю
            send_order_confirmation_to_user(customer_phone, order_id, total_amount)
            
        except Exception as e:
            conn.rollback()
            conn.close()
            print(f"Ошибка создания заказа в БД: {e}")
            return jsonify({'success': False, 'error': f'Ошибка базы данных: {str(e)}'}), 500
        
        conn.close()
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'total_amount': total_amount,
            'cashback_earned': cashback_earned,
            'message': f'Заказ #{order_id} успешно оформлен!'
        })
        
    except Exception as e:
        print(f"Ошибка создания заказа: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def send_order_notification_to_admin(order_id, customer_name, customer_phone, total_amount, delivery_info, delivery_type):
    """Отправка уведомления администратору в Telegram"""
    try:
        if not BOT_TOKEN or not Config.ADMIN_USER_ID:
            print("Нет данных для отправки уведомления администратору")
            return
        
        import requests
        
        delivery_type_text = "самовывоз" if delivery_type == 'pickup' else "доставка"
        
        message = f"🛒 *Новый заказ #{order_id}*\n\n" \
                 f"👤 *Клиент:* {customer_name}\n" \
                 f"📞 *Телефон:* {customer_phone}\n" \
                 f"💰 *Сумма:* {total_amount:.2f} руб.\n" \
                 f"🚚 *Тип:* {delivery_type_text}\n" \
                 f"📍 *Адрес:* {delivery_info}\n\n" \
                 f"⏰ *Время:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': Config.ADMIN_USER_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, json=payload, timeout=5)
        
        if response.status_code != 200:
            print(f"Ошибка отправки уведомления админу: {response.text}")
            
    except Exception as e:
        print(f"Ошибка отправки уведомления админу: {e}")

def send_order_confirmation_to_user(phone, order_id, total_amount):
    """Отправка подтверждения пользователю (заглушка для SMS)"""
    print(f"Заказ #{order_id} оформлен для {phone}. Сумма: {total_amount:.2f} руб.")

@app.route('/api/user/profile')
def api_user_profile():
    """Получение профиля пользователя и истории заказов"""
    try:
        user_data = get_telegram_user_data()
        user_id = user_data['id']
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Получаем ID пользователя в базе
        cursor.execute('SELECT id, balance, first_name, username, photo_url FROM users WHERE telegram_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({
                'balance': 0,
                'first_name': user_data.get('first_name', 'Пользователь'),
                'username': user_data.get('username'),
                'photo_url': user_data.get('photo_url', '/static/images/default-avatar.png'),
                'orders': []
            })
        
        user_db_id = user[0]
        balance = user[1]
        first_name = user[2] or user_data.get('first_name', 'Пользователь')
        username = user[3] or user_data.get('username')
        photo_url = user[4] or user_data.get('photo_url', '/static/images/default-avatar.png')
        
        # Получаем заказы пользователя
        cursor.execute('''
            SELECT id, total_amount, cashback_earned, pickup_location, delivery_type, 
                   delivery_city, delivery_address, status, created_at
            FROM orders 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
        ''', (user_db_id,))
        
        orders_data = cursor.fetchall()
        conn.close()
        
        orders_list = []
        for order in orders_data:
            # Формируем информацию о доставке
            if order[4] == 'pickup':
                delivery_info = order[3] or 'Самовывоз'
            else:
                city_info = f" в {order[5]}" if order[5] else ""
                address_info = f" - {order[6]}" if order[6] else ""
                delivery_info = f"Доставка{city_info}{address_info}"
            
            orders_list.append({
                'id': order[0],
                'total_amount': order[1],
                'cashback_earned': order[2],
                'pickup_location': delivery_info,
                'delivery_type': order[4],
                'delivery_city': order[5],
                'delivery_address': order[6],
                'status': order[7],
                'created_at': order[8]
            })
        
        return jsonify({
            'balance': balance,
            'first_name': first_name,
            'username': username,
            'photo_url': photo_url,
            'orders': orders_list
        })
        
    except Exception as e:
        print(f"Ошибка получения профиля: {e}")
        return jsonify({
            'balance': 0,
            'first_name': 'Ошибка',
            'username': 'error',
            'photo_url': '/static/images/default-avatar.png',
            'orders': []
        }), 500

@app.route('/api/products/search')
def api_products_search():
    """Поиск товаров"""
    try:
        query = request.args.get('q', '').strip().lower()
        
        if not query or len(query) < 2:
            return jsonify([])
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, description, price, image_path 
            FROM products 
            WHERE is_active = 1 AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?)
            ORDER BY name
            LIMIT 20
        ''', (f'%{query}%', f'%{query}%'))
        
        products_data = cursor.fetchall()
        conn.close()
        
        products_list = []
        for product in products_data:
            image_paths = get_image_paths(product[0], product[4])
            
            products_list.append({
                'id': product[0],
                'name': product[1],
                'description': product[2],
                'price': product[3],
                'image_path': image_paths['catalog']
            })
        
        return jsonify(products_list)
        
    except Exception as e:
        print(f"Ошибка поиска товаров: {e}")
        return jsonify([])

@app.route('/static/images/<path:filename>')
def serve_static_images(filename):
    """Обслуживание статических изображений"""
    return send_from_directory('static/images', filename)

@app.route('/static/images/products/<path:subpath>/<path:filename>')
def serve_product_images(subpath, filename):
    """Обслуживание изображений товаров"""
    try:
        return send_from_directory(f'static/images/products/{subpath}', filename)
    except:
        return send_from_directory('static/images', 'default-product.png')

@app.errorhandler(404)
def not_found(error):
    """Обработчик 404 ошибки"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Обработчик 500 ошибки"""
    print(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Создаем необходимые папки
    folders = [
        'data',
        'static/images/products/original',
        'static/images/products/catalog', 
        'static/images/products/product',
        'static/images/products/cart'
    ]
    
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
    
    print("=" * 50)
    print("VapeCloud Shop запущен!")
    print(f"Сайт доступен по адресу: http://localhost:5000")
    print(f"Для Telegram Mini Apps: https://t.me/{Config.BOT_USERNAME}")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)