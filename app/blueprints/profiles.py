"""Alumni directory, profile viewing and editing, resume downloads."""
from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, send_from_directory, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms import DirectoryFilterForm, ProfileForm
from app.models import (
    ActivityLog, Application, ApplicationStatus, Department, Job, Profile, Skill, User,
)
from app.utils import (
    approved_required, delete_upload, department_choices, multi_department_enabled,
    parse_skills, prepare_department_fields, programme_choices,
    programme_department_map, resolve_department, save_upload,
)

profiles_bp = Blueprint("profiles", __name__)


def _visible_profiles():
    """Base query: verified, unsuspended, directory-listed members."""
    return (
        Profile.query.join(User)
        .filter(
            User.is_approved.is_(True),
            User.is_blocked.is_(False),
            Profile.is_visible.is_(True),
        )
    )


@profiles_bp.route("/")
def directory():
    form = DirectoryFilterForm(request.args, meta={"csrf": False})
    form.department.choices = department_choices("All departments")
    form.programme.choices = programme_choices("All programmes")
    query = (
        Profile.query.join(User)
        .filter(
            User.is_approved.is_(True),
            User.is_blocked.is_(False),
            Profile.is_visible.is_(True),
        )
    )

    q = (form.q.data or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                User.full_name.ilike(like),
                Profile.headline.ilike(like),
                Profile.current_company.ilike(like),
                Profile.current_position.ilike(like),
                Profile.company_name.ilike(like),
                Profile.location.ilike(like),
            )
        )
    if form.department.data:
        query = query.filter(Profile.department_id == int(form.department.data))
    if form.programme.data:
        query = query.filter(Profile.programme == form.programme.data)
    if form.batch_year.data:
        query = query.filter(Profile.batch_year == int(form.batch_year.data))
    if form.graduation_year.data:
        query = query.filter(Profile.graduation_year == int(form.graduation_year.data))
    if form.skill.data:
        slug = Skill.slugify(form.skill.data)
        query = query.filter(Profile.skills.any(Skill.slug == slug))

    role = form.role.data
    if role == "seekers":
        query = query.filter(Profile.is_job_seeker.is_(True))
    elif role == "providers":
        query = query.filter(Profile.is_job_provider.is_(True))
    elif role == "hiring":
        query = query.filter(Profile.is_hiring.is_(True))

    page_num = request.args.get("page", 1, type=int)
    pagination = query.order_by(
        Profile.open_to_work.desc(), Profile.batch_year.desc(), User.full_name
    ).paginate(
        page=page_num, per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False
    )

    popular_skills = (
        db.session.query(Skill)
        .join(Skill.profiles)
        .group_by(Skill.id)
        .order_by(db.func.count(Profile.id).desc())
        .limit(18)
        .all()
    )

    return render_template(
        "profiles/directory.html",
        form=form, pagination=pagination, popular_skills=popular_skills,
        batch_years=_batch_years(),
    )


# --------------------------------------------------------------------------
# Browsing by batch (year of admission) and programme
# --------------------------------------------------------------------------
def _batch_years(department_id=None):
    """Distinct years of admission among listed members, newest first."""
    query = (
        db.session.query(Profile.batch_year, db.func.count(Profile.id))
        .join(User)
        .filter(User.is_approved.is_(True), User.is_blocked.is_(False),
                Profile.is_visible.is_(True))
    )
    if department_id:
        query = query.filter(Profile.department_id == department_id)
    return query.group_by(Profile.batch_year).order_by(Profile.batch_year.desc()).all()


@profiles_bp.route("/batches")
def batches():
    """Every batch, with a per-programme breakdown."""
    department_id = request.args.get("department", type=int)
    rows = (
        db.session.query(Profile.batch_year, Profile.programme, db.func.count(Profile.id))
        .join(User)
        .filter(User.is_approved.is_(True), User.is_blocked.is_(False),
                Profile.is_visible.is_(True))
    )
    if department_id:
        rows = rows.filter(Profile.department_id == department_id)
    rows = rows.group_by(Profile.batch_year, Profile.programme).order_by(
        Profile.batch_year.desc()
    ).all()

    years = {}
    for year, programme, count in rows:
        bucket = years.setdefault(year, {"year": year, "total": 0, "programmes": {}})
        bucket["total"] += count
        bucket["programmes"][programme] = count

    return render_template(
        "profiles/batches.html",
        batches=sorted(years.values(), key=lambda b: b["year"], reverse=True),
        programmes=[p for p, _ in programme_choices()],
        departments=Department.active() if multi_department_enabled() else [],
        department_id=department_id,
    )


@profiles_bp.route("/batch/<int:year>")
def batch(year):
    """Everyone admitted in one particular year."""
    programme = (request.args.get("programme") or "").strip()
    department_id = request.args.get("department", type=int)

    query = _visible_profiles().filter(Profile.batch_year == year)
    if programme:
        query = query.filter(Profile.programme == programme)
    if department_id:
        query = query.filter(Profile.department_id == department_id)

    members = query.order_by(Profile.programme, User.full_name).all()
    spread = {}
    for profile in members:
        spread[profile.programme] = spread.get(profile.programme, 0) + 1

    placements = [
        app for profile in members for app in profile.user.applications
        if app.status == ApplicationStatus.HIRED
    ]
    return render_template(
        "profiles/batch.html",
        year=year, members=members, programme=programme, spread=spread,
        placements=placements, all_years=[y for y, _ in _batch_years()],
        programmes=[p for p, _ in programme_choices()],
        departments=Department.active() if multi_department_enabled() else [],
        department_id=department_id,
    )


@profiles_bp.route("/<int:user_id>")
def view_profile(user_id):
    user = db.session.get(User, user_id)
    if user is None or user.profile is None:
        abort(404)

    viewer_is_self = current_user.is_authenticated and current_user.id == user.id
    viewer_is_admin = current_user.is_authenticated and current_user.is_admin
    if not (viewer_is_self or viewer_is_admin):
        if not user.is_approved or user.is_blocked or not user.profile.is_visible:
            abort(404)

    open_jobs = (
        Job.query.filter_by(posted_by_id=user.id, status="approved")
        .order_by(Job.created_at.desc())
        .all()
    )
    return render_template(
        "profiles/view.html",
        member=user, profile=user.profile, open_jobs=open_jobs,
        can_see_contact=current_user.is_authenticated,
        viewer_is_self=viewer_is_self,
    )


@profiles_bp.route("/me")
@login_required
def my_profile():
    if current_user.profile is None:
        return redirect(url_for("profiles.edit_profile"))

    my_jobs = (
        Job.query.filter_by(posted_by_id=current_user.id)
        .order_by(Job.created_at.desc())
        .all()
    )
    my_applications = (
        Application.query.filter_by(applicant_id=current_user.id)
        .order_by(Application.created_at.desc())
        .all()
    )
    received = (
        Application.query.join(Job)
        .filter(Job.posted_by_id == current_user.id)
        .order_by(Application.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "profiles/dashboard.html",
        profile=current_user.profile, my_jobs=my_jobs,
        my_applications=my_applications, received=received,
    )


@profiles_bp.route("/me/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    profile = current_user.profile
    if profile is None:
        profile = Profile(user_id=current_user.id, batch_year=current_app.config["FIRST_BATCH_YEAR"])
        db.session.add(profile)
        db.session.commit()

    form = ProfileForm(obj=profile)
    prepare_department_fields(form, profile)
    if request.method == "GET":
        form.full_name.data = current_user.full_name
        form.batch_year.data = str(profile.batch_year)
        form.graduation_year.data = str(profile.graduation_year) if profile.graduation_year else ""
        form.skills.data = ", ".join(s.name for s in profile.skills)

    if form.validate_on_submit():
        try:
            photo = save_upload(form.photo.data, "photo")
            resume = save_upload(form.resume.data, "resume")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(
        "profiles/edit.html", form=form, profile=profile,
        programme_map=programme_department_map(),
    )

        current_user.full_name = form.full_name.data.strip()

        # Scalar fields that map 1:1 from the form
        for field in (
            "programme", "register_number", "headline", "about", "current_position",
            "current_company", "location", "phone", "show_phone", "show_email",
            "linkedin_url", "github_url", "website_url", "is_job_seeker", "open_to_work",
            "is_job_provider", "is_hiring", "company_name", "company_website",
            "designation_at_company", "is_visible",
        ):
            setattr(profile, field, getattr(form, field).data)

        profile.batch_year = int(form.batch_year.data)
        profile.graduation_year = int(form.graduation_year.data) if form.graduation_year.data else None
        profile.experience_years = float(form.experience_years.data or 0)
        profile.department = resolve_department(form.department.data)

        if photo:
            delete_upload(profile.photo_filename, "photo")
            profile.photo_filename = photo
        if resume:
            delete_upload(profile.resume_filename, "resume")
            profile.resume_filename = resume

        profile.skills = [
            s for s in (Skill.get_or_create(n) for n in parse_skills(form.skills.data)) if s
        ]

        db.session.commit()
        flash("Your profile has been updated.", "success")
        return redirect(url_for("profiles.view_profile", user_id=current_user.id))

    return render_template(
        "profiles/edit.html", form=form, profile=profile,
        programme_map=programme_department_map(),
    )


@profiles_bp.route("/me/resume/delete", methods=["POST"])
@login_required
def delete_resume():
    profile = current_user.profile
    if profile and profile.resume_filename:
        delete_upload(profile.resume_filename, "resume")
        profile.resume_filename = None
        db.session.commit()
        flash("Resume removed.", "info")
    return redirect(url_for("profiles.edit_profile"))


@profiles_bp.route("/resume/<int:user_id>")
@login_required
@approved_required
def download_resume(user_id):
    """Resumes are visible to signed-in, approved members only."""
    user = db.session.get(User, user_id)
    if user is None or user.profile is None or not user.profile.resume_filename:
        abort(404)
    if not (current_user.id == user.id or current_user.is_admin):
        if not user.is_approved or user.is_blocked or not user.profile.is_visible:
            abort(404)
        ActivityLog.record(current_user, "resume_view", f"viewed resume of {user.email}")
        db.session.commit()

    return send_from_directory(
        current_app.config["RESUME_FOLDER"],
        user.profile.resume_filename,
        as_attachment=True,
        download_name=f"{user.full_name.replace(' ', '_')}_resume."
        + user.profile.resume_filename.rsplit(".", 1)[1],
    )
