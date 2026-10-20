"""Shared helpers: uploads, permissions, template filters."""
import os
import re
import secrets
from datetime import datetime, timezone
from functools import wraps

from flask import abort, current_app, flash, redirect, url_for
from flask_login import current_user
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename


# --------------------------------------------------------------------------
# Access control decorators
# --------------------------------------------------------------------------
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def approved_required(view):
    """Blocks members whose registration has not been verified by an admin."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.can_participate:
            flash(
                "Your membership is awaiting verification by the department admin. "
                "You will be notified once it is approved.",
                "warning",
            )
            return redirect(url_for("profiles.my_profile"))
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------------------------
# File uploads
# --------------------------------------------------------------------------
def _allowed(filename, allowed_exts):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_exts


def save_upload(file_storage, kind):
    """Persist an uploaded file and return its stored filename, or None.

    `kind` is either "resume" or "photo"; raises ValueError on a bad extension.
    """
    if not file_storage or not file_storage.filename:
        return None

    cfg = current_app.config
    if kind == "resume":
        allowed, folder = cfg["ALLOWED_RESUME_EXTENSIONS"], cfg["RESUME_FOLDER"]
    elif kind == "photo":
        allowed, folder = cfg["ALLOWED_IMAGE_EXTENSIONS"], cfg["PHOTO_FOLDER"]
    else:
        raise ValueError(f"Unknown upload kind: {kind}")

    original = secure_filename(file_storage.filename)
    if not _allowed(original, allowed):
        raise ValueError(f"Allowed file types: {', '.join(sorted(allowed))}")

    ext = original.rsplit(".", 1)[1].lower()
    stem = os.path.splitext(original)[0][:40] or kind
    stored = f"{stem}-{secrets.token_hex(8)}.{ext}"

    folder.mkdir(parents=True, exist_ok=True)
    file_storage.save(folder / stored)

    if kind == "photo":
        _shrink_image(folder / stored)
    return stored


def _shrink_image(path, max_side=600):
    """Downscale profile photos so the repo/uploads folder stays small."""
    try:
        from PIL import Image
    except ImportError:  # Pillow optional at runtime
        return
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            im.save(path, quality=85, optimize=True)
    except Exception:  # a corrupt upload should not break registration
        current_app.logger.warning("Could not post-process image %s", path)


def delete_upload(filename, kind):
    if not filename:
        return
    cfg = current_app.config
    folder = cfg["RESUME_FOLDER"] if kind == "resume" else cfg["PHOTO_FOLDER"]
    try:
        (folder / filename).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("Could not delete upload %s", filename)


# --------------------------------------------------------------------------
# Text helpers / template filters
# --------------------------------------------------------------------------
def parse_skills(raw):
    """Turn a comma/newline separated string into a de-duplicated name list."""
    if not raw:
        return []
    parts = re.split(r"[,\n;]+", raw)
    seen, out = set(), []
    for part in parts:
        name = " ".join(part.split())
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            out.append(name[:60])
    return out[:30]


def nl2br(value):
    if not value:
        return ""
    return Markup("<br>".join(escape(value).split("\n")))


def timeago(value):
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - value
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins} minute{'s' if mins > 1 else ''} ago"
    if seconds < 86400:
        hrs = seconds // 3600
        return f"{hrs} hour{'s' if hrs > 1 else ''} ago"
    days = seconds // 86400
    if days < 30:
        return f"{days} day{'s' if days > 1 else ''} ago"
    if days < 365:
        months = days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years > 1 else ''} ago"


def register_template_helpers(app):
    app.jinja_env.filters["nl2br"] = nl2br
    app.jinja_env.filters["timeago"] = timeago


# --------------------------------------------------------------------------
# Department helpers
# --------------------------------------------------------------------------
def multi_department_enabled():
    """True once an administrator has opened the portal to every department."""
    from app.models import MULTI_DEPARTMENT, Setting

    return Setting.is_on(MULTI_DEPARTMENT)


def selectable_departments():
    """Departments a registering member may choose from."""
    from app.models import Department

    if multi_department_enabled():
        return Department.active()
    primary = Department.primary()
    return [primary] if primary else []


def department_choices(blank_label=None):
    choices = [(str(d.id), d.name) for d in selectable_departments()]
    if blank_label:
        choices = [("", blank_label)] + choices
    return choices


def programme_choices(blank_label=None):
    """Programme choices across every selectable department, de-duplicated."""
    from app.models import Programme

    seen, choices = set(), []
    for dept in selectable_departments():
        for programme in dept.programme_list:
            if programme not in seen:
                seen.add(programme)
                choices.append((programme, programme))
    if not choices:  # database not seeded with departments yet
        choices = [(p, p) for p in Programme.ALL]
    if blank_label:
        choices = [("", blank_label)] + choices
    return choices


def programme_department_map():
    """programme -> department id, used to narrow the programme list in the UI."""
    return {
        programme: dept.id
        for dept in selectable_departments()
        for programme in dept.programme_list
    }


def resolve_department(raw_id):
    """Validate a submitted department id, falling back to the primary one."""
    from app.models import Department

    allowed = {d.id: d for d in selectable_departments() if d}
    try:
        dept = allowed.get(int(raw_id))
    except (TypeError, ValueError):
        dept = None
    return dept or Department.primary()


def prepare_department_fields(form, profile=None):
    """Fill the department/programme choices on a form before rendering."""
    form.department.choices = department_choices()
    form.programme.choices = programme_choices()
    if profile is not None and profile.department_id:
        form.department.data = str(profile.department_id)
    elif not form.department.data:
        choices = form.department.choices
        form.department.data = choices[0][0] if choices else ""
