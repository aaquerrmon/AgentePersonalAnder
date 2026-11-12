FROM python:3.12-slim

# uv (patrón oficial: https://docs.astral.sh/uv/guides/integration/docker/)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Primero solo los ficheros de dependencias, para cachear la capa de instalación
# (torch/docling no se instalan: solo el extra `agent`)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --extra agent

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# --no-sync: el entorno ya está sincronizado en la imagen, no toca la red al arrancar
CMD ["uv", "run", "--no-sync", "python", "-m", "app.main"]
