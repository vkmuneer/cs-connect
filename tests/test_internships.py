"""Alumni offering internships to current students."""
from datetime import timedelta

from tests.conftest import as_admin, ids, login


def _offer(client, **overrides):
    from app.utils import portal_today
    data = {
        "title": "Backend development intern", "organisation": "Acme Ltd",
        "location": "Kochi", "mode": "Hybrid",
        "description": "Work alongside the platform team on our billing APIs. " * 2,
        "learning_outcomes": "Git in a real team\nWriting tests that matter",
        "eligibility": "Final-year B.Sc or any M.Sc student",
        "skills": "Python, Git", "duration_weeks": "8", "seats": "2",
        "is_paid": "y", "stipend": "₹10,000 per month",
        "apply_by": (portal_today() + timedelta(days=20)).isoformat(),
    }
    data.update(overrides)
    return client.post("/internships/offer", data=data, follow_redirects=True)


def test_public_listing_is_empty_at_first(client, app):
    response = client.get("/internships/")
    assert response.status_code == 200
    assert "No internships listed yet" in response.get_data(as_text=True)


def test_member_offer_is_moderated_then_listed(client, app):
    from app.models import Internship, InternshipStatus
    login(client, "employer@test.edu")
    response = _offer(client)
    assert "will be listed for students once it is approved" in response.get_data(as_text=True)

    with app.app_context():
        internship = Internship.query.first()
        assert internship.status == InternshipStatus.PENDING
        assert internship.duration_label == "2 months"
        assert internship.seats_left == 2
        assert {s.name for s in internship.skills} == {"Python", "Git"}
        internship_id = internship.id

    client.post("/auth/logout")
    assert "Backend development intern" not in client.get("/internships/").get_data(as_text=True)

    as_admin(client)
    response = client.post(f"/admin/internships/{internship_id}/approve", follow_redirects=True)
    assert "now listed for students" in response.get_data(as_text=True)

    client.post("/auth/logout")
    assert "Backend development intern" in client.get("/internships/").get_data(as_text=True)


def test_admin_offer_is_listed_at_once(client, app):
    from app.models import Internship, InternshipStatus
    as_admin(client)
    _offer(client, title="Department internship")
    with app.app_context():
        assert Internship.query.filter_by(
            title="Department internship").first().status == InternshipStatus.APPROVED


def test_rejection_tells_the_alumnus_why(client, app):
    from app.extensions import db
    from app.models import Internship, InternshipStatus, Message
    i = ids(app)
    login(client, "employer@test.edu")
    _offer(client)
    with app.app_context():
        internship_id = Internship.query.first().id
    client.post("/auth/logout")

    as_admin(client)
    client.post(f"/admin/internships/{internship_id}/reject", follow_redirects=True,
                data={"rejection_note": "Please say what the student will work on"})
    with app.app_context():
        internship = db.session.get(Internship, internship_id)
        assert internship.status == InternshipStatus.REJECTED
        note = Message.query.filter_by(recipient_id=i["employer"]).order_by(
            Message.id.desc()).first()
        assert "Please say what the student will work on" in note.body


def test_form_validation(client, app):
    from app.utils import portal_today
    login(client, "employer@test.edu")
    response = _offer(client, apply_by="2001-01-01")
    assert "already passed" in response.get_data(as_text=True)

    response = _offer(client, starts_from=(portal_today() + timedelta(days=5)).isoformat(),
                      apply_by=(portal_today() + timedelta(days=20)).isoformat())
    assert "start date cannot be before the closing date" in response.get_data(as_text=True)

    response = _offer(client, stipend="")
    assert "untick" in response.get_data(as_text=True)

    response = _offer(client, description="too short")
    assert "Field must be between 30" in response.get_data(as_text=True)


def test_student_expresses_interest_and_is_accepted(client, app):
    from app.extensions import db
    from app.models import (
        InterestStatus, Internship, InternshipInterest, InternshipStatus, Message,
    )
    i = ids(app)
    login(client, "employer@test.edu")
    _offer(client, seats="1")
    with app.app_context():
        internship = Internship.query.first()
        internship.status = InternshipStatus.APPROVED
        db.session.commit()
        internship_id = internship.id
    client.post("/auth/logout")

    login(client, "seeker@test.edu")
    response = client.post(f"/internships/{internship_id}/interest", follow_redirects=True,
                           data={"note": "Final-year M.Sc, I have built two Flask apps."})
    assert "interest has been sent" in response.get_data(as_text=True)
    with app.app_context():
        interest = InternshipInterest.query.first()
        assert interest.status == InterestStatus.EXPRESSED
        assert interest.resume_filename == "seeker-cv.pdf", "the profile resume travels with it"
        assert Message.query.filter_by(recipient_id=i["employer"]).count() >= 1
        interest_id = interest.id

    # expressing interest twice is refused
    response = client.get(f"/internships/{internship_id}/interest", follow_redirects=True)
    assert "already expressed interest" in response.get_data(as_text=True)

    client.post("/auth/logout")
    login(client, "employer@test.edu")
    response = client.post(f"/internships/interest/{interest_id}/status", follow_redirects=True,
                           data={"status": "accepted", "offerer_note": "See you on the 1st"})
    assert "student has been notified" in response.get_data(as_text=True)
    with app.app_context():
        interest = db.session.get(InternshipInterest, interest_id)
        assert interest.status == InterestStatus.ACCEPTED
        assert db.session.get(Internship, internship_id).seats_left == 0


def test_places_cannot_be_over_allocated(client, app):
    from app.extensions import db
    from app.models import InterestStatus, Internship, InternshipInterest, InternshipStatus
    i = ids(app)
    login(client, "employer@test.edu")
    _offer(client, seats="1")
    with app.app_context():
        internship = Internship.query.first()
        internship.status = InternshipStatus.APPROVED
        db.session.add(InternshipInterest(internship_id=internship.id, student_id=i["seeker"],
                                          status=InterestStatus.ACCEPTED))
        db.session.add(InternshipInterest(internship_id=internship.id, student_id=i["hidden"],
                                          status=InterestStatus.EXPRESSED))
        db.session.commit()
        second = InternshipInterest.query.filter_by(student_id=i["hidden"]).first()
        second_id = second.id

    response = client.post(f"/internships/interest/{second_id}/status", follow_redirects=True,
                           data={"status": "accepted"})
    assert "every place on this internship is already taken" in response.get_data(as_text=True).lower()
    with app.app_context():
        assert db.session.get(InternshipInterest, second_id).status == InterestStatus.EXPRESSED


def test_you_cannot_express_interest_in_your_own_offer(client, app):
    from app.extensions import db
    from app.models import Internship, InternshipStatus
    login(client, "employer@test.edu")
    _offer(client)
    with app.app_context():
        internship = Internship.query.first()
        internship.status = InternshipStatus.APPROVED
        db.session.commit()
        internship_id = internship.id
    response = client.get(f"/internships/{internship_id}/interest", follow_redirects=True)
    assert "your own internship" in response.get_data(as_text=True)


def test_unverified_member_cannot_offer_or_apply(client, app):
    login(client, "pending@test.edu")
    response = client.get("/internships/offer", follow_redirects=True)
    assert "awaiting verification" in response.get_data(as_text=True)


def test_interest_list_is_owner_or_admin_only(client, app):
    from app.extensions import db
    from app.models import Internship, InternshipStatus
    login(client, "employer@test.edu")
    _offer(client)
    with app.app_context():
        internship = Internship.query.first()
        internship.status = InternshipStatus.APPROVED
        db.session.commit()
        internship_id = internship.id
    client.post("/auth/logout")

    login(client, "hidden@test.edu")
    assert client.get(f"/internships/{internship_id}/interested").status_code == 403
    assert client.get(f"/internships/{internship_id}/edit").status_code == 403
    assert client.post(f"/internships/{internship_id}/close").status_code == 403


def test_members_cannot_moderate(client, app):
    login(client, "seeker@test.edu")
    assert client.get("/admin/internships").status_code == 403


def test_pending_offer_is_not_publicly_readable(client, app):
    from app.models import Internship
    login(client, "employer@test.edu")
    _offer(client)
    with app.app_context():
        internship_id = Internship.query.first().id
    client.post("/auth/logout")
    assert client.get(f"/internships/{internship_id}").status_code == 404


def test_listing_filters(client, app):
    from app.extensions import db
    from app.models import Internship, InternshipStatus
    login(client, "employer@test.edu")
    _offer(client)
    _offer(client, title="Unpaid research intern", is_paid="", stipend="", mode="Remote")
    with app.app_context():
        for internship in Internship.query.all():
            internship.status = InternshipStatus.APPROVED
        db.session.commit()
    client.post("/auth/logout")

    body = client.get("/internships/?paid=1").get_data(as_text=True)
    assert "Backend development intern" in body and "Unpaid research intern" not in body
    body = client.get("/internships/?mode=Remote").get_data(as_text=True)
    assert "Unpaid research intern" in body and "Backend development intern" not in body
    body = client.get("/internships/?q=research").get_data(as_text=True)
    assert "Unpaid research intern" in body


def test_my_internships_page(client, app):
    login(client, "employer@test.edu")
    _offer(client)
    body = client.get("/internships/mine").get_data(as_text=True)
    assert "Offered by me" in body and "Backend development intern" in body
