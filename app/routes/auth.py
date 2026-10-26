from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, status
import aiosqlite
from app.config import DB_PATH, OTP_EXPIRATION_SECONDS, DEBUG, BOT_USERNAME
from app.models import LoginRequest, VerifyOtpRequest
from app.security import verify_password, generate_otp, create_access_token
from app.bot import send_otp_to_telegram
from app.dependencies import get_current_user
from fastapi import Depends

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.post("/login")
async def login(req: LoginRequest):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
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

        return {
            "success": True,
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "telegram_id": user["telegram_id"],
                "full_name": user["full_name"],
                "role": user["role"],
                "debt_amount": user["debt_amount"]
            }
        }

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {
        "success": True,
        "user": {
            "id": user["id"],
            "telegram_id": user["telegram_id"],
            "full_name": user["full_name"],
            "role": user["role"],
            "debt_amount": user["debt_amount"]
        }
    }
