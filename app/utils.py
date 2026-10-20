"""Shared helpers: uploads, permissions, template filters."""
import os
import re
import secrets
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, flash, redirect, url_for
from flask_login import current_user
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename


# --------------------------------------------------------------------------
# One clock for the whole portal
# --------------------------------------------------------------------------
def portal_timezone():
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    name = "Asia/Kolkata"
    try:
        from flask import current_app

        name = current_app.config.get("PORTAL_TIMEZONE") or name
    except Exception:  # outside an application context
        pass
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return timezone.utc


def portal_today():
    """Today's date where the college is, so a deadline means a local day."""
    return datetime.now(portal_timezone()).date()


def portal_year():
    return portal_today().year


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
# Safe links
# --------------------------------------------------------------------------
SAFE_URL_SCHEMES = ("http", "https")


class SafeURL:
    """URL validator that also pins the scheme to http/https.

    WTForms' own URL validator accepts anything scheme-like, so a stored
    `javascript:` or `data:` URL would end up in an href on a profile page.
    """

    def __init__(self, message=None):
        self.message = message or "Enter a full http:// or https:// address."

    def __call__(self, form, field):
        from wtforms.validators import StopValidation

        raw = (field.data or "").strip()
        if not raw:
            return
        scheme = urlparse(raw).scheme.lower()
        if scheme not in SAFE_URL_SCHEMES:
            field.data = ""
            raise StopValidation(self.message)


def safe_external_url(raw):
    """Return the URL only if it is safe to put in an href, else None.

    A second line of defence for links already in the database.
    """
    if not raw:
        return None
    candidate = str(raw).strip()
    if urlparse(candidate).scheme.lower() in SAFE_URL_SCHEMES:
        return candidate
    return None


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
    if kind == "photo":
        _require_real_image(file_storage)

    ext = original.rsplit(".", 1)[1].lower()
    stem = os.path.splitext(original)[0][:40] or kind
    stored = f"{stem}-{secrets.token_hex(8)}.{ext}"

    folder.mkdir(parents=True, exist_ok=True)
    file_storage.save(folder / stored)

    if kind == "photo":
        # Re-encoding also drops EXIF, including any GPS co-ordinates.
        _shrink_image(folder / stored)
    return stored


def _require_real_image(file_storage):
    """Reject a file that merely claims to be an image by its extension."""
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:  # Pillow optional at runtime
        return
    try:
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as im:
            im.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise ValueError("That file is not a readable image.")
    finally:
        file_storage.stream.seek(0)


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
    """Turn a comma/newline separated string into a de-duplicated name list.

    `raw` is normally the text from the form. It can also arrive as the
    profile's own skill collection when the field is missing from a submitted
    form, in which case WTForms leaves the object value in place.
    """
    if not raw:
        return []
    if not isinstance(raw, str):
        try:
            raw = ", ".join(getattr(item, "name", str(item)) for item in raw)
        except TypeError:
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
    app.jinja_env.filters["safe_url"] = lambda raw: safe_external_url(raw) or ""


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


# --------------------------------------------------------------------------
# Batch years (years of admission)
# --------------------------------------------------------------------------
DEFAULT_FIRST_BATCH_YEAR = 1995
DEFAULT_FUTURE_YEARS = 1
MAX_FUTURE_YEARS = 10


def batch_year_bounds():
    """(first, last) year of admission offered, from the admin settings.

    Falls back to the configured defaults when the settings table is not
    readable yet (fresh database, CLI before `flask seed`).
    """
    from flask import current_app

    from app.models import FIRST_BATCH_YEAR, FUTURE_YEARS, Setting

    first = current_app.config.get("FIRST_BATCH_YEAR", DEFAULT_FIRST_BATCH_YEAR)
    future = DEFAULT_FUTURE_YEARS
    try:
        stored_first = Setting.get(FIRST_BATCH_YEAR)
        stored_future = Setting.get(FUTURE_YEARS)
        if stored_first:
            first = int(stored_first)
        if stored_future is not None:
            future = int(stored_future)
    except Exception:  # no database yet — the defaults stand
        pass

    first = max(1900, min(int(first), portal_year()))
    future = max(0, min(int(future), MAX_FUTURE_YEARS))
    # Recomputed on every call, so a server running across New Year stays current.
    return first, portal_year() + future


def batch_years(newest_first=True):
    first, last = batch_year_bounds()
    years = list(range(first, last + 1))
    return list(reversed(years)) if newest_first else years


def batch_year_choices(blank_label=None):
    choices = [(str(y), str(y)) for y in batch_years()]
    if blank_label:
        choices = [("", blank_label)] + choices
    return choices


# --------------------------------------------------------------------------
# Password policy
# --------------------------------------------------------------------------
COMMON_PASSWORDS = {
    "password", "password1", "password123", "passw0rd", "12345678", "123456789",
    "1234567890", "qwerty123", "qwertyui", "iloveyou", "admin123", "administrator",
    "letmein", "welcome1", "welcome123", "monkey123", "dragon123", "football",
    "baseball", "sunshine", "princess", "abc12345", "abcd1234", "a1b2c3d4",
    "changeme", "change-me", "secret12", "trustno1", "starwars", "whatever",
    "qazwsxedc", "asdfghjkl", "zxcvbnm1", "college123", "student123", "alumni123",
    "cs connect", "csconnect", "csconnect123",
}


class StrongPassword:
    """Rejects the passwords that get guessed first.

    Deliberately light: length is the main defence, and anything stricter tends
    to push people towards writing passwords down.
    """

    def __init__(self, email_field=None):
        self.email_field = email_field

    def __call__(self, form, field):
        from wtforms.validators import ValidationError

        password = field.data or ""
        folded = password.strip().lower()

        if folded in COMMON_PASSWORDS:
            raise ValidationError("That password is too common. Please choose another.")
        if password.isdigit():
            raise ValidationError("Use more than digits alone.")
        if len(set(folded)) < 4:
            raise ValidationError("That password repeats too few characters.")

        email = None
        if self.email_field and hasattr(form, self.email_field):
            email = (getattr(form, self.email_field).data or "").lower()
        elif getattr(form, "_current_email", None):
            email = form._current_email.lower()
        if email:
            local = email.split("@")[0]
            if local and len(local) > 2 and local in folded:
                raise ValidationError("Do not use your email address in your password.")


# --------------------------------------------------------------------------
# Login throttling
# --------------------------------------------------------------------------
_LOGIN_ATTEMPTS = {}
LOGIN_MAX_ATTEMPTS = 8
LOGIN_WINDOW_SECONDS = 300
LOGIN_PRUNE_AT = 2048


def _attempt_key(email):
    from flask import request

    return (request.remote_addr or "?", (email or "").strip().lower())


def login_attempts_exhausted(email):
    """True when this address/email pair has failed too often, too recently.

    In-process and therefore per-worker: enough to blunt password guessing on
    a single-process deployment. Put a rate limiter in the proxy for more.
    """
    now = datetime.now(timezone.utc).timestamp()
    attempts = [
        t for t in _LOGIN_ATTEMPTS.get(_attempt_key(email), [])
        if now - t < LOGIN_WINDOW_SECONDS
    ]
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def record_failed_login(email):
    now = datetime.now(timezone.utc).timestamp()
    key = _attempt_key(email)
    attempts = [t for t in _LOGIN_ATTEMPTS.get(key, []) if now - t < LOGIN_WINDOW_SECONDS]
    attempts.append(now)
    _LOGIN_ATTEMPTS[key] = attempts

    if len(_LOGIN_ATTEMPTS) > LOGIN_PRUNE_AT:  # keep the dict from growing forever
        for stale, times in list(_LOGIN_ATTEMPTS.items()):
            if not any(now - t < LOGIN_WINDOW_SECONDS for t in times):
                _LOGIN_ATTEMPTS.pop(stale, None)


def clear_login_attempts(email):
    _LOGIN_ATTEMPTS.pop(_attempt_key(email), None)


def reset_login_throttle():
    """Test helper."""
    _LOGIN_ATTEMPTS.clear()
