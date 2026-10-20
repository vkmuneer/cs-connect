"""Administration: verification queue, job moderation, department content."""
from datetime import datetime, timezone

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app.extensions import db
from app.forms import (
    AdminUserForm, AnnouncementForm, ConfirmForm, CoordinatorForm, DepartmentForm,
    FacultyForm, FeatureToggleForm, JobModerationForm, PortalSettingsForm,
    SitePageForm,
)
from app.models import (
    FIRST_BATCH_YEAR, FUTURE_YEARS, MULTI_DEPARTMENT, ActivityLog, Announcement,
    Application, ApplicationStatus, Coordinator, Department, Faculty, Job,
    JobStatus, Message, Profile, Role, Setting, SitePage, Skill, User,
)
from app.utils import (
    admin_required, batch_year_bounds, delete_upload, multi_department_enabled,
    programme_choices, save_upload,
)

admin_bp = Blueprint("admin", __name__)

MANAGED_PAGES = [
    ("about-college", "About the College"),
    ("about-department", "About the Department"),
    ("programme-bsc", "B.Sc Computer Science"),
    ("programme-msc", "M.Sc Computer Science"),
    ("programme-phd", "Ph.D Computer Science"),
    ("contact", "Contact Us"),
]


@admin_bp.before_request
@login_required
@admin_required
def restrict_to_admins():
    """Every route in this blueprint is admin-only."""
    return None


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@admin_bp.route("/")
def dashboard():
    stats = {
        "members": User.query.filter_by(role=Role.MEMBER).count(),
        "pending_members": User.query.filter_by(is_approved=False, is_blocked=False).count(),
        "blocked": User.query.filter_by(is_blocked=True).count(),
        "jobs": Job.query.count(),
        "pending_jobs": Job.query.filter_by(status=JobStatus.PENDING).count(),
        "open_jobs": Job.query.filter_by(status=JobStatus.APPROVED).count(),
        "applications": Application.query.count(),
        "messages": Message.query.count(),
        "faculty": Faculty.query.count(),
        "announcements": Announcement.query.count(),
        "skills": Skill.query.count(),
        "placements": Application.placement_count(),
        "departments_active": Department.query.filter_by(is_active=True).count(),
        "departments_total": Department.query.count(),
        "coordinators": Coordinator.query.filter_by(is_active=True).count(),
        "multi_department": multi_department_enabled(),
    }
    pending_members = (
        User.query.filter_by(is_approved=False, is_blocked=False)
        .order_by(User.created_at.desc())
        .limit(6)
        .all()
    )
    pending_jobs = (
        Job.query.filter_by(status=JobStatus.PENDING)
        .order_by(Job.created_at.desc())
        .limit(6)
        .all()
    )
    recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()
    batch_spread = (
        db.session.query(Profile.batch_year, func.count(Profile.id))
        .join(User)
        .filter(User.is_approved.is_(True))
        .group_by(Profile.batch_year)
        .order_by(Profile.batch_year.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "admin/dashboard.html", stats=stats, pending_members=pending_members,
        pending_jobs=pending_jobs, recent_logs=recent_logs,
        batch_spread=batch_spread, confirm_form=ConfirmForm(),
    )


# --------------------------------------------------------------------------
# Members
# --------------------------------------------------------------------------
@admin_bp.route("/members")
def members():
    scope = request.args.get("scope", "all")
    q = (request.args.get("q") or "").strip()
    batch = request.args.get("batch", type=int)
    programme = (request.args.get("programme") or "").strip()
    department_id = request.args.get("department", type=int)

    query = User.query
    if scope == "pending":
        query = query.filter_by(is_approved=False, is_blocked=False)
    elif scope == "approved":
        query = query.filter_by(is_approved=True, is_blocked=False)
    elif scope == "blocked":
        query = query.filter_by(is_blocked=True)
    elif scope == "admins":
        query = query.filter_by(role=Role.ADMIN)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))

    # Batch, programme and department live on the profile, as does batch sorting,
    # so the join happens once if any of them is in play.
    sort = request.args.get("sort", "recent")
    if batch or programme or department_id or sort == "batch":
        query = query.outerjoin(Profile)
        if batch:
            query = query.filter(Profile.batch_year == batch)
        if programme:
            query = query.filter(Profile.programme == programme)
        if department_id:
            query = query.filter(Profile.department_id == department_id)

    if sort == "batch":
        order = (Profile.batch_year.desc(), User.full_name)
    elif sort == "name":
        order = (User.full_name,)
    else:
        order = (User.created_at.desc(),)

    pagination = query.order_by(*order).paginate(
        page=request.args.get("page", 1, type=int), per_page=20, error_out=False
    )
    counts = {
        "all": User.query.count(),
        "pending": User.query.filter_by(is_approved=False, is_blocked=False).count(),
        "approved": User.query.filter_by(is_approved=True, is_blocked=False).count(),
        "blocked": User.query.filter_by(is_blocked=True).count(),
        "admins": User.query.filter_by(role=Role.ADMIN).count(),
    }
    return render_template(
        "admin/members.html", pagination=pagination, scope=scope, q=q,
        counts=counts, confirm_form=ConfirmForm(),
        batch=batch, programme=programme, department_id=department_id, sort=sort,
        batch_years=[row[0] for row in _admin_batch_rows()],
        programmes=[p for p, _ in programme_choices()],
        departments=Department.all_ordered(),
    )


def _admin_batch_rows():
    """Every year of admission on record, newest first, with a member count."""
    return (
        db.session.query(Profile.batch_year, func.count(Profile.id))
        .group_by(Profile.batch_year)
        .order_by(Profile.batch_year.desc())
        .all()
    )


@admin_bp.route("/batches")
def batches():
    """Batch-wise register: counts, verification state and placements per year."""
    department_id = request.args.get("department", type=int)

    base = db.session.query(Profile).join(User)
    if department_id:
        base = base.filter(Profile.department_id == department_id)

    rows = {}
    for profile in base.all():
        row = rows.setdefault(profile.batch_year, {
            "year": profile.batch_year, "total": 0, "verified": 0, "pending": 0,
            "blocked": 0, "seekers": 0, "providers": 0, "hidden": 0,
            "programmes": {}, "placements": 0, "graduated": 0,
        })
        user = profile.user
        row["total"] += 1
        if user.is_blocked:
            row["blocked"] += 1
        elif user.is_approved:
            row["verified"] += 1
        else:
            row["pending"] += 1
        if profile.is_job_seeker:
            row["seekers"] += 1
        if profile.is_job_provider:
            row["providers"] += 1
        if not profile.is_visible:
            row["hidden"] += 1
        if profile.graduation_year:
            row["graduated"] += 1
        row["programmes"][profile.programme] = row["programmes"].get(profile.programme, 0) + 1
        row["placements"] += len([
            a for a in user.applications if a.status == ApplicationStatus.HIRED
        ])

    batches = sorted(rows.values(), key=lambda r: r["year"], reverse=True)
    totals = {
        "batches": len(batches),
        "members": sum(r["total"] for r in batches),
        "pending": sum(r["pending"] for r in batches),
        "placements": sum(r["placements"] for r in batches),
    }
    return render_template(
        "admin/batches.html", batches=batches, totals=totals,
        departments=Department.all_ordered(), department_id=department_id,
    )


def _get_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    return user


@admin_bp.route("/members/<int:user_id>/approve", methods=["POST"])
def approve_member(user_id):
    user = _get_user(user_id)
    form = ConfirmForm()
    if form.validate_on_submit():
        user.is_approved = True
        user.is_blocked = False
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=user.id,
            subject="Your CS Connect membership is verified",
            body="Welcome to CS Connect. Your membership has been verified by the "
                 "department, so your profile is now listed in the alumni directory "
                 "and you can post and apply for opportunities.",
        ))
        ActivityLog.record(current_user, "member_approve", user.email)
        db.session.commit()
        flash(f"{user.full_name} has been verified.", "success")
    return redirect(request.referrer or url_for("admin.members", scope="pending"))


@admin_bp.route("/members/<int:user_id>/block", methods=["POST"])
def block_member(user_id):
    user = _get_user(user_id)
    if user.id == current_user.id:
        flash("You cannot suspend your own account.", "danger")
        return redirect(url_for("admin.members"))
    form = ConfirmForm()
    if form.validate_on_submit():
        user.is_blocked = not user.is_blocked
        ActivityLog.record(
            current_user, "member_block" if user.is_blocked else "member_unblock", user.email
        )
        db.session.commit()
        flash(
            f"{user.full_name} has been {'suspended' if user.is_blocked else 'reinstated'}.",
            "info",
        )
    return redirect(request.referrer or url_for("admin.members"))


@admin_bp.route("/members/<int:user_id>/edit", methods=["GET", "POST"])
def edit_member(user_id):
    user = _get_user(user_id)
    form = AdminUserForm(obj=user)
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        clash = User.query.filter(User.email == email, User.id != user.id).first()
        if clash:
            flash("Another account already uses that email.", "danger")
            return render_template("admin/member_form.html", form=form, member=user)

        if user.id == current_user.id and form.role.data != Role.ADMIN:
            flash("You cannot remove your own administrator role.", "danger")
            return render_template("admin/member_form.html", form=form, member=user)

        user.full_name = form.full_name.data.strip()
        user.email = email
        user.role = form.role.data
        user.is_approved = form.is_approved.data
        user.is_blocked = form.is_blocked.data
        if form.new_password.data:
            user.set_password(form.new_password.data)
        ActivityLog.record(current_user, "member_edit", user.email)
        db.session.commit()
        flash("Member updated.", "success")
        return redirect(url_for("admin.members"))

    return render_template("admin/member_form.html", form=form, member=user)


@admin_bp.route("/members/<int:user_id>/delete", methods=["POST"])
def delete_member(user_id):
    user = _get_user(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin.members"))
    form = ConfirmForm()
    if form.validate_on_submit():
        if user.profile:
            delete_upload(user.profile.photo_filename, "photo")
            delete_upload(user.profile.resume_filename, "resume")
        label = f"{user.full_name} <{user.email}>"
        db.session.delete(user)
        ActivityLog.record(current_user, "member_delete", label)
        db.session.commit()
        flash(f"{label} has been removed.", "info")
    return redirect(url_for("admin.members"))


# --------------------------------------------------------------------------
# Job moderation
# --------------------------------------------------------------------------
@admin_bp.route("/jobs")
def jobs():
    scope = request.args.get("scope", "pending")
    query = Job.query
    if scope in (JobStatus.PENDING, JobStatus.APPROVED, JobStatus.REJECTED, JobStatus.CLOSED):
        query = query.filter_by(status=scope)
    pagination = query.order_by(Job.created_at.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=20, error_out=False
    )
    counts = {
        "all": Job.query.count(),
        JobStatus.PENDING: Job.query.filter_by(status=JobStatus.PENDING).count(),
        JobStatus.APPROVED: Job.query.filter_by(status=JobStatus.APPROVED).count(),
        JobStatus.REJECTED: Job.query.filter_by(status=JobStatus.REJECTED).count(),
        JobStatus.CLOSED: Job.query.filter_by(status=JobStatus.CLOSED).count(),
    }
    return render_template(
        "admin/jobs.html", pagination=pagination, scope=scope, counts=counts,
        confirm_form=ConfirmForm(), moderation_form=JobModerationForm(),
    )


def _get_job(job_id):
    job = db.session.get(Job, job_id)
    if job is None:
        abort(404)
    return job


@admin_bp.route("/jobs/<int:job_id>/approve", methods=["POST"])
def approve_job(job_id):
    job = _get_job(job_id)
    form = ConfirmForm()
    if form.validate_on_submit():
        job.status = JobStatus.APPROVED
        job.rejection_note = None
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=job.posted_by_id,
            subject=f"Approved: {job.title}",
            body=f"Your posting “{job.title}” at {job.company} is now live on the "
                 f"CS Connect job board.",
        ))
        ActivityLog.record(current_user, "job_approve", f"#{job.id} {job.title}")
        db.session.commit()
        flash(f"“{job.title}” is now live.", "success")
    return redirect(request.referrer or url_for("admin.jobs"))


@admin_bp.route("/jobs/<int:job_id>/reject", methods=["POST"])
def reject_job(job_id):
    job = _get_job(job_id)
    form = JobModerationForm()
    if form.validate_on_submit():
        job.status = JobStatus.REJECTED
        job.rejection_note = form.rejection_note.data or None
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=job.posted_by_id,
            subject=f"Not approved: {job.title}",
            body=f"Your posting “{job.title}” at {job.company} was not approved."
                 + (f"\n\nReason: {job.rejection_note}" if job.rejection_note else "")
                 + "\n\nYou can edit the posting and submit it again.",
        ))
        ActivityLog.record(current_user, "job_reject", f"#{job.id} {job.title}")
        db.session.commit()
        flash(f"“{job.title}” was rejected and the poster notified.", "info")
    return redirect(request.referrer or url_for("admin.jobs"))


@admin_bp.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    job = _get_job(job_id)
    form = ConfirmForm()
    if form.validate_on_submit():
        label = f"#{job.id} {job.title}"
        db.session.delete(job)
        ActivityLog.record(current_user, "job_delete", label)
        db.session.commit()
        flash("The posting has been deleted.", "info")
    return redirect(url_for("admin.jobs"))


# --------------------------------------------------------------------------
# Faculty
# --------------------------------------------------------------------------
@admin_bp.route("/faculty")
def faculty():
    members_list = Faculty.query.order_by(
        Faculty.is_current.desc(), Faculty.is_hod.desc(), Faculty.sort_order, Faculty.name
    ).all()
    return render_template(
        "admin/faculty.html", members=members_list, confirm_form=ConfirmForm()
    )


@admin_bp.route("/faculty/new", methods=["GET", "POST"])
@admin_bp.route("/faculty/<int:faculty_id>/edit", methods=["GET", "POST"])
def edit_faculty(faculty_id=None):
    member = db.session.get(Faculty, faculty_id) if faculty_id else None
    if faculty_id and member is None:
        abort(404)

    form = FacultyForm(obj=member)
    if form.validate_on_submit():
        try:
            photo = save_upload(form.photo.data, "photo")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("admin/faculty_form.html", form=form, member=member)

        if member is None:
            member = Faculty()
            db.session.add(member)

        if member.is_hod and not form.is_hod.data:
            pass
        for field in (
            "name", "designation", "qualification", "specialization", "email", "phone",
            "profile_url", "is_current", "is_hod", "served_from", "served_to", "sort_order",
        ):
            setattr(member, field, getattr(form, field).data)
        member.sort_order = form.sort_order.data or 100
        if photo:
            delete_upload(member.photo_filename, "photo")
            member.photo_filename = photo

        # Only one head of department at a time.
        if member.is_hod:
            db.session.flush()
            Faculty.query.filter(Faculty.id != member.id, Faculty.is_hod.is_(True)).update(
                {"is_hod": False}, synchronize_session=False
            )

        ActivityLog.record(current_user, "faculty_save", member.name)
        db.session.commit()
        flash("Faculty record saved.", "success")
        return redirect(url_for("admin.faculty"))

    return render_template("admin/faculty_form.html", form=form, member=member)


@admin_bp.route("/faculty/<int:faculty_id>/delete", methods=["POST"])
def delete_faculty(faculty_id):
    member = db.session.get(Faculty, faculty_id)
    if member is None:
        abort(404)
    form = ConfirmForm()
    if form.validate_on_submit():
        delete_upload(member.photo_filename, "photo")
        name = member.name
        db.session.delete(member)
        ActivityLog.record(current_user, "faculty_delete", name)
        db.session.commit()
        flash(f"{name} has been removed from the faculty list.", "info")
    return redirect(url_for("admin.faculty"))


# --------------------------------------------------------------------------
# Announcements
# --------------------------------------------------------------------------
@admin_bp.route("/announcements")
def announcements():
    items = Announcement.query.order_by(
        Announcement.is_pinned.desc(), Announcement.created_at.desc()
    ).all()
    return render_template(
        "admin/announcements.html", items=items, confirm_form=ConfirmForm()
    )


@admin_bp.route("/announcements/new", methods=["GET", "POST"])
@admin_bp.route("/announcements/<int:announcement_id>/edit", methods=["GET", "POST"])
def edit_announcement(announcement_id=None):
    item = db.session.get(Announcement, announcement_id) if announcement_id else None
    if announcement_id and item is None:
        abort(404)

    form = AnnouncementForm(obj=item)
    if form.validate_on_submit():
        if item is None:
            item = Announcement(author_id=current_user.id)
            db.session.add(item)
        for field in ("title", "category", "body", "event_date", "is_published", "is_pinned"):
            setattr(item, field, getattr(form, field).data)
        ActivityLog.record(current_user, "announcement_save", item.title)
        db.session.commit()
        flash("Announcement saved.", "success")
        return redirect(url_for("admin.announcements"))

    return render_template("admin/announcement_form.html", form=form, item=item)


@admin_bp.route("/announcements/<int:announcement_id>/delete", methods=["POST"])
def delete_announcement(announcement_id):
    item = db.session.get(Announcement, announcement_id)
    if item is None:
        abort(404)
    form = ConfirmForm()
    if form.validate_on_submit():
        title = item.title
        db.session.delete(item)
        ActivityLog.record(current_user, "announcement_delete", title)
        db.session.commit()
        flash("Announcement deleted.", "info")
    return redirect(url_for("admin.announcements"))


# --------------------------------------------------------------------------
# Site pages
# --------------------------------------------------------------------------
@admin_bp.route("/pages")
def pages():
    rows = []
    for slug, label in MANAGED_PAGES:
        page = SitePage.query.filter_by(slug=slug).first()
        rows.append({"slug": slug, "label": label, "page": page})
    return render_template("admin/pages.html", rows=rows)


@admin_bp.route("/pages/<slug>", methods=["GET", "POST"])
def edit_page(slug):
    label = dict(MANAGED_PAGES).get(slug)
    if label is None:
        abort(404)

    page = SitePage.query.filter_by(slug=slug).first()
    form = SitePageForm(obj=page)
    if request.method == "GET" and page is None:
        form.title.data = label

    if form.validate_on_submit():
        if page is None:
            page = SitePage(slug=slug)
            db.session.add(page)
        page.title = form.title.data.strip()
        page.body = form.body.data
        ActivityLog.record(current_user, "page_save", slug)
        db.session.commit()
        flash(f"“{page.title}” saved.", "success")
        return redirect(url_for("admin.pages"))

    return render_template("admin/page_form.html", form=form, slug=slug, label=label, page=page)


# --------------------------------------------------------------------------
# Audit trail
# --------------------------------------------------------------------------
@admin_bp.route("/logs")
def logs():
    pagination = ActivityLog.query.order_by(ActivityLog.created_at.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=50, error_out=False
    )
    return render_template("admin/logs.html", pagination=pagination)


# --------------------------------------------------------------------------
# Placements made through the portal
# --------------------------------------------------------------------------
@admin_bp.route("/placements")
def placements():
    rows = (
        Application.placements_query()
        .order_by(Application.updated_at.desc().nullslast())
        .all()
    )
    in_progress = (
        Application.query.filter(
            Application.status.in_([
                ApplicationStatus.SHORTLISTED, ApplicationStatus.INTERVIEW,
            ])
        )
        .order_by(Application.updated_at.desc().nullslast())
        .all()
    )
    return render_template(
        "admin/placements.html", placements=rows, in_progress=in_progress,
        stats=Application.placement_stats(),
    )


# --------------------------------------------------------------------------
# Departments — the college-wide extension, off until switched on
# --------------------------------------------------------------------------
@admin_bp.route("/departments", methods=["GET", "POST"])
def departments():
    toggle_form = FeatureToggleForm()
    settings_form = PortalSettingsForm()

    # Two forms on one page: the submit button tells them apart.
    if "first_batch_year" in request.form and settings_form.validate_on_submit():
        Setting.put(FIRST_BATCH_YEAR, settings_form.first_batch_year.data)
        Setting.put(FUTURE_YEARS, settings_form.future_years.data)
        ActivityLog.record(
            current_user, "setting_change",
            f"batch years {settings_form.first_batch_year.data} "
            f"+{settings_form.future_years.data} future",
        )
        db.session.commit()
        first, last = batch_year_bounds()
        flash(f"Years of admission now offered: {first} to {last}.", "success")
        return redirect(url_for("admin.departments"))

    if "enabled" in request.form or (
        request.method == "POST" and "first_batch_year" not in request.form
    ):
        if toggle_form.validate_on_submit():
            Setting.put(MULTI_DEPARTMENT, bool(toggle_form.enabled.data))
            ActivityLog.record(
                current_user, "setting_change",
                f"college-wide mode {'enabled' if toggle_form.enabled.data else 'disabled'}",
            )
            db.session.commit()
            if toggle_form.enabled.data:
                flash(
                    "College-wide mode is on. Activate the departments you want to open — "
                    "alumni can then register against them.",
                    "success",
                )
            else:
                flash(
                    "College-wide mode is off. The portal again serves the Department of "
                    "Computer Science only; existing records are untouched.",
                    "info",
                )
            return redirect(url_for("admin.departments"))

    first_year, last_year = batch_year_bounds()
    if request.method == "GET":
        toggle_form.enabled.data = multi_department_enabled()
        settings_form.first_batch_year.data = first_year
        settings_form.future_years.data = last_year - datetime.now(timezone.utc).year

    rows = Department.all_ordered()
    return render_template(
        "admin/departments.html", departments=rows, toggle_form=toggle_form,
        settings_form=settings_form, confirm_form=ConfirmForm(),
        enabled=multi_department_enabled(),
        first_year=first_year, last_year=last_year,
    )


@admin_bp.route("/departments/new", methods=["GET", "POST"])
@admin_bp.route("/departments/<int:department_id>/edit", methods=["GET", "POST"])
def edit_department(department_id=None):
    dept = db.session.get(Department, department_id) if department_id else None
    if department_id and dept is None:
        abort(404)

    form = DepartmentForm(obj=dept)
    if form.validate_on_submit():
        slug = Department.slugify(form.name.data)
        clash = Department.query.filter(
            Department.slug == slug, Department.id != (dept.id if dept else 0)
        ).first()
        if clash:
            flash("A department with that name already exists.", "danger")
            return render_template("admin/department_form.html", form=form, department=dept)

        if dept is None:
            dept = Department(slug=slug)
            db.session.add(dept)
        dept.slug = slug
        for field in ("name", "short_name", "description", "programmes", "email",
                      "website", "is_active"):
            setattr(dept, field, getattr(form, field).data)
        dept.sort_order = form.sort_order.data or 100
        ActivityLog.record(current_user, "department_save", dept.name)
        db.session.commit()
        flash(f"“{dept.name}” saved.", "success")
        return redirect(url_for("admin.departments"))

    return render_template("admin/department_form.html", form=form, department=dept)


@admin_bp.route("/departments/<int:department_id>/toggle", methods=["POST"])
def toggle_department(department_id):
    dept = db.session.get(Department, department_id)
    if dept is None:
        abort(404)
    form = ConfirmForm()
    if form.validate_on_submit():
        if dept.is_primary and dept.is_active:
            flash("The Department of Computer Science owns this portal and stays active.", "warning")
            return redirect(url_for("admin.departments"))
        dept.is_active = not dept.is_active
        ActivityLog.record(
            current_user,
            "department_activate" if dept.is_active else "department_deactivate", dept.name,
        )
        db.session.commit()
        state = "activated" if dept.is_active else "deactivated"
        note = ""
        if dept.is_active and not multi_department_enabled():
            note = " College-wide mode is still off, so it stays hidden until you switch that on."
        flash(f"{dept.name} {state}.{note}", "success" if dept.is_active else "info")
    return redirect(url_for("admin.departments"))


@admin_bp.route("/departments/<int:department_id>/delete", methods=["POST"])
def delete_department(department_id):
    dept = db.session.get(Department, department_id)
    if dept is None:
        abort(404)
    form = ConfirmForm()
    if form.validate_on_submit():
        if dept.is_primary:
            flash("The primary department cannot be deleted.", "danger")
            return redirect(url_for("admin.departments"))
        if dept.member_count:
            flash(
                f"{dept.name} still has {dept.member_count} member(s). Deactivate it instead.",
                "warning",
            )
            return redirect(url_for("admin.departments"))
        name = dept.name
        db.session.delete(dept)
        ActivityLog.record(current_user, "department_delete", name)
        db.session.commit()
        flash(f"{name} removed.", "info")
    return redirect(url_for("admin.departments"))


# --------------------------------------------------------------------------
# Coordinators, per department per academic year
# --------------------------------------------------------------------------
@admin_bp.route("/coordinators")
def coordinators():
    year = request.args.get("year") or ""
    department_id = request.args.get("department", type=int)

    query = Coordinator.query
    if year:
        query = query.filter_by(academic_year=year)
    if department_id:
        query = query.filter_by(department_id=department_id)
    rows = query.order_by(
        Coordinator.academic_year.desc(), Coordinator.sort_order, Coordinator.name
    ).all()

    grouped = {}
    for row in rows:
        grouped.setdefault(row.academic_year, []).append(row)

    return render_template(
        "admin/coordinators.html", grouped=grouped, year=year,
        years=Coordinator.academic_years(), departments=Department.all_ordered(),
        department_id=department_id, confirm_form=ConfirmForm(),
        current_year=Coordinator.current_year_label(),
    )


def _coordinator_choices():
    return [(str(d.id), d.name + ("" if d.is_active else " (inactive)"))
            for d in Department.all_ordered()]


@admin_bp.route("/coordinators/new", methods=["GET", "POST"])
@admin_bp.route("/coordinators/<int:coordinator_id>/edit", methods=["GET", "POST"])
def edit_coordinator(coordinator_id=None):
    row = db.session.get(Coordinator, coordinator_id) if coordinator_id else None
    if coordinator_id and row is None:
        abort(404)

    form = CoordinatorForm(obj=row)
    form.department.choices = _coordinator_choices()
    if request.method == "GET":
        if row is not None:
            form.department.data = str(row.department_id)
        else:
            primary = Department.primary()
            form.department.data = str(primary.id) if primary else ""
            form.academic_year.data = Coordinator.current_year_label()

    if form.validate_on_submit():
        dept = db.session.get(Department, int(form.department.data or 0))
        if dept is None:
            flash("Choose a department for this coordinator.", "danger")
            return render_template("admin/coordinator_form.html", form=form, coordinator=row)
        try:
            photo = save_upload(form.photo.data, "photo")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("admin/coordinator_form.html", form=form, coordinator=row)

        if row is None:
            row = Coordinator()
            db.session.add(row)
        row.department_id = dept.id
        for field in ("academic_year", "name", "role", "designation", "email",
                      "phone", "notes", "is_active"):
            setattr(row, field, getattr(form, field).data)
        row.sort_order = form.sort_order.data or 100
        if photo:
            delete_upload(row.photo_filename, "photo")
            row.photo_filename = photo

        # Link the record to a portal account when the email matches one.
        if row.email:
            member = User.query.filter_by(email=row.email.lower().strip()).first()
            row.user_id = member.id if member else None

        ActivityLog.record(
            current_user, "coordinator_save", f"{row.name} · {dept.name} · {row.academic_year}"
        )
        db.session.commit()
        flash("Coordinator saved.", "success")
        return redirect(url_for("admin.coordinators", year=row.academic_year))

    return render_template("admin/coordinator_form.html", form=form, coordinator=row)


@admin_bp.route("/coordinators/<int:coordinator_id>/delete", methods=["POST"])
def delete_coordinator(coordinator_id):
    row = db.session.get(Coordinator, coordinator_id)
    if row is None:
        abort(404)
    form = ConfirmForm()
    if form.validate_on_submit():
        delete_upload(row.photo_filename, "photo")
        label = f"{row.name} ({row.academic_year})"
        db.session.delete(row)
        ActivityLog.record(current_user, "coordinator_delete", label)
        db.session.commit()
        flash(f"{label} removed.", "info")
    return redirect(url_for("admin.coordinators"))
