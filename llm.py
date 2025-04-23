import os
import requests
from dotenv import load_dotenv
from typing import Dict, Any
import json

load_dotenv()

HUGGINGFACE_API_TOKEN = os.getenv("HF_API_TOKEN")
MODEL = "mistralai/Mistral-7B-Instruct-v0.1"

def serialize_response(response: Any) -> Dict[str, Any]:
    """Garantiza que la respuesta sea serializable a JSON"""
    try:
        if response is None:
            return {"output": "", "error": "Respuesta vacía", "status_code": 500}
        
        if isinstance(response, (str, int, float, bool)):
            return {"output": str(response), "error": None, "status_code": 200}
            
        if isinstance(response, dict):
            return {
                "output": json.dumps(response) if not isinstance(response.get("output"), str) else response.get("output", ""),
                "error": response.get("error"),
                "status_code": response.get("status_code", 200)
            }
            
        return {"output": str(response), "error": None, "status_code": 200}
    except Exception as e:
        return {"output": "", "error": f"Error de serialización: {str(e)}", "status_code": 500}

def ask_llm(prompt: str) -> Dict[str, Any]:
    """Versión ultra robusta con manejo completo de errores"""
    try:
        if not isinstance(prompt, str):
            raise ValueError("El prompt debe ser un string")
            
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

        response = requests.post(
            f"https://api-inference.huggingface.co/models/{MODEL}",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            error_msg = f"API Error {response.status_code}: {response.text[:200]}" if response.text else "Respuesta vacía de la API"
            return serialize_response({"error": error_msg, "status_code": response.status_code})

        try:
            api_response = response.json()
            generated_text = api_response[0].get("generated_text", "") if isinstance(api_response, list) else ""
            return serialize_response({"output": generated_text, "status_code": 200})
            
        except (IndexError, KeyError, AttributeError) as e:
            return serialize_response({"error": f"Error procesando respuesta: {str(e)}", "status_code": 500})

    except requests.exceptions.RequestException as e:
        return serialize_response({"error": f"Error de conexión: {str(e)}", "status_code": 503})
    except Exception as e:
        return serialize_response({"error": f"Error inesperado: {str(e)}", "status_code": 500})