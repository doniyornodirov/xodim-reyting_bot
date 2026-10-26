import aiosqlite
from app.config import DB_PATH
from app.security import hash_password

async def get_db():
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()

async def init_db():
    """Baza sxemasini yaratish va boshlang'ich ma'lumotlarni kiritish"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        
        # 1. Foydalanuvchilar jadvali
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'EMPLOYEE',
            password_hash TEXT NOT NULL,
            debt_amount REAL NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. Karta to'ldirish so'rovlari
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS card_topups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_number INTEGER NOT NULL,
            employee_id INTEGER NOT NULL REFERENCES users(id),
            card_number TEXT NOT NULL,
            card_holder TEXT NOT NULL,
            amount REAL NOT NULL,
            surcharge_amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            telegram_message_id INTEGER,
            approved_by_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 3. Berilgan summalar
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS given_amounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES users(id),
            amount REAL NOT NULL,
            comment TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            approved_by_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 4. Kunlik hisobotlar
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES users(id),
            report_date TEXT NOT NULL,
            paynet REAL NOT NULL DEFAULT 0,
            card_amount REAL NOT NULL DEFAULT 0,
            leviy REAL NOT NULL DEFAULT 0,
            debt_snapshot REAL NOT NULL DEFAULT 0,
            debt_paid REAL NOT NULL DEFAULT 0,
            sim_cards_count INTEGER NOT NULL DEFAULT 0,
            kunlik REAL NOT NULL DEFAULT 0,
            terminal REAL NOT NULL DEFAULT 0,
            given_amount REAL NOT NULL DEFAULT 0,
            skidka REAL NOT NULL DEFAULT 0,
            xarajat REAL NOT NULL DEFAULT 0,
            total_inflow REAL NOT NULL DEFAULT 0,
            total_outflow REAL NOT NULL DEFAULT 0,
            net_amount REAL NOT NULL DEFAULT 0,
            comment TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            reviewed_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_id, report_date)
        );
        """)

        # 5. Kassir topshirgan summalar
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS cashier_handovers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cashier_id INTEGER NOT NULL REFERENCES users(id),
            employee_id INTEGER NOT NULL REFERENCES users(id),
            handover_date TEXT NOT NULL,
            amount REAL NOT NULL,
            amount_uzs REAL NOT NULL DEFAULT 0,
            amount_usd REAL NOT NULL DEFAULT 0,
            usd_rate REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migratsiyalar: cashier_handovers
        for col_sql in [
            "ALTER TABLE cashier_handovers ADD COLUMN amount_uzs REAL NOT NULL DEFAULT 0",
            "ALTER TABLE cashier_handovers ADD COLUMN amount_usd REAL NOT NULL DEFAULT 0",
            "ALTER TABLE cashier_handovers ADD COLUMN usd_rate REAL NOT NULL DEFAULT 0"
        ]:
            try:
                await conn.execute(col_sql)
            except Exception:
                pass
        await conn.execute("UPDATE cashier_handovers SET amount_uzs = amount WHERE amount_uzs = 0 AND amount_usd = 0")

        # 6. Kassirlik tarixi
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS cashier_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            action TEXT NOT NULL,
            assigned_by_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 7. OTP kodlar
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            is_used INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 8. Audit loglar
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            actor_name TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 9. Sim-kartalar hisobi va tarqatish
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS sim_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_number TEXT UNIQUE NOT NULL,
            operator_type TEXT NOT NULL DEFAULT 'Uzmobile',
            employee_id INTEGER NOT NULL REFERENCES users(id),
            distributed_by_id INTEGER NOT NULL REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'GIVEN',
            distributed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sold_at TIMESTAMP
        );
        """)

        # Migratsiya: operator_type ustuni mavjud bo'lmasa qo'shish
        try:
            await conn.execute("ALTER TABLE sim_cards ADD COLUMN operator_type TEXT NOT NULL DEFAULT 'Uzmobile';")
        except Exception:
            pass

        # Indekslar
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_card_topups_date ON card_topups(created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_card_topups_number ON card_topups(card_number);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_given_amounts_date ON given_amounts(created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_reports_emp_date ON daily_reports(employee_id, report_date);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(report_date);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_cashier_handovers_date ON cashier_handovers(handover_date);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_cashier_handovers_created ON cashier_handovers(created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_cashier_history_created ON cashier_history(created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_otp_codes_created ON otp_codes(created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sim_cards_serial ON sim_cards(serial_number);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sim_cards_employee ON sim_cards(employee_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sim_cards_operator ON sim_cards(operator_type);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sim_cards_sold ON sim_cards(status, sold_at);")

        # 10. Tizim sozlamalari (Dollar kursi)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        await conn.execute("""
        INSERT OR IGNORE INTO system_settings (key, value)
        VALUES ('usd_rate', '12000');
        """)

        # 11. Sim-kartalar tarqatish partiyalari (dan - gacha)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS sim_distributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_type TEXT NOT NULL DEFAULT 'Uzmobile',
            start_serial TEXT NOT NULL,
            end_serial TEXT NOT NULL,
            total_count INTEGER NOT NULL,
            employee_id INTEGER NOT NULL REFERENCES users(id),
            distributed_by_id INTEGER NOT NULL REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'GIVEN',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sim_distributions_created ON sim_distributions(created_at);")

        # Agar sim_distributions bo'sh bo'lsa va sim_cards da ma'lumot bo'lsa, mavjud tarqatishlarni partiya qilib o'tkazish
        cur_dist = await conn.execute("SELECT COUNT(*) FROM sim_distributions")
        dist_count = (await cur_dist.fetchone())[0]
        if dist_count == 0:
            await conn.execute("""
                INSERT INTO sim_distributions (operator_type, start_serial, end_serial, total_count, employee_id, distributed_by_id, status, created_at)
                SELECT 
                    s.operator_type,
                    MIN(s.serial_number),
                    MAX(s.serial_number),
                    COUNT(s.id),
                    s.employee_id,
                    s.distributed_by_id,
                    'GIVEN',
                    s.distributed_at
                FROM sim_cards s
                GROUP BY s.operator_type, s.employee_id, s.distributed_by_id, s.distributed_at
            """)

        # Tasdiqlangan hisobotlardagi sim-kartalarni sim_cards da 'SOLD' holatiga sinxronlash
        cur_app_rep = await conn.execute("""
            SELECT employee_id, SUM(sim_cards_count) as total_sold
            FROM daily_reports
            WHERE status = 'APPROVED'
            GROUP BY employee_id
        """)
        approved_reports = await cur_app_rep.fetchall()
        for row in approved_reports:
            emp_id = row[0]
            total_sold = row[1] or 0
            if total_sold > 0:
                c_sold = await conn.execute("SELECT COUNT(*) FROM sim_cards WHERE employee_id = ? AND status = 'SOLD'", (emp_id,))
                already_sold = (await c_sold.fetchone())[0]
                diff = total_sold - already_sold
                if diff > 0:
                    await conn.execute("""
                        UPDATE sim_cards 
                        SET status = 'SOLD', sold_at = CURRENT_TIMESTAMP
                        WHERE id IN (
                            SELECT id FROM sim_cards 
                            WHERE employee_id = ? AND status = 'GIVEN'
                            ORDER BY id ASC
                            LIMIT ?
                        )
                    """, (emp_id, diff))

        # RAHBAR_ID foydalanuvchisini ADMIN sifatida tekshirish va yaratish
        from app.config import RAHBAR_ID
        if RAHBAR_ID and RAHBAR_ID.isdigit():
            rahbar_tg_id = int(RAHBAR_ID)
            cursor = await conn.execute("SELECT * FROM users WHERE telegram_id = ?", (rahbar_tg_id,))
            rahbar_user = await cursor.fetchone()
            if not rahbar_user:
                rahbar_pwd = hash_password(str(rahbar_tg_id))
                await conn.execute("""
                INSERT INTO users (telegram_id, full_name, role, password_hash, debt_amount, is_active)
                VALUES (?, 'Bosh Rahbar', 'ADMIN', ?, 0, 1)
                """, (rahbar_tg_id, rahbar_pwd))
            else:
                # Agar mavjud bo'lsa, rolini ADMIN deb yangilaymiz
                await conn.execute("UPDATE users SET role = 'ADMIN', is_active = 1 WHERE id = ?", (rahbar_user["id"],))

        await conn.commit()
