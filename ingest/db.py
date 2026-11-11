"""Acceso a PostgreSQL: tablas documentos_rag y chunks_rag."""
from __future__ import annotations

import logging
import time

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from config import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    WAIT_TIMEOUT_S,
)

log = logging.getLogger("ingest.db")


def wait_and_connect(timeout_s: int = WAIT_TIMEOUT_S):
    """Reintenta la conexión hasta que PostgreSQL acepte (o se agote el tiempo)."""
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = psycopg.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                dbname=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                connect_timeout=5,
                row_factory=dict_row,
            )
            conn.autocommit = True
            register_vector(conn)
            conn.execute("SELECT 1")
            return conn
        except Exception as exc:  # noqa: BLE001 - cualquier error de red/auth se reintenta
            last_error = exc
            log.info("PostgreSQL no disponible aún (%s); reintento en 2 s...", exc)
            time.sleep(2)
    raise RuntimeError(f"No se pudo conectar a PostgreSQL en {timeout_s}s: {last_error}")


def get_perfil_id(conn) -> int | None:
    """Primer perfil de la tabla (para vincular los documentos); None si no hay."""
    row = conn.execute("SELECT id FROM perfil ORDER BY id LIMIT 1").fetchone()
    return row["id"] if row else None


def load_ingested(conn) -> dict[str, str]:
    """Mapa de ruta relativa -> sha256 de los documentos ya ingeridos."""
    rows = conn.execute(
        """
        SELECT metadata->>'path' AS path, metadata->>'sha256' AS sha256
        FROM documentos_rag
        WHERE metadata ? 'path'
        """
    ).fetchall()
    return {row["path"]: row["sha256"] for row in rows if row["path"]}


def count_chunks(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM chunks_rag").fetchone()["n"]


def delete_documento_by_path(conn, path: str) -> None:
    """Borra el documento (y sus chunks en cascada) registrado para esa ruta."""
    conn.execute("DELETE FROM documentos_rag WHERE metadata->>'path' = %s", (path,))


def insert_documento(conn, titulo: str, fuente: str, perfil_id: int | None, metadata: dict) -> int:
    row = conn.execute(
        """
        INSERT INTO documentos_rag (titulo, fuente, perfil_id, metadata)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (titulo, fuente, perfil_id, Jsonb(metadata)),
    ).fetchone()
    return row["id"]


def insert_chunks(conn, doc_id: int, items) -> None:
    """Inserta chunks. items: iterable de (chunk_index, texto, metadata, embedding)."""
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunks_rag (doc_id, chunk_index, texto, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [(doc_id, idx, texto, Jsonb(meta), emb) for idx, texto, meta, emb in items],
        )
