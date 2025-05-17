from woocommerce_service import WooCommerceService

woo = WooCommerceService()

def buscar_productos_por_atributos(atributos: dict, limite=10):
    filtros = {
        'status': 'publish',
        'per_page': limite
    }

    terminos = []

    if atributos.get("marca"):
        terminos.append(atributos["marca"])
    if atributos.get("motor"):
        terminos.append(atributos["motor"])
    if atributos.get("anio"):
        terminos.append(atributos["anio"])
    if atributos.get("combustible"):
        terminos.append(atributos["combustible"])
    if atributos.get("cilindraje"):
        terminos.append(atributos["cilindraje"])

    if not terminos:
        return []

    filtros['search'] = " ".join(terminos)

    productos = woo.obtener_todos_los_productos(params=filtros)

    resultados = []

    for p in productos:
        coinciden = True

        for attr in p.get("attributes", []):
            nombre = attr.get("name", "").lower()
            opciones = [o.lower() for o in attr.get("options", [])]

            if "marca" in nombre and atributos.get("marca"):
                if atributos["marca"].lower() not in opciones:
                    coinciden = False
            if "motor" in nombre and atributos.get("motor"):
                if atributos["motor"].lower() not in opciones:
                    coinciden = False
            if "combustible" in nombre and atributos.get("combustible"):
                if atributos["combustible"].lower() not in opciones:
                    coinciden = False
            if "c.c" in nombre and atributos.get("cilindraje"):
                if not any(atributos["cilindraje"] in o for o in opciones):
                    coinciden = False
            if "año" in nombre and atributos.get("anio"):
                if not any(atributos["anio"] in o for o in opciones):
                    coinciden = False

        if coinciden:
            resultados.append(p)

    return resultados