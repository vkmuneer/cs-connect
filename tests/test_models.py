"""Model and helper behaviour, without going through HTTP."""
from datetime import date, datetime, timedelta, timezone

import pytest


def test_password_hashing_is_salted(app):
    from app.models import User
    with app.app_context():
        a, b = User(email="a@t.edu", full_name="A"), User(email="b@t.edu", full_name="B")
        a.set_password("same-password")
        b.set_password("same-password")
        assert a.password_hash != b.password_hash, "hashes must be salted"
        assert a.check_password("same-password") and b.check_password("same-password")


def test_user_role_and_participation_flags(app):
    from app.models import Role, User
    with app.app_context():
        admin = User(email="x@t.edu", full_name="X", role=Role.ADMIN)
        member = User(email="y@t.edu", full_name="Y", role=Role.MEMBER, is_approved=False)
        assert admin.is_admin and admin.can_participate
        assert not member.can_participate
        member.is_approved = True
        assert member.can_participate
        member.is_blocked = True
        assert not member.can_participate and not member.is_active


def test_profile_display_helpers(app):
    from app.models import Profile, User
    with app.app_context():
        user = User.query.filter_by(email="seeker@test.edu").first()
        profile = user.profile
        assert profile.display_batch == "2019"
        profile.graduation_year = 2021
        assert profile.display_batch == "2019–2021"
        assert profile.initials == "SM"
        assert profile.department_name == "Computer Science"


def test_skill_deduplication(app):
    from app.extensions import db
    from app.models import Skill
    with app.app_context():
        first = Skill.get_or_create("Machine Learning")
        again = Skill.get_or_create("  machine   learning  ")
        db.session.commit()
        assert first.id == again.id, "whitespace and case must not create duplicates"
        assert Skill.get_or_create("") is None
        assert Skill.slugify("Deep Learning") == "deep-learning"


def test_parse_skills(app):
    from app.utils import parse_skills
    assert parse_skills("Python, SQL; React\nDjango") == ["Python", "SQL", "React", "Django"]
    assert parse_skills("Python, python, PYTHON") == ["Python"]
    assert parse_skills("") == []
    assert parse_skills(None) == []
    assert len(parse_skills(", ".join(f"skill{n}" for n in range(60)))) == 30, "capped"
    assert len(parse_skills("x" * 200)[0]) == 60, "each name is capped"


def test_job_experience_and_expiry(app):
    """Deadlines use the portal's timezone, the same clock the form validates with."""
    from app.models import Job
    from app.utils import portal_today
    with app.app_context():
        job = Job(title="T", company="C", description="d", posted_by_id=1)
        job.min_experience, job.max_experience = 0, None
        assert job.experience_label == "Fresher"
        job.min_experience = 3
        assert job.experience_label == "3+ yrs"
        job.max_experience = 6
        assert job.experience_label == "3–6 yrs"

        assert job.is_expired is False
        job.deadline = portal_today() - timedelta(days=1)
        assert job.is_expired is True
        job.deadline = portal_today()
        assert job.is_expired is False, "a deadline of today is still open"
        job.status = "approved"
        assert job.is_open is True
        job.deadline = portal_today() - timedelta(days=1)
        assert job.is_open is False, "an expired posting is not open"


def test_placement_statistics(app):
    from app.extensions import db
    from app.models import Application, ApplicationStatus
    with app.app_context():
        assert Application.placement_count() == 0
        application = Application.query.first()
        application.status = ApplicationStatus.HIRED
        db.session.commit()
        stats = Application.placement_stats()
        assert stats["total"] == 1 and stats["companies"] == 1 and stats["members"] == 1
        assert stats["this_year"] == 1


def test_message_unread_count(app):
    from app.extensions import db
    from app.models import Message, User
    with app.app_context():
        seeker = User.query.filter_by(email="seeker@test.edu").first()
        assert Message.unread_count(seeker.id) == 1
        Message.query.filter_by(recipient_id=seeker.id).first().is_read = True
        db.session.commit()
        assert Message.unread_count(seeker.id) == 0


def test_setting_round_trip(app):
    from app.extensions import db
    from app.models import Setting
    with app.app_context():
        Setting.put("a_flag", True)
        db.session.commit()
        assert Setting.is_on("a_flag") is True
        Setting.put("a_flag", False)
        db.session.commit()
        assert Setting.is_on("a_flag") is False
        assert Setting.is_on("never_set", default=True) is True
        assert Setting.get("never_set") is None


def test_department_helpers(app):
    from app.models import Department
    with app.app_context():
        cs = Department.primary()
        assert cs.slug == "computer-science"
        assert "M.Sc Computer Science" in cs.programme_list
        # every approved, unsuspended member of the department, listed or not:
        # admin, employer, seeker and hidden (pending and blocked do not count)
        assert cs.member_count == 4
        assert [d.slug for d in Department.active()] == ["computer-science"]
        assert Department.slugify("Communication Media and History") == \
            "communication-media-and-history"


def test_coordinator_academic_year_label(app):
    from app.models import Coordinator
    with app.app_context():
        label = Coordinator.current_year_label()
        assert len(label) == 7 and label[4] == "-"
        start = int(label[:4])
        today = datetime.now(timezone.utc).date()
        assert start == (today.year if today.month >= 6 else today.year - 1)


def test_timeago_filter(app):
    from app.utils import timeago
    now = datetime.now(timezone.utc)
    assert timeago(now) == "just now"
    assert timeago(now - timedelta(minutes=5)) == "5 minutes ago"
    assert timeago(now - timedelta(hours=3)) == "3 hours ago"
    assert timeago(now - timedelta(days=2)) == "2 days ago"
    assert timeago(now - timedelta(days=400)) == "1 year ago"
    assert timeago(None) == ""
    naive = datetime.now()  # a naive timestamp must not raise
    assert timeago(naive) in ("just now", "1 minute ago")


def test_batch_year_bounds_respect_the_setting(app):
    from app.extensions import db
    from app.models import Setting
    from app.utils import batch_year_bounds
    this_year = datetime.now(timezone.utc).year
    with app.app_context():
        assert batch_year_bounds() == (1995, this_year + 1)
        Setting.put("first_batch_year", 2010)
        Setting.put("future_years", 0)
        db.session.commit()
        assert batch_year_bounds() == (2010, this_year)
        # absurd values are clamped, not trusted
        Setting.put("first_batch_year", 1200)
        Setting.put("future_years", 500)
        db.session.commit()
        first, last = batch_year_bounds()
        assert first == 1900 and last == this_year + 10


@pytest.mark.parametrize("password,ok", [
    ("Testing@123", True),
    ("a-long-enough-passphrase", True),
    ("password123", False),
    ("12345678", False),
    ("aaaaaaaa", False),
    ("87654321", False),
])
def test_password_policy(app, password, ok):
    from wtforms.validators import ValidationError
    from app.utils import StrongPassword

    class FakeField:
        def __init__(self, data):
            self.data = data

    validator = StrongPassword()
    try:
        validator(object(), FakeField(password))
        rejected = False
    except ValidationError:
        rejected = True
    assert rejected is (not ok), f"{password!r}"
