import os
from datetime import datetime

class Config:
    SECRET_KEY = 'your-secret-key-here'
    DATABASE_PATH = 'data/database.db'
    TELEGRAM_BOT_TOKEN = '8219066244:AAF5hoeQgMLvD4_RcW4SAV4zHtO7pMopS7Y'
    ADMIN_USER_ID = 8430108389  # Ваш Telegram ID
    
    # Настройки кешбека
    CASHBACK_RATE = 0.03  # 3%
    
    # Настройки сайта
    SITE_NAME = "VapeCloud"
    SITE_DESCRIPTION = "Лучший магазин вейпов и электронных сигарет"
    
    # Для Telegram Mini Apps
    BOT_USERNAME = 'VapeCloudShopBot'  # Замените на реальный username бота