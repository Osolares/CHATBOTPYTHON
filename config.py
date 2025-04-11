from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

db = SQLAlchemy()
migrate = Migrate()

class Config:
    # Database
    SQLALCHEMY_DATABASE_URI = 'sqlite:///autoparts_chatbot.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TOKEN_WHATSAPP = "TOKEN_OIOT"  # Mueve el token aquí

    # WooCommerce
    WOOCOMMERCE_URL = os.getenv('WOOCOMMERCE_URL')
    WOOCOMMERCE_KEY = os.getenv('WOOCOMMERCE_KEY')
    WOOCOMMERCE_SECRET = os.getenv('WOOCOMMERCE_SECRET')
    
    # WhatsApp
    WHATSAPP_TOKEN = os.getenv('Bearer EAASuhuwPLvsBOyi4z4jqFSEjK6LluwqP7ZBUI5neqElC0PhJ5VVmTADzVlkjZCm9iCFjcztQG0ONSKpc1joEKlxM5oNEuNLXloY4fxu9jZCCJh4asEU4mwZAo9qZC5aoQAFXrb2ZC8fsIfcq5u1K90MTBrny375KAHHTG4SFMz7eXM1dbwRiBhqGhOxNtFBmVTwQZDZD')
    PHONE_NUMBER_ID = os.getenv('641730352352096')
    TOKEN_WEBHOOK_WHATSAPP = os.getenv('TOKEN_OIOT')
