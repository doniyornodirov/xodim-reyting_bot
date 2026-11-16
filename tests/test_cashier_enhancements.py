import unittest
import asyncio
from datetime import datetime, timedelta
from app.database import init_db, get_db_connection
from app.routes.cashier import get_active_employees, record_handover, get_my_handovers
from app.models import CashierHandoverCreate
from app.security import get_tashkent_today_str

class TestCashierEnhancements(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.comp_id = 1
        self.cashier_id = 880
        self.cashier_user = {
            "id": self.cashier_id,
            "company_id": 1,
            "full_name": "Test Kassir",
            "role": "CASHIER",
            "shift_status": "WORKING"
        }
        self.emp1_id = 881
        self.emp2_id = 882

        async with get_db_connection() as conn:
            # Test xodimlar yaratish
            await conn.execute("DELETE FROM users WHERE id IN (?, ?, ?)", (self.cashier_id, self.emp1_id, self.emp2_id))
            await conn.execute("DELETE FROM cashier_handovers WHERE employee_id IN (?, ?)", (self.emp1_id, self.emp2_id))
            await conn.execute("DELETE FROM daily_reports WHERE employee_id IN (?, ?)", (self.emp1_id, self.emp2_id))

            await conn.execute("""
                INSERT INTO users (id, company_id, telegram_id, full_name, role, password_hash, shift_status, is_active)
                VALUES (?, 1, 998800, 'Test Kassir', 'CASHIER', 'pwd', 'WORKING', 1)
            """, (self.cashier_id,))
            await conn.execute("""
                INSERT INTO users (id, company_id, telegram_id, full_name, role, password_hash, shift_status, is_active)
                VALUES (?, 1, 998811, 'Faol Xodim 1', 'EMPLOYEE', 'pwd', 'WORKING', 1)
            """, (self.emp1_id,))
            await conn.execute("""
                INSERT INTO users (id, company_id, telegram_id, full_name, role, password_hash, shift_status, is_active)
                VALUES (?, 1, 998822, 'Damdagi Xodim 2', 'EMPLOYEE', 'pwd', 'RESTING', 1)
            """, (self.emp2_id,))
            await conn.commit()

    async def asyncTearDown(self):
        async with get_db_connection() as conn:
            await conn.execute("DELETE FROM cashier_handovers WHERE employee_id IN (?, ?)", (self.emp1_id, self.emp2_id))
            await conn.execute("DELETE FROM daily_reports WHERE employee_id IN (?, ?)", (self.emp1_id, self.emp2_id))
            await conn.execute("DELETE FROM users WHERE id IN (?, ?, ?)", (self.cashier_id, self.emp1_id, self.emp2_id))
            await conn.commit()

    async def test_01_resting_employee_excluded_from_cashier_list(self):
        """1. Damga chiqarilgan xodim (shift_status = 'RESTING') kassirning ro'yxatida chiqmasligi kerak"""
        res = await get_active_employees(date=None, user=self.cashier_user)
        emp_ids = [e["id"] for e in res["data"]]
        self.assertIn(self.emp1_id, emp_ids, "Faol (WORKING) xodim ro'yxatda bo'lishi kerak")
        self.assertNotIn(self.emp2_id, emp_ids, "Damdagi (RESTING) xodim ro'yxatda chiqmasligi kerak!")

    async def test_02_cashier_handover_with_custom_date_and_delay(self):
        """2. Kassir xodimdan kechiktirilgan kassa uchun sanani tanlab qabul qilishi va tekshiruvi"""
        today_str = get_tashkent_today_str()
        yesterday_str = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

        # Kechiktirilgan sana (kecha) uchun kassa topshirish
        req = CashierHandoverCreate(
            employee_id=self.emp1_id,
            handover_date=yesterday_str,
            amount_uzs=500000,
            amount_usd=0,
            usd_rate=12000,
            idempotency_key=f"test-handover-{yesterday_str}"
        )
        res = await record_handover(req, self.cashier_user)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["handover_date"], yesterday_str)

        # Kecha uchun xodim ro'yxatdan chiqib ketishi kerak
        res_yesterday = await get_active_employees(date=yesterday_str, user=self.cashier_user)
        yest_ids = [e["id"] for e in res_yesterday["data"]]
        self.assertNotIn(self.emp1_id, yest_ids, "Kecha uchun topshirib bo'lgan xodim kechagi ro'yxatda bo'lmasligi kerak")

        # Lekin BUGUNGI kun uchun xodim hali topshirmagan, bugungi ro'yxatda chiqishi shart!
        res_today = await get_active_employees(date=today_str, user=self.cashier_user)
        today_ids = [e["id"] for e in res_today["data"]]
        self.assertIn(self.emp1_id, today_ids, "Bugun uchun hali topshirmagan xodim bugungi ro'yxatda chiqishi shart!")

    async def test_03_persistent_history_and_today_indicator(self):
        """3. Kassa tarixi kunlik emas doimiy saqlanishi va 1 kunlik indikator to'g'ri hisoblanishi"""
        today_str = get_tashkent_today_str()
        yesterday_str = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

        # Kecha: 500 000 so'm topshirildi
        req1 = CashierHandoverCreate(
            employee_id=self.emp1_id,
            handover_date=yesterday_str,
            amount_uzs=500000,
            amount_usd=0,
            idempotency_key="key-yest-1"
        )
        await record_handover(req1, self.cashier_user)

        # Bugun: 1 000 000 so'm + 100 $ topshirildi (kurs: 12 000 -> 1 200 000 so'm, jami 2 200 000 so'm)
        req2 = CashierHandoverCreate(
            employee_id=self.emp1_id,
            handover_date=today_str,
            amount_uzs=1000000,
            amount_usd=100,
            idempotency_key="key-today-1"
        )
        await record_handover(req2, self.cashier_user)

        # Tarixni olish
        res = await get_my_handovers(date=None, user=self.cashier_user)
        self.assertTrue(res["success"])
        data = res["data"]

        # Kechagi ham, bugungi ham ro'yxatda ko'rinishi shart (kunlik emas har doimgi tarix!)
        self.assertGreaterEqual(len(data), 2)
        dates = [d["handover_date"] for d in data]
        self.assertIn(yesterday_str, dates)
        self.assertIn(today_str, dates)

        # 1 kunlik (bugungi) indikator
        summary = res["summary"]
        self.assertGreaterEqual(summary["today_total"], 2000000)
        self.assertGreaterEqual(summary["today_uzs"], 1000000)
        self.assertGreaterEqual(summary["today_usd"], 100)
        self.assertGreaterEqual(summary["today_count"], 1)

        # Barcha davr indikatori (bugun + kecha)
        self.assertGreaterEqual(summary["all_total"], summary["today_total"])

    async def test_04_duplicate_handover_same_day_blocked(self):
        """4. 1 kunga 1 marta kassa qabul qilinadi, takroriy qabul qilish bloklanishi shart"""
        from fastapi import HTTPException
        today_str = get_tashkent_today_str()

        # 1-marta topshirish: muvaffaqiyatli
        req1 = CashierHandoverCreate(
            employee_id=self.emp1_id,
            handover_date=today_str,
            amount_uzs=300000,
            amount_usd=0,
            idempotency_key="unique-handover-1"
        )
        res1 = await record_handover(req1, self.cashier_user)
        self.assertTrue(res1["success"])

        # 2-marta shu kunga yana topshirishga urinish: HTTPException(400) berishi shart!
        req2 = CashierHandoverCreate(
            employee_id=self.emp1_id,
            handover_date=today_str,
            amount_uzs=200000,
            amount_usd=0,
            idempotency_key="unique-handover-2"
        )
        with self.assertRaises(HTTPException) as cm:
            await record_handover(req2, self.cashier_user)

        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("allaqachon qabul qilingan", cm.exception.detail)
        self.assertIn("1 marta", cm.exception.detail)

        # get_active_employees tekshiruvi: emp1 'already_handed_over' ichida bo'lishi kerak
        emp_res = await get_active_employees(date=today_str, user=self.cashier_user)
        pending_ids = [e["id"] for e in emp_res["data"]]
        already_ids = [e["id"] for e in emp_res.get("already_handed_over", [])]
        self.assertNotIn(self.emp1_id, pending_ids)
        self.assertIn(self.emp1_id, already_ids)

    async def test_05_cashier_today_indicator_includes_delayed_handovers_received_today(self):
        """5. Boshqa kun uchun qabul qilingan kassa bugun olingan bo'lsa, bugungi indikator hisobiga kirishi shart"""
        today_str = get_tashkent_today_str()
        three_days_ago = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=3)).strftime("%Y-%m-%d")

        # 3 kun oldingi sana uchun bugun kassa qabul qilish
        req = CashierHandoverCreate(
            employee_id=self.emp1_id,
            handover_date=three_days_ago,
            amount_uzs=750000,
            amount_usd=50,
            usd_rate=12000,
            idempotency_key="delayed-received-today"
        )
        res = await record_handover(req, self.cashier_user)
        self.assertTrue(res["success"])

        # Kassir panelidagi bugungi indikatorni tekshirish
        handovers = await get_my_handovers(date=None, user=self.cashier_user)
        summary = handovers["summary"]

        # Jami summa = 750000 + 50*rate >= 1 250 000 so'm
        self.assertGreaterEqual(summary["today_total"], 1250000, "Bugun qabul qilingan kassa boshqa sana uchun bo'lsa ham, bugungi indikatorga kirishi kerak!")
        self.assertGreaterEqual(summary["today_uzs"], 750000)
        self.assertGreaterEqual(summary["today_usd"], 50)

if __name__ == "__main__":
    unittest.main()
