import asyncio
import logging
from datetime import datetime, timedelta, timezone
import aiosqlite
from app.config import DB_PATH
from app.security import get_tashkent_now

logger = logging.getLogger("data_retention")

RETENTION_DAYS = 90

async def run_data_retention_cleanup(retention_days: int = RETENTION_DAYS) -> dict:
    """
    90 kunlik ma'lumotlar saqlash siyosati (Rolling 90-Day Retention Policy):
    Tizimdagi 90 kundan eski bo'lgan barcha operatsiya va tarix ma'lumotlari avtomatik o'chiriladi.
    Yangi ma'lumotlar yozilib boriladi.
    
    O'chiriladigan jadvallar:
    1. card_topups (Karta to'ldirishlar tarixi)
    2. given_amounts (Berilgan summalar tarixi)
    3. daily_reports (Kunlik hisobotlar tarixi)
    4. cashier_handovers (Kassa topshirishlar tarixi)
    5. cashier_history (Kassir tayinlash tarixi)
    6. otp_codes (Eski OTP kodlar tarixi)
    7. sim_cards (Faqat 'SOLD' sotilgan sim-kartalar, 'GIVEN' qoldiqlar saqlanadi!)
    8. sim_distributions (Eski partiyalar tarixi)
    9. audit_logs (Audit jurnali)
    """
    now_tashkent = get_tashkent_now()
    cutoff_date = (now_tashkent - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    cutoff_datetime_tashkent = (now_tashkent - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_utc_datetime = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")

    deleted_counts = {}
    total_deleted = 0

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. card_topups (created_at UTC yoki Tashkent vaqti bilan tekshirish)
        cur = await conn.execute(
            "DELETE FROM card_topups WHERE created_at < ? OR DATETIME(created_at, '+5 hours') < ?",
            (cutoff_utc_datetime, cutoff_datetime_tashkent)
        )
        deleted_counts["card_topups"] = cur.rowcount
        total_deleted += cur.rowcount

        # 2. given_amounts
        cur = await conn.execute(
            "DELETE FROM given_amounts WHERE created_at < ? OR DATETIME(created_at, '+5 hours') < ?",
            (cutoff_utc_datetime, cutoff_datetime_tashkent)
        )
        deleted_counts["given_amounts"] = cur.rowcount
        total_deleted += cur.rowcount

        # 3. daily_reports (report_date 'YYYY-MM-DD' va created_at)
        cur = await conn.execute(
            "DELETE FROM daily_reports WHERE report_date < ? OR created_at < ?",
            (cutoff_date, cutoff_utc_datetime)
        )
        deleted_counts["daily_reports"] = cur.rowcount
        total_deleted += cur.rowcount

        # 4. cashier_handovers (handover_date 'YYYY-MM-DD' va created_at)
        cur = await conn.execute(
            "DELETE FROM cashier_handovers WHERE handover_date < ? OR created_at < ?",
            (cutoff_date, cutoff_utc_datetime)
        )
        deleted_counts["cashier_handovers"] = cur.rowcount
        total_deleted += cur.rowcount

        # 5. cashier_history
        cur = await conn.execute(
            "DELETE FROM cashier_history WHERE created_at < ?",
            (cutoff_utc_datetime,)
        )
        deleted_counts["cashier_history"] = cur.rowcount
        total_deleted += cur.rowcount

        # 6. otp_codes (90 kundan eski yoki muddati o'tib ketganlar)
        cur = await conn.execute(
            "DELETE FROM otp_codes WHERE created_at < ? OR expires_at < CURRENT_TIMESTAMP",
            (cutoff_utc_datetime,)
        )
        deleted_counts["otp_codes"] = cur.rowcount
        total_deleted += cur.rowcount

        # 7. sim_cards (Faqat 'SOLD' bo'lgan va 90 kundan oshganlar. 'GIVEN' - xodim qo'lidagi qoldiqlar saqlanadi!)
        cur = await conn.execute("""
            DELETE FROM sim_cards 
            WHERE status = 'SOLD' 
              AND (
                  (sold_at IS NOT NULL AND (sold_at < ? OR DATETIME(sold_at, '+5 hours') < ?))
                  OR (sold_at IS NULL AND (distributed_at < ? OR DATETIME(distributed_at, '+5 hours') < ?))
              )
        """, (cutoff_utc_datetime, cutoff_datetime_tashkent, cutoff_utc_datetime, cutoff_datetime_tashkent))
        deleted_counts["sim_cards"] = cur.rowcount
        total_deleted += cur.rowcount

        # 8. sim_distributions
        cur = await conn.execute(
            "DELETE FROM sim_distributions WHERE created_at < ? OR DATETIME(created_at, '+5 hours') < ?",
            (cutoff_utc_datetime, cutoff_datetime_tashkent)
        )
        deleted_counts["sim_distributions"] = cur.rowcount
        total_deleted += cur.rowcount

        # 9. audit_logs (Eski audit loglarni tozalash)
        cur = await conn.execute(
            "DELETE FROM audit_logs WHERE created_at < ? OR DATETIME(created_at, '+5 hours') < ?",
            (cutoff_utc_datetime, cutoff_datetime_tashkent)
        )
        deleted_counts["audit_logs"] = cur.rowcount
        total_deleted += cur.rowcount

        # Audit logga tozalash natijasi yoziladi
        log_detail = (
            f"90 kunlik siyosat bo'yicha tarix ma'lumotlari tozalandi. "
            f"Jami o'chirildi: {total_deleted} ta yozuv. Chegara: {cutoff_date}"
        )
        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('SYSTEM', 0, 'DATA_RETENTION_CLEANUP', 'Tizim (Avtomatik)', ?)
        """, (log_detail,))

        # Xotirani optimallashtirish (reclaim free pages)
        try:
            await conn.execute("PRAGMA optimize;")
        except Exception:
            pass

        await conn.commit()

    logger.info(f"Retention tozalash yakunlandi: {total_deleted} ta yozuv o'chirildi. {deleted_counts}")

    return {
        "success": True,
        "retention_days": retention_days,
        "cutoff_date": cutoff_date,
        "deleted_counts": deleted_counts,
        "total_deleted": total_deleted,
        "executed_at": now_tashkent.strftime("%Y-%m-%d %H:%M:%S")
    }


async def get_retention_stats(retention_days: int = RETENTION_DAYS) -> dict:
    """Ma'lumotlar saqlanishi holati va statistikasini olish"""
    now_tashkent = get_tashkent_now()
    cutoff_date = (now_tashkent - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    cutoff_utc_datetime = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")

    stats = {}
    tables = [
        ("card_topups", "created_at"),
        ("given_amounts", "created_at"),
        ("daily_reports", "report_date"),
        ("cashier_handovers", "handover_date"),
        ("cashier_history", "created_at"),
        ("audit_logs", "created_at"),
        ("sim_cards", "distributed_at"),
        ("sim_distributions", "created_at")
    ]

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        for table, date_col in tables:
            cur_total = await conn.execute(f"SELECT COUNT(*) as cnt, MIN({date_col}) as oldest, MAX({date_col}) as newest FROM {table}")
            row_total = await cur_total.fetchone()
            
            # 90 kundan eskilar soni
            check_cutoff = cutoff_date if date_col in ["report_date", "handover_date"] else cutoff_utc_datetime
            cur_expired = await conn.execute(f"SELECT COUNT(*) as cnt FROM {table} WHERE {date_col} < ?", (check_cutoff,))
            row_expired = await cur_expired.fetchone()

            stats[table] = {
                "total_rows": row_total["cnt"] if row_total else 0,
                "expired_rows": row_expired["cnt"] if row_expired else 0,
                "oldest_record": row_total["oldest"] if row_total else None,
                "newest_record": row_total["newest"] if row_total else None,
            }

    return {
        "success": True,
        "retention_days": retention_days,
        "cutoff_date": cutoff_date,
        "stats": stats,
        "current_time": now_tashkent.strftime("%Y-%m-%d %H:%M:%S")
    }


async def send_daily_digest_for_all_companies():
    """Barcha faol kompaniyalar uchun kechki yakuniy svodkani avtomatik yuborish"""
    from app.bot import send_daily_digest_for_company
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT id, name FROM companies WHERE is_active = 1")
            comps = await cur.fetchall()

        for c in comps:
            try:
                await send_daily_digest_for_company(c["id"])
                await asyncio.sleep(1.0)  # Telegram flood control
            except Exception as e:
                logger.warning(f"Kompaniya {c['id']} svodkasida xatolik: {e}")
    except Exception as e:
        logger.error(f"send_daily_digest_for_all_companies xatolik: {e}")

async def check_and_send_expiry_alerts_all():
    """Obunasi 3 kun yoki 1 kun qolgan firmalarga ogohlantirish yuborish"""
    from app.bot import send_subscription_expiry_alert
    from app.routes.saas import calculate_days_left
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT id, name, plan, subscription_expires_at FROM companies WHERE is_active = 1 AND plan != 'UNLIMITED'")
            comps = await cur.fetchall()

        for c in comps:
            days_left = calculate_days_left(c["plan"], c["subscription_expires_at"])
            if days_left in [1, 2, 3]:
                try:
                    await send_subscription_expiry_alert(c["id"], days_left)
                    await asyncio.sleep(1.0)
                except Exception as e:
                    logger.warning(f"Kompaniya {c['id']} obuna ogohlantirishida xatolik: {e}")
    except Exception as e:
        logger.error(f"check_and_send_expiry_alerts_all xatolik: {e}")

async def start_retention_scheduler(interval_hours: int = 24):
    """Fonda har daqiqada tekshirib, Toshkent vaqti bilan kerakli soatlarda vazifalarni bajaruvchi fon jarayoni"""
    logger.info("Markaziy fon scheduleri (Retention, Digest, Obuna ogohlantirishi) ishga tushdi.")
    last_digest_date = None
    last_expiry_check_date = None
    last_retention_date = None

    while True:
        try:
            now_t = get_tashkent_now()
            today_str = now_t.strftime("%Y-%m-%d")

            # 1. Soat 20:00 da kunlik svodka
            if now_t.hour == 20 and now_t.minute >= 0 and last_digest_date != today_str:
                last_digest_date = today_str
                logger.info("Kechki 20:00 avtomatik kunlik hisobot svodkasi vazifasi boshlandi...")
                asyncio.create_task(send_daily_digest_for_all_companies())

            # 2. Soat 10:00 da obuna ogohlantirishlari
            if now_t.hour == 10 and now_t.minute >= 0 and last_expiry_check_date != today_str:
                last_expiry_check_date = today_str
                logger.info("Ertalabki 10:00 obuna muddati ogohlantirishlari vazifasi boshlandi...")
                asyncio.create_task(check_and_send_expiry_alerts_all())

            # 3. Soat 03:00 da 90 kunlik tozalash
            if now_t.hour == 3 and now_t.minute >= 0 and last_retention_date != today_str:
                last_retention_date = today_str
                logger.info("Tungi 03:00 ma'lumotlar saqlanish tozalashi boshlandi...")
                asyncio.create_task(run_data_retention_cleanup())

            # Har 30 soniyada tekshirish
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            logger.info("Fon scheduleri to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Fon schedulerida kutilmagan xatolik: {e}")
            await asyncio.sleep(30)
