# Spec: Add Expense

## Overview
Step 7 replaces the `/expenses/add` stub with a working form that lets a
logged-in user record a new expense (amount, category, date, optional
description). Until now the only expenses in Spendly are the seeded demo rows,
so the profile page, summary stats and category breakdown built in Steps 4–6
cannot reflect anything a real user does. This step closes that loop: a
submitted expense is stored against the current user and immediately appears in
the profile dashboard.

## Depends on
- Step 1: Database setup (`expenses` table with `user_id`, `amount`,
  `category`, `description`, `date`)
- Step 3: Login and logout (`session["user_id"]` identifies the user)
- Step 4: Profile page UI (redirect target after a successful save, and the
  place the "Add expense" entry point lives)
- Step 5/6: Profile data helpers in `database/db.py` (the new expense must show
  up in the existing summary, transactions and category breakdown)

## Routes
- `GET /expenses/add` — render the empty add-expense form (date pre-filled with
  today) — logged-in. Logged-out visitors are redirected to `login`.
- `POST /expenses/add` — validate the submitted form, insert the expense for
  the current user, flash a success message and redirect to `profile` — logged-in.
  On a validation error, re-render the form with an error message and the
  user's previously entered values (HTTP 200).

The existing `/expenses/<id>/edit` and `/expenses/<id>/delete` stubs are NOT
touched (Steps 8 and 9).

## Database changes
No schema changes. The existing `expenses` table already has every required
column (verified in `database/db.py`), and `created_at` has a default.

New helper in `database/db.py` (not a schema change):
- `create_expense(user_id, amount, category, description, date, conn=None)` —
  parameterised `INSERT`, commits, returns `cursor.lastrowid`. Follows the
  `own_conn` / `try ... finally` pattern used by `create_user`.
- `EXPENSE_CATEGORIES` — module-level tuple of allowed categories, matching the
  categories already styled on the profile page and used in the seed data:
  `("Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other")`.

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`; title
  "Add Expense — Spendly"; links `static/css/add_expense.css` through the `head`
  block; a `<form method="post">` with:
  - `amount` — `<input type="number" step="0.01" min="0.01" required>`
  - `category` — `<select required>` built from the categories passed by the route
  - `date` — `<input type="date" required>` defaulting to today
  - `description` — optional `<input type="text" maxlength="200">`
  - a submit button and a "Cancel" link back to the profile page, both built
    with `url_for()`
  - an error block rendered from the `error` variable (same pattern as
    `login.html` / `register.html`)
- **Modify:** `templates/profile.html` — add an "Add expense" button/link
  (`url_for('add_expense')`) near the top of the page so the form is reachable.
  Reuse the existing `.btn-primary` class.

## Files to change
- `app.py`
  - Import `create_expense` and `EXPENSE_CATEGORIES` from `database.db`
  - Replace the `add_expense()` stub with a `GET`/`POST` view. The route does
    only: auth check, read form, validate, call `create_expense`, flash,
    redirect (or re-render with error). No SQL in the route.
  - Add `methods=["GET", "POST"]` to the existing `@app.route("/expenses/add")`
- `database/db.py` — add `EXPENSE_CATEGORIES` and `create_expense()`
- `templates/profile.html` — add the "Add expense" entry point
- `CLAUDE.md` — update the route table: `GET/POST /expenses/add` → Implemented

## Files to create
- `templates/add_expense.html`
- `static/css/add_expense.css` — page-specific styles for the form card
- `tests/test_07-add-expense.py` — written via `/test-feature 07-add-expense`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — `?` placeholders, never f-strings in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles; page styles go in `static/css/add_expense.css`
- All internal links use `url_for()` — never hardcoded URLs
- Auth uses the existing `session.get("user_id")` check; redirect logged-out
  users to `url_for("login")` exactly as `/profile` does. No new auth library.
- The expense is always saved for `session["user_id"]` — never accept a
  `user_id` from the form
- Server-side validation (never rely on the HTML attributes alone):
  - `amount`: must parse as a number, be finite, and be greater than 0;
    reject `nan`, `inf`, negatives and zero. Round to 2 decimals before saving.
  - `category`: must be one of `EXPENSE_CATEGORIES`
  - `date`: must parse with `datetime.strptime(value, "%Y-%m-%d")` and must not
    be in the future
  - `description`: optional; strip whitespace, max 200 characters, store `NULL`
    when empty
  - Any failure → re-render `add_expense.html` with a specific error message
    and the submitted values preserved; do not insert
- Use `abort()` for HTTP errors, never bare error strings
- Amounts display with the ₹ symbol, consistent with the profile page
- Do not implement `/expenses/<id>/edit` or `/expenses/<id>/delete`

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in shows the form with today's date
  pre-filled and all seven categories in the dropdown
- [ ] Submitting a valid expense redirects to `/profile` with a success message
- [ ] The new expense appears in the profile's recent transactions, and the
  total spent, transaction count and category breakdown update to include it
- [ ] The expense is stored against the logged-in user and is not visible to
  other users
- [ ] Leaving the description empty saves successfully (stored as `NULL`)
- [ ] Submitting amount `0`, a negative amount, a non-numeric amount, `nan` or
  `inf` shows an error and saves nothing
- [ ] Submitting a category outside the allowed list (e.g. via a tampered
  request) shows an error and saves nothing
- [ ] Submitting a malformed or future date shows an error and saves nothing
- [ ] After a validation error the form keeps the values the user entered
- [ ] A description containing quotes or `'; DROP TABLE expenses; --` is stored
  and displayed as plain text without breaking the app
- [ ] The profile page has an "Add expense" link that opens the form
- [ ] `/expenses/<id>/edit` and `/expenses/<id>/delete` still return their stub
  responses
- [ ] `pytest` passes, including the new Step 7 tests
