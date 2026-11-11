"""Cliente del endpoint de embeddings de vLLM (API compatible con OpenAI).

Nota importante: intfloat/multilingual-e5-small exige el prefijo "passage: "
al indexar textos y "query: " al buscar. Aquí solo se aplica el de indexación;
el texto se guarda en la BD sin prefijo.
"""
from __future__ import annotations

import logging
import time

import httpx

from config import (
    E5_PASSAGE_PREFIX,
    EMBED_BATCH_SIZE,
    EMBEDDINGS_BASE_URL,
    EMBEDDINGS_DIM,
    EMBEDDINGS_MODEL,
    EMBED_TIMEOUT_S,
    WAIT_TIMEOUT_S,
)

log = logging.getLogger("ingest.embeddings")

MAX_ATTEMPTS = 4


class Embedder:
    def __init__(self) -> None:
        self.model = EMBEDDINGS_MODEL
        self.dim = EMBEDDINGS_DIM
        self.batch_size = EMBED_BATCH_SIZE
        # Cliente para la API (base_url termina en /v1 -> POST /embeddings)
        self._api = httpx.Client(base_url=EMBEDDINGS_BASE_URL, timeout=EMBED_TIMEOUT_S)
        # Cliente para comprobaciones en la raíz del servidor (/health, /v1/models)
        origin = httpx.URL(EMBEDDINGS_BASE_URL).copy_with(path="/")
        self._origin = httpx.Client(base_url=str(origin), timeout=10.0)

    def wait_ready(self, timeout_s: int = WAIT_TIMEOUT_S) -> None:
        """Bloquea hasta que el servidor de embeddings responde correctamente."""
        deadline = time.monotonic() + timeout_s
        last = "sin intentos"
        while time.monotonic() < deadline:
            for path in ("/health", "/v1/models"):
                try:
                    resp = self._origin.get(path)
                except Exception as exc:  # noqa: BLE001 - el servidor aún no levanta
                    last = f"{path}: {exc}"
                    continue
                if resp.status_code == 200:
                    log.info("Servidor de embeddings listo en %s (modelo %s)", EMBEDDINGS_BASE_URL, self.model)
                    return
                last = f"{path}: HTTP {resp.status_code}"
            time.sleep(2)
        raise RuntimeError(f"El servidor de embeddings no respondió en {timeout_s}s (último: {last})")

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Embebe textos con el prefijo 'passage: ' que exige e5."""
        prefixed = [f"{E5_PASSAGE_PREFIX}{text}" for text in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(prefixed), self.batch_size):
            batch = prefixed[start : start + self.batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        last: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self._api.post("/embeddings", json={"model": self.model, "input": batch})
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda item: item.get("index", 0))
                vectors = [item["embedding"] for item in data]
                if len(vectors) != len(batch):
                    raise ValueError(f"Se pidieron {len(batch)} vectores y llegaron {len(vectors)}")
                for vec in vectors:
                    if len(vec) != self.dim:
                        raise ValueError(f"Dimensión inesperada: {len(vec)} (se esperaba {self.dim})")
                return vectors
            except Exception as exc:
                last = exc
                wait = 2**attempt
                log.warning("Error embebiendo lote (intento %d/%d): %s; reintento en %ss", attempt, MAX_ATTEMPTS, exc, wait)
                time.sleep(wait)
        raise RuntimeError(f"Falló el endpoint de embeddings tras {MAX_ATTEMPTS} intentos: {last}")
