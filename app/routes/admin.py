import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from datetime import datetime, timedelta, timezone
import aiosqlite
from app.config import DB_PATH
from app.models import (
    CreateUserRequest, UpdatePasswordRequest, SetDebtRequest, AppointCashierRequest, ToggleShiftRequest
)
from app.dependencies import require_role, get_current_user, invalidate_user_cache
from app.security import hash_password
from app.services.analytics_service import get_sales_monitoring_data

logger = logging.getLogger("admin_routes")

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_role(["ADMIN"]))])

@router.get("/users")
async def get_all_users(admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        comp_id = admin.get("company_id") or 1
        cursor = await conn.execute("""
            SELECT id, telegram_id, full_name, role, debt_amount, is_active, created_at,
                   last_latitude, last_longitude, last_distance_meters, last_location_updated_at,
                   shift_status, work_start_time, work_end_time, company_id,
                   bound_device_name, device_bound_at, allow_device_reset
            FROM users 
            WHERE company_id = ? AND role != 'DEVELOPER'
            ORDER BY is_active DESC, role ASC, full_name ASC
        """, (comp_id,))
        rows = await cursor.fetchall()
        users_data = []
        for r in rows:
            u_dict = dict(r)
            bname = (u_dict.get("bound_device_name") or "").strip()
            if bname and (bname.upper() == "K" or len(bname) <= 1):
                u_dict["bound_device_name"] = "Android telefon"
            users_data.append(u_dict)
        return {"success": True, "data": users_data}

@router.get("/employees")
async def get_admin_employees(admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        comp_id = admin.get("company_id") or 1
        cursor = await conn.execute("""
            SELECT id, telegram_id, full_name, role, company_id 
            FROM users 
            WHERE is_active = 1 AND role NOT IN ('ADMIN', 'DEVELOPER') AND company_id = ?
            ORDER BY full_name ASC
        """, (comp_id,))
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
        comp_id = admin.get("company_id") or 1

        # Kompaniyaning xodimlar limiti tekshiruvi (SaaS Tiered Monetization)
        cur_comp = await conn.execute("SELECT max_employees, owner_telegram_id FROM companies WHERE id = ?", (comp_id,))
        comp_info = await cur_comp.fetchone()
        max_emp = comp_info["max_employees"] if (comp_info and "max_employees" in comp_info.keys() and comp_info["max_employees"]) else 20
        comp_owner_tg = comp_info["owner_telegram_id"] if comp_info else None

        if comp_owner_tg:
            cur_cnt = await conn.execute(
                """
                SELECT COUNT(*) FROM users 
                WHERE company_id = ? 
                  AND is_active = 1 
                  AND UPPER(COALESCE(role, '')) NOT IN ('ADMIN', 'DEVELOPER', 'SUPERADMIN')
                  AND telegram_id != ?
                """,
                (comp_id, comp_owner_tg)
            )
        else:
            cur_cnt = await conn.execute(
                """
                SELECT COUNT(*) FROM users 
                WHERE company_id = ? 
                  AND is_active = 1 
                  AND UPPER(COALESCE(role, '')) NOT IN ('ADMIN', 'DEVELOPER', 'SUPERADMIN')
                """,
                (comp_id,)
            )
        curr_emp_count = (await cur_cnt.fetchone())[0]

        if role not in ('ADMIN', 'DEVELOPER') and curr_emp_count >= max_emp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Kompaniyangiz tarifidagi faol xodimlar limiti ({max_emp} ta) to'ldi! Yangi xodim qo'shish uchun tarifni oshiring yoki Dasturchi Admin bilan bog'laning."
            )

        cursor = await conn.execute("""
            INSERT INTO users (company_id, telegram_id, full_name, role, password_hash, debt_amount, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (comp_id, req.telegram_id, req.full_name.strip(), role, pwd_hash, req.initial_debt))
        user_id = cursor.lastrowid

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'USER', ?, 'CREATE', ?, ?)
        """, (comp_id, user_id, admin["full_name"], f"Yangi xodim qo'shildi: {req.full_name} (TG: {req.telegram_id})"))
        await conn.commit()
        invalidate_user_cache(user_id)

    return {
        "success": True,
        "message": f"Xodim {req.full_name} muvaffaqiyatli ro'yxatga olindi! Boshlang'ich login va parol: {req.telegram_id}",
        "data": {
            "id": user_id,
            "telegram_id": req.telegram_id,
            "full_name": req.full_name,
            "role": role,
            "company_id": comp_id
        }
    }

@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: int, admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        comp_id = admin.get("company_id") or 1
        cursor = await conn.execute("SELECT * FROM users WHERE id = ? AND company_id = ?", (user_id, comp_id))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi!")

        if user["role"] == "ADMIN" or user["id"] == admin["id"] or user["telegram_id"] == 8686341550:
            raise HTTPException(status_code=403, detail="Bosh Rahbar daxlsiz! Uni tizimdan hech kim bo'shata olmaydi va chiqara olmaydi!")

        new_status = 0 if user["is_active"] else 1
        status_name = "Faollashtirildi" if new_status else "Ishdan bo'shatildi"

        if new_status == 1:
            cur_comp = await conn.execute("SELECT max_employees, owner_telegram_id FROM companies WHERE id = ?", (comp_id,))
            comp_info = await cur_comp.fetchone()
            max_emp = comp_info["max_employees"] if (comp_info and "max_employees" in comp_info.keys() and comp_info["max_employees"]) else 20
            comp_owner_tg = comp_info["owner_telegram_id"] if comp_info else None

            if comp_owner_tg:
                cur_cnt = await conn.execute(
                    """
                    SELECT COUNT(*) FROM users 
                    WHERE company_id = ? 
                      AND is_active = 1 
                      AND UPPER(COALESCE(role, '')) NOT IN ('ADMIN', 'DEVELOPER', 'SUPERADMIN')
                      AND telegram_id != ?
                    """,
                    (comp_id, comp_owner_tg)
                )
            else:
                cur_cnt = await conn.execute(
                    """
                    SELECT COUNT(*) FROM users 
                    WHERE company_id = ? 
                      AND is_active = 1 
                      AND UPPER(COALESCE(role, '')) NOT IN ('ADMIN', 'DEVELOPER', 'SUPERADMIN')
                    """,
                    (comp_id,)
                )
            curr_emp_count = (await cur_cnt.fetchone())[0]

            if user["role"] not in ('ADMIN', 'DEVELOPER') and curr_emp_count >= max_emp:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Kompaniyangiz tarifidagi faol xodimlar limiti ({max_emp} ta) to'ldi! Xodimni qayta faollashtirish uchun tarifni oshiring yoki boshqa xodimlarni boshqaring."
                )

        await conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'USER', ?, 'STATUS_CHANGE', ?, ?)
        """, (comp_id, user_id, admin["full_name"], f"Xodim {user['full_name']} {status_name}"))
        await conn.commit()
        invalidate_user_cache(user_id)

    return {"success": True, "message": f"Xodim {user['full_name']} muvaffaqiyatli {status_name}!"}

@router.delete("/users/{user_id}")
@router.post("/users/{user_id}/delete")
async def delete_user(user_id: int, admin: dict = Depends(require_role(["ADMIN"]))):
    """
    Xodimni firmadan butunlay o'chirish (Hard Delete).
    Bosh Rahbar daxlsiz bo'lib, xodim o'chirilganda uning barcha bog'liq yozuvlari
    tozalanadi va u firmadan butunlay chiqib ketadi.
    """
    comp_id = admin.get("company_id") or 1
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE id = ? AND company_id = ?", (user_id, comp_id))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi!")

        if user["role"] in ("ADMIN", "DEVELOPER") or user["id"] == admin["id"] or user["telegram_id"] == 8686341550:
            raise HTTPException(
                status_code=403, 
                detail="Bosh Rahbar daxlsiz! Uni tizimdan hech kim o'chira olmaydi!"
            )

        # Xodimning tegishli yozuvlarini tozalash
        await conn.execute("DELETE FROM sim_cards WHERE employee_id = ? AND company_id = ?", (user_id, comp_id))
        await conn.execute("DELETE FROM sim_distributions WHERE employee_id = ? AND company_id = ?", (user_id, comp_id))
        await conn.execute("DELETE FROM location_events WHERE user_id = ? AND company_id = ?", (user_id, comp_id))
        await conn.execute("DELETE FROM otp_codes WHERE telegram_id = ?", (user["telegram_id"],))
        await conn.execute("DELETE FROM cashier_history WHERE user_id = ? OR assigned_by_id = ?", (user_id, user_id))
        await conn.execute("DELETE FROM cashier_handovers WHERE (employee_id = ? OR cashier_id = ?) AND company_id = ?", (user_id, user_id, comp_id))
        await conn.execute("DELETE FROM daily_reports WHERE employee_id = ? AND company_id = ?", (user_id, comp_id))
        await conn.execute("DELETE FROM card_topups WHERE employee_id = ? AND company_id = ?", (user_id, comp_id))
        await conn.execute("DELETE FROM given_amounts WHERE employee_id = ? AND company_id = ?", (user_id, comp_id))
        
        # Foydalanuvchini bazadan butunlay o'chirish
        await conn.execute("DELETE FROM users WHERE id = ? AND company_id = ?", (user_id, comp_id))

        # Audit log yozish
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'USER', ?, 'DELETE', ?, ?)
        """, (comp_id, user_id, admin["full_name"], f"Xodim '{user['full_name']}' (ID: {user_id}, TG: {user['telegram_id']}) firmadan butunlay o'chirildi."))

        await conn.commit()
        invalidate_user_cache(user_id)

    return {
        "success": True,
        "message": f"Xodim '{user['full_name']}' firmadan butunlay o'chirildi!"
    }

@router.post("/users/{user_id}/reset-device")
async def reset_user_device(
    user_id: int,
    admin: dict = Depends(require_role(["ADMIN"]))
):
    """
    Rahbar tomonidan xodimga yangi telefon apparatini biriktirishga ruxsat berish
    (masalan, xodim telefonini almashtirganida yoki yo'qotganida).
    """
    comp_id = admin.get("company_id") or 1
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE id = ? AND company_id = ?", (user_id, comp_id))
        target_user = await cur.fetchone()
        if not target_user:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")

        await conn.execute("""
            UPDATE users 
            SET allow_device_reset = 1,
                bound_device_token = NULL
            WHERE id = ?
        """, (user_id,))

        details = f"Rahbar '{admin['full_name']}' xodim '{target_user['full_name']}' ga yangi telefon apparatini biriktirishga ruxsat berdi."
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'DEVICE', ?, 'RESET_DEVICE_PERM', ?, ?)
        """, (comp_id, user_id, admin["full_name"], details))
        await conn.commit()
        invalidate_user_cache(user_id)

    return {
        "success": True,
        "message": f"'{target_user['full_name']}' uchun yangi telefon apparatini biriktirishga ruxsat berildi! Endi xodim yangi telefonidan kirishi mumkin."
    }

@router.post("/users/{user_id}/toggle-shift")
async def toggle_employee_shift(
    user_id: int, 
    req: Optional[ToggleShiftRequest] = None, 
    admin: dict = Depends(require_role(["ADMIN"]))
):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        comp_id = admin.get("company_id") or 1
        cursor = await conn.execute("SELECT * FROM users WHERE id = ? AND company_id = ?", (user_id, comp_id))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi!")

        if user["role"] == "ADMIN" or user["id"] == admin["id"] or user["telegram_id"] == 8686341550:
            raise HTTPException(status_code=403, detail="Bosh Rahbar daxlsiz! Uni dam olish rejimiga o'tkazib bo'lmaydi.")

        if not user["is_active"]:
            raise HTTPException(status_code=400, detail="Ishdan bo'shatilgan xodimning ish rejimini o'zgartirib bo'lmaydi! Avval uni faollashtiring.")

        current_shift = user["shift_status"] if ("shift_status" in user.keys() and user["shift_status"]) else "WORKING"

        if req and req.shift_status:
            target_status = req.shift_status.strip().upper()
            if target_status not in ["WORKING", "RESTING"]:
                raise HTTPException(status_code=400, detail="Status faqat 'WORKING' yoki 'RESTING' bo'lishi mumkin!")
            new_status = target_status
        else:
            new_status = "RESTING" if current_shift == "WORKING" else "WORKING"

        status_label = "Damda 🌙 (Dam olish rejimi)" if new_status == "RESTING" else "Ishda 🟢 (Faol ish rejimi)"

        await conn.execute("UPDATE users SET shift_status = ? WHERE id = ?", (new_status, user_id))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'USER_SHIFT', ?, 'STATUS_CHANGE', ?, ?)
        """, (comp_id, user_id, admin["full_name"], f"Xodim '{user['full_name']}' ish statusi '{status_label}' ga o'zgartirildi"))
        await conn.commit()
        invalidate_user_cache(user_id)

    return {
        "success": True,
        "shift_status": new_status,
        "message": f"Xodim {user['full_name']} muvaffaqiyatli '{status_label}' ga o'tkazildi!"
    }

@router.post("/users/{user_id}/debt")
async def assign_debt(user_id: int, req: SetDebtRequest, admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        comp_id = admin.get("company_id") or 1
        cursor = await conn.execute("SELECT * FROM users WHERE id = ? AND company_id = ?", (user_id, comp_id))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")

        # TT: "agar rahbar yangi qarz belgilasa mavjud qarzdorlikka qo'shib hisoblanib boriladi"
        added_amount = float(req.debt_amount)
        if added_amount < 0 or added_amount > 1_000_000_000:
            raise HTTPException(status_code=400, detail="Qarz summasi 0 dan 1 000 000 000 so'mgacha bo'lishi shart!")

        reason_text = req.reason.strip() if req.reason else "Ko'rsatilmadi"
        new_total_debt = round(user["debt_amount"] + added_amount, 2)

        await conn.execute("UPDATE users SET debt_amount = ? WHERE id = ?", (new_total_debt, user_id))

        audit_details = (
            f"{user['full_name']}ga {added_amount:,.0f} so'm yangi qarz biriktirildi. "
            f"Sababi: {reason_text}. Yangi jami qarz: {new_total_debt:,.0f} so'm"
        )
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'USER_DEBT', ?, 'ASSIGN', ?, ?)
        """, (comp_id, user_id, admin["full_name"], audit_details))
        await conn.commit()
        invalidate_user_cache(user_id)

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
        comp_id = admin.get("company_id") or 1
        cursor = await conn.execute("SELECT full_name FROM users WHERE id = ? AND company_id = ?", (user_id, comp_id))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")

        await conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'USER_PASSWORD', ?, 'UPDATE', ?, ?)
        """, (comp_id, user_id, admin["full_name"], f"{user['full_name']} paroli Rahbar tomonidan yangilandi"))
        await conn.commit()
        invalidate_user_cache(user_id)

    return {"success": True, "message": f"{user['full_name']} paroli muvaffaqiyatli yangilandi!"}

@router.post("/cashier/appoint")
async def appoint_cashier(req: AppointCashierRequest, admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        comp_id = admin.get("company_id") or 1
        cursor = await conn.execute("SELECT * FROM users WHERE id = ? AND company_id = ?", (req.user_id, comp_id))
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

        # 1. Hozirgi barcha kassirlarni aniqlash (faqat shu kompaniya doirasida)
        cursor = await conn.execute("SELECT * FROM users WHERE role = 'CASHIER' AND company_id = ?", (comp_id,))
        previous_cashiers = await cursor.fetchall()

        # Oldingi kassirlarni audit va cashier_history ga DISMISSED sifatida yozish
        for prev in previous_cashiers:
            if prev["id"] != target_user["id"]:
                await conn.execute("""
                    INSERT INTO cashier_history (company_id, user_id, action, assigned_by_id)
                    VALUES (?, ?, 'DISMISSED', ?)
                """, (comp_id, prev["id"], admin["id"]))
                await conn.execute("""
                    INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
                    VALUES (?, 'CASHIER', ?, 'DISMISS', ?, ?)
                """, (comp_id, prev["id"], admin["full_name"], f"{prev['full_name']} yangi kassir ({target_user['full_name']}) tayinlangani sababli avtomatik oddiy xodim holatiga o'tkazildi"))

        # 2. Shu kompaniyadagi barcha eski kassirlarni qat'iy oddiy xodim (EMPLOYEE) holatiga o'tkazish
        await conn.execute("""
            UPDATE users SET role = 'EMPLOYEE' 
            WHERE role = 'CASHIER' AND company_id = ?
        """, (comp_id,))

        # 3. Faqat yangi tanlangan xodimni CASHIER qilish (tizimda faqat 1 ta kassir)
        await conn.execute("""
            UPDATE users SET role = 'CASHIER' 
            WHERE id = ? AND company_id = ?
        """, (req.user_id, comp_id))

        # 4. Yangi tayinlovni tarixga va auditga yozish
        await conn.execute("""
            INSERT INTO cashier_history (company_id, user_id, action, assigned_by_id)
            VALUES (?, ?, 'APPOINTED', ?)
        """, (comp_id, req.user_id, admin["id"]))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'CASHIER', ?, 'APPOINT', ?, ?)
        """, (comp_id, req.user_id, admin["full_name"], f"{target_user['full_name']} yagona Kassir etib tayinlandi"))
        await conn.commit()
        invalidate_user_cache()

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
        comp_id = admin.get("company_id") or 1
        cursor = await conn.execute("SELECT * FROM users WHERE id = ? AND company_id = ?", (req.user_id, comp_id))
        target_user = await cursor.fetchone()
        if not target_user:
            raise HTTPException(status_code=404, detail="Tanlangan xodim topilmadi!")

        await conn.execute("UPDATE users SET role = 'EMPLOYEE' WHERE id = ? AND company_id = ?", (req.user_id, comp_id))
        await conn.execute("""
            INSERT INTO cashier_history (company_id, user_id, action, assigned_by_id)
            VALUES (?, ?, 'DISMISSED', ?)
        """, (comp_id, req.user_id, admin["id"]))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'CASHIER', ?, 'DISMISS', ?, ?)
        """, (comp_id, req.user_id, admin["full_name"], f"{target_user['full_name']} kassirlikdan bo'shatilib oddiy xodim holatiga qaytarildi"))
        await conn.commit()
        invalidate_user_cache(req.user_id)

    return {
        "success": True,
        "message": f"{target_user['full_name']} oddiy xodim holatiga qaytarildi!"
    }

@router.get("/cashier/history")
async def get_cashier_history(admin: dict = Depends(require_role(["ADMIN"]))):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        comp_id = admin.get("company_id") or 1
        cursor = await conn.execute("""
            SELECT ch.*, u.full_name as cashier_name, a.full_name as admin_name
            FROM cashier_history ch
            JOIN users u ON ch.user_id = u.id
            JOIN users a ON ch.assigned_by_id = a.id
            WHERE u.company_id = ?
            ORDER BY ch.id DESC LIMIT 50
        """, (comp_id,))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    entity_type: Optional[str] = Query(None),
    admin: dict = Depends(require_role(["ADMIN"]))
):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        comp_id = admin.get("company_id") or 1
        params = [comp_id]
        sql = "SELECT * FROM audit_logs WHERE company_id = ?"
        if entity_type and entity_type.strip():
            sql += " AND entity_type = ?"
            params.append(entity_type.strip().upper())
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await conn.execute(sql, tuple(params))
        rows = await cursor.fetchall()
        return {"success": True, "data": [dict(r) for r in rows]}

@router.get("/analytics/monitoring")
async def get_sales_monitoring(
    period: str = "7d",
    user_id: Optional[int] = None,
    refresh: bool = False,
    admin: dict = Depends(require_role(["ADMIN"]))
):
    """Faqat Rahbar uchun: Savdo monitoringi, vaqt bo'yicha dinamika (o'sish/pasayish) va xodim bo'yicha filtr"""
    comp_id = admin.get("company_id") or 1
    if refresh:
        from app.services.analytics_service import invalidate_analytics_cache
        invalidate_analytics_cache(comp_id)
    data = await get_sales_monitoring_data(company_id=comp_id, period=period, user_id=user_id)
    return {"success": True, "data": data}


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


@router.post("/clear-history")
async def admin_clear_history(admin: dict = Depends(require_role(["ADMIN"]))):
    """Barcha amaliyotlar tarixini tozalash va nollashtirish (faqat shu firma doirasida)"""
    comp_id = admin.get("company_id") or 1
    async with aiosqlite.connect(DB_PATH) as conn:
        tables_to_clear = [
            "card_topups",
            "given_amounts",
            "daily_reports",
            "cashier_handovers",
            "cashier_history",
            "audit_logs",
            "sim_cards",
            "sim_distributions"
        ]
        results = {}
        for table in tables_to_clear:
            cur = await conn.execute(f"DELETE FROM {table} WHERE company_id = ?", (comp_id,))
            results[table] = cur.rowcount

        cur = await conn.execute("UPDATE users SET debt_amount = 0.0 WHERE company_id = ?", (comp_id,))
        results["users_debt_reset"] = cur.rowcount

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'SYSTEM', 0, 'CLEAR_HISTORY', ?, 'Firma amaliyotlari va operatsiyalar tarixi tozalab nollashtirildi')
        """, (comp_id, admin["full_name"]))

        await conn.commit()
        invalidate_user_cache()

        return {
            "success": True,
            "message": "Firma operatsiyalari tarixi muvaffaqiyatli tozalandi va nollashtirildi!",
            "details": results
        }

@router.get("/backup-db")
async def download_database_backup(current_user: dict = Depends(get_current_user)):
    """Ma'lumotlar bazasining to'liq xavfsiz zaxira nusxasini (Snapshot) yuklab olish"""
    if current_user.get("role") not in ["ADMIN", "DEVELOPER"] and not current_user.get("is_super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faqat Rahbar yoki Dasturchi Admin baza zaxirasini yuklab olishi mumkin!"
        )

    import sqlite3
    import tempfile
    import os
    from fastapi.responses import FileResponse
    from app.security import get_tashkent_now

    now_str = get_tashkent_now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_xodim_reyting_{now_str}.db"
    temp_dir = tempfile.gettempdir()
    backup_filepath = os.path.join(temp_dir, backup_filename)

    try:
        # SQLite rasmiy Backup API orqali WAL holatidagi bazaning toza nusxasini olish
        src_conn = sqlite3.connect(DB_PATH)
        dest_conn = sqlite3.connect(backup_filepath)
        src_conn.backup(dest_conn)
        dest_conn.close()
        src_conn.close()

        return FileResponse(
            backup_filepath,
            media_type="application/x-sqlite3",
            filename=backup_filename,
            headers={"Content-Disposition": f'attachment; filename="{backup_filename}"'}
        )
    except Exception as e:
        logger.error(f"Baza zaxirasini olishda xatolik: {e}")
        raise HTTPException(status_code=500, detail=f"Baza zaxirasini yaratishda xatolik: {e}")

