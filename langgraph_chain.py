# langgraph_chain.py

from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
from langchain.llms import HuggingFaceHub
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import os
from dotenv import load_dotenv

load_dotenv()

# 1. Definimos el estado de la conversación
class State(TypedDict):
    step: str
    input: Optional[str]
    marca: Optional[str]
    modelo: Optional[str]
    output: Optional[str]

# 2. Modelo ligero (flan-t5-base)
llm = HuggingFaceHub(
    repo_id="google/flan-t5-base",
    model_kwargs={"temperature": 0.7, "max_new_tokens": 128},
    huggingfacehub_api_token=os.getenv("HF_API_TOKEN")
)

# 3. Funciones por paso

def paso_marca(state: State) -> State:
    user_input = state["input"]
    return {
        **state,
        "marca": user_input,
        "step": "awaiting_modelo",
        "output": f"✅ Marca recibida: {user_input}. Ahora, ¿cuál es el modelo?"
    }

def paso_modelo(state: State) -> State:
    user_input = state["input"]
    return {
        **state,
        "modelo": user_input,
        "step": "completed",
        "output": f"📋 Gracias. Recibimos:\nMarca: {state['marca']}\nModelo: {user_input}"
    }

def paso_final(state: State) -> State:
    return {**state, "output": "✅ Formulario completado. Gracias."}

# 4. Construcción del grafo
def build_chain():
    builder = StateGraph(state_schema=State)
    
    builder.add_node("awaiting_marca", paso_marca)
    builder.add_node("awaiting_modelo", paso_modelo)
    builder.add_node("completed", paso_final)

    builder.set_entry_point("awaiting_marca")

    builder.add_edge("awaiting_marca", "awaiting_modelo")
    builder.add_edge("awaiting_modelo", "completed")
    builder.set_finish_point("completed")

    return builder.compile()
