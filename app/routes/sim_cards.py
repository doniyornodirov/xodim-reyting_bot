from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
import aiosqlite

from app.database import get_db
from app.dependencies import get_current_user
from app.services.sim_service import VALID_OPERATORS, validate_serial_range, get_sim_inventory_summary
from app.services.idempotency import check_idempotency, record_idempotency_result

router = APIRouter(prefix="/api/sim-cards", tags=["Sim Cards"])

@router.get("/employees")
async def get_sim_employees(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Sim-karta tarqatish uchun faol xodimlar ro'yxati"""
    if current_user["role"] not in ["ADMIN", "CASHIER"]:
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan.")
    comp_id = current_user.get("company_id") or 1
    cursor = await db.execute("""
        SELECT id, telegram_id, full_name, role 
        FROM users 
        WHERE is_active = 1 AND role NOT IN ('ADMIN', 'DEVELOPER') AND company_id = ?
        ORDER BY full_name ASC
    """, (comp_id,))
    rows = await cursor.fetchall()
    return {"success": True, "data": [dict(r) for r in rows]}

VALID_OPERATORS = ["Uzmobile", "Beeline", "Ucell", "Mobiuz", "Perfectum"]

class SimDistributeRequest(BaseModel):
    operator_type: str = Field("Uzmobile", description="Sim-karta turi: Uzmobile, Beeline, Ucell, Mobiuz, Perfectum")
    start_serial: str = Field(..., description="18 xonali boshlang'ich seriya raqami")
    end_serial: Optional[str] = Field(None, description="18 xonali tugash seriya raqami")
    employee_id: int = Field(..., description="Qabul qiluvchi xodim ID si")
    idempotency_key: Optional[str] = Field(None, description="Noyob tranzaksiya kaliti (takroriy bosishdan himoya)")

@router.post("/distribute")
async def distribute_sim_cards(
    payload: SimDistributeRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Sim-kartalarni xodimlarga tarqatish (Rahbar va Kassir uchun).
    18 xonali seriya raqamlari diapazoni ('...dan ...gacha') va operator turi bo'yicha bazaga qo'shiladi.
    """
    if current_user["role"] not in ["ADMIN", "CASHIER"]:
        raise HTTPException(status_code=403, detail="Sim-karta tarqatish huquqi faqat Bosh Rahbar va Kassirga berilgan.")

    if current_user.get("role") != "ADMIN" and current_user.get("shift_status") == "RESTING":
        raise HTTPException(status_code=403, detail="Siz hozirda dam olish (damda) rejimidasiz! Sim-karta tarqatish amallari vaqtinchalik cheklangan.")

    # Idempotentlik tekshiruvi (takroriy bosishdan himoya)
    is_new, cached_res = await check_idempotency(payload.idempotency_key, current_user["id"], action="SIM_DISTRIBUTE")
    if not is_new:
        return cached_res

    op_type = payload.operator_type.strip()
    if op_type not in VALID_OPERATORS:
        raise HTTPException(status_code=400, detail=f"Noto'g'ri operator turi! Faqat {', '.join(VALID_OPERATORS)} tanlanishi mumkin.")

    try:
        start_num, end_num, total_count = validate_serial_range(payload.start_serial, payload.end_serial or payload.start_serial)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start_str = payload.start_serial.strip().replace(" ", "")
    end_str = (payload.end_serial.strip().replace(" ", "") if payload.end_serial else start_str)

    comp_id = current_user.get("company_id") or 1

    # 2. Xodimni tekshirish
    cursor = await db.execute("SELECT id, full_name, telegram_id, role, is_active, shift_status FROM users WHERE id = ? AND company_id = ?", (payload.employee_id, comp_id))
    employee = await cursor.fetchone()
    if not employee:
        raise HTTPException(status_code=404, detail="Tanlangan xodim topilmadi.")
    if employee["role"] == "ADMIN":
        raise HTTPException(status_code=400, detail="Rahbar xodim bo'la olmaydi va unga sim-karta biriktirib bo'lmaydi!")
    if not employee["is_active"]:
        raise HTTPException(status_code=400, detail="Faolsizlantirilgan xodimga sim-karta berib bo'lmaydi.")
    if employee["shift_status"] == "RESTING":
        raise HTTPException(status_code=400, detail=f"Xodim '{employee['full_name']}' hozirda dam olish (damda) rejimida! Unga sim-karta biriktirib bo'lmaydi.")

    # 3. Seriya raqamlari ro'yxatini shakllantirish
    serials_to_insert = [str(n).zfill(18) for n in range(start_num, end_num + 1)]

    # 4. Oldin kiritilgan seriyalarni tekshirish (Aynan shu operator va kompaniya ichida oraliq tekshiruvi)
    cur = await db.execute("""
        SELECT serial_number FROM sim_cards 
        WHERE operator_type = ? AND serial_number >= ? AND serial_number <= ? AND company_id = ? 
        LIMIT 1
    """, (op_type, start_str, end_str, comp_id))
    existing = await cur.fetchone()
    if existing:
        raise HTTPException(status_code=400, detail=f"{op_type} operatori bo'yicha sim-karta seriyasi bazada allaqachon mavjud: {existing['serial_number']}")

    # 5. Ommaviy saqlash (Batch insert)
    records = [(comp_id, serial, op_type, payload.employee_id, current_user["id"], "GIVEN") for serial in serials_to_insert]
    try:
        await db.executemany("""
            INSERT INTO sim_cards (company_id, serial_number, operator_type, employee_id, distributed_by_id, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, records)

        # Partiya tarixini saqlash (1 ta qator: dan - gacha)
        await db.execute("""
            INSERT INTO sim_distributions (company_id, operator_type, start_serial, end_serial, total_count, employee_id, distributed_by_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'GIVEN')
        """, (comp_id, op_type, start_str, end_str, total_count, payload.employee_id, current_user["id"]))

        # Audit log yozish
        audit_details = (
            f"Tarqatildi: {total_count} dona {op_type} ({start_str} -> {end_str}). "
            f"Qabul qiluvchi: {employee['full_name']} (ID: {payload.employee_id})"
        )
        await db.execute("""
            INSERT INTO audit_logs (company_id, entity_type, entity_id, action, actor_name, details)
            VALUES (?, 'sim_cards', ?, 'DISTRIBUTE', ?, ?)
        """, (comp_id, payload.employee_id, current_user["full_name"], audit_details))

        await db.commit()

        # Xodimning Telegramiga xabar jo'natish
        if employee["telegram_id"]:
            import asyncio
            from app.bot import send_sim_distribution_to_telegram
            from app.security import get_tashkent_now
            asyncio.create_task(send_sim_distribution_to_telegram(
                employee_tg_id=employee["telegram_id"],
                sim_data={
                    "operator_type": op_type,
                    "count": total_count,
                    "start_serial": start_str,
                    "end_serial": end_str,
                    "distributor_name": current_user["full_name"],
                    "date_time": get_tashkent_now().strftime("%d.%m.%Y %H:%M")
                }
            ))
    except Exception as e:
        await db.rollback()
        err_msg = str(e)
        if "unique" in err_msg.lower() or "duplicate" in err_msg.lower() or "integrity" in err_msg.lower():
            raise HTTPException(status_code=400, detail="Kiritilgan diapazonda takrorlanuvchi sim-karta seriyalari mavjud.")
        import logging
        logging.getLogger("sim_cards").error(f"Sim-karta tarqatishda kutilmagan xatolik: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Sim-karta tarqatishda xatolik yuz berdi: {err_msg}")

    res_data = {
        "success": True,
        "message": f"{total_count} dona {op_type} sim-kartasi {employee['full_name']} ga muvaffaqiyatli biriktirildi.",
        "data": {
            "operator_type": op_type,
            "count": total_count,
            "start_serial": start_str,
            "end_serial": end_str,
            "employee_id": payload.employee_id,
            "employee_name": employee["full_name"]
        }
    }
    await record_idempotency_result(payload.idempotency_key, current_user["id"], res_data, action="SIM_DISTRIBUTE")
    return res_data

@router.get("/search")
async def search_sim_card(
    serial: str = Query(..., description="Qidirilayotgan seriya raqami yoki uning qismi"),
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Rahbar uchun: 18 xonali sim-karta seriyasini yozib qidirganda
    sim-karta turi (operatori), qaysi xodimga, qachon va kim tomonidan berilganligini ko'rsatish.
    """
    if current_user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Sim-karta qidiruvi faqat Bosh Rahbar uchun ochiq.")

    clean_serial = serial.strip().replace(" ", "")
    if len(clean_serial) < 3:
        raise HTTPException(status_code=400, detail="Qidirish uchun kamida 3 ta belgi kiriting.")

    comp_id = current_user.get("company_id") or 1

    cursor = await db.execute("""
        SELECT 
            s.id,
            s.serial_number,
            s.operator_type,
            s.status,
            s.distributed_at,
            s.sold_at,
            u.id as employee_id,
            u.full_name as employee_name,
            u.telegram_id as employee_tg,
            d.full_name as distributor_name,
            d.role as distributor_role
        FROM sim_cards s
        JOIN users u ON s.employee_id = u.id
        JOIN users d ON s.distributed_by_id = d.id
        WHERE s.serial_number LIKE ? AND s.company_id = ?
        ORDER BY s.id DESC
        LIMIT 50
    """, (f"%{clean_serial}%", comp_id))
    rows = await cursor.fetchall()

    results = []
    for r in rows:
        status_label = "Xodimda (Sotilmagan)" if r["status"] == "GIVEN" else "Sotilgan ✅"
        distributor_role_label = "Bosh Rahbar" if r["distributor_role"] == "ADMIN" else "Kassir"
        results.append({
            "id": r["id"],
            "serial_number": r["serial_number"],
            "operator_type": r["operator_type"] or "Uzmobile",
            "status": r["status"],
            "status_label": status_label,
            "distributed_at": r["distributed_at"],
            "sold_at": r["sold_at"],
            "employee_id": r["employee_id"],
            "employee_name": r["employee_name"],
            "employee_tg": r["employee_tg"],
            "distributor_name": f"{r['distributor_name']} ({distributor_role_label})"
        })

    return {
        "success": True,
        "query": clean_serial,
        "count": len(results),
        "data": results
    }

@router.get("/summary")
async def get_sim_cards_summary(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Xodimlar bo'yicha sim-kartalar taqsimoti va oxirgi tarqatilgan partiyalar.
    """
    if current_user["role"] not in ["ADMIN", "CASHIER"]:
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan.")

    comp_id = current_user.get("company_id") or 1
    inventory = await get_sim_inventory_summary(db, comp_id)
    return {
        "success": True,
        "balances": inventory["balances"],
        "recent": inventory["recent"]
    }
