"""Attack-shaped tests: CSRF, XSS, injection, IDOR, traversal, throttling."""
import io

import pytest

from tests.conftest import (
    ADMIN_PASSWORD, MEMBER_PASSWORD, as_admin, csrf_token, ids, login, login_csrf,
)


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------
def test_state_changing_posts_need_a_token(csrf_app):
    client = csrf_app.test_client()
    i = ids(csrf_app)
    login_csrf(client, "employer@test.edu")  # a real session, so 400 means CSRF

    for path, data in [
        ("/alumni/me/edit", {"full_name": "X", "programme": "B.Sc Computer Science",
                             "batch_year": "2012"}),
        ("/jobs/post", {"title": "T", "company": "C", "description": "d" * 40,
                        "job_type": "Full-time", "work_mode": "Remote"}),
        (f"/messages/to/{i['seeker']}", {"subject": "s", "body": "hello there"}),
        (f"/jobs/{i['job_live']}/close", {}),
        ("/auth/logout", {}),
    ]:
        response = client.post(path, data=data)
        assert response.status_code == 400, f"{path} accepted a tokenless POST"


def test_a_valid_token_is_accepted(csrf_app):
    client = csrf_app.test_client()
    login_csrf(client, "employer@test.edu")
    token = csrf_token(client, "/alumni/me/edit")
    response = client.post("/alumni/me/edit", follow_redirects=True, data={
        "full_name": "Employer Member", "programme": "B.Sc Computer Science",
        "batch_year": "2012", "experience_years": "5", "is_visible": "y",
        "csrf_token": token,
    })
    assert response.status_code == 200
    assert "profile has been updated" in response.get_data(as_text=True)


def test_a_foreign_token_is_rejected(csrf_app):
    """A token minted for one session must not work in another."""
    attacker = csrf_app.test_client()
    login_csrf(attacker, "hidden@test.edu")
    stolen = csrf_token(attacker, "/alumni/me/edit")

    victim = csrf_app.test_client()
    login_csrf(victim, "employer@test.edu")
    response = victim.post("/alumni/me/edit", data={
        "full_name": "Hacked", "programme": "B.Sc Computer Science",
        "batch_year": "2012", "csrf_token": stolen,
    })
    assert response.status_code == 400


# --------------------------------------------------------------------------
# Cross-site scripting
# --------------------------------------------------------------------------
XSS = '<script>alert("xss")</script>'


def test_profile_text_is_escaped(client, app):
    i = ids(app)
    login(client, "seeker@test.edu")
    client.post("/alumni/me/edit", follow_redirects=True, data={
        "full_name": f"Seeker {XSS}", "programme": "M.Sc Computer Science",
        "batch_year": "2019", "experience_years": "1",
        "headline": XSS, "about": f"line one{XSS}\nline two",
        "location": XSS, "skills": f"Python, {XSS}", "is_visible": "y",
    })
    body = client.get(f"/alumni/{i['seeker']}").get_data(as_text=True)
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_nl2br_escapes_before_adding_breaks(app):
    from app.utils import nl2br
    rendered = str(nl2br('a\n<img src=x onerror=alert(1)>'))
    assert "<br>" in rendered
    assert "<img" not in rendered
    assert "&lt;img" in rendered


def test_job_text_is_escaped(client, app):
    login(client, "employer@test.edu")
    client.post("/jobs/post", follow_redirects=True, data={
        "title": f"Role {XSS}", "company": f"Acme {XSS}", "job_type": "Full-time",
        "work_mode": "Remote", "description": f"About the role {XSS} " * 3,
        "min_experience": "0", "vacancies": "1",
    })
    body = client.get("/jobs/").get_data(as_text=True)
    assert "<script>alert" not in body


@pytest.mark.parametrize("hostile", [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "javascript://comment%0Aalert(1)",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "vbscript:msgbox(1)",
])
def test_hostile_url_schemes_are_refused(client, app, hostile):
    """A stored javascript: URL would execute from the profile page's href."""
    from app.models import User
    login(client, "seeker@test.edu")
    response = client.post("/alumni/me/edit", follow_redirects=True, data={
        "full_name": "Seeker Member", "programme": "M.Sc Computer Science",
        "batch_year": "2019", "experience_years": "1", "is_visible": "y",
        "website_url": hostile,
    })
    assert "http:// or https://" in response.get_data(as_text=True)
    with app.app_context():
        user = User.query.filter_by(email="seeker@test.edu").first()
        assert not user.profile.website_url


def test_safe_url_filter_blanks_anything_odd(app):
    from app.utils import safe_external_url
    assert safe_external_url("https://example.com") == "https://example.com"
    assert safe_external_url("http://example.com") == "http://example.com"
    assert safe_external_url("javascript:alert(1)") is None
    assert safe_external_url("data:text/html,<script>") is None
    assert safe_external_url("") is None
    assert safe_external_url(None) is None


def test_https_url_is_still_accepted(client, app):
    from app.models import User
    login(client, "seeker@test.edu")
    client.post("/alumni/me/edit", follow_redirects=True, data={
        "full_name": "Seeker Member", "programme": "M.Sc Computer Science",
        "batch_year": "2019", "experience_years": "1", "is_visible": "y",
        "website_url": "https://seeker.example.com/cv",
    })
    with app.app_context():
        user = User.query.filter_by(email="seeker@test.edu").first()
        assert user.profile.website_url == "https://seeker.example.com/cv"


# --------------------------------------------------------------------------
# Injection
# --------------------------------------------------------------------------
@pytest.mark.parametrize("payload", [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "1 UNION SELECT password_hash FROM users",
    "%' OR 1=1 --",
])
def test_search_inputs_cannot_inject_sql(client, app, payload):
    from app.models import User
    assert client.get("/alumni/", query_string={"q": payload}).status_code == 200
    assert client.get("/jobs/", query_string={"q": payload}).status_code == 200
    assert client.get("/alumni/", query_string={"skill": payload}).status_code == 200
    with app.app_context():
        assert User.query.count() == 6  # the fixture is intact


def test_hostile_values_in_numeric_query_args(client, app):
    for path in ["/alumni/?batch_year=abc", "/alumni/?page=-1", "/alumni/?page=99999",
                 "/jobs/?page=abc", "/alumni/batches?department=abc"]:
        assert client.get(path).status_code in (200, 404), path


# --------------------------------------------------------------------------
# Insecure direct object references
# --------------------------------------------------------------------------
def test_object_ids_cannot_be_walked(client, app):
    """Enumerating ids must not hand out anything private."""
    login(client, "hidden@test.edu")
    for object_id in range(1, 40):
        assert client.get(f"/messages/{object_id}").status_code in (200, 403, 404)
        assert client.get(f"/jobs/{object_id}/applicants").status_code in (200, 403, 404)
        assert client.post(f"/jobs/application/{object_id}/status",
                           data={"status": "hired"}).status_code in (302, 403, 404)


def test_applicant_list_is_not_leaked_by_id(client, app):
    i = ids(app)
    login(client, "hidden@test.edu")
    response = client.get(f"/jobs/{i['job_live']}/applicants")
    assert response.status_code == 403
    assert "Seeker Member" not in response.get_data(as_text=True)


# --------------------------------------------------------------------------
# Uploads
# --------------------------------------------------------------------------
def test_executable_disguised_as_a_resume_is_refused(client, app):
    login(client, "seeker@test.edu")
    response = client.post("/alumni/me/edit", follow_redirects=True,
                           content_type="multipart/form-data", data={
        "full_name": "Seeker Member", "programme": "M.Sc Computer Science",
        "batch_year": "2019", "experience_years": "1", "is_visible": "y",
        "resume": (io.BytesIO(b"MZ\x90\x00 not a document"), "payload.exe"),
    })
    assert "Word documents only" in response.get_data(as_text=True)


def test_html_disguised_as_an_image_is_refused(client, app):
    login(client, "seeker@test.edu")
    response = client.post("/alumni/me/edit", follow_redirects=True,
                           content_type="multipart/form-data", data={
        "full_name": "Seeker Member", "programme": "M.Sc Computer Science",
        "batch_year": "2019", "experience_years": "1", "is_visible": "y",
        "photo": (io.BytesIO(b"<html><script>alert(1)</script></html>"), "evil.png"),
    })
    assert "not a readable image" in response.get_data(as_text=True)


def test_upload_filename_cannot_traverse(app):
    """A crafted filename must not escape the upload folder."""
    from werkzeug.datastructures import FileStorage
    from app.utils import save_upload
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buffer, "PNG")
    buffer.seek(0)
    with app.test_request_context():
        stored = save_upload(
            FileStorage(buffer, filename="../../../../etc/passwd.png",
                        content_type="image/png"),
            "photo",
        )
        assert "/" not in stored and ".." not in stored
        (app.config["PHOTO_FOLDER"] / stored).unlink()


def test_oversized_upload_is_rejected(client, app):
    login(client, "seeker@test.edu")
    too_big = io.BytesIO(b"x" * (app.config["MAX_CONTENT_LENGTH"] + 1024))
    response = client.post("/alumni/me/edit", content_type="multipart/form-data", data={
        "full_name": "Seeker Member", "programme": "M.Sc Computer Science",
        "batch_year": "2019", "resume": (too_big, "huge.pdf"),
    })
    assert response.status_code == 413


# --------------------------------------------------------------------------
# Sessions, redirects, throttling, headers
# --------------------------------------------------------------------------
def test_login_does_not_follow_an_external_next(client, app):
    response = client.post("/auth/login?next=https://evil.example.com/steal", data={
        "email": "seeker@test.edu", "password": MEMBER_PASSWORD,
    })
    assert response.status_code == 302
    assert "evil.example.com" not in response.headers["Location"]


@pytest.mark.parametrize("target", [
    "//evil.example.com", "https://evil.example.com", "http:/\\evil.example.com",
    "/\\evil.example.com", "javascript:alert(1)",
])
def test_open_redirect_targets_are_refused(client, app, target):
    response = client.post("/auth/login", query_string={"next": target}, data={
        "email": "seeker@test.edu", "password": MEMBER_PASSWORD,
    })
    assert response.status_code == 302
    assert "evil.example.com" not in response.headers["Location"]
    assert not response.headers["Location"].lower().startswith("javascript")


def test_session_id_changes_on_sign_in(client, app):
    """Guards against session fixation."""
    client.get("/auth/login")
    before = client.get_cookie("csconnect_session")
    login(client, "seeker@test.edu")
    after = client.get_cookie("csconnect_session")
    assert after is not None
    assert before is None or before.value != after.value


def test_repeated_bad_passwords_are_throttled(client, app):
    from app.utils import LOGIN_MAX_ATTEMPTS
    for _ in range(LOGIN_MAX_ATTEMPTS):
        response = login(client, "seeker@test.edu", "wrong-password")
        assert "Invalid email or password" in response.get_data(as_text=True)

    response = login(client, "seeker@test.edu", "wrong-password")
    assert "Too many failed sign-in attempts" in response.get_data(as_text=True)
    # and the correct password is refused while the window is open
    response = login(client, "seeker@test.edu", MEMBER_PASSWORD)
    assert "Too many failed sign-in attempts" in response.get_data(as_text=True)


def test_throttle_is_cleared_by_a_successful_sign_in(client, app):
    from app.utils import LOGIN_MAX_ATTEMPTS
    for _ in range(LOGIN_MAX_ATTEMPTS - 1):
        login(client, "seeker@test.edu", "wrong-password")
    response = login(client, "seeker@test.edu", MEMBER_PASSWORD)
    assert "Welcome back" in response.get_data(as_text=True)
    client.post("/auth/logout")
    response = login(client, "seeker@test.edu", "wrong-password")
    assert "Invalid email or password" in response.get_data(as_text=True)


def test_security_headers_are_present(client):
    response = client.get("/")
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_password_hashes_are_never_rendered(client, app):
    i = ids(app)
    as_admin(client)
    for path in ["/", "/alumni/", f"/alumni/{i['seeker']}", "/admin/members",
                 f"/admin/members/{i['seeker']}/edit", "/admin/logs"]:
        body = client.get(path).get_data(as_text=True)
        assert "pbkdf2:" not in body and "scrypt:" not in body, path


def test_passwords_are_hashed_not_stored(app):
    from app.models import User
    with app.app_context():
        user = User.query.filter_by(email="seeker@test.edu").first()
        assert MEMBER_PASSWORD not in user.password_hash
        assert user.password_hash.startswith(("pbkdf2:", "scrypt:"))
        assert user.check_password(MEMBER_PASSWORD)
        assert not user.check_password(MEMBER_PASSWORD.upper())
