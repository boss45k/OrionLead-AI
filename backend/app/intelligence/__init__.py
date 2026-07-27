"""
Company Intelligence Engine — Company-First Lead Collection
============================================================
Analyzes companies through a strict gate-based pipeline before any
contact is resolved.  Replaces the person-first collection paradigm.

New company-first flow:
  discover companies → anti-junk → website audit → business classification
  → user intent contract → growth signals → account scoring (7 hard gates)
  → contact resolution (ONLY if passed) → email verification → save

Quick-start
-----------
    from app.intelligence import run_intelligence_pipeline

    report = run_intelligence_pipeline(
        candidates=raw_company_leads,
        query='SaaS companies Nigeria',
        location='Nigeria',
        save_lead_fn=my_save_fn,
        allowed_types=frozenset({'b2b_saas'}),
    )
"""

# ── Shared models ─────────────────────────────────────────────────────────────
from app.intelligence.models import (
    EvidenceItem,
    IntelligenceDecision,
)

# ── User intent contract ──────────────────────────────────────────────────────
from app.intelligence.user_intent_contract import (
    IntentContract,
    UserIntentContract,
    get_intent_contract_engine,
    parse_query_intent,
)

# ── Core engine (existing) ────────────────────────────────────────────────────
try:
    from app.intelligence.company_intelligence import (
        CompanyProfile,
        CompanyIntelligenceEngine,
        analyze_company,
        get_intelligence_engine,
    )
except ImportError:
    pass

# ── Anti-junk engine ──────────────────────────────────────────────────────────
from app.intelligence.anti_junk_engine import (
    AntiJunkResult,
    AntiJunkEngine,
    check_company,
    get_anti_junk_engine,
)

# ── Website auditor ───────────────────────────────────────────────────────────
from app.intelligence.website_auditor import (
    WebsiteAuditResult,
    WebsiteAuditor,
    audit_website,
)

# ── Business classifier ───────────────────────────────────────────────────────
from app.intelligence.business_classifier import (
    BusinessClassification,
    BusinessClassifier,
    get_business_classifier,
)

# ── Growth detector ───────────────────────────────────────────────────────────
from app.intelligence.growth_detector import (
    GrowthResult,
    GrowthDetector,
    get_growth_detector,
)

# ── Account scorer (returns IntelligenceDecision) ─────────────────────────────
from app.intelligence.account_scorer import (
    AccountScorer,
    get_account_scorer,
)

# ── Contact resolver ──────────────────────────────────────────────────────────
from app.intelligence.contact_resolver import (
    ResolvedContact,
    ContactResolutionResult,
    ContactResolver,
    get_contact_resolver,
)

# ── Orchestrator (main entry point) ───────────────────────────────────────────
from app.intelligence.intelligence_orchestrator import (
    IntelligencePipelineReport,
    IntelligenceOrchestrator,
    run_intelligence_pipeline,
)

__all__ = [
    # Shared models
    "EvidenceItem",
    "IntelligenceDecision",
    # User intent
    "IntentContract",
    "UserIntentContract",
    "get_intent_contract_engine",
    "parse_query_intent",
    # Anti-junk
    "AntiJunkResult",
    "AntiJunkEngine",
    "check_company",
    "get_anti_junk_engine",
    # Website audit
    "WebsiteAuditResult",
    "WebsiteAuditor",
    "audit_website",
    # Business classifier
    "BusinessClassification",
    "BusinessClassifier",
    "get_business_classifier",
    # Growth
    "GrowthResult",
    "GrowthDetector",
    "get_growth_detector",
    # Account scorer
    "AccountScorer",
    "get_account_scorer",
    # Contact resolver
    "ResolvedContact",
    "ContactResolutionResult",
    "ContactResolver",
    "get_contact_resolver",
    # Orchestrator
    "IntelligencePipelineReport",
    "IntelligenceOrchestrator",
    "run_intelligence_pipeline",
]
