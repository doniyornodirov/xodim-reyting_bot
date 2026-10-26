import sqlite3

def clear_history():
    conn = sqlite3.connect("xodim_reyting.db")
    cursor = conn.cursor()

    tables_to_clear = [
        "card_topups",
        "given_amounts",
        "daily_reports",
        "cashier_handovers",
        "cashier_history",
        "otp_codes",
        "audit_logs",
        "sim_cards",
        "sim_distributions"
    ]

    results = {}
    for table in tables_to_clear:
        cursor.execute(f"DELETE FROM {table}")
        results[table] = cursor.rowcount

    cursor.execute("UPDATE users SET debt_amount = 0.0")
    results["users_debt_reset"] = cursor.rowcount

    try:
        cursor.execute("DELETE FROM sqlite_sequence WHERE name NOT IN ('users', 'system_settings')")
    except Exception:
        pass

    conn.commit()
    cursor.execute("VACUUM")
    conn.close()

    print("Tozalash yakunlandi:")
    for k, v in results.items():
        print(f"  - {k}: {v} ta yozuv tozalandi")

if __name__ == "__main__":
    clear_history()
