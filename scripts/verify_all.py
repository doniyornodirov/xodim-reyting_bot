"""
XodimKPI CRM - Avtomatlashtirilgan Sifat Nazorati (Quality Gate)
Har qanday commit va deploy oldidan barcha kod bazasini to'liq tekshiradi:
1. Pyflakes orqali barcha fayllarda NameError / e'lon qilinmagan o'zgaruvchilarni tekshirish;
2. Barcha asosiy tizim testlarini ishga tushirish (tests/test_core_systems.py);
3. JavaScript sintaksisini tekshirish (static/js/app.js).
"""

import sys
import io
import subprocess
from pyflakes import api, reporter

def check_python_undefined_names():
    print("🔍 1. Python kodida NameError va e'lon qilinmagan o'zgaruvchilar tekshirilmoqda...")
    error_stream = io.StringIO()
    rep = reporter.Reporter(error_stream, error_stream)
    api.checkPath("app", reporter=rep)
    output = error_stream.getvalue()
    undefined = [line for line in output.splitlines() if "undefined name" in line]
    if undefined:
        print(f"❌ XATOLIK: app/ papkasida {len(undefined)} ta e'lon qilinmagan o'zgaruvchi (NameError) topildi:")
        for u in undefined:
            print("  ->", u)
        return False
    print("✅ 1. Python kodida 0 ta NameError! (Barcha o'zgaruvchi va importlar to'liq)")
    return True

def run_core_tests():
    print("🔍 2. Tizim testlari ishga tushirilmoqda (tests/test_core_systems.py)...")
    res = subprocess.run([sys.executable, "-m", "unittest", "tests/test_core_systems.py", "-v"])
    if res.returncode != 0:
        print("❌ XATOLIK: Tizim testlari muvaffaqiyatsiz yakunlandi!")
        return False
    print("✅ 2. Barcha tizim testlari 100% muvaffaqiyatli o'tdi!")
    return True

def check_js_syntax():
    print("🔍 3. JavaScript fayllari sintaksisi tekshirilmoqda...")
    res = subprocess.run(["node", "-c", "static/js/app.js"])
    if res.returncode != 0:
        print("❌ XATOLIK: static/js/app.js da sintaksis xatosi bor!")
        return False
    print("✅ 3. JavaScript sintaksisi 100% toza!")
    return True

def main():
    print("=" * 60)
    print("🛡️ XodimKPI CRM - Quality Gate Tekshiruvi")
    print("=" * 60)
    
    ok1 = check_python_undefined_names()
    ok2 = run_core_tests()
    ok3 = check_js_syntax()

    print("=" * 60)
    if ok1 and ok2 and ok3:
        print("🎉 BARCHA TEKSHIRUVLAR MUVAFFAQIYATLI O'TDI! Kod deploy qilishga 100% tayyor.")
        print("=" * 60)
        sys.exit(0)
    else:
        print("🛑 TEKSHIRUV MUVAFFAQIYATSIZ TUGADI! Xatoliklarni to'g'irlang.")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
