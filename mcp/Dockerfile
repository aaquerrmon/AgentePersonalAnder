FROM python:3.12-slim

# uv (patrón oficial: https://docs.astral.sh/uv/guides/integration/docker/)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Primero solo los ficheros de dependencias, para cachear la capa de instalación
# torch/torchvision/transformers viven en el extra `ingest`, así que no se instalan aquí
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --extra mcp

COPY mcp/server.py ./

ENV PYTHONUNBUFFERED=1

# --no-sync: el entorno ya está sincronizado en la imagen, no toca la red al arrancar
CMD ["uv", "run", "--no-sync", "python", "server.py"]
