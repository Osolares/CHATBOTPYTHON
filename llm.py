import os
import requests
from dotenv import load_dotenv
from typing import Dict, Any
import json

load_dotenv()

HUGGINGFACE_API_TOKEN = os.getenv("HF_API_TOKEN")
MODEL = "mistralai/Mistral-7B-Instruct-v0.1"

def ask_llm(prompt: str) -> Dict[str, Any]:
    """
    Consulta el modelo LLM y devuelve una respuesta estandarizada y serializable.
    
    Args:
        prompt: Texto de entrada para el modelo
        
    Returns:
        Dict: {'output': str, 'error': Optional[str], 'status_code': int}
    """
    headers = {
        "Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": f"[INST] {prompt} [/INST]",
        "parameters": {
            "temperature": 0.7,
            "max_new_tokens": 300,
            "return_full_text": False
        }
    }

    try:
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{MODEL}",
            headers=headers,
            json=payload,
            timeout=30  # Añadir timeout para evitar bloqueos
        )

        if response.status_code == 200:
            # Asegurar que la respuesta sea serializable
            generated_text = response.json()[0].get("generated_text", "")
            return {
                "output": str(generated_text),  # Convertir a string para seguridad
                "error": None,
                "status_code": 200
            }
        else:
            error_msg = f"Error en API: {response.status_code} - {response.text[:200]}"
            return {
                "output": None,
                "error": error_msg,
                "status_code": response.status_code
            }

    except requests.exceptions.RequestException as e:
        return {
            "output": None,
            "error": f"Error de conexión: {str(e)}",
            "status_code": 500
        }
    except Exception as e:
        return {
            "output": None,
            "error": f"Error inesperado: {str(e)}",
            "status_code": 500
        }