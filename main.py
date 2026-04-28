import logging
import time

import schedule

import email_handler
import reporter
import router
from config import DAILY_REPORT_TIME, EMAIL_POLL_INTERVAL_MINUTES, LOG_DIR, LOG_FILE
from logger import setup_logging

logger = logging.getLogger(__name__)


def poll_emails() -> None:
    logger.info("Polling for new invoice emails...")
    try:
        emails = email_handler.fetch_unseen_emails()
        logger.info(f"Found {len(emails)} invoice email(s) to process")
        for email in emails:
            router.process_email(email)
    except Exception as e:
        logger.error(f"Poll cycle failed: {e}", exc_info=True)


def main() -> None:
    setup_logging(LOG_FILE, LOG_DIR)
    logger.info("rvc-invoices-bot starting up")
    logger.info(f"Poll interval: {EMAIL_POLL_INTERVAL_MINUTES} minutes")
    logger.info(f"Daily report time: {DAILY_REPORT_TIME}")

    schedule.every(EMAIL_POLL_INTERVAL_MINUTES).minutes.do(poll_emails)
    schedule.every().day.at(DAILY_REPORT_TIME).do(reporter.send_daily_report)

    poll_emails()  # Immediate first run on startup

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
