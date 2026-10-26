import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "xodimreyting_bot").strip().lstrip("@")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID", "").strip()
RAHBAR_ID = os.getenv("RAHBAR_ID", "8686341550").strip()
JWT_SECRET = os.getenv("JWT_SECRET", "super_secret_jwt_key_xodim_reyting_2026_xyz")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60 * 24  # 24 soat
OTP_EXPIRATION_SECONDS = 60  # 1 daqiqa
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
DB_PATH = BASE_DIR / "xodim_reyting.db"
TIMEZONE = "Asia/Tashkent"

# Bulutli baza (Supabase / Managed PostgreSQL) yoki SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Vercel va boshqa tashqi frontend domenlari uchun CORS
cors_raw = os.getenv("CORS_ORIGINS", "*").strip()
CORS_ORIGINS = [orig.strip() for orig in cors_raw.split(",") if orig.strip()] if cors_raw != "*" else ["*"]
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000").strip()

