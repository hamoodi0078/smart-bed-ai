"""One-time migration: add missing columns to the users table."""
import sqlite3

DB_PATH = "data/manues.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

existing = [row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()]
print(f"Existing columns: {existing}")

migrations = [
    ("role", "ALTER TABLE users ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT 'user'"),
    ("is_active", "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"),
    ("last_login", "ALTER TABLE users ADD COLUMN last_login DATETIME"),
]

for col, sql in migrations:
    if col not in existing:
        cursor.execute(sql)
        print(f"  Added column: {col}")
    else:
        print(f"  Column already exists: {col}")

conn.commit()
conn.close()
print("Database schema updated successfully!")
