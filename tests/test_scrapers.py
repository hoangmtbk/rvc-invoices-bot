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



from scrapers.factory import ScraperFactory
from scrapers.exceptions import ScraperNotSupportedException


def test_factory_easyinvoice_subdomain():
    from scrapers.easyinvoice import EasyInvoiceScraper
    page = MagicMock()
    scraper = ScraperFactory.get(
        "https://0102362584001hd.easyinvoice.com.vn/Search/Index", page, "CODE"
    )
    assert isinstance(scraper, EasyInvoiceScraper)


def test_factory_easyinvoice_vn_subdomain():
    """easyinvoice.vn subdomains (e.g. <tax-code>hd.easyinvoice.vn) must also resolve."""
    from scrapers.easyinvoice import EasyInvoiceScraper
    page = MagicMock()
    scraper = ScraperFactory.get(
        "http://0312668018hd.easyinvoice.vn/Invoice/ViewFromEmail?token=abc", page, "CODE"
    )
    assert isinstance(scraper, EasyInvoiceScraper)


def test_factory_bkavehoadon_root():
    """ehoadon.vn root domain must resolve to BKAVeHoadonScraper."""
    from scrapers.bkavehoadon import BKAVeHoadonScraper
    page = MagicMock()
    scraper = ScraperFactory.get(
        "https://tchd.ehoadon.vn/TCHD?MTC=OSDPQI3MAKB", page, "OSDPQI3MAKB"
    )
    assert isinstance(scraper, BKAVeHoadonScraper)


def test_factory_bkavehoadon_tracuu_subdomain():
    """tracuu.ehoadon.vn is a subdomain — must also resolve."""
    from scrapers.bkavehoadon import BKAVeHoadonScraper
    page = MagicMock()
    scraper = ScraperFactory.get(
        "http://tracuu.ehoadon.vn/OSDPQI3MAKB", page, "OSDPQI3MAKB"
    )
    assert isinstance(scraper, BKAVeHoadonScraper)


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

from scrapers.vnpt import VnptScraper, _classify_bytes


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
         patch.object(s, "_refresh_captcha_image"), \
         pytest.raises(CaptchaRequiredException, match="3 attempts"):
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
    """_enter_captcha must call click(click_count=3) before press_sequentially."""
    page = MagicMock()
    el = MagicMock()
    el.count.return_value = 1
    page.locator.return_value.first = el

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")
    s._enter_captcha("1234")

    el.click.assert_called_once_with(click_count=3)
    el.press_sequentially.assert_called_once()
    args, _ = el.press_sequentially.call_args
    assert args[0] == "1234"


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


# ── VNPT captcha — Capsolver integration test ────────────────────────────────


def test_screenshot_and_solve_captcha_calls_capsolver():
    """_screenshot_and_solve_captcha must call capsolver_solve_image with the screenshot path."""
    page = MagicMock()
    img_loc = MagicMock()
    img_loc.count.return_value = 1
    img_loc.is_visible.return_value = True
    page.locator.return_value.first = img_loc

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")

    with patch("scrapers.vnpt.capsolver_solve_image", return_value="7094") as mock_cap, \
         patch("tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("os.unlink"):
        mock_tmp.return_value.__enter__ = lambda self: self
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        mock_tmp.return_value.name = "/tmp/cap_test.png"
        result = s._screenshot_and_solve_captcha()

    mock_cap.assert_called_once_with("/tmp/cap_test.png")
    assert result == "7094"


# ── pre-submission validation tests ─────────────────────────────────────────

def test_vnpt_scrape_skips_submit_when_solution_is_not_4_digits():
    """Invalid solver output must refresh captcha and not call _enter_captcha/_submit."""
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()

    s = VnptScraper(page, "https://vttphcm-tt78.vnpt-invoice.com.vn/", "CODE")

    with patch.object(s, "_probe_bypass", return_value=False), \
         patch.object(s, "_fill_lookup_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value="AB1C"), \
         patch.object(s, "_enter_captcha") as mock_enter, \
         patch.object(s, "_submit_and_wait_for_results") as mock_submit, \
         patch.object(s, "_refresh_captcha_image") as mock_refresh, \
         pytest.raises(CaptchaRequiredException, match="3 attempts"):
        s.scrape()

    mock_enter.assert_not_called()
    mock_submit.assert_not_called()
    # refresh called on first 2 failures (not on last attempt)
    assert mock_refresh.call_count == 2


# ── Petrolimex scraper unit tests ────────────────────────────────────────────

from scrapers.petrolimex import PetrolimexScraper


def _make_petrolimex_page():
    """Return a MagicMock page with sensible defaults for Petrolimex tests."""
    page = MagicMock()
    page.goto = MagicMock()
    page.mouse = MagicMock()
    # locator(...).first returns a visible element by default
    loc = MagicMock()
    loc.count.return_value = 1
    loc.first.is_visible.return_value = True
    page.locator.return_value = loc
    page.evaluate.return_value = ""
    return page


def test_petrolimex_scraper_instantiation():
    page = _make_petrolimex_page()
    s = PetrolimexScraper(page, "https://hoadon.petrolimex.com.vn", "VF4S5TMTE*")
    assert s.lookup_code == "VF4S5TMTE*"
    assert "petrolimex" in s.url


def test_petrolimex_scrape_success():
    """Happy path: captcha solved first try, downloads visible, returns xml+pdf."""
    page = _make_petrolimex_page()
    s = PetrolimexScraper(page, "https://hoadon.petrolimex.com.vn", "VF4S5TMTE*")

    xml_data = b"<?xml version='1.0'?><HDon/>"
    pdf_data = b"%PDF-1.4 fake"

    with patch.object(s, "_enter_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value="1234"), \
         patch.object(s, "_enter_captcha"), \
         patch.object(s, "_click_submit"), \
         patch.object(s, "_downloads_visible", return_value=True), \
         patch.object(s, "_download_all", return_value=(xml_data, pdf_data)):
        result = s.scrape()

    assert result.xml_bytes == xml_data
    assert result.pdf_bytes == pdf_data


def test_petrolimex_scrape_invalid_captcha_retries_then_raises():
    """Solver returns non-4-digit string every time → CaptchaRequiredException."""
    page = _make_petrolimex_page()
    s = PetrolimexScraper(page, "https://hoadon.petrolimex.com.vn", "VF4S5TMTE*")

    with patch.object(s, "_enter_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value=""), \
         patch.object(s, "_enter_captcha") as mock_enter, \
         patch.object(s, "_click_submit") as mock_submit, \
         pytest.raises(CaptchaRequiredException, match="3 attempts"):
        s.scrape()

    mock_enter.assert_not_called()
    mock_submit.assert_not_called()


def test_petrolimex_scrape_no_downloads_after_submit_retries_then_raises():
    """Captcha valid but no downloads ever appear → CaptchaRequiredException."""
    page = _make_petrolimex_page()
    s = PetrolimexScraper(page, "https://hoadon.petrolimex.com.vn", "VF4S5TMTE*")

    with patch.object(s, "_enter_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value="9999"), \
         patch.object(s, "_enter_captcha"), \
         patch.object(s, "_click_submit"), \
         patch.object(s, "_downloads_visible", return_value=False), \
         pytest.raises(CaptchaRequiredException, match="3 attempts"):
        s.scrape()


def test_petrolimex_scrape_raises_invoice_not_found():
    """If page body contains 'không tìm thấy' after submit → InvoiceNotFoundException."""
    page = _make_petrolimex_page()
    page.evaluate.return_value = "kết quả không tìm thấy hóa đơn"
    s = PetrolimexScraper(page, "https://hoadon.petrolimex.com.vn", "VF4S5TMTE*")

    with patch.object(s, "_enter_code"), \
         patch.object(s, "_screenshot_and_solve_captcha", return_value="5678"), \
         patch.object(s, "_enter_captcha"), \
         patch.object(s, "_click_submit"), \
         pytest.raises(InvoiceNotFoundException, match="not found"):
        s.scrape()


def test_petrolimex_screenshot_and_solve_calls_capsolver():
    """_screenshot_and_solve_captcha delegates to capsolver_solve_image."""
    page = _make_petrolimex_page()
    img_loc = MagicMock()
    img_loc.count.return_value = 1
    img_loc.first.is_visible.return_value = True
    page.locator.return_value.first = img_loc

    s = PetrolimexScraper(page, "https://hoadon.petrolimex.com.vn", "VF4S5TMTE*")

    with patch("scrapers.petrolimex.capsolver_solve_image", return_value="4321") as mock_cap, \
         patch("tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("os.unlink"):
        mock_tmp.return_value.__enter__ = lambda self: self
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        mock_tmp.return_value.name = "/tmp/plx_test.png"
        result = s._screenshot_and_solve_captcha()

    mock_cap.assert_called_once_with("/tmp/plx_test.png")
    assert result == "4321"


# ── uid=111 Petrolimex email flow ────────────────────────────────────────────

from web_extraction_router import _extract_lookup_code


def test_extract_lookup_code_preserves_asterisk():
    """uid=111 email: code in email is VF4S5TMTE* — asterisk must be kept."""
    text = (
        "Kính gửi Quý khách hàng,\n"
        "Mã tra cứu: VF4S5TMTE*\n"
        "Vui lòng truy cập hoadon.petrolimex.com.vn để tra cứu hóa đơn.\n"
    )
    code = _extract_lookup_code(text)
    assert code == "VF4S5TMTE*"


def test_extract_lookup_code_plain_code_no_asterisk():
    """Codes without asterisk are extracted unchanged."""
    text = "Mã tra cứu: ABCDEF123\n"
    code = _extract_lookup_code(text)
    assert code == "ABCDEF123"


def test_petrolimex_uid111_full_flow():
    """Simulate the full uid=111 email: code=VF4S5TMTE*, captcha solved, xml+pdf returned."""
    page = _make_petrolimex_page()
    s = PetrolimexScraper(page, "https://hoadon.petrolimex.com.vn", "VF4S5TMTE*")

    xml_data = b"<?xml version='1.0'?><HDon/>"
    pdf_data = b"%PDF-1.4 fake"

    with patch.object(s, "_enter_code") as mock_code, \
         patch.object(s, "_screenshot_and_solve_captcha", return_value="9264"), \
         patch.object(s, "_enter_captcha") as mock_captcha, \
         patch.object(s, "_click_submit") as mock_submit, \
         patch.object(s, "_downloads_visible", return_value=True), \
         patch.object(s, "_download_all", return_value=(xml_data, pdf_data)):
        result = s.scrape()

    # Verify the full interaction chain ran in order
    mock_code.assert_called_once()
    mock_captcha.assert_called_once_with("9264")
    mock_submit.assert_called_once()
    assert result.xml_bytes == xml_data
    assert result.pdf_bytes == pdf_data


# ── BKAVeHoadon scraper tests ─────────────────────────────────────────────────

from scrapers.bkavehoadon import BKAVeHoadonScraper


def _make_bkav_page():
    """Build a mock page that satisfies the BKAVeHoadon scraper flow."""
    page = MagicMock()

    # Iframe element attached in DOM
    iframe_loc = MagicMock()
    iframe_loc.count.return_value = 1

    # Frame mock (returned by page.frame(name=...))
    frame = MagicMock()
    frame.url = "https://tchd.ehoadon.vn/Lookup?InvoiceGUID=abc"

    # #btnDownload in the frame — visible
    btn_dl = MagicMock()
    btn_dl.count.return_value = 1
    btn_dl.first.is_visible.return_value = True

    # XML download link in frame — visible after hover
    xml_link = MagicMock()
    xml_link.count.return_value = 1
    xml_link.first.is_visible.return_value = True

    # PDF download link in frame — visible after hover
    pdf_link = MagicMock()
    pdf_link.count.return_value = 1
    pdf_link.first.is_visible.return_value = True

    def frame_locator(sel):
        if "#btnDownload" in sel:
            return btn_dl
        if "LinkDownXML" in sel or "XML" in sel:
            return xml_link
        if "LinkDownPDF" in sel or "PDF" in sel:
            return pdf_link
        return MagicMock(count=MagicMock(return_value=0))

    frame.locator.side_effect = frame_locator

    def page_locator(sel):
        if "frameViewInvoice" in sel:
            return iframe_loc
        return MagicMock(count=MagicMock(return_value=0))

    page.locator.side_effect = page_locator
    page.frame.return_value = frame
    page.frames = [frame]
    page.evaluate.return_value = "Hóa đơn ĐPH"
    return page, frame


def test_bkavehoadon_instantiation():
    page = MagicMock()
    s = BKAVeHoadonScraper(page, "https://tchd.ehoadon.vn/TCHD?MTC=CODE123", "CODE123")
    assert s.lookup_code == "CODE123"


def test_bkavehoadon_build_lookup_url_from_tracuu():
    """tracuu.ehoadon.vn/CODE should be rewritten to tchd canonical URL."""
    page = MagicMock()
    s = BKAVeHoadonScraper(page, "http://tracuu.ehoadon.vn/OSDPQI3MAKB", "OSDPQI3MAKB")
    assert s._build_lookup_url() == "https://tchd.ehoadon.vn/TCHD?MTC=OSDPQI3MAKB"


def test_bkavehoadon_build_lookup_url_already_canonical():
    """tchd URL with MTC should be returned unchanged."""
    page = MagicMock()
    url = "https://tchd.ehoadon.vn/TCHD?MTC=OSDPQI3MAKB"
    s = BKAVeHoadonScraper(page, url, "OSDPQI3MAKB")
    assert s._build_lookup_url() == url


def test_bkavehoadon_scrape_success():
    page, frame = _make_bkav_page()
    xml_data = b"<?xml version='1.0'?><HDon/>"
    pdf_data = b"%PDF-1.4 fake"

    with patch.object(BKAVeHoadonScraper, "_download_from_frame",
                      side_effect=[xml_data, pdf_data]):
        s = BKAVeHoadonScraper(page, "https://tchd.ehoadon.vn/TCHD?MTC=CODE123", "CODE123")
        result = s.scrape()

    assert result.xml_bytes == xml_data
    assert result.pdf_bytes == pdf_data


def test_bkavehoadon_scrape_invoice_not_found():
    page = MagicMock()
    page.evaluate.return_value = "Không tìm thấy hóa đơn"
    # No iframe attached
    iframe_loc = MagicMock()
    iframe_loc.count.return_value = 0
    no_attach = MagicMock()
    no_attach.wait_for.side_effect = Exception("timeout")
    page.locator.return_value = no_attach

    from scrapers.exceptions import InvoiceNotFoundException
    s = BKAVeHoadonScraper(page, "https://tchd.ehoadon.vn/TCHD?MTC=BADCODE", "BADCODE")
    with pytest.raises(InvoiceNotFoundException):
        s.scrape()
