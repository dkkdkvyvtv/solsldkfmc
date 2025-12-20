import os
import json
import sqlite3
import hmac
import hashlib
import base64
from datetime import datetime
from urllib.parse import parse_qs, unquote
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, session
from config import Config
from database import Database
from PIL import Image
import io
import tempfile
import uuid
from functools import wraps

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
db = Database()

IMAGE_SIZES = {
    'catalog': (400, 300),
    'product': (600, 450),
    'cart': (120, 90)
}

# Система лояльности
LOYALTY_LEVELS = [
    {'min': 0, 'max': 10000, 'rate': 0.005, 'name': 'Новичок'},      # 0.5%
    {'min': 10000, 'max': 20000, 'rate': 0.01, 'name': 'Лояльный'},  # 1%
    {'min': 20000, 'max': 30000, 'rate': 0.02, 'name': 'Постоянный'}, # 2%
    {'min': 30000, 'max': 40000, 'rate': 0.03, 'name': 'Премиум'},    # 3%
    {'min': 40000, 'max': 50000, 'rate': 0.05, 'name': 'VIP'},        # 5%
    {'min': 50000, 'max': float('inf'), 'rate': 0.05, 'name': 'Элита'} # 5%
]

# Telegram Bot API секрет для проверки подписи
BOT_TOKEN = Config.TELEGRAM_BOT_TOKEN
API_SECRET_KEY = os.environ.get('API_SECRET_KEY', 'your-secret-api-key-here')

# Декоратор для проверки API ключа
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != API_SECRET_KEY:
            return jsonify({'success': False, 'error': 'Invalid API key'}), 401
        
        # Проверяем, что запрос от админа
        admin_id = request.headers.get('X-Telegram-User-ID')
        if not admin_id or int(admin_id) != Config.ADMIN_USER_ID:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

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
            db.execute_query(cursor, 'SELECT telegram_id, first_name, username, photo_url FROM users WHERE id = ?', (user_id,))
            user = db.fetchone(cursor)
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

def get_or_create_user(telegram_user_data, referral_code=None):
    """Получить или создать пользователя в базе данных с реферальной системой"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь
        db.execute_query(cursor, 'SELECT id, balance, is_verified, referral_code FROM users WHERE telegram_id = ?', (telegram_user_data['id'],))
        user = db.fetchone(cursor)
        
        if user:
            user_id = user[0]
            balance = user[1]
            is_verified = bool(user[2])
            # Обновляем данные пользователя
            db.execute_query(cursor, '''
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
            # Генерируем реферальный код
            ref_code = f"ref_{telegram_user_data['id']}_{uuid.uuid4().hex[:8]}"
            
            # Определяем, кто пригласил
            invited_by = None
            if referral_code:
                db.execute_query(cursor, 'SELECT id FROM users WHERE referral_code = ?', (referral_code,))
                referrer = db.fetchone(cursor)
                if referrer:
                    invited_by = referrer[0]
            
            # Создаем нового пользователя
            db.execute_query(cursor, '''
                INSERT INTO users (telegram_id, username, first_name, photo_url, balance, 
                                 is_verified, referral_code, invited_by, total_spent, total_orders)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                telegram_user_data['id'],
                telegram_user_data.get('username'),
                telegram_user_data.get('first_name', 'Пользователь'),
                telegram_user_data.get('photo_url', '/static/images/default-avatar.png'),
                0.0,
                0,  # Не верифицирован по умолчанию
                ref_code,
                invited_by,
                0.0,
                0
            ))
            user_id = db.lastrowid(cursor)
            balance = 0.0
            is_verified = False
            
            # Начисляем бонус пригласившему
            if invited_by:
                db.execute_query(cursor, '''
                    UPDATE users 
                    SET balance = balance + 100, total_invited = total_invited + 1 
                    WHERE id = ?
                ''', (invited_by,))
                
                # Записываем транзакцию
                db.execute_query(cursor, '''
                    INSERT INTO referral_bonuses (referrer_id, referred_id, amount)
                    VALUES (?, ?, ?)
                ''', (invited_by, user_id, 100.0))
        
        conn.commit()
        conn.close()
        
        return {
            'id': user_id,
            'telegram_id': telegram_user_data['id'],
            'first_name': telegram_user_data.get('first_name', 'Пользователь'),
            'username': telegram_user_data.get('username'),
            'photo_url': telegram_user_data.get('photo_url', '/static/images/default-avatar.png'),
            'balance': balance,
            'is_verified': is_verified,
            'referral_code': ref_code if not user else user[3]
        }
        
    except Exception as e:
        print(f"Ошибка при получении/создании пользователя: {e}")
        raise

def calculate_loyalty_cashback(user_id, order_amount):
    """Рассчитывает кешбек по системе лояльности"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Получаем общую сумму покупок пользователя
        db.execute_query(cursor, '''
            SELECT COALESCE(SUM(total_amount), 0) 
            FROM orders 
            WHERE user_id = ? AND status = 'completed'
        ''', (user_id,))
        
        total_spent = db.fetchone(cursor)[0]
        total_spent_with_new = total_spent + order_amount
        
        # Находим подходящий уровень лояльности
        cashback_rate = 0.005  # Минимальный по умолчанию
        level_name = "Новичок"
        
        for level in LOYALTY_LEVELS:
            if total_spent_with_new >= level['min'] and total_spent_with_new < level['max']:
                cashback_rate = level['rate']
                level_name = level['name']
                break
        
        cashback_amount = order_amount * cashback_rate
        
        conn.close()
        
        return {
            'rate': cashback_rate,
            'amount': cashback_amount,
            'level': level_name,
            'total_spent': total_spent_with_new
        }
        
    except Exception as e:
        print(f"Ошибка расчета лояльности: {e}")
        return {'rate': 0.005, 'amount': order_amount * 0.005, 'level': 'Новичок', 'total_spent': 0}

def process_and_save_image(image_data, filename, product_name):
    """Обработка и сохранение изображения товара"""
    try:
        # Создаем уникальное имя файла
        file_ext = os.path.splitext(filename)[1] if '.' in filename else '.jpg'
        unique_filename = f"{uuid.uuid4().hex}{file_ext}"
        
        os.makedirs('static/images/products/original', exist_ok=True)
        os.makedirs('static/images/products/catalog', exist_ok=True)
        os.makedirs('static/images/products/product', exist_ok=True)
        os.makedirs('static/images/products/cart', exist_ok=True)
        
        # Сохраняем оригинальный файл во временное место
        temp_path = os.path.join(tempfile.gettempdir(), unique_filename)
        with open(temp_path, 'wb') as f:
            f.write(image_data)
        
        # Открываем изображение
        image = Image.open(temp_path)
        
        # Сохраняем оригинал
        original_path = f'static/images/products/original/{unique_filename}'
        image.save(original_path, 'JPEG', quality=85)
        
        # Создаем уменьшенные версии
        for size_name, (width, height) in IMAGE_SIZES.items():
            resized_image = image.copy()
            resized_image.thumbnail((width, height), Image.Resampling.LANCZOS)
            
            size_path = f'static/images/products/{size_name}/{unique_filename}'
            resized_image.save(size_path, 'JPEG', quality=90)
        
        # Удаляем временный файл
        os.remove(temp_path)
        
        return f'/static/images/products/catalog/{unique_filename}'
        
    except Exception as e:
        print(f"Ошибка обработки изображения: {e}")
        import traceback
        traceback.print_exc()
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
            'cart': f'/static/images/products/cart/{filename}' if os.path.exists(cart_path) else '/static/images/default-avatar.png'
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
    
    # Логируем API запросы
    if request.path.startswith('/api/admin/'):
        app.logger.info(f"Admin API request: {request.method} {request.path}")
    
    # Проверяем, является ли запрос из Telegram Web App
    is_telegram = request.headers.get('X-Telegram-Init-Data') or request.args.get('tgWebAppData')
    if is_telegram:
        app.logger.info(f"Запрос из Telegram Web App: {request.path}")

@app.after_request
def after_request(response):
    """Действия после каждого запроса"""
    # Добавляем заголовки CORS
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Telegram-Init-Data, X-API-Key, X-Telegram-User-ID')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, DELETE, PUT')
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
    db.execute_query(cursor, '''
        SELECT id, name, display_name, icon, sort_order
        FROM sections 
        WHERE is_active = 1
        ORDER BY sort_order
    ''')
    sections_data = db.fetchall(cursor)
    
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
        db.execute_query(cursor, 'SELECT id FROM sections WHERE name = ?', (section,))
        section_row = db.fetchone(cursor)
        if section_row:
            section_id = section_row[0]
            # Получаем категории в этом разделе
            db.execute_query(cursor, 'SELECT name FROM categories WHERE section_id = ?', (section_id,))
            section_categories = [row[0] for row in db.fetchall(cursor)]
            
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
    
    db.execute_query(cursor, query, params)
    products_data = db.fetchall(cursor)
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
    
    db.execute_query(cursor, 'SELECT * FROM products WHERE id = ? AND is_active = 1', (product_id,))
    product_data = db.fetchone(cursor)
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

# ============================================
# API для лидерборда
# ============================================

@app.route('/api/leaderboard')
def api_leaderboard():
    """Получение лидерборда (топ 10 пользователей)"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT 
                u.id,
                u.telegram_id,
                u.first_name,
                u.username,
                u.photo_url,
                u.total_spent,
                u.total_orders,
                u.total_invited,
                u.balance,
                u.is_verified,
                ROW_NUMBER() OVER (ORDER BY u.total_spent DESC) as rank
            FROM users u
            WHERE u.total_spent > 0
            ORDER BY u.total_spent DESC
            LIMIT 10
        ''')
        
        leaders_data = db.fetchall(cursor)
        conn.close()
        
        leaders_list = []
        for leader in leaders_data:
            leaders_list.append({
                'rank': leader[10],
                'id': leader[0],
                'telegram_id': leader[1],
                'first_name': leader[2],
                'username': leader[3],
                'photo_url': leader[4] or '/static/images/default-avatar.png',
                'total_spent': leader[5],
                'total_orders': leader[6],
                'total_invited': leader[7],
                'balance': leader[8],
                'is_verified': bool(leader[9])
            })
        
        return jsonify(leaders_list)
        
    except Exception as e:
        print(f"Ошибка получения лидерборда: {e}")
        return jsonify([])

# ============================================
# API для верификации
# ============================================

@app.route('/api/admin/verify-user', methods=['POST'])
@require_api_key
def api_admin_verify_user():
    """Верификация пользователя администратором"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        username = data.get('username')
        action = data.get('action', 'verify')  # 'verify' или 'unverify'
        
        if not (user_id or username):
            return jsonify({'success': False, 'error': 'Не указан ID или username пользователя'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Ищем пользователя
        if user_id:
            db.execute_query(cursor, 'SELECT id FROM users WHERE telegram_id = ?', (user_id,))
        else:
            db.execute_query(cursor, 'SELECT id FROM users WHERE username = ?', (username,))
        
        user = db.fetchone(cursor)
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        user_db_id = user[0]
        
        # Выполняем действие
        is_verified = 1 if action == 'verify' else 0
        
        db.execute_query(cursor, 'UPDATE users SET is_verified = ? WHERE id = ?', (is_verified, user_db_id))
        
        conn.commit()
        conn.close()
        
        action_text = "верифицирован" if action == 'verify' else "деверифицирован"
        
        return jsonify({
            'success': True,
            'message': f'Пользователь успешно {action_text}'
        })
        
    except Exception as e:
        print(f"Ошибка верификации пользователя: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/check-verification', methods=['POST'])
@require_api_key
def api_admin_check_verification():
    """Проверка статуса верификации пользователя"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        username = data.get('username')
        
        if not (user_id or username):
            return jsonify({'success': False, 'error': 'Не указан ID или username пользователя'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Ищем пользователя
        if user_id:
            db.execute_query(cursor, 'SELECT id, first_name, username, is_verified FROM users WHERE telegram_id = ?', (user_id,))
        else:
            db.execute_query(cursor, 'SELECT id, first_name, username, is_verified FROM users WHERE username = ?', (username,))
        
        user = db.fetchone(cursor)
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        return jsonify({
            'success': True,
            'user': {
                'id': user[0],
                'first_name': user[1],
                'username': user[2],
                'is_verified': bool(user[3])
            }
        })
        
    except Exception as e:
        print(f"Ошибка проверки верификации: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API эндпоинты для админ-бота
# ============================================

@app.route('/api/admin/sections/check', methods=['POST'])
@require_api_key
def api_admin_sections_check():
    """Проверка существования раздела"""
    try:
        data = request.get_json()
        name = data.get('name')
        
        if not name:
            return jsonify({'success': False, 'error': 'Не указано имя раздела'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, 'SELECT id FROM sections WHERE name = ?', (name,))
        existing = db.fetchone(cursor)
        conn.close()
        
        if existing:
            return jsonify({'success': False, 'error': 'Раздел с таким ID уже существует'})
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Ошибка проверки раздела: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/sections/add', methods=['POST'])
@require_api_key
def api_admin_sections_add():
    """Добавление нового раздела"""
    try:
        data = request.get_json()
        
        required_fields = ['name', 'display_name', 'icon', 'sort_order']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Не указано поле: {field}'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем, существует ли раздел
        db.execute_query(cursor, 'SELECT id FROM sections WHERE name = ?', (data['name'],))
        existing = db.fetchone(cursor)
        
        if existing:
            conn.close()
            return jsonify({'success': False, 'error': 'Раздел с таким ID уже существует'})
        
        # Добавляем раздел
        db.execute_query(cursor, '''
            INSERT INTO sections (name, display_name, icon, sort_order)
            VALUES (?, ?, ?, ?)
        ''', (data['name'], data['display_name'], data['icon'], data['sort_order']))
        
        section_id = db.lastrowid(cursor)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'section_id': section_id,
            'message': 'Раздел успешно добавлен'
        })
        
    except Exception as e:
        print(f"Ошибка добавления раздела: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/sections/list', methods=['GET'])
@require_api_key
def api_admin_sections_list():
    """Получение списка всех разделов"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT s.id, s.name, s.display_name, s.icon, s.sort_order, s.is_active,
                   COUNT(c.id) as category_count
            FROM sections s
            LEFT JOIN categories c ON s.id = c.section_id AND c.is_active = 1
            GROUP BY s.id
            ORDER BY s.sort_order
        ''')
        
        sections_data = db.fetchall(cursor)
        conn.close()
        
        sections_list = []
        for section in sections_data:
            sections_list.append({
                'id': section[0],
                'name': section[1],
                'display_name': section[2],
                'icon': section[3],
                'sort_order': section[4],
                'is_active': bool(section[5]),
                'category_count': section[6]
            })
        
        return jsonify({'success': True, 'sections': sections_list})
        
    except Exception as e:
        print(f"Ошибка получения списка разделов: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/sections/<int:section_id>', methods=['GET'])
@require_api_key
def api_admin_sections_get(section_id):
    """Получение информации о разделе"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT s.id, s.name, s.display_name, s.icon, s.sort_order, s.is_active,
                   COUNT(c.id) as category_count
            FROM sections s
            LEFT JOIN categories c ON s.id = c.section_id AND c.is_active = 1
            WHERE s.id = ?
            GROUP BY s.id
        ''', (section_id,))
        
        section_data = db.fetchone(cursor)
        conn.close()
        
        if not section_data:
            return jsonify({'success': False, 'error': 'Раздел не найден'}), 404
        
        section = {
            'id': section_data[0],
            'name': section_data[1],
            'display_name': section_data[2],
            'icon': section_data[3],
            'sort_order': section_data[4],
            'is_active': bool(section_data[5]),
            'category_count': section_data[6]
        }
        
        return jsonify({'success': True, 'section': section})
        
    except Exception as e:
        print(f"Ошибка получения раздела: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/sections/<int:section_id>/delete', methods=['POST'])
@require_api_key
def api_admin_sections_delete(section_id):
    """Удаление раздела (деактивация)"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование раздела
        db.execute_query(cursor, 'SELECT name FROM sections WHERE id = ?', (section_id,))
        section = db.fetchone(cursor)
        
        if not section:
            conn.close()
            return jsonify({'success': False, 'error': 'Раздел не найден'}), 404
        
        # Деактивируем раздел
        db.execute_query(cursor, 'UPDATE sections SET is_active = 0 WHERE id = ?', (section_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Раздел успешно удален'})
        
    except Exception as e:
        print(f"Ошибка удаления раздела: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/sections/<int:section_id>/update', methods=['POST'])
@require_api_key
def api_admin_sections_update(section_id):
    """Обновление поля раздела"""
    try:
        data = request.get_json()
        field = data.get('field')
        value = data.get('value')
        
        if not field or value is None:
            return jsonify({'success': False, 'error': 'Не указано поле или значение'})
        
        # Проверяем допустимые поля
        allowed_fields = ['display_name', 'icon', 'sort_order']
        if field not in allowed_fields:
            return jsonify({'success': False, 'error': f'Недопустимое поле: {field}'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование раздела
        db.execute_query(cursor, 'SELECT id FROM sections WHERE id = ?', (section_id,))
        section = db.fetchone(cursor)
        
        if not section:
            conn.close()
            return jsonify({'success': False, 'error': 'Раздел не найден'}), 404
        
        # Обновляем поле
        if field == 'sort_order':
            value = int(value)
        
        query = f'UPDATE sections SET {field} = ? WHERE id = ?'
        db.execute_query(cursor, query, (value, section_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Раздел успешно обновлен'})
        
    except Exception as e:
        print(f"Ошибка обновления раздела: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API для категорий
# ============================================

@app.route('/api/admin/categories/check', methods=['POST'])
@require_api_key
def api_admin_categories_check():
    """Проверка существования категории"""
    try:
        data = request.get_json()
        name = data.get('name')
        
        if not name:
            return jsonify({'success': False, 'error': 'Не указано имя категории'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, 'SELECT id FROM categories WHERE name = ?', (name,))
        existing = db.fetchone(cursor)
        conn.close()
        
        if existing:
            return jsonify({'success': False, 'error': 'Категория с таким ID уже существует'})
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Ошибка проверки категории: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/categories/exists', methods=['POST'])
@require_api_key
def api_admin_categories_exists():
    """Проверка существования и активности категории"""
    try:
        data = request.get_json()
        name = data.get('name')
        
        if not name:
            return jsonify({'success': False, 'error': 'Не указано имя категории'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование И активность категории
        db.execute_query(cursor, 'SELECT id, is_active FROM categories WHERE name = ?', (name,))
        existing = db.fetchone(cursor)
        conn.close()
        
        if not existing:
            return jsonify({'success': False, 'exists': False, 'error': 'Категория не найдена'})
        
        is_active = bool(existing[1])
        if not is_active:
            return jsonify({'success': False, 'exists': True, 'is_active': False, 'error': 'Категория неактивна'})
        
        return jsonify({'success': True, 'exists': True, 'is_active': True})
        
    except Exception as e:
        print(f"Ошибка проверки существования категории: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/categories/add', methods=['POST'])
@require_api_key
def api_admin_categories_add():
    """Добавление новой категории"""
    try:
        data = request.get_json()
        
        required_fields = ['name', 'display_name', 'icon', 'sort_order']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Не указано поле: {field}'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем, существует ли категория
        db.execute_query(cursor, 'SELECT id FROM categories WHERE name = ?', (data['name'],))
        existing = db.fetchone(cursor)
        
        if existing:
            conn.close()
            return jsonify({'success': False, 'error': 'Категория с таким ID уже существует'})
        
        # Проверяем раздел, если указан
        section_id = data.get('section_id')
        if section_id:
            db.execute_query(cursor, 'SELECT id FROM sections WHERE id = ? AND is_active = 1', (section_id,))
            section = db.fetchone(cursor)
            if not section:
                conn.close()
                return jsonify({'success': False, 'error': 'Раздел не найден или неактивен'})
        
        # Добавляем категорию
        db.execute_query(cursor, '''
            INSERT INTO categories (name, display_name, icon, section_id, sort_order, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (data['name'], data['display_name'], data['icon'], section_id, data['sort_order']))
        
        category_id = db.lastrowid(cursor)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'category_id': category_id,
            'message': 'Категория успешно добавлена'
        })
        
    except Exception as e:
        print(f"Ошибка добавления категории: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/categories/list', methods=['GET'])
@require_api_key
def api_admin_categories_list():
    """Получение списка всех категорий"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT c.id, c.name, c.display_name, c.icon, c.sort_order, c.is_active,
                   c.section_id, s.display_name as section_name,
                   COUNT(p.id) as product_count
            FROM categories c
            LEFT JOIN sections s ON c.section_id = s.id
            LEFT JOIN products p ON c.name = p.category AND p.is_active = 1
            GROUP BY c.id
            ORDER BY c.sort_order
        ''')
        
        categories_data = db.fetchall(cursor)
        conn.close()
        
        categories_list = []
        for category in categories_data:
            categories_list.append({
                'id': category[0],
                'name': category[1],
                'display_name': category[2],
                'icon': category[3],
                'sort_order': category[4],
                'is_active': bool(category[5]),
                'section_id': category[6],
                'section_name': category[7],
                'product_count': category[8]
            })
        
        return jsonify({'success': True, 'categories': categories_list})
        
    except Exception as e:
        print(f"Ошибка получения списка категорий: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/categories/<int:category_id>', methods=['GET'])
@require_api_key
def api_admin_categories_get(category_id):
    """Получение информации о категории"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT c.id, c.name, c.display_name, c.icon, c.sort_order, c.is_active,
                   c.section_id, s.display_name as section_name,
                   COUNT(p.id) as product_count
            FROM categories c
            LEFT JOIN sections s ON c.section_id = s.id
            LEFT JOIN products p ON c.name = p.category AND p.is_active = 1
            WHERE c.id = ?
            GROUP BY c.id
        ''', (category_id,))
        
        category_data = db.fetchone(cursor)
        conn.close()
        
        if not category_data:
            return jsonify({'success': False, 'error': 'Категория не найден'}), 404
        
        category = {
            'id': category_data[0],
            'name': category_data[1],
            'display_name': category_data[2],
            'icon': category_data[3],
            'sort_order': category_data[4],
            'is_active': bool(category_data[5]),
            'section_id': category_data[6],
            'section_name': category_data[7],
            'product_count': category_data[8]
        }
        
        return jsonify({'success': True, 'category': category})
        
    except Exception as e:
        print(f"Ошибка получения категории: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/categories/<int:category_id>/delete', methods=['POST'])
@require_api_key
def api_admin_categories_delete(category_id):
    """Удаление категории (деактивация)"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование категории
        db.execute_query(cursor, 'SELECT name FROM categories WHERE id = ?', (category_id,))
        category = db.fetchone(cursor)
        
        if not category:
            conn.close()
            return jsonify({'success': False, 'error': 'Категория не найдена'}), 404
        
        # Деактивируем категорию
        db.execute_query(cursor, 'UPDATE categories SET is_active = 0 WHERE id = ?', (category_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Категория успешно удалена'})
        
    except Exception as e:
        print(f"Ошибка удаления категории: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/categories/<int:category_id>/update', methods=['POST'])
@require_api_key
def api_admin_categories_update(category_id):
    """Обновление поля категории"""
    try:
        data = request.get_json()
        field = data.get('field')
        value = data.get('value')
        
        if not field:
            return jsonify({'success': False, 'error': 'Не указано поле'})
        
        # Проверяем допустимые поля
        allowed_fields = ['display_name', 'icon', 'sort_order', 'section_id']
        if field not in allowed_fields:
            return jsonify({'success': False, 'error': f'Недопустимое поле: {field}'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование категории
        db.execute_query(cursor, 'SELECT id FROM categories WHERE id = ?', (category_id,))
        category = db.fetchone(cursor)
        
        if not category:
            conn.close()
            return jsonify({'success': False, 'error': 'Категория не найдена'}), 404
        
        # Если обновляем section_id, проверяем существование раздела
        if field == 'section_id' and value:
            db.execute_query(cursor, 'SELECT id FROM sections WHERE id = ?', (value,))
            section = db.fetchone(cursor)
            if not section:
                conn.close()
                return jsonify({'success': False, 'error': 'Раздел не найден'})
        
        # Преобразуем значение для sort_order
        if field == 'sort_order' and value is not None:
            try:
                value = int(value)
            except ValueError:
                conn.close()
                return jsonify({'success': False, 'error': 'sort_order должен быть числом'})
        
        # Для section_id разрешаем NULL
        if field == 'section_id' and (value is None or value == ''):
            query = f'UPDATE categories SET section_id = NULL WHERE id = ?'
            db.execute_query(cursor, query, (category_id,))
        else:
            query = f'UPDATE categories SET {field} = ? WHERE id = ?'
            db.execute_query(cursor, query, (value, category_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Категория успешно обновлена'})
        
    except Exception as e:
        print(f"Ошибка обновления категории: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API для товаров
# ============================================

@app.route('/api/admin/products/add', methods=['POST'])
@require_api_key
def api_admin_products_add():
    """Добавление нового товара с изображением"""
    try:
        # Проверяем, есть ли файл изображения
        image_file = request.files.get('image')
        
        # Получаем данные формы
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        category = request.form.get('category')
        specifications = request.form.get('specifications')
        
        # Проверяем обязательные поля
        if not name:
            return jsonify({'success': False, 'error': 'Не указано название товара'})
        if not price:
            return jsonify({'success': False, 'error': 'Не указана цена товара'})
        if not category:
            return jsonify({'success': False, 'error': 'Не указана категория товара'})
        
        try:
            price = float(price)
            if price <= 0:
                return jsonify({'success': False, 'error': 'Цена должна быть больше 0'})
        except ValueError:
            return jsonify({'success': False, 'error': 'Неверный формат цены'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем категорию
        db.execute_query(cursor, 'SELECT name FROM categories WHERE name = ? AND is_active = 1', (category,))
        category_check = db.fetchone(cursor)
        
        if not category_check:
            conn.close()
            return jsonify({'success': False, 'error': f'Категория "{category}" не найдена или неактивна'})
        
        # Обрабатываем изображение
        image_path = '/static/images/default-product.png'
        if image_file and image_file.filename:
            try:
                image_data = image_file.read()
                filename = image_file.filename
                image_path = process_and_save_image(image_data, filename, name)
            except Exception as e:
                print(f"Ошибка обработки изображения: {e}")
                # Используем изображение по умолчанию
        
        # Добавляем товар
        db.execute_query(cursor, '''
            INSERT INTO products (name, description, price, image_path, category, specifications, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (name, description, price, image_path, category, specifications))
        
        product_id = db.lastrowid(cursor)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'product_id': product_id,
            'message': 'Товар успешно добавлен'
        })
        
    except Exception as e:
        print(f"Ошибка добавления товара: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/products/list', methods=['GET'])
@require_api_key
def api_admin_products_list():
    """Получение списка всех товаров"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT p.id, p.name, p.description, p.price, p.image_path, 
                   p.category, p.is_active, p.created_at,
                   c.display_name as category_display_name
            FROM products p
            LEFT JOIN categories c ON p.category = c.name
            ORDER BY p.created_at DESC
        ''')
        
        products_data = db.fetchall(cursor)
        conn.close()
        
        products_list = []
        for product in products_data:
            products_list.append({
                'id': product[0],
                'name': product[1],
                'description': product[2],
                'price': product[3],
                'image_path': product[4],
                'category': product[5],
                'is_active': bool(product[6]),
                'created_at': product[7],
                'category_display_name': product[8] or product[5]
            })
        
        return jsonify({'success': True, 'products': products_list})
        
    except Exception as e:
        print(f"Ошибка получения списка товаров: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/products/<int:product_id>', methods=['GET'])
@require_api_key
def api_admin_products_get(product_id):
    """Получение информации о товаре"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT p.id, p.name, p.description, p.price, p.image_path, 
                   p.category, p.is_active, p.specifications,
                   c.display_name as category_display_name
            FROM products p
            LEFT JOIN categories c ON p.category = c.name
            WHERE p.id = ?
        ''', (product_id,))
        
        product_data = db.fetchone(cursor)
        conn.close()
        
        if not product_data:
            return jsonify({'success': False, 'error': 'Товар не найден'}), 404
        
        product = {
            'id': product_data[0],
            'name': product_data[1],
            'description': product_data[2],
            'price': product_data[3],
            'image_path': product_data[4],
            'category': product_data[5],
            'is_active': bool(product_data[6]),
            'specifications': product_data[7],
            'category_display_name': product_data[8] or product_data[5]
        }
        
        return jsonify({'success': True, 'product': product})
        
    except Exception as e:
        print(f"Ошибка получения товара: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/products/<int:product_id>/delete', methods=['POST'])
@require_api_key
def api_admin_products_delete(product_id):
    """Удаление товара (деактивация)"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование товара
        db.execute_query(cursor, 'SELECT name FROM products WHERE id = ?', (product_id,))
        product = db.fetchone(cursor)
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'error': 'Товар не найден'}), 404
        
        # Деактивируем товар
        db.execute_query(cursor, 'UPDATE products SET is_active = 0 WHERE id = ?', (product_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Товар успешно удален'})
        
    except Exception as e:
        print(f"Ошибка удаления товара: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API для городов
# ============================================

@app.route('/api/admin/cities/add', methods=['POST'])
@require_api_key
def api_admin_cities_add():
    """Добавление нового города"""
    try:
        data = request.get_json()
        city_name = data.get('name')
        
        if not city_name:
            return jsonify({'success': False, 'error': 'Не указано название города'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем, существует ли город
        db.execute_query(cursor, 'SELECT DISTINCT city FROM pickup_locations WHERE city = ?', (city_name,))
        existing = db.fetchone(cursor)
        
        if existing:
            conn.close()
            return jsonify({'success': False, 'error': f'Город "{city_name}" уже существует'})
        
        # Создаем пункты выдачи по умолчанию для нового города
        # Пункт самовывоза
        db.execute_query(cursor, '''
            INSERT INTO pickup_locations (name, address, city, location_type, delivery_price, is_active)
            VALUES (?, ?, ?, 'pickup', 0, 1)
        ''', ('Пункт выдачи', 'Укажите адрес', city_name))
        
        # Пункт доставки
        db.execute_query(cursor, '''
            INSERT INTO pickup_locations (name, address, city, location_type, delivery_price, is_active)
            VALUES (?, ?, ?, 'delivery', 300, 1)
        ''', ('Доставка по городу', 'Доставка курьером', city_name))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Город "{city_name}" успешно добавлен'
        })
        
    except Exception as e:
        print(f"Ошибка добавления города: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/cities/list', methods=['GET'])
@require_api_key
def api_admin_cities_list():
    """Получение списка всех городов"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT DISTINCT city 
            FROM pickup_locations 
            WHERE city IS NOT NULL AND is_active = 1
            ORDER BY city
        ''')
        
        cities_data = db.fetchall(cursor)
        
        # Получаем статистику по каждому городу
        cities_info = {}
        for city_tuple in cities_data:
            city = city_tuple[0]
            
            # Количество пунктов самовывоза
            db.execute_query(cursor, '''
                SELECT COUNT(*) FROM pickup_locations 
                WHERE city = ? AND location_type = 'pickup' AND is_active = 1
            ''', (city,))
            pickup_count = db.fetchone(cursor)[0]
            
            # Количество пунктов доставки
            db.execute_query(cursor, '''
                SELECT COUNT(*) FROM pickup_locations 
                WHERE city = ? AND location_type = 'delivery' AND is_active = 1
            ''', (city,))
            delivery_count = db.fetchone(cursor)[0]
            
            cities_info[city] = {
                'pickup': pickup_count,
                'delivery': delivery_count
            }
        
        conn.close()
        
        cities = [city[0] for city in cities_data]
        
        return jsonify({
            'success': True, 
            'cities': cities,
            'cities_info': cities_info
        })
        
    except Exception as e:
        print(f"Ошибка получения списка городов: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/cities/<city_name>/info', methods=['GET'])
@require_api_key
def api_admin_cities_info(city_name):
    """Получение информации о городе"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование города
        db.execute_query(cursor, 'SELECT DISTINCT city FROM pickup_locations WHERE city = ?', (city_name,))
        city_check = db.fetchone(cursor)
        
        if not city_check:
            conn.close()
            return jsonify({'success': False, 'error': 'Город не найден'}), 404
        
        # Количество пунктов в городе
        db.execute_query(cursor, 'SELECT COUNT(*) FROM pickup_locations WHERE city = ? AND is_active = 1', (city_name,))
        location_count = db.fetchone(cursor)[0]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'city': city_name,
            'location_count': location_count
        })
        
    except Exception as e:
        print(f"Ошибка получения информации о городе: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/cities/<city_name>/check', methods=['GET'])
@require_api_key
def api_admin_cities_check(city_name):
    """Проверка существования города"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, 'SELECT DISTINCT city FROM pickup_locations WHERE city = ?', (city_name,))
        city_check = db.fetchone(cursor)
        conn.close()
        
        if not city_check:
            return jsonify({'success': False, 'error': 'Город не найден'})
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Ошибка проверки города: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/cities/<city_name>/delete', methods=['POST'])
@require_api_key
def api_admin_cities_delete(city_name):
    """Удаление города и всех связанных пунктов"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование города
        db.execute_query(cursor, 'SELECT DISTINCT city FROM pickup_locations WHERE city = ?', (city_name,))
        city_check = db.fetchone(cursor)
        
        if not city_check:
            conn.close()
            return jsonify({'success': False, 'error': 'Город не найден'}), 404
        
        # Удаляем все пункты в этом городе
        db.execute_query(cursor, 'DELETE FROM pickup_locations WHERE city = ?', (city_name,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Город "{city_name}" и все связанные пункты успешно удалены'
        })
        
    except Exception as e:
        print(f"Ошибка удаления города: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API для пунктов выдачи
# ============================================

@app.route('/api/admin/locations/add', methods=['POST'])
@require_api_key
def api_admin_locations_add():
    """Добавление нового пункта выдачи"""
    try:
        data = request.get_json()
        
        required_fields = ['name', 'address', 'city', 'location_type']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Не указано поле: {field}'})
        
        # Проверяем тип пункта
        if data['location_type'] not in ['pickup', 'delivery']:
            return jsonify({'success': False, 'error': 'Недопустимый тип пункта'})
        
        # Устанавливаем цену доставки
        delivery_price = data.get('delivery_price', 0)
        if data['location_type'] == 'pickup':
            delivery_price = 0
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Добавляем пункт
        db.execute_query(cursor, '''
            INSERT INTO pickup_locations (name, address, city, location_type, delivery_price, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (data['name'], data['address'], data['city'], data['location_type'], delivery_price))
        
        location_id = db.lastrowid(cursor)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'location_id': location_id,
            'message': 'Пункт выдачи успешно добавлен'
        })
        
    except Exception as e:
        print(f"Ошибка добавления пункта выдачи: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/locations/list', methods=['GET'])
@require_api_key
def api_admin_locations_list():
    """Получение списка всех пунктов выдачи"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT id, name, address, city, location_type, delivery_price, is_active
            FROM pickup_locations
            ORDER BY city, location_type
        ''')
        
        locations_data = db.fetchall(cursor)
        conn.close()
        
        locations_list = []
        for location in locations_data:
            locations_list.append({
                'id': location[0],
                'name': location[1],
                'address': location[2],
                'city': location[3],
                'location_type': location[4],
                'delivery_price': location[5],
                'is_active': bool(location[6])
            })
        
        return jsonify({'success': True, 'locations': locations_list})
        
    except Exception as e:
        print(f"Ошибка получения списка пунктов выдачи: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/locations/<int:location_id>', methods=['GET'])
@require_api_key
def api_admin_locations_get(location_id):
    """Получение информации о пункте выдачи"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
            SELECT id, name, address, city, location_type, delivery_price, is_active
            FROM pickup_locations
            WHERE id = ?
        ''', (location_id,))
        
        location_data = db.fetchone(cursor)
        conn.close()
        
        if not location_data:
            return jsonify({'success': False, 'error': 'Пункт выдачи не найден'}), 404
        
        location = {
            'id': location_data[0],
            'name': location_data[1],
            'address': location_data[2],
            'city': location_data[3],
            'location_type': location_data[4],
            'delivery_price': location_data[5],
            'is_active': bool(location_data[6])
        }
        
        return jsonify({'success': True, 'location': location})
        
    except Exception as e:
        print(f"Ошибка получения пункта выдачи: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/locations/<int:location_id>/delete', methods=['POST'])
@require_api_key
def api_admin_locations_delete(location_id):
    """Удаление пункта выдачи (деактивация)"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование пункта
        db.execute_query(cursor, 'SELECT name FROM pickup_locations WHERE id = ?', (location_id,))
        location = db.fetchone(cursor)
        
        if not location:
            conn.close()
            return jsonify({'success': False, 'error': 'Пункт выдачи не найден'}), 404
        
        # Деактивируем пункт
        db.execute_query(cursor, 'UPDATE pickup_locations SET is_active = 0 WHERE id = ?', (location_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Пункт выдачи успешно удален'})
        
    except Exception as e:
        print(f"Ошибка удаления пункта выдачи: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/locations/<int:location_id>/update', methods=['POST'])
@require_api_key
def api_admin_locations_update(location_id):
    """Обновление поля пункта выдачи"""
    try:
        data = request.get_json()
        field = data.get('field')
        value = data.get('value')
        
        if not field or value is None:
            return jsonify({'success': False, 'error': 'Не указано поле или значение'})
        
        # Проверяем допустимые поля
        allowed_fields = ['name', 'address', 'city', 'delivery_price']
        if field not in allowed_fields:
            return jsonify({'success': False, 'error': f'Недопустимое поле: {field}'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Проверяем существование пункта
        db.execute_query(cursor, 'SELECT id FROM pickup_locations WHERE id = ?', (location_id,))
        location = db.fetchone(cursor)
        
        if not location:
            conn.close()
            return jsonify({'success': False, 'error': 'Пункт выдачи не найден'}), 404
        
        # Преобразуем значение для delivery_price
        if field == 'delivery_price':
            try:
                value = float(value)
            except ValueError:
                conn.close()
                return jsonify({'success': False, 'error': 'delivery_price должен быть числом'})
        
        # Обновляем поле
        query = f'UPDATE pickup_locations SET {field} = ? WHERE id = ?'
        db.execute_query(cursor, query, (value, location_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Пункт выдачи успешно обновлен'})
        
    except Exception as e:
        print(f"Ошибка обновления пункта выдачи: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API для статистики
# ============================================

@app.route('/api/admin/stats/profit', methods=['GET'])
@require_api_key
def api_admin_stats_profit():
    """Получение финансовой статистики"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Общая прибыль
        db.execute_query(cursor, '''
            SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status = 'completed'
        ''')
        total_profit = db.fetchone(cursor)[0]
        
        # Прибыль за сегодня
        if db.is_postgres:
            db.execute_query(cursor, '''
                SELECT COALESCE(SUM(total_amount), 0) FROM orders 
                WHERE status = 'completed' AND DATE(created_at) = CURRENT_DATE
            ''')
        else:
            db.execute_query(cursor, '''
                SELECT COALESCE(SUM(total_amount), 0) FROM orders 
                WHERE status = 'completed' AND DATE(created_at) = DATE('now')
            ''')
        today_profit = db.fetchone(cursor)[0]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'total_profit': float(total_profit),
            'today_profit': float(today_profit)
        })
        
    except Exception as e:
        print(f"Ошибка получения статистики: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# Остальные API эндпоинты (оригинальные)
# ============================================

@app.route('/api/init', methods=['POST'])
def api_init():
    """Инициализация приложения - получение данных пользователя"""
    try:
        data = request.get_json(silent=True) or {}
        init_data = data.get('initData')
        referral_code = data.get('referral_code')
        
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
        user = get_or_create_user(telegram_user_data, referral_code)
        
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
            'is_verified': user['is_verified'],
            'referral_code': user['referral_code'],
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
            'is_verified': False,
            'referral_code': None,
            'is_telegram': False
        }), 500

@app.route('/api/sections')
def api_sections():
    """Получение списка разделов"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        db.execute_query(cursor, '''
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
        
        sections_data = db.fetchall(cursor)
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
        
        db.execute_query(cursor, '''
            SELECT c.name, c.display_name, c.icon, s.display_name as section_name
            FROM categories c
            LEFT JOIN sections s ON c.section_id = s.id
            WHERE c.is_active = 1 
            ORDER BY c.sort_order
        ''')
        
        categories_data = db.fetchall(cursor)
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
            db.execute_query(cursor, '''
                SELECT c.name, c.display_name, c.icon
                FROM categories c
                WHERE c.is_active = 1
                ORDER BY c.sort_order
            ''')
        else:
            db.execute_query(cursor, '''
                SELECT c.name, c.display_name, c.icon
                FROM categories c
                JOIN sections s ON c.section_id = s.id
                WHERE s.name = ? AND c.is_active = 1
                ORDER BY c.sort_order
            ''', (section_name,))
        
        categories_data = db.fetchall(cursor)
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
        db.execute_query(cursor, '''
            SELECT s.id, s.name, s.display_name, s.icon
            FROM sections s
            WHERE s.is_active = 1
            ORDER BY s.sort_order
            LIMIT 3
        ''')
        
        sections_data = db.fetchall(cursor)
        
        result = {}
        
        for section in sections_data:
            section_id, section_name, display_name, icon = section
            
            # Получаем товары из этого раздела
            db.execute_query(cursor, '''
                SELECT p.id, p.name, p.description, p.price, p.image_path, p.category
                FROM products p
                JOIN categories c ON p.category = c.name
                WHERE c.section_id = ? AND p.is_active = 1
                ORDER BY p.created_at DESC
                LIMIT 6
            ''', (section_id,))
            
            products_data = db.fetchall(cursor)
            
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
            
            db.execute_query(cursor, '''
                SELECT p.id, p.name, p.description, p.price, p.image_path, p.category
                FROM products p
                WHERE p.is_active = 1
                ORDER BY p.created_at DESC
                LIMIT 6
            ''')
            
            products_data = db.fetchall(cursor)
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
        db.execute_query(cursor, 'SELECT id, name, price FROM products WHERE id = ? AND is_active = 1', (product_id,))
        product = db.fetchone(cursor)
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'error': 'Товар не найден'})
        
        # Проверяем, есть ли пользователь в базе
        db.execute_query(cursor, 'SELECT id, is_verified FROM users WHERE telegram_id = ?', (user_id,))
        user = db.fetchone(cursor)
        
        if not user:
            # Создаем пользователя если его нет
            db.execute_query(cursor, '''
                INSERT INTO users (telegram_id, first_name, username, photo_url, balance, is_verified, total_spent, total_orders)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_data['id'],
                user_data.get('first_name', 'Пользователь'),
                user_data.get('username'),
                user_data.get('photo_url', '/static/images/default-avatar.png'),
                0.0,
                0,
                0.0,
                0
            ))
            user_db_id = db.lastrowid(cursor)
            is_verified = False
        else:
            user_db_id = user[0]
            is_verified = bool(user[1])
        
        # Проверяем, есть ли товар уже в корзине
        db.execute_query(cursor, '''
            SELECT id, quantity FROM cart_items 
            WHERE user_id = ? AND product_id = ?
        ''', (user_db_id, product_id))
        
        existing_item = db.fetchone(cursor)
        
        if existing_item:
            # Увеличиваем количество
            db.execute_query(cursor, '''
                UPDATE cart_items SET quantity = quantity + 1 
                WHERE id = ?
            ''', (existing_item[0],))
        else:
            # Добавляем новый товар
            db.execute_query(cursor, '''
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
        db.execute_query(cursor, 'SELECT id FROM users WHERE telegram_id = ?', (user_id,))
        user = db.fetchone(cursor)
        
        if not user:
            conn.close()
            return jsonify({'items': [], 'total': 0})
        
        user_db_id = user[0]
        
        # Получаем товары в корзине
        db.execute_query(cursor, '''
            SELECT p.id, p.name, p.price, p.image_path, ci.quantity
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            WHERE ci.user_id = ? AND p.is_active = 1
            ORDER BY ci.created_at DESC
        ''', (user_db_id,))
        
        cart_items_data = db.fetchall(cursor)
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
        db.execute_query(cursor, 'SELECT id FROM users WHERE telegram_id = ?', (user_id,))
        user = db.fetchone(cursor)
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        user_db_id = user[0]
        
        if quantity == 0:
            # Удаляем товар из корзины
            db.execute_query(cursor, 'DELETE FROM cart_items WHERE user_id = ? AND product_id = ?', 
                          (user_db_id, product_id))
        else:
            # Обновляем количество
            db.execute_query(cursor, '''
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
        db.execute_query(cursor, 'SELECT id FROM users WHERE telegram_id = ?', (user_id,))
        user = db.fetchone(cursor)
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        user_db_id = user[0]
        
        db.execute_query(cursor, 'DELETE FROM cart_items WHERE user_id = ? AND product_id = ?', 
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
        
        db.execute_query(cursor, '''
            SELECT DISTINCT city 
            FROM pickup_locations 
            WHERE city IS NOT NULL AND is_active = 1
            ORDER BY city
        ''')
        
        cities_data = db.fetchall(cursor)
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
        
        db.execute_query(cursor, query, params)
        locations_data = db.fetchall(cursor)
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
        use_balance = data.get('use_balance', False)  # Оплата с баланса
        
        # Получаем данные пользователя
        user_data = get_telegram_user_data()
        user_id = user_data['id']
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Получаем ID пользователя в базе
        db.execute_query(cursor, 'SELECT id, is_verified, balance FROM users WHERE telegram_id = ?', (user_id,))
        user = db.fetchone(cursor)
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        user_db_id = user[0]
        is_verified = bool(user[1])
        user_balance = user[2]
        
        # Проверяем верификацию
        if not is_verified:
            conn.close()
            return jsonify({
                'success': False, 
                'error': 'Вы не верифицированы. Обратитесь к администратору в Telegram @Danil_623'
            }), 403
        
        # Получаем товары из корзины
        db.execute_query(cursor, '''
            SELECT p.id, p.price, ci.quantity
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            WHERE ci.user_id = ?
        ''', (user_db_id,))
        
        cart_items = db.fetchall(cursor)
        
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
                db.execute_query(cursor, 'SELECT name, address FROM pickup_locations WHERE id = ? AND location_type = "pickup"', 
                             (pickup_location_id,))
                location = db.fetchone(cursor)
                if location:
                    delivery_info = f"{location[0]} - {location[1]}"
            else:
                delivery_info = "Самовывоз"
                
        elif delivery_type == 'delivery':
            db.execute_query(cursor, 'SELECT delivery_price FROM pickup_locations WHERE city = ? AND location_type = "delivery" LIMIT 1', 
                         (delivery_city,))
            delivery_data = db.fetchone(cursor)
            
            if delivery_data:
                delivery_price = delivery_data[0]
                delivery_info = f"Доставка в {delivery_city} - {delivery_address}"
            else:
                conn.close()
                return jsonify({'success': False, 'error': 'Доставка в этот город недоступна'})
        
        # Рассчитываем итоговую сумму
        total_amount = items_total + delivery_price
        
        # Проверяем баланс, если оплата с баланса
        if use_balance:
            if user_balance < total_amount:
                conn.close()
                return jsonify({'success': False, 'error': 'Недостаточно средств на балансе'})
        
        # Рассчитываем кешбек по лояльности
        loyalty_data = calculate_loyalty_cashback(user_db_id, total_amount)
        cashback_earned = loyalty_data['amount']
        
        try:
            # Создаем заказ
            db.execute_query(cursor, '''
                INSERT INTO orders (user_id, total_amount, cashback_earned, customer_name, customer_phone, 
                                  pickup_location, delivery_type, delivery_city, delivery_address, delivery_price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''', (user_db_id, total_amount, cashback_earned, customer_name, customer_phone, 
                  delivery_info, delivery_type, delivery_city, delivery_address, delivery_price))
            
            order_id = db.lastrowid(cursor)
            
            # Если оплата с баланса, списываем средства
            if use_balance:
                db.execute_query(cursor, '''
                    UPDATE users SET balance = balance - ? 
                    WHERE id = ?
                ''', (total_amount, user_db_id))
            
            # Начисляем кешбек пользователю
            db.execute_query(cursor, '''
                UPDATE users SET balance = balance + ?, total_spent = total_spent + ?, total_orders = total_orders + 1 
                WHERE id = ?
            ''', (cashback_earned, total_amount, user_db_id))
            
            # Очищаем корзину
            db.execute_query(cursor, 'DELETE FROM cart_items WHERE user_id = ?', (user_db_id,))
            
            conn.commit()
            
            # Получаем username для уведомления
            db.execute_query(cursor, 'SELECT username FROM users WHERE id = ?', (user_db_id,))
            user_row = db.fetchone(cursor)
            username = user_row[0] if user_row else None
            
            # Отправляем уведомление администратору
            send_order_notification_to_admin(order_id, customer_name, customer_phone, username, total_amount, delivery_info, delivery_type)
            
            # Отправляем подтверждение пользователю
            send_order_confirmation_to_user(customer_phone, order_id, total_amount, cashback_earned, loyalty_data['level'])
            
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
            'loyalty_level': loyalty_data['level'],
            'loyalty_rate': loyalty_data['rate'] * 100,
            'message': f'Заказ #{order_id} успешно оформлен!'
        })
        
    except Exception as e:
        print(f"Ошибка создания заказа: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def send_order_notification_to_admin(order_id, customer_name, customer_phone, username, total_amount, delivery_info, delivery_type):
    """Отправка уведомления администратору в Telegram"""
    try:
        if not BOT_TOKEN or not Config.ADMIN_USER_ID:
            print("Нет данных для отправки уведомления администратору")
            return
        
        import requests
        
        delivery_type_text = "самовывоз" if delivery_type == 'pickup' else "доставка"
        username_text = f"@{username}" if username else "Нет username"
        
        message = f"🛒 *Новый заказ #{order_id}*\n\n" \
                 f"👤 *Клиент:* {customer_name}\n" \
                 f"📱 *Username:* {username_text}\n" \
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

def send_order_confirmation_to_user(phone, order_id, total_amount, cashback_earned, loyalty_level):
    """Отправка подтверждения пользователю"""
    print(f"Заказ #{order_id} оформлен для {phone}. Сумма: {total_amount:.2f} руб.")
    print(f"Начислен кешбек: {cashback_earned:.2f} руб. (Уровень: {loyalty_level})")

@app.route('/api/user/profile')
def api_user_profile():
    """Получение профиля пользователя и истории заказов"""
    try:
        user_data = get_telegram_user_data()
        user_id = user_data['id']
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 🔥 ВАЖНО: Получаем ВСЕ данные пользователя ОДНИМ запросом
        db.execute_query(cursor, '''
            SELECT 
                id, 
                telegram_id,
                balance, 
                first_name, 
                username, 
                photo_url, 
                is_verified, 
                referral_code, 
                total_spent, 
                total_orders, 
                total_invited,
                created_at
            FROM users 
            WHERE telegram_id = ?
        ''', (user_id,))
        
        user = db.fetchone(cursor)
        
        if not user:
            conn.close()
            print(f"❌ Пользователь не найден: telegram_id={user_id}")
            return jsonify({
                'balance': 0,
                'first_name': user_data.get('first_name', 'Пользователь'),
                'username': user_data.get('username'),
                'photo_url': user_data.get('photo_url', '/static/images/default-avatar.png'),
                'is_verified': False,  # ← ПО УМОЛЧАНИЮ False
                'referral_code': None,
                'total_spent': 0,
                'total_orders': 0,
                'total_invited': 0,
                'loyalty_level': 'Новичок',
                'loyalty_rate': 0.5,
                'next_level_threshold': 10000,
                'next_level_percent': 1.0,
                'progress_percentage': 0,
                'orders': []
            })
        
        # 🔥 ИЗВЛЕКАЕМ ДАННЫЕ ИЗ БАЗЫ
        user_db_id = user[0]
        telegram_id = user[1]
        balance = float(user[2])
        first_name = user[3] or user_data.get('first_name', 'Пользователь')
        username = user[4] or user_data.get('username')
        photo_url = user[5] or user_data.get('photo_url', '/static/images/default-avatar.png')
        is_verified = bool(user[6])  # ← ВОТ ОНО! Берем из базы
        referral_code = user[7]
        total_spent = float(user[8])
        total_orders = user[9]
        total_invited = user[10]
        created_at = user[11]
        
        print(f"✅ DEBUG: Пользователь {username} (ID: {telegram_id})")
        print(f"✅ DEBUG: is_verified из базы = {is_verified} (тип: {type(user[6])}, значение: {user[6]})")
        print(f"✅ DEBUG: balance = {balance}")
        
        # Определяем уровень лояльности
        loyalty_level = "Новичок"
        loyalty_rate = 0.005
        next_level_threshold = 10000
        next_level_percent = 1.0
        
        for level in LOYALTY_LEVELS:
            if total_spent >= level['min'] and total_spent < level['max']:
                loyalty_level = level['name']
                loyalty_rate = level['rate']
                
                # Находим следующий уровень
                next_level_index = LOYALTY_LEVELS.index(level) + 1
                if next_level_index < len(LOYALTY_LEVELS):
                    next_level = LOYALTY_LEVELS[next_level_index]
                    next_level_threshold = next_level['min']
                    next_level_percent = next_level['rate'] * 100
                break
        
        # Получаем заказы пользователя
        db.execute_query(cursor, '''
            SELECT id, total_amount, cashback_earned, pickup_location, delivery_type, 
                   delivery_city, delivery_address, status, created_at
            FROM orders 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
        ''', (user_db_id,))
        
        orders_data = db.fetchall(cursor)
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
        
        # 🔥 ВОЗВРАЩАЕМ ОТВЕТ СО ВСЕМИ ДАННЫМИ
        response_data = {
            'success': True,
            'balance': balance,
            'first_name': first_name,
            'username': username,
            'photo_url': photo_url,
            'is_verified': is_verified,  # ← ЭТО ГЛАВНОЕ ПОЛЕ
            'referral_code': referral_code,
            'total_spent': total_spent,
            'total_orders': total_orders,
            'total_invited': total_invited,
            'created_at': created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
            'loyalty_level': loyalty_level,
            'loyalty_rate': loyalty_rate * 100,
            'next_level_threshold': next_level_threshold,
            'next_level_percent': next_level_percent,
            'progress_percentage': min(100, (total_spent / next_level_threshold) * 100) if next_level_threshold > 0 else 0,
            'orders': orders_list
        }
        
        print(f"✅ Отправляем данные: is_verified = {is_verified}")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Ошибка получения профиля: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e),
            'balance': 0,
            'first_name': 'Ошибка',
            'username': 'error',
            'photo_url': '/static/images/default-avatar.png',
            'is_verified': False,  # ← ПРИ ОШИБКЕ ТОЖЕ False
            'referral_code': None,
            'total_spent': 0,
            'total_orders': 0,
            'total_invited': 0,
            'loyalty_level': 'Новичок',
            'loyalty_rate': 0.5,
            'next_level_threshold': 10000,
            'next_level_percent': 1.0,
            'progress_percentage': 0,
            'orders': []
        }), 500

@app.route('/api/user/profile/refresh', methods=['GET', 'POST'])
def api_user_profile_refresh():
    """Принудительное обновление профиля (без кэша)"""
    try:
        # Добавляем заголовки против кэширования
        response = api_user_profile()
        
        # Дополнительно добавляем заголовки
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-Refreshed-At'] = datetime.now().isoformat()
        
        return response
        
    except Exception as e:
        print(f"❌ Ошибка принудительного обновления: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'is_verified': False
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
        
        db.execute_query(cursor, '''
            SELECT id, name, description, price, image_path 
            FROM products 
            WHERE is_active = 1 AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?)
            ORDER BY name
            LIMIT 20
        ''', (f'%{query}%', f'%{query}%'))
        
        products_data = db.fetchall(cursor)
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

# Добавьте эти функции в app.py, если их нет

@app.route('/api/admin/check-verification', methods=['POST'])
@require_api_key

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
    print(f"API секретный ключ: {API_SECRET_KEY[:10]}...")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)