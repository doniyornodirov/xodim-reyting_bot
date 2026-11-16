import unittest
import asyncio
from unittest.mock import patch
import aiosqlite
from app.database import init_db, get_db_connection
from app.services.analytics_service import get_sales_monitoring_data, invalidate_analytics_cache

class TestSimMonitoringSync(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_sim_cards_migration_and_monitoring_consistency(self):
        # 1. Baza initsializatsiyasi
        await init_db()

        async with get_db_connection() as conn:
            # Test xodim va hisobot yaratish
            await conn.execute("DELETE FROM users WHERE id = 999 OR telegram_id = 888777999")
            await conn.execute("INSERT OR IGNORE INTO users (id, company_id, telegram_id, full_name, role, password_hash) VALUES (999, 1, 888777999, 'Test Elyor', 'EMPLOYEE', 'pwd')")
            
            # Tozalash
            await conn.execute("DELETE FROM daily_reports WHERE employee_id = 999")
            
            # 1 ta eski hisobot: sim_cards_count = 7, operatorlar = 0
            await conn.execute("""
                INSERT INTO daily_reports (
                    company_id, employee_id, report_date, paynet, card_amount, leviy, debt_snapshot, debt_paid,
                    sim_cards_count, sim_uzmobile, sim_beeline, sim_ucell, sim_mobiuz, sim_perfectum,
                    kunlik, terminal, given_amount, skidka, xarajat, total_inflow, total_outflow, net_amount, status
                ) VALUES (
                    1, 999, '2026-11-11', 100000, 0, 0, 0, 0,
                    7, 0, 0, 0, 0, 0,
                    0, 0, 0, 0, 0, 100000, 0, 100000, 'APPROVED'
                )
            """)

            # 2 ta yangi hisobot: jami 12 ta sim-karta (operatorlar ajratilgan)
            await conn.execute("""
                INSERT INTO daily_reports (
                    company_id, employee_id, report_date, paynet, card_amount, leviy, debt_snapshot, debt_paid,
                    sim_cards_count, sim_uzmobile, sim_beeline, sim_ucell, sim_mobiuz, sim_perfectum,
                    kunlik, terminal, given_amount, skidka, xarajat, total_inflow, total_outflow, net_amount, status
                ) VALUES (
                    1, 999, '2026-11-15', 100000, 0, 0, 0, 0,
                    12, 5, 2, 3, 1, 1,
                    0, 0, 0, 0, 0, 100000, 0, 100000, 'APPROVED'
                )
            """)
            await conn.commit()

        # 2. init_db() qayta ishga tushganda eski hisobotdagi 7 ta sim-karta Uzmobile'ga birikishi kerak
        await init_db()

        async with get_db_connection() as conn:
            cur = await conn.execute("SELECT sim_cards_count, sim_uzmobile FROM daily_reports WHERE employee_id = 999 AND report_date = '2026-11-11'")
            row = await cur.fetchone()
            self.assertEqual(row["sim_cards_count"], 7)
            self.assertEqual(row["sim_uzmobile"], 7, "Eski hisobotdagi 7 ta sim-karta Uzmobile'ga o'tishi kerak!")

        # 3. Monitoring ma'lumotlarini tekshirish
        invalidate_analytics_cache(1)
        res = await get_sales_monitoring_data(company_id=1, period="7d", user_id=999)
        summary = res["summary"]
        operators = res["operators"]

        total_sims = summary["total_sim_cards"]
        self.assertEqual(total_sims, 19, f"Jami sim-kartalar 19 dona bo'lishi kerak, hozir: {total_sims}")

        op_sum = sum(op["count"] for op in operators)
        self.assertEqual(op_sum, 19, f"Operatorlar bo'yicha jami {op_sum} ta, bu 19 ga teng bo'lishi shart!")

        # Uzmobile 5 + 7 = 12 ta bo'lishi kerak
        uzm = next((op for op in operators if op["operator_type"] == "Uzmobile"), None)
        self.assertIsNotNone(uzm)
        self.assertEqual(uzm["count"], 12)

        # Tozalash
        async with get_db_connection() as conn:
            await conn.execute("DELETE FROM daily_reports WHERE employee_id = 999")
            await conn.execute("DELETE FROM users WHERE id = 999 OR telegram_id = 888777999")
            await conn.commit()
            await conn.commit()

    async def test_report_submission_syncs_sims(self):
        from app.routes.reports import submit_daily_report
        from app.models import DailyReportCreate

        user = {
            "id": 999,
            "company_id": 1,
            "full_name": "Test Elyor",
            "role": "EMPLOYEE",
            "telegram_id": None
        }

        async with get_db_connection() as conn:
            await conn.execute("INSERT OR REPLACE INTO users (id, company_id, telegram_id, full_name, role, password_hash, debt_amount) VALUES (999, 1, 888777999, 'Test Elyor', 'EMPLOYEE', 'pwd', 0)")
            await conn.commit()

        # 1. Faqat sim_cards_count = 5 kiritilganda sim_uzmobile ham avtomatik 5 bo'lishi kerak
        req1 = DailyReportCreate(
            paynet=100000,
            card_amount=0,
            leviy=0,
            kunlik=0,
            terminal=0,
            given_amount=0,
            skidka=0,
            xarajat=0,
            debt_paid=0,
            sim_cards_count=5,
            sim_uzmobile=0,
            sim_beeline=0,
            sim_ucell=0,
            sim_mobiuz=0,
            sim_perfectum=0
        )

        with patch("app.routes.reports.get_tashkent_today_str") as mock_today:
            mock_today.return_value = "2026-11-16"
            res1 = await submit_daily_report(req=req1, user=user)
            self.assertTrue(res1["success"])

        async with get_db_connection() as conn:
            cur = await conn.execute("SELECT sim_cards_count, sim_uzmobile FROM daily_reports WHERE employee_id = 999 AND report_date = '2026-11-16'")
            row = await cur.fetchone()
            self.assertEqual(row["sim_cards_count"], 5)
            self.assertEqual(row["sim_uzmobile"], 5, "Operator ko'rsatilmaganda Uzmobile ga birikishi kerak!")

        # 2. Operatorlar ko'rsatilganda (masalan, Beeline: 3, Ucell: 4), sim_cards_count = 7 bo'lishi kerak
        req2 = DailyReportCreate(
            paynet=100000,
            card_amount=0,
            leviy=0,
            kunlik=0,
            terminal=0,
            given_amount=0,
            skidka=0,
            xarajat=0,
            debt_paid=0,
            sim_cards_count=0,
            sim_uzmobile=0,
            sim_beeline=3,
            sim_ucell=4,
            sim_mobiuz=0,
            sim_perfectum=0
        )

        with patch("app.routes.reports.get_tashkent_today_str") as mock_today:
            mock_today.return_value = "2026-11-17"
            res2 = await submit_daily_report(req=req2, user=user)
            self.assertTrue(res2["success"])

        async with get_db_connection() as conn:
            cur = await conn.execute("SELECT sim_cards_count, sim_beeline, sim_ucell FROM daily_reports WHERE employee_id = 999 AND report_date = '2026-11-17'")
            row = await cur.fetchone()
            self.assertEqual(row["sim_cards_count"], 7, "sim_cards_count operatorlar yig'indisiga (3+4=7) teng bo'lishi kerak!")
            self.assertEqual(row["sim_beeline"], 3)
            self.assertEqual(row["sim_ucell"], 4)

            # Tozalash
            await conn.execute("DELETE FROM daily_reports WHERE employee_id = 999")
            await conn.execute("DELETE FROM users WHERE id = 999 OR telegram_id = 888777999")
            await conn.commit()

    async def test_today_with_no_sales_returns_zero(self):
        # sim_cards jadvalida SOLD sim-kartalar bo'lsa ham, bugun hisobot bo'lmasa 0 bo'lishi kerak
        async with get_db_connection() as conn:
            await conn.execute("INSERT OR REPLACE INTO users (id, company_id, telegram_id, full_name, role, password_hash) VALUES (998, 1, 777666555, 'Test User', 'EMPLOYEE', 'pwd')")
            await conn.execute("INSERT OR REPLACE INTO sim_cards (company_id, operator_type, serial_number, status, employee_id, distributed_by_id) VALUES (1, 'Uzmobile', '8888888888', 'SOLD', 998, 998)")
            await conn.commit()

        invalidate_analytics_cache(1)
        res = await get_sales_monitoring_data(company_id=1, period="today", user_id=998)
        
        self.assertEqual(res["summary"]["total_sim_cards"], 0, "Bugun hisobot tasdiqlanmagan bo'lsa, jami sim-kartalar 0 bo'lishi kerak!")
        for op in res["operators"]:
            self.assertEqual(op["count"], 0, f"{op['operator_type']} 0 ta bo'lishi kerak, lekin {op['count']} ta chiqdi!")

        # Tozalash
        async with get_db_connection() as conn:
            await conn.execute("DELETE FROM sim_cards WHERE serial_number = '8888888888'")
            await conn.execute("DELETE FROM users WHERE id = 998")
            await conn.commit()

    async def test_paynet_and_card_topup_no_double_count(self):
        # 1. Test xodim va bugungi karta to'ldirish
        async with get_db_connection() as conn:
            await conn.execute("INSERT OR REPLACE INTO users (id, company_id, telegram_id, full_name, role, password_hash) VALUES (997, 1, 666555444, 'Test Card User', 'EMPLOYEE', 'pwd')")
            # Bugungi karta to'ldirish: 1 000 000 + 3% ustama = 1 030 000
            await conn.execute("""
                INSERT INTO card_topups (company_id, transaction_number, employee_id, card_number, card_holder, amount, surcharge_amount, surcharge_percent, status, created_at)
                VALUES (1, 99991, 997, '8600 0000 0000 0000', 'Test Holder', 1000000, 1030000, 3, 'APPROVED', CURRENT_TIMESTAMP)
            """)
            await conn.commit()

        invalidate_analytics_cache(1)

        # Hali kunlik hisobot topshirilmagan holat:
        res1 = await get_sales_monitoring_data(company_id=1, period="today", user_id=997)
        # Bugungi Yalpi Tushumda jonli ravishda karta to'ldirish (1 030 000) ko'rinishi kerak
        self.assertEqual(res1["summary"]["total_card_topup_amount"], 1030000)
        self.assertEqual(res1["summary"]["total_submitted_amount"], 1030000)
        self.assertEqual(res1["summary"]["total_paynet_amount"], 0)

        # 2. Kechqurun xodim hisobot topshirdi (Paynet: 2 000 000, Karta: 1 030 000, Jami inflow: 3 030 000)
        async with get_db_connection() as conn:
            from app.security import get_tashkent_today_str
            t_date = get_tashkent_today_str()
            await conn.execute("""
                INSERT INTO daily_reports (
                    company_id, employee_id, report_date, paynet, card_amount, leviy, debt_snapshot, debt_paid,
                    sim_cards_count, kunlik, terminal, given_amount, skidka, xarajat, total_inflow, total_outflow, net_amount, status
                ) VALUES (
                    1, 997, ?, 2000000, 1030000, 0, 0, 0,
                    0, 0, 0, 0, 0, 0, 3030000, 0, 3030000, 'APPROVED'
                )
            """, (t_date,))
            await conn.commit()

        invalidate_analytics_cache(1)

        # Hisobot tasdiqlangan holat:
        res2 = await get_sales_monitoring_data(company_id=1, period="today", user_id=997)
        # Yalpi tushum 3 030 000 bo'lishi kerak! Karta to'ldirish (1 030 000) 2 marta qo'shilib 4 060 000 bo'lib ketmasligi shart!
        self.assertEqual(res2["summary"]["total_submitted_amount"], 3030000, "Hisobot tasdiqlanganda karta to'ldirish 2 marta hisoblanmasligi kerak!")
        self.assertEqual(res2["summary"]["total_paynet_amount"], 2000000, "Paynet 2 000 000 so'm bo'lishi kerak!")
        self.assertEqual(res2["summary"]["total_card_topup_amount"], 1030000)

        # Tozalash
        async with get_db_connection() as conn:
            await conn.execute("DELETE FROM card_topups WHERE transaction_number = 99991")
            await conn.execute("DELETE FROM daily_reports WHERE employee_id = 997")
            await conn.execute("DELETE FROM users WHERE id = 997")
            await conn.commit()

if __name__ == "__main__":
    unittest.main()
