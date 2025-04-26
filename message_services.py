from typing import Dict, Any, Optional
from config import db, Config
from models import UserSession, PlatformMessage
from datetime import datetime
import requests
import json
import http.client

class MessageService:
    @staticmethod
    def get_or_create_user(identifier: Dict[str, str]) -> UserSession:
        """Obtiene o crea usuario basado en identificador de plataforma"""
        platform = identifier['platform']
        with db.session.begin():
            if platform in ['whatsapp', 'telegram']:
                user = db.session.query(UserSession).filter_by(
                    phone_number=identifier['phone']
                ).first()
            elif platform == 'messenger':
                user = db.session.query(UserSession).filter_by(
                    fb_user_id=identifier['fb_user_id']
                ).first()
            elif platform == 'web':
                user = db.session.query(UserSession).filter_by(
                    email=identifier['email']
                ).first()
            
            if not user:
                user = UserSession(
                    phone_number=identifier.get('phone'),
                    email=identifier.get('email'),
                    fb_user_id=identifier.get('fb_user_id'),
                    last_platform=platform
                )
                db.session.add(user)
                db.session.flush()
            
            user.last_platform = platform
            user.last_interaction = datetime.utcnow()
        
        return user

    @staticmethod
    def send_message(response_data: Dict[str, Any], platform: str, user: UserSession):
        """Envía mensaje por la plataforma adecuada"""
        if platform == 'whatsapp':
            WhatsAppService.send_message(response_data)
        elif platform == 'telegram':
            TelegramService.send_message(response_data, user)
        elif platform == 'messenger':
            MessengerService.send_message(response_data, user)
        elif platform == 'web':
            WebService.send_message(response_data, user)

class WhatsAppService:
    @staticmethod
    def send_message(data: Dict[str, Any]):
        """Envía mensaje a WhatsApp (existente)"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"{Config.WHATSAPP_TOKEN}"
        }
        
        try:
            connection = http.client.HTTPSConnection("graph.facebook.com")
            json_data = json.dumps(data)
            connection.request("POST", f"/v22.0/{Config.PHONE_NUMBER_ID}/messages", json_data, headers)
            response = connection.getresponse()
            return response.read()
        except Exception as e:
            agregar_mensajes_log(f"Error enviando a WhatsApp: {str(e)}")
            return None
        finally:
            connection.close()

class TelegramService:
    @staticmethod
    def send_message(data: Dict[str, Any], user: UserSession):
        """Envía mensaje a Telegram"""
        try:
            message = data.get('text', {}).get('body', '')
            payload = {
                'chat_id': user.phone_number,  # Usamos phone_number como chat_id
                'text': message
            }
            response = requests.post(
                f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage",
                json=payload
            )
            return response.json()
        except Exception as e:
            agregar_mensajes_log(f"Error enviando a Telegram: {str(e)}")

class MessengerService:
    @staticmethod
    def send_message(data: Dict[str, Any], user: UserSession):
        """Envía mensaje a Messenger"""
        try:
            message = data.get('text', {}).get('body', '')
            payload = {
                'recipient': {'id': user.fb_user_id},
                'message': {'text': message}
            }
            response = requests.post(
                f"https://graph.facebook.com/v18.0/me/messages?access_token={Config.FB_PAGE_TOKEN}",
                json=payload
            )
            return response.json()
        except Exception as e:
            agregar_mensajes_log(f"Error enviando a Messenger: {str(e)}")

class WebService:
    @staticmethod
    def send_message(data: Dict[str, Any], user: UserSession):
        """Envía mensaje al sitio web (ejemplo: WebSocket)"""
        try:
            # Implementación depende de tu sistema web
            pass
        except Exception as e:
            agregar_mensajes_log(f"Error enviando al sitio web: {str(e)}")