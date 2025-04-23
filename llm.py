import os
import requests
from dotenv import load_dotenv
from typing import Dict, Any
import json

load_dotenv()

HUGGINGFACE_API_TOKEN = os.getenv("HF_API_TOKEN")
MODEL = "google/flan-t5-small" 

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
    try:
        if not isinstance(prompt, str):
            raise ValueError("El prompt debe ser un string")
            
        headers = {
            "Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = {
            "inputs": prompt,
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

        if response.status_code == 200:
            response_data = response.json()
            # Asegurar serialización incluso si la estructura cambia
            if isinstance(response_data, list) and len(response_data) > 0:
                output = str(response_data[0].get("generated_text", ""))
            else:
                output = str(response_data.get("generated_text", "")) if isinstance(response_data, dict) else str(response_data)
            
            return {
                "output": output,
                "error": None,
                "status_code": 200
            }
        else:
            error_msg = f"API Error {response.status_code}"
            if response.text:
                try:
                    error_details = response.json()
                    error_msg += f": {str(error_details.get('error', response.text[:200]))}"
                except:
                    error_msg += f": {response.text[:200]}"
            
            return {
                "output": None,
                "error": error_msg,
                "status_code": response.status_code
            }

    except Exception as e:
        return {
            "output": None,
            "error": f"Error inesperado: {str(e)}",
            "status_code": 500
        }