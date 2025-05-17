import requests
from config import Config
from datetime import datetime
import random
import re
from html import unescape
#from catalog_service import get_woocommerce

class WooCommerceService:
    def __init__(self):
        self.base_url = f"{Config.WOOCOMMERCE_URL}/wp-json/wc/v3"
        self.auth = (Config.WOOCOMMERCE_KEY, Config.WOOCOMMERCE_SECRET)
    
    def obtener_ofertas_recientes(self, limite=5):
        """Obtiene productos en oferta de WooCommerce y los mezcla aleatoriamente"""
        try:
            params = {
                'on_sale': 'true',
                'status': 'publish',
                'per_page': 20,  # Traer más para poder mezclar
                '_fields': 'id,name,price,regular_price,sale_price,description,short_description,date_on_sale_to,permalink,images'
            }
            
            response = requests.get(
                f"{self.base_url}/products",
                params=params,
                auth=self.auth
            )
            response.raise_for_status()
            productos = response.json()
            random.shuffle(productos)  # Mezclar aleatoriamente
            return productos[:limite]
        
        except Exception as e:
            print(f"Error al obtener ofertas: {str(e)}")
            return []

    def formatear_ofertas_whatsapp(self, productos):
        """Formatea los productos para mensajes de WhatsApp con saltos de línea y detalles estructurados"""
        if not productos:
            return ["📢 No hay ofertas disponibles en este momento."]

        mensajes = []
        for producto in productos[:3]:  # Limitar a 5 productos
            try:
                nombre = producto.get('name', 'Producto sin nombre')
                precio = producto.get('price', 'Precio no disponible')
                precio_normal = producto.get('regular_price') or precio
                precio_oferta = producto.get('sale_price', '')
                sku = producto.get('sku', 'N/A')
                stock = producto.get('stock_status', 'N/A')
                enlace = producto.get('permalink', 'https://intermotores.com')
                imagen = producto.get('images', [{}])[0].get('src', '')
                descripcion_corta = producto.get('short_description', '')
                descripcion_larga = producto.get('description', '')
                fecha_oferta = producto.get('date_on_sale_to')  # formato ISO

                # Limpiar HTML y decodificar entidades
                def limpiar_html(texto):
                    texto = re.sub(r'<br\s*/?>', '\n', texto)
                    texto = re.sub(r'<.*?>', '', texto)
                    texto = unescape(texto)
                    return texto.strip()

                descripcion_corta = limpiar_html(descripcion_corta)
                descripcion_larga = limpiar_html(descripcion_larga)

                # Limitar descripción larga a 500 caracteres sin cortar palabras
                if len(descripcion_larga) > 500:
                    corte = descripcion_larga[:500].rfind(' ')
                    descripcion_larga = descripcion_larga[:corte] + '...'

                # Formato de fecha si existe
                fecha_oferta_texto = ''
                if fecha_oferta:
                    try:
                        fecha_dt = datetime.fromisoformat(fecha_oferta)
                        if fecha_dt > datetime.now():
                            fecha_oferta_texto = f"\n🗓 Oferta válida hasta: {fecha_dt.strftime('%d/%m/%Y')}"
                    except:
                        pass

                mensaje = (
                    f"🔩⚙ *{nombre}* ⚙🔩\n\n"
                    f"📝 *Descripción:*\n{descripcion_corta}\n\n"
                    f"🔗 Puedes ver imágenes y más información en el siguiente LINK:\n{enlace}\n\n"
                    f"💲 Precio: Q{precio_normal}"
                )

                if precio_oferta:
                    mensaje += f"\n💥🏷 *Súper Oferta (Efectivo):* Q{precio_oferta}"

                if fecha_oferta_texto:
                    mensaje += fecha_oferta_texto

                mensaje += (
                    #f"\n\n🌟 *Detalles:*\n{descripcion_larga}\n\n"
                    f"🚚 Envío a domicilio\n"
                    f"🤝 Pago contra entrega (solamente repuestos)\n"
                    f"💳 Aceptamos todas las tarjetas de crédito sin recargo  (Precio Normal)\n\n"
                    f"⚠️ *Nota:* Los precios y disponibilidad pueden cambiar en cualquier momento sin previo aviso."
                )

                #if imagen:
                #    mensaje += f"\n\n📷 {imagen}"

                mensajes.append(mensaje)
            except Exception as e:
                print(f"Error formateando producto: {str(e)}")
                continue

        return mensajes if mensajes else ["📢 No se pudieron cargar las ofertas"]

    def limpiar_html(self, texto):
        """Elimina etiquetas HTML simples del texto"""
        import re
        return re.sub(r'<[^>]*>', '', texto).strip()


    def obtener_producto_por_url(self, url_producto):
        try:
            page = 1
            while True:
                response = requests.get(
                    f"{self.base_url}/products",
                    params={'status': 'publish', 'per_page': 100, 'page': page},
                    auth=self.auth
                )
                response.raise_for_status()
                productos = response.json()

                if not productos:
                    break

                for prod in productos:
                    if prod.get('permalink') == url_producto:
                        return prod

                page += 1
            return None
        except Exception as e:
            print(f"Error buscando producto por URL: {str(e)}")
            return None

    def buscar_producto_por_nombre(self, nombre_producto):
        try:
            # Limpiar el nombre del producto para buscar
            nombre_limpio = re.sub(r'[^\w\s]', '', nombre_producto).strip()
            palabras_clave = nombre_limpio.split()[:5]  # Tomar las primeras 5 palabras como máximo

            # Buscar por cada palabra clave
            for palabra in palabras_clave:
                if len(palabra) < 3:  # Ignorar palabras muy cortas
                    continue

                response = requests.get(
                    f"{self.base_url}/products",
                    params={
                        'search': palabra,
                        'per_page': 5,  # Limitar resultados
                        'status': 'publish',
                        '_fields': 'id,name,price,regular_price,description,short_description,date_on_sale_to,permalink,images,stock_status,stock_quantity'
                    },
                    auth=self.auth
                )
                response.raise_for_status()
                productos = response.json()

                # Buscar coincidencia más cercana
                for prod in productos:
                    prod_name = prod.get('name', '').lower()
                    if nombre_limpio.lower() in prod_name or prod_name in nombre_limpio.lower():
                        return prod

            return None
        except Exception as e:
            print(f"Error buscando producto por nombre: {str(e)}")
            return None

    def formatear_producto_whatsapp(self, producto):
        try:
            nombre = producto.get('name', 'Producto sin nombre')
            precio = producto.get('price', 'N/A')
            precio_normal = producto.get('regular_price') or precio
            precio_oferta = producto.get('sale_price', '')
            descripcion = self.limpiar_html(producto.get('short_description') or producto.get('description', ''))
            enlace = producto.get('permalink', '')
            fecha_oferta = producto.get('date_on_sale_to')
            stock_status = producto.get('stock_status', 'instock')
            stock_quantity = producto.get('stock_quantity', 0)


            mensaje = f"🔩⚙ *{nombre}* ⚙🔩\n\n"

            if descripcion:
                mensaje += f"📝 *Descripción:*\n{descripcion}\n\n"

            mensaje += f"🔗 Ver más detalles aquí:\n{enlace}\n\n"
            # Manejo de stock
            if stock_status == 'outofstock' or stock_quantity <= 0:
                mensaje += "⚠️ *ESTADO:* AGOTADO\n\n Lo sentimos ya no contamos con este repuesto"
                #mensaje += "💲 *Precio normal:* Q{precio_normal}\n\n"
                mensaje += "📦 *Disponibilidad:* Puede consultarnos cuándo estará disponible\n"
            else:
                mensaje += f"💲 *Precio:* Q{precio_normal}"
                if precio_oferta and precio_oferta != precio_normal:
                    mensaje += f"\n💥 *Súper Oferta (Efectivo):* Q{precio_oferta}"

                #if stock_quantity > 0:
                #    mensaje += f"\n📦 *Disponibles:* {stock_quantity} unidades"



            #mensaje += f"💲 *Precio:* Q{precio_normal}"

           # if precio_oferta and precio_oferta != precio_normal:
           #     mensaje += f"\n💥 *Súper Oferta:* Q{precio_oferta}"

            if fecha_oferta:
                try:
                    fecha_dt = datetime.fromisoformat(fecha_oferta)
                    if fecha_dt > datetime.now():
                        mensaje += f"\n🗓 Oferta válida hasta: {fecha_dt.strftime('%d/%m/%Y')}"
                except:
                    pass

            mensaje += (
                "\n\n🚚 Envío a domicilio\n"
                "🤝 Pago contra entrega disponible\n"
                "💳 Aceptamos tarjetas de crédito sin recargo (precio normal)\n"
                "🚦 Aplican restricciones\n\n"

                "⚠️ *Nota:* Los precios y disponibilidad pueden cambiar sin previo aviso."
            )

            return mensaje

        except Exception as e:
            print(f"Error al formatear producto: {str(e)}")
            return "⚠️ Hubo un problema al mostrar la información del producto."

#def formatear_producto_whatsapp(self, producto):
#    try:
#        nombre = producto.get('name', 'Producto sin nombre')
#        precio = producto.get('price', 'N/A')
#        precio_normal = producto.get('regular_price') or precio
#        precio_oferta = producto.get('sale_price', '')
#        descripcion = self.limpiar_html(producto.get('short_description') or producto.get('description', ''))
#        enlace = producto.get('permalink', '')
#        fecha_oferta = producto.get('date_on_sale_to')
#
#        mensaje = f"🔩⚙ *{nombre}* ⚙🔩\n\n"
#
#        if descripcion:
#            mensaje += f"📝 *Descripción:*\n{descripcion}\n\n"
#
#        mensaje += f"🔗 Ver más detalles aquí:\n{enlace}\n\n"
#        mensaje += f"💲 *Precio regular:* Q{precio_normal}"
#
#        if precio_oferta and precio_oferta != precio_normal:
#            mensaje += f"\n💥 *Precio en oferta:* Q{precio_oferta}"
#
#        if fecha_oferta:
#            try:
#                fecha_dt = datetime.fromisoformat(fecha_oferta)
#                if fecha_dt > datetime.now():
#                    mensaje += f"\n🗓 Oferta válida hasta: {fecha_dt.strftime('%d/%m/%Y')}"
#            except:
#                pass
#
#        mensaje += (
#            "\n\n🚚 Envío a domicilio\n"
#            "🤝 Pago contra entrega disponible\n"
#            "💳 Aceptamos tarjetas de crédito sin recargo\n\n"
#            "⚠️ *Nota:* Los precios y disponibilidad pueden cambiar sin previo aviso."
#        )
#
#        return mensaje
#
#    except Exception as e:
#        print(f"Error al formatear producto: {str(e)}")
#        return "⚠️ Hubo un problema al mostrar la información del producto."
