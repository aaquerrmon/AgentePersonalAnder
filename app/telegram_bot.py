
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from app.config import TELEGRAM_ALLOWED_USERS
from app.trace import TelegramTrace

logger = logging.getLogger("app.telegram")


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "¡Hola! Soy tu asistente inteligente.\n\n"
        "Puedo consultar bases de datos y buscar "
        "información en tus documentos.\n\n"
        "Pregúntame lo que necesites."
    )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message

    if not user or not message or not message.text:
        return

    # Control de acceso
    if (
        TELEGRAM_ALLOWED_USERS
        and user.id not in TELEGRAM_ALLOWED_USERS
    ):
        logger.warning(
            "Mensaje rechazado de %s (%s): %s",
            user.id, user.username, message.text,
        )
        await message.reply_text(
            "No tienes autorización para utilizar este bot."
        )
        return

    agent = context.application.bot_data["agent"]

    # Identificador de conversación independiente.
    # En grupos también se separa el contexto por usuario.
    thread_id = f"telegram:{chat.id}:{user.id}"

    logger.info("Mensaje de %s (%s): %s", user.id, chat.id, message.text)

    try:
        await context.bot.send_chat_action(
            chat_id=chat.id,
            action="typing",
        )
    except Exception as e:
        logger.debug("No se pudo enviar el indicador de escritura: %s", e)

    # Traza: logs de depuración + estado y respuesta en streaming
    trace = TelegramTrace(context.bot, chat.id)

    try:

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": message.text,
                    }
                ]
            },
            config={
                "callbacks": [trace],
                "configurable": {
                    "thread_id": thread_id,
                }
            },
        )

        answer = result["messages"][-1].content

        if not isinstance(answer, str):
            answer = str(answer)

        await trace.finish(answer)

    except Exception:

        logger.exception("Error procesando el mensaje")

        await trace.fail("error interno")

        await message.reply_text(
            "Ha ocurrido un error al procesar tu consulta. "
            "Inténtalo de nuevo."
        )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Puedes preguntarme sobre:\n\n"
        "• Datos de PostgreSQL\n"
        "• Estadísticas y consultas SQL\n"
        "• Documentos y manuales\n"
        "• Búsquedas RAG\n"
        "• Preguntas que combinan SQL y documentos\n\n"
        "/clear — borra la conversación y empieza de cero"
    )


async def clear_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Borra el historial del hilo: el supervisor deja de estar
    anclado a respuestas anteriores (incluidas las fallidas)."""

    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message

    if not user or not message:
        return

    if (
        TELEGRAM_ALLOWED_USERS
        and user.id not in TELEGRAM_ALLOWED_USERS
    ):
        await message.reply_text(
            "No tienes autorización para utilizar este bot."
        )
        return

    checkpointer = context.application.bot_data["checkpointer"]
    thread_id = f"telegram:{chat.id}:{user.id}"

    await checkpointer.adelete_thread(thread_id)
    logger.info("Hilo borrado: %s", thread_id)

    await message.reply_text(
        "Conversación reiniciada. Pregúntame lo que necesites."
    )


def configure_handlers(application):

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("clear", clear_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )
