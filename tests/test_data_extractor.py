import pytest
from unittest.mock import MagicMock, patch

# Realistic Vietnamese e-invoice XML with namespaces
SAMPLE_XML_PURCHASE = b"""<?xml version="1.0" encoding="UTF-8"?>
<HDon xmlns="http://laphoadon.gdt.gov.vn/2014/09/xmlInvoiceDataFmt/v1">
  <DLHDon>
    <TTChung>
      <KHMSHDon>1</KHMSHDon>
      <KHHDon>C24TKQ</KHHDon>
      <SHDon>000123</SHDon>
      <NLap>2024-01-15</NLap>
      <HTToan>Chuy\xe1\xbb\x83n kho\xe1\xba\xa3n</HTToan>
      <MaQRCode>MKKUXJMAG</MaQRCode>
    </TTChung>
    <NDHDon>
      <NBan>
        <Ten>C\xc3\xb4ng ty CP Petrolimex</Ten>
        <MST>0100109106</MST>
        <DChi>22 H\xc3\xa0ng D\xe1\xba\xa7u, H\xc3\xa0 N\xe1\xbb\x99i</DChi>
        <STKNHang>102010000123456</STKNHang>
      </NBan>
      <NMua>
        <Ten>C\xc3\xb4ng ty TNHH RVC</Ten>
        <MST>0313028740</MST>
        <DChi>123 Nguy\xe1\xbb\x85n V\xc4\x83n Linh, Q7, TP.HCM</DChi>
      </NMua>
      <TToan>
        <TgTCThue>10000000</TgTCThue>
        <DSHHTDVu>
          <HHDVu>
            <TSuat>10%</TSuat>
          </HHDVu>
        </DSHHTDVu>
        <TgTThue>1000000</TgTThue>
        <TgTTTBSo>11000000</TgTTTBSo>
      </TToan>
    </NDHDon>
  </DLHDon>
</HDon>"""


def test_parse_xml_all_fields():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_PURCHASE)

    assert result["invoice_symbol"] == "1C24TKQ"
    assert result["invoice_number"] == "000123"
    assert result["issue_date"] == "2024-01-15"
    assert result["lookup_code"] == "MKKUXJMAG"
    assert result["seller_tax_code"] == "0100109106"
    assert result["buyer_tax_code"] == "0313028740"
    assert result["payment_method"] == "Chuyển khoản"
    assert result["bank_account"] == "102010000123456"
    assert result["total_before_tax"] == 10000000.0
    assert result["vat_rate"] == "10%"
    assert result["total_vat_amount"] == 1000000.0
    assert result["total_after_tax"] == 11000000.0


def test_parse_xml_invoice_type_purchase():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_PURCHASE)
    assert result["invoice_type"] == "PURCHASE"


def test_parse_xml_invoice_type_sale():
    from data_extractor import parse_xml
    # Replace seller MST with RVC tax code to trigger SALE
    sale_xml = SAMPLE_XML_PURCHASE.replace(
        b"<MST>0100109106</MST>", b"<MST>0313028740</MST>", 1
    )
    result = parse_xml(sale_xml)
    assert result["invoice_type"] == "SALE"


def test_parse_xml_strips_namespaces():
    from data_extractor import parse_xml
    # Should not raise even though XML has namespace declarations
    result = parse_xml(SAMPLE_XML_PURCHASE)
    assert result["invoice_number"] is not None


def test_parse_xml_raises_on_invalid_xml():
    from data_extractor import parse_xml
    with pytest.raises(ValueError, match="XML parse error"):
        parse_xml(b"this is not < valid xml >>>")


def test_to_float_handles_none():
    from data_extractor import _to_float
    assert _to_float(None) is None


def test_to_float_parses_numeric_string():
    from data_extractor import _to_float
    assert _to_float("10000000") == 10000000.0
    assert _to_float("1,000,000") == 1000000.0


def test_determine_invoice_type_sale():
    from data_extractor import _determine_invoice_type
    with patch("data_extractor.RVC_TAX_CODE", "0313028740"):
        assert _determine_invoice_type("0313028740") == "SALE"


def test_determine_invoice_type_purchase():
    from data_extractor import _determine_invoice_type
    with patch("data_extractor.RVC_TAX_CODE", "0313028740"):
        assert _determine_invoice_type("9999999999") == "PURCHASE"
        assert _determine_invoice_type(None) == "PURCHASE"
