"""A coordinator for each year of admission."""
from tests.conftest import as_admin, ids, login


def _assign(client, batch, name="Batch Rep", **overrides):
    data = {
        "department": "", "batch_year": str(batch), "academic_year": "",
        "name": name, "role": "Alumni Coordinator",
        "designation": f"{batch} batch", "email": f"rep{batch}@test.edu",
        "phone": "9000000000", "is_active": "y", "sort_order": "1",
    }
    data.update(overrides)
    return client.post("/admin/coordinators/new", data=data, follow_redirects=True)


def test_register_lists_every_year_of_admission(client, app):
    from datetime import datetime, timezone
    this_year = datetime.now(timezone.utc).year
    as_admin(client)
    body = client.get("/admin/batch-coordinators").get_data(as_text=True)
    assert "Batch coordinators" in body
    for year in (1995, 2000, 2019, this_year + 1):
        assert str(year) in body, year
    assert "Not assigned" in body
    assert f"{this_year + 1 - 1995 + 1}" in body  # the year count in the stat strip


def test_assigning_a_batch_coordinator(client, app):
    from app.models import Coordinator
    i = ids(app)
    as_admin(client)
    response = _assign(client, 1995, name="Nineties Rep",
                       department=str(i["dept_cs"]))
    assert "Coordinator saved" in response.get_data(as_text=True)

    with app.app_context():
        row = Coordinator.query.filter_by(name="Nineties Rep").first()
        assert row.batch_year == 1995
        assert row.is_batch_coordinator is True
        # the academic year follows from the batch
        assert row.academic_year == "1995-96"

    body = client.get("/admin/batch-coordinators").get_data(as_text=True)
    assert "Nineties Rep" in body


def _listed_years(html):
    """The years of admission the register's table actually lists."""
    import re
    table = html.split("<tbody>")[1].split("</tbody>")[0]
    return {int(y) for y in re.findall(r'<span class="strong">(\d{4})</span>', table)}


def test_filters_on_the_register(client, app):
    i = ids(app)
    as_admin(client)
    _assign(client, 2019, name="Covered Rep", department=str(i["dept_cs"]))

    missing = client.get("/admin/batch-coordinators?show=missing").get_data(as_text=True)
    assert "Covered Rep" not in missing
    assert 2019 not in _listed_years(missing)
    assert 2018 in _listed_years(missing)

    filled = client.get("/admin/batch-coordinators?show=filled").get_data(as_text=True)
    assert "Covered Rep" in filled
    assert _listed_years(filled) == {2019}

    with_members = client.get("/admin/batch-coordinators?show=with-members").get_data(as_text=True)
    listed = _listed_years(with_members)
    assert 2019 in listed and 2012 in listed  # batches that have members
    assert 1995 not in listed                 # nobody admitted in 1995 in the fixture

    # the intake label reads 2019-20, not 2019-2020
    assert "2019-20 intake" in filled


def test_batch_coordinator_appears_on_the_public_batch_page(client, app):
    i = ids(app)
    as_admin(client)
    _assign(client, 2019, name="Batch Of Nineteen", department=str(i["dept_cs"]),
            email="seeker@test.edu")
    client.post("/auth/logout")

    body = client.get("/alumni/batch/2019").get_data(as_text=True)
    assert "Batch coordinator" in body
    assert "Batch Of Nineteen" in body
    # a matching email links the record to that member's profile
    assert f"/alumni/{i['seeker']}" in body

    # another batch does not show them
    assert "Batch Of Nineteen" not in client.get("/alumni/batch/2012").get_data(as_text=True)


def test_batch_records_stay_out_of_the_department_listing(client, app):
    i = ids(app)
    as_admin(client)
    _assign(client, 2016, name="Batch Only Rep", department=str(i["dept_cs"]))
    client.post("/admin/coordinators/new", follow_redirects=True, data={
        "department": str(i["dept_cs"]), "batch_year": "", "academic_year": "2026-27",
        "name": "Department Rep", "role": "Staff Coordinator", "is_active": "y",
    })

    body = client.get("/admin/coordinators").get_data(as_text=True)
    assert "Department Rep" in body
    assert "Batch Only Rep" not in body, "batch records belong to their own register"

    client.post("/auth/logout")
    body = client.get("/coordinators").get_data(as_text=True)
    assert "Department Rep" in body
    assert "Batch Only Rep" not in body


def test_a_coordinator_needs_a_batch_or_an_academic_year(client, app):
    i = ids(app)
    as_admin(client)
    response = client.post("/admin/coordinators/new", data={
        "department": str(i["dept_cs"]), "batch_year": "", "academic_year": "",
        "name": "No Scope", "role": "Alumni Coordinator",
    })
    assert "pick the batch this coordinator looks after" in response.get_data(as_text=True)


def test_editing_keeps_the_batch(client, app):
    from app.models import Coordinator
    i = ids(app)
    as_admin(client)
    _assign(client, 2021, name="Editable Rep", department=str(i["dept_cs"]))
    with app.app_context():
        row_id = Coordinator.query.filter_by(name="Editable Rep").first().id

    body = client.get(f"/admin/coordinators/{row_id}/edit").get_data(as_text=True)
    assert '<option selected value="2021">' in body, "the batch must come back selected"

    client.post(f"/admin/coordinators/{row_id}/edit", follow_redirects=True, data={
        "department": str(i["dept_cs"]), "batch_year": "2021", "academic_year": "2021-22",
        "name": "Edited Rep", "role": "Student Coordinator", "is_active": "y",
        "sort_order": "2",
    })
    from app.extensions import db
    with app.app_context():
        row = db.session.get(Coordinator, row_id)
        assert row.name == "Edited Rep"
        assert row.batch_year == 2021
        assert row.role == "Student Coordinator"


def test_members_cannot_touch_the_register(client, app):
    login(client, "seeker@test.edu")
    assert client.get("/admin/batch-coordinators").status_code == 403
    assert client.post("/admin/coordinators/new", data={
        "batch_year": "1995", "name": "Sneaky", "role": "Alumni Coordinator",
    }).status_code == 403


def test_the_range_follows_the_batch_year_setting(client, app):
    as_admin(client)
    client.post("/admin/departments", data={"first_batch_year": "2015", "future_years": "0"})
    body = client.get("/admin/batch-coordinators").get_data(as_text=True)
    rows = body.split("<tbody>")[1]
    assert "2015" in rows
    assert "1995" not in rows, "years outside the configured range are not listed"
