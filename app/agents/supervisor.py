
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

from app.config import LLM_MODEL, LLM_TEMPERATURE
from app.mcp_client import get_mcp_tools

from app.agents.sql_agent import build_sql_agent
from app.agents.rag_agent import build_rag_agent


SUPERVISOR_PROMPT = """
Eres el supervisor de un asistente inteligente.

Tienes dos especialistas:

1. SQL:
   Consulta PostgreSQL, estadísticas, agregaciones,
   recuentos y datos estructurados.

2. RAG:
   Busca información en documentos, manuales,
   informes y procedimientos.

INSTRUCCIONES:

- Analiza cada pregunta.
- Delega en SQL cuando necesites datos estructurados.
- Delega en RAG cuando necesites información documental.
- Puedes utilizar ambos agentes para una misma pregunta.
- Si necesitas ambos, intenta obtener los resultados
  de ambos especialistas.
- No inventes resultados.
- Combina las respuestas y explica las fuentes.
- Mantén el contexto de la conversación.
- Responde siempre en español, salvo que el usuario
  solicite otro idioma.
"""


async def build_supervisor(checkpointer=None):

    model = ChatOpenAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
    )

    # Recuperar herramientas MCP
    mcp_tools = await get_mcp_tools()

    # Nombres reales de las herramientas publicadas por mcp/server.py
    sql_tool_names = {
        "postgres_query",
    }

    rag_tool_names = {
        "rag_search",
    }

    sql_tools = [
        t for t in mcp_tools
        if t.name in sql_tool_names
    ]

    rag_tools = [
        t for t in mcp_tools
        if t.name in rag_tool_names
    ]

    if not sql_tools or not rag_tools:
        raise RuntimeError(
            "No se han encontrado todas las herramientas MCP. "
            f"SQL: {[t.name for t in sql_tools]}. "
            f"RAG: {[t.name for t in rag_tools]}."
        )

    # Crear los especialistas
    sql_agent = build_sql_agent(model, sql_tools)
    rag_agent = build_rag_agent(model, rag_tools)

    # Herramienta de delegación SQL
    @tool
    async def consultar_base_datos(pregunta: str) -> str:
        """Consulta información estructurada en PostgreSQL."""

        result = await sql_agent.ainvoke({
            "messages": [
                {"role": "user", "content": pregunta}
            ]
        })

        return str(result["messages"][-1].content)

    # Herramienta de delegación RAG
    @tool
    async def buscar_documentacion(pregunta: str) -> str:
        """Busca información en documentos mediante RAG."""

        result = await rag_agent.ainvoke({
            "messages": [
                {"role": "user", "content": pregunta}
            ]
        })

        return str(result["messages"][-1].content)

    # Supervisor
    supervisor = create_agent(
        model=model,
        tools=[
            consultar_base_datos,
            buscar_documentacion,
        ],
        system_prompt=SUPERVISOR_PROMPT,
        name="supervisor",
        checkpointer=checkpointer,
    )

    return supervisor
