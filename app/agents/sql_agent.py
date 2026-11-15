
from langchain.agents import create_agent

from app.config import IDENTIDAD


# Esquema fijo (init/02-schema.sql). Literal en el código: en el portfolio
# no habrá Postgres/MCP, así que no se puede consultar al arrancar.
SCHEMA_SQL = """
- perfil: id INT PK, nombre_completo VARCHAR, titular VARCHAR, biografia TEXT,
  ubicacion VARCHAR, email VARCHAR, github_url VARCHAR, linkedin_url VARCHAR,
  web_personal VARCHAR
- experiencia: id INT PK, empresa VARCHAR, rol VARCHAR, tipo_contrato VARCHAR,
  fecha_inicio DATE, fecha_fin DATE (NULL = puesto actual), descripcion TEXT,
  perfil_id INT FK -> perfil.id
- proyectos: id INT PK, titulo VARCHAR, descripcion_completa TEXT, tipo VARCHAR,
  url_publica VARCHAR, destacado BOOLEAN, perfil_id INT FK -> perfil.id
- tecnologias: id INT PK, nombre VARCHAR UNIQUE, categoria VARCHAR,
  nivel VARCHAR, perfil_id INT FK -> perfil.id
- idiomas: id INT PK, lengua VARCHAR UNIQUE, nivel VARCHAR,
  perfil_id INT FK -> perfil.id
- educacion: id INT PK, titulo VARCHAR, institucion VARCHAR,
  fecha_inicio DATE, fecha_fin DATE, detalles TEXT,
  perfil_id INT FK -> perfil.id
- documentos_rag: id INT PK, titulo VARCHAR, fuente VARCHAR,
  proyecto_id INT FK -> proyectos.id, perfil_id INT FK -> perfil.id,
  metadata JSONB
- chunks_rag: id INT PK, doc_id INT FK -> documentos_rag.id ON DELETE CASCADE,
  chunk_index INT, texto TEXT, metadata JSONB, embedding VECTOR(384)
"""

SQL_PROMPT = IDENTIDAD + f"""
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

ESQUEMA DE LA BASE DE DATOS:
{SCHEMA_SQL}
"""


def build_sql_agent(model, tools):

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=SQL_PROMPT,
        name="sql_agent",
    )
