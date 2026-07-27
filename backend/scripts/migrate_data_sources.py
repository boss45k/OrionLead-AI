"""
Migration: upgrade data_sources table to production schema.

Run once from the backend directory:
    python scripts/migrate_data_sources.py

Safe to run multiple times — skips columns that already exist.
Also seeds the table with the three default sources if it is empty.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app
from app.models.models import db

# (column_name, DDL fragment)
MIGRATIONS = [
    ('source_type',     "ALTER TABLE data_sources ADD COLUMN source_type VARCHAR(50) NOT NULL DEFAULT 'API'"),
    ('api_key_masked',  "ALTER TABLE data_sources ADD COLUMN api_key_masked VARCHAR(255) DEFAULT NULL"),
    ('enabled',         "ALTER TABLE data_sources ADD COLUMN enabled TINYINT(1) NOT NULL DEFAULT 1"),
    ('sync_frequency',  "ALTER TABLE data_sources ADD COLUMN sync_frequency VARCHAR(20) DEFAULT 'manual'"),
    ('records_count',   "ALTER TABLE data_sources ADD COLUMN records_count INT DEFAULT 0"),
    ('last_sync',       "ALTER TABLE data_sources ADD COLUMN last_sync DATETIME DEFAULT NULL"),
    ('performance',     "ALTER TABLE data_sources ADD COLUMN performance FLOAT DEFAULT 0"),
    ('last_error',      "ALTER TABLE data_sources ADD COLUMN last_error TEXT DEFAULT NULL"),
    ('updated_at',      "ALTER TABLE data_sources ADD COLUMN updated_at DATETIME DEFAULT NULL"),
]

# Seed rows inserted only if the table is empty after migration
SEED_SOURCES = [
    {
        'name': 'LinkedIn API',
        'source_type': 'API',
        'url': 'https://api.linkedin.com/v2',
        'enabled': 1,
        'sync_frequency': 'daily',
        'status': 'active',
        'performance': 0,
    },
    {
        'name': 'Salesforce CSV',
        'source_type': 'CSV',
        'url': '',
        'enabled': 1,
        'sync_frequency': 'weekly',
        'status': 'active',
        'performance': 0,
    },
    {
        'name': 'Company Database',
        'source_type': 'Database',
        'url': '',
        'enabled': 0,
        'sync_frequency': 'manual',
        'status': 'disabled',
        'performance': 0,
    },
]


def _column_exists(conn, table: str, column: str) -> bool:
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        result = conn.execute(text(f"PRAGMA table_info({table})"))
        return any(row[1] == column for row in result)
    else:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            f"AND TABLE_NAME = '{table}' AND COLUMN_NAME = '{column}'"
        ))
        return result.scalar() > 0


def run():
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            # 1) Add missing columns
            for column, ddl in MIGRATIONS:
                if _column_exists(conn, 'data_sources', column):
                    print(f"  [skip] data_sources.{column} already exists")
                else:
                    conn.execute(text(ddl))
                    conn.commit()
                    print(f"  [ok]   data_sources.{column} added")

            # 2) Copy old 'type' column into 'source_type' if source_type is empty
            conn.execute(text(
                "UPDATE data_sources SET source_type = type "
                "WHERE (source_type IS NULL OR source_type = '') AND type IS NOT NULL"
            ))
            conn.commit()
            print("  [ok]   source_type backfilled from type column")

            # 3) Seed default sources if table is empty
            count = conn.execute(text("SELECT COUNT(*) FROM data_sources")).scalar()
            if count == 0:
                for s in SEED_SOURCES:
                    conn.execute(text(
                        "INSERT INTO data_sources (name, type, source_type, url, enabled, sync_frequency, status, performance, created_at) "
                        "VALUES (:name, :source_type, :source_type, :url, :enabled, :sync_frequency, :status, :performance, NOW())"
                    ), s)
                conn.commit()
                print(f"  [ok]   seeded {len(SEED_SOURCES)} default sources")
            else:
                print(f"  [skip] table already has {count} rows — not seeding")

        print("Migration complete.")


if __name__ == '__main__':
    run()
