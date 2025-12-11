import telebot
from telebot import types
import sqlite3
import json
import os
import requests
from config import Config
from database import Database

bot = telebot.TeleBot(Config.TELEGRAM_BOT_TOKEN)
db = Database()

def is_admin(user_id):
    return user_id == Config.ADMIN_USER_ID

@bot.message_handler(commands=['start'])
def start_command(message):
    if is_admin(message.from_user.id):
        show_admin_menu(message.chat.id)
    else:
        bot.send_sticker(
            message.chat.id,
            'CAACAgIAAxkBAAEP52lpK2wAAR0AASRZ2hH8N6BQB5rDVyTFAAIfPAACJGEIS2C8BvvyqC-DNgQ'
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "Открыть сайт", 
            url=f"https://t.me/{Config.BOT_USERNAME}/VapeCloud"
        ))
        
        bot.send_message(
            message.chat.id,
            "Для заказа перейдите на наш сайт:",
            reply_markup=markup
        )

def show_admin_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('📊 Статистика', '💰 Прибыль')
    markup.add('📂 Управление разделами', '📁 Управление категориями')
    markup.add('🛍️ Управление товарами', '📦 Список товаров')
    markup.add('🏪 Управление пунктами', '📍 Список пунктов')
    markup.add('🏙️ Управление городами', '📋 Список категорий')
    
    bot.send_message(
        chat_id,
        f"👑 Панель администратора VapeCloud\n\n"
        f"Выберите действие:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '📂 Управление разделами')
def manage_sections(message):
    if not is_admin(message.from_user.id):
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('➕ Добавить раздел', '✏️ Изменить раздел')
    markup.add('🗑️ Удалить раздел', '📋 Список разделов')
    markup.add('🔙 Назад')
    
    bot.send_message(
        message.chat.id,
        "📂 Управление разделами (суперкатегориями):",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '➕ Добавить раздел')
def add_section_start(message):
    if not is_admin(message.from_user.id):
        return
    
    markup = types.ReplyKeyboardRemove()
    msg = bot.send_message(
        message.chat.id,
        "📝 Введите ID раздела (английскими буквами, без пробелов, например: 'devices', 'accessories'):",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, add_section_id)

def add_section_id(message):
    section_data = {'id': message.text.lower().strip()}
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM sections WHERE name = ?', (section_data['id'],))
    existing = cursor.fetchone()
    conn.close()
    
    if existing:
        bot.send_message(message.chat.id, "❌ Раздел с таким ID уже существует!")
        show_admin_menu(message.chat.id)
        return
    
    msg = bot.send_message(
        message.chat.id,
        "📝 Введите отображаемое название раздела (на русском, например: 'Устройства'):"
    )
    bot.register_next_step_handler(msg, add_section_name, section_data)

def add_section_name(message, section_data):
    section_data['display_name'] = message.text.strip()
    
    msg = bot.send_message(
        message.chat.id,
        "🎨 Введите иконку для раздела (эмодзи, например: 📱, 🧴, 🧰):"
    )
    bot.register_next_step_handler(msg, add_section_icon, section_data)

def add_section_icon(message, section_data):
    section_data['icon'] = message.text.strip()
    
    msg = bot.send_message(
        message.chat.id,
        "🔢 Введите порядок сортировки (число, чем меньше - тем выше в списке):"
    )
    bot.register_next_step_handler(msg, add_section_order, section_data)

def add_section_order(message, section_data):
    try:
        section_data['order'] = int(message.text)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sections (name, display_name, icon, sort_order)
            VALUES (?, ?, ?, ?)
        ''', (
            section_data['id'],
            section_data['display_name'],
            section_data['icon'],
            section_data['order']
        ))
        
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ Раздел успешно добавлен!\n\n"
            f"ID: {section_data['id']}\n"
            f"Название: {section_data['display_name']}\n"
            f"Иконка: {section_data['icon']}\n"
            f"Порядок: {section_data['order']}"
        )
        show_admin_menu(message.chat.id)
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат числа!")
        show_admin_menu(message.chat.id)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при добавлении раздела: {str(e)}")
        show_admin_menu(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '🗑️ Удалить раздел')
def delete_section_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, display_name FROM sections 
        WHERE is_active = 1
        ORDER BY sort_order
    ''')
    sections = cursor.fetchall()
    conn.close()
    
    if not sections:
        bot.send_message(message.chat.id, "Нет активных разделов для удаления.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for sec_id, sec_name, display_name in sections:
        markup.add(types.InlineKeyboardButton(
            f"{display_name} ({sec_name})", 
            callback_data=f"delete_sec_{sec_id}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите раздел для удаления:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_sec_'))
def delete_section_confirm(call):
    section_id = call.data.replace('delete_sec_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name, display_name FROM sections WHERE id = ?', (section_id,))
    section = cursor.fetchone()
    
    if section:
        cursor.execute('SELECT COUNT(*) FROM categories WHERE section_id = ? AND is_active = 1', (section_id,))
        category_count = cursor.fetchone()[0]
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "✅ Да, удалить", 
            callback_data=f"confirm_delete_sec_{section_id}"
        ))
        markup.add(types.InlineKeyboardButton(
            "❌ Отмена", 
            callback_data="cancel_delete_sec"
        ))
        
        warning = ""
        if category_count > 0:
            warning = f"\n⚠️ Внимание: В этом разделе {category_count} категорий!"
        
        bot.edit_message_text(
            f"Вы уверены, что хотите удалить раздел '{section[1]} ({section[0]})'?{warning}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_sec_'))
def delete_section_final(call):
    section_id = call.data.replace('confirm_delete_sec_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name FROM sections WHERE id = ?', (section_id,))
    section_name = cursor.fetchone()[0]
    
    cursor.execute('UPDATE sections SET is_active = 0 WHERE id = ?', (section_id,))
    
    conn.commit()
    conn.close()
    
    bot.edit_message_text(
        f"✅ Раздел '{section_name}' успешно удален!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_delete_sec')
def cancel_delete_sec(call):
    bot.edit_message_text(
        "Удаление отменено.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda message: message.text == '✏️ Изменить раздел')
def edit_section_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, display_name, icon, sort_order 
        FROM sections 
        WHERE is_active = 1
        ORDER BY sort_order
    ''')
    sections = cursor.fetchall()
    conn.close()
    
    if not sections:
        bot.send_message(message.chat.id, "Нет активных разделов.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for sec in sections:
        markup.add(types.InlineKeyboardButton(
            f"{sec[2]} ({sec[1]})", 
            callback_data=f"edit_sec_{sec[0]}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите раздел для редактирования:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_sec_'))
def edit_section_menu(call):
    section_id = call.data.replace('edit_sec_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name, display_name, icon, sort_order FROM sections WHERE id = ?', (section_id,))
    section = cursor.fetchone()
    conn.close()
    
    if section:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✏️ Название", callback_data=f"edit_sec_name_{section_id}"),
            types.InlineKeyboardButton("🎨 Иконка", callback_data=f"edit_sec_icon_{section_id}")
        )
        markup.add(
            types.InlineKeyboardButton("🔢 Порядок", callback_data=f"edit_sec_order_{section_id}"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_sections")
        )
        
        bot.edit_message_text(
            f"Редактирование раздела:\n\n"
            f"ID: {section[0]}\n"
            f"Название: {section[1]}\n"
            f"Иконка: {section[2]}\n"
            f"Порядок: {section[3]}\n\n"
            f"Что хотите изменить?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_sec_name_'))
def edit_section_name(call):
    section_id = call.data.replace('edit_sec_name_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "Введите новое название раздела:"
    )
    bot.register_next_step_handler(msg, update_section_name, section_id)

def update_section_name(message, section_id):
    new_name = message.text.strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE sections SET display_name = ? WHERE id = ?', (new_name, section_id))
    conn.commit()
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"✅ Название раздела обновлено!"
    )
    show_admin_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_sec_icon_'))
def edit_section_icon(call):
    section_id = call.data.replace('edit_sec_icon_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "Введите новую иконку (эмодзи):"
    )
    bot.register_next_step_handler(msg, update_section_icon, section_id)

def update_section_icon(message, section_id):
    new_icon = message.text.strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE sections SET icon = ? WHERE id = ?', (new_icon, section_id))
    conn.commit()
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"✅ Иконка раздела обновлена!"
    )
    show_admin_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_sec_order_'))
def edit_section_order(call):
    section_id = call.data.replace('edit_sec_order_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "Введите новый порядок сортировки (число):"
    )
    bot.register_next_step_handler(msg, update_section_order, section_id)

def update_section_order(message, section_id):
    try:
        new_order = int(message.text)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE sections SET sort_order = ? WHERE id = ?', (new_order, section_id))
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ Порядок сортировки обновлен!"
        )
        show_admin_menu(message.chat.id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат числа!")
        show_admin_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_sections')
def back_to_sections(call):
    edit_section_start(call.message)

@bot.message_handler(func=lambda message: message.text == '📋 Список разделов')
def list_sections(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.id, s.name, s.display_name, s.icon, s.sort_order, s.is_active,
               COUNT(c.id) as category_count
        FROM sections s
        LEFT JOIN categories c ON s.id = c.section_id AND c.is_active = 1
        GROUP BY s.id
        ORDER BY s.sort_order
    ''')
    sections = cursor.fetchall()
    conn.close()
    
    if not sections:
        bot.send_message(message.chat.id, "Нет разделов в базе данных.")
        return
    
    sections_text = "📂 Список разделов:\n\n"
    for sec in sections:
        status = "✅ Активен" if sec[5] else "❌ Неактивен"
        sections_text += f"{sec[3]} {sec[2]}\n"
        sections_text += f"ID: {sec[1]}\n"
        sections_text += f"🔢 Порядок: {sec[4]}\n"
        sections_text += f"📁 Категорий: {sec[6]}\n"
        sections_text += f"📊 Статус: {status}\n"
        sections_text += "─" * 30 + "\n"
    
    bot.send_message(message.chat.id, sections_text)

@bot.message_handler(func=lambda message: message.text == '📁 Управление категориями')
def manage_categories(message):
    if not is_admin(message.from_user.id):
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('➕ Добавить категорию', '✏️ Изменить категорию')
    markup.add('🗑️ Удалить категорию', '📝 Привязать к разделу')
    markup.add('🔙 Назад')
    
    bot.send_message(
        message.chat.id,
        "📁 Управление категориями товаров:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '➕ Добавить категорию')
def add_category_start(message):
    if not is_admin(message.from_user.id):
        return
    
    # Сначала получаем список разделов для выбора
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, display_name FROM sections WHERE is_active = 1 ORDER BY sort_order')
    sections = cursor.fetchall()
    conn.close()
    
    if not sections:
        bot.send_message(message.chat.id, "❌ Нет активных разделов. Сначала создайте раздел.")
        show_admin_menu(message.chat.id)
        return
    
    section_list = "\n".join([f"• {name} (ID: {id})" for id, name in sections])
    
    msg = bot.send_message(
        message.chat.id,
        f"📂 Выберите раздел для категории из списка:\n\n{section_list}\n\n"
        f"Введите ID раздела (число):"
    )
    bot.register_next_step_handler(msg, add_category_section)

def add_category_section(message):
    try:
        section_id = int(message.text)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM sections WHERE id = ? AND is_active = 1', (section_id,))
        valid_section = cursor.fetchone()
        conn.close()
        
        if not valid_section:
            bot.send_message(message.chat.id, f"❌ Раздел с ID '{section_id}' не найден или неактивен.")
            show_admin_menu(message.chat.id)
            return
        
        category_data = {'section_id': section_id}
        
        markup = types.ReplyKeyboardRemove()
        msg = bot.send_message(
            message.chat.id,
            "📝 Введите ID категории (английскими буквами, без пробелов, например: 'pods', 'mods'):",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, add_category_id, category_data)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат ID раздела.")
        show_admin_menu(message.chat.id)

def add_category_id(message, category_data):
    category_data['id'] = message.text.lower().strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM categories WHERE name = ?', (category_data['id'],))
    existing = cursor.fetchone()
    conn.close()
    
    if existing:
        bot.send_message(message.chat.id, "❌ Категория с таким ID уже существует!")
        show_admin_menu(message.chat.id)
        return
    
    msg = bot.send_message(
        message.chat.id,
        "📝 Введите отображаемое название категории (на русском, например: 'Поды'):"
    )
    bot.register_next_step_handler(msg, add_category_name, category_data)

def add_category_name(message, category_data):
    category_data['display_name'] = message.text.strip()
    
    msg = bot.send_message(
        message.chat.id,
        "🎨 Введите иконку для категории (эмодзи, например: 🎯, ⚡, 💧):"
    )
    bot.register_next_step_handler(msg, add_category_icon, category_data)

def add_category_icon(message, category_data):
    category_data['icon'] = message.text.strip()
    
    msg = bot.send_message(
        message.chat.id,
        "🔢 Введите порядок сортировки (число, чем меньше - тем выше в списке):"
    )
    bot.register_next_step_handler(msg, add_category_order, category_data)

def add_category_order(message, category_data):
    try:
        category_data['order'] = int(message.text)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO categories (name, display_name, icon, section_id, sort_order)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            category_data['id'],
            category_data['display_name'],
            category_data['icon'],
            category_data['section_id'],
            category_data['order']
        ))
        
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ Категория успешно добавлена!\n\n"
            f"ID: {category_data['id']}\n"
            f"Название: {category_data['display_name']}\n"
            f"Иконка: {category_data['icon']}\n"
            f"Порядок: {category_data['order']}"
        )
        show_admin_menu(message.chat.id)
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат числа!")
        show_admin_menu(message.chat.id)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при добавлении категории: {str(e)}")
        show_admin_menu(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '📝 Привязать к разделу')
def assign_category_to_section_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.id, c.name, c.display_name, s.display_name 
        FROM categories c
        LEFT JOIN sections s ON c.section_id = s.id
        WHERE c.is_active = 1
        ORDER BY c.sort_order
    ''')
    categories = cursor.fetchall()
    conn.close()
    
    if not categories:
        bot.send_message(message.chat.id, "Нет активных категорий.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for cat_id, cat_name, display_name, section_name in categories:
        section_display = f" [{section_name}]" if section_name else " [Без раздела]"
        markup.add(types.InlineKeyboardButton(
            f"{display_name}{section_display}", 
            callback_data=f"assign_cat_{cat_id}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите категорию для привязки к разделу:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('assign_cat_'))
def assign_category_select_section(call):
    category_id = call.data.replace('assign_cat_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, display_name FROM sections WHERE is_active = 1 ORDER BY sort_order')
    sections = cursor.fetchall()
    conn.close()
    
    if not sections:
        bot.edit_message_text(
            "Нет активных разделов для привязки.",
            call.message.chat.id,
            call.message.message_id
        )
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    for sec_id, sec_name in sections:
        markup.add(types.InlineKeyboardButton(
            sec_name, 
            callback_data=f"assign_to_sec_{category_id}_{sec_id}"
        ))
    markup.add(types.InlineKeyboardButton(
        "❌ Убрать из раздела", 
        callback_data=f"remove_from_sec_{category_id}"
    ))
    
    bot.edit_message_text(
        "Выберите раздел для привязки категории:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('assign_to_sec_'))
def assign_category_final(call):
    data = call.data.replace('assign_to_sec_', '').split('_')
    category_id = data[0]
    section_id = data[1]
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE categories SET section_id = ? WHERE id = ?', (section_id, category_id))
    conn.commit()
    
    cursor.execute('SELECT display_name FROM categories WHERE id = ?', (category_id,))
    category_name = cursor.fetchone()[0]
    
    cursor.execute('SELECT display_name FROM sections WHERE id = ?', (section_id,))
    section_name = cursor.fetchone()[0]
    conn.close()
    
    bot.edit_message_text(
        f"✅ Категория '{category_name}' привязана к разделу '{section_name}'!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_from_sec_'))
def remove_category_from_section(call):
    category_id = call.data.replace('remove_from_sec_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE categories SET section_id = NULL WHERE id = ?', (category_id,))
    conn.commit()
    
    cursor.execute('SELECT display_name FROM categories WHERE id = ?', (category_id,))
    category_name = cursor.fetchone()[0]
    conn.close()
    
    bot.edit_message_text(
        f"✅ Категория '{category_name}' убрана из раздела!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda message: message.text == '🗑️ Удалить категорию')
def delete_category_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.id, c.name, c.display_name, s.display_name 
        FROM categories c
        LEFT JOIN sections s ON c.section_id = s.id
        WHERE c.is_active = 1
        ORDER BY c.sort_order
    ''')
    categories = cursor.fetchall()
    conn.close()
    
    if not categories:
        bot.send_message(message.chat.id, "Нет активных категорий для удаления.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for cat_id, cat_name, display_name, section_name in categories:
        section_display = f" [{section_name}]" if section_name else ""
        markup.add(types.InlineKeyboardButton(
            f"{display_name}{section_display}", 
            callback_data=f"delete_cat_{cat_id}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите категорию для удаления:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_cat_'))
def delete_category_confirm(call):
    category_id = call.data.replace('delete_cat_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name, display_name FROM categories WHERE id = ?', (category_id,))
    category = cursor.fetchone()
    
    if category:
        cursor.execute('SELECT COUNT(*) FROM products WHERE category = ? AND is_active = 1', (category[0],))
        product_count = cursor.fetchone()[0]
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "✅ Да, удалить", 
            callback_data=f"confirm_delete_cat_{category_id}"
        ))
        markup.add(types.InlineKeyboardButton(
            "❌ Отмена", 
            callback_data="cancel_delete_cat"
        ))
        
        warning = ""
        if product_count > 0:
            warning = f"\n⚠️ Внимание: В этой категории {product_count} товаров!"
        
        bot.edit_message_text(
            f"Вы уверены, что хотите удалить категорию '{category[1]} ({category[0]})'?{warning}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_cat_'))
def delete_category_final(call):
    category_id = call.data.replace('confirm_delete_cat_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name FROM categories WHERE id = ?', (category_id,))
    category_name = cursor.fetchone()[0]
    
    cursor.execute('UPDATE categories SET is_active = 0 WHERE id = ?', (category_id,))
    
    conn.commit()
    conn.close()
    
    bot.edit_message_text(
        f"✅ Категория '{category_name}' успешно удалена!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_delete_cat')
def cancel_delete_cat(call):
    bot.edit_message_text(
        "Удаление отменено.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda message: message.text == '✏️ Изменить категорию')
def edit_category_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.id, c.name, c.display_name, c.icon, c.sort_order, s.display_name
        FROM categories c
        LEFT JOIN sections s ON c.section_id = s.id
        WHERE c.is_active = 1
        ORDER BY c.sort_order
    ''')
    categories = cursor.fetchall()
    conn.close()
    
    if not categories:
        bot.send_message(message.chat.id, "Нет активных категорий.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for cat in categories:
        section_display = f" [{cat[5]}]" if cat[5] else ""
        markup.add(types.InlineKeyboardButton(
            f"{cat[2]}{section_display}", 
            callback_data=f"edit_cat_{cat[0]}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите категорию для редактирования:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_cat_'))
def edit_category_menu(call):
    category_id = call.data.replace('edit_cat_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name, display_name, icon, sort_order FROM categories WHERE id = ?', (category_id,))
    category = cursor.fetchone()
    conn.close()
    
    if category:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✏️ Название", callback_data=f"edit_name_{category_id}"),
            types.InlineKeyboardButton("🎨 Иконка", callback_data=f"edit_icon_{category_id}")
        )
        markup.add(
            types.InlineKeyboardButton("🔢 Порядок", callback_data=f"edit_order_{category_id}"),
            types.InlineKeyboardButton("📂 Раздел", callback_data=f"edit_section_{category_id}")
        )
        markup.add(
            types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_cats")
        )
        
        bot.edit_message_text(
            f"Редактирование категории:\n\n"
            f"ID: {category[0]}\n"
            f"Название: {category[1]}\n"
            f"Иконка: {category[2]}\n"
            f"Порядок: {category[3]}\n\n"
            f"Что хотите изменить?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_section_'))
def edit_category_section(call):
    category_id = call.data.replace('edit_section_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, display_name FROM sections WHERE is_active = 1 ORDER BY sort_order')
    sections = cursor.fetchall()
    conn.close()
    
    if not sections:
        bot.send_message(call.message.chat.id, "Нет активных разделов.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    for sec_id, sec_name in sections:
        markup.add(types.InlineKeyboardButton(
            sec_name, 
            callback_data=f"set_section_{category_id}_{sec_id}"
        ))
    markup.add(types.InlineKeyboardButton(
        "❌ Убрать из раздела", 
        callback_data=f"remove_section_{category_id}"
    ))
    
    bot.edit_message_text(
        "Выберите новый раздел для категории:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_section_'))
def update_category_section(call):
    data = call.data.replace('set_section_', '').split('_')
    category_id = data[0]
    section_id = data[1]
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE categories SET section_id = ? WHERE id = ?', (section_id, category_id))
    conn.commit()
    conn.close()
    
    bot.edit_message_text(
        f"✅ Раздел категории обновлен!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_section_'))
def remove_category_section(call):
    category_id = call.data.replace('remove_section_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE categories SET section_id = NULL WHERE id = ?', (category_id,))
    conn.commit()
    conn.close()
    
    bot.edit_message_text(
        f"✅ Категория убрана из раздела!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_name_'))
def edit_category_name(call):
    category_id = call.data.replace('edit_name_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "Введите новое название категории:"
    )
    bot.register_next_step_handler(msg, update_category_name, category_id)

def update_category_name(message, category_id):
    new_name = message.text.strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE categories SET display_name = ? WHERE id = ?', (new_name, category_id))
    conn.commit()
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"✅ Название категории обновлено!"
    )
    show_admin_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_icon_'))
def edit_category_icon(call):
    category_id = call.data.replace('edit_icon_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "Введите новую иконку (эмодзи):"
    )
    bot.register_next_step_handler(msg, update_category_icon, category_id)

def update_category_icon(message, category_id):
    new_icon = message.text.strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE categories SET icon = ? WHERE id = ?', (new_icon, category_id))
    conn.commit()
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"✅ Иконка категории обновлена!"
    )
    show_admin_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_order_'))
def edit_category_order(call):
    category_id = call.data.replace('edit_order_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "Введите новый порядок сортировки (число):"
    )
    bot.register_next_step_handler(msg, update_category_order, category_id)

def update_category_order(message, category_id):
    try:
        new_order = int(message.text)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE categories SET sort_order = ? WHERE id = ?', (new_order, category_id))
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ Порядок сортировки обновлен!"
        )
        show_admin_menu(message.chat.id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат числа!")
        show_admin_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_cats')
def back_to_categories(call):
    edit_category_start(call.message)

@bot.message_handler(func=lambda message: message.text == '🏙️ Управление городами')
def manage_cities(message):
    if not is_admin(message.from_user.id):
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('➕ Добавить город', '🗑️ Удалить город')
    markup.add('📋 Список городов', '🔙 Назад')
    
    bot.send_message(
        message.chat.id,
        "🏙️ Управление городами:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '➕ Добавить город')
def add_city_start(message):
    if not is_admin(message.from_user.id):
        return
    
    msg = bot.send_message(
        message.chat.id,
        "Введите название города:"
    )
    bot.register_next_step_handler(msg, add_city_confirm)

def add_city_confirm(message):
    city_name = message.text.strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT city FROM pickup_locations WHERE city = ?', (city_name,))
    existing = cursor.fetchone()
    
    if existing:
        bot.send_message(message.chat.id, f"❌ Город '{city_name}' уже существует!")
        conn.close()
        return
    
    # Создаем пункты выдачи по умолчанию для нового города
    cursor.execute('''
        INSERT INTO pickup_locations (name, address, city, location_type, delivery_price)
        VALUES (?, ?, ?, 'pickup', 0)
    ''', ('Пункт выдачи', 'Укажите адрес', city_name))
    
    cursor.execute('''
        INSERT INTO pickup_locations (name, address, city, location_type, delivery_price)
        VALUES (?, ?, ?, 'delivery', 300)
    ''', ('Доставка по городу', 'Доставка курьером', city_name))
    
    conn.commit()
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"✅ Город '{city_name}' добавлен! Созданы стандартные пункты выдачи и доставки."
    )
    show_admin_menu(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '🗑️ Удалить город')
def delete_city_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT city FROM pickup_locations WHERE city IS NOT NULL ORDER BY city')
    cities = cursor.fetchall()
    conn.close()
    
    if not cities:
        bot.send_message(message.chat.id, "Нет городов для удаления.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for city_tuple in cities:
        city = city_tuple[0]
        markup.add(types.InlineKeyboardButton(
            city, 
            callback_data=f"delete_city_{city}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите город для удаления (удалятся все связанные пункты выдачи):",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_city_'))
def delete_city_confirm(call):
    city_name = call.data.replace('delete_city_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM pickup_locations WHERE city = ?', (city_name,))
    location_count = cursor.fetchone()[0]
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "✅ Да, удалить", 
        callback_data=f"confirm_delete_city_{city_name}"
    ))
    markup.add(types.InlineKeyboardButton(
        "❌ Отмена", 
        callback_data="cancel_delete_city"
    ))
    
    bot.edit_message_text(
        f"Вы уверены, что хотите удалить город '{city_name}'?\n"
        f"Будут удалены {location_count} пунктов выдачи.",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_city_'))
def delete_city_final(call):
    city_name = call.data.replace('confirm_delete_city_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM pickup_locations WHERE city = ?', (city_name,))
    conn.commit()
    conn.close()
    
    bot.edit_message_text(
        f"✅ Город '{city_name}' и все связанные пункты выдачи удалены!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_delete_city')
def cancel_delete_city(call):
    bot.edit_message_text(
        "Удаление отменено.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda message: message.text == '📋 Список городов')
def list_cities(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT city, 
               COUNT(CASE WHEN location_type = 'pickup' THEN 1 END) as pickup_count,
               COUNT(CASE WHEN location_type = 'delivery' THEN 1 END) as delivery_count
        FROM pickup_locations 
        WHERE city IS NOT NULL
        GROUP BY city
        ORDER BY city
    ''')
    cities = cursor.fetchall()
    conn.close()
    
    if not cities:
        bot.send_message(message.chat.id, "Нет городов в базе данных.")
        return
    
    cities_text = "🏙️ Список городов:\n\n"
    for city, pickup_count, delivery_count in cities:
        cities_text += f"📍 {city}\n"
        cities_text += f"   🏪 Пунктов самовывоза: {pickup_count or 0}\n"
        cities_text += f"   🚚 Пунктов доставки: {delivery_count or 0}\n"
        cities_text += "─" * 30 + "\n"
    
    bot.send_message(message.chat.id, cities_text)

@bot.message_handler(func=lambda message: message.text == '🏪 Управление пунктами')
def manage_locations(message):
    if not is_admin(message.from_user.id):
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('➕ Добавить пункт', '🗑️ Удалить пункт')
    markup.add('✏️ Редактировать пункт', '🔙 Назад')
    
    bot.send_message(
        message.chat.id,
        "🏪 Управление пунктами выдачи:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '➕ Добавить пункт')
def add_pickup_location(message):
    if not is_admin(message.from_user.id):
        return
    
    # Сначала получаем список городов
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT city FROM pickup_locations WHERE city IS NOT NULL ORDER BY city')
    cities = cursor.fetchall()
    conn.close()
    
    if not cities:
        bot.send_message(message.chat.id, "❌ Нет городов. Сначала добавьте город.")
        show_admin_menu(message.chat.id)
        return
    
    city_list = "\n".join([f"• {city[0]}" for city in cities])
    
    msg = bot.send_message(
        message.chat.id,
        f"🏙️ Выберите город из списка:\n\n{city_list}\n\n"
        f"Введите название города:"
    )
    bot.register_next_step_handler(msg, add_location_city)

def add_location_city(message):
    city = message.text.strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT city FROM pickup_locations WHERE city = ?', (city,))
    valid_city = cursor.fetchone()
    conn.close()
    
    if not valid_city:
        bot.send_message(message.chat.id, f"❌ Город '{city}' не найден. Сначала добавьте город.")
        show_admin_menu(message.chat.id)
        return
    
    pickup_data = {'city': city}
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('🏪 Самовывоз', '🚚 Доставка')
    
    msg = bot.send_message(
        message.chat.id,
        f"Выберите тип пункта для города {city}:",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, add_location_type, pickup_data)

def add_location_type(message, pickup_data):
    if message.text == '🏪 Самовывоз':
        pickup_data['location_type'] = 'pickup'
    elif message.text == '🚚 Доставка':
        pickup_data['location_type'] = 'delivery'
    else:
        bot.send_message(message.chat.id, "❌ Неверный тип пункта.")
        show_admin_menu(message.chat.id)
        return
    
    remove_markup = types.ReplyKeyboardRemove()
    msg = bot.send_message(
        message.chat.id,
        "Введите название пункта выдачи:",
        reply_markup=remove_markup
    )
    bot.register_next_step_handler(msg, add_location_name, pickup_data)

def add_location_name(message, pickup_data):
    pickup_data['name'] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "Введите адрес пункта выдачи:"
    )
    bot.register_next_step_handler(msg, add_location_address, pickup_data)

def add_location_address(message, pickup_data):
    pickup_data['address'] = message.text
    
    if pickup_data['location_type'] == 'delivery':
        msg = bot.send_message(
            message.chat.id,
            "💰 Введите стоимость доставки (только число):"
        )
        bot.register_next_step_handler(msg, add_location_delivery_price, pickup_data)
    else:
        pickup_data['delivery_price'] = 0
        save_location(pickup_data, message.chat.id)

def add_location_delivery_price(message, pickup_data):
    try:
        pickup_data['delivery_price'] = float(message.text)
        save_location(pickup_data, message.chat.id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат цены!")
        show_admin_menu(message.chat.id)

def save_location(pickup_data, chat_id):
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO pickup_locations (name, address, city, location_type, delivery_price)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        pickup_data['name'],
        pickup_data['address'],
        pickup_data['city'],
        pickup_data['location_type'],
        pickup_data['delivery_price']
    ))
    
    conn.commit()
    conn.close()
    
    location_type_text = "самовывоза" if pickup_data['location_type'] == 'pickup' else "доставки"
    
    bot.send_message(
        chat_id,
        f"✅ Пункт {location_type_text} успешно добавлен!\n\n"
        f"Город: {pickup_data['city']}\n"
        f"Название: {pickup_data['name']}\n"
        f"Адрес: {pickup_data['address']}\n"
        f"Стоимость доставки: {pickup_data['delivery_price']} руб."
    )
    show_admin_menu(chat_id)

@bot.message_handler(func=lambda message: message.text == '✏️ Редактировать пункт')
def edit_location_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, address, city, location_type, delivery_price 
        FROM pickup_locations 
        WHERE is_active = 1
        ORDER BY city, location_type
    ''')
    locations = cursor.fetchall()
    conn.close()
    
    if not locations:
        bot.send_message(message.chat.id, "Нет активных пунктов выдачи.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for loc in locations:
        location_type = "🏪" if loc[4] == 'pickup' else "🚚"
        markup.add(types.InlineKeyboardButton(
            f"{location_type} {loc[1]} - {loc[2]}", 
            callback_data=f"edit_loc_{loc[0]}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите пункт для редактирования:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_loc_'))
def edit_location_menu(call):
    location_id = call.data.replace('edit_loc_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name, address, city, location_type, delivery_price FROM pickup_locations WHERE id = ?', (location_id,))
    location = cursor.fetchone()
    conn.close()
    
    if location:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✏️ Название", callback_data=f"edit_loc_name_{location_id}"),
            types.InlineKeyboardButton("📍 Адрес", callback_data=f"edit_loc_address_{location_id}")
        )
        if location[3] == 'delivery':
            markup.add(
                types.InlineKeyboardButton("💰 Стоимость", callback_data=f"edit_loc_price_{location_id}"),
            )
        markup.add(
            types.InlineKeyboardButton("🏙️ Город", callback_data=f"edit_loc_city_{location_id}"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_locs")
        )
        
        location_type = "самовывоза" if location[3] == 'pickup' else "доставки"
        
        bot.edit_message_text(
            f"Редактирование пункта {location_type}:\n\n"
            f"Город: {location[2]}\n"
            f"Название: {location[0]}\n"
            f"Адрес: {location[1]}\n"
            f"Стоимость доставки: {location[4]} руб.\n\n"
            f"Что хотите изменить?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_loc_name_'))
def edit_location_name(call):
    location_id = call.data.replace('edit_loc_name_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "Введите новое название пункта:"
    )
    bot.register_next_step_handler(msg, update_location_name, location_id)

def update_location_name(message, location_id):
    new_name = message.text.strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE pickup_locations SET name = ? WHERE id = ?', (new_name, location_id))
    conn.commit()
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"✅ Название пункта обновлено!"
    )
    show_admin_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_loc_address_'))
def edit_location_address(call):
    location_id = call.data.replace('edit_loc_address_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "Введите новый адрес:"
    )
    bot.register_next_step_handler(msg, update_location_address, location_id)

def update_location_address(message, location_id):
    new_address = message.text.strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE pickup_locations SET address = ? WHERE id = ?', (new_address, location_id))
    conn.commit()
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"✅ Адрес пункта обновлен!"
    )
    show_admin_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_loc_price_'))
def edit_location_price(call):
    location_id = call.data.replace('edit_loc_price_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "Введите новую стоимость доставки:"
    )
    bot.register_next_step_handler(msg, update_location_price, location_id)

def update_location_price(message, location_id):
    try:
        new_price = float(message.text)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE pickup_locations SET delivery_price = ? WHERE id = ?', (new_price, location_id))
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ Стоимость доставки обновлена!"
        )
        show_admin_menu(message.chat.id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат числа!")
        show_admin_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_loc_city_'))
def edit_location_city(call):
    location_id = call.data.replace('edit_loc_city_', '')
    
    # Получаем список городов
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT city FROM pickup_locations WHERE city IS NOT NULL ORDER BY city')
    cities = cursor.fetchall()
    conn.close()
    
    if not cities:
        bot.send_message(call.message.chat.id, "Нет городов.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    for city_tuple in cities:
        city = city_tuple[0]
        markup.add(types.InlineKeyboardButton(
            city, 
            callback_data=f"update_loc_city_{location_id}_{city}"
        ))
    
    bot.edit_message_text(
        "Выберите новый город для пункта:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('update_loc_city_'))
def update_location_city(call):
    data = call.data.replace('update_loc_city_', '').split('_')
    location_id = data[0]
    city = data[1]
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE pickup_locations SET city = ? WHERE id = ?', (city, location_id))
    conn.commit()
    conn.close()
    
    bot.edit_message_text(
        f"✅ Город пункта обновлен на '{city}'!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_locs')
def back_to_locations(call):
    edit_location_start(call.message)

@bot.message_handler(func=lambda message: message.text == '🗑️ Удалить пункт')
def delete_pickup_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, address, city, location_type 
        FROM pickup_locations 
        WHERE is_active = 1
        ORDER BY city, location_type
    ''')
    locations = cursor.fetchall()
    conn.close()
    
    if not locations:
        bot.send_message(message.chat.id, "Нет активных пунктов выдачи для удаления.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for loc_id, loc_name, loc_address, loc_city, loc_type in locations:
        location_type = "🏪" if loc_type == 'pickup' else "🚚"
        markup.add(types.InlineKeyboardButton(
            f"{location_type} {loc_name} - {loc_city}", 
            callback_data=f"delete_location_{loc_id}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите пункт выдачи для удаления:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_location_'))
def delete_location_confirm(call):
    location_id = call.data.replace('delete_location_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name, address, city, location_type FROM pickup_locations WHERE id = ?', (location_id,))
    location = cursor.fetchone()
    
    if location:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "✅ Да, удалить", 
            callback_data=f"confirm_delete_loc_{location_id}"
        ))
        markup.add(types.InlineKeyboardButton(
            "❌ Отмена", 
            callback_data="cancel_delete_loc"
        ))
        
        location_type = "самовывоза" if location[3] == 'pickup' else "доставки"
        
        bot.edit_message_text(
            f"Вы уверены, что хотите удалить пункт {location_type} '{location[0]} - {location[1]}' в городе {location[2]}?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_loc_'))
def delete_location_final(call):
    location_id = call.data.replace('confirm_delete_loc_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE pickup_locations SET is_active = 0 WHERE id = ?', (location_id,))
    conn.commit()
    conn.close()
    
    bot.edit_message_text(
        "✅ Пункт выдачи успешно удален!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_delete_loc')
def cancel_delete_loc(call):
    bot.edit_message_text(
        "Удаление отменено.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda message: message.text == '📍 Список пунктов')
def list_locations(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, address, city, location_type, delivery_price, is_active 
        FROM pickup_locations
        ORDER BY city, location_type
    ''')
    locations = cursor.fetchall()
    conn.close()
    
    if not locations:
        bot.send_message(message.chat.id, "Нет пунктов выдачи в базе данных.")
        return
    
    locations_text = "📍 Список пунктов выдачи:\n\n"
    
    current_city = None
    for location in locations:
        if location[3] != current_city:
            current_city = location[3]
            locations_text += f"\n🏙️ Город: {current_city}\n"
        
        status = "✅ Активен" if location[6] else "❌ Неактивен"
        location_type = "🏪 Самовывоз" if location[4] == 'pickup' else "🚚 Доставка"
        price_info = f" ({location[5]} руб.)" if location[4] == 'delivery' else ""
        
        locations_text += f"  {location_type}{price_info}\n"
        locations_text += f"    📍 {location[1]} - {location[2]}\n"
        locations_text += f"    📊 Статус: {status}\n"
        locations_text += "    " + "─" * 25 + "\n"
    
    bot.send_message(message.chat.id, locations_text)

@bot.message_handler(func=lambda message: message.text == '📋 Список категорий')
def list_categories(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.id, c.name, c.display_name, c.icon, c.sort_order, c.is_active,
               s.display_name as section_name
        FROM categories c
        LEFT JOIN sections s ON c.section_id = s.id
        ORDER BY c.sort_order
    ''')
    categories = cursor.fetchall()
    conn.close()
    
    if not categories:
        bot.send_message(message.chat.id, "Нет категорий в базе данных.")
        return
    
    categories_text = "📋 Список категорий:\n\n"
    for cat in categories:
        status = "✅ Активна" if cat[5] else "❌ Неактивна"
        section_info = f" [Раздел: {cat[6]}]" if cat[6] else " [Без раздела]"
        categories_text += f"{cat[3]} {cat[2]}{section_info}\n"
        categories_text += f"ID: {cat[1]}\n"
        categories_text += f"🔢 Порядок: {cat[4]}\n"
        categories_text += f"📊 Статус: {status}\n"
        categories_text += "─" * 30 + "\n"
    
    bot.send_message(message.chat.id, categories_text)

@bot.message_handler(func=lambda message: message.text == '💰 Прибыль')
def show_profit(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT SUM(total_amount) FROM orders WHERE status = 'completed'
    ''')
    total_profit = cursor.fetchone()[0] or 0
    
    cursor.execute('''
        SELECT SUM(total_amount) FROM orders 
        WHERE status = 'completed' AND DATE(created_at) = DATE('now')
    ''')
    today_profit = cursor.fetchone()[0] or 0
    
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"📊 Финансовая статистика:\n\n"
        f"💰 Общая прибыль: {total_profit:.2f} руб.\n"
        f"📈 Сегодня: {today_profit:.2f} руб."
    )

@bot.message_handler(func=lambda message: message.text == '🛍️ Управление товарами')
def manage_products(message):
    if not is_admin(message.from_user.id):
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('➕ Добавить товар', '🗑️ Удалить товар')
    markup.add('🔙 Назад')
    
    bot.send_message(
        message.chat.id,
        "🛍️ Управление товарами:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '➕ Добавить товар')
def add_product_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT name, display_name FROM categories WHERE is_active = 1 ORDER BY sort_order')
    categories = cursor.fetchall()
    conn.close()
    
    if not categories:
        bot.send_message(message.chat.id, "❌ Нет активных категорий. Сначала создайте категорию.")
        return
    
    msg = bot.send_message(
        message.chat.id,
        "📸 Отправьте фото товара (рекомендуемый размер: 600x450px):"
    )
    
    bot.register_next_step_handler(msg, add_product_photo, {'categories': categories})

def add_product_photo(message, product_data):
    if message.photo:
        file_id = message.photo[-1].file_id
        product_data['file_id'] = file_id
        
        msg = bot.send_message(
            message.chat.id,
            "✏️ Введите название товара:"
        )
        bot.register_next_step_handler(msg, add_product_name, product_data)
    else:
        bot.send_message(message.chat.id, "❌ Пожалуйста, отправьте фото.")
        show_admin_menu(message.chat.id)

def add_product_name(message, product_data):
    product_data['name'] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "📝 Введите описание товара:"
    )
    bot.register_next_step_handler(msg, add_product_description, product_data)

def add_product_description(message, product_data):
    product_data['description'] = message.text
    
    msg = bot.send_message(
        message.chat.id,
        "💰 Введите цену товара (только число):"
    )
    bot.register_next_step_handler(msg, add_product_price, product_data)

def add_product_price(message, product_data):
    try:
        product_data['price'] = float(message.text)
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        categories = product_data['categories']
        for cat_name, display_name in categories:
            markup.add(types.InlineKeyboardButton(f"{display_name} ({cat_name})"))
        
        category_list = "\n".join([f"• {display_name} ({cat_name})" for cat_name, display_name in categories])
        
        msg = bot.send_message(
            message.chat.id,
            f"📂 Выберите категорию товара из списка:\n\n{category_list}\n\n"
            f"Напишите ID категории (например: 'pods'):",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, add_product_category, product_data)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат цены.")
        show_admin_menu(message.chat.id)

def add_product_category(message, product_data):
    category = message.text.lower().strip()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM categories WHERE name = ? AND is_active = 1', (category,))
    valid_category = cursor.fetchone()
    conn.close()
    
    if not valid_category:
        bot.send_message(message.chat.id, f"❌ Категория '{category}' не найдена или неактивна.")
        show_admin_menu(message.chat.id)
        return
    
    product_data['category'] = category
    
    remove_markup = types.ReplyKeyboardRemove()
    
    msg = bot.send_message(
        message.chat.id,
        "⚙️ Введите характеристики товара (каждую с новой строки):",
        reply_markup=remove_markup
    )
    bot.register_next_step_handler(msg, add_product_specs, product_data)

def add_product_specs(message, product_data):
    try:
        specs = message.text.split('\n')
        product_data['specifications'] = json.dumps(specs, ensure_ascii=False)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO products (name, description, price, image_path, category, specifications)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            product_data['name'],
            product_data['description'],
            product_data['price'],
            '/static/images/default-product.png',
            product_data['category'],
            product_data['specifications']
        ))
        
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ Товар успешно добавлен!\n\n"
            f"📦 Название: {product_data['name']}\n"
            f"💰 Цена: {product_data['price']} руб.\n"
            f"📂 Категория: {product_data['category']}"
        )
        show_admin_menu(message.chat.id)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при добавлении товара: {str(e)}")
        show_admin_menu(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '🗑️ Удалить товар')
def delete_product_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, name FROM products WHERE is_active = 1')
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        bot.send_message(message.chat.id, "Нет активных товаров для удаления.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for product_id, product_name in products:
        markup.add(types.InlineKeyboardButton(
            product_name, 
            callback_data=f"delete_product_{product_id}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите товар для удаления:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_product_'))
def delete_product_confirm(call):
    product_id = call.data.replace('delete_product_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    
    if product:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "✅ Да, удалить", 
            callback_data=f"confirm_delete_{product_id}"
        ))
        markup.add(types.InlineKeyboardButton(
            "❌ Отмена", 
            callback_data="cancel_delete"
        ))
        
        bot.edit_message_text(
            f"Вы уверены, что хотите удалить товар '{product[0]}'?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_'))
def delete_product_final(call):
    product_id = call.data.replace('confirm_delete_', '')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE products SET is_active = 0 WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    
    bot.edit_message_text(
        "✅ Товар успешно удален!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_delete')
def cancel_delete(call):
    bot.edit_message_text(
        "Удаление отменено.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda message: message.text == '📦 Список товаров')
def list_products(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.id, p.name, p.price, p.category, p.is_active, c.display_name
        FROM products p
        LEFT JOIN categories c ON p.category = c.name
        ORDER BY p.created_at DESC
    ''')
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        bot.send_message(message.chat.id, "Нет товаров в базе данных.")
        return
    
    products_text = "📦 Список товаров:\n\n"
    for product in products:
        status = "✅ Активен" if product[4] else "❌ Неактивен"
        category_display = product[5] or product[3]
        products_text += f"{product[1]}\n"
        products_text += f"💰 Цена: {product[2]} руб.\n"
        products_text += f"📂 Категория: {category_display}\n"
        products_text += f"📊 Статус: {status}\n"
        products_text += "─" * 30 + "\n"
    
    bot.send_message(message.chat.id, products_text)

@bot.message_handler(func=lambda message: message.text == '🔙 Назад')
def back_to_main(message):
    if is_admin(message.from_user.id):
        show_admin_menu(message.chat.id)

if __name__ == '__main__':
    print("Админ бот запущен...")
    bot.polling(none_stop=True)
 