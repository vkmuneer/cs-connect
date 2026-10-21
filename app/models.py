"""Database models for the CS Connect alumni portal."""
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


def utcnow():
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Association tables
# --------------------------------------------------------------------------
profile_skills = db.Table(
    "profile_skills",
    db.Column("profile_id", db.Integer, db.ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)

job_skills = db.Table(
    "job_skills",
    db.Column("job_id", db.Integer, db.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)


# --------------------------------------------------------------------------
# Enum-ish constants (kept as plain strings for SQLite friendliness)
# --------------------------------------------------------------------------
class Role:
    ADMIN = "admin"
    FACULTY = "faculty"   # a teacher of the department
    MEMBER = "member"
    ALL = [ADMIN, FACULTY, MEMBER]
    LABELS = {ADMIN: "Administrator", FACULTY: "Faculty", MEMBER: "Member"}


class Programme:
    BSC = "B.Sc Computer Science"
    MSC = "M.Sc Computer Science"
    PHD = "Ph.D Computer Science"
    ALL = [BSC, MSC, PHD]


class JobStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"


class ApplicationStatus:
    APPLIED = "applied"
    SHORTLISTED = "shortlisted"
    INTERVIEW = "interview"
    HIRED = "hired"
    REJECTED = "rejected"
    ALL = [APPLIED, SHORTLISTED, INTERVIEW, HIRED, REJECTED]


class CoordinatorRole:
    ALUMNI = "Alumni Coordinator"
    STAFF = "Staff Coordinator"
    STUDENT = "Student Coordinator"
    PLACEMENT = "Placement Officer"
    OTHER = "Other"
    ALL = [ALUMNI, STAFF, STUDENT, PLACEMENT, OTHER]


# Administrator-controlled settings held in the settings table.
MULTI_DEPARTMENT = "multi_department_enabled"
FIRST_BATCH_YEAR = "first_batch_year"      # oldest year of admission offered
FUTURE_YEARS = "future_years"              # how many years ahead to offer


class InternshipStatus:
    PENDING = "pending"
    APPROVED = "approved"
    CLOSED = "closed"
    REJECTED = "rejected"


class InterestStatus:
    EXPRESSED = "expressed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    COMPLETED = "completed"
    ALL = [EXPRESSED, ACCEPTED, DECLINED, COMPLETED]


INTERNSHIP_MODES = ["On-site", "Remote", "Hybrid"]

TALK_MODES = ["On campus", "Online", "Either"]


class TalkStatus:
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ALL = [PROPOSED, CONFIRMED, COMPLETED, CANCELLED]

JOB_TYPES = ["Full-time", "Part-time", "Internship", "Contract", "Freelance"]
WORK_MODES = ["On-site", "Hybrid", "Remote"]


# --------------------------------------------------------------------------
# Users & profiles
# --------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default=Role.MEMBER, nullable=False, index=True)

    is_approved = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)

    profile = db.relationship(
        "Profile", back_populates="user", uselist=False,
        cascade="all, delete-orphan", passive_deletes=True,
    )
    jobs_posted = db.relationship(
        "Job", back_populates="posted_by", cascade="all, delete-orphan",
        passive_deletes=True, foreign_keys="Job.posted_by_id",
    )
    applications = db.relationship(
        "Application", back_populates="applicant", cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # -- auth helpers ------------------------------------------------------
    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_faculty(self):
        return self.role == Role.FACULTY

    @property
    def is_staff(self):
        """Department staff: an administrator or a teacher."""
        return self.role in (Role.ADMIN, Role.FACULTY)

    @property
    def role_label(self):
        return Role.LABELS.get(self.role, self.role.title())

    @property
    def is_active(self):
        """Flask-Login uses this to block sign-in for suspended accounts."""
        return not self.is_blocked

    @property
    def can_participate(self):
        """Who may post, apply, message and read resumes.

        Staff always may; a member once an administrator has verified them.
        """
        if self.is_blocked:
            return False
        return self.is_staff or self.is_approved

    def __repr__(self):
        return f"<User {self.email}>"


class Profile(db.Model):
    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )

    # Academic identity
    department_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="SET NULL"), index=True,
    )
    programme = db.Column(db.String(60), nullable=False, default=Programme.BSC, index=True)
    batch_year = db.Column(db.Integer, nullable=False, index=True)  # year of joining
    graduation_year = db.Column(db.Integer, index=True)
    register_number = db.Column(db.String(40))

    # Professional identity
    headline = db.Column(db.String(160))
    about = db.Column(db.Text)
    current_position = db.Column(db.String(120))
    current_company = db.Column(db.String(120))
    experience_years = db.Column(db.Float, default=0)
    location = db.Column(db.String(120), index=True)

    # Contact & links
    phone = db.Column(db.String(32))
    show_phone = db.Column(db.Boolean, default=False, nullable=False)
    show_email = db.Column(db.Boolean, default=True, nullable=False)
    linkedin_url = db.Column(db.String(255))
    github_url = db.Column(db.String(255))
    website_url = db.Column(db.String(255))

    # Files
    photo_filename = db.Column(db.String(255))
    resume_filename = db.Column(db.String(255))

    # Portal roles — a member can be both
    is_job_seeker = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_job_provider = db.Column(db.Boolean, default=False, nullable=False, index=True)
    open_to_work = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_hiring = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # Employer details (when is_job_provider)
    company_name = db.Column(db.String(160))
    company_website = db.Column(db.String(255))
    designation_at_company = db.Column(db.String(120))

    is_visible = db.Column(db.Boolean, default=True, nullable=False)

    # Expert talks: a member declares this themselves.
    offers_expert_talk = db.Column(db.Boolean, default=False, nullable=False, index=True)
    talk_topics = db.Column(db.Text)
    talk_mode = db.Column(db.String(20), default="Either")

    # Curated by an administrator: who the department puts forward as a
    # prominent alumnus, and why.
    is_featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    featured_title = db.Column(db.String(160))   # e.g. "Distinguished Alumnus 2026"
    featured_note = db.Column(db.Text)           # the citation shown on the card
    featured_order = db.Column(db.Integer, default=100, nullable=False)
    featured_at = db.Column(db.DateTime)

    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="profile")
    department = db.relationship("Department", back_populates="profiles")
    skills = db.relationship(
        "Skill", secondary=profile_skills, back_populates="profiles", lazy="selectin",
    )

    @property
    def display_batch(self):
        if self.graduation_year:
            return f"{self.batch_year}–{self.graduation_year}"
        return str(self.batch_year)

    @property
    def initials(self):
        parts = [p for p in (self.user.full_name or "").split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or "?"

    @classmethod
    def speakers_query(cls):
        """Members who have offered to give a talk or session to students."""
        return (
            cls.query.join(User)
            .filter(
                cls.offers_expert_talk.is_(True),
                cls.is_visible.is_(True),
                User.is_approved.is_(True),
                User.is_blocked.is_(False),
            )
            .order_by(User.full_name)
        )

    @classmethod
    def featured_query(cls):
        """Prominent alumni who are still verified, listed and unsuspended."""
        return (
            cls.query.join(User)
            .filter(
                cls.is_featured.is_(True),
                cls.is_visible.is_(True),
                User.is_approved.is_(True),
                User.is_blocked.is_(False),
            )
            .order_by(cls.featured_order, cls.featured_at.desc().nullslast())
        )

    @property
    def department_name(self):
        return self.department.name if self.department else "Computer Science"

    @property
    def placements(self):
        """Offers this member accepted through the portal."""
        return [a for a in self.user.applications if a.status == ApplicationStatus.HIRED]

    def __repr__(self):
        return f"<Profile {self.user_id} {self.programme} {self.batch_year}>"


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False, index=True)
    slug = db.Column(db.String(60), unique=True, nullable=False, index=True)

    profiles = db.relationship("Profile", secondary=profile_skills, back_populates="skills")
    jobs = db.relationship("Job", secondary=job_skills, back_populates="skills")

    @staticmethod
    def slugify(name):
        return "-".join(name.lower().strip().split())

    @classmethod
    def get_or_create(cls, name):
        name = " ".join(name.split())[:60]
        if not name:
            return None
        slug = cls.slugify(name)
        skill = cls.query.filter_by(slug=slug).first()
        if skill is None:
            skill = cls(name=name, slug=slug)
            db.session.add(skill)
            db.session.flush()
        return skill

    def __repr__(self):
        return f"<Skill {self.name}>"


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------
class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    posted_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    title = db.Column(db.String(160), nullable=False, index=True)
    company = db.Column(db.String(160), nullable=False, index=True)
    company_website = db.Column(db.String(255))
    location = db.Column(db.String(120), index=True)
    job_type = db.Column(db.String(40), default="Full-time", nullable=False, index=True)
    work_mode = db.Column(db.String(40), default="On-site", nullable=False, index=True)

    description = db.Column(db.Text, nullable=False)
    responsibilities = db.Column(db.Text)
    requirements = db.Column(db.Text)

    min_experience = db.Column(db.Float, default=0)
    max_experience = db.Column(db.Float)
    salary_range = db.Column(db.String(120))
    vacancies = db.Column(db.Integer, default=1)

    apply_url = db.Column(db.String(255))
    apply_email = db.Column(db.String(160))
    accepts_portal_applications = db.Column(db.Boolean, default=True, nullable=False)

    deadline = db.Column(db.Date, index=True)
    status = db.Column(db.String(20), default=JobStatus.PENDING, nullable=False, index=True)
    rejection_note = db.Column(db.String(255))
    view_count = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    posted_by = db.relationship("User", back_populates="jobs_posted", foreign_keys=[posted_by_id])
    skills = db.relationship("Skill", secondary=job_skills, back_populates="jobs", lazy="selectin")
    applications = db.relationship(
        "Application", back_populates="job", cascade="all, delete-orphan", passive_deletes=True,
    )

    @property
    def is_expired(self):
        from app.utils import portal_today

        return bool(self.deadline) and self.deadline < portal_today()

    @property
    def is_open(self):
        return self.status == JobStatus.APPROVED and not self.is_expired

    @property
    def experience_label(self):
        lo = self.min_experience or 0
        if self.max_experience:
            return f"{lo:g}–{self.max_experience:g} yrs"
        return "Fresher" if lo == 0 else f"{lo:g}+ yrs"

    def application_from(self, user):
        if not user or not user.is_authenticated:
            return None
        return Application.query.filter_by(job_id=self.id, applicant_id=user.id).first()

    def __repr__(self):
        return f"<Job {self.title} @ {self.company}>"


class Application(db.Model):
    __tablename__ = "applications"
    __table_args__ = (db.UniqueConstraint("job_id", "applicant_id", name="uq_application_once"),)

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    applicant_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    cover_letter = db.Column(db.Text)
    resume_filename = db.Column(db.String(255))  # snapshot at time of applying
    status = db.Column(db.String(20), default=ApplicationStatus.APPLIED, nullable=False, index=True)
    employer_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    job = db.relationship("Job", back_populates="applications")
    applicant = db.relationship("User", back_populates="applications")

    # ---- placements: hires that happened through this portal ------------
    @classmethod
    def placements_query(cls):
        """Applications that ended in an offer — the portal's placement record."""
        return cls.query.filter_by(status=ApplicationStatus.HIRED)

    @classmethod
    def placement_count(cls):
        return cls.placements_query().count()

    @classmethod
    def placement_stats(cls):
        from app.utils import portal_year

        rows = cls.placements_query().all()
        return {
            "total": len(rows),
            "companies": len({r.job.company for r in rows if r.job}),
            "members": len({r.applicant_id for r in rows}),
            "this_year": len([
                r for r in rows
                if r.updated_at and r.updated_at.year == portal_year()
            ]),
        }

    @property
    def placed_on(self):
        return self.updated_at or self.created_at

    def __repr__(self):
        return f"<Application job={self.job_id} user={self.applicant_id}>"


# --------------------------------------------------------------------------
# Internships offered by alumni to current students
# --------------------------------------------------------------------------
internship_skills = db.Table(
    "internship_skills",
    db.Column("internship_id", db.Integer,
              db.ForeignKey("internships.id", ondelete="CASCADE"), primary_key=True),
    db.Column("skill_id", db.Integer,
              db.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)


class Internship(db.Model):
    """A training place an alumnus offers to students of the department."""
    __tablename__ = "internships"

    id = db.Column(db.Integer, primary_key=True)
    offered_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    title = db.Column(db.String(160), nullable=False)
    organisation = db.Column(db.String(160), nullable=False)
    location = db.Column(db.String(120))
    mode = db.Column(db.String(20), default="On-site", nullable=False, index=True)

    description = db.Column(db.Text, nullable=False)
    learning_outcomes = db.Column(db.Text)
    eligibility = db.Column(db.String(400))

    duration_weeks = db.Column(db.Integer)
    seats = db.Column(db.Integer, default=1, nullable=False)
    is_paid = db.Column(db.Boolean, default=False, nullable=False)
    stipend = db.Column(db.String(120))

    starts_from = db.Column(db.Date)
    apply_by = db.Column(db.Date, index=True)

    status = db.Column(db.String(20), default=InternshipStatus.PENDING,
                       nullable=False, index=True)
    rejection_note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    offered_by = db.relationship("User", backref=db.backref(
        "internships_offered", cascade="all, delete-orphan", passive_deletes=True,
    ))
    skills = db.relationship("Skill", secondary=internship_skills, lazy="selectin")
    interests = db.relationship(
        "InternshipInterest", back_populates="internship",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    @property
    def is_expired(self):
        from app.utils import portal_today

        return bool(self.apply_by) and self.apply_by < portal_today()

    @property
    def is_open(self):
        return self.status == InternshipStatus.APPROVED and not self.is_expired

    @property
    def seats_left(self):
        taken = len([i for i in self.interests if i.status == InterestStatus.ACCEPTED])
        return max(0, (self.seats or 1) - taken)

    @property
    def duration_label(self):
        if not self.duration_weeks:
            return "Flexible"
        weeks = self.duration_weeks
        if weeks % 4 == 0 and weeks >= 4:
            months = weeks // 4
            return f"{months} month{'s' if months > 1 else ''}"
        return f"{weeks} week{'s' if weeks > 1 else ''}"

    def interest_from(self, user):
        if not user or not user.is_authenticated:
            return None
        return InternshipInterest.query.filter_by(
            internship_id=self.id, student_id=user.id
        ).first()

    def __repr__(self):
        return f"<Internship {self.title} @ {self.organisation}>"


class InternshipInterest(db.Model):
    """A student putting their hand up for an internship."""
    __tablename__ = "internship_interests"
    __table_args__ = (
        db.UniqueConstraint("internship_id", "student_id", name="uq_interest_once"),
    )

    id = db.Column(db.Integer, primary_key=True)
    internship_id = db.Column(
        db.Integer, db.ForeignKey("internships.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    note = db.Column(db.Text)
    resume_filename = db.Column(db.String(255))
    status = db.Column(db.String(20), default=InterestStatus.EXPRESSED,
                       nullable=False, index=True)
    offerer_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    internship = db.relationship("Internship", back_populates="interests")
    student = db.relationship("User", backref=db.backref(
        "internship_interests", cascade="all, delete-orphan", passive_deletes=True,
    ))

    def __repr__(self):
        return f"<InternshipInterest {self.internship_id} {self.student_id}>"


# --------------------------------------------------------------------------
# Expert talks and sessions by alumni
# --------------------------------------------------------------------------
class TalkSession(db.Model):
    """A talk or session by an alumnus, scheduled by the department."""
    __tablename__ = "talk_sessions"

    id = db.Column(db.Integer, primary_key=True)
    speaker_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    arranged_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    title = db.Column(db.String(200), nullable=False)
    topic = db.Column(db.Text)
    mode = db.Column(db.String(20), default="On campus", nullable=False)
    venue = db.Column(db.String(200))        # a room, or a meeting link
    audience = db.Column(db.String(200))     # e.g. Final-year B.Sc and M.Sc

    scheduled_for = db.Column(db.DateTime, index=True)
    duration_minutes = db.Column(db.Integer, default=60)

    status = db.Column(db.String(20), default=TalkStatus.PROPOSED, nullable=False, index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    speaker = db.relationship("User", foreign_keys=[speaker_id], backref=db.backref(
        "talks", cascade="all, delete-orphan", passive_deletes=True,
    ))
    arranged_by = db.relationship("User", foreign_keys=[arranged_by_id])

    @property
    def is_past(self):
        if not self.scheduled_for:
            return False
        when = self.scheduled_for
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when < datetime.now(timezone.utc)

    @property
    def is_upcoming(self):
        return (
            self.status in (TalkStatus.PROPOSED, TalkStatus.CONFIRMED)
            and not self.is_past
        )

    @property
    def when_label(self):
        if not self.scheduled_for:
            return "Date to be fixed"
        return self.scheduled_for.strftime("%d %B %Y, %H:%M")

    @classmethod
    def upcoming(cls, limit=None):
        query = (
            cls.query.filter(cls.status.in_([TalkStatus.PROPOSED, TalkStatus.CONFIRMED]))
            .filter(or_(cls.scheduled_for.is_(None),
                        cls.scheduled_for >= datetime.now(timezone.utc)))
            .order_by(cls.scheduled_for.asc().nullslast())
        )
        return query.limit(limit).all() if limit else query.all()

    def __repr__(self):
        return f"<TalkSession {self.title}>"


# --------------------------------------------------------------------------
# Messaging between members
# --------------------------------------------------------------------------
class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    subject = db.Column(db.String(160))
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    # Both sides cascade: sender_id/recipient_id are NOT NULL, so without this
    # SQLAlchemy would try to null them out when a member is deleted and fail.
    sender = db.relationship(
        "User", foreign_keys=[sender_id],
        backref=db.backref(
            "sent_messages", cascade="all, delete-orphan", passive_deletes=True,
        ),
    )
    recipient = db.relationship(
        "User", foreign_keys=[recipient_id],
        backref=db.backref(
            "received_messages", cascade="all, delete-orphan", passive_deletes=True,
        ),
    )

    @staticmethod
    def unread_count(user_id):
        return db.session.query(func.count(Message.id)).filter_by(
            recipient_id=user_id, is_read=False
        ).scalar() or 0

    def __repr__(self):
        return f"<Message {self.sender_id}->{self.recipient_id}>"


# --------------------------------------------------------------------------
# Image gallery
# --------------------------------------------------------------------------
class GalleryAlbum(db.Model):
    """A set of photographs — an alumni meet, a workshop, a farewell."""
    __tablename__ = "gallery_albums"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    event_date = db.Column(db.Date, index=True)
    is_published = db.Column(db.Boolean, default=True, nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=100, nullable=False)
    cover_image_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    images = db.relationship(
        "GalleryImage", back_populates="album", cascade="all, delete-orphan",
        passive_deletes=True, order_by="GalleryImage.sort_order, GalleryImage.id",
    )

    @staticmethod
    def slugify(title):
        cleaned = "".join(
            ch.lower() if (ch.isalnum() or ch.isspace()) else " " for ch in (title or "")
        )
        slug = "-".join(cleaned.split())[:80]
        return slug or "album"

    @property
    def cover(self):
        if self.cover_image_id:
            for image in self.images:
                if image.id == self.cover_image_id:
                    return image
        return self.images[0] if self.images else None

    @property
    def image_count(self):
        return len(self.images)

    @classmethod
    def published(cls):
        return (
            cls.query.filter_by(is_published=True)
            .order_by(cls.sort_order, cls.event_date.desc().nullslast(), cls.title)
            .all()
        )

    def __repr__(self):
        return f"<GalleryAlbum {self.slug}>"


class GalleryImage(db.Model):
    __tablename__ = "gallery_images"

    id = db.Column(db.Integer, primary_key=True)
    album_id = db.Column(
        db.Integer, db.ForeignKey("gallery_albums.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(300))
    sort_order = db.Column(db.Integer, default=100, nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    album = db.relationship("GalleryAlbum", back_populates="images")
    uploaded_by = db.relationship("User")

    def __repr__(self):
        return f"<GalleryImage {self.filename}>"


# --------------------------------------------------------------------------
# Department content (admin managed)
# --------------------------------------------------------------------------
class Faculty(db.Model):
    __tablename__ = "faculty"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    designation = db.Column(db.String(120))
    qualification = db.Column(db.String(160))
    specialization = db.Column(db.String(200))
    email = db.Column(db.String(160))
    phone = db.Column(db.String(32))
    photo_filename = db.Column(db.String(255))

    # The portal account this teacher signs in with, if one has been created.
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), unique=True, index=True,
    )

    is_current = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_hod = db.Column(db.Boolean, default=False, nullable=False)
    served_from = db.Column(db.Integer)
    served_to = db.Column(db.Integer)
    sort_order = db.Column(db.Integer, default=100, nullable=False)
    profile_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    account = db.relationship("User", backref=db.backref("faculty_record", uselist=False))

    @property
    def has_login(self):
        return self.user_id is not None

    @classmethod
    def for_user(cls, user):
        if not user or not getattr(user, "id", None):
            return None
        return cls.query.filter_by(user_id=user.id).first()

    @property
    def tenure(self):
        if self.served_from and self.served_to:
            return f"{self.served_from} – {self.served_to}"
        if self.served_from:
            return f"{self.served_from} – Present"
        return ""

    @property
    def initials(self):
        cleaned = self.name.replace("Dr.", "").replace("Prof.", "").replace("Mr.", "").replace("Ms.", "").replace("Mrs.", "")
        parts = [p for p in cleaned.split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or "F"

    def __repr__(self):
        return f"<Faculty {self.name}>"


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), default="News")  # News / Event / Notice
    is_published = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    event_date = db.Column(db.Date)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    author = db.relationship("User")

    def __repr__(self):
        return f"<Announcement {self.title}>"


class SitePage(db.Model):
    """Admin-editable content blocks (About College, About Department, etc.)."""
    __tablename__ = "site_pages"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(60), unique=True, nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    @classmethod
    def get(cls, slug, default_title=""):
        page = cls.query.filter_by(slug=slug).first()
        if page is None:
            page = cls(slug=slug, title=default_title or slug.replace("-", " ").title(), body="")
        return page

    def __repr__(self):
        return f"<SitePage {self.slug}>"


class ActivityLog(db.Model):
    """Lightweight audit trail for admin actions."""
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(80), nullable=False)
    detail = db.Column(db.String(400))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    actor = db.relationship("User")

    @classmethod
    def record(cls, actor, action, detail=""):
        db.session.add(cls(
            actor_id=getattr(actor, "id", None), action=action, detail=detail[:400],
        ))

    def __repr__(self):
        return f"<ActivityLog {self.action}>"


# --------------------------------------------------------------------------
# College-wide extension: departments, coordinators, feature switches
# --------------------------------------------------------------------------
class Department(db.Model):
    """A department of the college.

    Computer Science is the primary (and, out of the box, the only active)
    department. The others ship switched off; an administrator turns on the
    college-wide mode and then activates departments one at a time.
    """
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    slug = db.Column(db.String(60), unique=True, nullable=False, index=True)
    short_name = db.Column(db.String(30))

    description = db.Column(db.Text)
    email = db.Column(db.String(160))
    website = db.Column(db.String(255))
    programmes = db.Column(db.Text, default="")  # one per line

    is_active = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    sort_order = db.Column(db.Integer, default=100, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    profiles = db.relationship("Profile", back_populates="department")
    coordinators = db.relationship(
        "Coordinator", back_populates="department",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    @staticmethod
    def slugify(name):
        return "-".join(name.lower().split())

    @property
    def programme_list(self):
        return [line.strip() for line in (self.programmes or "").splitlines() if line.strip()]

    @property
    def member_count(self):
        return Profile.query.join(User).filter(
            Profile.department_id == self.id,
            User.is_approved.is_(True), User.is_blocked.is_(False),
        ).count()

    @classmethod
    def primary(cls):
        return (
            cls.query.filter_by(is_primary=True).first()
            or cls.query.filter_by(slug="computer-science").first()
        )

    @classmethod
    def active(cls):
        return cls.query.filter_by(is_active=True).order_by(cls.sort_order, cls.name).all()

    @classmethod
    def all_ordered(cls):
        return cls.query.order_by(cls.is_primary.desc(), cls.sort_order, cls.name).all()

    def __repr__(self):
        return f"<Department {self.name}>"


class Coordinator(db.Model):
    """Alumni / placement coordinators, recorded per department per year."""
    __tablename__ = "coordinators"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    academic_year = db.Column(db.String(12), nullable=False, index=True)  # e.g. 2025-26
    # Set for a batch coordinator: the year of admission they look after.
    # Left empty for a department-level coordinator.
    batch_year = db.Column(db.Integer, index=True)

    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(60), default=CoordinatorRole.ALUMNI, nullable=False, index=True)
    designation = db.Column(db.String(120))
    email = db.Column(db.String(160))
    phone = db.Column(db.String(32))
    photo_filename = db.Column(db.String(255))
    notes = db.Column(db.Text)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=100, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    department = db.relationship("Department", back_populates="coordinators")
    member = db.relationship("User")

    @property
    def initials(self):
        parts = [p for p in self.name.replace("Dr.", "").replace("Mr.", "")
                 .replace("Ms.", "").replace("Mrs.", "").split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or "C"

    @property
    def is_batch_coordinator(self):
        return self.batch_year is not None

    @staticmethod
    def academic_year_for_batch(batch_year):
        """A batch admitted in 1995 belongs to the 1995-96 academic year."""
        return f"{batch_year}-{str(int(batch_year) + 1)[2:]}"

    @classmethod
    def for_batch(cls, batch_year, active_only=True):
        query = cls.query.filter_by(batch_year=batch_year)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(cls.sort_order, cls.name).all()

    @classmethod
    def batch_map(cls, active_only=False):
        """batch year -> its coordinator records."""
        query = cls.query.filter(cls.batch_year.isnot(None))
        if active_only:
            query = query.filter_by(is_active=True)
        out = {}
        for row in query.order_by(cls.sort_order, cls.name).all():
            out.setdefault(row.batch_year, []).append(row)
        return out

    @classmethod
    def academic_years(cls):
        rows = (
            db.session.query(cls.academic_year)
            .filter(cls.batch_year.is_(None))
            .distinct()
            .order_by(cls.academic_year.desc())
            .all()
        )
        return [r[0] for r in rows]

    @classmethod
    def current_year_label(cls):
        """The academic year label for today — June starts a new year."""
        from app.utils import portal_today

        today = portal_today()
        start = today.year if today.month >= 6 else today.year - 1
        return f"{start}-{str(start + 1)[2:]}"

    def __repr__(self):
        return f"<Coordinator {self.name} {self.academic_year}>"


class Setting(db.Model):
    """Key/value store for administrator-controlled feature switches."""
    __tablename__ = "settings"

    key = db.Column(db.String(60), primary_key=True)
    # Text, not a short string: page copy lives here as well as flags.
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    @classmethod
    def get(cls, key, default=None):
        row = db.session.get(cls, key)
        return row.value if row is not None else default

    @classmethod
    def is_on(cls, key, default=False):
        raw = cls.get(key)
        if raw is None:
            return default
        return raw in ("1", "true", "yes", "on")

    @classmethod
    def clear(cls, key):
        row = db.session.get(cls, key)
        if row is not None:
            db.session.delete(row)
        return row

    @classmethod
    def put(cls, key, value):
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key)
            db.session.add(row)
        row.value = "1" if value is True else ("0" if value is False else str(value))
        return row

    def __repr__(self):
        return f"<Setting {self.key}={self.value}>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
