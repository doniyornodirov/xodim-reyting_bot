-- =========================================================================
-- Xodim-Reyting & Paynet CRM: Supabase / Managed PostgreSQL Sxemasi
-- Loyiha: https://github.com/Doniyor/Xodim-reyting
-- Maqsad: Supabase / Neon / AWS RDS / Railway PostgreSQL uchun to'liq sxema
-- =========================================================================

-- 1. Foydalanuvchilar (users)
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'EMPLOYEE', -- 'ADMIN', 'CASHIER', 'EMPLOYEE'
    password_hash TEXT NOT NULL,
    debt_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. Karta to'ldirish so'rovlari (card_topups)
CREATE TABLE IF NOT EXISTS card_topups (
    id BIGSERIAL PRIMARY KEY,
    transaction_number BIGINT NOT NULL,
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_number TEXT NOT NULL,
    card_holder TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    surcharge_amount DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED'
    telegram_message_id BIGINT,
    approved_by_name TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Berilgan summalar (given_amounts)
CREATE TABLE IF NOT EXISTS given_amounts (
    id BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount DOUBLE PRECISION NOT NULL,
    comment TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED'
    approved_by_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. Kunlik hisobotlar (daily_reports)
CREATE TABLE IF NOT EXISTS daily_reports (
    id BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    report_date DATE NOT NULL,
    paynet DOUBLE PRECISION NOT NULL DEFAULT 0,
    card_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    leviy DOUBLE PRECISION NOT NULL DEFAULT 0,
    debt_snapshot DOUBLE PRECISION NOT NULL DEFAULT 0,
    debt_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
    sim_cards_count INTEGER NOT NULL DEFAULT 0,
    kunlik DOUBLE PRECISION NOT NULL DEFAULT 0,
    terminal DOUBLE PRECISION NOT NULL DEFAULT 0,
    given_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    skidka DOUBLE PRECISION NOT NULL DEFAULT 0,
    xarajat DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_inflow DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_outflow DOUBLE PRECISION NOT NULL DEFAULT 0,
    net_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    comment TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED'
    reviewed_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(employee_id, report_date)
);

-- 5. Kassir topshirgan summalar (cashier_handovers)
CREATE TABLE IF NOT EXISTS cashier_handovers (
    id BIGSERIAL PRIMARY KEY,
    cashier_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    handover_date DATE NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    amount_uzs DOUBLE PRECISION NOT NULL DEFAULT 0,
    amount_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    usd_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 6. Kassirlik tarixi (cashier_history)
CREATE TABLE IF NOT EXISTS cashier_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL, -- 'APPOINTED', 'DISMISSED'
    assigned_by_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 7. Bir martalik tasdiqlash kodlari (otp_codes)
CREATE TABLE IF NOT EXISTS otp_codes (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    code TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    is_used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 8. Tizim audit jurnali (audit_logs - Append Only)
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    actor_name TEXT,
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 9. Sim-kartalar hisobi (sim_cards)
CREATE TABLE IF NOT EXISTS sim_cards (
    id BIGSERIAL PRIMARY KEY,
    serial_number TEXT UNIQUE NOT NULL,
    operator_type TEXT NOT NULL DEFAULT 'Uzmobile',
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    distributed_by_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'GIVEN', -- 'GIVEN', 'SOLD'
    distributed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    sold_at TIMESTAMPTZ
);

-- 10. Tizim sozlamalari (system_settings)
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 11. Sim-kartalar tarqatish partiyalari (sim_distributions)
CREATE TABLE IF NOT EXISTS sim_distributions (
    id BIGSERIAL PRIMARY KEY,
    operator_type TEXT NOT NULL DEFAULT 'Uzmobile',
    start_serial TEXT NOT NULL,
    end_serial TEXT NOT NULL,
    total_count INTEGER NOT NULL,
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    distributed_by_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'GIVEN',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- INDEKSLAR (High-Load Performance & Rolling 90-Day Retention Cleanup)
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_card_topups_date ON card_topups(created_at);
CREATE INDEX IF NOT EXISTS idx_card_topups_number ON card_topups(card_number);
CREATE INDEX IF NOT EXISTS idx_given_amounts_date ON given_amounts(created_at);
CREATE INDEX IF NOT EXISTS idx_daily_reports_emp_date ON daily_reports(employee_id, report_date);
CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_cashier_handovers_date ON cashier_handovers(handover_date);
CREATE INDEX IF NOT EXISTS idx_cashier_handovers_created ON cashier_handovers(created_at);
CREATE INDEX IF NOT EXISTS idx_cashier_history_created ON cashier_history(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_otp_codes_created ON otp_codes(created_at);
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_sim_cards_serial ON sim_cards(serial_number);
CREATE INDEX IF NOT EXISTS idx_sim_cards_employee ON sim_cards(employee_id);
CREATE INDEX IF NOT EXISTS idx_sim_cards_operator ON sim_cards(operator_type);
CREATE INDEX IF NOT EXISTS idx_sim_cards_sold ON sim_cards(status, sold_at);
CREATE INDEX IF NOT EXISTS idx_sim_distributions_created ON sim_distributions(created_at);

-- Standart tizim dollar kursi
INSERT INTO system_settings (key, value)
VALUES ('usd_rate', '12000')
ON CONFLICT (key) DO NOTHING;

-- Boshlang'ich Bosh Rahbar (Agar mavjud bo'lmasa)
-- Telegram ID: 8686341550, Boshlang'ich parol: 8686341550 (bcrypt xeshi)
INSERT INTO users (telegram_id, full_name, role, password_hash, debt_amount, is_active)
VALUES (8686341550, 'Bosh Rahbar', 'ADMIN', '$2b$12$60/q787aI6a5f78sW7Q7z.0yZ62u8h4c8w6964kU0172h/365516S', 0, 1)
ON CONFLICT (telegram_id) DO UPDATE SET role = 'ADMIN', is_active = 1;
