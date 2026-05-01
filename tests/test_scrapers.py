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
