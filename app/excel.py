import io
import datetime
from typing import List, Dict, Any, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def format_date_str(date_str: Optional[str]) -> str:
    """YYYY-MM-DD formatini DD.MM.YYYY ga o'tkazish"""
    if not date_str:
        return "-"
    try:
        parts = str(date_str).strip().split("-")
        if len(parts) == 3:
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
    except Exception:
        pass
    return str(date_str)

def generate_reports_excel(
    company_name: str,
    reports: List[Dict[str, Any]],
    date_display: str
) -> bytes:
    """
    Kompaniyaning kunlik hisobotlarini chiroyli va professional Excel (.xlsx) fayliga aylantirish
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Kunlik Hisobotlar"

    # Grid chiziqlarini ko'rsatish
    ws.views.sheetView[0].showGridLines = True

    # Ranglar va Uslublar
    TITLE_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    SUBTITLE_FILL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    HEADER_FILL = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    TOTAL_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    ZEBRA_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    FONT_TITLE = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    FONT_SUBTITLE = Font(name="Calibri", size=10, italic=True, color="475569")
    FONT_HEADER = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    FONT_DATA = Font(name="Calibri", size=10, color="0F172A")
    FONT_TOTAL = Font(name="Calibri", size=11, bold=True, color="92400E")

    FONT_STATUS_APPROVED = Font(name="Calibri", size=10, bold=True, color="16A34A")
    FONT_STATUS_REJECTED = Font(name="Calibri", size=10, bold=True, color="DC2626")
    FONT_STATUS_PENDING = Font(name="Calibri", size=10, bold=True, color="D97706")

    BORDER_THIN = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )
    BORDER_TOTAL = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="94A3B8"),
        bottom=Side(style="double", color="0F172A"),
    )

    ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
    ALIGN_LEFT = Alignment(horizontal="left", vertical="center")
    ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")

    CURRENCY_FORMAT = '#,##0'

    # Sarlavha: Kompaniya nomi
    ws.merge_cells("A1:R1")
    title_cell = ws["A1"]
    title_cell.value = f"🏢 {company_name.upper()} — KUNLIK HISOBOTLAR JADVALI"
    title_cell.font = FONT_TITLE
    title_cell.fill = TITLE_FILL
    title_cell.alignment = ALIGN_CENTER
    ws.row_dimensions[1].height = 36

    # Quyi sarlavha: Sana va ma'lumot
    ws.merge_cells("A2:R2")
    sub_cell = ws["A2"]
    from app.security import get_tashkent_now
    now_str = get_tashkent_now().strftime("%d.%m.%Y %H:%M")
    sub_cell.value = f"📅 Sana / Davr: {date_display}  |  📊 Jami hisobotlar soni: {len(reports)} ta  |  ⏰ Eksport vaqti: {now_str}"
    sub_cell.font = FONT_SUBTITLE
    sub_cell.fill = SUBTITLE_FILL
    sub_cell.alignment = ALIGN_CENTER
    ws.row_dimensions[2].height = 22

    # Bo'sh qator
    ws.row_dimensions[3].height = 10

    # Ustun sarlavhalari (Row 4)
    headers = [
        ("№", ALIGN_CENTER),
        ("Sana", ALIGN_CENTER),
        ("Xodim F.I.SH", ALIGN_LEFT),
        ("Paynet (so'm)", ALIGN_RIGHT),
        ("Karta (+3%)", ALIGN_RIGHT),
        ("Leviy (so'm)", ALIGN_RIGHT),
        ("Qarz to'lovi", ALIGN_RIGHT),
        ("Jami Kirim", ALIGN_RIGHT),
        ("Kunlik (so'm)", ALIGN_RIGHT),
        ("Terminal", ALIGN_RIGHT),
        ("Olingan summa", ALIGN_RIGHT),
        ("Skidka (so'm)", ALIGN_RIGHT),
        ("Xarajat (so'm)", ALIGN_RIGHT),
        ("Jami Chiqim", ALIGN_RIGHT),
        ("Sof Kassa (Net)", ALIGN_RIGHT),
        ("Sim-karta (dona)", ALIGN_CENTER),
        ("Holati", ALIGN_CENTER),
        ("Izoh", ALIGN_LEFT)
    ]

    ws.row_dimensions[4].height = 28
    for col_idx, (h_title, align) in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col_idx, value=h_title)
        cell.font = FONT_HEADER
        cell.fill = HEADER_FILL
        cell.alignment = align
        cell.border = BORDER_THIN

    # Ma'lumotlarni yozish (Row 5+)
    current_row = 5
    for idx, r in enumerate(reports, start=1):
        ws.row_dimensions[current_row].height = 20
        fill = ZEBRA_FILL if idx % 2 == 0 else PatternFill(fill_type=None)

        status_val = str(r.get("status", "PENDING")).upper()
        if status_val == "APPROVED":
            status_text = "Tasdiqlandi"
            status_font = FONT_STATUS_APPROVED
        elif status_val == "REJECTED":
            status_text = "Rad etildi"
            status_font = FONT_STATUS_REJECTED
        else:
            status_text = "Kutilmoqda"
            status_font = FONT_STATUS_PENDING

        row_values = [
            (idx, FONT_DATA, ALIGN_CENTER, None),
            (format_date_str(r.get("report_date")), FONT_DATA, ALIGN_CENTER, None),
            (r.get("employee_name") or r.get("full_name") or "-", FONT_DATA, ALIGN_LEFT, None),
            (r.get("paynet", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("card_amount", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("leviy", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("debt_paid", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("total_inflow", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("kunlik", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("terminal", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("given_amount", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("skidka", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("xarajat", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("total_outflow", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("net_amount", 0) or 0, FONT_DATA, ALIGN_RIGHT, CURRENCY_FORMAT),
            (r.get("sim_cards_count", 0) or 0, FONT_DATA, ALIGN_CENTER, CURRENCY_FORMAT),
            (status_text, status_font, ALIGN_CENTER, None),
            (r.get("comment", "") or "", FONT_DATA, ALIGN_LEFT, None)
        ]

        for col_idx, (val, font_style, align, num_fmt) in enumerate(row_values, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = font_style
            cell.alignment = align
            cell.border = BORDER_THIN
            if fill.fill_type:
                cell.fill = fill
            if num_fmt and isinstance(val, (int, float)):
                cell.number_format = num_fmt

        current_row += 1

    # Jami qatori (Total Row)
    if reports:
        ws.row_dimensions[current_row].height = 24
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=3)
        lbl_cell = ws.cell(row=current_row, column=1, value="JAMI (YIG'INDI):")
        lbl_cell.font = FONT_TOTAL
        lbl_cell.alignment = ALIGN_RIGHT
        lbl_cell.fill = TOTAL_FILL

        for c_idx in range(1, 4):
            ws.cell(row=current_row, column=c_idx).border = BORDER_TOTAL
            ws.cell(row=current_row, column=c_idx).fill = TOTAL_FILL

        # 4 dan 16-ustungacha formulalar (SUM)
        first_data_row = 5
        last_data_row = current_row - 1
        for c_idx in range(4, 17):
            col_letter = get_column_letter(c_idx)
            cell = ws.cell(row=current_row, column=c_idx)
            cell.value = f"=SUM({col_letter}{first_data_row}:{col_letter}{last_data_row})"
            cell.font = FONT_TOTAL
            cell.alignment = ALIGN_RIGHT if c_idx != 16 else ALIGN_CENTER
            cell.border = BORDER_TOTAL
            cell.fill = TOTAL_FILL
            cell.number_format = CURRENCY_FORMAT

        # Qolgan ustunlar (17 va 18)
        for c_idx in (17, 18):
            cell = ws.cell(row=current_row, column=c_idx, value="")
            cell.border = BORDER_TOTAL
            cell.fill = TOTAL_FILL

    # Ustun kengliklarini matnga qarab avtomatik moslash (Auto-fit width)
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            # 1 va 2-qatorlar merge qilingan, ularni hisobga olmaslik
            if cell.row in (1, 2, 3):
                continue
            if cell.value:
                # Agar formula bo'lsa taxminiy uzunlik
                val_str = str(cell.value)
                if val_str.startswith("="):
                    max_len = max(max_len, 14)
                else:
                    max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 11)

    # Birinchi bir nechta ustunlarga qulay minimal o'lcham
    ws.column_dimensions["A"].width = 7   # №
    ws.column_dimensions["B"].width = 13  # Sana
    ws.column_dimensions["C"].width = 24  # Xodim F.I.SH
    ws.column_dimensions["Q"].width = 15  # Holati
    ws.column_dimensions["R"].width = 28  # Izoh

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()

