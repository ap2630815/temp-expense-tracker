"""Tests for Step 8: Edit Expense (GET/POST /expenses/<id>/edit).

Written from the feature spec (.claude/specs/08-edit-expense.md).

Seed demo user (demo@spendly.com / demo123): 8 expenses in Sep 2026, total
279.54. Each test gets a "target" expense owned by the demo user (20.00, Food,
2026-09-30, "Target lunch") and a second user (other@example.com) with one
expense. "Today" is monkeypatched to 2026-09-30.
"""
import re
import sqlite3
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
FUTURE = "2026-10-01"
CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]
SUCCESS_MESSAGE = "Expense updated."
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


@pytest.fixture
def target_id(seeded_db):
    return query("SELECT id FROM expenses WHERE description = ?", (TARGET_DESCRIPTION,))[0]["id"]


@pytest.fixture
def other_expense_id(seeded_db):
    return query("SELECT id FROM expenses WHERE description = ?", (OTHER_DESCRIPTION,))[0]["id"]


@pytest.fixture
def target_before(target_id):
    return get_row(target_id)


def edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


def valid_form(**overrides):
    data = {
        "amount": "35.50",
        "category": "Transport",
        "date": "2026-09-28",
        "description": "Edited description",
    }
    data.update(overrides)
    return data


def post_edit(client, expense_id, **overrides):
    return client.post(edit_url(expense_id), data=valid_form(**overrides))


def assert_rejected(response, expense_id, before):
    assert response.status_code == 200, "Validation errors re-render with HTTP 200"
    assert 'role="alert"' in page(response), "Expected an error message block"
    assert get_row(expense_id) == before, "Stored expense must be unchanged on validation error"


def stat_count(text):
    match = re.search(r"Transactions\s*</span>\s*<span[^>]*>\s*(\d+)\s*</span>", text)
    assert match, "Could not find the Transactions stat"
    return int(match.group(1))


def input_tag(text, name):
    for tag in re.findall(r"<input\b[^>]*>", text, re.DOTALL):
        if re.search(r'\bname="' + name + '"', tag):
            return tag
    pytest.fail(f"Could not find the <input name={name}> element")


def attr_value(tag, attr):
    match = re.search(r'\b' + attr + r'="([^"]*)"', tag)
    return match.group(1) if match else None


def option_tag(text, value):
    match = re.search(r'<option\b[^>]*value="' + re.escape(value) + r'"[^>]*>', text)
    assert match, f"Missing category option {value}"
    return match.group(0)


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client, target_id):
        response = client.get(edit_url(target_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_logged_out_redirects_to_login(self, client, target_id):
        response = post_edit(client, target_id)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_logged_out_does_not_modify(self, client, target_id, target_before):
        post_edit(client, target_id)
        assert get_row(target_id) == target_before

    def test_logged_out_missing_id_redirects_not_404(self, client):
        response = client.get(edit_url(MISSING_ID))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ------------------------------------------------------------------ #
# 404 handling and ownership                                          #
# ------------------------------------------------------------------ #

class TestNotFoundAndOwnership:
    def test_get_missing_id_returns_404(self, auth_client):
        assert auth_client.get(edit_url(MISSING_ID)).status_code == 404

    def test_post_missing_id_returns_404(self, auth_client):
        before = expense_count()
        assert post_edit(auth_client, MISSING_ID).status_code == 404
        assert expense_count() == before

    def test_get_other_users_expense_returns_404(self, auth_client, other_expense_id):
        response = auth_client.get(edit_url(other_expense_id))
        assert response.status_code == 404
        assert OTHER_DESCRIPTION not in page(response), "Must not reveal foreign expense"

    def test_post_other_users_expense_returns_404_and_unchanged(
        self, auth_client, other_expense_id
    ):
        before = get_row(other_expense_id)
        response = post_edit(auth_client, other_expense_id)
        assert response.status_code == 404
        assert get_row(other_expense_id) == before, "Foreign expense must not be modified"

    def test_other_user_cannot_edit_demo_expense(self, client, target_id, target_before):
        log_in(client, OTHER_EMAIL, OTHER_PASSWORD)
        assert client.get(edit_url(target_id)).status_code == 404
        assert post_edit(client, target_id).status_code == 404
        assert get_row(target_id) == target_before

    def test_foreign_404_matches_missing_404(self, auth_client, other_expense_id):
        foreign = auth_client.get(edit_url(other_expense_id))
        missing = auth_client.get(edit_url(MISSING_ID))
        assert foreign.status_code == missing.status_code == 404

    def test_non_integer_id_returns_404(self, auth_client):
        assert auth_client.get("/expenses/abc/edit").status_code == 404


# ------------------------------------------------------------------ #
# GET form (prefill and edit-mode UI)                                 #
# ------------------------------------------------------------------ #

class TestEditForm:
    def test_get_returns_200_with_form(self, auth_client, target_id):
        response = auth_client.get(edit_url(target_id))
        assert response.status_code == 200
        assert "<form" in page(response)

    def test_get_prefills_current_values(self, auth_client, target_id):
        text = page(auth_client.get(edit_url(target_id)))
        assert attr_value(input_tag(text, "amount"), "value") == "20.00"
        assert attr_value(input_tag(text, "date"), "value") == TODAY
        assert TARGET_DESCRIPTION in text
        assert "selected" in option_tag(text, "Food")

    def test_get_only_current_category_selected(self, auth_client, target_id):
        text = page(auth_client.get(edit_url(target_id)))
        for category in CATEGORIES:
            if category != "Food":
                assert "selected" not in option_tag(text, category), (
                    f"{category} should not be selected"
                )

    @pytest.mark.parametrize(
        "stored, expected",
        [(7.5, "7.50"), (12, "12.00"), (1234.5, "1234.50"), (0.99, "0.99")],
    )
    def test_amount_prefilled_with_two_decimals(
        self, auth_client, target_id, stored, expected
    ):
        conn = db_module.get_db()
        conn.execute("UPDATE expenses SET amount = ? WHERE id = ?", (stored, target_id))
        conn.commit()
        conn.close()
        text = page(auth_client.get(edit_url(target_id)))
        assert attr_value(input_tag(text, "amount"), "value") == expected

    def test_null_description_renders_empty_not_none(self, auth_client, target_id):
        conn = db_module.get_db()
        conn.execute("UPDATE expenses SET description = NULL WHERE id = ?", (target_id,))
        conn.commit()
        conn.close()
        text = page(auth_client.get(edit_url(target_id)))
        value = attr_value(input_tag(text, "description"), "value")
        assert value in ("", None), "NULL description should render empty"
        assert "None" not in text, "NULL must not render as the string 'None'"

    def test_get_shows_edit_mode_labels(self, auth_client, target_id):
        text = page(auth_client.get(edit_url(target_id)))
        assert "Edit expense" in text
        assert "Save changes" in text
        assert "Edit Expense" in text  # page title

    def test_get_form_posts_to_edit_url(self, auth_client, target_id):
        text = page(auth_client.get(edit_url(target_id)))
        assert f'action="{edit_url(target_id)}"' in text

    def test_get_has_cancel_link_to_profile(self, auth_client, target_id):
        text = page(auth_client.get(edit_url(target_id)))
        assert "Cancel" in text
        assert 'href="/profile"' in text

    def test_get_has_expected_fields(self, auth_client, target_id):
        text = page(auth_client.get(edit_url(target_id)))
        for name in ("amount", "category", "date", "description"):
            assert f'name="{name}"' in text, f"Missing field {name}"

    def test_get_lists_all_categories(self, auth_client, target_id):
        text = page(auth_client.get(edit_url(target_id)))
        for category in CATEGORIES:
            option_tag(text, category)

    def test_get_does_not_modify(self, auth_client, target_id, target_before):
        auth_client.get(edit_url(target_id))
        assert get_row(target_id) == target_before

    def test_get_prefill_escapes_html_in_description(self, auth_client, target_id):
        conn = db_module.get_db()
        conn.execute(
            "UPDATE expenses SET description = ? WHERE id = ?", ("<b>x</b>", target_id)
        )
        conn.commit()
        conn.close()
        text = page(auth_client.get(edit_url(target_id)))
        assert "<b>x</b>" not in text
        assert "&lt;b&gt;x&lt;/b&gt;" in text

    def test_add_page_unchanged(self, auth_client):
        text = page(auth_client.get("/expenses/add"))
        assert "Add Expense" in text
        assert "Edit expense" not in text
        assert "Save changes" not in text
        assert 'action="/expenses/add"' in text or "action=" not in text.split("<form", 1)[1].split(">", 1)[0]
        assert attr_value(input_tag(text, "date"), "value") == TODAY


# ------------------------------------------------------------------ #
# Valid submission                                                    #
# ------------------------------------------------------------------ #

class TestValidPost:
    def test_valid_post_redirects_to_profile(self, auth_client, target_id):
        response = post_edit(auth_client, target_id)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")

    def test_valid_post_flashes_success_on_profile(self, auth_client, target_id):
        response = auth_client.post(
            edit_url(target_id), data=valid_form(), follow_redirects=True
        )
        assert response.status_code == 200
        assert SUCCESS_MESSAGE in page(response)

    def test_success_flash_not_shown_twice(self, auth_client, target_id):
        post_edit(auth_client, target_id)
        auth_client.get("/profile")
        assert SUCCESS_MESSAGE not in page(auth_client.get("/profile"))

    def test_valid_post_updates_row(self, auth_client, target_id):
        count = expense_count()
        post_edit(auth_client, target_id)
        row = get_row(target_id)
        assert row["amount"] == pytest.approx(35.50)
        assert row["category"] == "Transport"
        assert row["date"] == "2026-09-28"
        assert row["description"] == "Edited description"
        assert expense_count() == count, "Editing must not create or delete rows"

    def test_owner_and_created_at_unchanged(self, auth_client, target_id, target_before):
        post_edit(auth_client, target_id)
        row = get_row(target_id)
        assert row["user_id"] == target_before["user_id"]
        assert row["created_at"] == target_before["created_at"]
        assert row["id"] == target_before["id"]

    def test_other_rows_untouched(self, auth_client, target_id, other_expense_id):
        others_before = [
            dict(r)
            for r in query("SELECT * FROM expenses WHERE id != ? ORDER BY id", (target_id,))
        ]
        post_edit(auth_client, target_id)
        others_after = [
            dict(r)
            for r in query("SELECT * FROM expenses WHERE id != ? ORDER BY id", (target_id,))
        ]
        assert others_after == others_before

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_allowed_category_accepted(self, auth_client, target_id, category):
        response = post_edit(auth_client, target_id, category=category)
        assert response.status_code == 302
        assert get_row(target_id)["category"] == category

    @pytest.mark.parametrize(
        "raw, expected",
        [("12.5", 12.5), ("10.456", 10.46), ("7", 7.0), ("  3.20 ", 3.2)],
    )
    def test_amount_rounded_to_two_decimals(self, auth_client, target_id, raw, expected):
        post_edit(auth_client, target_id, amount=raw)
        assert get_row(target_id)["amount"] == pytest.approx(expected, abs=1e-9)

    def test_profile_reflects_edit(self, auth_client, target_id):
        before_text = page(auth_client.get("/profile"))
        assert "₹299.54" in before_text, "Seed total 279.54 + target 20.00"
        post_edit(
            auth_client, target_id, amount="120.00", category="Transport",
            description="Reflected edit",
        )
        text = page(auth_client.get("/profile"))
        assert "Reflected edit" in text
        assert TARGET_DESCRIPTION not in text
        assert "₹399.54" in text, "Total spent should reflect the new amount"
        assert "₹299.54" not in text
        assert stat_count(text) == stat_count(before_text), "Count must not change"

    def test_category_breakdown_reflects_edit(self, auth_client, target_id):
        post_edit(auth_client, target_id, amount="500.00", category="Shopping")
        text = page(auth_client.get("/profile"))
        breakdown = text[text.index("By category"):]
        assert "Shopping" in breakdown
        assert "₹500.00" in breakdown or "₹5" in breakdown

    def test_submitted_user_id_field_is_ignored(
        self, auth_client, target_id, target_before
    ):
        other_id = user_id_of(OTHER_EMAIL)
        response = post_edit(auth_client, target_id, user_id=str(other_id))
        assert response.status_code == 302
        row = get_row(target_id)
        assert row["user_id"] == target_before["user_id"]
        assert row["user_id"] != other_id
        assert row["description"] == "Edited description"

    def test_submitted_id_field_is_ignored(self, auth_client, target_id, other_expense_id):
        before = get_row(other_expense_id)
        post_edit(auth_client, target_id, id=str(other_expense_id))
        assert get_row(other_expense_id) == before
        assert get_row(target_id)["description"] == "Edited description"

    def test_old_dated_row_can_be_resaved(self, auth_client, target_id):
        conn = db_module.get_db()
        conn.execute("UPDATE expenses SET date = ? WHERE id = ?", ("2020-01-15", target_id))
        conn.commit()
        conn.close()
        response = post_edit(auth_client, target_id, date="2020-01-15")
        assert response.status_code == 302
        assert get_row(target_id)["date"] == "2020-01-15"

    def test_today_accepted(self, auth_client, target_id):
        assert post_edit(auth_client, target_id, date=TODAY).status_code == 302
        assert get_row(target_id)["date"] == TODAY


# ------------------------------------------------------------------ #
# Description                                                         #
# ------------------------------------------------------------------ #

class TestDescription:
    @pytest.mark.parametrize("value", ["", "   ", "\t \n"])
    def test_empty_or_whitespace_description_stored_as_null(
        self, auth_client, target_id, value
    ):
        response = post_edit(auth_client, target_id, description=value)
        assert response.status_code == 302
        assert get_row(target_id)["description"] is None

    def test_missing_description_field_stored_as_null(self, auth_client, target_id):
        data = valid_form()
        del data["description"]
        response = auth_client.post(edit_url(target_id), data=data)
        assert response.status_code == 302
        assert get_row(target_id)["description"] is None

    def test_description_is_stripped(self, auth_client, target_id):
        post_edit(auth_client, target_id, description="   padded text   ")
        assert get_row(target_id)["description"] == "padded text"

    def test_description_of_200_chars_accepted(self, auth_client, target_id):
        description = "a" * 200
        assert post_edit(auth_client, target_id, description=description).status_code == 302
        assert get_row(target_id)["description"] == description

    def test_description_of_201_chars_rejected(self, auth_client, target_id, target_before):
        response = post_edit(auth_client, target_id, description="a" * 201)
        assert_rejected(response, target_id, target_before)

    def test_sql_injection_description_stored_literally(self, auth_client, target_id):
        payload = "'; DROP TABLE expenses; --"
        count = expense_count()
        response = post_edit(auth_client, target_id, description=payload)
        assert response.status_code == 302
        assert get_row(target_id)["description"] == payload
        assert expense_count() == count, "expenses table must be intact"
        assert auth_client.get("/profile").status_code == 200

    def test_sql_injection_and_quotes_displayed_as_plain_text(self, auth_client, target_id):
        payload = "'; DROP TABLE expenses; --"
        post_edit(auth_client, target_id, description=payload)
        profile = auth_client.get("/profile")
        assert profile.status_code == 200
        assert "DROP TABLE expenses; --" in page(profile)
        edit_page = auth_client.get(edit_url(target_id))
        assert edit_page.status_code == 200
        assert "DROP TABLE expenses; --" in page(edit_page)

    def test_quotes_stored_and_escaped(self, auth_client, target_id):
        description = 'He said "hi" & it\'s <i>fine</i>'
        assert post_edit(auth_client, target_id, description=description).status_code == 302
        assert get_row(target_id)["description"] == description
        for url in ("/profile", edit_url(target_id)):
            text = page(auth_client.get(url))
            assert "<i>fine</i>" not in text, f"Unescaped HTML on {url}"
            assert "&lt;i&gt;fine&lt;/i&gt;" in text

    def test_html_in_description_escaped_in_error_rerender(self, auth_client, target_id):
        text = page(post_edit(auth_client, target_id, description="<b>x</b>", amount="abc"))
        assert "<b>x</b>" not in text
        assert "&lt;b&gt;x&lt;/b&gt;" in text


# ------------------------------------------------------------------ #
# Validation failures                                                 #
# ------------------------------------------------------------------ #

class TestValidation:
    @pytest.mark.parametrize("amount", ["0", "-5", "abc", "nan", "inf", "-inf", "", "0.001"])
    def test_invalid_amount_rejected(self, auth_client, target_id, target_before, amount):
        response = post_edit(auth_client, target_id, amount=amount)
        assert_rejected(response, target_id, target_before)

    @pytest.mark.parametrize("category", ["Travel", "food", "", "<script>", "Food'; --"])
    def test_invalid_category_rejected(self, auth_client, target_id, target_before, category):
        response = post_edit(auth_client, target_id, category=category)
        assert_rejected(response, target_id, target_before)

    @pytest.mark.parametrize(
        "value", ["not-a-date", "30-09-2026", "2026/09/30", "2026-13-01", "2026-02-30", ""]
    )
    def test_malformed_date_rejected(self, auth_client, target_id, target_before, value):
        response = post_edit(auth_client, target_id, date=value)
        assert_rejected(response, target_id, target_before)

    @pytest.mark.parametrize("value", [FUTURE, "2099-01-01"])
    def test_future_date_rejected(self, auth_client, target_id, target_before, value):
        response = post_edit(auth_client, target_id, date=value)
        assert_rejected(response, target_id, target_before)

    @pytest.mark.parametrize("missing", ["amount", "category", "date"])
    def test_missing_required_field_rejected(
        self, auth_client, target_id, target_before, missing
    ):
        data = valid_form()
        del data[missing]
        response = auth_client.post(edit_url(target_id), data=data)
        assert_rejected(response, target_id, target_before)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"amount": "0"},
            {"amount": "-5"},
            {"amount": "abc"},
            {"amount": "nan"},
            {"amount": "inf"},
            {"category": "Travel"},
            {"date": "not-a-date"},
            {"date": FUTURE},
            {"description": "a" * 201},
        ],
    )
    def test_rejected_post_keeps_submitted_values(self, auth_client, target_id, overrides):
        data = valid_form(
            amount="42.00", category="Bills", date="2026-09-15", description="keep-me-please"
        )
        data.update(overrides)
        text = page(auth_client.post(edit_url(target_id), data=data))
        expected_amount = data["amount"]
        assert attr_value(input_tag(text, "amount"), "value") == expected_amount
        if data["date"] == "not-a-date" or data["date"] == FUTURE:
            assert attr_value(input_tag(text, "date"), "value") == data["date"]
        else:
            assert attr_value(input_tag(text, "date"), "value") == "2026-09-15"
        if len(data["description"]) <= 200:
            assert "keep-me-please" in text
        if data["category"] == "Bills":
            assert "selected" in option_tag(text, "Bills")

    def test_rejected_post_stays_in_edit_mode(self, auth_client, target_id):
        text = page(post_edit(auth_client, target_id, amount="abc"))
        assert "Edit expense" in text
        assert "Save changes" in text
        assert f'action="{edit_url(target_id)}"' in text

    def test_rejected_post_does_not_flash_success(self, auth_client, target_id):
        post_edit(auth_client, target_id, amount="abc")
        assert SUCCESS_MESSAGE not in page(auth_client.get("/profile"))

    def test_rejected_post_keeps_date_max_today(self, auth_client, target_id):
        text = page(post_edit(auth_client, target_id, date=FUTURE))
        assert attr_value(input_tag(text, "date"), "max") == TODAY


# ------------------------------------------------------------------ #
# Profile integration and untouched stubs                             #
# ------------------------------------------------------------------ #

class TestProfileIntegration:
    def test_profile_rows_have_edit_links(self, auth_client, target_id):
        text = page(auth_client.get("/profile"))
        assert re.search(
            r'<a\b[^>]*href="' + re.escape(edit_url(target_id)) + r'"[^>]*>\s*Edit\s*</a>',
            text,
        ), "Profile row for the target expense should have an Edit link"

    def test_every_listed_transaction_has_edit_link(self, auth_client):
        text = page(auth_client.get("/profile"))
        links = re.findall(r'href="/expenses/(\d+)/edit"', text)
        assert links, "Expected Edit links on profile"
        assert len(links) == len(set(links)), "Each row should link to a distinct expense"

    def test_profile_does_not_link_to_other_users_expense(
        self, auth_client, other_expense_id
    ):
        text = page(auth_client.get("/profile"))
        assert edit_url(other_expense_id) not in text

    def test_edit_link_opens_edit_page(self, auth_client, target_id):
        text = page(auth_client.get("/profile"))
        match = re.search(r'href="(/expenses/' + str(target_id) + r'/edit)"', text)
        assert match
        assert auth_client.get(match.group(1)).status_code == 200


class TestDeleteRouteNoLongerStub:
    def test_delete_get_is_not_the_old_stub(self, auth_client, target_id):
        response = auth_client.get(f"/expenses/{target_id}/delete")
        assert response.status_code == 405
        assert "coming in Step 9" not in page(response)

    def test_delete_get_does_not_delete(self, auth_client, target_id):
        auth_client.get(f"/expenses/{target_id}/delete")
        assert get_row(target_id) is not None


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
    def test_get_redirects_to_login_not_500(self, stale_client, target_id):
        response = stale_client.get(edit_url(target_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_redirects_to_login_not_500(self, stale_client, target_id):
        response = post_edit(stale_client, target_id)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_does_not_modify(self, stale_client, target_id, target_before):
        post_edit(stale_client, target_id)
        assert get_row(target_id) == target_before

    def test_get_missing_id_redirects_to_login(self, stale_client):
        response = stale_client.get(edit_url(MISSING_ID))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_get_clears_stale_session(self, stale_client, target_id):
        stale_client.get(edit_url(target_id))
        with stale_client.session_transaction() as sess:
            assert "user_id" not in sess

    def test_post_clears_stale_session(self, stale_client, target_id):
        post_edit(stale_client, target_id)
        with stale_client.session_transaction() as sess:
            assert "user_id" not in sess

    def test_second_get_still_redirects_to_login(self, stale_client, target_id):
        stale_client.get(edit_url(target_id))
        response = stale_client.get(edit_url(target_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ------------------------------------------------------------------ #
# DB helpers                                                          #
# ------------------------------------------------------------------ #

class TestUpdateExpenseHelper:
    def test_owner_update_returns_rowcount_1_and_updates(self, target_id):
        user_id = user_id_of(DEMO_EMAIL)
        result = db_module.update_expense(
            target_id, user_id, 55.25, "Health", "Updated", "2026-09-01"
        )
        assert result == 1
        row = get_row(target_id)
        assert row["amount"] == pytest.approx(55.25)
        assert row["category"] == "Health"
        assert row["description"] == "Updated"
        assert row["date"] == "2026-09-01"

    def test_update_preserves_user_id_and_created_at(self, target_id, target_before):
        db_module.update_expense(
            target_id, target_before["user_id"], 1.0, "Other", None, "2026-09-01"
        )
        row = get_row(target_id)
        assert row["user_id"] == target_before["user_id"]
        assert row["created_at"] == target_before["created_at"]
        assert row["description"] is None

    def test_wrong_user_returns_0_and_does_not_modify(self, target_id, target_before):
        other_id = user_id_of(OTHER_EMAIL)
        result = db_module.update_expense(
            target_id, other_id, 1.0, "Other", "hijack", "2026-09-01"
        )
        assert result == 0
        assert get_row(target_id) == target_before

    def test_missing_id_returns_0(self, seeded_db):
        user_id = user_id_of(DEMO_EMAIL)
        count = expense_count()
        result = db_module.update_expense(
            MISSING_ID, user_id, 1.0, "Food", None, "2026-09-01"
        )
        assert result == 0
        assert expense_count() == count

    def test_uses_provided_connection_and_commits(self, target_id):
        user_id = user_id_of(DEMO_EMAIL)
        conn = db_module.get_db()
        try:
            result = db_module.update_expense(
                target_id, user_id, 9.99, "Food", "conn-case", "2026-09-01", conn=conn
            )
            assert result == 1
            row = conn.execute(
                "SELECT id FROM expenses WHERE id = ?", (target_id,)
            ).fetchone()
            assert row is not None, "Caller's connection must stay open"
        finally:
            conn.close()
        assert get_row(target_id)["description"] == "conn-case", "Change must be committed"

    def test_sql_injection_payload_stored_literally(self, target_id):
        user_id = user_id_of(DEMO_EMAIL)
        payload = "'; DROP TABLE expenses; --"
        count = expense_count()
        db_module.update_expense(target_id, user_id, 1.0, "Food", payload, "2026-09-01")
        assert get_row(target_id)["description"] == payload
        assert expense_count() == count


class TestGetExpenseByIdHelper:
    def test_returns_row_for_owner(self, target_id):
        user_id = user_id_of(DEMO_EMAIL)
        row = db_module.get_expense_by_id(target_id, user_id)
        assert row is not None
        assert row["id"] == target_id
        assert row["user_id"] == user_id
        assert row["amount"] == pytest.approx(20.00)
        assert row["category"] == "Food"
        assert row["description"] == TARGET_DESCRIPTION
        assert row["date"] == TODAY

    def test_returns_none_for_foreign_id(self, other_expense_id):
        demo_id = user_id_of(DEMO_EMAIL)
        assert db_module.get_expense_by_id(other_expense_id, demo_id) is None

    def test_returns_none_for_missing_id(self, seeded_db):
        assert db_module.get_expense_by_id(MISSING_ID, user_id_of(DEMO_EMAIL)) is None

    def test_accepts_provided_connection(self, target_id):
        conn = db_module.get_db()
        try:
            row = db_module.get_expense_by_id(target_id, user_id_of(DEMO_EMAIL), conn=conn)
            assert row is not None
            conn.execute("SELECT 1")  # connection still open
        finally:
            conn.close()


class TestRecentTransactionsIncludeId:
    def test_rows_include_id(self, seeded_db):
        user_id = user_id_of(DEMO_EMAIL)
        rows = db_module.get_recent_transactions(user_id)
        assert rows, "Demo user should have transactions"
        for row in rows:
            try:
                value = row["id"]
            except (KeyError, IndexError, TypeError):
                pytest.fail("get_recent_transactions rows must include 'id'")
            assert isinstance(value, int)

    def test_ids_belong_to_user(self, seeded_db):
        user_id = user_id_of(DEMO_EMAIL)
        ids = {row["id"] for row in db_module.get_recent_transactions(user_id)}
        owned = {r["id"] for r in query("SELECT id FROM expenses WHERE user_id = ?", (user_id,))}
        assert ids and ids <= owned
