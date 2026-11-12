
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

TELEGRAM_ALLOWED_USERS = {
    int(x.strip())
    for x in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
    if x.strip()
}

MCP_URL = os.getenv(
    "MCP_URL",
    "http://mcp:8001/mcp"
)

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4.1")
LLM_TEMPERATURE = float(
    os.getenv("LLM_TEMPERATURE", "0")
)

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "rag")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]

CHECKPOINT_DB_URI = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    "?sslmode=disable"
)
