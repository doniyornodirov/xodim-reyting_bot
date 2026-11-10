import math
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite

from app.config import DB_PATH
from app.dependencies import get_current_user, require_role
from app.models import WorkplaceLocationUpdate, LocationPingRequest

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

async def _get_workplace_settings(conn: aiosqlite.Connection) -> dict:
    cur = await conn.execute(
        "SELECT key, value FROM system_settings WHERE key IN ('workplace_lat', 'workplace_lon', 'workplace_radius', 'workplace_name')"
    )
    rows = await cur.fetchall()
    settings = {r["key"]: r["value"] for r in rows}

    try:
        lat = float(settings.get("workplace_lat", "0"))
        lon = float(settings.get("workplace_lon", "0"))
    except (ValueError, TypeError):
        lat, lon = 0.0, 0.0

    try:
        radius = int(settings.get("workplace_radius", "50"))
    except (ValueError, TypeError):
        radius = 50

    name = settings.get("workplace_name", "Bosh Ofis")
    is_configured = not (lat == 0.0 and lon == 0.0)

    return {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "radius_meters": radius,
        "is_configured": is_configured
    }

@router.get("/workplace")
async def get_workplace_location(user: dict = Depends(get_current_user)):
    """Ish joyi kordinatalari va geofence radiusini olish (barcha xodimlar uchun)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        workplace = await _get_workplace_settings(conn)
        return {"success": True, **workplace}

@router.post("/workplace")
async def update_workplace_location(
    payload: WorkplaceLocationUpdate,
    admin: dict = Depends(require_role(["ADMIN"]))
):
    """Ish joyi kordinatalarini belgilash yoki o'zgartirish (faqat Bosh Rahbar uchun)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        items = [
            ("workplace_lat", str(round(payload.latitude, 7))),
            ("workplace_lon", str(round(payload.longitude, 7))),
            ("workplace_radius", str(int(payload.radius_meters))),
            ("workplace_name", payload.name.strip() or "Bosh Ofis")
        ]

        for k, v in items:
            await conn.execute("""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, (k, v))

        audit_details = (
            f"Ish joyi geolokatsiyasi belgilandi: {payload.name.strip()} "
            f"({payload.latitude:.6f}, {payload.longitude:.6f}), radius: {payload.radius_meters} metr"
        )
        await conn.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('LOCATION', 1, 'UPDATE_WORKPLACE_GEOFENCE', ?, ?)
        """, (admin["full_name"], audit_details))

        await conn.commit()

        workplace = await _get_workplace_settings(conn)
        return {
            "success": True,
            "message": f"Ish joyi manzili ({payload.name}) muvaffaqiyatli saqlandi! Radius: {payload.radius_meters} metr",
            **workplace
        }

@router.post("/ping")
async def ping_employee_location(
    payload: LocationPingRequest,
    user: dict = Depends(get_current_user)
):
    """
    Xodim qurilmasidan avtomatik davriy lokatsiya yuborish.
    Xodimdan hech qanday qo'lda kiritish talab qilinmaydi.
    """
    user_id = user["id"]
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        workplace = await _get_workplace_settings(conn)

        distance_meters = None
        is_inside = None

        if workplace["is_configured"]:
            distance_meters = calculate_haversine_meters(
                workplace["latitude"],
                workplace["longitude"],
                payload.latitude,
                payload.longitude
            )
            is_inside = distance_meters <= workplace["radius_meters"]

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
            "radius_meters": workplace["radius_meters"],
            "is_inside": is_inside,
            "workplace_name": workplace["name"],
            "workplace_configured": workplace["is_configured"],
            "updated_at": datetime.now().isoformat()
        }

@router.get("/employees")
async def get_employees_location(admin: dict = Depends(require_role(["ADMIN"]))):
    """Barcha faol xodimlarning joriy joylashuvi va masofasini ko'rish (faqat Rahbar uchun)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        workplace = await _get_workplace_settings(conn)

        cur = await conn.execute("""
            SELECT id, telegram_id, full_name, role, is_active,
                   last_latitude, last_longitude, last_distance_meters, last_location_updated_at
            FROM users
            WHERE is_active = 1 AND role != 'ADMIN'
            ORDER BY 
                CASE WHEN last_distance_meters IS NULL THEN 1 ELSE 0 END,
                last_distance_meters ASC,
                full_name ASC
        """)
        rows = await cur.fetchall()

        employees = []
        for r in rows:
            dist = r["last_distance_meters"]
            is_inside = (dist <= workplace["radius_meters"]) if (dist is not None and workplace["is_configured"]) else None
            employees.append({
                "id": r["id"],
                "telegram_id": r["telegram_id"],
                "full_name": r["full_name"],
                "role": r["role"],
                "last_latitude": r["last_latitude"],
                "last_longitude": r["last_longitude"],
                "last_distance_meters": dist,
                "last_location_updated_at": r["last_location_updated_at"],
                "is_inside": is_inside
            })

        return {
            "success": True,
            "workplace": workplace,
            "employees": employees
        }
