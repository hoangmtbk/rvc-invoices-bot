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
