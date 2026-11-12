
from langchain.agents import create_agent


SQL_PROMPT = """
Eres un experto en PostgreSQL y análisis de datos.

Tu misión es responder preguntas sobre datos estructurados.

REGLAS:
- Utiliza exclusivamente las herramientas SQL disponibles.
- No inventes resultados.
- Realiza únicamente consultas de lectura.
- No ejecutes INSERT, UPDATE, DELETE, DROP ni ALTER.
- Respeta los permisos de la base de datos.
- Si no encuentras los datos, indícalo.
- Devuelve resultados claros y verificables.
"""


def build_sql_agent(model, tools):

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=SQL_PROMPT,
        name="sql_agent",
    )
