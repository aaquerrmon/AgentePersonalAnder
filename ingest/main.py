#!/usr/bin/env python3
"""Ingesta de documentos RAG.

Escanea DOCS_DIR (por defecto /docs, montado desde ./docs), convierte los
ficheros nuevos o modificados con docling, los trocea, los embebe con
intfloat/multilingual-e5-small (vLLM) y los guarda en documentos_rag/chunks_rag.

Es idempotente: guarda el sha256 de cada fichero en el metadata del documento
y lo vuelve a procesar solo si el contenido ha cambiado.
"""
from __future__ import annotations

import hashlib
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import config
import db
from embeddings import Embedder
from parsing import SUPPORTED_EXTS, Parser

log = logging.getLogger("ingest")

READ_CHUNK = 1024 * 1024


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(READ_CHUNK):
            digest.update(block)
    return digest.hexdigest()


def iter_documentos(docs_dir: Path):
    """Ficheros soportados (ocultos y no soportados se ignoran)."""
    if not docs_dir.is_dir():
        log.warning("El directorio %s no existe; no hay nada que ingerir.", docs_dir)
        return
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(docs_dir).parts):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTS:
            log.info("Omitido (formato no soportado): %s", path.name)
            continue
        yield path


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    started = time.monotonic()
    docs_dir = Path(config.DOCS_DIR)

    log.info("Conectando a PostgreSQL %s:%s/%s...", config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_DB)
    conn = db.wait_and_connect()
    log.info("PostgreSQL listo.")

    embedder = Embedder()
    embedder.wait_ready()

    perfil_id = db.get_perfil_id(conn)
    ingested = db.load_ingested(conn)
    files = list(iter_documentos(docs_dir))
    log.info(
        "Ficheros soportados en %s: %d (%d ya ingeridos)",
        docs_dir, len(files), len(ingested),
    )

    parser = Parser()
    stats = {"nuevos": 0, "actualizados": 0, "sin_cambios": 0, "chunks": 0, "errores": 0}

    for path in files:
        rel = str(path.relative_to(docs_dir))
        digest = sha256_of(path)

        if ingested.get(rel) == digest:
            stats["sin_cambios"] += 1
            log.info("Sin cambios: %s", rel)
            continue

        estado = "Actualizado" if rel in ingested else "Nuevo"
        t0 = time.monotonic()
        try:
            parsed = parser.parse(path)
            if not parsed.chunks:
                raise ValueError("no se pudo extraer contenido")

            vectors = embedder.embed_passages([chunk.enriquecido for chunk in parsed.chunks])
            if len(vectors) != len(parsed.chunks):
                raise ValueError("el nº de vectores no coincide con el nº de chunks")

            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            metadata = {
                "path": rel,
                "sha256": digest,
                "tamano": path.stat().st_size,
                "extension": path.suffix.lower().lstrip("."),
                "ingested_at": now,
                "n_chunks": len(parsed.chunks),
            }
            with conn.transaction():
                db.delete_documento_by_path(conn, rel)
                doc_id = db.insert_documento(
                    conn,
                    titulo=parsed.titulo[:250],
                    fuente=path.suffix.lower().lstrip("."),
                    perfil_id=perfil_id,
                    metadata=metadata,
                )
                db.insert_chunks(
                    conn,
                    doc_id,
                    [
                        (idx, chunk.texto, chunk.metadata, vector)
                        for idx, (chunk, vector) in enumerate(zip(parsed.chunks, vectors))
                    ],
                )

            stats["chunks"] += len(parsed.chunks)
            stats["actualizados" if rel in ingested else "nuevos"] += 1
            log.info(
                "%s: %s → %d chunks (%.1fs)",
                estado, rel, len(parsed.chunks), time.monotonic() - t0,
            )
        except Exception:
            stats["errores"] += 1
            log.exception("ERROR procesando %s", rel)

    total_chunks = db.count_chunks(conn)
    conn.close()

    log.info(
        "Resumen: %d nuevos, %d actualizados, %d sin cambios, %d omitidos por error | "
        "%d chunks insertados | %d chunks totales en la BD | %.1fs",
        stats["nuevos"], stats["actualizados"], stats["sin_cambios"], stats["errores"],
        stats["chunks"], total_chunks, time.monotonic() - started,
    )
    return 1 if stats["errores"] else 0


if __name__ == "__main__":
    sys.exit(main())
