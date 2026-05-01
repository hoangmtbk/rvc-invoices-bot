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
