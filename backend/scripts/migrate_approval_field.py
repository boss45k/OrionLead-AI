"""
One-time migration: add `approved_at` column to the users table.

Run once from the backend directory:
    python scripts/migrate_approval_field.py

Safe to run multiple times — skips the column if it already exists.
Existing active users are stamped approved_at=created_at so they are not
mistaken for newly-registered pending accounts.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app
from app.models.models import db


def _column_exists(conn, table: str, column: str) -> bool:
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        result = conn.execute(text(f'PRAGMA table_info({table})'))
        return any(row[1] == column for row in result)
    else:
        result = conn.execute(text(
            'SELECT COUNT(*) FROM information_schema.COLUMNS '
            'WHERE TABLE_SCHEMA = DATABASE() '
            f"AND TABLE_NAME = '{table}' AND COLUMN_NAME = '{column}'"
        ))
        return result.scalar() > 0


def run():
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            if _column_exists(conn, 'users', 'approved_at'):
                print('  [skip] users.approved_at already exists')
            else:
                conn.execute(text('ALTER TABLE users ADD COLUMN approved_at DATETIME DEFAULT NULL'))
                conn.commit()
                print('  [ok]   users.approved_at added')

            # Stamp existing active users so they aren't read as "never approved".
            result = conn.execute(text(
                'UPDATE users SET approved_at = created_at '
                'WHERE is_active = 1 AND approved_at IS NULL'
            ))
            conn.commit()
            print(f'  [ok]   {result.rowcount} existing active user(s) stamped approved_at')

        print('Migration complete.')


if __name__ == '__main__':
    run()
