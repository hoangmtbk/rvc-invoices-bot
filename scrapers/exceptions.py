# scrapers/exceptions.py

class CaptchaRequiredException(Exception):
    """Raised when the website requires a Captcha to proceed."""
    pass

class InvoiceNotFoundException(Exception):
    """Raised when the lookup code is submitted but the invoice is not found."""
    pass

class ScraperNotSupportedException(Exception):
    """Raised when the domain is not supported by the current factory."""
    pass