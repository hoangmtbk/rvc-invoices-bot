import logging

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def send_error_alert(subject: str, branch: str, error_message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured; skipping alert")
        return
    text = (
        f"RVC Invoice Bot ERROR\n"
        f"Subject: {subject}\n"
        f"Branch: {branch}\n"
        f"Error: {error_message}"
    )
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        logger.info("Error alert sent via Telegram")
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
