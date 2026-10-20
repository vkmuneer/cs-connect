"""Public pages: home, about college/department, faculty, announcements."""
from sqlalchemy import func

from flask import Blueprint, abort, render_template, request

from app.extensions import db
from app.models import (
    Announcement, Application, Coordinator, CoordinatorRole, Department, Faculty,
    Job, JobStatus, Profile, Programme, SitePage, User,
)
from app.utils import multi_department_enabled

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    latest_jobs = (
        Job.query.filter_by(status=JobStatus.APPROVED)
        .order_by(Job.created_at.desc())
        .limit(6)
        .all()
    )
    featured_alumni = (
        Profile.query.join(User)
        .filter(User.is_approved.is_(True), User.is_blocked.is_(False), Profile.is_visible.is_(True))
        .order_by(Profile.updated_at.desc().nullslast())
        .limit(8)
        .all()
    )
    announcements = (
        Announcement.query.filter_by(is_published=True)
        .order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())
        .limit(3)
        .all()
    )

    stats = {
        "alumni": User.query.filter_by(is_approved=True, is_blocked=False).count(),
        "jobs": Job.query.filter_by(status=JobStatus.APPROVED).count(),
        "providers": Profile.query.join(User)
            .filter(Profile.is_job_provider.is_(True), User.is_approved.is_(True)).count(),
        "seekers": Profile.query.join(User)
            .filter(Profile.is_job_seeker.is_(True), User.is_approved.is_(True)).count(),
        "batches": db.session.query(func.count(func.distinct(Profile.batch_year))).scalar() or 0,
        "placements": Application.placement_count(),
    }

    placements = (
        Application.placements_query()
        .order_by(Application.updated_at.desc().nullslast())
        .limit(4)
        .all()
    )

    return render_template(
        "index.html",
        latest_jobs=latest_jobs,
        featured_alumni=featured_alumni,
        announcements=announcements,
        stats=stats,
        placements=placements,
    )


# --------------------------------------------------------------------------
# Placements achieved through this portal
# --------------------------------------------------------------------------
@main_bp.route("/placements")
def placements():
    """Every offer that came out of a posting on this portal."""
    rows = (
        Application.placements_query()
        .order_by(Application.updated_at.desc().nullslast())
        .all()
    )
    stats = Application.placement_stats()

    by_company, by_batch, by_programme = {}, {}, {}
    for row in rows:
        if row.job:
            by_company[row.job.company] = by_company.get(row.job.company, 0) + 1
        profile = row.applicant.profile if row.applicant else None
        if profile:
            by_batch[profile.batch_year] = by_batch.get(profile.batch_year, 0) + 1
            by_programme[profile.programme] = by_programme.get(profile.programme, 0) + 1

    return render_template(
        "pages/placements.html", placements=rows, stats=stats,
        by_company=sorted(by_company.items(), key=lambda kv: -kv[1]),
        by_batch=sorted(by_batch.items(), reverse=True),
        by_programme=sorted(by_programme.items(), key=lambda kv: -kv[1]),
    )


# --------------------------------------------------------------------------
# Coordinators, by department and academic year
# --------------------------------------------------------------------------
@main_bp.route("/coordinators")
def coordinators():
    years = Coordinator.academic_years()
    year = request.args.get("year") or (years[0] if years else Coordinator.current_year_label())
    department_id = request.args.get("department", type=int)

    query = Coordinator.query.filter_by(academic_year=year, is_active=True)
    if department_id:
        query = query.filter_by(department_id=department_id)
    rows = query.order_by(Coordinator.sort_order, Coordinator.name).all()

    grouped = {}
    for row in rows:
        grouped.setdefault(row.department, []).append(row)

    return render_template(
        "pages/coordinators.html",
        grouped=grouped, years=years, year=year,
        current_year=Coordinator.current_year_label(),
        departments=Department.active() if multi_department_enabled() else [],
        department_id=department_id, roles=CoordinatorRole.ALL,
    )


# --------------------------------------------------------------------------
# College-wide view (only once an administrator switches it on)
# --------------------------------------------------------------------------
@main_bp.route("/departments")
def departments():
    if not multi_department_enabled():
        abort(404)
    rows = Department.active()
    return render_template("pages/departments.html", departments=rows)


@main_bp.route("/about/college")
def about_college():
    page = SitePage.get("about-college", "About the College")
    return render_template("pages/about_college.html", page=page)


@main_bp.route("/about/department")
def about_department():
    page = SitePage.get("about-department", "About the Department")
    programme_pages = {
        slug: SitePage.get(slug) for slug in ("programme-bsc", "programme-msc", "programme-phd")
    }
    batch_spread = (
        db.session.query(Profile.batch_year, func.count(Profile.id))
        .join(User)
        .filter(User.is_approved.is_(True))
        .group_by(Profile.batch_year)
        .order_by(Profile.batch_year)
        .all()
    )
    return render_template(
        "pages/about_department.html",
        page=page,
        programme_pages=programme_pages,
        programmes=Programme.ALL,
        batch_spread=batch_spread,
    )


@main_bp.route("/faculty")
def faculty():
    scope = request.args.get("scope", "current")
    if scope not in ("current", "former"):
        scope = "current"
    members = (
        Faculty.query.filter_by(is_current=(scope == "current"))
        .order_by(Faculty.is_hod.desc(), Faculty.sort_order, Faculty.name)
        .all()
    )
    counts = {
        "current": Faculty.query.filter_by(is_current=True).count(),
        "former": Faculty.query.filter_by(is_current=False).count(),
    }
    return render_template("pages/faculty.html", members=members, scope=scope, counts=counts)


@main_bp.route("/announcements")
def announcements():
    page_num = request.args.get("page", 1, type=int)
    pagination = (
        Announcement.query.filter_by(is_published=True)
        .order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())
        .paginate(page=page_num, per_page=10, error_out=False)
    )
    return render_template("pages/announcements.html", pagination=pagination)


@main_bp.route("/announcements/<int:announcement_id>")
def announcement_detail(announcement_id):
    item = db.session.get(Announcement, announcement_id)
    if item is None or not item.is_published:
        abort(404)
    return render_template("pages/announcement_detail.html", item=item)


@main_bp.route("/contact")
def contact():
    page = SitePage.get("contact", "Contact Us")
    return render_template("pages/contact.html", page=page)
