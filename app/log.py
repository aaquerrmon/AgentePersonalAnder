
import logging
import os

# HH:MM:SS.mmm NIVEL [logger] mensaje — pensado para `docker logs`
FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s [%(name)s] %(message)s"


def setup_logging():
    """Nivel global por LOG_LEVEL (DEBUG por defecto) + loggers ruidosos."""

    level = os.getenv("LOG_LEVEL", "DEBUG").upper()

    logging.basicConfig(
        level=level,
        format=FORMAT,
        datefmt="%H:%M:%S",
        force=True,
    )

    # httpx imprime cada petición: "HTTP Request: POST http://llm:8080/v1/... 200"
    logging.getLogger("httpx").setLevel("INFO")
    logging.getLogger("httpcore").setLevel("WARNING")

    # Peticiones JSON-RPC del cliente MCP y del SDK de OpenAI
    logging.getLogger("mcp").setLevel(level)
    logging.getLogger("openai").setLevel(level)
