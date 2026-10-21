"""The home page and dashboard copy an administrator can edit."""
from tests.conftest import as_admin, login


def test_defaults_render_before_anything_is_edited(client, app):
    body = client.get("/").get_data(as_text=True)
    assert "Where our graduates stay in touch" in body
    assert "Latest opportunities" in body
    assert "How the portal works" in body


def test_editor_lists_every_entry(client, app):
    from app.content import TEXTS
    as_admin(client)
    body = client.get("/admin/content").get_data(as_text=True)
    assert "Page text" in body
    for key, _group, _label, _default, _kind in TEXTS:
        assert f'name="{key}"' in body, key


def test_editing_the_home_page_headline(client, app):
    from app.models import Setting
    as_admin(client)
    response = client.post("/admin/content", follow_redirects=True, data={
        "home.hero_title": "The alumni of CS, Areekode",
        "home.hero_body": "Twenty-eight batches, one register.",
        "home.jobs_title": "Openings right now",
    })
    assert "updated" in response.get_data(as_text=True)
    with app.app_context():
        assert Setting.get("home.hero_title") == "The alumni of CS, Areekode"

    client.post("/auth/logout")
    body = client.get("/").get_data(as_text=True)
    assert "The alumni of CS, Areekode" in body
    assert "Twenty-eight batches, one register." in body
    assert "Openings right now" in body
    assert "Where our graduates stay in touch" not in body


def test_editing_the_dashboard(client, app):
    as_admin(client)
    client.post("/admin/content", data={
        "dashboard.title": "My alumni page",
        "dashboard.postings_title": "Openings I have listed",
    })
    client.post("/auth/logout")
    login(client, "employer@test.edu")
    body = client.get("/alumni/me").get_data(as_text=True)
    assert "My alumni page" in body
    assert "Openings I have listed" in body
    assert "My dashboard" not in body


def test_clearing_a_field_restores_the_default(client, app):
    from app.models import Setting
    as_admin(client)
    client.post("/admin/content", data={"home.hero_title": "Temporary wording"})
    assert "Temporary wording" in client.get("/").get_data(as_text=True)

    response = client.post("/admin/content", follow_redirects=True,
                           data={"home.hero_title": ""})
    assert "restored to the default" in response.get_data(as_text=True)
    with app.app_context():
        assert Setting.get("home.hero_title") is None
    assert "Where our graduates stay in touch" in client.get("/").get_data(as_text=True)


def test_submitting_the_default_wording_stores_no_override(client, app):
    from app.content import TEXT_DEFAULTS
    from app.models import Setting
    as_admin(client)
    client.post("/admin/content", data={
        "home.hero_title": TEXT_DEFAULTS["home.hero_title"],
    })
    with app.app_context():
        assert Setting.get("home.hero_title") is None, "no point storing the default"


def test_restore_all_defaults(client, app):
    from app.models import Setting
    as_admin(client)
    client.post("/admin/content", data={
        "home.hero_title": "One", "home.jobs_title": "Two", "dashboard.title": "Three",
    })
    response = client.post("/admin/content/reset", follow_redirects=True)
    assert "restored to the default wording" in response.get_data(as_text=True)
    with app.app_context():
        for key in ("home.hero_title", "home.jobs_title", "dashboard.title"):
            assert Setting.get(key) is None
    assert "Where our graduates stay in touch" in client.get("/").get_data(as_text=True)


def test_edited_text_is_escaped(client, app):
    as_admin(client)
    client.post("/admin/content", data={
        "home.hero_title": '<script>alert("x")</script>',
        "home.hero_body": "<img src=x onerror=alert(1)>",
    })
    client.post("/auth/logout")
    body = client.get("/").get_data(as_text=True)
    assert "<script>alert" not in body
    assert "<img src=x onerror" not in body
    assert "&lt;script&gt;" in body


def test_a_long_paragraph_survives_the_round_trip(client, app):
    """Setting.value holds page copy, not just short flags."""
    from app.models import Setting
    long_text = ("The department has graduated twenty-eight batches since 1995, and "
                 "this register exists so that none of them lose each other. ") * 4
    as_admin(client)
    client.post("/admin/content", data={"home.hero_body": long_text})
    with app.app_context():
        assert Setting.get("home.hero_body") == long_text.strip()
    assert long_text.strip()[:60] in client.get("/").get_data(as_text=True)


def test_members_cannot_edit_the_text(client, app):
    from app.models import Setting
    login(client, "seeker@test.edu")
    assert client.get("/admin/content").status_code == 403
    assert client.post("/admin/content", data={"home.hero_title": "Hacked"}).status_code == 403
    assert client.post("/admin/content/reset").status_code == 403
    with app.app_context():
        assert Setting.get("home.hero_title") is None
