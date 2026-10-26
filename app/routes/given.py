import re
from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from app.config import DB_PATH
from app.models import GivenAmountCreate, StatusActionRequest
from app.dependencies import get_current_user, require_role

router = APIRouter(prefix="/api/given", tags=["Given Amount"])

def validate_comment(comment: str) -> str:
    cleaned = comment.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Izoh maydoni to'ldirilishi shart!")
    if len(cleaned) > 500:
        raise HTTPException(status_code=400, detail="Izoh 500 ta belgidan oshmasligi kerak!")
    return cleaned

@router.post("/submit")
async def submit_given_amount(req: GivenAmountCreate, user: dict = Depends(get_current_user)):
    if user.get("role") == "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Bosh Rahbar xodim emas! Berilgan summa so'rovini faqat xodimlar (operator va kassir) yubora oladi."
        )
    amount = float(req.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Summa musbat bo'lishi shart!")
    validated_comment = validate_comment(req.comment)

    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("""
            INSERT INTO given_amounts (employee_id, amount, comment, status)
            VALUES (?, ?, ?, 'PENDING')
        """, (user["id"], amount, validated_comment))
        given_id = cursor.lastrowid

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('GIVEN_AMOUNT', ?, 'CREATE', ?, ?)
        """, (given_id, user["full_name"], f"Berilgan summa: {amount:,} so'm, Izoh: {validated_comment}"))
        await conn.commit()

    return {
        "success": True,
        "message": "Berilgan summa so'rovi qabul qilindi va tasdiqlashga yuborildi!",
        "data": {
            "id": given_id,
            "amount": amount,
            "comment": validated_comment,
            "status": "PENDING"
        }
    }

@router.get("/my-history")
async def get_my_given_history(user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT * FROM given_amounts 
            WHERE employee_id = ? 
            ORDER BY id DESC LIMIT 50
        """, (user["id"],))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/all")
async def get_all_given_amounts(user: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT g.*, u.full_name as employee_name 
            FROM given_amounts g
            JOIN users u ON g.employee_id = u.id
            ORDER BY g.id DESC LIMIT 100
        """)
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/{given_id}/status")
async def update_given_status(
    given_id: int, 
    req: StatusActionRequest, 
    user: dict = Depends(require_role(["ADMIN"]))
):
    if req.status not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Status 'APPROVED' yoki 'REJECTED' bo'lishi shart!")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM given_amounts WHERE id = ?", (given_id,))
        record = await cursor.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="So'rov topilmadi!")

        status_label = "Tasdiqlandi" if req.status == "APPROVED" else "Rad etildi"
        await conn.execute("""
            UPDATE given_amounts 
            SET status = ?, approved_by_id = ? 
            WHERE id = ?
        """, (req.status, user["id"], given_id))

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('GIVEN_AMOUNT', ?, ?, ?, ?)
        """, (given_id, req.status, user["full_name"], f"Berilgan summa statusi {status_label} holatiga o'zgartirildi"))
        await conn.commit()

    return {"success": True, "message": f"So'rov muvaffaqiyatli {status_label} holatiga o'tkazildi!"}
