"""
app.services.report_service — Kunlik Hisobotlar Servisi
Hisobot prefill, hisob-kitoblar va audit ma'lumotlari.
"""

from typing import Dict, Any, Optional
import aiosqlite
from app.services.fintech_calc import to_decimal, round_uzs

async def get_employee_report_prefill(
    conn: aiosqlite.Connection,
    company_id: int,
    user_id: int,
    today_str: str
) -> Dict[str, Any]:
    """
    Xodim uchun bugungi hisobot prefill ma'lumotlari:
    1. Tasdiqlangan karta to'ldirish summalari (+3% ustama bilan);
    2. Tasdiqlangan "Berilgan summa";
    3. Hozirgi qarzdorlik miqdori;
    4. Bugun allaqachon hisobot topshirilganligi holati.
    """
    # 1. Karta to'ldirish (+3% ustama bilan)
    cur = await conn.execute("""
        SELECT COALESCE(SUM(surcharge_amount), 0) FROM card_topups
        WHERE employee_id = ? AND status = 'APPROVED' AND company_id = ?
          AND DATE(created_at, '+5 hours') = ?
    """, (user_id, company_id, today_str))
    card_amount = (await cur.fetchone())[0]

    # 2. Berilgan summa
    cur = await conn.execute("""
        SELECT COALESCE(SUM(amount), 0) FROM given_amounts
        WHERE employee_id = ? AND status = 'APPROVED' AND company_id = ?
          AND DATE(created_at, '+5 hours') = ?
    """, (user_id, company_id, today_str))
    given_amount = (await cur.fetchone())[0]

    # 3. Qarzdorlik
    cur = await conn.execute("SELECT debt_amount FROM users WHERE id = ? AND company_id = ?", (user_id, company_id))
    user_row = await cur.fetchone()
    debt_snapshot = user_row[0] if user_row else 0

    # 4. Bugungi hisobot mavjudmi?
    cur = await conn.execute("""
        SELECT * FROM daily_reports 
        WHERE employee_id = ? AND report_date = ? AND company_id = ?
    """, (user_id, today_str, company_id))
    existing_report = await cur.fetchone()

    return {
        "success": True,
        "today": today_str,
        "card_amount": round_uzs(card_amount),
        "given_amount": round_uzs(given_amount),
        "debt_snapshot": round_uzs(debt_snapshot),
        "existing_report": dict(existing_report) if existing_report else None
    }
