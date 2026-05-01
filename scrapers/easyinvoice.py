from .base import BaseInvoiceScraper
from .result import ScrapedResult

class EasyInvoiceScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        raise NotImplementedError
