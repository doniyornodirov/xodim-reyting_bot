"""
app.services.rating_service — KPI va Reyting Ballarini Hisoblash Servisi
Har 1 000 000 so'm uchun = 1 ball, har 1 dona sim-karta uchun = 1 ball.
"""

from typing import List, Dict, Any
import aiosqlite
from app.services.fintech_calc import to_decimal, round_uzs
from app.security import get_tashkent_now

def calculate_kpi_points(total_sum: float | int, total_sim_cards: int) -> Dict[str, float]:
    """KPI ballarini hisoblash: 1 mln so'm = 1 ball, 1 sim-karta = 1 ball"""
    d_sum = to_decimal(total_sum)
    money_points = float(round(float(d_sum) / 1000000.0, 2))
    sim_points = float(total_sim_cards) * 1.0
    total_score = float(round(money_points + sim_points, 2))
    return {
        "money_points": money_points,
        "sim_points": sim_points,
        "total_score": total_score
    }

async def get_company_leaderboard(
    conn: aiosqlite.Connection,
    company_id: int,
    period: str = "monthly"
) -> List[Dict[str, Any]]:
    """Firma bo'yicha saralangan xodimlar liderlar jadvali (Leaderboard)"""
    params = [company_id]
    date_filter = ""
    if period == "monthly":
        tashkent_now = get_tashkent_now()
        y = tashkent_now.year
        m = tashkent_now.month
        start_month = f"{y:04d}-{m:02d}-01"
        next_m = 1 if m == 12 else m + 1
        next_y = y + 1 if m == 12 else y
        end_month = f"{next_y:04d}-{next_m:02d}-01"
        date_filter = "AND dr.report_date >= ? AND dr.report_date < ?"
        params.extend([start_month, end_month])

    params.append(company_id)

    query = f"""
    SELECT 
        u.id as employee_id,
        u.full_name as employee_name,
        u.role,
        COALESCE(SUM(dr.net_amount), 0) as total_sum,
        COALESCE(SUM(dr.sim_cards_count), 0) as total_sim_cards,
        COUNT(dr.id) as reports_count
    FROM users u
    LEFT JOIN daily_reports dr 
        ON dr.employee_id = u.id AND dr.status = 'APPROVED' AND dr.company_id = ? {date_filter}
    WHERE u.is_active = 1 AND u.role NOT IN ('ADMIN', 'DEVELOPER') AND u.company_id = ?
    GROUP BY u.id
    """
    cursor = await conn.execute(query, tuple(params))
    rows = await cursor.fetchall()

    leaderboard = []
    for r in rows:
        pts = calculate_kpi_points(r["total_sum"], r["total_sim_cards"])
        leaderboard.append({
            "employee_id": r["employee_id"],
            "employee_name": r["employee_name"],
            "role": r["role"],
            "total_sum": round_uzs(r["total_sum"]),
            "total_sim_cards": r["total_sim_cards"],
            "reports_count": r["reports_count"],
            "money_points": pts["money_points"],
            "sim_points": pts["sim_points"],
            "total_score": pts["total_score"]
        })

    # Eng yuqori balldan kamayish tartibida saralash
    leaderboard.sort(key=lambda x: x["total_score"], reverse=True)

    # O'rinlarni belgilash (Rank)
    for idx, item in enumerate(leaderboard, 1):
        item["rank"] = idx
        if idx == 1:
            item["badge"] = "🥇 1-o'rin"
        elif idx == 2:
            item["badge"] = "🥈 2-o'rin"
        elif idx == 3:
            item["badge"] = "🥉 3-o'rin"
        else:
            item["badge"] = f"#{idx}"

    return leaderboard
