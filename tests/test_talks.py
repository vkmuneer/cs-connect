"""Willingness to speak, and the scheduling of sessions."""
from datetime import timedelta

from tests.conftest import as_admin, ids, login


def _declare_willing(client, topics="Life after graduation\nGetting into data science"):
    return client.post("/alumni/me/edit", follow_redirects=True, data={
        "full_name": "Employer Member", "programme": "B.Sc Computer Science",
        "batch_year": "2012", "experience_years": "8", "is_visible": "y",
        "offers_expert_talk": "y", "talk_topics": topics, "talk_mode": "Either",
    })


def _schedule(client, speaker_id, **overrides):
    from app.utils import portal_today
    data = {
        "speaker": str(speaker_id), "title": "From our classrooms to a product team",
        "topic": "What the first two years of work actually ask of you.",
        "mode": "On campus", "venue": "Seminar hall",
        "audience": "Final-year B.Sc and M.Sc students",
        "scheduled_date": (portal_today() + timedelta(days=14)).isoformat(),
        "scheduled_time": "14:30", "duration_minutes": "60",
        "status": "confirmed", "notes": "Hosted by the alumni cell",
    }
    data.update(overrides)
    return client.post("/admin/talks/new", data=data, follow_redirects=True)


def test_public_page_before_anything_is_arranged(client, app):
    response = client.get("/talks")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "No sessions scheduled at the moment" in body
    assert "Nobody has offered yet" in body


def test_member_declares_willingness(client, app):
    from app.models import User
    login(client, "employer@test.edu")
    response = _declare_willing(client)
    assert "profile has been updated" in response.get_data(as_text=True)

    with app.app_context():
        profile = User.query.filter_by(email="employer@test.edu").first().profile
        assert profile.offers_expert_talk is True
        assert "data science" in profile.talk_topics
        assert profile.talk_mode == "Either"

    client.post("/auth/logout")
    body = client.get("/talks").get_data(as_text=True)
    assert "Employer Member" in body
    assert "Getting into data science" in body

    # and it shows on their profile and in the directory filter
    i = ids(app)
    assert "Available for talks" in client.get(f"/alumni/{i['employer']}").get_data(as_text=True)
    body = client.get("/alumni/?role=speakers").get_data(as_text=True)
    assert "Employer Member" in body and "Seeker Member" not in body


def test_admin_schedules_a_session_and_the_speaker_is_told(client, app):
    from app.models import Message, TalkSession
    i = ids(app)
    login(client, "employer@test.edu")
    _declare_willing(client)
    client.post("/auth/logout")

    as_admin(client)
    response = _schedule(client, i["employer"])
    assert "speaker has been notified" in response.get_data(as_text=True)

    with app.app_context():
        talk = TalkSession.query.first()
        assert talk.speaker_id == i["employer"]
        assert talk.status == "confirmed"
        assert talk.scheduled_for.hour == 14 and talk.scheduled_for.minute == 30
        assert talk.is_upcoming is True
        note = Message.query.filter_by(recipient_id=i["employer"]).order_by(
            Message.id.desc()).first()
        assert "Session scheduled" in note.subject
        assert "Seminar hall" in note.body

    client.post("/auth/logout")
    body = client.get("/talks").get_data(as_text=True)
    assert "From our classrooms to a product team" in body
    assert "Seminar hall" in body


def test_only_willing_members_are_offered_as_speakers(client, app):
    as_admin(client)
    body = client.get("/admin/talks/new").get_data(as_text=True)
    assert "Employer Member" not in body, "nobody has offered yet"

    client.post("/auth/logout")
    login(client, "employer@test.edu")
    _declare_willing(client)
    client.post("/auth/logout")

    as_admin(client)
    body = client.get("/admin/talks/new").get_data(as_text=True)
    assert "Employer Member" in body


def test_scheduling_validation(client, app):
    i = ids(app)
    as_admin(client)
    response = _schedule(client, i["employer"], scheduled_date="", scheduled_time="14:30")
    assert "Give a date as well as a time" in response.get_data(as_text=True)

    response = _schedule(client, i["employer"], scheduled_date="", scheduled_time="",
                         status="confirmed")
    assert "confirmed session needs a date" in response.get_data(as_text=True)

    # both problems at once, not just the first
    response = _schedule(client, i["employer"], scheduled_date="", status="confirmed")
    body = response.get_data(as_text=True)
    assert "Give a date as well as a time" in body
    assert "confirmed session needs a date" in body

    response = _schedule(client, i["employer"], scheduled_time="25:99")
    assert "24-hour time" in response.get_data(as_text=True)


def test_a_proposed_session_without_a_date_is_allowed(client, app):
    from app.models import TalkSession
    i = ids(app)
    as_admin(client)
    response = _schedule(client, i["employer"], scheduled_date="", scheduled_time="",
                         status="proposed")
    assert "Session saved" in response.get_data(as_text=True)
    with app.app_context():
        talk = TalkSession.query.first()
        assert talk.scheduled_for is None
        assert talk.when_label == "Date to be fixed"
        assert talk.is_upcoming is True


def test_past_sessions_move_out_of_the_upcoming_list(client, app):
    from datetime import datetime, timezone
    from app.extensions import db
    from app.models import TalkSession
    i = ids(app)
    as_admin(client)
    _schedule(client, i["employer"])
    with app.app_context():
        talk = TalkSession.query.first()
        talk.scheduled_for = datetime(2020, 1, 1, 10, 0, tzinfo=timezone.utc)
        db.session.commit()
        assert talk.is_past is True
        assert talk.is_upcoming is False
        assert TalkSession.upcoming() == []

    client.post("/auth/logout")
    body = client.get("/talks").get_data(as_text=True)
    assert "Already held" in body
    assert "No sessions scheduled at the moment" in body


def test_editing_and_deleting_a_session(client, app):
    from app.extensions import db
    from app.models import TalkSession
    i = ids(app)
    as_admin(client)
    _schedule(client, i["employer"])
    with app.app_context():
        talk_id = TalkSession.query.first().id

    response = client.post(f"/admin/talks/{talk_id}/edit", follow_redirects=True, data={
        "speaker": str(i["employer"]), "title": "Renamed session", "mode": "Online",
        "venue": "https://meet.example.com/ssc", "status": "cancelled",
        "scheduled_date": "", "scheduled_time": "", "duration_minutes": "45",
    })
    assert "Session saved" in response.get_data(as_text=True)
    with app.app_context():
        talk = db.session.get(TalkSession, talk_id)
        assert talk.title == "Renamed session" and talk.status == "cancelled"

    response = client.post(f"/admin/talks/{talk_id}/delete", follow_redirects=True)
    assert "removed" in response.get_data(as_text=True)
    with app.app_context():
        assert TalkSession.query.count() == 0


def test_members_cannot_schedule(client, app):
    i = ids(app)
    login(client, "seeker@test.edu")
    assert client.get("/admin/talks").status_code == 403
    assert client.get("/admin/talks/new").status_code == 403
    assert _schedule(client, i["employer"]).status_code == 403


def test_topics_are_escaped(client, app):
    login(client, "employer@test.edu")
    _declare_willing(client, topics='<script>alert("x")</script>')
    client.post("/auth/logout")
    body = client.get("/talks").get_data(as_text=True)
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_home_page_shows_the_next_session(client, app):
    i = ids(app)
    as_admin(client)
    _schedule(client, i["employer"], title="Campus session on careers")
    client.post("/auth/logout")
    body = client.get("/").get_data(as_text=True)
    assert "Talks coming up" in body
    assert "Campus session on careers" in body
