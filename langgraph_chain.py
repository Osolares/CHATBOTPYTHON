from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
from llm import ask_llm
import json

class ChatState(TypedDict):
    input: str
    output: Optional[str]
    error: Optional[str]  # Nuevo campo para errores

def safe_ask_llm(input_text: str) -> dict:
    try:
        output = ask_llm(input_text)
        # Asegurar que la respuesta del LLM sea serializable
        if not isinstance(output, (str, int, float, bool, list, dict)):
            output = str(output)
        return {"output": output, "error": None}
    except Exception as e:
        return {"output": None, "error": str(e)}

def simple_node(state: ChatState) -> dict:
    user_input = state.get("input", "")
    llm_response = ask_llm(user_input)  # Ahora recibe un dict estandarizado
    
    if llm_response.get("error"):
        return {
            "output": f"Error: {llm_response['error']}",
            "error": llm_response["error"]
        }
    
    return {
        "output": llm_response["output"],
        "error": None
    }

def build_chain():
    workflow = StateGraph(ChatState)
    workflow.add_node("Responder", simple_node)
    workflow.set_entry_point("Responder")
    workflow.add_edge("Responder", END)
    return workflow.compile()