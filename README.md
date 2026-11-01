# StudyOS

A personal academic workspace for college and university students: subjects, assignments, notes,
spaced-repetition flashcards, an immersive Pomodoro-style focus timer, study analytics, and a private
account for every user.

Stack: **Python + Flask**, **SQLite**, Jinja2, vanilla JS and CSS. The only dependency is Flask
(Werkzeug and Jinja2 come with it, all pure Python, so it installs on Android/Termux without compiling anything).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then set SECRET_KEY (see below)
python run.py                                          # http://localhost:5000
```

Create an account on the Register page. The database is created and upgraded automatically on start
(`python -m flask --app run init-db` does the same thing on demand).

Generate a secret key: `python -c "import secrets; print(secrets.token_hex(32))"`

### Android (Termux)

```bash
pkg install python git && pip install flask
python run.py            # open http://localhost:5000 in Chrome on the same phone
```

## Upgrading from the old single-user StudyOS

Your existing `data/studyos.db` is detected and used automatically. On first start:

1. A timestamped backup is written next to it (`studyos.db.backup-YYYYMMDD-HHMMSS`).
2. The schema is upgraded in place (versioned migrations, `PRAGMA user_version`); no rows are dropped.
3. The **first account you register adopts all pre-existing data** (subjects, tasks, notes, sessions, flashcards).
   Any later account starts with an empty, private workspace.

Flashcards now keep existing cards when their subject is deleted (previously they were deleted with it).

## Features

| Area | What you get |
|---|---|
| Navigation | Hamburger slide-out menu (scroll-locked page, overlay, Escape / tap-outside / link-select closes, active page derived from the real Flask route). Bottom dock has only Dashboard and Focus Timer. |
| Dashboard | Greeting, date, stats, assignment completion ring, 7-day activity chart, time by subject, streak, deadlines, recent sessions / completed tasks / notes. Everything is computed from your database rows. |
| Focus timer | Focus / short break / long break / custom. Absolute end-timestamp timing (no drift when the tab sleeps or the phone locks), pause/resume/reset/skip, session counter, auto-start options, chime, optional ambient noise (generated in the browser), fullscreen, screen wake-lock, immersive mode with controls that auto-hide after ~3 s and reappear on mouse / touch / keyboard. A finished focus session is saved exactly once (idempotent session key); breaks are never counted; a running timer survives page reloads. |
| Subjects | CRUD, colours, per-subject statistics, links to everything attached to the subject. |
| Assignments | CRUD, priority, deadline, subject, complete/uncomplete, filter, search, sort, overdue highlighting. |
| Notes | Plain-text editor with debounced autosave, search, subject filter, created / modified dates. |
| Flashcards | One card at a time, flip animation, shuffle, previous/next, progress, "Remembered" / "Revise again", Leitner spaced repetition (see below). Separate Manage page for create / edit / delete / search. |
| History | Totals, per-subject time, daily / weekly (8 weeks) / monthly (6 months) charts, recent sessions, date-range and subject filters. |
| Settings | 6 backgrounds, animation on/off, intensity, reduce-motion, accent colour, and all timer options, saved per user. |
| Accounts | Register, login, logout, profile, name/email change, password change, account deletion. |

### Spaced repetition

Leitner boxes 1-5. **Remembered** moves a card up one box and schedules it after 1 / 3 / 7 / 14 / 30 days.
**Revise again** drops it to box 1 and keeps it due today (it also comes back at the end of the current session).
New cards are due immediately. The "Due" tab shows what is due; "All" lets you browse the whole deck.

## Security notes

* Passwords: Werkzeug PBKDF2-SHA256 (600 000 iterations), never stored or logged in plaintext.
* Sessions: signed, `HttpOnly`, `SameSite=Lax`, `Secure` automatically in production, sliding 7-day expiry, session reset on login and password change.
* CSRF: per-session token required on every POST (forms and `fetch`), constant-time comparison.
* Login rate limiting: 5 failures / 15 min per email (and a wider per-IP limit), stored in the database so it works across workers. Registration is limited per IP. Unknown emails take the same time as wrong passwords and get the same message.
* Data isolation: every query on private data filters by `user_id`; ids from the URL or form (including `subject_id`) are checked for ownership; foreign records return 404.
* SQL injection: all values use `?` placeholders; the few dynamic SQL fragments come from fixed whitelists; `LIKE` wildcards in searches are escaped.
* Output is escaped by Jinja; strict CSP (`script-src 'self'`, no inline scripts), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Cache-Control: no-store`.
* Errors: users see a generic page; details go only to the server log.
* Secrets come from environment variables; production refuses to start without `SECRET_KEY`.
* Open redirects on `?next=` are blocked.
* Fonts (DM Sans, Outfit) load from Google Fonts; the CSP allows exactly those two hosts. If you need zero third-party requests, download the fonts into `app/static/fonts` and replace the `<link>` in `base.html`.

## Tests

```bash
python -m unittest discover -s tests -v      # 28 backend tests (auth, isolation, timer API, features, migration)
node --test tests/timer-core.test.js         # 14 timer-engine tests (fake clock)
pip install playwright && playwright install chromium
python tests/browser_check.py                # 81 real-browser checks; screenshots go to instance/shots/
```

## Production / deployment

```bash
export STUDYOS_ENV=production SECRET_KEY=<long random value> DATABASE_PATH=/var/data/studyos.db
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:8000 run:app        # on Windows use: pip install waitress; waitress-serve --port 8000 run:app
```

* Serve over HTTPS (the secure cookie flag is on in production). Behind a reverse proxy set `TRUSTED_PROXIES=1`.
* SQLite needs a **persistent disk**. On hosts with an ephemeral filesystem (free tiers of Render/Heroku-style platforms) use a persistent volume or you will lose data on every deploy.

### GitHub

```bash
git init && git add . && git commit -m "StudyOS"
git branch -M main
git remote add origin https://github.com/<you>/studyos.git
git push -u origin main
```

`.env`, databases, `instance/` and `data/` are git-ignored, so secrets and user data are never pushed.
Then connect the repository to your host (Render, Railway, Fly.io, PythonAnywhere), set the environment
variables above, and use `gunicorn run:app` as the start command.

### Moving to PostgreSQL later

All SQL is confined to `app/db.py`, `app/analytics/service.py` and the blueprint route modules, and uses
standard constructs. Porting means swapping `get_db()` for a psycopg connection (placeholders `?` -> `%s`),
and replacing the handful of SQLite-isms: `INSERT OR IGNORE` (-> `ON CONFLICT DO NOTHING`), `PRAGMA user_version`
migrations (-> a `schema_version` table), `COLLATE NOCASE` (-> `citext` / `lower()`), and `CURRENT_TIMESTAMP` text dates.

## Project layout

```
StudyOS/
├── app/
│   ├── __init__.py        app factory, security headers, error pages
│   ├── db.py              SQLite access + versioned migrations
│   ├── security.py        CSRF, auth guard, rate limiting, validators
│   ├── helpers.py         settings, local time, formatting, icons, nav model
│   ├── ownership.py       ownership checks used by every private lookup
│   ├── auth/ dashboard/ subjects/ tasks/ notes/ flashcards/ timer/ analytics/ settings/   (blueprints)
│   ├── templates/         Jinja templates (+ partials: icon sprite, charts, timer fields)
│   └── static/            css/, js/ (timer-core.js is pure logic), images/ (your logo, all sizes)
├── tests/                 backend, timer-engine and browser tests
├── config.py  run.py  requirements.txt  .env.example  .gitignore
```
