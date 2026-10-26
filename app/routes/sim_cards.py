from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
import aiosqlite

from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/sim-cards", tags=["Sim Cards"])

@router.get("/employees")
async def get_sim_employees(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Sim-karta tarqatish uchun faol xodimlar ro'yxati"""
    if current_user["role"] not in ["ADMIN", "CASHIER"]:
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan.")
    cursor = await db.execute("""
        SELECT id, telegram_id, full_name, role 
        FROM users 
        WHERE is_active = 1 AND role != 'ADMIN'
        ORDER BY full_name ASC
    """)
    rows = await cursor.fetchall()
    return {"success": True, "data": [dict(r) for r in rows]}

VALID_OPERATORS = ["Uzmobile", "Beeline", "Ucell", "Mobiuz", "Perfectum"]

class SimDistributeRequest(BaseModel):
    operator_type: str = Field("Uzmobile", description="Sim-karta turi: Uzmobile, Beeline, Ucell, Mobiuz, Perfectum")
    start_serial: str = Field(..., description="18 xonali boshlang'ich seriya raqami")
    end_serial: Optional[str] = Field(None, description="18 xonali tugash seriya raqami")
    employee_id: int = Field(..., description="Qabul qiluvchi xodim ID si")

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

    op_type = payload.operator_type.strip()
    if op_type not in VALID_OPERATORS:
        raise HTTPException(status_code=400, detail=f"Noto'g'ri operator turi! Faqat {', '.join(VALID_OPERATORS)} tanlanishi mumkin.")

    start_str = payload.start_serial.strip().replace(" ", "")
    end_str = (payload.end_serial.strip().replace(" ", "") if payload.end_serial else start_str)

    # 1. Format va uzunlik tekshiruvi (faqat 18 ta raqam)
    if not (start_str.isdigit() and len(start_str) == 18):
        raise HTTPException(status_code=400, detail="Boshlang'ich seriya raqami aynan 18 ta raqamdan iborat bo'lishi shart.")
    if not (end_str.isdigit() and len(end_str) == 18):
        raise HTTPException(status_code=400, detail="Tugash seriya raqami aynan 18 ta raqamdan iborat bo'lishi shart.")

    start_num = int(start_str)
    end_num = int(end_str)

    if start_num > end_num:
        raise HTTPException(status_code=400, detail="Boshlang'ich seriya raqami tugash seriya raqamidan katta bo'lishi mumkin emas.")

    total_count = end_num - start_num + 1
    if total_count > 1000:
        raise HTTPException(status_code=400, detail="Bitta amaliyotda ko'pi bilan 1000 ta sim-karta tarqatish mumkin.")

    # 2. Xodimni tekshirish
    cursor = await db.execute("SELECT id, full_name, telegram_id, role, is_active FROM users WHERE id = ?", (payload.employee_id,))
    employee = await cursor.fetchone()
    if not employee:
        raise HTTPException(status_code=404, detail="Tanlangan xodim topilmadi.")
    if employee["role"] == "ADMIN":
        raise HTTPException(status_code=400, detail="Rahbar xodim bo'la olmaydi va unga sim-karta biriktirib bo'lmaydi!")
    if not employee["is_active"]:
        raise HTTPException(status_code=400, detail="Faolsizlantirilgan xodimga sim-karta berib bo'lmaydi.")

    # 3. Seriya raqamlari ro'yxatini shakllantirish
    serials_to_insert = [str(n).zfill(18) for n in range(start_num, end_num + 1)]

    # 4. Oldin kiritilgan seriyalarni tekshirish
    placeholders = ",".join("?" for _ in serials_to_insert[:50])
    cur = await db.execute(f"SELECT serial_number FROM sim_cards WHERE serial_number IN ({placeholders}) LIMIT 1", serials_to_insert[:50])
    existing = await cur.fetchone()
    if existing:
        raise HTTPException(status_code=400, detail=f"Sim-karta seriyasi bazada allaqachon mavjud: {existing['serial_number']}")

    # 5. Ommaviy saqlash (Batch insert)
    records = [(serial, op_type, payload.employee_id, current_user["id"], "GIVEN") for serial in serials_to_insert]
    try:
        await db.executemany("""
            INSERT INTO sim_cards (serial_number, operator_type, employee_id, distributed_by_id, status)
            VALUES (?, ?, ?, ?, ?)
        """, records)

        # Partiya tarixini saqlash (1 ta qator: dan - gacha)
        await db.execute("""
            INSERT INTO sim_distributions (operator_type, start_serial, end_serial, total_count, employee_id, distributed_by_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'GIVEN')
        """, (op_type, start_str, end_str, total_count, payload.employee_id, current_user["id"]))

        # Audit log yozish
        audit_details = (
            f"Tarqatildi: {total_count} dona {op_type} ({start_str} -> {end_str}). "
            f"Qabul qiluvchi: {employee['full_name']} (ID: {payload.employee_id})"
        )
        await db.execute("""
            INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
            VALUES ('sim_cards', ?, 'DISTRIBUTE', ?, ?)
        """, (payload.employee_id, current_user["full_name"], audit_details))

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
    except aiosqlite.IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Kiritilgan diapazonda takrorlanuvchi sim-karta seriyalari mavjud.")

    return {
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
        WHERE s.serial_number LIKE ?
        ORDER BY s.id DESC
        LIMIT 50
    """, (f"%{clean_serial}%",))
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

    # Xodimlar bo'yicha qoldiq va sotilganlar (tasdiqlangan hisobotlar va sim-kartalar bo'yicha)
    cur = await db.execute("""
        SELECT 
            u.id, 
            u.full_name, 
            COALESCE(sim.total_given, 0) as total_given,
            MAX(COALESCE(rep.total_sold, 0), COALESCE(sim.sold_sims, 0)) as sold_count,
            MAX(0, COALESCE(sim.total_given, 0) - MAX(COALESCE(rep.total_sold, 0), COALESCE(sim.sold_sims, 0))) as in_stock
        FROM users u
        LEFT JOIN (
            SELECT 
                employee_id, 
                COUNT(id) as total_given,
                SUM(CASE WHEN status = 'SOLD' THEN 1 ELSE 0 END) as sold_sims
            FROM sim_cards
            GROUP BY employee_id
        ) sim ON u.id = sim.employee_id
        LEFT JOIN (
            SELECT employee_id, SUM(sim_cards_count) as total_sold
            FROM daily_reports
            WHERE status = 'APPROVED'
            GROUP BY employee_id
        ) rep ON u.id = rep.employee_id
        WHERE u.role != 'ADMIN' AND u.is_active = 1
        ORDER BY in_stock DESC, u.full_name ASC
    """)
    balances = [dict(row) for row in await cur.fetchall()]

    # Oxirgi tarqatilgan partiyalar (dan - gacha)
    cur2 = await db.execute("""
        SELECT 
            d.id,
            d.operator_type,
            d.start_serial,
            d.end_serial,
            d.total_count,
            d.status,
            d.created_at as distributed_at,
            u.full_name as employee_name,
            b.full_name as distributor_name
        FROM sim_distributions d
        JOIN users u ON d.employee_id = u.id
        JOIN users b ON d.distributed_by_id = b.id
        ORDER BY d.id DESC
        LIMIT 20
    """)
    recent = [dict(row) for row in await cur2.fetchall()]

    # Zaxira (fallback): Agar sim_distributions bo'sh bo'lsa, sim_cards dan partiya qilib olish
    if not recent:
        cur_fallback = await db.execute("""
            SELECT 
                MAX(s.id) as id,
                s.operator_type,
                MIN(s.serial_number) as start_serial,
                MAX(s.serial_number) as end_serial,
                COUNT(s.id) as total_count,
                s.status,
                s.distributed_at,
                u.full_name as employee_name,
                d.full_name as distributor_name
            FROM sim_cards s
            JOIN users u ON s.employee_id = u.id
            JOIN users d ON s.distributed_by_id = d.id
            GROUP BY s.operator_type, s.employee_id, s.distributed_by_id, s.distributed_at
            ORDER BY id DESC
            LIMIT 20
        """)
        recent = [dict(row) for row in await cur_fallback.fetchall()]

    return {
        "success": True,
        "balances": balances,
        "recent": recent
    }
