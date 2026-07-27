"""
Migration: add interest / buying-intent columns to the leads table.

Run once from the backend directory:
    python scripts/migrate_interest_fields.py

Safe to run multiple times — skips columns that already exist.
Compatible with SQLAlchemy 2.x (uses text() for raw SQL).
Supports MySQL/MariaDB, SQLite, and PostgreSQL.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app
from app.models.models import db

MIGRATIONS = [
    ('interest_category', "ALTER TABLE leads ADD COLUMN interest_category VARCHAR(100) DEFAULT NULL"),
    ('product_interest',  "ALTER TABLE leads ADD COLUMN product_interest VARCHAR(500) DEFAULT NULL"),
    ('buying_intent',     "ALTER TABLE leads ADD COLUMN buying_intent VARCHAR(20) DEFAULT NULL"),
    ('intent_confidence', "ALTER TABLE leads ADD COLUMN intent_confidence FLOAT DEFAULT NULL"),
    ('intent_source',     "ALTER TABLE leads ADD COLUMN intent_source VARCHAR(100) DEFAULT NULL"),
    ('intent_reason',     "ALTER TABLE leads ADD COLUMN intent_reason VARCHAR(500) DEFAULT NULL"),
]


def _column_exists(conn, table: str, column: str) -> bool:
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
