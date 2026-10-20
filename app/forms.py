"""WTForms definitions."""
from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField, DateField, DecimalField, EmailField, HiddenField, IntegerField,
    PasswordField, SelectField, StringField, SubmitField, TextAreaField, URLField,
)
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp, URL,
)

from app.models import JOB_TYPES, WORK_MODES, ApplicationStatus, CoordinatorRole, Programme

FIRST_BATCH = 1995
CURRENT_YEAR = date.today().year
YEAR_CHOICES = [(str(y), str(y)) for y in range(CURRENT_YEAR + 1, FIRST_BATCH - 1, -1)]
PROGRAMME_CHOICES = [(p, p) for p in Programme.ALL]


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=160)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")


class RegistrationForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(min=3, max=120)])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=160)])
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, message="Use at least 8 characters.")],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    department = SelectField("Department", choices=[], validators=[Optional()], validate_choice=False)
    programme = SelectField("Programme", choices=PROGRAMME_CHOICES, validators=[DataRequired()], validate_choice=False)
    batch_year = SelectField("Year of joining", choices=YEAR_CHOICES, validators=[DataRequired()])
    graduation_year = SelectField(
        "Year of completion", choices=[("", "— still studying —")] + YEAR_CHOICES,
        validators=[Optional()],
    )
    register_number = StringField("University register number", validators=[Optional(), Length(max=40)])
    is_job_seeker = BooleanField("I am looking for job opportunities")
    is_job_provider = BooleanField("I can offer / refer job opportunities")
    accept_terms = BooleanField(
        "I confirm I am an alumnus/student of the Department of Computer Science, SSC Areekode.",
        validators=[DataRequired(message="Please confirm your association with the department.")],
    )
    submit = SubmitField("Create account")


class ProfileForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(min=3, max=120)])
    department = SelectField("Department", choices=[], validators=[Optional()], validate_choice=False)
    programme = SelectField("Programme", choices=PROGRAMME_CHOICES, validators=[DataRequired()], validate_choice=False)
    batch_year = SelectField("Year of joining", choices=YEAR_CHOICES, validators=[DataRequired()])
    graduation_year = SelectField(
        "Year of completion", choices=[("", "— still studying —")] + YEAR_CHOICES,
        validators=[Optional()],
    )
    register_number = StringField("Register number", validators=[Optional(), Length(max=40)])

    headline = StringField(
        "Headline", validators=[Optional(), Length(max=160)],
        description="e.g. Senior Data Engineer | Python, Spark, AWS",
    )
    about = TextAreaField("About you", validators=[Optional(), Length(max=4000)])
    current_position = StringField("Current designation", validators=[Optional(), Length(max=120)])
    current_company = StringField("Current organisation", validators=[Optional(), Length(max=120)])
    experience_years = DecimalField(
        "Total experience (years)", validators=[Optional(), NumberRange(min=0, max=60)], places=1,
    )
    location = StringField("Location", validators=[Optional(), Length(max=120)])

    phone = StringField("Phone", validators=[Optional(), Length(max=32)])
    show_phone = BooleanField("Show my phone number to other members")
    show_email = BooleanField("Show my email to other members")

    linkedin_url = URLField("LinkedIn URL", validators=[Optional(), URL(), Length(max=255)])
    github_url = URLField("GitHub URL", validators=[Optional(), URL(), Length(max=255)])
    website_url = URLField("Portfolio / website", validators=[Optional(), URL(), Length(max=255)])

    skills = StringField(
        "Skills", validators=[Optional(), Length(max=1000)],
        description="Comma separated, e.g. Python, Django, React, MySQL",
    )

    photo = FileField(
        "Profile photo",
        validators=[FileAllowed(["png", "jpg", "jpeg", "webp"], "Images only (png, jpg, webp).")],
    )
    resume = FileField(
        "Resume / CV",
        validators=[FileAllowed(["pdf", "doc", "docx"], "PDF or Word documents only.")],
    )

    is_job_seeker = BooleanField("I am a job seeker")
    open_to_work = BooleanField("Actively open to work (shows a badge on my card)")
    is_job_provider = BooleanField("I am a job provider / recruiter")
    is_hiring = BooleanField("Currently hiring")
    company_name = StringField("Company name", validators=[Optional(), Length(max=160)])
    company_website = URLField("Company website", validators=[Optional(), URL(), Length(max=255)])
    designation_at_company = StringField("Your role there", validators=[Optional(), Length(max=120)])

    is_visible = BooleanField("List me in the alumni directory")
    submit = SubmitField("Save profile")


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords do not match.")],
    )
    submit = SubmitField("Update password")


class JobForm(FlaskForm):
    title = StringField("Job title", validators=[DataRequired(), Length(max=160)])
    company = StringField("Company", validators=[DataRequired(), Length(max=160)])
    company_website = URLField("Company website", validators=[Optional(), URL(), Length(max=255)])
    location = StringField("Location", validators=[Optional(), Length(max=120)])
    job_type = SelectField("Job type", choices=[(t, t) for t in JOB_TYPES], validators=[DataRequired()])
    work_mode = SelectField("Work mode", choices=[(m, m) for m in WORK_MODES], validators=[DataRequired()])

    description = TextAreaField("Role summary", validators=[DataRequired(), Length(min=30, max=8000)])
    responsibilities = TextAreaField("Key responsibilities", validators=[Optional(), Length(max=8000)])
    requirements = TextAreaField("Requirements / eligibility", validators=[Optional(), Length(max=8000)])

    skills = StringField(
        "Required skills", validators=[Optional(), Length(max=1000)],
        description="Comma separated — helps us match the right alumni.",
    )
    min_experience = DecimalField(
        "Minimum experience (years)", default=0,
        validators=[Optional(), NumberRange(min=0, max=50)], places=1,
    )
    max_experience = DecimalField(
        "Maximum experience (years)", validators=[Optional(), NumberRange(min=0, max=50)], places=1,
    )
    salary_range = StringField("Compensation", validators=[Optional(), Length(max=120)])
    vacancies = IntegerField("Number of openings", default=1, validators=[Optional(), NumberRange(min=1, max=999)])

    accepts_portal_applications = BooleanField("Accept applications through this portal", default=True)
    apply_url = URLField("External application link", validators=[Optional(), URL(), Length(max=255)])
    apply_email = EmailField("Application email", validators=[Optional(), Email(), Length(max=160)])
    deadline = DateField("Last date to apply", validators=[Optional()])
    submit = SubmitField("Submit opportunity")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        ok = True
        if self.max_experience.data is not None and self.min_experience.data is not None:
            if self.max_experience.data < self.min_experience.data:
                self.max_experience.errors.append("Maximum must be greater than minimum.")
                ok = False
        if not self.accepts_portal_applications.data and not (self.apply_url.data or self.apply_email.data):
            self.apply_url.errors.append(
                "Provide an application link or email when portal applications are switched off."
            )
            ok = False
        if self.deadline.data and self.deadline.data < date.today():
            self.deadline.errors.append("The deadline cannot be in the past.")
            ok = False
        return ok


class ApplicationForm(FlaskForm):
    cover_letter = TextAreaField(
        "Message to the employer", validators=[Optional(), Length(max=4000)],
        description="Briefly explain why you are a good fit.",
    )
    resume = FileField(
        "Attach a resume (optional — your profile resume is used otherwise)",
        validators=[FileAllowed(["pdf", "doc", "docx"], "PDF or Word documents only.")],
    )
    submit = SubmitField("Submit application")


class ApplicationStatusForm(FlaskForm):
    status = SelectField(
        "Status", choices=[(s, s.title()) for s in ApplicationStatus.ALL], validators=[DataRequired()],
    )
    employer_note = TextAreaField("Note to candidate", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Update")


class MessageForm(FlaskForm):
    subject = StringField("Subject", validators=[Optional(), Length(max=160)])
    body = TextAreaField("Message", validators=[DataRequired(), Length(min=2, max=4000)])
    submit = SubmitField("Send message")


class DirectoryFilterForm(FlaskForm):
    class Meta:
        csrf = False

    q = StringField("Search", validators=[Optional(), Length(max=120)])
    department = SelectField("Department", choices=[], validators=[Optional()], validate_choice=False)
    programme = SelectField(
        "Programme", choices=[("", "All programmes")] + PROGRAMME_CHOICES,
        validators=[Optional()], validate_choice=False,
    )
    batch_year = SelectField(
        "Year of admission", choices=[("", "All batches")] + YEAR_CHOICES, validators=[Optional()],
    )
    graduation_year = SelectField(
        "Year of completion", choices=[("", "Any year")] + YEAR_CHOICES, validators=[Optional()],
    )
    skill = StringField("Skill", validators=[Optional(), Length(max=60)])
    role = SelectField(
        "Showing",
        choices=[("", "Everyone"), ("seekers", "Job seekers"), ("providers", "Job providers"), ("hiring", "Currently hiring")],
        validators=[Optional()],
    )
    submit = SubmitField("Filter")


class JobFilterForm(FlaskForm):
    class Meta:
        csrf = False

    q = StringField("Search", validators=[Optional(), Length(max=120)])
    job_type = SelectField("Type", choices=[("", "All types")] + [(t, t) for t in JOB_TYPES], validators=[Optional()])
    work_mode = SelectField("Mode", choices=[("", "All modes")] + [(m, m) for m in WORK_MODES], validators=[Optional()])
    location = StringField("Location", validators=[Optional(), Length(max=120)])
    skill = StringField("Skill", validators=[Optional(), Length(max=60)])
    submit = SubmitField("Filter")


# --------------------------------------------------------------------------
# Admin forms
# --------------------------------------------------------------------------
class FacultyForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    designation = StringField("Designation", validators=[Optional(), Length(max=120)])
    qualification = StringField("Qualification", validators=[Optional(), Length(max=160)])
    specialization = StringField("Area of specialisation", validators=[Optional(), Length(max=200)])
    email = EmailField("Email", validators=[Optional(), Email(), Length(max=160)])
    phone = StringField("Phone", validators=[Optional(), Length(max=32)])
    photo = FileField("Photo", validators=[FileAllowed(["png", "jpg", "jpeg", "webp"], "Images only.")])
    profile_url = URLField("Profile link", validators=[Optional(), URL(), Length(max=255)])
    is_current = BooleanField("Currently serving", default=True)
    is_hod = BooleanField("Head of Department")
    served_from = IntegerField("Served from (year)", validators=[Optional(), NumberRange(min=1990, max=2100)])
    served_to = IntegerField("Served to (year)", validators=[Optional(), NumberRange(min=1990, max=2100)])
    sort_order = IntegerField("Display order", default=100, validators=[Optional(), NumberRange(min=0, max=999)])
    submit = SubmitField("Save")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.served_from.data and self.served_to.data and self.served_to.data < self.served_from.data:
            self.served_to.errors.append("End year must be after the start year.")
            return False
        return True


class AnnouncementForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    category = SelectField(
        "Category", choices=[("News", "News"), ("Event", "Event"), ("Notice", "Notice")],
        validators=[DataRequired()],
    )
    body = TextAreaField("Content", validators=[DataRequired(), Length(max=8000)])
    event_date = DateField("Event date", validators=[Optional()])
    is_published = BooleanField("Published", default=True)
    is_pinned = BooleanField("Pin to top")
    submit = SubmitField("Save")


class SitePageForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    body = TextAreaField("Content", validators=[DataRequired(), Length(max=20000)])
    submit = SubmitField("Save page")


class AdminUserForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=160)])
    role = SelectField("Role", choices=[("member", "Member"), ("admin", "Administrator")], validators=[DataRequired()])
    is_approved = BooleanField("Approved")
    is_blocked = BooleanField("Suspended")
    new_password = PasswordField("Reset password to", validators=[Optional(), Length(min=8)])
    submit = SubmitField("Save changes")


class JobModerationForm(FlaskForm):
    rejection_note = StringField("Reason (shown to the poster)", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Submit")


class DepartmentForm(FlaskForm):
    name = StringField("Department name", validators=[DataRequired(), Length(max=120)])
    short_name = StringField("Short code", validators=[Optional(), Length(max=30)],
                             description="e.g. CS, PHY, COM")
    description = TextAreaField("Description", validators=[Optional(), Length(max=4000)])
    programmes = TextAreaField(
        "Programmes offered", validators=[Optional(), Length(max=2000)],
        description="One programme per line — these become the choices on registration.",
    )
    email = EmailField("Department email", validators=[Optional(), Email(), Length(max=160)])
    website = URLField("Department page", validators=[Optional(), URL(), Length(max=255)])
    is_active = BooleanField("Active — alumni of this department may register")
    sort_order = IntegerField("Display order", default=100, validators=[Optional(), NumberRange(min=0, max=999)])
    submit = SubmitField("Save department")


class CoordinatorForm(FlaskForm):
    department = SelectField("Department", choices=[], validators=[DataRequired()], validate_choice=False)
    academic_year = StringField(
        "Academic year", validators=[DataRequired(), Regexp(r"^\d{4}-\d{2}$", message="Use the form 2025-26.")],
        description="e.g. 2025-26",
    )
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    role = SelectField("Role", choices=[(r, r) for r in CoordinatorRole.ALL], validators=[DataRequired()])
    designation = StringField("Designation", validators=[Optional(), Length(max=120)],
                              description="e.g. Assistant Professor, M.Sc final year")
    email = EmailField("Email", validators=[Optional(), Email(), Length(max=160)])
    phone = StringField("Phone", validators=[Optional(), Length(max=32)])
    photo = FileField("Photo", validators=[FileAllowed(["png", "jpg", "jpeg", "webp"], "Images only.")])
    notes = TextAreaField("Responsibilities", validators=[Optional(), Length(max=2000)])
    is_active = BooleanField("Currently serving", default=True)
    sort_order = IntegerField("Display order", default=100, validators=[Optional(), NumberRange(min=0, max=999)])
    submit = SubmitField("Save coordinator")


class FeatureToggleForm(FlaskForm):
    """The college-wide switch on the admin departments page."""
    enabled = BooleanField("Open the portal to every department of the college")
    submit = SubmitField("Save setting")


class ConfirmForm(FlaskForm):
    """Bare CSRF-protected form for destructive POST actions."""
    confirm_id = HiddenField()
    submit = SubmitField("Confirm")
