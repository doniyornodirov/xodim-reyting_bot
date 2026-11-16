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
from app.services.analytics_service import invalidate_analytics_cache
from fastapi.security import HTTPAuthorizationCredentials

class TestCoreSystems(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        from app.services.analytics_service import invalidate_analytics_cache
        invalidate_analytics_cache()

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

    async def test_05_bot_start_handlers(self):
        """5. Telegram bot /start komandasi barcha rollar uchun javob berishi tekshiruvi"""
        from unittest.mock import AsyncMock, MagicMock
        from app.bot import handle_start

        for uid, name in [
            (8686341550, "Bosh Rahbar"),
            (8694797293, "Dasturchi Admin"),
            (8662254493, "Doniyor operator"),
            (9999999999, "Yangi Mehmon")
        ]:
            msg = MagicMock()
            msg.from_user.id = uid
            msg.from_user.full_name = name
            msg.answer = AsyncMock()
            await handle_start(msg)
            self.assertTrue(msg.answer.called, f"{name} uchun javob berilishi shart!")

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

    async def test_05_bot_start_handlers(self):
        """5. Telegram bot /start komandasi barcha rollar uchun javob berishi tekshiruvi"""
        from unittest.mock import AsyncMock, MagicMock
        from app.bot import handle_start

        for uid, name in [
            (8686341550, "Bosh Rahbar"),
            (8694797293, "Dasturchi Admin"),
            (8662254493, "Doniyor operator"),
            (9999999999, "Yangi Mehmon")
        ]:
            msg = MagicMock()
            msg.from_user.id = uid
            msg.from_user.full_name = name
            msg.answer = AsyncMock()
            await handle_start(msg)
            self.assertTrue(msg.answer.called, f"{name} uchun javob berilishi shart!")

    async def test_06_analytics_today_filter(self):
        """6. Savdo monitoringi bo'yicha 'today' davr filtri va xodim bo'yicha filtr tekshiruvi"""
        from app.routes.admin import get_sales_monitoring
        admin_user = {"id": 1, "role": "ADMIN", "company_id": 1}
        res = await get_sales_monitoring(period="today", admin=admin_user)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["summary"]["period"], "today")
        self.assertEqual(res["data"]["summary"]["days_count"], 1)
        self.assertEqual(len(res["data"]["timeline"]), 1)
        self.assertIn("employees", res["data"])

        # Xodim bo'yicha filtr tekshiruvi
        res_emp = await get_sales_monitoring(period="today", user_id=4, admin=admin_user)
        self.assertTrue(res_emp["success"])
        self.assertEqual(res_emp["data"]["selected_user_id"], 4)

    async def test_07_cancel_daily_report_and_reopen(self):
        """7. Rahbar tomonidan hisobotni bekor qilish va qayta topshirish uchun ochish tekshiruvi"""
        from app.routes.reports import cancel_daily_report
        from app.security import get_tashkent_today_str

        test_date = get_tashkent_today_str()
        comp_id = 1
        emp_id = 4
        admin_user = {"id": 1, "role": "ADMIN", "company_id": 1, "full_name": "Bosh Rahbar"}

        async with aiosqlite.connect(DB_PATH) as conn:
            # Sinov hisoboti kiritamiz
            cursor = await conn.execute("""
                INSERT INTO daily_reports (
                    company_id, employee_id, report_date, paynet, card_amount, leviy,
                    debt_snapshot, debt_paid, sim_cards_count, kunlik, terminal,
                    given_amount, skidka, xarajat, total_inflow, total_outflow,
                    net_amount, status
                ) VALUES (?, ?, ?, 100000, 50000, 0, 100000, 20000, 1, 0, 0, 0, 0, 0, 150000, 0, 150000, 'APPROVED')
            """, (comp_id, emp_id, test_date))
            rep_id = cursor.lastrowid
            await conn.commit()

        # Bekor qilish funksiyasini chaqiramiz
        res = await cancel_daily_report(rep_id, admin_user)
        self.assertTrue(res["success"])

        # Bazada holat CANCELLED bo'lganini tekshiramiz
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT status FROM daily_reports WHERE id = ?", (rep_id,))
            r = await cursor.fetchone()
            self.assertEqual(r["status"], "CANCELLED")

            # Tozalash
            await conn.execute("DELETE FROM daily_reports WHERE id = ?", (rep_id,))
            await conn.commit()

    async def test_08_notify_card_topup_with_closed_report(self):
        """8. Kassa yopilgan xodim uchun karta so'rovi yuborilganda bot xabari shakllanishi tekshiruvi"""
        from app.bot import notify_card_topup_in_group
        topup_data = {
            "id": 999,
            "transaction_number": 999,
            "employee_name": "Doniyor operator",
            "employee_tg_id": 8662254493,
            "card_number": "8756 5734 7565 8476",
            "card_holder": "DSOJV",
            "amount_formatted": "1 000 000",
            "surcharge_formatted": "1 030 000",
            "is_repeat_today": False,
            "has_approved_today": False,
            "has_closed_report_today": True
        }
        try:
            await notify_card_topup_in_group(topup_data)
        except Exception as e:
            self.fail(f"notify_card_topup_in_group kassa yopilgan xodim uchun xato berdi: {e}")

    async def test_09_cashier_reopens_on_report_cancel_and_resubmit(self):
        """9. Hisobot bekor qilinganda yoki qayta topshirilganda kassir uchun xodim qayta ochilishi tekshiruvi"""
        from app.routes.reports import cancel_daily_report
        from app.routes.cashier import get_active_employees
        from app.security import get_tashkent_today_str

        today_str = get_tashkent_today_str()
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            # Sinov xodimi va hisobot yaratish
            await conn.execute("INSERT OR REPLACE INTO users (id, company_id, telegram_id, full_name, role, password_hash, debt_amount, is_active) VALUES (888, 1, 888888, 'Kassir Sinov Xodim', 'EMPLOYEE', 'hash', 0, 1)")
            await conn.execute("INSERT OR REPLACE INTO daily_reports (id, company_id, employee_id, report_date, net_amount, status) VALUES (888, 1, 888, ?, 500000, 'APPROVED')", (today_str,))
            await conn.execute("INSERT OR REPLACE INTO cashier_handovers (id, company_id, cashier_id, employee_id, handover_date, amount, amount_uzs, amount_usd, usd_rate) VALUES (888, 1, 1, 888, ?, 500000, 500000, 0, 12000)", (today_str,))
            await conn.commit()

        # 1. Hozirda kassa topshirilgan bo'lgani uchun xodim ro'yxatda bo'lmasligi kerak
        cashier_user = {"id": 1, "company_id": 1, "role": "CASHIER", "full_name": "Kassir Test"}
        emp_res = await get_active_employees(user=cashier_user)
        active_ids = [e["id"] for e in emp_res["data"]]
        self.assertNotIn(888, active_ids)

        # 2. Rahbar hisobotni bekor qiladi
        admin_user = {"id": 1, "company_id": 1, "role": "ADMIN", "full_name": "Rahbar Test"}
        cancel_res = await cancel_daily_report(report_id=888, user=admin_user)
        self.assertTrue(cancel_res["success"])

        # 3. Endi kassir uchun xodim ro'yxatda paydo bo'lishi shart!
        emp_res_after = await get_active_employees(user=cashier_user)
        active_ids_after = [e["id"] for e in emp_res_after["data"]]
        self.assertIn(888, active_ids_after)

        # Tozalash
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("DELETE FROM cashier_handovers WHERE id = 888")
            await conn.execute("DELETE FROM daily_reports WHERE id = 888")
            await conn.execute("DELETE FROM users WHERE id = 888")
            await conn.commit()

    async def test_10_five_operator_sim_cards_and_monitoring(self):
        """10. 5 ta operator bo'yicha sim-karta sotuvi va Savdo monitoringida to'g'ri aks etishi tekshiruvi"""
        from app.models import DailyReportCreate
        from app.routes.reports import submit_daily_report
        from app.routes.admin import get_sales_monitoring
        from app.security import get_tashkent_today_str

        today_str = get_tashkent_today_str()
        test_user = {"id": 777, "company_id": 1, "role": "EMPLOYEE", "full_name": "Operator Test Xodim", "telegram_id": 777777}
        admin_user = {"id": 1, "company_id": 1, "role": "ADMIN", "full_name": "Admin Test"}

        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("DELETE FROM daily_reports WHERE employee_id = 777")
            await conn.execute("INSERT OR REPLACE INTO users (id, company_id, telegram_id, full_name, role, password_hash, debt_amount, is_active) VALUES (777, 1, 777777, 'Operator Test Xodim', 'EMPLOYEE', 'hash', 0, 1)")
            await conn.commit()

        # 1. 5 ta operator bo'yicha hisobot topshirish
        req = DailyReportCreate(
            report_date=today_str,
            paynet=100000,
            leviy=0,
            debt_paid=0,
            sim_cards_count=0,
            sim_uzmobile=4,
            sim_beeline=3,
            sim_ucell=2,
            sim_mobiuz=1,
            sim_perfectum=1,
            kunlik=20000,
            terminal=0,
            skidka=0,
            xarajat=0,
            comment="5 operator testi"
        )
        res = await submit_daily_report(req=req, user=test_user)
        self.assertTrue(res["success"])
        rep_id = res["data"]["id"]

        # 2. Bazada hisobotni APPROVED qilish (monitoring tasdiqlangan hisobotlarni ko'rsatadi)
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT sim_cards_count, sim_uzmobile, sim_beeline, sim_ucell, sim_mobiuz, sim_perfectum FROM daily_reports WHERE id = ?", (rep_id,))
            row = await cursor.fetchone()
            self.assertEqual(row["sim_cards_count"], 11)
            self.assertEqual(row["sim_uzmobile"], 4)
            self.assertEqual(row["sim_beeline"], 3)
            self.assertEqual(row["sim_ucell"], 2)
            self.assertEqual(row["sim_mobiuz"], 1)
            self.assertEqual(row["sim_perfectum"], 1)

            await conn.execute("UPDATE daily_reports SET status = 'APPROVED' WHERE id = ?", (rep_id,))
            await conn.commit()
            invalidate_analytics_cache(1)

        # 3. Savdo monitoringi so'rovi tekshiruvi
        mon_res = await get_sales_monitoring(period="today", admin=admin_user)
        self.assertTrue(mon_res["success"])
        op_list = mon_res["data"]["operators"]
        op_dict = {o["operator_type"]: o["count"] for o in op_list}

        self.assertGreaterEqual(op_dict.get("Uzmobile", 0), 4)
        self.assertGreaterEqual(op_dict.get("Beeline", 0), 3)
        self.assertGreaterEqual(op_dict.get("Ucell", 0), 2)
        self.assertGreaterEqual(op_dict.get("Mobiuz", 0), 1)
        self.assertGreaterEqual(op_dict.get("Perfectum", 0), 1)

        # Tozalash
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("DELETE FROM daily_reports WHERE id = ?", (rep_id,))
            await conn.execute("DELETE FROM users WHERE id = 777")
            await conn.commit()

    async def test_11_reports_status_filtering_and_excel(self):
        """11. Hisobotlar holati (PENDING, APPROVED, REJECTED) bo'yicha saralash va Excel eksport tekshiruvi"""
        from app.routes.reports import get_all_reports

        admin_user = {"id": 1, "company_id": 1, "role": "ADMIN", "full_name": "Test Admin", "telegram_id": 12345}

        # Status bo'yicha so'rov
        res_pending = await get_all_reports(status="PENDING", user=admin_user)
        self.assertTrue(res_pending["success"])
        for r in res_pending["data"]:
            self.assertEqual(r["status"], "PENDING")

        res_approved = await get_all_reports(status="APPROVED", user=admin_user)
        self.assertTrue(res_approved["success"])
        for r in res_approved["data"]:
            self.assertEqual(r["status"], "APPROVED")

    async def test_12_company_individual_field_updates(self):
        """12. Firma ma'lumotlarini har biri alohida (mustaqil) tahrirlanishi tekshiruvi"""
        from app.routes.saas import edit_company_details, update_my_company_settings
        from app.models import UpdateCompanyAdminDetailsRequest, UpdateCompanySettingsRequest

        super_admin = {"id": 1, "company_id": 1, "role": "DEVELOPER", "full_name": "Super Admin"}
        test_comp_id = 9999

        async with aiosqlite.connect(DB_PATH) as conn:
            # Create a test company
            await conn.execute("DELETE FROM companies WHERE id = ?", (test_comp_id,))
            await conn.execute("DELETE FROM users WHERE company_id = ?", (test_comp_id,))
            await conn.execute("""
                INSERT INTO companies (id, name, slug, telegram_group_id, owner_telegram_id, owner_phone, max_employees)
                VALUES (?, 'Boshlangich Firma', 'boshlangich-firma', '-100111222', 999111, '+998901112233', 25)
            """, (test_comp_id,))
            await conn.execute("""
                INSERT INTO users (id, company_id, telegram_id, full_name, role, password_hash)
                VALUES (9991, ?, 999111, 'Eski Rahbar', 'ADMIN', 'fakehash')
            """, (test_comp_id,))
            await conn.commit()

        try:
            # 1. Faqat nomini yangilash
            req_name = UpdateCompanyAdminDetailsRequest(name="Alohida Yangilangan Firma")
            res1 = await edit_company_details(company_id=test_comp_id, req=req_name, super_admin=super_admin)
            self.assertTrue(res1["success"])

            async with aiosqlite.connect(DB_PATH) as conn:
                conn.row_factory = aiosqlite.Row
                cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (test_comp_id,))
                comp1 = await cur.fetchone()
                self.assertEqual(comp1["name"], "Alohida Yangilangan Firma")
                self.assertEqual(comp1["telegram_group_id"], "-100111222")
                self.assertEqual(comp1["owner_phone"], "+998901112233")

            # 2. Faqat guruh ID sini yangilash
            req_grp = UpdateCompanyAdminDetailsRequest(telegram_group_id="-100999888")
            res2 = await edit_company_details(company_id=test_comp_id, req=req_grp, super_admin=super_admin)
            self.assertTrue(res2["success"])

            async with aiosqlite.connect(DB_PATH) as conn:
                conn.row_factory = aiosqlite.Row
                cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (test_comp_id,))
                comp2 = await cur.fetchone()
                self.assertEqual(comp2["name"], "Alohida Yangilangan Firma")
                self.assertEqual(comp2["telegram_group_id"], "-100999888")

            # 3. Faqat telefon raqami va INN ni yangilash
            req_contact = UpdateCompanyAdminDetailsRequest(owner_phone="+998977778899", company_inn="123456789")
            res3 = await edit_company_details(company_id=test_comp_id, req=req_contact, super_admin=super_admin)
            self.assertTrue(res3["success"])

            async with aiosqlite.connect(DB_PATH) as conn:
                conn.row_factory = aiosqlite.Row
                cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (test_comp_id,))
                comp3 = await cur.fetchone()
                self.assertEqual(comp3["owner_phone"], "+998977778899")
                self.assertEqual(comp3["company_inn"], "123456789")

            # 4. Rahbar tomonidan o'z kompaniyasi sozlamalarini (/my-company/settings) alohida yangilash
            comp_admin = {"id": 9991, "company_id": test_comp_id, "role": "ADMIN", "full_name": "Eski Rahbar"}
            req_my = UpdateCompanySettingsRequest(name="Rahbar O'zgartirgan Firma")
            res4 = await update_my_company_settings(req=req_my, admin=comp_admin)
            self.assertTrue(res4["success"])

            async with aiosqlite.connect(DB_PATH) as conn:
                conn.row_factory = aiosqlite.Row
                cur = await conn.execute("SELECT name FROM companies WHERE id = ?", (test_comp_id,))
                comp4 = await cur.fetchone()
                self.assertEqual(comp4["name"], "Rahbar O'zgartirgan Firma")

        finally:
            async with aiosqlite.connect(DB_PATH) as conn:
                await conn.execute("DELETE FROM companies WHERE id = ?", (test_comp_id,))
                await conn.execute("DELETE FROM users WHERE company_id = ?", (test_comp_id,))
                await conn.commit()

if __name__ == "__main__":
    unittest.main()
