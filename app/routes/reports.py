import re
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
import aiosqlite
from app.config import DB_PATH
from app.models import DailyReportCreate, StatusActionRequest
from app.dependencies import get_current_user, require_role
from app.security import get_tashkent_today_str, get_tashkent_now
from app.bot import send_report_summary_to_telegram, send_report_status_to_telegram

logger = logging.getLogger("reports")

router = APIRouter(prefix="/api/reports", tags=["Reports"])

def validate_comment(comment: Optional[str]) -> str:
    if not comment:
        return ""
    cleaned = comment.strip()
    if len(cleaned) > 500:
        raise HTTPException(status_code=400, detail="Izoh 500 ta belgidan oshmasligi kerak!")
    return cleaned

@router.get("/today-prefill")
async def get_today_prefill(user: dict = Depends(get_current_user)):
    if user.get("role") == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bosh Rahbar xodim emas! Hisobot prefill faqat xodimlar uchun mavjud."
        )
    today_str = get_tashkent_today_str()

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Bugungi tasdiqlangan karta to'ldirish summalari (+3% ustama bilan)
        cursor = await conn.execute("""
            SELECT COALESCE(SUM(surcharge_amount), 0) FROM card_topups
            WHERE employee_id = ? AND status = 'APPROVED' 
            AND DATE(created_at, '+5 hours') = ?
        """, (user["id"], today_str))
        card_amount = (await cursor.fetchone())[0]

        # 2. Bugungi tasdiqlangan "Berilgan summa"
        cursor = await conn.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM given_amounts
            WHERE employee_id = ? AND status = 'APPROVED'
            AND DATE(created_at, '+5 hours') = ?
        """, (user["id"], today_str))
        given_amount = (await cursor.fetchone())[0]

        # 3. Foydalanuvchining hozirgi qarzdorligi (Rahbar belgilagan)
        cursor = await conn.execute("SELECT debt_amount FROM users WHERE id = ?", (user["id"],))
        debt_snapshot = (await cursor.fetchone())[0]

        # 4. Bugungi hisobot mavjudmi?
        cursor = await conn.execute("""
            SELECT * FROM daily_reports 
            WHERE employee_id = ? AND report_date = ?
        """, (user["id"], today_str))
        existing_report = await cursor.fetchone()

        return {
            "success": True,
            "today": today_str,
            "card_amount": card_amount,
            "given_amount": given_amount,
            "debt_snapshot": debt_snapshot,
            "existing_report": dict(existing_report) if existing_report else None
        }

@router.post("/submit")
async def submit_daily_report(req: DailyReportCreate, user: dict = Depends(get_current_user)):
    if user.get("role") == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bosh Rahbar xodim emas! Kunlik hisobotni faqat xodimlar (operator va kassir) topshira oladi."
        )
    today_str = get_tashkent_today_str()
    comment = validate_comment(req.comment)

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Avvalgi hisobotni tekshirish
        cursor = await conn.execute("""
            SELECT * FROM daily_reports 
            WHERE employee_id = ? AND report_date = ?
        """, (user["id"], today_str))
        existing = await cursor.fetchone()

        if existing and existing["status"] == "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bugungi hisobotingiz allaqachon Rahbar tomonidan tasdiqlangan va uni o'zgartirib bo'lmaydi!"
            )

        # Bugungi tasdiqlangan karta to'ldirish summasi
        cursor = await conn.execute("""
            SELECT COALESCE(SUM(surcharge_amount), 0) FROM card_topups
            WHERE employee_id = ? AND status = 'APPROVED' 
            AND DATE(created_at, '+5 hours') = ?
        """, (user["id"], today_str))
        card_amount = (await cursor.fetchone())[0]

        # Bugungi tasdiqlangan berilgan summa
        cursor = await conn.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM given_amounts
            WHERE employee_id = ? AND status = 'APPROVED'
            AND DATE(created_at, '+5 hours') = ?
        """, (user["id"], today_str))
        given_amount = (await cursor.fetchone())[0]

        # Hozirgi qarzdorlik
        cursor = await conn.execute("SELECT debt_amount FROM users WHERE id = ?", (user["id"],))
        debt_snapshot = (await cursor.fetchone())[0]

        if req.debt_paid > debt_snapshot:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Qarz uchun kiritilgan summa ({req.debt_paid:,.0f}) mavjud qarzdorlikdan ({debt_snapshot:,.0f}) ko'p bo'lishi mumkin emas!"
            )

        # Hisob-kitoblar:
        # Qarzdorlik kirimga qo'shilmaydi! Faqat qarz uchun to'lov kiritilsa kirimga qo'shiladi va qarzdorlikdan ayrilib boriladi.
        total_inflow = round(req.paynet + card_amount + req.leviy + req.debt_paid, 2)
        total_outflow = round(req.kunlik + req.terminal + given_amount + req.skidka + req.xarajat, 2)
        net_amount = round(total_inflow - total_outflow, 2)

        if existing:
            # Rollback & Overwrite: Eski kutilayotgan hisobot o'rniga yangisi toza bazaviy holatdan yangilanadi
            await conn.execute("""
                UPDATE daily_reports SET
                    paynet = ?, card_amount = ?, leviy = ?, debt_snapshot = ?,
                    debt_paid = ?, sim_cards_count = ?, kunlik = ?, terminal = ?,
                    given_amount = ?, skidka = ?, xarajat = ?, total_inflow = ?,
                    total_outflow = ?, net_amount = ?, comment = ?, status = 'PENDING',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                req.paynet, card_amount, req.leviy, debt_snapshot,
                req.debt_paid, req.sim_cards_count, req.kunlik, req.terminal,
                given_amount, req.skidka, req.xarajat, total_inflow,
                total_outflow, net_amount, comment, existing["id"]
            ))
            report_id = existing["id"]
            action_desc = "Qayta topshirildi (Eskisi yangilandi va qiymatlar qayta hisoblandi)"
        else:
            cursor = await conn.execute("""
                INSERT INTO daily_reports (
                    employee_id, report_date, paynet, card_amount, leviy,
                    debt_snapshot, debt_paid, sim_cards_count, kunlik, terminal,
                    given_amount, skidka, xarajat, total_inflow, total_outflow,
                    net_amount, comment, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """, (
                user["id"], today_str, req.paynet, card_amount, req.leviy,
                debt_snapshot, req.debt_paid, req.sim_cards_count, req.kunlik, req.terminal,
                given_amount, req.skidka, req.xarajat, total_inflow, total_outflow,
                net_amount, comment
            ))
            report_id = cursor.lastrowid
            action_desc = "Yangi topshirildi"

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('DAILY_REPORT', ?, 'SUBMIT', ?, ?)
        """, (report_id, user["full_name"], f"{action_desc}: Sana {today_str}, Umumiy summa: {net_amount:,} so'm"))
        await conn.commit()

    # Xodimning shaxsiy Telegramiga (lichkasiga) hisobot tafsilotlarini yuborish
    tg_id = user.get("telegram_id")
    if tg_id:
        submitted_at_str = get_tashkent_now().strftime("%d.%m.%Y %H:%M")
        report_summary = {
            "report_id": report_id,
            "employee_name": user["full_name"],
            "report_date": today_str,
            "submitted_at": submitted_at_str,
            "paynet": req.paynet,
            "card_amount": card_amount,
            "leviy": req.leviy,
            "debt_snapshot": debt_snapshot,
            "debt_paid": req.debt_paid,
            "sim_cards_count": req.sim_cards_count,
            "kunlik": req.kunlik,
            "terminal": req.terminal,
            "given_amount": given_amount,
            "skidka": req.skidka,
            "xarajat": req.xarajat,
            "total_inflow": total_inflow,
            "total_outflow": total_outflow,
            "net_amount": net_amount,
            "comment": comment
        }
        try:
            asyncio.create_task(send_report_summary_to_telegram(int(tg_id), report_summary))
        except Exception as e:
            logger.warning(f"Telegramga hisobot yuborishda task xatoligi: {e}")

    return {
        "success": True,
        "message": f"Kunlik hisobot muvaffaqiyatli topshirildi ({action_desc})!",
        "data": {
            "id": report_id,
            "report_date": today_str,
            "total_inflow": total_inflow,
            "total_outflow": total_outflow,
            "net_amount": net_amount,
            "status": "PENDING"
        }
    }

@router.get("/my-history")
async def get_my_reports(user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT * FROM daily_reports 
            WHERE employee_id = ? 
            ORDER BY report_date DESC LIMIT 30
        """, (user["id"],))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/all")
async def get_all_reports(
    date: Optional[str] = Query(None, description="Sana bo'yicha saralash (YYYY-MM-DD)"),
    start_date: Optional[str] = Query(None, description="Boshlanish sanasi (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Tugash sanasi (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Status bo'yicha saralash"),
    user: dict = Depends(require_role(["ADMIN"]))
):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        sql = """
            SELECT r.*, u.full_name as employee_name, u.telegram_id
            FROM daily_reports r
            JOIN users u ON r.employee_id = u.id
            WHERE 1=1
        """
        params = []
        if start_date and start_date.strip() and end_date and end_date.strip():
            sql += " AND r.report_date BETWEEN ? AND ?"
            params.extend([start_date.strip(), end_date.strip()])
        elif start_date and start_date.strip():
            sql += " AND r.report_date >= ?"
            params.append(start_date.strip())
        elif end_date and end_date.strip():
            sql += " AND r.report_date <= ?"
            params.append(end_date.strip())
        elif date and date.strip():
            sql += " AND r.report_date = ?"
            params.append(date.strip())

        if status and status.strip():
            sql += " AND r.status = ?"
            params.append(status.strip())

        sql += " ORDER BY r.report_date DESC, r.id DESC LIMIT 500"

        cursor = await conn.execute(sql, tuple(params))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/{report_id}/status")
async def update_report_status(
    report_id: int, 
    req: StatusActionRequest, 
    user: dict = Depends(require_role(["ADMIN"]))
):
    if req.status not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Status 'APPROVED' yoki 'REJECTED' bo'lishi shart!")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM daily_reports WHERE id = ?", (report_id,))
        report = await cursor.fetchone()
        if not report:
            raise HTTPException(status_code=404, detail="Hisobot topilmadi!")

        old_status = report["status"]
        emp_id = report["employee_id"]
        debt_paid = report["debt_paid"]
        sim_sold = report["sim_cards_count"]

        # Agar yangi tasdiqlanayotgan bo'lsa:
        if old_status != "APPROVED" and req.status == "APPROVED":
            # 1. Qarzdorlikni chegirish
            if debt_paid > 0:
                await conn.execute("""
                    UPDATE users 
                    SET debt_amount = MAX(0, debt_amount - ?)
                    WHERE id = ?
                """, (debt_paid, emp_id))

            # 2. Xodimning qo'lidagi sim-kartalaridan sim_sold donasini 'SOLD' (Sotilgan) holatiga o'tkazish
            if sim_sold > 0:
                await conn.execute("""
                    UPDATE sim_cards 
                    SET status = 'SOLD', sold_at = CURRENT_TIMESTAMP
                    WHERE id IN (
                        SELECT id FROM sim_cards 
                        WHERE employee_id = ? AND status = 'GIVEN'
                        ORDER BY id ASC
                        LIMIT ?
                    )
                """, (emp_id, sim_sold))

        # Agar oldin tasdiqlangan bo'lib, endi rad etilayotgan bo'lsa:
        elif old_status == "APPROVED" and req.status == "REJECTED":
            # 1. Qarzni qaytarish
            if debt_paid > 0:
                await conn.execute("""
                    UPDATE users 
                    SET debt_amount = debt_amount + ?
                    WHERE id = ?
                """, (debt_paid, emp_id))

            # 2. Sotilgan deb belgilangan sim-kartalarni yana 'GIVEN' holatiga qaytarish
            if sim_sold > 0:
                await conn.execute("""
                    UPDATE sim_cards 
                    SET status = 'GIVEN', sold_at = NULL
                    WHERE id IN (
                        SELECT id FROM sim_cards 
                        WHERE employee_id = ? AND status = 'SOLD'
                        ORDER BY id DESC
                        LIMIT ?
                    )
                """, (emp_id, sim_sold))

        status_label = "Tasdiqlandi" if req.status == "APPROVED" else "Rad etildi"
        await conn.execute("""
            UPDATE daily_reports 
            SET status = ?, reviewed_by = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (req.status, user["id"], report_id))

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('DAILY_REPORT', ?, ?, ?, ?)
        """, (report_id, req.status, user["full_name"], f"Hisobot statusi {status_label} holatiga o'zgartirildi"))

        # Xodimning telegram ID sini olish
        cursor = await conn.execute("SELECT telegram_id FROM users WHERE id = ?", (emp_id,))
        emp_user = await cursor.fetchone()
        emp_tg_id = emp_user[0] if emp_user else None

        await conn.commit()

    # Xodimning shaxsiy Telegramiga bildirishnoma yuborish
    if emp_tg_id:
        try:
            asyncio.create_task(send_report_status_to_telegram(
                int(emp_tg_id), 
                str(report["report_date"]), 
                req.status, 
                user["full_name"]
            ))
        except Exception as e:
            logger.warning(f"Hisobot statusini telegramga yuborishda task xatosi: {e}")

    return {"success": True, "message": f"Hisobot muvaffaqiyatli {status_label} holatiga o'tkazildi!"}
