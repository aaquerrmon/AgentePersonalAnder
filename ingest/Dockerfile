FROM python:3.12-slim

# Dependencias de sistema: libgl1/libglib para OpenCV (rapidocr) y OpenMP (torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# uv (patrón oficial: https://docs.astral.sh/uv/guides/integration/docker/)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Primero solo los ficheros de dependencias, para cachear la capa de instalación
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY *.py ./

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/root/.cache/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1

# --no-sync: el entorno ya está sincronizado en la imagen, no toca la red al arrancar
CMD ["uv", "run", "--no-sync", "python", "main.py"]
