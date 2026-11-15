# AgentePersonal

![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker%20Compose-2496ED?style=flat&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9?style=flat)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?style=flat&logo=postgresql&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-0.7-56B2A8?style=flat)
![vLLM](https://img.shields.io/badge/vLLM-0.33-1B4D4E?style=flat)
![docling](https://img.shields.io/badge/docling-2.150-E85D4C?style=flat)

Infraestructura **RAG** (Retrieval-Augmented Generation) personal: los documentos de `docs/` se convierten y trocean automáticamente con **docling**, se embeben con **vLLM** (`intfloat/multilingual-e5-small`, 384 dimensiones) y se almacenan en **PostgreSQL + pgvector** para búsqueda semántica ultrarrápida. Sobre esa base corre una **capa de agentes** (supervisor + especialistas SQL y RAG) que responde por **Telegram** en streaming — ver [Capa de agentes](#capa-de-agentes-telegram).

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
                              tu capa de agentes: servicio `agent` (ver «Capa de agentes»)
```

## Stack

| Componente | Tecnología | Detalle |
|---|---|---|
| Base de datos | PostgreSQL 17 + pgvector | `pgvector/pgvector:pg17-bookworm`, índice HNSW (cosine) |
| Embeddings | vLLM `v0.33.0` | `intfloat/multilingual-e5-small` (384d), API OpenAI en `/v1/embeddings` |
| LLM | vLLM `v0.33.0` | `Qwen/Qwen3-4B-AWQ` (AWQ), API OpenAI en `/v1/chat/completions`, tool-calling (hermes) + reasoning (qwen3), solo en `127.0.0.1:8080` |
| Ingesta | docling `2.150.0` | `HybridChunker` con el tokenizer de e5, `max_tokens=450` |
| Agentes | LangChain 1.x + LangGraph | Supervisor con checkpointer en Postgres y dos especialistas (SQL y RAG) |
| Chat | python-telegram-bot | Long polling, respuesta en streaming y allowlist por ID de usuario |
| Gestión de deps | uv | `pyproject.toml` + `uv.lock` en la raíz (entorno `./.venv` compartido), imagen construida con `uv sync --frozen` |
| Orquestación | Docker Compose | 7 servicios con healthchecks y dependencias |

## Requisitos

- Docker + Docker Compose
- GPU NVIDIA con drivers recientes (recomendado; vLLM funciona en CPU pero muy lento)
- [uv](https://docs.astral.sh/uv/) (solo para desarrollo local; el proyecto uv vive en la raíz y su entorno `./.venv` es compartido por todo el código)

## Puesta en marcha

```bash
# 1. Configurar el entorno
cp .env.example .env
#    Edita .env: POSTGRES_PASSWORD, PGADMIN_EMAIL, PGADMIN_PASSWORD,
#    TELEGRAM_BOT_TOKEN (de @BotFather) y TELEGRAM_ALLOWED_USERS
#    (RO_USER/RO_PASSWORD las usa el usuario de solo lectura del MCP)

# 2. Levantar todo (la ingesta corre automáticamente al arrancar)
docker compose up -d

# 3. Verificar
docker compose ps
docker compose logs -f ingest   # ingesta de documentos
docker compose logs -f agent    # bot de Telegram
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

## Capa de agentes (Telegram)

El servicio `agent` (imagen `app/Dockerfile`) es un bot de Telegram con un
**supervisor** que nunca responde de memoria: delega en dos especialistas y
combina sus resultados.

```
usuario ──► Telegram ──► supervisor (LangGraph + checkpointer en Postgres)
                            │
                            ├─ consultar_base_datos ─► agente SQL ─┐
                            │                                      ├─► MCP ─► postgres_query ─► BD
                            └─ buscar_documentacion ─► agente RAG ─┘        rag_search ─► vLLM + pgvector
```

| Módulo | Responsabilidad |
|---|---|
| `app/main.py` | Arranque: pool de conexiones, checkpointer (memoria por hilo) y bot en long polling |
| `app/agents/supervisor.py` | Orquestador: decide a qué especialista delegar y fusiona las respuestas |
| `app/agents/sql_agent.py` | Agente SQL, solo lectura, con el esquema de la BD **fijo** en el prompt (`SCHEMA_SQL`) |
| `app/agents/rag_agent.py` | Agente RAG: solo recuperación documental, no ejecuta SQL |
| `app/mcp_client.py` | Puente cliente MCP → tools de LangChain (conexión por llamada, sin estado) |
| `app/telegram_bot.py` | Handlers `/start`, `/help`, `/clear` + control de acceso por ID |
| `app/trace.py` | Streaming en vivo (estado y respuesta editándose) y logs de tokens |
| `app/log.py` | Formato de log pensado para `docker logs` |

Detalles que conviene saber:

- **Identidad** — los tres prompts comparten la constante `IDENTIDAD`
  (`app/config.py`): el asistente es el CV de **Ander Aquerreta Montoro**, que
  es la única persona con perfil en la BD, y si el usuario no especifica un
  nombre se presupone que habla de él (no pide aclaraciones ni filtra por nombre).
- **Esquema fijo** — `SCHEMA_SQL` vive en `app/agents/sql_agent.py` y **no se
  consulta al arrancar**: así el agente funciona igual sin Postgres/MCP (el caso
  del portfolio, con los datos en JSON). Si cambias `init/02-schema.sql`,
  actualiza también ese literal.
- **Memoria** — cada conversación es un hilo (`telegram:{chat_id}:{user_id}`,
  separado también en grupos) con checkpointer en Postgres; `/clear` borra el
  hilo y el supervisor deja de estar anclado a respuestas anteriores.
- **Streaming** — se publica una línea de estado por agente
  ("Agente SQL buscando en base de datos...") y la respuesta se va editando
  token a token, respetando los rate limits de Telegram (1,5 s / 2 s).
- **Razonamiento** — Qwen3 devuelve `reasoning` en streaming; `patch_reasoning_stream()`
  lo recupera para poder registrar el pensamiento en los logs.

### Comandos del bot

| Comando | Qué hace |
|---|---|
| `/start`, `/help` | Presentación y lista de capacidades |
| `/clear` | Borra la conversación del hilo |

> **Acceso:** `TELEGRAM_ALLOWED_USERS` es una allowlist de IDs numéricos
> (no @usuarios). Si está vacía, **cualquiera** puede usar el bot.

## Seguridad

- **Base de datos** — el usuario `RO_USER` (creado en `init/01-init.sql`) solo
  tiene `SELECT`. Además, el servidor MCP rechaza todo lo que no sea una única
  consulta `SELECT`/`WITH` y la ejecuta en una transacción `READ ONLY` con
  `statement_timeout = 10s`.
- **LLM** — solo se publica en `127.0.0.1` del host; no se expone en la LAN.
- **Telegram** — control de acceso por ID en `TELEGRAM_ALLOWED_USERS`; si está
  vacío el bot responde a cualquiera (no lo uses así en grupos).
- **Red** — los servicios solo se comunican por la red interna `agent-net`.

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
| `EMBEDDINGS_PORT` | `8000` | Puerto expuesto de vLLM (embeddings) |
| `EMBEDDINGS_MODEL` | `multilingual-e5-small` | Nombre del modelo servido |
| `VLLM_IMAGE_TAG` | `v0.33.0` | Tag de la imagen `vllm/vllm-openai` (compartida por embeddings y LLM) |
| `LLM_PORT` | `8080` | Puerto expuesto del LLM (en el contenedor escucha siempre el 8080; solo loopback) |
| `LLM_MODEL` | `Qwen/Qwen3-4B-AWQ` | Modelo HF servido por el LLM |
| `LLM_SERVED_MODEL_NAME` | `local-llm` | Nombre del modelo en la API (`/v1/models`) |
| `LLM_GPU_MEMORY_UTILIZATION` | `0.62` | Fracción de VRAM que reserva el LLM (embeddings usa 0.1) |
| `LLM_MAX_MODEL_LEN` | `4096` | Ventana de contexto máxima del LLM |
| `MCP_PORT` | `8001` | Puerto expuesto del servidor MCP (en el contenedor escucha siempre el 8001) |
| `RO_USER` | — | Usuario de solo lectura creado en `01-init.sql` (lo usa el servidor MCP) |
| `RO_PASSWORD` | — | Contraseña del usuario de solo lectura |
| `RAG_TABLE` | `chunks_rag` | Tabla que consulta `rag_search` |
| `RAG_TOP_K` | `5` | Resultados por defecto de `rag_search` |
| `MCP_URL` | `http://mcp:8001/mcp` | Endpoint MCP que usa la capa de agentes |
| `MCP_TRANSPORT` | `stdio` | `streamable-http` dentro de docker compose |
| `TELEGRAM_BOT_TOKEN` | — | Token de @BotFather (obligatoria, la lee `app/config.py`) |
| `TELEGRAM_ALLOWED_USERS` | vacío | IDs numéricos permitidos, separados por comas; vacío = bot abierto |
| `LLM_TEMPERATURE` | `0` | Temperatura del chat del agente |
| `LOG_LEVEL` | `DEBUG` | Nivel de log del servicio `agent` |

Valores por defecto (fijados en `docker-compose.yaml` o en el código; no suelen tocarse):

| Variable | Valor | Descripción |
|---|---|---|
| `DOCS_DIR` | `/docs` | Montado desde `./docs` (solo lectura) |
| `EMBEDDINGS_BASE_URL` | `http://embedding:8000/v1` | Endpoint usado por la ingesta |
| `EMBEDDINGS_DIM` | `384` | Dimensión esperada de los vectores |
| `EMBED_BATCH_SIZE` | `32` | Textos por petición al endpoint de embeddings |
| `EMBED_TIMEOUT_S` | `60` | Timeout de cada petición de embeddings |
| `WAIT_TIMEOUT_S` | `300` | Espera máxima a PostgreSQL / vLLM al arrancar |
| `CHUNK_MAX_TOKENS` | `450` | Límite por chunk (e5 admite 512) |
| `HF_MODEL_ID` | `intfloat/multilingual-e5-small` | Tokenizer usado por el chunker |

## Estructura del proyecto

```
AgentePersonal/
├── pyproject.toml            # proyecto uv (raíz): dependencias compartidas (extras: ingest, mcp, agent)
├── uv.lock                   # lockfile compartido
├── .dockerignore             # contexto mínimo para las imágenes
├── docker-compose.yaml       # 7 servicios: postgres, pgadmin, llm, embedding, ingest, mcp, agent
├── .env.example              # Plantilla de variables de entorno
├── docs/                     # Tus documentos (montados en la ingesta)
│   ├── .gitkeep
│   ├── TFG.pdf
│   └── TFM.pdf
├── init/                     # Se ejecutan solo con el volumen vacío
│   ├── 01-init.sql           # extensión pgvector + usuario de solo lectura
│   ├── 02-schema.sql         # esquema (perfil + RAG)
│   └── 03-seed.sql           # seed de perfil (TRUNCATE + INSERTs)
├── app/                      # Capa de agentes + bot de Telegram (servicio `agent`)
│   ├── Dockerfile            # python:3.12-slim + uv, extra `agent`
│   ├── main.py               # arranque: pool + checkpointer + long polling
│   ├── config.py             # variables de entorno + IDENTIDAD (prompts)
│   ├── agents/
│   │   ├── supervisor.py     # orquestador (delega en SQL/RAG)
│   │   ├── sql_agent.py      # agente SQL + SCHEMA_SQL fijo
│   │   └── rag_agent.py      # agente RAG
│   ├── mcp_client.py         # puente cliente MCP → tools de LangChain
│   ├── telegram_bot.py       # handlers y control de acceso
│   ├── trace.py              # streaming en Telegram + logs de tokens
│   └── log.py                # formato de log para `docker logs`
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
uv sync --all-extras                     # crea/actualiza ./.venv en la raíz (extras: ingest, mcp, agent)
uv add <paquete>                         # añade una dependencia a pyproject.toml + uv.lock
uv run python ingest/main.py             # ejecuta la ingesta localmente (sin Docker)
uv run python -m app.main                # arranca el bot de Telegram (requiere .env)
```

En Docker no cambia nada: cada imagen instala las mismas dependencias con
`uv sync --frozen` usando `pyproject.toml` + `uv.lock` de la raíz
(`build.context: .` con el Dockerfile de `ingest/`, `mcp/` o `app/`).

## Notas y troubleshooting

- **vLLM `--runner=pooling`**: desde v0.33 `--task=embed` ya no existe; el modelo va como argumento posicional y el modo pooling se activa con `--runner=pooling`.
- **`--gpu-memory-utilization`**: `0.62` para el LLM y `0.1` para embeddings, así deja GPU libre para otros usos. Súbelo si solo usas esta máquina para RAG.
- **Logs**: `docker compose logs -f embedding` / `ingest` / `agent`.
- **Re-ingesta manual**: `docker compose up ingest` (termina y se para, es one-shot).
- **Volumen `hf_cache`**: cachea los pesos de HuggingFace (tokenizer + modelo); el aviso *"not created by Docker Compose"* es benigno si se creó con un `docker run` previo.
- **Tamaños**: imagen de ingesta ~2.9 GB, imagen vLLM ~35 GB.
- **Modelo caído**: la ingesta espera con timeout (`WAIT_TIMEOUT_S`, 300 s) a que `/health` de vLLM responda antes de empezar.

## Roadmap

- [x] **Capa de agentes / chat** — supervisor LangGraph + especialistas SQL/RAG con streaming en Telegram (servicio `agent`).
- [ ] **API de retrieval** — endpoint FastAPI (`/search`) que exponga el pipeline de búsqueda (prefijo `query: ` → HNSW → top-k + score) para que la capa de agentes no tenga que tocar SQL.
- [ ] **Reranking** — cross-encoder sobre el top-k ampliado para mejorar la precisión.
- [ ] **Portfolio sin infraestructura** — sustituir Postgres/MCP/vLLM por datos en JSON y un LLM remoto para incrustar el asistente en la web (el esquema ya es un literal, `SCHEMA_SQL`).
- [ ] **Filtros por metadatos** — combinar el índice GIN con la búsqueda vectorial (por ejemplo, filtrar por `seccion`, `pagina` o `fuente`).
- [ ] **Watch de `docs/`** — recarga automática ante cambios (inotify/webhook) en lugar de re-ejecutar la ingesta a mano.
- [ ] **Tests + CI** — smoke tests del pipeline (parse → embed → insert) y del agente, en CI.
