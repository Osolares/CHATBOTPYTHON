from flask import Flask, request, jsonify, render_template
from config import app, db
from models import UserSession, Log, init_db
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import http.client
import json
import time

# Inicializar DB
with app.app_context():
    init_db()

app = Flask(__name__)

#Funcion para ordenar los registros por fecha y hora
def ordenar_por_fecha_y_hora(registros):
    return sorted(registros, key=lambda x: x.fecha_y_hora,reverse=True)

@app.route('/')
def index():
    registros = Log.query.order_by(Log.fecha_y_hora.desc()).all()
    return render_template('index.html', registros=registros)

mensajes_log = []

#Funcion para agregar mensajes y guardar en la base de datos
def agregar_mensajes_log(texto):
    mensajes_log.append(texto)

    #Guardar el mensaje en la base de datos
    nuevo_registro = Log(texto=texto)
    db.session.add(nuevo_registro)
    db.session.commit()

#Token de verificacion para la configuracion
TOKEN_WHATSAPP = "TOKEN_OIOT"

@app.route('/webhook', methods=['GET','POST'])
def webhook():
    if request.method == 'GET':
        challenge = verificar_token(request)
        return challenge
    elif request.method == 'POST':
        reponse = recibir_mensajes(request)
        return reponse

def verificar_token(req):
    token = req.args.get('hub.verify_token')
    challenge = req.args.get('hub.challenge')

    if challenge and token == TOKEN_WHATSAPP:
        return challenge
    else:
        return jsonify({'error':'Token Invalido'}),401

def recibir_mensajes(req):
    try:
        data = request.get_json()

        if not data or 'entry' not in data:
            agregar_mensajes_log("Error: JSON sin 'entry'")
            return jsonify({'message': 'EVENT_RECEIVED'})

        entry = data['entry'][0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        messages_list = value.get('messages', [])

        if messages_list:
            message = messages_list[0]
            numero = message.get("from")

            # Guardar log
            agregar_mensajes_log(json.dumps(message))

            msg_type = message.get("type")

            if msg_type == "interactive":
                interactive = message.get("interactive", {})
                tipo_interactivo = interactive.get("type")

                if tipo_interactivo == "button_reply":
                    text = interactive.get("button_reply", {}).get("id")
                    if text:
                        enviar_mensajes_whatsapp(text, numero)

                elif tipo_interactivo == "list_reply":
                    text = interactive.get("list_reply", {}).get("id")
                    if text:
                        enviar_mensajes_whatsapp(text, numero)

            elif msg_type == "text":
                text = message.get("text", {}).get("body")
                if text:
                    enviar_mensajes_whatsapp(text, numero)

        return jsonify({'message': 'EVENT_RECEIVED'})

    except Exception as e:
        agregar_mensajes_log(f"Error en recibir_mensajes: {str(e)}")
        return jsonify({'message': 'EVENT_RECEIVED'})


def bot_enviar_mensaje_whatsapp(data):
    headers = {
        "Content-Type" : "application/json",
        "Authorization" : "Bearer EAASuhuwPLvsBOyi4z4jqFSEjK6LluwqP7ZBUI5neqElC0PhJ5VVmTADzVlkjZCm9iCFjcztQG0ONSKpc1joEKlxM5oNEuNLXloY4fxu9jZCCJh4asEU4mwZAo9qZC5aoQAFXrb2ZC8fsIfcq5u1K90MTBrny375KAHHTG4SFMz7eXM1dbwRiBhqGhOxNtFBmVTwQZDZD"
    }
    
    connection = http.client.HTTPSConnection("graph.facebook.com")
    try:
        #Convertir el diccionaria a formato JSON
        json_data = json.dumps(data)
        connection.request("POST", "/v22.0/641730352352096/messages", json_data, headers)
        response = connection.getresponse()
        print(f"Estado: {response.status} - {response.reason}")
        return response.read()
    except Exception as e:
        agregar_mensajes_log(json.dumps(e))
        return None
    finally:
        connection.close()


def enviar_mensajes_whatsapp(texto,number):
    texto = texto.lower()

    if "hola" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "image",
                "image": {
                    "link": "https://intermotores.com/wp-content/uploads/2025/04/LOGO_INTERMOTORES.png"
                }
            },
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "👋 Gracias por comunicarse con nostros, es un placer atenderle 👨‍💻"
                }
            }
        ]
    elif "1" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "Estos son nuestros motores"
                }
            }
        ]
    elif "2" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "Estos son nuestros productos"
                }
            }
        ]
    elif "3" in texto:        
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "location",
                "location": {
                    "latitude": "14.564777",
                    "longitude": "-90.466011",
                    "name": "Intermotores",  # Nombre sin formato (texto plano)
                    "address": "Importadora Internacional de Motores Japoneses, s.a."
                }
            },
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "📍  Estamos ubicados en km 13.5 carretera a El Salvador frente a Plaza Express a un costado de farmacia Galeno, en Intermotores"
                }
            }
        ]
    elif "4" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "📅 Horario de Atención: \n\n Lunes a Viernes. \n🕜 Horario : 8:00 am a 5:00 pm \n\n Sábado. \n🕜 Horario : 8:00 am a 12:00 pm \n\n Domingo. Cerrado 🤓"
                }
            }
        ]
    elif "5" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "image",
                "image": {
                    "link": "https://intermotores.com/wp-content/uploads/2025/04/numeros_de_cuenta_intermotores.jpg"
                }
            }
        ]
    elif "6" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "🤝 Gracias por esperar es un placer atenderle, indíquenos *¿cómo podemos apoyarle?* pronto será atendido por nuestro personal de atención al cliente. 🤓"
                }
            }
        ]
    elif "7" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "🏠🛋*Enviamos nuestros productos hasta la puerta de su casa*, estos son nuestros métodos de envío: \n\n 🛵 Envíos dentro de la capital. \n Hacemos envíos directos dentro de la ciudad capital, aldea Puerta Parada, Santa Catarina Pinula y sus alrededores \n\n 🚚 Envío a Departamentos. \nHacemos envíos a los diferentes departamentos del país por medio de terceros o empresas de transporte como Guatex, Cargo Express, Forza o el de su preferencia. \n\n ⏳📦 Tiempo de envío. \nLos pedidos deben hacerse con 24 horas de anticipación y el tiempo de entrega para los envíos directos es de 24 a 48 horas y para los envíos a departamentos depende directamente de la empresa encargarda."}
            }
        ]
    elif "0" in texto:
        data = [
            # 📝 Texto normal del menú
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "🌐 Visita nuestro sitio web www.intermotores.com para más información.\n\n📌 *Por favor, ingresa un número #️⃣ para recibir información.*\n\n1️⃣ ⚙ Motores\n\n2️⃣ 🛞 Repuestos\n\n3️⃣ 📍 Ubicación\n\n4️⃣ 🕜 Horario de Atención\n\n5️⃣ 💳 Números de cuenta\n\n6️⃣ ⏳ Esperar para ser atendido por nuestro personal\n\n7️⃣ 🚛 Opciones de envío\n\n0️⃣ 🔙 Regresar al Menú"
                }
            },

            # 📋 Lista interactiva
            {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {
                        "text": "Selecciona una opción del menú:"
                    },
                    "footer": {
                        "text": "Toca una opción para continuar"
                    },
                    "action": {
                        "button": "Ver Menú",
                        "sections": [
                            {
                                "title": "Opciones Principales",
                                "rows": [
                                    {"id": "btn1", "title": "1️⃣ Motores", "description": "Información sobre motores"},
                                    {"id": "btn2", "title": "2️⃣ Repuestos", "description": "Repuestos disponibles"},
                                    {"id": "btn3", "title": "3️⃣ Ubicación", "description": "Dónde estamos ubicados"},
                                    {"id": "btn4", "title": "4️⃣ Horario", "description": "Horario de atención"},
                                    {"id": "btn5", "title": "5️⃣ Cuentas", "description": "Datos bancarios"},
                                    {"id": "btn6", "title": "6️⃣ Hablar con personal", "description": "Conectarte con alguien"},
                                    {"id": "btn7", "title": "7️⃣ Envíos", "description": "Opciones de envío"}
                                ]
                            }
                        ]
                    }
                }
            },

            # 🔘 Botones interactivos
            {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": "Selecciona una opción rápida:"
                    },
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "btn1", "title": "1️⃣ Motores"}},
                            {"type": "reply", "reply": {"id": "btn2", "title": "2️⃣ Repuestos"}},
                            {"type": "reply", "reply": {"id": "btn3", "title": "3️⃣ Ubicación"}}
                        ]
                    }
                }
            }
        ]
    elif "boton" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "interactive",
                "interactive":{
                    "type":"button",
                    "body": {
                        "text": "¿Confirmas tu registro?"
                    },
                    "footer": {
                        "text": "Selecciona una de las opciones"
                    },
                    "action": {
                        "buttons":[
                            {
                                "type": "reply",
                                "reply":{
                                    "id":"btnsi",
                                    "title":"👋Si"
                                }
                            },{
                                "type": "reply",
                                "reply":{
                                    "id":"btnno",
                                    "title":"👋No"
                                }
                            },{
                                "type": "reply",
                                "reply":{
                                    "id":"btntalvez",
                                    "title":"Tal Vez"
                                }
                            }
                        ]
                    }
                }
            }
        ]
    elif "btnsi" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "Muchas Gracias por Aceptar."
                }
            }
        ]
    elif "btnno" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "Es una Lastima."
                }
            }
        ]
    elif "btntalvez" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "Estare a la espera."
                }
            }
        ]
    elif "lista" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "interactive",
                "interactive":{
                    "type" : "list",
                    "body": {
                        "text": "Selecciona Alguna Opción"
                    },
                    "footer": {
                        "text": "Selecciona una de las opciones para poder ayudarte"
                    },
                    "action":{
                        "button":"Ver Opciones",
                        "sections":[
                            {
                                "title":"Compra y Venta",
                                "rows":[
                                    {
                                        "id":"btncompra",
                                        "title" : "Comprar",
                                        "description": "Compra los mejores articulos de tecnologia"
                                    },
                                    {
                                        "id":"btnvender",
                                        "title" : "Vender",
                                        "description": "Vende lo que ya no estes usando"
                                    }
                                ]
                            },{
                                "title":"Distribución y Entrega",
                                "rows":[
                                    {
                                        "id":"btndireccion",
                                        "title" : "Local",
                                        "description": "Puedes visitar nuestro local."
                                    },
                                    {
                                        "id":"btnentrega",
                                        "title" : "Entrega",
                                        "description": "La entrega se realiza todos los dias."
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        ]
    elif "btncompra" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "Los mejos articulos top en ofertas."
                }
            }
        ]
    elif "btnvender" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "Excelente elección."
                }
            }
        ]
    else:
        data= [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "🌐 Visita nuestro sitio web www.intermotores.com para más información.\n \n📌*Por favor, ingresa un número #️⃣ para recibir información.*\n \n1️⃣ ⚙Motores. \n\n2️⃣ 🛞Repuestos. \n\n3️⃣ 📍Ubicación. \n\n4️⃣ 🕜Horario de Atención. \n\n5️⃣ 💳Números de cuenta. \n\n6️⃣ ⏳Esperar para ser atendido por nuestro personal. \n\n7️⃣ 🚛Opciones de envío. \n\n0️⃣ 🔙Regresar al Menú. \n"
                }
            }
        ]

    # Envío secuencial con pausas
    for mensaje in data:
        bot_enviar_mensaje_whatsapp(mensaje)
        time.sleep(1)  # Pausa para cumplir con rate limits de WhatsApp

if __name__=='__main__':
    app.run(host='0.0.0.0',port=80,debug=True)