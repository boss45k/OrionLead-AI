"""
One-time migration: add completeness_score and email_type columns to leads table.

Run once from the backend directory:
    python scripts/migrate_lead_scoring_fields.py

Safe to run multiple times — skips columns that already exist.
Compatible with SQLAlchemy 2.x (uses text() for raw SQL).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app
from app.models.models import db

MIGRATIONS = [
    # (column_name, DDL_fragment)
    (
        'completeness_score',
        'ALTER TABLE leads ADD COLUMN completeness_score FLOAT DEFAULT 0.0',
    ),
    (
        'email_type',
        "ALTER TABLE leads ADD COLUMN email_type VARCHAR(30) DEFAULT NULL",
    ),
]


def _column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists. Works for MySQL/MariaDB and SQLite."""
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        result = conn.execute(text(f"PRAGMA table_info({table})"))
        return any(row[1] == column for row in result)
    elif dialect in ('mysql', 'mariadb'):
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            f"AND TABLE_NAME = '{table}' AND COLUMN_NAME = '{column}'"
        ))
        return result.scalar() > 0
    else:
        # PostgreSQL
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            f"WHERE table_name='{table}' AND column_name='{column}'"
        ))
        return result.scalar() > 0


def run():
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            for column, ddl in MIGRATIONS:
                if _column_exists(conn, 'leads', column):
                    print(f"  [skip] leads.{column} already exists")
                else:
                    conn.execute(text(ddl))
                    conn.commit()
                    print(f"  [ok]   leads.{column} added")
        print("Migration complete.")


if __name__ == '__main__':
    run()
