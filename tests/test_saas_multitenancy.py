"""
SaaS Ko'p Firmali (Multi-Tenant) CRM Arxitekturasi va Foydalanuvchilar Izolyatsiyasi Test To'plami
Yangi qo'shilgan firmalar, ularning rahbarlari, kassirlari va xodimlari muammosiz ishlashini 100% tekshiradi.
"""

import unittest
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
import aiosqlite
from app.config import DB_PATH
from app.database import init_db, get_db_connection
from app.security import hash_password, create_access_token, get_tashkent_today_str
from app.dependencies import get_current_user, invalidate_user_cache
from app.routes.saas import create_company, toggle_company_active, CreateCompanyRequest
from app.routes.admin import get_all_users, create_user, CreateUserRequest, assign_debt, SetDebtRequest
from app.routes.cards import (
    get_card_surcharge_rate, 
    update_card_surcharge_rate, 
    CardSurchargeUpdateRequest,
    create_card_topup, 
    update_topup_status
)
from app.routes.reports import submit_daily_report, get_all_reports, update_report_status, DailyReportCreate
from app.routes.cashier import get_active_employees, record_handover, get_my_handovers
from app.models import CashierHandoverCreate, CardTopupCreate, StatusActionRequest
from app.routes.sim_cards import distribute_sim_cards, search_sim_card, SimDistributeRequest
from app.routes.rating import get_leaderboard
from app.services.cashier_service import calculate_daily_cashier_comparison

class TestSaaSWorkflows(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.super_admin = {
            "id": 10,
            "telegram_id": 8694797293,
            "full_name": "Dasturchi Admin",
            "role": "DEVELOPER",
            "is_super_admin": True,
            "company_id": 0
        }

        # Test firma yaratish
        self.co2_tg = 9988776655
        self.co2_name = "Yangi Oltin Voha Telecom"
        
        # Avvalgi test qoldiqlarini tozalash
        async with get_db_connection() as conn:
            cur = await conn.execute("SELECT id FROM companies WHERE owner_telegram_id = ?", (self.co2_tg,))
            old_c = await cur.fetchone()
            if old_c:
                c_id = old_c["id"]
                await conn.execute("DELETE FROM card_topups WHERE company_id = ?", (c_id,))
                await conn.execute("DELETE FROM given_amounts WHERE company_id = ?", (c_id,))
                await conn.execute("DELETE FROM daily_reports WHERE company_id = ?", (c_id,))
                await conn.execute("DELETE FROM cashier_handovers WHERE company_id = ?", (c_id,))
                await conn.execute("DELETE FROM sim_cards WHERE company_id = ?", (c_id,))
                await conn.execute("DELETE FROM sim_distributions WHERE company_id = ?", (c_id,))
                await conn.execute("DELETE FROM users WHERE company_id = ?", (c_id,))
                await conn.execute("DELETE FROM companies WHERE id = ?", (c_id,))
                await conn.commit()

        # 1. Yangi firma yaratish
        req = CreateCompanyRequest(
            name=self.co2_name,
            owner_telegram_id=self.co2_tg,
            owner_name="Yangi Rahbar",
            plan="STANDARD",
            subscription_days=30,
            initial_password="pass123password"
        )
        res = await create_company(req, self.super_admin)
        self.assertTrue(res["success"])
        self.co2_id = res["data"]["company_id"]
        self.co2_owner_id = res["data"]["owner_user_id"]

        self.co2_admin = {
            "id": self.co2_owner_id,
            "telegram_id": self.co2_tg,
            "full_name": "Yangi Rahbar",
            "role": "ADMIN",
            "company_id": self.co2_id,
            "is_super_admin": False
        }

        # 2. Yangi firmaga xodim va kassir yaratish
        self.co2_emp_tg = 9988776601
        self.co2_cashier_tg = 9988776602

        u_req1 = CreateUserRequest(
            telegram_id=self.co2_emp_tg,
            full_name="Yangi Firma Xodimi",
            role="EMPLOYEE",
            password="pwd_emp_pass1",
            initial_debt=100000
        )
        u1_res = await create_user(u_req1, self.co2_admin)
        self.co2_emp_id = u1_res["data"]["id"]

        u_req2 = CreateUserRequest(
            telegram_id=self.co2_cashier_tg,
            full_name="Yangi Firma Kassiri",
            role="CASHIER",
            password="pwd_cash_pass2",
            initial_debt=0
        )
        u2_res = await create_user(u_req2, self.co2_admin)
        self.co2_cashier_id = u2_res["data"]["id"]

        self.co2_emp = {
            "id": self.co2_emp_id,
            "telegram_id": self.co2_emp_tg,
            "full_name": "Yangi Firma Xodimi",
            "role": "EMPLOYEE",
            "company_id": self.co2_id,
            "shift_status": "WORKING"
        }

        self.co2_cashier = {
            "id": self.co2_cashier_id,
            "telegram_id": self.co2_cashier_tg,
            "full_name": "Yangi Firma Kassiri",
            "role": "CASHIER",
            "company_id": self.co2_id,
            "shift_status": "WORKING"
        }

        # Bosh tashkilot (Company 1) Admin foydalanuvchisi
        self.co1_admin = {
            "id": 4,
            "telegram_id": 8686341550,
            "full_name": "Bosh Rahbar",
            "role": "ADMIN",
            "company_id": 1,
            "is_super_admin": False
        }

    async def asyncTearDown(self):
        async with get_db_connection() as conn:
            await conn.execute("DELETE FROM card_topups WHERE company_id = ?", (self.co2_id,))
            await conn.execute("DELETE FROM given_amounts WHERE company_id = ?", (self.co2_id,))
            await conn.execute("DELETE FROM daily_reports WHERE company_id = ?", (self.co2_id,))
            await conn.execute("DELETE FROM cashier_handovers WHERE company_id = ?", (self.co2_id,))
            await conn.execute("DELETE FROM sim_cards WHERE company_id = ?", (self.co2_id,))
            await conn.execute("DELETE FROM sim_distributions WHERE company_id = ?", (self.co2_id,))
            await conn.execute("DELETE FROM users WHERE company_id = ?", (self.co2_id,))
            await conn.execute("DELETE FROM companies WHERE id = ?", (self.co2_id,))
            await conn.commit()

    async def test_01_user_and_employee_tenant_isolation(self):
        """1. Foydalanuvchilar qat'iy ravishda faqat o'z firmasiga tegishli bo'lishi tekshiruvi"""
        users_co2 = await get_all_users(self.co2_admin)
        co2_user_ids = [u["id"] for u in users_co2["data"]]

        self.assertIn(self.co2_owner_id, co2_user_ids)
        self.assertIn(self.co2_emp_id, co2_user_ids)
        self.assertIn(self.co2_cashier_id, co2_user_ids)
        self.assertNotIn(self.co1_admin["id"], co2_user_ids, "Bosh tashkilot rahbari yangi firma ro'yxatida ko'rinmasligi kerak!")

        # Bosh tashkilot foydalanuvchilari orasida yangi firma xodimlari bo'lmasligi kerak
        users_co1 = await get_all_users(self.co1_admin)
        co1_user_ids = [u["id"] for u in users_co1["data"]]
        self.assertNotIn(self.co2_emp_id, co1_user_ids, "Yangi firma xodimi 1-firmada mutlaqo ko'rinmasligi shart!")

    async def test_02_card_topup_and_surcharge_tenant_isolation(self):
        """2. Karta so'rovlari va foiz stavkalari har bir firma uchun alohida ishlashi"""
        # 1-firma 3% turganini tekshirish
        sur1 = await get_card_surcharge_rate(self.co1_admin)
        self.assertEqual(sur1["percent"], 3)

        # 2-firma ustamasini 5% ga o'zgartirish
        up_res = await update_card_surcharge_rate(CardSurchargeUpdateRequest(percent=5), self.co2_admin)
        self.assertTrue(up_res["success"])

        # 1-firma foizi o'zgarmasdan 3% qolganini tasdiqlash
        sur1_after = await get_card_surcharge_rate(self.co1_admin)
        self.assertEqual(sur1_after["percent"], 3)

        # 2-firma xodimi 1 000 000 so'm karta so'rovi yuboradi (5% bilan: 1 050 000 so'm)
        topup_req = CardTopupCreate(
            card_number="8600 0000 0000 0002",
            card_holder="Xaridor Oltin Voha",
            amount=1000000,
            idempotency_key="topup-co2-1"
        )
        res_t = await create_card_topup(topup_req, self.co2_emp)
        self.assertTrue(res_t["success"])
        topup_id = res_t["data"]["id"]
        self.assertEqual(res_t["data"]["surcharge_amount"], 1050000)

        # IDOR xavfsizlik tekshiruvi: 1-firma rahbari 2-firmaning so'rovini tasdiqlay olmasligi kerak (404)
        with self.assertRaises(HTTPException) as cm:
            await update_topup_status(topup_id, StatusActionRequest(status="APPROVED"), self.co1_admin)
        self.assertEqual(cm.exception.status_code, 404)

        # 2-firma rahbari o'z so'rovini muvaffaqiyatli tasdiqlaydi
        res_app = await update_topup_status(topup_id, StatusActionRequest(status="APPROVED"), self.co2_admin)
        self.assertTrue(res_app["success"])

    async def test_03_sim_cards_and_daily_reports_tenant_isolation(self):
        """3. Sim-kartalar tarqatish va kunlik hisobotlarning firma bo'yicha to'liq izolyatsiyasi"""
        # 2-firma uchun 5 ta Uzmobile sim-karta tarqatish
        dist_req = SimDistributeRequest(
            operator_type="Uzmobile",
            start_serial="999000000000000001",
            end_serial="999000000000000005",
            employee_id=self.co2_emp_id
        )
        async with get_db_connection() as conn:
            dist_res = await distribute_sim_cards(dist_req, current_user=self.co2_admin, db=conn)
            self.assertTrue(dist_res["success"])

            # 1-firma rahbari seriya bo'yicha qidirganda 0 ta chiqishi kerak
            search_co1 = await search_sim_card(serial="999000000000000001", current_user=self.co1_admin, db=conn)
            self.assertEqual(len(search_co1["data"]), 0, "Boshqa firmaning sim-kartasi ko'rinmasligi kerak!")

            # 2-firma rahbari qidirganda topilishi kerak
            search_co2 = await search_sim_card(serial="999000000000000001", current_user=self.co2_admin, db=conn)
            self.assertEqual(len(search_co2["data"]), 1)

        # 2-firma xodimi kunlik hisobot topshiradi
        today_str = get_tashkent_today_str()
        rep_req = DailyReportCreate(
            naqd=500000,
            plastik=200000,
            paynet=100000,
            sim_uzmobile=2,
            sim_cards_count=2,
            kunlik=50000,
            terminal=0,
            skidka=0,
            xarajat=0,
            debt_paid=50000,
            comment="Co2 birinchi hisobot",
            idempotency_key="rep-co2-today"
        )
        rep_res = await submit_daily_report(rep_req, self.co2_emp)
        self.assertTrue(rep_res["success"])
        rep_id = rep_res["data"]["id"]

        # 1-firma rahbarining hisobotlar ro'yxatida chiqmasligi kerak
        reps_co1 = await get_all_reports(status="all", user=self.co1_admin)
        rep_ids_co1 = [r["id"] for r in reps_co1["data"]]
        self.assertNotIn(rep_id, rep_ids_co1)

        # 2-firma rahbari hisobotni tasdiqlaydi
        app_res = await update_report_status(rep_id, StatusActionRequest(status="APPROVED"), self.co2_admin)
        self.assertTrue(app_res["success"])

        # Qarz to'g'ri chegirilganini tekshirish (100 000 - 50 000 = 50 000)
        async with get_db_connection() as conn:
            cur = await conn.execute("SELECT debt_amount FROM users WHERE id = ?", (self.co2_emp_id,))
            rem_debt = (await cur.fetchone())[0]
            self.assertEqual(rem_debt, 50000)

    async def test_04_cashier_and_rating_tenant_isolation(self):
        """4. Kassir qabul qilish va Reyting hisob-kitoblarining to'liq mustaqilligi"""
        today_str = get_tashkent_today_str()

        # 2-firma kassiri o'z xodimlarini ro'yxatda ko'rishi kerak
        active_emps_co2 = await get_active_employees(date=today_str, user=self.co2_cashier)
        emp_ids = [e["id"] for e in active_emps_co2["data"]]
        self.assertIn(self.co2_emp_id, emp_ids)

        # 1-firma kassiri ro'yxatida 2-firma xodimi chiqmasligi kerak
        co1_cashier = {"id": 5, "company_id": 1, "role": "CASHIER", "shift_status": "WORKING"}
        active_emps_co1 = await get_active_employees(date=today_str, user=co1_cashier)
        co1_emp_ids = [e["id"] for e in active_emps_co1["data"]]
        self.assertNotIn(self.co2_emp_id, co1_emp_ids)

        # 2-firma kassiri kassa qabul qiladi
        hand_req = CashierHandoverCreate(
            employee_id=self.co2_emp_id,
            handover_date=today_str,
            amount_uzs=650000,
            amount_usd=0,
            idempotency_key="handover-co2-1"
        )
        hand_res = await record_handover(hand_req, self.co2_cashier)
        self.assertTrue(hand_res["success"])

        # Tarixda faqat 2-firmaning kassiri o'z kassa yozuvini ko'rishi kerak
        my_hands = await get_my_handovers(date=None, user=self.co2_cashier)
        self.assertEqual(my_hands["summary"]["today_total"], 650000)

        # 1-firma kassiri uchun bu 650 000 so'm ko'rinmasligi kerak
        co1_hands = await get_my_handovers(date=None, user=co1_cashier)
        co1_records = [h["id"] for h in co1_hands["data"]]
        self.assertNotIn(hand_res["data"]["id"], co1_records)

        # Reyting / Leaderboard izolyatsiyasi
        rating_res = await get_leaderboard(period="monthly", user=self.co2_admin)
        leaderboard_ids = [r["employee_id"] for r in rating_res["data"]]
        self.assertIn(self.co2_emp_id, leaderboard_ids)
        # 1-firma xodimlari 2-firmaning reytingida bo'lmasligi kerak
        self.assertNotIn(16, leaderboard_ids)

    async def test_05_company_status_toggle_and_security_lockout(self):
        """5. Firma bloklanganda uning foydalanuvchilari avtomatik bloklanishi"""
        from fastapi.security import HTTPAuthorizationCredentials

        # Token yaratish
        token = create_access_token({"sub": str(self.co2_owner_id)})
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        # Hozir faol
        invalidate_user_cache(self.co2_owner_id)
        user = await get_current_user(creds)
        self.assertEqual(user["id"], self.co2_owner_id)

        # Super Admin firmani bloklaydi
        t_res = await toggle_company_active(self.co2_id, self.super_admin)
        self.assertFalse(t_res["is_active"])

        # Keshni tozalash va qayta kirishga urinish: HTTP 403 berishi shart!
        invalidate_user_cache(self.co2_owner_id)
        with self.assertRaises(HTTPException) as cm:
            await get_current_user(creds)
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("vaqtinchalik to'xtatilgan", cm.exception.detail)

if __name__ == "__main__":
    unittest.main()
