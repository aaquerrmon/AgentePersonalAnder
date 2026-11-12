
import asyncio

from telegram.ext import Application

from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import (
    TELEGRAM_BOT_TOKEN,
    CHECKPOINT_DB_URI,
)

from app.agents.supervisor import build_supervisor
from app.telegram_bot import configure_handlers


async def main():

    # Pool de conexiones PostgreSQL.
    # autocommit/dict_row: mismas opciones que usa langgraph con
    # AsyncPostgresSaver.from_conn_string (las migraciones crean índices
    # CONCURRENTLY, que no se permiten dentro de una transacción).
    async with AsyncConnectionPool(
        conninfo=CHECKPOINT_DB_URI,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    ) as pool:

        # Abrir conexiones
        await pool.open()

        # Inicializar almacenamiento de memoria
        checkpointer = AsyncPostgresSaver(pool)

        await checkpointer.setup()

        print("Memoria PostgreSQL inicializada")

        # Crear supervisor
        agent = await build_supervisor(
            checkpointer=checkpointer
        )

        print("Supervisor inicializado")

        # Crear bot Telegram
        application = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .build()
        )

        # Compartir agente con los handlers
        application.bot_data["agent"] = agent

        configure_handlers(application)

        print("Bot Telegram iniciado")

        # Arrancar Telegram mediante long polling
        await application.initialize()
        await application.start()

        await application.updater.start_polling(
            drop_pending_updates=True
        )

        try:
            await asyncio.Event().wait()

        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
