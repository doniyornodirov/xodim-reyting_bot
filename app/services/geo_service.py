"""
app.services.geo_service — Geolokatsiya va Geofence Xizmati
Haversine masofa formulasi, smena vaqt intervallari va qurilma tekshiruvlari.
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Tuple

UZB_TZ = timezone(timedelta(hours=5))

def calculate_haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Yer sharining egriligini hisobga olgan holda ikki koordinata orasidagi masofani metrlarda hisoblash (Haversine formulasi).
    R = 6,371,000 metr.
    """
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2) + \
        math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)

def get_current_tashkent_hm() -> str:
    """O'zbekiston (Toshkent, UTC+5) bo'yicha joriy HH:MM vaqt"""
    return datetime.now(UZB_TZ).strftime("%H:%M")

def is_time_within_interval(current_hm: str, start_hm: str, end_hm: str) -> bool:
    """
    Berilgan joriy vaqt (HH:MM) xodimning ish boshlanish va tugash soatlari oralig'ida ekanligini tekshiradi.
    Kunduzgi smena (masalan: 09:00 - 19:00) va tungi smena (masalan: 20:00 - 06:00) ni to'liq qo'llab-quvvatlaydi.
    """
    if not start_hm or not end_hm:
        return True
    s = start_hm.strip()[:5]
    e = end_hm.strip()[:5]
    c = current_hm.strip()[:5]

    if s <= e:
        return s <= c <= e
    else: # Tungi smena: 20:00 - 06:00
        return c >= s or c <= e

def is_desktop_user_agent(ua_str: str) -> bool:
    """Windows, Mac, Linux kompyuterlarini aniqlash (faqat mobil qurilmalar ruxsat etiladi)"""
    if not ua_str:
        return False
    ua = ua_str.lower()
    is_mobile = any(m in ua for m in ["android", "iphone", "ipad", "ipod", "mobile", "blackberry", "iemobile", "opera mini"])
    if is_mobile:
        return False
    return any(d in ua for d in ["windows", "macintosh", "mac os x", "x11", "linux", "cros"])
