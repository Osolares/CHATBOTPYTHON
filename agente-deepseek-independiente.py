import os
from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState, StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage
from typing import List, Optional
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
_ = load_dotenv(find_dotenv())

class LLMProvider:
    """Clase mejorada para manejo de modelos con reintentos"""
    def __init__(self):
        self.models = self._initialize_models()
        self.current_model = self._select_model()
    

#model = ChatOpenAI(
#    model="deepseek-chat",
#    api_key=openai_deepseek_key,
#    base_url="https://api.deepseek.com/v1",
#    temperature=0.1,          # Reduce creatividad (pero no a 0 para evitar rigidez)
#    max_tokens=25,            # Fuerza respuestas más cortas
#    top_p=0.3,                # Limita las opciones de vocabulario
#    frequency_penalty=0.5,    # Penaliza repeticiones
#    presence_penalty=0.5,     # Favorece conceptos nuevos
#    stop=["\n", ".", ";"]     # Corta la respuesta en puntos lógicos
#)


    def _initialize_models(self):
        """Inicializa todos los modelos disponibles"""
        return {
            'deepseek': {
                'constructor': lambda: ChatOpenAI(
                    model="deepseek-chat",
                    openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
                    base_url="https://api.deepseek.com/v1",

                    temperature=0.1          # Reduce creatividad (pero no a 0 para evitar rigidez)
                    #max_tokens=25,            # Fuerza respuestas más cortas
                    #top_p=0.3,                # Limita las opciones de vocabulario
                    #frequency_penalty=0.5,    # Penaliza repeticiones
                    #presence_penalty=0.5,     # Favorece conceptos nuevos
                    #stop=["\n", ".", ";"]     # Corta la respuesta en puntos lógicos

                ),
                'priority': 1
            },
            'openai_gpt3': {
                'constructor': lambda: ChatOpenAI(
                    model="gpt-3.5-turbo",
                    openai_api_key=os.getenv("OPENAI_API_KEY"),
                    temperature=0.7
                ),
                'priority': 2
            }
        }
    
    def _select_model(self):
        """Selecciona el mejor modelo disponible"""
        for name, config in sorted(self.models.items(), key=lambda x: x[1]['priority']):
            try:
                model = config['constructor']()
                # Test simple para verificar conexión
                model.invoke([HumanMessage(content="Test connection")])
                logger.info(f"✅ Modelo seleccionado: {name}")
                return model
            except Exception as e:
                logger.warning(f"⚠️ Fallo con {name}: {str(e)}")
                continue
        
        raise RuntimeError("No hay modelos disponibles")

llm_provider = LLMProvider()

# Estado del mensaje (manteniendo tu estructura)
class EnhancedMessagesState(MessagesState):
    pass

# Nodos del grafo con manejo de errores
def robust_llm_node(state: EnhancedMessagesState):
    try:
        response = llm_provider.current_model.invoke(state["messages"])
        return {"messages": [response]}
    except Exception as e:
        logger.error(f"Error en generación: {e}")
        # Reintentar con otro modelo
        llm_provider.current_model = llm_provider._select_model()
        return {"messages": [AIMessage(content="Reintentando con otro modelo...")]}

# Construcción del grafo
builder = StateGraph(EnhancedMessagesState)
builder.add_node("llm_node", robust_llm_node)
builder.set_entry_point("llm_node")
builder.set_finish_point("llm_node")
graph = builder.compile()

# Función para ejecutar consultas
def run_query(query: str, use_tools: bool = False):
    try:
        query = (f"Resonde de forma tecnica y resumida maximo 15 palabras:  {query}")
        messages = graph.invoke({"messages": HumanMessage(content=query)})
        for msg in messages['messages']:
            print(f"\n🟢 Respuesta: {msg.content}")
    except Exception as e:
        print(f"\n🔴 Error grave: {str(e)}")

# Ejemplos de uso
if __name__ == "__main__":
    print(f"Python {os.sys.version}")
    print("Sistema de chat mejorado - Escribe 'salir' para terminar\n")
    
    while True:
        try:
            user_input = input("Tú: ")
            if user_input.lower() in ('salir', 'exit', 'quit'):
                break
                
            run_query(user_input)
            
        except KeyboardInterrupt:
            print("\nSaliendo...")
            break
        except Exception as e:
            print(f"\nError inesperado: {e}")