"""
One-time migration: add email-verification OTP columns to the users table.

Run once from the backend directory:
    python scripts/migrate_otp_fields.py

Safe to run multiple times — skips columns that already exist.
Existing users are stamped email_verified=1 so they are not locked out.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app
from app.models.models import db

MIGRATIONS = [
    ('email_verified', 'ALTER TABLE users ADD COLUMN email_verified TINYINT(1) NOT NULL DEFAULT 0'),
    ('otp_code',       'ALTER TABLE users ADD COLUMN otp_code VARCHAR(10) DEFAULT NULL'),
    ('otp_expires_at', 'ALTER TABLE users ADD COLUMN otp_expires_at DATETIME DEFAULT NULL'),
    ('otp_attempts',   'ALTER TABLE users ADD COLUMN otp_attempts INT NOT NULL DEFAULT 0'),
]


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
            for column, ddl in MIGRATIONS:
                if _column_exists(conn, 'users', column):
                    print(f'  [skip] users.{column} already exists')
                else:
                    conn.execute(text(ddl))
                    conn.commit()
                    print(f'  [ok]   users.{column} added')

            # Stamp all pre-existing users as verified so they are not locked out.
            # Only touches rows where the column is still 0 AND otp_code is NULL
            # (meaning they never went through the new OTP flow).
            result = conn.execute(text(
                'UPDATE users SET email_verified = 1 '
                'WHERE email_verified = 0 AND otp_code IS NULL'
            ))
            conn.commit()
            print(f'  [ok]   {result.rowcount} existing user(s) stamped email_verified=1')

        print('Migration complete.')


if __name__ == '__main__':
    run()
