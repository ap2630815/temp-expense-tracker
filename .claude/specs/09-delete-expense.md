# Spec: Delete Expense

## Overview
Step 9 replaces the `/expenses/<id>/delete` stub with a working delete. Steps 7
and 8 let users add and edit expenses, but there is no way to remove a mistaken
or duplicate entry. Each row in the profile's recent transactions gets a
"Delete" button; clicking it opens a small confirmation popup (a native
`<dialog>`) on the profile page itself, shown as a horizontal strip at the top
centre of the page, and confirming submits an ownership-checked `POST`. There is no separate
confirmation page or GET route (state-changing actions must not happen on a
plain `GET`).

## Depends on
- Step 1: Database setup (`expenses` table)
- Step 3: Login and logout (`session["user_id"]`)
- Step 4/5/6: Profile page and its data helpers
- Step 7: Add expense (flash-message conventions)
- Step 8: Edit expense (`get_expense_by_id`, `_require_valid_user`, the
  "Actions" column on the profile transactions table)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense, flash "Expense
  deleted." and redirect to `profile` — logged-in, owner only. Logged-out or
  stale sessions are redirected to `login`. If the expense does not exist **or
  belongs to another user**, `abort(404)`.

`GET /expenses/<id>/delete` is not allowed (405). The endpoint name
`delete_expense` and the path are unchanged.

## Database changes
No schema changes.

New helper in `database/db.py`:
- `delete_expense(expense_id, user_id, conn=None)` — parameterised
  `DELETE FROM expenses WHERE id = ? AND user_id = ?`, commits, returns
  `cursor.rowcount`. Same `own_conn` / `try ... finally` pattern as
  `update_expense`.

## Templates
- **Create:** none.
- **Modify:** `templates/landing.html` — in the signed-in hero (`/` while logged
  in), remove the "Signed in" badge and the black "Log out" button. The
  "Welcome back, <name>." heading and subtitle stay; logging out remains
  available from the navbar "Sign out" link in `base.html`.
- **Modify:** `templates/profile.html` — in the Actions cell,
  next to "Edit", add a `POST` form (`data-confirm-delete`) to
  `url_for('delete_expense', id=t.id)` containing a "Delete" button; add one
  `<dialog id="delete-dialog">` laid out as a horizontal strip: a message block
  ("Delete this expense?" / "This cannot be undone.") on the left, Cancel and
  Delete buttons on the right.

## Files to change
- `app.py` — import `delete_expense as remove_expense`; replace the stub with a
  POST-only view (guard, ownership 404, delete, flash, redirect)
- `database/db.py` — add `delete_expense()`
- `templates/profile.html` — Delete form + popup markup
- `templates/landing.html` — remove the signed-in badge and "Log out" button
- `static/css/profile.css` — delete button and popup styles (CSS variables only).
  The global reset removes a dialog's default auto margin, so the popup must set
  its own position: `position: fixed`, pinned near the top (`inset: 1rem 0 auto
  0`), `margin: 0 auto` for horizontal centring, `width: min(42rem, 100% - 2rem)`,
  `display: flex` while `[open]` (message left, buttons right, wrapping on narrow
  screens), with a dimmed `::backdrop`
- `static/js/main.js` — vanilla JS: intercept `form[data-confirm-delete]`
  submit, show the dialog, submit on confirm (falls back to `window.confirm`
  if `<dialog>` is unsupported)
- `CLAUDE.md` — route table
- Tests in steps 7 and 8 that asserted the old stub text

## Files to create
- `tests/test_09-delete-expense.py`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs; parameterised queries only
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`; no inline styles
- Vanilla JS only
- All internal links/actions use `url_for()`
- Deletion happens only on `POST`
- Ownership enforced in SQL (`WHERE id = ? AND user_id = ?`); never accept
  `user_id` from the form
- `abort(404)` for missing/foreign expenses; no bare error strings
- Do not rename the `delete_expense` endpoint

## Definition of done
- [ ] While signed in, `/` shows no "Signed in" badge and no black "Log out"
  button; the "Welcome back" heading remains and the navbar "Sign out" link
  still logs the user out
- [ ] Each transaction row on `/profile` has a "Delete" button next to "Edit"
- [ ] Clicking Delete opens a small popup; Cancel closes it and nothing is deleted
- [ ] The popup is a horizontal strip at the top centre of the page (horizontally
  centred, near the top edge, message on the left and Cancel/Delete buttons on
  the right), with the rest of the page dimmed behind it
- [ ] On a narrow (phone-width) screen the popup stays within the viewport and
  the buttons wrap below the message
- [ ] Confirming redirects to `/profile` with "Expense deleted." and the row is
  gone; total, count and category breakdown update
- [ ] Deleting the last matching expense leaves the profile rendering its empty
  state
- [ ] `GET /expenses/<id>/delete` returns 405 and deletes nothing
- [ ] POST while logged out redirects to `/login`
- [ ] POST for a missing id or another user's expense returns 404 and changes
  nothing; a second POST returns 404
- [ ] A tampered `user_id` field has no effect
- [ ] `pytest` passes
