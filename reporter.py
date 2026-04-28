import logging
from datetime import datetime, timedelta

import pandas as pd
import requests

from config import ERROR_CSV, INVOICE_CSV, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _telegram_url() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def _send_telegram(message: str) -> None:
    try:
        resp = requests.post(
            _telegram_url(),
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def send_error_alert(subject: str, branch: str, error: str) -> None:
    message = (
        "⚠️ Lỗi xử lý hóa đơn\n"
        f"📧 Email: {subject}\n"
        f"🔀 Nhánh: {branch}\n"
        f"❌ Lỗi: {error}"
    )
    _send_telegram(message)


def send_daily_report() -> None:
    yesterday_dt = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday_dt.strftime("%Y-%m-%d")
    report_date = yesterday_dt.strftime("%d/%m/%Y")

    try:
        inv_df = pd.read_csv(INVOICE_CSV, encoding="utf-8")
        inv_df["processed_date"] = pd.to_datetime(inv_df["processed_date"])
        inv_yday = inv_df[inv_df["processed_date"].dt.strftime("%Y-%m-%d") == yesterday_str]
    except FileNotFoundError:
        inv_yday = pd.DataFrame(columns=["invoice_type", "total_after_tax"])

    total = len(inv_yday)
    purchase = inv_yday[inv_yday["invoice_type"] == "PURCHASE"]
    sale = inv_yday[inv_yday["invoice_type"] == "SALE"]

    def fmt(n: float) -> str:
        return f"{n:,.0f}"

    lines = [
        f"📊 Báo cáo hóa đơn ngày {report_date}",
        "",
        f"✅ Tổng số hóa đơn: {total}",
        f"📥 Đầu vào (PURCHASE): {len(purchase)} hóa đơn | Tổng tiền: {fmt(purchase['total_after_tax'].sum())} VND",
        f"📤 Đầu ra (SALE): {len(sale)} hóa đơn | Tổng tiền: {fmt(sale['total_after_tax'].sum())} VND",
    ]

    try:
        err_df = pd.read_csv(ERROR_CSV, encoding="utf-8")
        err_df["error_date"] = pd.to_datetime(err_df["error_date"])
        err_yday = err_df[err_df["error_date"].dt.strftime("%Y-%m-%d") == yesterday_str]
        if len(err_yday) > 0:
            lines.append("")
            lines.append(f"⚠️ Lỗi xử lý: {len(err_yday)} email")
            for _, row in err_yday.iterrows():
                t = pd.to_datetime(row["error_date"]).strftime("%H:%M")
                lines.append(
                    f"- [{t}] Từ: {row['email_sender']} | "
                    f"Tiêu đề: {row['email_subject']} | "
                    f"Lỗi: {row['error_message']}"
                )
    except FileNotFoundError:
        pass

    _send_telegram("\n".join(lines))
    logger.info(f"Daily report sent for {report_date}")
