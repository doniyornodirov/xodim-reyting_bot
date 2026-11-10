import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite

from app.config import DB_PATH
from app.models import (
    CreateCompanyRequest,
    ExtendSubscriptionRequest,
    UpdateCompanySettingsRequest,
)
from app.dependencies import get_current_user, require_super_admin, require_role
from app.security import hash_password

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

            # Statistika: Faol xodimlar soni
            cur_users = await conn.execute(
                "SELECT COUNT(*) FROM users WHERE company_id = ? AND is_active = 1", (c_id,)
            )
            users_count = (await cur_users.fetchone())[0]

            # Kassirlar soni
            cur_cashiers = await conn.execute(
                "SELECT COUNT(*) FROM users WHERE company_id = ? AND role = 'CASHIER' AND is_active = 1", (c_id,)
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
                "employees_count": users_count,
                "cashiers_count": cashiers_count,
                "reports_count": reports_count,
                "topups_count": topups_count
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
        if req.plan == "UNLIMITED":
            expires_at = None
        else:
            exp_dt = now_utc + timedelta(days=req.subscription_days)
            expires_at = exp_dt.isoformat()

        # 4. Kompaniyani yaratish
        cur_c = await conn.execute("""
            INSERT INTO companies (name, slug, telegram_group_id, owner_telegram_id, plan, subscription_expires_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (req.name.strip(), slug, req.telegram_group_id.strip() if req.telegram_group_id else None,
              req.owner_telegram_id, req.plan, expires_at))
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
        details = (
            f"Yangi firma ro'yxatdan o'tkazildi: '{req.name}' (ID: {company_id}). "
            f"Rahbar: {req.owner_name} (TG: {req.owner_telegram_id}). "
            f"Tarif: {req.plan}, Obuna: {req.subscription_days} kun."
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

@router.post("/companies/{company_id}/extend")
async def extend_company_subscription(
    company_id: int,
    req: ExtendSubscriptionRequest,
    super_admin: dict = Depends(require_super_admin)
):
    """Super Admin tomonidan firmaning ijara obunasini belgilangan kunga uzaytirish"""
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

        await conn.execute("""
            UPDATE companies 
            SET subscription_expires_at = ?, is_active = 1
            WHERE id = ?
        """, (new_exp_iso, company_id))

        details = f"Firma '{comp['name']}' obunasi +{req.days} kunga uzaytirildi. Yangi muddat: {new_exp_dt.strftime('%d.%m.%Y %H:%M')}"
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (1, 'COMPANY', ?, 'EXTEND_SUBSCRIPTION', ?, ?)
        """, (company_id, super_admin["full_name"], details))

        await conn.commit()

    return {
        "success": True,
        "message": f"'{comp['name']}' obunasi muvaffaqiyatli +{req.days} kunga uzaytirildi! Yangi tugash sanasi: {new_exp_dt.strftime('%d.%m.%Y')}",
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
