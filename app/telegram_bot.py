
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from app.config import TELEGRAM_ALLOWED_USERS


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
        await message.reply_text(
            "No tienes autorización para utilizar este bot."
        )
        return

    agent = context.application.bot_data["agent"]

    # Identificador de conversación independiente.
    # En grupos también se separa el contexto por usuario.
    thread_id = f"telegram:{chat.id}:{user.id}"

    await context.bot.send_chat_action(
        chat_id=chat.id,
        action="typing",
    )

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
                "configurable": {
                    "thread_id": thread_id,
                }
            },
        )

        answer = result["messages"][-1].content

        if not isinstance(answer, str):
            answer = str(answer)

        # Telegram admite como máximo 4096 caracteres.
        for i in range(0, len(answer), 4000):
            await message.reply_text(
                answer[i:i + 4000]
            )

    except Exception as e:

        print(f"Error procesando mensaje: {e}")

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
        "• Preguntas que combinan SQL y documentos"
    )


def configure_handlers(application):

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )
