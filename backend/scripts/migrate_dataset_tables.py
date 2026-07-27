"""
Migration: create lead_outcomes and dataset_versions tables.

Run once from backend/:
    python scripts/migrate_dataset_tables.py

Safe to run multiple times — skips tables that already exist.
Compatible with MySQL/MariaDB and SQLite.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from app import create_app
from app.models.models import db, LeadOutcome, DatasetVersion


def _table_exists(conn, table: str) -> bool:
    inspector = inspect(conn)
    return table in inspector.get_table_names()


def run():
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:

            # ── lead_outcomes ────────────────────────────────────────────────
            if _table_exists(conn, 'lead_outcomes'):
                print("  [skip] lead_outcomes table already exists")
            else:
                db.metadata.tables['lead_outcomes'].create(db.engine)
                print("  [ok]   lead_outcomes table created")

            # ── dataset_versions ─────────────────────────────────────────────
            if _table_exists(conn, 'dataset_versions'):
                print("  [skip] dataset_versions table already exists")
            else:
                db.metadata.tables['dataset_versions'].create(db.engine)
                print("  [ok]   dataset_versions table created")

        # Back-fill AI-predicted outcomes for existing labeled leads
        # Any lead with qualification_score >= 70 gets a 'hot' ai_prediction;
        # >= 45 gets 'warm'; below gets 'cold'.  Only if no outcome exists yet.
        _backfill_ai_predictions(app)
        print("Migration complete.")


def _backfill_ai_predictions(app):
    """
    Seed LeadOutcome rows from existing leads' qualification_score.
    This gives the ML pipeline something to train on immediately,
    using the weakest label source (ai_prediction, confidence 0.6).
    Skips leads that already have an outcome record.
    """
    from app.models.models import Lead, LeadOutcome
    from app.services.dataset_manager import get_dataset_manager

    manager = get_dataset_manager()

    with app.app_context():
        leads_without_outcome = (
            Lead.query
            .outerjoin(LeadOutcome, Lead.id == LeadOutcome.lead_id)
            .filter(LeadOutcome.id.is_(None))
            .all()
        )

        seeded = 0
        for lead in leads_without_outcome:
            score = lead.qualification_score or 0.0
            if score >= 70:
                outcome = 'hot'
            elif score >= 45:
                outcome = 'warm'
            else:
                outcome = 'cold'

            manager.record_outcome(
                lead_id      = lead.id,
                outcome      = outcome,
                label_source = 'ai_prediction',
                ml_score     = score,
                scoring_method = 'backfill',
            )
            seeded += 1

        db.session.commit()
        print(f"  [ok]   Back-filled {seeded} AI-predicted outcome labels")


if __name__ == '__main__':
    run()
