"""The journeys the portal exists for, end to end."""
from tests.conftest import ADMIN_PASSWORD, MEMBER_PASSWORD, as_admin, ids, login


def test_registration_creates_an_unverified_member(client, app):
    from app.models import User
    response = client.post("/auth/register", follow_redirects=True, data={
        "full_name": "New Graduate", "email": "New.Graduate@Test.edu",
        "password": "Testing@123", "confirm": "Testing@123",
        "programme": "B.Sc Computer Science", "batch_year": "2020",
        "graduation_year": "2023", "register_number": "SSC/2020/01",
        "is_job_seeker": "y", "accept_terms": "y",
    })
    assert "awaiting verification" in response.get_data(as_text=True)
    with app.app_context():
        user = User.query.filter_by(email="new.graduate@test.edu").first()
        assert user is not None, "email should be stored lower-cased"
        assert user.is_approved is False
        assert user.role == "member"
        assert user.profile.batch_year == 2020
        assert user.profile.department.slug == "computer-science"


def test_registration_rejects_a_weak_or_mismatched_password(client):
    response = client.post("/auth/register", data={
        "full_name": "Weak Password", "email": "weak@test.edu",
        "password": "short", "confirm": "short",
        "programme": "B.Sc Computer Science", "batch_year": "2020", "accept_terms": "y",
    })
    assert "at least 8 characters" in response.get_data(as_text=True)

    response = client.post("/auth/register", data={
        "full_name": "Mismatch", "email": "mismatch@test.edu",
        "password": "Testing@123", "confirm": "Different@123",
        "programme": "B.Sc Computer Science", "batch_year": "2020", "accept_terms": "y",
    })
    assert "Passwords do not match" in response.get_data(as_text=True)


def test_registration_requires_the_declaration(client, app):
    from app.models import User
    client.post("/auth/register", data={
        "full_name": "No Terms", "email": "noterms@test.edu",
        "password": "Testing@123", "confirm": "Testing@123",
        "programme": "B.Sc Computer Science", "batch_year": "2020",
    })
    with app.app_context():
        assert User.query.filter_by(email="noterms@test.edu").first() is None


def test_duplicate_email_is_refused(client, app):
    from app.models import User
    client.post("/auth/register", data={
        "full_name": "Impostor", "email": "seeker@test.edu",
        "password": "Testing@123", "confirm": "Testing@123",
        "programme": "B.Sc Computer Science", "batch_year": "2020", "accept_terms": "y",
    })
    with app.app_context():
        assert User.query.filter_by(email="seeker@test.edu").count() == 1


def test_admin_verifies_a_member_and_they_are_notified(client, app):
    from app.models import Message, User
    i = ids(app)
    as_admin(client)
    response = client.post(f"/admin/members/{i['pending']}/approve", follow_redirects=True)
    assert "has been verified" in response.get_data(as_text=True)
    with app.app_context():
        from app.extensions import db
        assert db.session.get(User, i["pending"]).is_approved is True
        assert Message.query.filter_by(recipient_id=i["pending"]).count() == 1


def test_member_posting_goes_to_moderation_then_live(client, app):
    from app.extensions import db
    from app.models import Job, JobStatus
    login(client, "employer@test.edu")
    response = client.post("/jobs/post", follow_redirects=True, data={
        "title": "Graduate Engineer", "company": "Acme Ltd", "location": "Kochi",
        "job_type": "Full-time", "work_mode": "Hybrid",
        "description": "We are hiring graduates for our platform team. " * 3,
        "requirements": "Any degree in computing.", "skills": "Python, SQL",
        "min_experience": "0", "max_experience": "2", "vacancies": "2",
        "accepts_portal_applications": "y",
    })
    assert "once an administrator approves" in response.get_data(as_text=True)
    with app.app_context():
        job = Job.query.filter_by(title="Graduate Engineer").first()
        assert job.status == JobStatus.PENDING
        job_id = job.id
    # it is not on the public board yet
    client.post("/auth/logout")
    assert "Graduate Engineer" not in client.get("/jobs/").get_data(as_text=True)

    as_admin(client)
    response = client.post(f"/admin/jobs/{job_id}/approve", follow_redirects=True)
    assert "now live" in response.get_data(as_text=True)
    client.post("/auth/logout")
    assert "Graduate Engineer" in client.get("/jobs/").get_data(as_text=True)


def test_admin_posting_is_live_at_once(client, app):
    from app.models import Job, JobStatus
    as_admin(client)
    client.post("/jobs/post", follow_redirects=True, data={
        "title": "Department Opening", "company": "SSC", "job_type": "Contract",
        "work_mode": "On-site", "description": "A departmental vacancy. " * 4,
        "min_experience": "0", "vacancies": "1", "accepts_portal_applications": "y",
    })
    with app.app_context():
        assert Job.query.filter_by(title="Department Opening").first().status == JobStatus.APPROVED


def test_rejecting_a_posting_tells_the_poster_why(client, app):
    from app.extensions import db
    from app.models import Job, JobStatus, Message
    i = ids(app)
    as_admin(client)
    client.post(f"/admin/jobs/{i['job_pending']}/reject", follow_redirects=True,
                data={"rejection_note": "Not relevant to our graduates"})
    with app.app_context():
        job = db.session.get(Job, i["job_pending"])
        assert job.status == JobStatus.REJECTED
        assert job.rejection_note == "Not relevant to our graduates"
        note = Message.query.filter_by(recipient_id=i["employer"]).order_by(
            Message.id.desc()).first()
        assert "Not relevant to our graduates" in note.body


def test_apply_then_employer_hires_and_it_counts_as_a_placement(client, app):
    from app.extensions import db
    from app.models import Application, ApplicationStatus, Message
    i = ids(app)

    # a second member applies
    login(client, "hidden@test.edu")
    client.post("/alumni/me/edit", follow_redirects=True, data={
        "full_name": "Hidden Member", "programme": "B.Sc Computer Science",
        "batch_year": "2016", "experience_years": "2", "skills": "Python",
        "is_job_seeker": "y", "is_visible": "y",
    })
    response = client.post(f"/jobs/{i['job_live']}/apply", follow_redirects=True,
                           data={"cover_letter": "I would like to apply."})
    assert "attach a resume" in response.get_data(as_text=True)  # no resume on file

    # the fixture applicant already has one; the employer marks them hired
    client.post("/auth/logout")
    login(client, "employer@test.edu")
    response = client.post(f"/jobs/application/{i['application']}/status",
                           follow_redirects=True,
                           data={"status": "hired", "employer_note": "Offer accepted"})
    assert "status updated" in response.get_data(as_text=True)

    with app.app_context():
        application = db.session.get(Application, i["application"])
        assert application.status == ApplicationStatus.HIRED
        assert Application.placement_count() == 1
        assert Message.query.filter_by(recipient_id=i["seeker"]).count() >= 1

    client.post("/auth/logout")
    body = client.get("/placements").get_data(as_text=True)
    assert "Seeker Member" in body and "Live Role" in body


def test_cannot_apply_twice_or_to_your_own_posting(client, app):
    i = ids(app)
    login(client, "seeker@test.edu")
    response = client.get(f"/jobs/{i['job_live']}/apply", follow_redirects=True)
    assert "already applied" in response.get_data(as_text=True)

    client.post("/auth/logout")
    login(client, "employer@test.edu")
    response = client.get(f"/jobs/{i['job_live']}/apply", follow_redirects=True)
    assert "cannot apply to your own posting" in response.get_data(as_text=True)


def test_external_only_posting_refuses_portal_applications(client, app):
    i = ids(app)
    login(client, "seeker@test.edu")
    response = client.get(f"/jobs/{i['job_external']}/apply", follow_redirects=True)
    assert "outside the portal" in response.get_data(as_text=True)


def test_job_form_validation(client, app):
    login(client, "employer@test.edu")
    base = {
        "title": "Bad Job", "company": "Acme", "job_type": "Full-time",
        "work_mode": "Remote", "description": "A description long enough to pass. " * 2,
    }
    # maximum below minimum
    response = client.post("/jobs/post", data=dict(base, min_experience="5",
                                                   max_experience="2"))
    assert "Maximum must be greater" in response.get_data(as_text=True)
    # deadline in the past
    response = client.post("/jobs/post", data=dict(base, deadline="2001-01-01"))
    assert "deadline cannot be in the past" in response.get_data(as_text=True)
    # portal applications off with no other route to apply
    response = client.post("/jobs/post", data=dict(base))
    assert "application link or email" in response.get_data(as_text=True)
    # too short a description
    response = client.post("/jobs/post", data=dict(base, description="short",
                                                   accepts_portal_applications="y"))
    assert "Field must be between 30" in response.get_data(as_text=True)


def test_messaging_round_trip(client, app):
    from app.models import Message
    i = ids(app)
    login(client, "seeker@test.edu")
    response = client.post(f"/messages/to/{i['employer']}", follow_redirects=True,
                           data={"subject": "Thank you", "body": "Thanks for the update."})
    assert "Message sent" in response.get_data(as_text=True)
    with app.app_context():
        assert Message.query.filter_by(sender_id=i["seeker"],
                                       recipient_id=i["employer"]).count() == 1
    # unread count shows in the recipient's navigation
    client.post("/auth/logout")
    login(client, "employer@test.edu")
    assert "Messages" in client.get("/").get_data(as_text=True)


def test_cannot_message_an_unverified_member(client, app):
    i = ids(app)
    login(client, "seeker@test.edu")
    assert client.get(f"/messages/to/{i['pending']}").status_code == 404
    assert client.get(f"/messages/to/{i['seeker']}").status_code == 404  # yourself


def test_password_change(client, app):
    from app.models import User
    login(client, "seeker@test.edu")
    response = client.post("/auth/password", follow_redirects=True, data={
        "current_password": "wrong", "new_password": "NewPass@123",
        "confirm": "NewPass@123",
    })
    assert "current password is incorrect" in response.get_data(as_text=True)

    response = client.post("/auth/password", follow_redirects=True, data={
        "current_password": MEMBER_PASSWORD, "new_password": "NewPass@123",
        "confirm": "NewPass@123",
    })
    assert "Password updated" in response.get_data(as_text=True)
    with app.app_context():
        user = User.query.filter_by(email="seeker@test.edu").first()
        assert user.check_password("NewPass@123")
        assert not user.check_password(MEMBER_PASSWORD)


def test_admin_deleting_a_member_removes_everything_of_theirs(client, app):
    """The cascade that SQLite would skip without foreign keys switched on."""
    from app.models import Application, Job, Message, Profile, User
    i = ids(app)
    as_admin(client)
    response = client.post(f"/admin/members/{i['employer']}/delete", follow_redirects=True)
    assert "has been removed" in response.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(email="employer@test.edu").count() == 0
        assert Profile.query.filter_by(user_id=i["employer"]).count() == 0
        assert Job.query.filter_by(posted_by_id=i["employer"]).count() == 0
        assert Message.query.filter(
            (Message.sender_id == i["employer"]) | (Message.recipient_id == i["employer"])
        ).count() == 0
        assert Application.query.filter_by(job_id=i["job_live"]).count() == 0
        # everyone else is untouched
        assert User.query.filter_by(email="seeker@test.edu").count() == 1
