"""
Collection Policy
=================
Controls validation strictness per collection button.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import FrozenSet

@dataclass(frozen=True)
class CollectionPolicy:
    mode:                    str
    min_save_score:          float   # below this → drop
    min_semi_validated_score: float  # >= this → "semi_validated"
    min_validated_score:     float   # >= this → "validated"
    default_save_status:     str     # status when score is between min_save and min_semi
    run_full_intelligence:   bool    # True = run all 7 gates; False = hard-rejects only
    soft_signal_passthrough: FrozenSet[str] = field(default_factory=frozenset)
    # signals that are logged as warnings instead of causing rejection


RAW_COLLECTION = CollectionPolicy(
    mode="raw_collection",
    min_save_score=0.0,
    min_semi_validated_score=9999.0,
    min_validated_score=9999.0,
    default_save_status="unvalidated",
    run_full_intelligence=False,
    soft_signal_passthrough=frozenset({
        "generic_email", "missing_phone", "company_equals_contact_name",
        "weak_linkedin", "missing_decision_maker", "no_business_domain",
        "free_email_only_no_business_domain", "no_website_no_domain",
        "company_equals_contact_name",
    }),
)

BALANCED_INTELLIGENCE = CollectionPolicy(
    mode="balanced_intelligence",
    min_save_score=10.0,
    min_semi_validated_score=45.0,
    min_validated_score=9999.0,
    default_save_status="unvalidated",
    run_full_intelligence=True,
    soft_signal_passthrough=frozenset({
        "generic_email", "missing_phone", "company_equals_contact_name",
        "weak_linkedin", "missing_decision_maker", "no_business_domain",
        "free_email_only_no_business_domain",
    }),
)

STRICT_INTELLIGENCE = CollectionPolicy(
    mode="strict_intelligence",
    min_save_score=50.0,
    min_semi_validated_score=50.0,
    min_validated_score=70.0,
    default_save_status="semi_validated",
    run_full_intelligence=True,
    soft_signal_passthrough=frozenset(),
)
