from urllib.parse import urlparse

from .base import BaseInvoiceScraper
from .exceptions import ScraperNotSupportedException


def _get_registry() -> dict[str, type]:
    from .bkavehoadon import BKAVeHoadonScraper
    from .easyinvoice import EasyInvoiceScraper
    from .misa import MisaScraper
    from .petrolimex import PetrolimexScraper
    from .viettel import ViettelScraper
    from .vnpt import VnptScraper
    return {
        "ehoadon.vn":                       BKAVeHoadonScraper,
        "easyinvoice.vn":                   EasyInvoiceScraper,
        "easyinvoice.com.vn":               EasyInvoiceScraper,
        "meinvoice.vn":                     MisaScraper,
        "hoadon.petrolimex.com.vn":         PetrolimexScraper,
        "vietteltelecom.vn":                ViettelScraper,
        "vnpt-invoice.com.vn":              VnptScraper,
    }


class ScraperFactory:
    @classmethod
    def get(cls, url: str, page, lookup_code: str) -> BaseInvoiceScraper:
        netloc = (urlparse(url).hostname or "").lower()
        registry = _get_registry()
        for key, scraper_cls in registry.items():
            if netloc == key or netloc.endswith("." + key):
                return scraper_cls(page, url, lookup_code)
        raise ScraperNotSupportedException(f"No scraper registered for domain: {netloc}")
