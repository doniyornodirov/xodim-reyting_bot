"""
app.services.analytics_service — Savdo Monitoringi va Analitika Servisi
Vaqt bo'yicha dinamika, o'sish foizlari, operatorlar taqsimoti va yuqori tezlikdagi kesh.
"""

import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import aiosqlite
from app.config import DB_PATH

logger = logging.getLogger("analytics_service")

# Tezkor in-memory kesh: {cache_key: (expire_timestamp, data)}
_ANALYTICS_CACHE: Dict[str, tuple[float, Dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 30 # 30 soniyalik aqlli kesh

def invalidate_analytics_cache(company_id: Optional[int] = None) -> None:
    """Yangi hisobot tasdiqlanganda yoki o'zgarganda keshni tozalash"""
    global _ANALYTICS_CACHE
    if company_id is None:
        _ANALYTICS_CACHE.clear()
    else:
        prefix = f"comp_{company_id}:"
        keys_to_del = [k for k in _ANALYTICS_CACHE if k.startswith(prefix)]
        for k in keys_to_del:
            _ANALYTICS_CACHE.pop(k, None)

async def get_sales_monitoring_data(
    company_id: int,
    period: str = "7d",
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Savdo monitoringi va grafik ma'lumotlarini hisoblash (keshlangan).
    """
    cache_key = f"comp_{company_id}:p_{period}:u_{user_id or 0}"
    now = time.time()

    if cache_key in _ANALYTICS_CACHE:
        expire_at, cached_data = _ANALYTICS_CACHE[cache_key]
        if now < expire_at:
            return cached_data

    now_tashkent = datetime.now(timezone.utc) + timedelta(hours=5)
    today = now_tashkent.date()

    if period in ("today", "1d"):
        days_count = 1
    elif period == "30d":
        days_count = 30
    elif period == "this_month":
        days_count = today.day
    elif period == "all":
        days_count = 90
    else: # "7d" default
        days_count = 7

    start_date = today - timedelta(days=days_count - 1)
    prev_end_date = start_date - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=days_count - 1)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")
    prev_start_str = prev_start_date.strftime("%Y-%m-%d")
    prev_end_str = prev_end_date.strftime("%Y-%m-%d")

    uzb_weekdays = {0: "Dush", 1: "Sesh", 2: "Chor", 3: "Pay", 4: "Juma", 5: "Shan", 6: "Yak"}
    uzb_months = {1: "Yan", 2: "Fev", 3: "Mar", 4: "Apr", 5: "May", 6: "Iyun", 7: "Iyul", 8: "Avg", 9: "Sen", 10: "Okt", 11: "Noy", 12: "Dek"}

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        emp_filter = " AND employee_id = ?" if user_id else ""
        emp_param = (user_id,) if user_id else ()

        # 1. Joriy davrdagi kunlik hisobotlar
        try:
            cur = await conn.execute(f"""
                SELECT report_date,
                       COALESCE(SUM(total_inflow), 0) as submitted_amount,
                       COALESCE(SUM(net_amount), 0) as net_amount,
                       COALESCE(SUM(paynet), 0) as paynet_amount,
                       COALESCE(SUM(sim_cards_count), 0) as sim_cards_sold,
                       COALESCE(SUM(sim_uzmobile), 0) as sim_uzmobile,
                       COALESCE(SUM(sim_beeline), 0) as sim_beeline,
                       COALESCE(SUM(sim_ucell), 0) as sim_ucell,
                       COALESCE(SUM(sim_mobiuz), 0) as sim_mobiuz,
                       COALESCE(SUM(sim_perfectum), 0) as sim_perfectum
                FROM daily_reports
                WHERE status = 'APPROVED' AND report_date >= ? AND report_date <= ? AND company_id = ? {emp_filter}
                GROUP BY report_date
            """, (start_str, end_str, company_id) + emp_param)
            rep_rows = await cur.fetchall()
        except Exception as e:
            logger.warning(f"Monitoring sim ustunlari bilan so'rovda ogohlantirish: {e}")
            cur = await conn.execute(f"""
                SELECT report_date,
                       COALESCE(SUM(total_inflow), 0) as submitted_amount,
                       COALESCE(SUM(net_amount), 0) as net_amount,
                       COALESCE(SUM(paynet), 0) as paynet_amount,
                       COALESCE(SUM(sim_cards_count), 0) as sim_cards_sold,
                       0 as sim_uzmobile, 0 as sim_beeline, 0 as sim_ucell, 0 as sim_mobiuz, 0 as sim_perfectum
                FROM daily_reports
                WHERE status = 'APPROVED' AND report_date >= ? AND report_date <= ? AND company_id = ? {emp_filter}
                GROUP BY report_date
            """, (start_str, end_str, company_id) + emp_param)
            rep_rows = await cur.fetchall()

        reports_by_date = {r["report_date"]: dict(r) for r in rep_rows}

        # 2. Joriy davrdagi karta to'ldirishlar
        cur = await conn.execute(f"""
            SELECT DATE(created_at, '+5 hours') as topup_date,
                   COALESCE(SUM(surcharge_amount), 0) as card_amount,
                   COUNT(*) as card_count
            FROM card_topups
            WHERE status = 'APPROVED' AND DATE(created_at, '+5 hours') >= ? AND DATE(created_at, '+5 hours') <= ? AND company_id = ? {emp_filter}
            GROUP BY DATE(created_at, '+5 hours')
        """, (start_str, end_str, company_id) + emp_param)
        topup_rows = await cur.fetchall()
        topups_by_date = {r["topup_date"]: dict(r) for r in topup_rows}

        # 3. Oldingi davr yig'indilari
        cur = await conn.execute(f"""
            SELECT COALESCE(SUM(total_inflow), 0) as prev_submitted,
                   COALESCE(SUM(net_amount), 0) as prev_net,
                   COALESCE(SUM(paynet), 0) as prev_paynet,
                   COALESCE(SUM(sim_cards_count), 0) as prev_sims
            FROM daily_reports
            WHERE status = 'APPROVED' AND report_date >= ? AND report_date <= ? AND company_id = ? {emp_filter}
        """, (prev_start_str, prev_end_str, company_id) + emp_param)
        prev_rep = await cur.fetchone()
        prev_submitted = prev_rep["prev_submitted"] if prev_rep else 0
        prev_net = prev_rep["prev_net"] if prev_rep else 0
        prev_paynet = prev_rep["prev_paynet"] if prev_rep else 0
        prev_sims = prev_rep["prev_sims"] if prev_rep else 0

        cur = await conn.execute(f"""
            SELECT COALESCE(SUM(surcharge_amount), 0) as prev_cards,
                   COUNT(*) as prev_card_count
            FROM card_topups
            WHERE status = 'APPROVED' AND DATE(created_at, '+5 hours') >= ? AND DATE(created_at, '+5 hours') <= ? AND company_id = ? {emp_filter}
        """, (prev_start_str, prev_end_str, company_id) + emp_param)
        prev_top = await cur.fetchone()
        prev_cards = prev_top["prev_cards"] if prev_top else 0

        # 4. Operatorlar taqsimoti
        try:
            cur = await conn.execute(f"""
                SELECT 
                    COALESCE(SUM(sim_uzmobile), 0) as uzmobile,
                    COALESCE(SUM(sim_beeline), 0) as beeline,
                    COALESCE(SUM(sim_ucell), 0) as ucell,
                    COALESCE(SUM(sim_mobiuz), 0) as mobiuz,
                    COALESCE(SUM(sim_perfectum), 0) as perfectum
                FROM daily_reports
                WHERE status = 'APPROVED' AND report_date >= ? AND report_date <= ? AND company_id = ? {emp_filter}
            """, (start_str, end_str, company_id) + emp_param)
            op_sum = await cur.fetchone()

            op_counts = {
                "Uzmobile": int(op_sum["uzmobile"] or 0) if op_sum else 0,
                "Beeline": int(op_sum["beeline"] or 0) if op_sum else 0,
                "Ucell": int(op_sum["ucell"] or 0) if op_sum else 0,
                "Mobiuz": int(op_sum["mobiuz"] or 0) if op_sum else 0,
                "Perfectum": int(op_sum["perfectum"] or 0) if op_sum else 0
            }
        except Exception:
            op_counts = {"Uzmobile": 0, "Beeline": 0, "Ucell": 0, "Mobiuz": 0, "Perfectum": 0}

        # 5. Faol xodimlar ro'yxati
        cur = await conn.execute("""
            SELECT id, full_name, role 
            FROM users 
            WHERE is_active = 1 AND role NOT IN ('ADMIN', 'DEVELOPER') AND company_id = ?
            ORDER BY full_name ASC
        """, (company_id,))
        emp_rows = await cur.fetchall()
        employees = [{"id": r["id"], "full_name": r["full_name"], "role": r["role"]} for r in emp_rows]

        operator_icons = {
            "Uzmobile": "/static/icons/operators/uzmobile.png",
            "Beeline": "/static/icons/operators/beeline.png",
            "Ucell": "/static/icons/operators/ucell.png",
            "Mobiuz": "/static/icons/operators/mobiuz.png?v=874",
            "Perfectum": "/static/icons/operators/perfectum.png"
        }

    # Timeline qurish
    timeline = []
    total_submitted = 0.0
    total_net = 0.0
    total_paynet = 0.0
    total_sims = 0
    total_cards = 0.0
    total_card_count = 0
    prev_day_sub = float(prev_submitted) if days_count == 1 else None

    for i in range(days_count):
        curr_d = start_date + timedelta(days=i)
        curr_d_str = curr_d.strftime("%Y-%m-%d")
        label = f"{curr_d.day}-{uzb_months.get(curr_d.month, '')}"
        w_name = uzb_weekdays.get(curr_d.weekday(), "")

        rep_info = reports_by_date.get(curr_d_str, {})
        top_info = topups_by_date.get(curr_d_str, {})

        has_report = curr_d_str in reports_by_date
        c_amt = float(top_info.get("card_amount", 0.0))
        c_cnt = int(top_info.get("card_count", 0))

        if has_report:
            sub_amt = float(rep_info.get("submitted_amount", 0.0))
            net_amt = float(rep_info.get("net_amount", 0.0))
            paynet_amt = float(rep_info.get("paynet_amount", 0.0))
        else:
            # Bugun (yoki hisobot topshirilmagan kunda) tasdiqlangan karta to'ldirishlar
            # avtomatik hisoblanganligi uchun jonli ravishda Yalpi tushumda ko'rsatiladi.
            # Keyinchalik hisobot tasdiqlanganda hisobot ichidagi umumiy summa olinadi va 2 marta qo'shilmaydi.
            sub_amt = c_amt
            net_amt = c_amt
            paynet_amt = 0.0

        sims_cnt = int(rep_info.get("sim_cards_sold", 0))

        u_cnt = int(rep_info.get("sim_uzmobile", 0))
        b_cnt = int(rep_info.get("sim_beeline", 0))
        uc_cnt = int(rep_info.get("sim_ucell", 0))
        m_cnt = int(rep_info.get("sim_mobiuz", 0))
        p_cnt = int(rep_info.get("sim_perfectum", 0))
        day_op_sum = u_cnt + b_cnt + uc_cnt + m_cnt + p_cnt
        if sims_cnt > day_op_sum:
            # Agar eski hisobotda operatorlar bo'linmagan bo'lsa, qolganini Uzmobile ga qo'shish
            u_cnt += (sims_cnt - day_op_sum)
        elif day_op_sum > sims_cnt:
            sims_cnt = day_op_sum

        total_submitted += sub_amt
        total_net += net_amt
        total_paynet += paynet_amt
        total_sims += sims_cnt
        total_cards += c_amt
        total_card_count += c_cnt

        if prev_day_sub is not None and prev_day_sub > 0:
            day_change = round(((sub_amt - prev_day_sub) / prev_day_sub) * 100, 1)
        elif prev_day_sub is not None and sub_amt > 0:
            day_change = 100.0
        else:
            day_change = 0.0

        prev_day_sub = sub_amt

        timeline.append({
            "date": curr_d_str,
            "short_date": label,
            "weekday": w_name,
            "submitted_amount": sub_amt,
            "paynet_amount": paynet_amt,
            "net_amount": net_amt,
            "sim_cards_sold": sims_cnt,
            "sim_uzmobile": u_cnt,
            "sim_beeline": b_cnt,
            "sim_ucell": uc_cnt,
            "sim_mobiuz": m_cnt,
            "sim_perfectum": p_cnt,
            "card_topup_amount": c_amt,
            "card_topup_count": c_cnt,
            "day_change_pct": day_change
        })

    # Operatorlar taqsimoti va umumiy sim-kartalar sonining 100% mutanosibligini kafolatlash (Zero Discrepancy)
    if total_sims == 0:
        op_counts = {k: 0 for k in op_counts}
    else:
        op_total = sum(op_counts.values())
        if total_sims > op_total:
            op_counts["Uzmobile"] += (total_sims - op_total)
        elif op_total > total_sims:
            total_sims = op_total

    operators = [
        {
            "operator_type": name,
            "count": op_counts[name],
            "logo": operator_icons.get(name, "")
        }
        for name in ["Uzmobile", "Beeline", "Ucell", "Mobiuz", "Perfectum"]
    ]

    def calc_pct(cur_val, prev_val):
        if prev_val > 0:
            return round(((cur_val - prev_val) / prev_val) * 100, 1)
        elif cur_val > 0:
            return 100.0
        return 0.0

    summary = {
        "total_submitted_amount": total_submitted,
        "submitted_growth_pct": calc_pct(total_submitted, prev_submitted),
        "total_paynet_amount": total_paynet,
        "paynet_growth_pct": calc_pct(total_paynet, prev_paynet),
        "total_net_amount": total_net,
        "net_growth_pct": calc_pct(total_net, prev_net),
        "total_sim_cards": total_sims,
        "sim_growth_pct": calc_pct(total_sims, prev_sims),
        "total_card_topup_amount": total_cards,
        "card_growth_pct": calc_pct(total_cards, prev_cards),
        "total_card_topup_count": total_card_count,
        "avg_daily_submitted": round(total_submitted / max(1, days_count)),
        "period": period,
        "days_count": days_count,
        "start_date": start_str,
        "end_date": end_str
    }

    result = {
        "summary": summary,
        "timeline": timeline,
        "operators": operators,
        "employees": employees,
        "selected_user_id": user_id
    }

    # Keshga saqlash
    _ANALYTICS_CACHE[cache_key] = (now + CACHE_TTL_SECONDS, result)
    return result
