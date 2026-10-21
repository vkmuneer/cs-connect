"""Administrator-editable site content: outward links, and page text.

Each entry has a default, so a fresh install reads sensibly before anyone
edits anything. Stored values live in the `settings` table.
"""

# key -> (label, placeholder, icon name)
SOCIAL_LINKS = [
    ("link_website", "College website", "https://www.sscollege.ac.in", "globe"),
    ("link_linkedin", "LinkedIn", "https://www.linkedin.com/company/…", "linkedin"),
    ("link_instagram", "Instagram", "https://www.instagram.com/…", "instagram"),
    ("link_youtube", "YouTube", "https://www.youtube.com/@…", "youtube"),
    ("link_facebook", "Facebook", "https://www.facebook.com/…", "facebook"),
]

SOCIAL_DEFAULTS = {
    "link_website": "https://www.sscollege.ac.in",
}


def social_links():
    """The links an administrator has configured, in display order."""
    from app.models import Setting
    from app.utils import safe_external_url

    out = []
    for key, label, _placeholder, icon in SOCIAL_LINKS:
        try:
            raw = Setting.get(key, SOCIAL_DEFAULTS.get(key))
        except Exception:  # database not ready
            raw = SOCIAL_DEFAULTS.get(key)
        url = safe_external_url(raw)
        if url:
            out.append({"key": key, "label": label, "icon": icon, "url": url})
    return out


# --------------------------------------------------------------------------
# Editable page text
# --------------------------------------------------------------------------
# Each entry: key, the group it is edited under, a label, the default text, and
# whether it is a single line or a block. The default is what the site shows
# until an administrator changes it, so nothing is ever blank.
TEXTS = [
    # ---- home page: hero ------------------------------------------------
    ("home.hero_title", "Home — top of the page", "Headline",
     "Where our graduates stay in touch — and hire each other", "line"),
    ("home.hero_body", "Home — top of the page", "Opening paragraph",
     "CS Connect is the alumni network of the Department of Computer Science at "
     "Sullamussalam Science College, Areekode. Find a batchmate, list an opening "
     "for the juniors, mentor a final-year project, or take the next step in your "
     "own career.", "block"),
    ("home.cta_join", "Home — top of the page", "Join button", "Join the network", "line"),
    ("home.cta_jobs", "Home — top of the page", "Opportunities button",
     "Browse opportunities", "line"),
    ("home.cta_directory", "Home — top of the page", "Directory button",
     "Alumni directory", "line"),

    # ---- home page: statistics -----------------------------------------
    ("home.stat_members", "Home — statistics", "Members label", "Members", "line"),
    ("home.stat_batches", "Home — statistics", "Batches label", "Batches", "line"),
    ("home.stat_jobs", "Home — statistics", "Roles label", "Open roles", "line"),
    ("home.stat_placements", "Home — statistics", "Placements label",
     "Placed via portal", "line"),
    ("home.stat_providers", "Home — statistics", "Providers label", "Job providers", "line"),

    # ---- home page: sections -------------------------------------------
    ("home.jobs_title", "Home — sections", "Opportunities heading",
     "Latest opportunities", "line"),
    ("home.prominent_title", "Home — sections", "Prominent alumni heading",
     "Prominent alumni", "line"),
    ("home.prominent_note", "Home — sections", "Prominent alumni note",
     "Graduates the department puts forward, chosen from our registered members.",
     "block"),
    ("home.placements_title", "Home — sections", "Placements heading",
     "Hired through CS Connect", "line"),
    ("home.placements_note", "Home — sections", "Placements note",
     "Offers that began as a posting from one of our own alumni — the clearest "
     "measure of what this network is for.", "block"),
    ("home.members_title", "Home — sections", "Members heading",
     "Members of the network", "line"),

    # ---- home page: side panels ----------------------------------------
    ("home.news_title", "Home — side panels", "News heading", "News & events", "line"),
    ("home.talks_title", "Home — side panels", "Talks heading", "Talks coming up", "line"),
    ("home.batch_title", "Home — side panels", "Batches heading", "Find your batch", "line"),
    ("home.batch_body", "Home — side panels", "Batches text",
     "Browse by year of admission and programme.", "block"),
    ("home.how_title", "Home — side panels", "How it works heading",
     "How the portal works", "line"),
    ("home.how_step1", "Home — side panels", "Step 1",
     "Register with your batch and programme — the department verifies that you "
     "studied here.", "block"),
    ("home.how_step2", "Home — side panels", "Step 2",
     "Build your profile with your skills, experience and resume.", "block"),
    ("home.how_step3", "Home — side panels", "Step 3",
     "Job providers post openings; the department approves them before they go live.",
     "block"),
    ("home.how_step4", "Home — side panels", "Step 4",
     "Job seekers apply in one click, and the employer gets the resume with the "
     "application.", "block"),
    ("home.dept_title", "Home — side panels", "Department heading",
     "For the department", "line"),
    ("home.dept_body", "Home — side panels", "Department text",
     "Hosted by the Department of Computer Science, the portal doubles as a "
     "placement register: every posting, application and verification is recorded.",
     "block"),

    # ---- member dashboard ----------------------------------------------
    ("dashboard.title", "Member dashboard", "Heading", "My dashboard", "line"),
    ("dashboard.lede", "Member dashboard", "Introduction",
     "Your profile, your postings and everything you have applied to.", "block"),
    ("dashboard.completeness_title", "Member dashboard", "Completeness heading",
     "Profile completeness", "line"),
    ("dashboard.postings_title", "Member dashboard", "Postings heading",
     "My postings", "line"),
    ("dashboard.applications_title", "Member dashboard", "Applications heading",
     "My applications", "line"),
    ("dashboard.received_title", "Member dashboard", "Received heading",
     "Recent applications to my postings", "line"),
    ("dashboard.empty_postings", "Member dashboard", "No postings yet",
     "You have not posted anything yet.", "block"),
    ("dashboard.empty_applications", "Member dashboard", "No applications yet",
     "No applications yet.", "block"),
]

TEXT_DEFAULTS = {key: default for key, _group, _label, default, _kind in TEXTS}


def text_groups():
    """The editable entries, grouped in the order they are declared."""
    groups = {}
    for key, group, label, default, kind in TEXTS:
        groups.setdefault(group, []).append({
            "key": key, "label": label, "default": default, "kind": kind,
            "value": site_text(key), "is_default": site_text(key) == default,
        })
    return groups


def site_text(key):
    """The administrator's text for `key`, or the shipped default."""
    default = TEXT_DEFAULTS.get(key, "")
    try:
        from app.models import Setting

        stored = Setting.get(key)
    except Exception:  # database not ready
        return default
    if stored is None or not str(stored).strip():
        return default
    return stored
