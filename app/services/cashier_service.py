"""
app.services.cashier_service — Kassa va Kassirlik Amallari Servisi
Kassa taqqoslash, qabul qilish va tafovutlarni hisoblash.
"""

from typing import List, Dict, Any, Optional
import aiosqlite
from app.services.fintech_calc import to_decimal, round_uzs

async def calculate_daily_cashier_comparison(
    conn: aiosqlite.Connection,
    company_id: int,
    target_date: str
) -> List[Dict[str, Any]]:
    """
    Kassa taqqoslash: Har bir xodimning hisoboti bilan kassir qabul qilgan
    summani solishtirish va tafovutni hisoblash.
    """
    query = """
    SELECT 
        u.id as employee_id,
        u.full_name as employee_name,
        u.telegram_id,
        dr.id as report_id,
        COALESCE(dr.net_amount, 0) as report_amount,
        dr.status as report_status,
        COALESCE(ch_agg.total_cashier_amount, 0) as cashier_amount,
        COALESCE(ch_agg.total_amount_uzs, 0) as cashier_amount_uzs,
        COALESCE(ch_agg.total_amount_usd, 0) as cashier_amount_usd,
        ch_agg.cashier_names
    FROM users u
    LEFT JOIN daily_reports dr 
        ON dr.employee_id = u.id AND dr.report_date = ? AND dr.company_id = ?
    LEFT JOIN (
        SELECT 
            employee_id, 
            SUM(amount) as total_cashier_amount,
            SUM(amount_uzs) as total_amount_uzs,
            SUM(amount_usd) as total_amount_usd,
            GROUP_CONCAT(DISTINCT cashier_user.full_name) as cashier_names
        FROM cashier_handovers ch
        JOIN users cashier_user ON ch.cashier_id = cashier_user.id
        WHERE ch.handover_date = ? AND ch.company_id = ?
        GROUP BY employee_id
    ) ch_agg ON ch_agg.employee_id = u.id
    WHERE u.is_active = 1 AND u.role NOT IN ('ADMIN', 'DEVELOPER') AND u.company_id = ?
    ORDER BY u.full_name ASC
    """
    cursor = await conn.execute(query, (target_date, company_id, target_date, company_id, company_id))
    rows = await cursor.fetchall()

    results = []
    for r in rows:
        d_rep = to_decimal(r["report_amount"])
        d_cash = to_decimal(r["cashier_amount"])
        diff = round_uzs(d_cash - d_rep)
        rep_amt = round_uzs(d_rep)
        cash_amt = round_uzs(d_cash)

        results.append({
            "employee_id": r["employee_id"],
            "employee_name": r["employee_name"],
            "telegram_id": r["telegram_id"],
            "report_id": r["report_id"],
            "report_amount": rep_amt,
            "report_status": r["report_status"] or "TOPSHIRILMAGAN",
            "cashier_amount": cash_amt,
            "cashier_amount_uzs": round_uzs(r["cashier_amount_uzs"]),
            "cashier_amount_usd": float(r["cashier_amount_usd"] or 0),
            "cashier_names": r["cashier_names"] or "-",
            "difference": diff,
            "is_match": (diff == 0 and r["report_status"] is not None),
            "has_diff": (diff != 0 and r["report_status"] is not None)
        })

    return results


def summarize_cashier_comparison(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Kassa taqqoslash natijalarini jamlab, FinTech Zero Discrepancy xulosasini beradi.
    """
    total_expected = sum(r["report_amount"] for r in results if r["report_status"] != "TOPSHIRILMAGAN")
    total_collected = sum(r["cashier_amount"] for r in results)
    total_collected_uzs = sum(r["cashier_amount_uzs"] for r in results)
    total_collected_usd = sum(r["cashier_amount_usd"] for r in results)
    total_diff = total_collected - total_expected

    match_count = sum(1 for r in results if r["is_match"])
    diff_count = sum(1 for r in results if r["has_diff"])
    unsubmitted_count = sum(1 for r in results if r["report_status"] == "TOPSHIRILMAGAN")

    is_zero_discrepancy = (total_diff == 0 and diff_count == 0 and unsubmitted_count == 0 and len(results) > 0)

    return {
        "total_expected_uzs": total_expected,
        "total_collected_uzs": total_collected,
        "total_collected_pure_uzs": total_collected_uzs,
        "total_collected_pure_usd": total_collected_usd,
        "total_difference_uzs": total_diff,
        "match_count": match_count,
        "diff_count": diff_count,
        "unsubmitted_count": unsubmitted_count,
        "is_zero_discrepancy": is_zero_discrepancy,
        "status_text": "✅ 100% Zero Discrepancy (To'liq mos)" if is_zero_discrepancy else (
            f"⚠️ {diff_count} ta tafovut mavjud" if diff_count > 0 else (
                f"ℹ️ {unsubmitted_count} ta hisobot topshirilmagan" if unsubmitted_count > 0 else "✅ To'liq mos"
            )
        )
    }
