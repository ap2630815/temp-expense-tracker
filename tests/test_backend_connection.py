import pytest

import app as app_module
from database import db


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.seed_db()
    return db.get_user_by_email("demo@spendly.com")["id"]


@pytest.fixture
def empty_user_id(seeded_db):
    return db.create_user("New Person", "new@example.com", "hash")


@pytest.fixture
def client(seeded_db):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def log_in(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


class TestBuildSummary:
    def test_seeded_user(self, seeded_db):
        summary = app_module.build_summary(seeded_db)
        assert summary["total_spent"] == pytest.approx(279.54)
        assert summary["transaction_count"] == 8
        assert summary["top_category"] == "Shopping"

    def test_user_without_expenses(self, empty_user_id):
        assert app_module.build_summary(empty_user_id) == {
            "total_spent": 0,
            "transaction_count": 0,
            "top_category": "—",
        }


class TestBuildTransactions:
    def test_newest_first_with_expected_fields(self, seeded_db):
        transactions = app_module.build_transactions(seeded_db)
        assert len(transactions) == 8
        assert transactions[0] == {
            "date": "24 Sep 2026",
            "description": "Groceries - weekly shop",
            "category": "Food",
            "amount": 42.30,
        }
        assert transactions[-1]["date"] == "01 Sep 2026"

    def test_limited_to_ten(self, seeded_db):
        conn = db.get_db()
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date) "
            "VALUES (?, ?, ?, ?)",
            [(seeded_db, 1.0, "Food", "2026-09-25")] * 5,
        )
        conn.commit()
        conn.close()
        transactions = app_module.build_transactions(seeded_db)
        assert len(transactions) == 10
        # Missing description falls back to the category name.
        assert transactions[0]["description"] == "Food"

    def test_user_without_expenses(self, empty_user_id):
        assert app_module.build_transactions(empty_user_id) == []


class TestBuildCategoryBreakdown:
    def test_seeded_user(self, seeded_db):
        breakdown = app_module.build_category_breakdown(seeded_db)
        assert len(breakdown) == 7
        assert [c["amount"] for c in breakdown] == sorted(
            (c["amount"] for c in breakdown), reverse=True
        )
        assert breakdown[0]["category"] == "Shopping"
        assert breakdown[0]["percent"] == 100
        assert all(isinstance(c["pct"], int) for c in breakdown)
        assert sum(c["pct"] for c in breakdown) == 100

    def test_user_without_expenses(self, empty_user_id):
        assert app_module.build_category_breakdown(empty_user_id) == []


class TestProfileRoute:
    def test_requires_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")

    def test_seeded_user_sees_own_data(self, client, seeded_db):
        log_in(client, seeded_db)
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Demo User" in body
        assert "demo@spendly.com" in body
        assert "₹279.54" in body
        assert "Shopping" in body

    def test_new_user_sees_empty_state(self, client, empty_user_id):
        log_in(client, empty_user_id)
        response = client.get("/profile")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "₹0.00" in body
        assert "—" in body
