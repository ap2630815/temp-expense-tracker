"""Tests for Step 9: Delete Expense (GET/POST /expenses/<id>/delete).

Written from the feature spec (.claude/specs/09-delete-expense.md).

Seed demo user (demo@spendly.com / demo123): 8 expenses in Sep 2026, total
279.54. Each test gets a "target" expense owned by the demo user (20.00, Food,
2026-09-30, "Target lunch") and a second user (other@example.com) with one
expense. "Today" is monkeypatched to 2026-09-30.
"""
import re
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import app as app_module
import database.db as db_module

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
OTHER_EMAIL = "other@example.com"
OTHER_PASSWORD = "otherpass123"
OTHER_DESCRIPTION = "OTHER-USER-SECRET-PURCHASE"
TARGET_DESCRIPTION = "Target lunch"

TODAY = "2026-09-30"
SUCCESS_MESSAGE = "Expense deleted."
MISSING_ID = 424242


# ------------------------------------------------------------------ #
# Fixtures and helpers                                                #
# ------------------------------------------------------------------ #

@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_spendly.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)

    conn = db_module.get_db()
    db_module.init_db(conn)
    db_module.seed_db(conn)

    other_id = db_module.create_user(
        "Other Person", OTHER_EMAIL, generate_password_hash(OTHER_PASSWORD), conn=conn
    )
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, description, date) "
        "VALUES (?, ?, ?, ?, ?)",
        (other_id, 999.00, "Travel", OTHER_DESCRIPTION, "2026-09-10"),
    )
    demo_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, description, date) "
        "VALUES (?, ?, ?, ?, ?)",
        (demo_id, 20.00, "Food", TARGET_DESCRIPTION, TODAY),
    )
    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def client(seeded_db, monkeypatch):
    monkeypatch.setattr(app_module, "_today", lambda: date(2026, 9, 30))
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as test_client:
        yield test_client


def log_in(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture
def auth_client(client):
    log_in(client)
    return client


def page(response):
    return response.get_data(as_text=True)


def query(sql, params=()):
    conn = db_module.get_db()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def user_id_of(email):
    return query("SELECT id FROM users WHERE email = ?", (email,))[0]["id"]


def expense_count():
    return query("SELECT COUNT(*) AS c FROM expenses")[0]["c"]


def get_row(expense_id):
    rows = query("SELECT * FROM expenses WHERE id = ?", (expense_id,))
    return dict(rows[0]) if rows else None


def all_rows_except(expense_id):
    return [
        dict(r)
        for r in query("SELECT * FROM expenses WHERE id != ? ORDER BY id", (expense_id,))
    ]


@pytest.fixture
def target_id(seeded_db):
    return query("SELECT id FROM expenses WHERE description = ?", (TARGET_DESCRIPTION,))[0]["id"]


@pytest.fixture
def other_expense_id(seeded_db):
    return query("SELECT id FROM expenses WHERE description = ?", (OTHER_DESCRIPTION,))[0]["id"]


@pytest.fixture
def target_before(target_id):
    return get_row(target_id)


def delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


def post_delete(client, expense_id, **data):
    return client.post(delete_url(expense_id), data=data)


def stat_count(text):
    match = re.search(r"Transactions\s*</span>\s*<span[^>]*>\s*(\d+)\s*</span>", text)
    assert match, "Could not find the Transactions stat"
    return int(match.group(1))


def stat_total(text):
    match = re.search(r"Total spent\s*</span>\s*<span[^>]*>\s*(₹[\d,\.]+)\s*</span>", text)
    assert match, "Could not find the Total spent stat"
    return match.group(1)


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_post_logged_out_redirects_to_login(self, client, target_id):
        response = post_delete(client, target_id)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_logged_out_does_not_delete(self, client, target_id, target_before):
        post_delete(client, target_id)
        assert get_row(target_id) == target_before

    def test_logged_out_missing_id_redirects_not_404(self, client):
        response = client.post(delete_url(MISSING_ID))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ------------------------------------------------------------------ #
# 404 handling and ownership                                          #
# ------------------------------------------------------------------ #

class TestNotFoundAndOwnership:
    def test_post_missing_id_returns_404(self, auth_client):
        before = expense_count()
        assert post_delete(auth_client, MISSING_ID).status_code == 404
        assert expense_count() == before

    def test_post_other_users_expense_returns_404_and_row_remains(
        self, auth_client, other_expense_id
    ):
        before = get_row(other_expense_id)
        response = post_delete(auth_client, other_expense_id)
        assert response.status_code == 404
        assert get_row(other_expense_id) == before, "Foreign expense must remain"

    def test_other_user_cannot_delete_demo_expense(self, client, target_id, target_before):
        log_in(client, OTHER_EMAIL, OTHER_PASSWORD)
        assert post_delete(client, target_id).status_code == 404
        assert get_row(target_id) == target_before

    def test_foreign_404_matches_missing_404(self, auth_client, other_expense_id):
        foreign = post_delete(auth_client, other_expense_id)
        missing = post_delete(auth_client, MISSING_ID)
        assert foreign.status_code == missing.status_code == 404

    def test_non_integer_id_returns_404(self, auth_client):
        assert auth_client.post("/expenses/abc/delete").status_code == 404


# ------------------------------------------------------------------ #
# GET is not allowed (deletion is POST-only, confirmed by a popup)    #
# ------------------------------------------------------------------ #

class TestGetNotAllowed:
    def test_get_returns_405(self, auth_client, target_id):
        assert auth_client.get(delete_url(target_id)).status_code == 405

    def test_get_logged_out_returns_405(self, client, target_id):
        assert client.get(delete_url(target_id)).status_code == 405

    def test_get_does_not_delete(self, auth_client, target_id, target_before):
        count = expense_count()
        auth_client.get(delete_url(target_id))
        assert get_row(target_id) == target_before
        assert expense_count() == count

    def test_no_confirmation_template_route(self, auth_client, target_id):
        assert TARGET_DESCRIPTION not in page(auth_client.get(delete_url(target_id)))


# ------------------------------------------------------------------ #
# POST delete                                                         #
# ------------------------------------------------------------------ #

class TestPostDelete:
    def test_post_redirects_to_profile(self, auth_client, target_id):
        response = post_delete(auth_client, target_id)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")

    def test_post_removes_row_from_db(self, auth_client, target_id):
        count = expense_count()
        post_delete(auth_client, target_id)
        assert get_row(target_id) is None, "Row should be deleted"
        assert expense_count() == count - 1

    def test_post_flashes_message_on_profile(self, auth_client, target_id):
        response = auth_client.post(delete_url(target_id), follow_redirects=True)
        assert response.status_code == 200
        assert SUCCESS_MESSAGE in page(response)

    def test_flash_not_shown_twice(self, auth_client, target_id):
        post_delete(auth_client, target_id)
        auth_client.get("/profile")
        assert SUCCESS_MESSAGE not in page(auth_client.get("/profile"))

    def test_row_gone_from_profile(self, auth_client, target_id):
        assert TARGET_DESCRIPTION in page(auth_client.get("/profile"))
        post_delete(auth_client, target_id)
        assert TARGET_DESCRIPTION not in page(auth_client.get("/profile"))

    def test_second_post_returns_404(self, auth_client, target_id):
        assert post_delete(auth_client, target_id).status_code == 302
        assert post_delete(auth_client, target_id).status_code == 404

    def test_other_rows_untouched(self, auth_client, target_id, other_expense_id):
        before = all_rows_except(target_id)
        post_delete(auth_client, target_id)
        assert all_rows_except(target_id) == before
        assert get_row(other_expense_id) is not None

    def test_users_row_survives_delete(self, auth_client, target_id):
        users_before = [dict(r) for r in query("SELECT * FROM users ORDER BY id")]
        post_delete(auth_client, target_id)
        assert [dict(r) for r in query("SELECT * FROM users ORDER BY id")] == users_before

    def test_delete_one_of_many_demo_expenses_leaves_the_rest(self, auth_client, target_id):
        demo_id = user_id_of(DEMO_EMAIL)
        remaining = {
            r["id"] for r in query(
                "SELECT id FROM expenses WHERE user_id = ? AND id != ?", (demo_id, target_id)
            )
        }
        assert remaining, "Seed should provide other demo expenses"
        post_delete(auth_client, target_id)
        after = {
            r["id"] for r in query("SELECT id FROM expenses WHERE user_id = ?", (demo_id,))
        }
        assert after == remaining

    def test_tampered_user_id_cannot_delete_foreign_expense(
        self, auth_client, other_expense_id
    ):
        """Claiming to be the foreign owner via form data must not help."""
        before = get_row(other_expense_id)
        response = post_delete(
            auth_client, other_expense_id, user_id=str(before["user_id"])
        )
        assert response.status_code == 404
        assert get_row(other_expense_id) == before

    def test_tampered_user_id_does_not_block_own_delete(self, auth_client, target_id):
        other_id = user_id_of(OTHER_EMAIL)
        response = post_delete(auth_client, target_id, user_id=str(other_id))
        assert response.status_code == 302
        assert get_row(target_id) is None

    def test_tampered_id_field_ignored(self, auth_client, target_id, other_expense_id):
        before = get_row(other_expense_id)
        post_delete(auth_client, target_id, id=str(other_expense_id))
        assert get_row(other_expense_id) == before
        assert get_row(target_id) is None

    def test_post_with_sql_injection_payload_in_form_is_harmless(
        self, auth_client, target_id
    ):
        count = expense_count()
        response = post_delete(auth_client, target_id, user_id="1 OR 1=1; --")
        assert response.status_code == 302
        assert expense_count() == count - 1, "Exactly one row should be deleted"


# ------------------------------------------------------------------ #
# Profile effects                                                     #
# ------------------------------------------------------------------ #

class TestProfileAfterDelete:
    def test_total_and_count_update(self, auth_client, target_id):
        before = page(auth_client.get("/profile"))
        assert stat_total(before) == "₹299.54", "Seed total 279.54 + target 20.00"
        post_delete(auth_client, target_id)
        after = page(auth_client.get("/profile"))
        assert stat_total(after) == "₹279.54"
        assert stat_count(after) == stat_count(before) - 1

    def test_category_breakdown_updates(self, auth_client, target_id):
        demo_id = user_id_of(DEMO_EMAIL)
        post_delete(auth_client, target_id)
        expected_food = query(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM expenses "
            "WHERE user_id = ? AND category = 'Food'",
            (demo_id,),
        )[0]["s"]
        text = page(auth_client.get("/profile"))
        breakdown = text[text.index("By category"):]
        if expected_food:
            assert f"₹{expected_food:,.2f}" in breakdown
        else:
            assert "Food" not in breakdown

    def test_foreign_expense_not_in_demo_profile(self, auth_client, target_id):
        post_delete(auth_client, target_id)
        assert OTHER_DESCRIPTION not in page(auth_client.get("/profile"))

    def test_deleting_all_expenses_shows_empty_state_without_error(self, auth_client):
        demo_id = user_id_of(DEMO_EMAIL)
        ids = [r["id"] for r in query("SELECT id FROM expenses WHERE user_id = ?", (demo_id,))]
        assert ids
        for expense_id in ids:
            assert post_delete(auth_client, expense_id).status_code == 302
        response = auth_client.get("/profile")
        assert response.status_code == 200
        text = page(response)
        assert stat_count(text) == 0
        assert stat_total(text) == "₹0.00"
        assert TARGET_DESCRIPTION not in text
        assert query("SELECT id FROM expenses WHERE user_id = ?", (demo_id,)) == []
        assert query(
            "SELECT id FROM expenses WHERE description = ?", (OTHER_DESCRIPTION,)
        ), "Other user's expense must survive"

    def test_profile_has_delete_form_per_row(self, auth_client, target_id):
        text = page(auth_client.get("/profile"))
        match = re.search(
            rf'<form\b[^>]*action="{re.escape(delete_url(target_id))}"[^>]*>', text
        )
        assert match, "Expected a delete form for the row"
        assert re.search(r'method="post"', match.group(0), re.IGNORECASE)

    def test_profile_delete_form_next_to_edit_link(self, auth_client, target_id):
        text = page(auth_client.get("/profile"))
        edit_pos = text.index(f'href="/expenses/{target_id}/edit"')
        delete_pos = text.index(f'action="{delete_url(target_id)}"')
        row_end = text.index("</tr>", edit_pos)
        assert edit_pos < delete_pos < row_end, "Delete should follow Edit in same row"

    def test_profile_delete_forms_count_matches_rows(self, auth_client):
        text = page(auth_client.get("/profile"))
        edit_links = re.findall(r'href="/expenses/\d+/edit"', text)
        delete_forms = re.findall(r'action="/expenses/\d+/delete"', text)
        assert edit_links
        assert len(delete_forms) == len(edit_links)

    def test_profile_has_confirmation_popup(self, auth_client):
        text = page(auth_client.get("/profile"))
        assert "<dialog" in text
        assert "data-confirm-delete" in text

    def test_delete_is_not_a_plain_link(self, auth_client):
        text = page(auth_client.get("/profile"))
        assert not re.search(r'<a\b[^>]*href="/expenses/\d+/delete"', text)


# ------------------------------------------------------------------ #
# Stale session (user no longer exists)                               #
# ------------------------------------------------------------------ #

GHOST_USER_ID = 987654


def make_stale_by_deleting_user(client):
    log_in(client, OTHER_EMAIL, OTHER_PASSWORD)
    other_id = user_id_of(OTHER_EMAIL)
    conn = db_module.get_db()
    try:
        conn.execute("DELETE FROM expenses WHERE user_id = ?", (other_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (other_id,))
        conn.commit()
    finally:
        conn.close()
    assert query("SELECT id FROM users WHERE id = ?", (other_id,)) == []


def make_stale_by_session(client):
    with client.session_transaction() as sess:
        sess["user_id"] = GHOST_USER_ID


@pytest.fixture(params=["deleted_user", "ghost_session_id"])
def stale_client(request, client):
    if request.param == "deleted_user":
        make_stale_by_deleting_user(client)
    else:
        make_stale_by_session(client)
    return client


class TestStaleSession:
    def test_post_redirects_to_login_not_500(self, stale_client, target_id):
        response = post_delete(stale_client, target_id)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_does_not_delete(self, stale_client, target_id, target_before):
        post_delete(stale_client, target_id)
        assert get_row(target_id) == target_before

    def test_post_missing_id_redirects_to_login(self, stale_client):
        response = post_delete(stale_client, MISSING_ID)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_clears_stale_session(self, stale_client, target_id):
        post_delete(stale_client, target_id)
        with stale_client.session_transaction() as sess:
            assert "user_id" not in sess


# ------------------------------------------------------------------ #
# DB helper                                                           #
# ------------------------------------------------------------------ #

class TestDeleteExpenseHelper:
    def test_delete_own_expense_returns_1(self, seeded_db, target_id):
        owner = user_id_of(DEMO_EMAIL)
        assert db_module.delete_expense(target_id, owner) == 1
        assert get_row(target_id) is None

    def test_delete_nonexistent_returns_0(self, seeded_db):
        count = expense_count()
        assert db_module.delete_expense(MISSING_ID, user_id_of(DEMO_EMAIL)) == 0
        assert expense_count() == count

    def test_delete_foreign_expense_returns_0_and_row_remains(
        self, seeded_db, other_expense_id
    ):
        before = get_row(other_expense_id)
        assert db_module.delete_expense(other_expense_id, user_id_of(DEMO_EMAIL)) == 0
        assert get_row(other_expense_id) == before

    def test_second_delete_returns_0(self, seeded_db, target_id):
        owner = user_id_of(DEMO_EMAIL)
        assert db_module.delete_expense(target_id, owner) == 1
        assert db_module.delete_expense(target_id, owner) == 0

    def test_helper_accepts_provided_connection_and_commits(self, seeded_db, target_id):
        owner = user_id_of(DEMO_EMAIL)
        conn = db_module.get_db()
        try:
            assert db_module.delete_expense(target_id, owner, conn=conn) == 1
        finally:
            conn.close()
        assert get_row(target_id) is None, "Deletion must be committed"

    def test_helper_only_deletes_one_row(self, seeded_db, target_id):
        before = all_rows_except(target_id)
        db_module.delete_expense(target_id, user_id_of(DEMO_EMAIL))
        assert all_rows_except(target_id) == before
