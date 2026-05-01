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



def test_pick_best_url_prefers_subdomain_over_root():
    from web_extraction_router import _pick_best_url
    urls = [
        "https://easyinvoice.com.vn",
        "https://0102362584001hd.easyinvoice.com.vn/Search/Index",
    ]
    result = _pick_best_url(urls)
    assert "0102362584001hd" in result


def test_pick_best_url_returns_none_for_empty():
    from web_extraction_router import _pick_best_url
    assert _pick_best_url([]) is None


def test_pick_best_url_unknown_domain_falls_back_to_first():
    from web_extraction_router import _pick_best_url
    urls = ["https://unknown.vn/a", "https://another.vn/b"]
    result = _pick_best_url(urls)
    assert result == "https://unknown.vn/a"


def test_process_branch_web_returns_none_when_no_url_or_code():
    import tempfile
    from web_extraction_router import process_branch_web

    email = MagicMock()
    email.html = "<p>No invoice info here</p>"
    email.text = "No invoice info here"
    email.uid = "test123"

    with tempfile.TemporaryDirectory() as tmp:
        with patch("web_extraction_router.extract_direct_link", return_value=None):
            result = process_branch_web(email, tmp)
    assert result is None


def test_process_branch_web_returns_scraped_result_on_success():
    import tempfile
    from web_extraction_router import process_branch_web
    from scrapers.result import ScrapedResult

    email = MagicMock()
    email.html = (
        '<p>Mã tra cứu: MYCODE123 '
        '<a href="https://0102362584001hd.easyinvoice.com.vn/Search/Index">link</a></p>'
    )
    email.text = "Mã tra cứu: MYCODE123"
    email.uid = "uid999"

    mock_result = ScrapedResult(
        xml_bytes=b"<xml/>",
        xml_path="/tmp/web_MYCODE123.xml",
    )
    with tempfile.TemporaryDirectory() as tmp:
        with patch("web_extraction_router.extract_direct_link", return_value=None), \
             patch("web_extraction_router.scrape_invoice", return_value=mock_result):
            result = process_branch_web(email, tmp)

    assert result is not None
    assert result.xml_bytes == b"<xml/>"
