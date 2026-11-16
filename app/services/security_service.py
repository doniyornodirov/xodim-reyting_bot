"""
app.services.security_service — Kirish Xavfsizligi va Brute-Force Himoyasi
Parollarni terib ko'rishga qarshi avtomatik blokirovka (Rate Limiting & Lockout).
"""

import time
import asyncio
from typing import Dict, Any, Optional, Tuple
from fastapi import HTTPException, status

# In-memory urinishlar hisobi: {telegram_id: {"attempts": int, "lock_until": float}}
_FAILED_LOGINS: Dict[int, Dict[str, Any]] = {}
_SEC_LOCK = asyncio.Lock()

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900 # 15 daqiqa

async def check_login_lockout(telegram_id: int) -> None:
    """Agar foydalanuvchi bloklangan bo'lsa, HTTP 429 xatolik qaytarish"""
    now = time.time()
    async with _SEC_LOCK:
        record = _FAILED_LOGINS.get(telegram_id)
        if record:
            lock_until = record.get("lock_until", 0)
            if now < lock_until:
                remaining_mins = max(1, int((lock_until - now) / 60) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Parol {MAX_FAILED_ATTEMPTS} marta ketma-ket noto'g'ri kiritilganligi sababli, xavfsizlik yuzasidan hisob {remaining_mins} daqiqaga vaqtinchalik muzlatildi!"
                )
            elif lock_until > 0 and now >= lock_until:
                # Blok muddati tugagan bo'lsa tozalash
                _FAILED_LOGINS.pop(telegram_id, None)

async def record_failed_login(telegram_id: int) -> int:
    """
    Noto'g'ri parol kiritilganda hisoblagichni oshirish.
    Agar 5 taga yetsa, 15 daqiqaga bloklash.
    Qaytadi: qolgan urinishlar soni.
    """
    now = time.time()
    async with _SEC_LOCK:
        if telegram_id not in _FAILED_LOGINS:
            _FAILED_LOGINS[telegram_id] = {"attempts": 1, "lock_until": 0}
            return MAX_FAILED_ATTEMPTS - 1

        record = _FAILED_LOGINS[telegram_id]
        record["attempts"] += 1
        current_attempts = record["attempts"]

        if current_attempts >= MAX_FAILED_ATTEMPTS:
            record["lock_until"] = now + LOCKOUT_DURATION_SECONDS
            remaining_mins = int(LOCKOUT_DURATION_SECONDS / 60)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Parol {MAX_FAILED_ATTEMPTS} marta ketma-ket noto'g'ri kiritildi! Hisob {remaining_mins} daqiqaga muzlatildi."
            )

        return MAX_FAILED_ATTEMPTS - current_attempts

async def reset_failed_login(telegram_id: int) -> None:
    """Muvaffaqiyatli login qilinganda hisoblagichni nolga tushirish"""
    async with _SEC_LOCK:
        _FAILED_LOGINS.pop(telegram_id, None)
