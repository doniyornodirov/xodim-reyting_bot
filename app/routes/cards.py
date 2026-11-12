import re
import math
from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite
from app.config import DB_PATH
from app.database import get_db_connection, get_next_transaction_number
from app.models import CardTopupCreate, StatusActionRequest
from app.dependencies import get_current_user, require_role, require_active_shift
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
async def create_card_topup(req: CardTopupCreate, user: dict = Depends(require_active_shift)):
    if user.get("role") == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bosh Rahbar xodim emas! Karta to'ldirish so'rovini faqat xodimlar (operator va kassir) yubora oladi."
        )
    if user.get("shift_status") == "RESTING":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Siz hozirda dam olish (damda) rejimidasiz! Amallarni bajarish vaqtinchalik cheklangan. Ishga qaytish uchun Rahbarga murojaat qiling."
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

    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        # 1 kunda 2 va undan ortiq marta yuborilganini tekshirish (Toshkent vaqti +5 bo'yicha)
        clean_card = re.sub(r"\D", "", req.card_number)
        cursor = await conn.execute("""
            SELECT 
                COUNT(*),
                COALESCE(SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END), 0)
            FROM card_topups 
            WHERE REPLACE(card_number, ' ', '') = ? 
              AND company_id = ?
              AND (
                  DATE(created_at, '+5 hours') = DATE('now', '+5 hours')
                  OR DATE(created_at) = DATE('now', '+5 hours')
                  OR DATE(created_at) = DATE('now')
              )
        """, (clean_card, comp_id))
        row = await cursor.fetchone()
        repeat_count = row[0]
        approved_count = row[1]
        is_repeat_today = (repeat_count >= 1)
        has_approved_today = (approved_count >= 1)

        # Tartib raqamini hisoblash — 100% Atomik, hech qachon dublikat chiqarmaydi
        new_tx_number = await get_next_transaction_number(conn, comp_id)

        # Bazaga kiritish
        cursor = await conn.execute("""
            INSERT INTO card_topups (
                company_id, transaction_number, employee_id, card_number, card_holder, 
                amount, surcharge_amount, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
        """, (comp_id, new_tx_number, user["id"], formatted_card, validated_holder, amount, surcharge_amount))
        topup_id = cursor.lastrowid
        await conn.commit()

        # Audit log
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'CARD_TOPUP', ?, 'CREATE', ?, ?)
        """, (comp_id, topup_id, user["full_name"], f"Karta: {formatted_card}, Summa: {amount:,} so'm"))
        await conn.commit()

    # Telegram guruhga xabar yuborish (firma guruhiga yoki umumiy guruhga)
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
    msg_id = await notify_card_topup_in_group(topup_data, group_id=user.get("company_telegram_group_id"))
    if msg_id:
        async with get_db_connection() as conn:
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
    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        cursor = await conn.execute("""
            SELECT * FROM card_topups 
            WHERE employee_id = ? AND company_id = ?
            ORDER BY id DESC LIMIT 50
        """, (user["id"], comp_id))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/all")
async def get_all_card_topups(user: dict = Depends(require_role(["ADMIN"]))):
    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        cursor = await conn.execute("""
            SELECT c.*, u.full_name as employee_name 
            FROM card_topups c
            JOIN users u ON c.employee_id = u.id
            WHERE c.company_id = ?
            ORDER BY c.id DESC LIMIT 100
        """, (comp_id,))
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

    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM card_topups WHERE id = ? AND company_id = ?", (topup_id, comp_id))
        topup = await cursor.fetchone()
        if not topup:
            raise HTTPException(status_code=404, detail="So'rov topilmadi!")

        status_label = "Tasdiqlandi" if req.status == "APPROVED" else "Rad etildi"
        if topup["status"] == req.status:
            return {"success": True, "message": f"Ushbu so'rov allaqachon {status_label} holatida!"}

        await conn.execute("""
            UPDATE card_topups 
            SET status = ?, approved_by_name = ? 
            WHERE id = ? AND company_id = ?
        """, (req.status, user["full_name"], topup_id, comp_id))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'CARD_TOPUP', ?, ?, ?, ?)
        """, (comp_id, topup_id, req.status, user["full_name"], f"Web panel orqali status {status_label} holatiga o'zgartirildi"))
        await conn.commit()

    if topup["telegram_message_id"]:
        import asyncio
        from app.bot import update_group_card_topup_status
        asyncio.create_task(update_group_card_topup_status(
            message_id=topup["telegram_message_id"],
            topup_id=topup_id,
            new_status=req.status,
            actor_name=user["full_name"]
        ))

    return {"success": True, "message": f"Karta so'rovi muvaffaqiyatli {status_label} holatiga o'tkazildi!"}

@router.post("/{topup_id}/reject")
async def reject_card_topup(
    topup_id: int, 
    user: dict = Depends(get_current_user)
):
    """Xodim o'zi yuborgan karta to'ldirish so'rovini rad etishi (bekor qilishi)"""
    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM card_topups WHERE id = ? AND company_id = ?", (topup_id, comp_id))
        topup = await cursor.fetchone()
        if not topup:
            raise HTTPException(status_code=404, detail="So'rov topilmadi!")

        # Faqat o'z so'rovini yoki Bosh Rahbar rad eta oladi
        if user["role"] != "ADMIN" and topup["employee_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Siz faqat o'zingiz yuborgan karta so'rovini rad eta olasiz!")

        if topup["status"] == "REJECTED":
            raise HTTPException(status_code=400, detail="Ushbu so'rov allaqachon rad etilgan!")

        if topup["status"] == "APPROVED":
            raise HTTPException(status_code=400, detail="Tasdiqlangan karta so'rovini rad etib bo'lmaydi!")

        approved_label = f"Rad etildi (Xodim: {user['full_name']})"
        await conn.execute("""
            UPDATE card_topups 
            SET status = 'REJECTED', approved_by_name = ? 
            WHERE id = ? AND company_id = ?
        """, (approved_label, topup_id, comp_id))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'CARD_TOPUP', ?, 'REJECT', ?, ?)
        """, (comp_id, topup_id, user["full_name"], f"Xodim #{topup['transaction_number']} sonli karta so'rovini rad etdi"))
        await conn.commit()

    if topup["telegram_message_id"]:
        import asyncio
        from app.bot import update_group_card_topup_status
        asyncio.create_task(update_group_card_topup_status(
            message_id=topup["telegram_message_id"],
            topup_id=topup_id,
            new_status="REJECTED",
            actor_name=user["full_name"],
            reason_text="Xodim bekor qildi"
        ))

    return {
        "success": True, 
        "message": f"#{topup['transaction_number']} sonli karta so'rovi muvaffaqiyatli rad etildi!"
    }
