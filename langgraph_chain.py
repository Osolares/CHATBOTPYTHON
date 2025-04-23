from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
import os
from dotenv import load_dotenv

from langchain.llms import HuggingFaceHub
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

load_dotenv()

# Estado de la conversación
class State(TypedDict):
    step: str
    input: Optional[str]
    marca: Optional[str]
    modelo: Optional[str]
    anio: Optional[str]
    tipo: Optional[str]
    comentario: Optional[str]
    output: Optional[str]

# LLM liviano por ahora
llm = HuggingFaceHub(
    repo_id="google/flan-t5-base",
    model_kwargs={"temperature": 0.7, "max_new_tokens": 128},
    huggingfacehub_api_token=os.getenv("HF_API_TOKEN")
)

# Pasos
def paso_marca(state: State) -> State:
    return {
        **state,
        "marca": state["input"],
        "step": "awaiting_modelo",
        "output": f"👍 Perfecto. ¿Qué modelo es tu {state['marca']}?"
    }

def paso_modelo(state: State) -> State:
    return {
        **state,
        "modelo": state["input"],
        "step": "awaiting_anio",
        "output": f"📅 Entendido. ¿De qué año es tu {state['marca']} {state['modelo']}?"
    }

def paso_anio(state: State) -> State:
    return {
        **state,
        "anio": state["input"],
        "step": "awaiting_tipo",
        "output": f"🔧 ¿Qué tipo de repuesto estás buscando para tu {state['marca']} {state['modelo']} {state['anio']}?"
    }

def paso_tipo(state: State) -> State:
    return {
        **state,
        "tipo": state["input"],
        "step": "awaiting_comentario",
        "output": f"📌 ¿Querés agregar algún comentario, código de parte, o descripción adicional?"
    }

def paso_comentario(state: State) -> State:
    return {
        **state,
        "comentario": state["input"],
        "step": "completed",
        "output": (
            f"📝 Gracias por la información.\n\n"
            f"Marca: {state['marca']}\n"
            f"Modelo: {state['modelo']}\n"
            f"Año: {state['anio']}\n"
            f"Repuesto: {state['tipo']}\n"
            f"Comentario: {state['comentario']}\n\n"
            f"📦 Nuestro equipo revisará y te responderá con una cotización pronto."
        )
    }

def paso_final(state: State) -> State:
    return {**state, "output": "Gracias por contactar. ¿Te puedo ayudar en algo más?"}

# Construcción del grafo
def build_chain():
    builder = StateGraph(state_schema=State)

    builder.add_node("awaiting_marca", paso_marca)
    builder.add_node("awaiting_modelo", paso_modelo)
    builder.add_node("awaiting_anio", paso_anio)
    builder.add_node("awaiting_tipo", paso_tipo)
    builder.add_node("awaiting_comentario", paso_comentario)
    builder.add_node("completed", paso_final)

    builder.set_entry_point("awaiting_marca")

    builder.add_edge("awaiting_marca", "awaiting_modelo")
    builder.add_edge("awaiting_modelo", "awaiting_anio")
    builder.add_edge("awaiting_anio", "awaiting_tipo")
    builder.add_edge("awaiting_tipo", "awaiting_comentario")
    builder.add_edge("awaiting_comentario", "completed")

    builder.set_finish_point("completed")

    return builder.compile()
