import logging
import os
import shutil
import zipfile
from collections import defaultdict
from datetime import datetime

import data_extractor
import email_handler
import file_storage
import reporter
import storage
import web_extraction_router
from config import TEMP_DIR

logger = logging.getLogger(__name__)


def _dump_and_extract(email, uid_temp: str) -> bool:
    """Save all attachments to uid_temp, extract ZIPs recursively.
    Returns True if any ZIP attachment was present."""
    had_zip = False
    os.makedirs(uid_temp, exist_ok=True)
    for att in email.attachments:
        fname = att.filename or f"attachment_{id(att)}"
        if fname.lower().endswith(".zip"):
            had_zip = True
        fpath = os.path.join(uid_temp, fname)
        with open(fpath, "wb") as f:
            f.write(att.payload)
    changed = True
    while changed:
        changed = False
        for root, _, files in os.walk(uid_temp):
            for fn in list(files):
                if fn.lower().endswith(".zip"):
                    zip_path = os.path.join(root, fn)
                    try:
                        with zipfile.ZipFile(zip_path, "r") as zf:
                            zf.extractall(root)
                        os.remove(zip_path)
                        changed = True
                    except zipfile.BadZipFile:
                        os.remove(zip_path)
                        changed = True
    return had_zip


def _collect_pairs(uid_temp: str) -> list[dict]:
    """Group .xml, .pdf, .html files by filename stem."""
    by_stem: dict[str, dict] = defaultdict(dict)
    for root, _, files in os.walk(uid_temp):
        for fn in files:
            lower = fn.lower()
            if lower.endswith((".xml", ".pdf", ".html")):
                stem = os.path.splitext(fn)[0]
                ext = os.path.splitext(fn)[1].lstrip(".").lower()
                by_stem[stem][ext] = os.path.join(root, fn)
    return [{"stem": stem, **exts} for stem, exts in by_stem.items()]


def _process_pair(pair: dict, email, had_zip: bool) -> None:
    """Parse one file pair, upload to MinIO, append invoice to DB."""
    subject = email.subject or ""
    xml_bytes = pdf_bytes = None

    if "xml" in pair:
        with open(pair["xml"], "rb") as f:
            xml_bytes = f.read()
    if "pdf" in pair:
        with open(pair["pdf"], "rb") as f:
            pdf_bytes = f.read()
    if "html" in pair and xml_bytes is None:
        with open(pair["html"], encoding="utf-8", errors="replace") as f:
            html_content = f.read()
        extracted = web_extraction_router.extract_xml_from_html_attachment(html_content)
        if extracted:
            xml_bytes = extracted

    if xml_bytes is not None:
        data = data_extractor.parse_xml(xml_bytes)
        if "html" in pair and "xml" not in pair:
            branch = "HTML"
        elif had_zip:
            branch = "ZIP"
        else:
            branch = "XML"
    elif pdf_bytes is not None:
        data = data_extractor.parse_pdf_via_gemini(pdf_bytes)
        branch = "PDF"
    else:
        raise ValueError(f"No parseable file in pair: {pair.get('stem')}")

    date_str = datetime.now().strftime("%Y%m%d")
    inv_num = str(data.get("invoice_number") or "unknown")
    tax_code = str(data.get("seller_tax_code") or "unknown")
    xml_link = ""
    pdf_link = ""

    if xml_bytes is not None:
        xml_link = file_storage.upload_file(
            xml_bytes,
            file_storage.build_filename(tax_code, inv_num, date_str, "xml"),
            "application/xml",
        )
    if pdf_bytes is not None:
        pdf_link = file_storage.upload_file(
            pdf_bytes,
            file_storage.build_filename(tax_code, inv_num, date_str, "pdf"),
            "application/pdf",
        )

    data["xml_file_link"] = xml_link
    data["pdf_file_link"] = pdf_link
    data["processed_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["source_branch"] = branch
    data["source_email_subject"] = subject
    storage.append_invoice(data)
    logger.info(f"Invoice saved | branch={branch} | number={data.get('invoice_number')}")


def process_email(email) -> None:
    subject = email.subject or ""
    sender = str(email.from_)
    email_time = email.date.strftime("%H:%M") if email.date else ""
    uid_temp = os.path.join(TEMP_DIR, str(email.uid))
    branch = "UNKNOWN"

    try:
        if email.attachments:
            branch = "ATTACH"
            had_zip = _dump_and_extract(email, uid_temp)
            pairs = _collect_pairs(uid_temp)
            if pairs:
                for pair in pairs:
                    _process_pair(pair, email, had_zip)
                return

            logger.info(f"No invoice files in attachments — falling through to WEB | uid={email.uid}")

        branch = "WEB"
        logger.info(f"Branch WEB | uid={email.uid} | subject='{subject}'")
        result = web_extraction_router.process_branch_web(email, uid_temp)
        if result is None:
            raise ValueError("All extraction tiers failed — no XML or PDF retrieved")

        pair = {"stem": f"web_{email.uid}"}
        if result.xml_path:
            pair["xml"] = result.xml_path
        if result.pdf_path:
            pair["pdf"] = result.pdf_path
        if "xml" not in pair and "pdf" not in pair:
            raise ValueError("ScrapedResult has no file paths")
        _process_pair(pair, email, had_zip=False)

    except Exception as e:
        logger.error(
            f"Error processing email uid={email.uid} branch={branch}: {e}",
            exc_info=True,
        )
        reporter.send_error_alert(subject, branch, str(e))
        storage.append_error({
            "error_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "email_sender": sender,
            "email_time": email_time,
            "email_subject": subject,
            "branch": branch,
            "error_message": str(e),
        })
    finally:
        shutil.rmtree(uid_temp, ignore_errors=True)
        email_handler.mark_as_seen(email.uid)
