"""
Xodimni o'chirish (Delete Employee) va Firmadan butunlay chiqarish test to'plami.
"""

import unittest
import aiosqlite
from fastapi import HTTPException
from app.config import DB_PATH
from app.database import init_db, get_db_connection
from app.routes.admin import create_user, delete_user, get_all_users, CreateUserRequest

class TestDeleteEmployee(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.co1_admin = {
            "id": 4,
            "telegram_id": 8686341550,
            "full_name": "Bosh Rahbar",
            "role": "ADMIN",
            "company_id": 1,
            "is_super_admin": False
        }

        self.co2_admin = {
            "id": 999,
            "telegram_id": 9991112233,
            "full_name": "Begona Rahbar",
            "role": "ADMIN",
            "company_id": 99,
            "is_super_admin": False
        }

        # Test xodim yaratish
        self.test_emp_tg = 9988001122
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (self.test_emp_tg,))
            await conn.commit()

        u_req = CreateUserRequest(
            telegram_id=self.test_emp_tg,
            full_name="O'chiriluvchi Test Xodim",
            role="EMPLOYEE",
            password="testpassword123",
            initial_debt=50000
        )
        res = await create_user(u_req, self.co1_admin)
        self.test_emp_id = res["data"]["id"]

    async def asyncTearDown(self):
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (self.test_emp_tg,))
            await conn.commit()

    async def test_01_delete_regular_employee_success(self):
        """Oddiy xodim muvaffaqiyatli va butunlay o'chirilishi tekshiruvi"""
        # Xodim mavjudligini tasdiqlash
        users = await get_all_users(self.co1_admin)
        user_ids = [u["id"] for u in users["data"]]
        self.assertIn(self.test_emp_id, user_ids)

        # Xodimni o'chirish
        del_res = await delete_user(self.test_emp_id, self.co1_admin)
        self.assertTrue(del_res["success"])
        self.assertIn("firmadan butunlay o'chirildi", del_res["message"])

        # O'chirilgandan so'ng ro'yxatda chiqmasligi kerak
        users_after = await get_all_users(self.co1_admin)
        user_ids_after = [u["id"] for u in users_after["data"]]
        self.assertNotIn(self.test_emp_id, user_ids_after)

        # Bazada ham yo'qligini tekshirish
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT * FROM users WHERE id = ?", (self.test_emp_id,))
            user = await cur.fetchone()
            self.assertIsNone(user, "Xodim bazadan butunlay o'chirilgan bo'lishi shart!")

    async def test_02_admin_cannot_be_deleted(self):
        """Bosh Rahbar daxlsizligi: Adminni o'chirish taqiqlangan (HTTP 403)"""
        with self.assertRaises(HTTPException) as cm:
            await delete_user(self.co1_admin["id"], self.co1_admin)
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("Bosh Rahbar daxlsiz", cm.exception.detail)

    async def test_03_tenant_isolation_idor_prevention(self):
        """Begona firma rahbari boshqa firmaning xodimini o'chira olmasligi (HTTP 404)"""
        with self.assertRaises(HTTPException) as cm:
            await delete_user(self.test_emp_id, self.co2_admin)
        self.assertEqual(cm.exception.status_code, 404)

    async def test_04_delete_nonexistent_user(self):
        """Mavjud bo'lmagan xodim ID si bo'yicha 404 qaytishi"""
        with self.assertRaises(HTTPException) as cm:
            await delete_user(999999999, self.co1_admin)
        self.assertEqual(cm.exception.status_code, 404)

if __name__ == "__main__":
    unittest.main()
