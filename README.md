# CS Connect

Alumni network of the **Department of Computer Science**, Sullamussalam Science
College, Areekode — a Flask application where graduates stay in touch, list
openings for the juniors, and apply to them.

## What it does

- **Alumni directory** — search by name, company or role; filter by programme,
  year of admission, year of completion, skill, or who is hiring.
- **Browse by batch** — every year of admission as a card with its programme
  split, and a page per batch.
- **Job board** — verified members post openings; the department approves each
  one before it goes live. Applications carry the candidate's resume.
- **Placements** — when an employer marks an application *Hired*, the offer is
  counted and shown on a public placements page: no separate bookkeeping.
- **Messaging** — direct messages between members, plus portal notifications for
  approvals and application status changes.
- **Coordinators** — alumni, staff and student coordinators recorded per
  department per academic year.
- **Department pages** — about the college and the department, faculty (current
  and former), news and events, all editable by an administrator.
- **Internships** — alumni offer training places to current students; the
  department approves each one; students express interest in a click and the
  offerer accepts, declines or marks them completed.
- **Talks and sessions** — a member ticks a box to say they will speak to
  students and lists their topics; the department schedules a session, and the
  speaker is notified by portal message every time it changes.
- **Prominent alumni** — a curated page of graduates the department puts
  forward, with a citation for each.
- **Gallery** — albums of photographs from meets and events, uploaded several at
  a time and resized for the web.
- **Coordinators** — per department per academic year, and a separate register
  with a coordinator for every year of admission since the first batch.
- **Editable page text** — every heading, paragraph and button label on the home
  page and the member dashboard is editable from the admin area, and can be put
  back to the shipped wording at any time.
- **Outward links** — college website, LinkedIn, Instagram, YouTube and Facebook,
  shown as icons in the header and footer.
- **College-wide mode** — the portal ships serving Computer Science alone. An
  administrator can open it to the other departments of the college (English,
  Physics, Mathematics, Commerce, Communication Media and History, Economics),
  activating them one at a time.

## Running it locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit it — at minimum set SECRET_KEY
flask seed                  # creates the schema, content and demo data
flask run --port 5001
```

Open <http://127.0.0.1:5001> and sign in as the administrator.

No passwords are hard-coded anywhere. Set `ADMIN_PASSWORD` (and `DEMO_PASSWORD`
for the sample accounts) in your `.env` to choose them; leave them unset and
`flask seed` generates them and prints them once:

```
Seeding complete.

Generated passwords — copy them now, they are not stored:
  admin@sscollege.ac.in: <generated>
  the sample alumni accounts: <generated>
```

To change the administrator password later:

```bash
flask create-admin admin@sscollege.ac.in 'a-password-you-choose'
```

> Port 5000 is taken by AirPlay Receiver on macOS, hence `--port 5001`.

## Commands

| Command | What it does |
| --- | --- |
| `flask seed` | Syncs the schema, then creates content, the admin and demo data |
| `flask seed --no-demo` | The same without the sample alumni and jobs |
| `flask sync-schema` | Creates new tables and adds new columns, without losing data |
| `flask init-db` | Creates the tables only |
| `flask create-admin <email> <password>` | Creates an admin, or promotes an account and resets its password |

## Configuration

Everything is read from the environment (see `.env.example`):

| Variable | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | a development fallback | **Set this.** Sessions and CSRF depend on it |
| `DATABASE_URL` | SQLite in `instance/` | Any SQLAlchemy URL |
| `ADMIN_EMAIL` | `admin@sscollege.ac.in` | The bootstrap administrator |
| `ADMIN_PASSWORD` | none | Used by `flask seed`; one is generated and printed if unset |
| `DEMO_PASSWORD` | none | Password for the sample alumni accounts; generated if unset |
| `REQUIRE_ADMIN_APPROVAL` | `1` | `0` lets registrations in without verification |
| `FLASK_CONFIG` | `development` | `development`, `production` or `testing` |

## Layout

```
app/
  blueprints/   main, auth, profiles, jobs, messages, admin
  templates/    Jinja templates, one folder per blueprint
  static/       stylesheet, script, images, uploads
  models.py     users, profiles, skills, jobs, applications, messages,
                faculty, announcements, departments, coordinators, settings
  forms.py      WTForms definitions
  utils.py      uploads, access-control decorators, department helpers
  schema.py     idempotent schema sync (no Alembic)
  seed.py       initial content and demo data
config.py       configuration objects
wsgi.py         entry point
```

## Tests

```bash
pytest                      # the whole suite
pytest tests/test_security.py -v
```

198 tests across thirteen files, each running against a fresh in-memory database:

| File | Covers |
| --- | --- |
| `tests/test_public_pages.py` | every visitor-facing page, filters, what the directory must not show |
| `tests/test_authorization.py` | admin gates, profile visibility, resumes, messages, job ownership, privilege escalation |
| `tests/test_security.py` | CSRF, XSS, SQL injection, IDOR, uploads, open redirect, session fixation, throttling, headers |
| `tests/test_workflows.py` | registration → verification → posting → moderation → application → hire |
| `tests/test_features.py` | batch browsing, the year range, placements, coordinators, college-wide mode |
| `tests/test_models.py` | model helpers, password hashing, the portal clock, password policy |
| `tests/test_prominent.py` | highlighting alumni, ordering, citations, visibility rules |
| `tests/test_batch_coordinators.py` | the per-year-of-admission register |
| `tests/test_internships.py` | offering, moderation, interest, places, permissions |
| `tests/test_talks.py` | willingness, scheduling, notifications, past sessions |
| `tests/test_gallery.py` | albums, uploads, covers, deletion, image verification |
| `tests/test_content.py` | editing page text, restoring defaults, escaping |
| `tests/test_links.py` | outward links, scheme validation, output filtering |

## Security

What the application does, and what it deliberately leaves to the deployment.

**In the application**

- **Passwords**: Werkzeug hashing (salted per user), a minimum of 8 characters, and a
  check against common passwords and the account's own email. Nothing is logged.
- **Sign-in**: 8 failed attempts per address/email in 5 minutes, then a pause. A
  missing account still performs a hash comparison, so timing does not reveal
  which emails exist. The session id is replaced on sign-in.
- **Suspension** takes effect on the next request, not at the next sign-in.
- **CSRF**: every state-changing request carries a token, sign-out included.
- **XSS**: Jinja autoescaping throughout, no `|safe`, no inline script. Stored
  links are restricted to `http`/`https` on the way in and filtered again on the
  way out, so a `javascript:` URL cannot reach an href.
- **Authorization** is checked per object: profiles respect their visibility,
  messages are readable only by their two parties, applications and applicant
  lists only by the posting's owner or an administrator, and the whole admin
  blueprint is gated in `before_request`.
- **Uploads**: extension allowlist, `secure_filename` plus a random suffix,
  images decoded to prove they are images (and re-encoded, which drops EXIF),
  8 MB per request, and everything under `/static/uploads/` served as an
  attachment with `nosniff`.
- **Redirects** after sign-in must be relative; protocol-relative, backslash,
  userinfo and control-character targets are refused.
- **Headers** on every response: CSP (`script-src 'self'`), `X-Frame-Options:
  DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS when served
  over TLS. Signed-in pages are `no-store`.
- **SQL**: the ORM throughout; the only raw statement is the schema sync, whose
  table and column names come from a literal in `app/schema.py`.
- **Foreign keys** are switched on for SQLite, so deleting a member really does
  remove their profile, postings, applications and messages.
- **Deadlines and "today"** use `PORTAL_TIMEZONE` (default `Asia/Kolkata`), so
  the model and the form agree regardless of the server's clock.

**For the deployment**

- Serve over HTTPS with `FLASK_CONFIG=production`, which marks the cookies secure.
- Put a real rate limiter in the proxy: the sign-in throttle is per worker and
  in memory.
- Run behind a production WSGI server; `flask run` is for development.
- Set a long random `SECRET_KEY` (rotating it signs everyone out).
- Back up `instance/` and `app/static/uploads/` — the database and the uploaded
  resumes and photos.
- There is no email delivery, so password resets are done by an administrator and
  registrations are verified by hand. Email addresses are not confirmed.

## Notes

- Uploads (resumes, photos) are written to `app/static/uploads/` and are not
  tracked by git. Profile photos are downscaled to 600px on the long edge.
- Resumes are downloadable by signed-in, verified members only, and every
  download is written to the activity log.
- There is no migration tool: new tables come from `db.create_all()` and the
  few added columns are applied by `flask sync-schema`.
- The development server is for development. Use a production WSGI server
  (gunicorn, uWSGI) behind a reverse proxy for a real deployment, with
  `FLASK_CONFIG=production`.
