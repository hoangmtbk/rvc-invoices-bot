import logging
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import requests

from config import DB_PATH, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _telegram_url() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def _send_telegram(message: str) -> None:
    try:
        resp = requests.post(
            _telegram_url(),
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def _query_df(sql: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


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
        inv_df = _query_df(
            "SELECT invoice_type, total_after_tax, processed_date FROM invoices"
        )
        inv_df["processed_date"] = pd.to_datetime(inv_df["processed_date"])
        inv_df["total_after_tax"] = pd.to_numeric(inv_df["total_after_tax"], errors="coerce").fillna(0)
        inv_yday = inv_df[inv_df["processed_date"].dt.strftime("%Y-%m-%d") == yesterday_str]
    except Exception:
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
        err_df = _query_df("SELECT * FROM errors")
        err_df["error_date"] = pd.to_datetime(err_df["error_date"])
        err_yday = err_df[err_df["error_date"].dt.strftime("%Y-%m-%d") == yesterday_str]
        if len(err_yday) > 0:
            lines.append("")
            lines.append(f"⚠️ Lỗi xử lý: {len(err_yday)} email")
            MAX_ERRORS = 10
            shown = err_yday.head(MAX_ERRORS)
            for _, row in shown.iterrows():
                t = pd.to_datetime(row["error_date"]).strftime("%H:%M")
                subject = str(row["email_subject"])[:60]
                lines.append(
                    f"- [{t}] {subject} | {row['error_message']}"
                )
            if len(err_yday) > MAX_ERRORS:
                lines.append(f"  ... và {len(err_yday) - MAX_ERRORS} lỗi khác")
    except Exception:
        pass

    message = "\n".join(lines)
    # Telegram max message length is 4096 chars
    if len(message) > 4000:
        message = message[:4000] + "\n... (đã cắt bớt)"
    _send_telegram(message)
    logger.info(f"Daily report sent for {report_date}")
