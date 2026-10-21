"""The teachers' side of the portal: their dashboard and their own entry."""
from functools import wraps

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required

from app.extensions import db
from app.forms import FacultySelfForm
from app.models import (
    ActivityLog, Application, ApplicationStatus, Faculty, Internship,
    InternshipStatus, Job, JobStatus, Profile, TalkSession, User,
)
from app.utils import delete_upload, save_upload

staff_bp = Blueprint("staff", __name__)


def staff_required(view):
    """Teachers and administrators only."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        if not current_user.is_staff:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@staff_bp.route("/")
@login_required
@staff_required
def dashboard():
    """What a teacher sees after signing in."""
    record = Faculty.for_user(current_user)

    my_jobs = (
        Job.query.filter_by(posted_by_id=current_user.id)
        .order_by(Job.created_at.desc())
        .all()
    )
    my_internships = (
        Internship.query.filter_by(offered_by_id=current_user.id)
        .order_by(Internship.created_at.desc())
        .all()
    )
    my_talks = (
        TalkSession.query.filter_by(speaker_id=current_user.id)
        .order_by(TalkSession.scheduled_for.desc().nullslast())
        .all()
    )

    stats = {
        "members": User.query.filter_by(is_approved=True, is_blocked=False).count(),
        "batches": db.session.query(Profile.batch_year).distinct().count(),
        "open_jobs": Job.query.filter_by(status=JobStatus.APPROVED).count(),
        "open_internships": Internship.query.filter_by(
            status=InternshipStatus.APPROVED).count(),
        "placements": Application.placement_count(),
        "seekers": Profile.query.join(User).filter(
            Profile.is_job_seeker.is_(True), User.is_approved.is_(True)).count(),
    }

    recent_placements = (
        Application.placements_query()
        .order_by(Application.updated_at.desc().nullslast())
        .limit(5)
        .all()
    )
    open_to_work = (
        Profile.query.join(User)
        .filter(Profile.open_to_work.is_(True), Profile.is_visible.is_(True),
                User.is_approved.is_(True), User.is_blocked.is_(False))
        .order_by(Profile.updated_at.desc().nullslast())
        .limit(6)
        .all()
    )

    return render_template(
        "staff/dashboard.html", record=record, stats=stats,
        my_jobs=my_jobs, my_internships=my_internships, my_talks=my_talks,
        recent_placements=recent_placements, open_to_work=open_to_work,
    )


@staff_bp.route("/entry", methods=["GET", "POST"])
@login_required
@staff_required
def my_entry():
    """A teacher keeping their own faculty-page entry up to date."""
    record = Faculty.for_user(current_user)
    if record is None:
        flash(
            "Your account is not linked to an entry on the faculty page. "
            "An administrator can link it for you.",
            "warning",
        )
        return redirect(url_for("staff.dashboard"))

    form = FacultySelfForm(obj=record)
    if form.validate_on_submit():
        try:
            photo = save_upload(form.photo.data, "photo")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("staff/entry.html", form=form, record=record)

        for field in ("qualification", "specialization", "email", "phone", "profile_url"):
            setattr(record, field, getattr(form, field).data)
        if photo:
            delete_upload(record.photo_filename, "photo")
            record.photo_filename = photo

        ActivityLog.record(current_user, "faculty_self_edit", record.name)
        db.session.commit()
        flash("Your entry on the faculty page has been updated.", "success")
        return redirect(url_for("staff.dashboard"))

    return render_template("staff/entry.html", form=form, record=record)
