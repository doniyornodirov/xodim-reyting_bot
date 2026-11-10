import math
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite

from app.config import DB_PATH
from app.dependencies import get_current_user, require_role
from app.models import LocationPingRequest, SetEmployeeWorkplaceRequest

router = APIRouter(prefix="/api/location", tags=["Location & Geofencing"])

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

@router.get("/my-workplace")
async def get_my_workplace(user: dict = Depends(get_current_user)):
    """Xodimning o'ziga biriktirilgan ish joyi kordinatalarini olish"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT id, full_name, workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters
            FROM users WHERE id = ?
        """, (user["id"],))
        row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Foydalanuvchi topilmadi")

        w_lat = row["workplace_latitude"]
        w_lon = row["workplace_longitude"]
        is_configured = (w_lat is not None and w_lon is not None and (w_lat != 0.0 or w_lon != 0.0))

        return {
            "success": True,
            "is_configured": is_configured,
            "workplace_name": row["workplace_name"] or "Ish joyi",
            "latitude": w_lat,
            "longitude": w_lon,
            "radius_meters": row["workplace_radius_meters"] or 50
        }

@router.post("/ping")
async def ping_employee_location(
    payload: LocationPingRequest,
    user: dict = Depends(get_current_user)
):
    """
    Xodim qurilmasidan avtomatik davriy lokatsiya yuborish.
    Rahbar kuzatilmaydi (faqat xodimlar).
    Xodimdan hech qanday qo'lda kiritish talab qilinmaydi.
    """
    if user["role"] == "ADMIN":
        return {"success": True, "message": "Rahbar kuzatilmaydi"}

    user_id = user["id"]
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT id, full_name, workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters
            FROM users WHERE id = ?
        """, (user_id,))
        row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xodim topilmadi")

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

        await conn.execute("""
            UPDATE users
            SET last_latitude = ?,
                last_longitude = ?,
                last_distance_meters = ?,
                last_location_updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            round(payload.latitude, 7),
            round(payload.longitude, 7),
            distance_meters,
            user_id
        ))
        await conn.commit()

        return {
            "success": True,
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
    Bosh Rahbar tomonidan muayyan xodim uchun alohida ish joyi lokatsiyasini belgilash.
    Har bir xodim uchun alohida kordinata va radius bo'lishi mumkin.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("SELECT id, full_name, role, last_latitude, last_longitude FROM users WHERE id = ?", (payload.user_id,))
        target_user = await cur.fetchone()

        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xodim topilmadi")

        if target_user["role"] == "ADMIN":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bosh Rahbarga ish joyi belgilanmaydi!")

        wp_name = payload.workplace_name.strip() or "Ish joyi"
        wp_lat = round(payload.latitude, 7)
        wp_lon = round(payload.longitude, 7)
        wp_radius = int(payload.radius_meters)

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
                last_distance_meters = ?
            WHERE id = ?
        """, (wp_name, wp_lat, wp_lon, wp_radius, new_distance, payload.user_id))

        audit_details = (
            f"Xodim '{target_user['full_name']}' uchun alohida ish joyi belgilandi: {wp_name} "
            f"({wp_lat:.6f}, {wp_lon:.6f}), radius: {wp_radius} metr"
        )
        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('LOCATION', ?, 'SET_EMPLOYEE_WORKPLACE', ?, ?)
        """, (payload.user_id, admin["full_name"], audit_details))

        await conn.commit()

        return {
            "success": True,
            "message": f"Xodim '{target_user['full_name']}' uchun ish joyi ({wp_name}) muvaffaqiyatli saqlandi! Radius: {wp_radius} metr",
            "employee_id": payload.user_id,
            "workplace_name": wp_name,
            "latitude": wp_lat,
            "longitude": wp_lon,
            "radius_meters": wp_radius,
            "distance_meters": new_distance
        }

@router.post("/clear-employee-workplace/{user_id}")
async def clear_employee_workplace(
    user_id: int,
    admin: dict = Depends(require_role(["ADMIN"]))
):
    """Xodimga biriktirilgan ish joyi lokatsiyasini o'chirish / tozalash"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("SELECT id, full_name FROM users WHERE id = ?", (user_id,))
        target_user = await cur.fetchone()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xodim topilmadi")

        await conn.execute("""
            UPDATE users
            SET workplace_name = 'Ish joyi',
                workplace_latitude = NULL,
                workplace_longitude = NULL,
                workplace_radius_meters = 50,
                last_distance_meters = NULL
            WHERE id = ?
        """, (user_id,))

        audit_details = f"Xodim '{target_user['full_name']}' uchun belgilangan ish joyi lokatsiyasi tozalandi"
        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('LOCATION', ?, 'CLEAR_EMPLOYEE_WORKPLACE', ?, ?)
        """, (user_id, admin["full_name"], audit_details))

        await conn.commit()

        return {
            "success": True,
            "message": f"'{target_user['full_name']}' ish joyi lokatsiyasi tozalandi"
        }

@router.get("/employees")
async def get_all_employees_location(admin: dict = Depends(require_role(["ADMIN"]))):
    """
    Barcha xodimlarning alohida biriktirilgan ish joylari va ularning jonli joylashuvi.
    Faqat Bosh Rahbar ko'ra oladi.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("""
            SELECT id, telegram_id, full_name, role, is_active,
                   workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                   last_latitude, last_longitude, last_distance_meters, last_location_updated_at
            FROM users
            WHERE is_active = 1 AND role != 'ADMIN'
            ORDER BY 
                CASE WHEN workplace_latitude IS NULL THEN 1 ELSE 0 END,
                CASE WHEN last_distance_meters IS NULL THEN 1 ELSE 0 END,
                last_distance_meters ASC,
                full_name ASC
        """)
        rows = await cur.fetchall()

        employees = []
        for r in rows:
            w_lat = r["workplace_latitude"]
            w_lon = r["workplace_longitude"]
            is_configured = (w_lat is not None and w_lon is not None and (w_lat != 0.0 or w_lon != 0.0))

            dist = r["last_distance_meters"]
            radius = r["workplace_radius_meters"] or 50
            is_inside = (dist <= radius) if (dist is not None and is_configured) else None

            employees.append({
                "id": r["id"],
                "telegram_id": r["telegram_id"],
                "full_name": r["full_name"],
                "role": r["role"],
                "workplace_name": r["workplace_name"] or "Ish joyi",
                "workplace_latitude": w_lat,
                "workplace_longitude": w_lon,
                "workplace_radius_meters": radius,
                "is_workplace_configured": is_configured,
                "last_latitude": r["last_latitude"],
                "last_longitude": r["last_longitude"],
                "last_distance_meters": dist,
                "last_location_updated_at": r["last_location_updated_at"],
                "is_inside": is_inside
            })

        return {
            "success": True,
            "employees": employees
        }
