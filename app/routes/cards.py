import re
import math
from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite
from app.config import DB_PATH
from app.models import CardTopupCreate, StatusActionRequest
from app.dependencies import get_current_user, require_role
from app.bot import notify_card_topup_in_group

router = APIRouter(prefix="/api/cards", tags=["Cards"])

def format_card_number(raw: str) -> str:
    cleaned = re.sub(r"\D", "", raw)
    if len(cleaned) != 16:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Karta raqami aynan 16 ta raqamdan iborat bo'lishi shart!"
        )
    return " ".join([cleaned[i:i+4] for i in range(0, 16, 4)])

def validate_card_holder(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Karta egasi maydoni to'ldirilishi majburiy!")
    if re.search(r"\d", cleaned):
        raise HTTPException(status_code=400, detail="Karta egasi ismida raqam qatnashishi mumkin emas!")
    return cleaned

@router.post("/topup")
async def create_card_topup(req: CardTopupCreate, user: dict = Depends(get_current_user)):
    if user.get("role") == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bosh Rahbar xodim emas! Karta to'ldirish so'rovini faqat xodimlar (operator va kassir) yubora oladi."
        )
    formatted_card = format_card_number(req.card_number)
    validated_holder = validate_card_holder(req.card_holder)
    amount = float(req.amount)
    if amount < 30000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Karta to'ldirish uchun eng kam summa: 30 000 so'm!"
        )

    # 3% ustamani 1000 so'mda yaxlitlash (masalan, 50 000 -> 52 000)
    surcharge_amount = float(math.ceil((amount * 1.03) / 1000.0) * 1000)

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1 kunda 2 va undan ortiq marta yuborilganini tekshirish (Toshkent vaqti +5 bo'yicha)
        clean_card = re.sub(r"\D", "", req.card_number)
        cursor = await conn.execute("""
            SELECT 
                COUNT(*),
                COALESCE(SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END), 0)
            FROM card_topups 
            WHERE REPLACE(card_number, ' ', '') = ? 
              AND (
                  DATE(created_at, '+5 hours') = DATE('now', '+5 hours')
                  OR DATE(created_at) = DATE('now', '+5 hours')
                  OR DATE(created_at) = DATE('now')
              )
        """, (clean_card,))
        row = await cursor.fetchone()
        repeat_count = row[0]
        approved_count = row[1]
        is_repeat_today = (repeat_count >= 1)
        has_approved_today = (approved_count >= 1)

        # Tartib raqamini hisoblash (#123)
        cursor = await conn.execute("SELECT MAX(transaction_number) FROM card_topups")
        max_num = (await cursor.fetchone())[0] or 100
        new_tx_number = max_num + 1

        # Bazaga kiritish
        cursor = await conn.execute("""
            INSERT INTO card_topups (
                transaction_number, employee_id, card_number, card_holder, 
                amount, surcharge_amount, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
        """, (new_tx_number, user["id"], formatted_card, validated_holder, amount, surcharge_amount))
        topup_id = cursor.lastrowid
        await conn.commit()

        # Audit log
        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('CARD_TOPUP', ?, 'CREATE', ?, ?)
        """, (topup_id, user["full_name"], f"Karta: {formatted_card}, Summa: {amount:,} so'm"))
        await conn.commit()

    # Telegram guruhga xabar yuborish
    topup_data = {
        "id": topup_id,
        "transaction_number": new_tx_number,
        "employee_name": user["full_name"],
        "card_number": formatted_card,
        "card_holder": validated_holder,
        "amount_formatted": f"{int(amount):,}".replace(",", " "),
        "surcharge_formatted": f"{int(surcharge_amount):,}".replace(",", " "),
        "is_repeat_today": is_repeat_today,
        "has_approved_today": has_approved_today
    }
    msg_id = await notify_card_topup_in_group(topup_data)
    if msg_id:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE card_topups SET telegram_message_id = ? WHERE id = ?",
                (msg_id, topup_id)
            )
            await conn.commit()

    repeat_msg = " ⚠️ Diqqat: Bu kartaga bugun to'lov qilindi!" if is_repeat_today else ""
    return {
        "success": True,
        "message": f"Karta to'ldirish so'rovi muvaffaqiyatli yuborildi!{repeat_msg}",
        "data": {
            "id": topup_id,
            "transaction_number": new_tx_number,
            "card_number": formatted_card,
            "card_holder": validated_holder,
            "amount": amount,
            "surcharge_amount": surcharge_amount,
            "status": "PENDING",
            "is_repeat_today": is_repeat_today,
            "has_approved_today": has_approved_today
        }
    }

@router.get("/my-history")
async def get_my_card_history(user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT * FROM card_topups 
            WHERE employee_id = ? 
            ORDER BY id DESC LIMIT 50
        """, (user["id"],))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/all")
async def get_all_card_topups(user: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT c.*, u.full_name as employee_name 
            FROM card_topups c
            JOIN users u ON c.employee_id = u.id
            ORDER BY c.id DESC LIMIT 100
        """)
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/{topup_id}/status")
async def update_topup_status(
    topup_id: int, 
    req: StatusActionRequest, 
    user: dict = Depends(require_role(["ADMIN"]))
):
    if req.status not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Status 'APPROVED' yoki 'REJECTED' bo'lishi shart!")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM card_topups WHERE id = ?", (topup_id,))
        topup = await cursor.fetchone()
        if not topup:
            raise HTTPException(status_code=404, detail="So'rov topilmadi!")

        status_label = "Tasdiqlandi" if req.status == "APPROVED" else "Rad etildi"
        await conn.execute("""
            UPDATE card_topups 
            SET status = ?, approved_by_name = ? 
            WHERE id = ?
        """, (req.status, user["full_name"], topup_id))

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('CARD_TOPUP', ?, ?, ?, ?)
        """, (topup_id, req.status, user["full_name"], f"Web panel orqali status {status_label} holatiga o'zgartirildi"))
        await conn.commit()

    return {"success": True, "message": f"Karta so'rovi muvaffaqiyatli {status_label} holatiga o'tkazildi!"}
