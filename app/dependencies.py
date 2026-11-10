from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import aiosqlite
from app.config import DB_PATH, RAHBAR_ID, DEVELOPER_ID
from app.security import decode_access_token

security = HTTPBearer(auto_error=False)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tizimga kirish talab etiladi (Token topilmadi)"
        )
    
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yaroqsiz yoki muddati o'tgan token"
        )
    
    user_id = int(payload["sub"])
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = await cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Foydalanuvchi topilmadi")
        
        # Ishdan bo'shatilgan xodim darhol uziladi
        if not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sizning akkauntingiz faol emas yoki ishdan bo'shatilgansiz!"
            )

        # Super Admin tekshiruvi (Faqat Dasturchi Admin: 8694797293)
        dev_id_val = int(DEVELOPER_ID) if DEVELOPER_ID and DEVELOPER_ID.isdigit() else 8694797293
        is_super_admin = (int(user["telegram_id"]) == dev_id_val or user["role"] == "DEVELOPER")

        # SaaS: Foydalanuvchi qaysi kompaniyaga tegishli ekanligini tekshirish
        company_id = user["company_id"] if ("company_id" in user.keys() and user["company_id"]) else 1
        cur_c = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        comp = await cur_c.fetchone()

        if not comp:
            company_id = 1
            company_name = "Bosh Tashkilot"
            company_plan = "UNLIMITED"
            company_group_id = None
            company_expires_at = None
        else:
            company_name = comp["name"]
            company_plan = comp["plan"]
            company_group_id = comp["telegram_group_id"]
            company_expires_at = comp["subscription_expires_at"]

            # Super Admin har doim cheklovsiz tizimga kira oladi
            if not is_super_admin:
                if not comp["is_active"]:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Kompaniyangiz tizimdan vaqtinchalik to'xtatilgan (Bloklangan). Super Admin bilan bog'laning!"
                    )
                if comp["plan"] != "UNLIMITED" and comp["subscription_expires_at"]:
                    try:
                        exp_str = str(comp["subscription_expires_at"]).replace("Z", "+00:00")
                        exp_dt = datetime.fromisoformat(exp_str)
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        now_utc = datetime.now(timezone.utc)
                        if now_utc > exp_dt:
                            raise HTTPException(
                                status_code=status.HTTP_403_FORBIDDEN,
                                detail="Kompaniyangizning foydalanish obuna muddati tugagan! Xizmatni davom ettirish uchun to'lov qiling va platforma ma'muriyati bilan bog'laning."
                            )
                    except HTTPException:
                        raise
                    except Exception:
                        pass

    user_dict = dict(user)
    user_dict["company_id"] = company_id
    user_dict["company_name"] = company_name
    user_dict["company_plan"] = company_plan
    user_dict["company_telegram_group_id"] = company_group_id
    user_dict["company_subscription_expires_at"] = company_expires_at
    user_dict["is_super_admin"] = is_super_admin
    return user_dict

def require_role(allowed_roles: list[str]):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        # DEVELOPER har qanday admin boshqaruv amalini bajara oladi
        if current_user.get("role") == "DEVELOPER" or current_user.get("is_super_admin"):
            return current_user
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ushbu amalni bajarish uchun sizda yetarli ruxsat yo'q!"
            )
        return current_user
    return role_checker

async def require_super_admin(current_user: dict = Depends(get_current_user)):
    """Faqat Dasturchi Admin (Super Admin: 8694797293) ga ruxsat beruvchi himoya"""
    if not current_user.get("is_super_admin") and current_user.get("role") != "DEVELOPER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ushbu amal faqat Dasturchi Admin (Super Admin) uchun ruxsat etilgan!"
        )
    return current_user

async def require_active_shift(current_user: dict = Depends(get_current_user)):
    # Bosh Rahbar va Dasturchi Admin har doim daxlsiz va amallarni bajara oladi
    if current_user.get("role") in ["ADMIN", "DEVELOPER"] or current_user.get("is_super_admin"):
        return current_user

    if current_user.get("shift_status") == "RESTING":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Siz hozirda dam olish (damda) rejimidasiz! Amallarni bajarish vaqtinchalik cheklangan. Ishga qaytish uchun Rahbarga murojaat qiling."
        )
    return current_user
