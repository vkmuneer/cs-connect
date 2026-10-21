"""Teacher logins, created by an administrator from the faculty list."""
import re

from tests.conftest import as_admin, ids, login


def _faculty_row(app, **overrides):
    """A faculty record on the public page, with no login yet."""
    from app.extensions import db
    from app.models import Faculty
    data = {
        "name": "Dr. Test Teacher", "designation": "Assistant Professor",
        "qualification": "M.Sc, Ph.D", "specialization": "Networks",
        "email": "teacher@test.edu", "is_current": True, "served_from": 2015,
        "sort_order": 5,
    }
    data.update(overrides)
    with app.app_context():
        row = Faculty(**data)
        db.session.add(row)
        db.session.commit()
        return row.id


def _create_login(client, faculty_id, **overrides):
    data = {"email": "teacher@test.edu", "password": "Teaching@123"}
    data.update(overrides)
    return client.post(f"/admin/faculty/{faculty_id}/login", data=data,
                       follow_redirects=True)


def test_admin_creates_a_login_for_a_teacher(client, app):
    from app.extensions import db
    from app.models import Faculty, Role, User
    faculty_id = _faculty_row(app)
    as_admin(client)
    response = _create_login(client, faculty_id)
    assert "Login created for Dr. Test Teacher" in response.get_data(as_text=True)

    with app.app_context():
        account = User.query.filter_by(email="teacher@test.edu").first()
        assert account is not None
        assert account.role == Role.FACULTY
        assert account.is_faculty and account.is_staff and not account.is_admin
        assert account.is_approved is True
        assert account.can_participate is True
        assert db.session.get(Faculty, faculty_id).user_id == account.id


def test_a_generated_password_is_shown_once(client, app):
    from app.models import User
    faculty_id = _faculty_row(app)
    as_admin(client)
    response = _create_login(client, faculty_id, password="")
    body = response.get_data(as_text=True)
    assert "copy it now" in body
    match = re.search(r"password: (\S+) — copy it now", body)
    assert match, "the generated password must be shown"
    generated = match.group(1)
    with app.app_context():
        assert User.query.filter_by(email="teacher@test.edu").first().check_password(generated)


def test_the_teacher_can_sign_in_and_lands_on_the_staff_dashboard(client, app):
    faculty_id = _faculty_row(app)
    as_admin(client)
    _create_login(client, faculty_id)
    client.post("/auth/logout")

    response = client.post("/auth/login", data={
        "email": "teacher@test.edu", "password": "Teaching@123",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/staff/")

    body = client.get("/staff/", follow_redirects=True).get_data(as_text=True)
    assert "Staff dashboard" in body
    assert "Dr. Test Teacher" in body
    assert "Assistant Professor" in body


def test_a_teacher_edits_their_own_faculty_entry(client, app):
    from app.extensions import db
    from app.models import Faculty
    faculty_id = _faculty_row(app)
    as_admin(client)
    _create_login(client, faculty_id)
    client.post("/auth/logout")
    login(client, "teacher@test.edu", "Teaching@123")

    response = client.post("/staff/entry", follow_redirects=True, data={
        "qualification": "Ph.D (Computer Science) 2024, M.Sc 2010",
        "specialization": "Network Security, IoT",
        "email": "teacher@sscollege.ac.in", "phone": "+91 90000 00000",
        "profile_url": "https://sscollege.ac.in/staff-details/99",
    })
    assert "entry on the faculty page has been updated" in response.get_data(as_text=True)

    with app.app_context():
        row = db.session.get(Faculty, faculty_id)
        assert row.specialization == "Network Security, IoT"
        assert row.email == "teacher@sscollege.ac.in"
        assert row.name == "Dr. Test Teacher", "the name stays with the office"

    client.post("/auth/logout")
    body = client.get("/faculty").get_data(as_text=True)
    assert "Network Security, IoT" in body
    assert "teacher@sscollege.ac.in" in body


def test_a_teacher_cannot_change_their_name_or_designation(client, app):
    """Those fields are not on the self-service form at all."""
    from app.extensions import db
    from app.models import Faculty
    faculty_id = _faculty_row(app)
    as_admin(client)
    _create_login(client, faculty_id)
    client.post("/auth/logout")
    login(client, "teacher@test.edu", "Teaching@123")

    client.post("/staff/entry", follow_redirects=True, data={
        "qualification": "M.Sc", "name": "Professor Impostor",
        "designation": "Head of Department", "is_hod": "y", "served_from": "1990",
    })
    with app.app_context():
        row = db.session.get(Faculty, faculty_id)
        assert row.name == "Dr. Test Teacher"
        assert row.designation == "Assistant Professor"
        assert row.is_hod is False
        assert row.served_from == 2015


def test_a_teacher_cannot_reach_the_admin_area(client, app):
    faculty_id = _faculty_row(app)
    as_admin(client)
    _create_login(client, faculty_id)
    client.post("/auth/logout")
    login(client, "teacher@test.edu", "Teaching@123")

    for path in ["/admin/", "/admin/members", "/admin/faculty", "/admin/content",
                 "/admin/departments", "/admin/talks", "/admin/gallery"]:
        assert client.get(path).status_code == 403, path
    assert client.post(f"/admin/faculty/{faculty_id}/login",
                       data={"email": "x@test.edu"}).status_code == 403


def test_staff_postings_go_live_without_moderation(client, app):
    from app.models import Internship, InternshipStatus, Job, JobStatus
    from app.utils import portal_today
    faculty_id = _faculty_row(app)
    as_admin(client)
    _create_login(client, faculty_id)
    client.post("/auth/logout")
    login(client, "teacher@test.edu", "Teaching@123")

    response = client.post("/jobs/post", follow_redirects=True, data={
        "title": "Project assistant", "company": "SSC Research Centre",
        "job_type": "Contract", "work_mode": "On-site",
        "description": "Assist with a funded project in the department. " * 2,
        "min_experience": "0", "vacancies": "1", "accepts_portal_applications": "y",
    })
    assert "published" in response.get_data(as_text=True)
    with app.app_context():
        assert Job.query.filter_by(title="Project assistant").first().status == JobStatus.APPROVED

    client.post("/internships/offer", follow_redirects=True, data={
        "title": "Research internship", "organisation": "SSC Research Centre",
        "mode": "On-site", "description": "Work on a funded research problem. " * 3,
        "seats": "2", "duration_weeks": "8",
    })
    with app.app_context():
        internship = Internship.query.filter_by(title="Research internship").first()
        assert internship.status == InternshipStatus.APPROVED


def test_a_teacher_may_read_the_directory_and_resumes(client, app):
    i = ids(app)
    faculty_id = _faculty_row(app)
    as_admin(client)
    _create_login(client, faculty_id)
    client.post("/auth/logout")
    login(client, "teacher@test.edu", "Teaching@123")

    assert client.get("/alumni/").status_code == 200
    assert client.get("/alumni/batches").status_code == 200
    # the fixture seeker has a resume filename but no file on disk, so a 404
    # here still proves the permission check let the teacher through
    assert client.get(f"/alumni/resume/{i['seeker']}").status_code in (200, 404)
    assert client.get(f"/messages/to/{i['seeker']}").status_code == 200


def test_resetting_and_revoking_a_login(client, app):
    from app.extensions import db
    from app.models import Faculty, User
    faculty_id = _faculty_row(app)
    as_admin(client)
    _create_login(client, faculty_id)

    response = _create_login(client, faculty_id, password="Changed@12345")
    assert "Login reset" in response.get_data(as_text=True)
    with app.app_context():
        account = User.query.filter_by(email="teacher@test.edu").first()
        assert account.check_password("Changed@12345")

    response = client.post(f"/admin/faculty/{faculty_id}/revoke-login", follow_redirects=True)
    assert "has been removed" in response.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(email="teacher@test.edu").first() is None
        row = db.session.get(Faculty, faculty_id)
        assert row is not None, "the faculty entry survives"
        assert row.user_id is None

    # and that teacher can no longer sign in
    client.post("/auth/logout")
    response = login(client, "teacher@test.edu", "Changed@123")
    assert "Invalid email or password" in response.get_data(as_text=True)


def test_an_email_already_in_use_is_refused(client, app):
    from app.models import Faculty, User
    faculty_id = _faculty_row(app)
    as_admin(client)
    response = _create_login(client, faculty_id, email="seeker@test.edu")
    assert "already belongs to another account" in response.get_data(as_text=True)
    with app.app_context():
        from app.extensions import db
        assert db.session.get(Faculty, faculty_id).user_id is None
        assert User.query.filter_by(email="seeker@test.edu").first().role == "member"


def test_a_member_is_not_staff(client, app):
    login(client, "seeker@test.edu")
    assert client.get("/staff/").status_code == 403
    assert client.get("/staff/entry").status_code == 403


def test_a_teacher_without_an_entry_is_told_so(client, app):
    """An account with the faculty role but no linked record."""
    from app.extensions import db
    from app.models import Role, User
    with app.app_context():
        account = User(email="unlinked@test.edu", full_name="Unlinked Teacher",
                       role=Role.FACULTY, is_approved=True)
        account.set_password("Teaching@123")
        db.session.add(account)
        db.session.commit()

    login(client, "unlinked@test.edu", "Teaching@123")
    assert client.get("/staff/").status_code == 200
    response = client.get("/staff/entry", follow_redirects=True)
    assert "not linked to an entry on the faculty page" in response.get_data(as_text=True)


def test_the_admin_faculty_list_shows_login_state(client, app):
    faculty_id = _faculty_row(app)
    as_admin(client)
    body = client.get("/admin/faculty").get_data(as_text=True)
    assert "No login" in body and "Create login" in body

    _create_login(client, faculty_id)
    body = client.get("/admin/faculty").get_data(as_text=True)
    assert "Can sign in" in body
    assert "never signed in" in body
    assert "Reset password" in body and "Revoke" in body
