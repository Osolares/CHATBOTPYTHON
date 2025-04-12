import requests
from config import Config
from datetime import datetime
import random

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
        """Formatea productos en oferta para mensaje de WhatsApp con estilo personalizado"""
        if not productos:
            return ["📢 No hay ofertas disponibles en este momento."]

        mensajes = []

        for producto in productos[:3]:  # Mostrar máximo 3
            try:
                nombre = producto.get('name', 'Producto sin nombre')
                precio_regular = producto.get('regular_price', '')
                precio_oferta = producto.get('price', '')
                descripcion_corta = self.limpiar_html(producto.get('short_description', ''))
                descripcion_larga = self.limpiar_html(producto.get('description', ''))
                enlace = producto.get('permalink', 'https://intermotores.com')
                imagen = producto.get('images', [{}])[0].get('src', '')
                fecha_fin_oferta = producto.get('date_on_sale_to', None)

                mensaje = (
                    f"🔩⚙ *{nombre}* ⚙🔩\n"
                    f"📝 *Descripción:* {descripcion_corta or 'Sin descripción corta.'}\n"
                    f"🔗 Puedes ver imágenes y más información en el siguiente LINK:\n{enlace}\n"
                    f"💲 *Precio:* Q{precio_regular}\n"
                )

                if precio_oferta and precio_oferta != precio_regular:
                    mensaje += f"💥🏷 *Súper Oferta (Efectivo):* Q{precio_oferta}\n"

                if fecha_fin_oferta:
                    try:
                        fecha = datetime.strptime(fecha_fin_oferta, "%Y-%m-%dT%H:%M:%S")
                        if fecha > datetime.now():
                            mensaje += f"📅 *Oferta válida hasta:* {fecha.strftime('%d/%m/%Y')}\n"
                    except Exception as e:
                        print(f"Error al convertir fecha: {str(e)}")

                mensaje += (
                    f"\n🌟 *Detalles:* {descripcion_larga or 'Sin detalles adicionales.'}\n\n"
                    "🚚 Envío a domicilio\n"
                    "🤝 Pago contra entrega (solamente repuestos)\n"
                    "💳 Aceptamos todas las tarjetas de crédito sin recargo\n\n"
                    "⚠ Nota: Los precios y disponibilidad pueden cambiar en cualquier momento sin previo aviso."
                )

                if imagen:
                    mensaje += f"\n📷 {imagen}"

                mensajes.append(mensaje)

            except Exception as e:
                print(f"Error formateando producto: {str(e)}")
                continue

        return mensajes if mensajes else ["📢 No se pudieron cargar las ofertas"]

    def limpiar_html(self, texto):
        """Elimina etiquetas HTML simples del texto"""
        import re
        return re.sub(r'<[^>]*>', '', texto).strip()
