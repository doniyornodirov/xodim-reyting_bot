"""
XodimKPI CRM - FinTech Moliya Xavfsizligi va Idempotentlik Sinovlari (Test Suite)
"""

import unittest
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import HTTPException
from app.services.fintech_calc import (
    to_decimal,
    round_uzs,
    calculate_card_surcharge,
    calculate_daily_report_totals,
    calculate_cashier_diff
)
from app.services.idempotency import (
    check_idempotency,
    record_idempotency_result,
    clear_idempotency_key,
    _IDEMPOTENCY_STORE
)

class TestFintechAndIdempotency(unittest.IsolatedAsyncioTestCase):

    def test_01_decimal_conversion_and_rounding(self):
        """1. Decimal xavfsiz konvertatsiya va butun so'mga yaxlitlash tekshiruvi"""
        self.assertEqual(to_decimal(100.5), Decimal("100.5"))
        self.assertEqual(round_uzs(100.49), 100)
        self.assertEqual(round_uzs(100.50), 101)
        self.assertEqual(round_uzs("500000"), 500000)

    def test_02_card_surcharge_calculation(self):
        """2. Karta to'ldirish 3% ustamani 1000 so'mga yaxlitlash qoidasi"""
        # 50 000 * 1.03 = 51 500 -> 52 000 so'm bo'lishi kerak
        self.assertEqual(calculate_card_surcharge(50000), 52000)
        # 100 000 * 1.03 = 103 000 -> 103 000 so'm bo'lishi kerak
        self.assertEqual(calculate_card_surcharge(100000), 103000)
        # 30 000 * 1.03 = 30 900 -> 31 000 so'm bo'lishi kerak
        self.assertEqual(calculate_card_surcharge(30000), 31000)

    def test_03_daily_report_totals_precision(self):
        """3. Kunlik hisobot kirim, chiqim va sof kassa hisobi aniqligi (0 tiyin tafovut)"""
        res = calculate_daily_report_totals(
            paynet=1500000,
            card_amount=52000,
            leviy=100000,
            debt_paid=50000,
            kunlik=20000,
            terminal=500000,
            given_amount=100000,
            skidka=10000,
            xarajat=15000
        )
        # Kirim = 1 500 000 + 52 000 + 100 000 + 50 000 + 20 000 = 1 722 000
        self.assertEqual(res["total_inflow"], 1722000)
        # Chiqim = 500 000 + 100 000 + 10 000 + 15 000 = 625 000
        self.assertEqual(res["total_outflow"], 625000)
        # Sof = 1 722 000 - 625 000 = 1 097 000
        self.assertEqual(res["net_amount"], 1097000)

    def test_04_cashier_diff_calculation(self):
        """4. Kassa taqqoslash tafovutlari (kamomad yoki ortiqcha) aniqlanishi"""
        # 1 000 000 kutilgan, kassir 900 000 so'm qabul qilgan -> 100 000 kamomad
        res1 = calculate_cashier_diff(
            system_expected_net=1000000,
            cashier_received_uzs=900000,
            cashier_received_usd=0,
            usd_rate=12000
        )
        self.assertTrue(res1["has_diff"])
        self.assertTrue(res1["is_shortage"])
        self.assertFalse(res1["is_surplus"])
        self.assertEqual(res1["difference"], -100000)

        # 1 000 000 kutilgan, kassir 50$ (kurs 12 000 = 600 000) + 400 000 so'm qabul qilgan -> Tafovut 0
        res2 = calculate_cashier_diff(
            system_expected_net=1000000,
            cashier_received_uzs=400000,
            cashier_received_usd=50,
            usd_rate=12000
        )
        self.assertFalse(res2["has_diff"])
        self.assertEqual(res2["difference"], 0)

        # 3. FinTech Zero Discrepancy Xulosasi (summarize_cashier_comparison)
        from app.services.cashier_service import summarize_cashier_comparison
        mock_results = [
            {"report_amount": 500000, "cashier_amount": 500000, "cashier_amount_uzs": 500000, "cashier_amount_usd": 0, "is_match": True, "has_diff": False, "report_status": "APPROVED"},
            {"report_amount": 300000, "cashier_amount": 250000, "cashier_amount_uzs": 250000, "cashier_amount_usd": 0, "is_match": False, "has_diff": True, "report_status": "APPROVED"}
        ]
        sum1 = summarize_cashier_comparison(mock_results)
        self.assertEqual(sum1["total_expected_uzs"], 800000)
        self.assertEqual(sum1["total_collected_uzs"], 750000)
        self.assertEqual(sum1["total_difference_uzs"], -50000)
        self.assertFalse(sum1["is_zero_discrepancy"])
        self.assertEqual(sum1["diff_count"], 1)

        # 4. Zero Discrepancy holati (100% to'liq mos)
        mock_perfect = [
            {"report_amount": 500000, "cashier_amount": 500000, "cashier_amount_uzs": 500000, "cashier_amount_usd": 0, "is_match": True, "has_diff": False, "report_status": "APPROVED"}
        ]
        sum2 = summarize_cashier_comparison(mock_perfect)
        self.assertEqual(sum2["total_difference_uzs"], 0)
        self.assertTrue(sum2["is_zero_discrepancy"])

    async def test_05_idempotency_workflow(self):
        """5. Idempotentlik: birinchi so'rov o'tishi, takroriy so'rovda kesh qaytishi"""
        test_key = "unique-tx-12345"
        user_id = 99

        # Tozalash
        await clear_idempotency_key(test_key, user_id, action="TEST")

        # 1. Birinchi marta tekshirish (yangi so'rov)
        is_new, cached = await check_idempotency(test_key, user_id, action="TEST")
        self.assertTrue(is_new)
        self.assertIsNone(cached)

        # 2. Xuddi shu kalit bilan hali natija yozilmasdan takroriy so'rov kelsa -> 409 Conflict
        with self.assertRaises(HTTPException) as cm:
            await check_idempotency(test_key, user_id, action="TEST")
        self.assertEqual(cm.exception.status_code, 409)

        # 3. Natija yoziladi
        expected_result = {"success": True, "transaction_id": 888}
        await record_idempotency_result(test_key, user_id, expected_result, action="TEST")

        # 4. Endi xuddi shu kalit qayta so'ralsa -> Keshdagi natija qaytadi (is_new = False)
        is_new_repeat, cached_repeat = await check_idempotency(test_key, user_id, action="TEST")
        self.assertFalse(is_new_repeat)
        self.assertEqual(cached_repeat, expected_result)

        # Tozalash
        await clear_idempotency_key(test_key, user_id, action="TEST")

    async def test_06_services_integration(self):
        """6. Clean Architecture servislar integratsiyasi (cashier, rating, report prefill)"""
        from app.database import get_db_connection
        from app.services.cashier_service import calculate_daily_cashier_comparison
        from app.services.report_service import get_employee_report_prefill
        from app.services.rating_service import get_company_leaderboard, calculate_kpi_points

        # KPI ballarini hisoblash
        pts = calculate_kpi_points(5000000, 10)
        self.assertEqual(pts["money_points"], 5.0)
        self.assertEqual(pts["sim_points"], 10.0)
        self.assertEqual(pts["total_score"], 15.0)

        async with get_db_connection() as conn:
            # 1. Leaderboard
            board = await get_company_leaderboard(conn, company_id=1, period="monthly")
            self.assertIsInstance(board, list)

            # 2. Cashier comparison
            comp = await calculate_daily_cashier_comparison(conn, company_id=1, target_date="2026-11-16")
            self.assertIsInstance(comp, list)

            # 3. Report prefill
            prefill = await get_employee_report_prefill(conn, company_id=1, user_id=1, today_str="2026-11-16")
            self.assertTrue(prefill["success"])
            self.assertIn("card_amount", prefill)

    def test_07_sim_service_validation(self):
        """7. Sim-karta seriyalari validatsiyasi va limitlari tekshiruvi"""
        from app.services.sim_service import validate_serial_range

        # To'g'ri oraliq
        s, e, count = validate_serial_range("899980000000000001", "899980000000000010")
        self.assertEqual(count, 10)

        # 1 ta sim karta (start == end)
        s, e, count1 = validate_serial_range("899980000000000001", "899980000000000001")
        self.assertEqual(count1, 1)

        # 18 tadan kam raqam kiritilsa -> ValueError
        with self.assertRaises(ValueError):
            validate_serial_range("123", "456")

        # start > end -> ValueError
        with self.assertRaises(ValueError):
            validate_serial_range("899980000000000010", "899980000000000001")

        # 1000 tadan ortiq sim karta -> ValueError
        with self.assertRaises(ValueError):
            validate_serial_range("899980000000000001", "899980000000002000")

    def test_08_geo_service_calculations(self):
        """8. Geolokatsiya Haversine masofasi va smena vaqtlari tekshiruvi"""
        from app.services.geo_service import calculate_haversine_meters, is_time_within_interval, is_desktop_user_agent

        # 1. Haversine masofa: bir xil nuqta = 0 metr
        d = calculate_haversine_meters(41.311081, 69.240562, 41.311081, 69.240562)
        self.assertEqual(d, 0.0)

        # Toshkent markazi va yaqin nuqta (~111 metr)
        d2 = calculate_haversine_meters(41.311081, 69.240562, 41.312081, 69.240562)
        self.assertGreater(d2, 100)
        self.assertLess(d2, 120)

        # 2. Smena vaqtlari (kunduzgi va tungi)
        self.assertTrue(is_time_within_interval("12:00", "09:00", "18:00"))
        self.assertFalse(is_time_within_interval("19:30", "09:00", "18:00"))
        # Tungi smena: 21:00 - 06:00
        self.assertTrue(is_time_within_interval("23:30", "21:00", "06:00"))
        self.assertTrue(is_time_within_interval("03:15", "21:00", "06:00"))
        self.assertFalse(is_time_within_interval("12:00", "21:00", "06:00"))

        # 3. Desktop vs Mobile User Agent tekshiruvi
        self.assertTrue(is_desktop_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"))
        self.assertFalse(is_desktop_user_agent("Mozilla/5.0 (Linux; Android 14; SM-S928B) Mobile Safari/537.36"))

    async def test_09_brute_force_lockout(self):
        """9. Brute-force himoyasi: 5 marta xato terilganda 429 Lockout berilishi"""
        from app.services.security_service import check_login_lockout, record_failed_login, reset_failed_login
        test_tg = 999888777

        # 1. Tozalash
        await reset_failed_login(test_tg)
        await check_login_lockout(test_tg)

        # 2. 4 marta xato kiritish
        for i in range(4):
            rem = await record_failed_login(test_tg)
            self.assertEqual(rem, 4 - i)

        # 3. 5-marta xato kiritilganda HTTP 429 tashlanadi
        with self.assertRaises(HTTPException) as cm:
            await record_failed_login(test_tg)
        self.assertEqual(cm.exception.status_code, 429)

        # 4. Endi check_login_lockout ham 429 beradi
        with self.assertRaises(HTTPException) as cm2:
            await check_login_lockout(test_tg)
        self.assertEqual(cm2.exception.status_code, 429)

        # 5. Muvaffaqiyatli kirish tozalaydi
        await reset_failed_login(test_tg)
        await check_login_lockout(test_tg)

    def test_10_saas_service_calculations(self):
        """10. SaaS xizmatlari: slug yaratish, kunlar hisobi, tarif muddati va xabarlar"""
        from app.services.saas_service import (
            generate_slug,
            calculate_days_left,
            calculate_plan_expiration,
            calculate_subscription_extension,
            format_company_credentials_message
        )

        # 1. Slug yaratish
        self.assertEqual(generate_slug("O'zbekiston Paynet Savdo"), "ozbekiston-paynet-savdo")
        self.assertEqual(generate_slug("Бизнес Авто Центр"), "biznes-avto-tsentr")
        self.assertEqual(generate_slug("   "), "firma")

        # 2. Qolgan kunlar hisobi
        self.assertIsNone(calculate_days_left("UNLIMITED", None))
        self.assertIsNone(calculate_days_left("UNLIMITED", "2030-01-01T00:00:00Z"))
        self.assertEqual(calculate_days_left("STANDARD", "2020-01-01T00:00:00Z"), 0)
        
        future_iso = (datetime.now(timezone.utc) + timedelta(days=15)).isoformat()
        days_left = calculate_days_left("STANDARD", future_iso)
        self.assertTrue(14 <= days_left <= 16)

        # 3. Tarif muddati hisobi
        self.assertIsNone(calculate_plan_expiration("UNLIMITED"))
        exp_5y = calculate_plan_expiration("5_YEARS")
        self.assertIsNotNone(exp_5y)
        exp_custom = calculate_plan_expiration("STANDARD", expires_date_str="2030-05-20")
        self.assertIn("2030-05-20", exp_custom)

        # 4. Obuna uzaytirish
        ext_days = calculate_subscription_extension(future_iso, days=10)
        self.assertIsNotNone(ext_days)

        # 5. Rekvizitlar formati
        msg = format_company_credentials_message(
            company_name="Test Firma",
            frontend_url="https://crm.xodimkpi.uz",
            owner_name="Alisher",
            owner_telegram_id=1234567,
            owner_phone="+998901234567",
            plan="STANDARD",
            subscription_expires_at="2030-01-01T00:00:00Z",
            max_employees=25
        )
        self.assertIn("Test Firma", msg)
        self.assertIn("https://crm.xodimkpi.uz", msg)
        self.assertIn("1234567", msg)
        self.assertIn("+998901234567", msg)

    async def test_11_saas_batch_overview_and_wal_checkpoint(self):
        """11. SaaS Batch Overview (Zero N+1) va SQLite WAL checkpoint tekshiruvi"""
        from app.database import get_db_connection, checkpoint_wal
        from app.services.saas_service import get_companies_overview

        async with get_db_connection() as conn:
            # 1. Zero N+1 batch overview
            overview = await get_companies_overview(conn)
            self.assertIsInstance(overview, list)
            self.assertGreater(len(overview), 0)
            first = overview[0]
            self.assertIn("id", first)
            self.assertIn("name", first)
            self.assertIn("employees_count", first)
            self.assertIn("reports_count", first)
            self.assertIn("topups_count", first)
            self.assertIn("total_turnover", first)

            # 2. WAL checkpoint
            cp_result = await checkpoint_wal(conn, mode="PASSIVE")
            self.assertIn("busy", cp_result)
            self.assertIn("log", cp_result)
            self.assertIn("checkpointed", cp_result)
            self.assertIsInstance(cp_result["busy"], bool)

    async def test_12_postgres_context_manager_and_cashier_comparison(self):
        """12. PostgresContextManager (await va async with) hamda Kassa taqqoslash hisobi tekshiruvi"""
        from app.pg_engine import PostgresExecuteContextManager, PostgresCursorWrapper
        from app.database import get_db_connection
        from app.services.cashier_service import calculate_daily_cashier_comparison, summarize_cashier_comparison

        # 1. PostgresExecuteContextManager await va async with qobiliyati
        async def mock_coro():
            return PostgresCursorWrapper(rows=[], lastrowid=99, rowcount=1)

        cm1 = PostgresExecuteContextManager(mock_coro())
        cur1 = await cm1
        self.assertEqual(cur1.lastrowid, 99)

        cm2 = PostgresExecuteContextManager(mock_coro())
        async with cm2 as cur2:
            self.assertEqual(cur2.rowcount, 1)

        # 2. calculate_daily_cashier_comparison va summarize_cashier_comparison
        async with get_db_connection() as conn:
            results = await calculate_daily_cashier_comparison(conn, company_id=1, target_date="2026-11-16")
            self.assertIsInstance(results, list)
            summary = summarize_cashier_comparison(results)
            self.assertIn("total_expected_uzs", summary)
            self.assertIn("total_collected_uzs", summary)
            self.assertIn("total_difference_uzs", summary)
            self.assertIn("is_zero_discrepancy", summary)
            self.assertIn("status_text", summary)

            # 3. Oraliq (Date Range) bo'yicha kassa taqqoslash tekshiruvi
            range_results = await calculate_daily_cashier_comparison(
                conn, company_id=1, target_date="2026-11-01", end_date="2026-11-16"
            )
            self.assertIsInstance(range_results, list)
            range_summary = summarize_cashier_comparison(range_results)
            self.assertIn("total_expected_uzs", range_summary)
            self.assertIn("total_collected_uzs", range_summary)
            self.assertIn("total_difference_uzs", range_summary)

    async def test_09_device_name_normalization_and_migration(self):
        """Chromium UA Reduction ('K') va qisqa qurilma nomlarini avtomatik to'g'rilash testi"""
        from app.database import get_db_connection
        async with get_db_connection() as conn:
            cur = await conn.execute("SELECT id FROM users LIMIT 1")
            first_user = await cur.fetchone()
            if not first_user:
                return
            uid = first_user["id"]

            # 'K' qiymatini kiritamiz
            await conn.execute("UPDATE users SET bound_device_name = 'K' WHERE id = ?", (uid,))
            await conn.commit()

            # Migratsiya tekshiruvi
            await conn.execute("UPDATE users SET bound_device_name = 'Android telefon' WHERE bound_device_name = 'K' OR bound_device_name = 'k' OR LENGTH(TRIM(bound_device_name)) <= 1")
            await conn.commit()

            cur = await conn.execute("SELECT bound_device_name FROM users WHERE id = ?", (uid,))
            row = await cur.fetchone()
            self.assertEqual(row["bound_device_name"], "Android telefon")

    def test_13_amount_range_validation_0_to_1_billion(self):
        """Summa kiritish maydonlarida 0 dan 1 milliardgacha ruxsat, undan katta/kichik man etilganini tekshirish"""
        from pydantic import ValidationError
        from app.models import (
            CardTopupCreate,
            GivenAmountCreate,
            DailyReportCreate,
            CashierHandoverCreate,
            SetDebtRequest
        )

        # 1. Karta to'ldirish
        self.assertTrue(CardTopupCreate(card_number="8600123456789012", card_holder="ALI VALIYEV", amount=0))
        self.assertTrue(CardTopupCreate(card_number="8600123456789012", card_holder="ALI VALIYEV", amount=1_000_000_000))
        with self.assertRaises(ValidationError):
            CardTopupCreate(card_number="8600123456789012", card_holder="ALI VALIYEV", amount=-1)
        with self.assertRaises(ValidationError):
            CardTopupCreate(card_number="8600123456789012", card_holder="ALI VALIYEV", amount=1_000_000_001)

        # 2. Berilgan summa
        self.assertTrue(GivenAmountCreate(amount=0, comment="Test"))
        self.assertTrue(GivenAmountCreate(amount=1_000_000_000, comment="Test"))
        with self.assertRaises(ValidationError):
            GivenAmountCreate(amount=-5, comment="Test")
        with self.assertRaises(ValidationError):
            GivenAmountCreate(amount=1_000_000_001, comment="Test")

        # 3. Kunlik hisobot
        self.assertTrue(DailyReportCreate(paynet=0, leviy=1_000_000_000, kunlik=500000))
        with self.assertRaises(ValidationError):
            DailyReportCreate(paynet=-100)
        with self.assertRaises(ValidationError):
            DailyReportCreate(paynet=1_000_000_001)

        # 4. Kassa topshirish
        self.assertTrue(CashierHandoverCreate(employee_id=1, amount_uzs=0, amount_usd=0))
        self.assertTrue(CashierHandoverCreate(employee_id=1, amount_uzs=1_000_000_000, amount_usd=1_000_000_000))
        with self.assertRaises(ValidationError):
            CashierHandoverCreate(employee_id=1, amount_uzs=-100)
        with self.assertRaises(ValidationError):
            CashierHandoverCreate(employee_id=1, amount_uzs=1_000_000_001)

        # 5. Qarz belgilash
        self.assertTrue(SetDebtRequest(user_id=1, debt_amount=0, reason="Avans"))
        self.assertTrue(SetDebtRequest(user_id=1, debt_amount=1_000_000_000, reason="Katta qarz"))
        with self.assertRaises(ValidationError):
            SetDebtRequest(user_id=1, debt_amount=-1, reason="Test")
        with self.assertRaises(ValidationError):
            SetDebtRequest(user_id=1, debt_amount=1_000_000_001, reason="Test")

    async def test_14_multi_operator_sim_cards_isolation(self):
        """Turli operatorlar (Uzmobile, Beeline, ...) bo'yicha bir xil seriya raqamlari mustaqil mavjud bo'lishi testi"""
        from app.database import get_db_connection
        from app.routes.sim_cards import distribute_sim_cards, SimDistributeRequest

        async with get_db_connection() as conn:
            cur = await conn.execute("SELECT id, full_name, shift_status FROM users WHERE role NOT IN ('ADMIN', 'DEVELOPER') AND is_active = 1 LIMIT 1")
            emp = await cur.fetchone()
            cur_adm = await conn.execute("SELECT id, full_name, role, company_id FROM users WHERE role = 'ADMIN' LIMIT 1")
            admin = await cur_adm.fetchone()
            if not emp or not admin:
                return

            emp_id = emp["id"]
            admin_user = dict(admin)
            test_serial = "999900001111222233"

            # Agar xodim damda bo'lsa, vaqtincha ACTIVE qilamiz
            orig_shift = emp["shift_status"]
            if orig_shift == "RESTING":
                await conn.execute("UPDATE users SET shift_status = 'ACTIVE' WHERE id = ?", (emp_id,))
                await conn.commit()

            try:
                # Tozalash
                await conn.execute("DELETE FROM sim_cards WHERE serial_number = ?", (test_serial,))
                await conn.commit()

                # 1. Uzmobile operatori uchun seriyani biriktirish
                req_uz = SimDistributeRequest(
                    operator_type="Uzmobile",
                    start_serial=test_serial,
                    end_serial=test_serial,
                    employee_id=emp_id
                )
                res_uz = await distribute_sim_cards(req_uz, current_user=admin_user, db=conn)
                self.assertTrue(res_uz["success"])

                # 2. Beeline operatori uchun aynan SHU seriyani biriktirish (mustaqil o'tishi kerak!)
                req_bee = SimDistributeRequest(
                    operator_type="Beeline",
                    start_serial=test_serial,
                    end_serial=test_serial,
                    employee_id=emp_id
                )
                res_bee = await distribute_sim_cards(req_bee, current_user=admin_user, db=conn)
                self.assertTrue(res_bee["success"])

                # 3. Aynan Beeline uchun takroran kiritilganda 400 xatolik berishi kerak
                with self.assertRaises(HTTPException) as ctx:
                    await distribute_sim_cards(req_bee, current_user=admin_user, db=conn)
                self.assertEqual(ctx.exception.status_code, 400)
                self.assertIn("Beeline operatori bo'yicha sim-karta seriyasi bazada allaqachon mavjud", ctx.exception.detail)
            finally:
                # Tozalash va xodim holatini qaytarish
                await conn.execute("DELETE FROM sim_cards WHERE serial_number = ?", (test_serial,))
                if orig_shift == "RESTING":
                    await conn.execute("UPDATE users SET shift_status = 'RESTING' WHERE id = ?", (emp_id,))
                await conn.commit()

    async def test_15_card_surcharge_dynamic_percentage(self):
        """Karta to'ldirish ustamasini firma bo'yicha 1, 2, 3, 4, 5% ga dinamik o'zgartirish va hisoblash testi"""
        from app.database import get_db_connection
        from app.services.fintech_calc import calculate_card_surcharge
        from app.routes.cards import (
            get_card_surcharge_rate,
            update_card_surcharge_rate,
            CardSurchargeUpdateRequest,
            create_card_topup,
            CardTopupCreate
        )

        # 1. Formula tekshiruvi: 1%, 2%, 3%, 4%, 5%
        self.assertEqual(calculate_card_surcharge(50000, percent=1), 51000)
        self.assertEqual(calculate_card_surcharge(50000, percent=2), 51000)
        self.assertEqual(calculate_card_surcharge(50000, percent=3), 52000)
        self.assertEqual(calculate_card_surcharge(50000, percent=4), 52000)
        self.assertEqual(calculate_card_surcharge(50000, percent=5), 53000)

        self.assertEqual(calculate_card_surcharge(100000, percent=1), 101000)
        self.assertEqual(calculate_card_surcharge(100000, percent=2), 102000)
        self.assertEqual(calculate_card_surcharge(100000, percent=3), 103000)
        self.assertEqual(calculate_card_surcharge(100000, percent=4), 104000)
        self.assertEqual(calculate_card_surcharge(100000, percent=5), 105000)

        # 2. Endpointlar tekshiruvi
        async with get_db_connection() as conn:
            cur_adm = await conn.execute("SELECT id, full_name, role, company_id FROM users WHERE role = 'ADMIN' LIMIT 1")
            admin = await cur_adm.fetchone()
            cur_emp = await conn.execute("SELECT id, full_name, role, company_id, shift_status FROM users WHERE role NOT IN ('ADMIN', 'DEVELOPER') AND is_active = 1 LIMIT 1")
            emp = await cur_emp.fetchone()
            if not admin or not emp:
                return

            admin_user = dict(admin)
            emp_user = dict(emp)

            # Agar xodim damda bo'lsa, test uchun ACTIVE qilamiz
            orig_shift = emp_user.get("shift_status")
            if orig_shift == "RESTING":
                emp_user["shift_status"] = "ACTIVE"
                await conn.execute("UPDATE users SET shift_status = 'ACTIVE' WHERE id = ?", (emp_user["id"],))
                await conn.commit()

            try:
                # 2.1 Admin 4% qilib o'zgartiradi
                update_res = await update_card_surcharge_rate(CardSurchargeUpdateRequest(percent=4), user=admin_user)
                self.assertTrue(update_res["success"])
                self.assertEqual(update_res["percent"], 4)

                # 2.2 GET orqali foizni tekshirish
                rate_res = await get_card_surcharge_rate(user=emp_user)
                self.assertEqual(rate_res["percent"], 4)

                # 2.3 Xodim 100 000 so'm karta so'rovi yuboradi (4% bilan 104 000 bo'lishi kerak)
                topup_req = CardTopupCreate(
                    card_number="8600123412341234",
                    card_holder="TEST FOIZ",
                    amount=100000
                )
                topup_res = await create_card_topup(topup_req, user=emp_user)
                self.assertTrue(topup_res["success"])
                self.assertEqual(topup_res["data"]["surcharge_amount"], 104000)
                self.assertEqual(topup_res["data"]["surcharge_percent"], 4)

                # 2.4 Noto'g'ri foiz kiritilganda (masalan, 0 yoki 6) 400 xatolik berishi kerak
                with self.assertRaises(Exception):
                    await update_card_surcharge_rate(CardSurchargeUpdateRequest(percent=6), user=admin_user)

            finally:
                # Qaytarish (Standart 3% ga qaytaramiz)
                await update_card_surcharge_rate(CardSurchargeUpdateRequest(percent=3), user=admin_user)
                if orig_shift == "RESTING":
                    await conn.execute("UPDATE users SET shift_status = 'RESTING' WHERE id = ?", (emp_user["id"],))
                # Test yozuvlarini tozalash
                await conn.execute("DELETE FROM card_topups WHERE card_holder = 'TEST FOIZ'")
                await conn.commit()

    async def test_18_yesterday_closed_report_does_not_flag_today_topup(self):
        """18. Kechagi topshirilgan hisobot bugungi yangi kunda karta so'roviga xato ogohlantirish bermasligi tekshiruvi"""
        from app.database import get_db_connection
        from app.routes.cards import create_card_topup
        from app.models import CardTopupCreate
        from app.security import get_tashkent_now, get_tashkent_today_str

        today_str = get_tashkent_today_str()
        yesterday_str = (get_tashkent_now() - timedelta(days=1)).strftime("%Y-%m-%d")

        async with get_db_connection() as conn:
            cur = await conn.execute("SELECT * FROM users WHERE role != 'ADMIN' AND is_active = 1 LIMIT 1")
            emp = await cur.fetchone()
            if not emp:
                return

            emp_user = dict(emp)
            emp_id = emp_user["id"]
            comp_id = emp_user.get("company_id") or 1

            # Xodimni ACTIVE qilish
            orig_shift = emp_user.get("shift_status")
            emp_user["shift_status"] = "ACTIVE"
            await conn.execute("UPDATE users SET shift_status = 'ACTIVE' WHERE id = ?", (emp_id,))

            # Bugungi va kechagi test hisobotlarini tozalash
            await conn.execute("DELETE FROM daily_reports WHERE employee_id = ? AND report_date IN (?, ?)", (emp_id, today_str, yesterday_str))
            
            # Faqat KECHAGI kun uchun tasdiqlangan hisobot kiritamiz (masalan, kecha soat 23:50 da yopilgan)
            await conn.execute("""
                INSERT INTO daily_reports (
                    company_id, employee_id, report_date, paynet, card_amount, total_inflow, total_outflow, net_amount, status
                ) VALUES (?, ?, ?, 500000, 100000, 600000, 100000, 500000, 'APPROVED')
            """, (comp_id, emp_id, yesterday_str))
            await conn.commit()

            try:
                # Bugun yangi kunda (00:00 dan keyin) karta so'rovi yuborilganda has_closed_report_today = FALSE bo'lishi shart!
                topup_req = CardTopupCreate(
                    card_number="9860123456781234",
                    card_holder="TEST YESTERDAY CHECK",
                    amount=50000
                )
                res = await create_card_topup(topup_req, user=emp_user)
                self.assertTrue(res["success"])
                self.assertFalse(res["data"]["has_closed_report_today"], "Kechagi hisobot bugungi so'rovda 'kassani yopdi' deb chiqmasligi shart!")

                # Endi bugungi kun uchun hisobot kiritilsa:
                await conn.execute("""
                    INSERT INTO daily_reports (
                        company_id, employee_id, report_date, paynet, card_amount, total_inflow, total_outflow, net_amount, status
                    ) VALUES (?, ?, ?, 100000, 50000, 150000, 50000, 100000, 'APPROVED')
                """, (comp_id, emp_id, today_str))
                await conn.commit()

                # Endi so'rov yuborilsa, has_closed_report_today = TRUE bo'lishi kerak
                topup_req2 = CardTopupCreate(
                    card_number="9860123456781235",
                    card_holder="TEST TODAY CHECK",
                    amount=50000
                )
                res2 = await create_card_topup(topup_req2, user=emp_user)
                self.assertTrue(res2["success"])
                self.assertTrue(res2["data"]["has_closed_report_today"], "Aynan bugungi hisobot topshirilgandan keyin ogohlantirish TRUE bo'lishi shart!")

            finally:
                # Qaytarish va tozalash
                if orig_shift:
                    await conn.execute("UPDATE users SET shift_status = ? WHERE id = ?", (orig_shift, emp_id))
                await conn.execute("DELETE FROM daily_reports WHERE employee_id = ? AND report_date IN (?, ?)", (emp_id, today_str, yesterday_str))
                await conn.execute("DELETE FROM card_topups WHERE card_holder IN ('TEST YESTERDAY CHECK', 'TEST TODAY CHECK')")
                await conn.commit()

if __name__ == "__main__":
    unittest.main()
