import secrets
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from app.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_MINUTES

# Toshkent vaqt mintaqasi (UTC+5)
TASHKENT_TZ = timezone(timedelta(hours=5))

def get_tashkent_now() -> datetime:
    return datetime.now(TASHKENT_TZ)

def get_tashkent_today_str() -> str:
    return get_tashkent_now().strftime("%Y-%m-%d")

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def generate_otp() -> str:
    """6 xonali xavfsiz tasodifiy OTP kod"""
    return f"{secrets.randbelow(900000) + 100000}"

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
