import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.config import BOT_TOKEN, TELEGRAM_GROUP_ID
import aiosqlite
from app.config import DB_PATH

logger = logging.getLogger("telegram_bot")

from aiohttp.resolver import DefaultResolver
from aiohttp import ClientSession
from aiogram.client.session.aiohttp import AiohttpSession

bot: Bot | None = None
dp: Dispatcher | None = None

if BOT_TOKEN:
    try:
        bot = Bot(token=BOT_TOKEN)
        dp = Dispatcher()
    except Exception as e:
        logger.error(f"Telegram bot yaratishda xatolik: {e}")

def get_topup_keyboard(topup_id: int, current_status: str) -> InlineKeyboardMarkup | None:
    """Statusga qarab o'zgaruvchi inline tugmalar (Rad etilganda tugmalar ko'rinmaydi)"""
    if current_status == "REJECTED":
        return None  # Rad etilgan so'rov uchun tugmalar butunlay yo'q qilinadi
    elif current_status == "APPROVED":
        buttons = [
            [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"topup_reject_{topup_id}")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    else:  # PENDING
        buttons = [
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"topup_approve_{topup_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"topup_reject_{topup_id}")
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

async def check_is_group_admin(chat_id: int, user_id: int) -> bool:
    """Foydalanuvchi guruh admini ekanligini tekshirish"""
    if not bot:
        return True
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ["creator", "administrator"]
    except Exception as e:
        logger.warning(f"Adminlik tekshirishda xatolik: {e}")
        return False

# Telegram bot komandalarini ro'yxatga olish
if dp:
    @dp.message(CommandStart())
    async def handle_start(message: types.Message):
        user_tg_id = message.from_user.id
        user_name = message.from_user.full_name

        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM users WHERE telegram_id = ?", (user_tg_id,))
            user = await cursor.fetchone()

        if user:
            role_title = {
                "ADMIN": "Bosh Rahbar",
                "CASHIER": "Kassir",
                "EMPLOYEE": "Xodim"
            }.get(user["role"], "Xodim")
            
            await message.answer(
                f"Assalomu alaykum, <b>{user['full_name']}</b>!\n\n"
                f"Siz tizimda <b>{role_title}</b> sifatida ro'yxatdan o'tgansiz.\n"
                f"Sizning Telegram ID: <code>{user_tg_id}</code>\n\n"
                f"Web ilovaga kirishda ushbu ID va parolingizdan foydalaning.",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"Assalomu alaykum, <b>{user_name}</b>!\n\n"
                f"Sizning Telegram ID raqamingiz: <code>{user_tg_id}</code> (bosib nusxa oling).\n\n"
                f"Ushbu ID raqamingizni Rahbarga taqdim eting, shunda sizni Xodim-Reyting CRM tizimiga ro'yxatga oladi.",
                parse_mode="HTML"
            )

    @dp.callback_query(F.data.startswith("topup_"))
    async def handle_topup_callback(query: CallbackQuery):
        data = query.data
        chat_id = query.message.chat.id
        actor_id = query.from_user.id
        actor_name = query.from_user.full_name

        # 1. Adminlik huquqini tekshirish
        is_admin = await check_is_group_admin(chat_id, actor_id)
        if not is_admin:
            await query.answer("❌ Faqat guruh adminlari so'rov statusini o'zgartira oladi!", show_alert=True)
            return

        action, topup_id_str = data.replace("topup_", "").split("_")
        topup_id = int(topup_id_str)
        new_status = "APPROVED" if action == "approve" else "REJECTED"
        status_text = "Tasdiqlandi ✅" if new_status == "APPROVED" else "Rad etildi ❌"

        # 2. Bazada yangilash
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("""
                SELECT c.*, u.full_name as employee_name
                FROM card_topups c
                JOIN users u ON c.employee_id = u.id
                WHERE c.id = ?
            """, (topup_id,))
            topup = await cursor.fetchone()
            if not topup:
                await query.answer("So'rov topilmadi!", show_alert=True)
                return

            # Agar so'rov allaqachon RAD ETILGAN bo'lsa (xodim yoki admin tomonidan), guruh admini o'zgartira olmaydi!
            if topup["status"] == "REJECTED":
                await query.answer("❌ Ushbu so'rov xodim tomonidan bekor qilingan! Guruh adminlari uni o'zgartira olmaydi.", show_alert=True)
                try:
                    await query.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass
                return

            new_status = "APPROVED" if action == "approve" else "REJECTED"
            status_text = "Tasdiqlandi ✅" if new_status == "APPROVED" else "Rad etildi ❌"

            await conn.execute("""
                UPDATE card_topups 
                SET status = ?, approved_by_name = ?
                WHERE id = ?
            """, (new_status, actor_name, topup_id))

            # Audit log
            await conn.execute("""
                INSERT INTO audit_logs (entity_type, entity_id, action, actor_name, details)
                VALUES ('CARD_TOPUP', ?, ?, ?, ?)
            """, (topup_id, new_status, actor_name, f"Telegram guruh orqali status {new_status} ga o'zgartirildi"))
            await conn.commit()

        # 3. Telegram xabari matnini yangilash
        keyboard = get_topup_keyboard(topup_id, new_status)
        amount_formatted = f"{int(topup['amount']):,}".replace(",", " ")
        surcharge_formatted = f"{int(topup['surcharge_amount']):,}".replace(",", " ")

        from app.security import get_tashkent_now
        try:
            from datetime import datetime, timedelta
            c_time = topup['created_at']
            if isinstance(c_time, str):
                clean_time = c_time.split(".")[0].replace("T", " ")
                dt = datetime.fromisoformat(clean_time)
                dt_tashkent = dt + timedelta(hours=5)
                tashkent_str = dt_tashkent.strftime("%d.%m.%Y %H:%M")
            else:
                tashkent_str = get_tashkent_now().strftime("%d.%m.%Y %H:%M")
        except Exception:
            tashkent_str = get_tashkent_now().strftime("%d.%m.%Y %H:%M")

        if new_status == "REJECTED":
            # Rad etilganda karta raqami nusxalanmaydigan (<code> tegisiz va ko'rinmas \u200b bilan) qilinadi!
            card_display = "\u200b".join(str(topup['card_number']))
            status_line = f"❌ <b>Rad etildi</b> <i>(Admin: {actor_name})</i>"
            keyboard = None
        else:
            card_display = f"<code>{topup['card_number']}</code>"
            status_line = f"✅ <b>Tasdiqlandi</b> <i>(Admin: {actor_name})</i>"

        new_text = (
            f"💳 <b>Karta to'ldirish so'rovi #{topup['transaction_number']}</b>\n\n"
            f"👤 {topup['employee_name']}\n"
            f"🔢 {card_display}\n"
            f"🏷️ {topup['card_holder']}\n"
            f"💰 {amount_formatted} so'm\n"
            f"📈 {surcharge_formatted} so'm (+3%)\n"
            f"⏰ {tashkent_str}\n\n"
            f"{status_line}"
        )

        try:
            await query.message.edit_text(new_text, reply_markup=keyboard, parse_mode="HTML")
            await query.answer(f"So'rov muvaffaqiyatli: {status_text}")
        except Exception as e:
            logger.warning(f"Xabarni yangilashda xatolik: {e}")
            await query.answer("Status o'zgartirildi!")

async def send_otp_to_telegram(telegram_id: int, otp_code: str) -> bool:
    """Xodim lichkasiga 6 xonali OTP kod jo'natish"""
    if not BOT_TOKEN:
        logger.info(f"[DEV OTP] Bot token ko'rsatilmagan. Foydalanuvchi {telegram_id} uchun OTP kod: {otp_code}")
        return False

    text = (
        f"🔐 <b>Xodim-Reyting CRM: Bir martalik kirish kodi</b>\n\n"
        f"Sizning tasdiqlash kodingiz: <code>{otp_code}</code>\n\n"
        f"⚠️ Ushbu kod <b>1 daqiqa</b> amal qiladi. Kodni hech kimga bermang!"
    )

    # 1. Aiogram orqali yuborish (2.5 soniya kutish)
    if bot:
        try:
            await asyncio.wait_for(
                bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML"),
                timeout=2.5
            )
            return True
        except Exception as e:
            logger.warning(f"Aiogram orqali yuborishda ogohlantirish ({e}), tezkor HTTP API ga o'tilmoqda...")

    # 2. To'g'ridan-to'g'ri Telegram HTTP API orqali (100% kafolatlangan zaxira)
    import httpx
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(url, json={
                "chat_id": telegram_id,
                "text": text,
                "parse_mode": "HTML"
            })
            data = resp.json()
            if data.get("ok"):
                logger.info(f"OTP kod Telegram HTTP API orqali muvaffaqiyatli yuborildi: {telegram_id}")
                return True
            else:
                logger.error(f"Telegram HTTP API xatolik qaytardi: {data}")
    except Exception as e:
        logger.error(f"Telegram HTTP API orqali yuborishda xatolik: {e}")

    return False

async def notify_card_topup_in_group(topup_data: dict) -> int | None:
    """Guruhga karta to'ldirish so'rovini yuborish"""
    if not bot or not TELEGRAM_GROUP_ID:
        logger.info(f"[DEV TOPUP] Guruhga xabar: {topup_data}")
        return None

    from app.security import get_tashkent_now
    tashkent_now = get_tashkent_now().strftime("%d.%m.%Y %H:%M")

    repeat_warning = ""
    if topup_data.get("is_repeat_today"):
        repeat_warning = "\n\n⚠️ <b>DIQQAT: Bu kartaga bugun to'lov qilindi!</b> 🔄"

    text = (
        f"💳 <b>Karta to'ldirish so'rovi #{topup_data['transaction_number']}</b>\n\n"
        f"👤 {topup_data['employee_name']}\n"
        f"🔢 <code>{topup_data['card_number']}</code>\n"
        f"🏷️ {topup_data['card_holder']}\n"
        f"💰 {topup_data['amount_formatted']} so'm\n"
        f"📈 {topup_data['surcharge_formatted']} so'm (+3%)\n"
        f"⏰ {tashkent_now}\n"
        f"⏳ Kutilmoqda ⏳{repeat_warning}"
    )

    keyboard = get_topup_keyboard(topup_data["id"], "PENDING")
    
    # Guruh IDlarini tekshirish (-5381348358 va -1005381348358)
    target_chat_ids = []
    try:
        target_chat_ids.append(int(TELEGRAM_GROUP_ID))
    except Exception:
        pass
    raw_str = str(TELEGRAM_GROUP_ID).strip()
    if raw_str.startswith("-") and not raw_str.startswith("-100"):
        try:
            target_chat_ids.append(int("-100" + raw_str[1:]))
        except Exception:
            pass

    for cid in target_chat_ids:
        try:
            msg = await asyncio.wait_for(
                bot.send_message(
                    chat_id=cid,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                ),
                timeout=2.5
            )
            return msg.message_id
        except Exception as e:
            logger.warning(f"Telegram guruhga ({cid}) yuborishda urinish natijasi: {e}")

    logger.error(f"Guruhga so'rov yuborilmadi. Iltimos, botni guruhga qo'shing va admin huquqini bering! ({TELEGRAM_GROUP_ID})")
    return None

async def update_group_card_topup_status(message_id: int, topup_id: int, new_status: str, actor_name: str, reason_text: str = "") -> bool:
    """Guruhdagi karta to'ldirish xabari matnini 'Rad etildi'ga yangilash va tugmalarni butunlay olib tashlash"""
    if not BOT_TOKEN or not TELEGRAM_GROUP_ID or not message_id:
        return False

    import httpx
    from app.security import get_tashkent_now

    # Bazadan so'rov ma'lumotlarini olish
    topup = None
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("""
                SELECT c.*, u.full_name as employee_name
                FROM card_topups c
                JOIN users u ON c.employee_id = u.id
                WHERE c.id = ?
            """, (topup_id,))
            topup = await cur.fetchone()
    except Exception as e:
        logger.warning(f"Bazada topup ma'lumotlarini olishda xatolik: {e}")

    if not topup:
        return False

    amount_formatted = f"{int(topup['amount']):,}".replace(",", " ")
    surcharge_formatted = f"{int(topup['surcharge_amount']):,}".replace(",", " ")

    try:
        from datetime import datetime, timedelta
        c_time = topup['created_at']
        if isinstance(c_time, str):
            clean_time = c_time.split(".")[0].replace("T", " ")
            dt = datetime.fromisoformat(clean_time)
            dt_tashkent = dt + timedelta(hours=5)
            tashkent_str = dt_tashkent.strftime("%d.%m.%Y %H:%M")
        else:
            tashkent_str = get_tashkent_now().strftime("%d.%m.%Y %H:%M")
    except Exception:
        tashkent_str = get_tashkent_now().strftime("%d.%m.%Y %H:%M")

    if new_status == "REJECTED":
        reason = reason_text or f"Xodim o'zi bekor qildi ({actor_name})"
        status_line = f"❌ <b>Rad etildi</b> <i>({reason})</i>"
        # Rad etilganda karta raqami nusxalanmaydigan (<code> tegisiz va ko'rinmas \u200b bilan) qilinadi!
        card_display = "\u200b".join(str(topup['card_number']))
        markup = None
    else:
        status_line = f"✅ <b>Tasdiqlandi</b> <i>(Admin: {actor_name})</i>"
        card_display = f"<code>{topup['card_number']}</code>"
        markup = get_topup_keyboard(topup_id, "APPROVED")

    text = (
        f"💳 <b>Karta to'ldirish so'rovi #{topup['transaction_number']}</b>\n\n"
        f"👤 {topup['employee_name']}\n"
        f"🔢 {card_display}\n"
        f"🏷️ {topup['card_holder']}\n"
        f"💰 {amount_formatted} so'm\n"
        f"📈 {surcharge_formatted} so'm (+3%)\n"
        f"⏰ {tashkent_str}\n\n"
        f"{status_line}"
    )

    target_chat_ids = []
    try:
        target_chat_ids.append(int(TELEGRAM_GROUP_ID))
    except Exception:
        pass
    raw_str = str(TELEGRAM_GROUP_ID).strip()
    if raw_str.startswith("-") and not raw_str.startswith("-100"):
        try:
            target_chat_ids.append(int("-100" + raw_str[1:]))
        except Exception:
            pass

    for cid in target_chat_ids:
        # 1. Aiogram orqali yangilash
        if bot:
            try:
                await bot.edit_message_text(
                    chat_id=cid,
                    message_id=message_id,
                    text=text,
                    reply_markup=markup,
                    parse_mode="HTML"
                )
                logger.info(f"Guruh xabari muvaffaqiyatli '{new_status}' holatiga yangilandi: {cid}")
                return True
            except Exception as e:
                logger.warning(f"Aiogram bilan guruh xabarini yangilashda urinish: {e}")

        # 2. To'g'ridan-to'g'ri Telegram HTTP API orqali (100% kafolat)
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
            async with httpx.AsyncClient(timeout=8.0) as client:
                reply_markup_payload = markup.model_dump(exclude_none=True) if markup else None
                resp = await client.post(url, json={
                    "chat_id": cid,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup_payload
                })
                data = resp.json()
                if data.get("ok"):
                    logger.info(f"Telegram HTTP API orqali guruh xabari '{new_status}' holatiga yangilandi: {cid}")
                    return True
        except Exception as e:
            logger.error(f"Telegram HTTP API orqali guruh xabarini yangilashda xatolik: {e}")

    return False

async def send_cashier_receipt_to_telegram(employee_tg_id: int, receipt_data: dict) -> bool:
    """Xodimga kassa topshirilganligi chekini shaxsiy telegramiga yuborish"""
    if not bot or not employee_tg_id:
        return False
    try:
        uzs_val = float(receipt_data.get('amount_uzs', 0))
        usd_val = float(receipt_data.get('amount_usd', 0))
        total_val = float(receipt_data.get('total_amount', 0))
        rate_val = float(receipt_data.get('usd_rate', 0))

        uzs_str = f"{uzs_val:,.0f}".replace(",", " ")
        usd_str = f"{usd_val:,.0f}".replace(",", " ")
        total_str = f"{total_val:,.0f}".replace(",", " ")
        rate_str = f"{rate_val:,.0f}".replace(",", " ")

        details_lines = []
        if uzs_val > 0:
            details_lines.append(f"💵 <b>So'mda:</b> {uzs_str} so'm")
        if usd_val > 0:
            details_lines.append(f"💲 <b>Dollarda:</b> {usd_str} $ (Kurs: 1$ = {rate_str} so'm)")
        
        breakdown_text = "\n".join(details_lines) if details_lines else f"💵 <b>Summa:</b> {total_str} so'm"

        text = (
            "🧾 <b>KASSA TOPSHIRILDI (RASMIY CHEK)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Xodim:</b> {receipt_data['employee_name']}\n"
            f"💼 <b>Qabul qildi:</b> {receipt_data['cashier_name']}\n"
            f"📅 <b>Sana va vaqt:</b> {receipt_data['date_time']}\n"
            "─────────────────────\n"
            f"{breakdown_text}\n"
            f"💰 <b>Jami ekvivalent summa:</b> <b>{total_str} so'm</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <i>Kassa topshirilganligi tizimda muvaffaqiyatli qayd etildi.</i>"
        )
        await bot.send_message(chat_id=int(employee_tg_id), text=text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(f"Kassa chekini xodimga (TG: {employee_tg_id}) yuborishda xatolik: {e}")
        return False

async def send_sim_distribution_to_telegram(employee_tg_id: int, sim_data: dict) -> bool:
    """Sim-karta xodimga biriktirilganda shaxsiy telegramiga bildirishnoma yuborish"""
    if not bot or not employee_tg_id:
        return False
    try:
        text = (
            "📲 <b>SIZGA SIM-KARTALAR BIRIKTIRILDI!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"📶 <b>Operator turi:</b> {sim_data['operator_type']}\n"
            f"🔢 <b>Miqdori:</b> <b>{sim_data['count']} dona</b>\n"
            f"📋 <b>Boshlang'ich seriya:</b> <code>{sim_data['start_serial']}</code>\n"
            f"📋 <b>Tugash seriya:</b> <code>{sim_data['end_serial']}</code>\n"
            f"👤 <b>Tarqatuvchi:</b> {sim_data['distributor_name']}\n"
            f"⏰ <b>Vaqti:</b> {sim_data['date_time']}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "ℹ️ <i>Iltimos, berilgan sim-kartalar seriyalarini tekshirib qabul qilib oling.</i>"
        )
        await bot.send_message(chat_id=int(employee_tg_id), text=text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(f"Sim-karta xabarini xodimga (TG: {employee_tg_id}) yuborishda xatolik: {e}")
        return False

async def send_report_summary_to_telegram(employee_tg_id: int, report_data: dict) -> bool:
    """Xodim kunlik hisobot topshirganda shaxsiy telegramiga (lichkasiga) to'liq tafsilotlarni yuborish"""
    if not bot or not employee_tg_id:
        return False
    try:
        def fmt(val):
            return f"{float(val or 0):,.0f}".replace(",", " ")

        paynet_str = fmt(report_data.get("paynet", 0))
        card_str = fmt(report_data.get("card_amount", 0))
        leviy_str = fmt(report_data.get("leviy", 0))
        inflow_str = fmt(report_data.get("total_inflow", 0))

        debt_paid_val = float(report_data.get("debt_paid", 0) or 0)
        debt_paid_str = fmt(debt_paid_val)
        sim_count = int(report_data.get("sim_cards_count", 0) or 0)

        kunlik_str = fmt(report_data.get("kunlik", 0))
        terminal_str = fmt(report_data.get("terminal", 0))
        given_val = float(report_data.get("given_amount", 0) or 0)
        given_str = fmt(given_val)
        skidka_str = fmt(report_data.get("skidka", 0))
        xarajat_str = fmt(report_data.get("xarajat", 0))
        outflow_str = fmt(report_data.get("total_outflow", 0))
        net_str = fmt(report_data.get("net_amount", 0))

        comment = (report_data.get("comment") or "").strip()
        comment_block = f"\n💬 <b>Izoh:</b> <i>{comment}</i>\n" if comment else ""
        debt_paid_inflow = f"🔹 Qarz to'lovi: {debt_paid_str} so'm\n" if debt_paid_val > 0 else ""
        given_block = f"🔸 Berilgan summa: {given_str} so'm\n" if given_val > 0 else ""

        text = (
            "📊 <b>KUNLIK HISOBOT TOPSHIRILDI</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Xodim:</b> {report_data['employee_name']}\n"
            f"📅 <b>Sana:</b> {report_data['report_date']}\n"
            f"⏰ <b>Topshirilgan vaqt:</b> {report_data.get('submitted_at', '')}\n"
            "─────────────────────\n"
            "📥 <b>KIRIM QISMI:</b>\n"
            f"🔹 Paynet: {paynet_str} so'm\n"
            f"🔹 Karta (+3%): {card_str} so'm\n"
            f"🔹 Leviy: {leviy_str} so'm\n"
            f"{debt_paid_inflow}"
            f"💰 <b>Jami kirim:</b> <b>{inflow_str} so'm</b>\n"
            "─────────────────────\n"
            "📤 <b>CHIQIM QISMI:</b>\n"
            f"🔸 Kunlik xarajat: {kunlik_str} so'm\n"
            f"🔸 Terminal: {terminal_str} so'm\n"
            f"{given_block}"
            f"🔸 Skidka: {skidka_str} so'm\n"
            f"🔸 Xarajat: {xarajat_str} so'm\n"
            f"📱 Sim-kartalar: <b>{sim_count} dona</b>\n"
            f"💸 <b>Jami chiqim:</b> <b>{outflow_str} so'm</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>TOPSHIRILADIGAN SOF SUMMA:</b>\n"
            f"👉 <b>{net_str} so'm</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"{comment_block}"
            "⏳ <b>Status:</b> <i>Ko'rib chiqilmoqda (Kutilmoqda)</i>\n"
            "ℹ️ <i>Hisobotingiz qabul qilindi va Rahbar tasdiqlashiga yuborildi.</i>"
        )
        await asyncio.wait_for(
            bot.send_message(chat_id=int(employee_tg_id), text=text, parse_mode="HTML"),
            timeout=5.0
        )
        return True
    except Exception as e:
        logger.warning(f"Hisobot tafsilotlarini xodimga (TG: {employee_tg_id}) yuborishda xatolik: {e}")
        return False

async def send_report_status_to_telegram(employee_tg_id: int, report_date: str, status_str: str, admin_name: str) -> bool:
    """Rahbar hisobotni tasdiqlaganda yoki rad etganda xodim lichkasiga xabar yuborish"""
    if not bot or not employee_tg_id:
        return False
    try:
        is_approved = (status_str == "APPROVED")
        icon = "✅" if is_approved else "❌"
        status_text = "TASDIQLANDI" if is_approved else "RAD ETILDI"
        advice = "Reyting ballaringiz yangilandi." if is_approved else "Iltimos, ma'lumotlarni tekshirib qayta yuboring."

        text = (
            f"{icon} <b>KUNLIK HISOBOT {status_text}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>Sana:</b> {report_date}\n"
            f"👤 <b>Ko'rib chiqdi:</b> {admin_name}\n"
            f"📌 <b>Natija:</b> {icon} {status_text}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"ℹ️ <i>{advice}</i>"
        )
        await asyncio.wait_for(
            bot.send_message(chat_id=int(employee_tg_id), text=text, parse_mode="HTML"),
            timeout=5.0
        )
        return True
    except Exception as e:
        logger.warning(f"Hisobot statusini xodimga (TG: {employee_tg_id}) yuborishda xatolik: {e}")
        return False

async def start_bot_polling():
    """Botni fonda asinxron ishga tushirish"""
    if bot and dp:
        try:
            logger.info("Telegram Bot Polling ishga tushmoqda...")
            await dp.start_polling(bot, handle_signals=False)
        except Exception as e:
            logger.error(f"Bot pollingda to'xtadi: {e}")

