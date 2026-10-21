"""Lightweight schema sync.

The project has no migration tool, so new tables come from `db.create_all()`
and the handful of columns added to existing tables are applied here. Each
step is idempotent, so running it on an up-to-date database does nothing.
"""
from sqlalchemy import inspect, text

from app.extensions import db

# table -> column -> DDL fragment used by ALTER TABLE ... ADD COLUMN
ADDED_COLUMNS = {
    "profiles": {
        "department_id": "INTEGER REFERENCES departments(id)",
        "is_featured": "BOOLEAN NOT NULL DEFAULT 0",
        "featured_title": "VARCHAR(160)",
        "featured_note": "TEXT",
        "featured_order": "INTEGER NOT NULL DEFAULT 100",
        "featured_at": "DATETIME",
        "offers_expert_talk": "BOOLEAN NOT NULL DEFAULT 0",
        "talk_topics": "TEXT",
        "talk_mode": "VARCHAR(20)",
    },
    "coordinators": {
        "batch_year": "INTEGER",
    },
    "faculty": {
        "user_id": "INTEGER REFERENCES users(id)",
    },
}


def sync_schema():
    """Create missing tables and add missing columns. Returns a change list."""
    inspector = inspect(db.engine)
    before = set(inspector.get_table_names())

    db.create_all()

    inspector = inspect(db.engine)
    changes = [f"created table {name}" for name in sorted(set(inspector.get_table_names()) - before)]

    for table, columns in ADDED_COLUMNS.items():
        if table not in inspector.get_table_names():
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        for column, ddl in columns.items():
            if column in existing:
                continue
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            changes.append(f"added {table}.{column}")

    db.session.commit()
    return changes
