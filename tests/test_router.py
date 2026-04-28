import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest


def _make_email(uid="1", subject="Hóa đơn test", attachments=None, text="", html=""):
    email = MagicMock()
    email.uid = uid
    email.subject = subject
    email.attachments = attachments or []
    email.text = text
    email.html = html
    email.from_ = "sender@example.com"
    email.date = MagicMock()
    email.date.strftime.return_value = "09:00"
    return email


def _make_attachment(filename: str, payload: bytes = b"data"):
    att = MagicMock()
    att.filename = filename
    att.payload = payload
    return att


def test_branch_xml_calls_parse_xml():
    att = _make_attachment("invoice.xml", b"<xml/>")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "001"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_parse.assert_called_once_with(b"<xml/>")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "XML"
    assert stored["source_email_subject"] == "Hóa đơn test"
    assert "processed_date" in stored


def test_branch_zip_extracts_and_parses_xml(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("invoice.xml", b"<?xml version='1.0'?><HDon/>")
    zip_bytes = buf.getvalue()

    att = _make_attachment("invoice.zip", zip_bytes)
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "002"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.TEMP_DIR", str(tmp_path)):

        from router import process_email
        process_email(email)

    mock_parse.assert_called_once()
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "ZIP"


def test_branch_pdf_calls_gemini():
    att = _make_attachment("invoice.pdf", b"%PDF-1.4")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_pdf_via_gemini", return_value={"invoice_number": "003"}) as mock_gemini, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_gemini.assert_called_once_with(b"%PDF-1.4")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "PDF"


def test_branch_web_xml_path():
    email = _make_email(
        text="mã tra cứu: ABC123\nhttps://www.meinvoice.vn/tra-cuu"
    )

    with patch("router.web_scraper.download_invoice_file", return_value=(b"<HDon/>", "xml")) as mock_web, \
         patch("router.data_extractor.parse_xml", return_value={"invoice_number": "004"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_web.assert_called_once()
    mock_parse.assert_called_once_with(b"<HDon/>")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "WEB"


def test_branch_web_pdf_path():
    email = _make_email(
        text="mã tra cứu: ABC123\nhttps://www.meinvoice.vn/tra-cuu"
    )

    with patch("router.web_scraper.download_invoice_file", return_value=(b"%PDF", "pdf")), \
         patch("router.data_extractor.parse_pdf_via_gemini", return_value={"invoice_number": "005"}) as mock_gemini, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_gemini.assert_called_once_with(b"%PDF")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "WEB"


def test_error_sends_alert_and_logs_error():
    att = _make_attachment("invoice.xml", b"bad xml")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", side_effect=ValueError("XML parse error")), \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.storage.append_error") as mock_err, \
         patch("router.reporter.send_error_alert") as mock_alert, \
         patch("router.email_handler.mark_as_seen"):

        from router import process_email
        process_email(email)

    mock_store.assert_not_called()
    mock_err.assert_called_once()
    err_data = mock_err.call_args[0][0]
    assert err_data["branch"] == "XML"
    assert err_data["email_subject"] == "Hóa đơn test"
    mock_alert.assert_called_once()


def test_mark_as_seen_always_called_even_on_error():
    att = _make_attachment("invoice.xml", b"bad")
    email = _make_email(uid="99", attachments=[att])

    with patch("router.data_extractor.parse_xml", side_effect=Exception("Boom")), \
         patch("router.storage.append_error"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.email_handler.mark_as_seen") as mock_seen:

        from router import process_email
        process_email(email)

    mock_seen.assert_called_once_with("99")


def test_xml_takes_priority_over_zip_and_pdf():
    xml_att = _make_attachment("invoice.xml", b"<xml/>")
    pdf_att = _make_attachment("invoice.pdf", b"%PDF")
    zip_att = _make_attachment("archive.zip", b"PK")
    email = _make_email(attachments=[xml_att, pdf_att, zip_att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "001"}) as mock_xml, \
         patch("router.data_extractor.parse_pdf_via_gemini") as mock_pdf, \
         patch("router.storage.append_invoice"), \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"):

        from router import process_email
        process_email(email)

    mock_xml.assert_called_once()
    mock_pdf.assert_not_called()
