-- =========================================================================
-- Xodim-Reyting & Paynet CRM: Supabase / PostgreSQL Mukammal Sxemasi (v2.0)
-- Barcha 15 ta jadval, kompozit indekslar va boshlang'ich sozlamalar
-- =========================================================================

-- 0. Tashkilotlar va firmalar (Multi-Tenant SaaS: companies)
CREATE TABLE IF NOT EXISTS companies (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    telegram_group_id TEXT,
    owner_telegram_id BIGINT,
    owner_phone TEXT,
    owner_extra_contact TEXT,
    company_inn TEXT,
    notes TEXT,
    plan TEXT DEFAULT 'STANDARD',
    subscription_expires_at TIMESTAMPTZ,
    max_employees INTEGER NOT NULL DEFAULT 20,
    card_surcharge_percent INTEGER NOT NULL DEFAULT 3,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Bosh Tashkilot (ID=1)
INSERT INTO companies (id, name, slug, telegram_group_id, owner_telegram_id, plan, max_employees, is_active)
VALUES (1, 'Bosh Tashkilot', 'bosh-tashkilot', '-5381348358', 8686341550, 'UNLIMITED', 9999, 1)
ON CONFLICT (id) DO UPDATE SET max_employees = 9999, is_active = 1;

-- 0.1 Tartib raqamlari hisoblagichi (Atomic Sequence Counters)
CREATE TABLE IF NOT EXISTS company_counters (
    company_id BIGINT PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    last_transaction_number BIGINT NOT NULL DEFAULT 100
);
INSERT INTO company_counters (company_id, last_transaction_number)
VALUES (1, 100)
ON CONFLICT (company_id) DO NOTHING;

-- 1. Foydalanuvchilar (users)
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT REFERENCES companies(id) ON DELETE CASCADE,
    telegram_id BIGINT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'EMPLOYEE', -- 'ADMIN', 'CASHIER', 'EMPLOYEE', 'DEVELOPER'
    password_hash TEXT NOT NULL,
    debt_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_latitude DOUBLE PRECISION,
    last_longitude DOUBLE PRECISION,
    last_distance_meters DOUBLE PRECISION,
    last_location_updated_at TIMESTAMPTZ,
    workplace_name TEXT DEFAULT 'Ish joyi',
    workplace_latitude DOUBLE PRECISION,
    workplace_longitude DOUBLE PRECISION,
    workplace_radius_meters INTEGER DEFAULT 50,
    work_start_time TEXT DEFAULT '09:00',
    work_end_time TEXT DEFAULT '19:00',
    shift_status TEXT DEFAULT 'WORKING',
    last_motion_at TIMESTAMPTZ,
    stillness_state TEXT DEFAULT 'ACTIVE',
    is_charging INTEGER DEFAULT 0,
    last_motion_lat DOUBLE PRECISION,
    last_motion_lon DOUBLE PRECISION,
    bound_device_token TEXT,
    bound_device_name TEXT,
    device_bound_at TIMESTAMPTZ,
    allow_device_reset INTEGER DEFAULT 0,
    loc_state TEXT DEFAULT 'INSIDE',
    loc_state_changed_at TIMESTAMPTZ,
    loc_max_distance DOUBLE PRECISION DEFAULT 0.0,
    loc_signal_lost_at TIMESTAMPTZ,
    loc_last_event_id BIGINT
);

-- 2. Karta to'ldirish so'rovlari (card_topups)
CREATE TABLE IF NOT EXISTS card_topups (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
    transaction_number BIGINT NOT NULL,
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_number TEXT NOT NULL,
    card_holder TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    surcharge_amount DOUBLE PRECISION NOT NULL,
    surcharge_percent INTEGER NOT NULL DEFAULT 3,
    status TEXT NOT NULL DEFAULT 'PENDING',
    telegram_message_id BIGINT,
    approved_by_name TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Berilgan summalar (given_amounts)
CREATE TABLE IF NOT EXISTS given_amounts (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount DOUBLE PRECISION NOT NULL,
    comment TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    approved_by_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. Kunlik hisobotlar (daily_reports)
CREATE TABLE IF NOT EXISTS daily_reports (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
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
    status TEXT NOT NULL DEFAULT 'PENDING',
    reviewed_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(employee_id, report_date)
);

-- 5. Kassir topshirgan summalar (cashier_handovers)
CREATE TABLE IF NOT EXISTS cashier_handovers (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
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
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
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

-- 8. Tizim audit jurnali (audit_logs)
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
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
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
    serial_number TEXT NOT NULL,
    operator_type TEXT NOT NULL DEFAULT 'Uzmobile',
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    distributed_by_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'GIVEN',
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
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
    operator_type TEXT NOT NULL DEFAULT 'Uzmobile',
    start_serial TEXT NOT NULL,
    end_serial TEXT NOT NULL,
    total_count INTEGER NOT NULL,
    employee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    distributed_by_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'GIVEN',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 12. Lidlar (leads)
CREATE TABLE IF NOT EXISTS leads (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    source TEXT DEFAULT 'WEBSITE',
    status TEXT DEFAULT 'NEW',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 13. Xodimlarning geolokatsiya va jonli monitoring tarixi (location_events)
CREATE TABLE IF NOT EXISTS location_events (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL DEFAULT 1 REFERENCES companies(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_date VARCHAR(20) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER DEFAULT 0,
    distance_meters DOUBLE PRECISION DEFAULT 0.0,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- INDEKSLAR (High-Load Performance & Rolling 90-Day Retention Cleanup)
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_card_topups_date ON card_topups(created_at);
CREATE INDEX IF NOT EXISTS idx_card_topups_company ON card_topups(company_id);
CREATE INDEX IF NOT EXISTS idx_card_topups_number ON card_topups(card_number);
CREATE INDEX IF NOT EXISTS idx_given_amounts_date ON given_amounts(created_at);
CREATE INDEX IF NOT EXISTS idx_given_amounts_company ON given_amounts(company_id);
CREATE INDEX IF NOT EXISTS idx_daily_reports_emp_date ON daily_reports(employee_id, report_date);
CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_daily_reports_company ON daily_reports(company_id);
CREATE INDEX IF NOT EXISTS idx_cashier_handovers_date ON cashier_handovers(handover_date);
CREATE INDEX IF NOT EXISTS idx_cashier_handovers_created ON cashier_handovers(created_at);
CREATE INDEX IF NOT EXISTS idx_cashier_handovers_company ON cashier_handovers(company_id);
CREATE INDEX IF NOT EXISTS idx_cashier_history_created ON cashier_history(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_otp_codes_created ON otp_codes(created_at);
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sim_cards_comp_op_serial ON sim_cards(company_id, operator_type, serial_number);
CREATE INDEX IF NOT EXISTS idx_sim_cards_serial ON sim_cards(serial_number);
CREATE INDEX IF NOT EXISTS idx_sim_cards_employee ON sim_cards(employee_id);
CREATE INDEX IF NOT EXISTS idx_sim_cards_operator ON sim_cards(operator_type);
CREATE INDEX IF NOT EXISTS idx_sim_cards_company ON sim_cards(company_id);
CREATE INDEX IF NOT EXISTS idx_sim_cards_sold ON sim_cards(status, sold_at);
CREATE INDEX IF NOT EXISTS idx_sim_distributions_created ON sim_distributions(created_at);
CREATE INDEX IF NOT EXISTS idx_location_events_user_date ON location_events(user_id, event_date);
CREATE INDEX IF NOT EXISTS idx_location_events_company_date ON location_events(company_id, event_date);
CREATE INDEX IF NOT EXISTS idx_location_events_type ON location_events(event_type);
CREATE INDEX IF NOT EXISTS idx_location_events_created ON location_events(created_at);

-- =========================================================================
-- BOSHLANG'ICH SOZLAMALAR VA ADMINLAR
-- =========================================================================
INSERT INTO system_settings (key, value)
VALUES ('usd_rate', '12000')
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_settings (key, value)
VALUES ('workplace_lat', '0')
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_settings (key, value)
VALUES ('workplace_lon', '0')
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_settings (key, value)
VALUES ('workplace_radius', '50')
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_settings (key, value)
VALUES ('workplace_name', 'Bosh Ofis')
ON CONFLICT (key) DO NOTHING;

-- Boshlang'ich Bosh Rahbar (8686341550)
INSERT INTO users (company_id, telegram_id, full_name, role, password_hash, debt_amount, is_active)
VALUES (1, 8686341550, 'Bosh Rahbar', 'ADMIN', '$2b$12$3iXmfAnXHpmvi8tVlH8Vh.bb6lZ5XzDO7FQQsucpNRN7kekLqU7Ke', 0, 1)
ON CONFLICT (telegram_id) DO UPDATE SET role = 'ADMIN', is_active = 1;

-- Boshlang'ich Dasturchi Admin (8694797293) - Platforma egasi, birorta firmaga tegishli emas (company_id = NULL)
INSERT INTO users (company_id, telegram_id, full_name, role, password_hash, debt_amount, is_active)
VALUES (NULL, 8694797293, 'Dasturchi Admin', 'DEVELOPER', '$2b$12$9A7iQ..ARjY8RfM9a4Eyle3G4oaiuOqnjqEV9HOOhOiGC0i2NHSlK', 0, 1)
ON CONFLICT (telegram_id) DO UPDATE SET role = 'DEVELOPER', company_id = NULL, is_active = 1;

-- =========================================================================
-- SQLITE MOSLASHUVCHAN HELPER FUNKSIYALARI (SCALAR MAX / MIN)
-- =========================================================================
CREATE OR REPLACE FUNCTION max(a numeric, b numeric) RETURNS numeric AS 'SELECT GREATEST(a, b);' LANGUAGE sql IMMUTABLE;
CREATE OR REPLACE FUNCTION max(a bigint, b bigint) RETURNS bigint AS 'SELECT GREATEST(a, b);' LANGUAGE sql IMMUTABLE;
CREATE OR REPLACE FUNCTION max(a double precision, b double precision) RETURNS double precision AS 'SELECT GREATEST(a, b);' LANGUAGE sql IMMUTABLE;
CREATE OR REPLACE FUNCTION min(a numeric, b numeric) RETURNS numeric AS 'SELECT LEAST(a, b);' LANGUAGE sql IMMUTABLE;
CREATE OR REPLACE FUNCTION min(a bigint, b bigint) RETURNS bigint AS 'SELECT LEAST(a, b);' LANGUAGE sql IMMUTABLE;
CREATE OR REPLACE FUNCTION min(a double precision, b double precision) RETURNS double precision AS 'SELECT LEAST(a, b);' LANGUAGE sql IMMUTABLE;
