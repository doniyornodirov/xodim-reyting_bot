import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
import aiosqlite

from app.config import DB_PATH, FRONTEND_URL
from app.models import (
    CreateCompanyRequest,
    ExtendSubscriptionRequest,
    UpdateCompanySettingsRequest,
    UpdateCompanyAdminDetailsRequest,
    TestGroupRequest,
)
from app.dependencies import get_current_user, require_super_admin, require_role
from app.security import hash_password, create_access_token

router = APIRouter(prefix="/api/saas", tags=["SaaS Multi-Tenant Management"])

def generate_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "firma"

def calculate_days_left(plan: str, exp_val: Optional[str]) -> Optional[int]:
    if plan == "UNLIMITED" or not exp_val:
        return None
    try:
        clean_exp = str(exp_val).replace("Z", "+00:00")
        exp_dt = datetime.fromisoformat(clean_exp)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = (exp_dt - now).total_seconds()
        if diff <= 0:
            return 0
        return int(diff // 86400) + 1
    except Exception:
        return 0

@router.get("/companies")
async def list_companies(super_admin: dict = Depends(require_super_admin)):
    """Super Admin uchun barcha ijarachi firmalar (tenants) ro'yxati va statistikasi"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("""
            SELECT c.*,
                   u.full_name as owner_name
            FROM companies c
            LEFT JOIN users u ON u.telegram_id = c.owner_telegram_id AND u.company_id = c.id
            ORDER BY c.id ASC
        """)
        companies_raw = await cur.fetchall()

        result = []
        for c in companies_raw:
            c_id = c["id"]

            # Statistika: Faol xodimlar soni (Firma rahbarlari, Adminlar va Dasturchilar bundan qat'iy mustasno)
            cur_users = await conn.execute(
                """
                SELECT COUNT(*) FROM users 
                WHERE company_id = ? 
                  AND is_active = 1 
                  AND UPPER(COALESCE(role, '')) NOT IN ('ADMIN', 'DEVELOPER', 'SUPERADMIN')
                  AND (telegram_id != ? OR ? IS NULL)
                """, (c_id, c["owner_telegram_id"], c["owner_telegram_id"])
            )
            users_count = (await cur_users.fetchone())[0]

            # Kassirlar soni (Firma rahbarlari bundan ham mustasno)
            cur_cashiers = await conn.execute(
                """
                SELECT COUNT(*) FROM users 
                WHERE company_id = ? 
                  AND UPPER(COALESCE(role, '')) = 'CASHIER' 
                  AND is_active = 1
                  AND (telegram_id != ? OR ? IS NULL)
                """, (c_id, c["owner_telegram_id"], c["owner_telegram_id"])
            )
            cashiers_count = (await cur_cashiers.fetchone())[0]

            # Topshirilgan hisobotlar soni
            cur_rep = await conn.execute(
                "SELECT COUNT(*) FROM daily_reports WHERE company_id = ?", (c_id,)
            )
            reports_count = (await cur_rep.fetchone())[0]

            # Karta to'ldirish so'rovlari soni
            cur_topups = await conn.execute(
                "SELECT COUNT(*) FROM card_topups WHERE company_id = ?", (c_id,)
            )
            topups_count = (await cur_topups.fetchone())[0]

            # Oxirgi faollik sanasi (hisobot, karta so'rovi yoki kassa topshirish)
            cur_last = await conn.execute("""
                SELECT MAX(ts) FROM (
                    SELECT MAX(created_at) as ts FROM daily_reports WHERE company_id = ?
                    UNION ALL
                    SELECT MAX(created_at) as ts FROM card_topups WHERE company_id = ?
                    UNION ALL
                    SELECT MAX(created_at) as ts FROM cashier_handovers WHERE company_id = ?
                )
            """, (c_id, c_id, c_id))
            last_activity = (await cur_last.fetchone())[0]

            # Jami aylanma (savdo tushumlari)
            cur_sales = await conn.execute(
                "SELECT COALESCE(SUM(total_inflow), 0) FROM daily_reports WHERE company_id = ?", (c_id,)
            )
            total_turnover = (await cur_sales.fetchone())[0]

            # Xodimlar umumiy qarzi
            cur_debt = await conn.execute(
                "SELECT COALESCE(SUM(debt_amount), 0) FROM users WHERE company_id = ? AND is_active = 1", (c_id,)
            )
            total_debt = (await cur_debt.fetchone())[0]

            days_left = calculate_days_left(c["plan"], c["subscription_expires_at"])

            result.append({
                "id": c["id"],
                "name": c["name"],
                "slug": c["slug"],
                "telegram_group_id": c["telegram_group_id"],
                "owner_telegram_id": c["owner_telegram_id"],
                "owner_name": c["owner_name"] or "Belgilanmagan",
                "plan": c["plan"],
                "subscription_expires_at": c["subscription_expires_at"],
                "days_left": days_left,
                "is_active": bool(c["is_active"]),
                "created_at": c["created_at"],
                "max_employees": c["max_employees"] if ("max_employees" in c.keys() and c["max_employees"]) else 20,
                "employees_count": users_count,
                "cashiers_count": cashiers_count,
                "reports_count": reports_count,
                "topups_count": topups_count,
                "owner_phone": c["owner_phone"] if ("owner_phone" in c.keys() and c["owner_phone"]) else None,
                "owner_extra_contact": c["owner_extra_contact"] if ("owner_extra_contact" in c.keys() and c["owner_extra_contact"]) else None,
                "company_inn": c["company_inn"] if ("company_inn" in c.keys() and c["company_inn"]) else None,
                "notes": c["notes"] if ("notes" in c.keys() and c["notes"]) else None,
                "last_activity": last_activity,
                "total_turnover": float(total_turnover or 0),
                "total_debt": float(total_debt or 0)
            })

    return {"success": True, "data": result}

@router.post("/companies/create")
async def create_company(
    req: CreateCompanyRequest,
    super_admin: dict = Depends(require_super_admin)
):
    """Super Admin tomonidan yangi firma (Tenant) yaratish va uning Rahbarini avtomatik ro'yxatga olish"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Telegram ID band emasligini tekshirish
        cur = await conn.execute("SELECT id, full_name FROM users WHERE telegram_id = ?", (req.owner_telegram_id,))
        if await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Telegram ID {req.owner_telegram_id} ga ega foydalanuvchi tizimda allaqachon mavjud!"
            )

        # 2. Slug yaratish va unikal qilish
        base_slug = generate_slug(req.name)
        slug = base_slug
        idx = 1
        while True:
            cur_s = await conn.execute("SELECT id FROM companies WHERE slug = ?", (slug,))
            if not await cur_s.fetchone():
                break
            idx += 1
            slug = f"{base_slug}-{idx}"

        # 3. Obuna muddati
        now_utc = datetime.now(timezone.utc)
        tashkent_tz = timezone(timedelta(hours=5))
        if req.plan == "UNLIMITED":
            expires_at = None
        else:
            if req.expires_date and req.expires_date.strip():
                try:
                    date_obj = datetime.strptime(req.expires_date.strip(), "%Y-%m-%d")
                    # Belgilangan sananing 23:59:59 gacha amal qiladi (Toshkent vaqti)
                    exp_dt = datetime(date_obj.year, date_obj.month, date_obj.day, 23, 59, 59, tzinfo=tashkent_tz)
                    expires_at = exp_dt.astimezone(timezone.utc).isoformat()
                except ValueError:
                    raise HTTPException(status_code=400, detail="Sana formati noto'g'ri! YYYY-MM-DD bo'lishi kerak.")
            elif req.plan == "5_YEARS":
                # 5 yil keyingi sana (Toshkent vaqti 23:59:59)
                tashkent_now = datetime.now(tashkent_tz)
                try:
                    exp_dt = tashkent_now.replace(year=tashkent_now.year + 5, hour=23, minute=59, second=59, microsecond=0)
                except ValueError:
                    exp_dt = tashkent_now.replace(year=tashkent_now.year + 5, month=2, day=28, hour=23, minute=59, second=59, microsecond=0)
                expires_at = exp_dt.astimezone(timezone.utc).isoformat()
            else:
                days = req.subscription_days or 30
                exp_dt = now_utc + timedelta(days=days)
                expires_at = exp_dt.isoformat()

        # 4. Kompaniyani yaratish
        max_emp = req.max_employees or 20
        cur_c = await conn.execute("""
            INSERT INTO companies (
                name, slug, telegram_group_id, owner_telegram_id, plan,
                subscription_expires_at, max_employees, is_active,
                owner_phone, owner_extra_contact, company_inn, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
        """, (
            req.name.strip(),
            slug,
            req.telegram_group_id.strip() if req.telegram_group_id else None,
            req.owner_telegram_id,
            req.plan,
            expires_at,
            max_emp,
            req.owner_phone.strip() if req.owner_phone else None,
            req.owner_extra_contact.strip() if req.owner_extra_contact else None,
            req.company_inn.strip() if req.company_inn else None,
            req.notes.strip() if req.notes else None
        ))
        company_id = cur_c.lastrowid

        # 5. Firma Rahbarini (Admin) yaratish
        pwd = req.initial_password.strip() if req.initial_password else str(req.owner_telegram_id)
        pwd_hash = hash_password(pwd)
        cur_u = await conn.execute("""
            INSERT INTO users (company_id, telegram_id, full_name, role, password_hash, debt_amount, is_active)
            VALUES (?, ?, ?, 'ADMIN', ?, 0, 1)
        """, (company_id, req.owner_telegram_id, req.owner_name.strip(), pwd_hash))
        owner_user_id = cur_u.lastrowid

        # 6. Audit log
        if expires_at:
            try:
                exp_display = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).astimezone(tashkent_tz).strftime("%d.%m.%Y")
            except Exception:
                exp_display = expires_at
        else:
            exp_display = "Cheksiz"

        details = (
            f"Yangi firma ro'yxatdan o'tkazildi: '{req.name}' (ID: {company_id}). "
            f"Rahbar: {req.owner_name} (TG: {req.owner_telegram_id}). "
            f"Tarif: {req.plan}, Amal qilish sanasi: {exp_display} gacha."
        )
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'CREATE', ?, ?)
        """, (company_id, super_admin["full_name"], details))

        await conn.commit()

    return {
        "success": True,
        "message": f"'{req.name}' firmasi muvaffaqiyatli yaratildi! Firma Rahbari: {req.owner_name} (Login/Parol: {req.owner_telegram_id})",
        "data": {
            "company_id": company_id,
            "company_name": req.name.strip(),
            "owner_user_id": owner_user_id,
            "owner_telegram_id": req.owner_telegram_id,
            "subscription_expires_at": expires_at,
            "plan": req.plan
        }
    }

@router.post("/companies/{company_id}/toggle-active")
async def toggle_company_active(
    company_id: int,
    super_admin: dict = Depends(require_super_admin)
):
    """Super Admin tomonidan firmadagi xizmatni vaqtinchalik to'xtatish yoki faollashtirish"""
    if company_id == 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bosh Tashkilotni (1-kompaniya) to'xtatib bo'lmaydi!"
        )

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        comp = await cur.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Firma topilmadi!")

        new_status = 0 if comp["is_active"] else 1
        status_text = "Faollashtirildi" if new_status else "Vaqtinchalik to'xtatildi (Bloklandi)"

        await conn.execute("UPDATE companies SET is_active = ? WHERE id = ?", (new_status, company_id))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'STATUS_CHANGE', ?, ?)
        """, (company_id, super_admin["full_name"], f"Firma '{comp['name']}' holati o'zgartirildi: {status_text}"))

        await conn.commit()

    return {
        "success": True,
        "message": f"'{comp['name']}' firmasi muvaffaqiyatli {status_text}!",
        "is_active": bool(new_status)
    }

@router.post("/companies/{company_id}/update-limit")
async def update_company_limit(
    company_id: int,
    max_employees: int,
    super_admin: dict = Depends(require_super_admin)
):
    """Super Admin tomonidan firmaning ruxsat etilgan xodimlar limitini o'zgartirish"""
    if max_employees < 1 or max_employees > 10000:
        raise HTTPException(status_code=400, detail="Xodimlar limiti 1 dan 10000 gacha bo'lishi kerak!")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        comp = await cur.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Firma topilmadi!")

        await conn.execute("UPDATE companies SET max_employees = ? WHERE id = ?", (max_employees, company_id))
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'UPDATE_LIMIT', ?, ?)
        """, (company_id, super_admin["full_name"], f"Firma '{comp['name']}' xodimlar limiti {max_employees} taga o'zgartirildi"))
        await conn.commit()

    return {
        "success": True,
        "message": f"'{comp['name']}' firmasi xodimlar limiti {max_employees} taga muvaffaqiyatli o'zgartirildi!",
        "max_employees": max_employees
    }

@router.post("/companies/{company_id}/edit-details")
async def edit_company_details(
    company_id: int,
    req: UpdateCompanyAdminDetailsRequest,
    super_admin: dict = Depends(require_super_admin)
):
    """Super Admin tomonidan firma nomi, guruh ID, limit va Rahbar ma'lumotlarini (F.I.SH, TG ID, Parol) tahrirlash"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        comp = await cur.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Firma topilmadi!")

        comp_updates = []
        comp_params = []

        if req.name and req.name.strip():
            comp_updates.append("name = ?")
            comp_params.append(req.name.strip())

        if req.telegram_group_id is not None:
            clean_grp = req.telegram_group_id.strip() if req.telegram_group_id.strip() else None
            comp_updates.append("telegram_group_id = ?")
            comp_params.append(clean_grp)

        if req.owner_phone is not None:
            clean_phone = req.owner_phone.strip() if req.owner_phone.strip() else None
            comp_updates.append("owner_phone = ?")
            comp_params.append(clean_phone)

        if req.owner_extra_contact is not None:
            clean_extra = req.owner_extra_contact.strip() if req.owner_extra_contact.strip() else None
            comp_updates.append("owner_extra_contact = ?")
            comp_params.append(clean_extra)

        if req.company_inn is not None:
            clean_inn = req.company_inn.strip() if req.company_inn.strip() else None
            comp_updates.append("company_inn = ?")
            comp_params.append(clean_inn)

        if req.notes is not None:
            clean_notes = req.notes.strip() if req.notes.strip() else None
            comp_updates.append("notes = ?")
            comp_params.append(clean_notes)

        if req.max_employees is not None:
            if req.max_employees < 1 or req.max_employees > 10000:
                raise HTTPException(status_code=400, detail="Xodimlar limiti 1 dan 10000 gacha bo'lishi kerak!")
            comp_updates.append("max_employees = ?")
            comp_params.append(req.max_employees)

        old_owner_tg = comp["owner_telegram_id"]

        # Rahbar (ADMIN) foydalanuvchini topish
        cur_user = await conn.execute(
            "SELECT * FROM users WHERE company_id = ? AND role = 'ADMIN' LIMIT 1",
            (company_id,)
        )
        owner_user = await cur_user.fetchone()
        if not owner_user and old_owner_tg:
            cur_user = await conn.execute(
                "SELECT * FROM users WHERE telegram_id = ? AND company_id = ? LIMIT 1",
                (old_owner_tg, company_id)
            )
            owner_user = await cur_user.fetchone()

        if req.owner_telegram_id is not None:
            new_owner_tg = req.owner_telegram_id
            if new_owner_tg != old_owner_tg:
                cur_exist = await conn.execute(
                    "SELECT id, full_name, company_id FROM users WHERE telegram_id = ?",
                    (new_owner_tg,)
                )
                existing = await cur_exist.fetchone()
                if existing and (owner_user is None or existing["id"] != owner_user["id"]):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Telegram ID {new_owner_tg} boshqa foydalanuvchi ({existing['full_name']}) tomonidan band!"
                    )
                comp_updates.append("owner_telegram_id = ?")
                comp_params.append(new_owner_tg)

        if comp_updates:
            comp_params.append(company_id)
            await conn.execute(
                f"UPDATE companies SET {', '.join(comp_updates)} WHERE id = ?",
                tuple(comp_params)
            )

        # Rahbar ma'lumotlarini yangilash
        if owner_user:
            user_updates = ["role = 'ADMIN'"]
            user_params = []

            if req.owner_telegram_id is not None:
                user_updates.append("telegram_id = ?")
                user_params.append(req.owner_telegram_id)

            if req.owner_name and req.owner_name.strip():
                user_updates.append("full_name = ?")
                user_params.append(req.owner_name.strip())

            if req.new_password and req.new_password.strip():
                pwd_hash = hash_password(req.new_password.strip())
                user_updates.append("password_hash = ?")
                user_params.append(pwd_hash)

            if user_updates:
                user_params.append(owner_user["id"])
                await conn.execute(
                    f"UPDATE users SET {', '.join(user_updates)} WHERE id = ?",
                    tuple(user_params)
                )
        elif req.owner_telegram_id and req.owner_name:
            pwd = req.new_password.strip() if (req.new_password and req.new_password.strip()) else str(req.owner_telegram_id)
            pwd_hash = hash_password(pwd)
            await conn.execute("""
                INSERT INTO users (company_id, telegram_id, full_name, role, password_hash, debt_amount, is_active)
                VALUES (?, ?, ?, 'ADMIN', ?, 0, 1)
            """, (company_id, req.owner_telegram_id, req.owner_name.strip(), pwd_hash))

        # Audit log
        details = (
            f"Firma #{company_id} tahrirlandi: "
            f"Nomi: '{req.name or comp['name']}', "
            f"Rahbar: '{req.owner_name or (owner_user['full_name'] if owner_user else '-')}' "
            f"(TG: {req.owner_telegram_id or old_owner_tg}), "
            f"Guruh: '{req.telegram_group_id if req.telegram_group_id is not None else comp['telegram_group_id']}'"
        )
        if req.new_password and req.new_password.strip():
            details += ", Yangi parol o'rnatildi."

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'EDIT_DETAILS', ?, ?)
        """, (company_id, super_admin["full_name"], details))

        await conn.commit()

    return {
        "success": True,
        "message": f"'{req.name or comp['name']}' firmasi ma'lumotlari muvaffaqiyatli saqlandi!"
    }

@router.post("/companies/{company_id}/update-plan")
async def update_company_plan(
    company_id: int,
    new_plan: str = Query(..., pattern="^(STANDARD|5_YEARS|UNLIMITED)$"),
    super_admin: dict = Depends(require_super_admin)
):
    """Firma tarif rejasini o'zgartirish (STANDARD, 5_YEARS, UNLIMITED)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT id, name, plan, subscription_expires_at FROM companies WHERE id = ?", (company_id,))
        comp = await cur.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Firma topilmadi!")

        tashkent_tz = timezone(timedelta(hours=5))
        now_utc = datetime.now(timezone.utc)
        new_expires_at = comp["subscription_expires_at"]

        if new_plan == "UNLIMITED":
            new_expires_at = None
        elif new_plan == "5_YEARS":
            tashkent_now = datetime.now(tashkent_tz)
            try:
                exp_dt = tashkent_now.replace(year=tashkent_now.year + 5, hour=23, minute=59, second=59, microsecond=0)
            except ValueError:
                exp_dt = tashkent_now.replace(year=tashkent_now.year + 5, month=2, day=28, hour=23, minute=59, second=59, microsecond=0)
            new_expires_at = exp_dt.astimezone(timezone.utc).isoformat()
        elif new_plan == "STANDARD" and not new_expires_at:
            new_expires_at = (now_utc + timedelta(days=30)).isoformat()

        await conn.execute("""
            UPDATE companies 
            SET plan = ?, subscription_expires_at = ?, is_active = 1 
            WHERE id = ?
        """, (new_plan, new_expires_at, company_id))

        details = f"Firma '{comp['name']}' tarifi '{comp['plan']}' dan '{new_plan}' ga o'zgartirildi."
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'UPDATE_PLAN', ?, ?)
        """, (company_id, super_admin["full_name"], details))

        await conn.commit()

    return {
        "success": True,
        "message": f"'{comp['name']}' firmasi tarifi muvaffaqiyatli '{new_plan}' ga o'zgartirildi!"
    }

@router.post("/companies/{company_id}/extend")
async def extend_company_subscription(
    company_id: int,
    req: ExtendSubscriptionRequest,
    super_admin: dict = Depends(require_super_admin)
):
    """Super Admin tomonidan firmaning ijara obunasini belgilangan sana yoki kunga uzaytirish"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        comp = await cur.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Firma topilmadi!")

        if comp["plan"] == "UNLIMITED":
            return {
                "success": True,
                "message": f"'{comp['name']}' firmasi Cheksiz (UNLIMITED) tarifida, obunani uzaytirish talab etilmaydi."
            }

        now_utc = datetime.now(timezone.utc)
        tashkent_tz = timezone(timedelta(hours=5))

        if req.new_expires_date and req.new_expires_date.strip():
            try:
                date_obj = datetime.strptime(req.new_expires_date.strip(), "%Y-%m-%d")
                new_exp_dt = datetime(date_obj.year, date_obj.month, date_obj.day, 23, 59, 59, tzinfo=tashkent_tz)
                new_exp_iso = new_exp_dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                raise HTTPException(status_code=400, detail="Sana formati noto'g'ri! YYYY-MM-DD bo'lishi kerak.")
        elif req.days:
            cur_exp = comp["subscription_expires_at"]
            base_dt = now_utc
            if cur_exp:
                try:
                    parsed_exp = datetime.fromisoformat(str(cur_exp).replace("Z", "+00:00"))
                    if parsed_exp.tzinfo is None:
                        parsed_exp = parsed_exp.replace(tzinfo=timezone.utc)
                    if parsed_exp > now_utc:
                        base_dt = parsed_exp
                except Exception:
                    base_dt = now_utc
            new_exp_dt = base_dt + timedelta(days=req.days)
            new_exp_iso = new_exp_dt.isoformat()
        else:
            raise HTTPException(status_code=400, detail="Yangi amal qilish sanasi yoki kunlar soni kiritilishi shart!")

        await conn.execute("""
            UPDATE companies 
            SET subscription_expires_at = ?, is_active = 1
            WHERE id = ?
        """, (new_exp_iso, company_id))

        display_date = new_exp_dt.astimezone(tashkent_tz).strftime('%d.%m.%Y')
        details = f"Firma '{comp['name']}' obuna muddati uzaytirildi. Yangi amal qilish sanasi: {display_date} gacha"
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'EXTEND_SUBSCRIPTION', ?, ?)
        """, (company_id, super_admin["full_name"], details))

        await conn.commit()

    return {
        "success": True,
        "message": f"'{comp['name']}' firmasi obunasi muvaffaqiyatli uzaytirildi! Yangi amal qilish sanasi: {display_date} gacha",
        "subscription_expires_at": new_exp_iso
    }

@router.get("/my-company")
async def get_my_company(user: dict = Depends(get_current_user)):
    """Har qanday tizim foydalanuvchisi o'zi tegishli bo'lgan firma ma'lumotlarini olishi"""
    comp_id = user.get("company_id") or 1
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (comp_id,))
        comp = await cur.fetchone()

    if not comp:
        raise HTTPException(status_code=404, detail="Kompaniya ma'lumotlari topilmadi!")

    days_left = calculate_days_left(comp["plan"], comp["subscription_expires_at"])

    return {
        "success": True,
        "data": {
            "id": comp["id"],
            "name": comp["name"],
            "slug": comp["slug"],
            "plan": comp["plan"],
            "telegram_group_id": comp["telegram_group_id"],
            "subscription_expires_at": comp["subscription_expires_at"],
            "days_left": days_left,
            "is_active": bool(comp["is_active"]),
            "is_super_admin": user.get("is_super_admin", False)
        }
    }

@router.post("/my-company/settings")
async def update_my_company_settings(
    req: UpdateCompanySettingsRequest,
    admin: dict = Depends(require_role(["ADMIN"]))
):
    """Firma Rahbari tomonidan o'z kompaniyasining xabarnoma guruhi yoki nomini sozlash"""
    comp_id = admin.get("company_id") or 1

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (comp_id,))
        comp = await cur.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Kompaniya topilmadi!")

        updates = []
        params = []
        if req.name and req.name.strip():
            updates.append("name = ?")
            params.append(req.name.strip())

        if req.telegram_group_id is not None:
            updates.append("telegram_group_id = ?")
            params.append(req.telegram_group_id.strip() if req.telegram_group_id.strip() else None)

        if not updates:
            return {"success": True, "message": "O'zgartirishlar kiritilmadi."}

        params.append(comp_id)
        await conn.execute(f"UPDATE companies SET {', '.join(updates)} WHERE id = ?", tuple(params))

        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'COMPANY', ?, 'UPDATE_SETTINGS', ?, ?)
        """, (comp_id, comp_id, admin["full_name"], "Firma sozlamalari yangilandi"))

        await conn.commit()

    return {"success": True, "message": "Firma sozlamalari muvaffaqiyatli yangilandi!"}

@router.get("/backup-db")
async def download_saas_database_backup(super_admin: dict = Depends(require_super_admin)):
    """Dasturchi Admin (Super Admin) uchun butun platforma bazasining to'liq zaxirasini (.db) yuklab olish"""
    import sqlite3
    import tempfile
    import os
    from fastapi.responses import FileResponse
    from app.security import get_tashkent_now

    now_str = get_tashkent_now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"full_backup_saas_{now_str}.db"
    temp_dir = tempfile.gettempdir()
    backup_filepath = os.path.join(temp_dir, backup_filename)

    try:
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
        raise HTTPException(status_code=500, detail=f"Baza zaxirasini olishda xatolik: {e}")

@router.post("/test-telegram-group")
async def test_telegram_group(
    req: TestGroupRequest,
    super_admin: dict = Depends(require_super_admin)
):
    """Telegram guruh ID si to'g'riligini va bot u guruhda borligini tekshirish"""
    from app.bot import bot
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram bot sozlanmagan (BOT_TOKEN yo'q)!")

    grp_id_str = req.telegram_group_id.strip()
    if not grp_id_str:
        raise HTTPException(status_code=400, detail="Guruh ID si kiritilishi shart!")

    try:
        grp_id = int(grp_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Telegram Guruh ID faqat butun sondan iborat bo'lishi kerak (masalan: -100123456789)!")

    try:
        chat = await bot.get_chat(chat_id=grp_id)
        # Bot guruhda adminmi yoki oddiy a'zomi?
        bot_user = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id=grp_id, user_id=bot_user.id)
        is_admin = bot_member.status in ["administrator", "creator"]
        return {
            "success": True,
            "title": chat.title or "Nomsiz guruh",
            "type": chat.type,
            "is_admin": is_admin,
            "message": f"✅ '{chat.title}' guruhi topildi! Bot holati: {'Admin 👑' if is_admin else 'Oddiy a\'zo (Admin huquqi bering) ⚠️'}"
        }
    except Exception as e:
        err_msg = str(e)
        if "chat not found" in err_msg.lower():
            detail = "Guruh topilmadi! Guruh ID sini tekshiring yoki botni avval ushbu guruhga qo'shing."
        elif "bot was kicked" in err_msg.lower() or "not a member" in err_msg.lower():
            detail = "Bot ushbu guruhda yo'q yoki chiqarib yuborilgan! @xodimkpi_bot ni guruhga qo'shing."
        else:
            detail = f"Telegram xatosi: {err_msg}"
        return {
            "success": False,
            "detail": detail
        }

@router.post("/companies/{company_id}/send-credentials")
async def send_company_credentials(
    company_id: int,
    super_admin: dict = Depends(require_super_admin)
):
    """Firma Rahbarining shaxsiy Telegram lichkasiga kirish rekvizitlarini jo'natish"""
    from app.bot import bot
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram bot sozlanmagan!")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT c.*, u.full_name as owner_name, u.telegram_id as user_tg
            FROM companies c
            LEFT JOIN users u ON u.telegram_id = c.owner_telegram_id AND u.company_id = c.id
            WHERE c.id = ?
        """, (company_id,))
        comp = await cur.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Firma topilmadi!")

        owner_tg = comp["owner_telegram_id"] or comp["user_tg"]
        if not owner_tg:
            raise HTTPException(status_code=400, detail="Firma Rahbarining Telegram ID si belgilanmagan!")

        owner_name = comp["owner_name"] or "Firma Rahbari"
        tashkent_tz = timezone(timedelta(hours=5))
        exp_val = comp["subscription_expires_at"]
        if comp["plan"] == "UNLIMITED":
            exp_text = "Cheksiz (Unlimited ♾️)"
        elif exp_val:
            try:
                exp_text = datetime.fromisoformat(str(exp_val).replace("Z", "+00:00")).astimezone(tashkent_tz).strftime("%d.%m.%Y")
            except Exception:
                exp_text = str(exp_val)
        else:
            exp_text = "Belgilanmagan"

        phone_line = f"📞 <b>Aloqa raqami:</b> <code>{comp['owner_phone']}</code>\n" if ("owner_phone" in comp.keys() and comp["owner_phone"]) else ""

        text = (
            f"🏢 <b>Hurmatli {owner_name}!</b>\n\n"
            f"Sizning <b>\"{comp['name']}\"</b> tashkilotingiz uchun <b>XodimKPI CRM</b> tizimida Rahbarlik kabineti muvaffaqiyatli faollashtirildi! 🎉\n\n"
            f"🌐 <b>CRM Havolasi:</b> {FRONTEND_URL}\n"
            f"👤 <b>Login (Telegram ID):</b> <code>{owner_tg}</code>\n"
            f"🔑 <b>Boshlang'ich parol:</b> <code>{owner_tg}</code> (yoki o'rnatilgan parolingiz)\n"
            f"{phone_line}"
            f"📅 <b>Obuna amal qilish sanasi:</b> {exp_text} gacha\n"
            f"👥 <b>Xodimlar limiti:</b> {comp['max_employees']} ta\n\n"
            f"<i>💡 Tizimga kirib, xodimlaringizni qo'shishingiz va hisobotlarni qabul qilishni boshlashingiz mumkin.</i>"
        )

        try:
            await bot.send_message(chat_id=int(owner_tg), text=text, parse_mode="HTML")
        except Exception as e:
            err_str = str(e).lower()
            if "blocked" in err_str or "not found" in err_str or "can't initiate" in err_str:
                raise HTTPException(
                    status_code=400,
                    detail=f"Xabar yuborib bo'lmadi! Rahbar ({owner_name}) botimizga hali /start bosmagan. Unga @xodimkpi_bot ga kirib /start bosishini ayting."
                )
            raise HTTPException(status_code=400, detail=f"Telegram xatosi: {e}")

        # Audit log
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'SEND_CREDENTIALS', ?, ?)
        """, (company_id, super_admin["full_name"], f"Firma #{company_id} Rahbariga ({owner_name}) kirish rekvizitlari bot orqali yuborildi"))
        await conn.commit()

    return {
        "success": True,
        "message": f"'{comp['name']}' firmasi Rahbariga ({owner_name}) kirish rekvizitlari muvaffaqiyatli yuborildi! ✉️"
    }

@router.post("/companies/{company_id}/impersonate")
async def impersonate_company(
    company_id: int,
    super_admin: dict = Depends(require_super_admin)
):
    """Super Admin uchun tanlangan firma kabinetiga uning Rahbari sifatida kirish (Kuzatuv rejimi)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        comp = await cur.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Firma topilmadi!")

        # Firmaning Admin foydalanuvchisini topish
        cur_user = await conn.execute(
            "SELECT * FROM users WHERE company_id = ? AND role = 'ADMIN' AND is_active = 1 LIMIT 1",
            (company_id,)
        )
        owner_user = await cur_user.fetchone()
        if not owner_user:
            cur_user = await conn.execute(
                "SELECT * FROM users WHERE company_id = ? AND is_active = 1 LIMIT 1",
                (company_id,)
            )
            owner_user = await cur_user.fetchone()

        if not owner_user:
            raise HTTPException(status_code=400, detail="Ushbu firmada faol foydalanuvchi topilmadi!")

        # Token yaratish
        token_data = {
            "sub": str(owner_user["id"]),
            "impersonated_by": super_admin["id"],
            "impersonated_company_id": company_id
        }
        token = create_access_token(token_data)

        # Audit log
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'IMPERSONATE', ?, ?)
        """, (company_id, super_admin["full_name"], f"Super Admin '{comp['name']}' firmasining kabinetiga kuzatuvchi sifatida kirdi"))
        await conn.commit()

    return {
        "success": True,
        "token": token,
        "company_name": comp["name"],
        "user": {
            "id": owner_user["id"],
            "full_name": owner_user["full_name"],
            "role": owner_user["role"],
            "telegram_id": owner_user["telegram_id"],
            "company_id": company_id
        }
    }

@router.delete("/companies/{company_id}")
async def delete_company(
    company_id: int,
    super_admin: dict = Depends(require_super_admin)
):
    """Super Admin tomonidan firmani va uning barcha bog'langan ma'lumotlarini tozalash / o'chirish"""
    if company_id == 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bosh Tashkilotni (1-kompaniya) o'chirib bo'lmaydi!"
        )

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        comp = await cur.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Firma topilmadi!")

        comp_name = comp["name"]

        # Kaskad tozalash (Xavfsiz va aniq jadvallar bo'yicha)
        cascade_tables = [
            "users", "daily_reports", "card_topups", "cashier_handovers",
            "cashier_history", "given_amounts", "sim_cards",
            "sim_distributions", "audit_logs"
        ]
        for tbl in cascade_tables:
            try:
                await conn.execute(f"DELETE FROM {tbl} WHERE company_id = ?", (company_id,))
            except Exception:
                pass

        await conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))

        # Bosh Tashkilot audit logiga yozish
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'DELETE_COMPANY', ?, ?)
        """, (company_id, super_admin["full_name"], f"Firma #{company_id} ('{comp_name}') va uning barcha ma'lumotlari Dasturchi tomonidan butunlay o'chirildi"))
        await conn.commit()

    return {
        "success": True,
        "message": f"'{comp_name}' firmasi va barcha bog'liq ma'lumotlari muvaffaqiyatli o'chirildi!"
    }
