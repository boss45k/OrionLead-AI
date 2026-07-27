"""
XGBoost Lead Scoring Model — Professional ML Layer
====================================================
Replaces the GradientBoosting 12-feature model with:
  • 30 engineered features (B2B conversion signals)
  • XGBoost classifier with Optuna hyperparameter tuning
  • Isotonic probability calibration
  • SHAP TreeExplainer for per-prediction explanations
  • Version-safe loading (feature-count mismatch → auto-retrain)
  • Synthetic-data bootstrap when real leads < MIN_REAL_LEADS

Public API (same interface as the old LeadScoringModel):
    model = XGBLeadScoringModel()
    model.load_model()
    score  = model.predict(features)           # int 0-100 or None
    result = model.predict_with_explanation(features)
    ok     = model.train_from_leads(leads)
"""

from __future__ import annotations

import logging
import pickle
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

N_FEATURES      = 37
MIN_REAL_LEADS  = 50          # below this, bootstrap with synthetic data
OPTUNA_TRIALS   = 20
MODEL_VERSION   = "xgb_v5"   # bumped: added buying_intent, hiring_signal, employee_count features

# ── Human-readable labels for SHAP feature importance output ─────────────────
# Keys match the feature index order in extract_features().
# Used by the /api/v1/ai/feature-importance endpoint to translate internal
# feature names into descriptions a sales manager can understand.
FEATURE_LABELS: Dict[int, Dict[str, str]] = {
    0:  {'name': 'position_seniority',     'label': 'Job seniority level'},
    1:  {'name': 'interest_relevance',     'label': 'Relevance of stated interests'},
    2:  {'name': 'company_formality',      'label': 'Company formality / scale'},
    3:  {'name': 'source_credibility',     'label': 'Lead source credibility'},
    4:  {'name': 'email_quality',          'label': 'Email address quality'},
    5:  {'name': 'data_completeness',      'label': 'Profile data completeness'},
    6:  {'name': 'has_phone',              'label': 'Phone number provided'},
    7:  {'name': 'has_linkedin',           'label': 'LinkedIn profile provided'},
    8:  {'name': 'has_website',            'label': 'Website provided'},
    9:  {'name': 'has_industry',           'label': 'Industry specified'},
    10: {'name': 'name_quality',           'label': 'Full name quality'},
    11: {'name': 'is_corporate_email',     'label': 'Corporate (non-free) email'},
    12: {'name': 'country_tier',           'label': 'Country conversion tier'},
    13: {'name': 'interest_count',         'label': 'Number of stated interests'},
    14: {'name': 'notes_length_score',     'label': 'Engagement notes length'},
    15: {'name': 'company_size_indicator', 'label': 'Company size indicator'},
    16: {'name': 'decision_maker_score',   'label': 'Decision-maker authority'},
    17: {'name': 'multi_channel_presence', 'label': 'Multi-channel contact presence'},
    18: {'name': 'email_tld_quality',      'label': 'Email domain TLD quality'},
    19: {'name': 'budget_signal_score',    'label': 'Budget signals in notes'},
    20: {'name': 'position_keyword_count', 'label': 'Power titles in position'},
    21: {'name': 'interest_high_value_count', 'label': 'High-value interest count'},
    22: {'name': 'med_value_interest_count',  'label': 'Medium-value interest count'},
    23: {'name': 'has_city',               'label': 'City information provided'},
    24: {'name': 'has_notes',              'label': 'Notes text present'},
    25: {'name': 'notes_budget_strong',    'label': 'Strong budget signals in notes'},
    26: {'name': 'industry_value_score',      'label': 'Industry conversion rate score'},
    27: {'name': 'interest_diversity',        'label': 'Interest mix diversity'},
    28: {'name': 'email_domain_prestige',     'label': 'Email domain prestige score'},
    # ── 5 new features (v3, now indices 29-33 after removing duplicate) ──────
    29: {'name': 'email_format_confidence',   'label': 'Email format validity confidence'},
    30: {'name': 'spam_risk_score',           'label': 'Spam/bot risk score (inverted)'},
    31: {'name': 'enrichment_completeness',   'label': 'Enriched field coverage score'},
    32: {'name': 'domain_age_proxy',          'label': 'Domain age/maturity proxy'},
    33: {'name': 'source_reliability_score',  'label': 'Source reliability & trust score'},
    # ── 3 new features (v5, indices 34-36) ──────────────────────────────────
    34: {'name': 'buying_intent_score',       'label': 'Buying intent signal strength'},
    35: {'name': 'hiring_signal_score',       'label': 'Company hiring activity score'},
    36: {'name': 'employee_count_score',      'label': 'Company size (employee count)'},
}

_FREE_DOMAINS = frozenset([
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com',
    'live.com', 'aol.com', 'protonmail.com', 'mail.com', 'yandex.com',
    'me.com', 'gmx.com', 'fastmail.com',
])

# High-value B2B technology interests
_INTERESTS_HIGH = frozenset([
    'artificial intelligence', 'machine learning', 'automation', 'analytics',
    'cloud computing', 'cybersecurity', 'digital transformation', 'data science',
    'saas integration', 'enterprise software', 'business intelligence',
    'api integration', 'devops', 'microservices', 'data engineering',
    'real-time analytics', 'predictive analytics', 'mlops', 'llm', 'nlp',
])
_INTERESTS_MED = frozenset([
    'crm', 'erp', 'marketing automation', 'sales enablement', 'customer success',
    'project management', 'collaboration tools', 'e-commerce', 'mobile apps',
    'web development', 'it infrastructure', 'helpdesk', 'reporting',
    'workflow automation', 'document management', 'hr software',
])

# Country tier mappings (tier 3 = best conversion quality)
_TIER3 = frozenset([
    'united states', 'united kingdom', 'canada', 'australia', 'singapore',
    'germany', 'netherlands', 'sweden', 'switzerland', 'denmark',
    'united arab emirates', 'israel', 'japan', 'south korea', 'norway',
    'finland', 'ireland', 'new zealand',
])
_TIER2 = frozenset([
    'france', 'spain', 'italy', 'brazil', 'mexico', 'india',
    'south africa', 'belgium', 'poland', 'portugal', 'czech republic',
    'austria', 'hungary', 'romania', 'greece',
])

# Budget signal keywords for notes
_BUDGET_STRONG = re.compile(
    r'\$\s*\d|budget|pre[- ]?approved|decision maker|approved fund|capex|opex',
    re.IGNORECASE,
)
_BUDGET_WEAK = re.compile(
    r'invest|spend|purchas|procur|pilot|evaluating|compare|timeline',
    re.IGNORECASE,
)

FEATURE_NAMES: List[str] = [
    # --- Core 12 (preserved for backward compat) ---
    'position_seniority',         # 0  0-5
    'interest_relevance',         # 1  0-5  high-value kw matched
    'company_formality',          # 2  0-5
    'source_credibility',         # 3  0-3
    'email_quality',              # 4  0-3
    'data_completeness',          # 5  0-5  proportion of 10 key fields
    'has_phone',                  # 6  0-1
    'has_linkedin',               # 7  0-1
    'has_website',                # 8  0-1
    'has_industry',               # 9  0-1
    'name_quality',               # 10 0-2
    'is_corporate_email',         # 11 0-1
    # --- 18 extended features ---
    'country_tier',               # 12 0-3  geographic conversion quality
    'interest_count',             # 13 0-10 raw number of interests (capped)
    'notes_length_score',         # 14 0-5  binned note length → engagement proxy
    'company_size_indicator',     # 15 0-5  inferred from company suffix
    'decision_maker_score',       # 16 0-5  buying-authority keywords
    'multi_channel_presence',     # 17 0-4  channels with data (email+phone+li+web)
    'email_tld_quality',          # 18 0-3  .com=3, .io/.co=2, .net/.org=2, ccTLD=1
    'budget_signal_score',        # 19 0-3  dollar/budget keywords in notes
    'position_keyword_count',     # 20 0-5  count of power-title tokens
    'interest_high_value_count',  # 21 0-10 count of high-tier interests
    'interest_med_value_count',   # 22 0-10 count of medium-tier interests
    'has_city',                   # 23 0-1
    'has_notes',                  # 24 0-1
    'notes_budget_strong',        # 25 0-1  strong budget signals present
    'industry_value_score',       # 26 0-5  industry tier → numeric
    'interest_diversity',         # 27 0-3  0=none,1=low,2=medium,3=high diversity
    'email_domain_prestige',      # 28 0-3  well-known corp domain = 3
    # --- 5 new v3 features (re-indexed after removing duplicate #26) ---
    'email_format_confidence',    # 29 0-3  email regex validity + structure
    'spam_risk_score',            # 30 0-3  inverse of spam risk (3=clean, 0=spammy)
    'enrichment_completeness',    # 31 0-5  count of enrichment-only fields filled
    'domain_age_proxy',           # 32 0-3  domain maturity estimate from TLD+structure
    'source_reliability_score',   # 33 0-5  source reliability combining credibility + trust signals
    # --- 3 new v5 features ---
    'buying_intent_score',        # 34 0-3  high/medium/low/none from intent analysis
    'hiring_signal_score',        # 35 0-5  normalised hiring activity (from intelligence suite)
    'employee_count_score',       # 36 0-5  log-scale employee count bucket
]

assert len(FEATURE_NAMES) == N_FEATURES, f"Feature count mismatch: {len(FEATURE_NAMES)}"


# ─── Feature extraction ───────────────────────────────────────────────────────

def extract_features(lead_data: Dict[str, Any]) -> np.ndarray:
    """
    Extract ML features from a lead dict.

    Handles missing fields gracefully — returns 0 for any absent field.
    Returns shape (1, N_FEATURES) float32 array.
    """
    try:
        # Use pre-computed features from auto-retrain dataset logs if available
        if '_features_override' in lead_data:
            arr = np.array([lead_data['_features_override']], dtype=np.float32)
            if arr.shape[1] == N_FEATURES:
                return arr

        # ── helpers ──────────────────────────────────────────────────────────
        position  = str(lead_data.get('position', '')).lower()
        company   = str(lead_data.get('company',  '')).lower()
        email     = str(lead_data.get('email',    '')).lower()
        source    = str(lead_data.get('source',   '')).lower()
        industry  = str(lead_data.get('industry', '')).lower()
        country   = str(lead_data.get('country',  '')).lower()
        notes     = str(lead_data.get('notes',    ''))
        name      = str(lead_data.get('name',     ''))

        interests = lead_data.get('interests', [])
        if not isinstance(interests, list):
            interests = [interests] if interests else []
        interests_str = ' '.join(str(i).lower() for i in interests)

        # ── email domain ─────────────────────────────────────────────────────
        _GENERATED_SOURCES = frozenset({
            'generated', 'generated_personal', 'generated_generic',
            'inferred', 'guessed',
        })
        dp = lead_data.get('data_points') or {}
        _email_src = str(dp.get('email_source') or '').strip().lower()
        _email_is_generated = _email_src in _GENERATED_SOURCES
        # Treat generated/inferred emails as absent so ML doesn't reward garbage
        if _email_is_generated:
            email = ''

        email_domain = ''
        if '@' in email:
            email_domain = email.split('@')[1]
        is_corporate = int(bool(email_domain) and email_domain not in _FREE_DOMAINS)

        # ── 0. position_seniority (continuous, proportional to conversion rate)
        # C-suite → 4.6, VP → 3.8, Director → 3.0, Manager → 2.2, Staff → 1.2, unknown → 0
        if any(t in position for t in ['ceo', 'cto', 'cfo', 'coo', 'cpo', 'cmo', 'cro',
                                        'chief', 'founder', 'president', 'managing director',
                                        'executive director']):
            pos_seniority = 4.6
        elif any(t in position for t in ['vp', 'vice president', 'head of', 'general manager',
                                          'svp', 'evp']):
            pos_seniority = 3.8
        elif any(t in position for t in ['director']):
            pos_seniority = 3.0
        elif any(t in position for t in ['manager', 'lead', 'senior', 'principal',
                                          'supervisor', 'staff engineer']):
            pos_seniority = 2.2
        elif position:
            pos_seniority = 1.2
        else:
            pos_seniority = 0.0

        # ── 1. interest_relevance (high-value kw, capped at 5) ───────────────
        hv_kws = ['automation', 'analytics', 'ai', 'machine learning', 'security',
                  'integration', 'enterprise', 'saas', 'cloud', 'data', 'crm',
                  'erp', 'devops', 'fintech', 'digital transformation', 'b2b']
        interest_rel = min(sum(1 for kw in hv_kws if kw in interests_str), 5)

        # ── 2. company_formality ─────────────────────────────────────────────
        if any(s in company for s in ['enterprise', 'corporation', 'global',
                                       'international', 'worldwide']):
            co_formal = 5
        elif any(s in company for s in ['corp', 'inc', 'group', 'holdings',
                                         'ventures', 'partners']):
            co_formal = 4
        elif any(s in company for s in ['llc', 'ltd', 'limited', 'gmbh', 'ag',
                                         's.a.', 'srl', 'bv']):
            co_formal = 3
        elif len(company) > 2:
            co_formal = 2
        else:
            co_formal = 0

        # ── 3. source_credibility (continuous, proportional to conv rate × 10)
        # referral=4.6, partner=4.0, linkedin=3.2, conference=2.8, inbound=2.5,
        # content=2.2, email_campaign=1.8, social_media=1.2, cold_outreach=1.0, web=0.8
        src_cred_map = {
            'referral': 4.6, 'partner': 4.0, 'linkedin': 3.2,
            'conference': 2.8, 'inbound': 2.5, 'content': 2.2,
            'email_campaign': 1.8, 'social_media': 1.2,
            'cold_outreach': 1.0, 'web': 0.8,
        }
        src_cred = next((v for k, v in src_cred_map.items() if k in source), 1.0)

        # ── 4. email_quality ─────────────────────────────────────────────────
        if not email or '@' not in email:
            email_qual = 0
        else:
            email_qual = 3 if is_corporate else 1

        # ── 5. data_completeness ─────────────────────────────────────────────
        key_fields = ['name', 'email', 'phone', 'company', 'position',
                      'linkedin_url', 'website', 'industry', 'country', 'interests']
        # Generated email doesn't count as a real filled field
        filled = sum(
            1 for f in key_fields
            if lead_data.get(f) and not (f == 'email' and _email_is_generated)
        )
        completeness = round(filled / len(key_fields) * 5, 2)

        # ── 6-9. binary flags ────────────────────────────────────────────────
        has_phone    = int(bool(lead_data.get('phone')))
        has_linkedin = int(bool(lead_data.get('linkedin_url')))
        has_website  = int(bool(lead_data.get('website')))
        has_industry = int(bool(lead_data.get('industry')))

        # ── 10. name_quality ─────────────────────────────────────────────────
        parts = [p for p in name.split() if len(p) > 1]
        name_qual = 2 if len(parts) >= 2 else (1 if len(parts) == 1 else 0)

        # ═══ New features (12-29) ═══════════════════════════════════════════

        # ── 12. country_tier ─────────────────────────────────────────────────
        if country in _TIER3:
            ctry_tier = 3
        elif country in _TIER2:
            ctry_tier = 2
        elif country:
            ctry_tier = 1
        else:
            ctry_tier = 0

        # ── 13. interest_count ───────────────────────────────────────────────
        interest_count = min(len(interests), 10)

        # ── 14. notes_length_score ───────────────────────────────────────────
        nl = len(notes)
        if nl == 0:
            notes_len_score = 0
        elif nl < 50:
            notes_len_score = 1
        elif nl < 100:
            notes_len_score = 2
        elif nl < 200:
            notes_len_score = 3
        elif nl < 500:
            notes_len_score = 4
        else:
            notes_len_score = 5

        # ── 15. company_size_indicator ───────────────────────────────────────
        if any(s in company for s in ['corporation', 'global', 'international',
                                       'holdings', 'enterprise']):
            co_size = 5     # large enterprise
        elif any(s in company for s in ['corp', 'inc', 'group', 'partners',
                                         'ventures', 'associates']):
            co_size = 4     # mid-large
        elif any(s in company for s in ['llc', 'ltd', 'limited', 'solutions',
                                         'technologies']):
            co_size = 3     # SMB
        elif any(s in company for s in ['ai', 'tech', 'labs', 'systems',
                                         'digital', 'hq']):
            co_size = 2     # startup
        elif company:
            co_size = 1
        else:
            co_size = 0

        # ── 16. decision_maker_score ─────────────────────────────────────────
        dm_kws = ['ceo', 'cto', 'cfo', 'founder', 'president', 'owner', 'chief',
                  'vp', 'director', 'head of', 'managing']
        dm_score = min(sum(1 for kw in dm_kws if kw in position), 5)

        # ── 17. multi_channel_presence ───────────────────────────────────────
        channels = (int(bool(email)) + int(bool(lead_data.get('phone'))) +
                    int(bool(lead_data.get('linkedin_url'))) +
                    int(bool(lead_data.get('website'))))
        multi_channel = channels  # 0-4

        # ── 18. email_tld_quality ────────────────────────────────────────────
        if not email_domain:
            tld_qual = 0
        else:
            tld = email_domain.rsplit('.', 1)[-1]
            if tld == 'com':
                tld_qual = 3
            elif tld in ('io', 'co', 'ai', 'tech', 'app'):
                tld_qual = 2
            elif tld in ('net', 'org', 'edu', 'gov', 'biz'):
                tld_qual = 2
            else:
                tld_qual = 1   # country-code or other

        # ── 19. budget_signal_score ──────────────────────────────────────────
        if _BUDGET_STRONG.search(notes):
            budget_sig = 3
        elif _BUDGET_WEAK.search(notes):
            budget_sig = 2
        elif notes:
            budget_sig = 1
        else:
            budget_sig = 0

        # ── 20. position_keyword_count ───────────────────────────────────────
        power_kws = ['chief', 'vp', 'vice president', 'director', 'manager',
                     'head', 'founder', 'president', 'partner', 'principal']
        pos_kw_count = min(sum(1 for kw in power_kws if kw in position), 5)

        # ── 21. interest_high_value_count ────────────────────────────────────
        i_high = sum(1 for i in interests
                     if any(hv in str(i).lower() for hv in _INTERESTS_HIGH))
        i_high = min(i_high, 10)

        # ── 22. interest_med_value_count ─────────────────────────────────────
        i_med = sum(1 for i in interests
                    if any(mv in str(i).lower() for mv in _INTERESTS_MED))
        i_med = min(i_med, 10)

        # ── 23. has_city ─────────────────────────────────────────────────────
        has_city = int(bool(lead_data.get('city')))

        # ── 24. has_notes ────────────────────────────────────────────────────
        has_notes = int(bool(notes.strip()))

        # ── 25. notes_budget_strong ──────────────────────────────────────────
        notes_bgt_strong = int(bool(_BUDGET_STRONG.search(notes)))

        # ── 26. industry_value_score (continuous, proportional to conv rate × 10)
        # Maps industry keyword → rate × 10 for fine-grained split signal
        _IND_RATES = [
            ('ai / ml', 4.0), ('machine learning', 4.0), ('saas', 3.8),
            ('fintech', 3.5), ('cybersecurity', 3.4), ('cloud', 3.5),
            ('data analytics', 3.3), ('devops', 3.2),
            ('healthcare technology', 3.0), ('healthcare tech', 3.0),
            ('erp', 2.8), ('crm', 2.8), ('marketing technology', 2.8),
            ('hrtech', 2.4), ('insurtech', 2.4), ('e-commerce', 2.5),
            ('proptech', 2.0), ('legaltech', 2.2), ('logistics', 2.0),
            ('manufacturing technology', 2.2), ('biotech', 2.2),
            ('supply chain', 2.0), ('professional services', 1.8),
            ('consulting', 2.0), ('traditional manufacturing', 1.2),
            ('healthcare', 1.0), ('education', 0.8), ('retail', 1.5),
            ('government', 0.6), ('non-profit', 0.5),
        ]
        ind_val = next((v for kw, v in _IND_RATES if kw in industry), 1.0)

        # ── 27. interest_diversity ───────────────────────────────────────────
        has_high = int(i_high > 0)
        has_med  = int(i_med > 0)
        has_any  = int(interest_count > 0)
        interest_div = has_high + has_med + has_any  # 0-3

        # ── 28. email_domain_prestige ────────────────────────────────────────
        # Well-known B2B SaaS / tech / finance companies email → 3
        _PRESTIGE = re.compile(
            r'\.(salesforce|microsoft|google|amazon|apple|ibm|oracle|sap|'
            r'adobe|linkedin|hubspot|zendesk|stripe|twilio|cloudflare|'
            r'datadog|snowflake|palantir|nvidia|intel|cisco|vmware|'
            r'jpmorgan|goldman|blackrock|deloitte|mckinsey|bain|bcg)\.',
            re.IGNORECASE,
        )
        if email_domain and _PRESTIGE.search(f'.{email_domain}.'):
            dom_prestige = 3
        elif is_corporate and tld_qual >= 2:
            dom_prestige = 2
        elif is_corporate:
            dom_prestige = 1
        else:
            dom_prestige = 0

        # ═══ v3 features (30-34) ═════════════════════════════════════════════

        # ── 29. email_format_confidence ─────────────────────────────────────
        # Validates email structure; corporate domain and realistic format → 3
        _EMAIL_RE = re.compile(
            r'^[a-zA-Z0-9._%+\-]{1,64}@[a-zA-Z0-9.\-]{2,255}\.[a-zA-Z]{2,10}$'
        )
        if not email or '@' not in email:
            email_fmt_conf = 0
        elif not _EMAIL_RE.match(email):
            email_fmt_conf = 1  # present but malformed
        elif is_corporate:
            email_fmt_conf = 3  # valid + corporate domain
        else:
            email_fmt_conf = 2  # valid but free-email

        # ── 30. spam_risk_score (inverted: 3=clean, 0=spammy) ───────────────
        _DISPOSABLE_QUICK = frozenset([
            'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'throwaway.email',
            'yopmail.com', '10minutemail.com', 'trashmail.com', 'maildrop.cc',
            'sharklasers.com', 'fakeinbox.com', 'mailsac.com', 'getnada.com',
        ])
        _ROLE_PFX_QUICK = frozenset([
            'admin', 'info', 'contact', 'support', 'noreply', 'no-reply',
            'hello', 'sales', 'marketing', 'hr', 'careers', 'team',
        ])
        spam_risk = 0
        if email_domain and email_domain in _DISPOSABLE_QUICK:
            spam_risk += 2
        if '@' in email:
            pfx = email.split('@')[0].split('+')[0]
            if pfx in _ROLE_PFX_QUICK:
                spam_risk += 1
        if name:
            letters = re.sub(r'[^a-zA-Z]', '', name)
            if len(letters) >= 4:
                vowels = sum(1 for c in letters.lower() if c in 'aeiouy')
                if vowels / len(letters) < 0.10:
                    spam_risk += 2
        spam_risk_inv = max(0, 3 - min(spam_risk, 3))  # invert: clean=3, spammy=0

        # ── 31. enrichment_completeness ─────────────────────────────────────
        # Fields that only get filled through enrichment (not basic form)
        enrichment_fields = ['linkedin_url', 'website', 'industry', 'country', 'city',
                             'interests', 'notes']
        enrich_filled = sum(1 for f in enrichment_fields if lead_data.get(f) not in (None, '', [], {}))
        enrichment_score = round(enrich_filled / len(enrichment_fields) * 5, 2)

        # ── 32. domain_age_proxy ─────────────────────────────────────────────
        # Older/more established domains tend to have .com + known corp names
        # and NOT generic subdomains.  Heuristic: 0-3
        if not email_domain:
            dom_age_proxy = 0
        elif _PRESTIGE.search(f'.{email_domain}.'):  # prestige → definitely established
            dom_age_proxy = 3
        elif tld_qual == 3 and is_corporate:  # .com + corporate → likely mature
            dom_age_proxy = 2
        elif tld_qual >= 2:
            dom_age_proxy = 1
        else:
            dom_age_proxy = 0

        # ── 33. source_reliability_score ────────────────────────────────────
        # Combines raw source credibility with known-reliable source signals
        _RELIABLE_SOURCES = {
            'referral': 5.0, 'partner': 4.5, 'conference': 4.0,
            'linkedin': 3.5, 'inbound': 3.5, 'content': 3.0,
            'email_campaign': 2.5, 'social_media': 2.0,
            'cold_outreach': 1.5, 'web': 1.0,
        }
        src_rel = next((v for k, v in _RELIABLE_SOURCES.items() if k in source), 1.0)

        # ═══ v5 features (34-36) ══════════════════════════════════════════════

        # ── 34. buying_intent_score ─────────────────────────────────────────
        # Maps the buying_intent field (set by Interest Collect / intelligence
        # orchestrator) to a 0-3 ordinal.  Most leads have no intent signal (0).
        _bi_map = {'high': 3, 'medium': 2, 'low': 1, 'none': 0}
        _bi_raw = str(lead_data.get('buying_intent') or 'none').lower().strip()
        buying_intent_score = float(_bi_map.get(_bi_raw, 0))

        # ── 35. hiring_signal_score ─────────────────────────────────────────
        # Hiring activity detected by HiringSignalDetector / intelligence suite.
        # Stored in data_points.hiring_score (0-100) → normalise to 0-5.
        _dp = lead_data.get('data_points') or {}
        _hs_raw = _dp.get('hiring_score') or lead_data.get('hiring_score') or 0
        try:
            hiring_signal_score = round(min(float(_hs_raw) / 20.0, 5.0), 2)
        except (TypeError, ValueError):
            hiring_signal_score = 0.0

        # ── 36. employee_count_score ────────────────────────────────────────
        # Log-scale bucket from employee_count (Apollo / PDL enrichment).
        # Larger companies = higher conversion ceiling on B2B deals.
        _ec_raw = lead_data.get('employee_count') or _dp.get('employee_count') or 0
        try:
            _ec = int(_ec_raw)
        except (TypeError, ValueError):
            _ec = 0
        if _ec >= 1000:
            employee_count_score = 5.0
        elif _ec >= 200:
            employee_count_score = 4.0
        elif _ec >= 50:
            employee_count_score = 3.0
        elif _ec >= 10:
            employee_count_score = 2.0
        elif _ec >= 1:
            employee_count_score = 1.0
        else:
            employee_count_score = 0.0

        return np.array([[
            pos_seniority,      # 0
            interest_rel,       # 1
            co_formal,          # 2
            src_cred,           # 3
            email_qual,         # 4
            completeness,       # 5
            has_phone,          # 6
            has_linkedin,       # 7
            has_website,        # 8
            has_industry,       # 9
            name_qual,          # 10
            is_corporate,       # 11
            ctry_tier,          # 12
            interest_count,     # 13
            notes_len_score,    # 14
            co_size,            # 15
            dm_score,           # 16
            multi_channel,      # 17
            tld_qual,           # 18
            budget_sig,         # 19
            pos_kw_count,       # 20
            i_high,             # 21
            i_med,              # 22
            has_city,           # 23
            has_notes,          # 24
            notes_bgt_strong,   # 25
            ind_val,            # 26
            interest_div,       # 27
            dom_prestige,       # 28
            email_fmt_conf,       # 29
            spam_risk_inv,        # 30
            enrichment_score,     # 31
            dom_age_proxy,        # 32
            src_rel,              # 33
            buying_intent_score,  # 34
            hiring_signal_score,  # 35
            employee_count_score, # 36
        ]], dtype=np.float32)

    except Exception as exc:
        logger.error(f"extract_features error: {exc}", exc_info=True)
        return np.zeros((1, N_FEATURES), dtype=np.float32)


# ─── Calibration wrapper ─────────────────────────────────────────────────────

class _CalibratedXGBWrapper:
    """
    Thin wrapper that pairs an XGBClassifier with a fitted IsotonicRegression
    calibrator, exposing a `predict_proba(X)` interface identical to sklearn.
    Stored inside the pickle payload so loading is transparent.
    """

    def __init__(self, clf, calibrator) -> None:
        self.clf        = clf
        self.calibrator = calibrator

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw  = self.clf.predict_proba(X)[:, 1]
        cal  = self.calibrator.transform(raw)
        return np.column_stack([1.0 - cal, cal])

    # Expose the inner XGB for SHAP (TreeExplainer needs the raw booster)
    @property
    def estimator(self):
        return self.clf


# ─── XGBoost Model ────────────────────────────────────────────────────────────

class XGBLeadScoringModel:
    """
    XGBoost lead scoring model with:
    - 30 engineered features
    - Optuna hyperparameter tuning (OPTUNA_TRIALS trials)
    - Isotonic calibration for reliable probabilities
    - SHAP TreeExplainer for per-prediction explanations
    - Synthetic-data bootstrap when real leads < MIN_REAL_LEADS
    - Version-safe loading (stale feature count → discard + retrain)
    """

    def __init__(self) -> None:
        self.model = None                  # CalibratedClassifierCV wrapping XGBClassifier
        self.feature_names: List[str]      = FEATURE_NAMES[:]
        self.training_stats: Dict[str, Any] = {}
        self.model_path = (
            Path(__file__).parent.parent.parent / 'models' / 'lead_scoring_sklearn.pkl'
        )
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self._shap_explainer = None
        self._shap_lock = threading.Lock()

    # ── Public interface (same as old LeadScoringModel) ──────────────────────

    @property
    def is_trained(self) -> bool:
        """True when a trained model is loaded and ready to score."""
        return self.model is not None

    def predict(self, features: np.ndarray) -> Optional[int]:
        """Return 0-100 probability score, or None if model not ready."""
        try:
            if self.model is None:
                self.load_model()
            if self.model is None:
                return None
            if features.shape[1] != N_FEATURES:
                logger.warning(
                    f"Feature count mismatch: got {features.shape[1]}, "
                    f"expected {N_FEATURES}"
                )
                return None
            prob = self.model.predict_proba(features)[0][1]
            return int(round(float(prob) * 100))
        except Exception as exc:
            logger.error(f"XGB predict error: {exc}")
            return None

    def predict_with_explanation(self, features: np.ndarray) -> Dict[str, Any]:
        """Return score + SHAP top-factors explanation."""
        score = self.predict(features)
        if score is None:
            return {'score': None, 'explanation': 'Model not trained'}

        result: Dict[str, Any] = {'score': score}

        try:
            shap_vals = self._compute_shap(features)
            if shap_vals is not None:
                # shap_vals shape: (1, N_FEATURES) — values for positive class
                sv = shap_vals[0]
                top = sorted(
                    zip(self.feature_names, features[0].tolist(), sv.tolist()),
                    key=lambda x: abs(x[2]),
                    reverse=True,
                )[:5]
                result['top_factors'] = [
                    {
                        'feature':    n,
                        'value':      float(v),
                        'shap_impact': float(s),
                        'direction':  'positive' if s > 0 else 'negative',
                    }
                    for n, v, s in top
                ]
                result['shap_available'] = True
        except Exception as exc:
            logger.debug(f"SHAP explanation skipped: {exc}")
            result['shap_available'] = False

        return result

    def train_from_leads(self, leads: List[Dict[str, Any]]) -> bool:
        """
        Train on qualified leads.  If fewer than MIN_REAL_LEADS qualified real
        records exist, synthetic data is loaded as bootstrap.

        Steps:
          1. Collect qualified real leads (have qualification_score > 0)
          2. Optionally bootstrap with synthetic data
          3. Extract 30 features per lead
          4. Optuna tuning (OPTUNA_TRIALS trials, AUC-ROC objective)
          5. Isotonic calibration on a hold-out split
          6. AUC + accuracy evaluation on 20% hold-out
          7. Save model + stats
        """
        try:
            from sklearn.metrics import roc_auc_score, accuracy_score
            from sklearn.model_selection import train_test_split
            import xgboost as xgb
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)

            # ── 1. Collect all candidate leads (synthetic + real with confirmed outcomes)
            # Leads with confirmed human outcomes (converted/rejected/cold/contacted)
            # come in with explicit '_label', 'outcome', or 'status' fields.
            # DB leads with only qualification_score are excluded — using a model's
            # own score as a training label creates a circular dependency.
            qualified = list(leads)
            n_real = sum(
                1 for l in qualified
                if '_label' not in l  # synthetic leads have _label
            )
            logger.info(f"[XGB] Candidate leads: {len(qualified)} ({n_real} non-synthetic)")

            # ── 2. Always mix synthetic data for a balanced, large dataset ────
            import random as _random
            synth = self._load_synthetic_leads()
            if synth:
                _random.seed(42)
                synth_sample = _random.sample(synth, min(5000, len(synth)))
                qualified = synth_sample + qualified  # real leads at end = recency bias
                logger.info(
                    f"[XGB] Mixed {len(synth_sample)} synthetic + "
                    f"{n_real} real leads for training"
                )
            elif n_real < 10:
                logger.warning("[XGB] Not enough data and no synthetic available")
                return False

            # ── 3. Build feature matrix ───────────────────────────────────────
            rows, labels = [], []
            for lead in qualified:
                feat = extract_features(lead)
                if feat.shape[1] != N_FEATURES:
                    continue
                # Only use explicit labels — synthetic (_label) or human feedback (outcome).
                # DB leads without a confirmed outcome are skipped; using qualification_score
                # as a label creates circular dependency (model learns to reconstruct itself).
                _STATUS_TO_LABEL = {
                    'converted': 1, 'contacted': 1,
                    'rejected': 0, 'cold': 0, 'unqualified': 0,
                }
                if '_label' in lead:
                    label = int(lead['_label'])
                elif lead.get('outcome') in _STATUS_TO_LABEL:
                    label = _STATUS_TO_LABEL[lead['outcome']]
                elif lead.get('status') in _STATUS_TO_LABEL:
                    label = _STATUS_TO_LABEL[lead['status']]
                else:
                    continue  # no confirmed outcome — skip this lead
                rows.append(feat[0])
                labels.append(label)

            if len(rows) < 20:
                logger.warning(f"[XGB] Too few samples after extraction: {len(rows)}")
                return False

            X = np.array(rows, dtype=np.float32)
            y = np.array(labels, dtype=np.int32)
            n_pos = int(y.sum())
            n_neg = len(y) - n_pos

            if n_pos < 5 or n_neg < 5:
                logger.warning(f"[XGB] Class imbalance too extreme: pos={n_pos}, neg={n_neg}")
                return False

            logger.info(f"[XGB] Dataset: {len(y)} samples (pos={n_pos}, neg={n_neg})")

            # ── 4. 3-way stratified split: 65% train / 15% calibration / 20% test ──
            X_temp, X_te, y_temp, y_te = train_test_split(
                X, y, test_size=0.20, stratify=y, random_state=42
            )
            X_tr, X_cal, y_tr, y_cal = train_test_split(
                X_temp, y_temp, test_size=0.1875, stratify=y_temp, random_state=42
            )   # 0.1875 × 80% = 15% of total

            # ── 5. Optuna: tune XGBoost on train split with 3-fold CV AUC ────
            scale_pos_weight = n_neg / max(n_pos, 1)

            def _objective(trial: optuna.Trial) -> float:
                from sklearn.model_selection import StratifiedKFold, cross_val_score
                # Use a tight learning_rate range to avoid extreme underfitting
                lr = trial.suggest_float('learning_rate', 0.05, 0.3, log=True)
                # Scale n_estimators inversely to learning rate for budget balance
                n_est = trial.suggest_int('n_estimators', 200, 800)
                params = {
                    'n_estimators':     n_est,
                    'max_depth':        trial.suggest_int('max_depth', 3, 7),
                    'learning_rate':    lr,
                    'subsample':        trial.suggest_float('subsample', 0.6, 1.0),
                    'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                    'min_child_weight': trial.suggest_int('min_child_weight', 1, 8),
                    'reg_alpha':        trial.suggest_float('reg_alpha', 1e-5, 1.0, log=True),
                    'reg_lambda':       trial.suggest_float('reg_lambda', 1e-5, 1.0, log=True),
                    'scale_pos_weight': scale_pos_weight,
                    'eval_metric':      'logloss',
                    'random_state':     42,
                    'n_jobs':           -1,
                }
                clf = xgb.XGBClassifier(**params)
                skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
                scores = cross_val_score(clf, X_tr, y_tr, cv=skf,
                                         scoring='roc_auc', n_jobs=1)
                return float(scores.mean())

            study = optuna.create_study(direction='maximize',
                                        sampler=optuna.samplers.TPESampler(seed=None))  # random seed for diverse trials
            study.optimize(_objective, n_trials=OPTUNA_TRIALS,
                           timeout=120, show_progress_bar=False)

            best = study.best_params
            best['scale_pos_weight'] = scale_pos_weight
            best['eval_metric']  = 'logloss'
            best['random_state'] = 42
            best['n_jobs']       = -1
            logger.info(f"[XGB] Best Optuna params: {best}")
            logger.info(f"[XGB] Best CV AUC: {study.best_value:.4f}")

            # ── 6. Fit final XGB on train split ───────────────────────────────
            base_clf = xgb.XGBClassifier(**best)
            base_clf.fit(X_tr, y_tr)

            # ── 6b. Isotonic calibration on cal split (avoids cv='prefit') ────
            from sklearn.isotonic import IsotonicRegression
            raw_cal = base_clf.predict_proba(X_cal)[:, 1]
            calibrator = IsotonicRegression(out_of_bounds='clip')
            calibrator.fit(raw_cal, y_cal)

            # Wrap into a sklearn-compatible model for predict_proba
            calibrated = _CalibratedXGBWrapper(base_clf, calibrator)

            # ── 7. Evaluate on hold-out ───────────────────────────────────────
            from sklearn.metrics import precision_score, recall_score, f1_score

            proba = calibrated.predict_proba(X_te)[:, 1]
            preds = (proba >= 0.5).astype(int)
            auc   = float(roc_auc_score(y_te, proba))
            acc   = float(accuracy_score(y_te, preds))
            prec  = float(precision_score(y_te, preds, zero_division=0))
            rec   = float(recall_score(y_te, preds, zero_division=0))
            f1    = float(f1_score(y_te, preds, zero_division=0))

            logger.info(
                f"[XGB] Hold-out AUC={auc:.4f}  ACC={acc:.4f}  "
                f"P={prec:.4f}  R={rec:.4f}  F1={f1:.4f}"
            )

            # ── 7b. Compare old model vs new before replacing ─────────────────
            old_auc = self.training_stats.get('hold_out_auc', 0.0) if self.model else 0.0
            if self.model is not None and old_auc > 0:
                improvement = auc - old_auc
                logger.info(
                    f"[XGB] Model comparison: new_AUC={auc:.4f} old_AUC={old_auc:.4f} "
                    f"delta={improvement:+.4f}"
                )
                if improvement < -0.05:
                    logger.warning(
                        f"[XGB] New model is significantly worse (delta={improvement:.4f}) — "
                        "keeping old model. Use force=True to override."
                    )
                    # Still save stats but do not replace the model weights
                    self.training_stats['rejected_new_auc']  = round(auc, 4)
                    self.training_stats['rejected_new_reason'] = 'auc_regression'
                    return True  # training technically succeeded, model unchanged

            # ── 8. Persist ────────────────────────────────────────────────────
            self.model = calibrated
            self._shap_explainer = None   # invalidate cached explainer
            self.training_stats = {
                'model_version':      MODEL_VERSION,
                'n_features':         N_FEATURES,
                'n_samples':          len(y),
                'n_real':             n_real,
                'n_synthetic':        len(y) - n_real,
                'n_positive':         n_pos,
                'n_negative':         n_neg,
                'positive_rate':      round(n_pos / len(y) * 100, 1),
                'hold_out_auc':       round(auc, 4),
                'hold_out_accuracy':  round(acc, 4),
                'hold_out_precision': round(prec, 4),
                'hold_out_recall':    round(rec, 4),
                'hold_out_f1':        round(f1, 4),
                'best_cv_auc':        round(study.best_value, 4),
                'best_params':        best,
                'trained_at':         __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                'old_auc':            round(old_auc, 4),
            }
            self.save_model()
            # Archive versioned copy (keep last 5)
            self._archive_model()
            logger.info(
                f"[XGB] Model trained & saved — "
                f"AUC={auc:.4f}, P={prec:.4f}, R={rec:.4f}, F1={f1:.4f}, n={len(y)}"
            )
            return True

        except Exception as exc:
            logger.error(f"[XGB] train_from_leads error: {exc}", exc_info=True)
            return False

    # ── Persistence ──────────────────────────────────────────────────────────

    def save_model(self) -> None:
        try:
            payload = {
                'model':          self.model,
                'feature_names':  self.feature_names,
                'training_stats': self.training_stats,
                'model_version':  MODEL_VERSION,
                'n_features':     N_FEATURES,
            }
            with open(self.model_path, 'wb') as fh:
                pickle.dump(payload, fh, protocol=4)
            logger.info(f"[XGB] Model saved → {self.model_path}")
        except Exception as exc:
            logger.error(f"[XGB] save_model error: {exc}")

    def _archive_model(self, max_versions: int = 5) -> None:
        """Copy current model to a versioned archive file; prune oldest if > max_versions."""
        try:
            import shutil
            from datetime import datetime, timezone

            archive_dir = self.model_path.parent / 'archive'
            archive_dir.mkdir(parents=True, exist_ok=True)

            ts  = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            dst = archive_dir / f'lead_scoring_{MODEL_VERSION}_{ts}.pkl'
            shutil.copy2(self.model_path, dst)
            logger.info(f"[XGB] Model archived → {dst.name}")

            # Prune oldest archives beyond max_versions
            archives = sorted(archive_dir.glob('*.pkl'))
            for old in archives[:-max_versions]:
                old.unlink(missing_ok=True)
                logger.debug(f"[XGB] Pruned old archive: {old.name}")
        except Exception as exc:
            logger.warning(f"[XGB] _archive_model error (non-fatal): {exc}")

    def list_versions(self) -> List[dict]:
        """Return metadata for all archived model versions (newest first)."""
        archive_dir = self.model_path.parent / 'archive'
        if not archive_dir.exists():
            return []
        versions = []
        for path in sorted(archive_dir.glob('*.pkl'), reverse=True):
            try:
                with open(path, 'rb') as fh:
                    data = pickle.load(fh)
                stats = data.get('training_stats', {})
                versions.append({
                    'filename':    path.name,
                    'auc':         stats.get('hold_out_auc'),
                    'accuracy':    stats.get('hold_out_accuracy'),
                    'precision':   stats.get('hold_out_precision'),
                    'recall':      stats.get('hold_out_recall'),
                    'f1':          stats.get('hold_out_f1'),
                    'n_samples':   stats.get('n_samples'),
                    'trained_at':  stats.get('trained_at'),
                    'model_version': data.get('model_version'),
                })
            except Exception:
                versions.append({'filename': path.name, 'error': 'unreadable'})
        return versions

    def rollback(self, filename: str) -> bool:
        """Load a specific archived version as the active model. Returns True on success."""
        try:
            import shutil

            archive_dir = self.model_path.parent / 'archive'
            src = archive_dir / filename
            if not src.exists():
                logger.error(f"[XGB] Rollback file not found: {src}")
                return False

            # Backup current model before overwrite
            if self.model_path.exists():
                shutil.copy2(self.model_path, self.model_path.with_suffix('.pkl.bak'))

            shutil.copy2(src, self.model_path)
            self.load_model()
            logger.info(f"[XGB] Rolled back to: {filename}")
            return True
        except Exception as exc:
            logger.error(f"[XGB] rollback error: {exc}")
            return False

    def load_model(self) -> None:
        try:
            if not self.model_path.exists():
                logger.warning(f"[XGB] No model file at {self.model_path}")
                return

            with open(self.model_path, 'rb') as fh:
                data = pickle.load(fh)

            # Support bare-model legacy format
            if not isinstance(data, dict):
                logger.info("[XGB] Legacy model format detected — discarding (version mismatch)")
                return

            saved_version  = data.get('model_version', '')
            saved_features = data.get('n_features', 0)

            if saved_version != MODEL_VERSION or saved_features != N_FEATURES:
                logger.warning(
                    f"[XGB] Stale model: version={saved_version!r} "
                    f"features={saved_features} — discarding, retrain needed"
                )
                return

            self.model          = data.get('model')
            self.feature_names  = data.get('feature_names', FEATURE_NAMES[:])
            self.training_stats = data.get('training_stats', {})
            self._shap_explainer = None
            logger.info(
                f"[XGB] Model loaded — "
                f"AUC={self.training_stats.get('hold_out_auc', 'N/A')} "
                f"n={self.training_stats.get('n_samples', '?')}"
            )
        except Exception as exc:
            logger.error(f"[XGB] load_model error: {exc}")
            self.model = None

    def is_ready(self) -> bool:
        """Return True only when a trained, version-compatible model is in memory."""
        return self.model is not None

    # ── SHAP ─────────────────────────────────────────────────────────────────

    def _compute_shap(self, features: np.ndarray) -> Optional[np.ndarray]:
        """
        Compute SHAP values for the positive class.
        Uses TreeExplainer on the inner XGBClassifier (fast).
        Thread-safe; builds explainer lazily.
        """
        try:
            import shap

            if self.model is None:
                return None

            # Build explainer once (lazy, thread-safe)
            if self._shap_explainer is None:
                with self._shap_lock:
                    if self._shap_explainer is None:
                        # Reach inside CalibratedClassifierCV → XGBClassifier
                        inner = getattr(self.model, 'estimator', self.model)
                        self._shap_explainer = shap.TreeExplainer(inner)

            sv = self._shap_explainer.shap_values(features)
            # XGBoost binary: shap_values returns (1, n_features) array
            if isinstance(sv, list):
                sv = sv[1]       # index 1 = positive class for some versions
            return np.array(sv)
        except Exception as exc:
            logger.debug(f"SHAP compute error: {exc}")
            return None

    # ── Synthetic data helper ─────────────────────────────────────────────────

    @staticmethod
    def _load_synthetic_leads() -> List[Dict[str, Any]]:
        """Load pre-generated synthetic leads from disk."""
        try:
            import json
            synth_path = (
                Path(__file__).parent.parent.parent / 'data' / 'synthetic_leads.json'
            )
            if not synth_path.exists():
                logger.info("[XGB] Synthetic data file not found — generating now")
                from app.services.data_generator import get_generator
                gen  = get_generator()
                data = gen.generate(n=15_000)
                synth_path.parent.mkdir(parents=True, exist_ok=True)
                with open(synth_path, 'w') as fh:
                    json.dump(data, fh)
                return data

            with open(synth_path) as fh:
                data = json.load(fh)
            logger.info(f"[XGB] Loaded {len(data)} synthetic leads from {synth_path}")
            return data
        except Exception as exc:
            logger.error(f"[XGB] _load_synthetic_leads error: {exc}")
            return []
