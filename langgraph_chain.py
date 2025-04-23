from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
from llm import ask_llm

# Define el tipo de estado manualmente
class ChatState(TypedDict):
    input: str
    output: Optional[str]

def simple_node(state: ChatState) -> dict:
    user_input = state.get("input", "")
    output = ask_llm(user_input)
    return {"output": output}

def build_chain():
    # Crea el grafo con nuestro tipo de estado definido
    workflow = StateGraph(ChatState)
    
    workflow.add_node("Responder", simple_node)
    workflow.set_entry_point("Responder")
    workflow.add_edge("Responder", END)
    
    return workflow.compile()