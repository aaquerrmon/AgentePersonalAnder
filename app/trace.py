
import asyncio
import json
import logging
import time
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessageChunk

logger = logging.getLogger("app.trace")

# Líneas de estado por agente que se muestran en Telegram
DELEGATION_LINES = {
    "consultar_base_datos": "Agente SQL buscando en base de datos...",
    "buscar_documentacion": "Agente RAG buscando en documentos...",
}
SUPERVISOR_LINE = "Agente Supervisor razonando..."


def patch_reasoning_stream():
    """langchain-openai descarta delta.reasoning (el pensamiento de Qwen3);
    lo recuperamos en additional_kwargs['reasoning'], cuyo merge al agregar
    chunks concatena strings, así que no rompe la respuesta final."""

    import langchain_openai.chat_models.base as lc_base

    original = lc_base._convert_delta_to_message_chunk

    if getattr(original, "reasoning_patch", False):
        return

    def convert(delta, default_class):
        chunk = original(delta, default_class)
        # delta es un Mapping (así lo declara el conversor original)
        reasoning = delta.get("reasoning") or delta.get("reasoning_content")
        if reasoning and isinstance(chunk, AIMessageChunk):
            chunk.additional_kwargs["reasoning"] = reasoning
        return chunk

    convert.reasoning_patch = True
    lc_base._convert_delta_to_message_chunk = convert


def _short(value, limit: int = 300) -> str:
    try:
        text = (
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, default=str)
        )
    except Exception:
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


class TelegramTrace(AsyncCallbackHandler):
    """Traza de una conversación: logs de depuración + mensajes en vivo de
    Telegram (estado y respuesta en streaming).

    - Estado: qué agente está trabajando ("Agente SQL buscando en base de
      datos..."), sin tokens ni tiempos.
    - Respuesta: se va editando a medida que llegan los tokens del supervisor.

    Los tokens de los sub-agentes (SQL/RAG) se clasifican como internos
    recorriendo el árbol de runs hasta encontrar una tool.

    bot=None → solo escribe en los logs (útil para pruebas sin Telegram).
    """

    STATUS_EVERY = 1.5  # s mínimos entre edits de estado (límite de Telegram)
    ANSWER_EVERY = 2.0  # s mínimos entre edits de la respuesta

    def __init__(self, bot=None, chat_id=None):
        self.bot = bot
        self.chat_id = chat_id

        self.parents: dict[UUID, UUID | None] = {}
        self.chain_names: dict[UUID, str] = {}
        self.tool_runs: set[UUID] = set()
        self.active_tools: dict[UUID, tuple[str, str, float]] = {}
        self.error_line = ""

        # Líneas de agente en orden de aparición, sin repetir
        self.agent_lines: list[str] = []
        self.answer_parts: list[str] = []

        self.status_msg = None
        self.answer_msg = None
        self.next_status = 0.0
        self.next_answer = 0.0
        self.closed = False

        self._lock = asyncio.Lock()

    # ------------------------------------------------------------
    # Árbol de runs: interno (dentro de una tool) o supervisor
    # ------------------------------------------------------------

    def _remember(self, run_id, parent_run_id):
        self.parents[run_id] = parent_run_id

    def _is_inner(self, run_id) -> bool:
        current = self.parents.get(run_id)
        while current is not None:
            if current in self.tool_runs:
                return True
            current = self.parents.get(current)
        return False

    # ------------------------------------------------------------
    # Mensajes en vivo
    # ------------------------------------------------------------

    def _add_line(self, line: str):
        """Las líneas se acumulan en orden y no se repiten: al terminar
        quedan visibles como history por encima de la respuesta."""

        if line not in self.agent_lines:
            self.agent_lines.append(line)

    def _compose_status(self) -> str:
        lines = list(self.agent_lines)

        if self.error_line:
            lines.append(self.error_line)

        if not lines:
            lines.append(SUPERVISOR_LINE)

        return "\n".join(lines)[:3800]

    async def _push_status(self, force: bool = False):
        text = self._compose_status()
        now = time.monotonic()
        if not force and now < self.next_status:
            return
        self.next_status = now + self.STATUS_EVERY

        if self.bot is None:
            logger.info("— %s", text.replace("\n", "\n  "))
            return

        async with self._lock:
            try:
                if self.status_msg is None:
                    self.status_msg = await self.bot.send_message(
                        self.chat_id, text
                    )
                elif self.status_msg.text != text:
                    self.status_msg = await self.status_msg.edit_text(text)
            except Exception as e:
                # "message is not modified" y demás: nunca romper la consulta
                logger.debug("No se pudo actualizar el estado: %s", e)

    async def _push_answer(self, force: bool = False):
        if not self.answer_parts:
            return
        text = "".join(self.answer_parts)[:4000]
        now = time.monotonic()
        if not force and now < self.next_answer:
            return
        self.next_answer = now + self.ANSWER_EVERY

        if self.bot is None:
            logger.info(
                "— parcial (%d caracteres): %s", len(text), _short(text, 200)
            )
            return

        async with self._lock:
            try:
                if self.answer_msg is None:
                    self.answer_msg = await self.bot.send_message(
                        self.chat_id, text
                    )
                elif self.answer_msg.text != text:
                    self.answer_msg = await self.answer_msg.edit_text(text)
            except Exception as e:
                logger.debug("No se pudo actualizar la respuesta: %s", e)

    # ------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------

    async def finish(self, answer: str):
        """Respuesta completa: corrige el mensaje en streaming y trocea."""

        self.closed = True
        self.answer_parts = [answer]

        if self.bot is None:
            logger.info("— respuesta final (%d caracteres): %s", len(answer), answer)
            await self._push_status(force=True)
            return

        async with self._lock:
            try:
                first = answer[:4000]
                if self.answer_msg is None:
                    if first:
                        self.answer_msg = await self.bot.send_message(
                            self.chat_id, first
                        )
                elif self.answer_msg.text != first:
                    self.answer_msg = await self.answer_msg.edit_text(first)
                for i in range(4000, len(answer), 4000):
                    await self.bot.send_message(
                        self.chat_id, answer[i : i + 4000]
                    )
            except Exception as e:
                logger.warning("No se pudo enviar la respuesta final: %s", e)

        await self._push_status(force=True)

    async def fail(self, error):
        self.closed = True
        self.error_line = f"❌ {_short(str(error), 300)}"
        await self._push_status(force=True)

    # ------------------------------------------------------------
    # Callbacks de langchain
    # ------------------------------------------------------------

    async def on_chat_model_start(
        self, serialized, messages, *, run_id, parent_run_id=None,
        metadata=None, **kwargs
    ):
        self._remember(run_id, parent_run_id)
        model = (
            (metadata or {}).get("ls_model_name")
            or (serialized or {}).get("kwargs", {}).get("model")
            or (serialized or {}).get("name")
            or "?"
        )
        quien = "interno" if self._is_inner(run_id) else "supervisor"
        logger.info("LLM ▶ %s (%s)", model, quien)
        if quien == "supervisor":
            self._add_line(SUPERVISOR_LINE)
        for batch in messages:
            for message in batch:
                logger.debug(
                    "    prompt %s: %s",
                    type(message).__name__,
                    _short(getattr(message, "content", ""), 2000),
                )
        await self._push_status()

    async def on_llm_new_token(
        self, token, *, run_id, parent_run_id=None, chunk=None, **kwargs
    ):
        self._remember(run_id, parent_run_id)

        reasoning = ""
        message = getattr(chunk, "message", None)
        if message is not None:
            reasoning = message.additional_kwargs.get("reasoning") or ""

        if reasoning:
            logger.debug("💭 %s", reasoning)

        if token:
            if self._is_inner(run_id):
                logger.debug("token interno: %r", token)
            else:
                self.answer_parts.append(token)
                logger.debug("token: %r", token)
                await self._push_answer()

        await self._push_status()

    async def on_llm_end(
        self, response, *, run_id, parent_run_id=None, **kwargs
    ):
        # generations es list[list[Generation]]: la primera tanda, primer intento
        first_batch = response.generations[0] if response.generations else []
        generation = first_batch[0] if first_batch else None
        message = getattr(generation, "message", None)
        content = getattr(message, "content", "") if message is not None else ""
        usage = getattr(message, "usage_metadata", None) if message else None
        reasoning = (
            message.additional_kwargs.get("reasoning", "") if message else ""
        ) or ""

        logger.info(
            "LLM ◀ %s%s%s",
            _short(content, 300),
            f" | uso: {_short(usage, 200)}" if usage else "",
            # turnos de tool call: el contenido va vacío
            f" | tools: {_short(getattr(message, 'tool_calls', None), 300)}"
            if not content and getattr(message, "tool_calls", None) else "",
        )
        if reasoning:
            logger.debug("💭 pensamiento completo: %s", _short(reasoning, 4000))
        await self._push_status()

    async def on_llm_error(
        self, error, *, run_id, parent_run_id=None, **kwargs
    ):
        logger.error("LLM ✗ %s", error)
        self.error_line = f"❌ LLM: {_short(str(error), 200)}"
        await self._push_status(force=True)

    async def on_chain_start(
        self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs
    ):
        self._remember(run_id, parent_run_id)
        name = (serialized or {}).get("name") or "?"
        self.chain_names[run_id] = name
        logger.debug("cadena ▶ %s | %s", name, _short(inputs, 300))

    async def on_chain_end(
        self, outputs, *, run_id, parent_run_id=None, **kwargs
    ):
        name = self.chain_names.pop(run_id, "?")
        logger.debug("cadena ◀ %s | %s", name, _short(outputs, 300))

    async def on_chain_error(
        self, error, *, run_id, parent_run_id=None, **kwargs
    ):
        logger.error("cadena ✗ %s", error)

    async def on_tool_start(
        self, serialized, input_str, *, run_id, parent_run_id=None,
        inputs=None, **kwargs
    ):
        self._remember(run_id, parent_run_id)
        self.tool_runs.add(run_id)
        name = (serialized or {}).get("name") or "?"
        args = _short(inputs if inputs is not None else input_str, 150)
        self.active_tools[run_id] = (name, args, time.monotonic())
        logger.info("tool ▶ %s(%s)", name, args)

        # Solo la delegación interesa en Telegram; las tools MCP
        # (postgres_query/rag_search) quedan cubiertas por su agente
        line = DELEGATION_LINES.get(name)
        if line:
            self._add_line(line)

        await self._push_status()

    async def on_tool_end(
        self, output, *, run_id, parent_run_id=None, **kwargs
    ):
        name, _, t0 = self.active_tools.pop(run_id, ("?", "", time.monotonic()))
        text = getattr(output, "content", None)
        if not isinstance(text, str):
            text = str(output)
        duration = time.monotonic() - t0
        logger.info(
            "tool ◀ %s → %d caracteres (%.2fs): %s",
            name, len(text), duration, _short(text, 300),
        )
        await self._push_status()

    async def on_tool_error(
        self, error, *, run_id, parent_run_id=None, **kwargs
    ):
        name, _, _ = self.active_tools.pop(run_id, ("?", "", time.monotonic()))
        self.error_line = f"❌ {name}: {_short(str(error), 200)}"
        logger.error("tool ✗ %s: %s", name, error)
        await self._push_status(force=True)
