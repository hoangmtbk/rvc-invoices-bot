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


def test_single_xml_attachment_xml_branch(tmp_path):
    att = _make_attachment("HD001.xml", b"<HDon/>")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "001", "seller_tax_code": "TAX"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://rvc-s3.rvctel.vn/rvc-invoices/file.xml"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_parse.assert_called_once()
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "XML"
    assert stored["xml_file_link"] == "https://rvc-s3.rvctel.vn/rvc-invoices/file.xml"
    assert stored["pdf_file_link"] == ""


def test_zip_with_xml_sets_zip_branch(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("HD002.xml", b"<?xml version='1.0'?><HDon/>")
    zip_bytes = buf.getvalue()

    att = _make_attachment("HD002.zip", zip_bytes)
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "002", "seller_tax_code": "TAX"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://rvc-s3.rvctel.vn/rvc-invoices/file.xml"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_parse.assert_called_once()
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "ZIP"


def test_pdf_only_attachment_pdf_branch(tmp_path):
    att = _make_attachment("HD003.pdf", b"%PDF-1.4")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_pdf_via_gemini", return_value={"invoice_number": "003", "seller_tax_code": "TAX"}) as mock_gemini, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://rvc-s3.rvctel.vn/rvc-invoices/file.pdf"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_gemini.assert_called_once_with(b"%PDF-1.4")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "PDF"
    assert stored["pdf_file_link"] == "https://rvc-s3.rvctel.vn/rvc-invoices/file.pdf"
    assert stored["xml_file_link"] == ""


def test_paired_xml_and_pdf_both_uploaded(tmp_path):
    xml_att = _make_attachment("HD004.xml", b"<HDon/>")
    pdf_att = _make_attachment("HD004.pdf", b"%PDF-1.4")
    email = _make_email(attachments=[xml_att, pdf_att])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "004", "seller_tax_code": "TAX"}), \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", side_effect=["https://xml.url", "https://pdf.url"]), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    stored = mock_store.call_args[0][0]
    assert stored["xml_file_link"] == "https://xml.url"
    assert stored["pdf_file_link"] == "https://pdf.url"


def test_multiple_pairs_multiple_invoice_calls(tmp_path):
    xml1 = _make_attachment("HD001.xml", b"<HDon/>")
    xml2 = _make_attachment("HD002.xml", b"<HDon/>")
    email = _make_email(attachments=[xml1, xml2])

    with patch("router.data_extractor.parse_xml", return_value={"invoice_number": "001", "seller_tax_code": "TAX"}), \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://url"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    assert mock_store.call_count == 2


def test_web_branch_xml_path(tmp_path):
    from scrapers.result import ScrapedResult

    xml_file = tmp_path / "invoice_005.xml"
    xml_file.write_bytes(b"<HDon/>")
    mock_result = ScrapedResult(xml_bytes=b"<HDon/>", xml_path=str(xml_file))

    email = _make_email(text="mã tra cứu: ABC123\nhttps://www.meinvoice.vn/tra-cuu")

    with patch("router.web_extraction_router.process_branch_web", return_value=mock_result), \
         patch("router.data_extractor.parse_xml", return_value={"invoice_number": "005", "seller_tax_code": "TAX"}) as mock_parse, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://url"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_parse.assert_called_once_with(b"<HDon/>")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "XML"


def test_web_branch_pdf_path(tmp_path):
    from scrapers.result import ScrapedResult

    pdf_file = tmp_path / "invoice_006.pdf"
    pdf_file.write_bytes(b"%PDF")
    mock_result = ScrapedResult(pdf_bytes=b"%PDF", pdf_path=str(pdf_file))

    email = _make_email(text="mã tra cứu: ABC123\nhttps://www.meinvoice.vn/tra-cuu")

    with patch("router.web_extraction_router.process_branch_web", return_value=mock_result), \
         patch("router.data_extractor.parse_pdf_via_gemini", return_value={"invoice_number": "006", "seller_tax_code": "TAX"}) as mock_gemini, \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.file_storage.upload_file", return_value="https://url"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_gemini.assert_called_once_with(b"%PDF")
    stored = mock_store.call_args[0][0]
    assert stored["source_branch"] == "PDF"


def test_error_sends_alert_and_logs_error(tmp_path):
    att = _make_attachment("HD007.xml", b"bad xml")
    email = _make_email(attachments=[att])

    with patch("router.data_extractor.parse_xml", side_effect=ValueError("XML parse error")), \
         patch("router.storage.append_invoice") as mock_store, \
         patch("router.storage.append_error") as mock_err, \
         patch("router.reporter.send_error_alert") as mock_alert, \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.file_storage.upload_file"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_store.assert_not_called()
    mock_err.assert_called_once()
    err_data = mock_err.call_args[0][0]
    assert "XML parse error" in err_data["error_message"]
    mock_alert.assert_called_once()


def test_mark_as_seen_always_called_even_on_error(tmp_path):
    att = _make_attachment("HD008.xml", b"bad")
    email = _make_email(uid="99", attachments=[att])

    with patch("router.data_extractor.parse_xml", side_effect=Exception("Boom")), \
         patch("router.storage.append_error"), \
         patch("router.reporter.send_error_alert"), \
         patch("router.email_handler.mark_as_seen") as mock_seen, \
         patch("router.file_storage.upload_file"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        from router import process_email
        process_email(email)

    mock_seen.assert_called_once_with("99")


def test_process_email_web_branch_calls_process_pair(tmp_path, monkeypatch):
    import router
    from scrapers.result import ScrapedResult

    xml_file = tmp_path / "web_CODE.xml"
    xml_file.write_bytes(b"<xml/>")
    mock_result = ScrapedResult(
        xml_bytes=b"<xml/>",
        xml_path=str(xml_file),
    )

    email = _make_email(
        uid="uid001",
        subject="Invoice",
        text="Mã tra cứu: CODE",
        html='<a href="https://0102362584001hd.easyinvoice.com.vn/Search/Index">link</a>',
    )

    with patch("router.web_extraction_router.process_branch_web", return_value=mock_result), \
         patch("router._process_pair") as mock_pair, \
         patch("router.shutil.rmtree"), \
         patch("router.email_handler.mark_as_seen"), \
         patch("router.TEMP_DIR", str(tmp_path)):
        router.process_email(email)

    mock_pair.assert_called_once()
    call_args = mock_pair.call_args[0]
    assert call_args[0].get("xml") == str(xml_file)
