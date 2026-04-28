import json
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET

import google.genai as genai
from google.genai import types

from config import GEMINI_API_KEY, RVC_TAX_CODE

logger = logging.getLogger(__name__)

GEMINI_PROMPT = """Bạn là trợ lý trích xuất dữ liệu hóa đơn điện tử Việt Nam.
Trích xuất thông tin từ file PDF hóa đơn và trả về JSON với định dạng chính xác sau.
QUAN TRỌNG: Chỉ trả về JSON thuần túy, KHÔNG có văn bản hay markdown khác.

{
  "invoice_symbol": "ký hiệu hóa đơn hoặc null",
  "invoice_number": "số hóa đơn hoặc null",
  "issue_date": "ngày lập YYYY-MM-DD hoặc null",
  "lookup_code": "mã tra cứu hoặc null",
  "lookup_website": "website tra cứu hoặc null",
  "seller_name": "tên người bán hoặc null",
  "seller_tax_code": "mã số thuế người bán hoặc null",
  "seller_address": "địa chỉ người bán hoặc null",
  "buyer_name": "tên người mua hoặc null",
  "buyer_tax_code": "mã số thuế người mua hoặc null",
  "buyer_address": "địa chỉ người mua hoặc null",
  "payment_method": "hình thức thanh toán hoặc null",
  "bank_account": "số tài khoản ngân hàng hoặc null",
  "total_before_tax": số_thực_hoặc_null,
  "vat_rate": "thuế suất ví dụ '10%' hoặc null",
  "total_vat_amount": số_thực_hoặc_null,
  "total_after_tax": số_thực_hoặc_null
}"""


def _strip_namespaces(xml_str: str) -> str:
    # Remove xmlns declarations so ET does not inject {ns} into tag names
    xml_str = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", xml_str)
    # Also strip any {ns} prefixes that may already be present in the string
    xml_str = re.sub(r"\{[^}]+\}", "", xml_str)
    return xml_str


def _find_text(root: ET.Element, *tags: str) -> str | None:
    for tag in tags:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            return el.text.strip()
    return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def _determine_invoice_type(seller_tax_code: str | None) -> str:
    return "SALE" if seller_tax_code == RVC_TAX_CODE else "PURCHASE"


def parse_xml(xml_bytes: bytes) -> dict:
    try:
        xml_str = xml_bytes.decode("utf-8", errors="replace")
        xml_str = _strip_namespaces(xml_str)
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise ValueError(f"XML parse error: {e}")

    nban = root.find(".//NBan") or root
    nmua = root.find(".//NMua") or root
    hhdvu = root.find(".//HHDVu")

    seller_tax_code = _find_text(nban, "MST", "MaSoThue")
    symbol_part1 = _find_text(root, "KHMSHDon") or ""
    symbol_part2 = _find_text(root, "KHHDon") or ""

    return {
        "invoice_type": _determine_invoice_type(seller_tax_code),
        "invoice_symbol": (symbol_part1 + symbol_part2).strip() or None,
        "invoice_number": _find_text(root, "SHDon", "SoHoaDon"),
        "issue_date": _find_text(root, "NLap", "NgayLap"),
        "lookup_code": _find_text(
            root, "MaQRCode", "MTra", "MCCQT", "MaTraCuu", "MaKiemTra"
        ),
        "lookup_website": None,
        "seller_name": _find_text(nban, "Ten"),
        "seller_tax_code": seller_tax_code,
        "seller_address": _find_text(nban, "DChi", "DiaChiNBan"),
        "buyer_name": _find_text(nmua, "Ten"),
        "buyer_tax_code": _find_text(nmua, "MST", "MaSoThue"),
        "buyer_address": _find_text(nmua, "DChi"),
        "payment_method": _find_text(root, "HTToan", "HinhThucThanhToan"),
        "bank_account": _find_text(nban, "STKNHang", "SoTK", "TaiKhoanNH"),
        "total_before_tax": _to_float(_find_text(root, "TgTCThue", "TongTienChuaThue")),
        "vat_rate": _find_text(hhdvu, "TSuat", "ThueSuat") if hhdvu is not None else None,
        "total_vat_amount": _to_float(_find_text(root, "TgTThue", "TongTienThue")),
        "total_after_tax": _to_float(_find_text(root, "TgTTTBSo", "TongTienThanhToan")),
    }


def parse_pdf_via_gemini(pdf_bytes: bytes) -> dict:
    client = genai.Client(api_key=GEMINI_API_KEY)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            uploaded = client.files.upload(
                file=f,
                config=types.UploadFileConfig(mime_type="application/pdf")
            )
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[GEMINI_PROMPT, uploaded]
        )
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned invalid JSON: {e}")
    finally:
        os.unlink(tmp_path)

    data["invoice_type"] = _determine_invoice_type(data.get("seller_tax_code"))
    return data
