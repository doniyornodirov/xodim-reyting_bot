# GEMINI.md — Xodim-Reyting Loyihasi Uchun Asosiy Xotira (Persistent Memory)

> **Loyiha maqsadi**: Tashkilotdagi xodimlarning ish faoliyati, KPI va reyting ballarini hisoblovchi, monitoring qiluvchi yuqori yuklamaga chidamli va xavfsiz tizim.
> **Asos**: https://claude-presentation.netlify.app/ metodologiyasi Gemini va Antigravity muhitiga to'liq moslashtirilgan holda (Memory, Settings, Rules, Hooks, Skills, Commands, Agents).

---

## 1. 🧠 ASOSIY TAMOYILLAR (CORE PRINCIPLES)

Gemini agenti va ishlab chiquvchilar ushbu 4 ta ustuvor tamoyilga qat'iy rioya qilishi shart:

1. **Galutsinatsiyasiz ishlash (Zero-Hallucination Policy)**:
   - Hech qachon mavjud bo'lmagan kutubxona, funksiya, fayl yo'li yoki ma'lumotlar bazasi jadvallarini to'qib chiqarmang.
   - Har qanday kod yozishdan oldin loyihaning haqiqiy tuzilmasi, bog'liqliklari (`package.json`, `pom.xml`, `requirements.txt` yoki `.csproj`) va mavjud servislar tekshiriladi.
   - Shubhali holatlarda taxmin qilmang — tekshiring yoki savol bering.

2. **Ma'lumotlar Xavfsizligi (Zero-Trust Security & OWASP Top 10)**:
   - Hech qanday maxfiy kalit (API token, parol, DB credential) kod ichida qattiq yozilmaydi (hardcode taqiqlangan). Faqat `.env` / Environment Variables.
   - Barcha kiruvchi ma'lumotlar sanitizatsiya va qat'iy validatsiyadan o'tishi shart (Zod, FluentValidation, class-validator yoki DTO validatorlar).
   - SQL Injection'ga qarshi faqat parametrlashtirilgan so'rovlar / ORM ishlatiladi. Xom SQL (raw query) qat'iy taqiqlanadi (faqat maxsus profillangan va indekslangan hollar bundan mustasno).
   - Har bir endpoint va biznes mantiqda RBAC (Role-Based Access Control) va ruxsatlar tekshiriladi. Xodim reytingini faqat tegishli vakolatli rollar (Admin, Rahbar, HR) o'zgartira oladi.
   - Har bir reyting o'zgarishi uchun audit log yuritiladi (kim, qachon, qaysi sabab bilan o'zgartirdi).

3. **Yuqori Yuklama va Optimal Ishlash (High-Load & Performance)**:
   - N+1 so'rovlar muammosiga mutlaqo yo'l qo'yilmaydi (Eager loading, `JOIN`, `.Include()`, batch loading majburiy).
   - Reytinglar, liderlar jadvali (Leaderboard), xodim profillari va ko'p o'qiladigan ma'lumotlar Redis keshida saqlanadi (Cache-Aside / Stale-While-Revalidate pattern).
   - Reyting hisoblash algoritmi va ommaviy ma'lumotlar importi asinxron navbatlar (RabbitMQ, BullMQ, Kafka yoki Hangfire) orqali fonda (background worker) bajariladi. API request hech qachon og'ir hisob-kitoblar bilan bloklanmaydi.
   - Barcha ro'yxat qaytaruvchi endpointlar sahifalanishi (Pagination - limit, offset yoki cursor-based) shart. Cheklovlarsiz `SELECT *` qat'iy taqiqlanadi.
   - Indekslar: `employee_id`, `department_id`, `score`, `created_at` kabi tez-tez filtrlanuvchi ustunlarga kompozit indekslar qo'yiladi.

4. **Barqaror va Bir Xil Kod Standarti (Consistent Output & Architecture)**:
   - Xatoliklarni boshqarish: Tasodifiy `throw` tashlash taqiqlanadi. `Result<T>` yoki standartlashtirilgan javob formati (`{ success: boolean, data: T, error: ErrorResponse }`) ishlatiladi.
   - Aniq tiplashtirish (Exact Types): `any` yoki umumiy `object` ishlatish taqiqlanadi.
   - Arxitektura: Qatlamli arxitektura (Clean Architecture / Hexagonal) — Domain, Application, Infrastructure, Presentation.

---

## 2. 📁 LOYIHA TUZILMASI VA KONFIGURATSIYA (.gemini/)

Gemini va Antigravity muhitida avtomatlashtirish qoidalari `.gemini/` papkasida jamlangan:

```text
.gemini/
├── settings.json                   # Ruxsatlar, xavfsizlik va cheklovlar
├── rules/                          # Har bir sessiya uchun qat'iy ko'rsatmalar
│   ├── 01-anti-hallucination.md     # Galutsinatsiyasiz ishlash qoidalari
│   ├── 02-security.md               # Xavfsizlik va ma'lumotlar himoyasi
│   ├── 03-high-load-performance.md  # Kesh, indekslar, asinxron hisoblash
│   ├── 04-code-standards.md         # Result<T>, tiplashtirish, error handling
│   └── 05-architecture.md           # Qatlamlar va bog'liqlik qoidalari
├── skills/                         # Qayta ishlatiluvchi bilimlar (Skills)
│   ├── anti-hallucination-checker/  # Kodni tasdiqlash protokoli
│   ├── high-load-optimization/      # So'rovlarni va keshni optimallash
│   ├── security-audit/              # OWASP tekshiruv nazorat ro'yxati
│   └── rating-calculator/           # Yuqori tezlikda reyting hisoblash namunasi
├── commands/                       # Bitta buyruq bilan ishga tushuvchi pipeline
│   ├── add-endpoint.md              # Yangi to'liq endpoint yaratish
│   ├── audit-security.md            # Xavfsizlik tahlilini yurgizish
│   ├── optimize-query.md            # SQL so'rov va indeks tahlili
│   └── recalculate-rating.md        # Reyting hisoblash navbatini boshqarish
├── agents/                         # Maxsus ixtisoslashgan AI rollar
│   ├── architect.md                 # Tizim va ma'lumotlar bazasi arxitektori
│   ├── security-officer.md          # Xavfsizlik va ruxsatlar bo'yicha ekspert
│   ├── performance-engineer.md      # Kesh, so'rovlar va yuklama bo'yicha muhandis
│   └── code-reviewer.md             # Kod sifati va qoidalarga rioya nazorati
└── hooks/                          # Event-driven avtomatlashtirish
    ├── pre-commit.json              # Saqlash va commit oldidan tekshiruvlar
    ├── run-tests.sh                 # Avtomatik test skripti
    └── run-lint.sh                  # Avtomatik lint va formatlash
```

---

## 3. ⚡ TEZKOR BUYRUQLAR (COMMANDS)

- `/add-endpoint <METHOD> <PATH>`: Yangi endpoint uchun Controller, DTO, Validator, Service, Repository va Test fayllarini biryo'la yaratish.
- `/audit-security`: Kod bazasidagi xavfsizlik zaifliklarini (SQLi, IDOR, ruxsatlar, sanitizatsiya) tekshirish.
- `/optimize-query`: Tanlangan so'rovning N+1 xavfi, indeks mavjudligi va kesh ehtiyojini tahlil qilish.
- `/recalculate-rating`: Ommaviy reyting hisoblash tizimini xavfsiz va bloklanishlarsiz loyihalash/tekshirish.

---

## 4. 🚫 TAQIQLANGAN AMALLAR (STRICTLY FORBIDDEN)

1. `.env`, `.pem`, `.key`, yoki parollarni o'z ichiga olgan fayllarni o'qish, yaratish yoki gitga chiqarish.
2. Sahifalashsiz (pagination) `find()`, `SELECT *`, yoki butun jadvalni xotiraga yuklash.
3. Reyting o'zgartirish operatsiyalarini tranzaksiyasiz (transaction) va audit logsiz bajarish.
4. Foydalanuvchi ma'lumotlarini (PINFL, passport, parol xeshlari) ochiq holda loglarga chiqarish (PII masking majburiy).
5. Frontenddan kelgan ma'lumotga ishonib, serverda huquqlarni qayta tekshirmasdan operatsiyani bajarish.

---

## 5. 🔄 HAR BIR KOD YOZISH BOSQICHI (DEVELOPMENT WORKFLOW)

1. **Context Check**: Loyiha konfiguratsiyasi va mavjud kodni o'rganing.
2. **Security & Load Plan**: Yangi kiritilayotgan funksiya qanday yuklama beradi? Kesh kerakmi? Ruxsatlar qanday?
3. **Write Implementation**: Strict types, DTO validation, Result<T> pattern orqali yozish.
4. **Self-Verification**: Anti-hallucination checklist bo'yicha kodni ko'rib chiqish.
