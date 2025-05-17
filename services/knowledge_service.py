# services/knowledge_service.py
import json

class KnowledgeService:
    def __init__(self, path='data/product_knowledge.json'):
        with open(path, 'r', encoding='utf-8') as file:
            self.knowledge = json.load(file)

    def validar_info(self, categoria, marca, serie):
        errores = []
        if categoria not in self.knowledge["categorias_disponibles"]:
            errores.append(f"No trabajamos la categoría '{categoria}'.")
        if marca in self.knowledge["marcas_no_trabajadas"]:
            errores.append(f"No trabajamos la marca '{marca}'.")
        if marca not in self.knowledge["marcas_permitidas"]:
            errores.append(f"La marca '{marca}' no está registrada.")
        if serie not in self.knowledge["series_disponibles"]:
            errores.append(f"No tenemos productos para la serie '{serie}'.")
        return errores
