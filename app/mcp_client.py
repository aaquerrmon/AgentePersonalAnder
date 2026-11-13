
import json
import logging
import time
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import create_model

from app.config import MCP_URL

logger = logging.getLogger("app.mcp")

# langchain-mcp-adapters exige mcp<2 y el servidor usa mcp 2.x (MCPServer),
# así que el puente JSON-Schema -> herramienta langchain se hace aquí a mano.
_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _args_schema(input_schema: dict) -> type:
    """Modelo pydantic dinámico a partir del inputSchema de la tool MCP."""

    required = set(input_schema.get("required", []))

    fields = {
        name: (
            _JSON_TYPES.get(prop.get("type"), Any),
            ... if name in required else prop.get("default", None),
        )
        for name, prop in input_schema.get("properties", {}).items()
    }

    return create_model("McpToolArgs", **fields)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


async def _call_tool(name: str, arguments: dict) -> str:
    """Ejecuta una tool MCP. Conexión por llamada: sin estado y se
    recupera solo si el servidor MCP se reinicia."""

    started = time.monotonic()
    logger.info(
        "MCP ▶ %s | entrada: %s",
        name,
        _clip(json.dumps(arguments, ensure_ascii=False, default=str), 2000),
    )

    async with streamable_http_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)

    text = "".join(
        block.text
        for block in result.content
        if getattr(block, "type", None) == "text"
    )

    logger.info(
        "MCP ◀ %s | salida (%d caracteres, %.2fs): %s",
        name, len(text), time.monotonic() - started, _clip(text, 4000),
    )

    if result.is_error:
        logger.error("MCP ✗ %s: %s", name, text)
        raise RuntimeError(text or f"Error en la tool MCP {name}")

    return text


_SCHEMA_SQL = """
SELECT table_name,
       string_agg(column_name || ' ' || data_type, ', '
                  ORDER BY ordinal_position) AS columnas
FROM information_schema.columns
WHERE table_schema = 'public'
GROUP BY table_name
ORDER BY table_name
"""


async def get_database_schema() -> str:
    """Tablas y columnas visibles para el usuario RO, formateadas para
    inyectarlas en el prompt del agente SQL (una sola petición MCP)."""

    raw = await _call_tool("postgres_query", {"query": _SCHEMA_SQL})
    data = json.loads(raw)

    if data.get("error"):
        raise RuntimeError(f"Error consultando el esquema: {data['error']}")

    return "\n".join(
        f"- {row['table_name']}: {row['columnas']}"
        for row in data.get("rows", [])
    )


async def get_mcp_tools():

    async with streamable_http_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools

    tools = [
        StructuredTool(
            name=item.name,
            description=item.description or "",
            args_schema=_args_schema(item.input_schema),
            coroutine=lambda _name=item.name, **kwargs: _call_tool(
                _name, kwargs
            ),
        )
        for item in mcp_tools
    ]

    logger.info(
        "Herramientas MCP en %s: %s",
        MCP_URL, ", ".join(item.name for item in tools),
    )

    return tools
