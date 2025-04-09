from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import http.client
import json
import time

app = Flask(__name__)

#Configuracion de la base de datos SQLITE
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///metapython.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db =SQLAlchemy(app)


#Modelo de la tabla log
class Log(db.Model):
    id = db.Column(db.Integer,primary_key=True)
    fecha_y_hora = db.Column(db.DateTime, default=datetime.utcnow)
    texto = db.Column(db.TEXT)

#Crear la tabla si no existe
with app.app_context():
    db.create_all()

#Funcion para ordenar los registros por fecha y hora
def ordenar_por_fecha_y_hora(registros):
    return sorted(registros, key=lambda x: x.fecha_y_hora,reverse=True)

@app.route('/')
def index():
    #obtener todos los registros de la base de datos
    registros = Log.query.all()
    registros_ordenados = ordenar_por_fecha_y_hora(registros)
    return render_template('index.html',registros=registros_ordenados)

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
        req = request.get_json()
        entry =req['entry'][0]
        changes = entry['changes'][0]
        value = changes['value']
        objeto_mensaje = value['messages']

        if objeto_mensaje:
            messages = objeto_mensaje[0]

            if "type" in messages:
                tipo = messages["type"]

                #Guardar Log en la BD
                agregar_mensajes_log(json.dumps(messages))

                if tipo == "interactive":
                    tipo_interactivo = messages["interactive"]["type"]

                    if tipo_interactivo == "button_reply":
                        text = messages["interactive"]["button_reply"]["id"]
                        numero = messages["from"]

                        enviar_mensajes_whatsapp(text,numero)
                    
                    elif tipo_interactivo == "list_reply":
                        text = messages["interactive"]["list_reply"]["id"]
                        numero = messages["from"]

                        enviar_mensajes_whatsapp(text,numero)

                if "text" in messages:
                    text = messages["text"]["body"]
                    numero = messages["from"]

                    enviar_mensajes_whatsapp(text,numero)

                    #Guardar Log en la BD
                    agregar_mensajes_log(json.dumps(messages))

        return jsonify({'message':'EVENT_RECEIVED'})
    except Exception as e:
        return jsonify({'message':'EVENT_RECEIVED'})

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
                    "body": "🤝 Dame una breve descripción de la falla. 🤓"
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
                    "body": "📅 *Estos son nuestros métodos de envío:* \n\n Envíos en la capital. \n🕜 Horario : 8:00 am a 5:00 pm \n\n Envío al exterior. \n🕜 Horario : 8:00 am a 12:00 pm \n\n Pago contra entrega. Cerrado 🤓"
                }
            }
        ]
    elif "0" in texto:
        data = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "🚀👋 Hola, visita nuestro sitio web www.intermotores.com 🌐 para más información.\n \n📌*Por favor, ingresa un número #️⃣ para recibir información.*\n \n1️⃣. ⚙Motores. \n2️⃣. 🛞Repuestos. \n3️⃣. 📍Ubicación. \n4️⃣. 🕜Horario de Atención. \n5️⃣. 💳Números de cuenta. \n6️⃣. 🛎Reportar Garantía. \n7️⃣. 🚛Formas de envío. \n0️⃣. 🔙Regresar al Menú. \n"
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
                    "body": "🚀👋 Hola, visita nuestro sitio web www.intermotores.com 🌐 para más información.\n \n📌*Por favor, ingresa un número #️⃣ para recibir información.*\n \n1️⃣. ⚙Motores. \n2️⃣. 🛞Repuestos. \n3️⃣. 📍Ubicación. \n4️⃣. 🕜Horario de Atención. \n5️⃣. 💳Números de cuenta. \n6️⃣. 🛎Reportar Garantía. \n7️⃣. 🚛Formas de envío. \n0️⃣. 🔙Regresar al Menú. \n"
                }
            }
        ]

    # Envío secuencial con pausas
    for mensaje in data:
        bot_enviar_mensaje_whatsapp(mensaje)
        time.sleep(1)  # Pausa para cumplir con rate limits de WhatsApp

if __name__=='__main__':
    app.run(host='0.0.0.0',port=80,debug=True)