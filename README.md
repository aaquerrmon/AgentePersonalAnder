# AgentePersonal

![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker%20Compose-2496ED?style=flat&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9?style=flat)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?style=flat&logo=postgresql&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-0.7-56B2A8?style=flat)
![vLLM](https://img.shields.io/badge/vLLM-0.33-1B4D4E?style=flat)
![docling](https://img.shields.io/badge/docling-2.150-E85D4C?style=flat)

Infraestructura **RAG** (Retrieval-Augmented Generation) personal: los documentos de `docs/` se convierten y trocean automáticamente con **docling**, se embeben con **vLLM** (`intfloat/multilingual-e5-small`, 384 dimensiones) y se almacenan en **PostgreSQL + pgvector** para búsqueda semántica ultrarrápida.

## Arquitectura

```
                 ┌────────────────────────── docker compose ──────────────────────────┐
                 │                                                                    │
  docs/*.pdf ───►│  rag-ingest (one-shot)                                             │
  docs/*.md      │    1. escanea /docs        ┌──────────────────────┐                │
  docs/*.txt ───►│    2. sha256 (idempotente) │  vllm-embedding      │                │
                 │    3. docling + HybridChunk│  intfloat/e5-small   │                │
                 │    4. POST /v1/embeddings ─►  384 dims, GPU       │                │
                 │         (passage: )        └──────────────────────┘                │
                 │    5. INSERT transaccional           ▲                             │
                 │            │                         │                             │
                 │            ▼                         │                             │
                 │  ┌──────────────────────┐   ┌────────┴─────────┐                   │
                 │  │ postgres (pgvector)  │   │ pgadmin4         │                   │
                 │  │ documentos_rag       │   │ UI en :5050      │                   │
                 │  │ chunks_rag (HNSW)    │   └──────────────────┘                   │
                 │  └──────────────────────┘                                          │
                 └────────────────────────────────────────────────────────────────────┘
                                        ▲
                                        │ query: → cosine/HNSW → top-k
                              tu capa de retrieval / agentes
```

## Stack

| Componente | Tecnología | Detalle |
|---|---|---|
| Base de datos | PostgreSQL 17 + pgvector | `pgvector/pgvector:pg17-bookworm`, índice HNSW (cosine) |
| Embeddings | vLLM `v0.33.0` | `intfloat/multilingual-e5-small` (384d), API OpenAI en `/v1/embeddings` |
| Ingesta | docling `2.150.0` | `HybridChunker` con el tokenizer de e5, `max_tokens=450` |
| Gestión de deps | uv | `pyproject.toml` + `uv.lock` en la raíz (entorno `./.venv` compartido), imagen construida con `uv sync --frozen` |
| Orquestación | Docker Compose | 4 servicios con healthchecks y dependencias |

## Requisitos

- Docker + Docker Compose
- GPU NVIDIA con drivers recientes (recomendado; vLLM funciona en CPU pero muy lento)
- [uv](https://docs.astral.sh/uv/) (solo para desarrollo local; el proyecto uv vive en la raíz y su entorno `./.venv` es compartido por todo el código)

## Puesta en marcha

```bash
# 1. Configurar el entorno
cp .env.example .env
#    Edita .env: POSTGRES_PASSWORD, PGADMIN_EMAIL, PGADMIN_PASSWORD

# 2. Levantar todo (la ingesta corre automáticamente al arrancar)
docker compose up -d

# 3. Verificar
docker compose ps
docker compose logs -f ingest
```

> **Nota:** los scripts de `init/` solo se ejecutan la primera vez que arranca
> PostgreSQL con el volumen `postgres_data` vacío.

## Ingesta de documentos

1. Suelta tus documentos en `docs/` (subcarpetas también valen).
2. Ejecuta la ingesta:
   ```bash
   docker compose up -d        # arranca todo y la ingesta corre sola
   docker compose up ingest    # o solo la ingesta, sin tocar el resto
   ```
3. Comprueba el resultado:
   ```bash
   docker exec postgres-vector psql -U admin -d mydatabase -c \
     "SELECT d.titulo, count(c.id) AS chunks FROM documentos_rag d
      JOIN chunks_rag c ON c.doc_id = d.id GROUP BY d.id;"
   ```

**Formatos soportados**

- **docling**: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.xls`, `.html`, `.htm`, `.md`, `.csv`, `.odt`, `.ods`, `.odp`, `.epub`, `.rtf`, `.adoc`, `.tex`, imágenes (`.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, `.webp`)
- **texto plano** (lectura directa): `.txt`

**Idempotencia** — cada fichero se identifica por su hash SHA-256 guardado en `documentos_rag.metadata->>'sha256'`:

| Situación | Resultado |
|---|---|
| Fichero nuevo | Se convierte, trocea, embebe e inserta |
| Fichero sin cambios | Se omite (`Sin cambios: ...`, 0 chunks insertados) |
| Fichero modificado | Se reemplaza en una transacción (delete + insert con cascade, sin duplicados) |
| Error en un fichero | Se registra y continúa con el resto (exit code 1 al final) |

## Esquema de la base de datos

Definido en `init/02-schema.sql`:

**RAG**

- `documentos_rag` — `titulo`, `fuente`, `perfil_id`, `metadata JSONB` (aquí vive el `path` y el `sha256` de cada fichero ingerido)
- `chunks_rag` — `doc_id`, `chunk_index`, `texto`, `metadata JSONB` (`seccion`, `pagina`...), `embedding VECTOR(384)`, `UNIQUE (doc_id, chunk_index)`
- Índices: **HNSW** sobre `embedding` (distancia de coseno) y **GIN** sobre `metadata`

**Perfil** — `perfil`, `experiencia`, `proyectos`, `tecnologias`, `idiomas`, `educacion`, sembradas por `init/03-seed.sql`.

> ⚠️ `03-seed.sql` hace `TRUNCATE ... CASCADE` de todas las tablas (incluidas
> las RAG). Como los scripts de `init/` solo corren con el volumen vacío, esto
> solo puede pasar si borras `postgres_data` y vuelves a arrancar.

## Búsqueda semántica

**Crítico:** `multilingual-e5-small` exige prefijos — indexa con `passage: ` y busca con `query: `. La BD guarda el texto **crudo** (sin prefijo); el prefijo solo se aplica al pedir el vector al endpoint.

```bash
# 1. Embedder la consulta con el prefijo "query: "
curl -s http://localhost:8000/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model": "multilingual-e5-small", "input": ["query: ¿cómo se trocean los documentos?"]}'
```

```sql
-- 2. Buscar los chunks más similares (distancia de coseno con el índice HNSW)
SELECT c.id,
       d.titulo,
       c.metadata->>'seccion' AS seccion,
       left(c.texto, 80) AS texto,
       1 - (c.embedding <=> '<vector_de_384_dims>'::vector) AS similitud
FROM chunks_rag c
JOIN documentos_rag d ON d.id = c.doc_id
ORDER BY c.embedding <=> '<vector_de_384_dims>'::vector
LIMIT 5;
```

## Servidor MCP

`mcp/server.py` expone dos tools: `postgres_query` (SQL de solo lectura) y
`rag_search` (embeddings + pgvector). En `docker compose up` corre como servicio
`mcp` con transporte **streamable-http**:

```bash
docker compose up -d mcp
# cliente MCP → http://localhost:8001/mcp
```

Fuera de Docker sigue siendo stdio por defecto (el cliente lanza el proceso):
`MCP_TRANSPORT=streamable-http uv run --extra mcp python mcp/server.py`.

## Variables de entorno

Todas se definen en `.env` (copia `.env.example`):

| Variable | Default | Descripción |
|---|---|---|
| `POSTGRES_USER` | — | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | — | Contraseña de PostgreSQL |
| `POSTGRES_DB` | — | Base de datos |
| `POSTGRES_PORT` | `5432` | Puerto expuesto de PostgreSQL |
| `PGADMIN_EMAIL` | — | Email de acceso a pgAdmin |
| `PGADMIN_PASSWORD` | — | Contraseña de pgAdmin |
| `PGADMIN_PORT` | `5050` | Puerto expuesto de pgAdmin |
| `EMBEDDINGS_PORT` | `8000` | Puerto expuesto de vLLM |
| `EMBEDDINGS_MODEL` | `multilingual-e5-small` | Nombre del modelo servido |
| `VLLM_IMAGE_TAG` | `v0.33.0` | Tag de la imagen `vllm/vllm-openai` |
| `MCP_PORT` | `8001` | Puerto expuesto del servidor MCP (en el contenedor escucha siempre el 8001) |

Valores fijados en `docker-compose.yaml` (no suelen tocarse):

| Variable | Valor | Descripción |
|---|---|---|
| `DOCS_DIR` | `/docs` | Montado desde `./docs` (solo lectura) |
| `EMBEDDINGS_BASE_URL` | `http://embedding:8000/v1` | Endpoint usado por la ingesta |
| `EMBEDDINGS_DIM` | `384` | Dimensión esperada de los vectores |
| `CHUNK_MAX_TOKENS` | `450` | Límite por chunk (e5 admite 512) |
| `HF_MODEL_ID` | `intfloat/multilingual-e5-small` | Tokenizer usado por el chunker |

## Estructura del proyecto

```
AgentePersonal/
├── pyproject.toml            # proyecto uv (raíz): dependencias compartidas
├── uv.lock                   # lockfile compartido
├── .dockerignore             # contexto mínimo para la imagen de ingesta
├── docker-compose.yaml       # 5 servicios: postgres, pgadmin, embedding, ingest, mcp
├── .env.example              # Plantilla de variables de entorno
├── docs/                     # Tus documentos (montados en la ingesta)
│   └── .gitkeep
├── init/                     # Se ejecutan solo con el volumen vacío
│   ├── 01-init.sql           # extensión pgvector
│   ├── 02-schema.sql         # esquema (perfil + RAG)
│   └── 03-seed.sql           # seed de perfil (TRUNCATE + INSERTs)
├── ingest/                   # Servicio de ingesta (código, no deps)
│   ├── Dockerfile            # python:3.12-slim + uv (contexto = raíz)
│   ├── main.py               # orquestador: scan → sha256 → parse → embed → insert
│   ├── parsing.py            # docling HybridChunker + ruta directa para .txt
│   ├── embeddings.py         # cliente /v1/embeddings (prefijo passage:, reintentos)
│   ├── db.py                 # psycopg3 + pgvector, idempotencia por sha256
│   └── config.py             # configuración desde variables de entorno
└── mcp/                      # Servidor MCP (SQL de solo lectura + búsqueda RAG)
    ├── Dockerfile            # python:3.12-slim + uv, extra `mcp` (sin torch)
    └── server.py             # tools postgres_query y rag_search (stdio / streamable-http)
```

## Desarrollo local (uv)

El entorno uv se gestiona **en la raíz** del proyecto, de modo que cualquier
código del repo (la ingesta u otro módulo futuro) reutiliza el mismo `./.venv`:

```bash
uv sync --all-extras                     # crea/actualiza ./.venv en la raíz (extras: ingest, mcp)
uv add <paquete>                         # añade una dependencia a pyproject.toml + uv.lock
uv run python ingest/main.py             # ejecuta la ingesta localmente (sin Docker)
```

En Docker no cambia nada: la imagen instala las mismas dependencias con
`uv sync --frozen` usando `pyproject.toml` + `uv.lock` de la raíz
(`build.context: .`, `dockerfile: ingest/Dockerfile`).

## Notas y troubleshooting

- **vLLM `--runner=pooling`**: desde v0.33 `--task=embed` ya no existe; el modelo va como argumento posicional y el modo pooling se activa con `--runner=pooling`.
- **`--gpu-memory-utilization=0.30`**: deja el 70 % de la GPU libre para otros usos. Súbelo si solo usas esta máquina para RAG.
- **Logs**: `docker compose logs -f embedding` / `docker compose logs -f ingest`.
- **Re-ingesta manual**: `docker compose up ingest` (termina y se para, es one-shot).
- **Volumen `hf_cache`**: cachea los pesos de HuggingFace (tokenizer + modelo); el aviso *"not created by Docker Compose"* es benigno si se creó con un `docker run` previo.
- **Tamaños**: imagen de ingesta ~2.9 GB, imagen vLLM ~35 GB.
- **Modelo caído**: la ingesta espera con timeout (`WAIT_TIMEOUT_S`, 300 s) a que `/health` de vLLM responda antes de empezar.

## Roadmap

- [ ] **API de retrieval** — endpoint FastAPI (`/search`) que exponga el pipeline de búsqueda (prefijo `query: ` → HNSW → top-k + score) para que la capa de agentes no tenga que tocar SQL.
- [ ] **Reranking** — cross-encoder sobre el top-k ampliado para mejorar la precisión.
- [ ] **Capa de agentes / chat** — LLM que consuma la API de retrieval para responder preguntas sobre el corpus y el perfil.
- [ ] **Filtros por metadatos** — combinar el índice GIN con la búsqueda vectorial (por ejemplo, filtrar por `seccion`, `pagina` o `fuente`).
- [ ] **Watch de `docs/`** — recarga automática ante cambios (inotify/webhook) en lugar de re-ejecutar la ingesta a mano.
- [ ] **Tests + CI** — smoke tests del pipeline (parse → embed → insert) en CI.
