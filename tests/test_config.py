import os
import importlib
from unittest.mock import patch


def test_config_constants():
    with patch.dict(os.environ, {
        "IMAP_SERVER": "mail.example.com",
        "IMAP_PORT": "993",
        "EMAIL_POLL_INTERVAL_MINUTES": "15",
        "DAILY_REPORT_TIME": "08:00",
        "RVC_TAX_CODE": "0313028740",
        "IMAP_USER": "",
        "IMAP_PASSWORD": "",
        "GEMINI_API_KEY": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "MINIO_ENDPOINT": "rvc-minio:9000",
        "MINIO_ACCESS_KEY": "minioadmin",
        "MINIO_SECRET_KEY": "minioadmin",
        "MINIO_BUCKET": "rvc-invoices",
        "MINIO_PUBLIC_URL": "https://rvc-s3.rvctel.vn",
        "WEB_PORT": "8080",
        "WEB_SECRET": "testsecret",
    }, clear=True):
        import config
        importlib.reload(config)
        assert config.IMAP_SERVER == "mail.example.com"
        assert config.IMAP_PORT == 993
        assert config.DB_PATH.endswith("invoices.db")
        assert config.MINIO_ENDPOINT == "rvc-minio:9000"
        assert config.MINIO_BUCKET == "rvc-invoices"
        assert config.MINIO_PUBLIC_URL == "https://rvc-s3.rvctel.vn"
        assert config.WEB_PORT == 8080
        assert config.WEB_SECRET == "testsecret"
        assert config.LOG_FILE.endswith("bot.log")
        assert not hasattr(config, "INVOICE_CSV")
        assert not hasattr(config, "ERROR_CSV")
