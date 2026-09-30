import calendar
import sqlite3
from datetime import date, datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import (
    get_db,
    init_db,
    seed_db,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_expense_summary,
    get_recent_transactions,
    get_category_breakdown,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key-change-in-production"  # dev only

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Context processors                                                  #
# ------------------------------------------------------------------ #

@app.context_processor
def inject_current_user():
    current_user = None
    if session.get("user_id"):
        current_user = get_user_by_id(session["user_id"])
    return {"current_user": current_user}


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    current_user = None
    if "user_id" in session:
        current_user = get_user_by_id(session["user_id"])
    return render_template("landing.html", current_user=current_user)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password or not confirm_password:
            return render_template("register.html", error="Please fill in all fields.")

        if len(password) < 8:
            return render_template(
                "register.html", error="Password must be at least 8 characters."
            )

        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match.")

        password_hash = generate_password_hash(password)
        try:
            user_id = create_user(name, email, password_hash)
        except sqlite3.IntegrityError:
            return render_template(
                "register.html", error="An account with that email already exists."
            )

        session["user_id"] = user_id
        return redirect(url_for("profile"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template(
                "login.html", error="Please enter your email and password."
            )

        user = get_user_by_email(email)
        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid email or password.")

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


def _today():
    return date.today()


def _parse_iso_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError):
        return None


def _months_back(today, months):
    year, month_index = divmod(today.year * 12 + today.month - 1 - months, 12)
    month = month_index + 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_filter_presets(today):
    end = today.isoformat()
    return [
        {"key": "this_month", "label": "This Month",
         "date_from": today.replace(day=1).isoformat(), "date_to": end},
        {"key": "last_3", "label": "Last 3 Months",
         "date_from": _months_back(today, 3).isoformat(), "date_to": end},
        {"key": "last_6", "label": "Last 6 Months",
         "date_from": _months_back(today, 6).isoformat(), "date_to": end},
        {"key": "all", "label": "All Time", "date_from": None, "date_to": None},
    ]


def resolve_date_filter(raw_from, raw_to):
    date_from = _parse_iso_date(raw_from)
    date_to = _parse_iso_date(raw_to)
    if date_from is None or date_to is None:
        return None, None, None
    if date_from > date_to:
        return None, None, "Start date must be before end date."
    return date_from, date_to, None


# ==== SECTION 1: TRANSACTIONS (subagent 1 only) ==== #
def build_transactions(user_id, date_from=None, date_to=None):
    return [
        {
            "date": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": row["description"] or row["category"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in get_recent_transactions(
            user_id, limit=10, date_from=date_from, date_to=date_to
        )
    ]
# ==== END SECTION 1 ==== #


# ==== SECTION 2: SUMMARY (subagent 2 only) ==== #
def build_summary(user_id, date_from=None, date_to=None):
    summary = get_expense_summary(user_id, date_from=date_from, date_to=date_to)
    summary["top_category"] = summary["top_category"] or "—"
    return summary
# ==== END SECTION 2 ==== #


# ==== SECTION 3: CATEGORY BREAKDOWN (subagent 3 only) ==== #
def build_category_breakdown(user_id, date_from=None, date_to=None):
    rows = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)
    if not rows:
        return []
    total = sum(item["amount"] for item in rows)
    if not total:
        return []
    items = [dict(item) for item in rows]
    for item in items:
        item["pct"] = int(item["amount"] * 100 // total)
    remainder = 100 - sum(item["pct"] for item in items)
    if remainder:
        max(items, key=lambda item: item["amount"])["pct"] += remainder
    return items
# ==== END SECTION 3 ==== #


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user_row = get_user_by_id(user_id)
    created_at = datetime.strptime(user_row["created_at"], "%Y-%m-%d %H:%M:%S")
    name_parts = user_row["name"].split()
    user = {
        "name": user_row["name"],
        "email": user_row["email"],
        "initials": "".join(part[0].upper() for part in name_parts[:2]),
        "member_since": created_at.strftime("%d %b %Y"),
    }

    date_from, date_to, filter_error = resolve_date_filter(
        request.args.get("date_from"), request.args.get("date_to")
    )
    if filter_error:
        flash(filter_error)

    presets = get_filter_presets(_today())
    for preset in presets:
        preset["active"] = (preset["date_from"], preset["date_to"]) == (date_from, date_to)
    date_filter = {
        "presets": presets,
        "date_from": date_from,
        "date_to": date_to,
        "custom_active": date_from is not None
        and not any(preset["active"] for preset in presets),
    }

    return render_template(
        "profile.html",
        user=user,
        date_filter=date_filter,
        summary=build_summary(user_id, date_from, date_to),
        transactions=build_transactions(user_id, date_from, date_to),
        category_breakdown=build_category_breakdown(user_id, date_from, date_to),
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
