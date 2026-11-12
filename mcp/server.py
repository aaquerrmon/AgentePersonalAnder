
import os
import json
import re
import requests

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row
from mcp.server.mcpserver import MCPServer


load_dotenv()

# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("RO_USER"),
    "password": os.getenv("RO_PASSWORD"),
    "connect_timeout": 5,
}

EMBEDDINGS_BASE_URL = os.getenv(
    "EMBEDDINGS_BASE_URL",
    "http://localhost:8000/v1"
).rstrip("/")

EMBEDDINGS_MODEL = os.getenv(
    "EMBEDDINGS_MODEL",
    "multilingual-e5-small"
)

RAG_TABLE = os.getenv("RAG_TABLE", "chunks_rag")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

# Validar nombre de tabla para evitar inyección SQL
if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", RAG_TABLE):
    raise ValueError("Nombre de tabla RAG no válido")


# Servidor MCP
mcp = MCPServer("PostgreSQL-RAG-MCP")


# --------------------------------------------------
# CONEXIÓN A POSTGRESQL
# --------------------------------------------------

def get_connection():
    return psycopg.connect(
        **DB_CONFIG,
        row_factory=dict_row
    )


# --------------------------------------------------
# GENERACIÓN DE EMBEDDINGS SIN OPENAI
# --------------------------------------------------

def generate_embedding(text: str) -> list[float]:
    """
    Genera embeddings mediante una petición HTTP
    directamente al servidor de embeddings.

    No utiliza la librería openai.
    """

    url = f"{EMBEDDINGS_BASE_URL}/embeddings"

    headers = {
        "Content-Type": "application/json",
    }

    payload = {
        "model": EMBEDDINGS_MODEL,
        "input": text
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    return result["data"][0]["embedding"]


# --------------------------------------------------
# TOOL 1: CONSULTAS SQL
# --------------------------------------------------

@mcp.tool()
def postgres_query(
    query: str,
    params: dict | None = None,
    max_rows: int = 100
) -> str:
    """
    Ejecuta consultas SQL de solo lectura sobre PostgreSQL.

    Args:
        query: Consulta SQL SELECT o WITH.
               Para parámetros usa %(nombre)s.
        params: Diccionario de parámetros SQL.
        max_rows: Número máximo de filas devueltas.
    """

    query = query.strip()

    # Comprobaciones básicas
    if not re.match(r"^(SELECT|WITH)\b", query, re.IGNORECASE):
        return json.dumps({
            "error": "Solo se permiten consultas SELECT o WITH."
        })

    # No permitimos múltiples sentencias
    if ";" in query:
        return json.dumps({
            "error": "No se permiten múltiples sentencias SQL."
        })

    max_rows = max(1, min(max_rows, 500))

    try:
        with get_connection() as conn:
            with conn.transaction():

                # Protección adicional en PostgreSQL
                conn.execute("SET TRANSACTION READ ONLY")

                conn.execute(
                    "SET LOCAL statement_timeout = '10s'"
                )

                with conn.cursor() as cur:
                    cur.execute(query, params or {})

                    rows = cur.fetchmany(max_rows + 1)

                    truncated = len(rows) > max_rows
                    rows = rows[:max_rows]

                    result = {
                        "rows": rows,
                        "count": len(rows),
                        "truncated": truncated
                    }

                    return json.dumps(
                        result,
                        default=str,
                        ensure_ascii=False
                    )

    except Exception as e:
        return json.dumps({
            "error": str(e)
        })


# --------------------------------------------------
# TOOL 2: BÚSQUEDA SEMÁNTICA RAG
# --------------------------------------------------

@mcp.tool()
def rag_search(
    question: str,
    top_k: int = RAG_TOP_K,
    metadata_filter: dict | None = None
) -> str:
    """
    Busca documentos relevantes utilizando embeddings
    y pgvector.

    Args:
        question: Pregunta o texto que queremos buscar.
        top_k: Número de documentos que queremos recuperar.
        metadata_filter: Filtro opcional sobre los metadatos
                         JSONB de los documentos.
    """

    try:
        # 1. Generar embedding de la pregunta
        query_embedding = generate_embedding(question)

        # 2. Limitar resultados
        top_k = max(1, min(top_k, 20))

        # 3. Construir consulta vectorial
        sql = f"""
            SELECT
                id,
                texto AS content,
                metadata,
                1 - (embedding <=> %s::vector)
                    AS similarity
            FROM {RAG_TABLE}
            WHERE embedding IS NOT NULL
        """

        params = [json.dumps(query_embedding)]

        # Filtro opcional por metadatos
        if metadata_filter:
            sql += " AND metadata @> %s::jsonb"
            params.append(json.dumps(metadata_filter))

        sql += """
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        params.extend([
            json.dumps(query_embedding),
            top_k
        ])

        # 4. Ejecutar búsqueda
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                results = cur.fetchall()

        # 5. Devolver resultados
        documents = []

        for row in results:
            documents.append({
                "id": row["id"],
                "content": row["content"],
                "metadata": row["metadata"],
                "similarity": float(row["similarity"])
            })

        return json.dumps(
            {
                "question": question,
                "total_results": len(documents),
                "results": documents
            },
            default=str,
            ensure_ascii=False
        )

    except Exception as e:
        return json.dumps({
            "error": str(e)
        })


# --------------------------------------------------
# ARRANQUE DEL SERVIDOR
# --------------------------------------------------

if __name__ == "__main__":

    # STDIO: el cliente MCP lanzará este proceso.
    # No necesita abrir otro puerto HTTP.

    mcp.run(transport="stdio")
