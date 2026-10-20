"""Every page a visitor can reach must render."""
import pytest

from tests.conftest import ids


PUBLIC_PATHS = [
    "/", "/about/college", "/about/department", "/faculty", "/faculty?scope=former",
    "/announcements", "/contact", "/alumni/", "/alumni/batches", "/jobs/",
    "/placements", "/coordinators", "/auth/login", "/auth/register",
]


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_page_renders(client, path):
    assert client.get(path).status_code == 200


def test_directory_filters_combine(client, app):
    for query in [
        "?q=seeker", "?programme=M.Sc+Computer+Science", "?batch_year=2019",
        "?graduation_year=2022", "?skill=Python", "?role=seekers", "?role=hiring",
        "?programme=M.Sc+Computer+Science&batch_year=2019&skill=Python",
    ]:
        assert client.get(f"/alumni/{query}").status_code == 200


def test_directory_hides_unlisted_and_unapproved(client, app):
    body = client.get("/alumni/").get_data(as_text=True)
    assert "Seeker Member" in body
    assert "Hidden Member" not in body     # is_visible = False
    assert "Pending Member" not in body    # not verified
    assert "Blocked Member" not in body    # suspended


def test_batch_pages(client, app):
    assert client.get("/alumni/batch/2019").status_code == 200
    body = client.get("/alumni/batch/2019").get_data(as_text=True)
    assert "Seeker Member" in body
    assert "Employer Member" not in body   # 2012 batch
    assert client.get("/alumni/batch/1900").status_code == 200  # empty, not an error


def test_job_board_shows_only_approved(client, app):
    body = client.get("/jobs/").get_data(as_text=True)
    assert "Live Role" in body
    assert "Pending Role" not in body


def test_pending_job_is_not_publicly_readable(client, app):
    assert client.get(f"/jobs/{ids(app)['job_pending']}").status_code == 404
    assert client.get(f"/jobs/{ids(app)['job_live']}").status_code == 200


def test_departments_page_hidden_until_enabled(client, app):
    assert client.get("/departments").status_code == 404


def test_unknown_page_is_a_404_page(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "Page not found" in response.get_data(as_text=True)


def test_unauthenticated_users_are_redirected(client):
    for path in ["/alumni/me", "/alumni/me/edit", "/jobs/post", "/messages/", "/admin/"]:
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/auth/login" in response.headers["Location"], path
