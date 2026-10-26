from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta
import aiosqlite
from app.config import DB_PATH
from app.models import (
    CreateUserRequest, UpdatePasswordRequest, SetDebtRequest, AppointCashierRequest
)
from app.dependencies import require_role
from app.security import hash_password

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_role(["ADMIN"]))])

@router.get("/users")
async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT id, telegram_id, full_name, role, debt_amount, is_active, created_at 
            FROM users 
            ORDER BY is_active DESC, role ASC, full_name ASC
        """)
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/employees")
async def get_admin_employees():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT id, telegram_id, full_name, role 
            FROM users 
            WHERE is_active = 1 AND role != 'ADMIN'
            ORDER BY full_name ASC
        """)
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/users/create")
async def create_user(req: CreateUserRequest, admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT id FROM users WHERE telegram_id = ?", (req.telegram_id,))
        if await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Telegram ID {req.telegram_id} ga ega foydalanuvchi allaqachon mavjud!"
            )

        # Standart boshlang'ich parol — foydalanuvchining o'z Telegram IDsi
        pwd_hash = hash_password(str(req.telegram_id))
        role = req.role if req.role in ["EMPLOYEE", "CASHIER", "ADMIN"] else "EMPLOYEE"

        cursor = await conn.execute("""
            INSERT INTO users (telegram_id, full_name, role, password_hash, debt_amount, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (req.telegram_id, req.full_name.strip(), role, pwd_hash, req.initial_debt))
        user_id = cursor.lastrowid

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('USER', ?, 'CREATE', ?, ?)
        """, (user_id, admin["full_name"], f"Yangi xodim qo'shildi: {req.full_name} (TG: {req.telegram_id})"))
        await conn.commit()

    return {
        "success": True,
        "message": f"Xodim {req.full_name} muvaffaqiyatli ro'yxatga olindi! Boshlang'ich login va parol: {req.telegram_id}"
    }

@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: int, admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi!")

        if user["role"] == "ADMIN" or user["id"] == admin["id"] or user["telegram_id"] == 8686341550:
            raise HTTPException(status_code=403, detail="Bosh Rahbar daxlsiz! Uni tizimdan hech kim bo'shata olmaydi va chiqara olmaydi!")

        new_status = 0 if user["is_active"] else 1
        status_name = "Faollashtirildi" if new_status else "Ishdan bo'shatildi"

        await conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('USER', ?, 'STATUS_CHANGE', ?, ?)
        """, (user_id, admin["full_name"], f"Xodim {user['full_name']} {status_name}"))
        await conn.commit()

    return {"success": True, "message": f"Xodim {user['full_name']} muvaffaqiyatli {status_name}!"}

@router.post("/users/{user_id}/debt")
async def assign_debt(user_id: int, req: SetDebtRequest, admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")

        # TT: "agar rahbar yangi qarz belgilasa mavjud qarzdorlikka qo'shib hisoblanib boriladi"
        added_amount = float(req.debt_amount)
        if added_amount <= 0:
            raise HTTPException(status_code=400, detail="Qarz summasi 0 dan katta bo'lishi shart!")

        reason_text = req.reason.strip() if req.reason else "Ko'rsatilmadi"
        new_total_debt = round(user["debt_amount"] + added_amount, 2)

        await conn.execute("UPDATE users SET debt_amount = ? WHERE id = ?", (new_total_debt, user_id))

        audit_details = (
            f"{user['full_name']}ga {added_amount:,.0f} so'm yangi qarz biriktirildi. "
            f"Sababi: {reason_text}. Yangi jami qarz: {new_total_debt:,.0f} so'm"
        )
        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('USER_DEBT', ?, 'ASSIGN', ?, ?)
        """, (user_id, admin["full_name"], audit_details))
        await conn.commit()

    return {
        "success": True,
        "message": f"Xodim {user['full_name']}ga {added_amount:,.0f} so'm qarz biriktirildi! Jami qarzdorlik: {new_total_debt:,.0f} so'm",
        "new_debt": new_total_debt
    }

@router.post("/users/{user_id}/password")
async def update_password(user_id: int, req: UpdatePasswordRequest, admin: dict = Depends(require_role(["ADMIN"]))):
    if len(req.new_password.strip()) < 3:
        raise HTTPException(status_code=400, detail="Parol kamida 3 ta belgidan iborat bo'lishi kerak!")

    pwd_hash = hash_password(req.new_password.strip())

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT full_name FROM users WHERE id = ?", (user_id,))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")

        await conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('USER_PASSWORD', ?, 'UPDATE', ?, ?)
        """, (user_id, admin["full_name"], f"{user['full_name']} paroli Rahbar tomonidan yangilandi"))
        await conn.commit()

    return {"success": True, "message": f"{user['full_name']} paroli muvaffaqiyatli yangilandi!"}

@router.post("/cashier/appoint")
async def appoint_cashier(req: AppointCashierRequest, admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE id = ?", (req.user_id,))
        target_user = await cursor.fetchone()
        if not target_user:
            raise HTTPException(status_code=404, detail="Tanlangan xodim topilmadi!")

        if target_user["role"] == "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bosh rahbar kassir yoki oddiy xodim bo'la olmaydi!"
            )

        if not target_user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ishdan bo'shatilgan xodimni kassir etib tayinlab bo'lmaydi!"
            )

        # 1. Hozirgi barcha kassirlarni aniqlash
        cursor = await conn.execute("SELECT * FROM users WHERE role = 'CASHIER'")
        previous_cashiers = await cursor.fetchall()

        # Oldingi kassirlarni audit va cashier_history ga DISMISSED sifatida yozish
        for prev in previous_cashiers:
            if prev["id"] != target_user["id"]:
                await conn.execute("""
                    INSERT INTO cashier_history (user_id, action, assigned_by_id)
                    VALUES (?, 'DISMISSED', ?)
                """, (prev["id"], admin["id"]))
                await conn.execute("""
                    INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
                    VALUES ('CASHIER', ?, 'DISMISS', ?, ?)
                """, (prev["id"], admin["full_name"], f"{prev['full_name']} yangi kassir ({target_user['full_name']}) tayinlangani sababli avtomatik oddiy xodim holatiga o'tkazildi"))

        # 2. Barcha eski kassirlarni qat'iy oddiy xodim (EMPLOYEE) holatiga o'tkazish
        await conn.execute("""
            UPDATE users SET role = 'EMPLOYEE' 
            WHERE role = 'CASHIER'
        """)

        # 3. Faqat yangi tanlangan xodimni CASHIER qilish (tizimda faqat 1 ta kassir)
        await conn.execute("""
            UPDATE users SET role = 'CASHIER' 
            WHERE id = ?
        """, (req.user_id,))

        # 4. Yangi tayinlovni tarixga va auditga yozish
        await conn.execute("""
            INSERT INTO cashier_history (user_id, action, assigned_by_id)
            VALUES (?, 'APPOINTED', ?)
        """, (req.user_id, admin["id"]))

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('CASHIER', ?, 'APPOINT', ?, ?)
        """, (req.user_id, admin["full_name"], f"{target_user['full_name']} yagona Kassir etib tayinlandi"))
        await conn.commit()

        prev_names = [p["full_name"] for p in previous_cashiers if p["id"] != target_user["id"]]
        prev_info = f" (Oldingi kassir {', '.join(prev_names)} avtomatik oddiy xodimga aylandi)" if prev_names else ""

    return {
        "success": True,
        "message": f"Kassir muvaffaqiyatli tayinlandi: {target_user['full_name']}!{prev_info}"
    }

@router.post("/cashier/dismiss")
async def dismiss_cashier(req: AppointCashierRequest, admin: dict = Depends(require_role(["ADMIN"]))):
    """Kassirni oddiy xodim roliga qaytarish"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE id = ?", (req.user_id,))
        target_user = await cursor.fetchone()
        if not target_user:
            raise HTTPException(status_code=404, detail="Tanlangan xodim topilmadi!")

        await conn.execute("UPDATE users SET role = 'EMPLOYEE' WHERE id = ?", (req.user_id,))
        await conn.execute("""
            INSERT INTO cashier_history (user_id, action, assigned_by_id)
            VALUES (?, 'DISMISSED', ?)
        """, (req.user_id, admin["id"]))

        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('CASHIER', ?, 'DISMISS', ?, ?)
        """, (req.user_id, admin["full_name"], f"{target_user['full_name']} kassirlikdan bo'shatilib oddiy xodim holatiga qaytarildi"))
        await conn.commit()

    return {
        "success": True,
        "message": f"{target_user['full_name']} oddiy xodim holatiga qaytarildi!"
    }

@router.get("/cashier/history")
async def get_cashier_history():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT ch.*, u.full_name as cashier_name, admin.full_name as admin_name
            FROM cashier_history ch
            JOIN users u ON ch.user_id = u.id
            JOIN users admin ON ch.assigned_by_id = admin.id
            ORDER BY ch.id DESC LIMIT 50
        """)
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/audit-logs")
async def get_audit_logs():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT * FROM audit_logs 
            ORDER BY id DESC LIMIT 100
        """)
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/analytics/monitoring")
async def get_sales_monitoring(period: str = "7d", admin: dict = Depends(require_role(["ADMIN"]))):
    """Faqat Rahbar uchun: Savdo monitoringi, vaqt bo'yicha dinamika (o'sish/pasayish)"""
    now_tashkent = datetime.utcnow() + timedelta(hours=5)
    today = now_tashkent.date()

    if period == "30d":
        days_count = 30
    elif period == "this_month":
        days_count = today.day
    elif period == "all":
        days_count = 90
    else: # "7d" default
        days_count = 7

    start_date = today - timedelta(days=days_count - 1)
    prev_end_date = start_date - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=days_count - 1)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")
    prev_start_str = prev_start_date.strftime("%Y-%m-%d")
    prev_end_str = prev_end_date.strftime("%Y-%m-%d")

    uzb_weekdays = {
        0: "Dush", 1: "Sesh", 2: "Chor", 3: "Pay", 4: "Juma", 5: "Shan", 6: "Yak"
    }
    uzb_months = {
        1: "Yan", 2: "Fev", 3: "Mar", 4: "Apr", 5: "May", 6: "Iyun",
        7: "Iyul", 8: "Avg", 9: "Sen", 10: "Okt", 11: "Noy", 12: "Dek"
    }

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Joriy davrdagi kunlik hisobotlar (tasdiqlangan)
        cur = await conn.execute("""
            SELECT report_date,
                   COALESCE(SUM(total_inflow), 0) as submitted_amount,
                   COALESCE(SUM(net_amount), 0) as net_amount,
                   COALESCE(SUM(sim_cards_count), 0) as sim_cards_sold
            FROM daily_reports
            WHERE status = 'APPROVED' AND report_date >= ? AND report_date <= ?
            GROUP BY report_date
        """, (start_str, end_str))
        rep_rows = await cur.fetchall()
        reports_by_date = {r["report_date"]: dict(r) for r in rep_rows}

        # 2. Joriy davrdagi karta to'ldirishlar (tasdiqlangan)
        cur = await conn.execute("""
            SELECT DATE(created_at, '+5 hours') as topup_date,
                   COALESCE(SUM(surcharge_amount), 0) as card_amount,
                   COUNT(*) as card_count
            FROM card_topups
            WHERE status = 'APPROVED' AND DATE(created_at, '+5 hours') >= ? AND DATE(created_at, '+5 hours') <= ?
            GROUP BY DATE(created_at, '+5 hours')
        """, (start_str, end_str))
        topup_rows = await cur.fetchall()
        topups_by_date = {r["topup_date"]: dict(r) for r in topup_rows}

        # 3. Oldingi davr yig'indilari (o'sish yoki pasayishni hisoblash uchun)
        cur = await conn.execute("""
            SELECT COALESCE(SUM(total_inflow), 0) as prev_submitted,
                   COALESCE(SUM(net_amount), 0) as prev_net,
                   COALESCE(SUM(sim_cards_count), 0) as prev_sims
            FROM daily_reports
            WHERE status = 'APPROVED' AND report_date >= ? AND report_date <= ?
        """, (prev_start_str, prev_end_str))
        prev_rep = await cur.fetchone()
        prev_submitted = prev_rep["prev_submitted"] if prev_rep else 0
        prev_net = prev_rep["prev_net"] if prev_rep else 0
        prev_sims = prev_rep["prev_sims"] if prev_rep else 0

        cur = await conn.execute("""
            SELECT COALESCE(SUM(surcharge_amount), 0) as prev_cards,
                   COUNT(*) as prev_card_count
            FROM card_topups
            WHERE status = 'APPROVED' AND DATE(created_at, '+5 hours') >= ? AND DATE(created_at, '+5 hours') <= ?
        """, (prev_start_str, prev_end_str))
        prev_top = await cur.fetchone()
        prev_cards = prev_top["prev_cards"] if prev_top else 0

        # 4. Operatorlar bo'yicha taqsimot
        cur = await conn.execute("""
            SELECT operator_type, COUNT(*) as count
            FROM sim_cards
            WHERE status = 'SOLD'
            GROUP BY operator_type
            ORDER BY count DESC
        """)
        op_rows = await cur.fetchall()
        operators = [dict(r) for r in op_rows]
        if not operators:
            cur = await conn.execute("""
                SELECT operator_type, COUNT(*) as count
                FROM sim_cards
                GROUP BY operator_type
                ORDER BY count DESC
            """)
            op_rows = await cur.fetchall()
            operators = [dict(r) for r in op_rows]

    # Timeline qurish (kunlik uzluksiz ketma-ketlik)
    timeline = []
    total_submitted = 0.0
    total_net = 0.0
    total_sims = 0
    total_cards = 0.0
    total_card_count = 0
    prev_day_sub = None

    for i in range(days_count):
        curr_d = start_date + timedelta(days=i)
        curr_d_str = curr_d.strftime("%Y-%m-%d")
        label = f"{curr_d.day}-{uzb_months.get(curr_d.month, '')}"
        w_name = uzb_weekdays.get(curr_d.weekday(), "")

        rep_info = reports_by_date.get(curr_d_str, {})
        top_info = topups_by_date.get(curr_d_str, {})

        sub_amt = float(rep_info.get("submitted_amount", 0.0))
        net_amt = float(rep_info.get("net_amount", 0.0))
        sims_cnt = int(rep_info.get("sim_cards_sold", 0))

        c_amt = float(top_info.get("card_amount", 0.0))
        c_cnt = int(top_info.get("card_count", 0))

        total_submitted += sub_amt
        total_net += net_amt
        total_sims += sims_cnt
        total_cards += c_amt
        total_card_count += c_cnt

        if prev_day_sub is not None and prev_day_sub > 0:
            day_change = round(((sub_amt - prev_day_sub) / prev_day_sub) * 100, 1)
        elif prev_day_sub is not None and sub_amt > 0:
            day_change = 100.0
        else:
            day_change = 0.0
        prev_day_sub = sub_amt

        timeline.append({
            "date": curr_d_str,
            "short_date": label,
            "weekday": w_name,
            "submitted_amount": sub_amt,
            "net_amount": net_amt,
            "sim_cards_sold": sims_cnt,
            "card_topup_amount": c_amt,
            "card_topup_count": c_cnt,
            "day_change_pct": day_change
        })

    def calc_pct(cur_val, prev_val):
        if prev_val > 0:
            return round(((cur_val - prev_val) / prev_val) * 100, 1)
        elif cur_val > 0:
            return 100.0
        return 0.0

    summary = {
        "total_submitted_amount": total_submitted,
        "submitted_growth_pct": calc_pct(total_submitted, prev_submitted),
        "total_net_amount": total_net,
        "net_growth_pct": calc_pct(total_net, prev_net),
        "total_sim_cards": total_sims,
        "sim_growth_pct": calc_pct(total_sims, prev_sims),
        "total_card_topup_amount": total_cards,
        "card_growth_pct": calc_pct(total_cards, prev_cards),
        "total_card_topup_count": total_card_count,
        "avg_daily_submitted": round(total_submitted / max(1, days_count)),
        "period": period,
        "days_count": days_count,
        "start_date": start_str,
        "end_date": end_str
    }

    return {
        "success": True,
        "data": {
            "summary": summary,
            "timeline": timeline,
            "operators": operators
        }
    }


@router.get("/retention/status")
async def get_data_retention_status(admin: dict = Depends(require_role(["ADMIN"]))):
    """90 kunlik ma'lumotlar saqlanish holati va statistikasi"""
    from app.retention import get_retention_stats
    return await get_retention_stats(retention_days=90)


@router.post("/retention/run-cleanup")
async def trigger_data_retention_cleanup(admin: dict = Depends(require_role(["ADMIN"]))):
    """90 kundan eski ma'lumotlarni qo'lda tozalashni ishga tushirish"""
    from app.retention import run_data_retention_cleanup
    res = await run_data_retention_cleanup(retention_days=90)
    return {
        "success": True,
        "message": f"90 kundan eski ma'lumotlar muvaffaqiyatli tozalandi. Jami {res['total_deleted']} ta yozuv o'chirildi.",
        "data": res
    }

