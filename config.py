from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
from dotenv import load_dotenv
import pytz

GUATEMALA_TZ = pytz.timezone("America/Guatemala")
def hora_guatemala():
    from datetime import datetime
    return datetime.now(GUATEMALA_TZ)

# Cargar variables de entorno
load_dotenv()

db = SQLAlchemy()
migrate = Migrate()

class Config:
    # Database
    SQLALCHEMY_DATABASE_URI = 'sqlite:///autoparts_chatbot.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    #TOKEN_WHATSAPP = "TOKEN_OIOT"  # Mueve el token aquí

    # WooCommerce
    WOOCOMMERCE_URL = os.getenv('WOOCOMMERCE_URL')
    WOOCOMMERCE_KEY = os.getenv('WOOCOMMERCE_KEY')
    WOOCOMMERCE_SECRET = os.getenv('WOOCOMMERCE_SECRET')
    
    # WhatsApp
    WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN')
    PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')
    TOKEN_WEBHOOK_WHATSAPP = os.getenv('TOKEN_WEBHOOK_WHATSAPP')

    # Telegram
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    
    # Messenger
    FB_PAGE_TOKEN = os.getenv('FB_PAGE_TOKEN')
    FB_VERIFY_TOKEN = os.getenv('FB_VERIFY_TOKEN')
    
    # Web
    WEB_SECRET_KEY = os.getenv('WEB_SECRET_KEY')