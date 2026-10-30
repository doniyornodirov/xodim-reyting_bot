import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.bot import start_bot_polling, bot
from app.config import CORS_ORIGINS
from app.routes import auth, cards, given, reports, cashier, admin, rating, sim_cards, settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app_main")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Baza sxemasini tekshirish va ishga tushirish
    logger.info("Ma'lumotlar bazasi initsializatsiya qilinmoqda...")
    await init_db()
    
    # 2. Telegram Bot Pollingni fonda ishga tushirish
    bot_task = None
    if bot:
        logger.info("Telegram Bot Polling boshlanmoqda...")
        bot_task = asyncio.create_task(start_bot_polling())
    else:
        logger.warning("BOT_TOKEN ko'rsatilmagan, Telegram bot fonda ishlamaydi (Web CRM lokal rejimda ishlaydi).")

    # 3. 90 kunlik tarix ma'lumotlarini tozalash va fon schedulerni ishga tushirish
    from app.retention import run_data_retention_cleanup, start_retention_scheduler
    retention_task = None
    try:
        logger.info("90 kunlik ma'lumotlar saqlanish siyosati (Retention) bo'yicha tozalash tekshirilmoqda...")
        cleanup_res = await run_data_retention_cleanup(retention_days=90)
        logger.info(f"Retention tozalash yakunlandi: {cleanup_res['total_deleted']} ta eski yozuv tozalandi.")
    except Exception as e:
        logger.error(f"Retention tozalashda xatolik: {e}")

    retention_task = asyncio.create_task(start_retention_scheduler(interval_hours=24))

    yield

    if bot_task:
        bot_task.cancel()
    if retention_task:
        retention_task.cancel()

app = FastAPI(
    title="Xodim-Reyting & Paynet CRM",
    description="Telegram Bot bilan integratsiyalashgan yuqori yuklamaga chidamli Paynet va xodimlar reytingi tizimi",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Docker, Railway va monitoring uchun health check endpoint"""
    return {"status": "ok", "app": "Xodim-Reyting CRM"}

# API routerlarini ulash
app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(given.router)
app.include_router(reports.router)
app.include_router(cashier.router)
app.include_router(admin.router)
app.include_router(rating.router)
app.include_router(sim_cards.router)
app.include_router(settings.router)

# Statik fayllarni ulash
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/manifest.json")
async def manifest():
    manifest_file = STATIC_DIR / "manifest.json"
    if manifest_file.exists():
        return FileResponse(manifest_file, media_type="application/manifest+json")
    return {"error": "manifest.json topilmadi"}

@app.get("/sw.js")
async def service_worker():
    sw_file = STATIC_DIR / "sw.js"
    if sw_file.exists():
        return FileResponse(
            sw_file,
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"}
        )
    return {"error": "sw.js topilmadi"}

@app.get("/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Xodim-Reyting CRM API ishlamoqda. static/index.html topilmadi."}

