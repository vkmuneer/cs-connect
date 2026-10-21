"""Job board: browsing, posting, moderating-by-owner and applications."""
from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms import ApplicationForm, ApplicationStatusForm, ConfirmForm, JobFilterForm, JobForm
from app.models import (
    ActivityLog, Application, ApplicationStatus, Job, JobStatus, Message, Profile, Skill, User,
)
from app.utils import approved_required, parse_skills, save_upload

jobs_bp = Blueprint("jobs", __name__)


def _owner_or_admin(job):
    return current_user.is_authenticated and (
        current_user.is_admin or job.posted_by_id == current_user.id
    )


@jobs_bp.route("/")
def listing():
    form = JobFilterForm(request.args, meta={"csrf": False})
    query = Job.query.filter_by(status=JobStatus.APPROVED)

    q = (form.q.data or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Job.title.ilike(like), Job.company.ilike(like), Job.description.ilike(like))
        )
    if form.job_type.data:
        query = query.filter(Job.job_type == form.job_type.data)
    if form.work_mode.data:
        query = query.filter(Job.work_mode == form.work_mode.data)
    if form.location.data:
        query = query.filter(Job.location.ilike(f"%{form.location.data.strip()}%"))
    if form.skill.data:
        query = query.filter(Job.skills.any(Skill.slug == Skill.slugify(form.skill.data)))

    page_num = request.args.get("page", 1, type=int)
    pagination = query.order_by(Job.created_at.desc()).paginate(
        page=page_num, per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False
    )

    in_demand = (
        db.session.query(Skill)
        .join(Skill.jobs)
        .filter(Job.status == JobStatus.APPROVED)
        .group_by(Skill.id)
        .order_by(db.func.count(Job.id).desc())
        .limit(15)
        .all()
    )
    return render_template("jobs/listing.html", form=form, pagination=pagination, in_demand=in_demand)


@jobs_bp.route("/<int:job_id>")
def detail(job_id):
    job = db.session.get(Job, job_id)
    if job is None:
        abort(404)
    if job.status != JobStatus.APPROVED and not _owner_or_admin(job):
        abort(404)

    if job.status == JobStatus.APPROVED and not _owner_or_admin(job):
        job.view_count = (job.view_count or 0) + 1
        db.session.commit()

    existing = job.application_from(current_user)
    similar = (
        Job.query.filter(
            Job.status == JobStatus.APPROVED, Job.id != job.id,
            or_(Job.company == job.company, Job.job_type == job.job_type),
        )
        .order_by(Job.created_at.desc())
        .limit(4)
        .all()
    )
    return render_template(
        "jobs/detail.html", job=job, existing_application=existing,
        can_manage=_owner_or_admin(job), similar=similar,
    )


@jobs_bp.route("/post", methods=["GET", "POST"])
@login_required
@approved_required
def create():
    form = JobForm()
    if form.validate_on_submit():
        job = Job(posted_by_id=current_user.id)
        _apply_job_form(form, job)
        # Staff postings go live immediately; member postings are moderated.
        job.status = JobStatus.APPROVED if current_user.is_staff else JobStatus.PENDING
        db.session.add(job)

        profile = current_user.profile
        if profile and not profile.is_job_provider:
            profile.is_job_provider = True

        ActivityLog.record(current_user, "job_create", f"{job.title} @ {job.company}")
        db.session.commit()

        if job.status == JobStatus.PENDING:
            flash(
                "Thank you! Your opportunity has been submitted and will appear on the "
                "board once an administrator approves it.",
                "success",
            )
        else:
            flash("Opportunity published.", "success")
        return redirect(url_for("jobs.detail", job_id=job.id))

    return render_template("jobs/form.html", form=form, job=None)


@jobs_bp.route("/<int:job_id>/edit", methods=["GET", "POST"])
@login_required
def edit(job_id):
    job = db.session.get(Job, job_id)
    if job is None:
        abort(404)
    if not _owner_or_admin(job):
        abort(403)

    form = JobForm(obj=job)
    if request.method == "GET":
        form.skills.data = ", ".join(s.name for s in job.skills)

    if form.validate_on_submit():
        _apply_job_form(form, job)
        # Re-moderate member edits to an already-approved posting.
        if not current_user.is_staff and job.status == JobStatus.APPROVED:
            job.status = JobStatus.PENDING
            flash("Your changes were saved and sent for re-approval.", "info")
        else:
            flash("Opportunity updated.", "success")
        ActivityLog.record(current_user, "job_edit", f"#{job.id} {job.title}")
        db.session.commit()
        return redirect(url_for("jobs.detail", job_id=job.id))

    return render_template("jobs/form.html", form=form, job=job)


def _apply_job_form(form, job):
    for field in (
        "title", "company", "company_website", "location", "job_type", "work_mode",
        "description", "responsibilities", "requirements", "salary_range",
        "accepts_portal_applications", "apply_url", "apply_email", "deadline",
    ):
        setattr(job, field, getattr(form, field).data)
    job.min_experience = float(form.min_experience.data or 0)
    job.max_experience = float(form.max_experience.data) if form.max_experience.data is not None else None
    job.vacancies = form.vacancies.data or 1
    job.skills = [s for s in (Skill.get_or_create(n) for n in parse_skills(form.skills.data)) if s]


@jobs_bp.route("/<int:job_id>/close", methods=["POST"])
@login_required
def close(job_id):
    job = db.session.get(Job, job_id)
    if job is None:
        abort(404)
    if not _owner_or_admin(job):
        abort(403)
    form = ConfirmForm()
    if form.validate_on_submit():
        job.status = JobStatus.CLOSED
        ActivityLog.record(current_user, "job_close", f"#{job.id} {job.title}")
        db.session.commit()
        flash("The opportunity has been closed.", "info")
    return redirect(url_for("jobs.detail", job_id=job.id))


@jobs_bp.route("/<int:job_id>/reopen", methods=["POST"])
@login_required
def reopen(job_id):
    job = db.session.get(Job, job_id)
    if job is None:
        abort(404)
    if not _owner_or_admin(job):
        abort(403)
    form = ConfirmForm()
    if form.validate_on_submit():
        job.status = JobStatus.APPROVED if current_user.is_staff else JobStatus.PENDING
        db.session.commit()
        flash("The opportunity has been reopened.", "success")
    return redirect(url_for("jobs.detail", job_id=job.id))


# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------
@jobs_bp.route("/<int:job_id>/apply", methods=["GET", "POST"])
@login_required
@approved_required
def apply(job_id):
    job = db.session.get(Job, job_id)
    if job is None or job.status != JobStatus.APPROVED:
        abort(404)
    if not job.accepts_portal_applications:
        flash("This employer accepts applications outside the portal — use the link on the posting.", "info")
        return redirect(url_for("jobs.detail", job_id=job.id))
    if job.posted_by_id == current_user.id:
        flash("You cannot apply to your own posting.", "warning")
        return redirect(url_for("jobs.detail", job_id=job.id))
    if job.is_expired:
        flash("The application deadline for this opportunity has passed.", "warning")
        return redirect(url_for("jobs.detail", job_id=job.id))
    if job.application_from(current_user):
        flash("You have already applied to this opportunity.", "info")
        return redirect(url_for("jobs.detail", job_id=job.id))

    form = ApplicationForm()
    profile = current_user.profile
    if form.validate_on_submit():
        try:
            uploaded = save_upload(form.resume.data, "resume")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("jobs/apply.html", form=form, job=job, profile=profile)

        resume = uploaded or (profile.resume_filename if profile else None)
        if not resume:
            flash("Please attach a resume, or upload one to your profile first.", "danger")
            return render_template("jobs/apply.html", form=form, job=job, profile=profile)

        if uploaded and profile and not profile.resume_filename:
            profile.resume_filename = uploaded

        db.session.add(Application(
            job_id=job.id, applicant_id=current_user.id,
            cover_letter=form.cover_letter.data, resume_filename=resume,
        ))
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=job.posted_by_id,
            subject=f"New application: {job.title}",
            body=f"{current_user.full_name} has applied for “{job.title}”. "
                 f"Open the job's applicants list to review the profile and resume.",
        ))
        ActivityLog.record(current_user, "job_apply", f"#{job.id} {job.title}")
        db.session.commit()
        flash("Application submitted. The employer has been notified.", "success")
        return redirect(url_for("jobs.detail", job_id=job.id))

    return render_template("jobs/apply.html", form=form, job=job, profile=profile)


@jobs_bp.route("/<int:job_id>/applicants")
@login_required
def applicants(job_id):
    job = db.session.get(Job, job_id)
    if job is None:
        abort(404)
    if not _owner_or_admin(job):
        abort(403)

    rows = (
        Application.query.filter_by(job_id=job.id)
        .order_by(Application.created_at.desc())
        .all()
    )
    return render_template(
        "jobs/applicants.html", job=job, applications=rows, status_form=ApplicationStatusForm(),
    )


@jobs_bp.route("/application/<int:application_id>/status", methods=["POST"])
@login_required
def update_application(application_id):
    application = db.session.get(Application, application_id)
    if application is None:
        abort(404)
    if not _owner_or_admin(application.job):
        abort(403)

    form = ApplicationStatusForm()
    if form.validate_on_submit():
        application.status = form.status.data
        application.employer_note = form.employer_note.data
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=application.applicant_id,
            subject=f"Update on your application: {application.job.title}",
            body=f"Your application for “{application.job.title}” at {application.job.company} "
                 f"is now marked as “{form.status.data}”."
                 + (f"\n\nNote from the employer:\n{form.employer_note.data}" if form.employer_note.data else ""),
        ))
        db.session.commit()
        flash("Application status updated and the candidate has been notified.", "success")
    else:
        flash("Could not update the application.", "danger")
    return redirect(url_for("jobs.applicants", job_id=application.job_id))


@jobs_bp.route("/my/applications")
@login_required
def my_applications():
    rows = (
        Application.query.filter_by(applicant_id=current_user.id)
        .order_by(Application.created_at.desc())
        .all()
    )
    return render_template("jobs/my_applications.html", applications=rows)


@jobs_bp.route("/matches")
@login_required
@approved_required
def matches():
    """Opportunities that overlap with the member's own skill set."""
    profile = current_user.profile
    skill_ids = [s.id for s in profile.skills] if profile else []
    results = []
    if skill_ids:
        results = (
            Job.query.filter(Job.status == JobStatus.APPROVED)
            .filter(Job.skills.any(Skill.id.in_(skill_ids)))
            .order_by(Job.created_at.desc())
            .limit(30)
            .all()
        )
    return render_template("jobs/matches.html", jobs=results, profile=profile)
