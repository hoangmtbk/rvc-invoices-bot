from .base import BaseInvoiceScraper
from .result import ScrapedResult

class VnptScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        raise NotImplementedError
