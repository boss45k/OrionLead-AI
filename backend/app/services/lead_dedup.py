"""
Company-level lead deduplication.

Rule: if a teammate (same company) already collected the same person
(matched by email OR linkedin_url), the new save is blocked and the
existing lead is returned to the caller.
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


def company_duplicate(
    email: str | None,
    linkedin_url: str | None,
    current_user_id: int,
) -> tuple:
    """
    Return (existing_lead, collector_name) if a teammate in the same company
    already collected a lead matching by email or linkedin_url.
    Returns (None, None) when no duplicate is found or the user has no company.
    """
    from app.models.models import db, Lead, User

    user = User.query.get(current_user_id)
    company = (user.company or '').strip().lower() if user else ''
    if not company:
        return None, None

    teammate_ids = [
        row.id for row in
        User.query.filter(
            db.func.lower(db.func.trim(User.company)) == company,
            User.id != current_user_id,
        ).with_entities(User.id).all()
    ]
    if not teammate_ids:
        return None, None

    conditions = []
    if email:
        conditions.append(Lead.email == email)
    if linkedin_url:
        conditions.append(Lead.linkedin_url == linkedin_url)
    if not conditions:
        return None, None

    existing = (
        Lead.query
        .filter(Lead.collected_by.in_(teammate_ids), db.or_(*conditions))
        .order_by(Lead.created_at.asc())
        .first()
    )
    if not existing:
        return None, None

    collector = User.query.get(existing.collected_by)
    collector_name = (
        (collector.full_name or collector.email) if collector else 'a teammate'
    )
    logger.info(
        "[dedup] lead %s already owned by user %s (company=%s) — blocking re-save",
        existing.id, existing.collected_by, company,
    )
    return existing, collector_name
