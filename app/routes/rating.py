from fastapi import APIRouter, Depends
import aiosqlite
from app.config import DB_PATH
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/rating", tags=["Rating"])

@router.get("/leaderboard")
async def get_leaderboard(period: str = "monthly", user: dict = Depends(get_current_user)):
    """
    Reyting hisoblash:
    - Berilgan va tasdiqlangan hisobot summasining har 1 000 000 so'miga = 1 ball
    - Har 1 dona sim kartaga = 1 ball
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        date_filter = ""
        if period == "monthly":
            date_filter = "AND strftime('%Y-%m', dr.report_date) = strftime('%Y-%m', 'now', '+5 hours')"

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
            ON dr.employee_id = u.id AND dr.status = 'APPROVED' {date_filter}
        WHERE u.is_active = 1 AND u.role != 'ADMIN'
        GROUP BY u.id
        """
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        leaderboard = []
        for r in rows:
            money_pts = round(r["total_sum"] / 1000000.0, 2)
            sim_pts = r["total_sim_cards"] * 1.0
            total_score = round(money_pts + sim_pts, 2)
            leaderboard.append({
                "employee_id": r["employee_id"],
                "employee_name": r["employee_name"],
                "role": r["role"],
                "total_sum": r["total_sum"],
                "total_sim_cards": r["total_sim_cards"],
                "reports_count": r["reports_count"],
                "money_points": money_pts,
                "sim_points": sim_pts,
                "total_score": total_score
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

        return {
            "success": True,
            "period": period,
            "data": leaderboard
        }
