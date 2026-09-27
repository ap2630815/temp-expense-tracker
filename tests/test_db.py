import sqlite3

import pytest

from database import db


@pytest.fixture
def conn(tmp_path):
    connection = db.get_db(tmp_path / "test.db")
    yield connection
    connection.close()


class TestGetDb:
    def test_returns_connection_with_row_factory(self, conn):
        assert conn.row_factory is sqlite3.Row

    def test_foreign_keys_pragma_enabled(self, conn):
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1


class TestInitDb:
    def test_creates_users_and_expenses_tables(self, conn):
        db.init_db(conn)

        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "users" in tables
        assert "expenses" in tables

    def test_is_idempotent(self, conn):
        db.init_db(conn)
        db.init_db(conn)

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchall()
        assert len(tables) == 1


class TestSeedDb:
    def test_inserts_demo_user_and_expenses(self, conn):
        db.init_db(conn)
        db.seed_db(conn)

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()
        assert user is not None
        assert user["name"] == "Demo User"
        assert user["password_hash"] != "demo123"

        expenses = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user["id"],)
        ).fetchall()
        assert len(expenses) == 8

        categories = {row["category"] for row in expenses}
        expected_categories = {
            "Food", "Transport", "Bills", "Health",
            "Entertainment", "Shopping", "Other",
        }
        assert expected_categories.issubset(categories)

    def test_does_not_reseed_if_users_exist(self, conn):
        db.init_db(conn)
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Someone Else", "other@example.com", "hash"),
        )
        conn.commit()

        db.seed_db(conn)

        users = conn.execute("SELECT * FROM users").fetchall()
        assert len(users) == 1
        assert users[0]["email"] == "other@example.com"

        expenses = conn.execute("SELECT * FROM expenses").fetchall()
        assert len(expenses) == 0

    def test_is_idempotent(self, conn):
        db.init_db(conn)
        db.seed_db(conn)
        db.seed_db(conn)

        users = conn.execute(
            "SELECT * FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchall()
        assert len(users) == 1

        expenses = conn.execute("SELECT * FROM expenses").fetchall()
        assert len(expenses) == 8
