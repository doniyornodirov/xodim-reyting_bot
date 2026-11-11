import re
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
import aiosqlite
from app.config import DB_PATH
from app.models import DailyReportCreate, StatusActionRequest, SendExcelTelegramRequest
from app.dependencies import get_current_user, require_role, require_active_shift
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
async def submit_daily_report(req: DailyReportCreate, user: dict = Depends(require_active_shift)):
    if user.get("role") == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bosh Rahbar xodim emas! Kunlik hisobotni faqat xodimlar (operator va kassir) topshira oladi."
        )
    if user.get("shift_status") == "RESTING":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Siz hozirda dam olish (damda) rejimidasiz! Amallarni bajarish vaqtinchalik cheklangan. Ishga qaytish uchun Rahbarga murojaat qiling."
        )
    today_str = get_tashkent_today_str()
    comment = validate_comment(req.comment)
    comp_id = user.get("company_id") or 1

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Avvalgi hisobotni tekshirish
        cursor = await conn.execute("""
            SELECT * FROM daily_reports 
            WHERE employee_id = ? AND report_date = ? AND company_id = ?
        """, (user["id"], today_str, comp_id))
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
            AND company_id = ?
            AND DATE(created_at, '+5 hours') = ?
        """, (user["id"], comp_id, today_str))
        card_amount = (await cursor.fetchone())[0]

        # Bugungi tasdiqlangan berilgan summa
        cursor = await conn.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM given_amounts
            WHERE employee_id = ? AND status = 'APPROVED'
            AND company_id = ?
            AND DATE(created_at, '+5 hours') = ?
        """, (user["id"], comp_id, today_str))
        given_amount = (await cursor.fetchone())[0]

        # Hozirgi qarzdorlik
        cursor = await conn.execute("SELECT debt_amount FROM users WHERE id = ? AND company_id = ?", (user["id"], comp_id))
        debt_snapshot = (await cursor.fetchone())[0]

        if req.debt_paid > debt_snapshot:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Qarz uchun kiritilgan summa ({req.debt_paid:,.0f}) mavjud qarzdorlikdan ({debt_snapshot:,.0f}) ko'p bo'lishi mumkin emas!"
            )

        min_allowed = min(50000, debt_snapshot)
        if 0 < req.debt_paid < min_allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Qarz uchun to'lov eng kamida {min_allowed:,.0f} so'm bo'lishi kerak!"
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
                WHERE id = ? AND company_id = ?
            """, (
                req.paynet, card_amount, req.leviy, debt_snapshot,
                req.debt_paid, req.sim_cards_count, req.kunlik, req.terminal,
                given_amount, req.skidka, req.xarajat, total_inflow,
                total_outflow, net_amount, comment, existing["id"], comp_id
            ))
            report_id = existing["id"]
            action_desc = "Qayta topshirildi (Eskisi yangilandi va qiymatlar qayta hisoblandi)"
        else:
            cursor = await conn.execute("""
                INSERT INTO daily_reports (
                    company_id, employee_id, report_date, paynet, card_amount, leviy,
                    debt_snapshot, debt_paid, sim_cards_count, kunlik, terminal,
                    given_amount, skidka, xarajat, total_inflow, total_outflow,
                    net_amount, comment, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """, (
                comp_id, user["id"], today_str, req.paynet, card_amount, req.leviy,
                debt_snapshot, req.debt_paid, req.sim_cards_count, req.kunlik, req.terminal,
                given_amount, req.skidka, req.xarajat, total_inflow, total_outflow,
                net_amount, comment
            ))
            report_id = cursor.lastrowid
            action_desc = "Yangi topshirildi"

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'DAILY_REPORT', ?, 'SUBMIT', ?, ?)
        """, (comp_id, report_id, user["full_name"], f"{action_desc}: Sana {today_str}, Umumiy summa: {net_amount:,} so'm"))
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
    comp_id = user.get("company_id") or 1
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT * FROM daily_reports 
            WHERE employee_id = ? AND company_id = ?
            ORDER BY report_date DESC LIMIT 30
        """, (user["id"], comp_id))
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
    comp_id = user.get("company_id") or 1
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        sql = """
            SELECT r.*, u.full_name as employee_name, u.telegram_id
            FROM daily_reports r
            JOIN users u ON r.employee_id = u.id
            WHERE r.company_id = ?
        """
        params = [comp_id]
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

    comp_id = user.get("company_id") or 1
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM daily_reports WHERE id = ? AND company_id = ?", (report_id, comp_id))
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
                    WHERE id = ? AND company_id = ?
                """, (debt_paid, emp_id, comp_id))

            # 2. Xodimning qo'lidagi sim-kartalaridan sim_sold donasini 'SOLD' (Sotilgan) holatiga o'tkazish
            if sim_sold > 0:
                await conn.execute("""
                    UPDATE sim_cards 
                    SET status = 'SOLD', sold_at = CURRENT_TIMESTAMP
                    WHERE id IN (
                        SELECT id FROM sim_cards 
                        WHERE employee_id = ? AND status = 'GIVEN' AND company_id = ?
                        ORDER BY id ASC
                        LIMIT ?
                    )
                """, (emp_id, comp_id, sim_sold))

        # Agar oldin tasdiqlangan bo'lib, endi rad etilayotgan bo'lsa:
        elif old_status == "APPROVED" and req.status == "REJECTED":
            # 1. Qarzni qaytarish
            if debt_paid > 0:
                await conn.execute("""
                    UPDATE users 
                    SET debt_amount = debt_amount + ?
                    WHERE id = ? AND company_id = ?
                """, (debt_paid, emp_id, comp_id))

            # 2. Sotilgan deb belgilangan sim-kartalarni yana 'GIVEN' holatiga qaytarish
            if sim_sold > 0:
                await conn.execute("""
                    UPDATE sim_cards 
                    SET status = 'GIVEN', sold_at = NULL
                    WHERE id IN (
                        SELECT id FROM sim_cards 
                        WHERE employee_id = ? AND status = 'SOLD' AND company_id = ?
                        ORDER BY id DESC
                        LIMIT ?
                    )
                """, (emp_id, comp_id, sim_sold))

        status_label = "Tasdiqlandi" if req.status == "APPROVED" else "Rad etildi"
        await conn.execute("""
            UPDATE daily_reports 
            SET status = ?, reviewed_by = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND company_id = ?
        """, (req.status, user["id"], report_id, comp_id))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'DAILY_REPORT', ?, ?, ?, ?)
        """, (comp_id, report_id, req.status, user["full_name"], f"Hisobot statusi {status_label} holatiga o'zgartirildi"))

        # Xodimning telegram ID sini olish
        cursor = await conn.execute("SELECT telegram_id FROM users WHERE id = ? AND company_id = ?", (emp_id, comp_id))
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

@router.post("/send-daily-digest")
async def trigger_daily_digest(
    target_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(require_role(["ADMIN"]))
):
    """
    Firma Rahbari tomonidan bugungi yoki belgilangan sana/davr bo'yicha hisobot svodkasini
    o'zining shaxsiy Telegram lichkasiga (va agar sozlangan bo'lsa guruhga) yuborish
    """
    from app.bot import send_daily_digest_for_company
    comp_id = user.get("company_id") or 1
    caller_tg = user.get("telegram_id")
    res = await send_daily_digest_for_company(
        comp_id,
        target_date=target_date,
        end_date=end_date,
        send_to_owner=True,
        owner_override_tg=caller_tg
    )
    return res

@router.get("/export-excel")
async def export_reports_excel_endpoint(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    target_date: Optional[str] = None,
    date: Optional[str] = None,
    send_telegram: bool = True,
    user: dict = Depends(require_role(["ADMIN"]))
):
    """
    Belgilangan sana yoki sana oralig'i bo'yicha hisobotlarni professional Excel (.xlsx) fayliga
    eksport qilish, brauzerga yuklab berish VA rahbarning shaxsiy Telegram lichkasiga yuborish
    """
    from app.excel import generate_reports_excel
    from app.bot import send_document_to_telegram

    comp_id = user.get("company_id") or 1
    # Sanalarni normalizatsiya qilish
    s_date = (start_date or target_date or date or "").strip()
    e_date = (end_date or "").strip()

    if s_date and not e_date:
        e_date = s_date
    elif not s_date and e_date:
        s_date = e_date

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Kompaniya ma'lumotlari
        cur_c = await conn.execute("SELECT * FROM companies WHERE id = ?", (comp_id,))
        comp = await cur_c.fetchone()
        comp_name = comp["name"] if comp else "Kompaniya"
        owner_tg = user.get("telegram_id") or (comp["owner_telegram_id"] if comp else None)

        if s_date and e_date:
            cur_r = await conn.execute("""
                SELECT r.*, u.full_name as employee_name
                FROM daily_reports r
                JOIN users u ON r.employee_id = u.id
                WHERE r.company_id = ? AND r.report_date >= ? AND r.report_date <= ?
                ORDER BY r.report_date DESC, r.id DESC
            """, (comp_id, s_date, e_date))
            if s_date == e_date:
                try:
                    from datetime import datetime
                    d_fmt = datetime.strptime(s_date, "%Y-%m-%d").strftime("%d.%m.%Y")
                    date_display = d_fmt
                except Exception:
                    date_display = s_date
                filename = f"Hisobotlar_{s_date}.xlsx"
            else:
                try:
                    from datetime import datetime
                    d1 = datetime.strptime(s_date, "%Y-%m-%d").strftime("%d.%m.%Y")
                    d2 = datetime.strptime(e_date, "%Y-%m-%d").strftime("%d.%m.%Y")
                    date_display = f"{d1} — {d2}"
                except Exception:
                    date_display = f"{s_date} — {e_date}"
                filename = f"Hisobotlar_{s_date}_dan_{e_date}_gacha.xlsx"
        else:
            cur_r = await conn.execute("""
                SELECT r.*, u.full_name as employee_name
                FROM daily_reports r
                JOIN users u ON r.employee_id = u.id
                WHERE r.company_id = ?
                ORDER BY r.report_date DESC, r.id DESC
            """, (comp_id,))
            date_display = "Barcha sanalar"
            filename = f"Hisobotlar_Barcha_{get_tashkent_today_str()}.xlsx"

        reports_rows = await cur_r.fetchall()
        reports_list = [dict(r) for r in reports_rows]

    # Excel baytlarini generatsiya qilish
    excel_bytes = generate_reports_excel(comp_name, reports_list, date_display)

    # Rahbar shaxsiy Telegram lichkasiga hujjat sifatida yuborish
    if send_telegram and owner_tg:
        total_count = len(reports_list)
        total_net = sum((r.get("net_amount") or 0) for r in reports_list)
        total_sims = sum((r.get("sim_cards_count") or 0) for r in reports_list)
        total_net_fmt = f"{int(total_net):,}".replace(",", " ")

        caption = (
            f"📥 <b>KUNLIK HISOBOTLAR (EXCEL)</b>\n"
            f"🏢 <b>{comp_name}</b>\n"
            f"📅 <b>Sana / Davr:</b> {date_display}\n"
            f"👥 <b>Jami hisobotlar soni:</b> {total_count} ta\n"
            f"💰 <b>Jami sof kassa (Net):</b> <b>{total_net_fmt} so'm</b>\n"
            f"📱 <b>Sotilgan sim-kartalar:</b> {total_sims} dona\n\n"
            f"📎 <i>Belgilangan davr bo'yicha Excel (.xlsx) hisoboti biriktirildi.</i>"
        )
        try:
            asyncio.create_task(send_document_to_telegram(
                chat_id=int(owner_tg),
                file_bytes=excel_bytes,
                filename=filename,
                caption=caption
            ))
        except Exception as e:
            logger.warning(f"Excel faylini telegramga yuborishda task xatosi: {e}")

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@router.post("/send-excel-telegram")
async def send_excel_telegram_endpoint(
    req: SendExcelTelegramRequest,
    user: dict = Depends(require_role(["ADMIN"]))
):
    """
    Frontendda yaratilgan har qanday Excel faylini rahbarning shaxsiy Telegram lichkasiga yuborish
    """
    import base64
    from app.bot import send_document_to_telegram

    comp_id = user.get("company_id") or 1
    owner_tg = user.get("telegram_id")
    if not owner_tg:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT owner_telegram_id FROM companies WHERE id = ?", (comp_id,))
            c_row = await cur.fetchone()
            owner_tg = c_row["owner_telegram_id"] if c_row else None

    if not owner_tg:
        return {"success": False, "message": "Rahbar Telegram ID si topilmadi"}

    try:
        file_bytes = base64.b64decode(req.file_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Base64 dekodlashda xatolik: {e}")

    caption = req.caption or f"📥 <b>{req.filename}</b>\n\n📎 <i>Excel hisoboti biriktirildi.</i>"
    success = await send_document_to_telegram(
        chat_id=int(owner_tg),
        file_bytes=file_bytes,
        filename=req.filename,
        caption=caption
    )

    return {
        "success": success,
        "message": "Excel fayli shaxsiy Telegramingizga (@xodim_reyting_bot) yuborildi!" if success else "Telegramga yuborib bo'lmadi (Bot bilan chat boshlanmagan bo'lishi mumkin)."
    }
