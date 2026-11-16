import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Union, Dict, Any

Number = Union[int, float, str, Decimal]

def to_decimal(val: Number) -> Decimal:
    """Ixtiyoriy sonni xavfsiz va aniq Decimal formatiga o'tkazish"""
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    try:
        # float ni string orqali o'tkazish suzuvchi nuqta xatolarini oldini oladi
        return Decimal(str(val))
    except Exception:
        return Decimal("0")

def round_uzs(val: Number) -> int:
    """So'mni butun songa yaxlitlash (moliyaviy standart)"""
    d = to_decimal(val)
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def calculate_card_surcharge(base_amount: Number) -> int:
    """
    Karta to'ldirish uchun 3% ustama hisoblash.
    Qoida: (summa * 1.03) hisoblanib, eng yaqin yuqori 1000 so'mga yaxlitlanadi (math.ceil).
    Masalan: 50 000 * 1.03 = 51 500 -> 52 000 so'm
    """
    amt = to_decimal(base_amount)
    if amt <= 0:
        return 0
    raw_surcharge = float(amt) * 1.03
    return int(math.ceil(raw_surcharge / 1000.0) * 1000)

def calculate_daily_report_totals(
    paynet: Number = 0,
    card_amount: Number = 0,
    leviy: Number = 0,
    debt_paid: Number = 0,
    kunlik: Number = 0,
    terminal: Number = 0,
    given_amount: Number = 0,
    skidka: Number = 0,
    xarajat: Number = 0
) -> Dict[str, int]:
    """
    Kunlik hisobot bo'yicha jami kirim, chiqim va sof topshiriladigan summani
    Decimal aniqligida 0 tiyin xatosiz hisoblash.
    
    Kirim (Inflow) = paynet + card_amount + leviy + debt_paid + kunlik
    Chiqim (Outflow) = terminal + given_amount + skidka + xarajat
    Sof Kassa (Net) = Kirim - Chiqim
    """
    d_paynet = to_decimal(paynet)
    d_card = to_decimal(card_amount)
    d_leviy = to_decimal(leviy)
    d_debt_paid = to_decimal(debt_paid)
    d_kunlik = to_decimal(kunlik)

    d_terminal = to_decimal(terminal)
    d_given = to_decimal(given_amount)
    d_skidka = to_decimal(skidka)
    d_xarajat = to_decimal(xarajat)

    total_inflow = d_paynet + d_card + d_leviy + d_debt_paid + d_kunlik
    total_outflow = d_terminal + d_given + d_skidka + d_xarajat
    net_amount = total_inflow - total_outflow

    return {
        "total_inflow": round_uzs(total_inflow),
        "total_outflow": round_uzs(total_outflow),
        "net_amount": round_uzs(net_amount)
    }

def calculate_cashier_diff(
    system_expected_net: Number,
    cashier_received_uzs: Number,
    cashier_received_usd: Number = 0,
    usd_rate: Number = 0
) -> Dict[str, Any]:
    """
    Kassa taqqoslash: Tizim hisoblagan summa bilan kassir qabul qilgan summa
    o'rtasidagi tafovutni hisoblash.
    """
    d_expected = to_decimal(system_expected_net)
    d_uzs = to_decimal(cashier_received_uzs)
    d_usd = to_decimal(cashier_received_usd)
    d_rate = to_decimal(usd_rate)

    usd_in_uzs = d_usd * d_rate
    total_received = d_uzs + usd_in_uzs
    difference = total_received - d_expected

    return {
        "expected_amount": round_uzs(d_expected),
        "total_received": round_uzs(total_received),
        "difference": round_uzs(difference),
        "has_diff": round_uzs(difference) != 0,
        "is_shortage": round_uzs(difference) < 0, # Kamomad
        "is_surplus": round_uzs(difference) > 0   # Ortiqcha
    }
