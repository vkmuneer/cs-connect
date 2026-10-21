"""Shared fixtures. Each test gets a fresh in-memory database."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    Application, ApplicationStatus, Department, Job, JobStatus, Message, Profile,
    Programme, Role, Setting, Skill, User,
)
from app.utils import reset_login_throttle  # noqa: E402

ADMIN_PASSWORD = "AdminTest@123"
MEMBER_PASSWORD = "MemberTest@123"
TOKEN_RE = re.compile(r'name="csrf_token" (?:type="hidden" )?value="([^"]+)"')


@pytest.fixture
def app(tmp_path):
    application = create_app("testing")
    # Uploads go to a temporary directory: a test must never leave files in
    # app/static/uploads.
    uploads = tmp_path / "uploads"
    application.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret",
        ADMIN_PASSWORD=ADMIN_PASSWORD,
        DEMO_PASSWORD=MEMBER_PASSWORD,
        UPLOAD_FOLDER=uploads,
        RESUME_FOLDER=uploads / "resumes",
        PHOTO_FOLDER=uploads / "photos",
        GALLERY_FOLDER=uploads / "gallery",
    )
    for folder in ("UPLOAD_FOLDER", "RESUME_FOLDER", "PHOTO_FOLDER", "GALLERY_FOLDER"):
        application.config[folder].mkdir(parents=True, exist_ok=True)
    # The context is popped before the tests run: a context left pushed would be
    # reused by every test request, and Flask-Login caches the signed-in user on
    # `g`, so one request's user would leak into the next.
    with application.app_context():
        db.create_all()
        _build_fixture()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()
    reset_login_throttle()


@pytest.fixture
def csrf_app(app):
    """The same app with CSRF switched back on."""
    app.config["WTF_CSRF_ENABLED"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _build_fixture():
    """A small, explicit fixture: one admin, four members, three jobs."""
    cs = Department(
        name="Computer Science", slug="computer-science", short_name="CS",
        is_primary=True, is_active=True, sort_order=1,
        programmes="B.Sc Computer Science\nM.Sc Computer Science\nPh.D Computer Science",
    )
    physics = Department(
        name="Physics", slug="physics", short_name="PHY", is_active=False,
        sort_order=10, programmes="B.Sc Physics\nM.Sc Physics",
    )
    db.session.add_all([cs, physics])
    Setting.put("multi_department_enabled", False)
    Setting.put("first_batch_year", 1995)
    Setting.put("future_years", 1)
    db.session.flush()

    def member(email, name, **kwargs):
        approved = kwargs.pop("approved", True)
        blocked = kwargs.pop("blocked", False)
        role = kwargs.pop("role", Role.MEMBER)
        user = User(email=email, full_name=name, role=role,
                    is_approved=approved, is_blocked=blocked)
        user.set_password(kwargs.pop("password", MEMBER_PASSWORD))
        db.session.add(user)
        db.session.flush()
        profile = Profile(
            user_id=user.id, department_id=cs.id,
            programme=kwargs.pop("programme", Programme.BSC),
            batch_year=kwargs.pop("batch_year", 2018),
            **kwargs,
        )
        db.session.add(profile)
        db.session.flush()
        return user

    admin = member("admin@test.edu", "Admin User", role=Role.ADMIN,
                   password=ADMIN_PASSWORD, is_visible=False)
    employer = member("employer@test.edu", "Employer Member", is_job_provider=True,
                      is_hiring=True, company_name="Acme Ltd", batch_year=2012)
    seeker = member("seeker@test.edu", "Seeker Member", is_job_seeker=True,
                    open_to_work=True, resume_filename="seeker-cv.pdf",
                    programme=Programme.MSC, batch_year=2019)
    hidden = member("hidden@test.edu", "Hidden Member", is_visible=False, batch_year=2016)
    pending = member("pending@test.edu", "Pending Member", approved=False, batch_year=2021)
    blocked = member("blocked@test.edu", "Blocked Member", blocked=True, batch_year=2017)

    seeker.profile.skills = [Skill.get_or_create("Python"), Skill.get_or_create("SQL")]

    live = Job(posted_by_id=employer.id, title="Live Role", company="Acme Ltd",
               location="Kochi", description="A real opening." * 5,
               status=JobStatus.APPROVED, accepts_portal_applications=True)
    pending_job = Job(posted_by_id=employer.id, title="Pending Role", company="Acme Ltd",
                      description="Awaiting moderation." * 5, status=JobStatus.PENDING)
    external = Job(posted_by_id=employer.id, title="External Role", company="Acme Ltd",
                   description="Apply elsewhere." * 5, status=JobStatus.APPROVED,
                   accepts_portal_applications=False, apply_url="https://acme.example/jobs")
    db.session.add_all([live, pending_job, external])
    db.session.flush()
    live.skills = [Skill.get_or_create("Python")]

    db.session.add(Application(
        job_id=live.id, applicant_id=seeker.id, resume_filename="seeker-cv.pdf",
        cover_letter="Please consider me.", status=ApplicationStatus.SHORTLISTED,
    ))
    db.session.add(Message(
        sender_id=employer.id, recipient_id=seeker.id, subject="Hello", body="Interested?",
    ))
    db.session.commit()


# --------------------------------------------------------------------------
# helpers used by the tests
# --------------------------------------------------------------------------
def login(client, email, password=MEMBER_PASSWORD):
    return client.post("/auth/login", follow_redirects=True,
                       data={"email": email, "password": password})


def as_admin(client):
    return login(client, "admin@test.edu", ADMIN_PASSWORD)


def login_csrf(client, email, password=MEMBER_PASSWORD):
    """Sign in on an app that has CSRF enabled."""
    response = client.post("/auth/login", follow_redirects=True, data={
        "email": email, "password": password,
        "csrf_token": csrf_token(client, "/auth/login"),
    })
    assert "Welcome back" in response.get_data(as_text=True), f"sign-in failed for {email}"
    return response


def ids(app):
    """Primary keys of the fixture rows, by a readable name."""
    with app.app_context():
        out = {u.email.split("@")[0]: u.id for u in User.query.all()}
        out["job_live"] = Job.query.filter_by(title="Live Role").first().id
        out["job_pending"] = Job.query.filter_by(title="Pending Role").first().id
        out["job_external"] = Job.query.filter_by(title="External Role").first().id
        out["application"] = Application.query.first().id
        out["message"] = Message.query.first().id
        out["dept_cs"] = Department.query.filter_by(slug="computer-science").first().id
        out["dept_physics"] = Department.query.filter_by(slug="physics").first().id
        return out


def csrf_token(client, path):
    match = TOKEN_RE.search(client.get(path).get_data(as_text=True))
    assert match, f"no CSRF token on {path}"
    return match.group(1)
