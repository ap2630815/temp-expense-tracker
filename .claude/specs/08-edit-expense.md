# Spec: Edit Expense

## Overview
Step 8 replaces the `/expenses/<id>/edit` stub with a working form that lets a
logged-in user correct an existing expense (amount, category, date, description).
Step 7 let users add expenses but there is no way to fix a typo or a wrong
category afterwards. This step adds an "Edit" entry point on each row of the
profile's recent transactions, a pre-filled form, and an ownership-checked
update so users can only modify their own expenses.

## Depends on
- Step 1: Database setup (`expenses` table)
- Step 3: Login and logout (`session["user_id"]`)
- Step 4/5/6: Profile page and its data helpers (entry point and redirect target)
- Step 7: Add expense (reuses `_validate_expense_form`, `EXPENSE_CATEGORIES`,
  the add-expense form layout and `add_expense.css`)

## Routes
- `GET /expenses/<int:id>/edit` — render the add/edit form pre-filled with the
  expense's current values — logged-in, owner only. Logged-out visitors are
  redirected to `login`. If the expense does not exist **or belongs to another
  user**, `abort(404)` (do not reveal that it exists).
- `POST /expenses/<int:id>/edit` — validate the form, update the expense, flash
  a success message and redirect to `profile` — logged-in, owner only. Same
  auth/404 rules as GET. On a validation error, re-render the form with an
  error message and the submitted values (HTTP 200).

The `/expenses/<id>/delete` stub is NOT touched (Step 9).

## Database changes
No schema changes.

New helpers in `database/db.py`:
- `get_expense_by_id(expense_id, user_id, conn=None)` — parameterised
  `SELECT * FROM expenses WHERE id = ? AND user_id = ?`; returns a row or `None`.
  Scoping by `user_id` in SQL is what enforces ownership.
- `update_expense(expense_id, user_id, amount, category, description, date, conn=None)`
  — parameterised `UPDATE ... WHERE id = ? AND user_id = ?`, commits, returns
  `cursor.rowcount` (0 means nothing was updated). Follows the `own_conn` /
  `try ... finally` pattern of `create_expense`. Never modifies `user_id` or
  `created_at`.
- Modify `get_recent_transactions()` to also `SELECT id` so the profile can
  link each row to its edit page. `build_transactions()` in `app.py` passes the
  `id` through.

## Templates
- **Create:** none — reuse `templates/add_expense.html` for both add and edit
  (see Modify), avoiding a duplicated form.
- **Modify:** `templates/add_expense.html` — accept an optional `expense_id`
  (or `is_edit` flag). When editing: title "Edit Expense — Spendly", heading
  "Edit expense", submit button "Save changes", and the form posts to
  `url_for('edit_expense', id=expense_id)`; otherwise unchanged. Cancel link
  still goes to `url_for('profile')`.
- **Modify:** `templates/profile.html` — add an "Actions" column to the recent
  transactions table with an "Edit" link per row
  (`url_for('edit_expense', id=t.id)`).

## Files to change
- `app.py`
  - Import `get_expense_by_id`, `update_expense`, and `abort` from flask
  - Replace the `edit_expense()` stub with a `GET`/`POST` view: auth check,
    fetch owned expense (404 if missing), read form, run `_validate_expense_form`,
    call `update_expense`, flash, redirect (or re-render with error). No SQL in
    the route.
  - Add `"id"` to the dicts built in `build_transactions()`
- `database/db.py` — add `get_expense_by_id()`, `update_expense()`; add `id` to
  the `get_recent_transactions()` select
- `templates/add_expense.html` — edit-mode variants (see above)
- `templates/profile.html` — Edit link column
- `static/css/profile.css` — style for the Edit link (use existing variables)
- `CLAUDE.md` — route table: `GET/POST /expenses/<id>/edit` → Implemented

## Files to create
- `tests/test_08-edit-expense.py` — written via `/test-feature 08-edit-expense`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — `?` placeholders, never f-strings in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles; page styles go in the existing CSS files
- All internal links use `url_for()` — never hardcoded URLs
- Auth uses `session.get("user_id")`; redirect logged-out users to
  `url_for("login")`, and handle a stale session (user no longer exists) exactly
  as `add_expense()` does
- Ownership is enforced in SQL (`WHERE id = ? AND user_id = ?`) for both the
  read and the update; another user's expense id returns 404 on GET and POST
- Never accept `user_id` from the form; the owner never changes
- Reuse `_validate_expense_form` — do not duplicate validation rules (amount > 0
  and finite, valid category, valid non-future date, description ≤ 200 chars,
  empty description stored as `NULL`)
- Use `abort(404)` for missing/foreign expenses, never bare error strings
- Amounts display with the ₹ symbol, consistent with the profile page
- Do not implement `/expenses/<id>/delete`
- Do not rename the `edit_expense` endpoint (templates use `url_for('edit_expense')`)

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting the edit page for your own expense shows the form pre-filled with
  its current amount, category, date and description
- [ ] The edit page heading/button read "Edit expense" / "Save changes"; the add
  page is unchanged
- [ ] Submitting valid changes redirects to `/profile` with a success message
- [ ] The profile's transactions, total spent and category breakdown reflect the
  edited values
- [ ] Clearing the description saves successfully (stored as `NULL`)
- [ ] Amount `0`, negative, non-numeric, `nan`, `inf`, an invalid category, a
  malformed or future date, or a description over 200 chars shows an error,
  keeps the entered values, and leaves the stored expense unchanged
- [ ] Requesting a non-existent expense id returns 404 (GET and POST)
- [ ] Requesting or posting to another user's expense returns 404 and does not
  modify it
- [ ] A tampered `user_id` field in the POST does not change the expense owner
- [ ] Each row in the profile's recent transactions has an "Edit" link that opens
  that expense's edit page
- [ ] A description containing quotes or `'; DROP TABLE expenses; --` is stored
  and displayed as plain text without breaking the app
- [ ] `/expenses/<id>/delete` still returns its stub response
- [ ] The old Step 7 test asserting the edit stub text is updated; `pytest`
  passes, including the new Step 8 tests
