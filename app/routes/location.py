import math
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite

from app.config import DB_PATH
from app.dependencies import get_current_user, require_role
from app.models import LocationPingRequest, SetEmployeeWorkplaceRequest

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
    """Xodimning o'ziga biriktirilgan ish joyi va belgilangan ish soatlarini olish"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT id, full_name, workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                   work_start_time, work_end_time
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
            "current_time": current_hm
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
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

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
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

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

@router.get("/employees")
async def get_all_employees_location(admin: dict = Depends(require_role(["ADMIN"]))):
    """
    Barcha xodimlarning alohida biriktirilgan ish joylari, ish vaqti soatlari va ularning jonli holati.
    Faqat Rahbar ko'ra oladi (o'z firmasi bo'yicha).
    """
    comp_id = admin.get("company_id") or 1
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("""
            SELECT id, telegram_id, full_name, role, is_active,
                   workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                   work_start_time, work_end_time, shift_status,
                   last_latitude, last_longitude, last_distance_meters, last_location_updated_at
            FROM users
            WHERE is_active = 1 AND role NOT IN ('ADMIN', 'DEVELOPER') AND company_id = ?
            ORDER BY 
                CASE WHEN workplace_latitude IS NULL THEN 1 ELSE 0 END,
                CASE WHEN last_distance_meters IS NULL THEN 1 ELSE 0 END,
                last_distance_meters ASC,
                full_name ASC
        """, (comp_id,))
        rows = await cur.fetchall()

        current_hm = get_current_tashkent_hm()
        employees = []
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
                "is_inside": is_inside
            })

        return {
            "success": True,
            "current_server_time": current_hm,
            "employees": employees
        }
