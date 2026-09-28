# Spec: Registration

## Overview
This step wires up real account creation and sign-in for Spendly. `GET /register` and `GET /login` already render their templates, but submitting either form does nothing yet — there is no server-side handling, no password hashing check, and no session. This step adds `POST` handling to both routes so a visitor can create an account and be signed in, and so an existing user can sign back in. It establishes the session mechanism that every later step (logout, profile, expenses) depends on to know who is currently logged in.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, password hashing with werkzeug) must be complete. It is.

## Routes
- `GET /register` — renders the registration form — public (already implemented, unchanged)
- `POST /register` — creates a new user, hashes the password, starts a session, redirects to `/profile` — public
- `GET /login` — renders the sign-in form — public (already implemented, unchanged)
- `POST /login` — verifies credentials, starts a session, redirects to `/profile` — public

## Database changes
No database changes. The `users` table from Step 1 already has everything needed (`name`, `email`, `password_hash`). Only new query helper functions are needed in `database/db.py`:
- `create_user(name, email, password_hash)` — inserts a row, returns the new user id; must let a `sqlite3.IntegrityError` on duplicate email propagate so the route can catch it and show a friendly error
- `get_user_by_email(email)` — returns the matching row or `None`

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html` — change `<form method="POST" action="/register">` to `action="{{ url_for('register') }}"` (currently hardcoded, violates the no-hardcoded-URLs rule)
  - `templates/login.html` — change `<form method="POST" action="/login">` to `action="{{ url_for('login') }}"` (same issue)

## Files to change
- `app.py` — add `app.config["SECRET_KEY"]`, add `methods=["GET", "POST"]` to `register` and `login`, implement form handling (validate input, call `db.py` helpers, set `session["user_id"]`, redirect)
- `database/db.py` — add `create_user()` and `get_user_by_email()`
- `templates/register.html` — fix form action
- `templates/login.html` — fix form action

## Files to create
None.

## New dependencies
No new dependencies. `werkzeug.security` (`generate_password_hash`, `check_password_hash`) is already available via Flask.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (`generate_password_hash` on register, `check_password_hash` on login)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No DB logic inline in routes — every query goes through `database/db.py`
- Use Flask's `session` (cookie-based) to track `user_id`; no new session table
- Re-render the same template with an `error` message on validation failure (empty fields, duplicate email, wrong password) instead of raising — both templates already have `{% if error %}` blocks ready to use
- Do not implement `/logout` or `/profile` beyond their current stubs — they belong to Steps 3 and 4

## Definition of done
- [ ] Submitting the register form with a new name/email/password creates a row in `users` with a hashed password and redirects to `/profile`
- [ ] Submitting the register form with an email that already exists re-renders `register.html` with an error, and no duplicate row is created
- [ ] Submitting the login form with the seeded demo account (`demo@spendly.com` / `demo123`) redirects to `/profile`
- [ ] Submitting the login form with a wrong password re-renders `login.html` with an error
- [ ] After a successful register or login, `session["user_id"]` is set (verifiable via a temporary print or the Flask debugger)
- [ ] Both form actions use `url_for()`, not hardcoded paths
- [ ] `python app.py` starts without errors on port 5001
