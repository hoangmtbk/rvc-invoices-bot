from .base import BaseInvoiceScraper
from .result import ScrapedResult

class PetrolimexScraper(BaseInvoiceScraper):
    def scrape(self) -> ScrapedResult:
        raise NotImplementedError
