from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from app.config import DB_PATH
from app.models import CashierHandoverCreate
from app.dependencies import get_current_user, require_role
from app.security import get_tashkent_today_str

router = APIRouter(prefix="/api/cashier", tags=["Cashier"])

@router.get("/employees")
async def get_active_employees(user: dict = Depends(require_role(["CASHIER", "ADMIN"]))):
    today_str = get_tashkent_today_str()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT id, telegram_id, full_name, role 
            FROM users 
            WHERE is_active = 1 AND role != 'ADMIN'
              AND id NOT IN (
                  SELECT employee_id FROM cashier_handovers 
                  WHERE handover_date = ?
              )
            ORDER BY full_name ASC
        """, (today_str,))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/handover")
async def record_handover(req: CashierHandoverCreate, user: dict = Depends(require_role(["CASHIER", "ADMIN"]))):
    import asyncio
    from app.bot import send_cashier_receipt_to_telegram
    from app.security import get_tashkent_now

    today_str = get_tashkent_today_str()

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

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

        total_amount = round(amount_uzs + (amount_usd * usd_rate), 2)
        if total_amount <= 0:
            raise HTTPException(status_code=400, detail="Qabul qilinayotgan summa 0 dan katta bo'lishi shart!")

        cursor = await conn.execute("SELECT full_name, telegram_id, role FROM users WHERE id = ?", (req.employee_id,))
        emp = await cursor.fetchone()
        if not emp:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")
        if emp["role"] == "ADMIN":
            raise HTTPException(status_code=400, detail="Rahbar xodim bo'la olmaydi va undan kassa qabul qilib bo'lmaydi!")

        # Bugun allaqachon topshirganini tekshirish
        cursor = await conn.execute(
            "SELECT id FROM cashier_handovers WHERE employee_id = ? AND handover_date = ?",
            (req.employee_id, today_str)
        )
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail=f"{emp['full_name']} bugungi kassa summasini allaqachon topshirgan!")

        cursor = await conn.execute("""
            INSERT INTO cashier_handovers (cashier_id, employee_id, handover_date, amount, amount_uzs, amount_usd, usd_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user["id"], req.employee_id, today_str, total_amount, amount_uzs, amount_usd, usd_rate))
        handover_id = cursor.lastrowid

        parts = []
        if amount_uzs > 0:
            parts.append(f"{amount_uzs:,.0f} so'm".replace(",", " "))
        if amount_usd > 0:
            parts.append(f"{amount_usd:,.0f} $ (kurs: {usd_rate:,.0f})".replace(",", " "))
        details_breakdown = " + ".join(parts) if parts else f"{total_amount:,.0f} so'm".replace(",", " ")

        log_text = f"Kassir {user['full_name']} xodim {emp['full_name']}dan kassa qabul qildi: {details_breakdown} (Jami ekvivalent: {total_amount:,.0f} so'm)".replace(",", " ")

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('CASHIER_HANDOVER', ?, 'RECORD', ?, ?)
        """, (handover_id, user["full_name"], log_text))
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

    return {
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

@router.get("/my-handovers")
async def get_my_handovers(user: dict = Depends(require_role(["CASHIER", "ADMIN"]))):
    today_str = get_tashkent_today_str()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT ch.*, u.full_name as employee_name, cash.full_name as cashier_name
            FROM cashier_handovers ch
            JOIN users u ON ch.employee_id = u.id
            JOIN users cash ON ch.cashier_id = cash.id
            WHERE ch.handover_date = ?
            ORDER BY ch.id DESC
        """, (today_str,))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/comparison")
async def get_comparison(date: str = None, user: dict = Depends(require_role(["ADMIN"]))):
    target_date = date or get_tashkent_today_str()

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
        SELECT 
            u.id as employee_id,
            u.full_name as employee_name,
            u.telegram_id,
            dr.id as report_id,
            COALESCE(dr.net_amount, 0) as report_amount,
            dr.status as report_status,
            COALESCE(ch_agg.total_cashier_amount, 0) as cashier_amount,
            COALESCE(ch_agg.total_amount_uzs, 0) as cashier_amount_uzs,
            COALESCE(ch_agg.total_amount_usd, 0) as cashier_amount_usd,
            ch_agg.cashier_names
        FROM users u
        LEFT JOIN daily_reports dr 
            ON dr.employee_id = u.id AND dr.report_date = ?
        LEFT JOIN (
            SELECT 
                employee_id, 
                SUM(amount) as total_cashier_amount,
                SUM(amount_uzs) as total_amount_uzs,
                SUM(amount_usd) as total_amount_usd,
                GROUP_CONCAT(DISTINCT cashier_user.full_name) as cashier_names
            FROM cashier_handovers ch
            JOIN users cashier_user ON ch.cashier_id = cashier_user.id
            WHERE ch.handover_date = ?
            GROUP BY employee_id
        ) ch_agg ON ch_agg.employee_id = u.id
        WHERE u.is_active = 1 AND u.role != 'ADMIN'
        ORDER BY u.full_name ASC
        """
        cursor = await conn.execute(query, (target_date, target_date))
        rows = await cursor.fetchall()

        results = []
        for r in rows:
            rep_amt = r["report_amount"]
            cash_amt = r["cashier_amount"]
            diff = cash_amt - rep_amt
            results.append({
                "employee_id": r["employee_id"],
                "employee_name": r["employee_name"],
                "telegram_id": r["telegram_id"],
                "report_id": r["report_id"],
                "report_amount": rep_amt,
                "report_status": r["report_status"] or "TOPSHIRILMAGAN",
                "cashier_amount": cash_amt,
                "cashier_amount_uzs": r["cashier_amount_uzs"],
                "cashier_amount_usd": r["cashier_amount_usd"],
                "cashier_names": r["cashier_names"] or "-",
                "difference": diff,
                "is_match": (rep_amt == cash_amt and r["report_status"] is not None)
            })

        return {"success": True, "date": target_date, "data": results}

@router.get("/all-handovers")
async def get_all_handovers(user: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT ch.*, u.full_name as employee_name, cash.full_name as cashier_name
            FROM cashier_handovers ch
            JOIN users u ON ch.employee_id = u.id
            JOIN users cash ON ch.cashier_id = cash.id
            ORDER BY ch.handover_date DESC, ch.id DESC LIMIT 100
        """)
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

