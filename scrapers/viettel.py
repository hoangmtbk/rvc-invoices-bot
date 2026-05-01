from .base import BaseInvoiceScraper
from .result import ScrapedResult

class ViettelScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        raise NotImplementedError
