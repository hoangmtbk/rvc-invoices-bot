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

INVOICE_CSV: str = os.path.join(DATA_DIR, "Tong_hop_hoa_don.csv")
ERROR_CSV: str = os.path.join(DATA_DIR, "errors.csv")
LOG_FILE: str = os.path.join(LOG_DIR, "bot.log")
