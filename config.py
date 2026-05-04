import os
from dotenv import load_dotenv

load_dotenv()

IMAP_SERVER: str = os.getenv("IMAP_SERVER", "mail.rvctel.vn")
IMAP_PORT: int = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER: str = os.getenv("IMAP_USER", "")
IMAP_PASSWORD: str = os.getenv("IMAP_PASSWORD", "")

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

EMAIL_POLL_INTERVAL_MINUTES: int = int(os.getenv("EMAIL_POLL_INTERVAL_MINUTES", "15"))
DAILY_REPORT_TIME: str = os.getenv("DAILY_REPORT_TIME", "08:00")

RVC_TAX_CODE: str = os.getenv("RVC_TAX_CODE", "0313028740")

BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR: str = os.path.join(BASE_DIR, "data")
TEMP_DIR: str = os.path.join(BASE_DIR, "temp")
LOG_DIR: str = os.path.join(BASE_DIR, "logs")

DB_PATH: str = os.path.join(DATA_DIR, "invoices.db")
LOG_FILE: str = os.path.join(LOG_DIR, "bot.log")

MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "rvc-minio:9000")
MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "rvc-invoices")
MINIO_PUBLIC_URL: str = os.getenv("MINIO_PUBLIC_URL", "")

WEB_PORT: int = int(os.getenv("WEB_PORT", "8080"))
WEB_SECRET: str = os.getenv("WEB_SECRET", "")
MANUAL_SECRET: str = os.getenv("MANUAL_SECRET", "")
