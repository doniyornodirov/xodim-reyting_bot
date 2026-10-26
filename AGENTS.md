# AGENTS.md — Ko'p Agentli Muhitlar Uchun Qo'llanma (Gemini & Antigravity & Multi-Agent)

Ushbu loyiha barcha zamonaviy AI agentlar (Google Gemini CLI, Google Antigravity, Cursor AI, OpenAI Codex) uchun unifikatsiyalangan standart qoidalar asosida ishlaydi.

## 📌 Asosiy Ko'rsatmalar
Barcha agentlar loyihadagi quyidagi asosiy fayllarga qat'iy tayanishi lozim:
1. **[GEMINI.md](file:///c:/Users/Doniyor/Xodim-reyting/GEMINI.md)** — Loyihaning yagona xotirasi (Persistent Memory).
2. **[.gemini/settings.json](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/settings.json)** — Ruxsatlar va xavfsizlik cheklovlari.
3. **[.gemini/rules/](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/)** — Qat'iy qoidalar:
   - [01-anti-hallucination.md](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/01-anti-hallucination.md) (Galutsinatsiyasiz ishlash)
   - [02-security.md](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/02-security.md) (OWASP, RBAC, IDOR, Audit)
   - [03-high-load-performance.md](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/03-high-load-performance.md) (Redis ZSET, N+1, Queue)
   - [04-code-standards.md](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/04-code-standards.md) (Result<T>, Exact types)
   - [05-architecture.md](file:///c:/Users/Doniyor/Xodim-reyting/.gemini/rules/05-architecture.md) (Clean Architecture)

## ⚡ Asosiy Buyruqlar
- `/add-endpoint`: To'liq yangi endpoint pipeline
- `/audit-security`: Xavfsizlik auditi
- `/optimize-query`: So'rov va indeks optimallashtirish
- `/recalculate-rating`: Ommaviy reyting hisoblash
