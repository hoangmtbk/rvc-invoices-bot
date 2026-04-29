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


def test_parse_pdf_via_gemini_parses_json_response(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    mock_response = MagicMock()
    mock_response.text = (
        '{"invoice_number": "001", "seller_tax_code": "0100109106",'
        ' "total_after_tax": 5500000, "seller_name": "Cty ABC"}'
    )
    mock_client = MagicMock()
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("data_extractor.genai.Client", return_value=mock_client), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"):

        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        from data_extractor import parse_pdf_via_gemini
        result = parse_pdf_via_gemini(b"%PDF-1.4")

    assert result["invoice_number"] == "001"
    assert result["invoice_type"] == "PURCHASE"
    assert result["total_after_tax"] == 5500000
    assert result["seller_name"] == "Cty ABC"


def test_parse_pdf_via_gemini_strips_markdown_fences(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    mock_response = MagicMock()
    mock_response.text = '```json\n{"invoice_number": "002", "seller_tax_code": null}\n```'
    mock_client = MagicMock()
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("data_extractor.genai.Client", return_value=mock_client), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"):

        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        from data_extractor import parse_pdf_via_gemini
        result = parse_pdf_via_gemini(b"%PDF-1.4")

    assert result["invoice_number"] == "002"


def test_parse_pdf_via_gemini_raises_on_invalid_json(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    mock_response = MagicMock()
    mock_response.text = "Không thể trích xuất dữ liệu từ file này."
    mock_client = MagicMock()
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("data_extractor.genai.Client", return_value=mock_client), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"):

        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        from data_extractor import parse_pdf_via_gemini
        with pytest.raises(ValueError, match="invalid JSON"):
            parse_pdf_via_gemini(b"%PDF-1.4")


def test_parse_pdf_via_gemini_sets_sale_type(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    mock_response = MagicMock()
    mock_response.text = '{"invoice_number": "003", "seller_tax_code": "0313028740"}'
    mock_client = MagicMock()
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("data_extractor.genai.Client", return_value=mock_client), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"), \
         patch("data_extractor.RVC_TAX_CODE", "0313028740"):

        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        from data_extractor import parse_pdf_via_gemini
        result = parse_pdf_via_gemini(b"%PDF-1.4")

    assert result["invoice_type"] == "SALE"


SAMPLE_XML_WITH_CONTRACT = b"""<?xml version="1.0" encoding="UTF-8"?>
<HDon xmlns="http://laphoadon.gdt.gov.vn/2014/09/xmlInvoiceDataFmt/v1">
  <DLHDon>
    <TTChung>
      <SHDon>000999</SHDon>
      <NLap>2026-04-29</NLap>
      <SoHopDong>HD-2026-001</SoHopDong>
    </TTChung>
    <NDHDon>
      <NBan><MST>0100109106</MST></NBan>
      <NMua>
        <MST>0313028740</MST>
        <MaThueBao>VT-00123456</MaThueBao>
      </NMua>
      <TToan>
        <TgTCThue>0</TgTCThue>
        <TgTThue>0</TgTThue>
        <TgTTTBSo>0</TgTTTBSo>
      </TToan>
    </NDHDon>
  </DLHDon>
</HDon>"""


def test_parse_xml_contract_number():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_WITH_CONTRACT)
    assert result["contract_number"] == "HD-2026-001"


def test_parse_xml_customer_code_mathuebao():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_WITH_CONTRACT)
    assert result["customer_code"] == "VT-00123456"


def test_parse_xml_contract_number_missing_returns_none():
    from data_extractor import parse_xml
    result = parse_xml(SAMPLE_XML_PURCHASE)
    assert result.get("contract_number") is None


def test_parse_pdf_via_gemini_includes_new_fields(tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    mock_response = MagicMock()
    mock_response.text = (
        '{"invoice_number": "001", "seller_tax_code": "0100109106",'
        ' "total_after_tax": 5500000,'
        ' "contract_number": "HD-001", "customer_code": "KH-999"}'
    )
    mock_client = MagicMock()
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("data_extractor.genai.Client", return_value=mock_client), \
         patch("data_extractor.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("data_extractor.os.unlink"):
        mock_file = MagicMock()
        mock_file.name = str(fake_pdf)
        mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        from data_extractor import parse_pdf_via_gemini
        result = parse_pdf_via_gemini(b"%PDF-1.4")

    assert result["contract_number"] == "HD-001"
    assert result["customer_code"] == "KH-999"
