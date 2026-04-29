import logging
import sqlite3
from datetime import datetime, timedelta

import requests

from config import DB_PATH, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

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

    def fmt(n: float) -> str:
        return f"{n:,.0f}"

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT invoice_type, total_after_tax FROM invoices "
            "WHERE processed_date LIKE ?",
            (f"{yesterday_str}%",),
        ).fetchall()
        conn.close()
    except Exception:
        rows = []

    total = len(rows)
    purchase = [r for r in rows if r["invoice_type"] == "PURCHASE"]
    sale = [r for r in rows if r["invoice_type"] == "SALE"]

    def _sum(rlist):
        s = 0.0
        for r in rlist:
            try:
                s += float(r["total_after_tax"] or 0)
            except (TypeError, ValueError):
                pass
        return s

    lines = [
        f"📊 Báo cáo hóa đơn ngày {report_date}",
        "",
        f"✅ Tổng số hóa đơn: {total}",
        f"📥 Đầu vào (PURCHASE): {len(purchase)} hóa đơn | Tổng tiền: {fmt(_sum(purchase))} VND",
        f"📤 Đầu ra (SALE): {len(sale)} hóa đơn | Tổng tiền: {fmt(_sum(sale))} VND",
    ]

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        err_rows = conn.execute(
            "SELECT error_date, email_sender, email_subject, error_message "
            "FROM errors WHERE error_date LIKE ?",
            (f"{yesterday_str}%",),
        ).fetchall()
        conn.close()
        if err_rows:
            lines.append("")
            lines.append(f"⚠️ Lỗi xử lý: {len(err_rows)} email")
            for row in err_rows:
                try:
                    t = datetime.strptime(row["error_date"], "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
                except Exception:
                    t = "??"
                lines.append(
                    f"- [{t}] Từ: {row['email_sender']} | "
                    f"Tiêu đề: {row['email_subject']} | "
                    f"Lỗi: {row['error_message']}"
                )
    except Exception:
        pass

    _send_telegram("\n".join(lines))
    logger.info(f"Daily report sent for {report_date}")
