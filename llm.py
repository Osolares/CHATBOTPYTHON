import os
import requests
from dotenv import load_dotenv

load_dotenv()  # Carga variables de entorno desde .env

HUGGINGFACE_API_TOKEN = os.getenv("HF_API_TOKEN")
MODEL = "mistralai/Mistral-7B-Instruct-v0.1"  # Modelo a usar

def ask_llm(prompt):
    headers = {
        "Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": f"[INST] {prompt} [/INST]",  # Formato instruct para Mistral
        "parameters": {
            "temperature": 0.7,  # Controla la creatividad (0-1)
            "max_new_tokens": 300,  # Longitud máxima de respuesta
            "return_full_text": False  # No devolver el prompt
        }
    }

    response = requests.post(
        f"https://api-inference.huggingface.co/models/{MODEL}",
        headers=headers,
        json=payload
    )

    if response.status_code == 200:
        return response.json()[0]["generated_text"]
    else:
        print("Error Hugging Face:", response.text)
        return "Hubo un error al consultar el modelo."