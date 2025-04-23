from langgraph.graph import StateGraph, END
from llm import ask_llm

def simple_node(state):
    user_input = state.get("input", "")
    output = ask_llm(user_input)  # Consulta al modelo de lenguaje
    return {"output": output}

def build_chain():
    workflow = StateGraph()  # Crea un nuevo grafo de flujo
    
    # Añade un nodo llamado "Responder" que usa la función simple_node
    workflow.add_node("Responder", simple_node)
    
    # Configura el punto de entrada y final del grafo
    workflow.set_entry_point("Responder")
    workflow.set_finish_point(END)
    
    return workflow.compile()  # Compila el grafo para su uso