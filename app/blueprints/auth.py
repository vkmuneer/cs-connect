"""Registration, sign-in and account security."""
from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from urllib.parse import urlparse

from app.extensions import db
from app.forms import LoginForm, PasswordChangeForm, RegistrationForm
from app.models import ActivityLog, Profile, Role, User
from app.utils import (
    prepare_department_fields, programme_department_map, resolve_department,
)

auth_bp = Blueprint("auth", __name__)


def _is_safe_redirect(target):
    """Only allow relative redirects back into this application."""
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.netloc and not parsed.scheme and target.startswith("/")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegistrationForm()
    prepare_department_fields(form)
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists. Try signing in.", "danger")
            return render_template(
                "auth/register.html", form=form, programme_map=programme_department_map(),
            )

        auto_approve = not current_app.config["REQUIRE_ADMIN_APPROVAL"]
        user = User(
            email=email,
            full_name=form.full_name.data.strip(),
            role=Role.MEMBER,
            is_approved=auto_approve,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()

        grad = form.graduation_year.data
        profile = Profile(
            user_id=user.id,
            department=resolve_department(form.department.data),
            programme=form.programme.data,
            batch_year=int(form.batch_year.data),
            graduation_year=int(grad) if grad else None,
            register_number=(form.register_number.data or "").strip() or None,
            is_job_seeker=form.is_job_seeker.data,
            is_job_provider=form.is_job_provider.data,
            open_to_work=form.is_job_seeker.data,
        )
        db.session.add(profile)
        ActivityLog.record(user, "register", f"{user.full_name} <{user.email}> registered")
        db.session.commit()

        login_user(user)
        if auto_approve:
            flash("Welcome to CS Connect! Complete your profile to get discovered.", "success")
        else:
            flash(
                "Account created. An administrator will verify your membership shortly — "
                "meanwhile you can fill in your profile.",
                "info",
            )
        return redirect(url_for("profiles.edit_profile"))

    return render_template(
        "auth/register.html", form=form, programme_map=programme_department_map(),
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", form=form)
        if user.is_blocked:
            flash("This account has been suspended. Please contact the department admin.", "danger")
            return render_template("auth/login.html", form=form)

        login_user(user, remember=form.remember.data)
        user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()

        next_page = request.args.get("next")
        if not _is_safe_redirect(next_page):
            next_page = url_for("admin.dashboard") if user.is_admin else url_for("main.index")
        flash(f"Welcome back, {user.full_name.split()[0]}!", "success")
        return redirect(next_page)

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = PasswordChangeForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Your current password is incorrect.", "danger")
            return render_template("auth/change_password.html", form=form)
        current_user.set_password(form.new_password.data)
        ActivityLog.record(current_user, "password_change", current_user.email)
        db.session.commit()
        flash("Password updated.", "success")
        return redirect(url_for("profiles.my_profile"))
    return render_template("auth/change_password.html", form=form)
