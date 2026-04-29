import pytest
from unittest.mock import MagicMock, patch


def test_try_direct_download_xml_by_content_type():
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml; charset=utf-8"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        from web_extraction_router import _try_direct_download
        result = _try_direct_download(
            ["https://example.com/download?token=ABC123"]
        )

    assert result is not None
    content, ctype = result
    assert ctype == "xml"
    assert b"<?xml" in content


def test_try_direct_download_xml_by_magic_bytes():
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/octet-stream"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        from web_extraction_router import _try_direct_download
        result = _try_direct_download(
            ["https://example.com/invoice/file?token=XYZ"]
        )

    assert result is not None
    _, ctype = result
    assert ctype == "xml"


def test_try_direct_download_pdf_by_magic_bytes():
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/octet-stream"}
    mock_resp.content = b"%PDF-1.4 fake pdf content"
    mock_resp.raise_for_status = MagicMock()

    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        from web_extraction_router import _try_direct_download
        result = _try_direct_download(
            ["https://example.com/download?token=ABC"]
        )

    assert result is not None
    _, ctype = result
    assert ctype == "pdf"


def test_try_direct_download_skips_non_matching_urls():
    from web_extraction_router import _try_direct_download
    result = _try_direct_download(
        ["https://example.com/about-us", "https://www.google.com"]
    )
    assert result is None


def test_try_direct_download_returns_none_on_request_failure():
    with patch("web_extraction_router.requests.get", side_effect=Exception("timeout")):
        from web_extraction_router import _try_direct_download
        result = _try_direct_download(
            ["https://example.com/download?token=ABC"]
        )
    assert result is None


def test_extract_lookup_code_misa_pattern():
    from web_extraction_router import _extract_lookup_code
    assert _extract_lookup_code("mã số: ABC123XYZ") == "ABC123XYZ"


def test_extract_lookup_code_common_pattern():
    from web_extraction_router import _extract_lookup_code
    assert _extract_lookup_code("mã tra cứu: MKKUXJMAG") == "MKKUXJMAG"


def test_extract_lookup_code_vnpt_pattern():
    from web_extraction_router import _extract_lookup_code
    assert _extract_lookup_code("Mã nhận hóa đơn: VNPT2024ABC") == "VNPT2024ABC"


def test_extract_lookup_code_viettel_pattern():
    from web_extraction_router import _extract_lookup_code
    assert _extract_lookup_code("Mã bí mật: VT_SECRET_123") == "VT_SECRET_123"


def test_extract_lookup_code_returns_none_when_not_found():
    from web_extraction_router import _extract_lookup_code
    assert _extract_lookup_code("no code here at all") is None


def test_extract_urls_finds_https_urls():
    from web_extraction_router import _extract_urls
    text = "Click https://www.meinvoice.vn/tra-cuu to view your invoice"
    urls = _extract_urls(text)
    assert "https://www.meinvoice.vn/tra-cuu" in urls


def test_download_invoice_file_stage1_xml_success():
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    body = "Download: https://hoadon.petrolimex.com.vn/download?token=XYZ123"
    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        from web_extraction_router import download_invoice_file
        content, ctype = download_invoice_file(body, "")

    assert ctype == "xml"
    assert b"<?xml" in content


def test_download_invoice_file_raises_when_no_url_no_code():
    from web_extraction_router import download_invoice_file
    with pytest.raises(ValueError):
        download_invoice_file("Nothing useful here.", "")


def test_download_invoice_file_raises_unsupported_domain():
    from web_extraction_router import download_invoice_file
    body = "mã tra cứu: ABC123\nhttps://unknown-portal.vn/invoice"
    with pytest.raises(ValueError):
        download_invoice_file(body, "")


import base64


# ── Tier 1 ──────────────────────────────────────────────────────────────────

VALID_XML_BYTES = b'<?xml version="1.0" encoding="UTF-8"?><Root/>'
VALID_XML_B64 = base64.b64encode(VALID_XML_BYTES).decode()


def test_tier1_extracts_xml_from_hidden_input_by_id():
    from web_extraction_router import extract_xml_from_html_attachment
    html = f'<html><body><input type="hidden" id="xmlData" value="{VALID_XML_B64}"/></body></html>'
    result = extract_xml_from_html_attachment(html)
    assert result is not None
    assert result.startswith(b"<?xml")


def test_tier1_extracts_xml_from_hidden_input_by_name():
    from web_extraction_router import extract_xml_from_html_attachment
    html = f'<html><body><input type="hidden" name="xmlContent" value="{VALID_XML_B64}"/></body></html>'
    result = extract_xml_from_html_attachment(html)
    assert result is not None
    assert result.startswith(b"<?xml")


def test_tier1_regex_fallback_finds_base64_in_other_attribute():
    from web_extraction_router import extract_xml_from_html_attachment
    html = f'<html><body><div data-payload="{VALID_XML_B64}"></div></body></html>'
    result = extract_xml_from_html_attachment(html)
    assert result is not None
    assert result.startswith(b"<?xml")


def test_tier1_returns_none_on_invalid_base64():
    from web_extraction_router import extract_xml_from_html_attachment
    html = '<html><body><input type="hidden" id="xmlData" value="not-valid-base64!!!"/></body></html>'
    result = extract_xml_from_html_attachment(html)
    assert result is None


def test_tier1_returns_none_when_no_hidden_inputs():
    from web_extraction_router import extract_xml_from_html_attachment
    html = "<html><body><p>No invoice data here.</p></body></html>"
    result = extract_xml_from_html_attachment(html)
    assert result is None


# ── Tier 2 ──────────────────────────────────────────────────────────────────

def test_tier2_finds_tai_xml_anchor_returns_xml():
    from web_extraction_router import extract_direct_link
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    html = '<a href="https://example.com/getXml?id=1">Tải XML</a>'
    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        result = extract_direct_link(html)
    assert result is not None
    content, ctype = result
    assert ctype == "xml"
    assert content.startswith(b"<?xml")


def test_tier2_finds_anchor_by_href_keyword():
    from web_extraction_router import extract_direct_link
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    html = '<a href="https://example.com/exportXml?token=ABC">Xem hóa đơn</a>'
    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        result = extract_direct_link(html)
    assert result is not None
    _, ctype = result
    assert ctype == "xml"


def test_tier2_finds_tai_pdf_anchor_returns_pdf():
    from web_extraction_router import extract_direct_link
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/pdf"}
    mock_resp.content = b"%PDF-1.4 fake"
    mock_resp.raise_for_status = MagicMock()

    html = '<a href="https://example.com/invoice.pdf">Tải PDF</a>'
    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        result = extract_direct_link(html)
    assert result is not None
    _, ctype = result
    assert ctype == "pdf"


def test_tier2_token_url_in_text_body_caught_by_substrategy1():
    from web_extraction_router import extract_direct_link
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/xml"}
    mock_resp.content = b"<?xml version='1.0'?><HDon/>"
    mock_resp.raise_for_status = MagicMock()

    with patch("web_extraction_router.requests.get", return_value=mock_resp):
        result = extract_direct_link(
            email_body_html="",
            email_body_text="https://example.com/download?token=XYZ123",
        )
    assert result is not None
    _, ctype = result
    assert ctype == "xml"


def test_tier2_returns_none_when_no_matching_links():
    from web_extraction_router import extract_direct_link
    html = '<a href="https://example.com/about">About us</a>'
    result = extract_direct_link(html)
    assert result is None


# ── Tier 3 ──────────────────────────────────────────────────────────────────

def test_tier3_routes_easyinvoice_subdomain_to_scrape_easyinvoice():
    from web_extraction_router import dynamic_web_router
    xml_bytes = b"<?xml version='1.0'?><HDon/>"
    with patch("web_extraction_router.scrape_easyinvoice", return_value=xml_bytes) as mock_scraper:
        result = dynamic_web_router(
            "https://0310674520hd.easyinvoice.vn/lookup",
            "CODE123",
            "",
        )
    mock_scraper.assert_called_once_with("https://0310674520hd.easyinvoice.vn/lookup", "CODE123")
    assert result == (xml_bytes, "xml")


def test_tier3_routes_meinvoice_to_scrape_misa():
    from web_extraction_router import dynamic_web_router
    xml_bytes = b"<?xml version='1.0'?><HDon/>"
    with patch("web_extraction_router.scrape_misa", return_value=xml_bytes) as mock_scraper:
        result = dynamic_web_router(
            "https://www.meinvoice.vn/tra-cuu",
            "MKKUXJMAG",
            "",
        )
    mock_scraper.assert_called_once()
    assert result == (xml_bytes, "xml")


def test_tier3_unknown_domain_logs_warning_returns_none(caplog):
    from web_extraction_router import dynamic_web_router
    import logging
    with caplog.at_level(logging.WARNING, logger="web_extraction_router"):
        result = dynamic_web_router(
            "https://unknown-portal.vn/invoice",
            "ABC123",
            "",
        )
    assert result is None
    assert "Unsupported provider domain" in caplog.text
    assert "unknown-portal.vn" in caplog.text


# ── process_branch_4 ─────────────────────────────────────────────────────────

def test_process_branch4_tier2_success_skips_tier3():
    from web_extraction_router import process_branch_4
    email = MagicMock()
    email.html = '<a href="https://example.com/getXml?id=1">Tải XML</a>'
    email.text = ""

    xml_resp = MagicMock()
    xml_resp.headers = {"Content-Type": "application/xml"}
    xml_resp.content = b"<?xml version='1.0'?><HDon/>"
    xml_resp.raise_for_status = MagicMock()

    with patch("web_extraction_router.requests.get", return_value=xml_resp), \
         patch("web_extraction_router.dynamic_web_router") as mock_t3:
        result = process_branch_4(email)

    assert result is not None
    assert result[1] == "xml"
    mock_t3.assert_not_called()


def test_process_branch4_tier2_fails_tier3_succeeds():
    from web_extraction_router import process_branch_4
    email = MagicMock()
    email.html = ""
    email.text = "mã tra cứu: MKKUXJMAG\nhttps://www.meinvoice.vn/tra-cuu"

    with patch("web_extraction_router.extract_direct_link", return_value=None), \
         patch("web_extraction_router.dynamic_web_router",
               return_value=(b"<?xml?><HDon/>", "xml")) as mock_t3:
        result = process_branch_4(email)

    assert result == (b"<?xml?><HDon/>", "xml")
    mock_t3.assert_called_once()


def test_process_branch4_both_tiers_fail_returns_none():
    from web_extraction_router import process_branch_4
    email = MagicMock()
    email.html = ""
    email.text = "Nothing useful here."

    with patch("web_extraction_router.extract_direct_link", return_value=None), \
         patch("web_extraction_router.dynamic_web_router", return_value=None):
        result = process_branch_4(email)

    assert result is None
