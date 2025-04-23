from langgraph.graph import StateGraph
from typing import TypedDict, Optional, Dict, Any
from llm import ask_llm
import json

class ChatState(TypedDict):
    input: str
    output: Optional[str]
    error: Optional[str]
    status_code: Optional[int]

def ensure_serializable(data: Any) -> Dict[str, Any]:
    """Función de seguridad para garantizar serialización"""
    try:
        if isinstance(data, dict):
            return {k: str(v) if not isinstance(v, (str, int, float, bool)) else v for k, v in data.items()}
        return {"output": str(data)}
    except Exception as e:
        return {"error": f"Serialization failed: {str(e)}", "status_code": 500}

def simple_node(state: ChatState) -> Dict[str, Any]:
    try:
        user_input = state.get("input", "")
        if not user_input or not isinstance(user_input, str):
            return ensure_serializable({
                "error": "Input inválido",
                "status_code": 400
            })
            
        llm_response = ask_llm(user_input)
        return ensure_serializable(llm_response)
        
    except Exception as e:
        return ensure_serializable({
            "error": f"Error en simple_node: {str(e)}",
            "status_code": 500
        })

def build_chain():
    workflow = StateGraph(ChatState)
    workflow.add_node("Responder", simple_node)
    workflow.set_entry_point("Responder")
    workflow.add_edge("Responder", END)
    return workflow.compile()