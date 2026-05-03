#!/usr/bin/env python3
"""Full end-to-end test: scrape uid=111 email → download XML+PDF → save to DB.

Reads the email directly, runs PetrolimexScraper, then hands the result to
the real router._process_pair so the invoice is written to the database.

Usage (inside container):
    python /app/scripts/e2e_petrolimex.py [uid]
"""
import sys, os, tempfile, logging

sys.path.insert(0, "/app")
from dotenv import load_dotenv
load_dotenv("/app/.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("e2e")

TARGET_UID = sys.argv[1] if len(sys.argv) > 1 else "111"

# ── 1. Fetch email ─────────────────────────────────────────────────────────
from imap_tools import MailBox, AND, UidRange
from config import IMAP_SERVER, IMAP_PORT, IMAP_USER, IMAP_PASSWORD

logger.info("Fetching email uid=%s ...", TARGET_UID)
with MailBox(IMAP_SERVER, port=IMAP_PORT).login(IMAP_USER, IMAP_PASSWORD, "INBOX") as mb:
    msgs = list(mb.fetch(AND(uid=UidRange(TARGET_UID, TARGET_UID)), mark_seen=False))

if not msgs:
    logger.error("No email found with uid=%s", TARGET_UID)
    sys.exit(1)

email = msgs[0]
logger.info("Subject: %s", email.subject)

# ── 2. Extract code + URL ──────────────────────────────────────────────────
from web_extraction_router import _extract_lookup_code, _extract_urls, _pick_best_url

combined = (email.text or "") + " " + (email.html or "")
code = _extract_lookup_code(combined)
url  = _pick_best_url(_extract_urls(combined))
logger.info("Lookup code: %r   URL: %r", code, url)
assert code and url, "Could not extract code or URL from email"

# ── 3. Run scraper ──────────────────────────────────────────────────────────
from scrapers import scrape_invoice

with tempfile.TemporaryDirectory() as tmpdir:
    logger.info("Running scraper ...")
    result = scrape_invoice(url, code, download_dir=tmpdir)

    logger.info(
        "Scraper result: xml=%s pdf=%s",
        f"{len(result.xml_bytes)}B" if result.xml_bytes else "none",
        f"{len(result.pdf_bytes)}B" if result.pdf_bytes else "none",
    )
    logger.info("xml_path=%s  pdf_path=%s", result.xml_path, result.pdf_path)

    if not result.xml_bytes and not result.pdf_bytes:
        logger.error("No files downloaded — aborting")
        sys.exit(1)

    # ── 4. Parse + save to DB ──────────────────────────────────────────────
    from router import _process_pair
    from datetime import datetime

    pair = {"stem": f"e2e_{TARGET_UID}"}
    if result.xml_path:
        pair["xml"] = result.xml_path
    if result.pdf_path:
        pair["pdf"] = result.pdf_path

    logger.info("Saving to database ...")
    _process_pair(pair, email, had_zip=False)
    logger.info("SUCCESS — invoice saved to database")
