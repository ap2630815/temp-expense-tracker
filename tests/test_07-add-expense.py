"""Tests for Step 7: Add Expense (GET/POST /expenses/add).

Written from the feature spec (.claude/specs/07-add-expense.md).

Seed demo user (demo@spendly.com / demo123): 8 expenses in Sep 2026, total
279.54. A second user (other@example.com) has one expense. "Today" is
monkeypatched to 2026-09-30.
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

TODAY = "2026-09-30"
FUTURE = "2026-10-01"
CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]
SUCCESS_MESSAGE = "Expense added."
FILTER_ERROR = "Start date must be before end date."


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


def valid_form(**overrides):
    data = {
        "amount": "20.00",
        "category": "Food",
        "date": TODAY,
        "description": "Lunch special",
    }
    data.update(overrides)
    return data


def post_expense(client, **overrides):
    return client.post("/expenses/add", data=valid_form(**overrides))


def assert_rejected(client, response, before):
    assert response.status_code == 200, "Validation errors re-render with HTTP 200"
    assert 'role="alert"' in page(response), "Expected an error message block"
    assert expense_count() == before, "No row should be inserted on validation error"


def stat_count(text):
    match = re.search(r"Transactions\s*</span>\s*<span[^>]*>\s*(\d+)\s*</span>", text)
    assert match, "Could not find the Transactions stat"
    return int(match.group(1))


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_logged_out_redirects_to_login(self, client):
        response = post_expense(client)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_logged_out_inserts_nothing(self, client):
        before = expense_count()
        post_expense(client)
        assert expense_count() == before


# ------------------------------------------------------------------ #
# GET form                                                            #
# ------------------------------------------------------------------ #

class TestForm:
    def test_get_returns_200_with_form(self, auth_client):
        response = auth_client.get("/expenses/add")
        text = page(response)
        assert response.status_code == 200
        assert "<form" in text
        assert "Add Expense" in text

    def test_get_prefills_today(self, auth_client):
        text = page(auth_client.get("/expenses/add"))
        assert TODAY in text, "Date should default to today"

    def test_get_lists_all_seven_categories(self, auth_client):
        text = page(auth_client.get("/expenses/add"))
        for category in CATEGORIES:
            assert re.search(
                r'<option\b[^>]*value="' + category + r'"', text
            ), f"Missing category option {category}"

    def test_get_has_expected_fields(self, auth_client):
        text = page(auth_client.get("/expenses/add"))
        for name in ("amount", "category", "date", "description"):
            assert f'name="{name}"' in text, f"Missing field {name}"

    def test_get_has_cancel_link_to_profile(self, auth_client):
        text = page(auth_client.get("/expenses/add"))
        assert "Cancel" in text
        assert 'href="/profile"' in text

    def test_get_does_not_insert(self, auth_client):
        before = expense_count()
        auth_client.get("/expenses/add")
        assert expense_count() == before


# ------------------------------------------------------------------ #
# Valid submission                                                    #
# ------------------------------------------------------------------ #

class TestValidPost:
    def test_valid_post_redirects_to_profile(self, auth_client):
        response = post_expense(auth_client)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")

    def test_valid_post_flashes_success_on_profile(self, auth_client):
        response = auth_client.post(
            "/expenses/add", data=valid_form(), follow_redirects=True
        )
        assert response.status_code == 200
        assert SUCCESS_MESSAGE in page(response)

    def test_success_flash_not_shown_twice(self, auth_client):
        post_expense(auth_client)
        auth_client.get("/profile")
        assert SUCCESS_MESSAGE not in page(auth_client.get("/profile"))

    def test_valid_post_stores_row_for_session_user(self, auth_client):
        before = expense_count()
        post_expense(auth_client, amount="20.00", category="Food", description="Lunch special")
        assert expense_count() == before + 1
        rows = query(
            "SELECT * FROM expenses WHERE description = ?", ("Lunch special",)
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == user_id_of(DEMO_EMAIL)
        assert row["amount"] == pytest.approx(20.00)
        assert row["category"] == "Food"
        assert row["date"] == TODAY

    @pytest.mark.parametrize(
        "raw, expected",
        [("12.5", 12.5), ("10.456", 10.46), ("7", 7.0), ("  3.20 ", 3.2)],
    )
    def test_amount_rounded_to_two_decimals(self, auth_client, raw, expected):
        post_expense(auth_client, amount=raw, description="rounding-case")
        rows = query("SELECT amount FROM expenses WHERE description = ?", ("rounding-case",))
        assert len(rows) == 1
        assert rows[0]["amount"] == pytest.approx(expected, abs=1e-9)

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_allowed_category_accepted(self, auth_client, category):
        response = post_expense(auth_client, category=category, description="cat-case")
        assert response.status_code == 302
        rows = query("SELECT category FROM expenses WHERE description = ?", ("cat-case",))
        assert [r["category"] for r in rows] == [category]

    def test_expense_appears_in_profile_transactions(self, auth_client):
        post_expense(auth_client, description="Brand new purchase", amount="20.00")
        text = page(auth_client.get("/profile"))
        assert "Brand new purchase" in text
        assert "₹20.00" in text

    def test_profile_totals_and_count_update(self, auth_client):
        before_text = page(auth_client.get("/profile"))
        assert stat_count(before_text) == 8
        assert "₹279.54" in before_text
        post_expense(auth_client, amount="20.00")
        text = page(auth_client.get("/profile"))
        assert stat_count(text) == 9
        assert "₹299.54" in text, "Total spent should include the new expense"

    def test_category_breakdown_updates(self, auth_client):
        # Seed Food total is 46.80; add 100 to make Food the top category.
        post_expense(auth_client, amount="100.00", category="Food")
        text = page(auth_client.get("/profile"))
        breakdown = text[text.index("By category"):]
        assert "₹146.80" in breakdown

    def test_other_user_does_not_see_new_expense(self, client):
        log_in(client)
        post_expense(client, description="Demo private lunch")
        client.get("/logout")
        log_in(client, OTHER_EMAIL, OTHER_PASSWORD)
        text = page(client.get("/profile"))
        assert "Demo private lunch" not in text

    def test_submitted_user_id_field_is_ignored(self, auth_client):
        other_id = user_id_of(OTHER_EMAIL)
        post_expense(auth_client, user_id=str(other_id), description="spoof-attempt")
        rows = query("SELECT user_id FROM expenses WHERE description = ?", ("spoof-attempt",))
        assert len(rows) == 1
        assert rows[0]["user_id"] == user_id_of(DEMO_EMAIL)
        assert rows[0]["user_id"] != other_id


# ------------------------------------------------------------------ #
# Description                                                         #
# ------------------------------------------------------------------ #

class TestDescription:
    @pytest.mark.parametrize("value", ["", "   ", "\t \n"])
    def test_empty_or_whitespace_description_stored_as_null(self, auth_client, value):
        response = post_expense(auth_client, description=value, amount="77.77")
        assert response.status_code == 302
        rows = query("SELECT description FROM expenses WHERE amount = ?", (77.77,))
        assert len(rows) == 1
        assert rows[0]["description"] is None

    def test_missing_description_field_stored_as_null(self, auth_client):
        data = valid_form(amount="66.66")
        del data["description"]
        response = auth_client.post("/expenses/add", data=data)
        assert response.status_code == 302
        rows = query("SELECT description FROM expenses WHERE amount = ?", (66.66,))
        assert len(rows) == 1 and rows[0]["description"] is None

    def test_description_is_stripped(self, auth_client):
        post_expense(auth_client, description="   padded text   ")
        rows = query("SELECT description FROM expenses WHERE description LIKE ?", ("%padded text%",))
        assert [r["description"] for r in rows] == ["padded text"]

    def test_description_of_200_chars_accepted(self, auth_client):
        description = "a" * 200
        response = post_expense(auth_client, description=description)
        assert response.status_code == 302
        rows = query("SELECT description FROM expenses WHERE description = ?", (description,))
        assert len(rows) == 1

    def test_description_of_201_chars_rejected(self, auth_client):
        before = expense_count()
        response = post_expense(auth_client, description="a" * 201)
        assert_rejected(auth_client, response, before)

    def test_sql_injection_description_stored_literally(self, auth_client):
        payload = "'; DROP TABLE expenses; --"
        response = post_expense(auth_client, description=payload)
        assert response.status_code == 302
        rows = query("SELECT description FROM expenses WHERE description = ?", (payload,))
        assert len(rows) == 1, "Payload should be stored as plain text"
        assert expense_count() >= 9, "expenses table must still exist with its data"
        assert auth_client.get("/profile").status_code == 200

    def test_sql_injection_and_quotes_displayed_as_plain_text_on_profile(self, auth_client):
        post_expense(auth_client, description="'; DROP TABLE expenses; --", amount="11.11")
        post_expense(auth_client, description='He said "hi" & it\'s fine', amount="22.22")
        response = auth_client.get("/profile")
        text = page(response)
        assert response.status_code == 200
        assert "DROP TABLE expenses; --" in text, "Injection payload should be displayed as text"
        assert "He said" in text and "it" in text
        assert '"hi"' not in text or "&#34;hi&#34;" in text or "&quot;hi&quot;" in text
        assert expense_count() >= 10, "expenses table must be intact"

    def test_html_in_description_is_escaped(self, auth_client):
        post_expense(auth_client, description="<b>x</b>")
        text = page(auth_client.get("/profile"))
        assert "<b>x</b>" not in text
        assert "&lt;b&gt;x&lt;/b&gt;" in text

    def test_html_in_description_escaped_in_error_rerender(self, auth_client):
        response = post_expense(auth_client, description="<b>x</b>", amount="abc")
        text = page(response)
        assert "<b>x</b>" not in text
        assert "&lt;b&gt;x&lt;/b&gt;" in text


# ------------------------------------------------------------------ #
# Validation: amount                                                  #
# ------------------------------------------------------------------ #

class TestAmountValidation:
    @pytest.mark.parametrize("amount", ["0", "-1", "abc", "nan", "inf", "-inf", "", "   ", "0.001"])
    def test_invalid_amount_rejected(self, auth_client, amount):
        before = expense_count()
        response = post_expense(auth_client, amount=amount)
        assert_rejected(auth_client, response, before)

    def test_missing_amount_field_rejected(self, auth_client):
        before = expense_count()
        data = valid_form()
        del data["amount"]
        response = auth_client.post("/expenses/add", data=data)
        assert_rejected(auth_client, response, before)

    @pytest.mark.parametrize("amount", ["0", "-1", "abc", "nan", "inf", "0.001"])
    def test_invalid_amount_preserves_entered_values(self, auth_client, amount):
        response = post_expense(
            auth_client,
            amount=amount,
            category="Bills",
            date="2026-09-15",
            description="keep-me-please",
        )
        text = page(response)
        assert f'value="{amount}"' in text, "Entered amount should be preserved"
        assert "keep-me-please" in text, "Entered description should be preserved"
        assert "2026-09-15" in text, "Entered date should be preserved"
        option = re.search(r'<option\b[^>]*value="Bills"[^>]*>', text)
        assert option and "selected" in option.group(0), "Entered category should stay selected"


# ------------------------------------------------------------------ #
# Validation: category                                                #
# ------------------------------------------------------------------ #

class TestCategoryValidation:
    @pytest.mark.parametrize(
        "category", ["Travel", "food", "FOOD", "", "<script>", "Food'; --"]
    )
    def test_invalid_category_rejected(self, auth_client, category):
        before = expense_count()
        response = post_expense(auth_client, category=category)
        assert_rejected(auth_client, response, before)

    def test_category_surrounding_whitespace_is_trimmed(self, auth_client):
        response = post_expense(auth_client, category=" Food ", description="padded-cat")
        assert response.status_code == 302
        rows = query("SELECT category FROM expenses WHERE description = ?", ("padded-cat",))
        assert [r["category"] for r in rows] == ["Food"]

    def test_missing_category_rejected(self, auth_client):
        before = expense_count()
        data = valid_form()
        del data["category"]
        response = auth_client.post("/expenses/add", data=data)
        assert_rejected(auth_client, response, before)


# ------------------------------------------------------------------ #
# Validation: date                                                    #
# ------------------------------------------------------------------ #

class TestDateValidation:
    @pytest.mark.parametrize(
        "value",
        ["not-a-date", "30-09-2026", "2026/09/30", "2026-13-01", "2026-02-30", "", "2026-9-3x"],
    )
    def test_malformed_date_rejected(self, auth_client, value):
        before = expense_count()
        response = post_expense(auth_client, date=value)
        assert_rejected(auth_client, response, before)

    def test_future_date_rejected(self, auth_client):
        before = expense_count()
        response = post_expense(auth_client, date=FUTURE)
        assert_rejected(auth_client, response, before)

    def test_far_future_date_rejected(self, auth_client):
        before = expense_count()
        response = post_expense(auth_client, date="2099-01-01")
        assert_rejected(auth_client, response, before)

    def test_today_accepted(self, auth_client):
        response = post_expense(auth_client, date=TODAY, description="today-case")
        assert response.status_code == 302
        rows = query("SELECT date FROM expenses WHERE description = ?", ("today-case",))
        assert [r["date"] for r in rows] == [TODAY]

    def test_past_date_accepted(self, auth_client):
        response = post_expense(auth_client, date="2020-01-15", description="past-case")
        assert response.status_code == 302
        rows = query("SELECT date FROM expenses WHERE description = ?", ("past-case",))
        assert [r["date"] for r in rows] == ["2020-01-15"]

    def test_missing_date_field_rejected(self, auth_client):
        before = expense_count()
        data = valid_form()
        del data["date"]
        response = auth_client.post("/expenses/add", data=data)
        assert_rejected(auth_client, response, before)

    def test_invalid_date_preserves_other_values(self, auth_client):
        response = post_expense(
            auth_client, date=FUTURE, amount="42.00", description="keep-this-text"
        )
        text = page(response)
        assert "keep-this-text" in text
        assert "42.00" in text


# ------------------------------------------------------------------ #
# Profile integration and untouched stubs                             #
# ------------------------------------------------------------------ #

class TestProfileIntegration:
    def test_profile_has_add_expense_link(self, auth_client):
        text = page(auth_client.get("/profile"))
        assert re.search(
            r'<a\b[^>]*href="/expenses/add"[^>]*>\s*[^<]*Add expense', text, re.IGNORECASE
        ), "Profile should link to /expenses/add with 'Add expense' text"

    def test_filter_error_flash_still_renders_as_error(self, auth_client):
        response = auth_client.get(
            "/profile", query_string={"date_from": "2026-09-20", "date_to": "2026-09-01"}
        )
        text = page(response)
        assert FILTER_ERROR in text
        match = re.search(r'<div\b([^>]*)>\s*' + re.escape(FILTER_ERROR), text)
        assert match, "Filter error should be rendered in its own alert element"
        assert "success" not in match.group(1), "Filter error must not use success styling"
        assert "error" in match.group(1)

    def test_success_flash_not_styled_as_error(self, auth_client):
        response = auth_client.post("/expenses/add", data=valid_form(), follow_redirects=True)
        text = page(response)
        match = re.search(r'<div\b([^>]*)>\s*' + re.escape(SUCCESS_MESSAGE), text)
        assert match, "Success message should be in its own element"
        assert "error" not in match.group(1)


class TestDeleteRouteNoLongerStub:
    def test_delete_requires_login(self, client):
        response = client.post("/expenses/1/delete")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ------------------------------------------------------------------ #
# DB helper: create_expense                                           #
# ------------------------------------------------------------------ #

class TestCreateExpenseHelper:
    def test_expense_categories_constant(self):
        assert tuple(db_module.EXPENSE_CATEGORIES) == tuple(CATEGORIES)

    def test_inserts_row_and_returns_lastrowid(self, seeded_db):
        user_id = user_id_of(DEMO_EMAIL)
        new_id = db_module.create_expense(user_id, 12.34, "Food", "Tea", "2026-09-29")
        assert isinstance(new_id, int)
        rows = query("SELECT * FROM expenses WHERE id = ?", (new_id,))
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == user_id
        assert row["amount"] == pytest.approx(12.34)
        assert row["category"] == "Food"
        assert row["description"] == "Tea"
        assert row["date"] == "2026-09-29"
        assert row["created_at"], "created_at should default"

    def test_none_description_stored_as_null(self, seeded_db):
        user_id = user_id_of(DEMO_EMAIL)
        new_id = db_module.create_expense(user_id, 5.0, "Other", None, "2026-09-29")
        row = query("SELECT description FROM expenses WHERE id = ?", (new_id,))[0]
        assert row["description"] is None

    def test_successive_inserts_return_distinct_ids(self, seeded_db):
        user_id = user_id_of(DEMO_EMAIL)
        first = db_module.create_expense(user_id, 1.0, "Food", None, "2026-09-29")
        second = db_module.create_expense(user_id, 2.0, "Food", None, "2026-09-29")
        assert second != first

    def test_uses_provided_connection_and_commits(self, seeded_db):
        user_id = user_id_of(DEMO_EMAIL)
        conn = db_module.get_db()
        try:
            new_id = db_module.create_expense(
                user_id, 3.0, "Bills", "conn-case", "2026-09-29", conn=conn
            )
            # Connection must remain usable (helper must not close a caller's conn).
            row = conn.execute("SELECT id FROM expenses WHERE id = ?", (new_id,)).fetchone()
            assert row is not None
        finally:
            conn.close()
        assert len(query("SELECT id FROM expenses WHERE id = ?", (new_id,))) == 1, (
            "Row should be committed and visible to other connections"
        )

    def test_sql_injection_payload_stored_literally(self, seeded_db):
        user_id = user_id_of(DEMO_EMAIL)
        payload = "'; DROP TABLE expenses; --"
        new_id = db_module.create_expense(user_id, 1.0, "Food", payload, "2026-09-29")
        row = query("SELECT description FROM expenses WHERE id = ?", (new_id,))[0]
        assert row["description"] == payload
        assert expense_count() >= 10

    def test_nonexistent_user_rejected_by_foreign_key(self, seeded_db):
        import sqlite3

        before = expense_count()
        with pytest.raises(sqlite3.IntegrityError):
            db_module.create_expense(99999, 1.0, "Food", None, "2026-09-29")
        assert expense_count() == before


# ------------------------------------------------------------------ #
# Date input max attribute (review follow-up)                         #
# ------------------------------------------------------------------ #

def date_input_tag(text):
    """Return the <input> tag whose name is 'date', or fail."""
    for tag in re.findall(r"<input\b[^>]*>", text, re.DOTALL):
        if re.search(r'\bname="date"', tag):
            return tag
    pytest.fail("Could not find the date <input> element")


def attr_value(tag, attr):
    match = re.search(r'\b' + attr + r'="([^"]*)"', tag)
    return match.group(1) if match else None


class TestDateInputMax:
    def test_get_date_input_has_max_equal_to_today(self, auth_client):
        tag = date_input_tag(page(auth_client.get("/expenses/add")))
        assert attr_value(tag, "max") == TODAY, "Date input max should be today's date"

    def test_get_date_input_still_prefilled_with_today(self, auth_client):
        tag = date_input_tag(page(auth_client.get("/expenses/add")))
        assert attr_value(tag, "value") == TODAY, "Date input should be pre-filled with today"

    def test_get_date_input_is_type_date(self, auth_client):
        tag = date_input_tag(page(auth_client.get("/expenses/add")))
        assert attr_value(tag, "type") == "date"

    def test_max_is_not_a_future_date(self, auth_client):
        tag = date_input_tag(page(auth_client.get("/expenses/add")))
        assert attr_value(tag, "max") != FUTURE

    @pytest.mark.parametrize(
        "overrides",
        [
            {"amount": "abc"},
            {"date": FUTURE},
            {"category": "Travel"},
            {"description": "a" * 201},
        ],
    )
    def test_max_present_after_validation_error(self, auth_client, overrides):
        response = post_expense(auth_client, **overrides)
        assert response.status_code == 200
        tag = date_input_tag(page(response))
        assert attr_value(tag, "max") == TODAY, (
            "Re-rendered form after a validation error must keep max=today"
        )

    def test_future_date_error_rerender_keeps_max_today(self, auth_client):
        response = post_expense(auth_client, date=FUTURE)
        tag = date_input_tag(page(response))
        assert attr_value(tag, "max") == TODAY
        assert attr_value(tag, "max") != FUTURE, "max must be today, not the rejected value"


# ------------------------------------------------------------------ #
# Stale session (user no longer exists)                               #
# ------------------------------------------------------------------ #

GHOST_USER_ID = 987654


def make_stale_by_deleting_user(client):
    """Log in as the other user, then delete their expenses and user row."""
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
    return other_id


def make_stale_by_session(client):
    with client.session_transaction() as sess:
        sess["user_id"] = GHOST_USER_ID
    return GHOST_USER_ID


@pytest.fixture(params=["deleted_user", "ghost_session_id"])
def stale_client(request, client):
    if request.param == "deleted_user":
        make_stale_by_deleting_user(client)
    else:
        make_stale_by_session(client)
    return client


class TestStaleSession:
    def test_get_redirects_to_login_not_500(self, stale_client):
        response = stale_client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_valid_redirects_to_login_not_500(self, stale_client):
        response = post_expense(stale_client)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_valid_inserts_nothing(self, stale_client):
        before = expense_count()
        post_expense(stale_client, description="stale-insert-attempt")
        assert expense_count() == before
        assert query(
            "SELECT id FROM expenses WHERE description = ?", ("stale-insert-attempt",)
        ) == []

    def test_post_invalid_also_redirects_to_login(self, stale_client):
        before = expense_count()
        response = post_expense(stale_client, amount="abc")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert expense_count() == before

    def test_get_clears_stale_session(self, stale_client):
        stale_client.get("/expenses/add")
        with stale_client.session_transaction() as sess:
            assert "user_id" not in sess, "Stale user_id should be cleared from session"

    def test_post_clears_stale_session(self, stale_client):
        post_expense(stale_client)
        with stale_client.session_transaction() as sess:
            assert "user_id" not in sess, "Stale user_id should be cleared from session"

    def test_second_get_after_get_still_redirects_to_login(self, stale_client):
        stale_client.get("/expenses/add")
        response = stale_client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_second_get_after_post_still_redirects_to_login(self, stale_client):
        post_expense(stale_client)
        response = stale_client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_profile_redirects_to_login_after_stale_get(self, stale_client):
        stale_client.get("/expenses/add")
        response = stale_client.get("/profile")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_profile_redirects_to_login_after_stale_post(self, stale_client):
        post_expense(stale_client)
        response = stale_client.get("/profile")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_login_page_reachable_after_stale_redirect(self, stale_client):
        response = stale_client.get("/expenses/add", follow_redirects=True)
        assert response.status_code == 200
        assert "<form" in page(response)

    def test_valid_user_can_log_in_after_stale_session_cleared(self, stale_client):
        stale_client.get("/expenses/add")
        log_in(stale_client)
        assert stale_client.get("/expenses/add").status_code == 200
