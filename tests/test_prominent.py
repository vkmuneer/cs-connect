"""Highlighting prominent alumni, and who may do it."""
from tests.conftest import as_admin, ids, login


def _highlight(client, user_id, **overrides):
    data = {
        "featured_title": "Distinguished Alumna 2026",
        "featured_note": "Led the platform team and mentors every junior who asks.",
        "featured_order": "1", "is_featured": "y",
    }
    data.update(overrides)
    return client.post(f"/admin/members/{user_id}/highlight", data=data,
                       follow_redirects=True)


def test_public_page_is_empty_until_someone_is_highlighted(client, app):
    response = client.get("/alumni/prominent")
    assert response.status_code == 200
    assert "No alumni have been highlighted yet" in response.get_data(as_text=True)


def test_admin_highlights_a_member(client, app):
    from app.models import User
    i = ids(app)
    as_admin(client)
    response = _highlight(client, i["seeker"])
    assert "now appears among the prominent alumni" in response.get_data(as_text=True)

    with app.app_context():
        profile = User.query.filter_by(email="seeker@test.edu").first().profile
        assert profile.is_featured is True
        assert profile.featured_title == "Distinguished Alumna 2026"
        assert profile.featured_at is not None

    client.post("/auth/logout")
    body = client.get("/alumni/prominent").get_data(as_text=True)
    assert "Seeker Member" in body
    assert "Distinguished Alumna 2026" in body
    assert "mentors every junior" in body


def test_highlight_shows_on_the_profile_the_card_and_the_home_page(client, app):
    i = ids(app)
    as_admin(client)
    _highlight(client, i["seeker"])
    client.post("/auth/logout")

    body = client.get(f"/alumni/{i['seeker']}").get_data(as_text=True)
    assert "Distinguished Alumna 2026" in body
    assert "mentors every junior" in body

    assert "Prominent alumnus" in client.get("/alumni/").get_data(as_text=True)

    body = client.get("/").get_data(as_text=True)
    assert "Prominent alumni" in body and "Seeker Member" in body


def test_citation_is_escaped(client, app):
    i = ids(app)
    as_admin(client)
    _highlight(client, i["seeker"], featured_note='<script>alert("x")</script>',
               featured_title='<img src=x onerror=alert(1)>')
    client.post("/auth/logout")
    body = client.get("/alumni/prominent").get_data(as_text=True)
    assert "<script>alert" not in body
    assert "<img src=x" not in body
    assert "&lt;script&gt;" in body


def test_removing_the_highlight(client, app):
    from app.models import User
    i = ids(app)
    as_admin(client)
    _highlight(client, i["seeker"])
    response = client.post(f"/admin/members/{i['seeker']}/unhighlight", follow_redirects=True)
    assert "no longer highlighted" in response.get_data(as_text=True)
    with app.app_context():
        profile = User.query.filter_by(email="seeker@test.edu").first().profile
        assert profile.is_featured is False
        assert profile.featured_at is None
    client.post("/auth/logout")
    assert "Seeker Member" not in client.get("/alumni/prominent").get_data(as_text=True)


def test_unticking_the_box_also_removes_them(client, app):
    i = ids(app)
    as_admin(client)
    _highlight(client, i["seeker"])
    response = _highlight(client, i["seeker"], is_featured="")
    assert "no longer highlighted" in response.get_data(as_text=True)


def test_order_decides_who_comes_first(client, app):
    i = ids(app)
    as_admin(client)
    _highlight(client, i["seeker"], featured_order="5", featured_title="Second Pick")
    _highlight(client, i["employer"], featured_order="1", featured_title="First Pick")
    client.post("/auth/logout")
    body = client.get("/alumni/prominent").get_data(as_text=True)
    assert body.index("First Pick") < body.index("Second Pick")


def test_an_unlisted_or_unverified_member_is_hidden_from_the_public_page(client, app):
    """They stay on the admin table, but the public page must not show them."""
    i = ids(app)
    as_admin(client)
    _highlight(client, i["hidden"], featured_title="Quiet Achiever")      # is_visible False
    _highlight(client, i["pending"], featured_title="Not Yet Verified")   # unapproved

    body = client.get("/admin/prominent").get_data(as_text=True)
    assert "Quiet Achiever" in body and "Unlisted" in body
    assert "Not Yet Verified" in body and "Unverified" in body

    client.post("/auth/logout")
    body = client.get("/alumni/prominent").get_data(as_text=True)
    assert "Hidden Member" not in body
    assert "Pending Member" not in body


def test_suspending_a_highlighted_member_hides_them(client, app):
    from app.extensions import db
    from app.models import User
    i = ids(app)
    as_admin(client)
    _highlight(client, i["employer"], featured_title="Industry Leader")
    client.post("/auth/logout")
    assert "Industry Leader" in client.get("/alumni/prominent").get_data(as_text=True)

    with app.app_context():
        db.session.get(User, i["employer"]).is_blocked = True
        db.session.commit()
    assert "Industry Leader" not in client.get("/alumni/prominent").get_data(as_text=True)


def test_a_member_cannot_highlight_anyone(client, app):
    i = ids(app)
    login(client, "seeker@test.edu")
    assert client.get("/admin/prominent").status_code == 403
    assert client.get(f"/admin/members/{i['seeker']}/highlight").status_code == 403
    assert _highlight(client, i["seeker"]).status_code == 403
    assert client.post(f"/admin/members/{i['seeker']}/unhighlight").status_code == 403
    from app.models import User
    with app.app_context():
        assert User.query.filter_by(email="seeker@test.edu").first().profile.is_featured is False


def test_a_member_cannot_highlight_themselves_through_the_profile_form(client, app):
    from app.models import User
    login(client, "seeker@test.edu")
    client.post("/alumni/me/edit", follow_redirects=True, data={
        "full_name": "Seeker Member", "programme": "M.Sc Computer Science",
        "batch_year": "2019", "experience_years": "1", "is_visible": "y",
        "is_featured": "y", "featured_title": "Self Appointed",
        "featured_note": "I am prominent.",
    })
    with app.app_context():
        profile = User.query.filter_by(email="seeker@test.edu").first().profile
        assert profile.is_featured is False
        assert profile.featured_title is None


def test_admin_suggestion_list_and_nav(client, app):
    as_admin(client)
    body = client.get("/admin/prominent").get_data(as_text=True)
    assert "Members you might put forward" in body
    assert "Employer Member" in body  # a listed, verified member
    assert "Pending Member" not in body.split("Members you might put forward")[1]
    assert "Prominent" in client.get("/admin/").get_data(as_text=True)


def test_highlighting_someone_without_a_profile_is_handled(client, app):
    """No profile means nothing to highlight — a message, not a crash."""
    from app.extensions import db
    from app.models import Role, User
    with app.app_context():
        bare = User(email="bare@test.edu", full_name="Bare Account",
                    role=Role.MEMBER, is_approved=True)
        bare.set_password("Testing@123")
        db.session.add(bare)
        db.session.commit()
        bare_id = bare.id

    as_admin(client)
    response = client.get(f"/admin/members/{bare_id}/highlight", follow_redirects=True)
    assert response.status_code == 200
    assert "has not filled in a profile yet" in response.get_data(as_text=True)
