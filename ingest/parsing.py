"""Extracción de contenido y chunking con docling + HybridChunker.

- Formatos estructurados (PDF, DOCX, HTML, MD, CSV, imágenes...): docling.
- Texto plano (.txt): lectura directa con troceado por párrafos.

El chunker usa el tokenizer de e5 y un límite de CHUNK_MAX_TOKENS para que
ningún chunk supere los 512 tokens del modelo (incluido el prefijo "passage: ").
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from config import CHUNK_MAX_TOKENS, HF_MODEL_ID

log = logging.getLogger("ingest.parsing")

# Formatos que docling convierte:
# https://docling-project.github.io/docling/usage/supported_formats/
DOCLING_EXTS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".html", ".htm", ".md", ".csv",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
    ".odt", ".ods", ".odp", ".epub", ".rtf", ".adoc", ".tex",
}
# Texto plano: docling no soporta .txt, se trocea directamente
PLAIN_EXTS = {".txt"}
SUPPORTED_EXTS = DOCLING_EXTS | PLAIN_EXTS

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.S)


@dataclass
class ParsedChunk:
    texto: str          # texto crudo: lo que se guarda en chunks_rag.texto
    enriquecido: str    # con sección/encabezados: lo que se envía al modelo
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    titulo: str
    chunks: list[ParsedChunk] = field(default_factory=list)


def _page_no(meta_obj) -> int | None:
    """Extrae el número de página del meta de un chunk (si existe)."""
    prov = getattr(meta_obj, "prov", None)
    if isinstance(prov, (list, tuple)):
        prov = prov[0] if prov else None
    page = getattr(prov, "page_no", None) if prov is not None else None
    return int(page) if page is not None else None


class Parser:
    """Construye docling y el tokenizer de forma perezosa (son pesados)."""

    def __init__(self) -> None:
        self._converter = None
        self._chunker = None
        self._hf_tokenizer = None

    def _ensure_ready(self) -> None:
        if self._chunker is not None:
            return
        from docling.chunking import HybridChunker
        from docling.document_converter import DocumentConverter
        from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
        from transformers import AutoTokenizer

        log.info("Cargando tokenizer '%s' y motor de conversión de docling...", HF_MODEL_ID)
        self._hf_tokenizer = AutoTokenizer.from_pretrained(HF_MODEL_ID)
        hf_tokenizer = HuggingFaceTokenizer(tokenizer=self._hf_tokenizer, max_tokens=CHUNK_MAX_TOKENS)
        self._converter = DocumentConverter()
        self._chunker = HybridChunker(tokenizer=hf_tokenizer, merge_peers=True)
        log.info("Parser listo (max_tokens=%d)", CHUNK_MAX_TOKENS)

    def parse(self, path: Path) -> ParsedDocument:
        self._ensure_ready()
        if path.suffix.lower() in PLAIN_EXTS:
            return self._parse_plain(path)
        return self._parse_docling(path)

    # ------------------------------------------------------------------ docling
    def _parse_docling(self, path: Path) -> ParsedDocument:
        result = self._converter.convert(source=str(path))
        doc = result.document
        parsed = ParsedDocument(titulo=path.stem)
        for chunk in self._chunker.chunk(dl_doc=doc):
            texto = (chunk.text or "").strip()
            if not texto:
                continue
            # contextualize() anteponga los encabezados de la sección: es la
            # forma recomendada para alimentar al modelo de embeddings
            enriquecido = (self._chunker.contextualize(chunk=chunk) or texto).strip()
            meta: dict = {}
            headings = getattr(chunk.meta, "headings", None)
            if headings:
                meta["seccion"] = " > ".join(str(h) for h in headings)
            page = _page_no(chunk.meta)
            if page is not None:
                meta["pagina"] = page
            parsed.chunks.append(ParsedChunk(texto=texto, enriquecido=enriquecido, metadata=meta))
        return parsed

    # ------------------------------------------------------------ texto plano
    def _parse_plain(self, path: Path) -> ParsedDocument:
        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = ParsedDocument(titulo=path.stem)
        section: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            nonlocal buffer
            piece = "\n\n".join(buffer).strip()
            if piece:
                meta = {"seccion": section} if section else {}
                parsed.chunks.append(
                    ParsedChunk(texto=piece, enriquecido=_with_section(piece, section), metadata=meta)
                )
            buffer = []

        for block in (b.strip() for b in re.split(r"\n\s*\n", text)):
            if not block:
                continue
            heading = _HEADING_RE.match(block)
            if heading:
                flush()
                section = heading.group(1).strip().splitlines()[0]
                continue
            if buffer and self._count_tokens("\n\n".join(buffer + [block])) > CHUNK_MAX_TOKENS:
                flush()
            if self._count_tokens(block) > CHUNK_MAX_TOKENS:
                # Párrafo gigante: se divide por ventanas de tokens con solape
                for piece in self._window(block):
                    meta = {"seccion": section} if section else {}
                    parsed.chunks.append(
                        ParsedChunk(texto=piece, enriquecido=_with_section(piece, section), metadata=meta)
                    )
                continue
            buffer.append(block)
        flush()
        return parsed

    def _count_tokens(self, text: str) -> int:
        return len(self._hf_tokenizer.encode(text, add_special_tokens=False))

    def _window(self, text: str) -> list[str]:
        ids = self._hf_tokenizer.encode(text, add_special_tokens=False)
        step = max(CHUNK_MAX_TOKENS - 50, 1)
        pieces: list[str] = []
        for start in range(0, len(ids), step):
            window = self._hf_tokenizer.decode(ids[start : start + CHUNK_MAX_TOKENS], skip_special_tokens=True).strip()
            if window:
                pieces.append(window)
            if start + CHUNK_MAX_TOKENS >= len(ids):
                break
        return pieces


def _with_section(text: str, section: str | None) -> str:
    return f"{section}\n{text}" if section else text
