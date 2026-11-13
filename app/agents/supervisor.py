
import logging

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig

from app.config import LLM_MODEL, LLM_TEMPERATURE
from app.mcp_client import get_mcp_tools, get_database_schema

from app.agents.sql_agent import build_sql_agent
from app.agents.rag_agent import build_rag_agent

logger = logging.getLogger("app.supervisor")


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

- NUNCA respondas desde tu memoria ni repitas respuestas
  anteriores del historial: toda pregunta sobre datos se
  delega SIEMPRE, aunque creas saber la respuesta.
- Delega en SQL todo sobre personas o datos estructurados:
  perfil, idiomas, experiencia, proyectos, tecnologías,
  educación, recuentos, estadísticas.
- Delega en RAG todo sobre documentos, manuales,
  informes y procedimientos.
- Puedes utilizar ambos agentes para una misma pregunta.
- Si un agente devuelve error o "no encontrado",
  reintenta con otra formulación antes de responder.
- No inventes resultados.
- Combina las respuestas y explica las fuentes.
- Mantén el contexto de la conversación.
- Responde siempre en español, salvo que el usuario
  solicite otro idioma.
"""


async def build_supervisor(checkpointer=None):

    # streaming=True: sin esto langchain solo emite on_llm_new_token
    # en astream, y aquí los agentes se invocan con ainvoke.
    model = ChatOpenAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        streaming=True,
        # incluye usage en el último chunk (vLLM soporta stream_options)
        stream_usage=True,
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

    # Esquema de la BD para el agente SQL: sin él el modelo improvisa
    # nombres de tablas. Si falla, se arranca sin esquema (no se bloquea).
    try:
        schema = await get_database_schema()
        logger.info("Esquema de la BD:\n%s", schema)
    except Exception as e:
        logger.warning("No se pudo obtener el esquema de la BD: %s", e)
        schema = ""

    # Crear los especialistas
    sql_agent = build_sql_agent(model, sql_tools, schema)
    rag_agent = build_rag_agent(model, rag_tools)

    # Herramienta de delegación SQL.
    # config se inyecta (RunnableConfig no va en el esquema de la tool) y es lo
    # que hace que los callbacks/línea de tracing bajen hasta el sub-agente.
    @tool
    async def consultar_base_datos(
        pregunta: str, config: RunnableConfig
    ) -> str:
        """Consulta información estructurada en PostgreSQL."""

        result = await sql_agent.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": pregunta}
                ]
            },
            config=config,
        )

        return str(result["messages"][-1].content)

    # Herramienta de delegación RAG
    @tool
    async def buscar_documentacion(
        pregunta: str, config: RunnableConfig
    ) -> str:
        """Busca información en documentos mediante RAG."""

        result = await rag_agent.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": pregunta}
                ]
            },
            config=config,
        )

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
