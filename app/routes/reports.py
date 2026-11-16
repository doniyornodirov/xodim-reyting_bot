import re
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
import aiosqlite
from app.config import DB_PATH
from app.database import get_db_connection
from app.models import DailyReportCreate, StatusActionRequest, SendExcelTelegramRequest
from app.dependencies import get_current_user, require_role, require_active_shift
from app.security import get_tashkent_today_str, get_tashkent_now
from app.bot import send_report_summary_to_telegram, send_report_status_to_telegram
from app.services.fintech_calc import to_decimal, round_uzs
from app.services.idempotency import check_idempotency, record_idempotency_result
from app.services.report_service import get_employee_report_prefill
from app.services.analytics_service import invalidate_analytics_cache

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
    comp_id = user.get("company_id") or 1

    async with get_db_connection() as conn:
        return await get_employee_report_prefill(conn, comp_id, user["id"], today_str)

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

    # Idempotentlik tekshiruvi (takroriy bosishdan himoya)
    is_new, cached_res = await check_idempotency(req.idempotency_key, user["id"], action="DAILY_REPORT")
    if not is_new:
        return cached_res

    # Midnight Rollover himoyasi: agar soat 00:00 dan o'tgan bo'lsa ham xodim formani ochgan sanasini yo'qotmaydi
    target_date = get_tashkent_today_str()
    if req.report_date and req.report_date.strip():
        date_candidate = req.report_date.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_candidate):
            target_date = date_candidate

    today_str = target_date
    comment = validate_comment(req.comment)
    comp_id = user.get("company_id") or 1

    async with get_db_connection() as conn:
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

        # Hisob-kitoblar (Decimal aniqligida 0 tiyin xatosiz):
        # Qarzdorlik kirimga qo'shilmaydi! Faqat qarz uchun to'lov kiritilsa kirimga qo'shiladi va qarzdorlikdan ayrilib boriladi.
        d_inflow = to_decimal(req.paynet) + to_decimal(card_amount) + to_decimal(req.leviy) + to_decimal(req.debt_paid)
        d_outflow = to_decimal(req.kunlik) + to_decimal(req.terminal) + to_decimal(given_amount) + to_decimal(req.skidka) + to_decimal(req.xarajat)
        total_inflow = float(round_uzs(d_inflow))
        total_outflow = float(round_uzs(d_outflow))
        net_amount = float(round_uzs(d_inflow - d_outflow))

        # 5 ta operator bo'yicha sim-karta hisobi (100% sinxron va mutanosib)
        sim_uz = int(req.sim_uzmobile or 0)
        sim_bee = int(req.sim_beeline or 0)
        sim_uc = int(req.sim_ucell or 0)
        sim_mob = int(req.sim_mobiuz or 0)
        sim_perf = int(req.sim_perfectum or 0)
        total_op_sims = sim_uz + sim_bee + sim_uc + sim_mob + sim_perf

        legacy_sims = int(req.sim_cards_count or 0)
        if total_op_sims > 0:
            final_sims = total_op_sims
        elif legacy_sims > 0:
            final_sims = legacy_sims
            sim_uz = legacy_sims  # Operatorlar kiritilmagan bo'lsa, asosiy operator Uzmobile'ga biriktiriladi
        else:
            final_sims = 0

        if existing:
            # Rollback & Overwrite: Eski kutilayotgan hisobot o'rniga yangisi toza bazaviy holatdan yangilanadi
            await conn.execute("""
                UPDATE daily_reports SET
                    paynet = ?, card_amount = ?, leviy = ?, debt_snapshot = ?,
                    debt_paid = ?, sim_cards_count = ?, sim_uzmobile = ?, sim_beeline = ?,
                    sim_ucell = ?, sim_mobiuz = ?, sim_perfectum = ?, kunlik = ?, terminal = ?,
                    given_amount = ?, skidka = ?, xarajat = ?, total_inflow = ?,
                    total_outflow = ?, net_amount = ?, comment = ?, status = 'PENDING',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND company_id = ?
            """, (
                req.paynet, card_amount, req.leviy, debt_snapshot,
                req.debt_paid, final_sims, sim_uz, sim_bee,
                sim_uc, sim_mob, sim_perf, req.kunlik, req.terminal,
                given_amount, req.skidka, req.xarajat, total_inflow,
                total_outflow, net_amount, comment, existing["id"], comp_id
            ))
            report_id = existing["id"]
            action_desc = "Qayta topshirildi (Eskisi yangilandi va qiymatlar qayta hisoblandi)"

            # Agar oldingi topshirilgan hisobotga doir cashier_handovers yozuvi bo'lsa, uni tozalash
            # Shunda kassir yangi topshirilgan hisobot bo'yicha kassani qayta qabul qila oladi
            cursor = await conn.execute(
                "SELECT id, amount FROM cashier_handovers WHERE employee_id = ? AND handover_date = ? AND company_id = ?",
                (user["id"], today_str, comp_id)
            )
            old_handover = await cursor.fetchone()
            if old_handover:
                await conn.execute(
                    "DELETE FROM cashier_handovers WHERE id = ? AND company_id = ?",
                    (old_handover["id"], comp_id)
                )
                await conn.execute("""
                    INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
                    VALUES (?, 'CASHIER_HANDOVER', ?, 'RESET', ?, ?)
                """, (
                    comp_id, 
                    old_handover["id"], 
                    user["full_name"], 
                    f"Xodim hisobotini qayta topshirgani sababli oldingi kassa yozuvi ({old_handover['amount']:,.0f} so'm) yangilanish uchun tozalandi"
                ))
        else:
            try:
                cursor = await conn.execute("""
                    INSERT INTO daily_reports (
                        company_id, employee_id, report_date, paynet, card_amount, leviy,
                        debt_snapshot, debt_paid, sim_cards_count, sim_uzmobile, sim_beeline,
                        sim_ucell, sim_mobiuz, sim_perfectum, kunlik, terminal,
                        given_amount, skidka, xarajat, total_inflow, total_outflow,
                        net_amount, comment, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """, (
                    comp_id, user["id"], today_str, req.paynet, card_amount, req.leviy,
                    debt_snapshot, req.debt_paid, final_sims, sim_uz, sim_bee,
                    sim_uc, sim_mob, sim_perf, req.kunlik, req.terminal,
                    given_amount, req.skidka, req.xarajat, total_inflow, total_outflow,
                    net_amount, comment
                ))
                report_id = cursor.lastrowid
                action_desc = "Yangi topshirildi"
            except Exception as e:
                err_msg = str(e).lower()
                if "unique" in err_msg or "duplicate key" in err_msg or "uq_daily_reports" in err_msg:
                    raise HTTPException(status_code=400, detail="Bugungi hisobotingiz allaqachon topshirilgan!")
                raise e

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'DAILY_REPORT', ?, 'SUBMIT', ?, ?)
        """, (comp_id, report_id, user["full_name"], f"{action_desc}: Sana {today_str}, Umumiy summa: {net_amount:,} so'm"))
        await conn.commit()
        invalidate_analytics_cache(comp_id)

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
            "sim_cards_count": final_sims,
            "sim_uzmobile": sim_uz,
            "sim_beeline": sim_bee,
            "sim_ucell": sim_uc,
            "sim_mobiuz": sim_mob,
            "sim_perfectum": sim_perf,
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

    response_payload = {
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
    await record_idempotency_result(req.idempotency_key, user["id"], response_payload, action="DAILY_REPORT")
    return response_payload

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
        s_date = start_date.strip() if isinstance(start_date, str) and start_date.strip() else None
        e_date = end_date.strip() if isinstance(end_date, str) and end_date.strip() else None
        d_date = date.strip() if isinstance(date, str) and date.strip() else None
        st_val = status.strip() if isinstance(status, str) and status.strip() else None

        if s_date and e_date:
            sql += " AND r.report_date BETWEEN ? AND ?"
            params.extend([s_date, e_date])
        elif s_date:
            sql += " AND r.report_date >= ?"
            params.append(s_date)
        elif e_date:
            sql += " AND r.report_date <= ?"
            params.append(e_date)
        elif d_date:
            sql += " AND r.report_date = ?"
            params.append(d_date)

        if st_val and st_val != "all":
            if st_val == "REJECTED":
                sql += " AND (r.status = 'REJECTED' OR r.status = 'CANCELLED')"
            else:
                sql += " AND r.status = ?"
                params.append(st_val)

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
            op_sold_map = {
                "Uzmobile": int(report["sim_uzmobile"] or 0),
                "Beeline": int(report["sim_beeline"] or 0),
                "Ucell": int(report["sim_ucell"] or 0),
                "Mobiuz": int(report["sim_mobiuz"] or 0),
                "Perfectum": int(report["sim_perfectum"] or 0),
            }
            has_op_breakdown = any(c > 0 for c in op_sold_map.values())

            if has_op_breakdown:
                for op_name, count in op_sold_map.items():
                    if count > 0:
                        await conn.execute("""
                            UPDATE sim_cards 
                            SET status = 'SOLD', sold_at = CURRENT_TIMESTAMP
                            WHERE id IN (
                                SELECT id FROM sim_cards 
                                WHERE employee_id = ? AND status = 'GIVEN' AND company_id = ? AND operator_type = ?
                                ORDER BY id ASC
                                LIMIT ?
                            )
                        """, (emp_id, comp_id, op_name, count))
            elif sim_sold > 0:
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

            # 2. Sotilgan deb belgilangan sim-kartalarni yana 'GIVEN' holatiga qaytarish (Rollback)
            op_sold_map = {
                "Uzmobile": int(report["sim_uzmobile"] or 0),
                "Beeline": int(report["sim_beeline"] or 0),
                "Ucell": int(report["sim_ucell"] or 0),
                "Mobiuz": int(report["sim_mobiuz"] or 0),
                "Perfectum": int(report["sim_perfectum"] or 0),
            }
            has_op_breakdown = any(c > 0 for c in op_sold_map.values())

            if has_op_breakdown:
                for op_name, count in op_sold_map.items():
                    if count > 0:
                        await conn.execute("""
                            UPDATE sim_cards 
                            SET status = 'GIVEN', sold_at = NULL
                            WHERE id IN (
                                SELECT id FROM sim_cards 
                                WHERE employee_id = ? AND status = 'SOLD' AND company_id = ? AND operator_type = ?
                                ORDER BY id DESC
                                LIMIT ?
                            )
                        """, (emp_id, comp_id, op_name, count))
            elif sim_sold > 0:
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
        invalidate_analytics_cache(comp_id)

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

@router.post("/{report_id}/cancel")
async def cancel_daily_report(
    report_id: int,
    user: dict = Depends(require_role(["ADMIN"]))
):
    """
    Rahbar tomonidan xodimning hisobotini bekor qilish.
    Bu xodimga o'sha kun uchun hisobotni boshqatdan topshirish imkonini ochadi.
    Agar hisobot oldin tasdiqlangan bo'lsa, uning qarzdorlik va sim-karta yozuvlari
    avtomatik ravishda xavfsiz rollback qilinadi.
    """
    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM daily_reports WHERE id = ? AND company_id = ?",
            (report_id, comp_id)
        )
        report = await cursor.fetchone()
        if not report:
            raise HTTPException(status_code=404, detail="Hisobot topilmadi!")

        old_status = report["status"]
        emp_id = report["employee_id"]
        debt_paid = report["debt_paid"] or 0
        sim_sold = report["sim_cards_count"] or 0

        # Agar oldin tasdiqlangan bo'lsa - qarz va sim-kartalarni xavfsiz qaytarish (rollback)
        if old_status == "APPROVED":
            if debt_paid > 0:
                await conn.execute("""
                    UPDATE users 
                    SET debt_amount = debt_amount + ?
                    WHERE id = ? AND company_id = ?
                """, (debt_paid, emp_id, comp_id))

            op_sold_map = {
                "Uzmobile": int(report["sim_uzmobile"] or 0),
                "Beeline": int(report["sim_beeline"] or 0),
                "Ucell": int(report["sim_ucell"] or 0),
                "Mobiuz": int(report["sim_mobiuz"] or 0),
                "Perfectum": int(report["sim_perfectum"] or 0),
            }
            has_op_breakdown = any(c > 0 for c in op_sold_map.values())

            if has_op_breakdown:
                for op_name, count in op_sold_map.items():
                    if count > 0:
                        await conn.execute("""
                            UPDATE sim_cards 
                            SET status = 'GIVEN', sold_at = NULL
                            WHERE id IN (
                                SELECT id FROM sim_cards 
                                WHERE employee_id = ? AND status = 'SOLD' AND company_id = ? AND operator_type = ?
                                ORDER BY id DESC
                                LIMIT ?
                            )
                        """, (emp_id, comp_id, op_name, count))
            elif sim_sold > 0:
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

        # Statusni CANCELLED holatiga o'tkazish
        await conn.execute("""
            UPDATE daily_reports 
            SET status = 'CANCELLED', reviewed_by = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND company_id = ?
        """, (user["id"], report_id, comp_id))

        # Agar ushbu xodim uchun ushbu sanada kassa qabul qilingan bo'lsa (cashier_handovers),
        # hisobot bekor qilingani sababli uni ham tozalash (kassirga yangi hisobot bo'yicha qayta qabul qilish imkonini ochish)
        rep_date = str(report["report_date"])
        cursor = await conn.execute(
            "SELECT id, amount FROM cashier_handovers WHERE employee_id = ? AND handover_date = ? AND company_id = ?",
            (emp_id, rep_date, comp_id)
        )
        old_handover = await cursor.fetchone()
        if old_handover:
            await conn.execute(
                "DELETE FROM cashier_handovers WHERE id = ? AND company_id = ?",
                (old_handover["id"], comp_id)
            )
            await conn.execute("""
                INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
                VALUES (?, 'CASHIER_HANDOVER', ?, 'CANCEL', ?, ?)
            """, (
                comp_id, 
                old_handover["id"], 
                user["full_name"], 
                f"Hisobot bekor qilingani sababli oldingi kassa yozuvi ({old_handover['amount']:,.0f} so'm) bekor qilindi va kassirga qayta qabul qilish imkoni ochildi"
            ))

        # Audit log
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'DAILY_REPORT', ?, 'CANCEL', ?, ?)
        """, (comp_id, report_id, user["full_name"], "Hisobot bekor qilindi va xodimga boshqatdan topshirish uchun ochildi"))

        # Xodim ma'lumotini olish
        cursor = await conn.execute("SELECT telegram_id, full_name FROM users WHERE id = ? AND company_id = ?", (emp_id, comp_id))
        emp_user = await cursor.fetchone()
        emp_tg_id = emp_user["telegram_id"] if emp_user else None
        emp_name = emp_user["full_name"] if emp_user else "Xodim"

        await conn.commit()
        invalidate_analytics_cache(comp_id)

    # Xodimning shaxsiy Telegramiga bildirishnoma yuborish
    if emp_tg_id:
        try:
            asyncio.create_task(send_report_status_to_telegram(
                int(emp_tg_id), 
                str(report["report_date"]), 
                "CANCELLED", 
                user["full_name"]
            ))
        except Exception as e:
            logger.warning(f"Hisobot bekor qilinganini telegramga yuborishda xatolik: {e}")

    return {
        "success": True, 
        "message": f"{emp_name} xodimining hisoboti bekor qilindi va boshqatdan topshirish imkoniyati ochildi!"
    }

@router.post("/send-daily-digest")
async def trigger_daily_digest(
    target_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(require_role(["ADMIN"]))
):
    """
    Firma Rahbari tomonidan bugungi yoki belgilangan sana/davr bo'yicha hisobot svodkasini
    faqat o'zining shaxsiy Telegram lichkasiga yuborish (Telegram guruhlarga yuborilmaydi)
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
    status: Optional[str] = None,
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

        # Status bo'yicha saralash filtri (agar tanlangan bo'lsa)
        if status and status.strip() and status.strip() != "all":
            st = status.strip()
            if st == "REJECTED":
                reports_list = [r for r in reports_list if r.get("status") in ("REJECTED", "CANCELLED")]
            else:
                reports_list = [r for r in reports_list if r.get("status") == st]

    # Excel baytlarini generatsiya qilish (Event Loop ni bloklamaslik uchun alohida thread pool da bajariladi)
    excel_bytes = await asyncio.to_thread(generate_reports_excel, comp_name, reports_list, date_display)

    # FAQAT Rahbar shaxsiy Telegram lichkasiga hujjat sifatida yuborish (guruhlarga yuborish qat'iy taqiqlangan)
    if send_telegram and owner_tg:
        try:
            owner_int = int(owner_tg)
            if owner_int > 0:
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
                asyncio.create_task(send_document_to_telegram(
                    chat_id=owner_int,
                    file_bytes=excel_bytes,
                    filename=filename,
                    caption=caption
                ))
            else:
                logger.warning(f"Excel faylini guruhga ({owner_int}) yuborish rad etildi! Faqat rahbar shaxsiy lichkasiga ruxsat berilgan.")
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
    Frontendda yaratilgan har qanday Excel faylini FAQAT rahbarning shaxsiy Telegram lichkasiga yuborish (guruhlarga yuborilmaydi)
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
        owner_int = int(owner_tg)
        if owner_int <= 0:
            return {"success": False, "message": "Excel faylini guruhga yuborish taqiqlangan! Faqat rahbar shaxsiy lichkasiga yuboriladi."}
    except Exception:
        return {"success": False, "message": "Noto'g'ri Telegram ID formati"}

    try:
        file_bytes = base64.b64decode(req.file_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Base64 dekodlashda xatolik: {e}")

    caption = req.caption or f"📥 <b>{req.filename}</b>\n\n📎 <i>Excel hisoboti biriktirildi.</i>"
    success = await send_document_to_telegram(
        chat_id=owner_int,
        file_bytes=file_bytes,
        filename=req.filename,
        caption=caption
    )

    return {
        "success": success,
        "message": "Excel fayli rahbar shaxsiy Telegramingizga (@xodimkpi_bot) yuborildi!" if success else "Telegramga yuborib bo'lmadi (Bot bilan chat boshlanmagan bo'lishi mumkin)."
    }
