from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import aiosqlite
from app.config import DB_PATH
from app.dependencies import get_current_user, require_role

router = APIRouter(prefix="/api/settings", tags=["Settings"])

class UpdateUsdRateRequest(BaseModel):
    rate: float = Field(gt=0, description="Dollar kursi musbat son bo'lishi shart")

@router.get("/usd-rate")
async def get_usd_rate(user: dict = Depends(get_current_user)):
    """Dollar kursini olish (barcha xodimlar va rahbar uchun)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT value FROM system_settings WHERE key = 'usd_rate'")
        row = await cur.fetchone()
        rate = float(row["value"]) if row else 12000.0

        formatted_rate = f"{rate:,.0f}".replace(",", " ")

        return {
            "success": True,
            "rate": rate,
            "formatted": f"1$ = {formatted_rate} so'm"
        }

@router.post("/usd-rate")
async def update_usd_rate(
    payload: UpdateUsdRateRequest,
    admin: dict = Depends(require_role(["ADMIN"]))
):
    """Dollar kursini yangilash (faqat Bosh Rahbar uchun)"""
    new_rate = round(float(payload.rate), 2)
    formatted_rate = f"{new_rate:,.0f}".replace(",", " ")

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            INSERT INTO system_settings (key, value, updated_at)
            VALUES ('usd_rate', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """, (str(new_rate),))

        audit_details = f"Dollar kursi yangilandi: 1$ = {formatted_rate} so'm"
        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('SYSTEM', 1, 'UPDATE_USD_RATE', ?, ?)
        """, (admin["full_name"], audit_details))

        await conn.commit()

    return {
        "success": True,
        "message": f"Dollar kursi muvaffaqiyatli belgilandi: 1$ = {formatted_rate} so'm",
        "rate": new_rate,
        "formatted": f"1$ = {formatted_rate} so'm"
    }
