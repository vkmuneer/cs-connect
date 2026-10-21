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
    FacultyForm, FeatureAlumnusForm, FeatureToggleForm, GalleryAlbumForm,
    GalleryImageForm, GalleryUploadForm, JobModerationForm, PortalSettingsForm,
    SiteLinksForm, SitePageForm, TalkSessionForm,
)
from app.models import (
    FIRST_BATCH_YEAR, FUTURE_YEARS, MULTI_DEPARTMENT, ActivityLog, Announcement,
    Application, ApplicationStatus, Coordinator, Department, Faculty, GalleryAlbum,
    GalleryImage, Internship,
    InternshipStatus, Job, JobStatus, Message, Profile, Role, Setting, SitePage,
    Skill, TalkSession, TalkStatus, User,
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
        "prominent": Profile.query.filter_by(is_featured=True).count(),
        "internships": Internship.query.filter_by(status=InternshipStatus.APPROVED).count(),
        "pending_internships": Internship.query.filter_by(
            status=InternshipStatus.PENDING).count(),
        "talks_upcoming": len(TalkSession.upcoming()),
        "speakers": Profile.query.filter_by(offers_expert_talk=True).count(),
        "albums": GalleryAlbum.query.count(),
        "gallery_images": GalleryImage.query.count(),
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

    # Department-level records only; batch coordinators have their own register.
    query = Coordinator.query.filter(Coordinator.batch_year.is_(None))
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
            form.batch_year.data = str(row.batch_year) if row.batch_year else ""
        else:
            primary = Department.primary()
            form.department.data = str(primary.id) if primary else ""
            # ?batch=2009 comes from the batch register's "Add" links.
            batch = request.args.get("batch", type=int)
            if batch:
                form.batch_year.data = str(batch)
                form.academic_year.data = Coordinator.academic_year_for_batch(batch)
            else:
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
        for field in ("name", "role", "designation", "email", "phone", "notes",
                      "is_active"):
            setattr(row, field, getattr(form, field).data)

        # A batch coordinator belongs to a year of admission; its academic year
        # follows from that batch unless one was typed in.
        batch = form.batch_year.data
        row.batch_year = int(batch) if batch else None
        row.academic_year = (
            form.academic_year.data
            or (Coordinator.academic_year_for_batch(row.batch_year) if row.batch_year
                else Coordinator.current_year_label())
        )
        row.sort_order = form.sort_order.data or 100
        if photo:
            delete_upload(row.photo_filename, "photo")
            row.photo_filename = photo

        # Link the record to a portal account when the email matches one.
        if row.email:
            member = User.query.filter_by(email=row.email.lower().strip()).first()
            row.user_id = member.id if member else None

        scope = f"batch {row.batch_year}" if row.batch_year else dept.name
        ActivityLog.record(
            current_user, "coordinator_save", f"{row.name} · {scope} · {row.academic_year}"
        )
        db.session.commit()
        flash("Coordinator saved.", "success")
        if row.batch_year:
            return redirect(url_for("admin.batch_coordinators"))
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


# --------------------------------------------------------------------------
# Prominent alumni — curated from the registered members
# --------------------------------------------------------------------------
@admin_bp.route("/prominent")
def prominent():
    featured = (
        Profile.query.filter_by(is_featured=True)
        .order_by(Profile.featured_order, Profile.featured_at.desc().nullslast())
        .all()
    )
    # Members worth considering: most placements, then most recently active.
    suggestions = (
        Profile.query.join(User)
        .filter(
            Profile.is_featured.is_(False),
            Profile.is_visible.is_(True),
            User.is_approved.is_(True),
            User.is_blocked.is_(False),
        )
        .order_by(Profile.experience_years.desc().nullslast(), Profile.batch_year)
        .limit(12)
        .all()
    )
    return render_template(
        "admin/prominent.html", featured=featured, suggestions=suggestions,
        confirm_form=ConfirmForm(),
    )


def _get_profile(user_id):
    user = _get_user(user_id)
    if user.profile is None:
        flash(f"{user.full_name} has not filled in a profile yet.", "warning")
        return None
    return user.profile


@admin_bp.route("/members/<int:user_id>/highlight", methods=["GET", "POST"])
def highlight_member(user_id):
    """Add a member to the prominent alumni page, or edit their citation."""
    user = _get_user(user_id)
    profile = _get_profile(user_id)
    if profile is None:
        return redirect(url_for("admin.members"))

    form = FeatureAlumnusForm(obj=profile)
    if form.validate_on_submit():
        was_featured = profile.is_featured
        profile.is_featured = form.is_featured.data
        profile.featured_title = (form.featured_title.data or "").strip() or None
        profile.featured_note = (form.featured_note.data or "").strip() or None
        profile.featured_order = form.featured_order.data or 100
        if profile.is_featured and not was_featured:
            profile.featured_at = datetime.now(timezone.utc)
        elif not profile.is_featured:
            profile.featured_at = None

        ActivityLog.record(
            current_user,
            "alumnus_highlight" if profile.is_featured else "alumnus_unhighlight",
            f"{user.full_name} <{user.email}>",
        )
        db.session.commit()
        if profile.is_featured:
            flash(f"{user.full_name} now appears among the prominent alumni.", "success")
        else:
            flash(f"{user.full_name} is no longer highlighted.", "info")
        return redirect(url_for("admin.prominent"))

    return render_template("admin/prominent_form.html", form=form, member=user, profile=profile)


@admin_bp.route("/members/<int:user_id>/unhighlight", methods=["POST"])
def unhighlight_member(user_id):
    user = _get_user(user_id)
    form = ConfirmForm()
    if form.validate_on_submit() and user.profile:
        user.profile.is_featured = False
        user.profile.featured_at = None
        ActivityLog.record(current_user, "alumnus_unhighlight", user.email)
        db.session.commit()
        flash(f"{user.full_name} is no longer highlighted.", "info")
    return redirect(request.referrer or url_for("admin.prominent"))


# --------------------------------------------------------------------------
# Batch coordinators — one register, every year of admission
# --------------------------------------------------------------------------
@admin_bp.route("/batch-coordinators")
def batch_coordinators():
    """Every year of admission since the first batch, with its coordinators."""
    first_year, last_year = batch_year_bounds()
    coordinators_by_batch = Coordinator.batch_map()

    # How many members registered in each year, so an admin can see which
    # batches actually need a coordinator.
    members = dict(
        db.session.query(Profile.batch_year, func.count(Profile.id))
        .group_by(Profile.batch_year)
        .all()
    )

    show = request.args.get("show", "all")
    rows = []
    for year in range(last_year, first_year - 1, -1):
        people = coordinators_by_batch.get(year, [])
        if show == "missing" and people:
            continue
        if show == "filled" and not people:
            continue
        if show == "with-members" and not members.get(year):
            continue
        rows.append({
            "year": year,
            "coordinators": people,
            "members": members.get(year, 0),
        })

    total_years = last_year - first_year + 1
    covered = len([y for y in coordinators_by_batch if first_year <= y <= last_year])
    return render_template(
        "admin/batch_coordinators.html", rows=rows, show=show,
        first_year=first_year, last_year=last_year, total_years=total_years,
        covered=covered, confirm_form=ConfirmForm(),
    )


# --------------------------------------------------------------------------
# Outward links shown in the header and footer
# --------------------------------------------------------------------------
@admin_bp.route("/links", methods=["GET", "POST"])
def links():
    from app.content import SOCIAL_DEFAULTS, SOCIAL_LINKS, social_links

    form = SiteLinksForm()
    if form.validate_on_submit():
        for key, _label, _placeholder, _icon in SOCIAL_LINKS:
            value = (getattr(form, key).data or "").strip()
            Setting.put(key, value)
        ActivityLog.record(current_user, "links_save", "site links updated")
        db.session.commit()
        flash("Links saved.", "success")
        return redirect(url_for("admin.links"))

    if request.method == "GET":
        for key, _label, _placeholder, _icon in SOCIAL_LINKS:
            getattr(form, key).data = Setting.get(key, SOCIAL_DEFAULTS.get(key, ""))

    return render_template(
        "admin/links.html", form=form, fields=SOCIAL_LINKS, active=social_links(),
    )


# --------------------------------------------------------------------------
# Internship moderation
# --------------------------------------------------------------------------
@admin_bp.route("/internships")
def internships():
    scope = request.args.get("scope", "pending")
    query = Internship.query
    if scope in (InternshipStatus.PENDING, InternshipStatus.APPROVED,
                 InternshipStatus.REJECTED, InternshipStatus.CLOSED):
        query = query.filter_by(status=scope)
    rows = query.order_by(Internship.created_at.desc()).all()
    counts = {
        "all": Internship.query.count(),
        InternshipStatus.PENDING: Internship.query.filter_by(
            status=InternshipStatus.PENDING).count(),
        InternshipStatus.APPROVED: Internship.query.filter_by(
            status=InternshipStatus.APPROVED).count(),
        InternshipStatus.REJECTED: Internship.query.filter_by(
            status=InternshipStatus.REJECTED).count(),
        InternshipStatus.CLOSED: Internship.query.filter_by(
            status=InternshipStatus.CLOSED).count(),
    }
    return render_template(
        "admin/internships.html", internships=rows, scope=scope, counts=counts,
        confirm_form=ConfirmForm(), moderation_form=JobModerationForm(),
    )


def _get_internship(internship_id):
    internship = db.session.get(Internship, internship_id)
    if internship is None:
        abort(404)
    return internship


@admin_bp.route("/internships/<int:internship_id>/approve", methods=["POST"])
def approve_internship(internship_id):
    internship = _get_internship(internship_id)
    form = ConfirmForm()
    if form.validate_on_submit():
        internship.status = InternshipStatus.APPROVED
        internship.rejection_note = None
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=internship.offered_by_id,
            subject=f"Approved: {internship.title}",
            body=f"Your internship “{internship.title}” at {internship.organisation} is "
                 f"now listed for the students of the department. Thank you.",
        ))
        ActivityLog.record(current_user, "internship_approve", f"#{internship.id} {internship.title}")
        db.session.commit()
        flash(f"“{internship.title}” is now listed for students.", "success")
    return redirect(request.referrer or url_for("admin.internships"))


@admin_bp.route("/internships/<int:internship_id>/reject", methods=["POST"])
def reject_internship(internship_id):
    internship = _get_internship(internship_id)
    form = JobModerationForm()
    if form.validate_on_submit():
        internship.status = InternshipStatus.REJECTED
        internship.rejection_note = form.rejection_note.data or None
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=internship.offered_by_id,
            subject=f"Not approved: {internship.title}",
            body=f"Your internship “{internship.title}” was not approved."
                 + (f"\n\nReason: {internship.rejection_note}" if internship.rejection_note else "")
                 + "\n\nYou can edit it and submit it again.",
        ))
        ActivityLog.record(current_user, "internship_reject", f"#{internship.id}")
        db.session.commit()
        flash("The offer was rejected and the alumnus notified.", "info")
    return redirect(request.referrer or url_for("admin.internships"))


@admin_bp.route("/internships/<int:internship_id>/delete", methods=["POST"])
def delete_internship(internship_id):
    internship = _get_internship(internship_id)
    form = ConfirmForm()
    if form.validate_on_submit():
        label = f"#{internship.id} {internship.title}"
        db.session.delete(internship)
        ActivityLog.record(current_user, "internship_delete", label)
        db.session.commit()
        flash("The internship has been deleted.", "info")
    return redirect(url_for("admin.internships"))


# --------------------------------------------------------------------------
# Expert talks: who is willing, and what is scheduled
# --------------------------------------------------------------------------
def _speaker_choices():
    """Members who have offered to speak, plus anyone already scheduled."""
    rows = Profile.speakers_query().all()
    choices = [
        (str(p.user_id), f"{p.user.full_name} — {p.headline or p.programme}")
        for p in rows
    ]
    known = {value for value, _label in choices}
    for talk in TalkSession.query.all():
        if str(talk.speaker_id) not in known and talk.speaker:
            choices.append((str(talk.speaker_id), f"{talk.speaker.full_name} (not listed)"))
            known.add(str(talk.speaker_id))
    return choices


@admin_bp.route("/talks")
def talks():
    upcoming = TalkSession.upcoming()
    past = [
        t for t in TalkSession.query.order_by(
            TalkSession.scheduled_for.desc().nullslast()
        ).all()
        if t not in upcoming
    ]
    speakers = Profile.speakers_query().all()
    return render_template(
        "admin/talks.html", upcoming=upcoming, past=past, speakers=speakers,
        confirm_form=ConfirmForm(),
    )


@admin_bp.route("/talks/new", methods=["GET", "POST"])
@admin_bp.route("/talks/<int:talk_id>/edit", methods=["GET", "POST"])
def edit_talk(talk_id=None):
    talk = db.session.get(TalkSession, talk_id) if talk_id else None
    if talk_id and talk is None:
        abort(404)

    form = TalkSessionForm(obj=talk)
    form.speaker.choices = _speaker_choices()
    if request.method == "GET":
        if talk is not None:
            form.speaker.data = str(talk.speaker_id)
            if talk.scheduled_for:
                form.scheduled_date.data = talk.scheduled_for.date()
                form.scheduled_time.data = talk.scheduled_for.strftime("%H:%M")
        else:
            requested = request.args.get("speaker", type=int)
            if requested:
                form.speaker.data = str(requested)

    if form.validate_on_submit():
        speaker = db.session.get(User, int(form.speaker.data or 0))
        if speaker is None:
            flash("Choose a speaker for this session.", "danger")
            return render_template("admin/talks_form.html", form=form, talk=talk)

        creating = talk is None
        if creating:
            talk = TalkSession(arranged_by_id=current_user.id)
            db.session.add(talk)
        talk.speaker_id = speaker.id
        for field in ("title", "topic", "mode", "venue", "audience", "status", "notes"):
            setattr(talk, field, getattr(form, field).data)
        talk.duration_minutes = form.duration_minutes.data or 60

        if form.scheduled_date.data:
            hour, minute = 10, 0
            if form.scheduled_time.data:
                hour, minute = (int(part) for part in form.scheduled_time.data.split(":"))
            talk.scheduled_for = datetime(
                form.scheduled_date.data.year, form.scheduled_date.data.month,
                form.scheduled_date.data.day, hour, minute, tzinfo=timezone.utc,
            )
        else:
            talk.scheduled_for = None

        # Tell the speaker, so a session is never scheduled behind their back.
        db.session.add(Message(
            sender_id=current_user.id, recipient_id=speaker.id,
            subject=f"Session {'scheduled' if creating else 'updated'}: {talk.title}",
            body=f"The department has {'scheduled' if creating else 'updated'} your "
                 f"session “{talk.title}”.\n\n"
                 f"When: {talk.when_label}\n"
                 f"Mode: {talk.mode}\n"
                 f"Where: {talk.venue or 'to be confirmed'}\n"
                 f"Status: {talk.status}\n\n"
                 f"Reply to this message if the timing does not suit you.",
        ))
        ActivityLog.record(current_user, "talk_save", f"{talk.title} · {speaker.full_name}")
        db.session.commit()
        flash("Session saved, and the speaker has been notified.", "success")
        return redirect(url_for("admin.talks"))

    return render_template("admin/talks_form.html", form=form, talk=talk)


@admin_bp.route("/talks/<int:talk_id>/delete", methods=["POST"])
def delete_talk(talk_id):
    talk = db.session.get(TalkSession, talk_id)
    if talk is None:
        abort(404)
    form = ConfirmForm()
    if form.validate_on_submit():
        title = talk.title
        db.session.delete(talk)
        ActivityLog.record(current_user, "talk_delete", title)
        db.session.commit()
        flash(f"“{title}” removed.", "info")
    return redirect(url_for("admin.talks"))


# --------------------------------------------------------------------------
# Photo gallery
# --------------------------------------------------------------------------
@admin_bp.route("/gallery")
def gallery():
    albums = GalleryAlbum.query.order_by(
        GalleryAlbum.sort_order, GalleryAlbum.event_date.desc().nullslast()
    ).all()
    return render_template(
        "admin/gallery.html", albums=albums, confirm_form=ConfirmForm(),
    )


@admin_bp.route("/gallery/new", methods=["GET", "POST"])
@admin_bp.route("/gallery/<int:album_id>/edit", methods=["GET", "POST"])
def edit_album(album_id=None):
    album = db.session.get(GalleryAlbum, album_id) if album_id else None
    if album_id and album is None:
        abort(404)

    form = GalleryAlbumForm(obj=album)
    if form.validate_on_submit():
        slug = GalleryAlbum.slugify(form.title.data)
        clash = GalleryAlbum.query.filter(
            GalleryAlbum.slug == slug, GalleryAlbum.id != (album.id if album else 0)
        ).first()
        if clash:
            slug = f"{slug}-{int(datetime.now(timezone.utc).timestamp()) % 10000}"

        if album is None:
            album = GalleryAlbum(slug=slug)
            db.session.add(album)
        else:
            album.slug = slug
        for field in ("title", "description", "event_date", "is_published"):
            setattr(album, field, getattr(form, field).data)
        album.sort_order = form.sort_order.data or 100
        ActivityLog.record(current_user, "album_save", album.title)
        db.session.commit()
        flash(f"“{album.title}” saved.", "success")
        return redirect(url_for("admin.album_images", album_id=album.id))

    return render_template("admin/gallery_form.html", form=form, album=album)


@admin_bp.route("/gallery/<int:album_id>/images", methods=["GET", "POST"])
def album_images(album_id):
    album = db.session.get(GalleryAlbum, album_id)
    if album is None:
        abort(404)

    form = GalleryUploadForm()
    if form.validate_on_submit():
        files = request.files.getlist("images")
        added, refused = 0, []
        for index, storage in enumerate(files):
            if not storage or not storage.filename:
                continue
            try:
                stored = save_upload(storage, "gallery")
            except ValueError as exc:
                refused.append(f"{storage.filename}: {exc}")
                continue
            if stored:
                db.session.add(GalleryImage(
                    album_id=album.id, filename=stored,
                    caption=(form.caption.data or "").strip() or None,
                    sort_order=100 + len(album.images) + index,
                    uploaded_by_id=current_user.id,
                ))
                added += 1
        if added:
            ActivityLog.record(current_user, "gallery_upload", f"{added} to {album.title}")
            db.session.commit()
            flash(f"{added} image{'' if added == 1 else 's'} added.", "success")
        for problem in refused:
            flash(problem, "danger")
        if not added and not refused:
            flash("Choose at least one image to upload.", "warning")
        return redirect(url_for("admin.album_images", album_id=album.id))

    return render_template(
        "admin/gallery_images.html", album=album, form=form,
        image_form=GalleryImageForm(), confirm_form=ConfirmForm(),
    )


@admin_bp.route("/gallery/image/<int:image_id>/update", methods=["POST"])
def update_gallery_image(image_id):
    image = db.session.get(GalleryImage, image_id)
    if image is None:
        abort(404)
    form = GalleryImageForm()
    if form.validate_on_submit():
        image.caption = (form.caption.data or "").strip() or None
        image.sort_order = form.sort_order.data or 100
        db.session.commit()
        flash("Image updated.", "success")
    return redirect(url_for("admin.album_images", album_id=image.album_id))


@admin_bp.route("/gallery/image/<int:image_id>/cover", methods=["POST"])
def set_album_cover(image_id):
    image = db.session.get(GalleryImage, image_id)
    if image is None:
        abort(404)
    form = ConfirmForm()
    if form.validate_on_submit():
        image.album.cover_image_id = image.id
        db.session.commit()
        flash("Cover image set.", "success")
    return redirect(url_for("admin.album_images", album_id=image.album_id))


@admin_bp.route("/gallery/image/<int:image_id>/delete", methods=["POST"])
def delete_gallery_image(image_id):
    image = db.session.get(GalleryImage, image_id)
    if image is None:
        abort(404)
    album_id = image.album_id
    form = ConfirmForm()
    if form.validate_on_submit():
        if image.album.cover_image_id == image.id:
            image.album.cover_image_id = None
        delete_upload(image.filename, "gallery")
        db.session.delete(image)
        ActivityLog.record(current_user, "gallery_image_delete", image.filename)
        db.session.commit()
        flash("Image removed.", "info")
    return redirect(url_for("admin.album_images", album_id=album_id))


@admin_bp.route("/gallery/<int:album_id>/delete", methods=["POST"])
def delete_album(album_id):
    album = db.session.get(GalleryAlbum, album_id)
    if album is None:
        abort(404)
    form = ConfirmForm()
    if form.validate_on_submit():
        title = album.title
        for image in album.images:
            delete_upload(image.filename, "gallery")
        db.session.delete(album)
        ActivityLog.record(current_user, "album_delete", title)
        db.session.commit()
        flash(f"“{title}” and its images were removed.", "info")
    return redirect(url_for("admin.gallery"))


# --------------------------------------------------------------------------
# Editable page text
# --------------------------------------------------------------------------
@admin_bp.route("/content", methods=["GET", "POST"])
def content():
    """Every piece of copy on the home page and the member dashboard."""
    from app.content import TEXT_DEFAULTS, text_groups

    if request.method == "POST":
        changed = restored = 0
        for key, default in TEXT_DEFAULTS.items():
            if key not in request.form:
                continue
            submitted = (request.form.get(key) or "").strip()
            stored = Setting.get(key)
            if not submitted or submitted == default.strip():
                # Empty, or back to the shipped wording: drop the override.
                if stored is not None:
                    Setting.clear(key)
                    restored += 1
            elif submitted != (stored or ""):
                Setting.put(key, submitted)
                changed += 1

        if changed or restored:
            ActivityLog.record(
                current_user, "content_save",
                f"{changed} edited, {restored} restored to default",
            )
            db.session.commit()
            parts = []
            if changed:
                parts.append(f"{changed} text{'' if changed == 1 else 's'} updated")
            if restored:
                parts.append(f"{restored} restored to the default")
            flash(" and ".join(parts).capitalize() + ".", "success")
        else:
            flash("Nothing changed.", "info")
        return redirect(url_for("admin.content"))

    return render_template("admin/content.html", groups=text_groups())


@admin_bp.route("/content/reset", methods=["POST"])
def reset_content():
    """Put every piece of copy back to the wording the portal ships with."""
    from app.content import TEXT_DEFAULTS

    form = ConfirmForm()
    if form.validate_on_submit():
        cleared = 0
        for key in TEXT_DEFAULTS:
            if Setting.clear(key) is not None:
                cleared += 1
        ActivityLog.record(current_user, "content_reset", f"{cleared} texts")
        db.session.commit()
        flash(
            f"{cleared} text{'' if cleared == 1 else 's'} restored to the default wording."
            if cleared else "Everything was already at the default wording.",
            "info",
        )
    return redirect(url_for("admin.content"))
