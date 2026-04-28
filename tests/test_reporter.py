from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def test_send_error_alert_formats_message_correctly():
    with patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_error_alert
        send_error_alert("Hóa đơn Petrolimex tháng 1", "ZIP", "No XML in archive")

    mock_post.assert_called_once()
    body = mock_post.call_args[1]["json"]["text"]
    assert "Hóa đơn Petrolimex tháng 1" in body
    assert "ZIP" in body
    assert "No XML in archive" in body
    assert "⚠️" in body


def test_send_error_alert_does_not_raise_on_telegram_failure():
    with patch("reporter.requests.post", side_effect=Exception("Network error")):
        from reporter import send_error_alert
        send_error_alert("subject", "XML", "error")  # must not raise


def test_send_daily_report_invoice_summary():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    inv_df = pd.DataFrame([
        {"processed_date": f"{yesterday} 09:00:00", "invoice_type": "PURCHASE", "total_after_tax": 5000000.0},
        {"processed_date": f"{yesterday} 10:00:00", "invoice_type": "PURCHASE", "total_after_tax": 3000000.0},
        {"processed_date": f"{yesterday} 11:00:00", "invoice_type": "SALE",     "total_after_tax": 8000000.0},
    ])

    with patch("reporter.pd.read_csv", side_effect=[inv_df, FileNotFoundError()]), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    body = mock_post.call_args[1]["json"]["text"]
    assert "Tổng số hóa đơn: 3" in body
    assert "PURCHASE" in body
    assert "SALE" in body
    assert "8,000,000" in body or "8000000" in body
    assert "Lỗi" not in body


def test_send_daily_report_includes_errors_when_present():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    inv_df = pd.DataFrame([
        {"processed_date": f"{yesterday} 10:00:00", "invoice_type": "PURCHASE", "total_after_tax": 5000000.0},
    ])
    err_df = pd.DataFrame([
        {
            "error_date": f"{yesterday} 09:05:00",
            "email_sender": "supplier@abc.com",
            "email_time": "09:05",
            "email_subject": "Hóa đơn XYZ",
            "branch": "ZIP",
            "error_message": "Corrupt ZIP file",
        }
    ])

    with patch("reporter.pd.read_csv", side_effect=[inv_df, err_df]), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    body = mock_post.call_args[1]["json"]["text"]
    assert "Lỗi xử lý: 1 email" in body
    assert "supplier@abc.com" in body
    assert "Hóa đơn XYZ" in body
    assert "Corrupt ZIP file" in body


def test_send_daily_report_omits_error_section_when_no_errors():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    inv_df = pd.DataFrame([
        {"processed_date": f"{yesterday} 10:00:00", "invoice_type": "PURCHASE", "total_after_tax": 1000000.0},
    ])
    err_df = pd.DataFrame(columns=["error_date", "email_sender", "email_time", "email_subject", "branch", "error_message"])

    with patch("reporter.pd.read_csv", side_effect=[inv_df, err_df]), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    body = mock_post.call_args[1]["json"]["text"]
    assert "Lỗi" not in body


def test_send_daily_report_handles_missing_invoice_csv():
    with patch("reporter.pd.read_csv", side_effect=FileNotFoundError()), \
         patch("reporter.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        from reporter import send_daily_report
        send_daily_report()

    mock_post.assert_called_once()
    body = mock_post.call_args[1]["json"]["text"]
    assert "Tổng số hóa đơn: 0" in body
