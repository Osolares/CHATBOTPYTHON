import requests
from config import Config
from datetime import datetime
import random
import re
from html import unescape

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
                'per_page': 100,  # Traer más para poder mezclar
                '_fields': 'id,name,price,regular_price,description,short_description,date_on_sale_to,permalink,images'
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
        for producto in productos[:3]:  # Limitar a 3 productos
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
                    f"\n\n🌟 *Detalles:*\n{descripcion_larga}\n\n"
                    f"🚚 Envío a domicilio\n"
                    f"🤝 Pago contra entrega (solamente repuestos)\n"
                    f"💳 Aceptamos todas las tarjetas de crédito sin recargo\n\n"
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
