"""
Migration: add assigned_to column to leads table.
Safe to run multiple times — skips the column if it already exists.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from app import create_app
from app.models.models import db


def run():
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            dialect = db.engine.dialect.name

            if dialect == 'sqlite':
                result = conn.execute(db.text("PRAGMA table_info(leads)"))
                cols = [row[1] for row in result.fetchall()]
                if 'assigned_to' not in cols:
                    conn.execute(db.text("ALTER TABLE leads ADD COLUMN assigned_to INTEGER REFERENCES users(id)"))
                    conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_leads_assigned_to ON leads(assigned_to)"))
                    conn.commit()
                    print('[ok] leads.assigned_to added (sqlite)')
                else:
                    print('[skip] leads.assigned_to already exists')

            else:  # MySQL / PostgreSQL
                result = conn.execute(db.text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_NAME='leads' AND COLUMN_NAME='assigned_to'"
                ))
                exists = result.scalar()
                if not exists:
                    conn.execute(db.text(
                        "ALTER TABLE leads ADD COLUMN assigned_to INT NULL, "
                        "ADD INDEX ix_leads_assigned_to (assigned_to), "
                        "ADD CONSTRAINT fk_leads_assigned_to FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL"
                    ))
                    conn.commit()
                    print('[ok] leads.assigned_to added (mysql)')
                else:
                    print('[skip] leads.assigned_to already exists')


if __name__ == '__main__':
    run()
