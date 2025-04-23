from langgraph.graph import StateGraph, END
from langgraph.graph.graph import State
from llm import ask_llm
from typing import TypedDict, Optional

# Define el tipo de estado para el grafo
class ChatState(TypedDict):
    input: str
    output: Optional[str]

def simple_node(state: ChatState) -> ChatState:
    user_input = state.get("input", "")
    output = ask_llm(user_input)
    return {"output": output}

def build_chain():
    # Crea el grafo especificando el esquema de estado
    workflow = StateGraph(ChatState)
    
    workflow.add_node("Responder", simple_node)
    workflow.set_entry_point("Responder")
    workflow.set_finish_point(END)
    
    return workflow.compile()