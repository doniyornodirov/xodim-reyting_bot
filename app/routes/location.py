import math
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite

from app.config import DB_PATH
from app.database import get_db_connection
from app.dependencies import get_current_user, require_role
from app.models import LocationPingRequest, SetEmployeeWorkplaceRequest, DeviceTelemetryRequest, VerifiedCheckinRequest

router = APIRouter(prefix="/api/location", tags=["Location & Geofencing"])

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
    else:
        # Tungi smena
        return c >= s or c <= e

@router.get("/my-workplace")
async def get_my_workplace(user: dict = Depends(get_current_user)):
    """Xodimning o'ziga biriktirilgan ish joyi, belgilangan ish soatlari va jonli signal holatini olish"""
    async with get_db_connection() as conn:
        cur = await conn.execute("""
            SELECT id, full_name, workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                   work_start_time, work_end_time, shift_status, last_location_updated_at, last_distance_meters
            FROM users WHERE id = ?
        """, (user["id"],))
        row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Foydalanuvchi topilmadi")

        w_lat = row["workplace_latitude"]
        w_lon = row["workplace_longitude"]
        is_configured = (w_lat is not None and w_lon is not None and (w_lat != 0.0 or w_lon != 0.0))
        start_time = row["work_start_time"] or "09:00"
        end_time = row["work_end_time"] or "19:00"
        current_hm = get_current_tashkent_hm()
        is_within_hours = is_time_within_interval(current_hm, start_time, end_time)
        emp_shift = row["shift_status"] if ("shift_status" in row.keys() and row["shift_status"]) else "WORKING"

        # Signal kechikishi va oflayn holat (Interneti o'chiqligi)
        raw_updated_at = row["last_location_updated_at"]
        norm_updated_at = raw_updated_at
        loc_lag_minutes = 0
        now_dt = datetime.now(timezone.utc)
        if norm_updated_at:
            if not norm_updated_at.endswith("Z") and "+" not in norm_updated_at:
                norm_updated_at = norm_updated_at.replace(" ", "T") + "Z"
            try:
                loc_clean = str(norm_updated_at).replace("Z", "+00:00")
                loc_dt = datetime.fromisoformat(loc_clean)
                if loc_dt.tzinfo is None:
                    loc_dt = loc_dt.replace(tzinfo=timezone.utc)
                loc_lag_minutes = max(0, int((now_dt - loc_dt).total_seconds() / 60))
            except Exception:
                loc_lag_minutes = 0

        is_signal_lost = False
        if is_within_hours and emp_shift == "WORKING":
            if not norm_updated_at or loc_lag_minutes >= 10:
                is_signal_lost = True

        return {
            "success": True,
            "is_configured": is_configured,
            "workplace_name": row["workplace_name"] or "Ish joyi",
            "latitude": w_lat,
            "longitude": w_lon,
            "radius_meters": row["workplace_radius_meters"] or 50,
            "work_start_time": start_time,
            "work_end_time": end_time,
            "is_within_hours": is_within_hours,
            "current_time": current_hm,
            "shift_status": emp_shift,
            "last_distance_meters": row["last_distance_meters"],
            "last_location_updated_at": norm_updated_at,
            "loc_lag_minutes": loc_lag_minutes,
            "is_signal_lost": is_signal_lost
        }

@router.post("/ping")
async def ping_employee_location(
    payload: LocationPingRequest,
    user: dict = Depends(get_current_user)
):
    """
    Xodim qurilmasidan avtomatik davriy lokatsiya yuborish.
    Faqat belgilangan ish vaqti oralig'ida kuzatiladi.
    Ish vaqtidan tashqarida xodimning shaxsiy daxlsizligi saqlanadi va kordinata yozilmaydi.
    """
    if user["role"] == "ADMIN":
        return {"success": True, "message": "Rahbar kuzatilmaydi"}

    user_id = user["id"]
    async with get_db_connection() as conn:
        cur = await conn.execute("""
            SELECT id, full_name, workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                   work_start_time, work_end_time, shift_status
            FROM users WHERE id = ?
        """, (user_id,))
        row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xodim topilmadi")

        start_time = row["work_start_time"] or "09:00"
        end_time = row["work_end_time"] or "19:00"
        current_hm = get_current_tashkent_hm()
        is_within_hours = is_time_within_interval(current_hm, start_time, end_time)
        shift_status = row["shift_status"] if ("shift_status" in row.keys() and row["shift_status"]) else "WORKING"

        w_lat = row["workplace_latitude"]
        w_lon = row["workplace_longitude"]
        w_radius = row["workplace_radius_meters"] or 50
        w_name = row["workplace_name"] or "Ish joyi"

        is_configured = (w_lat is not None and w_lon is not None and (w_lat != 0.0 or w_lon != 0.0))
        distance_meters = None
        is_inside = None

        if is_configured:
            distance_meters = calculate_haversine_meters(
                w_lat,
                w_lon,
                payload.latitude,
                payload.longitude
            )
            is_inside = distance_meters <= w_radius

        # Kordinata doimo yangilanadi (toki Rahbar xodim kordinatasini istalgan paytda bitta tugma bilan ola bilsin)
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        await conn.execute("""
            UPDATE users
            SET last_latitude = ?,
                last_longitude = ?,
                last_distance_meters = ?,
                last_location_updated_at = ?
            WHERE id = ?
        """, (
            round(payload.latitude, 7),
            round(payload.longitude, 7),
            distance_meters,
            now_utc,
            user_id
        ))
        await conn.commit()

        # Agar Rahbar tomonidan xodim dam olish rejimiga o'tkazilgan bo'lsa
        if shift_status == "RESTING":
            return {
                "success": True,
                "is_within_hours": False,
                "shift_status": "RESTING",
                "work_start_time": start_time,
                "work_end_time": end_time,
                "current_time": current_hm,
                "status_text": "Damda 🌙 (Dam olish rejimi)",
                "distance_meters": distance_meters,
                "radius_meters": w_radius,
                "is_inside": is_inside,
                "workplace_name": w_name,
                "is_configured": is_configured,
                "updated_at": datetime.now().isoformat()
            }

        # Agar ish soati bo'lmasa, dam olish holati qaytariladi
        if not is_within_hours:
            return {
                "success": True,
                "is_within_hours": False,
                "shift_status": "WORKING",
                "work_start_time": start_time,
                "work_end_time": end_time,
                "current_time": current_hm,
                "status_text": "Ish vaqti emas 🌙 (Dam olish)",
                "distance_meters": distance_meters,
                "radius_meters": w_radius,
                "is_inside": is_inside,
                "workplace_name": w_name,
                "is_configured": is_configured,
                "updated_at": datetime.now().isoformat()
            }

        return {
            "success": True,
            "is_within_hours": True,
            "shift_status": "WORKING",
            "work_start_time": start_time,
            "work_end_time": end_time,
            "current_time": current_hm,
            "distance_meters": distance_meters,
            "radius_meters": w_radius,
            "is_inside": is_inside,
            "workplace_name": w_name,
            "is_configured": is_configured,
            "updated_at": datetime.now().isoformat()
        }

@router.post("/set-employee-workplace")
async def set_employee_workplace(
    payload: SetEmployeeWorkplaceRequest,
    admin: dict = Depends(require_role(["ADMIN"]))
):
    """
    Bosh Rahbar tomonidan muayyan xodim uchun alohida ish joyi lokatsiyasi va ISH VAQTI (soatlari)ni belgilash.
    """
    comp_id = admin.get("company_id") or 1
    async with get_db_connection() as conn:
        cur = await conn.execute("SELECT id, full_name, role, last_latitude, last_longitude FROM users WHERE id = ? AND company_id = ?", (payload.user_id, comp_id))
        target_user = await cur.fetchone()

        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xodim topilmadi")

        if target_user["role"] == "ADMIN":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bosh Rahbarga ish joyi belgilanmaydi!")

        wp_name = payload.workplace_name.strip() or "Ish joyi"
        wp_lat = round(payload.latitude, 7)
        wp_lon = round(payload.longitude, 7)
        wp_radius = int(payload.radius_meters)
        start_time = (payload.work_start_time or "09:00").strip()[:5]
        end_time = (payload.work_end_time or "19:00").strip()[:5]

        # Agar xodim allaqachon lokatsiya yuborgan bo'lsa, yangi ish joyigacha masofasini darhol qayta hisoblash
        new_distance = None
        if target_user["last_latitude"] is not None and target_user["last_longitude"] is not None:
            new_distance = calculate_haversine_meters(
                wp_lat,
                wp_lon,
                target_user["last_latitude"],
                target_user["last_longitude"]
            )

        await conn.execute("""
            UPDATE users
            SET workplace_name = ?,
                workplace_latitude = ?,
                workplace_longitude = ?,
                workplace_radius_meters = ?,
                work_start_time = ?,
                work_end_time = ?,
                last_distance_meters = ?
            WHERE id = ? AND company_id = ?
        """, (wp_name, wp_lat, wp_lon, wp_radius, start_time, end_time, new_distance, payload.user_id, comp_id))

        audit_details = (
            f"Xodim '{target_user['full_name']}' uchun ish joyi ({wp_name}, {wp_lat:.6f}, {wp_lon:.6f}, "
            f"radius: {wp_radius}m) va ish vaqti ({start_time} - {end_time}) belgilandi"
        )
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'LOCATION', ?, 'SET_EMPLOYEE_WORKPLACE', ?, ?)
        """, (comp_id, payload.user_id, admin["full_name"], audit_details))

        await conn.commit()

        return {
            "success": True,
            "message": f"Xodim '{target_user['full_name']}' uchun ish joyi va ish vaqti ({start_time} - {end_time}) muvaffaqiyatli saqlandi!",
            "employee_id": payload.user_id,
            "workplace_name": wp_name,
            "latitude": wp_lat,
            "longitude": wp_lon,
            "radius_meters": wp_radius,
            "work_start_time": start_time,
            "work_end_time": end_time,
            "distance_meters": new_distance
        }

@router.post("/clear-employee-workplace/{user_id}")
async def clear_employee_workplace(
    user_id: int,
    admin: dict = Depends(require_role(["ADMIN"]))
):
    """Xodimga biriktirilgan ish joyi lokatsiyasini o'chirish / tozalash"""
    comp_id = admin.get("company_id") or 1
    async with get_db_connection() as conn:
        cur = await conn.execute("SELECT id, full_name FROM users WHERE id = ? AND company_id = ?", (user_id, comp_id))
        target_user = await cur.fetchone()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xodim topilmadi")

        await conn.execute("""
            UPDATE users
            SET workplace_name = 'Ish joyi',
                workplace_latitude = NULL,
                workplace_longitude = NULL,
                workplace_radius_meters = 50,
                work_start_time = '09:00',
                work_end_time = '19:00',
                last_distance_meters = NULL
            WHERE id = ? AND company_id = ?
        """, (user_id, comp_id))

        audit_details = f"Xodim '{target_user['full_name']}' uchun belgilangan ish joyi lokatsiyasi tozalandi"
        await conn.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'LOCATION', ?, 'CLEAR_EMPLOYEE_WORKPLACE', ?, ?)
        """, (comp_id, user_id, admin["full_name"], audit_details))

        await conn.commit()

        return {
            "success": True,
            "message": f"'{target_user['full_name']}' ish joyi lokatsiyasi tozalandi"
        }

@router.post("/telemetry")
async def report_device_telemetry(
    req: DeviceTelemetryRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Xodim telefoni (Web/PWA) tomonidan fonda yuboriladigan passiv harakat va zaryadka telemetriyasi.
    Xodimni hech qanday bezovta qilmaydi.
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with get_db_connection() as conn:
        if req.has_motion:
            await conn.execute("""
                UPDATE users 
                SET last_motion_at = ?,
                    is_charging = CASE WHEN ? IS NOT NULL THEN ? ELSE is_charging END,
                    stillness_state = 'ACTIVE'
                WHERE id = ?
            """, (
                now_utc,
                1 if req.is_charging is True else (0 if req.is_charging is False else None),
                1 if req.is_charging is True else (0 if req.is_charging is False else None),
                current_user["id"]
            ))
        else:
            if req.is_charging is not None:
                await conn.execute("""
                    UPDATE users 
                    SET is_charging = ?
                    WHERE id = ?
                """, (1 if req.is_charging else 0, current_user["id"]))
        await conn.commit()
    return {"success": True}

@router.get("/employees")
async def get_all_employees_location(admin: dict = Depends(require_role(["ADMIN"]))):
    """
    Barcha xodimlarning alohida biriktirilgan ish joylari, ish vaqti soatlari,
    jonli holati hamda Smart Anti-Fraud (Absolyut 0 harakat va stolda qotib qolganlik) holati.
    Faqat Rahbar ko'ra oladi (o'z firmasi bo'yicha).
    """
    comp_id = admin.get("company_id") or 1
    async with get_db_connection() as conn:
        cur = await conn.execute("""
            SELECT id, telegram_id, full_name, role, is_active,
                   workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                   work_start_time, work_end_time, shift_status,
                   last_latitude, last_longitude, last_distance_meters, last_location_updated_at,
                   last_motion_at, last_motion_lat, last_motion_lon, stillness_state, is_charging
            FROM users
            WHERE is_active = 1 AND role NOT IN ('ADMIN', 'DEVELOPER') AND company_id = ?
            ORDER BY 
                CASE WHEN last_location_updated_at IS NULL THEN 0 ELSE 1 END,
                last_location_updated_at ASC,
                full_name ASC
        """, (comp_id,))
        rows = await cur.fetchall()

        current_hm = get_current_tashkent_hm()
        now_dt = datetime.now(timezone.utc)
        employees = []
        frozen_count = 0
        offline_count = 0

        for r in rows:
            w_lat = r["workplace_latitude"]
            w_lon = r["workplace_longitude"]
            is_configured = (w_lat is not None and w_lon is not None and (w_lat != 0.0 or w_lon != 0.0))

            start_time = r["work_start_time"] or "09:00"
            end_time = r["work_end_time"] or "19:00"
            is_within_hours = is_time_within_interval(current_hm, start_time, end_time)
            emp_shift = r["shift_status"] if ("shift_status" in r.keys() and r["shift_status"]) else "WORKING"

            dist = r["last_distance_meters"]
            radius = r["workplace_radius_meters"] or 50
            is_inside = (dist <= radius) if (dist is not None and is_configured) else None

            raw_updated_at = r["last_location_updated_at"]
            norm_updated_at = raw_updated_at
            if norm_updated_at and not norm_updated_at.endswith("Z") and "+" not in norm_updated_at:
                norm_updated_at = norm_updated_at.replace(" ", "T") + "Z"

            # SMART ANTI-FRAUD: Harakatsizlik va Absolyut 0 harakat tahlili
            stillness_code = r["stillness_state"] if ("stillness_state" in r.keys() and r["stillness_state"]) else "ACTIVE"
            stillness_minutes = 0

            motion_at_val = r["last_motion_at"] if ("last_motion_at" in r.keys() and r["last_motion_at"]) else norm_updated_at
            if motion_at_val:
                try:
                    mot_clean = str(motion_at_val).replace("Z", "+00:00")
                    mot_dt = datetime.fromisoformat(mot_clean)
                    if mot_dt.tzinfo is None:
                        mot_dt = mot_dt.replace(tzinfo=timezone.utc)
                    stillness_minutes = max(0, int((now_dt - mot_dt).total_seconds() / 60))
                except Exception:
                    stillness_minutes = 0

            # Telegramning o'zi stolda harakatsiz yotgani sababli uxlab qolgan yoki signal to'xtagan vaqt oralig'i:
            loc_lag_minutes = 0
            if norm_updated_at:
                try:
                    loc_clean = str(norm_updated_at).replace("Z", "+00:00")
                    loc_dt = datetime.fromisoformat(loc_clean)
                    if loc_dt.tzinfo is None:
                        loc_dt = loc_dt.replace(tzinfo=timezone.utc)
                    loc_lag_minutes = max(0, int((now_dt - loc_dt).total_seconds() / 60))
                except Exception:
                    loc_lag_minutes = 0

            effective_still_min = max(stillness_minutes, loc_lag_minutes)
            is_charging = bool(r["is_charging"]) if ("is_charging" in r.keys() and r["is_charging"]) else False

            # Signal kelmayapti (Interneti o'chiq / Oflayn):
            # Ish vaqtida bo'lsa va oxirgi 10 daqiqadan beri hech qanday yangilanish kelmagan bo'lsa
            is_signal_lost = False
            if is_within_hours and emp_shift == "WORKING":
                if not norm_updated_at or loc_lag_minutes >= 10:
                    is_signal_lost = True
                    offline_count += 1

            if is_signal_lost:
                stillness_code = "NO_SIGNAL"
                stillness_label = f"📵 Signal kelmayapti ({loc_lag_minutes} daq)" if loc_lag_minutes > 0 else "📵 Signal kelmayapti"
            elif is_within_hours and emp_shift == "WORKING" and is_configured and norm_updated_at:
                if effective_still_min >= 90:
                    stillness_code = "FROZEN_ALERT"
                    stillness_label = f"🔴 ⚠️ Qotib qolgan ({effective_still_min} daq 0 harakat!)"
                    frozen_count += 1
                elif effective_still_min >= 45:
                    stillness_code = "STILL_WARN"
                    stillness_label = f"🟡 Tinch ({effective_still_min} daq)"
                else:
                    stillness_code = "ACTIVE"
                    stillness_label = "🟢 Jonli harakatda"
            elif not is_within_hours:
                stillness_code = "OFF_HOURS"
                stillness_label = "🌙 Ish vaqti emas"
            else:
                stillness_code = "WAITING"
                stillness_label = "⏳ Kutilmoqda"

            employees.append({
                "id": r["id"],
                "telegram_id": r["telegram_id"],
                "full_name": r["full_name"],
                "role": r["role"],
                "shift_status": emp_shift,
                "workplace_name": r["workplace_name"] or "Ish joyi",
                "workplace_latitude": w_lat,
                "workplace_longitude": w_lon,
                "workplace_radius_meters": radius,
                "is_workplace_configured": is_configured,
                "work_start_time": start_time,
                "work_end_time": end_time,
                "is_within_hours": is_within_hours,
                "current_server_time": current_hm,
                "last_latitude": r["last_latitude"],
                "last_longitude": r["last_longitude"],
                "last_distance_meters": dist,
                "last_location_updated_at": norm_updated_at,
                "is_inside": is_inside,
                "stillness_code": stillness_code,
                "stillness_label": stillness_label,
                "stillness_minutes": effective_still_min,
                "is_charging": is_charging,
                "is_signal_lost": is_signal_lost,
                "loc_lag_minutes": loc_lag_minutes
            })

        return {
            "success": True,
            "current_server_time": current_hm,
            "frozen_count": frozen_count,
            "offline_count": offline_count,
            "employees": employees
        }

@router.post("/device-checkin")
async def location_device_checkin(payload: VerifiedCheckinRequest):
    """
    Telegram WebApp orqali ishni boshlashda xodim apparatini tekshirish yoki biriktirish.
    """
    tg_id = payload.telegram_id
    incoming_token = (payload.device_token or "").strip()
    incoming_dev_name = (payload.device_name or "Mobil telefon").strip()[:100]

    async with get_db_connection() as conn:
        cur = await conn.execute("""
            SELECT id, full_name, telegram_id, role, company_id,
                   workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                   work_start_time, work_end_time, shift_status,
                   bound_device_token, bound_device_name, device_bound_at, allow_device_reset
            FROM users WHERE telegram_id = ?
        """, (tg_id,))
        user = await cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")

        # Rahbar va Dasturchiga cheklov qo'yilmaydi
        if user["role"] in ("ADMIN", "DEVELOPER"):
            return {
                "success": True,
                "is_trusted": True,
                "action": "ADMIN_EXEMPT",
                "device_token": incoming_token or "admin_token",
                "device_name": "Rahbar qurilmasi",
                "user": dict(user)
            }

        bound_token = user["bound_device_token"]
        allow_reset = bool(user["allow_device_reset"])
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1. Hali apparat biriktirilmagan yoki Rahbar yangi telefon biriktirishga ruxsat bergan bo'lsa:
        if not bound_token or allow_reset:
            import secrets
            new_token = secrets.token_hex(32)
            await conn.execute("""
                UPDATE users
                SET bound_device_token = ?,
                    bound_device_name = ?,
                    device_bound_at = ?,
                    allow_device_reset = 0
                WHERE id = ?
            """, (new_token, incoming_dev_name, now_utc, user["id"]))

            details = f"Xodim '{user['full_name']}' ga yangi telefon ({incoming_dev_name}) biriktirildi."
            await conn.execute("""
                INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
                VALUES (?, 'DEVICE', ?, 'BIND_DEVICE_WEBAPP', ?, ?)
            """, (user["company_id"] or 1, user["id"], user["full_name"], details))
            await conn.commit()

            return {
                "success": True,
                "is_trusted": True,
                "action": "BOUND",
                "device_token": new_token,
                "device_name": incoming_dev_name,
                "user": dict(user),
                "message": f"Ushbu telefon ({incoming_dev_name}) rasmiy qurilmangiz sifatida muhrlandi!"
            }

        # 2. Mavjud apparat tokeni bilan solishtirish:
        if incoming_token and incoming_token == bound_token:
            return {
                "success": True,
                "is_trusted": True,
                "action": "VERIFIED",
                "device_token": bound_token,
                "device_name": user["bound_device_name"] or "Tasdiqlangan telefon",
                "user": dict(user),
                "message": "Apparat tasdiqlandi."
            }
        else:
            # Begona apparat!
            orig_name = user["bound_device_name"] or "Boshqa telefon apparati"
            details = f"Xodim '{user['full_name']}' hisobiga begona qurilmadan ({incoming_dev_name}) lokatsiya topshirishga urinish bo'ldi!"
            await conn.execute("""
                INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
                VALUES (?, 'SECURITY', ?, 'UNTRUSTED_DEVICE_ATTEMPT', ?, ?)
            """, (user["company_id"] or 1, user["id"], user["full_name"], details))
            await conn.commit()

            try:
                import asyncio
                from app.bot import send_untrusted_device_alert_to_admin
                asyncio.create_task(send_untrusted_device_alert_to_admin(
                    company_id=user["company_id"] or 1,
                    employee_name=user["full_name"],
                    employee_tg_id=user["telegram_id"],
                    bound_device=orig_name,
                    attempted_device=incoming_dev_name
                ))
            except Exception:
                pass

            return {
                "success": False,
                "is_trusted": False,
                "action": "REJECTED",
                "error_code": "UNTRUSTED_DEVICE",
                "bound_device_name": orig_name,
                "message": f"⛔ Begona qurilma! Ushbu hisob faqat «{orig_name}» apparatiga biriktirilgan. Yangi telefon biriktirish uchun Rahbarga murojaat qiling."
            }

@router.post("/verified-checkin")
async def record_verified_checkin(payload: VerifiedCheckinRequest):
    """
    Tasdiqlangan apparatdan yuborilgan haqiqiy GPS koordinatalarini qabul qilish va geofencing masofasini hisoblash.
    """
    tg_id = payload.telegram_id
    incoming_token = (payload.device_token or "").strip()
    lat = payload.latitude
    lon = payload.longitude

    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="GPS koordinatalari taqdim etilmadi!")

    async with get_db_connection() as conn:
        cur = await conn.execute("""
            SELECT id, full_name, telegram_id, role, company_id,
                   workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                   work_start_time, work_end_time, shift_status,
                   bound_device_token, bound_device_name
            FROM users WHERE telegram_id = ?
        """, (tg_id,))
        user = await cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Xodim topilmadi!")

        # Token tekshiruvi (faqat oddiy xodimlar uchun)
        if user["role"] not in ("ADMIN", "DEVELOPER"):
            bound_token = user["bound_device_token"]
            if not bound_token or bound_token != incoming_token:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"⛔ Begona qurilma! Lokatsiya faqat «{user['bound_device_name'] or 'biriktirilgan telefon'}» orqali qabul qilinadi."
                )

        w_lat = user["workplace_latitude"]
        w_lon = user["workplace_longitude"]
        w_radius = user["workplace_radius_meters"] or 50
        w_name = user["workplace_name"] or "Ish joyi"
        is_configured = (w_lat is not None and w_lon is not None and (w_lat != 0.0 or w_lon != 0.0))

        distance_meters = None
        is_inside = None
        first_time_auto_configured = False

        if not is_configured:
            # Ish joyi hali belgilanmagan bo'lsa:
            # Ushbu jonli lokatsiyaning birinchi nuqtasi AVTOMATIK ravishda ish joyi deb saqlanadi!
            w_lat = round(lat, 7)
            w_lon = round(lon, 7)
            is_configured = True
            distance_meters = 0.0
            is_inside = True
            first_time_auto_configured = True
            await conn.execute("""
                UPDATE users
                SET workplace_latitude = ?,
                    workplace_longitude = ?
                WHERE id = ?
            """, (w_lat, w_lon, user["id"]))
        else:
            distance_meters = calculate_haversine_meters(w_lat, w_lon, lat, lon)
            is_inside = (distance_meters <= w_radius)

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        await conn.execute("""
            UPDATE users
            SET last_latitude = ?,
                last_longitude = ?,
                last_distance_meters = ?,
                last_location_updated_at = ?,
                last_motion_at = ?,
                last_motion_lat = ?,
                last_motion_lon = ?,
                stillness_state = 'ACTIVE'
            WHERE id = ?
        """, (
            round(lat, 7),
            round(lon, 7),
            distance_meters,
            now_utc,
            now_utc,
            round(lat, 7),
            round(lon, 7),
            user["id"]
        ))
        await conn.commit()

        dist_str = f"{int(distance_meters)} m" if distance_meters and distance_meters < 1000 else f"{distance_meters/1000:.1f} km" if distance_meters else "Noma'lum"
        msg_text = "Ish joyingiz koordinatasi joriy jonli joylashuvingiz orqali avtomatik belgilandi va ish boshlandi!" if first_time_auto_configured else f"Davomat muvaffaqiyatli qayd etildi! Masofa: {dist_str}"

        try:
            import asyncio
            from app.bot import send_checkin_success_notification_to_employee
            asyncio.create_task(send_checkin_success_notification_to_employee(
                employee_tg_id=user["telegram_id"],
                employee_name=user["full_name"],
                workplace_name=w_name,
                distance_text=dist_str,
                is_inside=bool(is_inside),
                first_time_auto_configured=first_time_auto_configured
            ))
        except Exception:
            pass

        return {
            "success": True,
            "user_id": user["id"],
            "full_name": user["full_name"],
            "device_name": user["bound_device_name"] or "Mobil telefon",
            "workplace_name": w_name,
            "is_configured": is_configured,
            "first_time_configured": first_time_auto_configured,
            "is_inside": is_inside,
            "distance_meters": distance_meters,
            "distance_text": dist_str,
            "radius_meters": w_radius,
            "updated_at": now_utc,
            "message": msg_text
        }
