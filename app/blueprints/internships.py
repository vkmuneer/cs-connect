"""Internships: alumni offering training places to current students."""
from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms import (
    ConfirmForm, InterestStatusForm, InternshipForm, InternshipInterestForm,
)
from app.models import (
    ActivityLog, InterestStatus, Internship, InternshipInterest, InternshipStatus,
    Message, Skill,
)
from app.utils import approved_required, parse_skills, save_upload

internships_bp = Blueprint("internships", __name__)


def _owner_or_admin(internship):
    return current_user.is_authenticated and (
        current_user.is_admin or internship.offered_by_id == current_user.id
    )


@internships_bp.route("/")
def listing():
    """Open internships, newest first."""
    q = (request.args.get("q") or "").strip()
    mode = (request.args.get("mode") or "").strip()
    paid = request.args.get("paid")

    query = Internship.query.filter_by(status=InternshipStatus.APPROVED)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Internship.title.ilike(like), Internship.organisation.ilike(like),
            Internship.description.ilike(like),
        ))
    if mode:
        query = query.filter(Internship.mode == mode)
    if paid == "1":
        query = query.filter(Internship.is_paid.is_(True))

    pagination = query.order_by(Internship.created_at.desc()).paginate(
        page=request.args.get("page", 1, type=int),
        per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False,
    )
    return render_template(
        "internships/listing.html", pagination=pagination, q=q, mode=mode, paid=paid,
    )


@internships_bp.route("/<int:internship_id>")
def detail(internship_id):
    internship = db.session.get(Internship, internship_id)
    if internship is None:
        abort(404)
    if internship.status != InternshipStatus.APPROVED and not _owner_or_admin(internship):
        abort(404)
    return render_template(
        "internships/detail.html", internship=internship,
        existing=internship.interest_from(current_user),
        can_manage=_owner_or_admin(internship),
    )


@internships_bp.route("/offer", methods=["GET", "POST"])
@login_required
@approved_required
def create():
    form = InternshipForm()
    if form.validate_on_submit():
        internship = Internship(offered_by_id=current_user.id)
        _apply_form(form, internship)
        internship.status = (
            InternshipStatus.APPROVED if current_user.is_staff else InternshipStatus.PENDING
        )
        db.session.add(internship)
        ActivityLog.record(
            current_user, "internship_create", f"{internship.title} @ {internship.organisation}"
        )
        db.session.commit()
        if internship.status == InternshipStatus.PENDING:
            flash(
                "Thank you — your internship has been sent to the department and will "
                "be listed for students once it is approved.",
                "success",
            )
        else:
            flash("Internship published.", "success")
        return redirect(url_for("internships.detail", internship_id=internship.id))
    return render_template("internships/form.html", form=form, internship=None)


@internships_bp.route("/<int:internship_id>/edit", methods=["GET", "POST"])
@login_required
def edit(internship_id):
    internship = db.session.get(Internship, internship_id)
    if internship is None:
        abort(404)
    if not _owner_or_admin(internship):
        abort(403)

    form = InternshipForm(obj=internship)
    if request.method == "GET":
        form.skills.data = ", ".join(s.name for s in internship.skills)

    if form.validate_on_submit():
        _apply_form(form, internship)
        if not current_user.is_staff and internship.status == InternshipStatus.APPROVED:
            internship.status = InternshipStatus.PENDING
            flash("Your changes were saved and sent for re-approval.", "info")
        else:
            flash("Internship updated.", "success")
        ActivityLog.record(current_user, "internship_edit", f"#{internship.id} {internship.title}")
        db.session.commit()
        return redirect(url_for("internships.detail", internship_id=internship.id))

    return render_template("internships/form.html", form=form, internship=internship)


def _apply_form(form, internship):
    for field in ("title", "organisation", "location", "mode", "description",
                  "learning_outcomes", "eligibility", "is_paid", "stipend",
                  "starts_from", "apply_by"):
        setattr(internship, field, getattr(form, field).data)
    internship.duration_weeks = form.duration_weeks.data or None
    internship.seats = form.seats.data or 1
    if not internship.is_paid:
        internship.stipend = None
    internship.skills = [
        s for s in (Skill.get_or_create(n) for n in parse_skills(form.skills.data)) if s
    ]


@internships_bp.route("/<int:internship_id>/close", methods=["POST"])
@login_required
def close(internship_id):
    internship = db.session.get(Internship, internship_id)
    if internship is None:
        abort(404)
    if not _owner_or_admin(internship):
        abort(403)
    form = ConfirmForm()
    if form.validate_on_submit():
        internship.status = InternshipStatus.CLOSED
        ActivityLog.record(current_user, "internship_close", f"#{internship.id}")
        db.session.commit()
        flash("The internship has been closed.", "info")
    return redirect(url_for("internships.detail", internship_id=internship.id))


# --------------------------------------------------------------------------
# Students expressing interest
# --------------------------------------------------------------------------
@internships_bp.route("/<int:internship_id>/interest", methods=["GET", "POST"])
@login_required
@approved_required
def express_interest(internship_id):
    internship = db.session.get(Internship, internship_id)
    if internship is None or internship.status != InternshipStatus.APPROVED:
        abort(404)
    if internship.offered_by_id == current_user.id:
        flash("This is your own internship.", "warning")
        return redirect(url_for("internships.detail", internship_id=internship.id))
    if internship.is_expired:
        flash("The closing date for this internship has passed.", "warning")
        return redirect(url_for("internships.detail", internship_id=internship.id))
    if internship.interest_from(current_user):
        flash("You have already expressed interest in this internship.", "info")
        return redirect(url_for("internships.detail", internship_id=internship.id))

    form = InternshipInterestForm()
    profile = current_user.profile
    if form.validate_on_submit():
        try:
            uploaded = save_upload(form.resume.data, "resume")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(
                "internships/interest.html", form=form, internship=internship, profile=profile,
            )

        resume = uploaded or (profile.resume_filename if profile else None)
        if uploaded and profile and not profile.resume_filename:
            profile.resume_filename = uploaded

        db.session.add(InternshipInterest(
            internship_id=internship.id, student_id=current_user.id,
            note=form.note.data, resume_filename=resume,
        ))
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=internship.offered_by_id,
            subject=f"Interest in your internship: {internship.title}",
            body=f"{current_user.full_name} has expressed interest in “{internship.title}”. "
                 f"Open the internship's interest list to see their profile.",
        ))
        ActivityLog.record(current_user, "internship_interest", f"#{internship.id}")
        db.session.commit()
        flash("Your interest has been sent to the offerer.", "success")
        return redirect(url_for("internships.detail", internship_id=internship.id))

    return render_template(
        "internships/interest.html", form=form, internship=internship, profile=profile,
    )


@internships_bp.route("/<int:internship_id>/interested")
@login_required
def interested(internship_id):
    internship = db.session.get(Internship, internship_id)
    if internship is None:
        abort(404)
    if not _owner_or_admin(internship):
        abort(403)
    rows = (
        InternshipInterest.query.filter_by(internship_id=internship.id)
        .order_by(InternshipInterest.created_at.desc())
        .all()
    )
    return render_template(
        "internships/interested.html", internship=internship, interests=rows,
        status_form=InterestStatusForm(),
    )


@internships_bp.route("/interest/<int:interest_id>/status", methods=["POST"])
@login_required
def update_interest(interest_id):
    interest = db.session.get(InternshipInterest, interest_id)
    if interest is None:
        abort(404)
    if not _owner_or_admin(interest.internship):
        abort(403)

    form = InterestStatusForm()
    if form.validate_on_submit():
        if (form.status.data == InterestStatus.ACCEPTED
                and interest.status != InterestStatus.ACCEPTED
                and interest.internship.seats_left < 1):
            flash("Every place on this internship is already taken.", "warning")
            return redirect(url_for("internships.interested",
                                    internship_id=interest.internship_id))

        interest.status = form.status.data
        interest.offerer_note = form.offerer_note.data
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=interest.student_id,
            subject=f"Update on the internship: {interest.internship.title}",
            body=f"Your interest in “{interest.internship.title}” at "
                 f"{interest.internship.organisation} is now marked as "
                 f"“{form.status.data}”."
                 + (f"\n\nNote:\n{form.offerer_note.data}" if form.offerer_note.data else ""),
        ))
        db.session.commit()
        flash("Updated, and the student has been notified.", "success")
    return redirect(url_for("internships.interested", internship_id=interest.internship_id))


@internships_bp.route("/mine")
@login_required
def mine():
    offered = (
        Internship.query.filter_by(offered_by_id=current_user.id)
        .order_by(Internship.created_at.desc())
        .all()
    )
    expressed = (
        InternshipInterest.query.filter_by(student_id=current_user.id)
        .order_by(InternshipInterest.created_at.desc())
        .all()
    )
    return render_template("internships/mine.html", offered=offered, expressed=expressed)
