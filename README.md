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
