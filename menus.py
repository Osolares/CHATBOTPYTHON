def generar_list_menu(number):
    #"""Retorna la estructura del botón 'Ver Menú' para reutilizar"""
    return {
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": "Menú Principal"
            },
            "footer": {
                "text": ""
            },
            "action": {
                "button": "Ver Menú",
                "sections": [
                    {
                        "title": "Opciones Principales",
                        "rows": [
                            {"id": "1", "title": "1️⃣ ⚙Motores", "description": "Cotizar Motores"},
                            {"id": "2", "title": "2️⃣ 🛞Repuestos", "description": "Cotizar Repuestos"},
                            {"id": "3", "title": "3️⃣ 📍Ubicación", "description": "Dónde estamos ubicados"},
                            {"id": "4", "title": "4️⃣ 🕜Horario", "description": "Horario de atención"},
                            {"id": "5", "title": "5️⃣ ☎Contacto", "description": "Contáctanos"},
                            {"id": "6", "title": "6️⃣ 💳Cuentas y Pagos", "description": "Cuentas de banco y formas de pago"},
                            {"id": "7", "title": "7️⃣ ⏳Hablar con personal", "description": "Esperar para ser atendido por nuestro personal"},
                            {"id": "8", "title": "8️⃣ 🚛Envíos", "description": "Opciones de envío"}
                        ]
                    }
                ]
            }
        }
    }

def generar_menu_principal(number):
    """Retorna la estructura del botón 'Ver Menú' para reutilizar"""
    return {
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": "🌐 Visita nuestro sitio web www.intermotores.com para más información.\n\n1️⃣ ⚙ Motores\n2️⃣ 🛞 Repuestos\n3️⃣ 📍 Ubicación\n4️⃣ 🕜 Horario de Atención\n5️⃣ ☎ Contacto\n6️⃣  💳 Formas de pago y números de cuenta\n7️⃣ ⏳ Esperar para ser atendido por nuestro personal\n8️⃣ 🚛 Opciones de envío\n0️⃣ 🔙 Regresar al Menú \n\n📌 *Escribe el número #️⃣ de tu elección.*"
            },
            "footer": {
                "text": ""
            },
            "action": {
                "button": "Ver Menú",
                "sections": [
                    {
                        "title": "Opciones Principales",
                        "rows": [
                            {"id": "1", "title": "1️⃣ ⚙Corizar Motores y Repuestos", "description": "Llenar el formuilario para cotizar"},
                            {"id": "2", "title": "2️⃣ 📣Ofertas!!!...", "description": "Ofertas recientes"},
                            {"id": "3", "title": "3️⃣ 📍Ubicación", "description": "Dónde estamos ubicados"},
                            {"id": "4", "title": "4️⃣ 🕜Horario", "description": "Horario de atención"},
                            {"id": "5", "title": "5️⃣ ☎Contacto", "description": "Contáctanos"},
                            {"id": "6", "title": "6️⃣ 💳Cuentas y Pagos", "description": "Cuentas de banco y formas de pago"},
                            {"id": "7", "title": "7️⃣ ⏳Hablar con personal", "description": "Esperar para ser atendido por nuestro personal"},
                            {"id": "8", "title": "8️⃣ 🚛Envíos", "description": "Opciones de envío"}
                            ]
                    }
                ]
            }
        }
    }
