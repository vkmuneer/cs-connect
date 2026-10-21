"""CS Connect — Alumni network of the Department of Computer Science,
Sullamussalam Science College, Areekode."""
import os

from flask import Flask, render_template

from app.extensions import csrf, db, login_manager
from app.utils import register_template_helpers
from config import config_map


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_CONFIG", "default")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_map[config_name])

    _ensure_directories(app)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    register_template_helpers(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_context(app)
    _register_security(app)
    _register_cli(app)

    return app


def _register_security(app):
    """Response headers and a check that suspended accounts lose access at once."""
    from flask import flash, redirect, request, url_for
    from flask_login import current_user, logout_user

    @app.before_request
    def _reject_suspended_sessions():
        # is_active only gates sign-in; a session opened before the suspension
        # would otherwise keep working until it expired.
        if current_user.is_authenticated and current_user.is_blocked:
            logout_user()
            flash(
                "This account has been suspended. Please contact the department admin.",
                "danger",
            )
            return redirect(url_for("auth.login"))
        return None

    @app.after_request
    def _security_headers(response):
        # Everything is served from this origin: no inline script, no framing,
        # no content-type guessing, and no referrer leaking to third parties.
        # script-src stays strict — there is no inline script anywhere, which is
        # where XSS would land. style-src allows inline because the templates set
        # computed widths (chart bars) as style attributes.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; object-src 'none'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if not app.debug and app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        # Signed-in pages carry personal data: keep them out of the browser cache
        # so the back button after sign-out does not show them.
        if current_user.is_authenticated and not request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-store, max-age=0")

        # Uploaded files are user content. Gallery and profile images are
        # verified as real images on upload and re-encoded, so they may render
        # inline; anything else (resumes above all) is forced to download.
        if request.path.startswith("/static/uploads/"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            inline = request.path.startswith(
                ("/static/uploads/gallery/", "/static/uploads/photos/")
            )
            if not inline:
                response.headers["Content-Disposition"] = "attachment"
        return response


def _ensure_directories(app):
    for key in ("UPLOAD_FOLDER", "RESUME_FOLDER", "PHOTO_FOLDER", "GALLERY_FOLDER"):
        app.config[key].mkdir(parents=True, exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)


def _register_blueprints(app):
    from app.blueprints.admin import admin_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.internships import internships_bp
    from app.blueprints.jobs import jobs_bp
    from app.blueprints.main import main_bp
    from app.blueprints.messages import messages_bp
    from app.blueprints.profiles import profiles_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(profiles_bp, url_prefix="/alumni")
    app.register_blueprint(jobs_bp, url_prefix="/jobs")
    app.register_blueprint(internships_bp, url_prefix="/internships")
    app.register_blueprint(messages_bp, url_prefix="/messages")
    app.register_blueprint(admin_bp, url_prefix="/admin")


def _register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/error.html", code=403,
                               title="Access denied",
                               message="You do not have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/error.html", code=404,
                               title="Page not found",
                               message="The page you are looking for does not exist."), 404

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("errors/error.html", code=413,
                               title="File too large",
                               message="Uploads are limited to 8 MB."), 413

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return render_template("errors/error.html", code=500,
                               title="Something went wrong",
                               message="An unexpected error occurred. Please try again."), 500


def _register_context(app):
    from datetime import datetime, timezone

    from flask_login import current_user

    from app.models import MULTI_DEPARTMENT, Department, Message, Setting

    @app.context_processor
    def inject_globals():
        unread = 0
        pending_jobs = 0
        pending_users = 0
        pending_internships = 0
        if current_user.is_authenticated:
            unread = Message.unread_count(current_user.id)
            if current_user.is_admin:
                from app.models import Internship, InternshipStatus, Job, JobStatus, User
                pending_jobs = Job.query.filter_by(status=JobStatus.PENDING).count()
                pending_users = User.query.filter_by(is_approved=False, is_blocked=False).count()
                pending_internships = Internship.query.filter_by(
                    status=InternshipStatus.PENDING).count()
        multi_department = False
        departments = []
        try:
            multi_department = Setting.is_on(MULTI_DEPARTMENT)
            if multi_department:
                departments = Department.active()
        except Exception:  # database not initialised yet
            pass

        from app.content import social_links

        try:
            links = social_links()
        except Exception:
            links = []

        return {
            "SOCIAL_LINKS": links,
            "MULTI_DEPARTMENT": multi_department,
            "ACTIVE_DEPARTMENTS": departments,
            "COLLEGE_NAME": "Sullamussalam Science College",
            "COLLEGE_PLACE": "Areekode, Malappuram, Kerala",
            "COLLEGE_URL": "https://www.sscollege.ac.in",
            "DEPARTMENT_NAME": "Department of Computer Science",
            "SITE_NAME": "CS Connect",
            "current_year": datetime.now(timezone.utc).year,
            "unread_messages": unread,
            "pending_jobs_count": pending_jobs,
            "pending_internships_count": pending_internships,
            "pending_users_count": pending_users,
        }


def _register_cli(app):
    import click

    from app.seed import seed_database

    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("sync-schema")
    def sync_schema_command():
        """Create new tables and add new columns without losing data."""
        from app.schema import sync_schema

        changes = sync_schema()
        for change in changes:
            click.echo(f"  {change}")
        click.echo(f"Schema up to date ({len(changes)} change(s)).")

    @app.cli.command("seed")
    @click.option("--demo/--no-demo", default=True, help="Include sample alumni and jobs.")
    def seed(demo):
        """Create tables, the admin account, department content and demo data."""
        from app.schema import sync_schema

        sync_schema()
        generated = seed_database(include_demo=demo)
        click.echo("Seeding complete.")
        if generated:
            click.echo("\nGenerated passwords — copy them now, they are not stored:")
            for who, password in generated.values():
                click.echo(f"  {who}: {password}")
            click.echo(
                "\nSet ADMIN_PASSWORD (and DEMO_PASSWORD) in .env to choose them yourself."
            )

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.argument("password")
    @click.option("--name", default="Administrator")
    def create_admin(email, password, name):
        """Create or promote an administrator account."""
        from app.models import Profile, Role, User

        user = User.query.filter_by(email=email.lower()).first()
        if user is None:
            user = User(email=email.lower(), full_name=name, role=Role.ADMIN, is_approved=True)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(Profile(user_id=user.id, batch_year=1995, is_visible=False))
            click.echo(f"Created admin {email}")
        else:
            user.role = Role.ADMIN
            user.is_approved = True
            user.set_password(password)
            click.echo(f"Promoted {email} to admin and reset the password.")
        db.session.commit()
