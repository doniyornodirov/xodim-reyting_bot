import os
import sys
import time
import asyncio
from pathlib import Path
from datetime import datetime, timezone

# Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
TEST_DB_PATH = BASE_DIR / "test_stress_200.db"
os.environ["DB_PATH"] = str(TEST_DB_PATH)
os.environ["BOT_TOKEN"] = ""  # Mock telegram to avoid real network calls during load test

import aiosqlite
import httpx
from app.config import JWT_SECRET, JWT_ALGORITHM
from app.security import hash_password, create_access_token
from app.database import init_db
from app.main import app
import app.routes.auth as auth_mod
import app.bot as bot_mod

# Mock send_otp_to_telegram to return immediately so we measure pure backend concurrency
async def mock_send_otp(*args, **kwargs):
    await asyncio.sleep(0.01) # 10ms network sim
    return True

auth_mod.send_otp_to_telegram = mock_send_otp
bot_mod.send_otp_to_telegram = mock_send_otp

TOTAL_EMPLOYEES = 200
TOTAL_ADMINS = 5

async def setup_test_database():
    """Test bazasini tozalash va 200 ta xodim + 5 ta rahbar yaratish"""
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass

    await init_db()

    async with aiosqlite.connect(TEST_DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Kompaniyaning max_employees sini 1000 ga ko'tarish
        await conn.execute("UPDATE companies SET max_employees = 1000 WHERE id = 1;")

        # Boshlang'ich parol
        pwd_hash = hash_password("password123")

        # 200 ta xodim kiritish
        emp_records = []
        for i in range(1, TOTAL_EMPLOYEES + 1):
            tg_id = 9000000000 + i
            full_name = f"Xodim Operator {i:03d}"
            emp_records.append((
                1, tg_id, full_name, "EMPLOYEE", pwd_hash, 0.0, 1,
                "Bosh Ofis", 41.311087, 69.240562, 100, "08:00", "22:00", "WORKING"
            ))

        await conn.executemany("""
            INSERT INTO users (
                company_id, telegram_id, full_name, role, password_hash, debt_amount, is_active,
                workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                work_start_time, work_end_time, shift_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, emp_records)

        # 5 ta admin kiritish
        admin_records = []
        for i in range(1, TOTAL_ADMINS + 1):
            tg_id = 8000000000 + i
            full_name = f"Rahbar Admin {i}"
            admin_records.append((
                1, tg_id, full_name, "ADMIN", pwd_hash, 0.0, 1
            ))

        await conn.executemany("""
            INSERT INTO users (
                company_id, telegram_id, full_name, role, password_hash, debt_amount, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, admin_records)

        await conn.commit()

        # Barcha xodimlar va adminlarni xotiraga olish
        cursor = await conn.execute("SELECT id, telegram_id, full_name, role FROM users ORDER BY id ASC")
        rows = await cursor.fetchall()
        users_list = [dict(r) for r in rows]

    return users_list

def generate_tokens(users_list):
    tokens = {}
    for u in users_list:
        token = create_access_token({
            "sub": str(u["id"]),
            "telegram_id": u["telegram_id"],
            "role": u["role"],
            "full_name": u["full_name"]
        })
        tokens[u["id"]] = token
    return tokens

async def run_stress_test():
    print("=" * 70)
    print("🚀 [STRESS & CONCURRENCY TEST] 200 TA XODIM VA RAHBAR YUKLAMA TESTI")
    print("=" * 70)

    print("\n📦 1. Test bazasi tayyorlanmoqda (200 ta xodim + 5 ta rahbar)...")
    users = await setup_test_database()
    tokens = generate_tokens(users)
    employees = [u for u in users if u["role"] == "EMPLOYEE"]
    admins = [u for u in users if u["role"] == "ADMIN"]
    print(f"   ✅ Baza tayyor: {len(employees)} ta xodim, {len(admins)} ta rahbar.")

    transport = httpx.ASGITransport(app=app)
    limits = httpx.Limits(max_keepalive_connections=300, max_connections=300)

    results = {}

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", limits=limits, timeout=30.0) as client:

        # -------------------------------------------------------------
        # TEST 1: 200 TA XODIM BIR VAQTNING O'ZIDA GEOLOKATSIYA PING YUBORISHI
        # -------------------------------------------------------------
        print("\n📍 TEST 1: 200 ta xodim bir vaqtning o'zida /api/location/ping yubormoqda...")
        start_t = time.perf_counter()

        async def ping_worker(emp):
            t0 = time.perf_counter()
            token = tokens[emp["id"]]
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "latitude": 41.311087 + (emp["id"] * 0.00001),
                "longitude": 69.240562 + (emp["id"] * 0.00001),
                "accuracy": 15.0
            }
            try:
                resp = await client.post("/api/location/ping", json=payload, headers=headers)
                latency = (time.perf_counter() - t0) * 1000
                return {"status": resp.status_code, "latency": latency, "data": resp.json() if resp.status_code == 200 else resp.text}
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                return {"status": 500, "latency": latency, "error": str(e)}

        ping_tasks = [ping_worker(emp) for emp in employees]
        ping_res = await asyncio.gather(*ping_tasks)
        total_time_1 = (time.perf_counter() - start_t) * 1000

        successes_1 = [r for r in ping_res if r["status"] == 200]
        failures_1 = [r for r in ping_res if r["status"] != 200]
        latencies_1 = [r["latency"] for r in ping_res]
        latencies_1.sort()

        p50_1 = latencies_1[len(latencies_1) // 2]
        p95_1 = latencies_1[int(len(latencies_1) * 0.95)]
        p99_1 = latencies_1[int(len(latencies_1) * 0.99)]
        max_1 = latencies_1[-1]

        print(f"   📊 Natija: Jami {len(ping_res)} so'rov | Muvaffaqiyatli: {len(successes_1)} | Xato: {len(failures_1)}")
        print(f"   ⏱️ Umumiy vaqt: {total_time_1:.1f}ms | RPS: {len(ping_res)/(total_time_1/1000):.1f} req/s")
        print(f"   ⚡ Kechikish: Mediana (p50): {p50_1:.1f}ms | p95: {p95_1:.1f}ms | p99: {p99_1:.1f}ms | Max: {max_1:.1f}ms")
        if failures_1:
            print(f"   ❌ Xatolik namunasi: {failures_1[:3]}")

        results["location_ping"] = {
            "total": len(ping_res),
            "success": len(successes_1),
            "failed": len(failures_1),
            "p50_ms": p50_1,
            "p95_ms": p95_1,
            "max_ms": max_1,
            "failures": failures_1[:3]
        }

        # -------------------------------------------------------------
        # TEST 2: 200 TA XODIM BIR VAQTNING O'ZIDA TELEMETRIYA YUBORISHI
        # -------------------------------------------------------------
        print("\n🔋 TEST 2: 200 ta xodim bir vaqtning o'zida /api/location/telemetry yubormoqda...")
        start_t = time.perf_counter()

        async def telemetry_worker(emp):
            t0 = time.perf_counter()
            token = tokens[emp["id"]]
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "has_motion": True,
                "is_charging": False,
                "stillness_seconds": 10
            }
            try:
                resp = await client.post("/api/location/telemetry", json=payload, headers=headers)
                latency = (time.perf_counter() - t0) * 1000
                return {"status": resp.status_code, "latency": latency}
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                return {"status": 500, "latency": latency, "error": str(e)}

        telem_tasks = [telemetry_worker(emp) for emp in employees]
        telem_res = await asyncio.gather(*telem_tasks)
        total_time_2 = (time.perf_counter() - start_t) * 1000

        successes_2 = [r for r in telem_res if r["status"] == 200]
        failures_2 = [r for r in telem_res if r["status"] != 200]
        latencies_2 = sorted([r["latency"] for r in telem_res])

        print(f"   📊 Natija: Jami {len(telem_res)} | Muvaffaqiyatli: {len(successes_2)} | Xato: {len(failures_2)}")
        print(f"   ⏱️ Umumiy vaqt: {total_time_2:.1f}ms | p95: {latencies_2[int(len(latencies_2)*0.95)]:.1f}ms | Max: {latencies_2[-1]:.1f}ms")
        if failures_2:
            print(f"   ❌ Xatolik namunasi: {failures_2[:3]}")

        # -------------------------------------------------------------
        # TEST 3: 50 TA XODIM BIR VAQTDA KARTA TO'LDIRISH SO'ROVI YUBORISHI (RACE CONDITION CHECK)
        # -------------------------------------------------------------
        print("\n💳 TEST 3: 50 ta xodim bir vaqtning o'zida /api/cards/topup yubormoqda (Race Condition & Lock tekshiruvi)...")
        start_t = time.perf_counter()

        async def topup_worker(emp, idx):
            t0 = time.perf_counter()
            token = tokens[emp["id"]]
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "card_number": f"8600 1234 5678 {idx:04d}",
                "card_holder": "Aliyev Vali",
                "amount": 500000 + (idx * 10000)
            }
            try:
                resp = await client.post("/api/cards/topup", json=payload, headers=headers)
                latency = (time.perf_counter() - t0) * 1000
                return {"status": resp.status_code, "latency": latency, "data": resp.json() if resp.status_code == 200 else resp.text}
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                return {"status": 500, "latency": latency, "error": str(e)}

        topup_tasks = [topup_worker(employees[i], i) for i in range(50)]
        topup_res = await asyncio.gather(*topup_tasks)
        total_time_3 = (time.perf_counter() - start_t) * 1000

        successes_3 = [r for r in topup_res if r["status"] == 200]
        failures_3 = [r for r in topup_res if r["status"] != 200]

        # Baza tekshiruvi: transaction_number larda dublikatlar bormi?
        async with aiosqlite.connect(TEST_DB_PATH) as conn:
            cursor = await conn.execute("SELECT transaction_number, COUNT(*) FROM card_topups GROUP BY transaction_number HAVING COUNT(*) > 1")
            duplicate_txs = await cursor.fetchall()
            cursor2 = await conn.execute("SELECT COUNT(*) FROM card_topups")
            total_topups_saved = (await cursor2.fetchone())[0]

        print(f"   📊 Natija: Jami {len(topup_res)} | Muvaffaqiyatli: {len(successes_3)} | Xato: {len(failures_3)}")
        print(f"   ⏱️ Umumiy vaqt: {total_time_3:.1f}ms")
        print(f"   🔍 Bazaga saqlangan jami topuplar: {total_topups_saved} ta")
        if duplicate_txs:
            print(f"   🚨 KRITIK RACE CONDITION ANIQLANDI! Dublikat transaction_number lar soni: {len(duplicate_txs)}")
            for d in duplicate_txs[:5]:
                print(f"      -> #{d[0]} raqami {d[1]} marta takrorlangan!")
        else:
            print("   ✅ Transaction number dublikatlari topilmadi.")

        results["card_topup"] = {
            "total": len(topup_res),
            "success": len(successes_3),
            "failed": len(failures_3),
            "duplicate_tx_count": len(duplicate_txs),
            "duplicates": [f"#{d[0]} ({d[1]}x)" for d in duplicate_txs[:5]]
        }

        # -------------------------------------------------------------
        # TEST 4: RAHBARLAR KUZATUV PANELINI BIR VAQTDA SO'ROV QILISHI (10 TA PARALLEL SO'ROV)
        # -------------------------------------------------------------
        print("\n👥 TEST 4: Rahbarlar bir vaqtda xodimlar va lokatsiyalar ro'yxatini yuklamoqda...")
        start_t = time.perf_counter()

        async def admin_worker(adm):
            t0 = time.perf_counter()
            token = tokens[adm["id"]]
            headers = {"Authorization": f"Bearer {token}"}
            try:
                r1 = await client.get("/api/location/employees", headers=headers)
                r2 = await client.get("/api/admin/employees", headers=headers)
                latency = (time.perf_counter() - t0) * 1000
                return {"status": r1.status_code if r1.status_code != 200 else r2.status_code, "latency": latency}
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                return {"status": 500, "latency": latency, "error": str(e)}

        admin_tasks = [admin_worker(admins[i % len(admins)]) for i in range(10)]
        admin_res = await asyncio.gather(*admin_tasks)
        total_time_4 = (time.perf_counter() - start_t) * 1000
        successes_4 = [r for r in admin_res if r["status"] == 200]
        failures_4 = [r for r in admin_res if r["status"] != 200]
        print(f"   📊 Natija: Jami {len(admin_res)} | Muvaffaqiyatli: {len(successes_4)} | Xato: {len(failures_4)}")
        print(f"   ⏱️ Umumiy vaqt: {total_time_4:.1f}ms")

        # -------------------------------------------------------------
        # TEST 5: 50 TA XODIM KUNLIK HISOBOT VA BERILGAN SUMMA TOPSHIRISHI
        # -------------------------------------------------------------
        print("\n📝 TEST 5: 50 ta xodim bir vaqtning o'zida hisobot va berilgan summa topshirmoqda...")
        start_t = time.perf_counter()

        async def report_worker(emp, idx):
            t0 = time.perf_counter()
            token = tokens[emp["id"]]
            headers = {"Authorization": f"Bearer {token}"}
            payload_rep = {
                "paynet": 200000 + (idx * 5000),
                "card_amount": 0,
                "leviy": 50000,
                "debt_paid": 0,
                "sim_cards_count": 5,
                "kunlik": 50000,
                "terminal": 0,
                "skidka": 0,
                "xarajat": 10000,
                "comment": f"Hisobot {idx}"
            }
            payload_given = {
                "amount": 100000 + (idx * 5000),
                "comment": f"Berilgan summa {idx}"
            }
            try:
                r1 = await client.post("/api/reports/submit", json=payload_rep, headers=headers)
                r2 = await client.post("/api/given/submit", json=payload_given, headers=headers)
                latency = (time.perf_counter() - t0) * 1000
                st = r1.status_code if r1.status_code != 200 else r2.status_code
                return {"status": st, "latency": latency, "detail": r1.text if r1.status_code != 200 else r2.text}
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                return {"status": 500, "latency": latency, "error": str(e)}

        rep_tasks = [report_worker(employees[i], i) for i in range(50)]
        rep_res = await asyncio.gather(*rep_tasks)
        total_time_5 = (time.perf_counter() - start_t) * 1000
        successes_5 = [r for r in rep_res if r["status"] == 200]
        failures_5 = [r for r in rep_res if r["status"] != 200]
        print(f"   📊 Natija: Jami {len(rep_res)} | Muvaffaqiyatli: {len(successes_5)} | Xato: {len(failures_5)}")
        print(f"   ⏱️ Umumiy vaqt: {total_time_5:.1f}ms")
        if failures_5:
            print(f"   ❌ Xatolik namunasi: {failures_5[:2]}")

        # -------------------------------------------------------------
        # TEST 6: REYTING LEADERBOARD (50 TA PARALLEL SO'ROV)
        # -------------------------------------------------------------
        print("\n🏆 TEST 6: Reyting leaderboard (50 ta parallel so'rov)...")
        start_t = time.perf_counter()

        async def rating_worker(emp):
            t0 = time.perf_counter()
            token = tokens[emp["id"]]
            headers = {"Authorization": f"Bearer {token}"}
            try:
                resp = await client.get("/api/rating/leaderboard", headers=headers)
                latency = (time.perf_counter() - t0) * 1000
                return {"status": resp.status_code, "latency": latency}
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                return {"status": 500, "latency": latency, "error": str(e)}

        rating_tasks = [rating_worker(employees[i]) for i in range(50)]
        rating_res = await asyncio.gather(*rating_tasks)
        total_time_6 = (time.perf_counter() - start_t) * 1000
        successes_6 = [r for r in rating_res if r["status"] == 200]
        failures_6 = [r for r in rating_res if r["status"] != 200]
        latencies_6 = sorted([r["latency"] for r in rating_res])
        print(f"   📊 Natija: Jami {len(rating_res)} | Muvaffaqiyatli: {len(successes_6)} | Xato: {len(failures_6)}")
        print(f"   ⏱️ Umumiy vaqt: {total_time_6:.1f}ms | p95: {latencies_6[int(len(latencies_6)*0.95)]:.1f}ms")

        # -------------------------------------------------------------
        # TEST 7: 50 TA FOYDALANUVCHINING BIR VAQTNING O'ZIDA LOGIN QILISHI (_otp_lock BOTTLENECK)
        # -------------------------------------------------------------
        print("\n🔑 TEST 7: 50 ta foydalanuvchi bir vaqtning o'zida /api/auth/login so'rovini yubormoqda...")
        start_t = time.perf_counter()

        async def login_worker(emp):
            t0 = time.perf_counter()
            payload = {
                "telegram_id": emp["telegram_id"],
                "password": "password123"
            }
            try:
                resp = await client.post("/api/auth/login", json=payload)
                latency = (time.perf_counter() - t0) * 1000
                return {"status": resp.status_code, "latency": latency, "detail": resp.text if resp.status_code != 200 else ""}
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                return {"status": 500, "latency": latency, "error": str(e)}

        login_tasks = [login_worker(employees[i]) for i in range(50)]
        login_res = await asyncio.gather(*login_tasks)
        total_time_7 = (time.perf_counter() - start_t) * 1000
        successes_7 = [r for r in login_res if r["status"] == 200]
        failures_7 = [r for r in login_res if r["status"] != 200]
        latencies_7 = sorted([r["latency"] for r in login_res])

        print(f"   📊 Natija: Jami {len(login_res)} | Muvaffaqiyatli: {len(successes_7)} | Xato: {len(failures_7)}")
        print(f"   ⏱️ Umumiy vaqt: {total_time_7:.1f}ms ({total_time_7/1000:.2f} soniya)")
        print(f"   ⚡ Kechikish: Min: {latencies_7[0]:.1f}ms | p50: {latencies_7[len(latencies_7)//2]:.1f}ms | p95: {latencies_7[int(len(latencies_7)*0.95)]:.1f}ms | Max: {latencies_7[-1]:.1f}ms")
        if failures_7:
            print(f"   ❌ Xatolik namunasi: {failures_7[:2]}")

    print("\n" + "=" * 70)
    print("🏁 STRESS TEST YAKUNLANDI")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_stress_test())
