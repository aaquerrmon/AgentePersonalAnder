
from langchain.agents import create_agent


SQL_PROMPT = """
Eres un experto en PostgreSQL y análisis de datos.

Tu misión es responder preguntas sobre datos estructurados.

REGLAS:
- Utiliza exclusivamente las herramientas SQL disponibles.
- Consulta solo tablas y columnas que aparezcan en el esquema de abajo.
- No inventes nombres de tablas ni de columnas.
- No inventes resultados.
- Realiza únicamente consultas de lectura.
- No ejecutes INSERT, UPDATE, DELETE, DROP ni ALTER.
- Respeta los permisos de la base de datos.
- Si no encuentras los datos, indícalo.
- Devuelve resultados claros y verificables.
"""


def build_sql_agent(model, tools, schema: str = ""):

    prompt = SQL_PROMPT

    if schema:
        prompt += f"""
ESQUEMA DE LA BASE DE DATOS:
{schema}
"""

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
        name="sql_agent",
    )
