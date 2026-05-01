from dataclasses import dataclass


@dataclass
class ScrapedResult:
    xml_bytes: bytes | None = None
    pdf_bytes: bytes | None = None
    xml_path: str | None = None
    pdf_path: str | None = None
