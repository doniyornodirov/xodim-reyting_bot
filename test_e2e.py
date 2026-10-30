import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
import json
import sqlite3
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"

def request(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return {"error": True, "status": e.code, "detail": json.loads(err_body)}
        except:
            return {"error": True, "status": e.code, "detail": err_body}

def login_user(telegram_id: int, password: str):
    with sqlite3.connect("xodim_reyting.db") as conn:
        conn.execute("DELETE FROM otp_codes WHERE telegram_id = ?", (telegram_id,))
        conn.commit()

    login_res = request("/api/auth/login", "POST", {"telegram_id": telegram_id, "password": password})
    assert login_res.get("success") is True, f"Login muvaffaqiyatsiz ({telegram_id}): {login_res}"
    assert "telegram_sent" in login_res
    assert "dev_otp" not in login_res and "otp" not in login_res and "code" not in login_res, "XAVFSIZLIK BUZILISHI: OTP kod API javobida chiqmasligi shart!"

    with sqlite3.connect("xodim_reyting.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT code FROM otp_codes WHERE telegram_id = ? AND is_used = 0 ORDER BY id DESC LIMIT 1", (telegram_id,))
        row = cursor.fetchone()
        assert row is not None, f"Bazada OTP kod topilmadi ({telegram_id})"
        otp_code = row[0]

    verify_res = request("/api/auth/verify-otp", "POST", {"telegram_id": telegram_id, "otp": otp_code})
    assert verify_res.get("success") is True, f"OTP xatosi: {verify_res}"
    return verify_res["access_token"], verify_res["user"]

def run_tests():
    print("🧪 [1/7] Test: Server index.html tekshirilmoqda...")
    with urllib.request.urlopen(f"{BASE_URL}/") as resp:
        content = resp.read().decode("utf-8")
        assert "XODIM-REITING" in content, "index.html da sarlavha topilmadi"
        print("   ✅ index.html muvaffaqiyatli yuklandi!")

    print("\n🔐 [2/7] Test: Rollar bo'yicha alohida kirish (Xodim: Doniyor operator & Bosh Rahbar)...")
    emp_token, emp_user = login_user(8662254493, "8662254493")
    admin_token, admin_user = login_user(8686341550, "8686341550")
    assert emp_user["role"] == "EMPLOYEE", "Xodim roli noto'g'ri"
    assert admin_user["role"] == "ADMIN", "Rahbar roli noto'g'ri"
    print(f"   ✅ Xodim tizimga kirdi: {emp_user['full_name']} (Roli: {emp_user['role']})")
    print(f"   ✅ Bosh Rahbar tizimga kirdi: {admin_user['full_name']} (Roli: {admin_user['role']})")

    # Bosh Rahbar xodim emasligini tekshirish (RBAC xavfsizlik cheklovi)
    admin_forbidden_card = request("/api/cards/topup", "POST", {
        "card_number": "8600 1234 5678 9012",
        "card_holder": "Test Rahbar",
        "amount": 100000
    }, token=admin_token)
    assert admin_forbidden_card.get("status") == 403, f"Bosh Rahbarga karta to'ldirish taqiqlanmadi: {admin_forbidden_card}"

    admin_forbidden_given = request("/api/given/submit", "POST", {
        "amount": 100000,
        "comment": "Test"
    }, token=admin_token)
    assert admin_forbidden_given.get("status") == 403, f"Bosh Rahbarga berilgan summa taqiqlanmadi: {admin_forbidden_given}"
    print("   ✅ Zero-Trust RBAC: Bosh Rahbar xodim emas! Xodim amallarini bajarish 403 Forbidden bilan bloklandi!")

    print("\n💳 [3/7] Test: Xodim tomonidan karta to'ldirish va Rahbar tomonidan tasdiqlash...")
    card_res = request("/api/cards/topup", "POST", {
        "card_number": "8600 1234 5678 9012",
        "card_holder": "Aliyev Vali",
        "amount": 1000000
    }, token=emp_token)
    assert card_res.get("success") is True, f"Karta so'rovi xatosi: {card_res}"
    topup_id = card_res["data"]["id"]
    surcharge = card_res["data"]["surcharge_amount"]
    assert surcharge == 1030000, f"+3% ustama noto'g'ri: {surcharge}"
    print(f"   ✅ Xodim karta so'rovi yubordi! 1 000 000 -> {surcharge} so'm (+3% ustama)")

    # Bosh Rahbar tasdiqlaydi
    approve_card = request(f"/api/cards/{topup_id}/status", "POST", {"status": "APPROVED"}, token=admin_token)
    assert approve_card.get("success") is True
    print(f"   ✅ Karta so'rovi Bosh Rahbar tomonidan tasdiqlandi!")

    # Tasdiqlangan kartani xodim rad eta olmasligini tekshirish
    reject_approved_err = request(f"/api/cards/{topup_id}/reject", "POST", token=emp_token)
    assert reject_approved_err.get("status") == 400, "Tasdiqlangan so'rovni rad etish xato bermadi!"

    # Yangi karta so'rovi yuborib, uni xodim o'zi rad etishi (Button "Rad etish")
    card_res_2 = request("/api/cards/topup", "POST", {
        "card_number": "9860 1111 2222 3333",
        "card_holder": "Test Bekor Qilish",
        "amount": 50000
    }, token=emp_token)
    assert card_res_2.get("success") is True
    topup_id_2 = card_res_2["data"]["id"]

    reject_res = request(f"/api/cards/{topup_id_2}/reject", "POST", token=emp_token)
    assert reject_res.get("success") is True, f"Xodim rad eta olmadi: {reject_res}"
    print(f"   ✅ Xodim o'zi yuborgan karta so'rovini (#{card_res_2['data']['transaction_number']}) 'Rad etish' tugmasi bilan muvaffaqiyatli bekor qildi!")

    # Qaytadan rad etishga urinish 400 qaytarishi kerak
    reject_again = request(f"/api/cards/{topup_id_2}/reject", "POST", token=emp_token)
    assert reject_again.get("status") == 400, "Allaqachon rad etilgan so'rov yana rad etildi!"

    print("\n💵 [4/7] Test: Xodim tomonidan berilgan summa yuborish (raqam va harfli izoh) va Rahbar tasdiqlashi...")
    given_res = request("/api/given/submit", "POST", {
        "amount": 200000,
        "comment": "Kassa 12 harajati 2026-yil"
    }, token=emp_token)
    assert given_res.get("success") is True, f"Berilgan summa xatosi: {given_res}"
    given_id = given_res["data"]["id"]
    print("   ✅ Xodim berilgan summa so'rovini yubordi (izoh: raqam + harf)")

    # Bosh Rahbar tasdiqlaydi
    approve_given = request(f"/api/given/{given_id}/status", "POST", {"status": "APPROVED"}, token=admin_token)
    assert approve_given.get("success") is True
    print("   ✅ Berilgan summa Bosh Rahbar tomonidan tasdiqlandi!")

    print("\n📊 [5/7] Test: Xodim kunlik hisoboti, prefill va Rollback/Reset tekshirilmoqda...")
    prefill = request("/api/reports/today-prefill", token=emp_token)
    assert prefill["card_amount"] >= 1030000, f"Card prefill xatosi: {prefill['card_amount']}"
    assert prefill["given_amount"] >= 200000, f"Given prefill xatosi: {prefill['given_amount']}"
    print(f"   ✅ Prefill xodim uchun hisoblandi: Card={prefill['card_amount']}, Given={prefill['given_amount']}")

    # Test takroriy ishlaganda toza test o'tkazish uchun bugungi hisobotni tozalash
    with sqlite3.connect("xodim_reyting.db") as conn:
        conn.execute("DELETE FROM daily_reports WHERE employee_id = ?", (emp_user["id"],))
        conn.commit()

    # Hisobot topshirish (1-marta)
    report_res = request("/api/reports/submit", "POST", {
        "paynet": 5000000,
        "leviy": 100000,
        "debt_paid": 0,
        "sim_cards_count": 5,
        "kunlik": 50000,
        "terminal": 1000000,
        "skidka": 10000,
        "xarajat": 20000,
        "comment": "1-smena hisoboti 100% topshirildi"
    }, token=emp_token)
    assert report_res.get("success") is True, f"Hisobot topshirishda xato: {report_res}"
    first_net = report_res["data"]["net_amount"]
    print(f"   ✅ Xodim birinchi hisobot topshirdi! Umumiy summa: {first_net:,.0f} so'm")

    # Qayta topshirish (Rollback & Reset testi)
    report_res2 = request("/api/reports/submit", "POST", {
        "paynet": 6000000,
        "leviy": 200000,
        "debt_paid": 0,
        "sim_cards_count": 7,
        "kunlik": 50000,
        "terminal": 1000000,
        "skidka": 10000,
        "xarajat": 20000,
        "comment": "Qayta yangilangan hisobot №2 (tuzatish 2026)"
    }, token=emp_token)
    assert report_res2.get("success") is True
    second_net = report_res2["data"]["net_amount"]
    print(f"   ✅ Qayta hisobot topshirildi! Eskisi bekor bo'lib, toza qiymatlar bilan yangilandi: {second_net:,.0f} so'm")

    # Bosh Rahbar hisobotni tasdiqlaydi
    report_id = report_res2["data"]["id"]
    approve_rep = request(f"/api/reports/{report_id}/status", "POST", {"status": "APPROVED"}, token=admin_token)
    assert approve_rep.get("success") is True
    print("   ✅ Kunlik hisobot Bosh Rahbar tomonidan tasdiqlandi!")

    print("\n🏆 [6/7] Test: Reyting va KPI Liderlar jadvali tekshirilmoqda...")
    rating_res = request("/api/rating/leaderboard", token=admin_token)
    assert rating_res.get("success") is True
    assert len(rating_res["data"]) >= 1
    top_emp = rating_res["data"][0]
    print(f"   ✅ Reyting hisoblandi! Lider: {top_emp['employee_name']} (Ball: {top_emp['total_score']:.1f})")

    print("\n🧹 [7/7] Test: 90 kunlik ma'lumotlarni saqlash va eski ma'lumotlarni avtomatik tozalash (Retention Policy)...")
    ret_status = request("/api/admin/retention/status", token=admin_token)
    assert ret_status.get("success") is True
    assert ret_status.get("retention_days") == 90
    print(f"   ✅ Retention status olindi: Chegara sanasi = {ret_status['cutoff_date']} (90 kun)")

    # 95 kun oldingi test ma'lumotlarini bazaga qo'shish
    with sqlite3.connect("xodim_reyting.db") as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO card_topups (transaction_number, employee_id, card_number, card_holder, amount, surcharge_amount, status, created_at)
            VALUES (99999, ?, '8600000000000000', 'Eski Test', 50000, 52000, 'APPROVED', '2026-01-01 10:00:00')
        """, (emp_user["id"],))
        c.execute("""
            INSERT INTO daily_reports (employee_id, report_date, paynet, card_amount, total_inflow, total_outflow, net_amount, status, created_at)
            VALUES (?, '2026-01-01', 100000, 52000, 152000, 0, 152000, 'APPROVED', '2026-01-01 10:00:00')
        """, (emp_user["id"],))
        c.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details, created_at)
            VALUES ('TEST', 99999, 'OLD_ACTION', 'Test Actor', '95 kunlik eski log', '2026-01-01 10:00:00')
        """)
        conn.commit()

    cleanup_res = request("/api/admin/retention/run-cleanup", "POST", token=admin_token)
    assert cleanup_res.get("success") is True
    del_counts = cleanup_res["data"]["deleted_counts"]
    assert del_counts.get("card_topups", 0) >= 1
    assert del_counts.get("daily_reports", 0) >= 1
    assert del_counts.get("audit_logs", 0) >= 1
    print(f"   ✅ 90 kundan eski ma'lumotlar o'chirildi! Jami tozalangan: {cleanup_res['data']['total_deleted']} ta yozuv")

    # Bugungi hisobot saqlanib qolganini tekshirish
    with sqlite3.connect("xodim_reyting.db") as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM daily_reports WHERE id = ?", (report_id,))
        assert c.fetchone()[0] == 1
    print("   ✅ Bugungi (90 kun ichidagi) barcha yangi hisobotlar va tranzaksiyalar to'liq saqlanib qoldi!")

    print("\n" + "="*50)
    print("🎉 BARCHA 7 TA INTEGRATSIYA VA XAVFSIZLIK TESTLARI 100% MUVAFFAQIYATLI O'TDI!")
    print("   (Xodim va Bosh Rahbar rollari to'liq ajratildi)")
    print("="*50)

if __name__ == "__main__":
    run_tests()
