import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
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

            # Foydalanuvchi ma'lumotlarini kompaniyasi bilan birga olish
            cursor = await conn.execute("""
                SELECT u.*, c.name as company_name
                FROM users u
                LEFT JOIN companies c ON c.id = u.company_id
                WHERE u.telegram_id = ?
            """, (user_tg_id,))
            user = await cursor.fetchone()

            # Agar foydalanuvchi kompaniya egasi (owner) bo'lsa, lekin roli ADMIN bo'lmasa, uni darhol ADMIN ga o'tkazish
            if user and user["role"] not in ("ADMIN", "DEVELOPER"):
                cur_comp = await conn.execute("SELECT id, name FROM companies WHERE owner_telegram_id = ?", (user_tg_id,))
                owned_comp = await cur_comp.fetchone()
                if owned_comp:
                    await conn.execute("UPDATE users SET role = 'ADMIN', company_id = ? WHERE telegram_id = ?", (owned_comp["id"], user_tg_id))
                    await conn.commit()
                    cursor = await conn.execute("""
                        SELECT u.*, c.name as company_name
                        FROM users u
                        LEFT JOIN companies c ON c.id = u.company_id
                        WHERE u.telegram_id = ?
                    """, (user_tg_id,))
                    user = await cursor.fetchone()

        if user:
            is_super = (user["company_id"] == 1 and user["role"] == "ADMIN")
            is_company_admin = (user["company_id"] != 1 and user["role"] == "ADMIN")
            is_developer = (user["role"] == "DEVELOPER")
            comp_name = user["company_name"] or "Tashkilot"

            if is_developer:
                role_title = "👑 Dasturchi Admin (Super Admin)"
            elif is_super:
                role_title = "👑 Bosh Tashkilot Rahbari"
            elif is_company_admin:
                role_title = f"👑 Firma Rahbari ({comp_name})"
            elif user["role"] == "CASHIER":
                role_title = f"💼 Kassir ({comp_name})"
            else:
                role_title = f"👤 Xodim ({comp_name})"

            # RAHBARLAR (ADMIN, DEVELOPER): Mutlaqo lokatsiya so'ralmaydi, pastdagi klaviatura tozalanadi
            if user["role"] in ("ADMIN", "DEVELOPER"):
                inline_crm_kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🌐 Web CRM Tizimiga kirish", url="https://xodim-reyting-bot.onrender.com/")]
                    ]
                )
                await message.answer(
                    f"Assalomu alaykum, Hurmatli <b>{user['full_name']}</b>!\n\n"
                    f"🏢 <b>Tashkilot:</b> {comp_name}\n"
                    f"🎖 <b>Maqomingiz:</b> {role_title}\n"
                    f"🔑 <b>Telegram ID:</b> <code>{user_tg_id}</code>\n\n"
                    f"👑 Siz <b>Rahbar</b> maqomidasiz. Xodimlar kabi lokatsiya yuborishingiz shart emas va talab etilmaydi.\n\n"
                    f"Tizimni boshqarish, xodimlar reytingi va kassa hisobotlarini nazorat qilish uchun CRM tizimiga kiring:",
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode="HTML"
                )
                await message.answer(
                    "👇 <b>CRM Tizimiga kirish havolasi:</b>",
                    reply_markup=inline_crm_kb,
                    parse_mode="HTML"
                )
            else:
                # XODIMLAR VA KASSIRLAR: Ish joyi va lokatsiya tartibi (Klaviaturani tozalaymiz)
                w_name = user["workplace_name"] or "Bosh ofis / Ish joyi"
                w_hours = f"{user['work_start_time'] or '09:00'} - {user['work_end_time'] or '19:00'}"
                await message.answer(
                    f"Assalomu alaykum, <b>{user['full_name']}</b>!\n\n"
                    f"🏢 <b>Tashkilot:</b> {comp_name}\n"
                    f"👤 <b>Maqomingiz:</b> {role_title}\n"
                    f"📍 <b>Filial:</b> {w_name}\n"
                    f"⏰ <b>Ish vaqti:</b> {w_hours}\n"
                    f"🔑 <b>Telegram ID:</b> <code>{user_tg_id}</code>\n\n"
                    f"📍 <b>JOYLASHUV YUBORISH TARTIBI:</b>\n"
                    f"Pastdagi <b>📎 (Skrepka)</b> -> <b>📍 Geopozitsiya</b> bo'limi orqali:\n\n"
                    f"1️⃣ <b>Filialning aniq joylashuvini belgilash:</b>\n"
                    f"   Filialingizga borganingizda <i>'Отправить свою геопозицию' (Oddiy joylashuv)</i> ni yuboring. Ushbu koordinata filialingizning rasmiy manzili sifatida saqlanadi.\n\n"
                    f"2️⃣ <b>🛰 Kunlik jonli kuzatuv (Live Location):</b>\n"
                    f"   <i>'Транслировать геопозицию...'</i> ni tanlab <b>8 soat</b> qilib yuboring. Telefoningiz fonda filialda ekanligingizni CRM tizimiga avtomatik uzatib turadi.",
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode="HTML"
                )
        else:
            # Ro'yxatdan o'tmagan mehmon: Klaviaturani tozalaymiz
            await message.answer(
                f"Assalomu alaykum, <b>{user_name}</b>!\n\n"
                f"Sizning Telegram ID raqamingiz: <code>{user_tg_id}</code> (bosib nusxa oling).\n\n"
                f"Ushbu ID raqamingizni Rahbarga taqdim eting, shunda sizni Xodim-Reyting CRM tizimiga ro'yxatga oladi.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="HTML"
            )

    @dp.message(F.text == "ℹ️ Jonli joylashuv qo'llanmasi")
    @dp.message(Command("location"))
    async def handle_location_guide(message: types.Message):
        user_tg_id = message.from_user.id
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT role FROM users WHERE telegram_id = ?", (user_tg_id,))
            u = await cur.fetchone()

        if u and u["role"] in ("ADMIN", "DEVELOPER"):
            await message.answer(
                "👑 <b>Hurmatli Rahbar!</b>\n\nSiz rahbar maqomidasiz. Lokatsiya monitoringi faqat xodimlar uchun mo'ljallangan.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="HTML"
            )
            return

        guide_text = (
            "🛰 <b>JOYLASHUV BO'YICHA QO'LLANMA:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Xabar yozish maydonidagi <b>📎 (Skrepka)</b> -> <b>📍 Geopozitsiya (Location)</b> bo'limi orqali:\n\n"
            "1️⃣ <b>1-usul: Oddiy joylashuv (Filialning aniq manzili):</b>\n"
            "• Filialingizga borganingizda <i>'Отправить свою геопозицию'</i> tugmasini bosing;\n"
            "• Ushbu manzil filialingizning rasmiy koordinatasi sifatida biriktiriladi.\n\n"
            "2️⃣ <b>2-usul: Jonli joylashuv (Kun bo'yi kuzatuv):</b>\n"
            "• <i>'Транслировать мою геопозицию...'</i> tugmasini bosing;\n"
            "• Muddat sifatida <b>8 soat</b> (ish kuni davomi) ni tanlang va yuboring;\n"
            "• Telefoningiz ekrani o'chiq bo'lsa ham, Telegram filialda ekanligingizni CRM tizimiga uzatib turadi.\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )
        await message.answer(guide_text, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")

    async def update_employee_location_from_telegram(
        user_tg_id: int,
        lat: float,
        lon: float,
        live_period: int | None = None,
        is_live_edit: bool = False
    ) -> dict:
        """
        Telegram bot orqali yuborilgan lokatsiyani (bir martalik yoki jonli Live Location)
        xodim profiliga kiritish va geofencing masofasini hisoblash
        """
        from datetime import datetime, timezone
        from app.routes.location import calculate_haversine_meters, get_current_tashkent_hm, is_time_within_interval

        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("""
                SELECT id, full_name, role, is_active, company_id,
                       workplace_name, workplace_latitude, workplace_longitude, workplace_radius_meters,
                       work_start_time, work_end_time, shift_status
                FROM users WHERE telegram_id = ?
            """, (user_tg_id,))
            user = await cur.fetchone()

            if not user or not user["is_active"]:
                return {"success": False, "reply_text": "Siz tizimda faol xodim sifatida topilmadingiz."}

            if user["role"] in ("ADMIN", "DEVELOPER"):
                return {"success": True, "reply_text": "Bosh Rahbar yoki Dasturchi lokatsiyasi kuzatilmaydi."}

            shift_status = user["shift_status"] if ("shift_status" in user.keys() and user["shift_status"]) else "WORKING"
            if shift_status == "RESTING":
                if not is_live_edit:
                    return {
                        "success": True,
                        "reply_text": "🌙 <b>Dam olish rejimidasiz:</b>\nRahbar sizni bugun damda deb belgilagan, shu sababli ish kordinatalari hisoblanmaydi."
                    }
                return {"success": True}

            w_lat = user["workplace_latitude"]
            w_lon = user["workplace_longitude"]
            w_radius = user["workplace_radius_meters"] or 50
            w_name = user["workplace_name"] or "Bosh ofis / Ish joyi"
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            time_hm = get_current_tashkent_hm()

            # 1-USUL: XODIM YUBORGAN ODDIY JOYLASHUV (Static location) -> FILIALNING ANIQ JOYLASHUVI SIFATIDA SAQLANADI
            is_static_location = (live_period is None and not is_live_edit)
            if is_static_location:
                await conn.execute("""
                    UPDATE users
                    SET workplace_latitude = ?,
                        workplace_longitude = ?,
                        last_latitude = ?,
                        last_longitude = ?,
                        last_distance_meters = 0.0,
                        last_location_updated_at = ?
                    WHERE id = ?
                """, (
                    round(lat, 7),
                    round(lon, 7),
                    round(lat, 7),
                    round(lon, 7),
                    now_utc,
                    user["id"]
                ))
                await conn.commit()

                reply_text = (
                    f"🏢 <b>FILIALNING ANIQ JOYLASHUVI SAQLANDI!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📍 <b>Filial:</b> {w_name}\n"
                    f"📌 <b>Aniq koordinata:</b> <code>{lat:.6f}, {lon:.6f}</code>\n"
                    f"✅ Ushbu manzil ish joyingiz (filial) rasmiy koordinatasi sifatida muvaffaqiyatli saqlandi!\n\n"
                    f"🛰 <b>2-Qadam (Kunlik kuzatuv):</b>\n"
                    f"Kun davomida ish joyida ekanligingizni tasdiqlash uchun pastdagi <b>📎 (Skrepka)</b> -> <b>📍 Geopozitsiya</b> -> <i>'Транслировать геопозицию...' (Jonli joylashuv)</i> ni tanlab <b>8 soat</b> qilib yuboring.\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🕒 <b>Toshkent vaqti:</b> {time_hm}"
                )
                return {"success": True, "reply_text": reply_text}

            # 2-USUL: JONLI JOYLASHUV (Live location) -> FILIALGA NISBATAN KUZATILIB TIZIMGA YUBORILIB TURILADI
            is_configured = (w_lat is not None and w_lon is not None and (w_lat != 0.0 or w_lon != 0.0))
            distance_meters = None
            is_inside = None
            if is_configured:
                distance_meters = calculate_haversine_meters(w_lat, w_lon, lat, lon)
                is_inside = (distance_meters <= w_radius)

            await conn.execute("""
                UPDATE users
                SET last_latitude = ?,
                    last_longitude = ?,
                    last_distance_meters = ?,
                    last_location_updated_at = ?
                WHERE id = ?
            """, (
                round(lat, 7),
                round(lon, 7),
                distance_meters,
                now_utc,
                user["id"]
            ))
            await conn.commit()

            # Fondagi jonli koordinata yangilanishi (Telegram Live update) bo'lsa, xodimni xabarlar bilan bezovta qilmaymiz
            if is_live_edit:
                return {"success": True}

            # Jonli lokatsiya ilk bor yoqilgandagi tasdiq xabari
            is_within = is_time_within_interval(time_hm, user["work_start_time"] or "09:00", user["work_end_time"] or "19:00")
            if is_configured:
                dist_int = int(distance_meters)
                dist_str = f"{dist_int} metr" if dist_int < 1000 else f"{dist_int/1000:.1f} km"
                if is_inside:
                    status_msg = f"🟢 <b>Siz filialdasiz!</b>\n🏢 <b>Filial:</b> {w_name}\n📏 <b>Filialgacha masofa:</b> {dist_str} (Ruxsat: {w_radius} m)"
                else:
                    status_msg = f"🔴 <b>Diqqat: Siz filialdan tashqaridasiz!</b>\n🏢 <b>Filial:</b> {w_name}\n📏 <b>Filialgacha masofa:</b> {dist_str} (Ruxsat: {w_radius} m)\n⚠️ Iltimos, filial hududida bo'ling."
            else:
                status_msg = (
                    f"⚪ <b>Jonli joylashuv qabul qilindi</b>\n"
                    f"Kordinata: <code>{lat:.5f}, {lon:.5f}</code>\n\n"
                    f"⚠️ <i>Filialingizning aniq koordinatasi hali belgilanmagan! Iltimos, filialda turib 1 marta oddiy joylashuv (Geopozitsiya) yuboring.</i>"
                )

            hours_msg = ""
            if not is_within:
                hours_msg = f"\n🌙 <i>Hozir belgilangan ish soati emas ({user['work_start_time'] or '09:00'} - {user['work_end_time'] or '19:00'}).</i>\n"

            period_str = "8 soat"
            if live_period:
                hours_cnt = live_period // 3600
                period_str = f"{hours_cnt} soat" if hours_cnt > 0 else f"{live_period // 60} daqiqa"

            reply_text = (
                f"🛰 <b>JONLI JOYLASHUV FAOLLASHDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"{status_msg}\n"
                f"{hours_msg}\n"
                f"🛰 Jonli joylashuvingiz ish kuni davomida ({period_str}) avtomatik kuzatilib, CRM tizimiga yuborilib turadi.\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🕒 <b>Toshkent vaqti:</b> {time_hm}"
            )
            return {"success": True, "reply_text": reply_text}

    @dp.message(F.location)
    async def handle_location_message(message: types.Message):
        """Xodimdan kelgan bir martalik yoki jonli lokatsiyaning birinchi xabari"""
        user_tg_id = message.from_user.id
        loc = message.location
        if not loc:
            return
        lat = loc.latitude
        lon = loc.longitude
        live_period = getattr(loc, "live_period", None)

        res = await update_employee_location_from_telegram(
            user_tg_id=user_tg_id,
            lat=lat,
            lon=lon,
            live_period=live_period,
            is_live_edit=False
        )
        if res.get("reply_text"):
            is_admin_user = ("Rahbar" in res["reply_text"] or "Dasturchi" in res["reply_text"])
            await message.reply(
                res["reply_text"],
                reply_markup=ReplyKeyboardRemove() if is_admin_user else None,
                parse_mode="HTML"
            )

    @dp.edited_message(F.location)
    async def handle_location_edited(message: types.Message):
        """Xodim harakatlanganda Telegram tomonidan fonda uzatiladigan jonli koordinata yangilanishlari"""
        user_tg_id = message.from_user.id
        loc = message.location
        if not loc:
            return
        lat = loc.latitude
        lon = loc.longitude
        live_period = getattr(loc, "live_period", None)

        await update_employee_location_from_telegram(
            user_tg_id=user_tg_id,
            lat=lat,
            lon=lon,
            live_period=live_period,
            is_live_edit=True
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

    # 1. To'g'ridan-to'g'ri Telegram HTTP API orqali (eng tezkor va ishonchli, eski soket muammosidan xoli)
    import aiohttp
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        timeout = aiohttp.ClientTimeout(total=3.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json={
                "chat_id": telegram_id,
                "text": text,
                "parse_mode": "HTML"
            }) as resp:
                data = await resp.json()
                if data.get("ok"):
                    logger.info(f"OTP kod Telegram HTTP API orqali bir zumda yuborildi: {telegram_id}")
                    return True
                else:
                    logger.warning(f"Telegram HTTP API javobi: {data}")
    except Exception as e:
        logger.warning(f"Telegram HTTP API orqali yuborishda xatolik ({e}), aiogram zaxirasiga o'tilmoqda...")

    # 2. Aiogram zaxira kanali
    if bot:
        try:
            await asyncio.wait_for(
                bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML"),
                timeout=3.0
            )
            return True
        except Exception as e:
            logger.error(f"Aiogram zaxira orqali ham yuborib bo'lmadi: {e}")

    return False

async def notify_card_topup_in_group(topup_data: dict, group_id: str | None = None) -> int | None:
    """Guruhga karta to'ldirish so'rovini yuborish (firma guruhiga yoki markaziy guruhga)"""
    target_raw_group = str(group_id).strip() if group_id and str(group_id).strip() else str(TELEGRAM_GROUP_ID).strip()
    if not bot or not target_raw_group:
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
    
    # Guruh IDlarini tekshirish
    target_chat_ids = []
    try:
        target_chat_ids.append(int(target_raw_group))
    except Exception:
        pass
    if target_raw_group.startswith("-") and not target_raw_group.startswith("-100"):
        try:
            target_chat_ids.append(int("-100" + target_raw_group[1:]))
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

    logger.error(f"Guruhga so'rov yuborilmadi. Iltimos, botni guruhga qo'shing va admin huquqini bering! ({target_raw_group})")
    return None

async def update_group_card_topup_status(message_id: int, topup_id: int, new_status: str, actor_name: str, reason_text: str = "") -> bool:
    """Guruhdagi karta to'ldirish xabari matnini 'Rad etildi'ga yangilash va tugmalarni butunlay olib tashlash"""
    if not BOT_TOKEN or not message_id:
        return False

    import httpx
    from app.security import get_tashkent_now

    # Bazadan so'rov ma'lumotlarini olish (kompaniyaning shaxsiy guruhi bilan)
    topup = None
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("""
                SELECT c.*, u.full_name as employee_name, comp.telegram_group_id as company_group_id
                FROM card_topups c
                JOIN users u ON c.employee_id = u.id
                LEFT JOIN companies comp ON c.company_id = comp.id
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

    grp_id = topup.get("company_group_id") or TELEGRAM_GROUP_ID
    target_raw_group = str(grp_id).strip()
    target_chat_ids = []
    try:
        target_chat_ids.append(int(target_raw_group))
    except Exception:
        pass
    if target_raw_group.startswith("-") and not target_raw_group.startswith("-100"):
        try:
            target_chat_ids.append(int("-100" + target_raw_group[1:]))
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

async def send_daily_digest_for_company(
    company_id: int,
    target_date: str | None = None,
    end_date: str | None = None,
    send_to_owner: bool = True,
    owner_override_tg: int | None = None
) -> dict:
    """
    Kompaniya uchun bugungi yoki belgilangan sana/davr bo'yicha yakuniy svodkani hisoblash va
    FAQAT Rahbar shaxsiy lichkasiga yuborish (Telegram guruhlarga yuborilmaydi)
    """
    if not bot:
        return {"success": False, "message": "Bot faol emas"}

    from datetime import datetime
    from app.security import get_tashkent_now
    now_tashkent = get_tashkent_now()
    today_str = now_tashkent.strftime("%Y-%m-%d")
    time_display = now_tashkent.strftime("%H:%M")

    # Sana yoki Sana oralig'i (Date or Date Range)
    if target_date and str(target_date).strip():
        start_date_str = str(target_date).strip()
    else:
        start_date_str = today_str

    if end_date and str(end_date).strip() and str(end_date).strip() != start_date_str:
        end_date_str = str(end_date).strip()
        is_range = True
        try:
            d1 = datetime.strptime(start_date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
            d2 = datetime.strptime(end_date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
            date_display = f"{d1} — {d2}"
        except Exception:
            date_display = f"{start_date_str} — {end_date_str}"
        header_title = "📊 <b>DAVRIY HISOBOT SVODKASI</b>"
    else:
        end_date_str = start_date_str
        is_range = False
        try:
            date_display = datetime.strptime(start_date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            date_display = start_date_str
        header_title = "📊 <b>KUN YAKUNI HISOBOT SVODKASI</b>" if start_date_str == today_str else "📊 <b>KUNLIK HISOBOT SVODKASI</b>"

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Kompaniya ma'lumotlari
        cur_c = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        comp = await cur_c.fetchone()
        if not comp:
            return {"success": False, "message": "Kompaniya topilmadi"}

        comp_name = comp["name"]
        owner_tg = comp["owner_telegram_id"]

        # 2. Xodimlar soni va ro'yxati
        cur_u = await conn.execute(
            "SELECT id, full_name, telegram_id FROM users WHERE company_id = ? AND is_active = 1 AND role NOT IN ('ADMIN', 'DEVELOPER')",
            (company_id,)
        )
        all_emps = await cur_u.fetchall()
        total_emps = len(all_emps)
        all_emp_ids = {u["id"]: u["full_name"] for u in all_emps}

        # 3. Kunlik hisobotlar
        if is_range:
            cur_rep = await conn.execute("""
                SELECT r.*, u.full_name
                FROM daily_reports r
                JOIN users u ON r.employee_id = u.id
                WHERE r.company_id = ? AND r.report_date >= ? AND r.report_date <= ?
            """, (company_id, start_date_str, end_date_str))
        else:
            cur_rep = await conn.execute("""
                SELECT r.*, u.full_name
                FROM daily_reports r
                JOIN users u ON r.employee_id = u.id
                WHERE r.company_id = ? AND r.report_date = ?
            """, (company_id, start_date_str))
        reports = await cur_rep.fetchall()

        submitted_emp_ids = set()
        total_paynet = 0
        total_card_reports = 0
        total_leviy = 0
        total_net = 0
        total_sims_reported = 0
        total_debt_paid = 0

        leader_name = "Hali hisobot topshirilmadi"
        max_net = -1

        for r in reports:
            submitted_emp_ids.add(r["employee_id"])
            total_paynet += (r["paynet"] or 0)
            total_card_reports += (r["card_amount"] or 0)
            total_leviy += (r["leviy"] or 0)
            total_net += (r["net_amount"] or 0)
            total_sims_reported += (r["sim_cards_count"] or 0)
            total_debt_paid += (r["debt_paid"] or 0)

            if (r["net_amount"] or 0) > max_net:
                max_net = r["net_amount"]
                leader_name = f"{r['full_name']} ({int(max_net):,} so'm)".replace(",", " ")

        submitted_count = len(submitted_emp_ids)
        not_submitted_count = max(0, total_emps - submitted_count)

        # Topshirmaganlar ro'yxati (3 tagacha)
        not_submitted_names = [name for uid, name in all_emp_ids.items() if uid not in submitted_emp_ids]
        not_sub_text = ""
        if not_submitted_names:
            preview_not_sub = ", ".join(not_submitted_names[:3])
            if len(not_submitted_names) > 3:
                preview_not_sub += f" va yana {len(not_submitted_names) - 3} ta"
            not_sub_text = f"\n⚠️ <b>Topshirmaganlar:</b> <i>{preview_not_sub}</i>"

        # 4. Kassa qabul qilish
        if is_range:
            cur_cash = await conn.execute("""
                SELECT SUM(amount_uzs) as sum_uzs, SUM(amount_usd) as sum_usd, SUM(amount) as sum_total
                FROM cashier_handovers
                WHERE company_id = ? AND handover_date >= ? AND handover_date <= ?
            """, (company_id, start_date_str, end_date_str))
        else:
            cur_cash = await conn.execute("""
                SELECT SUM(amount_uzs) as sum_uzs, SUM(amount_usd) as sum_usd, SUM(amount) as sum_total
                FROM cashier_handovers
                WHERE company_id = ? AND handover_date = ?
            """, (company_id, start_date_str))
        cash_row = await cur_cash.fetchone()
        kassa_uzs = int(cash_row["sum_uzs"] or 0) if cash_row else 0
        kassa_usd = int(cash_row["sum_usd"] or 0) if cash_row else 0
        kassa_total = int(cash_row["sum_total"] or 0) if cash_row else 0

        # 5. Karta to'ldirish so'rovlari
        if is_range:
            cur_top = await conn.execute("""
                SELECT COUNT(*) as cnt, SUM(amount) as sum_amount
                FROM card_topups
                WHERE company_id = ? AND DATE(created_at, '+5 hours') >= ? AND DATE(created_at, '+5 hours') <= ? AND status = 'APPROVED'
            """, (company_id, start_date_str, end_date_str))
        else:
            cur_top = await conn.execute("""
                SELECT COUNT(*) as cnt, SUM(amount) as sum_amount
                FROM card_topups
                WHERE company_id = ? AND DATE(created_at, '+5 hours') = ? AND status = 'APPROVED'
            """, (company_id, start_date_str))
        top_row = await cur_top.fetchone()
        topup_cnt = top_row["cnt"] or 0 if top_row else 0
        topup_sum = int(top_row["sum_amount"] or 0) if top_row else 0

    # Telegram formatlangan xabar
    total_net_fmt = f"{int(total_net):,}".replace(",", " ")
    total_paynet_fmt = f"{int(total_paynet):,}".replace(",", " ")
    topup_sum_fmt = f"{topup_sum:,}".replace(",", " ")

    text = (
        f"{header_title}\n"
        f"🏢 <b>{comp_name}</b>\n"
        f"📅 <b>Sana / Davr:</b> {date_display} (⏰ {time_display})\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Xodimlar hisoboti:</b> {submitted_count}/{total_emps} ta topshirdi"
        f"{not_sub_text}\n\n"
        f"💰 <b>Jami sof kassa (Net):</b> <b>{total_net_fmt} so'm</b>\n"
        f"📲 <b>Paynet tushumi:</b> {total_paynet_fmt} so'm\n"
        f"💳 <b>Karta to'ldirish:</b> {topup_sum_fmt} so'm ({topup_cnt} ta)\n"
        f"📱 <b>Sotilgan sim-kartalar:</b> {total_sims_reported} dona\n"
    )

    if total_debt_paid > 0:
        debt_paid_fmt = f"{int(total_debt_paid):,}".replace(",", " ")
        text += f"🤝 <b>Qarz uchun to'landi:</b> {debt_paid_fmt} so'm\n"

    kassa_uzs_fmt = f"{kassa_uzs:,}".replace(",", " ")
    kassa_total_fmt = f"{kassa_total:,}".replace(",", " ")
    text += (
        f"\n🏦 <b>Kassir qabul qilgan kassa:</b>\n"
        f"• So'mda: {kassa_uzs_fmt} so'm\n"
    )
    if kassa_usd > 0:
        kassa_usd_fmt = f"{kassa_usd:,}".replace(",", " ")
        text += f"• Dollarda: ${kassa_usd_fmt}\n"
    text += (
        f"• <b>Jami ekvivalent:</b> <b>{kassa_total_fmt} so'm</b>\n\n"
        f"🏆 <b>Kun yetakchisi:</b> {leader_name}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <i>Xodim-Reyting CRM tahlili</i>"
    )

    # Qayerga yuborish: FAQAT Rahbar shaxsiy lichkasiga (Telegram guruhlarga yuborish qat'iy taqiqlangan)
    sent_owner = False
    target_owner_id = owner_override_tg or owner_tg

    if send_to_owner and target_owner_id:
        try:
            target_owner_int = int(target_owner_id)
            # Faqat musbat (shaxsiy profil) ID larga yuboriladi, guruh ID lari (manfiy) qat'iy cheklangan
            if target_owner_int > 0:
                await asyncio.wait_for(
                    bot.send_message(chat_id=target_owner_int, text=text, parse_mode="HTML"),
                    timeout=5.0
                )
                sent_owner = True
            else:
                logger.warning(f"Svodkani guruhga ({target_owner_int}) yuborish rad etildi! Faqat rahbar shaxsiy lichkasiga yuboriladi.")
        except Exception as e:
            logger.warning(f"Svodkani rahbar lichkasiga ({target_owner_id}) yuborishda xatolik: {e}")

    sent = sent_owner
    msg = "Svodka rahbar shaxsiy Telegram lichkasiga muvaffaqiyatli yuborildi! 🚀" if sent else "Telegramga yuborib bo'lmadi (Rahbar bot bilan shaxsiy chat boshlamagan bo'lishi mumkin)."

    return {
        "success": sent,
        "message": msg,
        "data": {
            "submitted_count": submitted_count,
            "total_emps": total_emps,
            "total_net": total_net,
            "kassa_total": kassa_total,
            "sim_cards_sold": total_sims_reported,
            "leader": leader_name
        }
    }

async def send_document_to_telegram(
    chat_id: int,
    file_bytes: bytes,
    filename: str,
    caption: str = ""
) -> bool:
    """Excel yoki boshqa hujjatni FAQAT rahbar shaxsiy lichkasiga yuborish (guruhlarga yuborish qat'iy taqiqlangan)"""
    if not bot or not chat_id:
        return False
    try:
        target_chat = int(chat_id)
        # Guruh ID lari manfiy (< 0) bo'ladi. Excel hech qachon guruhga yuborilmaydi!
        if target_chat < 0:
            logger.warning(f"Excel faylini guruhga ({target_chat}) yuborish rad etildi! Faqat rahbar shaxsiy lichkasiga yuboriladi.")
            return False

        from aiogram.types import BufferedInputFile
        doc = BufferedInputFile(file_bytes, filename=filename)
        await asyncio.wait_for(
            bot.send_document(chat_id=target_chat, document=doc, caption=caption, parse_mode="HTML"),
            timeout=10.0
        )
        return True
    except Exception as e:
        logger.warning(f"Hujjatni rahbar shaxsiy lichkasiga ({chat_id}) yuborishda xatolik: {e}")
        return False

async def send_subscription_expiry_alert(company_id: int, days_left: int) -> bool:
    """Obunasi tugashiga 3 kun yoki 1 kun qolgan firma rahbariga Telegram orqali ogohlantirish"""
    if not bot:
        return False

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        comp = await cur.fetchone()

    if not comp or comp["plan"] == "UNLIMITED" or not comp["owner_telegram_id"]:
        return False

    owner_tg = int(comp["owner_telegram_id"])
    comp_name = comp["name"]

    try:
        from datetime import datetime, timezone, timedelta
        exp_raw = str(comp["subscription_expires_at"]).replace("Z", "+00:00")
        exp_dt = datetime.fromisoformat(exp_raw)
        tashkent_tz = timezone(timedelta(hours=5))
        exp_display = exp_dt.astimezone(tashkent_tz).strftime("%d.%m.%Y")
    except Exception:
        exp_display = str(comp["subscription_expires_at"])

    day_word = f"{days_left} kun" if days_left > 1 else "1 KUN (ERTANGA)"
    icon = "⚠️" if days_left > 1 else "🚨"

    text = (
        f"{icon} <b>DIQQAT: OBUNA MUDDATI TUGAMOQDA!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Hurmatli <b>{comp_name}</b> rahbari!\n\n"
        f"Sizning <b>Xodim-Reyting CRM</b> tizimidan foydalanish ijara obunangiz tugashiga <b>{day_word}</b> qoldi.\n\n"
        f"📅 <b>Tugash sanasi:</b> {exp_display}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Xizmat to'xtab qolmasligi va tizimdan uzluksiz foydalanish uchun iltimos, o'z vaqtida obunani uzaytiring.\n\n"
        "📞 <i>Dasturchi Admin bilan bog'lanish: @xodim_reyting_bot</i>"
    )

    try:
        await asyncio.wait_for(
            bot.send_message(chat_id=owner_tg, text=text, parse_mode="HTML"),
            timeout=4.0
        )
        return True
    except Exception as e:
        logger.warning(f"Obuna ogohlantirishini yuborishda xatolik (TG: {owner_tg}): {e}")
        return False

async def start_bot_polling():
    """Botni fonda asinxron ishga tushirish"""
    if bot and dp:
        try:
            logger.info("Telegram Bot Polling ishga tushmoqda...")
            await dp.start_polling(bot, handle_signals=False)
        except Exception as e:
            logger.error(f"Bot pollingda to'xtadi: {e}")

