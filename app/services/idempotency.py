import time
import asyncio
from typing import Dict, Any, Optional, Tuple
from fastapi import HTTPException, status

# In-memory xotira: {key: {"status": "PROCESSING" | "COMPLETED", "result": Any, "expire_at": float, "user_id": int}}
_IDEMPOTENCY_STORE: Dict[str, Dict[str, Any]] = {}
_LOCK = asyncio.Lock()

async def check_idempotency(
    key: Optional[str],
    user_id: int,
    action: str = "TRANSACTION",
    ttl_seconds: int = 120
) -> Tuple[bool, Optional[Any]]:
    """
    Idempotentlik kalitini tekshirish.
    
    Qaytadi:
        (True, None) -> Yangi so'rov, davom ettirish mumkin.
        (False, cached_result) -> Ushbu so'rov allaqachon bajarilgan, keshdagi natijani qaytarish kerak.
    
    Agar ayni paytda xuddi shu kalit bilan boshqa so'rov ishlayotgan bo'lsa (in-flight):
        HTTP 409 Conflict tashlanadi.
    """
    if not key or not key.strip():
        # Kalit berilmagan bo'lsa tekshiruvsiz o'tkaziladi
        return True, None

    normalized_key = f"{user_id}:{action}:{key.strip()}"
    now = time.time()

    async with _LOCK:
        # Eski (muddati o'tgan) kalitlarni tozalash
        expired_keys = [k for k, v in _IDEMPOTENCY_STORE.items() if v["expire_at"] < now]
        for k in expired_keys:
            del _IDEMPOTENCY_STORE[k]

        entry = _IDEMPOTENCY_STORE.get(normalized_key)
        if entry:
            if entry["status"] == "PROCESSING":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ushbu so'rov ayni paytda serverda qayta ishlanmoqda. Qayta bosmang!"
                )
            if entry["status"] == "COMPLETED":
                return False, entry["result"]

        # Yangi kalitni band qilish (PROCESSING)
        _IDEMPOTENCY_STORE[normalized_key] = {
            "status": "PROCESSING",
            "result": None,
            "expire_at": now + ttl_seconds,
            "user_id": user_id
        }
        return True, None

async def record_idempotency_result(
    key: Optional[str],
    user_id: int,
    result: Any,
    action: str = "TRANSACTION",
    ttl_seconds: int = 120
) -> None:
    """Bajarilgan so'rov natijasini keshga yozish"""
    if not key or not key.strip():
        return

    normalized_key = f"{user_id}:{action}:{key.strip()}"
    async with _LOCK:
        if normalized_key in _IDEMPOTENCY_STORE:
            _IDEMPOTENCY_STORE[normalized_key]["status"] = "COMPLETED"
            _IDEMPOTENCY_STORE[normalized_key]["result"] = result
            _IDEMPOTENCY_STORE[normalized_key]["expire_at"] = time.time() + ttl_seconds
        else:
            _IDEMPOTENCY_STORE[normalized_key] = {
                "status": "COMPLETED",
                "result": result,
                "expire_at": time.time() + ttl_seconds,
                "user_id": user_id
            }

async def clear_idempotency_key(key: Optional[str], user_id: int, action: str = "TRANSACTION") -> None:
    """Xatolik yuz berganda blokirovkani yechish"""
    if not key or not key.strip():
        return
    normalized_key = f"{user_id}:{action}:{key.strip()}"
    async with _LOCK:
        _IDEMPOTENCY_STORE.pop(normalized_key, None)
