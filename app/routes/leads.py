import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
import aiosqlite
from pydantic import BaseModel, Field

from app.config import DB_PATH, RAHBAR_ID
from app.models import CreateLeadRequest
from app.dependencies import get_current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/leads", tags=["Sotuv Lidlar"])

class UpdateLeadStatusRequest(BaseModel):
    status: str = Field(..., max_length=50)
    notes: Optional[str] = Field(None, max_length=500)

@router.post("")
async def create_lead(req: CreateLeadRequest):
    """
    Sotuv saytidan (xodimkpi.uz) yangi mijoz so'rovini qabul qilish.
    1. Ma'lumotlar bazasida saqlaydi.
    2. Bosh Rahbar (8686341550) Telegramiga bot orqali darhol xabarnoma yuboradi.
    """
    clean_name = req.name.strip()
    clean_phone = req.phone.strip()
    clean_tg = (req.telegram or "").strip()
    clean_plan = (req.plan or "").strip()
    clean_source = (req.source or "xodimkpi.uz").strip()

    if not clean_name:
        raise HTTPException(status_code=400, detail="Ismingizni kiriting")
    if len(clean_phone) < 7:
        raise HTTPException(status_code=400, detail="Telefon raqamingizni to'liq kiriting")

    lead_id = None
    created_at_str = datetime.now(timezone(timedelta(hours=5))).strftime("%Y-%m-%d %H:%M:%S")

    # 1. Bazaga yozish
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """
            INSERT INTO leads (name, phone, telegram, plan, source, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'YANGI', CURRENT_TIMESTAMP)
            """,
            (clean_name, clean_phone, clean_tg, clean_plan, clean_source)
        )
        await conn.commit()
        lead_id = cursor.lastrowid

    # 2. Bosh Rahbar Telegramiga xabar yuborish
    try:
        from app.bot import bot
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        target_chat_id = int(RAHBAR_ID) if RAHBAR_ID and RAHBAR_ID.isdigit() else 8686341550

        clean_tg_handle = clean_tg.lstrip("@").strip()
        tg_display = f"@{clean_tg_handle}" if clean_tg_handle else "<i>Kiritilmagan</i>"

        text = (
            f"🚀 <b>YANGI SOTUV LIDI (XodimKPI)!</b> 🎉\n\n"
            f"👤 <b>Mijoz:</b> {clean_name}\n"
            f"📞 <b>Telefon:</b> <code>{clean_phone}</code>\n"
            f"📱 <b>Telegram:</b> {tg_display}\n"
            f"📦 <b>Tanlangan tarif:</b> <b>{clean_plan or 'Aniqlanmagan'}</b>\n"
            f"🌐 <b>Manba:</b> {clean_source}\n"
            f"🕒 <b>Vaqt:</b> {created_at_str}\n\n"
            f"<i>Tez orada mijoz bilan bog'laning!</i>"
        )

        buttons = []
        if clean_tg_handle:
            buttons.append([InlineKeyboardButton(text="💬 Telegramda yozish", url=f"https://t.me/{clean_tg_handle}")])

        reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

        await bot.send_message(
            chat_id=target_chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logger.info(f"Lid haqida xabarnoma Bosh Rahbarga ({target_chat_id}) muvaffaqiyatli yuborildi.")
    except Exception as e:
        logger.warning(f"Telegram bot orqali Bosh Rahbarga lid yuborishda xatolik: {e}")

    return {
        "success": True,
        "message": "So'rovingiz qabul qilindi! Bosh rahbarimiz tez orada siz bilan bog'lanadi.",
        "lead_id": lead_id
    }

@router.get("")
async def list_leads(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    Lidlar ro'yxatini olish (Faqat ADMIN va DEVELOPER rollari uchun).
    """
    if current_user.get("role") not in ["ADMIN", "DEVELOPER"] and not current_user.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        query = "SELECT * FROM leads"
        params = []
        if status_filter:
            query += " WHERE status = ?"
            params.append(status_filter)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()

        count_query = "SELECT COUNT(*) FROM leads"
        count_params = []
        if status_filter:
            count_query += " WHERE status = ?"
            count_params.append(status_filter)

        count_cursor = await conn.execute(count_query, count_params)
        total = (await count_cursor.fetchone())[0]

        return {
            "success": True,
            "total": total,
            "leads": [dict(r) for r in rows]
        }

@router.patch("/{lead_id}/status")
async def update_lead_status(
    lead_id: int,
    req: UpdateLeadStatusRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Lid holatini yangilash (YANGI, BOG'LANILDI, SINOV_BERILDI, TO'LADI, RAD_ETILDI).
    """
    if current_user.get("role") not in ["ADMIN", "DEVELOPER"] and not current_user.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan")

    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "UPDATE leads SET status = ?, notes = COALESCE(?, notes) WHERE id = ?",
            (req.status, req.notes, lead_id)
        )
        await conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Lid topilmadi")

    return {"success": True, "message": "Holat yangilandi"}

