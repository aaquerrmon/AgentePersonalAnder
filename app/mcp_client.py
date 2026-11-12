
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import create_model

from app.config import MCP_URL

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


async def _call_tool(name: str, arguments: dict) -> str:
    """Ejecuta una tool MCP. Conexión por llamada: sin estado y se
    recupera solo si el servidor MCP se reinicia."""

    async with streamable_http_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)

    text = "".join(
        block.text
        for block in result.content
        if getattr(block, "type", None) == "text"
    )

    if result.is_error:
        raise RuntimeError(text or f"Error en la tool MCP {name}")

    return text


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

    print("Herramientas MCP:")

    for item in tools:
        print(f"  - {item.name}")

    return tools
