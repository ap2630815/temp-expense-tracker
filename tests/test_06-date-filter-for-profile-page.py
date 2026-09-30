"""Tests for Step 6: date-range filter on GET /profile.

Written from the feature spec (.claude/specs/06-date-filter-for-profile-page.md).

Seed demo user (demo@spendly.com / demo123), 8 expenses in Sep 2026:
    09-01  4.50 Food          Coffee at local cafe
    09-03 32.00 Transport     Gas fill-up
    09-05 60.00 Bills         Internet bill
    09-08 25.75 Health        Pharmacy - vitamins
    09-12 15.00 Entertainment Movie ticket
    09-16 89.99 Shopping      New running shoes
    09-20 10.00 Other         Donation to charity
    09-24 42.30 Food          Groceries - weekly shop
Total 279.54, top category Shopping.
"""
import html
import re
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import app as app_module
import database.db as db_module

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

# (date, amount, category, description)
SEED = [
    ("2026-09-01", 4.50, "Food", "Coffee at local cafe"),
    ("2026-09-03", 32.00, "Transport", "Gas fill-up"),
    ("2026-09-05", 60.00, "Bills", "Internet bill"),
    ("2026-09-08", 25.75, "Health", "Pharmacy - vitamins"),
    ("2026-09-12", 15.00, "Entertainment", "Movie ticket"),
    ("2026-09-16", 89.99, "Shopping", "New running shoes"),
    ("2026-09-20", 10.00, "Other", "Donation to charity"),
    ("2026-09-24", 42.30, "Food", "Groceries - weekly shop"),
]
DESCRIPTIONS = {row[0]: row[3] for row in SEED}

OTHER_EMAIL = "other@example.com"
OTHER_DESCRIPTION = "OTHER-USER-SECRET-PURCHASE"

ERROR_MESSAGE = "Start date must be before end date."


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """Isolated on-disk SQLite DB seeded with the demo user plus a second user."""
    db_file = tmp_path / "test_spendly.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)

    conn = db_module.get_db()
    db_module.init_db(conn)
    db_module.seed_db(conn)

    other_id = db_module.create_user(
        "Other Person", OTHER_EMAIL, generate_password_hash("otherpass123"), conn=conn
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


def add_expense(user_email, expense_date, amount, category, description):
    conn = db_module.get_db()
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (user_email,)
    ).fetchone()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, description, date) "
        "VALUES (?, ?, ?, ?, ?)",
        (user["id"], amount, category, description, expense_date),
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# Helpers for reading the rendered page                               #
# ------------------------------------------------------------------ #

def get_profile(client, **params):
    return client.get("/profile", query_string=params)


def page(response):
    return response.get_data(as_text=True)


def transactions_section(text):
    start = text.index("Recent transactions")
    end = text.index("By category")
    return text[start:end]


def breakdown_section(text):
    return text[text.index("By category"):]


def transaction_count(text):
    match = re.search(r"Transactions\s*</span>\s*<span[^>]*>\s*(\d+)\s*</span>", text)
    assert match, "Could not find the Transactions stat on the profile page"
    return int(match.group(1))


def preset_anchor(text, label):
    match = re.search(
        r"<a\b([^>]*)>\s*" + re.escape(label) + r"\s*</a>", text, re.DOTALL
    )
    assert match, f"Preset link '{label}' not found"
    return match.group(1)


def preset_href(text, label):
    attrs = preset_anchor(text, label)
    match = re.search(r'href="([^"]*)"', attrs)
    assert match, f"Preset '{label}' has no href"
    return html.unescape(match.group(1))


def preset_is_active(text, label):
    attrs = preset_anchor(text, label)
    return "is-active" in attrs or "aria-current" in attrs


def assert_unfiltered(text):
    assert "₹279.54" in text, "Expected all-time total ₹279.54"
    assert transaction_count(text) == 8
    for description in DESCRIPTIONS.values():
        assert description in text, f"Missing '{description}' in unfiltered view"


PRESET_LABELS = ["This Month", "Last 3 Months", "Last 6 Months", "All Time"]


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_profile_without_login_redirects_to_login(self, client):
        response = get_profile(client)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_profile_with_filter_params_without_login_redirects(self, client):
        response = get_profile(client, date_from="2026-09-01", date_to="2026-09-30")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_unauthenticated_filter_does_not_leak_data(self, client):
        response = get_profile(client, date_from="2026-09-01", date_to="2026-09-30")
        body = page(response)
        for description in DESCRIPTIONS.values():
            assert description not in body


# ------------------------------------------------------------------ #
# Unfiltered / All Time                                               #
# ------------------------------------------------------------------ #

class TestUnfiltered:
    def test_no_params_shows_all_expenses(self, auth_client):
        response = get_profile(auth_client)
        assert response.status_code == 200
        assert_unfiltered(page(response))

    def test_no_params_top_category_is_shopping(self, auth_client):
        assert "Shopping" in page(get_profile(auth_client))

    def test_no_params_all_time_preset_is_active(self, auth_client):
        text = page(get_profile(auth_client))
        assert preset_is_active(text, "All Time")
        for label in ("This Month", "Last 3 Months", "Last 6 Months"):
            assert not preset_is_active(text, label), f"{label} should not be active"

    def test_no_params_no_error_message(self, auth_client):
        assert ERROR_MESSAGE not in page(get_profile(auth_client))


# ------------------------------------------------------------------ #
# Custom range                                                        #
# ------------------------------------------------------------------ #

class TestCustomRange:
    def test_custom_range_filters_transactions(self, auth_client):
        response = get_profile(auth_client, date_from="2026-09-05", date_to="2026-09-16")
        assert response.status_code == 200
        section = transactions_section(page(response))
        for day in ("2026-09-05", "2026-09-08", "2026-09-12", "2026-09-16"):
            assert DESCRIPTIONS[day] in section, f"{day} should be included"
        for day in ("2026-09-01", "2026-09-03", "2026-09-20", "2026-09-24"):
            assert DESCRIPTIONS[day] not in section, f"{day} should be excluded"

    def test_custom_range_bounds_are_inclusive(self, auth_client):
        text = page(get_profile(auth_client, date_from="2026-09-05", date_to="2026-09-16"))
        assert DESCRIPTIONS["2026-09-05"] in text, "date_from must be inclusive"
        assert DESCRIPTIONS["2026-09-16"] in text, "date_to must be inclusive"

    def test_custom_range_summary_stats_respect_filter(self, auth_client):
        # 60.00 + 25.75 + 15.00 + 89.99 = 190.74
        text = page(get_profile(auth_client, date_from="2026-09-05", date_to="2026-09-16"))
        assert "₹190.74" in text
        assert "₹279.54" not in text
        assert transaction_count(text) == 4

    def test_custom_range_top_category_reflects_filter(self, auth_client):
        # Only Food (4.50) and Transport (32.00) in range -> Transport on top.
        text = page(get_profile(auth_client, date_from="2026-09-01", date_to="2026-09-03"))
        assert transaction_count(text) == 2
        assert "₹36.50" in text
        assert "Shopping" not in text

    def test_custom_range_category_breakdown_respects_filter(self, auth_client):
        text = page(get_profile(auth_client, date_from="2026-09-01", date_to="2026-09-05"))
        breakdown = breakdown_section(text)
        for category in ("Food", "Transport", "Bills"):
            assert category in breakdown, f"{category} expected in breakdown"
        for category in ("Health", "Entertainment", "Shopping", "Other"):
            assert category not in breakdown, f"{category} should be excluded"

    def test_single_day_range_from_equals_to_is_valid(self, auth_client):
        response = get_profile(auth_client, date_from="2026-09-08", date_to="2026-09-08")
        text = page(response)
        assert ERROR_MESSAGE not in text
        assert transaction_count(text) == 1
        assert DESCRIPTIONS["2026-09-08"] in text
        assert "₹25.75" in text

    def test_custom_range_repeated_food_category_aggregated(self, auth_client):
        # Both Food expenses (4.50 + 42.30 = 46.80) in range.
        text = page(get_profile(auth_client, date_from="2026-09-01", date_to="2026-09-30"))
        assert "₹46.80" in breakdown_section(text)

    def test_custom_range_orders_transactions_newest_first(self, auth_client):
        text = page(get_profile(auth_client, date_from="2026-09-01", date_to="2026-09-30"))
        section = transactions_section(text)
        assert section.index(DESCRIPTIONS["2026-09-24"]) < section.index(
            DESCRIPTIONS["2026-09-01"]
        ), "Transactions should remain ordered newest first"

    def test_custom_range_outside_data_excludes_old_expense(self, auth_client):
        add_expense(DEMO_EMAIL, "2025-01-10", 500.00, "Travel", "Ancient trip")
        text = page(get_profile(auth_client, date_from="2026-09-01", date_to="2026-09-30"))
        assert "Ancient trip" not in text
        assert "₹279.54" in text

    def test_custom_range_form_reflects_selected_dates(self, auth_client):
        text = page(get_profile(auth_client, date_from="2026-09-05", date_to="2026-09-16"))
        assert 'value="2026-09-05"' in text
        assert 'value="2026-09-16"' in text

    def test_custom_range_is_visibly_marked_and_no_preset_active(self, auth_client):
        text = page(get_profile(auth_client, date_from="2026-09-05", date_to="2026-09-16"))
        for label in PRESET_LABELS:
            assert not preset_is_active(text, label), (
                f"{label} must not be active for a custom range"
            )
        assert "is-active" in text, "Custom range should be visibly marked active"

    def test_filter_form_uses_date_inputs_and_apply_button(self, auth_client):
        text = page(get_profile(auth_client))
        assert re.search(r'<input[^>]*type="date"[^>]*name="date_from"', text)
        assert re.search(r'<input[^>]*type="date"[^>]*name="date_to"', text)
        assert "Apply" in text

    def test_filter_form_submits_via_get(self, auth_client):
        text = page(get_profile(auth_client))
        assert re.search(r'<form[^>]*method="get"', text, re.IGNORECASE)


# ------------------------------------------------------------------ #
# Empty range                                                         #
# ------------------------------------------------------------------ #

class TestEmptyRange:
    @pytest.fixture
    def empty_text(self, auth_client):
        response = get_profile(auth_client, date_from="2020-01-01", date_to="2020-01-31")
        assert response.status_code == 200
        return page(response)

    def test_empty_range_shows_zero_total(self, empty_text):
        assert "₹0.00" in empty_text

    def test_empty_range_shows_zero_transactions(self, empty_text):
        assert transaction_count(empty_text) == 0

    def test_empty_range_lists_no_transactions(self, empty_text):
        for description in DESCRIPTIONS.values():
            assert description not in empty_text

    def test_empty_range_has_empty_breakdown(self, empty_text):
        breakdown = breakdown_section(empty_text)
        for category in ("Food", "Transport", "Bills", "Health",
                         "Entertainment", "Shopping", "Other"):
            assert category not in breakdown

    def test_empty_range_shows_no_error_message(self, empty_text):
        assert ERROR_MESSAGE not in empty_text

    def test_new_user_with_no_expenses_can_filter(self, client):
        # A user with no expenses at all should see zeros, not errors.
        conn = db_module.get_db()
        db_module.create_user(
            "Empty User", "empty@example.com", generate_password_hash("emptypass123"),
            conn=conn,
        )
        conn.close()
        log_in(client, "empty@example.com", "emptypass123")
        response = get_profile(client, date_from="2026-09-01", date_to="2026-09-30")
        text = page(response)
        assert response.status_code == 200
        assert "₹0.00" in text
        assert transaction_count(text) == 0


# ------------------------------------------------------------------ #
# Invalid input                                                       #
# ------------------------------------------------------------------ #

MALFORMED = [
    "not-a-date",
    "2026-13-01",
    "2026-02-30",
    "09/01/2026",
    "20260901",
    "2026-9-1x",
    "",
    "   ",
]


class TestInvalidInput:
    @pytest.mark.parametrize("bad", MALFORMED)
    def test_malformed_date_from_falls_back_to_unfiltered(self, auth_client, bad):
        response = get_profile(auth_client, date_from=bad, date_to="2026-09-10")
        assert response.status_code == 200
        assert_unfiltered(page(response))

    @pytest.mark.parametrize("bad", MALFORMED)
    def test_malformed_date_to_falls_back_to_unfiltered(self, auth_client, bad):
        response = get_profile(auth_client, date_from="2026-09-01", date_to=bad)
        assert response.status_code == 200
        assert_unfiltered(page(response))

    def test_both_malformed_falls_back_to_unfiltered(self, auth_client):
        response = get_profile(auth_client, date_from="foo", date_to="bar")
        assert response.status_code == 200
        assert_unfiltered(page(response))

    def test_only_date_from_provided_is_unfiltered(self, auth_client):
        response = get_profile(auth_client, date_from="2026-09-10")
        assert response.status_code == 200
        assert_unfiltered(page(response))

    def test_only_date_to_provided_is_unfiltered(self, auth_client):
        response = get_profile(auth_client, date_to="2026-09-10")
        assert response.status_code == 200
        assert_unfiltered(page(response))

    def test_malformed_date_does_not_show_range_error(self, auth_client):
        text = page(get_profile(auth_client, date_from="not-a-date", date_to="2026-09-10"))
        assert ERROR_MESSAGE not in text, "Malformed dates fall back silently"

    def test_reversed_range_shows_error_message(self, auth_client):
        response = get_profile(auth_client, date_from="2026-09-20", date_to="2026-09-01")
        assert response.status_code == 200
        assert ERROR_MESSAGE in page(response)

    def test_reversed_range_falls_back_to_unfiltered(self, auth_client):
        response = get_profile(auth_client, date_from="2026-09-20", date_to="2026-09-01")
        assert_unfiltered(page(response))

    def test_reversed_range_marks_all_time_active(self, auth_client):
        text = page(get_profile(auth_client, date_from="2026-09-20", date_to="2026-09-01"))
        assert preset_is_active(text, "All Time")

    def test_error_message_not_shown_on_subsequent_clean_request(self, auth_client):
        get_profile(auth_client, date_from="2026-09-20", date_to="2026-09-01")
        text = page(get_profile(auth_client))
        assert ERROR_MESSAGE not in text, "Flash error must not persist"

    def test_extra_unknown_params_are_ignored(self, auth_client):
        response = get_profile(auth_client, foo="bar")
        assert response.status_code == 200
        assert_unfiltered(page(response))


# ------------------------------------------------------------------ #
# Presets                                                             #
# ------------------------------------------------------------------ #

class TestPresets:
    def test_all_four_presets_are_rendered(self, auth_client):
        text = page(get_profile(auth_client))
        for label in PRESET_LABELS:
            assert label in text, f"Preset '{label}' missing"

    def test_all_time_link_is_clean_profile_url(self, auth_client, app=app_module.app):
        with app.test_request_context():
            from flask import url_for
            expected = url_for("profile")
        text = page(get_profile(auth_client))
        assert preset_href(text, "All Time") == expected
        assert "?" not in preset_href(text, "All Time")

    def test_this_month_link_starts_on_first_of_current_month_and_ends_today(
        self, auth_client
    ):
        text = page(get_profile(auth_client))
        href = preset_href(text, "This Month")
        assert "date_from=2026-09-01" in href
        assert "date_to=2026-09-30" in href

    @pytest.mark.parametrize("label", ["Last 3 Months", "Last 6 Months"])
    def test_rolling_window_presets_end_today(self, auth_client, label):
        href = preset_href(page(get_profile(auth_client)), label)
        assert "date_to=2026-09-30" in href
        assert "date_from=" in href

    def test_rolling_windows_start_before_this_month_and_ordered(self, auth_client):
        text = page(get_profile(auth_client))
        starts = {}
        for label in ("This Month", "Last 3 Months", "Last 6 Months"):
            match = re.search(r"date_from=(\d{4}-\d{2}-\d{2})", preset_href(text, label))
            assert match, f"{label} must carry a date_from"
            starts[label] = match.group(1)
        assert starts["Last 6 Months"] < starts["Last 3 Months"] < starts["This Month"]

    @pytest.mark.parametrize("label", ["This Month", "Last 3 Months", "Last 6 Months"])
    def test_preset_links_target_profile_route(self, auth_client, label):
        href = preset_href(page(get_profile(auth_client)), label)
        assert href.startswith("/profile?")

    def test_following_this_month_link_filters_to_current_month(
        self, auth_client, monkeypatch
    ):
        add_expense(DEMO_EMAIL, "2026-08-15", 77.00, "Travel", "August trip")
        href = preset_href(page(get_profile(auth_client)), "This Month")
        response = auth_client.get(href)
        text = page(response)
        assert response.status_code == 200
        assert "August trip" not in text
        assert_unfiltered(text)

    def test_this_month_excludes_expenses_from_previous_month(self, auth_client):
        add_expense(DEMO_EMAIL, "2026-08-31", 12.34, "Travel", "Last-day-of-August")
        href = preset_href(page(get_profile(auth_client)), "This Month")
        text = page(auth_client.get(href))
        assert "Last-day-of-August" not in text
        assert "₹279.54" in text

    def test_this_month_starts_on_first_when_today_is_mid_month(
        self, auth_client, monkeypatch
    ):
        monkeypatch.setattr(app_module, "_today", lambda: date(2026, 9, 10))
        href = preset_href(page(get_profile(auth_client)), "This Month")
        assert "date_from=2026-09-01" in href
        assert "date_to=2026-09-10" in href
        text = page(auth_client.get(href))
        # 4.50 + 32.00 + 60.00 + 25.75 = 122.25 (09-01 .. 09-08)
        assert "₹122.25" in text
        assert transaction_count(text) == 4
        assert DESCRIPTIONS["2026-09-12"] not in text

    def test_this_month_window_ends_today_excluding_future_dates(
        self, auth_client, monkeypatch
    ):
        monkeypatch.setattr(app_module, "_today", lambda: date(2026, 9, 10))
        href = preset_href(page(get_profile(auth_client)), "This Month")
        text = page(auth_client.get(href))
        for day in ("2026-09-12", "2026-09-16", "2026-09-20", "2026-09-24"):
            assert DESCRIPTIONS[day] not in text

    @pytest.mark.parametrize("label", ["Last 3 Months", "Last 6 Months"])
    def test_rolling_presets_exclude_very_old_expenses(self, auth_client, label):
        add_expense(DEMO_EMAIL, "2024-01-10", 500.00, "Travel", "Ancient trip")
        href = preset_href(page(get_profile(auth_client)), label)
        text = page(auth_client.get(href))
        assert "Ancient trip" not in text
        for description in DESCRIPTIONS.values():
            assert description in text, f"{label} should include Sep 2026 expenses"

    @pytest.mark.parametrize("label", ["Last 3 Months", "Last 6 Months"])
    def test_rolling_presets_exclude_future_expenses(self, auth_client, label):
        add_expense(DEMO_EMAIL, "2026-10-15", 55.00, "Travel", "Future trip")
        href = preset_href(page(get_profile(auth_client)), label)
        text = page(auth_client.get(href))
        assert "Future trip" not in text

    def test_all_time_link_includes_very_old_expenses(self, auth_client):
        add_expense(DEMO_EMAIL, "2024-01-10", 500.00, "Travel", "Ancient trip")
        href = preset_href(page(get_profile(auth_client)), "All Time")
        text = page(auth_client.get(href))
        assert "Ancient trip" in text
        assert "₹779.54" in text

    @pytest.mark.parametrize(
        "label, key",
        [
            ("This Month", "this_month"),
            ("Last 3 Months", "last_3"),
            ("Last 6 Months", "last_6"),
        ],
    )
    def test_active_preset_is_marked_after_following_link(
        self, auth_client, label, key
    ):
        href = preset_href(page(get_profile(auth_client)), label)
        text = page(auth_client.get(href))
        assert preset_is_active(text, label), f"{label} should be active"
        for other in PRESET_LABELS:
            if other != label:
                assert not preset_is_active(text, other), (
                    f"{other} should not be active when {label} is"
                )

    def test_preset_selection_shows_fields_not_as_custom(self, auth_client):
        href = preset_href(page(get_profile(auth_client)), "This Month")
        text = page(auth_client.get(href))
        assert 'value="2026-09-01"' not in text, (
            "A preset is not a custom range; date inputs should stay blank"
        )


# ------------------------------------------------------------------ #
# Currency                                                            #
# ------------------------------------------------------------------ #

class TestCurrencySymbol:
    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"date_from": "2026-09-01", "date_to": "2026-09-30"},
            {"date_from": "2026-09-05", "date_to": "2026-09-16"},
            {"date_from": "2020-01-01", "date_to": "2020-01-31"},
            {"date_from": "2026-09-20", "date_to": "2026-09-01"},
            {"date_from": "garbage", "date_to": "2026-09-01"},
        ],
    )
    def test_rupee_symbol_always_present(self, auth_client, params):
        text = page(get_profile(auth_client, **params))
        assert "₹" in text

    def test_rupee_symbol_in_every_section_when_filtered(self, auth_client):
        text = page(get_profile(auth_client, date_from="2026-09-05", date_to="2026-09-16"))
        assert "₹" in transactions_section(text)
        assert "₹" in breakdown_section(text)
        assert "₹190.74" in text


# ------------------------------------------------------------------ #
# Data isolation and query safety                                     #
# ------------------------------------------------------------------ #

class TestIsolationAndSafety:
    def test_filter_never_shows_other_users_rows(self, auth_client):
        response = get_profile(auth_client, date_from="2026-09-01", date_to="2026-09-30")
        text = page(response)
        assert OTHER_DESCRIPTION not in text
        assert "Travel" not in text
        assert "₹999.00" not in text
        assert "₹279.54" in text

    def test_unfiltered_view_never_shows_other_users_rows(self, auth_client):
        text = page(get_profile(auth_client))
        assert OTHER_DESCRIPTION not in text
        assert "₹999.00" not in text

    def test_other_user_sees_only_their_own_filtered_rows(self, client):
        log_in(client, OTHER_EMAIL, "otherpass123")
        text = page(get_profile(client, date_from="2026-09-01", date_to="2026-09-30"))
        assert OTHER_DESCRIPTION in text
        assert "₹999.00" in text
        assert transaction_count(text) == 1
        for description in DESCRIPTIONS.values():
            assert description not in text

    def test_other_user_range_outside_their_data_is_empty(self, client):
        log_in(client, OTHER_EMAIL, "otherpass123")
        text = page(get_profile(client, date_from="2026-09-01", date_to="2026-09-05"))
        assert OTHER_DESCRIPTION not in text
        assert transaction_count(text) == 0
        assert "₹0.00" in text

    @pytest.mark.parametrize(
        "payload",
        [
            "2026-09-01' OR '1'='1",
            "2026-09-01'; DROP TABLE expenses; --",
            "' OR 1=1 --",
            "2026-09-01 UNION SELECT * FROM users",
        ],
    )
    def test_sql_injection_in_date_from_is_harmless(self, auth_client, seeded_db, payload):
        response = get_profile(auth_client, date_from=payload, date_to="2026-09-30")
        assert response.status_code == 200
        assert_unfiltered(page(response))
        conn = db_module.get_db()
        count = conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"]
        conn.close()
        assert count == 9, "expenses table must be intact after injection attempt"

    @pytest.mark.parametrize(
        "payload",
        [
            "2026-09-30' OR '1'='1",
            "2026-09-30'; DELETE FROM expenses; --",
        ],
    )
    def test_sql_injection_in_date_to_is_harmless(self, auth_client, payload):
        response = get_profile(auth_client, date_from="2026-09-01", date_to=payload)
        assert response.status_code == 200
        text = page(response)
        assert OTHER_DESCRIPTION not in text
        assert_unfiltered(text)
        conn = db_module.get_db()
        count = conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"]
        conn.close()
        assert count == 9

    def test_injection_cannot_expose_other_users_data(self, auth_client):
        response = get_profile(
            auth_client, date_from="' OR user_id > 0 --", date_to="2026-09-30"
        )
        assert OTHER_DESCRIPTION not in page(response)

    def test_filtering_does_not_modify_database(self, auth_client):
        get_profile(auth_client, date_from="2026-09-05", date_to="2026-09-16")
        conn = db_module.get_db()
        rows = conn.execute(
            "SELECT date, amount, category, description FROM expenses "
            "WHERE user_id = (SELECT id FROM users WHERE email = ?) ORDER BY date",
            (DEMO_EMAIL,),
        ).fetchall()
        conn.close()
        assert len(rows) == len(SEED)
        assert [(r["date"], r["amount"], r["category"], r["description"]) for r in rows] == sorted(SEED)

    def test_very_long_date_value_does_not_crash(self, auth_client):
        response = get_profile(auth_client, date_from="9" * 5000, date_to="2026-09-30")
        assert response.status_code == 200
        assert_unfiltered(page(response))

    def test_markup_in_date_param_is_escaped(self, auth_client):
        payload = "<script>alert(1)</script>"
        response = get_profile(auth_client, date_from=payload, date_to="2026-09-30")
        assert response.status_code == 200
        assert payload not in page(response)
