import sqlite3

DB_NAME = "db.sqlite3"

# Global connection for use in bot handlers
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cur = conn.cursor()

# One-time init during startup
def initialize_database():
    with sqlite3.connect(DB_NAME) as init_conn:
        cur = init_conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            balance REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            txn_id TEXT UNIQUE,
            status TEXT DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_id TEXT,
            service_name TEXT,
            link TEXT,
            quantity INTEGER,
            price REAL,
            status TEXT
        );
        """)
        init_conn.commit()
