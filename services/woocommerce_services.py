# services/woocommerce_service.py
import requests
from config import Config

class WooCommerceService:
    def __init__(self):
        self.base_url = f"{Config.WOOCOMMERCE_URL}/wp-json/wc/v3"
        self.auth = (Config.WOOCOMMERCE_KEY, Config.WOOCOMMERCE_SECRET)

    def buscar_producto(self, categoria, marca, motor):
        try:
            params = {
                "category": categoria,
                "attribute": f"pa_marca,{marca},pa_motor,{motor}",
                "status": "publish",
                "per_page": 10,
                "_fields": "id,name,price,permalink,attributes,stock_status"
            }
            response = requests.get(f"{self.base_url}/products", auth=self.auth, params=params)
            response.raise_for_status()
            productos = response.json()
            disponibles = [p for p in productos if p['stock_status'] == 'instock']
            return disponibles
        except requests.RequestException as e:
            print(f"Error al consultar WooCommerce: {e}")
            return []
