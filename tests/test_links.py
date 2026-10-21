"""The outward links an administrator configures."""
from tests.conftest import as_admin, login


def test_links_page_and_saving(client, app):
    from app.models import Setting
    as_admin(client)
    assert "Outward links" in client.get("/admin/links").get_data(as_text=True)

    response = client.post("/admin/links", follow_redirects=True, data={
        "link_website": "https://www.sscollege.ac.in",
        "link_linkedin": "https://www.linkedin.com/company/ssc-cs",
        "link_instagram": "https://www.instagram.com/ssc_cs",
        "link_youtube": "https://www.youtube.com/@ssccs",
        "link_facebook": "",
    })
    assert "Links saved" in response.get_data(as_text=True)
    with app.app_context():
        assert Setting.get("link_linkedin") == "https://www.linkedin.com/company/ssc-cs"
        assert Setting.get("link_facebook") == ""


def test_icons_appear_in_the_header_and_footer(client, app):
    as_admin(client)
    client.post("/admin/links", data={
        "link_website": "https://www.sscollege.ac.in",
        "link_youtube": "https://www.youtube.com/@ssccs",
    })
    client.post("/auth/logout")
    body = client.get("/").get_data(as_text=True)
    assert body.count("https://www.youtube.com/@ssccs") == 2, "top bar and footer"
    assert 'aria-label="YouTube"' in body
    assert 'rel="noopener noreferrer"' in body
    # an unset network shows no icon
    assert 'aria-label="Facebook"' not in body


def test_a_hostile_link_is_refused(client, app):
    from app.models import Setting
    as_admin(client)
    response = client.post("/admin/links", data={"link_instagram": "javascript:alert(1)"})
    assert "http:// or https://" in response.get_data(as_text=True)
    with app.app_context():
        assert not Setting.get("link_instagram")


def test_a_stored_hostile_link_is_filtered_on_output(client, app):
    """Even if one reached the database, it must not render as a link."""
    from app.extensions import db
    from app.models import Setting
    with app.app_context():
        Setting.put("link_facebook", "javascript:alert(1)")
        db.session.commit()
    body = client.get("/").get_data(as_text=True)
    assert "javascript:alert" not in body
    assert 'aria-label="Facebook"' not in body


def test_members_cannot_change_the_links(client, app):
    login(client, "seeker@test.edu")
    assert client.get("/admin/links").status_code == 403
    assert client.post("/admin/links", data={"link_website": "https://evil.example"}).status_code == 403
