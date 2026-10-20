"""Who may see and do what — the checks that matter most."""
from tests.conftest import ADMIN_PASSWORD, as_admin, ids, login


def test_member_cannot_reach_admin_area(client, app):
    login(client, "seeker@test.edu")
    for path in ["/admin/", "/admin/members", "/admin/jobs", "/admin/departments",
                 "/admin/coordinators", "/admin/placements", "/admin/batches",
                 "/admin/logs", "/admin/faculty", "/admin/pages"]:
        assert client.get(path).status_code == 403, path


def test_member_cannot_post_to_admin_endpoints(client, app):
    i = ids(app)
    login(client, "seeker@test.edu")
    for path in [f"/admin/members/{i['pending']}/approve",
                 f"/admin/members/{i['employer']}/block",
                 f"/admin/jobs/{i['job_pending']}/approve",
                 f"/admin/departments/{i['dept_physics']}/toggle"]:
        assert client.post(path, data={}).status_code == 403, path


def test_admin_reaches_the_admin_area(client, app):
    as_admin(client)
    for path in ["/admin/", "/admin/members", "/admin/batches", "/admin/placements"]:
        assert client.get(path).status_code == 200, path


def test_hidden_profile_is_not_viewable_by_others(client, app):
    i = ids(app)
    assert client.get(f"/alumni/{i['hidden']}").status_code == 404
    login(client, "seeker@test.edu")
    assert client.get(f"/alumni/{i['hidden']}").status_code == 404


def test_hidden_profile_is_viewable_by_its_owner_and_admin(client, app):
    i = ids(app)
    login(client, "hidden@test.edu")
    assert client.get(f"/alumni/{i['hidden']}").status_code == 200
    client.post("/auth/logout")
    as_admin(client)
    assert client.get(f"/alumni/{i['hidden']}").status_code == 200


def test_resume_download_requires_an_approved_member(client, app):
    i = ids(app)
    # a visitor is sent to sign in
    assert client.get(f"/alumni/resume/{i['seeker']}").status_code == 302
    # an unverified member is bounced with a warning
    login(client, "pending@test.edu")
    response = client.get(f"/alumni/resume/{i['seeker']}", follow_redirects=True)
    assert "awaiting verification" in response.get_data(as_text=True)


def test_one_member_cannot_read_another_members_message(client, app):
    i = ids(app)
    login(client, "hidden@test.edu")  # not a party to the fixture message
    assert client.get(f"/messages/{i['message']}").status_code == 403


def test_message_parties_can_read_it(client, app):
    i = ids(app)
    login(client, "seeker@test.edu")
    assert client.get(f"/messages/{i['message']}").status_code == 200
    client.post("/auth/logout")
    login(client, "employer@test.edu")
    assert client.get(f"/messages/{i['message']}").status_code == 200


def test_member_cannot_delete_another_members_message(client, app):
    i = ids(app)
    login(client, "hidden@test.edu")
    assert client.post(f"/messages/{i['message']}/delete").status_code == 403


def test_only_owner_or_admin_manages_a_job(client, app):
    i = ids(app)
    login(client, "seeker@test.edu")
    assert client.get(f"/jobs/{i['job_live']}/edit").status_code == 403
    assert client.get(f"/jobs/{i['job_live']}/applicants").status_code == 403
    assert client.post(f"/jobs/{i['job_live']}/close").status_code == 403


def test_owner_manages_their_own_job(client, app):
    i = ids(app)
    login(client, "employer@test.edu")
    assert client.get(f"/jobs/{i['job_live']}/edit").status_code == 200
    assert client.get(f"/jobs/{i['job_live']}/applicants").status_code == 200


def test_member_cannot_change_an_application_they_do_not_own(client, app):
    i = ids(app)
    login(client, "hidden@test.edu")
    response = client.post(f"/jobs/application/{i['application']}/status",
                           data={"status": "hired"})
    assert response.status_code == 403
    from app.extensions import db
    from app.models import Application
    with app.app_context():
        assert db.session.get(Application, i["application"]).status == "shortlisted"


def test_unverified_member_cannot_post_or_apply(client, app):
    i = ids(app)
    login(client, "pending@test.edu")
    for path in ["/jobs/post", f"/jobs/{i['job_live']}/apply", "/jobs/matches",
                 f"/messages/to/{i['employer']}"]:
        response = client.get(path, follow_redirects=True)
        assert "awaiting verification" in response.get_data(as_text=True), path


def test_suspended_account_cannot_sign_in(client, app):
    response = login(client, "blocked@test.edu")
    assert "suspended" in response.get_data(as_text=True)
    assert client.get("/alumni/me").status_code == 302


def test_suspension_ends_a_live_session(client, app):
    """A session opened before the suspension must stop working at once.

    User.is_active is False for a suspended account, so Flask-Login stops
    treating the session as signed in from the very next request.
    """
    from app.extensions import db
    from app.extensions import db
    from app.models import User
    login(client, "seeker@test.edu")
    assert client.get("/alumni/me").status_code == 200

    with app.app_context():
        user = User.query.filter_by(email="seeker@test.edu").first()
        user.is_blocked = True
        db.session.commit()

    response = client.get("/alumni/me")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]
    # and nothing else behind the login wall is reachable either
    assert client.get("/jobs/post").status_code == 302
    assert client.get("/messages/").status_code == 302
    body = client.get("/", follow_redirects=True).get_data(as_text=True)
    assert "Dashboard" not in body  # the nav no longer shows a signed-in member


def test_admin_cannot_suspend_or_delete_themselves(client, app):
    i = ids(app)
    as_admin(client)
    response = client.post(f"/admin/members/{i['admin']}/block", follow_redirects=True)
    assert "cannot suspend your own account" in response.get_data(as_text=True)
    response = client.post(f"/admin/members/{i['admin']}/delete", follow_redirects=True)
    assert "cannot delete your own account" in response.get_data(as_text=True)
    from app.extensions import db
    from app.models import User
    with app.app_context():
        assert db.session.get(User, i["admin"]).is_blocked is False


def test_member_cannot_promote_themselves(client, app):
    """The role field only exists on the admin form; posting it must not work."""
    from app.models import Role, User
    login(client, "seeker@test.edu")
    client.post("/alumni/me/edit", data={
        "full_name": "Seeker Member", "programme": "M.Sc Computer Science",
        "batch_year": "2019", "experience_years": "1", "role": "admin",
        "is_approved": "y", "is_visible": "y",
    }, follow_redirects=True)
    with app.app_context():
        user = User.query.filter_by(email="seeker@test.edu").first()
        assert user.role == Role.MEMBER
        assert user.is_approved is True  # unchanged, not escalated


def test_profile_save_without_the_skills_field_does_not_crash(client, app):
    """A partial POST must not 500 — WTForms leaves the relationship in place."""
    from app.extensions import db
    from app.models import User
    login(client, "seeker@test.edu")
    response = client.post("/alumni/me/edit", data={
        "full_name": "Seeker Member", "programme": "M.Sc Computer Science",
        "batch_year": "2019", "experience_years": "1", "is_visible": "y",
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="seeker@test.edu").first()
        assert {s.name for s in user.profile.skills} == {"Python", "SQL"}
