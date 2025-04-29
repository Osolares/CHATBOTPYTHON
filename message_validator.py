from typing import Dict, Any
from config import db
from models import Log
from datetime import datetime
import json

class MessageValidator:
    """Validador universal de mensajes para todas las plataformas."""
    
    @classmethod
    def validate(cls, platform: str, message_data: dict) -> Dict[str, Any]:
        """
        Valida y estandariza mensajes entrantes de cualquier plataforma.
        
        Args:
            platform: "whatsapp", "telegram", "messenger", "web"
            message_data: Datos crudos del mensaje recibido
            
        Returns:
            Dict con estructura estandarizada:
            {
                "is_valid": bool,
                "platform": str,
                "user_id": str,  # phone, email, chat_id, etc.
                "message_content": str,
                "message_type": str,  # "text", "button", "list", etc.
                "raw_message": dict  # datos originales
            }
        """
        result = {
            "is_valid": False,
            "platform": platform,
            "user_id": None,
            "message_content": None,
            "message_type": None,
            "raw_message": message_data
        }
        
        try:
            if platform == "whatsapp":
                return cls._validate_whatsapp(message_data, result)
            elif platform == "telegram":
                return cls._validate_telegram(message_data, result)
            elif platform == "messenger":
                return cls._validate_messenger(message_data, result)
            elif platform == "web":
                return cls._validate_web(message_data, result)
                
        except Exception as e:
            error_msg = f"Validation error ({platform}): {str(e)}"
            cls._log_error(error_msg)
            
        return result
    
    @classmethod
    def _validate_whatsapp(cls, data: dict, result: dict) -> dict:
        """Valida mensajes de WhatsApp Business API."""
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        message = value.get("messages", [{}])[0]
        
        if not message.get("from"):
            return result
            
        result["user_id"] = message["from"]
        
        # Manejar diferentes tipos de mensaje
        message_type = message.get("type")
        if message_type == "text":
            result.update({
                "is_valid": True,
                "message_content": message.get("text", {}).get("body"),
                "message_type": "text"
            })
        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                result.update({
                    "is_valid": True,
                    "message_content": interactive.get("button_reply", {}).get("id"),
                    "message_type": "button"
                })
            elif interactive.get("type") == "list_reply":
                result.update({
                    "is_valid": True,
                    "message_content": interactive.get("list_reply", {}).get("id"),
                    "message_type": "list"
                })
                
        return result
    
    @classmethod
    def _validate_telegram(cls, data: dict, result: dict) -> dict:
        """Valida mensajes de Telegram."""
        if "message" not in data:
            # Puede ser una callback query
            if "callback_query" in data:
                callback = data["callback_query"]
                result.update({
                    "is_valid": True,
                    "user_id": str(callback.get("from", {}).get("id")),
                    "message_content": callback.get("data"),
                    "message_type": "callback"
                })
            return result
            
        message = data["message"]
        result["user_id"] = str(message.get("from", {}).get("id"))
        
        if "text" in message:
            result.update({
                "is_valid": True,
                "message_content": message["text"],
                "message_type": "text"
            })
        elif "data" in message:
            result.update({
                "is_valid": True,
                "message_content": message["data"],
                "message_type": "callback"
            })
            
        return result
    
    @classmethod
    def _validate_messenger(cls, data: dict, result: dict) -> dict:
        """Valida mensajes de Facebook Messenger."""
        entry = data.get("entry", [{}])[0]
        messaging = entry.get("messaging", [{}])[0]
        
        if "message" not in messaging or "text" not in messaging["message"]:
            return result
            
        result.update({
            "is_valid": True,
            "user_id": messaging.get("sender", {}).get("id"),
            "message_content": messaging["message"]["text"],
            "message_type": "text"
        })
        
        return result
    
    @classmethod
    def _validate_web(cls, data: dict, result: dict) -> dict:
        """Valida mensajes del chat web."""
        if not data.get("message") or not data.get("email"):
            return result
            
        result.update({
            "is_valid": True,
            "user_id": data["email"],
            "message_content": data["message"],
            "message_type": "text"
        })
        
        return result
    
    @staticmethod
    def _log_error(error_msg: str):
        """Registra errores de validación."""
        try:
            with db.session.begin():
                log = Log(texto=error_msg)
                db.session.add(log)
        except Exception as e:
            pass  # Fallback silencioso