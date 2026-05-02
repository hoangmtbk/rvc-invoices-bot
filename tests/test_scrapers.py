import pytest
from scrapers.result import ScrapedResult
from scrapers.exceptions import (
    CaptchaRequiredException,
    InvoiceNotFoundException,
    ScraperNotSupportedException,
)


def test_scraped_result_defaults():
    r = ScrapedResult()
    assert r.xml_bytes is None
    assert r.pdf_bytes is None
    assert r.xml_path is None
    assert r.pdf_path is None


def test_scraped_result_with_xml():
    r = ScrapedResult(xml_bytes=b"<xml/>", xml_path="/tmp/a.xml")
    assert r.xml_bytes == b"<xml/>"
    assert r.xml_path == "/tmp/a.xml"
    assert r.pdf_bytes is None


def test_exceptions_are_exceptions():
    assert issubclass(CaptchaRequiredException, Exception)
    assert issubclass(InvoiceNotFoundException, Exception)
    assert issubclass(ScraperNotSupportedException, Exception)


from unittest.mock import MagicMock, patch
from scrapers.base import BaseInvoiceScraper


class _ConcreteScaper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        return ScrapedResult(xml_bytes=b"<xml/>")


def test_handle_captcha_no_op_when_no_image():
    page = MagicMock()
    img_loc = MagicMock()
    img_loc.count.return_value = 0
    page.locator.return_value = img_loc

    scraper = _ConcreteScaper(page, "https://example.com", "CODE")
    scraper._handle_captcha_if_present()  # must not raise


def test_handle_captcha_no_op_when_image_not_visible():
    page = MagicMock()
    img_loc = MagicMock()
    img_loc.count.return_value = 1
    img_loc.first.is_visible.return_value = False
    page.locator.return_value = img_loc

    scraper = _ConcreteScaper(page, "https://example.com", "CODE")
    scraper._handle_captcha_if_present()  # must not raise


def test_handle_captcha_raises_when_gemini_returns_empty():
    page = MagicMock()
    img_loc = MagicMock()
    img_loc.count.return_value = 1
    img_loc.first.is_visible.return_value = True
    inp_loc = MagicMock()
    inp_loc.count.return_value = 1

    def locator_side_effect(sel):
        if "input" not in sel.lower():
            return img_loc
        return inp_loc

    page.locator.side_effect = locator_side_effect

    scraper = _ConcreteScaper(page, "https://example.com", "CODE")
    with patch.object(scraper, "_solve_captcha", return_value=""):
        with patch("tempfile.NamedTemporaryFile"):
            with patch("os.unlink"):
                with pytest.raises(CaptchaRequiredException):
                    scraper._handle_captcha_if_present()


from scrapers.factory import ScraperFactory
from scrapers.exceptions import ScraperNotSupportedException


def test_factory_easyinvoice_subdomain():
    from scrapers.easyinvoice import EasyInvoiceScraper
    page = MagicMock()
    scraper = ScraperFactory.get(
        "https://0102362584001hd.easyinvoice.com.vn/Search/Index", page, "CODE"
    )
    assert isinstance(scraper, EasyInvoiceScraper)


def test_factory_vnpt_subdomain():
    from scrapers.vnpt import VnptScraper
    page = MagicMock()
    scraper = ScraperFactory.get(
        "https://6101145281-tt78.vnpt-invoice.com.vn/lookup", page, "CODE"
    )
    assert isinstance(scraper, VnptScraper)


def test_factory_meinvoice():
    from scrapers.misa import MisaScraper
    page = MagicMock()
    scraper = ScraperFactory.get("https://www.meinvoice.vn/tra-cuu", page, "CODE")
    assert isinstance(scraper, MisaScraper)


def test_factory_unknown_raises():
    page = MagicMock()
    with pytest.raises(ScraperNotSupportedException):
        ScraperFactory.get("https://unknown-provider.vn/invoice", page, "CODE")


from scrapers import scrape_invoice


def test_scrape_invoice_raises_for_unknown_domain():
    with patch("scrapers.sync_playwright") as mock_pw, \
         patch("scrapers.build_stealth_context") as mock_ctx:
        mock_pw.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_pw.return_value.__exit__ = MagicMock(return_value=False)
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_ctx.return_value = (mock_browser, mock_context)
        mock_context.new_page.return_value = mock_page

        with pytest.raises(ScraperNotSupportedException):
            scrape_invoice("https://unknown-provider.vn/invoice", "CODE")


def test_scrape_invoice_saves_files_when_download_dir_given(tmp_path):
    mock_result = ScrapedResult(xml_bytes=b"<xml/>", pdf_bytes=b"%PDF")

    with patch("scrapers.sync_playwright") as mock_pw, \
         patch("scrapers.build_stealth_context") as mock_ctx, \
         patch("scrapers.ScraperFactory") as mock_factory_cls, \
         patch("scrapers.stealth_sync"):

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_ctx.return_value = (mock_browser, mock_context)
        mock_context.new_page.return_value = mock_page
        mock_scraper = MagicMock()
        mock_scraper.scrape.return_value = mock_result
        mock_factory_cls.get.return_value = mock_scraper

        mock_playwright_instance = MagicMock()
        mock_pw.return_value.__enter__ = MagicMock(return_value=mock_playwright_instance)
        mock_pw.return_value.__exit__ = MagicMock(return_value=False)

        result = scrape_invoice(
            "https://0102362584001hd.easyinvoice.com.vn/Search/Index",
            "CODE123",
            download_dir=str(tmp_path),
        )

    assert result.xml_path is not None
    assert result.pdf_path is not None
    assert (tmp_path / "web_CODE123.xml").exists()
    assert (tmp_path / "web_CODE123.pdf").exists()


# ── VNPT scraper unit tests ──────────────────────────────────────────────────

from scrapers.vnpt import VnptScraper, _classify_bytes, _solve_vnpt_captcha


def test_classify_bytes_xml():
    assert _classify_bytes(b"<?xml version='1.0'?><HDon/>") == "xml"


def test_classify_bytes_pdf():
    assert _classify_bytes(b"%PDF-1.4 fake") == "pdf"


def test_classify_bytes_unknown():
    assert _classify_bytes(b"garbage data here") is None


def test_classify_bytes_xml_with_leading_whitespace():
    assert _classify_bytes(b"  \n<?xml version='1.0'?><Root/>") == "xml"


def test_vnpt_scraper_instantiation():
    page = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "TESTCODE")
    assert s.lookup_code == "TESTCODE"
    assert "vnpt-invoice.com.vn" in s.url


def test_vnpt_assert_invoice_found_raises_on_not_found_text():
    page = MagicMock()
    page.evaluate.return_value = True  # page contains "không tìm thấy"
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "BAD")
    with pytest.raises(InvoiceNotFoundException, match="not found"):
        s._assert_invoice_found()


def test_vnpt_assert_invoice_found_passes_when_text_absent():
    page = MagicMock()
    page.evaluate.return_value = False
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "GOOD")
    s._assert_invoice_found()  # should not raise


def test_vnpt_scrape_raises_after_max_captcha_retries():
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()
    page.locator.return_value.count.return_value = 0
    page.locator.return_value.first.is_visible.return_value = False

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")

    with patch.object(s, "_probe_bypass", return_value=False), \
         patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value=""), \
         pytest.raises(CaptchaRequiredException, match="empty"):
        s.scrape()


def test_vnpt_scrape_raises_captcha_after_all_failed_submits():
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")

    with patch.object(s, "_probe_bypass", return_value=False), \
         patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value="1234"), \
         patch.object(s, "_enter_captcha"), \
         patch.object(s, "_submit_and_wait_for_results", return_value=False), \
         patch.object(s, "_refresh_captcha_image"), \
         pytest.raises(CaptchaRequiredException, match="3 attempts"):
        s.scrape()


def test_vnpt_download_all_files_returns_xml_and_pdf():
    page = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")

    xml_data = b"<?xml version='1.0'?><HDon/>"
    pdf_data = b"%PDF-1.4 fake"

    with patch.object(s, "_download_column", side_effect=[xml_data, pdf_data]):
        xml, pdf = s._download_all_files()

    assert xml == xml_data
    assert pdf == pdf_data


def test_vnpt_download_all_files_xml_preferred_over_second_col():
    """Both columns return XML — second col is ignored for xml slot."""
    page = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    xml_data = b"<?xml version='1.0'?><HDon/>"

    with patch.object(s, "_download_column", return_value=xml_data), \
         patch.object(s, "_download_pdf_via_href", return_value=None):
        xml, pdf = s._download_all_files()

    assert xml == xml_data
    assert pdf is None  # second col also XML — not placed in pdf slot


def test_vnpt_download_all_files_falls_back_to_pdf_href():
    page = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    pdf_data = b"%PDF-1.4 fake"

    with patch.object(s, "_download_column", return_value=None), \
         patch.object(s, "_download_pdf_via_href", return_value=pdf_data):
        xml, pdf = s._download_all_files()

    assert xml is None
    assert pdf == pdf_data


def test_vnpt_enter_captcha_clears_field_with_triple_click():
    """_enter_captcha must call triple_click before press_sequentially, not just click."""
    page = MagicMock()
    el = MagicMock()
    el.count.return_value = 1
    page.locator.return_value.first = el

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    s._enter_captcha("1234")

    el.triple_click.assert_called_once()
    el.press_sequentially.assert_called_once()
    args, _ = el.press_sequentially.call_args
    assert args[0] == "1234"
    # Must NOT call .click() (which would deselect the triple-click selection)
    el.click.assert_not_called()


def test_vnpt_refresh_captcha_uses_javascript_not_click():
    """Refreshing via img.click() does nothing; must use JS src replacement."""
    page = MagicMock()
    page.wait_for_load_state = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    s._refresh_captcha_image()

    # evaluate must have been called with JS that changes the src
    page.evaluate.assert_called_once()
    js_code = page.evaluate.call_args[0][0]
    assert "img.src" in js_code
    assert "Date.now()" in js_code
    # No direct Playwright locator click should have happened
    page.locator.assert_not_called()


def test_vnpt_submit_returns_false_when_captcha_validation_error_visible():
    """If jQuery remote validation error span is visible, submit returns False immediately."""
    page = MagicMock()
    # wait_for_selector succeeds (the error span appeared)
    page.wait_for_selector = MagicMock()
    # The first locator call is for _SUBMIT_BTN, others depend on the selector string
    captcha_error_loc = MagicMock()
    captcha_error_loc.count.return_value = 1
    captcha_error_loc.first.inner_text.return_value = "ErrorMessage"

    result_row_loc = MagicMock()
    result_row_loc.count.return_value = 0

    def locator_side_effect(sel):
        if "field-validation-error" in sel or "valmsg-for" in sel:
            return captcha_error_loc
        m = MagicMock()
        m.count.return_value = 0
        m.first.is_visible.return_value = True
        return m

    page.locator.side_effect = locator_side_effect

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    result = s._submit_and_wait_for_results()

    assert result is False


# ── bypass probe tests ──────────────────────────────────────────────────────

def test_probe_bypass_returns_true_when_submit_succeeds():
    page = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    with patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_enter_captcha"), \
         patch.object(s, "_submit_and_wait_for_results", return_value=True):
        assert s._probe_bypass() is True


def test_probe_bypass_returns_false_when_submit_fails():
    page = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    with patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_enter_captcha"), \
         patch.object(s, "_submit_and_wait_for_results", return_value=False):
        assert s._probe_bypass() is False


def test_scrape_bypass_path_returns_result_when_bypass_succeeds():
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    xml_data = b"<?xml version='1.0'?><HDon/>"
    with patch.object(s, "_probe_bypass", return_value=True), \
         patch.object(s, "_assert_invoice_found"), \
         patch.object(s, "_download_all_files", return_value=(xml_data, None)):
        result = s.scrape()
    assert result.xml_bytes == xml_data


def test_scrape_bypass_path_raises_when_no_files_downloaded():
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()
    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    with patch.object(s, "_probe_bypass", return_value=True), \
         patch.object(s, "_assert_invoice_found"), \
         patch.object(s, "_download_all_files", return_value=(None, None)), \
         pytest.raises(InvoiceNotFoundException):
        s.scrape()
