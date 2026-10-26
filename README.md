# 🌟 Xodim-Reyting Tizimi: Mukammal Gemini & Dasturlash Standartlari

Ushbu loyiha **Gemini va Google Antigravity** muhiti uchun maxsus moslashtirilgan 7 ta ustun asosida yaratilgan bo'lib, sun'iy intellekt (Gemini, Antigravity, Cursor) yordamida **galutsinatsiyalarsiz**, **maksimal xavfsiz** va **yuqori yuklamada (High-Load)** ham chaqqon ishlaydigan xodimlar reytingi va KPI tizimini barpo etish uchun xizmat qiladi.

---

## 🏛️ 7 Ustun Qanday Amalga Oshirildi?

Tizimdagi har bir muammo va uning yechimi loyihada to'liq aks ettirilgan:

| # | Konsept | Joylashuvi | Hal Qilingan Muammo |
|---|---|---|---|
| 1 | **Memory** | [`GEMINI.md`](file:///c:/Users/Doniyor/Xodim-reyting/GEMINI.md) | Har sessiyada stack va qoidalarni qaytadan tushuntirish kerak emas. Bir marta yozilgan, har doim yuklanadi. |
| 2 | **Settings** | [`.gemini/settings.json`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/settings.json) | Fayllar va tool ruxsatlari — ruxsatsiz fayllar (`.env`, kalitlar) o'zgartirilmaydi, jamoada bir xil xulq-atvor. |
| 3 | **Rules** | [`.gemini/rules/`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/) | Har bir sessiya uchun qat'iy yo'riqnomalar: Galutsinatsiyani taqiqlash, xavfsizlik, yuqori yuklama, kod standarti, arxitektura. |
| 4 | **Hooks** | [`.gemini/hooks/`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/hooks/) | Event-driven avtomatlashtirish: saqlashda lint, commit oldidan test va tiplarni tekshirish avtomatlashgan. |
| 5 | **Skills** | [`.gemini/skills/`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/skills/) | Qayta ishlatiluvchi jamoaviy bilimlar: so'rovlarni optimallash, xavfsizlik auditi, reyting hisoblash formulasi. |
| 6 | **Commands** | [`.gemini/commands/`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/commands/) | Bitta trigger orqali to'liq pipeline (`/add-endpoint`, `/audit-security`, `/optimize-query`, `/recalculate-rating`). |
| 7 | **Agents** | [`.gemini/agents/`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/agents/) | Ixtisoslashgan AI rollari: Architect, Security Officer, Performance Engineer, Code Reviewer. |

---

## 🛡️ 1. Galutsinatsiyasiz Ishlash (Zero-Hallucination Policy)

- **Pre-Flight Checks**: Har qanday import yoki funksiya chaqiruvidan oldin uning `package.json` va fayl tizimida haqiqatan ham mavjudligi tekshiriladi.
- **Sxemani Taxmin Qilmaslik**: Ma'lumotlar bazasi ustunlari nomi taxmin qilinmaydi, faqat mavjud modellar yoki migratsiyalar asosida kod yoziladi.
- **Qat'iy Tiplashtirish**: `any` yoki tekshirilmagan tiplar taqiqlangan, har bir xatolik `Result.fail()` orqali aniq ko'rsatiladi.
- 🔗 Batafsil: [`01-anti-hallucination.md`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/01-anti-hallucination.md)

---

## 🔒 2. Ma'lumotlar Xavfsizligi (Zero-Trust Security & OWASP Top 10)

- **RBAC & IDOR Himoyasi**: Bo'lim boshlig'i faqat o'z bo'limi xodimini baholay oladi. Hech qanday ruxsatsiz reyting tahrirlanishiga yo'l qo'yilmaydi.
- **Xom SQL Taqiqlangan**: Faqat parametrlashtirilgan so'rovlar yoki xavfsiz ORM ishlatiladi.
- **O'zgartirib Bo'lmas Audit Log**: Har bir reyting o'zgarishi `audit_logs` (Append-Only) jadvalida kim, qachon, eski qiymat, yangi qiymat va sabab bilan qayd etiladi.
- **Maxfiy Kalitlar Himoyasi**: Hech bir maxfiy kalit gitga kirmaydi, loglarda shaxsiy ma'lumotlar (PINFL, passport) niqoblanadi (PII Masking).
- 🔗 Batafsil: [`02-security.md`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/02-security.md)

---

## 🚀 3. Yuqori Yuklamada Optimal Ishlash (High-Load Architecture)

- **Redis ZSET Leaderboard**: Liderlar jadvali bazadan emas, balki Redis Sorted Sets (`ZADD`, `ZREVRANGE`, `ZREVRANK`) orqali $O(\log N)$ vaqtda xotiradan beriladi (1-2ms javob vaqti).
- **N+1 Muammosiga Barham**: Eager loading (`.Include()`, `JOIN`) yoki batch loader majburiy.
- **Asinxron Fon Navbatlari**: Ommaviy reyting hisoblash (minglab xodimlar) API javobini bloklamasdan, BullMQ / RabbitMQ orqali 500 tadan to'plamlarga bo'lib (Chunking) fonda bajariladi.
- **Kompozit Indekslar**: `(department_id, period, total_score DESC)` kabi ko'p so'raladigan ustunlar doimo indekslangan.
- **Majburiy Sahifalash**: Har bir ro'yxat `limit` (max 100) va cursor orqali sahifalanadi.
- 🔗 Batafsil: [`03-high-load-performance.md`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/03-high-load-performance.md)

---

## 💻 4. Barqaror Kod Standarti (Result<T> Pattern)

Biznes mantiqda tasodifiy `throw` tashlash o'rniga:
- Barcha funksiyalar `Result.ok(data)` yoki `Result.fail(error)` formatida qiymat qaytaradi.
- Strukturaviy JSON loglash (Correlation ID, Duration, User ID).
- 🔗 Batafsil: [`04-code-standards.md`](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/04-code-standards.md)

---

## ⚙️ Tezkor Slash Buyruqlar (Commands)

| Buyruq | Tavsif |
|---|---|
| `/add-endpoint <METHOD> <PATH>` | Yangi endpoint uchun barcha 6 ta qatlam faylini (DTO, UseCase, Repo, Controller, Route, Test) yaratadi |
| `/audit-security` | Kod bazasini OWASP zaifliklari va IDOR bo'yicha avtomatik tekshiradi |
| `/optimize-query <QUERY>` | SQL so'rovini N+1 va indekslar bo'yicha tahlil qilib, kesh qatlamini qo'shadi |
| `/recalculate-rating` | Ommaviy reyting hisoblash fon navbatini ishga tushiradi/sinovdan o'tkazadi |

---

## 🤝 Ko'p Platformali Moslik (Cross-Tool Interoperability)
Ushbu loyiha barcha asosiy AI yordamchilari bilan to'liq mos keladi:
- **Google Gemini CLI & Antigravity IDE**: `GEMINI.md` va `.gemini/` orqali to'liq avtomatlashtirilgan.
- **Cursor AI & Boshqa Agentlar**: `AGENTS.md` va `.gemini/rules/` qoidalariga rioya qiladi.
