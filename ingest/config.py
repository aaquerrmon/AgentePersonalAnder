"""Configuración del pipeline de ingesta RAG (leída de variables de entorno)."""
from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


# PostgreSQL
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = _int("POSTGRES_PORT", 5432)
POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_DB = os.getenv("POSTGRES_DB", "mydatabase")

# Directorio de documentos (montado como volumen de solo lectura)
DOCS_DIR = os.getenv("DOCS_DIR", "/docs")

# Endpoint de embeddings (vLLM, API compatible con OpenAI)
EMBEDDINGS_BASE_URL = os.getenv("EMBEDDINGS_BASE_URL", "http://embedding:8000/v1").rstrip("/")
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "multilingual-e5-small")
EMBEDDINGS_DIM = _int("EMBEDDINGS_DIM", 384)
EMBED_BATCH_SIZE = _int("EMBED_BATCH_SIZE", 32)
EMBED_TIMEOUT_S = _int("EMBED_TIMEOUT_S", 60)

# Repositorio de HuggingFace del que se descarga el tokenizer (chunking y validación)
HF_MODEL_ID = os.getenv("HF_MODEL_ID", "intfloat/multilingual-e5-small")

# Límite de tokens por chunk: por debajo de los 512 de e5 para dejar sitio
# al prefijo "passage: " y a los encabezados que añade contextualize()
CHUNK_MAX_TOKENS = _int("CHUNK_MAX_TOKENS", 450)

# e5 exige prefijos: "passage: " al indexar, "query: " al buscar
E5_PASSAGE_PREFIX = "passage: "

# Esperas iniciales de arranque (PostgreSQL / vLLM)
WAIT_TIMEOUT_S = _int("WAIT_TIMEOUT_S", 300)
