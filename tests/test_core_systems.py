"""
XodimKPI CRM - Asosiy Arxitektura va Xavfsizlik Sinovlari (Core Systems Test Suite)
Hech qanday qo'shimcha paket talab qilmaydi, standart Python kutubxonasida ishlaydi.
"""

import unittest
import asyncio
import aiosqlite
from app.config import DB_PATH
from app.database import init_db
from app.dependencies import get_current_user, invalidate_user_cache, _USER_CACHE
from app.security import create_access_token
from app.retention import get_retention_stats, run_data_retention_cleanup
from fastapi.security import HTTPAuthorizationCredentials

class TestCoreSystems(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()

    async def test_01_db_and_unique_indexes(self):
        """1. Baza initsializatsiyasi va Unique indekslar mavjudligi tekshiruvi"""
        async with aiosqlite.connect(DB_PATH) as conn:
            cur = await conn.execute("PRAGMA index_list('cashier_handovers')")
            indexes = [r[1] for r in await cur.fetchall()]
            self.assertIn("uq_cashier_handovers_emp_date", indexes, "uq_cashier_handovers_emp_date indeksi mavjud bo'lishi shart!")

            cur2 = await conn.execute("PRAGMA index_list('daily_reports')")
            indexes2 = [r[1] for r in await cur2.fetchall()]
            self.assertIn("uq_daily_reports_emp_date", indexes2, "uq_daily_reports_emp_date indeksi mavjud bo'lishi shart!")

    async def test_02_auth_in_memory_cache(self):
        """2. Auth keshining ishlashi va invalidation tekshiruvi"""
        token = create_access_token({"sub": "4"})
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        # 1-so'rov (keshlanishi kerak)
        u1 = await get_current_user(creds)
        self.assertIsNotNone(u1)
        self.assertIn(4, _USER_CACHE)

        # 2-so'rov (keshdan olinishi kerak)
        u2 = await get_current_user(creds)
        self.assertEqual(u1["id"], u2["id"])

        # Keshni tozalash
        invalidate_user_cache(4)
        self.assertNotIn(4, _USER_CACHE)

    async def test_03_location_events_in_retention(self):
        """3. location_events jadvalining Retention tozalash ro'yxatida borligi"""
        stats = await get_retention_stats()
        self.assertIn("location_events", stats["stats"], "location_events statistikada bo'lishi shart!")

        cleanup = await run_data_retention_cleanup(retention_days=90)
        self.assertTrue(cleanup["success"])
        self.assertIn("location_events", cleanup["deleted_counts"])

    async def test_04_cashier_handover_race_condition_prevention(self):
        """4. Bitta kunda bir xodimga 2 marta kassa topshirishga urinishda Unique cheklov ishlashi"""
        test_date = "2029-12-31"
        comp_id = 1
        cashier_id = 5
        emp_id = 16

        async with aiosqlite.connect(DB_PATH) as conn:
            # Tozalash
            await conn.execute(
                "DELETE FROM cashier_handovers WHERE company_id = ? AND employee_id = ? AND handover_date = ?",
                (comp_id, emp_id, test_date)
            )
            await conn.commit()

            # 1-marta muvaffaqiyatli qo'shish
            await conn.execute("""
                INSERT INTO cashier_handovers (company_id, cashier_id, employee_id, handover_date, amount, amount_uzs, amount_usd, usd_rate)
                VALUES (?, ?, ?, ?, 100000, 100000, 0, 12000)
            """, (comp_id, cashier_id, emp_id, test_date))
            await conn.commit()

            # 2-marta o'sha sanada qo'shish IntegrityError (UniqueViolation) berishi shart!
            with self.assertRaises(Exception):
                await conn.execute("""
                    INSERT INTO cashier_handovers (company_id, cashier_id, employee_id, handover_date, amount, amount_uzs, amount_usd, usd_rate)
                    VALUES (?, ?, ?, ?, 200000, 200000, 0, 12000)
                """, (comp_id, cashier_id, emp_id, test_date))
                await conn.commit()

            # Tozalash
            await conn.execute(
                "DELETE FROM cashier_handovers WHERE company_id = ? AND employee_id = ? AND handover_date = ?",
                (comp_id, emp_id, test_date)
            )
            await conn.commit()

if __name__ == "__main__":
    unittest.main()
