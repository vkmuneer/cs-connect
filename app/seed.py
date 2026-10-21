"""Initial content and demo data for CS Connect."""
import secrets
import string
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from app.extensions import db
from app.models import (
    FIRST_BATCH_YEAR, FUTURE_YEARS, MULTI_DEPARTMENT, Announcement, Application,
    ApplicationStatus, Coordinator, GalleryAlbum, Internship, InternshipStatus,
    TalkSession, TalkStatus,
    CoordinatorRole, Department, Faculty, Job, JobStatus, Message, Profile,
    Programme, Role, Setting, SitePage, Skill, User,
)

# The department that owns the portal today, plus every other department of
# the college — shipped inactive, ready for an administrator to switch on.
DEPARTMENTS = [
    dict(name="Computer Science", short_name="CS", is_primary=True, is_active=True,
         sort_order=1, email="cs@sscollege.ac.in",
         description="Undergraduate, postgraduate and research programmes in computing.",
         programmes="B.Sc Computer Science\nM.Sc Computer Science\nPh.D Computer Science"),
    dict(name="English", short_name="ENG", sort_order=10,
         description="Language, literature and communication studies.",
         programmes="B.A English\nM.A English"),
    dict(name="Physics", short_name="PHY", sort_order=11,
         description="Undergraduate and postgraduate study in physics.",
         programmes="B.Sc Physics\nM.Sc Physics"),
    dict(name="Mathematics", short_name="MAT", sort_order=12,
         description="Pure and applied mathematics.",
         programmes="B.Sc Mathematics\nM.Sc Mathematics"),
    dict(name="Commerce", short_name="COM", sort_order=13,
         description="Commerce, accounting and management studies.",
         programmes="B.Com\nM.Com"),
    dict(name="Communication Media and History", short_name="CMH", sort_order=14,
         description="Communicative media, journalism and historical studies.",
         programmes="B.A Communicative Media\nB.A History\nM.A History"),
    dict(name="Economics", short_name="ECO", sort_order=15,
         description="Economic theory, development and policy.",
         programmes="B.A Economics\nM.A Economics"),
]

# Coordinator appointments are real administrative roles, so none are invented
# here. An administrator fills these in under Admin -> Coordinators and
# Admin -> Batch coordinators.
COORDINATORS = []


PAGES = {
    "about-college": (
        "About Sullamussalam Science College",
        "Sullamussalam Science College, Areekode is an aided arts and science college "
        "affiliated to the University of Calicut, established by the Sullamussalam "
        "Oriental Higher Secondary School Committee.\n\n"
        "Set on the banks of the Chaliyar in Malappuram district, the campus has grown "
        "into one of the leading higher-education centres of the Eranad region, offering "
        "undergraduate, postgraduate and research programmes across the sciences, "
        "humanities and commerce.\n\n"
        "The college is re-accredited by NAAC and is known for a culture of academic "
        "discipline, community service and an unusually active alumni fraternity."
    ),
    "about-department": (
        "About the Department of Computer Science",
        "The Department of Computer Science began with the B.Sc Computer Science "
        "programme and has since grown to offer postgraduate and research study, "
        "supported by well-equipped laboratories and a dedicated faculty.\n\n"
        "Teaching combines a strong foundation in computing fundamentals — data "
        "structures, operating systems, databases, networks — with contemporary "
        "practice in software engineering, web and mobile development, data science "
        "and machine learning.\n\n"
        "Beyond the syllabus, the department runs coding clubs, hackathons, internships "
        "and an industry-interaction cell. CS Connect is the department's own alumni "
        "network: a place where our graduates find each other, mentor current students "
        "and share the opportunities they come across."
    ),
    "programme-bsc": (
        "B.Sc Computer Science",
        "A six-semester undergraduate programme under the University of Calicut "
        "covering programming, data structures, DBMS, operating systems, computer "
        "networks, web technologies and a final-semester project."
    ),
    "programme-msc": (
        "M.Sc Computer Science",
        "A four-semester postgraduate programme with advanced study in algorithms, "
        "distributed systems, machine learning and research methodology, concluding "
        "with a dissertation."
    ),
    "programme-phd": (
        "Ph.D Computer Science",
        "Doctoral research guided by departmental supervisors, with current interests "
        "in machine learning, image processing, natural language processing and "
        "network security."
    ),
    "contact": (
        "Contact Us",
        "Department of Computer Science\n"
        "Sullamussalam Science College\n"
        "Areekode, Malappuram District, Kerala 673639\n\n"
        "Phone: +91 483 285 3363\n"
        "Email: cs@sscollege.ac.in\n\n"
        "Office hours: Monday to Friday, 9:30 am to 4:30 pm."
    ),
}

# Faculty of the P.G & Research Department of Computer Science, taken from the
# college website (sscollege.ac.in/department/1/faculty and the staff-details
# pages) in October 2026. Qualifications are condensed from the prose there.
FACULTY = [
    dict(name="Dr. Shameem Kappan", designation="Head of Department & Associate Professor",
         qualification="Ph.D (Computer Science) 2020, M.Phil 2010, MCA 1999",
         specialization="Network Security",
         email="shameemk@gmail.com", is_hod=True, served_from=2000, sort_order=1,
         profile_url="https://sscollege.ac.in/staff-details/2"),
    dict(name="Dr. Mohamed Basheer K P", designation="Associate Professor (lien period)",
         qualification="Ph.D and M.Phil (Computer Science), Bharathidasan University",
         specialization="Artificial Intelligence, Biometric Security Systems",
         email="mbasheerkp@gmail.com", phone="+91 96339 13396",
         served_from=2001, sort_order=2,
         profile_url="https://sscollege.ac.in/staff-details/3"),
    dict(name="Swapna Mol George", designation="Assistant Professor",
         qualification="M.Sc Computer Science (First Rank, University of Calicut) 2007, "
                       "UGC-NET with JRF 2010, Ph.D pursuing",
         specialization="Machine Learning, Speech Processing",
         email="swapna@sscollege.ac.in", served_from=2011, sort_order=3,
         profile_url="https://sscollege.ac.in/staff-details/7"),
    dict(name="Dr. Muneer V K", designation="Assistant Professor",
         qualification="Ph.D (Computer Science, University of Calicut) 2024, MCA 2008, "
                       "UGC-NET 2012",
         specialization="Artificial Intelligence, Machine Learning, Programming Languages",
         email="vkmuneer@sscollege.ac.in", phone="+91 97447 94110",
         served_from=2012, sort_order=4,
         profile_url="https://sscollege.ac.in/staff-details/1"),
    dict(name="Rababa Kareem K", designation="Assistant Professor",
         qualification="M.Sc Computer Science (MG University, Kottayam) 2002, UGC-NET",
         specialization="Computer Science",
         email="rababa@sscollege.ac.in", phone="+91 94005 54199",
         served_from=2012, sort_order=5,
         profile_url="https://sscollege.ac.in/staff-details/6"),
    dict(name="Ayyoob M P", designation="Assistant Professor",
         qualification="MCA (University of Calicut) 2009",
         specialization="Computer Vision",
         email="mpayyoobmp@gmail.com", served_from=2012, sort_order=6,
         profile_url="https://sscollege.ac.in/staff-details/4"),
    dict(name="Dr. Rizwana Kallooravi Thandil", designation="Assistant Professor",
         qualification="Ph.D (University of Calicut) 2024, MCA 2009, "
                       "B.Sc Computer Science 2004, UGC-NET",
         specialization="Computational Intelligence, Speech Processing",
         email="ktrizwana@sscollege.ac.in", served_from=2012, sort_order=7,
         profile_url="https://sscollege.ac.in/staff-details/5"),
    dict(name="Jashira P", designation="Assistant Professor (on contract)",
         qualification="M.Sc Computer Science 2018, UGC-NET 2018",
         email="jashirap@gmail.com", served_from=2024, sort_order=8,
         profile_url="https://sscollege.ac.in/staff-details/70"),
    dict(name="Insaf P", designation="Guest Faculty",
         qualification="MCA (APJ Abdul Kalam Technological University) 2020, UGC-NET 2019",
         email="insaf@sscollege.ac.in", phone="+91 82811 72366",
         served_from=2022, sort_order=9,
         profile_url="https://sscollege.ac.in/staff-details/8"),
]

ANNOUNCEMENTS = [
    dict(title="Alumni Meet 2026 — save the date",
         category="Event",
         body="The annual gathering of the Department of Computer Science alumni will be "
              "held on the college campus. The day includes a department address, a "
              "placement-and-higher-studies panel for final-year students, and the "
              "customary lunch by the Chaliyar.\n\n"
              "Registration opens on the portal next month. Alumni travelling from "
              "outside Kerala are requested to confirm early so accommodation can be "
              "arranged.",
         event_date=date.today() + timedelta(days=45), is_pinned=True),
    dict(title="Mentorship drive: adopt a final-year project",
         category="News",
         body="We are pairing final-year B.Sc and M.Sc project teams with alumni "
              "mentors working in the industry. A mentor commits to roughly two hours a "
              "month — a code review, a design discussion, or simply a reality check on "
              "scope.\n\n"
              "If you would like to mentor a team, mark yourself as available on your "
              "profile and the department will get in touch."),
    dict(title="Campus recruitment: register your company",
         category="Notice",
         body="Alumni who hire for their organisations can list openings directly on the "
              "CS Connect job board. Postings are reviewed by the department before they "
              "go live, and applications reach you with the candidate's resume attached.\n\n"
              "For on-campus drives, write to the placement cell at cs@sscollege.ac.in."),
]

DEMO_MEMBERS = [
    dict(email="nasrin.cs@example.com", name="Nasrin Fathima", programme=Programme.MSC,
         batch=2016, grad=2018, headline="Senior Software Engineer | Python, Django, AWS",
         position="Senior Software Engineer", company="Zoho Corporation",
         location="Chennai, Tamil Nadu", experience=7,
         skills=["Python", "Django", "PostgreSQL", "AWS", "Docker"],
         seeker=False, provider=True, hiring=True, open_to_work=False,
         company_name="Zoho Corporation", designation="Senior Software Engineer",
         about="M.Sc from the department, now building billing systems at Zoho. "
               "Happy to review resumes for backend roles and to talk to anyone "
               "preparing for product-company interviews."),
    dict(email="rahul.dev@example.com", name="Rahul Krishnan", programme=Programme.BSC,
         batch=2019, grad=2022, headline="Frontend Developer | React, TypeScript",
         position="Frontend Developer", company="Infosys",
         location="Bengaluru, Karnataka", experience=3,
         skills=["JavaScript", "React", "TypeScript", "CSS", "Figma"],
         seeker=True, provider=False, hiring=False, open_to_work=True,
         about="Three years on design systems and dashboards. Looking for a product "
               "team where frontend is taken seriously."),
    dict(email="ayisha.data@example.com", name="Ayisha Sulthana", programme=Programme.MSC,
         batch=2018, grad=2020, headline="Data Scientist | ML, NLP",
         position="Data Scientist", company="Tata Consultancy Services",
         location="Kochi, Kerala", experience=5,
         skills=["Python", "Machine Learning", "NLP", "Pandas", "SQL"],
         seeker=False, provider=True, hiring=True, open_to_work=False,
         company_name="Tata Consultancy Services", designation="Data Scientist",
         about="Working on document-understanding models. Our Kochi team hires "
               "freshers every cycle — ping me before you apply."),
    dict(email="sufiyan.qa@example.com", name="Sufiyan Ahmed", programme=Programme.BSC,
         batch=2020, grad=2023, headline="QA Engineer | Selenium, API testing",
         position="QA Engineer", company="UST Global",
         location="Thiruvananthapuram, Kerala", experience=2,
         skills=["Selenium", "Java", "API Testing", "Jenkins"],
         seeker=True, provider=False, hiring=False, open_to_work=True,
         about="Automation-first tester. Interested in moving towards SDET work."),
    dict(email="hiba.flutter@example.com", name="Hiba Mariyam", programme=Programme.BSC,
         batch=2021, grad=2024, headline="Flutter Developer | Mobile apps",
         position="Mobile Developer", company="Freelance",
         location="Kozhikode, Kerala", experience=1.5,
         skills=["Flutter", "Dart", "Firebase", "REST API"],
         seeker=True, provider=False, hiring=False, open_to_work=True,
         about="Shipped four apps on the Play Store, two of them for local businesses "
               "in Areekode. Open to full-time mobile roles."),
    dict(email="jaleel.cloud@example.com", name="Jaleel Rahman", programme=Programme.BSC,
         batch=2012, grad=2015, headline="DevOps Lead | Kubernetes, Terraform",
         position="DevOps Lead", company="Gadgeon Systems",
         location="Kochi, Kerala", experience=10,
         skills=["Kubernetes", "Terraform", "AWS", "Linux", "CI/CD"],
         seeker=False, provider=True, hiring=True, open_to_work=False,
         company_name="Gadgeon Systems", designation="DevOps Lead",
         about="From the 2012 batch. I run platform engineering at Gadgeon and refer "
               "candidates from the department whenever a req opens."),
    dict(email="safa.student@example.com", name="Safa Jabin", programme=Programme.MSC,
         batch=2024, grad=None, headline="M.Sc final year | Looking for internships",
         position="Student", company="SSC Areekode",
         location="Areekode, Kerala", experience=0,
         skills=["Python", "Machine Learning", "Streamlit", "SQL"],
         seeker=True, provider=False, hiring=False, open_to_work=True,
         about="Final-year M.Sc student working on a dissertation in medical image "
               "classification. Seeking a six-month internship."),
]

DEMO_JOBS = [
    dict(poster="nasrin.cs@example.com", title="Backend Engineer (Python)",
         company="Zoho Corporation", location="Chennai, Tamil Nadu",
         job_type="Full-time", work_mode="Hybrid",
         description="We are expanding the billing platform team and looking for "
                     "engineers who enjoy working on systems that handle real money, "
                     "real scale and real deadlines. You will own services end to end, "
                     "from schema design to on-call.",
         responsibilities="Design and build REST APIs in Python/Django.\n"
                          "Model billing data and write migrations that survive scale.\n"
                          "Review code and mentor two junior engineers.\n"
                          "Share the team's on-call rotation.",
         requirements="2+ years with Python and a relational database.\n"
                      "Comfortable with Git, Docker and Linux.\n"
                      "B.Sc/M.Sc in Computer Science or equivalent experience.",
         skills=["Python", "Django", "PostgreSQL", "Docker"],
         min_exp=2, max_exp=6, salary="₹9,00,000 – ₹16,00,000 per year", vacancies=3,
         status=JobStatus.APPROVED, days_ahead=30),
    dict(poster="ayisha.data@example.com", title="Data Science Intern",
         company="Tata Consultancy Services", location="Kochi, Kerala",
         job_type="Internship", work_mode="On-site",
         description="A six-month paid internship with the applied-AI group in Kochi. "
                     "Interns work alongside a mentor on a live document-understanding "
                     "problem and present their work to the practice at the end of the term.",
         responsibilities="Prepare and label datasets.\n"
                          "Run and document model experiments.\n"
                          "Build a small Streamlit demo of the final model.",
         requirements="Final-year B.Sc/M.Sc student.\n"
                      "Python, pandas and a first course in machine learning.\n"
                      "Available full-time for six months.",
         skills=["Python", "Machine Learning", "Pandas", "NLP"],
         min_exp=0, max_exp=1, salary="₹25,000 per month stipend", vacancies=4,
         status=JobStatus.APPROVED, days_ahead=20),
    dict(poster="jaleel.cloud@example.com", title="DevOps Engineer",
         company="Gadgeon Systems", location="Kochi, Kerala",
         job_type="Full-time", work_mode="On-site",
         description="Join the platform team that keeps roughly forty microservices "
                     "running for our IoT customers. You will spend your time in "
                     "Kubernetes, Terraform and a good deal of Bash.",
         responsibilities="Maintain and extend EKS clusters.\n"
                          "Own Terraform modules for new environments.\n"
                          "Improve CI pipelines and cut build times.",
         requirements="3+ years in DevOps or SRE work.\n"
                      "Hands-on Kubernetes and at least one IaC tool.\n"
                      "Strong Linux fundamentals.",
         skills=["Kubernetes", "Terraform", "AWS", "CI/CD", "Linux"],
         min_exp=3, max_exp=8, salary="₹12,00,000 – ₹20,00,000 per year", vacancies=2,
         status=JobStatus.APPROVED, days_ahead=40),
    dict(poster="jaleel.cloud@example.com", title="Junior Flutter Developer",
         company="Gadgeon Systems", location="Kochi, Kerala",
         job_type="Full-time", work_mode="Hybrid",
         description="A fresher-friendly mobile role for someone who has already "
                     "shipped something to a store. You will work on the companion app "
                     "for an industrial monitoring product.",
         responsibilities="Build screens against a documented REST API.\n"
                          "Write widget tests.\n"
                          "Work with the designer on a shared component library.",
         requirements="Flutter and Dart, demonstrated through a published app or a "
                      "public repository.\nUnderstanding of REST and JSON.",
         skills=["Flutter", "Dart", "Firebase", "REST API"],
         min_exp=0, max_exp=2, salary="₹4,20,000 – ₹6,00,000 per year", vacancies=1,
         status=JobStatus.APPROVED, days_ahead=25),
    dict(poster="nasrin.cs@example.com", title="Technical Support Associate",
         company="Zoho Corporation", location="Remote (India)",
         job_type="Part-time", work_mode="Remote",
         description="Part-time support role suited to final-year students and recent "
                     "graduates. You will answer product questions over email and chat "
                     "and escalate real bugs with a clean reproduction.",
         responsibilities="Handle the first-response queue.\n"
                          "Write reproduction steps for engineering.\n"
                          "Keep the help-centre articles current.",
         requirements="Clear written English.\nBasic SQL is a plus.",
         skills=["Communication", "SQL", "Customer Support"],
         min_exp=0, max_exp=None, salary="₹18,000 per month", vacancies=5,
         status=JobStatus.PENDING, days_ahead=15),
]


def generate_password(length=16):
    """A readable random password, used when none is configured."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def seed_database(include_demo=True):
    """Seed the database. Returns any credentials that had to be generated.

    Passwords are never hard-coded: set ADMIN_PASSWORD (and DEMO_PASSWORD for
    the sample accounts) in the environment, or one is generated here and
    handed back so the caller can print it exactly once.
    """
    generated = {}

    _seed_settings()
    _seed_departments()
    _seed_pages()
    _seed_faculty()
    admin, admin_password = _seed_admin()
    if admin_password:
        generated["admin"] = (admin.email, admin_password)
    _seed_announcements(admin)
    _seed_coordinators()
    if include_demo:
        demo_password = _seed_members_and_jobs()
        if demo_password:
            generated["demo"] = ("the sample alumni accounts", demo_password)
    _backfill_departments()
    db.session.commit()
    return generated


def _seed_settings():
    """College-wide mode ships switched off; an admin turns it on."""
    if Setting.get(MULTI_DEPARTMENT) is None:
        Setting.put(MULTI_DEPARTMENT, False)
    if Setting.get(FIRST_BATCH_YEAR) is None:
        Setting.put(FIRST_BATCH_YEAR, current_app.config.get("FIRST_BATCH_YEAR", 1995))
    if Setting.get(FUTURE_YEARS) is None:
        Setting.put(FUTURE_YEARS, 1)
    db.session.flush()


def _seed_departments():
    for row in DEPARTMENTS:
        dept = Department.query.filter_by(slug=Department.slugify(row["name"])).first()
        if dept is None:
            db.session.add(Department(slug=Department.slugify(row["name"]), **row))
    db.session.flush()


def _seed_coordinators():
    if Coordinator.query.count():
        return
    cs = Department.primary()
    if cs is None:
        return
    current = Coordinator.current_year_label()
    start = int(current.split("-")[0])
    previous = f"{start - 1}-{str(start)[2:]}"
    for row in COORDINATORS:
        row = dict(row)
        year = current if row.pop("year") == "current" else previous
        db.session.add(Coordinator(department_id=cs.id, academic_year=year, **row))
    db.session.flush()


def _backfill_departments():
    """Existing members belong to the department that owns the portal."""
    cs = Department.primary()
    if cs is None:
        return
    Profile.query.filter(Profile.department_id.is_(None)).update(
        {"department_id": cs.id}, synchronize_session=False
    )
    db.session.flush()


def _seed_pages():
    for slug, (title, body) in PAGES.items():
        page = SitePage.query.filter_by(slug=slug).first()
        if page is None:
            db.session.add(SitePage(slug=slug, title=title, body=body))
    db.session.flush()


def _seed_faculty():
    if Faculty.query.count():
        return
    for row in FACULTY:
        db.session.add(Faculty(**row))
    db.session.flush()


def _seed_admin():
    """Create the bootstrap administrator. Returns (user, generated_password)."""
    email = current_app.config["ADMIN_EMAIL"].lower()
    admin = User.query.filter_by(email=email).first()
    generated = None
    if admin is None:
        password = current_app.config.get("ADMIN_PASSWORD")
        if not password:
            password = generated = generate_password()
        admin = User(
            email=email, full_name="Department Administrator",
            role=Role.ADMIN, is_approved=True,
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.flush()
        db.session.add(Profile(
            user_id=admin.id, programme=Programme.MSC,
            batch_year=current_app.config["FIRST_BATCH_YEAR"],
            headline="Department of Computer Science",
            is_visible=False,
        ))
        db.session.flush()
    return admin, generated


def _seed_announcements(admin):
    if Announcement.query.count():
        return
    for row in ANNOUNCEMENTS:
        db.session.add(Announcement(author_id=admin.id, **row))
    db.session.flush()


def _seed_members_and_jobs():
    """Create the sample alumni and jobs. Returns a generated password, if any."""
    if User.query.filter(User.role == Role.MEMBER).count():
        return None

    admin_row = User.query.filter_by(role=Role.ADMIN).first()
    admin_id = admin_row.id if admin_row else None

    demo_password = current_app.config.get("DEMO_PASSWORD")
    generated = None
    if not demo_password:
        demo_password = generated = generate_password()

    users = {}
    for row in DEMO_MEMBERS:
        user = User(
            email=row["email"], full_name=row["name"],
            role=Role.MEMBER, is_approved=True,
        )
        user.set_password(demo_password)
        db.session.add(user)
        db.session.flush()

        profile = Profile(
            user_id=user.id, programme=row["programme"], batch_year=row["batch"],
            graduation_year=row["grad"], headline=row["headline"], about=row["about"],
            current_position=row["position"], current_company=row["company"],
            location=row["location"], experience_years=row["experience"],
            is_job_seeker=row["seeker"], is_job_provider=row["provider"],
            is_hiring=row["hiring"], open_to_work=row["open_to_work"],
            company_name=row.get("company_name"),
            designation_at_company=row.get("designation"),
            show_email=True, is_visible=True,
        )
        profile.skills = [Skill.get_or_create(name) for name in row["skills"]]
        db.session.add(profile)
        users[row["email"]] = user
    db.session.flush()

    # One member still awaiting verification, so the admin queue is not empty.
    pending = User(
        email="unverified.alum@example.com", full_name="Abdul Basith",
        role=Role.MEMBER, is_approved=False,
    )
    pending.set_password(demo_password)
    db.session.add(pending)
    db.session.flush()
    db.session.add(Profile(
        user_id=pending.id, programme=Programme.BSC, batch_year=2017,
        graduation_year=2020, headline="Systems Administrator",
        location="Dubai, UAE", is_job_seeker=True, open_to_work=True,
    ))

    jobs = {}
    for row in DEMO_JOBS:
        poster = users[row["poster"]]
        job = Job(
            posted_by_id=poster.id, title=row["title"], company=row["company"],
            location=row["location"], job_type=row["job_type"], work_mode=row["work_mode"],
            description=row["description"], responsibilities=row["responsibilities"],
            requirements=row["requirements"], min_experience=row["min_exp"],
            max_experience=row["max_exp"], salary_range=row["salary"],
            vacancies=row["vacancies"], status=row["status"],
            deadline=date.today() + timedelta(days=row["days_ahead"]),
            view_count=0,
        )
        job.skills = [Skill.get_or_create(name) for name in row["skills"]]
        db.session.add(job)
        db.session.flush()
        jobs[row["title"]] = job

    # A couple of applications and a message, so dashboards have content.
    db.session.add(Application(
        job_id=jobs["Data Science Intern"].id,
        applicant_id=users["safa.student@example.com"].id,
        cover_letter="I am in the final semester of M.Sc Computer Science at the "
                     "department and my dissertation is on medical image "
                     "classification. I would value six months with your applied-AI "
                     "group and can join full-time from next month.",
        status=ApplicationStatus.SHORTLISTED,
    ))
    # Two alumni put forward by the department, to show the facility in use.
    for email, title, note, order in [
        ("nasrin.cs@example.com", "Distinguished Alumna 2026",
         "M.Sc 2018. Senior engineer on Zoho's billing platform, and the first "
         "person from the department to mentor three successive final-year "
         "project teams. Reviews resumes for every junior who asks.", 1),
        ("jaleel.cloud@example.com", "Industry Leader",
         "B.Sc 2015. Runs platform engineering at Gadgeon and has referred eleven "
         "graduates of the department into the company since 2019.", 2),
    ]:
        profile = users[email].profile
        profile.is_featured = True
        profile.featured_title = title
        profile.featured_note = note
        profile.featured_order = order
        profile.featured_at = datetime.now(timezone.utc)

    # Alumni willing to come back and speak to students.
    for email, topics in [
        ("nasrin.cs@example.com",
         "Life after graduation: the first two years\n"
         "Preparing for product-company interviews\n"
         "Writing backend code that survives scale"),
        ("ayisha.data@example.com",
         "Getting into data science from a B.Sc\nWhat a machine-learning team actually does"),
    ]:
        profile = users[email].profile
        profile.offers_expert_talk = True
        profile.talk_topics = topics
        profile.talk_mode = "Either"
    db.session.flush()

    # One session already on the calendar.
    db.session.add(TalkSession(
        speaker_id=users["nasrin.cs@example.com"].id,
        arranged_by_id=admin_id,
        title="From our classrooms to a product team",
        topic="What the first two years of work ask of you, and what nobody tells you "
              "while you are still a student.",
        mode="On campus", venue="Seminar hall", audience="Final-year B.Sc and M.Sc students",
        scheduled_for=datetime.now(timezone.utc) + timedelta(days=21),
        duration_minutes=75, status=TalkStatus.CONFIRMED,
    ))

    # Internships offered to current students: one listed, one awaiting approval.
    listed = Internship(
        offered_by_id=users["jaleel.cloud@example.com"].id,
        title="Platform engineering intern", organisation="Gadgeon Systems",
        location="Kochi, Kerala", mode="On-site",
        description="Six weeks with the platform team: you will containerise a small "
                    "internal service, write its CI pipeline, and watch it through a "
                    "release. A mentor sits with you for an hour each day.",
        learning_outcomes="Docker and Kubernetes in a real cluster\n"
                          "Reading someone else's code\n"
                          "What on-call actually looks like",
        eligibility="Final-year B.Sc or any M.Sc student",
        duration_weeks=6, seats=2, is_paid=True, stipend="₹12,000 per month",
        starts_from=date.today() + timedelta(days=40),
        apply_by=date.today() + timedelta(days=25),
        status=InternshipStatus.APPROVED,
    )
    listed.skills = [Skill.get_or_create(n) for n in ("Docker", "Linux", "Python")]
    db.session.add(listed)

    pending_internship = Internship(
        offered_by_id=users["ayisha.data@example.com"].id,
        title="Data annotation and analysis intern", organisation="Tata Consultancy Services",
        location="Kochi, Kerala", mode="Hybrid",
        description="Help the applied-AI group prepare and analyse a document dataset, "
                    "and present what you find at the end of the term.",
        learning_outcomes="Pandas on real, messy data\nHow a model is evaluated",
        eligibility="Any M.Sc student", duration_weeks=8, seats=1,
        is_paid=True, stipend="₹8,000 per month",
        apply_by=date.today() + timedelta(days=30),
        status=InternshipStatus.PENDING,
    )
    pending_internship.skills = [Skill.get_or_create(n) for n in ("Python", "Pandas")]
    db.session.add(pending_internship)

    # An album for the department to fill with photographs.
    if not GalleryAlbum.query.count():
        db.session.add(GalleryAlbum(
            title="Alumni Meet 2026", slug="alumni-meet-2026",
            description="Photographs from the annual gathering on the campus. "
                        "Upload yours from the admin gallery.",
            event_date=date.today() + timedelta(days=45),
            is_published=True, sort_order=10,
        ))

    # Two offers accepted through the portal — the placement showcase.
    db.session.add(Application(
        job_id=jobs["Junior Flutter Developer"].id,
        applicant_id=users["hiba.flutter@example.com"].id,
        cover_letter="I have four Flutter apps on the Play Store, two built for "
                     "businesses here in Areekode.",
        status=ApplicationStatus.HIRED,
        employer_note="Offer accepted — joining next month. Welcome aboard!",
    ))
    db.session.add(Application(
        job_id=jobs["Backend Engineer (Python)"].id,
        applicant_id=users["sufiyan.qa@example.com"].id,
        cover_letter="Two years in QA automation and keen to move into backend work.",
        status=ApplicationStatus.HIRED,
        employer_note="Hired into the billing platform team after three rounds.",
    ))
    db.session.add(Message(
        sender_id=users["jaleel.cloud@example.com"].id,
        recipient_id=users["rahul.dev@example.com"].id,
        subject="Frontend opening at Gadgeon",
        body="Saw your profile on CS Connect — we have a React position opening up "
             "next quarter. Send me your resume and I will refer you internally.",
    ))
    db.session.flush()
    return generated
