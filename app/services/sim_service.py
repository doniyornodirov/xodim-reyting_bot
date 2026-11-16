"""
app.services.sim_service — Sim-kartalar Hisobi va Partiyalarni Boshqarish Servisi
Seriya raqamlarini oraliq bo'yicha shakllantirish, tekshirish va xodimlar balansini hisoblash.
"""

from typing import List, Dict, Any, Tuple
import aiosqlite

VALID_OPERATORS = ["Uzmobile", "Beeline", "Ucell", "Mobiuz", "Perfectum"]

def validate_serial_range(start_serial: str, end_serial: str) -> Tuple[int, int, int]:
    """
    18 xonali boshlang'ich va tugash seriyalarini tekshirish.
    Qaytadi: (start_num, end_num, total_count)
    """
    s_clean = start_serial.strip().replace(" ", "")
    e_clean = (end_serial.strip().replace(" ", "") if end_serial else s_clean)

    if not (s_clean.isdigit() and len(s_clean) == 18):
        raise ValueError("Boshlang'ich seriya raqami aynan 18 ta raqamdan iborat bo'lishi shart.")
    if not (e_clean.isdigit() and len(e_clean) == 18):
        raise ValueError("Tugash seriya raqami aynan 18 ta raqamdan iborat bo'lishi shart.")

    start_num = int(s_clean)
    end_num = int(e_clean)

    if start_num > end_num:
        raise ValueError("Boshlang'ich seriya raqami tugash seriya raqamidan katta bo'lishi mumkin emas.")

    total_count = end_num - start_num + 1
    if total_count > 1000:
        raise ValueError("Bitta amaliyotda ko'pi bilan 1000 ta sim-karta tarqatish mumkin.")

    return start_num, end_num, total_count

async def get_sim_inventory_summary(
    db: aiosqlite.Connection,
    company_id: int
) -> Dict[str, Any]:
    """
    Xodimlar bo'yicha sim-kartalar qoldig'i (in_stock) va
    oxirgi tarqatilgan partiyalar ro'yxatini hisoblash.
    """
    # 1. Xodimlar balansi
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
            WHERE company_id = ?
            GROUP BY employee_id
        ) sim ON u.id = sim.employee_id
        LEFT JOIN (
            SELECT employee_id, SUM(sim_cards_count) as total_sold
            FROM daily_reports
            WHERE status = 'APPROVED' AND company_id = ?
            GROUP BY employee_id
        ) rep ON u.id = rep.employee_id
        WHERE u.role NOT IN ('ADMIN', 'DEVELOPER') AND u.is_active = 1 AND u.company_id = ?
        ORDER BY in_stock DESC, u.full_name ASC
    """, (company_id, company_id, company_id))
    balances = [dict(row) for row in await cur.fetchall()]

    # 2. Oxirgi tarqatilgan partiyalar
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
        WHERE d.company_id = ?
        ORDER BY d.id DESC
        LIMIT 20
    """, (company_id,))
    recent = [dict(row) for row in await cur2.fetchall()]

    # Zaxira (fallback): Agar sim_distributions bo'sh bo'lsa
    if not recent:
        cur_fallback = await db.execute("""
            SELECT 
                MAX(s.id) as id,
                s.operator_type,
                MIN(s.serial_number) as start_serial,
                MAX(s.serial_number) as end_serial,
                COUNT(s.id) as total_count,
                MAX(s.status) as status,
                s.distributed_at,
                u.full_name as employee_name,
                d.full_name as distributor_name
            FROM sim_cards s
            JOIN users u ON s.employee_id = u.id
            JOIN users d ON s.distributed_by_id = d.id
            WHERE s.company_id = ?
            GROUP BY s.operator_type, s.employee_id, s.distributed_by_id, s.distributed_at, u.full_name, d.full_name
            ORDER BY id DESC
            LIMIT 20
        """, (company_id,))
        recent = [dict(row) for row in await cur_fallback.fetchall()]

    return {
        "balances": balances,
        "recent": recent
    }
