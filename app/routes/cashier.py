from typing import Optional
from datetime import datetime
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
async def get_active_employees(
    date: Optional[str] = None, 
    user: dict = Depends(require_role(["CASHIER", "ADMIN"]))
):
    target_date = get_tashkent_today_str()
    if date and date.strip():
        clean_date = date.strip()
        try:
            datetime.strptime(clean_date, "%Y-%m-%d")
            target_date = clean_date
        except ValueError:
            pass

    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        # Xodim damga chiqarilganda (shift_status = 'RESTING') kassirning ro'yxatida mutlaqo chiqmasligi shart
        # 1. Hali kassa topshirmagan faol xodimlar
        cursor = await conn.execute("""
            SELECT id, telegram_id, full_name, role 
            FROM users 
            WHERE is_active = 1 AND role NOT IN ('ADMIN', 'DEVELOPER') AND company_id = ?
              AND (shift_status IS NULL OR shift_status != 'RESTING')
              AND id NOT IN (
                  SELECT employee_id FROM cashier_handovers 
                  WHERE handover_date = ? AND company_id = ?
              )
            ORDER BY full_name ASC
        """, (comp_id, target_date, comp_id))
        rows = await cursor.fetchall()

        # 2. Ushbu sana uchun kassa allaqachon qabul qilingan xodimlar
        cursor_handed = await conn.execute("""
            SELECT u.id, u.telegram_id, u.full_name, u.role,
                   ch.id as handover_id, ch.amount, ch.amount_uzs, ch.amount_usd, ch.created_at as handed_at
            FROM cashier_handovers ch
            JOIN users u ON u.id = ch.employee_id
            WHERE ch.handover_date = ? AND ch.company_id = ?
            ORDER BY u.full_name ASC
        """, (target_date, comp_id))
        handed_rows = await cursor_handed.fetchall()

        return {
            "success": True, 
            "date": target_date, 
            "data": [dict(r) for r in rows],
            "already_handed_over": [dict(r) for r in handed_rows]
        }

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
    handover_date = today_str
    if req.handover_date and req.handover_date.strip():
        clean_d = req.handover_date.strip()
        try:
            datetime.strptime(clean_d, "%Y-%m-%d")
            handover_date = clean_d
        except ValueError:
            raise HTTPException(status_code=400, detail="Sana formati noto'g'ri (YYYY-MM-DD bo'lishi kerak)!")
        
        if handover_date > today_str:
            raise HTTPException(status_code=400, detail="Kelajakdagi sana uchun kassa qabul qilib bo'lmaydi!")

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

        if amount_uzs < 0 or amount_uzs > 1_000_000_000:
            raise HTTPException(status_code=400, detail="So'mda qabul qilingan summa 0 dan 1 000 000 000 so'mgacha bo'lishi shart!")
        if amount_usd < 0 or amount_usd > 1_000_000_000:
            raise HTTPException(status_code=400, detail="Dollarda qabul qilingan summa 0 dan 1 000 000 000 gacha bo'lishi shart!")

        # Decimal aniqligida ekvivalent summani yaxlitlash (Zero float drift)
        d_total = to_decimal(amount_uzs) + (to_decimal(amount_usd) * to_decimal(usd_rate))
        total_amount = float(round_uzs(d_total))
        if total_amount < 0 or total_amount > 1_000_000_000:
            raise HTTPException(status_code=400, detail="Umumiy summa 0 dan 1 000 000 000 so'mgacha bo'lishi shart!")

        cursor = await conn.execute("SELECT full_name, telegram_id, role, shift_status FROM users WHERE id = ? AND company_id = ?", (req.employee_id, comp_id))
        emp = await cursor.fetchone()
        if not emp:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")
        if emp["role"] == "ADMIN":
            raise HTTPException(status_code=400, detail="Rahbar xodim bo'la olmaydi va undan kassa qabul qilib bo'lmaydi!")

        # Agar xodim damda bo'lsa, undan kassa qabul qilish cheklangan
        if emp["shift_status"] == "RESTING":
            raise HTTPException(status_code=400, detail=f"{emp['full_name']} hozirda dam olish (damda) rejimida! Undan kassa qabul qilib bo'lmaydi.")

        # Belgilangan sana bo'yicha allaqachon topshirganini tekshirish (Kassir 1 kunga 1 marta qabul qila oladi)
        cursor = await conn.execute(
            "SELECT id FROM cashier_handovers WHERE employee_id = ? AND handover_date = ? AND company_id = ?",
            (req.employee_id, handover_date, comp_id)
        )
        existing_handover = await cursor.fetchone()
        if existing_handover:
            date_formatted = datetime.strptime(handover_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            raise HTTPException(
                status_code=400, 
                detail=f"Ushbu sana ({date_formatted}) uchun {emp['full_name']}dan kassa allaqachon qabul qilingan! Kassir bir kunga faqat 1 marta kassa qabul qila oladi."
            )

        try:
            cursor = await conn.execute("""
                INSERT INTO cashier_handovers (company_id, cashier_id, employee_id, handover_date, amount, amount_uzs, amount_usd, usd_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (comp_id, user["id"], req.employee_id, handover_date, total_amount, amount_uzs, amount_usd, usd_rate))
            handover_id = cursor.lastrowid
        except Exception as e:
            err_msg = str(e).lower()
            if "unique" in err_msg or "duplicate key" in err_msg or "uq_cashier_handovers" in err_msg:
                date_formatted = datetime.strptime(handover_date, "%Y-%m-%d").strftime("%d.%m.%Y")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Ushbu sana ({date_formatted}) uchun {emp['full_name']}dan kassa allaqachon qabul qilingan! Kassir bir kunga faqat 1 marta kassa qabul qila oladi."
                )
            raise e

        parts = []
        if amount_uzs > 0:
            parts.append(f"{amount_uzs:,.0f} so'm".replace(",", " "))
        if amount_usd > 0:
            parts.append(f"{amount_usd:,.0f} $ (kurs: {usd_rate:,.0f})".replace(",", " "))
        details_breakdown = " + ".join(parts) if parts else f"{total_amount:,.0f} so'm".replace(",", " ")

        date_formatted = datetime.strptime(handover_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        log_text = f"Kassir {user['full_name']} xodim {emp['full_name']}dan {date_formatted} sanasi uchun kassa qabul qildi: {details_breakdown} (Jami ekvivalent: {total_amount:,.0f} so'm)".replace(",", " ")

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
                    "handover_date": date_formatted,
                    "amount_uzs": amount_uzs,
                    "amount_usd": amount_usd,
                    "usd_rate": usd_rate,
                    "total_amount": total_amount,
                    "date_time": tashkent_now_str
                }
            ))

    response_payload = {
        "success": True,
        "message": f"{emp['full_name']}dan {date_formatted} sanasi uchun kassa muvaffaqiyatli qabul qilindi va chek Telegram botdan jo'natildi!",
        "data": {
            "id": handover_id,
            "employee_id": req.employee_id,
            "employee_name": emp["full_name"],
            "amount": total_amount,
            "amount_uzs": amount_uzs,
            "amount_usd": amount_usd,
            "usd_rate": usd_rate,
            "handover_date": handover_date
        }
    }
    await record_idempotency_result(req.idempotency_key, user["id"], response_payload, action="CASHIER_HANDOVER")
    return response_payload

@router.get("/my-handovers")
async def get_my_handovers(
    date: Optional[str] = None, 
    user: dict = Depends(require_role(["CASHIER", "ADMIN"]))
):
    today_str = get_tashkent_today_str()
    comp_id = user.get("company_id") or 1
    async with get_db_connection() as conn:
        # Barcha kassa qabul qilish tarixi (kunlik emas, to'liq doimiy yozib boriladigan tarix)
        if date and date.strip() and date.strip().lower() not in ("all", "null", "undefined"):
            clean_date = date.strip()
            cursor = await conn.execute("""
                SELECT ch.*, 
                       COALESCE(u.full_name, 'Noma''lum xodim') as employee_name, 
                       COALESCE(cash.full_name, 'Kassir') as cashier_name
                FROM cashier_handovers ch
                LEFT JOIN users u ON ch.employee_id = u.id
                LEFT JOIN users cash ON ch.cashier_id = cash.id
                WHERE ch.company_id = ? AND ch.handover_date = ?
                ORDER BY ch.id DESC
            """, (comp_id, clean_date))
        else:
            cursor = await conn.execute("""
                SELECT ch.*, 
                       COALESCE(u.full_name, 'Noma''lum xodim') as employee_name, 
                       COALESCE(cash.full_name, 'Kassir') as cashier_name
                FROM cashier_handovers ch
                LEFT JOIN users u ON ch.employee_id = u.id
                LEFT JOIN users cash ON ch.cashier_id = cash.id
                WHERE ch.company_id = ?
                ORDER BY ch.created_at DESC, ch.id DESC LIMIT 500
            """, (comp_id,))
        rows = await cursor.fetchall()
        rows_list = [dict(r) for r in rows]

        # Bugungi kun uchun alohida 1 kunlik yig'ilgan kassalar indikatori
        cur_today = await conn.execute("""
            SELECT 
                COALESCE(SUM(amount), 0) as total_amount,
                COALESCE(SUM(amount_uzs), 0) as total_uzs,
                COALESCE(SUM(amount_usd), 0) as total_usd,
                COUNT(*) as total_count
            FROM cashier_handovers
            WHERE company_id = ? AND handover_date = ?
        """, (comp_id, today_str))
        today_row = await cur_today.fetchone()

        # Barcha davr uchun jami yig'ilgan kassa
        cur_all = await conn.execute("""
            SELECT 
                COALESCE(SUM(amount), 0) as total_amount,
                COALESCE(SUM(amount_uzs), 0) as total_uzs,
                COALESCE(SUM(amount_usd), 0) as total_usd,
                COUNT(*) as total_count
            FROM cashier_handovers
            WHERE company_id = ?
        """, (comp_id,))
        all_row = await cur_all.fetchone()

        summary = {
            "today_total": float(today_row["total_amount"]) if today_row else 0.0,
            "today_uzs": float(today_row["total_uzs"]) if today_row else 0.0,
            "today_usd": float(today_row["total_usd"]) if today_row else 0.0,
            "today_count": int(today_row["total_count"]) if today_row else 0,
            "today_date": today_str,
            "all_total": float(all_row["total_amount"]) if all_row else 0.0,
            "all_uzs": float(all_row["total_uzs"]) if all_row else 0.0,
            "all_usd": float(all_row["total_usd"]) if all_row else 0.0,
            "all_count": int(all_row["total_count"]) if all_row else 0
        }

        return {
            "success": True, 
            "summary": summary, 
            "data": rows_list
        }

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
            ORDER BY ch.created_at DESC, ch.id DESC LIMIT 500
        """, (comp_id,))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

