import logging
import os
import shutil
import zipfile
from datetime import datetime

import data_extractor
import email_handler
import reporter
import storage
import web_extraction_router
from config import TEMP_DIR

logger = logging.getLogger(__name__)


def _find_attachment(email, extension: str):
    for att in email.attachments:
        if (att.filename or "").lower().endswith(extension):
            return att
    return None


def process_email(email) -> None:
    subject = email.subject or ""
    sender = str(email.from_)
    email_time = email.date.strftime("%H:%M") if email.date else ""
    branch = "UNKNOWN"

    try:
        xml_att = _find_attachment(email, ".xml")
        zip_att = _find_attachment(email, ".zip")
        pdf_att = _find_attachment(email, ".pdf")
        html_att = _find_attachment(email, ".html")

        if xml_att:
            branch = "XML"
            logger.info(f"Branch XML | uid={email.uid} | subject='{subject}'")
            data = data_extractor.parse_xml(xml_att.payload)

        elif zip_att:
            branch = "ZIP"
            logger.info(f"Branch ZIP | uid={email.uid} | subject='{subject}'")
            uid_temp = os.path.join(TEMP_DIR, str(email.uid))
            os.makedirs(uid_temp, exist_ok=True)
            try:
                zip_path = os.path.join(uid_temp, zip_att.filename or "attachment.zip")
                with open(zip_path, "wb") as f:
                    f.write(zip_att.payload)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(uid_temp)
                xml_file = next(
                    (
                        os.path.join(root, fn)
                        for root, _, files in os.walk(uid_temp)
                        for fn in files
                        if fn.lower().endswith(".xml")
                    ),
                    None,
                )
                if not xml_file:
                    raise FileNotFoundError("No XML file found inside ZIP")
                with open(xml_file, "rb") as f:
                    data = data_extractor.parse_xml(f.read())
            finally:
                shutil.rmtree(uid_temp, ignore_errors=True)

        elif pdf_att:
            branch = "PDF"
            logger.info(f"Branch PDF | uid={email.uid} | subject='{subject}'")
            data = data_extractor.parse_pdf_via_gemini(pdf_att.payload)

        elif html_att:
            branch = "HTML"
            logger.info(f"Branch HTML | uid={email.uid} | subject='{subject}'")
            html_content = html_att.payload.decode("utf-8", errors="replace")
            xml_bytes = web_extraction_router.extract_xml_from_html_attachment(html_content)
            if xml_bytes is None:
                raise ValueError("No Base64 XML found in HTML attachment")
            data = data_extractor.parse_xml(xml_bytes)

        else:
            branch = "WEB"
            logger.info(f"Branch WEB | uid={email.uid} | subject='{subject}'")
            result = web_extraction_router.process_branch_4(email)
            if result is None:
                raise ValueError("All extraction tiers failed — no XML or PDF retrieved")
            file_bytes, content_type = result
            if content_type == "xml":
                data = data_extractor.parse_xml(file_bytes)
            else:
                data = data_extractor.parse_pdf_via_gemini(file_bytes)

        data["processed_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["source_branch"] = branch
        data["source_email_subject"] = subject
        storage.append_invoice(data)
        logger.info(f"Invoice saved | branch={branch} | number={data.get('invoice_number')}")

    except Exception as e:
        logger.error(
            f"Error processing email uid={email.uid} branch={branch}: {e}",
            exc_info=True,
        )
        reporter.send_error_alert(subject, branch, str(e))
        storage.append_error(
            {
                "error_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "email_sender": sender,
                "email_time": email_time,
                "email_subject": subject,
                "branch": branch,
                "error_message": str(e),
            }
        )
    finally:
        email_handler.mark_as_seen(email.uid)
