from fastapi import APIRouter, Depends
from app.database import get_db_connection
from app.dependencies import get_current_user
from app.services.rating_service import get_company_leaderboard

router = APIRouter(prefix="/api/rating", tags=["Rating"])

@router.get("/leaderboard")
async def get_leaderboard(period: str = "monthly", user: dict = Depends(get_current_user)):
    """
    Firma bo'yicha xodimlar reytingi va KPI ballari jadvali.
    Biznes mantiq Clean Architecture bo'yicha rating_service orqali boshqariladi.
    """
    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        data = await get_company_leaderboard(conn, comp_id, period)
        return {
            "success": True,
            "period": period,
            "data": data
        }
