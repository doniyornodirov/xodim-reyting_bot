from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from app.config import DB_PATH
from app.database import get_db_connection
from app.models import CashierHandoverCreate
from app.dependencies import get_current_user, require_role
from app.security import get_tashkent_today_str
from app.services.fintech_calc import to_decimal, round_uzs
from app.services.idempotency import check_idempotency, record_idempotency_result
from app.services.cashier_service import calculate_daily_cashier_comparison, summarize_cashier_comparison

router = APIRouter(prefix="/api/cashier", tags=["Cashier"])

@router.get("/employees")
async def get_active_employees(user: dict = Depends(require_role(["CASHIER", "ADMIN"]))):
    today_str = get_tashkent_today_str()
    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        # Avto-tozalash: Agar xodimning bugungi hisoboti bekor qilingan (CANCELLED) bo'lsa,
        # unga tegishli cashier_handovers eski yozuvini tozalash (kassirga yangi hisobot bo'yicha yana ochish)
        await conn.execute("""
            DELETE FROM cashier_handovers 
            WHERE handover_date = ? AND company_id = ?
              AND employee_id IN (
                  SELECT employee_id FROM daily_reports 
                  WHERE report_date = ? AND company_id = ? AND status = 'CANCELLED'
              )
        """, (today_str, comp_id, today_str, comp_id))

        # Avto-tozalash: Agar xodim hisobotini qayta topshirgan bo'lsa (status = 'PENDING' va dr.updated_at > ch.created_at),
        # demak kassa eski hisobot bo'yicha qabul qilingan, uni ham tozalash:
        await conn.execute("""
            DELETE FROM cashier_handovers 
            WHERE handover_date = ? AND company_id = ?
              AND id IN (
                  SELECT ch.id FROM cashier_handovers ch
                  JOIN daily_reports dr 
                    ON dr.employee_id = ch.employee_id 
                   AND dr.report_date = ch.handover_date 
                   AND dr.company_id = ch.company_id
                  WHERE ch.handover_date = ? AND ch.company_id = ?
                    AND dr.status = 'PENDING'
                    AND dr.updated_at > ch.created_at
              )
        """, (today_str, comp_id, today_str, comp_id))
        await conn.commit()

        cursor = await conn.execute("""
            SELECT id, telegram_id, full_name, role 
            FROM users 
            WHERE is_active = 1 AND role NOT IN ('ADMIN', 'DEVELOPER') AND company_id = ?
              AND id NOT IN (
                  SELECT employee_id FROM cashier_handovers 
                  WHERE handover_date = ? AND company_id = ?
              )
            ORDER BY full_name ASC
        """, (comp_id, today_str, comp_id))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/handover")
async def record_handover(req: CashierHandoverCreate, user: dict = Depends(require_role(["CASHIER", "ADMIN"]))):
    if user.get("role") != "ADMIN" and user.get("shift_status") == "RESTING":
        raise HTTPException(
            status_code=403,
            detail="Siz hozirda dam olish (damda) rejimidasiz! Kassa amallarini bajarish vaqtinchalik cheklangan."
        )

    # Idempotentlik tekshiruvi (takroriy bosishdan himoya)
    is_new, cached_res = await check_idempotency(req.idempotency_key, user["id"], action="CASHIER_HANDOVER")
    if not is_new:
        return cached_res

    import asyncio
    from app.bot import send_cashier_receipt_to_telegram
    from app.security import get_tashkent_now

    today_str = get_tashkent_today_str()
    comp_id = user.get("company_id") or 1

    async with get_db_connection() as conn:
        # Tizimdagi joriy dollar kursini aniqlash
        cur = await conn.execute("SELECT value FROM system_settings WHERE key = 'usd_rate'")
        rate_row = await cur.fetchone()
        system_rate = float(rate_row["value"]) if rate_row else 12000.0
        # Dollar kursini kassir belgilamaydi, tizimdan avtomatik belgilanadi
        usd_rate = system_rate
        amount_uzs = float(req.amount_uzs)
        amount_usd = float(req.amount_usd)

        # Agar faqat umumiy amount yuborilgan bo'lsa (orqaga qarab moslik):
        if amount_uzs == 0 and amount_usd == 0 and req.amount > 0:
            amount_uzs = float(req.amount)

        # Decimal aniqligida ekvivalent summani yaxlitlash (Zero float drift)
        d_total = to_decimal(amount_uzs) + (to_decimal(amount_usd) * to_decimal(usd_rate))
        total_amount = float(round_uzs(d_total))
        if total_amount <= 0:
            raise HTTPException(status_code=400, detail="Qabul qilinayotgan summa 0 dan katta bo'lishi shart!")

        cursor = await conn.execute("SELECT full_name, telegram_id, role FROM users WHERE id = ? AND company_id = ?", (req.employee_id, comp_id))
        emp = await cursor.fetchone()
        if not emp:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")
        if emp["role"] == "ADMIN":
            raise HTTPException(status_code=400, detail="Rahbar xodim bo'la olmaydi va undan kassa qabul qilib bo'lmaydi!")

        # Bugun allaqachon topshirganini tekshirish
        cursor = await conn.execute(
            "SELECT id FROM cashier_handovers WHERE employee_id = ? AND handover_date = ? AND company_id = ?",
            (req.employee_id, today_str, comp_id)
        )
        existing_handover = await cursor.fetchone()
        if existing_handover:
            # Tekshirish: agar xodimning bugungi hisoboti CANCELLED yoki PENDING bo'lsa (qayta topshirilgan/ochilgan bo'lsa):
            cursor = await conn.execute(
                "SELECT status FROM daily_reports WHERE employee_id = ? AND report_date = ? AND company_id = ?",
                (req.employee_id, today_str, comp_id)
            )
            rep_row = await cursor.fetchone()
            if rep_row and rep_row["status"] in ("CANCELLED", "PENDING"):
                # Eskisini tozalab, yangi topshirilgan hisobot bo'yicha qabul qilishga ruxsat berish
                await conn.execute("DELETE FROM cashier_handovers WHERE id = ? AND company_id = ?", (existing_handover["id"], comp_id))
            else:
                raise HTTPException(status_code=400, detail=f"{emp['full_name']} bugungi kassa summasini allaqachon topshirgan!")

        try:
            cursor = await conn.execute("""
                INSERT INTO cashier_handovers (company_id, cashier_id, employee_id, handover_date, amount, amount_uzs, amount_usd, usd_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (comp_id, user["id"], req.employee_id, today_str, total_amount, amount_uzs, amount_usd, usd_rate))
            handover_id = cursor.lastrowid
        except Exception as e:
            err_msg = str(e).lower()
            if "unique" in err_msg or "duplicate key" in err_msg or "uq_cashier_handovers" in err_msg:
                raise HTTPException(status_code=400, detail=f"{emp['full_name']} bugungi kassa summasini allaqachon topshirgan!")
            raise e

        parts = []
        if amount_uzs > 0:
            parts.append(f"{amount_uzs:,.0f} so'm".replace(",", " "))
        if amount_usd > 0:
            parts.append(f"{amount_usd:,.0f} $ (kurs: {usd_rate:,.0f})".replace(",", " "))
        details_breakdown = " + ".join(parts) if parts else f"{total_amount:,.0f} so'm".replace(",", " ")

        log_text = f"Kassir {user['full_name']} xodim {emp['full_name']}dan kassa qabul qildi: {details_breakdown} (Jami ekvivalent: {total_amount:,.0f} so'm)".replace(",", " ")

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'CASHIER_HANDOVER', ?, 'RECORD', ?, ?)
        """, (comp_id, handover_id, user["full_name"], log_text))
        await conn.commit()

        # Telegram orqali xodimga rasmiy chek jo'natish
        if emp["telegram_id"]:
            tashkent_now_str = get_tashkent_now().strftime("%d.%m.%Y %H:%M")
            asyncio.create_task(send_cashier_receipt_to_telegram(
                employee_tg_id=emp["telegram_id"],
                receipt_data={
                    "employee_name": emp["full_name"],
                    "cashier_name": user["full_name"],
                    "amount_uzs": amount_uzs,
                    "amount_usd": amount_usd,
                    "usd_rate": usd_rate,
                    "total_amount": total_amount,
                    "date_time": tashkent_now_str
                }
            ))

    response_payload = {
        "success": True,
        "message": f"{emp['full_name']}dan kassa muvaffaqiyatli qabul qilindi va chek Telegram botdan jo'natildi!",
        "data": {
            "id": handover_id,
            "employee_id": req.employee_id,
            "employee_name": emp["full_name"],
            "amount": total_amount,
            "amount_uzs": amount_uzs,
            "amount_usd": amount_usd,
            "usd_rate": usd_rate,
            "handover_date": today_str
        }
    }
    await record_idempotency_result(req.idempotency_key, user["id"], response_payload, action="CASHIER_HANDOVER")
    return response_payload

@router.get("/my-handovers")
async def get_my_handovers(user: dict = Depends(require_role(["CASHIER", "ADMIN"]))):
    today_str = get_tashkent_today_str()
    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        cursor = await conn.execute("""
            SELECT ch.*, u.full_name as employee_name, cash.full_name as cashier_name
            FROM cashier_handovers ch
            JOIN users u ON ch.employee_id = u.id
            JOIN users cash ON ch.cashier_id = cash.id
            WHERE ch.handover_date = ? AND ch.company_id = ?
            ORDER BY ch.id DESC
        """, (today_str, comp_id))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/comparison")
async def get_comparison(
    date: str = None,
    start_date: str = None,
    end_date: str = None,
    user: dict = Depends(require_role(["ADMIN"]))
):
    import logging
    logger = logging.getLogger(__name__)

    try:
        from datetime import datetime
        s_date = None
        e_date = None

        if start_date and end_date:
            s_clean = start_date.strip()
            e_clean = end_date.strip()
            datetime.strptime(s_clean, "%Y-%m-%d")
            datetime.strptime(e_clean, "%Y-%m-%d")
            s_date = s_clean
            e_date = e_clean
        elif date and ("_" in date or ":" in date):
            delimiter = "_" if "_" in date else ":"
            parts = date.strip().split(delimiter)
            if len(parts) == 2:
                datetime.strptime(parts[0].strip(), "%Y-%m-%d")
                datetime.strptime(parts[1].strip(), "%Y-%m-%d")
                s_date = parts[0].strip()
                e_date = parts[1].strip()
        elif date:
            clean_date = date.strip()
            if clean_date.lower() not in ("undefined", "null", ""):
                datetime.strptime(clean_date, "%Y-%m-%d")
                s_date = clean_date
                e_date = clean_date

        if not s_date or not e_date:
            today_str = get_tashkent_today_str()
            s_date = today_str
            e_date = today_str

        if s_date > e_date:
            s_date, e_date = e_date, s_date

    except (ValueError, TypeError):
        today_str = get_tashkent_today_str()
        s_date = today_str
        e_date = today_str

    comp_id = user.get("company_id") or 1

    try:
        async with get_db_connection() as conn:
            results = await calculate_daily_cashier_comparison(conn, comp_id, s_date, e_date)
            summary = summarize_cashier_comparison(results)
            return {
                "success": True,
                "date": s_date if s_date == e_date else f"{s_date}_{e_date}",
                "start_date": s_date,
                "end_date": e_date,
                "is_range": (s_date != e_date),
                "summary": summary,
                "data": results
            }
    except Exception as e:
        logger.error(f"Kassa taqqoslashda xatolik ({s_date} -> {e_date}, comp_id={comp_id}): {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Kassa taqqoslash ma'lumotlarini yuklashda xatolik yuz berdi. Iltimos qayta urinib ko'ring."
        )

@router.get("/all-handovers")
async def get_all_handovers(user: dict = Depends(require_role(["ADMIN"]))):
    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        cursor = await conn.execute("""
            SELECT ch.*, u.full_name as employee_name, cash.full_name as cashier_name
            FROM cashier_handovers ch
            JOIN users u ON ch.employee_id = u.id
            JOIN users cash ON ch.cashier_id = cash.id
            WHERE ch.company_id = ?
            ORDER BY ch.handover_date DESC, ch.id DESC LIMIT 100
        """, (comp_id,))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

