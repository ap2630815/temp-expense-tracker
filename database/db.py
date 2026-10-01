import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

DB_PATH = Path(__file__).resolve().parent.parent / "spendly.db"

EXPENSE_CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)


def get_db(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    conn.commit()

    if own_conn:
        conn.close()


def seed_db(conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    existing = conn.execute("SELECT id FROM users LIMIT 1").fetchone()

    if existing is None:
        password_hash = generate_password_hash("demo123")
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", password_hash),
        )
        user_id = cursor.lastrowid

        sample_expenses = [
            (user_id, 4.50, "Food", "Coffee at local cafe", "2026-09-01"),
            (user_id, 32.00, "Transport", "Gas fill-up", "2026-09-03"),
            (user_id, 60.00, "Bills", "Internet bill", "2026-09-05"),
            (user_id, 25.75, "Health", "Pharmacy - vitamins", "2026-09-08"),
            (user_id, 15.00, "Entertainment", "Movie ticket", "2026-09-12"),
            (user_id, 89.99, "Shopping", "New running shoes", "2026-09-16"),
            (user_id, 10.00, "Other", "Donation to charity", "2026-09-20"),
            (user_id, 42.30, "Food", "Groceries - weekly shop", "2026-09-24"),
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, description, date) "
            "VALUES (?, ?, ?, ?, ?)",
            sample_expenses,
        )
        conn.commit()

    if own_conn:
        conn.close()


def create_user(name, email, password_hash, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
    finally:
        if own_conn:
            conn.close()

    return cursor.lastrowid


def get_user_by_email(email, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        if own_conn:
            conn.close()

    return row


def get_user_by_id(user_id, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        if own_conn:
            conn.close()

    return row


def create_expense(user_id, amount, category, description, date, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, description, date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, description, date),
        )
        conn.commit()
    finally:
        if own_conn:
            conn.close()

    return cursor.lastrowid


def _date_clause(date_from, date_to):
    clause = ""
    params = []
    if date_from:
        clause += " AND date >= ?"
        params.append(date_from)
    if date_to:
        clause += " AND date <= ?"
        params.append(date_to)
    return clause, params


def get_expense_summary(user_id, date_from=None, date_to=None, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    date_sql, date_params = _date_clause(date_from, date_to)
    params = (user_id, *date_params)

    try:
        totals = conn.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total "
            "FROM expenses WHERE user_id = ?" + date_sql,
            params,
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?" + date_sql +
            " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            params,
        ).fetchone()
    finally:
        if own_conn:
            conn.close()

    return {
        "total_spent": totals["total"],
        "transaction_count": totals["count"],
        "top_category": top["category"] if top else None,
    }


def get_recent_transactions(user_id, limit=5, date_from=None, date_to=None, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    date_sql, date_params = _date_clause(date_from, date_to)

    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ?" + date_sql +
            " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *date_params, limit),
        ).fetchall()
    finally:
        if own_conn:
            conn.close()

    return rows


def get_category_breakdown(user_id, date_from=None, date_to=None, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    date_sql, date_params = _date_clause(date_from, date_to)

    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ?" + date_sql +
            " GROUP BY category ORDER BY total DESC",
            (user_id, *date_params),
        ).fetchall()
    finally:
        if own_conn:
            conn.close()

    if not rows:
        return []

    max_total = rows[0]["total"]
    return [
        {
            "category": row["category"],
            "amount": row["total"],
            "percent": round(row["total"] / max_total * 100),
        }
        for row in rows
    ]


if __name__ == "__main__":
    conn = get_db()
    init_db(conn)
    seed_db(conn)
    conn.close()
    print(f"Database initialized at {DB_PATH}")
