import logging

from imap_tools import AND, MailBox

from config import IMAP_PASSWORD, IMAP_PORT, IMAP_SERVER, IMAP_USER

logger = logging.getLogger(__name__)

SUBJECT_KEYWORDS = ["hóa đơn điện tử", "hóa đơn", "hddt"]


def fetch_unseen_emails() -> list:
    emails = []
    try:
        with MailBox(IMAP_SERVER, port=IMAP_PORT).login(
            IMAP_USER, IMAP_PASSWORD, initial_folder="INBOX"
        ) as mailbox:
            for msg in mailbox.fetch(AND(seen=False), mark_seen=False):
                subject_lower = (msg.subject or "").lower()
                if any(kw in subject_lower for kw in SUBJECT_KEYWORDS):
                    emails.append(msg)
                    logger.info(f"Matched email: uid={msg.uid} subject='{msg.subject}'")
    except Exception as e:
        logger.error(f"IMAP fetch failed: {e}")
        raise
    return emails


def mark_as_seen(uid: str) -> None:
    try:
        with MailBox(IMAP_SERVER, port=IMAP_PORT).login(
            IMAP_USER, IMAP_PASSWORD, initial_folder="INBOX"
        ) as mailbox:
            mailbox.flag(uid, ["\\Seen"], True)
            logger.info(f"Marked as seen: uid={uid}")
    except Exception as e:
        logger.error(f"Failed to mark seen uid={uid}: {e}")
