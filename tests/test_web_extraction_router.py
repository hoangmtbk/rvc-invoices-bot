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
