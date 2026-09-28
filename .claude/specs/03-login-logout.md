# Spec: Login and Logout

## Overview
Complete the authentication loop for Spendly. User registration and login (`POST /login`, session creation) were already implemented as part of the registration feature. This step implements the logout flow — replacing the `GET /logout` stub with a route that clears the session — and updates the shared navigation in `base.html` so it reflects whether a visitor is signed in. It also amends `POST /login` so a successful sign-in lands the user back on `/` (the landing page) instead of the `/profile` stub, where they see a personalized "Welcome back" message and a log-out link rather than the marketing hero. Finally, it guards `GET/POST /login` and `GET/POST /register` so an already-authenticated visitor is redirected away from those forms — a logged-in user cannot revisit login or registration until they log out. This closes out the basic auth cycle (register → login → logout) that every later step (profile, expenses) depends on.

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`)
- Step 02 — Registration (user creation, `POST /login` session logic already implemented in `app.py`)

## Routes
- `GET /logout` — clear the session and redirect to the landing page — logged-in (safe to hit while logged out too; it just becomes a no-op redirect)
- `POST /login` — (existing route, redirect target amended) on success, redirect to `/` (landing) instead of `/profile`, so the user immediately sees the personalized "Welcome back" landing state
- `GET /` — (existing route, behavior amended) now looks up the logged-in user (if any) via `get_user_by_id` and passes it to `landing.html` as `current_user`, so the template can render a "Welcome back" state — public route, content varies by auth state
- `GET/POST /register` — (existing route, guard added) if `session.get('user_id')` is already set, redirect immediately to `/` (landing) instead of showing the registration form or processing a submission — logged-out only
- `GET/POST /login` — (existing route, guard added) if `session.get('user_id')` is already set, redirect immediately to `/` (landing) instead of showing the login form or processing a submission — logged-out only

## Database changes
No new tables or columns. A new DB helper is needed in `database/db.py`:
- `get_user_by_id(user_id)` — parameterized `SELECT * FROM users WHERE id = ?`, mirrors the existing `get_user_by_email` pattern. Used by `GET /` to fetch the display name for the welcome message.

## Templates
- **Modify:** `templates/base.html`
  - Nav currently always shows "Sign in" / "Get started" regardless of auth state.
  - Use the `session` object (auto-available in Jinja) to branch: if `session.get('user_id')` is set, show a "Log out" link (`url_for('logout')`) instead of "Sign in" / "Get started".
  - Do not add a link to `/profile` — that stub belongs to Step 4 and is out of scope here.
- **Modify:** `templates/landing.html`
  - The hero section's inner content (`hero-inner`) branches on `current_user`: if set, show a "Welcome back, `<name>`" heading, a short subtext, and a "Log out" link (`url_for('logout')`) in place of the marketing badge/title/subtitle/CTA buttons; otherwise render the existing marketing content unchanged.
  - The decorative `hero-visual` dashboard mock, features section, and CTA section are left untouched regardless of auth state — out of scope for this step.
  - The page's inline "how it works" modal script must null-guard the `how-it-works-btn` listener, since that button is absent from the DOM in the logged-in branch.

## Files to change
- `app.py` — replace the `logout()` stub body with real session-clearing logic; import and use `get_user_by_id`; amend `landing()` to pass `current_user`; amend `login()`'s success redirect to `url_for('landing')`; add an already-logged-in guard at the top of both `login()` and `register()`
- `database/db.py` — add `get_user_by_id()` helper
- `templates/base.html` — conditional nav based on session state
- `templates/landing.html` — conditional hero content based on `current_user`, plus the modal-script null guard

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use f-strings in SQL (`get_user_by_id` uses a `?` placeholder)
- Passwords hashed with werkzeug (N/A — no password handling in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Clear the session with `session.pop("user_id", None)` — must not raise an error if the user isn't logged in
- `GET /logout` only — no form, no POST needed, since it's a simple nav link
- `get_user_by_id` lives in `database/db.py`, never inline SQL in `app.py`
- `landing()` stays one responsibility: look up the current user (if any), render the template — no other logic
- Do not touch or implement the `/profile` stub — it stays exactly as-is until Step 4
- Use `url_for()` for every internal link — never hardcode URLs
- The already-logged-in guard on `login()`/`register()` must run before any `request.method` branching, so a logged-in user is redirected away regardless of GET or POST

## Definition of done
- [ ] While logged in, the nav shows a "Log out" link instead of "Sign in" / "Get started"
- [ ] While logged out, the nav shows "Sign in" / "Get started" as before
- [ ] Clicking "Log out" (or visiting `/logout` directly) while logged in clears the session and redirects to the landing page
- [ ] Visiting `/logout` while already logged out does not error, and redirects to the landing page
- [ ] After logout, visiting a page that reads `session["user_id"]` no longer sees a logged-in user
- [ ] Submitting valid login credentials redirects to `/` instead of `/profile`
- [ ] After logging in, `/` shows "Welcome back, `<name>`" and a "Log out" link instead of the marketing hero
- [ ] After logging out, `/` reverts to showing the marketing hero (badge, title, "Create free account", "See how it works")
- [ ] The "how it works" video modal still opens without a JS console error when the marketing hero is shown (logged out), and no JS error occurs on the welcome-back page (logged in), where the button doesn't exist
- [ ] While logged in, visiting `/login` redirects to `/` instead of showing the login form
- [ ] While logged in, visiting `/register` redirects to `/` instead of showing the registration form
- [ ] While logged out, `/login` and `/register` behave exactly as before (forms render normally)
- [ ] `/profile` remains an unmodified Step 4 stub
