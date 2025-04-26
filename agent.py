import os
from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())
deepseek_key = os.environ["DEEPSEEK_API_KEY"]

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
import uuid
from langgraph.store.memory import InMemoryStore
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.base import BaseStore
from langchain_core.messages import merge_message_runs
from trustcall import create_extractor

# Model Configuration for DeepSeek
model = ChatOpenAI(
    model="deepseek-chat",
    api_key=deepseek_key,
    base_url="https://api.deepseek.com/v1",
    temperature=0,
    max_tokens=200,  # Increased for better responses
)

# Memory Schema
class Memory(BaseModel):
    content: str = Field(description="El contenido principal de la memoria.")

class MemoryCollection(BaseModel):
    memories: list[Memory] = Field(description="Una lista de recuerdos sobre el usuario.")

# Initialize memory store
in_memory_store = InMemoryStore()

# Modified version that works with DeepSeek
def create_memory_collection(message: str) -> MemoryCollection:
    """Create memory collection manually since with_structured_output doesn't work with DeepSeek"""
    response = model.invoke([HumanMessage(message)])
    content = response.content
    return MemoryCollection(memories=[Memory(content=content)])

# Initialize with sample data
memory_collection = create_memory_collection(
    "Mi nombre es Oscar, soy un gerente de ventas de motores y repuestos para vehículos."
)

# Save memories to namespace
user_id = "1"
namespace_for_memory = (user_id, "memories")

for memory in memory_collection.memories:
    key = str(uuid.uuid4())
    value = memory.model_dump()
    in_memory_store.put(namespace_for_memory, key, value)

# Trustcall Extractor Configuration
trustcall_extractor = create_extractor(
    model,
    tools=[Memory],
    tool_choice="Memory",
    enable_inserts=True,
)

# Chatbot Instruction
MODEL_SYSTEM_MESSAGE = """Eres un chatbot útil. Estás diseñado para acompañar al usuario o clientes. 

Tienes una memoria a largo plazo que registra la información que aprendes sobre el usuario a lo largo del tiempo.

Memoria actual (puede incluir recuerdos actualizados de esta conversación):

{memory}"""

# Trustcall Instruction
TRUSTCALL_INSTRUCTION = """Reflexione sobre la siguiente interacción.

Utilice las herramientas proporcionadas para conservar cualquier recuerdo necesario sobre el usuario.

Utilice llamadas de herramientas paralelas para gestionar actualizaciones e inserciones simultáneamente:"""

def call_model(state: MessagesState, config: RunnableConfig, store: BaseStore):
    """Carga recuerdos de la store y úsalos para personalizar la respuesta del chatbot."""
    
    user_id = config["configurable"]["user_id"]
    namespace = ("memories", user_id)
    memories = store.search(namespace)

    info = "\n".join(f"- {mem.value['content']}" for mem in memories)
    system_msg = MODEL_SYSTEM_MESSAGE.format(memory=info)

    response = model.invoke([SystemMessage(content=system_msg)] + state["messages"])
    return {"messages": response}

def write_memory(state: MessagesState, config: RunnableConfig, store: BaseStore):
    """Reflexiona sobre el historial de chat y actualiza la colección de recuerdos."""
    
    user_id = config["configurable"]["user_id"]
    namespace = ("memories", user_id)
    existing_items = store.search(namespace)

    tool_name = "Memory"
    existing_memories = (
        [(existing_item.key, tool_name, existing_item.value)
         for existing_item in existing_items]
        if existing_items
        else None
    )

    updated_messages = list(merge_message_runs(
        messages=[SystemMessage(content=TRUSTCALL_INSTRUCTION)] + state["messages"]
    ))

    result = trustcall_extractor.invoke({
        "messages": updated_messages, 
        "existing": existing_memories
    })

    for r, rmeta in zip(result["responses"], result["response_metadata"]):
        store.put(
            namespace,
            rmeta.get("json_doc_id", str(uuid.uuid4())),
            r.model_dump(mode="json"),
        )

# Define the graph
builder = StateGraph(MessagesState)
builder.add_node("call_model", call_model)
builder.add_node("write_memory", write_memory)
builder.add_edge(START, "call_model")
builder.add_edge("call_model", "write_memory")
builder.add_edge("write_memory", END)

# Memory stores
across_thread_memory = InMemoryStore()
within_thread_memory = MemorySaver()

# Compile the graph
graph = builder.compile(
    checkpointer=within_thread_memory,
    store=across_thread_memory
)

# Example usage
config = {"configurable": {"thread_id": "1", "user_id": "1"}}

# First interaction
input_messages = [HumanMessage(content="Hola, soy Oscar")]
for chunk in graph.stream({"messages": input_messages}, config, stream_mode="values"):
    chunk["messages"][-1].pretty_print()

# Second interaction
input_messages = [HumanMessage(content="Hoy vendí repuesto para un vehículo Hyundai Starex modelo 2008 turbo diésel")]
for chunk in graph.stream({"messages": input_messages}, config, stream_mode="values"):
    chunk["messages"][-1].pretty_print()

# Check stored memories
user_id = "1"
namespace = ("memories", user_id)
memories = across_thread_memory.search(namespace)
print("\nMemorias almacenadas:")
for m in memories:
    print(f"- {m.value['content']}")