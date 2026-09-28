# Spec: Profile Page

## Overview
This feature replaces the `/profile` stub with a fully designed, fully data-driven profile page matching the reference design (`images/profile-page.png`): a two-column layout with a transaction table on the left and a category breakdown on the right. This revision supersedes the prior hardcoded-mockup iteration of this spec: the page's user info, summary stats, transaction history, and category breakdown are now all computed from the real signed-in user's data in the `users`/`expenses` tables, so each user sees their own actual name, email, signup date, spending totals, and transactions — not shared placeholder data. Additionally, `POST /login` (and the already-logged-in guard on `GET/POST /login`) now redirect to `/profile` instead of `/` (landing), so a successful sign-in lands the user directly on their own real profile data. (That redirect lives in `login()`, documented in `03-login-logout.md`, but is noted here since it changes how and when `/profile` is reached.)

## Depends on
- Step 1: Database setup (schema must exist)
- Step 2: Registration (user accounts must be creatable)
- Step 3: Login + Logout (session must be set; `/profile` must be a protected route)

## Routes
- `GET /profile` — render the profile page for the signed-in user, computed from their real data — logged-in only (redirect to `/login` if not authenticated)
- `POST /login` and the already-authenticated guard on `GET/POST /login` (existing routes, redirect target amended) — now redirect to `url_for('profile')` instead of `url_for('landing')`

## Database changes
No new tables or columns. Three new read helpers added to `database/db.py`, following the existing pattern (parameterized queries, optional `conn` argument, own-connection handling):
- `get_expense_summary(user_id, conn=None)` — returns `{"total_spent", "transaction_count", "top_category"}` for a user: `total_spent`/`transaction_count` from `SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?`; `top_category` from the category with the highest summed `amount` (`GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1`), or `None` if the user has no expenses.
- `get_recent_transactions(user_id, limit=5, conn=None)` — the user's `limit` most recent expenses (`ORDER BY date DESC, id DESC`), returned as `sqlite3.Row`s with `date`, `description`, `category`, `amount`.
- `get_category_breakdown(user_id, conn=None)` — every category the user has spent in, summed and sorted descending by amount, each with a `percent` computed relative to the highest category's total (`round(amount / max_amount * 100)`) for proportional progress bars; returns `[]` for a user with no expenses.

The navbar's signed-in username (see "Navbar changes" below) continues to use the existing `get_user_by_id()` helper via the `app.py` context processor added in the prior iteration — unchanged.

## Navbar changes
The nav displays the signed-in user's real name next to a "Sign out" link (unchanged from the prior iteration):
- `app.py`'s `inject_current_user()` context processor injects `current_user` (via `get_user_by_id()`) into every template's context.
- `templates/base.html`'s nav shows `current_user.name` + "Sign out" when logged in; unchanged when logged out.
- `landing()`'s own explicit `current_user` kwarg still overrides the context processor for that route, so it needs no changes.

## Templates
`templates/profile.html` (existing, unchanged structurally from the prior iteration — only the underlying data source changed, not the markup):
1. **User info card** (full width) — circular avatar with initials derived from the real user's name, real name, real email, "Member since `<Day Month Year>`" derived from the real `users.created_at`
2. **Summary stats row** (3 cards) — uppercase muted labels ("TOTAL SPENT", "TRANSACTIONS", "TOP CATEGORY") with real computed values; `top_category` displays `"—"` when the user has no expenses
3. **Two-column row:** Recent Transactions table (left, real rows, dates formatted `Day Mon Year`) and By Category breakdown (right, real rows, sorted by amount descending) — both render as empty (header-only table, no breakdown rows) for a user with zero expenses, without erroring
- No icons anywhere on this page (unchanged)
- Stacks to a single column on narrow viewports (unchanged)

No template file changes were needed for this revision — the Jinja variable names (`user.name`, `t.category`, `c.percent`, etc.) were already shaped to match real query results.

## Files to change
- `database/db.py` — add `get_expense_summary()`, `get_recent_transactions()`, `get_category_breakdown()`
- `app.py`:
  - `profile()` — replace hardcoded `user`/`summary`/`transactions`/`category_breakdown` with real lookups: `get_user_by_id()` (name/email/formatted `created_at`/derived initials), `get_expense_summary()`, `get_recent_transactions()`, `get_category_breakdown()`
  - `login()` — change both the success redirect and the already-logged-in guard from `url_for('landing')` to `url_for('profile')`
  - New imports: `datetime` (stdlib, for formatting `date`/`created_at` strings), the three new `database.db` helpers

## Files to create
None.

## Category colors
Unchanged from the prior iteration — 7 fixed categories (`Food, Transport, Bills, Health, Entertainment, Shopping, Other`, matching `seed_db()`), each with a distinct CSS-variable-backed color (`--accent`, `--accent-2`, `--info`, `--danger`, `--violet`, `--teal`, `--ink-soft`/`--border-soft`) already added to `style.css`'s `:root`.

## New dependencies
None (`datetime` is standard library).

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()`
- Parameterised queries only — never string-format SQL; all three new helpers use `?` placeholders
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values in templates or `profile.css`
- All templates extend `base.html`
- No inline styles except the established computed `style="width: {{ percent }}%"` on bar fills
- Authentication guard: check `session.get("user_id")`; if absent, `redirect(url_for("login"))`
- DB logic lives only in `database/db.py`, never inline in routes — `profile()` calls the three new helpers rather than running SQL itself
- Category badges use a CSS class per category, not inline colour styles
- No icons on this page
- Every user must see only their own data — all three new helpers filter by `user_id`, and none accept or trust any user-supplied ID (always `session["user_id"]`)
- A user with zero expenses must not crash the page — `get_expense_summary` uses `COALESCE(SUM(...), 0)` and returns `None` (not a query error) for `top_category`; the route substitutes `"—"` for display

## Definition of done
- [ ] Visiting `/profile` without being logged in redirects to `/login`
- [ ] Visiting `/profile` while logged in returns HTTP 200
- [ ] Successful login (`POST /login`) redirects to `/profile`, not `/`
- [ ] The info card shows the actual signed-in user's real name, email, and signup date — not another user's or placeholder data
- [ ] Two different registered users see two different profile pages, each showing only their own data
- [ ] The stats row shows the real total spent, real transaction count, and the real highest-spend category for that user
- [ ] The transaction table shows that user's real recent expenses (up to 5), and the category breakdown shows their real per-category totals sorted descending
- [ ] A newly registered user with zero expenses sees `₹0.00` total, `0` transactions, `—` top category, and an empty (header-only) table and breakdown — no error
- [ ] The navbar shows the signed-in user's real name and a "Sign out" link when logged in; unchanged ("Sign in"/"Get started") when logged out
- [ ] No hex colour values appear in `profile.html` or `profile.css`
- [ ] No icons appear anywhere on the profile page
