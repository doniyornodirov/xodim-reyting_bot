import io
import math
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
import aiosqlite

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

from app.config import DB_PATH
from app.database import get_db_connection
from app.dependencies import get_current_user, require_role
from app.models import (
    LocationPingRequest,
    SetEmployeeWorkplaceRequest,
    DeviceTelemetryRequest,
    VerifiedCheckinRequest,
    LocationHistoryExportRequest
)

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

def format_event_dt_tashkent(dt_str: str) -> str:
    """ISO yoki matnli vaqtni Toshkent vaqti bo'yicha formatlash (DD.MM.YYYY HH:MM:SS)"""
    if not dt_str:
        return "-"
    try:
        clean_s = str(dt_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        uzb_dt = dt.astimezone(UZB_TZ)
        return uzb_dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return str(dt_str)[:19].replace("T", " ")

def format_event_time_tashkent(dt_str: str) -> str:
    """Faqat Toshkent soatini olish (HH:MM)"""
    if not dt_str:
        return "-"
    try:
        clean_s = str(dt_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        uzb_dt = dt.astimezone(UZB_TZ)
        return uzb_dt.strftime("%H:%M")
    except Exception:
        return str(dt_str)[:16].replace("T", " ")

def set_cell_background(cell, fill_hex: str):
    """DOCX jadval katakchasi orqa fon rangini o'rnatish"""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=140, right=140):
    """DOCX jadval katakchasi ichki hoshiyalarini o'rnatish (dxa birliklarida)"""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def set_table_borders(table, color="CBD5E1", sz="4", val="single"):
    """DOCX jadval chegara chiziqlarini chiroyli yupqa stilga o'rnatish"""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="none"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

async def record_location_event_update(
    conn: aiosqlite.Connection,
    user: dict | aiosqlite.Row,
    lat: float,
    lon: float,
    live_period: int | None = None,
    is_live_edit: bool = False,
    source: str = "TELEGRAM"
) -> dict:
    """
    Xodimning har bir jonli yoki davriy lokatsiya yangilanishini tahlil qilib,
    aniq tarixiy hodisalar (Live boshlanishi, 1 kunda qayta yuborilganlik,
    ish joyidan belgilangan radiusdan chiqish/qaytish, internet uzilishi)ni location_events ga muhrlash.
    """
    user_role = (user.get("role") or "").upper() if isinstance(user, dict) else (dict(user).get("role") or "").upper()
    if user_role in ("ADMIN", "DEVELOPER"):
        return {"success": True, "exempt": True}

    shift_status = user.get("shift_status") if isinstance(user, dict) else dict(user).get("shift_status")
    if shift_status == "RESTING":
        return {"success": True, "resting": True}

    u_dict = dict(user) if not isinstance(user, dict) else user
    user_id = u_dict["id"]
    company_id = u_dict.get("company_id") or 1

    now_utc_dt = datetime.now(timezone.utc)
    now_utc_str = now_utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    tashkent_now = datetime.now(UZB_TZ)
    today_str = tashkent_now.strftime("%Y-%m-%d")

    w_lat = u_dict.get("workplace_latitude")
    w_lon = u_dict.get("workplace_longitude")
    w_radius = u_dict.get("workplace_radius_meters") or 50
    is_configured = (w_lat is not None and w_lon is not None and (w_lat != 0.0 or w_lon != 0.0))

    distance_meters = calculate_haversine_meters(w_lat, w_lon, lat, lon) if is_configured else 0.0
    is_inside = (distance_meters <= w_radius) if is_configured else True

    restarted_warning = False
    starts_today_count = 0

    # 1. JONLI JOYLASHUV BOSHLANISHI YOKI BIR KUNDA QAYTA YUBORILISHI
    # Agar bu jonli joylashuv boshlangan ilk xabar bo'lsa (is_live_edit == False):
    if (live_period is not None or not is_live_edit) and not is_live_edit:
        cur_cnt = await conn.execute(
            "SELECT COUNT(*) FROM location_events WHERE user_id = ? AND event_date = ? AND event_type IN ('LIVE_STARTED', 'LIVE_RESTARTED')",
            (user_id, today_str)
        )
        row_cnt = await cur_cnt.fetchone()
        starts_today_count = row_cnt[0] if row_cnt else 0
        period_str = f"{live_period // 3600} soat" if (live_period and live_period >= 3600) else (f"{live_period // 60} daqiqa" if live_period else "8 soat")

        if starts_today_count == 0:
            await conn.execute("""
                INSERT INTO location_events (company_id, user_id, event_date, event_type, started_at, latitude, longitude, distance_meters, details)
                VALUES (?, ?, ?, 'LIVE_STARTED', ?, ?, ?, ?, ?)
            """, (company_id, user_id, today_str, now_utc_str, lat, lon, distance_meters, f"Kunlik jonli joylashuv boshlandi ({period_str})"))
        else:
            restarted_warning = True
            await conn.execute("""
                INSERT INTO location_events (company_id, user_id, event_date, event_type, started_at, latitude, longitude, distance_meters, details)
                VALUES (?, ?, ?, 'LIVE_RESTARTED', ?, ?, ?, ?, ?)
            """, (company_id, user_id, today_str, now_utc_str, lat, lon, distance_meters, f"Kun davomida {starts_today_count + 1}-marta jonli joylashuv qayta yuborildi ({period_str})"))

    # 2. INTERNET YOKI GPS QAYTA TIKLANISHI (SIGNAL_RESTORED)
    if u_dict.get("loc_signal_lost_at"):
        try:
            lost_dt = datetime.fromisoformat(str(u_dict["loc_signal_lost_at"]).replace("Z", "+00:00"))
            if lost_dt.tzinfo is None:
                lost_dt = lost_dt.replace(tzinfo=timezone.utc)
            duration_sec = max(60, int((now_utc_dt - lost_dt).total_seconds()))
        except Exception:
            duration_sec = 15 * 60
        duration_min = max(1, round(duration_sec / 60))

        await conn.execute("""
            INSERT INTO location_events (company_id, user_id, event_date, event_type, started_at, ended_at, duration_seconds, latitude, longitude, details)
            VALUES (?, ?, ?, 'SIGNAL_RESTORED', ?, ?, ?, ?, ?, ?)
        """, (company_id, user_id, today_str, u_dict["loc_signal_lost_at"], now_utc_str, duration_sec, lat, lon, f"Internet yoki GPS signali qayta tiklandi. O'chiq bo'lgan vaqt: {duration_min} daqiqa"))

        # Ochiq qolgan SIGNAL_LOST yozuvini yopish
        await conn.execute("""
            UPDATE location_events
            SET ended_at = ?, duration_seconds = ?
            WHERE user_id = ? AND event_type = 'SIGNAL_LOST' AND (ended_at IS NULL OR ended_at = '')
        """, (now_utc_str, duration_sec, user_id))

        await conn.execute("UPDATE users SET loc_signal_lost_at = NULL WHERE id = ?", (user_id,))

    # 3. GEOFENCING (ISH JOYIDAN CHIQISH VA QAYTISH HODISALARI)
    current_loc_state = u_dict.get("loc_state") or "INSIDE"
    loc_state_changed_at = u_dict.get("loc_state_changed_at")
    loc_max_dist = u_dict.get("loc_max_distance") or 0.0
    loc_last_event_id = u_dict.get("loc_last_event_id")

    if is_configured:
        if not is_inside:
            # Xodim belgilangan radiusdan tashqarida
            if current_loc_state != "OUTSIDE":
                # Ayni hozir chiqdi
                cur_ins = await conn.execute("""
                    INSERT INTO location_events (company_id, user_id, event_date, event_type, started_at, distance_meters, latitude, longitude, details)
                    VALUES (?, ?, ?, 'OUT_OF_BOUNDS_ENTER', ?, ?, ?, ?, ?)
                """, (company_id, user_id, today_str, now_utc_str, distance_meters, lat, lon, f"Ish joyidan chiqdi (Masofa: {int(distance_meters)}m, Ruxsat: {w_radius}m)"))
                new_event_id = cur_ins.lastrowid

                await conn.execute("""
                    UPDATE users
                    SET loc_state = 'OUTSIDE',
                        loc_state_changed_at = ?,
                        loc_max_distance = ?,
                        loc_last_event_id = ?
                    WHERE id = ?
                """, (now_utc_str, distance_meters, new_event_id, user_id))
            else:
                # Hali ham tashqarida: agar ko'proq uzoqlashgan bo'lsa maksimal masofani yangilash
                if distance_meters > loc_max_dist:
                    await conn.execute("UPDATE users SET loc_max_distance = ? WHERE id = ?", (distance_meters, user_id))
                    if loc_last_event_id:
                        await conn.execute("UPDATE location_events SET distance_meters = ? WHERE id = ?", (distance_meters, loc_last_event_id))
        else:
            # Xodim ish joyi radiusida
            if current_loc_state == "OUTSIDE":
                # Tashqaridan ish joyiga qaytib kirdi!
                duration_sec = 60
                if loc_state_changed_at:
                    try:
                        left_dt = datetime.fromisoformat(str(loc_state_changed_at).replace("Z", "+00:00"))
                        if left_dt.tzinfo is None:
                            left_dt = left_dt.replace(tzinfo=timezone.utc)
                        duration_sec = max(60, int((now_utc_dt - left_dt).total_seconds()))
                    except Exception:
                        duration_sec = 60
                duration_min = max(1, round(duration_sec / 60))
                final_max_dist = max(loc_max_dist, distance_meters)

                await conn.execute("""
                    INSERT INTO location_events (company_id, user_id, event_date, event_type, started_at, ended_at, duration_seconds, distance_meters, latitude, longitude, details)
                    VALUES (?, ?, ?, 'OUT_OF_BOUNDS_EXIT', ?, ?, ?, ?, ?, ?, ?)
                """, (company_id, user_id, today_str, loc_state_changed_at or now_utc_str, now_utc_str, duration_sec, final_max_dist, lat, lon, f"Ish joyiga qaytdi. Tashqarida bo'lgan vaqt: {duration_min} daqiqa (Maksimal masofa: {int(final_max_dist)}m)"))

                if loc_last_event_id:
                    await conn.execute("""
                        UPDATE location_events
                        SET ended_at = ?, duration_seconds = ?, distance_meters = ?
                        WHERE id = ?
                    """, (now_utc_str, duration_sec, final_max_dist, loc_last_event_id))

                await conn.execute("""
                    UPDATE users
                    SET loc_state = 'INSIDE',
                        loc_state_changed_at = ?,
                        loc_max_distance = 0.0,
                        loc_last_event_id = NULL
                    WHERE id = ?
                """, (now_utc_str, user_id))

    return {
        "success": True,
        "distance_meters": distance_meters,
        "is_inside": is_inside,
        "restarted_warning": restarted_warning,
        "starts_today_count": starts_today_count + 1 if restarted_warning else 1
    }

async def check_employee_signal_loss():
    """
    Har 30-60 soniyada fonda tekshiruvchi funksiya:
    Agar xodim ish soati ichida bo'lsa va oxirgi koordinata yangilanishidan 15 daqiqa o'tgan bo'lsa,
    internet yoki GPS o'chirilgan (SIGNAL_LOST) deb tarixga qayd etadi.
    """
    now_utc_dt = datetime.now(timezone.utc)
    tashkent_now = datetime.now(UZB_TZ)
    today_str = tashkent_now.strftime("%Y-%m-%d")
    time_hm = tashkent_now.strftime("%H:%M")

    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("""
                SELECT id, company_id, full_name, work_start_time, work_end_time,
                       last_location_updated_at, loc_signal_lost_at
                FROM users
                WHERE is_active = 1
                  AND shift_status = 'WORKING'
                  AND UPPER(COALESCE(role, '')) NOT IN ('ADMIN', 'DEVELOPER')
                  AND last_location_updated_at IS NOT NULL
            """)
            users = await cur.fetchall()

            for u in users:
                start_t = u["work_start_time"] or "09:00"
                end_t = u["work_end_time"] or "19:00"
                if not is_time_within_interval(time_hm, start_t, end_t):
                    continue

                raw_upd = u["last_location_updated_at"]
                if not raw_upd:
                    continue

                try:
                    upd_clean = str(raw_upd).replace("Z", "+00:00")
                    loc_dt = datetime.fromisoformat(upd_clean)
                    if loc_dt.tzinfo is None:
                        loc_dt = loc_dt.replace(tzinfo=timezone.utc)
                    lag_min = (now_utc_dt - loc_dt).total_seconds() / 60.0
                except Exception:
                    lag_min = 0.0

                # 15 daqiqa uzilish bo'lsa va hali yozilmagan bo'lsa
                if lag_min >= 15.0 and not u["loc_signal_lost_at"]:
                    lost_time_str = (loc_dt + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    await conn.execute("""
                        INSERT INTO location_events (company_id, user_id, event_date, event_type, started_at, details)
                        VALUES (?, ?, ?, 'SIGNAL_LOST', ?, ?)
                    """, (u["company_id"], u["id"], today_str, lost_time_str, f"Internet yoki GPS joylashuv o'chirildi (Signal {int(lag_min)} daqiqadan beri kelmayapti)"))

                    await conn.execute("""
                        UPDATE users SET loc_signal_lost_at = ? WHERE id = ?
                    """, (lost_time_str, u["id"]))

            await conn.commit()
    except Exception:
        pass

@router.get("/my-workplace")
async def get_my_workplace(user: dict = Depends(get_current_user)):
    """Xodimning o'ziga biriktirilgan ish joyi, belgilangan ish soatlari va jonli signal holatini olish"""
    if user.get("role") in ("ADMIN", "DEVELOPER"):
        return {
            "success": True,
            "is_configured": False,
            "is_signal_lost": False,
            "is_within_hours": False,
            "shift_status": "WORKING",
            "message": "Rahbar va Dasturchi lokatsiyaga bog'lanmagan"
        }
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
    if user.get("role") in ("ADMIN", "DEVELOPER"):
        return {"success": True, "message": "Rahbar va Dasturchi kuzatilmaydi"}

    user_id = user["id"]
    async with get_db_connection() as conn:
        cur = await conn.execute("""
            SELECT id, company_id, role, full_name, workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                   work_start_time, work_end_time, shift_status, loc_state, loc_state_changed_at, loc_max_distance, loc_signal_lost_at, loc_last_event_id
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

        # Tarixiy hodisalar jurnali (Location Events) ga muhrlash
        if is_within_hours and shift_status != "RESTING":
            await record_location_event_update(
                conn=conn,
                user=row,
                lat=payload.latitude,
                lon=payload.longitude,
                live_period=None,
                is_live_edit=True,
                source="WEB_PING"
            )

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

        # Windows kompyuter / noutbuk uchun cheklov qo'yilmaydi (faqat mobil apparatlar cheklanadi)
        import re
        if re.search(r"Windows|Win32|Win64|kompyuter|Macintosh", incoming_dev_name, re.I):
            return {
                "success": True,
                "is_trusted": True,
                "action": "WINDOWS_EXEMPT",
                "device_token": incoming_token or "windows_token",
                "device_name": incoming_dev_name,
                "user": dict(user),
                "message": "Windows kompyuter uchun apparat cheklovi qo'yilmaydi."
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

        # Tarixiy hodisalar jurnali (Location Events) ga muhrlash
        await record_location_event_update(
            conn=conn,
            user=user,
            lat=lat,
            lon=lon,
            live_period=8 * 3600,
            is_live_edit=False,
            source="WEB_CHECKIN"
        )
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


# =========================================================================
# GEOLOKATSIYA VA JONLI MONITORING TARIXI (DOCX HISOBOT VA EKSPORT)
# =========================================================================

def generate_location_history_docx(
    comp_name: str,
    start_date: str,
    end_date: str,
    users: list[dict],
    events: list[dict]
) -> tuple[io.BytesIO, dict]:
    """
    Xodimlarning jonli joylashuv va ish joyi nazorati tarixi bo'yicha
    to'liq va professional Microsoft Word (.docx) hisobotini generatsiya qilish.
    """
    doc = docx.Document()
    sec = doc.sections[0]
    sec.top_margin = Inches(0.5)
    sec.bottom_margin = Inches(0.5)
    sec.left_margin = Inches(0.5)
    sec.right_margin = Inches(0.5)

    # 1. Hujjat sarlavhasi
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_title = p_title.add_run("XODIMLARNING GEOLOKATSIYA VA ISH JOYI MONITORING HISOBOTI\n")
    r_title.font.name = "Calibri"
    r_title.font.size = Pt(14)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(30, 58, 138)

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_sub = p_sub.add_run(
        f"🏢 Tashkilot: {comp_name}   |   📅 Davr: {start_date} dan {end_date} gacha   |   🕒 Shakllantirildi: {datetime.now(UZB_TZ).strftime('%d.%m.%Y %H:%M')}"
    )
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(9.5)
    r_sub.font.italic = True
    r_sub.font.color.rgb = RGBColor(100, 116, 139)

    # Statistika xulosalari
    total_employees = len(users)
    active_live_users = len(set(e["user_id"] for e in events if e.get("event_type") in ("LIVE_STARTED", "LIVE_RESTARTED")))
    out_of_bounds_events = [e for e in events if e.get("event_type") == "OUT_OF_BOUNDS_ENTER"]
    out_of_bounds_exits = [e for e in events if e.get("event_type") == "OUT_OF_BOUNDS_EXIT"]
    signal_lost_events = [e for e in events if e.get("event_type") == "SIGNAL_LOST"]
    signal_rest_events = [e for e in events if e.get("event_type") == "SIGNAL_RESTORED"]
    live_restarts = [e for e in events if e.get("event_type") == "LIVE_RESTARTED"]

    total_out_minutes = sum((e.get("duration_seconds") or 0) for e in out_of_bounds_exits) // 60
    total_sig_lost_minutes = sum((e.get("duration_seconds") or 0) for e in signal_rest_events) // 60

    # 2. Umumiy statistika kartochkasi (Summary Cards Table)
    sum_tbl = doc.add_table(rows=2, cols=4)
    sum_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(sum_tbl, color="E2E8F0")

    stat_cards = [
        ("👥 Jami Xodimlar", f"{total_employees} nafar", "F1F5F9", "1E293B"),
        ("🛰 Jonli Lokatsiya", f"{active_live_users} nafar faol", "EFF6FF", "1D4ED8"),
        ("🚪 Ish joyidan chiqish", f"{len(out_of_bounds_events)} ta ({total_out_minutes} daq)", "FEF2F2", "B91C1C"),
        ("📵 Aloqa uzilishi", f"{len(signal_lost_events)} ta ({total_sig_lost_minutes} daq)", "FFFBEB", "B45309"),
    ]
    for col_idx, (card_title, card_val, bg_hex, text_hex) in enumerate(stat_cards):
        c_title = sum_tbl.cell(0, col_idx)
        c_title.text = card_title
        set_cell_background(c_title, bg_hex)
        set_cell_margins(c_title, top=80, bottom=40, left=100, right=100)
        p1 = c_title.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p1.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(8.5)
            run.font.bold = True
            run.font.color.rgb = RGBColor(100, 116, 139)

        c_val = sum_tbl.cell(1, col_idx)
        c_val.text = card_val
        set_cell_background(c_val, bg_hex)
        set_cell_margins(c_val, top=40, bottom=80, left=100, right=100)
        p2 = c_val.paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p2.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(10.5)
            run.font.bold = True
            r_int = int(text_hex[0:2], 16)
            g_int = int(text_hex[2:4], 16)
            b_int = int(text_hex[4:6], 16)
            run.font.color.rgb = RGBColor(r_int, g_int, b_int)

    doc.add_paragraph()

    # 3. Xodimlar bo'yicha yakuniy hisobot jadvali
    p_sec1 = doc.add_paragraph()
    r_sec1 = p_sec1.add_run("1. XODIMLAR BO'YICHA MONITORING VA INTIZOM XULOSASI")
    r_sec1.font.name = "Calibri"
    r_sec1.font.size = Pt(11)
    r_sec1.font.bold = True
    r_sec1.font.color.rgb = RGBColor(15, 23, 42)

    emp_tbl = doc.add_table(rows=1 + len(users), cols=7)
    emp_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(emp_tbl, color="CBD5E1")

    headers_emp = [
        "№", "Xodim F.I.SH", "Filial / Ruxsat", "Jonli Joylashuv",
        "Ish joyidan chiqishlar", "Internet / GPS uzilishlar", "Holat / Xulosa"
    ]
    for col_idx, h_text in enumerate(headers_emp):
        cell = emp_tbl.cell(0, col_idx)
        cell.text = h_text
        set_cell_background(cell, "1E3A8A")
        set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(8.5)
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, u in enumerate(users, start=1):
        u_events = [e for e in events if e.get("user_id") == u["id"]]
        live_s = [e for e in u_events if e.get("event_type") == "LIVE_STARTED"]
        live_r = [e for e in u_events if e.get("event_type") == "LIVE_RESTARTED"]
        outs_enter = [e for e in u_events if e.get("event_type") == "OUT_OF_BOUNDS_ENTER"]
        outs_exit = [e for e in u_events if e.get("event_type") == "OUT_OF_BOUNDS_EXIT"]
        sigs_lost = [e for e in u_events if e.get("event_type") == "SIGNAL_LOST"]
        sigs_rest = [e for e in u_events if e.get("event_type") == "SIGNAL_RESTORED"]

        # Jonli lokatsiya ustuni
        if not live_s and not live_r:
            live_text = "Yuborilmagan ❌"
        else:
            first_live_time = format_event_time_tashkent(live_s[0]["started_at"]) if live_s else format_event_time_tashkent(live_r[0]["started_at"])
            restarts_cnt = len(live_r)
            if restarts_cnt > 0:
                live_text = f"🕒 {first_live_time}\n(⚠️ {restarts_cnt + 1} marta qayta yuborilgan)"
            else:
                live_text = f"🕒 {first_live_time} (1 marta)"

        # Ish joyidan chiqish ustuni
        if not outs_enter:
            out_text = "✅ Chiqmagan\n(Doim ish joyida)"
        else:
            max_d = max((e.get("distance_meters") or 0) for e in outs_enter)
            tot_out_m = sum((e.get("duration_seconds") or 0) for e in outs_exit) // 60
            out_text = f"⚠️ {len(outs_enter)} marta\n(Maks: {int(max_d)}m, {tot_out_m} daq)"

        # Internet uzilish ustuni
        if not sigs_lost:
            sig_text = "✅ Uzilishsiz\n(Doim onlayn)"
        else:
            tot_sig_m = sum((e.get("duration_seconds") or 0) for e in sigs_rest) // 60
            sig_text = f"📵 {len(sigs_lost)} marta\n(Jami: {tot_sig_m} daq o'chiq)"

        # Holat ustuni
        if len(outs_enter) == 0 and len(sigs_lost) == 0 and (live_s or live_r):
            status_text = "🟢 Qoidaga muvofiq"
        elif not live_s and not live_r:
            status_text = "⚪ Lokatsiya yo'q"
        else:
            status_text = "⚠️ Qoidabuzarlik bor"

        wp_info = f"{u.get('workplace_name') or 'Bosh ofis'}\n({u.get('workplace_radius_meters') or 50} m ruxsat)"

        row_cells = [
            str(row_idx),
            u["full_name"],
            wp_info,
            live_text,
            out_text,
            sig_text,
            status_text
        ]

        bg_color = "F8FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, cell_val in enumerate(row_cells):
            c = emp_tbl.cell(row_idx, col_idx)
            c.text = cell_val
            set_cell_background(c, bg_color)
            set_cell_margins(c, top=80, bottom=80, left=100, right=100)
            p = c.paragraphs[0]
            if col_idx in (0, 3, 6):
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.font.name = "Calibri"
                run.font.size = Pt(8)
                if col_idx == 1:
                    run.font.bold = True

    doc.add_paragraph()

    # 4. Batafsil xronologik hodisalar jurnali
    p_sec2 = doc.add_paragraph()
    r_sec2 = p_sec2.add_run("2. BATAFSIL HODISALAR VA VOQEALAR XRONOLOGIYASI")
    r_sec2.font.name = "Calibri"
    r_sec2.font.size = Pt(11)
    r_sec2.font.bold = True
    r_sec2.font.color.rgb = RGBColor(15, 23, 42)

    user_map = {u["id"]: u["full_name"] for u in users}
    events_to_show = events[:300]

    ev_tbl = doc.add_table(rows=1 + len(events_to_show), cols=6)
    ev_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(ev_tbl, color="CBD5E1")

    headers_ev = ["Vaqt", "Xodim", "Hodisa Turi", "Masofa", "Davomiylik", "Tafsilot"]
    for col_idx, h_text in enumerate(headers_ev):
        cell = ev_tbl.cell(0, col_idx)
        cell.text = h_text
        set_cell_background(cell, "334155")
        set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(8)
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)

    ev_type_labels = {
        "LIVE_STARTED": "🟢 Jonli joylashuv boshlandi",
        "LIVE_RESTARTED": "⚠️ Qayta yuborildi",
        "OUT_OF_BOUNDS_ENTER": "🔴 Ish joyidan chiqdi",
        "OUT_OF_BOUNDS_EXIT": "🟢 Ish joyiga qaytdi",
        "SIGNAL_LOST": "📵 Internet/GPS o'chirildi",
        "SIGNAL_RESTORED": "🟢 Aloqa tiklandi",
    }

    for row_idx, ev in enumerate(events_to_show, start=1):
        dt_formatted = format_event_dt_tashkent(ev.get("started_at"))
        emp_name = user_map.get(ev.get("user_id"), f"Xodim #{ev.get('user_id')}")
        ev_label = ev_type_labels.get(ev.get("event_type"), ev.get("event_type") or "-")
        dist_str = f"{int(ev['distance_meters'])} m" if ev.get("distance_meters") else "-"
        dur_str = f"{ev['duration_seconds'] // 60} daq" if ev.get("duration_seconds") else "-"
        details = ev.get("details") or "-"

        ev_cells = [dt_formatted, emp_name, ev_label, dist_str, dur_str, details]
        bg_color = "F8FAFC" if row_idx % 2 == 1 else "FFFFFF"

        for col_idx, cell_val in enumerate(ev_cells):
            c = ev_tbl.cell(row_idx, col_idx)
            c.text = cell_val
            set_cell_background(c, bg_color)
            set_cell_margins(c, top=60, bottom=60, left=80, right=80)
            p = c.paragraphs[0]
            if col_idx in (0, 3, 4):
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.font.name = "Calibri"
                run.font.size = Pt(7.5)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    summary = {
        "company_name": comp_name,
        "total_employees": total_employees,
        "active_live_users": active_live_users,
        "total_out_bounds_count": len(out_of_bounds_events),
        "total_out_bounds_minutes": total_out_minutes,
        "total_signal_lost_count": len(signal_lost_events),
        "total_signal_lost_minutes": total_sig_lost_minutes,
        "total_events": len(events)
    }

    return buf, summary


@router.post("/history/export-docx")
async def export_location_history_docx(
    req: LocationHistoryExportRequest,
    admin: dict = Depends(require_role(["ADMIN", "DEVELOPER"]))
):
    """
    Rahbar (yoki Dasturchi Admin) uchun xodimlarning geolokatsiya tarixi bo'yicha
    DOCX hisobotini shakllantirib, uning shaxsiy Telegramiga bot orqali jo'natish.
    """
    from app.bot import bot
    from aiogram.types import BufferedInputFile

    comp_id = admin.get("company_id") or 1
    # Dasturchi Admin bo'lsa (company_id=0), 1-kompaniyani ko'rsatish
    if comp_id == 0:
        comp_id = 1

    admin_tg_id = admin.get("telegram_id")
    if not admin_tg_id:
        raise HTTPException(status_code=400, detail="Rahbarning Telegram ID si aniqlanmadi!")

    async with get_db_connection() as conn:
        # Tashkilot nomi
        cur_c = await conn.execute("SELECT name FROM companies WHERE id = ?", (comp_id,))
        c_row = await cur_c.fetchone()
        comp_name = c_row["name"] if c_row else "Bosh Tashkilot"

        # Xodimlar ro'yxati
        if req.user_id:
            cur_u = await conn.execute("""
                SELECT id, full_name, workplace_name, workplace_radius_meters
                FROM users WHERE id = ? AND company_id = ?
            """, (req.user_id, comp_id))
        else:
            cur_u = await conn.execute("""
                SELECT id, full_name, workplace_name, workplace_radius_meters
                FROM users 
                WHERE company_id = ? 
                  AND is_active = 1
                  AND UPPER(COALESCE(role, '')) NOT IN ('ADMIN', 'DEVELOPER')
                ORDER BY full_name ASC
            """, (comp_id,))
        users_raw = await cur_u.fetchall()
        users_list = [dict(u) for u in users_raw]

        if not users_list:
            raise HTTPException(status_code=404, detail="Kompaniyada hisobot uchun faol xodimlar topilmadi!")

        # Hodisalar ro'yxati (location_events)
        if req.user_id:
            cur_ev = await conn.execute("""
                SELECT * FROM location_events
                WHERE company_id = ? 
                  AND user_id = ?
                  AND event_date BETWEEN ? AND ?
                ORDER BY started_at ASC
            """, (comp_id, req.user_id, req.start_date, req.end_date))
        else:
            cur_ev = await conn.execute("""
                SELECT * FROM location_events
                WHERE company_id = ? 
                  AND event_date BETWEEN ? AND ?
                ORDER BY started_at ASC
            """, (comp_id, req.start_date, req.end_date))
        events_raw = await cur_ev.fetchall()
        events_list = [dict(e) for e in events_raw]

        # DOCX generatsiyasi
        docx_buf, summary = generate_location_history_docx(
            comp_name=comp_name,
            start_date=req.start_date,
            end_date=req.end_date,
            users=users_list,
            events=events_list
        )

        # Telegram bot orqali Rahbarga jo'natish
        if not bot:
            raise HTTPException(status_code=500, detail="Telegram bot faollashtirilmagan (BOT_TOKEN topilmadi)!")

        file_bytes = docx_buf.getvalue()
        filename = f"Geolokatsiya_tarixi_{req.start_date}_{req.end_date}.docx"

        caption = (
            f"📍 <b>XODIMLAR GEOLOKATSIYA TARIXI HISOBOTI (DOCX)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏢 <b>Tashkilot:</b> {comp_name}\n"
            f"📅 <b>Davr:</b> {req.start_date} dan {req.end_date} gacha\n"
            f"👥 <b>Xodimlar soni:</b> {summary['total_employees']} nafar\n"
            f"🛰 <b>Jonli joylashuv yuborganlar:</b> {summary['active_live_users']} nafar\n"
            f"🚪 <b>Ish joyidan chiqishlar:</b> {summary['total_out_bounds_count']} ta ({summary['total_out_bounds_minutes']} daq)\n"
            f"📵 <b>Internet/GPS uzilishlar:</b> {summary['total_signal_lost_count']} ta ({summary['total_signal_lost_minutes']} daq)\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📎 Batafsil jadvallar va aniq xronologiya ilova qilingan Word (.docx) faylida."
        )

        try:
            await bot.send_document(
                chat_id=admin_tg_id,
                document=BufferedInputFile(file_bytes, filename=filename),
                caption=caption
            )
        except Exception as err:
            raise HTTPException(status_code=500, detail=f"Telegram bot orqali jo'natishda xatolik: {err}")

        return {
            "success": True,
            "message": f"Geolokatsiya tarixi DOCX hisoboti Rahbarning Telegramiga ({admin_tg_id}) muvaffaqiyatli jo'natildi!",
            "filename": filename,
            "summary": summary
        }


@router.get("/history/download-docx")
async def download_location_history_docx(
    start_date: str = Query(..., description="Boshlanish sanasi"),
    end_date: str = Query(..., description="Tugash sanasi"),
    user_id: Optional[int] = Query(None, description="Xodim ID si"),
    admin: dict = Depends(require_role(["ADMIN", "DEVELOPER"]))
):
    """DOCX formatdagi hisobotni veb-brauzer orqali to'g'ridan-to'g'ri yuklab olish"""
    comp_id = admin.get("company_id") or 1
    if comp_id == 0:
        comp_id = 1

    async with get_db_connection() as conn:
        cur_c = await conn.execute("SELECT name FROM companies WHERE id = ?", (comp_id,))
        c_row = await cur_c.fetchone()
        comp_name = c_row["name"] if c_row else "Bosh Tashkilot"

        if user_id:
            cur_u = await conn.execute("""
                SELECT id, full_name, workplace_name, workplace_radius_meters
                FROM users WHERE id = ? AND company_id = ?
            """, (user_id, comp_id))
        else:
            cur_u = await conn.execute("""
                SELECT id, full_name, workplace_name, workplace_radius_meters
                FROM users 
                WHERE company_id = ? 
                  AND is_active = 1
                  AND UPPER(COALESCE(role, '')) NOT IN ('ADMIN', 'DEVELOPER')
                ORDER BY full_name ASC
            """, (comp_id,))
        users_list = [dict(u) for u in await cur_u.fetchall()]

        if not users_list:
            raise HTTPException(status_code=404, detail="Xodimlar topilmadi!")

        if user_id:
            cur_ev = await conn.execute("""
                SELECT * FROM location_events
                WHERE company_id = ? 
                  AND user_id = ?
                  AND event_date BETWEEN ? AND ?
                ORDER BY started_at ASC
            """, (comp_id, user_id, start_date, end_date))
        else:
            cur_ev = await conn.execute("""
                SELECT * FROM location_events
                WHERE company_id = ? 
                  AND event_date BETWEEN ? AND ?
                ORDER BY started_at ASC
            """, (comp_id, start_date, end_date))
        events_list = [dict(e) for e in await cur_ev.fetchall()]

        docx_buf, _ = generate_location_history_docx(
            comp_name=comp_name,
            start_date=start_date,
            end_date=end_date,
            users=users_list,
            events=events_list
        )

        filename = f"Geolokatsiya_tarixi_{start_date}_{end_date}.docx"
        return Response(
            content=docx_buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )


@router.get("/history/events")
async def get_location_history_events(
    start_date: str = Query(..., description="Boshlanish sanasi"),
    end_date: str = Query(..., description="Tugash sanasi"),
    user_id: Optional[int] = Query(None, description="Xodim ID si"),
    admin: dict = Depends(require_role(["ADMIN", "DEVELOPER"]))
):
    """Geolokatsiya hodisalari jurnali (Events JSON ro'yxati)"""
    comp_id = admin.get("company_id") or 1
    if comp_id == 0:
        comp_id = 1

    async with get_db_connection() as conn:
        if user_id:
            cur = await conn.execute("""
                SELECT le.*, u.full_name as employee_name, u.telegram_id as employee_tg_id
                FROM location_events le
                JOIN users u ON u.id = le.user_id
                WHERE le.company_id = ? AND le.user_id = ? AND le.event_date BETWEEN ? AND ?
                ORDER BY le.started_at DESC
                LIMIT 500
            """, (comp_id, user_id, start_date, end_date))
        else:
            cur = await conn.execute("""
                SELECT le.*, u.full_name as employee_name, u.telegram_id as employee_tg_id
                FROM location_events le
                JOIN users u ON u.id = le.user_id
                WHERE le.company_id = ? AND le.event_date BETWEEN ? AND ?
                ORDER BY le.started_at DESC
                LIMIT 500
            """, (comp_id, start_date, end_date))

        rows = await cur.fetchall()
        return {
            "success": True,
            "events": [dict(r) for r in rows]
        }
