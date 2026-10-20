"""Configuration objects for CS Connect."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'cs_connect.sqlite'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Uploads
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    RESUME_FOLDER = UPLOAD_FOLDER / "resumes"
    PHOTO_FOLDER = UPLOAD_FOLDER / "photos"
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB per request
    ALLOWED_RESUME_EXTENSIONS = {"pdf", "doc", "docx"}
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # Sessions / security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    WTF_CSRF_TIME_LIMIT = None

    # Domain settings
    FIRST_BATCH_YEAR = 1995
    ITEMS_PER_PAGE = 12

    # Does a newly registered alumnus need admin approval before the
    # directory lists them / they can post jobs?
    REQUIRE_ADMIN_APPROVAL = os.environ.get("REQUIRE_ADMIN_APPROVAL", "1") == "1"

    # Bootstrap admin (created by `flask seed`). No default password: when
    # ADMIN_PASSWORD is unset, `flask seed` generates one and prints it once.
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sscollege.ac.in")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or None

    # Password for the sample accounts from `flask seed`; generated when unset.
    DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD") or None


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
