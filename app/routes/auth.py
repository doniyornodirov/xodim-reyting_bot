import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, status
import aiosqlite
from app.config import DB_PATH, OTP_EXPIRATION_SECONDS, DEBUG, BOT_USERNAME, RAHBAR_ID, DEVELOPER_ID
from app.database import get_db_connection
from app.models import LoginRequest, VerifyOtpRequest, DeviceVerifyOrBindRequest
from app.security import verify_password, generate_otp, create_access_token
from app.bot import send_otp_to_telegram
from app.dependencies import get_current_user
from fastapi import Depends

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# Foydalanuvchi darajasidagi alohida qulflar (Faqat bitta xodim ketma-ket bosib yubormasligi uchun,
# boshqa 200 ta xodim bir-biriga aslo to'siq bo'lmaydi)
_user_locks: dict[int, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()

async def get_user_lock(telegram_id: int) -> asyncio.Lock:
    async with _locks_guard:
        if telegram_id not in _user_locks:
            _user_locks[telegram_id] = asyncio.Lock()
        return _user_locks[telegram_id]

@router.post("/login")
async def login(req: LoginRequest):
    user_lock = await get_user_lock(req.telegram_id)
    async with user_lock:
        async with get_db_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (req.telegram_id,)
            )
            user = await cursor.fetchone()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Bunday Telegram ID ga ega xodim topilmadi!"
                )

            if not user["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Ushbu xodim ishdan bo'shatilgan va tizimga kira olmaydi!"
                )

            if not verify_password(req.password, user["password_hash"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Parol noto'g'ri kiritildi!"
                )

            # Kompaniya holatini tekshirish
            dev_id_val = int(DEVELOPER_ID) if DEVELOPER_ID and DEVELOPER_ID.isdigit() else 8694797293
            is_super_admin = (int(user["telegram_id"]) == dev_id_val or user["role"] == "DEVELOPER")
            if not is_super_admin:
                comp_id = user["company_id"] if ("company_id" in user.keys() and user["company_id"]) else 1
                cur_c = await conn.execute("SELECT * FROM companies WHERE id = ?", (comp_id,))
                comp = await cur_c.fetchone()
                if comp:
                    if not comp["is_active"]:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Kompaniyangiz tizimdan vaqtinchalik to'xtatilgan (Bloklangan). Super Admin bilan bog'laning!"
                        )
                    if comp["plan"] != "UNLIMITED" and comp["subscription_expires_at"]:
                        try:
                            clean_exp = str(comp["subscription_expires_at"]).replace("Z", "+00:00")
                            exp_dt = datetime.fromisoformat(clean_exp)
                            if exp_dt.tzinfo is None:
                                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                            if datetime.now(timezone.utc) > exp_dt:
                                raise HTTPException(
                                    status_code=status.HTTP_403_FORBIDDEN,
                                    detail="Kompaniyangizning foydalanish obuna muddati tugagan! Obunangizni uzaytiring."
                                )
                        except HTTPException:
                            raise
                        except Exception:
                            pass

            # 1 minutda faqat 1 marta urinish mumkinligini tekshirish (Rate limit)
            now = datetime.now(timezone.utc)
            cursor = await conn.execute("""
                SELECT expires_at FROM otp_codes 
                WHERE telegram_id = ? 
                ORDER BY id DESC LIMIT 1
            """, (req.telegram_id,))
            last_otp = await cursor.fetchone()
            if last_otp:
                exp_str = last_otp["expires_at"]
                try:
                    exp_dt = datetime.fromisoformat(exp_str)
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    seconds_left = int((exp_dt - now).total_seconds())
                    if seconds_left > 0:
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"1 minutda faqat 1 marta urinish mumkin! Qayta urinish {seconds_left} soniyadan keyin."
                        )
                except HTTPException:
                    raise
                except Exception:
                    pass

            # 6 xonali tasodifiy OTP yaratish
            otp_code = generate_otp()
            expires_at = now + timedelta(seconds=OTP_EXPIRATION_SECONDS)

            # Eski foydalanilmagan kodlarni bekor qilish
            await conn.execute(
                "UPDATE otp_codes SET is_used = 1 WHERE telegram_id = ? AND is_used = 0",
                (req.telegram_id,)
            )
            
            await conn.execute("""
                INSERT INTO otp_codes (telegram_id, code, expires_at, is_used)
                VALUES (?, ?, ?, 0)
            """, (req.telegram_id, otp_code, expires_at.isoformat()))
            await conn.commit()

            # Telegram bot orqali lichkaga yuborish
            sent = False
            try:
                sent = await send_otp_to_telegram(req.telegram_id, otp_code)
            except Exception:
                sent = False

            if sent:
                message = "Tasdiqlash kodi Telegram lichkangizga muvaffaqiyatli yuborildi!"
            else:
                message = f"Tasdiqlash kodi botga uzatildi. Agar kod kelmasa, @{BOT_USERNAME} ga /start bosing."

            return {
                "success": True,
                "telegram_sent": sent,
                "message": message,
                "telegram_id": req.telegram_id,
                "expires_in": OTP_EXPIRATION_SECONDS,
                "bot_username": BOT_USERNAME
            }

@router.post("/verify-otp")
async def verify_otp(req: VerifyOtpRequest):
    async with get_db_connection() as conn:
        cursor = await conn.execute("""
            SELECT * FROM otp_codes 
            WHERE telegram_id = ? AND is_used = 0
            ORDER BY id DESC LIMIT 1
        """, (req.telegram_id,))
        otp_record = await cursor.fetchone()

        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Faol tasdiqlash kodi topilmadi, qaytadan login qiling!"
            )

        # Vaqt tekshiruvi (1 daqiqa)
        expires_at = datetime.fromisoformat(otp_record["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            await conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp_record["id"],))
            await conn.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kodni 1 minutdan so'ng kiritdingiz — muddat o'tdi, yangitdan urining!"
            )

        if otp_record["code"] != req.otp.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kiritilgan tasdiqlash kodi noto'g'ri!"
            )

        # Kodni ishlatildi deb belgilash
        await conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp_record["id"],))

        # Foydalanuvchini olish
        cursor = await conn.execute("SELECT * FROM users WHERE telegram_id = ?", (req.telegram_id,))
        user = await cursor.fetchone()

        await conn.commit()

        # Token yaratish (PyJWT talabiga ko'ra 'sub' satr bo'lishi shart)
        token = create_access_token({
            "sub": str(user["id"]),
            "telegram_id": user["telegram_id"],
            "role": user["role"],
            "full_name": user["full_name"]
        })

        # Kompaniya nomini olish
        if user["role"] == "DEVELOPER":
            comp_id = 0
            comp_name = "SaaS Platforma"
            comp_plan = "PLATFORM"
            comp_expires_at = None
        else:
            comp_id = user["company_id"] if ("company_id" in user.keys() and user["company_id"]) else 1
            cur_c = await conn.execute("SELECT name, plan, subscription_expires_at, is_active FROM companies WHERE id = ?", (comp_id,))
            comp = await cur_c.fetchone()
            comp_name = comp["name"] if comp else "Bosh Tashkilot"
            comp_plan = comp["plan"] if comp else "STANDARD"
            comp_expires_at = comp["subscription_expires_at"] if comp else None

        dev_id_val = int(DEVELOPER_ID) if DEVELOPER_ID and DEVELOPER_ID.isdigit() else 8694797293
        is_super_admin = (int(user["telegram_id"]) == dev_id_val or user["role"] == "DEVELOPER")

        return {
            "success": True,
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "company_id": comp_id,
                "company_name": comp_name,
                "company_plan": comp_plan,
                "company_subscription_expires_at": comp_expires_at,
                "telegram_id": user["telegram_id"],
                "full_name": user["full_name"],
                "role": user["role"],
                "debt_amount": user["debt_amount"],
                "shift_status": user["shift_status"] if ("shift_status" in user.keys() and user["shift_status"]) else "WORKING",
                "is_super_admin": is_super_admin
            }
        }

@router.post("/device/verify-or-bind")
async def verify_or_bind_device(
    req: DeviceVerifyOrBindRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Qurilmani tekshirish va biriktirish (Device Binding & Hardware Token Verification).
    Xodimning hisobini uning haqiqiy telefon apparatiga mixlab qo'yadi.
    Boshqa qurilmadan (masalan, ikkinchi telefondan) kirishga urinishlarni avtomatik bloklaydi.
    """
    user_id = current_user["id"]
    role = current_user.get("role")

    # Rahbarlar va Dasturchilar uchun qurilma cheklovi talab etilmaydi
    if role in ("ADMIN", "DEVELOPER"):
        return {
            "success": True,
            "is_trusted": True,
            "is_admin": True,
            "device_name": "Rahbar qurilmasi",
            "message": "Rahbar uchun apparat cheklovi qo'yilmaydi."
        }

    async with get_db_connection() as conn:
        cur = await conn.execute("""
            SELECT id, full_name, telegram_id, company_id,
                   bound_device_token, bound_device_name, device_bound_at, allow_device_reset
            FROM users WHERE id = ?
        """, (user_id,))
        u = await cur.fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

        bound_token = u["bound_device_token"]
        allow_reset = bool(u["allow_device_reset"])
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1. Birinchi marta ulanayotgan bo'lsa YOKI Rahbar yangi telefon biriktirishga ruxsat bergan bo'lsa:
        if not bound_token or allow_reset:
            import secrets
            new_device_token = secrets.token_hex(32) # 64-belgili apparat maxfiy kaliti
            dev_name = (req.device_name or "Mobil telefon").strip()[:100]

            await conn.execute("""
                UPDATE users 
                SET bound_device_token = ?,
                    bound_device_name = ?,
                    device_bound_at = ?,
                    allow_device_reset = 0
                WHERE id = ?
            """, (new_device_token, dev_name, now_utc, user_id))

            details = f"Xodim '{u['full_name']}' ga yangi apparat ({dev_name}) muhrlab biriktirildi."
            await conn.execute("""
                INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
                VALUES (?, 'DEVICE', ?, 'BIND_DEVICE', ?, ?)
            """, (u["company_id"] or 1, user_id, u["full_name"], details))
            await conn.commit()

            return {
                "success": True,
                "is_trusted": True,
                "action": "BOUND",
                "device_token": new_device_token,
                "device_name": dev_name,
                "message": f"Ushbu qurilma ({dev_name}) rasmiy telefoningiz sifatida muvaffaqiyatli biriktirildi!"
            }

        # 2. Qurilma allaqachon biriktirilgan bo'lsa, xotiradagi token solishtiriladi:
        incoming_token = req.device_token.strip() if req.device_token else ""
        if incoming_token and incoming_token == bound_token:
            return {
                "success": True,
                "is_trusted": True,
                "action": "VERIFIED",
                "device_token": bound_token,
                "device_name": u["bound_device_name"] or "Tasdiqlangan telefon",
                "message": "Qurilma tasdiqlangan."
            }
        else:
            dev_name_orig = u["bound_device_name"] or "Boshqa telefon"
            incoming_dev = (req.device_name or "Mobil telefon").strip()[:100]

            try:
                import asyncio
                from app.bot import send_untrusted_device_alert_to_admin
                asyncio.create_task(send_untrusted_device_alert_to_admin(
                    company_id=u["company_id"] or 1,
                    employee_name=u["full_name"],
                    employee_tg_id=u["telegram_id"],
                    bound_device=dev_name_orig,
                    attempted_device=incoming_dev
                ))
            except Exception:
                pass

            return {
                "success": False,
                "is_trusted": False,
                "action": "REJECTED",
                "error_code": "UNTRUSTED_DEVICE",
                "bound_device_name": dev_name_orig,
                "message": f"⛔ DIQQAT: Begona qurilma aniqlandi! Tizimga faqat sizning rasmiy ro'yxatdan o'tgan telefoningiz ({dev_name_orig}) orqali kirish mumkin. Yangi telefon biriktirish uchun Rahbaringizga murojaat qiling."
            }

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {
        "success": True,
        "user": {
            "id": user["id"],
            "company_id": user.get("company_id", 1),
            "company_name": user.get("company_name", "Bosh Tashkilot"),
            "company_plan": user.get("company_plan", "STANDARD"),
            "company_subscription_expires_at": user.get("company_subscription_expires_at"),
            "telegram_id": user["telegram_id"],
            "full_name": user["full_name"],
            "role": user["role"],
            "debt_amount": user["debt_amount"],
            "shift_status": user.get("shift_status") or "WORKING",
            "is_super_admin": user.get("is_super_admin", False)
        }
    }
