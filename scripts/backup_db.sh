#!/usr/bin/env bash
# =========================================================================
# Avtomatik Ma'lumotlar Bazasi Zaxiralash Skripti (Daily Backup)
# Har kecha cron orqali avtomatik zaxiralaydi (masalan: 03:00 da)
# Cron o'rnatish: 0 3 * * * /var/www/xodim-reyting/scripts/backup_db.sh
# =========================================================================

set -e

BACKUP_DIR="/var/backups/xodim-reyting"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR"

echo "[$TIMESTAMP] Zaxiralash boshlandi..."

# 1. Agar PostgreSQL bo'lsa (Supabase / Docker PostgreSQL)
if [ -n "$DATABASE_URL" ]; then
    echo "PostgreSQL bazasini zaxiralash..."
    pg_dump "$DATABASE_URL" | gzip > "$BACKUP_DIR/db_backup_$TIMESTAMP.sql.gz"
    echo "PostgreSQL zaxirasi saqlandi: $BACKUP_DIR/db_backup_$TIMESTAMP.sql.gz"
elif [ -f "./xodim_reyting.db" ]; then
    # 2. Agar SQLite bo'lsa
    echo "SQLite faylini zaxiralash..."
    sqlite3 ./xodim_reyting.db ".backup '$BACKUP_DIR/db_backup_$TIMESTAMP.sqlite'"
    gzip "$BACKUP_DIR/db_backup_$TIMESTAMP.sqlite"
    echo "SQLite zaxirasi saqlandi: $BACKUP_DIR/db_backup_$TIMESTAMP.sqlite.gz"
fi

# 3. 30 kundan eski zaxira fayllarini avtomatik tozalash (Retention)
find "$BACKUP_DIR" -type f -name "db_backup_*.gz" -mtime +30 -delete

echo "[$TIMESTAMP] Zaxiralash muvaffaqiyatli yakunlandi!"
