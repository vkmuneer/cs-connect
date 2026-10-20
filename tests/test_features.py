"""Batch browsing, placements, coordinators and college-wide mode."""
from tests.conftest import as_admin, ids, login


# --------------------------------------------------------------------------
# Batches and the admin-controlled year range
# --------------------------------------------------------------------------
def test_batch_overview_groups_by_year_and_programme(client, app):
    body = client.get("/alumni/batches").get_data(as_text=True)
    assert "2019" in body and "2012" in body
    assert "M.Sc Computer Science" in body


def test_batch_page_filters_by_programme(client, app):
    body = client.get("/alumni/batch/2019?programme=M.Sc+Computer+Science").get_data(as_text=True)
    assert "Seeker Member" in body
    body = client.get("/alumni/batch/2019?programme=B.Sc+Computer+Science").get_data(as_text=True)
    assert "Seeker Member" not in body


def test_admin_batch_register(client, app):
    as_admin(client)
    body = client.get("/admin/batches").get_data(as_text=True)
    assert "Year of admission" in body
    assert "2021" in body  # the pending member's batch appears for the admin
    assert "Batch size" in body


def test_admin_member_filters(client, app):
    i = ids(app)
    as_admin(client)
    body = client.get("/admin/members?batch=2019").get_data(as_text=True)
    assert "Seeker Member" in body and "Employer Member" not in body

    body = client.get("/admin/members?programme=M.Sc+Computer+Science").get_data(as_text=True)
    assert "Seeker Member" in body and "Employer Member" not in body

    body = client.get("/admin/members?scope=pending").get_data(as_text=True)
    assert "Pending Member" in body and "Seeker Member" not in body

    for sort in ("batch", "name", "recent"):
        assert client.get(f"/admin/members?sort={sort}").status_code == 200


def test_year_range_is_administrator_controlled(client, app):
    from datetime import datetime, timezone
    from app.utils import batch_year_bounds
    this_year = datetime.now(timezone.utc).year

    with app.app_context():
        assert batch_year_bounds() == (1995, this_year + 1)

    as_admin(client)
    response = client.post("/admin/departments", follow_redirects=True, data={
        "first_batch_year": "2005", "future_years": "2",
    })
    assert f"2005 to {this_year + 2}" in response.get_data(as_text=True)
    with app.app_context():
        assert batch_year_bounds() == (2005, this_year + 2)

    # a visitor's registration form follows at once
    visitor = app.test_client()
    body = visitor.get("/auth/register").get_data(as_text=True)
    assert f'value="{this_year + 2}"' in body
    assert 'value="1995"' not in body


def test_out_of_range_batch_year_is_refused(client, app):
    from app.models import User
    as_admin(client)
    client.post("/admin/departments", data={"first_batch_year": "2010", "future_years": "0"})
    client.post("/auth/logout")

    response = client.post("/auth/register", data={
        "full_name": "Too Old", "email": "tooold@test.edu",
        "password": "Testing@123", "confirm": "Testing@123",
        "programme": "B.Sc Computer Science", "batch_year": "1995", "accept_terms": "y",
    })
    assert "Not a valid choice" in response.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(email="tooold@test.edu").first() is None


# --------------------------------------------------------------------------
# Placements
# --------------------------------------------------------------------------
def test_placements_page_counts_only_hires(client, app):
    from app.extensions import db
    from app.models import Application, ApplicationStatus
    body = client.get("/placements").get_data(as_text=True)
    assert "No placements recorded yet" in body  # fixture application is shortlisted

    with app.app_context():
        application = Application.query.first()
        application.status = ApplicationStatus.HIRED
        db.session.commit()

    body = client.get("/placements").get_data(as_text=True)
    assert "Seeker Member" in body
    assert "Live Role" in body
    assert "No placements recorded yet" not in body


def test_placement_badge_on_the_profile_and_home_page(client, app):
    from app.extensions import db
    from app.models import Application, ApplicationStatus
    i = ids(app)
    with app.app_context():
        Application.query.first().status = ApplicationStatus.HIRED
        db.session.commit()
    assert "Hired through" in client.get(f"/alumni/{i['seeker']}").get_data(as_text=True)
    assert "Hired through" in client.get("/").get_data(as_text=True)


def test_admin_placements_view(client, app):
    as_admin(client)
    body = client.get("/admin/placements").get_data(as_text=True)
    assert "Hired through the portal" in body
    assert "Shortlisted" in body  # the in-progress section lists the fixture application


# --------------------------------------------------------------------------
# Coordinators
# --------------------------------------------------------------------------
def test_coordinator_lifecycle(client, app):
    from app.models import Coordinator
    i = ids(app)
    as_admin(client)
    year = None
    with app.app_context():
        year = Coordinator.current_year_label()

    response = client.post("/admin/coordinators/new", follow_redirects=True, data={
        "department": str(i["dept_cs"]), "academic_year": year,
        "name": "Dr. Coordinator", "role": "Alumni Coordinator",
        "designation": "Assistant Professor", "email": "seeker@test.edu",
        "is_active": "y", "sort_order": "1",
    })
    assert "Coordinator saved" in response.get_data(as_text=True)

    with app.app_context():
        row = Coordinator.query.filter_by(name="Dr. Coordinator").first()
        assert row.academic_year == year
        assert row.user_id == i["seeker"], "a matching email should link the account"
        row_id = row.id

    body = client.get("/coordinators").get_data(as_text=True)
    assert "Dr. Coordinator" in body and "Alumni Coordinator" in body

    response = client.post(f"/admin/coordinators/{row_id}/delete", follow_redirects=True)
    assert "removed" in response.get_data(as_text=True)
    with app.app_context():
        assert Coordinator.query.filter_by(name="Dr. Coordinator").count() == 0


def test_coordinator_year_format_is_validated(client, app):
    i = ids(app)
    as_admin(client)
    response = client.post("/admin/coordinators/new", data={
        "department": str(i["dept_cs"]), "academic_year": "2026",
        "name": "Bad Year", "role": "Alumni Coordinator",
    })
    assert "Use the form 2025-26" in response.get_data(as_text=True)


# --------------------------------------------------------------------------
# College-wide mode
# --------------------------------------------------------------------------
def test_college_wide_mode_round_trip(client, app):
    from app.models import Department, Setting, User
    i = ids(app)
    as_admin(client)

    # off by default
    assert client.get("/departments").status_code == 404

    client.post(f"/admin/departments/{i['dept_physics']}/toggle", follow_redirects=True)
    assert client.get("/departments").status_code == 404, "still hidden while the mode is off"

    response = client.post("/admin/departments", follow_redirects=True, data={"enabled": "y"})
    assert "College-wide mode is on" in response.get_data(as_text=True)
    assert client.get("/departments").status_code == 200

    client.post("/auth/logout")
    body = client.get("/auth/register").get_data(as_text=True)
    assert "Physics" in body

    response = client.post("/auth/register", follow_redirects=True, data={
        "full_name": "Physics Graduate", "email": "phy@test.edu",
        "password": "Testing@123", "confirm": "Testing@123",
        "department": str(i["dept_physics"]), "programme": "M.Sc Physics",
        "batch_year": "2015", "accept_terms": "y",
    })
    assert "awaiting verification" in response.get_data(as_text=True)
    with app.app_context():
        user = User.query.filter_by(email="phy@test.edu").first()
        assert user.profile.department.slug == "physics"
        assert user.profile.programme == "M.Sc Physics"

    # switching back off hides the extension but keeps the records.
    # Registration signed us in as the new member, so sign out first.
    client.post("/auth/logout")
    as_admin(client)
    response = client.post("/admin/departments", follow_redirects=True, data={})
    assert "Computer Science only" in response.get_data(as_text=True)
    assert client.get("/departments").status_code == 404
    with app.app_context():
        assert Setting.is_on("multi_department_enabled") is False
        assert User.query.filter_by(email="phy@test.edu").first().profile.department.slug == "physics"


def test_a_disabled_department_cannot_be_chosen(client, app):
    """Physics is inactive, so a submitted Physics id falls back to the host."""
    from app.models import User
    i = ids(app)
    client.post("/auth/register", follow_redirects=True, data={
        "full_name": "Sneaky Physics", "email": "sneaky@test.edu",
        "password": "Testing@123", "confirm": "Testing@123",
        "department": str(i["dept_physics"]), "programme": "B.Sc Computer Science",
        "batch_year": "2015", "accept_terms": "y",
    })
    with app.app_context():
        user = User.query.filter_by(email="sneaky@test.edu").first()
        assert user.profile.department.slug == "computer-science"


def test_host_department_stays_active(client, app):
    i = ids(app)
    as_admin(client)
    response = client.post(f"/admin/departments/{i['dept_cs']}/toggle", follow_redirects=True)
    assert "stays active" in response.get_data(as_text=True)
    from app.extensions import db
    from app.models import Department
    with app.app_context():
        assert db.session.get(Department, i["dept_cs"]).is_active is True


def test_department_with_members_cannot_be_deleted(client, app):
    i = ids(app)
    as_admin(client)
    response = client.post(f"/admin/departments/{i['dept_cs']}/delete", follow_redirects=True)
    assert "cannot be deleted" in response.get_data(as_text=True)
