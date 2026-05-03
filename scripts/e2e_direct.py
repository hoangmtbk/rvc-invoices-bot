#!/usr/bin/env python3
"""E2E test for any scraper without needing an email: provide URL + lookup_code directly.

Usage (inside container):
    python /app/scripts/e2e_direct.py <url> <lookup_code>

    # With DB save:
    python /app/scripts/e2e_direct.py <url> <lookup_code> --save-db

Example:
    python /app/scripts/e2e_direct.py \
        "https://hoadon.petrolimex.com.vn" "VF4S5TMTE*"
"""
import sys
import os
import tempfile
import logging

sys.path.insert(0, "/app")
from dotenv import load_dotenv
load_dotenv("/app/.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("e2e_direct")

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(1)

URL = sys.argv[1]
CODE = sys.argv[2]
SAVE_DB = "--save-db" in sys.argv

logger.info("URL: %s", URL)
logger.info("Lookup code: %r", CODE)

from scrapers import scrape_invoice

with tempfile.TemporaryDirectory() as tmpdir:
    logger.info("Running scraper ...")
    result = scrape_invoice(URL, CODE, download_dir=tmpdir)

    logger.info(
        "Scraper result: xml=%s pdf=%s",
        f"{len(result.xml_bytes)}B" if result.xml_bytes else "none",
        f"{len(result.pdf_bytes)}B" if result.pdf_bytes else "none",
    )

    if not result.xml_bytes and not result.pdf_bytes:
        logger.error("No files downloaded — aborting")
        sys.exit(1)

    if SAVE_DB:
        from router import _process_pair

        pair = {"stem": f"e2e_direct_{CODE}"}
        if result.xml_path:
            pair["xml"] = result.xml_path
        if result.pdf_path:
            pair["pdf"] = result.pdf_path

        logger.info("Saving to database ...")
        _process_pair(pair, email=None, had_zip=False)
        logger.info("SUCCESS — invoice saved to database")
    else:
        logger.info("SUCCESS (pass --save-db to also write to database)")
