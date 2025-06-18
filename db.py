# --- DB Connection & Initialization ---
import sqlite3

# Shared connection for reuse
conn = sqlite3.connect("db.sqlite3", check_same_thread=False)
cur = conn.cursor()

def initialize_database():
    """Creates necessary tables if they don't exist."""
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
    conn.commit()
