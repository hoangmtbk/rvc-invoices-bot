import os
import importlib
from unittest.mock import patch


def test_config_default_values():
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
    }, clear=True):
        import config
        importlib.reload(config)
        assert config.IMAP_SERVER == "mail.example.com"
        assert config.IMAP_PORT == 993
        assert config.EMAIL_POLL_INTERVAL_MINUTES == 15
        assert config.DAILY_REPORT_TIME == "08:00"
        assert config.RVC_TAX_CODE == "0313028740"
        assert config.INVOICE_CSV.endswith("Tong_hop_hoa_don.csv")
        assert config.ERROR_CSV.endswith("errors.csv")
        assert config.LOG_FILE.endswith("bot.log")
