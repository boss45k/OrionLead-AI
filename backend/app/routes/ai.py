"""
AI Engine Routes
REST endpoints for starting, stopping, and managing the AI engine.
Primary AI: Gemini 2.5 Flash with Groq fallback + rule-based last resort.
"""

# ┌──────────────────────────────────────────────────────────────────────────┐
# │                          TABLE OF CONTENTS                               │
# ├─────┬──────────────────────────────────────────────────────────────────┤ │
# │  §1 │ Imports · URL Sanitizer · Blueprint Setup                        │ │
# │  §2 │ In-Memory State  (activity log · task tracker)                   │ │
# │  §3 │ Initialization & Helpers  (AI init · data normalization)         │ │
# │  §4 │ Core AI Qualification  (qualify_lead · fast qualifier)           │ │
# │  §5 │ Engine Control Endpoints  (start · stop · restart · stats)       │ │
# │  §6 │ Feedback System Endpoints                                        │ │
# │  §7 │ Evaluation Dashboard & Lead Explanation  (SHAP)                  │ │
# │  §8 │ Lead Qualification & Logs  (single · batch · refresh)            │ │
# │  §9 │ Intelligence & Analysis  (chat · email · pipeline summary)       │ │
# │ §10 │ Social Lead Collection  (/collect-social)                        │ │
# │ §11 │ Web Lead Collection  (/collect-leads)                            │ │
# │ §12 │ Interest-Based Collection  (/collect-by-interest)                │ │
# │ §13 │ ML Model Training & Versioning  (/train-ml · /retrain)           │ │
# │ §14 │ AI Lead Enrichment  (/enrich · /enrich/batch)                    │ │
# │ §15 │ Auto-Collect Pipeline  (/collect/auto)                           │ │
# │ §16 │ Extended Multi-Source Collection  (/collect-extended)            │ │
# └─────┴──────────────────────────────────────────────────────────────────┘ │

from flask import Blueprint, request, jsonify, current_app, g
from app.exceptions import APIException
from app.utils.error_handler import handle_exceptions, success_response
from app.utils.rate_limiter import get_limiter
from app.routes.auth import token_required, admin_required, manager_or_admin_required
from app.services.advanced_ai import (
    initialize_advanced_ai,
    train_ml_model_from_leads,
)
from app.services.gemini_service import get_ai_service
from sqlalchemy.orm.attributes import flag_modified
import logging
from datetime import datetime, timezone
import os
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL SANITIZER — strip tracking redirects, cap length before DB insert
# ---------------------------------------------------------------------------
_URL_REDIRECT_HOSTS = frozenset({
    'bing.com', 'google.com', 'yahoo.com', 'duckduckgo.com',
    'yandex.com', 'yandex.ru', 'baidu.com', 'ask.com', 'ecosia.org',
    'search.yahoo.com', 'sogou.com',
    'redirect.', 'click.', 'track.', 'ad.', 'ads.',
})
_URL_REDIRECT_PATHS = ('aclick', '/adr', '/click', '/track', '/redirect',
                        'doubleclick', 'adclick', 'adserver',
                        '/search', '/search?', 'search/site')

def _sanitize_url(url: str, max_len: int = 500) -> str | None:
    """Return a clean, storable website URL or None if it looks like a tracking redirect."""
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.netloc.lower().replace('www.', '')
        path = parsed.path.lower()
        # Reject known ad/redirect domains and path patterns
        if any(rh in host for rh in _URL_REDIRECT_HOSTS):
            return None
        if any(rp in path for rp in _URL_REDIRECT_PATHS):
            return None
        # Reject URLs with very long query strings (tracking pixels, ad params)
        if len(parsed.query) > 100:
            return None
        # Truncate to column limit
        return url[:max_len] if len(url) > max_len else url
    except Exception:
        return url[:max_len] if url else None

ai_bp = Blueprint('ai', __name__, url_prefix='/api/v1/ai')
limiter = get_limiter()


@ai_bp.before_request
def _block_sub_admin():
    """Company Admins (sub_admin) have no access to the AI Engine."""
    if getattr(g, 'role', None) == 'sub_admin':
        from app.exceptions import AuthorizationError
        raise AuthorizationError(
            "Company Admins do not have access to the AI Engine. "
            "Contact the system administrator for AI operations."
        )


# ============================================================================
# § 2 · IN-MEMORY STATE — Activity Log & Task Tracker
# ============================================================================
_activity_log = []
_log_lock = threading.Lock()

# ============================================================================
# § 2 (cont.) — Collection Progress Tracker  (in-memory, per-task)
# ============================================================================
_collection_tasks = {}
_tasks_lock = threading.Lock()


def _update_task(task_id: str, **kwargs):
    """Update a collection task's progress."""
    with _tasks_lock:
        if task_id in _collection_tasks:
            _collection_tasks[task_id].update(kwargs)


def _get_task(task_id: str) -> dict:
    with _tasks_lock:
        return dict(_collection_tasks.get(task_id, {}))


def _create_task(task_id: str, platforms: list, query: str):
    with _tasks_lock:
        _collection_tasks[task_id] = {
            'id': task_id,
            'status': 'running',
            'query': query,
            'platforms': platforms,
            'total_platforms': len(platforms),
            'completed_platforms': 0,
            'current_platform': '',
            'saved': 0,
            'total_collected': 0,
            'percent': 0,
            'started_at': datetime.now(timezone.utc).isoformat(),
        }


def _cleanup_old_tasks():
    """Remove tasks older than 20 minutes."""
    with _tasks_lock:
        cutoff = datetime.now(timezone.utc).timestamp() - 1200
        to_remove = [
            tid for tid, t in _collection_tasks.items()
            if datetime.fromisoformat(t['started_at']).timestamp() < cutoff
        ]
        for tid in to_remove:
            del _collection_tasks[tid]

def _add_log(event: str, status: str = 'success', details: str = ''):
    """Add an entry to the real activity log"""
    with _log_lock:
        _activity_log.insert(0, {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event': event,
            'status': status,
            'details': details,
        })
        if len(_activity_log) > 200:
            _activity_log.pop()

# ============================================================================
# § 3 · INITIALIZATION & HELPERS  (AI init · data normalization)
# ============================================================================

# Track if we've initialized advanced AI in this process
_advanced_ai_initialized = False

def ensure_advanced_ai_initialized():
    """Ensure Advanced AI is initialized (call this at the start of each relevant endpoint)"""
    global _advanced_ai_initialized
    if not _advanced_ai_initialized:
        try:
            initialize_advanced_ai()
            logger.info("Advanced AI Stack initialized successfully")
            _advanced_ai_initialized = True
        except Exception as e:
            logger.warning(f"Advanced AI initialization warning: {str(e)}")
            _advanced_ai_initialized = True  # Mark as attempted to avoid repeated failures


# External AI Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
USE_EXTERNAL_AI = GEMINI_API_KEY or GROQ_API_KEY or ANTHROPIC_API_KEY


@ai_bp.route('/debug-ai-state', methods=['GET'])
@token_required
@admin_required
def debug_ai_state():
    """Debug endpoint to see what AI components are initialized"""
    import app.services.advanced_ai as adv_ai
    
    return jsonify({
        'ollama_client': f"{adv_ai._ollama_client}" if adv_ai._ollama_client else None,
        'spacy_nlp': f"{adv_ai._spacy_nlp}" if adv_ai._spacy_nlp else None,
        'ml_model': f"{adv_ai._ml_model}" if adv_ai._ml_model else None,
        'faiss_dedup': f"{adv_ai._faiss_dedup}" if adv_ai._faiss_dedup else None,
        'embedder': f"{adv_ai._embedder}" if adv_ai._embedder else None,
        'all_initialized': all([adv_ai._ollama_client, adv_ai._spacy_nlp, adv_ai._ml_model, adv_ai._faiss_dedup, adv_ai._embedder])
    })


# AI Engine state — persistent across requests
AI_ENGINE_STATE = {
    'running': True,
    'started_at': datetime.now().isoformat(),
    'processed_count': 0,
    'qualified_count': 0,
    'average_score': 0.0,
    'external_ai_enabled': USE_EXTERNAL_AI,
    'advanced_ai_enabled': True,
    'ai_provider': 'Gemini',
    'fallback_chain': 'Gemini → Groq → Smart Rules',
}


# ---------------------------------------------------------------------------
# Shared data-normalization helpers used across all save paths
# ---------------------------------------------------------------------------
def _norm_industry(raw: str) -> str:
    """Normalize industry string: replace underscores/hyphens, title-case if all-lower."""
    if not raw:
        return ''
    s = raw.replace('_', ' ').replace('-', ' ').strip()
    # Only title-case when the source is all-lowercase (preserve "B2B SaaS", "SaaS" etc.)
    if s == s.lower():
        s = s.title()
    return s


_QUERY_INDUSTRY_MAP = [
    (['fintech', 'financial technology', 'payments', 'neobank', 'banking'],        'Finance & Fintech'),
    (['healthtech', 'health tech', 'healthcare', 'medtech', 'biotech', 'pharma'],  'Healthcare & MedTech'),
    (['edtech', 'education', 'e-learning', 'elearning', 'online learning'],         'Education & EdTech'),
    (['artificial intelligence', 'machine learning', 'deep learning', 'generative ai', 'llm', ' nlp'], 'AI & Data'),
    (['cybersecurity', 'infosec', 'cyber security', 'information security'],        'Cybersecurity'),
    (['ecommerce', 'e-commerce', 'shopify', 'online retail'],                       'E-commerce & Retail'),
    (['logistics', 'supply chain', 'shipping', 'freight', 'last-mile'],             'Logistics & Supply Chain'),
    (['real estate', 'proptech', 'property management', 'realty'],                  'Real Estate & PropTech'),
    (['hrtech', 'human resources', 'recruitment', 'recruiting', 'talent acquisition'], 'HR & Talent'),
    (['legaltech', 'lawtech', 'law firm', 'legal services'],                        'Legal & LegalTech'),
    (['martech', 'digital marketing', 'advertising technology', ' seo '],           'Marketing & AdTech'),
    (['insurtech', 'insurance technology'],                                          'Insurance & InsurTech'),
    (['agritech', 'agtech', 'agriculture technology', 'farming technology'],        'Agriculture & AgriTech'),
    (['cleantech', 'renewable energy', 'solar energy', 'climate tech'],             'Energy & CleanTech'),
    (['telecom', 'telecommunications', 'network operator'],                         'Telecommunications'),
    (['gaming', 'game development', 'esports'],                                     'Gaming'),
    (['media', 'content creation', 'publishing', 'news media'],                    'Media & Publishing'),
    (['construction', 'architecture', 'building materials'],                        'Construction'),
    (['travel', 'hospitality', 'hotel technology', 'tourism'],                     'Travel & Hospitality'),
    (['saas', 'software as a service', 'b2b software'],                             'Software / SaaS'),
    (['software', 'tech startup', 'developer tools', 'cloud platform'],             'Technology'),
]

_BIZ_TYPE_TO_INDUSTRY = {
    'b2b_saas':   'Software / SaaS',
    'b2c_saas':   'Software',
    'agency':     'Marketing & Agencies',
    'marketplace':'Marketplace',
    'ecommerce':  'E-commerce & Retail',
}

_INTEREST_STOPWORDS = frozenset({
    'companies', 'company', 'businesses', 'business', 'startup', 'startups',
    'firms', 'firm', 'agencies', 'agency', 'organizations', 'organization',
    'people', 'persons', 'professionals', 'leads', 'lead', 'contacts',
    'in', 'of', 'the', 'a', 'an', 'and', 'or', 'with', 'by', 'to', 'from',
    'at', 'on', 'is', 'are', 'for', 'that', 'this', 'tech', 'technology',
})


def _infer_industry_and_interests(query: str, lead_data: dict):
    """Infer missing industry / interests from query + intelligence classification."""
    import re as _re
    q = query.lower()

    # 1. Try business_type from classifier first
    inferred_industry = ''
    _btype = ((lead_data.get('_company_intelligence') or {})
              .get('classification') or {}).get('business_type', '')
    if _btype and _btype != 'unknown':
        inferred_industry = _BIZ_TYPE_TO_INDUSTRY.get(_btype, '')

    # 2. Fall back to query keyword scan
    if not inferred_industry:
        for keywords, label in _QUERY_INDUSTRY_MAP:
            if any(kw in q for kw in keywords):
                inferred_industry = label
                break

    # 3. Extract meaningful terms from query for interests
    tokens = _re.split(r'[\s,\(\)/]+', query.strip())
    seen: set = set()
    inferred_interests: list = []
    for tok in tokens:
        t = tok.strip().lower().rstrip('s')
        if len(t) < 3 or t in _INTEREST_STOPWORDS or tok.strip().lower() in _INTEREST_STOPWORDS:
            continue
        key = tok.strip().lower()
        if key not in seen:
            seen.add(key)
            inferred_interests.append(tok.strip())
        if len(inferred_interests) >= 5:
            break

    return inferred_industry, inferred_interests


def _classify_email_type(email: str, existing_type: str = '') -> str:
    """Re-classify email_type when the scraper produced 'unknown'."""
    if existing_type and existing_type not in ('unknown', ''):
        return existing_type
    if not email or '@' not in email:
        return existing_type or 'missing'
    from app.services.lead_quality_engine import _is_generic_email, _is_free_email
    if _is_generic_email(email):
        return 'generic'
    if _is_free_email(email):
        return 'free'
    return 'company'


# ---------------------------------------------------------------------------
# Shared status derivation — single source of truth for score → DB status
# ---------------------------------------------------------------------------
def _derive_status(result: dict) -> str:
    """Map AI result to DB status using the AI category as the authority.

    Category from qualification agent / ML layer:
      Hot        → 'hot'
      Warm       → 'warm'
      Cold / Unqualified / anything else → 'cold'
    """
    cat = (result.get('category') or '').lower().strip()
    if cat == 'hot':
        return 'hot'
    if cat == 'warm':
        return 'warm'
    return 'cold'


# ============================================================================
# § 4 · CORE AI QUALIFICATION  (ML decision layer · fast qualifier)
# ---------------------------------------------------------------------------
# ML Decision Layer — replaces fixed-weight parallel execution
# ============================================================================
def qualify_lead_with_external_ai(lead_data, lead_id=None):
    """
    Intelligent qualification via MLDecisionLayer.

    Routing tiers (decided per-lead based on data completeness + ML confidence):
      TIER_1_ML_ONLY    → Agent + ML only        (high completeness, high ML conf)
      TIER_2_ML_GROQ    → Agent + ML + Groq      (medium completeness/confidence)
      TIER_3_FULL       → Agent + ML + Gemini    (default: low confidence or sparse)
      TIER_4_LLM_HEAVY  → LLM primary            (very sparse data, cold start)

    Dynamic weights: derived from per-provider MAE tracked over last 200 samples.
    Quality gate: LLM responses are evaluated before their score is accepted.
    Logging: every prediction is appended to data/training_dataset.jsonl.
    """
    from app.services.ml_decision_layer import get_decision_layer
    try:
        dl = get_decision_layer()
        tier, result = dl.qualify(lead_data, lead_id=lead_id)
        logger.info(
            f"[MLRouter] {lead_data.get('name', '?')} → "
            f"tier={tier} score={result['score']} "
            f"providers={result.get('ai_provider', '?')} "
            f"latency={result.get('latency_ms', '?')}ms"
        )
        return result
    except Exception as e:
        logger.error(f"MLDecisionLayer failed, using emergency fallback: {e}", exc_info=True)
        # Emergency fallback: bare rule-based agent only
        try:
            from app.services.qualification_agent import QualificationAgent
            agent = QualificationAgent()
            r = agent.qualify_lead(lead_data)
            return {
                'score': r.score, 'category': r.category,
                'confidence': r.confidence, 'ai_provider': 'QualificationAgent (fallback)',
                'routing_tier': 'emergency_fallback',
            }
        except Exception:
            return {
                'score': 50, 'category': 'Warm', 'confidence': 0.3,
                'ai_provider': 'None', 'routing_tier': 'emergency_fallback',
            }


_FAST_BATCH_THRESHOLD = 15  # above this, skip LLM API calls entirely

# ── AI settings persistence ───────────────────────────────────────────────────
_SETTINGS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'ai_settings.json')
)
_SETTINGS_DEFAULTS: dict = {
    'confidence_threshold': 75,
    'batch_size':           100,
    'max_workers':          4,
    'processing_speed':     'normal',
    'auto_qualify':         True,
}

def _load_ai_settings() -> dict:
    """Read settings from disk; fall back to defaults on any error."""
    try:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            return {**_SETTINGS_DEFAULTS, **saved}
    except Exception:
        pass
    return dict(_SETTINGS_DEFAULTS)

def _save_ai_settings(data: dict) -> None:
    """Persist only recognised keys; atomic write via temp file."""
    current = _load_ai_settings()
    for key in _SETTINGS_DEFAULTS:
        if key in data:
            current[key] = data[key]
    os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    tmp = _SETTINGS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(current, f, indent=2)
    os.replace(tmp, _SETTINGS_PATH)


def _qualify_fast(lead_data: dict) -> dict:
    """Score a lead using QualificationAgent + ML model only — zero LLM API calls.

    Used for large batches so we never hit Groq/Gemini rate limits.
    Blend weight for ML is dynamic (15-45%) based on training dataset size so an
    under-trained model cannot distort the rule-based agent's scores.
    """
    from app.services.qualification_agent import QualificationAgent
    from app.services.ml_model import extract_features
    from app.services.advanced_ai import get_ml_model

    agent = QualificationAgent()
    r = agent.qualify_lead(lead_data)
    agent_score = float(r.score)

    ml_score = None
    try:
        ml = get_ml_model()  # cached singleton — no per-call disk I/O
        if ml is not None and ml.model is not None:
            features = extract_features(lead_data)
            raw = ml.predict(features)
            if raw is not None:
                ml_score = float(raw)
    except Exception as _ml_err:
        logger.debug(f"_qualify_fast: ML skipped ({_ml_err})")

    if ml_score is not None:
        # Dynamic weighting driven by real labeled samples, not total sample count.
        # The model is trained mostly on synthetic data — until we have enough real
        # outcome labels (converted/cold/contacted), ML predictions are unreliable
        # and must be kept to a tiny weight that cannot materially hurt rule scores.
        try:
            from app.services.ml_decision_layer import DATASET_PATH
            import json as _json
            n_labeled = 0
            if DATASET_PATH.exists():
                for _line in DATASET_PATH.read_text().splitlines():
                    try:
                        if _json.loads(_line).get('label') is not None:
                            n_labeled += 1
                    except Exception:
                        pass
        except Exception:
            n_labeled = 0

        # Gate: only blend ML once we have meaningful real feedback
        if n_labeled >= 50:
            ml_weight = 0.40   # trusted model — significant influence
        elif n_labeled >= 20:
            ml_weight = 0.20   # partially trained — light influence
        elif n_labeled >= 5:
            ml_weight = 0.08   # barely trained — nearly invisible
        else:
            ml_weight = 0.0    # no real labels yet — rules only

        if ml_weight > 0:
            blended = (1.0 - ml_weight) * agent_score + ml_weight * ml_score
            # Floor: ML cannot suppress agent score by more than 15 pts
            final = round(max(blended, agent_score - 15))
        else:
            final = round(agent_score)
    else:
        final = round(agent_score)

    category = 'Hot' if final >= 80 else 'Warm' if final >= 60 else 'Cold'
    provider = 'QualificationAgent+ML' if (ml_score is not None and ml_weight > 0) else 'QualificationAgent'
    if isinstance(r.reasoning, str):
        reasoning = r.reasoning
    elif isinstance(r.reasoning, dict):
        parts = [f"{k}: {v}" for k, v in r.reasoning.items() if v]
        reasoning = '; '.join(parts)
    else:
        reasoning = ''

    return {
        'score':         final,
        'category':      category,
        'confidence':    float(r.confidence),
        'ai_provider':   provider,
        'routing_tier':  'fast_batch',
        'reasoning':     reasoning,
    }


# ============================================================================
# § 5 · ENGINE CONTROL ENDPOINTS  (start · stop · restart · stats · model)
# ============================================================================

@ai_bp.route('/start', methods=['POST'])
@token_required
@admin_required
@handle_exceptions
def start_engine():
    """Start the AI engine"""
    try:
        AI_ENGINE_STATE['running'] = True
        AI_ENGINE_STATE['started_at'] = datetime.now().isoformat()
        
        logger.info("AI Engine started")
        return jsonify({
            'status': 'success',
            'message': 'AI Engine started successfully',
            'data': AI_ENGINE_STATE
        }), 200
    except Exception as e:
        logger.error(f"Error starting AI engine: {str(e)}")
        raise APIException(f"Failed to start AI engine: {str(e)}", status_code=500)


@ai_bp.route('/stop', methods=['POST'])
@token_required
@admin_required
@handle_exceptions
def stop_engine():
    """Stop the AI engine"""
    try:
        AI_ENGINE_STATE['running'] = False
        
        logger.info("AI Engine stopped")
        return jsonify({
            'status': 'success',
            'message': 'AI Engine stopped successfully',
            'data': AI_ENGINE_STATE
        }), 200
    except Exception as e:
        logger.error(f"Error stopping AI engine: {str(e)}")
        raise APIException(f"Failed to stop AI engine: {str(e)}", status_code=500)


@ai_bp.route('/restart', methods=['POST'])
@token_required
@admin_required
@handle_exceptions
def restart_engine():
    """Restart the AI engine"""
    try:
        AI_ENGINE_STATE['running'] = True
        AI_ENGINE_STATE['started_at'] = datetime.now().isoformat()
        
        logger.info("AI Engine restarted")
        return jsonify({
            'status': 'success',
            'message': 'AI Engine restarted successfully',
            'data': AI_ENGINE_STATE
        }), 200
    except Exception as e:
        logger.error(f"Error restarting AI engine: {str(e)}")
        raise APIException(f"Failed to restart AI engine: {str(e)}", status_code=500)


@ai_bp.route('/stats', methods=['GET'])
@token_required
@handle_exceptions
def get_stats():
    try:
        from app.models.models import db, Lead, User as _User
        from sqlalchemy import func

        # Apply same ownership rules as the leads list
        def _own(q):
            if g.role == 'manager':
                mgr = _User.query.get(g.user_id)
                co  = (mgr.company or '').strip().lower() if mgr else ''
                if co:
                    tids = [r.id for r in _User.query.filter(
                        db.func.lower(db.func.trim(_User.company)) == co
                    ).with_entities(_User.id).all()]
                    return q.filter(Lead.collected_by.in_(tids))
                return q.filter(Lead.collected_by == g.user_id)
            if g.role != 'admin':
                return q.filter(Lead.collected_by == g.user_id)
            return q

        base = _own(Lead.query)
        total = base.count()
        hot   = base.filter(Lead.status == 'hot').count()
        warm  = base.filter(Lead.status == 'warm').count()
        cold  = base.filter(Lead.status == 'cold').count()
        qualified = hot + warm
        avg_score_row = _own(db.session.query(func.avg(Lead.qualification_score))).scalar()
        avg_score = float(avg_score_row) if avg_score_row else 0.0
        with_email    = base.filter(Lead.email.isnot(None),        Lead.email != '').count()
        with_phone    = base.filter(Lead.phone.isnot(None),        Lead.phone != '').count()
        with_linkedin = base.filter(Lead.linkedin_url.isnot(None), Lead.linkedin_url != '').count()

        # Country / industry breakdown
        country_rows = _own(db.session.query(Lead.country, func.count(Lead.id))).filter(
            Lead.country.isnot(None), Lead.country != ''
        ).group_by(Lead.country).order_by(func.count(Lead.id).desc()).limit(10).all()
        industry_rows = _own(db.session.query(Lead.industry, func.count(Lead.id))).filter(
            Lead.industry.isnot(None), Lead.industry != ''
        ).group_by(Lead.industry).order_by(func.count(Lead.id).desc()).limit(10).all()

        ai_svc = get_ai_service()

        stats = {
            'total_leads': total,
            'hot': hot,
            'warm': warm,
            'cold': cold,
            'total_qualified': qualified,
            'average_score': round(avg_score, 1),
            'with_email': with_email,
            'with_phone': with_phone,
            'with_linkedin': with_linkedin,
            'data_completeness': round((with_email / total * 100) if total else 0, 1),
            'by_country': {r[0]: r[1] for r in country_rows},
            'by_industry': {r[0]: r[1] for r in industry_rows},
            'running': AI_ENGINE_STATE['running'],
            'started_at': AI_ENGINE_STATE['started_at'],
            'processed_count': AI_ENGINE_STATE['processed_count'],
            'ai_provider': ai_svc.provider_name,
            'ai_available': ai_svc.is_available,
            'ai_model': ai_svc.model_name,
            'external_ai_enabled': bool(USE_EXTERNAL_AI),
            'external_ai_config': {
                'gemini': bool(GEMINI_API_KEY),
                'groq': bool(GROQ_API_KEY),
                'anthropic': bool(ANTHROPIC_API_KEY),
            },
        }

        # Attach ML model training stats — only if already initialized.
        # Calling get_ml_model() when _initialized=False triggers the full
        # torch/sentence-transformers import chain (10-30 s). Use
        # is_ml_model_ready() as a guard so this stat is simply absent on
        # the first page load (pre-warm thread fills it in the background).
        try:
            from app.services.advanced_ai import is_ml_model_ready, get_ml_model
            if is_ml_model_ready():
                ml = get_ml_model()
                if ml and ml.training_stats:
                    ts = ml.training_stats
                    stats['ml_model'] = {
                        'auc':        ts.get('hold_out_auc'),
                        'accuracy':   ts.get('hold_out_accuracy'),
                        'f1':         ts.get('hold_out_f1'),
                        'n_samples':  ts.get('n_samples'),
                        'trained_at': ts.get('trained_at'),
                        'version':    ts.get('model_version'),
                    }
        except Exception:
            pass

        return jsonify({
            'status': 'success',
            'stats': stats
        }), 200
    except Exception as e:
        logger.error(f"Error fetching AI stats: {str(e)}")
        raise APIException(f"Failed to fetch AI stats: {str(e)}", status_code=500)


@ai_bp.route('/quality-report', methods=['GET'])
@token_required
@manager_or_admin_required
@handle_exceptions
def quality_report():
    """
    Return per-provider accuracy metrics, dynamic weights, and dataset stats.
    Used by the dashboard to monitor ML health.
    """
    try:
        from app.services.ml_decision_layer import get_decision_layer, QUALITY_LOG_PATH
        dl = get_decision_layer()
        report = dl.quality_report()

        # Attach recent quality log tail (last 20 entries)
        recent_quality = []
        try:
            if QUALITY_LOG_PATH.exists():
                lines = QUALITY_LOG_PATH.read_text().splitlines()
                for line in lines[-20:]:
                    if line.strip():
                        recent_quality.append(json.loads(line))
        except Exception:
            pass

        return jsonify({
            'status': 'success',
            'report': report,
            'recent_quality_events': list(reversed(recent_quality)),
        }), 200
    except Exception as e:
        logger.error(f"quality_report error: {e}")
        raise APIException(f"Failed to get quality report: {e}", status_code=500)


@ai_bp.route('/retrain-auto', methods=['POST'])
@token_required
@admin_required
@handle_exceptions
def retrain_auto():
    """
    Trigger an automatic ML model retrain if enough labeled data exists.
    Safe to call repeatedly — no-ops when insufficient data.
    Body (optional): {"min_new_labeled": 20}
    """
    try:
        body = request.get_json(silent=True) or {}
        min_labeled = int(body.get('min_new_labeled', 20))

        from app.services.ml_decision_layer import auto_retrain_if_ready
        result = auto_retrain_if_ready(min_labeled)

        return jsonify({
            'status': 'success',
            **result,
        }), 200
    except Exception as e:
        logger.error(f"retrain_auto error: {e}")
        raise APIException(f"Auto-retrain failed: {e}", status_code=500)


@ai_bp.route('/dataset-stats', methods=['GET'])
@token_required
@handle_exceptions
def dataset_stats():
    """Return training dataset statistics (total, labeled, positives/negatives)."""
    try:
        from app.services.ml_decision_layer import get_decision_layer
        stats = get_decision_layer().dataset.dataset_stats()
        return jsonify({'status': 'success', 'stats': stats}), 200
    except Exception as e:
        raise APIException(f"Dataset stats failed: {e}", status_code=500)


@ai_bp.route('/model-status', methods=['GET'])
@token_required
@manager_or_admin_required
@handle_exceptions
def model_status():
    """
    Return the current status of the ML scoring model.
    Indicates whether the model file exists, when it was trained,
    and whether it is currently loaded in memory.
    """
    try:
        import os
        from pathlib import Path
        from app.services.advanced_ai import get_ml_model

        model_path = Path(os.getenv('MODEL_PATH', './models/')) / 'lead_scoring_sklearn.pkl'
        file_exists = model_path.exists()
        trained_at  = None
        if file_exists:
            import datetime as _dt
            mtime = model_path.stat().st_mtime
            trained_at = _dt.datetime.fromtimestamp(mtime, tz=_dt.timezone.utc).isoformat()

        ml_model = get_ml_model()
        model_loaded = ml_model is not None and ml_model.model is not None

        if not file_exists:
            logger.warning("[ModelStatus] No model file found — ML layer disabled until training completes")

        return jsonify({
            'status':       'success',
            'model_loaded': model_loaded,
            'model_file_exists': file_exists,
            'model_path':   str(model_path),
            'trained_at':   trained_at,
            'n_features':   getattr(ml_model, 'n_features', None) if ml_model else None,
        }), 200
    except Exception as e:
        logger.error(f"model_status error: {e}")
        raise APIException(f"Failed to get model status: {e}", status_code=500)


@ai_bp.route('/feature-importance', methods=['GET'])
@token_required
@manager_or_admin_required
@handle_exceptions
def feature_importance():
    """
    Return global feature importance aggregated from recent SHAP values.

    Pulls the last N predictions from training_dataset.jsonl, extracts
    the stored feature vectors, runs SHAP on them, and returns a ranked
    list with human-readable labels.

    Query params:
        n  (int, default 100) — number of recent records to include
    """
    try:
        n = min(int(request.args.get('n', 100)), 500)

        from app.services.ml_decision_layer import get_decision_layer, DATASET_PATH
        from app.services.advanced_ai import get_ml_model
        from app.services.ml_model import FEATURE_LABELS

        dl = get_decision_layer()
        ml_model = get_ml_model()

        if ml_model is None or ml_model.model is None:
            return jsonify({
                'status':  'error',
                'message': 'ML model not loaded — run /api/v1/ai/train first',
            }), 503

        # ── Collect feature vectors from JSONL ──────────────────────────────
        import json as _json
        import numpy as _np

        records = []
        try:
            if DATASET_PATH.exists():
                lines = DATASET_PATH.read_text().splitlines()
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        rec = _json.loads(line)
                        feats = rec.get('features', [])
                        if len(feats) == 30:
                            records.append(feats)
                            if len(records) >= n:
                                break
                    except _json.JSONDecodeError:
                        pass
        except Exception as _e:
            logger.warning(f"feature_importance: failed to read dataset: {_e}")

        if not records:
            return jsonify({
                'status':  'error',
                'message': 'No prediction records found — qualify some leads first',
            }), 404

        X = _np.array(records, dtype=_np.float32)

        # ── SHAP global importance ──────────────────────────────────────────
        # ml_model.model is a _CalibratedXGBWrapper; SHAP needs the raw XGB clf
        raw_clf = getattr(ml_model.model, 'clf', ml_model.model)
        try:
            import shap
            explainer = shap.TreeExplainer(raw_clf)
            shap_values = explainer.shap_values(X)
            # shap_values shape: (n_samples, n_features) or list for multi-class
            if isinstance(shap_values, list):
                shap_values = shap_values[1]  # positive class
            mean_abs_shap = _np.abs(shap_values).mean(axis=0)
        except Exception as _shap_err:
            logger.warning(f"feature_importance: SHAP failed, falling back to model importances: {_shap_err}")
            # Fallback: raw XGB has feature_importances_ (use getattr to satisfy Pylance)
            _fi = getattr(raw_clf, 'feature_importances_', None)
            if _fi is None:
                return jsonify({'status': 'error', 'message': 'SHAP unavailable and model has no feature_importances_'}), 503
            mean_abs_shap = _fi

        # ── Build ranked output ─────────────────────────────────────────────
        importance_list = []
        for idx, importance in enumerate(mean_abs_shap):
            meta = FEATURE_LABELS.get(idx, {'name': f'feature_{idx}', 'label': f'Feature {idx}'})
            importance_list.append({
                'rank':       0,  # filled below
                'index':      idx,
                'name':       meta['name'],
                'label':      meta['label'],
                'importance': round(float(importance), 5),
            })

        importance_list.sort(key=lambda x: x['importance'], reverse=True)
        for i, item in enumerate(importance_list):
            item['rank'] = i + 1

        return jsonify({
            'status':        'success',
            'n_samples_used': len(records),
            'features':      importance_list,
            'top_5':         [f['label'] for f in importance_list[:5]],
        }), 200

    except Exception as e:
        logger.error(f"feature_importance error: {e}")
        raise APIException(f"Failed to compute feature importance: {e}", status_code=500)


# ============================================================================
# § 6 · FEEDBACK SYSTEM ENDPOINTS
# ============================================================================

@ai_bp.route('/feedback', methods=['POST'])
@token_required
@handle_exceptions
def submit_feedback():
    """
    Submit outcome feedback for a lead.

    Stores the real outcome to:
      - LeadOutcome DB table (durable, versioned, used for retraining)
      - JSONL training dataset file (backward compat with MLDecisionLayer)
      - FeedbackAccuracyTracker (per-source / per-channel MAE + precision/recall)

    Body:
      lead_id       int      required
      outcome       str      required  converted|contacted|rejected|unqualified|cold|warm|hot
      label_source  str      optional  business_outcome|user_feedback|ai_prediction
                                       default: user_feedback
      feedback_notes str     optional  free-text reason from sales team

    Outcomes:
      converted   — lead became a customer         → binary=1
      contacted   — engaged and responded          → binary=1
      hot         — strong buying signals          → binary=1
      rejected    — explicitly declined            → binary=0
      unqualified — wrong fit                      → binary=0
      cold        — no response after outreach     → binary=0
      warm        — responding, not yet converted  → binary=None (soft)
    """
    try:
        body         = request.get_json(silent=True) or {}
        lead_id      = body.get('lead_id')
        outcome      = str(body.get('outcome', '')).lower().strip()
        label_source = str(body.get('label_source', 'user_feedback')).lower().strip()
        feedback_notes = body.get('feedback_notes')

        # ── 1. Input validation ───────────────────────────────────────────────
        if not lead_id or not isinstance(lead_id, int):
            return jsonify({'status': 'error', 'message': 'lead_id (int) is required'}), 400

        valid_outcomes = ('converted', 'contacted', 'rejected', 'unqualified',
                          'cold', 'warm', 'hot')
        if outcome not in valid_outcomes:
            return jsonify({
                'status': 'error',
                'message': f'outcome must be one of: {valid_outcomes}',
            }), 400

        valid_sources = ('business_outcome', 'user_feedback', 'ai_prediction')
        if label_source not in valid_sources:
            return jsonify({
                'status': 'error',
                'message': f'label_source must be one of: {valid_sources}',
            }), 400

        # ── 2. Verify lead exists ─────────────────────────────────────────────
        from app.models.models import db, Lead, LeadOutcome
        from flask import g
        lead = db.session.get(Lead, lead_id)
        if not lead:
            return jsonify({'status': 'error', 'message': f'Lead {lead_id} not found'}), 404

        recorded_by   = getattr(g, 'user_id', None)
        user_role     = getattr(g, 'role', 'user')
        is_privileged = user_role in ('admin', 'manager')

        # Managers/admins → auto-approved; regular users → pending review
        approval_status = 'approved' if is_privileged else 'pending'
        ml_score_at_submit = lead.qualification_score

        # ── 3. Persist label to DB ────────────────────────────────────────────
        from datetime import datetime, timezone as _tz
        now = datetime.now(_tz.utc)

        existing = LeadOutcome.query.filter_by(lead_id=lead_id).first()
        if existing:
            existing.outcome         = outcome
            existing.label_source    = label_source
            existing.binary_label    = LeadOutcome.derive_binary(outcome)
            existing.feedback_notes  = feedback_notes
            existing.recorded_by     = recorded_by
            existing.approval_status = approval_status
            existing.approved_by     = recorded_by if is_privileged else None
            existing.approved_at     = now         if is_privileged else None
            existing.approval_note   = None
            existing.updated_at      = now
            outcome_record = existing
        else:
            outcome_record = LeadOutcome(
                lead_id         = lead_id,
                outcome         = outcome,
                label_source    = label_source,
                binary_label    = LeadOutcome.derive_binary(outcome),
                feedback_notes  = feedback_notes,
                recorded_by     = recorded_by,
                approval_status = approval_status,
                approved_by     = recorded_by if is_privileged else None,
                approved_at     = now         if is_privileged else None,
            )
            db.session.add(outcome_record)
        db.session.commit()

        labeled = 0
        model_vs_reality = {}

        # ── 4. Only run ML pipeline for approved labels ───────────────────────
        if approval_status == 'approved':
            from app.services.ml_decision_layer import get_decision_layer
            dl = get_decision_layer()
            labeled = dl.on_lead_status_change(
                lead_id        = lead_id,
                new_status     = outcome,
                label_source   = label_source,
                feedback_notes = feedback_notes,
                recorded_by    = recorded_by,
            )
            model_vs_reality = dl.feedback_tracker.model_vs_reality(lead_id)

            # Background auto-retrain check
            def _background_retrain(app_ctx):
                with app_ctx:
                    try:
                        from app.services.ml_decision_layer import auto_retrain_if_ready
                        result = auto_retrain_if_ready(min_new_labeled=20)
                        if result.get('retrained'):
                            logger.info(f"[feedback] auto-retrain triggered: {result.get('stats')}")
                    except Exception as _re:
                        logger.debug(f"[feedback] auto-retrain skipped: {_re}")
            threading.Thread(
                target=_background_retrain,
                args=(current_app.app_context(),),
                daemon=True,
            ).start()

        logger.info(
            "feedback_submitted",
            extra={
                'event':           'feedback_submitted',
                'user_id':         recorded_by,
                'lead_id':         lead_id,
                'outcome':         outcome,
                'approval_status': approval_status,
            },
        )

        # ── 5. Build response ─────────────────────────────────────────────────
        response_data: dict = {
            'lead_id':            lead_id,
            'outcome':            outcome,
            'label_source':       label_source,
            'binary_label':       LeadOutcome.derive_binary(outcome),
            'approval_status':    approval_status,
            'pending_review':     approval_status == 'pending',
            'records_labeled':    labeled,
            'ml_score_at_submit': ml_score_at_submit,
            'model_vs_reality':   model_vs_reality,
        }
        msg = ('Feedback submitted — awaiting manager approval'
               if approval_status == 'pending'
               else 'Feedback submitted and approved')
        return success_response(message=msg, **response_data)

    except Exception as e:
        logger.error(f"submit_feedback error: {e}", exc_info=True)
        raise APIException(f"Feedback submission failed: {e}", status_code=500)


@ai_bp.route('/feedback/pending', methods=['GET'])
@token_required
@manager_or_admin_required
@handle_exceptions
def get_pending_feedback():
    """Return all labels awaiting manager approval."""
    from app.models.models import db, LeadOutcome, Lead, User
    records = (
        LeadOutcome.query
        .filter_by(approval_status='pending')
        .order_by(LeadOutcome.recorded_at.desc())
        .all()
    )
    lead_ids = [r.lead_id for r in records]
    leads_map = {l.id: l for l in Lead.query.filter(Lead.id.in_(lead_ids)).all()} if lead_ids else {}
    user_ids  = [r.recorded_by for r in records if r.recorded_by]
    users_map = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}

    items = []
    for r in records:
        lead = leads_map.get(r.lead_id)
        submitter = users_map.get(r.recorded_by)
        items.append({
            **r.to_dict(),
            'lead_name':       lead.name    if lead else None,
            'lead_company':    lead.company if lead else None,
            'lead_email':      lead.email   if lead else None,
            'submitted_by_name':  submitter.full_name if submitter else None,
            'submitted_by_email': submitter.email     if submitter else None,
        })

    return jsonify({'status': 'success', 'data': items, 'count': len(items)}), 200


@ai_bp.route('/feedback/<int:outcome_id>/approve', methods=['POST'])
@token_required
@manager_or_admin_required
@handle_exceptions
def approve_feedback(outcome_id):
    """Approve a pending label — it now counts toward ML training."""
    from app.models.models import db, LeadOutcome
    from flask import g
    from datetime import datetime, timezone as _tz
    body = request.get_json(silent=True) or {}

    record = db.session.get(LeadOutcome, outcome_id)
    if not record:
        return jsonify({'status': 'error', 'message': 'Outcome record not found'}), 404
    if record.approval_status == 'approved':
        return jsonify({'status': 'error', 'message': 'Already approved'}), 409

    record.approval_status = 'approved'
    record.approved_by     = getattr(g, 'user_id', None)
    record.approved_at     = datetime.now(_tz.utc)
    record.approval_note   = body.get('note', '').strip() or None
    db.session.commit()

    # Now feed into ML pipeline
    try:
        from app.services.ml_decision_layer import get_decision_layer
        dl = get_decision_layer()
        dl.on_lead_status_change(
            lead_id      = record.lead_id,
            new_status   = record.outcome,
            label_source = record.label_source,
            recorded_by  = record.recorded_by,
        )
    except Exception as _e:
        logger.warning(f"approve_feedback: ML pipeline error: {_e}")

    logger.info(f"Label {outcome_id} approved by {getattr(g, 'email', '?')} for lead {record.lead_id}")
    return jsonify({'status': 'success', 'message': 'Label approved — counts toward ML training', 'data': record.to_dict()}), 200


@ai_bp.route('/feedback/<int:outcome_id>/reject', methods=['POST'])
@token_required
@manager_or_admin_required
@handle_exceptions
def reject_feedback(outcome_id):
    """Reject a pending label — excluded from ML training, user can re-label."""
    from app.models.models import db, LeadOutcome
    from flask import g
    from datetime import datetime, timezone as _tz
    body = request.get_json(silent=True) or {}

    record = db.session.get(LeadOutcome, outcome_id)
    if not record:
        return jsonify({'status': 'error', 'message': 'Outcome record not found'}), 404
    if record.approval_status == 'rejected':
        return jsonify({'status': 'error', 'message': 'Already rejected'}), 409

    record.approval_status = 'rejected'
    record.approved_by     = getattr(g, 'user_id', None)
    record.approved_at     = datetime.now(_tz.utc)
    record.approval_note   = body.get('note', '').strip() or None
    db.session.commit()

    logger.info(f"Label {outcome_id} rejected by {getattr(g, 'email', '?')} for lead {record.lead_id}")
    return jsonify({'status': 'success', 'message': 'Label rejected', 'data': record.to_dict()}), 200


@ai_bp.route('/feedback-accuracy', methods=['GET'])
@token_required
@handle_exceptions
def get_feedback_accuracy():
    """
    Full accuracy report showing how well each scoring component predicted
    real outcomes, broken down by:
      - provider (ml / rule / llm)
      - label_source (business_outcome / user_feedback / ai_prediction)
      - lead_source channel (linkedin / web / facebook / etc.)

    Also returns current dataset stats from both the DB and the JSONL file.

    No body required. Query params:
      lead_id  int  optional — include per-lead model-vs-reality comparison
    """
    try:
        from app.services.ml_decision_layer import get_decision_layer
        from app.services.dataset_manager import get_dataset_manager

        dl      = get_decision_layer()
        manager = get_dataset_manager()

        # Per-provider, per-source accuracy
        accuracy_report = dl.feedback_tracker.accuracy_report()

        # DB dataset health
        db_stats = manager.get_dataset_stats()

        # JSONL dataset stats
        jsonl_stats = dl.dataset.dataset_stats()

        # Dynamic provider weights (used in scoring)
        dynamic_weights = dl.tracker.provider_weights(['agent', 'ml', 'gemini', 'groq'])

        # Optional: per-lead comparison
        lead_id = request.args.get('lead_id', type=int)
        lead_comparison = None
        if lead_id:
            lead_comparison = dl.feedback_tracker.model_vs_reality(lead_id)

        return success_response(
            message='Feedback accuracy report',
            accuracy=accuracy_report,
            dynamic_weights=dynamic_weights,
            db_dataset=db_stats,
            jsonl_dataset=jsonl_stats,
            lead_comparison=lead_comparison,
        )

    except Exception as e:
        logger.error(f"get_feedback_accuracy error: {e}", exc_info=True)
        raise APIException(f"Feedback accuracy report failed: {e}", status_code=500)


# ============================================================================
# § 7 · EVALUATION DASHBOARD & LEAD EXPLANATION  (SHAP)
# ============================================================================

@ai_bp.route('/dashboard', methods=['GET'])
@token_required
@manager_or_admin_required
@handle_exceptions
def get_evaluation_dashboard():
    """
    Evaluation Dashboard — aggregated ML + AI performance metrics.

    Returns:
      - model_metrics_history: AUC/accuracy/P/R/F1 over time (last 50 runs)
      - current_model:         active model stats snapshot
      - conversion_by_tier:    hot/warm/cold → actual conversion rates
      - provider_agreement:    how often ML and LLM agree on tier
      - dataset_health:        labeled count, positive rate, label source breakdown
      - feedback_accuracy:     per-source accuracy from FeedbackAccuracyTracker
    """
    try:
        from pathlib import Path
        from app.models.models import db, Lead, LeadOutcome
        from app.services.ml_model import XGBLeadScoringModel
        from app.services.ml_decision_layer import get_decision_layer
        from app.services.dataset_manager import get_dataset_manager

        dl      = get_decision_layer()
        manager = get_dataset_manager()

        # ── 1. Metrics history (JSONL time series) ────────────────────────────
        metrics_history = []
        metrics_path = Path(__file__).parent.parent.parent / 'data' / 'metrics_history.jsonl'
        if metrics_path.exists():
            with open(metrics_path) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            metrics_history.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        metrics_history = metrics_history[-50:]  # last 50 training runs

        # ── 2. Current model stats ────────────────────────────────────────────
        m = XGBLeadScoringModel()
        m.load_model()
        current_model = m.training_stats or {}

        # ── 3. Conversion rates by qualification tier (from DB) ───────────────
        conversion_by_tier = {'hot': {}, 'warm': {}, 'cold': {}}
        try:
            from sqlalchemy import func

            # Count leads per AI-assigned category + actual outcome
            rows = (
                db.session.query(
                    Lead.status,
                    LeadOutcome.outcome,
                    func.count(LeadOutcome.id),
                )
                .join(LeadOutcome, Lead.id == LeadOutcome.lead_id)
                .group_by(Lead.status, LeadOutcome.outcome)
                .all()
            )
            tier_totals: dict = {}
            tier_conversions: dict = {}
            _POSITIVE_OUT = {'converted', 'contacted', 'hot'}
            for lead_status, outcome, cnt in rows:
                t = lead_status.lower() if lead_status else 'unknown'
                tier_totals[t]       = tier_totals.get(t, 0) + cnt
                if outcome in _POSITIVE_OUT:
                    tier_conversions[t] = tier_conversions.get(t, 0) + cnt

            for t in ('hot', 'warm', 'cold'):
                total = tier_totals.get(t, 0)
                conv  = tier_conversions.get(t, 0)
                conversion_by_tier[t] = {
                    'total':           total,
                    'converted':       conv,
                    'conversion_rate': round(conv / total, 3) if total else None,
                }
        except Exception as _tier_err:
            logger.warning(f"dashboard conversion_by_tier: {_tier_err}")

        # ── 4. ML vs LLM agreement rate (from JSONL dataset) ─────────────────
        from app.services.ml_decision_layer import DATASET_PATH, SCORE_HOT, SCORE_WARM

        total_records = agree = 0
        try:
            if DATASET_PATH.exists():
                with open(DATASET_PATH) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            ps  = rec.get('provider_scores', {})
                            ml  = ps.get('ml')
                            llm = ps.get('gemini') or ps.get('groq')
                            if ml is not None and llm is not None:
                                total_records += 1
                                # Agree = same tier bucket
                                def _tier(s):
                                    return 'hot' if s >= SCORE_HOT else ('warm' if s >= SCORE_WARM else 'cold')
                                if _tier(ml) == _tier(llm):
                                    agree += 1
                        except json.JSONDecodeError:
                            pass
        except Exception as _agr_err:
            logger.warning(f"dashboard agreement: {_agr_err}")

        agreement_rate = round(agree / total_records, 3) if total_records else None

        # ── 5. Dataset health ─────────────────────────────────────────────────
        db_stats    = manager.get_dataset_stats()
        jsonl_stats = dl.dataset.dataset_stats()

        # ── 6. Feedback accuracy ──────────────────────────────────────────────
        feedback_accuracy = dl.feedback_tracker.accuracy_report()

        return jsonify({
            'status':                'success',
            'model_metrics_history': metrics_history,
            'current_model':         {
                'auc':       current_model.get('hold_out_auc'),
                'accuracy':  current_model.get('hold_out_accuracy'),
                'precision': current_model.get('hold_out_precision'),
                'recall':    current_model.get('hold_out_recall'),
                'f1':        current_model.get('hold_out_f1'),
                'n_samples': current_model.get('n_samples'),
                'trained_at': current_model.get('trained_at'),
                'model_version': current_model.get('model_version'),
            },
            'conversion_by_tier':    conversion_by_tier,
            'ml_llm_agreement':      {
                'agreement_rate':   agreement_rate,
                'total_comparisons': total_records,
                'agreements':        agree,
            },
            'dataset_health':        {
                'db':   db_stats,
                'jsonl': jsonl_stats,
            },
            'feedback_accuracy':     feedback_accuracy,
            'dynamic_weights':       dl.tracker.provider_weights(['agent', 'ml', 'gemini', 'groq']),
        }), 200

    except Exception as exc:
        logger.error(f"dashboard error: {exc}", exc_info=True)
        raise APIException(f"Dashboard failed: {exc}", status_code=500)


@ai_bp.route('/explain/<int:lead_id>', methods=['GET'])
@token_required
@handle_exceptions
def explain_lead(lead_id):
    """
    Return a combined SHAP + LLM explainability report for a specific lead.

    Response includes:
      - shap_factors: top-3 feature contributions (name, value, impact, direction)
      - llm_explanation: human-readable summary generated from SHAP output
      - ml_score: current ML model score
      - scoring_breakdown: per-provider scores from JSONL log
    """
    try:
        from app.models.models import db, Lead
        from app.services.advanced_ai import get_ml_model, extract_features
        from app.services.ml_decision_layer import DATASET_PATH

        lead = db.session.get(Lead, lead_id)
        lead_data: dict | None = None

        if lead is not None:
            lead_data = {
                'name':         lead.name or '',
                'email':        lead.email or '',
                'phone':        lead.phone or '',
                'company':      lead.company or '',
                'position':     lead.position or '',
                'industry':     lead.industry or '',
                'country':      lead.country or '',
                'city':         lead.city or '',
                'linkedin_url': lead.linkedin_url or '',
                'website':      lead.website or '',
                'source':       lead.source or '',
                'interests':    lead.interests or [],
                'notes':        getattr(lead, 'notes', '') or '',
            }
        else:
            demo = None
            if demo:
                lead_data = {
                    'name':         demo.get('name', ''),
                    'email':        demo.get('email', ''),
                    'phone':        demo.get('phone', ''),
                    'company':      demo.get('company', ''),
                    'position':     demo.get('position', ''),
                    'industry':     demo.get('industry', ''),
                    'country':      demo.get('country', ''),
                    'city':         demo.get('location', '').split(',')[0].strip(),
                    'linkedin_url': demo.get('linkedin_url', ''),
                    'website':      demo.get('website', ''),
                    'source':       demo.get('source', ''),
                    'interests':    demo.get('interests', []),
                    'notes':        demo.get('notes', ''),
                }

        if lead_data is None:
            return jsonify({'status': 'error', 'message': f'Lead {lead_id} not found'}), 404

        # ── SHAP explanation ─────────────────────────────────────────────────
        model = get_ml_model()
        shap_factors = []
        ml_score = None

        if model is not None and model.model is not None:
            features = extract_features(lead_data)
            result   = model.predict_with_explanation(features)
            ml_score = result.get('score')

            if result.get('shap_available') and result.get('top_factors'):
                for f in result['top_factors'][:3]:
                    shap_factors.append({
                        'feature':     f['feature'],
                        'value':       round(f['value'], 3),
                        'impact':      round(f['shap_impact'], 4),
                        'direction':   f['direction'],
                        'description': _shap_feature_description(
                            f['feature'], f['direction']
                        ),
                    })

        # ── Read scoring breakdown from JSONL log ────────────────────────────
        scoring_breakdown = {}
        try:
            if DATASET_PATH.exists():
                with open(DATASET_PATH) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
                        if rec.get('lead_id') == lead_id:
                            scoring_breakdown = rec.get('provider_scores', {})
                            break
        except Exception:
            pass

        # ── LLM human-readable explanation ───────────────────────────────────
        llm_explanation = _generate_shap_explanation(
            lead_data, shap_factors, ml_score, scoring_breakdown
        )

        return jsonify({
            'status':            'success',
            'lead_id':           lead_id,
            'name':              lead_data['name'],
            'company':           lead_data['company'],
            'ml_score':          ml_score,
            'shap_factors':      shap_factors,
            'llm_explanation':   llm_explanation,
            'scoring_breakdown': scoring_breakdown,
        }), 200

    except Exception as exc:
        logger.error(f"explain_lead error: {exc}", exc_info=True)
        raise APIException(f"Explanation failed: {exc}", status_code=500)


def _shap_feature_description(feature: str, direction: str) -> str:
    """Convert a SHAP feature name + direction into a plain-English sentence."""
    _DESCRIPTIONS = {
        'position_seniority':       ('Senior title indicates decision-making authority',
                                     'Junior title limits buying authority'),
        'interest_relevance':       ('Interests closely match our product offering',
                                     'Interests do not align with our product'),
        'company_formality':        ('Established company structure signals budget capacity',
                                     'Informal company structure may limit budget'),
        'source_credibility':       ('Lead came from a high-trust source (referral/partner)',
                                     'Lead source has low historical conversion rate'),
        'email_quality':            ('Corporate email confirms professional identity',
                                     'Free or missing email reduces verification confidence'),
        'data_completeness':        ('Profile is well-filled with actionable data',
                                     'Sparse profile reduces qualification accuracy'),
        'has_phone':                ('Phone number available for direct outreach', ''),
        'has_linkedin':             ('LinkedIn profile enables social verification', ''),
        'decision_maker_score':     ('Job title includes buying-authority keywords',
                                     'No clear decision-maker signals in title'),
        'budget_signal_score':      ('Notes contain budget or procurement language',
                                     'No budget signals found in notes'),
        'industry_value_score':     ('Industry has high historical conversion rates',
                                     'Industry shows lower typical conversion rates'),
        'email_format_confidence':  ('Valid corporate email format confirmed',
                                     'Email format or domain raises concerns'),
        'spam_risk_score':          ('Lead passes spam/bot detection filters',
                                     'Lead shows spam or role-email patterns'),
        'source_reliability_score': ('Source is historically reliable for qualified leads',
                                     'Source has lower reliability for conversions'),
    }
    pos_msg, neg_msg = _DESCRIPTIONS.get(feature, (feature.replace('_', ' ').title(), ''))
    if direction == 'positive':
        return pos_msg or f'{feature.replace("_", " ")} increases conversion probability'
    else:
        return neg_msg or f'{feature.replace("_", " ")} decreases conversion probability'


def _generate_shap_explanation(
    lead_data: dict,
    shap_factors: list,
    ml_score,
    scoring_breakdown: dict,
) -> str:
    """
    Generate a human-readable explanation from SHAP factors.
    Tries Gemini/Groq first; falls back to a structured template.
    """
    if shap_factors:
        positives = [f for f in shap_factors if f['direction'] == 'positive']
        negatives = [f for f in shap_factors if f['direction'] == 'negative']

        pos_text = '; '.join(f['description'] for f in positives) if positives else 'No major positive signals'
        neg_text = '; '.join(f['description'] for f in negatives) if negatives else 'No major negative signals'

        template = (
            f"{lead_data.get('name', 'This lead')} at {lead_data.get('company', 'unknown company')} "
            f"received an ML score of {ml_score}/100. "
            f"Key positive signals: {pos_text}. "
            f"Areas of concern: {neg_text}."
        )

        # Try to get a richer LLM explanation
        try:
            from app.services.gemini_service import get_ai_service
            ai_svc = get_ai_service()
            prompt = (
                f"In 2-3 sentences, explain to a salesperson why this B2B lead scored {ml_score}/100. "
                f"Positive signals: {pos_text}. Concerns: {neg_text}. "
                f"Lead: {lead_data.get('position','')} at {lead_data.get('company','')} "
                f"({lead_data.get('industry','')}). Be specific and actionable."
            )
            ai_svc.prefer_fast = True
            resp = ai_svc.qualify_lead({'name': 'explain', '_explain_prompt': prompt,
                                        'position': lead_data.get('position', ''),
                                        'company': lead_data.get('company', ''),
                                        'industry': lead_data.get('industry', '')})
            reasoning = resp.get('reason') or resp.get('reasoning') or ''
            if reasoning and len(reasoning) > 30:
                return reasoning
        except Exception:
            pass

        return template

    score_str = f"{ml_score}/100" if ml_score is not None else "unavailable"
    return (
        f"ML model scored {lead_data.get('name', 'this lead')} at {score_str}. "
        "SHAP explanation not available — run retraining to enable detailed explanations."
    )


# ============================================================================
# § 8 · LEAD QUALIFICATION & LOGS  (single · batch · normalize · refresh)
# ============================================================================

@ai_bp.route('/logs', methods=['GET'])
@token_required
@handle_exceptions
def get_logs():
    try:
        limit = request.args.get('limit', 50, type=int)
        with _log_lock:
            logs = list(_activity_log[:limit])
        return jsonify({
            'status': 'success',
            'logs': logs,
            'total': len(_activity_log),
        }), 200
    except Exception as e:
        logger.error(f"Error fetching AI logs: {str(e)}")
        raise APIException(f"Failed to fetch AI logs: {str(e)}", status_code=500)


@ai_bp.route('/task-status/<task_id>', methods=['GET'])
@token_required
@handle_exceptions
def get_task_status(task_id):
    """
    Poll the result of a Celery background task.

    Returns
    -------
    { task_id, status, result, error }

    status values mirror Celery states:
      PENDING   — queued, not yet picked up by a worker
      STARTED   — worker has begun processing
      SUCCESS   — finished; result contains the payload
      FAILURE   — task raised an unrecoverable exception
      RETRY     — worker is about to retry
    """
    demo_task = None
    if demo_task is not None:
        return jsonify({
            'task_id': task_id,
            'status':  demo_task['state'],
            'result':  demo_task.get('result'),
            'error':   demo_task.get('error'),
        }), 200

    try:
        from celery.result import AsyncResult
        ar = AsyncResult(task_id)
        if ar.state == 'SUCCESS':
            return jsonify({
                'task_id': task_id,
                'status':  'SUCCESS',
                'result':  ar.result,
                'error':   None,
            }), 200
        if ar.state == 'FAILURE':
            return jsonify({
                'task_id': task_id,
                'status':  'FAILURE',
                'result':  None,
                'error':   str(ar.info),
            }), 200
        # PENDING / STARTED / RETRY — still running
        return jsonify({
            'task_id': task_id,
            'status':  ar.state,
            'result':  None,
            'error':   None,
        }), 200
    except Exception as e:
        logger.error('[task-status] task_id=%s error=%s', task_id, e)
        raise APIException(f'Failed to fetch task status: {e}', status_code=500)


@ai_bp.route('/qualify/<int:lead_id>', methods=['POST'])
@token_required
@limiter.limit("30 per hour")
@handle_exceptions
def qualify_single(lead_id):
    """Qualify a single lead by ID using the AI qualification chain."""
    try:
        from app.models.models import db, Lead

        lead = db.session.get(Lead, lead_id)
        if not lead:
            return jsonify({'status': 'error', 'message': f'Lead {lead_id} not found'}), 404

        ai_svc = get_ai_service()
        data = request.get_json(force=True, silent=True) or {}
        use_ai = data.get('use_ai', True)

        dp = lead.data_points if isinstance(lead.data_points, dict) else {}
        lead_data = {
            'name': lead.name,
            'email': lead.email,
            'company': lead.company,
            'position': lead.position,
            'industry': lead.industry or '',
            'country': lead.country or '',
            'city': lead.city or '',
            'website': lead.website or '',
            'linkedin_url': lead.linkedin_url or '',
            'phone': lead.phone or '',
            'interests': lead.interests or [],
            'product': lead.product or '',
            'source': lead.source or '',
            'completeness_score': lead.completeness_score or 0,
            'email_type': lead.email_type or '',
            'data_points': dp,
        }

        fast_mode = data.get('fast', False)
        if fast_mode:
            # Fast ML path — QualificationAgent + XGBoost, no LLM API calls
            result = _qualify_fast(lead_data)
        elif use_ai:
            # Full AI pipeline — Groq/Gemini via MLDecisionLayer
            result = qualify_lead_with_external_ai(lead_data, lead_id=lead.id)
        else:
            result = ai_svc.qualify_lead_fast(lead_data)

        lead.qualification_score = result['score']
        lead.status = _derive_status(result)
        if not hasattr(lead, 'data_points') or not lead.data_points:
            lead.data_points = {}
        if isinstance(lead.data_points, dict):
            lead.data_points['ai_qualification'] = {
                'score': result['score'],
                'category': result['category'],
                'confidence': result.get('confidence', 0),
                'reasoning': result.get('reason', result.get('reasoning', '')),
                'strengths': result.get('details', {}).get('llm_strengths', []),
                'weaknesses': result.get('details', {}).get('llm_weaknesses', []),
                'next_action': result.get('next_action', ''),
                'layers_used': result.get('layers_used', []),
                'scoring_method': result.get('scoring_method', ''),
                'ai_provider': result.get('ai_provider', ''),
                'qualified_at': datetime.now(timezone.utc).isoformat(),
            }
            flag_modified(lead, 'data_points')
        db.session.commit()

        _add_log('Single lead qualified', 'success',
                 f'{lead.name} → {result["score"]} ({result["category"]})')

        return jsonify({
            'status': 'success',
            'lead_id': lead.id,
            'name': lead.name,
            'company': lead.company,
            'score': result['score'],
            'category': result['category'],
            'confidence': result.get('confidence', 0),
            'reasoning': result.get('reasoning', ''),
            'strengths': result.get('strengths', []),
            'weaknesses': result.get('weaknesses', []),
            'next_action': result.get('next_action', ''),
            'ai_provider': result.get('ai_provider', ''),
        }), 200

    except Exception as e:
        logger.error(f"Error qualifying lead {lead_id}: {str(e)}")
        raise APIException(f"Failed to qualify lead: {str(e)}", status_code=500)


@ai_bp.route('/qualify-batch', methods=['POST'])
@token_required
@limiter.limit("10 per hour")
@handle_exceptions
def qualify_batch():
    data     = request.get_json(force=True, silent=True) or {}
    cfg      = _load_ai_settings()
    lead_ids = data.get('lead_ids') or None   # None means "use limit query"
    limit    = min(int(data.get('limit', cfg.get('batch_size', 100))), 1000)
    use_ai   = data.get('use_ai', True)

    # Validate lead_ids when provided
    if lead_ids is not None:
        if not isinstance(lead_ids, list):
            raise APIException('lead_ids must be an array', status_code=400)
        if len(lead_ids) > 1000:
            raise APIException('Maximum 1000 lead IDs per batch', status_code=400)
        invalid = [x for x in lead_ids if not isinstance(x, int) or x <= 0]
        if invalid:
            raise APIException('All lead_ids must be positive integers', status_code=400)

    # Dispatch to Celery — returns immediately
    from app.tasks.agent_tasks import qualify_batch_async
    task = qualify_batch_async.delay(
        lead_ids=lead_ids,
        limit=limit,
        use_ai=use_ai,
        user_id=g.user_id,
        user_email=g.email,
    )
    _add_log('Batch qualification queued', 'info',
             f'task_id={task.id} limit={limit} use_ai={use_ai}')

    return jsonify({
        'status':  'queued',
        'task_id': task.id,
        'message': f'Batch qualification started — poll /ai/task-status/{task.id}',
    }), 202



@ai_bp.route('/normalize-statuses', methods=['POST'])
@token_required
def normalize_statuses():
    """
    Re-apply score → status rules to every lead in the DB without calling the AI.
    Uses max(qualification_score, completeness_score) so prior AI scores are respected.
    Thresholds: ≥80 → hot, ≥60 → warm, <60 → cold.
    """
    try:
        from app.models.models import Lead, db

        leads = Lead.query.all()
        updated = hot = warm = cold = 0

        for lead in leads:
            # Prefer AI qualification_score; only fall back to completeness_score
            # if AI has never run on this lead (qualification_score is null/0)
            qs = lead.qualification_score or 0
            score = qs if qs > 0 else (lead.completeness_score or 0)
            new_st = 'hot' if score >= 80 else 'warm' if score >= 60 else 'cold'
            if lead.status != new_st:
                lead.status = new_st
                updated += 1
            if new_st == 'hot':   hot  += 1
            elif new_st == 'warm': warm += 1
            else:                  cold += 1

        db.session.commit()
        logger.info(f"[normalize_statuses] {updated}/{len(leads)} leads updated: {hot} hot, {warm} warm, {cold} cold")

        return jsonify({
            'status':  'success',
            'message': f'Normalized {len(leads)} leads — {updated} statuses changed',
            'data':    {'total': len(leads), 'updated': updated, 'hot': hot, 'warm': warm, 'cold': cold},
        }), 200

    except Exception as e:
        try:
            from app.models.models import db
            db.session.rollback()
        except Exception:
            pass
        raise APIException(f"Failed to normalize statuses: {str(e)}", status_code=500)


@ai_bp.route('/settings', methods=['POST', 'GET'])
@token_required
@manager_or_admin_required
@handle_exceptions
def manage_settings():
    """Get or update AI engine settings (persisted to data/ai_settings.json).
    GET is available to manager and admin. POST (edit) requires admin.
    """
    if request.method == 'POST':
        if g.role != 'admin':
            from app.exceptions import AuthorizationError
            raise AuthorizationError("Only admins can change AI settings")
        data = request.get_json(force=True, silent=True) or {}
        _save_ai_settings(data)
        saved = _load_ai_settings()
        logger.info(f"AI settings saved: {saved}")
        return jsonify({
            'status':  'success',
            'message': 'Settings saved successfully',
            'data':    saved,
        }), 200
    else:
        return jsonify({
            'status':   'success',
            'settings': _load_ai_settings(),
        }), 200


@ai_bp.route('/refresh-leads', methods=['POST'])
@token_required
@handle_exceptions
def refresh_leads():
    """Refresh/requalify all leads with AI - returns immediately, processing happens in background"""
    import threading
    from flask import current_app

    # Capture the app object before spawning the thread so the thread has an app context
    app = current_app._get_current_object()  # type: ignore[attr-defined]

    def process_leads_background():
        """Process leads in background thread using fast path (no LLM API calls)."""
        with app.app_context():
            try:
                from app.models.models import db, Lead
                from app.services.advanced_ai import initialize_advanced_ai

                initialize_advanced_ai()
                leads = Lead.query.all()
                use_fast = len(leads) > _FAST_BATCH_THRESHOLD

                for lead in leads:
                    try:
                        dp = lead.data_points if isinstance(lead.data_points, dict) else {}
                        lead_data = {
                            'name': lead.name,
                            'email': lead.email or '',
                            'company': lead.company or '',
                            'position': lead.position or '',
                            'industry': lead.industry or '',
                            'country': lead.country or '',
                            'city': lead.city or '',
                            'website': lead.website or '',
                            'linkedin_url': lead.linkedin_url or '',
                            'phone': lead.phone or '',
                            'interests': lead.interests or [],
                            'product': lead.product or '',
                            'source': lead.source or '',
                            'completeness_score': lead.completeness_score or 0,
                            'email_type': lead.email_type or '',
                            'data_points': dp,
                        }

                        ai_result = _qualify_fast(lead_data) if use_fast else qualify_lead_with_external_ai(lead_data, lead_id=lead.id)
                        lead.qualification_score = ai_result['score']
                        new_st = _derive_status(ai_result)
                        if lead.status != 'hot' or new_st == 'hot':
                            lead.status = new_st
                        if isinstance(lead.data_points, dict):
                            lead.data_points['ai_qualification'] = {
                                'score': ai_result['score'],
                                'category': ai_result.get('category', ''),
                                'confidence': ai_result.get('confidence', 0),
                                'ai_provider': ai_result.get('ai_provider', ''),
                                'qualified_at': datetime.now(timezone.utc).isoformat(),
                            }
                            flag_modified(lead, 'data_points')
                    except Exception as e:
                        logger.warning(f"Failed to qualify lead {lead.id}: {str(e)}")

                db.session.commit()
                logger.info(f"Background refresh complete: {len(leads)} leads ({'fast' if use_fast else 'full AI'} path)")
            except Exception as e:
                logger.error(f"Background refresh error: {str(e)}")
                db.session.rollback()

    # Start background thread - don't wait for it
    thread = threading.Thread(target=process_leads_background, daemon=True)
    thread.start()
    
    # Return immediately
    return jsonify({
        'status': 'success',
        'message': 'Lead refresh started in background. Check back in 30 seconds.',
        'data': {
            'processing': True,
            'leads_being_updated': 'all'
        }
    }), 202


@ai_bp.route('/refresh-lead/<int:lead_id>', methods=['POST'])
@token_required
@handle_exceptions
def refresh_single_lead(lead_id):
    """Refresh/requalify a single lead with AI — dispatches to Celery, returns immediately."""
    from app.models.models import db, Lead

    lead = db.get_or_404(Lead, lead_id, description='Lead not found')

    from app.tasks.agent_tasks import qualify_lead_async
    task = qualify_lead_async.delay(lead.id)

    logger.info('[refresh_single_lead] lead=%d queued as task=%s', lead_id, task.id)
    return jsonify({
        'status':  'queued',
        'task_id': task.id,
        'message': f'Lead {lead.name} queued for AI refresh — poll /ai/task-status/{task.id}',
        'data': {
            'lead_id': lead.id,
            'name':    lead.name,
        },
    }), 202


# ============================================================================
# § 9 · INTELLIGENCE & ANALYSIS ENDPOINTS  (chat · email · pipeline summary)
# ============================================================================

@ai_bp.route('/health', methods=['GET'])
@token_required
@handle_exceptions
def ai_health():
    ai_svc = get_ai_service()
    health = dict(ai_svc.health_check())  # copy — don't mutate the 60-s cache
    ai_status = health.pop('status', 'unknown')
    _add_log('Health check', ai_status, f"Model: {health.get('model', 'none')}")
    return jsonify({'status': 'success', 'ai_status': ai_status, **health}), 200


@ai_bp.route('/intelligence/<int:lead_id>', methods=['POST'])
@token_required
@handle_exceptions
def lead_intelligence(lead_id):
    """
    Full 8-step B2B Lead Intelligence Engine for a single lead.

    Runs: company validation → business intelligence extraction →
          decision-maker detection → email classification →
          website + intent analysis → LinkedIn enrichment →
          strict scoring (gate: score≥70 AND intent≠low) →
          recommended action (SAVE | REVIEW | DISCARD).

    Optionally fetches the company website before analysis if
    ?fetch_website=true is passed (adds ~3-5s latency).

    Updates the lead's qualification_score and data_points in place.
    Returns the full intelligence report JSON.
    """
    try:
        from app.models.models import db, Lead
        from sqlalchemy.orm.attributes import flag_modified

        lead_obj = db.session.get(Lead, lead_id)
        if not lead_obj:
            return jsonify({'status': 'error', 'message': f'Lead {lead_id} not found'}), 404

        lead_data: dict = {
            'id':                 lead_obj.id,
            'name':               lead_obj.name or '',
            'email':              lead_obj.email or '',
            'email_type':         lead_obj.email_type or '',
            'phone':              lead_obj.phone or '',
            'company':            lead_obj.company or '',
            'position':           lead_obj.position or '',
            'industry':           lead_obj.industry or '',
            'country':            lead_obj.country or '',
            'city':               lead_obj.city or '',
            'website':            lead_obj.website or '',
            'linkedin_url':       lead_obj.linkedin_url or '',
            'source':             lead_obj.source or '',
            'notes':              lead_obj.notes or '',
            'interests':          lead_obj.interests or [],
            'qualification_score': lead_obj.qualification_score or 0,
            'data_points':        lead_obj.data_points or {},
        }

        # Optionally fetch website content to improve intent detection
        website_text = ''
        if request.args.get('fetch_website') == 'true' and lead_obj.website:
            try:
                _resp = __import__('requests').get(
                    lead_obj.website,
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=8,
                    allow_redirects=True,
                )
                if _resp.status_code == 200:
                    from bs4 import BeautifulSoup as _BS
                    _soup = _BS(_resp.text, 'html.parser')
                    for _tag in _soup(['script', 'style', 'nav', 'footer']):
                        _tag.decompose()
                    website_text = ' '.join(_soup.get_text().split())[:1200]
            except Exception as _we:
                logger.debug(f"[intelligence] website fetch skipped: {_we}")

        ai_svc = get_ai_service()
        report = ai_svc.lead_intelligence_analysis(lead_data, website_content=website_text)

        # ── Write back to DB ──────────────────────────────────────────────────
        prev_score = lead_obj.qualification_score or 0
        new_score  = report.get('qualification_score', prev_score)

        # Always update qualification_score from the intelligence report
        lead_obj.qualification_score = new_score

        # Apply db_updates (fills blank fields only — never overwrites existing data)
        for field, value in (report.get('db_updates') or {}).items():
            if value and not getattr(lead_obj, field, None):
                setattr(lead_obj, field, value)

        # Persist intelligence report in data_points
        dp = dict(lead_obj.data_points or {})
        dp['intelligence_report'] = {
            'is_lead':              report.get('is_lead'),
            'buying_intent':        report.get('buying_intent'),
            'buying_intent_signals':report.get('buying_intent_signals', []),
            'quality_tier':         report.get('quality_tier'),
            'source_quality':       report.get('source_quality'),
            'recommended_action':   report.get('recommended_action'),
            'decision_makers':      report.get('decision_makers', []),
            'emails':               report.get('emails', []),
            'reasons':              report.get('reasons', []),
            'industry_inferred':    report.get('industry_inferred', False),
            'ai_provider':          report.get('ai_provider'),
            'prompt_version':       report.get('prompt_version'),
            'analyzed_at':          report.get('analyzed_at'),
        }
        lead_obj.data_points = dp
        flag_modified(lead_obj, 'data_points')
        db.session.commit()

        logger.info(
            f"[intelligence] lead={lead_id} score {prev_score:.0f}→{new_score:.0f} "
            f"action={report.get('recommended_action')} "
            f"intent={report.get('buying_intent')} "
            f"provider={report.get('provider_key')}"
        )

        return jsonify({
            'status':   'success',
            'lead_id':  lead_id,
            'previous_score': prev_score,
            'new_score':      new_score,
            'report':   report,
        }), 200

    except Exception as exc:
        logger.error(f"[intelligence] lead={lead_id} error: {exc}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(exc)}), 500


@ai_bp.route('/intelligence-batch', methods=['POST'])
@token_required
@handle_exceptions
def lead_intelligence_batch():
    """
    Run the Lead Intelligence Engine on multiple leads.

    Body: { "lead_ids": [1, 2, 3], "fetch_website": false }

    Processes up to 20 leads per call. Returns a summary + per-lead actions.
    Uses the rule-based engine when the AI service is unavailable to avoid
    blocking the batch.
    """
    try:
        from app.models.models import db, Lead
        from sqlalchemy.orm.attributes import flag_modified

        body     = request.get_json(silent=True) or {}
        lead_ids = body.get('lead_ids', [])
        fetch_w  = bool(body.get('fetch_website', False))

        if not lead_ids or not isinstance(lead_ids, list):
            return jsonify({'status': 'error', 'message': 'lead_ids list required'}), 400
        if len(lead_ids) > 20:
            lead_ids = lead_ids[:20]

        ai_svc = get_ai_service()
        results = []

        for lead_id in lead_ids:
            try:
                lead_obj = db.session.get(Lead, lead_id)
                if not lead_obj:
                    results.append({'lead_id': lead_id, 'error': 'not found'})
                    continue

                lead_data = {
                    'id':           lead_obj.id,
                    'name':         lead_obj.name or '',
                    'email':        lead_obj.email or '',
                    'email_type':   lead_obj.email_type or '',
                    'phone':        lead_obj.phone or '',
                    'company':      lead_obj.company or '',
                    'position':     lead_obj.position or '',
                    'industry':     lead_obj.industry or '',
                    'country':      lead_obj.country or '',
                    'city':         lead_obj.city or '',
                    'website':      lead_obj.website or '',
                    'linkedin_url': lead_obj.linkedin_url or '',
                    'source':       lead_obj.source or '',
                    'notes':        lead_obj.notes or '',
                    'interests':    lead_obj.interests or [],
                    'data_points':  lead_obj.data_points or {},
                }

                website_text = ''
                if fetch_w and lead_obj.website:
                    try:
                        _r = __import__('requests').get(
                            lead_obj.website,
                            headers={'User-Agent': 'Mozilla/5.0'},
                            timeout=6, allow_redirects=True,
                        )
                        if _r.status_code == 200:
                            from bs4 import BeautifulSoup as _BS2
                            _s2 = _BS2(_r.text, 'html.parser')
                            for _t in _s2(['script', 'style', 'nav', 'footer']):
                                _t.decompose()
                            website_text = ' '.join(_s2.get_text().split())[:800]
                    except Exception:
                        pass

                report = ai_svc.lead_intelligence_analysis(lead_data, website_content=website_text)

                prev_score = lead_obj.qualification_score or 0
                lead_obj.qualification_score = report.get('qualification_score', prev_score)

                for field, value in (report.get('db_updates') or {}).items():
                    if value and not getattr(lead_obj, field, None):
                        setattr(lead_obj, field, value)

                dp = dict(lead_obj.data_points or {})
                dp['intelligence_report'] = {
                    'is_lead':            report.get('is_lead'),
                    'buying_intent':      report.get('buying_intent'),
                    'quality_tier':       report.get('quality_tier'),
                    'recommended_action': report.get('recommended_action'),
                    'decision_makers':    report.get('decision_makers', []),
                    'reasons':            report.get('reasons', []),
                    'ai_provider':        report.get('ai_provider'),
                    'analyzed_at':        report.get('analyzed_at'),
                }
                lead_obj.data_points = dp
                flag_modified(lead_obj, 'data_points')
                db.session.commit()

                results.append({
                    'lead_id':            lead_id,
                    'recommended_action': report.get('recommended_action'),
                    'qualification_score': report.get('qualification_score'),
                    'buying_intent':      report.get('buying_intent'),
                    'quality_tier':       report.get('quality_tier'),
                    'ai_provider':        report.get('provider_key'),
                })

            except Exception as _le:
                logger.warning(f"[intelligence-batch] lead={lead_id} error: {_le}")
                results.append({'lead_id': lead_id, 'error': str(_le)})

        summary = {
            'save':    sum(1 for r in results if r.get('recommended_action') == 'SAVE'),
            'review':  sum(1 for r in results if r.get('recommended_action') == 'REVIEW'),
            'discard': sum(1 for r in results if r.get('recommended_action') == 'DISCARD'),
            'errors':  sum(1 for r in results if 'error' in r),
        }

        return jsonify({
            'status':    'success',
            'processed': len(results),
            'summary':   summary,
            'results':   results,
        }), 200

    except Exception as exc:
        logger.error(f"[intelligence-batch] error: {exc}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(exc)}), 500


@ai_bp.route('/analyze-lead/<int:lead_id>', methods=['POST'])
@token_required
@handle_exceptions
def analyze_lead(lead_id):
    """Deep AI analysis of a single lead"""
    try:
        from app.models.models import db, Lead

        lead = db.get_or_404(Lead, lead_id, description="Lead not found")
        lead_name = lead.name
        lead_data = {
            'name': lead.name, 'email': lead.email, 'company': lead.company,
            'position': lead.position, 'industry': lead.industry or '',
            'country': lead.country or '', 'city': lead.city or '',
            'website': lead.website or '', 'linkedin_url': lead.linkedin_url or '',
            'phone': lead.phone or '', 'interests': lead.interests or [],
            'product': lead.product or '',
            'source': lead.source or '', 'qualification_score': lead.qualification_score,
        }

        ai_svc = get_ai_service()
        result = ai_svc.analyze_lead(lead_data)

        _add_log('Lead analyzed', 'success', f"{lead_name} ({lead_data.get('company')}) — {result.get('ai_provider', '')}")

        return jsonify({
            'status': 'success',
            'lead_id': lead_id,
            'lead_name': lead_name,
            **result,
        }), 200
    except Exception as e:
        logger.error(f"Error analyzing lead {lead_id}: {e}")
        raise APIException(f"Failed to analyze lead: {str(e)}", status_code=500)


@ai_bp.route('/generate-email/<int:lead_id>', methods=['POST'])
@token_required
@handle_exceptions
def generate_email(lead_id):
    """Generate personalized outreach email for a lead"""
    try:
        from app.models.models import db, Lead

        data = request.get_json(force=True, silent=True) or {}
        email_type = data.get('email_type', 'cold_outreach')
        tone = data.get('tone', 'professional')
        custom_context = data.get('context', '')

        lead = db.get_or_404(Lead, lead_id, description="Lead not found")
        lead_name = lead.name
        lead_data = {
            'name': lead.name, 'email': lead.email, 'company': lead.company,
            'position': lead.position, 'industry': lead.industry or '',
            'country': lead.country or '', 'city': lead.city or '',
            'interests': lead.interests or [],
        }

        ai_svc = get_ai_service()
        result = ai_svc.generate_email(lead_data, email_type=email_type,
                                            tone=tone, custom_context=custom_context)

        _add_log('Email generated', 'success', f"For {lead_name} — {email_type} ({tone})")

        return jsonify({
            'status': 'success',
            'lead_id': lead_id,
            **result,
        }), 200
    except Exception as e:
        logger.error(f"Error generating email for lead {lead_id}: {e}")
        raise APIException(f"Failed to generate email: {str(e)}", status_code=500)


@ai_bp.route('/chat', methods=['POST'])
@token_required
@handle_exceptions
def ai_chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get('message', '').strip()
    history      = data.get('history', [])
    if not user_message:
        return jsonify({'status': 'error', 'message': 'message is required'}), 400

    try:
        from app.models.models import db, Lead

        # Ownership-filtered base query (mirrors leads list & analytics)
        base = Lead.query
        if g.role != 'admin':
            base = base.filter(
                db.or_(
                    Lead.collected_by == g.user_id,
                    db.and_(Lead.collected_by == None, Lead.origin != 'mobile'),  # noqa: E711
                )
            )

        # Top leads for context
        top_leads = base.order_by(Lead.qualification_score.desc()).limit(10).all()
        leads_context = [{
            'name': l.name, 'company': l.company, 'position': l.position,
            'country': l.country, 'industry': l.industry,
            'qualification_score': l.qualification_score, 'status': l.status,
            'email': l.email, 'source': l.source,
        } for l in top_leads]

        # Aggregate pipeline stats for richer context
        pipeline_stats = {
            'total':     base.count(),
            'hot':       base.filter(Lead.status == 'hot').count(),
            'warm':      base.filter(Lead.status == 'warm').count(),
            'contacted': base.filter(Lead.status == 'contacted').count(),
            'converted': base.filter(Lead.status == 'converted').count(),
        }

        ai_svc = get_ai_service()
        result = ai_svc.chat(
            user_message,
            leads_context=leads_context,
            history=history,
            pipeline_stats=pipeline_stats,
        )

        _add_log('AI Chat', 'success', f"Q: {user_message[:60]}...")

        return jsonify({'status': 'success', **result}), 200
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        raise APIException(f"Chat failed: {str(e)}", status_code=500)


@ai_bp.route('/pipeline-summary', methods=['GET'])
@token_required
@handle_exceptions
def pipeline_summary():
    try:
        from app.models.models import db, Lead
        from sqlalchemy import func

        total = Lead.query.count()
        hot = Lead.query.filter_by(status='hot').count()
        warm = Lead.query.filter_by(status='warm').count()
        cold = Lead.query.filter(Lead.status.in_(['cold', 'pending'])).count()
        avg_row = db.session.query(func.avg(Lead.qualification_score)).scalar()
        avg_score = float(avg_row) if avg_row else 0.0
        with_email = Lead.query.filter(Lead.email.isnot(None), Lead.email != '').count()
        with_phone = Lead.query.filter(Lead.phone.isnot(None), Lead.phone != '').count()
        with_linkedin = Lead.query.filter(Lead.linkedin_url.isnot(None), Lead.linkedin_url != '').count()

        country_rows = db.session.query(Lead.country, func.count(Lead.id)).filter(
            Lead.country.isnot(None)
        ).group_by(Lead.country).order_by(func.count(Lead.id).desc()).limit(5).all()
        industry_rows = db.session.query(Lead.industry, func.count(Lead.id)).filter(
            Lead.industry.isnot(None)
        ).group_by(Lead.industry).order_by(func.count(Lead.id).desc()).limit(5).all()

        stats = {
            'total': total, 'hot': hot, 'warm': warm, 'cold': cold,
            'avg_score': avg_score,
            'countries': ', '.join(r[0] for r in country_rows if r[0]),
            'top_industries': ', '.join(r[0] for r in industry_rows if r[0]),
            'with_email': with_email, 'with_phone': with_phone, 'with_linkedin': with_linkedin,
        }

        sample_leads = [{
            'name': l.name, 'company': l.company, 'qualification_score': l.qualification_score,
            'status': l.status, 'country': l.country, 'industry': l.industry,
        } for l in Lead.query.order_by(Lead.qualification_score.desc()).limit(5).all()]

        ai_svc = get_ai_service()
        result = ai_svc.generate_pipeline_summary(stats, sample_leads)

        _add_log('Pipeline summary generated', 'success', f"{total} leads analyzed")

        return jsonify({
            'status': 'success',
            **result,
        }), 200
    except Exception as e:
        logger.error(f"Pipeline summary error: {e}")
        raise APIException(f"Failed to generate pipeline summary: {str(e)}", status_code=500)


# ============================================================================
# § 10 · SOCIAL LEAD COLLECTION  (/collect-social)
# ============================================================================

@ai_bp.route('/collect-social', methods=['POST'])
@token_required
@handle_exceptions
def collect_leads_from_social():
    """
    Collect leads from public social media groups/communities.
    Runs in background thread to avoid timeout with many platforms.

    Request Body:
        {
            "query": "SaaS startups",
            "platforms": ["reddit", "telegram", "twitter", "facebook"],
            "industry": "technology",          (optional)
            "max_per_platform": 10             (optional, default 10, max 30)
        }
    """
    import threading

    try:
        from app.models.models import db, Lead
        from app.services.social_media_collector import get_social_collector, PLATFORM_TYPES

        data = request.get_json(force=True, silent=True) or {}
        query = data.get('query', '').strip()
        platforms = data.get('platforms', [])
        industry = data.get('industry', '').strip()
        max_per_platform = min(int(data.get('max_per_platform', 10)), 30)
        collect_type = data.get('collect_type', 'both').strip().lower()  # person, company, both
        collect_location = data.get('location', '').strip()
        # Optional enrichment filters consumed by QueryPlanner
        _sc_titles    = [t for t in (data.get('titles') or []) if isinstance(t, str) and t.strip()]
        _sc_email_req = bool(data.get('email_required', False))

        if not query:
            return jsonify({'status': 'error', 'message': 'query is required'}), 400
        if not platforms or not isinstance(platforms, list):
            return jsonify({'status': 'error', 'message': 'platforms must be a non-empty list'}), 400

        invalid = [p for p in platforms if p.lower() not in PLATFORM_TYPES]
        if invalid:
            return jsonify({
                'status': 'error',
                'message': f'Unknown platforms: {invalid}',
                'supported_platforms': PLATFORM_TYPES,
            }), 400

        import uuid
        task_id = str(uuid.uuid4())
        _cleanup_old_tasks()
        _create_task(task_id, platforms, query)

        app = current_app._get_current_object()  # type: ignore[attr-defined]
        _social_user_id = g.user_id  # captured here; g is request-scoped and unavailable inside the thread

        def collect_social_in_background():
          with app.app_context():
            try:
                import time as _time
                from app.services.lead_quality_engine import CollectionQualityReport
                collector = get_social_collector()

                # ── QueryPlanner — build targeted queries before platform loop ─
                from app.search.query_planner import QueryPlanner as _QP
                _plan = _QP.build(query, {
                    'country':        collect_location,
                    'industry':       industry,
                    'lead_type':      collect_type,
                    'titles':         _sc_titles,
                    'email_required': _sc_email_req,
                })
                logger.info(
                    f"[social] QueryPlan: type={_plan.lead_type} "
                    f"linkedin_q={len(_plan.linkedin_queries)}"
                )

                n_platforms = len(platforms)
                all_leads: list = []
                quality_reports: list = []

                # Per-platform timeouts — still needed for collection phase
                _PLATFORM_TIMEOUT = {
                    'reddit': 45,   'twitter': 40, 'x': 40,
                    'facebook': 55, 'telegram': 55, 'linkedin': 60,
                }

                for idx, platform_name in enumerate(platforms):
                    platform_name = platform_name.lower().strip()
                    start_pct = max(5, int((idx / n_platforms) * 80))
                    end_pct   = max(start_pct + 5, int(((idx + 1) / n_platforms) * 80))
                    _update_task(task_id, current_platform=platform_name, percent=start_pct)
                    _plat_report = CollectionQualityReport(source=platform_name)

                    plat_timeout = _PLATFORM_TIMEOUT.get(platform_name, 55)

                    _loc_query = f"{query} {collect_location}".strip() if collect_location else query

                    def _run(p=platform_name, _lq=_loc_query):
                        if p == 'reddit':
                            return collector._collect_from_reddit(_lq, industry, max_per_platform)
                        elif p == 'telegram':
                            return collector._collect_from_telegram(_lq, max_per_platform)
                        elif p in ('twitter', 'x'):
                            return collector._collect_from_twitter(_lq, industry, max_per_platform)
                        elif p == 'facebook':
                            return collector._collect_from_facebook(_lq, industry, max_per_platform)
                        elif p == 'linkedin':
                            return collector._collect_from_linkedin(
                                _lq, industry, max_per_platform,
                                custom_queries=_plan.linkedin_queries or None,
                            )
                        return []

                    platform_leads: list = []
                    _result: list = [None, None]

                    def _run_in_thread():
                        try:
                            _result[0] = _run()
                        except Exception as _e:
                            _result[1] = _e

                    _t = threading.Thread(target=_run_in_thread, daemon=True)
                    _t.start()
                    elapsed = 0
                    poll = 3.0
                    while elapsed < plat_timeout:
                        _t.join(timeout=poll)
                        if not _t.is_alive():
                            if _result[1]:
                                logger.error(f"Platform {platform_name} error: {_result[1]}")
                            platform_leads = _result[0] or []
                            break
                        elapsed += poll
                        frac = min(elapsed / plat_timeout, 0.92)
                        live_pct = int(start_pct + frac * (end_pct - start_pct))
                        with _tasks_lock:
                            t = _collection_tasks.get(task_id)
                            if t and t.get('status') == 'running' and t.get('percent', 0) < live_pct:
                                t['percent'] = live_pct
                    else:
                        logger.warning(f"Platform {platform_name} timed out after {plat_timeout}s")

                    # Stage 1+2 candidate filter: reject page titles and non-business junk
                    # BEFORE quality gate so they don't inflate rejection counters.
                    try:
                        from app.services.lead_candidate_filter import filter_candidates as _fc
                        _n_before = len(platform_leads)
                        platform_leads = _fc(platform_leads, query=query, location=collect_location)
                        if len(platform_leads) < _n_before:
                            logger.info(
                                "[social/%s] candidate filter: %d → %d leads",
                                platform_name, _n_before, len(platform_leads),
                            )
                    except Exception as _fe:
                        logger.debug("[social] candidate filter error: %s", _fe)

                    # Stage 1+3 fast intelligence check: reject NGOs, universities,
                    # government, directories, aggregators, parked domains, and
                    # @handles BEFORE enrichment so Hunter credits are not wasted.
                    try:
                        from app.intelligence.fast_check import batch_fast_check as _bfc_social
                        _n_before_intel = len(platform_leads)
                        platform_leads, _social_intel_rej = _bfc_social(platform_leads)
                        if _social_intel_rej:
                            logger.info(
                                "[social/%s] fast intelligence check: %d → %d leads "
                                "(%d rejected)",
                                platform_name, _n_before_intel,
                                len(platform_leads), _social_intel_rej,
                            )
                    except Exception as _ife:
                        logger.debug("[social] fast intelligence check error: %s", _ife)

                    # Lightweight per-platform candidate collection (no Hunter, no quality gate).
                    # Hunter / ZeroBounce run ONLY after company passes intelligence (Stage 8).
                    for lead in platform_leads:
                        if 'lead_type' not in lead:
                            lead['lead_type'] = collector._classify_lead_type(lead)
                        _plat_report.raw_candidates += 1

                        # LinkedIn: resolve company domain cheaply (regex/DB lookup — no Hunter).
                        if platform_name == 'linkedin' and not lead.get('website') and lead.get('company'):
                            try:
                                _resolved = collector._find_company_domain(lead['company'])
                                if _resolved:
                                    lead['website'] = _resolved
                            except Exception:
                                pass

                        # Tag with button + platform for audit trail
                        lead.setdefault('_button', 'social_collect')
                        lead.setdefault('data_points', {})['platform'] = platform_name

                        all_leads.append(lead)

                    _plat_report.log_summary()
                    quality_reports.append(_plat_report.to_dict())
                    _update_task(task_id, completed_platforms=idx + 1, percent=end_pct,
                                 total_collected=len(all_leads))

                _update_task(task_id, percent=83, current_platform='intelligence',
                             total_collected=len(all_leads))

                # Filter by collect_type before intelligence so the orchestrator
                # processes only the lead types the user requested.
                if collect_type == 'person':
                    all_leads = [l for l in all_leads if (l.get('lead_type') or '').lower() != 'company']
                elif collect_type == 'company':
                    all_leads = [l for l in all_leads if (l.get('lead_type') or '').lower() != 'person']

                # ── Intelligence pipeline (company-first, 7 hard gates) ───────
                # All candidates must pass: anti_junk → website_audit →
                # business_classifier → user_intent → account_scorer →
                # contact_resolution (Hunter) → email_verify → save.
                # Raw candidates that fail any gate are rejected with a reason.
                saved_social_leads: list = []
                _social_duplicates = 0

                def _social_save_fn(lead_data: dict) -> bool:
                    nonlocal _social_duplicates
                    """DB write called by IntelligenceOrchestrator after company passes all gates."""
                    _co = (lead_data.get('company') or '').strip().rstrip('.')
                    if not _co:
                        return False

                    # Location fallback
                    if not lead_data.get('country') and collect_location:
                        _parts = [p.strip() for p in collect_location.split(',')]
                        lead_data['country'] = _parts[-1]
                        if not lead_data.get('city') and len(_parts) > 1:
                            lead_data['city'] = _parts[0]

                    _s_country = (lead_data.get('country') or '')[:100]
                    _s_city    = (lead_data.get('city') or '')[:100]
                    # Strip platform prefixes scraped into city (e.g. "Linked In Dubai" → "Dubai")
                    _PLATFORM_PREFIXES = ('linkedin', 'linked in', 'reddit', 'twitter', 'facebook', 'instagram')
                    _sc_lower = _s_city.strip().lower()
                    for _pfx in _PLATFORM_PREFIXES:
                        if _sc_lower.startswith(_pfx):
                            _s_city = _s_city.strip()[len(_pfx):].strip().strip('·-–—').strip()
                            break
                    # Reject city values that are job titles, not real cities
                    _TITLE_WORDS = {'ceo','cto','cmo','coo','founder','director','manager','owner','vp','president'}
                    if _s_city and _s_city.strip().lower() in _TITLE_WORDS:
                        _s_city = ''
                    # Don't store city when it equals the country name
                    if _s_city and _s_city.strip().lower() == _s_country.strip().lower():
                        _s_city = ''
                    _s_loc = (lead_data.get('location') or '')[:255]
                    if not _s_loc and (_s_country or _s_city):
                        _s_loc = ', '.join(p for p in [_s_city, _s_country] if p)

                    # DB dedup: scoped to current user so other users can collect same lead
                    try:
                        _uid = getattr(g, 'user_id', None)
                        if lead_data.get('email') and _uid:
                            if Lead.query.filter_by(email=lead_data['email'], collected_by=_uid).first():
                                _social_duplicates += 1
                                return False
                        if lead_data.get('name') and lead_data.get('source') and _uid:
                            if Lead.query.filter_by(
                                name=lead_data['name'], source=lead_data['source'], collected_by=_uid
                            ).first():
                                _social_duplicates += 1
                                return False
                    except Exception:
                        pass

                    # Use policy-tiered status from orchestrator
                    _social_suggested_status = lead_data.get('_suggested_status', 'unvalidated')

                    try:
                        _dp_s  = dict(lead_data.get('data_points') or {})
                        _int_s = _dp_s.get('intent') or {}
                        _bi_s  = (lead_data.get('buying_intent') or _int_s.get('buying_intent') or 'none')[:20]
                        _ic_s  = float(lead_data.get('intent_confidence') or _int_s.get('confidence') or 0.0)
                        _qs_s  = float(lead_data.get('final_company_score') or lead_data.get('qualification_score') or 0.0)
                        # Fill empty industry/interests from query + classifier
                        if not lead_data.get('industry') or not lead_data.get('interests'):
                            _inf_ind_s, _inf_int_s = _infer_industry_and_interests(query, lead_data)
                            if not lead_data.get('industry'):
                                lead_data['industry'] = _inf_ind_s
                            if not lead_data.get('interests'):
                                lead_data['interests'] = _inf_int_s
                        lead = Lead(
                            name=             (lead_data.get('name') or _co or '')[:255] or None,
                            email=            lead_data.get('email'),
                            phone=            lead_data.get('phone'),
                            company=          _co[:255],
                            position=         (lead_data.get('position') or '')[:255] or None,
                            location=         (_s_loc or '')[:255] or None,
                            country=          (_s_country or '')[:100] or None,
                            city=             (_s_city or '')[:100] or None,
                            industry=         (lead_data.get('industry') or '')[:100] or None,
                            website=          _sanitize_url(lead_data.get('website') or ''),
                            linkedin_url=     (lead_data.get('linkedin_url') or '')[:500] or None,
                            interests=        lead_data.get('interests', []),
                            source=           lead_data.get('source', 'social_media'),
                            lead_type=        lead_data.get('lead_type') or (
                                'person' if lead_data.get('position') or lead_data.get('linkedin_url')
                                else 'company'
                            ),
                            status=           _social_suggested_status,
                            qualification_score  = _qs_s,
                            completeness_score   = _qs_s,
                            buying_intent=    _bi_s,
                            intent_confidence=_ic_s,
                            email_type=       lead_data.get('email_type') or _dp_s.get('email_type'),
                            data_points=      _dp_s,
                            collected_by=     _social_user_id,
                        )
                        with db.session.begin_nested():
                            db.session.add(lead)
                        saved_social_leads.append(lead)
                        return True
                    except Exception as _dbe:
                        logger.warning(f"[social] DB save failed: {_dbe}", exc_info=True)
                        db.session.rollback()
                        return False

                from app.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
                from app.services.collection_policy import BALANCED_INTELLIGENCE as _SOCIAL_POLICY
                _social_orch = IntelligenceOrchestrator(
                    allowed_types=frozenset({'b2b_saas', 'b2b_services', 'ecommerce', 'unknown'}),
                    use_hunter=True,
                    use_zerobounce=True,
                    policy=_SOCIAL_POLICY,
                )
                _social_intel_report = _social_orch.run_pipeline(
                    candidates=all_leads,
                    query=query,
                    location=collect_location or '',
                    save_lead_fn=_social_save_fn,
                    collection_button='social_collect',
                )

                saved = _social_intel_report.n_saved
                if saved > 0:
                    try:
                        db.session.commit()
                        for _l in saved_social_leads:
                            if _l.id:
                                threading.Thread(
                                    target=_auto_enrich_lead_async,
                                    args=(_l.id, current_app.app_context()),
                                    daemon=True,
                                ).start()
                    except Exception as ce:
                        logger.error(f"[social] Failed to commit: {ce}")
                        db.session.rollback()
                        saved = 0

                total_rejected = _social_intel_report.n_rejected + _social_intel_report.n_needs_review
                logger.info(
                    f"[social] intelligence pipeline done: {saved}/{len(all_leads)} saved, "
                    f"{_social_intel_report.n_rejected} rejected, "
                    f"{_social_intel_report.n_needs_review} needs_review"
                )
                _update_task(
                    task_id, percent=100, status='done', saved=saved,
                    total_collected=len(all_leads), current_platform='',
                    quality_reports=quality_reports,
                    total_rejected=total_rejected,
                    duplicates=_social_duplicates,
                    intelligence_report=_social_intel_report.to_dict(),
                )

                _add_log(
                    'Social media collection completed',
                    'success' if saved > 0 else 'info',
                    f'Collected {len(all_leads)} leads from {", ".join(platforms)}, '
                    f'saved {saved} new, rejected {total_rejected}'
                )
            except Exception as e:
                logger.error(f"Background social collection error: {e}")
                _update_task(task_id, percent=100, status='error', current_platform='')
                db.session.rollback()

        thread = threading.Thread(target=collect_social_in_background, daemon=True)
        thread.start()

        return jsonify({
            'status': 'success',
            'message': f'Collecting from {len(platforms)} platform{"s" if len(platforms) > 1 else ""}...',
            'data': {
                'task_id': task_id,
                'platforms_searched': platforms,
                'query': query,
                'processing': True,
            }
        }), 202

    except Exception as e:
        logger.error(f"Social media collection error: {e}")
        raise APIException(f"Failed to collect from social media: {str(e)}", status_code=500)


@ai_bp.route('/collect-social/status/<task_id>', methods=['GET'])
@token_required
@limiter.exempt
@handle_exceptions
def collect_social_status(task_id):
    """Get progress of a background social collection task."""
    task = _get_task(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404
    return jsonify({'status': 'success', 'data': task}), 200


# ============================================================================
# § 11 · WEB LEAD COLLECTION  (/collect-leads)
# ============================================================================

@ai_bp.route('/collect-leads', methods=['POST'])
@token_required
@handle_exceptions
def collect_leads_from_web():
    """
    Async web collection with progress tracking (same pattern as social collection).
    Returns a task_id immediately, poll /collect-leads/status/<task_id> for progress.
    """
    import threading

    try:
        from app.models.models import db, Lead
        from app.services.public_web_collector import get_collector, COUNTRY_SOURCES

        data = request.get_json(force=True, silent=True) or {}
        query = data.get('query', '').strip()
        countries = data.get('countries', [])
        city = data.get('city', '').strip() or None
        max_per_country = min(int(data.get('max_per_country', 10)), 50)
        collection_type = data.get('collection_type', 'companies').strip().lower()
        # Optional enrichment filters consumed by QueryPlanner
        _wc_industry  = data.get('industry', '').strip()
        _wc_titles    = [t for t in (data.get('titles') or []) if isinstance(t, str) and t.strip()]
        _wc_email_req = bool(data.get('email_required', False))

        if collection_type not in ('companies', 'people'):
            collection_type = 'companies'

        if not query:
            return jsonify({'status': 'error', 'message': 'query is required'}), 400
        if not countries or not isinstance(countries, list):
            return jsonify({'status': 'error', 'message': 'countries must be a non-empty list of country codes'}), 400

        invalid = [c for c in countries if c not in COUNTRY_SOURCES]
        if invalid:
            return jsonify({
                'status': 'error',
                'message': f'Unknown country codes: {invalid}',
                'supported_countries': list(COUNTRY_SOURCES.keys()),
            }), 400

        import uuid
        task_id = str(uuid.uuid4())
        _cleanup_old_tasks()

        # Create task with web-specific fields
        with _tasks_lock:
            _collection_tasks[task_id] = {
                'id': task_id,
                'status': 'running',
                'query': query,
                'countries': countries,
                'total_countries': len(countries),
                'completed_countries': 0,
                'current_country': '',
                'saved': 0,
                'total_collected': 0,
                'percent': 0,
                'started_at': datetime.now(timezone.utc).isoformat(),
                'by_country': {},
            }

        app = current_app._get_current_object()  # type: ignore[attr-defined]
        _web_user_id = g.user_id  # captured here; g is request-scoped and unavailable inside the thread

        def collect_in_background():
          with app.app_context():
            try:
                import time as _time
                collector = get_collector()
                all_leads = []
                country_index = 0
                _city = city if len(countries) == 1 else None
                _deadline = _time.time() + 180  # 3-minute scraping deadline (AI planning already took ~20-40s)

                # ── AI Query Intelligence — runs ONCE before any API call ─────────
                # Gemini analyzes the query and returns a CollectionStrategy with:
                #  • custom Google search queries targeting named decision-makers
                #  • optimal source order (Apollo → Serper → Hunter → Places)
                #  • DM titles for Apollo people search
                #  • rejection signals to drop non-B2B results immediately
                from app.services.ai_collection_orchestrator import (
                    get_orchestrator as _get_orch,
                    is_valid_candidate as _is_valid_candidate,
                )
                _orch = _get_orch()
                _strategy_country = (
                    COUNTRY_SOURCES.get(countries[0], {}).get('name', countries[0])
                    if len(countries) == 1
                    else ', '.join(
                        COUNTRY_SOURCES.get(cc, {}).get('name', cc) for cc in countries[:3]
                    )
                )
                # ── QueryPlanner — deterministic filter merge + query generation ─
                from app.search.query_planner import QueryPlanner as _QP
                _plan = _QP.build(query, {
                    'country':        _strategy_country,
                    'city':           _city or '',
                    'lead_type':      collection_type,
                    'industry':       _wc_industry,
                    'titles':         _wc_titles,
                    'email_required': _wc_email_req,
                })
                logger.info(
                    f"[web] QueryPlan: type={_plan.lead_type} "
                    f"google_q={len(_plan.google_queries)} "
                    f"linkedin_q={len(_plan.linkedin_queries)}"
                )

                _strategy = _orch.analyze_query(
                    query=query,
                    country_name=_strategy_country,
                    country_code=countries[0] if len(countries) == 1 else '',
                    collection_type=collection_type,
                )

                # Merge: AI queries take priority; fall back to plan queries.
                # Append negative terms to all queries regardless of source.
                _neg_sfx = ' '.join(_plan.negative_terms[:6])
                if _strategy.search_queries:
                    _ai_queries = [
                        f"{q} {_neg_sfx}" if _neg_sfx not in q else q
                        for q in _strategy.search_queries
                    ]
                else:
                    _ai_queries = [
                        f"{q} {_neg_sfx}" for q in _plan.google_queries[:3]
                    ]

                logger.info(
                    f"[collect] AI strategy: intent={_strategy.intent} "
                    f"persona={_strategy.persona} provider={_strategy.provider} "
                    f"sources={_strategy.sources} "
                    f"dm_titles={_strategy.dm_titles[:4]} "
                    f"search_queries={len(_ai_queries)}"
                )
                _update_task(task_id, percent=5, current_stage=1, stage_name='AI Orchestrator',
                    strategy={
                        'intent': _strategy.intent,
                        'persona': _strategy.persona,
                        'sources': _strategy.sources,
                        'dm_titles': _strategy.dm_titles,
                        'rejection_signals': _strategy.rejection_signals,
                        'confidence': _strategy.confidence,
                        'provider': _strategy.provider,
                        'search_queries': _ai_queries[:3],
                    },
                    plan=_plan.as_debug_dict())

                for country_code in countries:
                    if _time.time() > _deadline:
                        logger.warning(f"[web] collection deadline reached — stopping after {country_index} countries")
                        break

                    # Base percent range for this country: e.g. 1 country = 5%→75%
                    _base_pct = max(5, int((country_index / len(countries)) * 75))
                    _next_pct = max(_base_pct + 5, int(((country_index + 1) / len(countries)) * 75))

                    def _on_url_progress(done, total, _b=_base_pct, _n=_next_pct):
                        if total <= 0:
                            return
                        pct = _b + int((done / total) * (_n - _b))
                        _update_task(task_id, current_country=country_code, percent=pct)

                    _update_task(task_id, current_country=country_code, percent=_base_pct,
                                 current_stage=2, stage_name='Discovery')
                    try:
                        if collection_type == 'people':
                            # ── Apollo first: highest-quality B2B person leads ────
                            # Titles come from AI strategy — targeted to the query intent.
                            apollo_leads: list = []
                            try:
                                from app.services.apollo_service import get_apollo_service
                                _apollo = get_apollo_service()
                                if _apollo.is_configured() and 'apollo' in _strategy.sources:
                                    _country_info = __import__(
                                        'app.services.public_web_collector',
                                        fromlist=['COUNTRY_SOURCES'],
                                    ).COUNTRY_SOURCES.get(country_code, {})
                                    _country_name = _country_info.get('name', country_code)
                                    _apollo_leads_raw = _apollo.search_people(
                                        keywords=query,
                                        titles=_strategy.dm_titles,   # AI-selected titles
                                        locations=[city or _country_name],
                                    )
                                    for _al in _apollo_leads_raw:
                                        if _al.get('name') and (
                                            _al.get('email') or _al.get('linkedin_url')
                                        ):
                                            _al['lead_type'] = 'person'
                                            apollo_leads.append(_al)
                                    if apollo_leads:
                                        logger.info(
                                            f"[collect] Apollo returned {len(apollo_leads)} "
                                            f"person leads for {country_code}"
                                        )
                            except Exception as _ae:
                                logger.debug(f"[collect] Apollo people search skipped: {_ae}")

                            # ── Web scraping + LinkedIn snippets ──────────────────
                            # _ai_queries: AI strategy queries + negative terms
                            # (built above after orchestrator call); plan fallback applied there.
                            web_leads = collector.collect_people_by_country(
                                query=query, country_code=country_code,
                                city=_city, max_leads=max_per_country,
                                deadline=_deadline, on_progress=_on_url_progress,
                                custom_queries=_ai_queries or None,
                            )
                            # Merge: Apollo first (verified emails), then web
                            seen_merge = set(
                                (l.get('email') or '').lower()
                                for l in apollo_leads if l.get('email')
                            )
                            for _wl in web_leads:
                                _we = ((_wl.get('email') or '').lower())
                                if not _we or _we not in seen_merge:
                                    apollo_leads.append(_wl)
                                    if _we:
                                        seen_merge.add(_we)
                            leads = apollo_leads[:max_per_country]
                        else:
                            leads = collector.collect_by_country(
                                query=query, country_code=country_code,
                                city=_city, max_leads=max_per_country,
                                deadline=_deadline, on_progress=_on_url_progress,
                            )
                        all_leads.extend(leads)
                        country_index += 1
                        with _tasks_lock:
                            if task_id in _collection_tasks:
                                _collection_tasks[task_id]['by_country'][country_code] = len(leads)
                        _update_task(task_id, completed_countries=country_index,
                                     total_collected=len(all_leads),
                                     percent=int((country_index / len(countries)) * 80))
                    except Exception as e:
                        logger.warning(f"Collection failed for {country_code}: {e}")
                        country_index += 1
                        with _tasks_lock:
                            if task_id in _collection_tasks:
                                _collection_tasks[task_id]['by_country'][country_code] = 0

                # ── Apollo B2B people search — real personal emails ──────────────
                # Runs once after web scraping. Uses AI-selected DM titles.
                try:
                    from app.services.apollo_service import ApolloService
                    _apollo = ApolloService()
                    if _apollo.is_configured() and not _apollo.needs_upgrade() and 'apollo' in _strategy.sources:
                        _country_names = [
                            COUNTRY_SOURCES.get(cc, {}).get('name', cc) for cc in countries
                        ]
                        _apollo_leads = _apollo.search_people(
                            keywords=query,
                            locations=_country_names,
                            titles=_strategy.dm_titles,   # AI-selected titles
                            per_page=min(max_per_country * len(countries), 25),
                        )
                        if _apollo_leads:
                            for _al in _apollo_leads:
                                _al['lead_type'] = 'person'
                                _al['source']    = 'apollo'
                                _al.setdefault('data_points', {})['email_verified'] = True
                                _al.setdefault('data_points', {})['email_source']   = 'apollo'
                            all_leads.extend(_apollo_leads)
                            logger.info(
                                f"[web] Apollo added {len(_apollo_leads)} person leads "
                                f"with personal emails"
                            )
                except Exception as _ae:
                    logger.debug(f"[web] Apollo search skipped: {_ae}")

                # ── News collector — named executives from press releases ────────
                # Pulls from BusinessWire, TechCrunch, PRNewswire, Google News feeds.
                # Returns name+company+position leads (no email) for Hunter enrichment.
                try:
                    from app.services.news_collector import get_news_collector as _get_nc
                    _nc_web = _get_nc()
                    _news_web_leads = _nc_web.collect(keywords=query,
                                                       max_results=min(max_per_country * len(countries), 20))
                    for _nl in _news_web_leads:
                        _nl['lead_type'] = 'person'
                        _nl['_source_query'] = f"news:{query}"
                        _nl.setdefault('_button', 'web_collect')
                    all_leads.extend(_news_web_leads)
                    if _news_web_leads:
                        logger.info(f"[web] News collector: {len(_news_web_leads)} leads from press releases")
                except Exception as _nce:
                    logger.debug(f"[web] News collector skipped: {_nce}")

                # ── GitHub collector — tech founders / open-source decision-makers ─
                # Uses GitHub Search API (free, unauthenticated; GITHUB_TOKEN lifts rate limit).
                # Returns self-reported name+company+email from public profiles.
                try:
                    from app.services.github_collector import get_github_collector as _get_gc
                    _gc_web = _get_gc()
                    _gh_locs = [COUNTRY_SOURCES.get(cc, {}).get('name', cc) for cc in countries[:2]]
                    _gh_web_leads = _gc_web.collect(
                        keywords=query,
                        locations=_gh_locs,
                        max_results=min(max_per_country, 15),
                    )
                    for _gl in _gh_web_leads:
                        _gl['lead_type'] = 'person'
                        _gl['_source_query'] = f"github:{query}"
                        _gl.setdefault('_button', 'web_collect')
                    all_leads.extend(_gh_web_leads)
                    if _gh_web_leads:
                        logger.info(f"[web] GitHub collector: {len(_gh_web_leads)} tech founder leads")
                except Exception as _ghe_web:
                    logger.debug(f"[web] GitHub collector skipped: {_ghe_web}")

                _update_task(task_id, percent=82, current_country='pipeline',
                             total_collected=len(all_leads),
                             current_stage=3, stage_name='Normalization + Dedup')

                # ── Lead type filter (respect user's "companies" vs "people" choice) ──
                if collection_type == 'companies':
                    all_leads = [l for l in all_leads if (l.get('lead_type') or '').lower() != 'person']
                elif collection_type == 'people':
                    all_leads = [l for l in all_leads if (l.get('lead_type') or '').lower() != 'company']

                # ── Fast intelligence pre-check (no HTTP) ────────────────────
                # Removes NGOs, universities, government entities, directories,
                # aggregator pages, URL names, @handles BEFORE the 9-stage pipeline
                # so enrichment/Hunter credits are not wasted on junk.
                try:
                    from app.intelligence.fast_check import batch_fast_check as _bfc_web
                    _n_web_before = len(all_leads)
                    all_leads, _web_intel_rej = _bfc_web(all_leads)
                    if _web_intel_rej:
                        logger.info(
                            "[web] fast intelligence check: %d → %d leads "
                            "(%d rejected as non-business)",
                            _n_web_before, len(all_leads), _web_intel_rej,
                        )
                except Exception as _wif_err:
                    logger.debug("[web] fast intelligence check error: %s", _wif_err)

                # ── Full 9-stage pipeline ─────────────────────────────────────
                # Each candidate flows through:
                #  2. Dedup  3. Pre-filter  4. Enrich  5. Intent  6. Verify
                #  7. Quality Gate  8. ML Qualify  9. Intelligence  → Save
                from app.services.lead_quality_engine import CollectionQualityReport
                from app.services.candidate_pipeline import CandidatePipeline

                web_report = CollectionQualityReport(source='public_web')
                saved_web_leads = []

                def _db_save_fn(lead_data: dict) -> bool:
                    """DB write + dedup check called by pipeline at Stage 10."""
                    _co = (lead_data.get('company') or '').strip().rstrip('.')
                    if not _co:
                        return False

                    # Tagline/bio guard — scraped bios often land in company field
                    _co_lower = _co.lower()
                    _is_tagline = (
                        len(_co.split()) > 5 or
                        any(_co_lower.startswith(p) for p in (
                            'we ', 'i ', 'our ', 'my ', 'the ', 'a ', 'an ',
                            'helping ', 'building ', 'creating ', 'making ',
                        )) or
                        any(w in _co_lower for w in (
                            ' invest ', ' believe ', ' strive ', ' mission ',
                        ))
                    )
                    if _is_tagline:
                        return False

                    # DB dedup: scoped to current user so other users can collect same lead
                    try:
                        _uid = getattr(g, 'user_id', None)
                        if lead_data.get('email') and _uid:
                            if Lead.query.filter_by(email=lead_data['email'], collected_by=_uid).first():
                                web_report.record_duplicate()
                                return False
                        if lead_data.get('company') and lead_data.get('country') and _uid:
                            if Lead.query.filter_by(
                                company=lead_data['company'],
                                country=lead_data['country'],
                                collected_by=_uid,
                            ).first():
                                web_report.record_duplicate()
                                return False
                    except Exception:
                        pass

                    # Use policy-tiered status from orchestrator
                    _web_suggested_status = lead_data.get('_suggested_status', 'unvalidated')

                    try:
                        _save_country = (lead_data.get('country') or '')[:100]
                        _save_city    = (lead_data.get('city') or '')[:100]
                        _TITLE_WORDS_W = {'ceo','cto','cmo','coo','founder','director','manager','owner','vp','president'}
                        if _save_city and _save_city.strip().lower() in _TITLE_WORDS_W:
                            _save_city = ''
                        # Don't store city when it equals the country name
                        if _save_city and _save_city.strip().lower() == _save_country.strip().lower():
                            _save_city = ''
                        _save_loc = (lead_data.get('location') or '')[:255]
                        if not _save_loc and (_save_country or _save_city):
                            _save_loc = ', '.join(p for p in [_save_city, _save_country] if p)

                        _dp_w  = dict(lead_data.get('data_points') or {})
                        _int_w = _dp_w.get('intent') or {}
                        _bi_w  = (lead_data.get('buying_intent') or _int_w.get('buying_intent') or 'none')[:20]
                        _ic_w  = float(lead_data.get('intent_confidence') or _int_w.get('confidence') or 0.0)
                        _qs_w  = float(lead_data.get('final_company_score') or lead_data.get('qualification_score') or 30.0)
                        # Fill empty industry/interests from query + classifier
                        if not lead_data.get('industry') or not lead_data.get('interests'):
                            _inf_ind_w, _inf_int_w = _infer_industry_and_interests(query, lead_data)
                            if not lead_data.get('industry'):
                                lead_data['industry'] = _inf_ind_w
                            if not lead_data.get('interests'):
                                lead_data['interests'] = _inf_int_w
                        lead = Lead(
                            name=             (lead_data.get('name') or _co or '')[:255] or None,
                            email=            lead_data.get('email'),
                            phone=            lead_data.get('phone'),
                            company=          _co[:255],
                            position=         (lead_data.get('position') or '')[:255] or None,
                            location=         _save_loc or None,
                            country=          _save_country or None,
                            city=             _save_city or None,
                            industry=         _norm_industry(lead_data.get('industry') or '')[:100] or None,
                            website=          _sanitize_url(lead_data.get('website') or ''),
                            linkedin_url=     (lead_data.get('linkedin_url') or '')[:500] or None,
                            interests=        lead_data.get('interests', []),
                            source=           lead_data.get('source', 'web_public'),
                            lead_type=        lead_data.get('lead_type') or (
                                'person' if lead_data.get('position') or lead_data.get('linkedin_url')
                                else 'company'
                            ),
                            status=           _web_suggested_status,
                            qualification_score  = _qs_w,
                            completeness_score   = _qs_w,
                            buying_intent=    _bi_w,
                            intent_confidence=_ic_w,
                            email_type=       _classify_email_type(
                                lead_data.get('email') or '',
                                lead_data.get('email_type') or _dp_w.get('email_type') or '',
                            ),
                            data_points=      _dp_w,
                            collected_by=     _web_user_id,
                        )
                        db.session.add(lead)
                        db.session.commit()
                        saved_web_leads.append(lead)
                        return True
                    except Exception as _dbe:
                        logger.warning(f"[pipeline] DB save failed: {_dbe}", exc_info=True)
                        db.session.rollback()
                        return False

                def _pipeline_stage_cb(stage_num, stage_name, counts=None):
                    _update_task(task_id, current_stage=stage_num, stage_name=stage_name,
                                 pipeline_counts=counts or {})

                # ── Tag all leads with button source ────────────────────────
                for _l in all_leads:
                    _l.setdefault('_button', 'web_collect')

                # ── Company-first intelligence pipeline ─────────────────────
                # All candidates must pass: anti_junk → website_audit →
                # business_classifier → user_intent → account_scorer (7 gates)
                # → contact_resolution → email_verify → save.
                # Hunter / ZeroBounce are ONLY called after company passes.
                _web_location = (
                    ', '.join(
                        COUNTRY_SOURCES.get(cc, {}).get('name', cc)
                        for cc in countries[:1]
                    ) if countries else (city or '')
                )
                # 'unknown' lets the classifier pass businesses it can't categorise as SaaS
                _web_allowed_types = frozenset({'b2b_saas', 'b2b_services', 'ecommerce', 'unknown'})

                # BALANCED runs all 7 gates including Gate 4 (location/intent match),
                # which rejects companies clearly from a different country than the search.
                from app.services.collection_policy import BALANCED_INTELLIGENCE as _WEB_POLICY
                pipeline = CandidatePipeline()
                pipeline.run(
                    candidates=all_leads,
                    source='public_web',
                    save_lead_fn=_db_save_fn,
                    report=web_report,
                    options={
                        # ── Intelligence gate (company-first) ─────────────────
                        'company_first_mode': True,
                        'policy':            _WEB_POLICY,
                        'query':             query,
                        'location':          _web_location,
                        'allowed_types':     _web_allowed_types,
                        # ── Legacy options (used when company_first_mode=False) ─
                        'strategy':          _strategy,
                        'collection_type':   collection_type,
                        'intent':            _strategy.intent,
                        'region':            countries[0] if len(countries) == 1 else 'unknown',
                        'use_hunter':        True,
                        'use_verify':        True,
                        'use_ml':            True,
                        'use_intelligence':  True,
                        'min_score':         35,
                        'stage_callback':    _pipeline_stage_cb,
                    },
                )

                saved = web_report.saved

                # Deep intelligence analysis + final scoring run in background
                # on every saved lead (post-save non-blocking).
                for _l in saved_web_leads:
                    if _l.id:
                        threading.Thread(
                            target=_auto_enrich_lead_async,
                            args=(_l.id, current_app.app_context()),
                            daemon=True,
                        ).start()

                logger.info(
                    f"[pipeline] complete: {saved}/{len(all_leads)} saved, "
                    f"{web_report.rejected} rejected, {web_report.duplicates} dupes"
                )
                _update_task(
                    task_id, percent=100, status='done', saved=saved,
                    total_collected=len(all_leads), current_country='',
                    quality_report=web_report.to_dict(),
                    total_rejected=web_report.rejected,
                    duplicates=web_report.duplicates,
                    rejection_reasons=dict(web_report.rejection_reasons),
                    current_stage=10, stage_name='Complete',
                )
            except Exception as e:
                logger.error(f"Background web collection error: {e}")
                _update_task(task_id, percent=100, status='error', current_country='')
                db.session.rollback()

        thread = threading.Thread(target=collect_in_background, daemon=True)
        thread.start()

        return jsonify({
            'status': 'success',
            'message': f'Collecting from {len(countries)} {"country" if len(countries) == 1 else "countries"}...',
            'data': {
                'task_id': task_id,
                'query': query,
                'countries': countries,
                'max_per_country': max_per_country,
                'processing': True,
            }
        }), 202

    except Exception as e:
        logger.error(f"Error starting lead collection: {e}")
        raise APIException(f"Failed to start lead collection: {str(e)}", status_code=500)


@ai_bp.route('/collect-leads/status/<task_id>', methods=['GET'])
@token_required
@limiter.exempt
@handle_exceptions
def collect_leads_status(task_id):
    """Get progress of a background web collection task."""
    task = _get_task(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404
    return jsonify({'status': 'success', 'data': task}), 200


@ai_bp.route('/collect-leads/sync', methods=['POST'])
@token_required
@handle_exceptions
def collect_leads_sync():
    """
    Synchronous version - collect leads and return results immediately.
    Supports both company and people collection modes.
    
    Request Body:
        {
            "query": "marketing agencies",
            "countries": ["US", "UK"],
            "city": "New York",
            "max_per_country": 10,
            "collection_type": "companies"   // "companies" or "people"
        }
    """
    try:
        from app.models.models import db, Lead
        from app.services.public_web_collector import get_collector, COUNTRY_SOURCES

        data = request.get_json(force=True, silent=True) or {}
        query = data.get('query', '').strip()
        countries = data.get('countries', [])
        city = data.get('city', '').strip() or None
        max_per_country = min(int(data.get('max_per_country', 5)), 20)
        collection_type = data.get('collection_type', 'companies').strip().lower()

        if collection_type not in ('companies', 'people'):
            collection_type = 'companies'

        if not query:
            return jsonify({'status': 'error', 'message': 'query is required'}), 400
        if not countries or not isinstance(countries, list):
            return jsonify({'status': 'error', 'message': 'countries must be a non-empty list'}), 400

        invalid = [c for c in countries if c not in COUNTRY_SOURCES]
        if invalid:
            return jsonify({
                'status': 'error',
                'message': f'Unknown country codes: {invalid}',
            }), 400

        collector = get_collector()
        all_leads = []
        country_stats = {}

        import time as _time
        _t0 = _time.time()
        logger.info(f"Sync collection ({collection_type}): query='{query}', countries={countries}, city={city}, max={max_per_country}")

        for country_code in countries:
            try:
                if collection_type == 'people':
                    leads = collector.collect_people_by_country(
                        query=query,
                        country_code=country_code,
                        city=city if len(countries) == 1 else None,
                        max_leads=max_per_country,
                    )
                else:
                    leads = collector.collect_by_country(
                        query=query,
                        country_code=country_code,
                        city=city if len(countries) == 1 else None,
                        max_leads=max_per_country,
                    )
                all_leads.extend(leads)
                country_stats[country_code] = len(leads)
            except Exception as e:
                logger.warning(f"Collection failed for {country_code}: {e}")
                country_stats[country_code] = 0

        # Batch enrichment (Hunter + Explorium + AI field fill) — once after collection
        try:
            from app.services.lead_fallback import enrich_lead_fallbacks
            _enriched = []
            for _rl in all_leads:
                try:
                    _enriched.append(enrich_lead_fallbacks(
                        _rl, scrape_contact=False, use_hunter=True,
                        generate_email=False, debug=False,
                    ))
                except Exception:
                    _enriched.append(_rl)
            all_leads = _enriched
        except Exception as _enr_err:
            logger.warning(f"[web-sync] batch enrichment error: {_enr_err}")

        # Email verification — SMTP-confirm emails before quality gate
        _with_email = [ld for ld in all_leads if ld.get('email')]
        if _with_email:
            try:
                from app.services.email_verifier import bulk_verify
                bulk_verify(_with_email, max_to_verify=20)
            except Exception as _ve:
                logger.debug(f"[web-sync] email verification skipped: {_ve}")

        # Save to database
        from app.services.lead_quality_engine import (
            evaluate_lead_quality, CollectionQualityReport,
        )
        sync_report = CollectionQualityReport(source='web_sync')
        saved = 0
        skipped_sync = 0
        saved_leads = []
        for lead_data in all_leads:
            sync_report.raw_candidates += 1
            try:
                # Quality gate — same strict rules as the async web collection path
                _qd = evaluate_lead_quality(lead_data, source='web_sync', report=sync_report)
                if not _qd.should_save:
                    logger.debug(
                        f"[web-sync] lead rejected by quality gate: "
                        f"tier={_qd.tier} reasons={_qd.reasons}"
                    )
                    skipped_sync += 1
                    continue

                lead_data.setdefault('data_points', {}).update(_qd.metadata)
                lead_data['qualification_score'] = _qd.quality_score
                sync_report.record_score(_qd.quality_score)
                sync_report.parsed_candidates += 1

                # DB dedup: scoped to current user so other users can collect same lead
                existing = None
                _uid_sync = getattr(g, 'user_id', None)
                _dp_sync = lead_data.get('data_points') or {}
                if lead_data.get('email') and _dp_sync.get('email_verified') and _uid_sync:
                    existing = Lead.query.filter_by(email=lead_data['email'], collected_by=_uid_sync).first()
                if not existing and lead_data.get('company') and lead_data.get('country') and _uid_sync:
                    existing = Lead.query.filter_by(
                        company=lead_data['company'],
                        country=lead_data['country'],
                        collected_by=_uid_sync,
                    ).first()
                if existing:
                    sync_report.record_duplicate()
                    continue

                lead = Lead(
                    name=(lead_data.get('name') or 'Unknown')[:255],
                    email=lead_data.get('email'),
                    phone=lead_data.get('phone'),
                    company=(lead_data.get('company') or '')[:255],
                    position=lead_data.get('position'),
                    location=lead_data.get('location'),
                    country=lead_data.get('country'),
                    city=lead_data.get('city'),
                    industry=_norm_industry(lead_data.get('industry') or ''),
                    website=lead_data.get('website'),
                    linkedin_url=lead_data.get('linkedin_url'),
                    interests=lead_data.get('interests', []),
                    source=lead_data.get('source', 'web_public'),
                    lead_type=lead_data.get('lead_type'),
                    status='pending',
                    qualification_score=_qd.quality_score,
                    email_type=_classify_email_type(
                        lead_data.get('email') or '',
                        lead_data.get('email_type') or '',
                    ),
                    data_points=lead_data.get('data_points', {}),
                )
                db.session.add(lead)
                saved += 1
                saved_leads.append({
                    'name': lead.name,
                    'email': lead.email,
                    'company': lead.company,
                    'country': lead.country,
                    'city': lead.city,
                    'industry': lead.industry,
                    'score': lead.qualification_score,
                    'lead_type': lead.lead_type,
                })
            except Exception as e:
                logger.warning(f"Failed to save lead: {e}")

        sync_report.log_summary()
        logger.info(
            f"[web-sync] quality gate: {saved} saved, {skipped_sync} rejected"
        )
        if saved > 0:
            db.session.commit()

        duration = round(_time.time() - _t0, 2)
        return jsonify({
            'status': 'success',
            'message': f'Collected {len(all_leads)} leads, saved {saved} new leads',
            'data': {
                'total_collected': len(all_leads),
                'total_saved': saved,
                'by_country': country_stats,
                'duration_seconds': duration,
                'leads': saved_leads[:50],  # Return first 50 for preview
            }
        }), 200

    except Exception as e:
        logger.error(f"Sync collection error: {e}")
        raise APIException(f"Failed to collect leads: {str(e)}", status_code=500)


@ai_bp.route('/supported-countries', methods=['GET'])
@token_required
@handle_exceptions
def get_supported_countries_route():
    """Get list of supported countries for web collection"""
    from app.services.public_web_collector import get_supported_countries
    countries = get_supported_countries()
    return jsonify({
        'status': 'success',
        'countries': countries,
        'total': len(countries),
    }), 200


# ============================================================================
# § 12 · INTEREST-BASED COLLECTION  (/collect-by-interest)
# ============================================================================

@ai_bp.route('/lead-categories', methods=['GET'])
@token_required
@handle_exceptions
def get_lead_categories():
    """
    Return all available lead categories for interest-based collection.

    Response:
        {
            "status": "success",
            "categories": [
                {
                    "slug": "laptops",
                    "name": "Laptops",
                    "keywords": [...],
                    "intent_phrases": [...],
                    "source_types": [...],
                    "minimum_quality_score": 35.0
                },
                ...
            ],
            "total": 16
        }
    """
    from config.lead_categories import CATEGORIES
    cats = []
    for slug, cat in sorted(CATEGORIES.items(), key=lambda x: x[1].category_name):
        cats.append({
            'slug':                  slug,
            'name':                  cat.category_name,
            'keywords':              cat.keywords,
            'intent_phrases':        cat.intent_phrases,
            'source_types':          cat.source_types,
            'minimum_quality_score': cat.minimum_quality_score,
        })
    return jsonify({
        'status':     'success',
        'categories': cats,
        'total':      len(cats),
    }), 200


@ai_bp.route('/collect-by-interest', methods=['POST'])
@token_required
@handle_exceptions
def collect_leads_by_interest():
    """
    Start an async interest-based collection task.

    Returns task_id immediately (HTTP 202). Poll
    /ai/collect-by-interest/status/<task_id> for progress.
    """
    """

    Request Body:
        {
            "category":  "electronics",
            "country":   "Argentina",
            "city":      "Buenos Aires",   // optional
            "max_leads": 30,
            "sources":   ["web", "directories", "news"]  // optional
        }

    Response (202):
        {
            "status":  "success",
            "task_id": "<uuid>",
            "message": "Interest collection started for Electronics / Argentina"
        }
    """
    import uuid
    from config.lead_categories import get_category

    data          = request.get_json(force=True, silent=True) or {}
    category_name = (data.get('category') or '').strip()
    country_name  = (data.get('country')  or '').strip()
    city          = (data.get('city')      or '').strip() or None
    max_leads     = min(int(data.get('max_leads', 30)), 200)
    sources       = data.get('sources')

    if not category_name:
        return jsonify({'status': 'error', 'message': 'category is required'}), 400
    if not country_name:
        return jsonify({'status': 'error', 'message': 'country is required'}), 400

    cat = get_category(category_name)
    if cat is None:
        from config.lead_categories import list_category_names
        return jsonify({
            'status':  'error',
            'message': f"Unknown category: '{category_name}'",
            'available_categories': list_category_names(),
        }), 400

    if sources is not None:
        valid_sources = {'web', 'social', 'news', 'directories', 'github'}
        bad = [s for s in sources if s not in valid_sources]
        if bad:
            return jsonify({
                'status':  'error',
                'message': f"Invalid sources: {bad}. Valid: {sorted(valid_sources)}",
            }), 400

    task_id = str(uuid.uuid4())
    _cleanup_old_tasks()

    location_label = f"{cat.category_name} / {country_name}" + (f" / {city}" if city else "")
    with _tasks_lock:
        _collection_tasks[task_id] = {
            'id':           task_id,
            'status':       'running',
            'type':         'interest',
            'category':     cat.category_name,
            'country':      country_name,
            'city':         city,
            'percent':      0,
            'stage_name':   'Starting...',
            'saved':        0,
            'rejected':     0,
            'duplicates':   0,
            'raw_candidates': 0,
            'quality_report': None,
            'error':        None,
            'started_at':   datetime.now(timezone.utc).isoformat(),
        }

    app_ctx = current_app.app_context()  # type: ignore[attr-defined]
    _interest_user_id = g.user_id  # captured here; g is request-scoped and unavailable inside the thread

    def collect_interest_in_background():
        with app_ctx:
            try:
                from app.models.models import db
                from app.services.interest_collector import collect_by_interest

                def _on_progress(pct: int, msg: str) -> None:
                    _update_task(task_id, percent=pct, stage_name=msg)

                _add_log(f"Interest collection started: {location_label}", status='info')

                report = collect_by_interest(
                    category_name=category_name,
                    country_name=country_name,
                    city=city,
                    max_leads=max_leads,
                    sources=sources,
                    db_session=db.session,
                    progress_callback=_on_progress,
                    collected_by=_interest_user_id,
                )

                _add_log(
                    f"Interest collection done: {cat.category_name} — "
                    f"saved {report.saved}, rejected {report.rejected}",
                    status='success' if report.saved > 0 else 'warning',
                )

                # Auto-enrich every saved lead in a background thread
                for _lid in (report.saved_lead_ids or []):
                    threading.Thread(
                        target=_auto_enrich_lead_async,
                        args=(_lid, current_app.app_context()),
                        daemon=True,
                    ).start()

                _update_task(
                    task_id,
                    status='done',
                    percent=100,
                    stage_name=f"Done — saved {report.saved} leads",
                    saved=report.saved,
                    rejected=report.rejected,
                    duplicates=report.duplicates,
                    raw_candidates=report.raw_candidates,
                    quality_report=report.to_dict(),
                )

            except RuntimeError as exc:
                logger.warning("[Interest] collection aborted: %s", exc)
                _update_task(task_id, status='error', percent=100,
                             stage_name='Failed', error=str(exc))
            except Exception as exc:
                logger.error("[Interest] collection error: %s", exc, exc_info=True)
                _update_task(task_id, status='error', percent=100,
                             stage_name='Failed', error=str(exc))

    threading.Thread(target=collect_interest_in_background, daemon=True).start()

    return jsonify({
        'status':  'success',
        'task_id': task_id,
        'message': f"Interest collection started for {location_label}",
        'data':    {'task_id': task_id, 'processing': True},
    }), 202


@ai_bp.route('/collect-by-interest/status/<task_id>', methods=['GET'])
@token_required
@limiter.exempt
@handle_exceptions
def collect_interest_status(task_id):
    """Get progress of a background interest collection task."""
    task = _get_task(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404
    return jsonify({'status': 'success', 'data': task}), 200


# ============================================================================
# § 13 · ML MODEL TRAINING & VERSIONING  (/train-ml · /retrain)
# ============================================================================

@ai_bp.route('/train-ml', methods=['POST'])
@token_required
@admin_required
@limiter.limit("5 per hour")
@handle_exceptions
def train_ml_model():
    """
    Train (or re-train) the local ML scoring model using qualified leads from the DB.
    Requires at least 10 leads with qualification scores.

    Returns training summary with number of leads used and whether training succeeded.
    """
    try:
        from app.models.models import Lead

        # Fetch all leads that have a qualification score
        leads_q = Lead.query.filter(
            Lead.qualification_score.isnot(None),
            Lead.qualification_score > 0,
        ).all()

        if not leads_q:
            return jsonify({
                'status': 'error',
                'message': 'No qualified leads found. Run AI qualification first.',
            }), 400

        # Convert ORM objects to dicts that extract_features() understands
        lead_dicts = []
        for l in leads_q:
            lead_dicts.append({
                'name': l.name or '',
                'email': l.email or '',
                'phone': l.phone or '',
                'company': l.company or '',
                'position': l.position or '',
                'industry': l.industry or '',
                'linkedin_url': l.linkedin_url or '',
                'website': l.website or '',
                'source': l.source or '',
                'interests': l.interests or [],
                'qualification_score': float(l.qualification_score),
            })

        success = train_ml_model_from_leads(lead_dicts)

        if success:
            hot  = sum(1 for l in lead_dicts if l['qualification_score'] >= 80)
            warm = sum(1 for l in lead_dicts if 60 <= l['qualification_score'] < 80)
            cold = sum(1 for l in lead_dicts if l['qualification_score'] < 60)

            # Pull training stats from the saved model
            from app.services.ml_model import XGBLeadScoringModel
            m = XGBLeadScoringModel()
            m.load_model()
            stats = m.training_stats or {}

            _add_log(
                'ML model trained',
                'success',
                f'{len(lead_dicts)} leads — AUC:{stats.get("hold_out_auc", "N/A")}',
            )
            return jsonify({
                'status': 'success',
                'message': f'ML model trained on {len(lead_dicts)} leads',
                'data': {
                    'leads_used': len(lead_dicts),
                    'hot_labels': hot,
                    'warm_labels': warm,
                    'cold_labels': cold,
                    'cv_accuracy': stats.get('cv_accuracy'),
                    'cv_std': stats.get('cv_std'),
                    'positive_rate_pct': stats.get('positive_rate'),
                    'algorithm': 'GradientBoosting + Platt calibration',
                    'features': 12,
                },
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': f'Training failed — need at least 10 scored leads (found {len(lead_dicts)})',
            }), 400

    except Exception as e:
        logger.error(f"ML training error: {e}")
        raise APIException(f"Failed to train ML model: {str(e)}", status_code=500)


@ai_bp.route('/retrain', methods=['POST'])
@token_required
@admin_required
@limiter.limit("10 per hour")
@handle_exceptions
def retrain_model():
    """
    Full retraining pipeline with stratified splits, metric logging, and old-vs-new comparison.

    Body (all optional):
      {
        "force": false,          // skip AUC regression guard
        "use_db": true,          // pull labels from LeadOutcome DB table
        "balance": "auto",       // auto | smote | weighted | none
        "min_leads": 20,         // minimum labeled leads required
        "synthetic_n": 0         // extra synthetic leads to blend in (0-50000)
      }

    Returns full training report: AUC, precision, recall, F1, improvement vs old model.
    """
    try:
        from app.models.models import db, Lead
        from app.services.ml_model import XGBLeadScoringModel
        from app.services.ml_decision_layer import get_decision_layer

        body         = request.get_json(force=True, silent=True) or {}
        force        = bool(body.get('force', False))
        use_db       = bool(body.get('use_db', True))
        balance      = body.get('balance', 'auto')
        min_leads    = int(body.get('min_leads', 20))
        synthetic_n  = min(int(body.get('synthetic_n', 0)), 50_000)

        dl    = get_decision_layer()
        model = XGBLeadScoringModel()
        model.load_model()
        old_stats = dict(model.training_stats) if model.training_stats else {}

        leads_as_dicts = []

        if use_db:
            # Pull leads with verified labels from LeadOutcome
            try:
                from app.services.dataset_manager import get_dataset_manager
                manager = get_dataset_manager()
                result  = manager.build_training_dataset(balance_method=balance)
                leads_as_dicts = result.leads
                logger.info(
                    f"[retrain] DB dataset: n={result.stats['n_total']} "
                    f"pos={result.stats['positive_rate']:.1%}"
                )
            except Exception as db_err:
                logger.warning(f"[retrain] DB dataset failed, falling back to scored leads: {db_err}")

        if not leads_as_dicts:
            # Fallback: all DB leads with qualification scores
            db_leads = Lead.query.filter(
                Lead.qualification_score.isnot(None),
                Lead.qualification_score > 0,
            ).all()
            for l in db_leads:
                leads_as_dicts.append({
                    'name': l.name or '', 'email': l.email or '',
                    'phone': l.phone or '', 'company': l.company or '',
                    'position': l.position or '', 'industry': l.industry or '',
                    'linkedin_url': l.linkedin_url or '', 'website': l.website or '',
                    'source': l.source or '', 'interests': l.interests or [],
                    'country': l.country or '', 'city': l.city or '',
                    'notes': getattr(l, 'notes', '') or '',
                    'qualification_score': float(l.qualification_score),
                })
            # Also add JSONL labeled records
            labeled = dl.dataset.load_labeled()
            for rec in labeled:
                label = rec['label']
                leads_as_dicts.append({
                    '_features_override': rec.get('features', []),
                    'qualification_score': int(label * 100),
                    '_label': int(label),
                })

        # Blend in synthetic data if requested
        n_synthetic_used = 0
        if synthetic_n > 0:
            try:
                from pathlib import Path as _Path
                synth_path = _Path(__file__).resolve().parent.parent.parent / 'data' / 'synthetic_leads.json'
                if synth_path.exists():
                    import json as _json
                    with open(synth_path) as _fh:
                        synth_pool = _json.load(_fh)
                    import random as _random
                    sample = _random.sample(synth_pool, min(synthetic_n, len(synth_pool)))
                else:
                    from app.services.data_generator import get_generator
                    sample = get_generator().generate(n=synthetic_n)
                leads_as_dicts.extend(sample)
                n_synthetic_used = len(sample)
                logger.info(f"[retrain] blended {n_synthetic_used} synthetic leads — total: {len(leads_as_dicts)}")
            except Exception as _syn_err:
                logger.warning(f"[retrain] synthetic blend failed: {_syn_err}")

        if len(leads_as_dicts) < min_leads:
            return jsonify({
                'status': 'error',
                'message': f'Not enough labeled leads: {len(leads_as_dicts)} < {min_leads}',
                'hint':    'Submit feedback via POST /api/v1/ai/feedback to label leads',
            }), 400

        # If force mode, temporarily override the guard threshold
        if force:
            # Clear current model so comparison shows 0 baseline (no regression block)
            model.model = None
            model.training_stats = {}

        success = model.train_from_leads(leads_as_dicts)

        new_stats = model.training_stats or {}
        old_auc   = old_stats.get('hold_out_auc', 0.0)
        new_auc   = new_stats.get('hold_out_auc', 0.0)

        # Write metrics to metrics history file
        _append_metrics_history(new_stats)

        _add_log(
            'ML model retrained',
            'success' if success else 'error',
            f'{len(leads_as_dicts)} leads — AUC:{new_auc}  old:{old_auc}',
        )

        return jsonify({
            'status':   'success' if success else 'degraded',
            'retrained': success,
            'leads_used': len(leads_as_dicts),
            'synthetic_used': n_synthetic_used,
            'old_model': {
                'auc':       old_auc,
                'accuracy':  old_stats.get('hold_out_accuracy'),
                'precision': old_stats.get('hold_out_precision'),
                'recall':    old_stats.get('hold_out_recall'),
                'f1':        old_stats.get('hold_out_f1'),
                'n_samples': old_stats.get('n_samples'),
                'trained_at': old_stats.get('trained_at'),
            },
            'new_model': {
                'auc':       new_auc,
                'accuracy':  new_stats.get('hold_out_accuracy'),
                'precision': new_stats.get('hold_out_precision'),
                'recall':    new_stats.get('hold_out_recall'),
                'f1':        new_stats.get('hold_out_f1'),
                'n_samples': new_stats.get('n_samples'),
                'cv_auc':    new_stats.get('best_cv_auc'),
                'trained_at': new_stats.get('trained_at'),
            },
            'improvement': {
                'auc_delta': round(new_auc - old_auc, 4) if (old_auc and new_auc) else None,
                'accepted':  not new_stats.get('rejected_new_reason'),
            },
        }), 200

    except Exception as exc:
        logger.error(f"[retrain] error: {exc}", exc_info=True)
        raise APIException(f"Retrain failed: {exc}", status_code=500)


@ai_bp.route('/model-versions', methods=['GET'])
@token_required
@admin_required
@handle_exceptions
def list_model_versions():
    """List all archived model versions (newest first) with their metrics."""
    from app.services.ml_model import XGBLeadScoringModel
    m = XGBLeadScoringModel()
    versions = m.list_versions()
    return jsonify({'status': 'success', 'versions': versions, 'count': len(versions)}), 200


@ai_bp.route('/rollback', methods=['POST'])
@token_required
@admin_required
@handle_exceptions
def rollback_model():
    """
    Revert the active ML model to a specific archived version.

    Body:
      { "filename": "lead_scoring_xgb_v2_20250101T120000Z.pkl" }
    """
    from app.services.ml_model import XGBLeadScoringModel

    body     = request.get_json(force=True, silent=True) or {}
    filename = (body.get('filename') or '').strip()

    if not filename:
        return jsonify({'status': 'error', 'message': 'filename is required'}), 400
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'status': 'error', 'message': 'invalid filename'}), 400

    m = XGBLeadScoringModel()
    success = m.rollback(filename)

    if success:
        stats = m.training_stats or {}
        _add_log('ML model rolled back', 'warning', f'Reverted to: {filename}')
        return jsonify({
            'status':    'success',
            'filename':  filename,
            'auc':       stats.get('hold_out_auc'),
            'n_samples': stats.get('n_samples'),
        }), 200
    else:
        return jsonify({'status': 'error', 'message': f'Rollback to {filename} failed'}), 400


def _append_metrics_history(stats: dict) -> None:
    """Append training metrics to a time-series JSONL file for dashboard use."""
    try:
        import json
        from pathlib import Path
        metrics_path = Path(__file__).parent.parent.parent / 'data' / 'metrics_history.jsonl'
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            'ts':         stats.get('trained_at', datetime.now(timezone.utc).isoformat()),
            'auc':        stats.get('hold_out_auc'),
            'accuracy':   stats.get('hold_out_accuracy'),
            'precision':  stats.get('hold_out_precision'),
            'recall':     stats.get('hold_out_recall'),
            'f1':         stats.get('hold_out_f1'),
            'n_samples':  stats.get('n_samples'),
            'n_real':     stats.get('n_real'),
            'cv_auc':     stats.get('best_cv_auc'),
        }
        with open(metrics_path, 'a') as fh:
            fh.write(json.dumps(entry) + '\n')
    except Exception as exc:
        logger.warning(f"_append_metrics_history: {exc}")


# ============================================================================
# § 14 · AI LEAD ENRICHMENT  (/enrich · /enrich/batch)
# ============================================================================

@ai_bp.route('/enrich/<int:lead_id>', methods=['POST'])
@token_required
@limiter.limit("60 per hour")
@handle_exceptions
def enrich_lead(lead_id):
    """
    Use AI to enrich a lead's missing fields.
    Infers: industry, company_size, pain_points, position title normalisation.

    Returns the fields that were filled in (only updates fields that were blank).
    """
    try:
        from app.models.models import db, Lead

        lead = db.session.get(Lead, lead_id)
        if not lead:
            return jsonify({'status': 'error', 'message': f'Lead {lead_id} not found'}), 404

        lead_data = {
            'name': lead.name or '',
            'email': lead.email or '',
            'company': lead.company or '',
            'position': lead.position or '',
            'industry': lead.industry or '',
            'website': lead.website or '',
            'country': lead.country or '',
            'city': lead.city or '' if hasattr(lead, 'city') else '',
            'interests': lead.interests or [],
            'notes': lead.notes or '' if hasattr(lead, 'notes') else '',
        }

        ai_svc = get_ai_service()
        enriched = ai_svc.enrich_lead(lead_data)

        updated_fields: dict = {}

        # Only write back fields that were blank and AI filled in
        if enriched.get('company') and not lead.company:
            lead.company = enriched['company'][:255]
            updated_fields['company'] = enriched['company']

        if enriched.get('industry') and not lead.industry:
            lead.industry = enriched['industry']
            updated_fields['industry'] = enriched['industry']

        if enriched.get('position') and not lead.position:
            lead.position = enriched['position']
            updated_fields['position'] = enriched['position']

        if enriched.get('company_size') and hasattr(lead, 'company_size') and not lead.company_size:
            lead.company_size = enriched['company_size']
            updated_fields['company_size'] = enriched['company_size']

        if enriched.get('country') and not lead.country:
            lead.country = enriched['country']
            updated_fields['country'] = enriched['country']

        if enriched.get('city') and hasattr(lead, 'city') and not lead.city:
            lead.city = enriched['city']
            updated_fields['city'] = enriched['city']

        # Rebuild location string if we filled in city/country but location is blank
        if not lead.location and (lead.city or lead.country):
            parts = [p for p in [lead.city, lead.country] if p]
            lead.location = ', '.join(parts)
            updated_fields['location'] = lead.location

        if updated_fields:
            db.session.commit()
            _add_log('Lead enriched', 'success',
                     f"{lead.name} — filled: {', '.join(updated_fields.keys())}")

        return jsonify({
            'status': 'success',
            'lead_id': lead_id,
            'lead_name': lead.name,
            'updated_fields': updated_fields,
            'enrichment_data': enriched,
            'ai_provider': enriched.get('ai_provider', 'AI'),
        }), 200

    except Exception as e:
        logger.error(f"Enrichment error for lead {lead_id}: {e}")
        raise APIException(f"Failed to enrich lead: {str(e)}", status_code=500)


# ---------------------------------------------------------------------------
# AUTO-ENRICH HELPER — called after any lead is saved to DB
# ---------------------------------------------------------------------------

def _auto_enrich_lead_async(lead_id: int, app_ctx):
    """
    Background thread: enrich a single lead's missing fields right after save.
    Only fires when fields are actually missing to avoid unnecessary API calls.
    """
    import time
    time.sleep(0.5)  # Let the commit settle
    with app_ctx:
        try:
            from app.models.models import db, Lead
            lead = db.session.get(Lead, lead_id)
            if not lead:
                return
            # Check if enrichment is needed (skip API call when all fields present)
            needs_enrichment = not (lead.industry and lead.company and lead.country and lead.position)
            lead_data = {
                'name': lead.name or '',
                'email': lead.email or '',
                'company': lead.company or '',
                'position': lead.position or '',
                'industry': lead.industry or '',
                'website': lead.website or '',
                'country': lead.country or '',
                'city': lead.city or '' if hasattr(lead, 'city') else '',
                'interests': lead.interests or [],
            }
            if needs_enrichment:
                ai_svc = get_ai_service()
                enriched = ai_svc.enrich_lead(lead_data)
                changed = False
                if enriched.get('company') and not lead.company:
                    lead.company = enriched['company'][:255]
                    changed = True
                if enriched.get('industry') and not lead.industry:
                    lead.industry = enriched['industry']
                    changed = True
                if enriched.get('position') and not lead.position:
                    lead.position = enriched['position']
                    changed = True
                if enriched.get('country') and not lead.country:
                    lead.country = enriched['country']
                    changed = True
                if enriched.get('city') and hasattr(lead, 'city') and not lead.city:
                    lead.city = enriched['city']
                    changed = True
                if changed:
                    if not lead.location and (lead.city or lead.country):
                        parts = [p for p in [lead.city, lead.country] if p]
                        lead.location = ', '.join(parts)
                    db.session.commit()
                    logger.info(f"[auto-enrich] lead {lead_id} ({lead.name}) updated fields")

            # ── Serper website discovery for leads with no website ────────────────
            # Runs for both company and person leads before Hunter so Hunter
            # has a domain to search against.
            if not lead.website and lead.company:
                try:
                    import requests as _req2
                    _serper_key2 = os.environ.get('SERPER_API_KEY', '')
                    if _serper_key2:
                        _sr2 = _req2.post(
                            'https://google.serper.dev/search',
                            headers={'X-API-KEY': _serper_key2, 'Content-Type': 'application/json'},
                            json={'q': f'"{lead.company}" official website', 'num': 3},
                            verify=False, timeout=8,
                        )
                        if _sr2.ok:
                            from urllib.parse import urlparse as _up2
                            for _r2 in _sr2.json().get('organic', []):
                                _lnk2 = _r2.get('link', '')
                                if not _lnk2 or any(x in _lnk2 for x in ('linkedin', 'facebook', 'twitter', 'instagram', 'youtube', 'wikipedia')):
                                    continue
                                _dom2 = _up2(_lnk2).netloc.replace('www.', '').split(':')[0]
                                if _dom2 and '.' in _dom2:
                                    lead.website = f'https://{_dom2}'
                                    db.session.commit()
                                    logger.info(f"[auto-enrich] lead {lead_id} website found via Serper: {lead.website}")
                                    break
                except Exception as _we2:
                    logger.debug(f"[auto-enrich] Serper website lookup failed for {lead_id}: {_we2}")

            # Hunter email upgrade — replace missing/generic email using domain search
            _GENERIC_PREFIXES_AE = {
                'info', 'contact', 'hello', 'support', 'sales', 'admin', 'team',
                'business', 'inquiry', 'enquiry', 'help', 'feedback', 'service',
                'office', 'general', 'mail', 'reception', 'marketing',
            }
            _email_is_generic = (
                not lead.email or
                (lead.email and '@' in lead.email and
                 lead.email.split('@')[0].lower() in _GENERIC_PREFIXES_AE)
            )
            if _email_is_generic and (lead.website or lead.email):
                try:
                    from app.services.lead_fallback import enrich_lead_fallbacks
                    _ld_hunter = {
                        'name':    lead.name or '',
                        'email':   lead.email or '',
                        'company': lead.company or '',
                        'website': lead.website or '',
                        'data_points': lead.data_points or {},
                    }
                    _enriched_h = enrich_lead_fallbacks(
                        _ld_hunter,
                        scrape_contact=False,
                        use_hunter=True,
                        generate_email=False,
                    )
                    _new_email = (_enriched_h.get('email') or '').strip()
                    if _new_email and _new_email != lead.email:
                        lead.email = _new_email
                        lead.email_type = 'personal_business'
                        _dp = dict(lead.data_points or {})
                        _dp.update(_enriched_h.get('data_points') or {})
                        lead.data_points = _dp
                        db.session.commit()
                        logger.info(
                            f"[auto-enrich] lead {lead_id} email upgraded "
                            f"to personal via Hunter: {_new_email}"
                        )
                except Exception as _he:
                    logger.debug(f"[auto-enrich] Hunter email upgrade skipped for {lead_id}: {_he}")

            # For person leads with NO email: find company domain via Serper → Hunter find_email
            if not lead.email and lead.company and getattr(lead, 'lead_type', '') == 'person':
                try:
                    import requests as _req
                    _serper_key = os.environ.get('SERPER_API_KEY', '')
                    if _serper_key:
                        _sr = _req.post(
                            'https://google.serper.dev/search',
                            headers={'X-API-KEY': _serper_key, 'Content-Type': 'application/json'},
                            json={'q': f'"{lead.company}" official website', 'num': 3},
                            verify=False, timeout=8,
                        )
                        if _sr.ok:
                            from urllib.parse import urlparse as _up
                            for _r in _sr.json().get('organic', []):
                                _link = _r.get('link', '')
                                if not _link or any(x in _link for x in ('linkedin', 'facebook', 'twitter', 'instagram')):
                                    continue
                                _domain = _up(_link).netloc.replace('www.', '').split(':')[0]
                                if not _domain:
                                    continue
                                # Try Hunter find_email(first, last, domain)
                                from app.services.lead_fallback import hunter_find_email
                                _parts = (lead.name or '').strip().split()
                                _first = _parts[0] if _parts else ''
                                _last  = _parts[-1] if len(_parts) > 1 else ''
                                _found = hunter_find_email(_domain, _first, _last)
                                if _found:
                                    lead.email      = _found
                                    lead.email_type = 'personal_business'
                                    if not lead.website:
                                        lead.website = f'https://{_domain}'
                                    db.session.commit()
                                    logger.info(
                                        f"[auto-enrich] person lead {lead_id} "
                                        f"email found via Serper+Hunter: {_found}"
                                    )
                                break
                except Exception as _pe:
                    logger.debug(f"[auto-enrich] Serper+Hunter person lookup failed for {lead_id}: {_pe}")

            # ── ML qualification ───────────────────────────────────────────────
            try:
                _dp_ml = lead.data_points or {}
                _lead_data_for_scoring = {
                    'name':           lead.name or '',
                    'email':          lead.email or '',
                    'company':        lead.company or '',
                    'position':       lead.position or '',
                    'industry':       lead.industry or '',
                    'website':        lead.website or '',
                    'linkedin_url':   lead.linkedin_url or '',
                    'country':        lead.country or '',
                    'city':           lead.city or '' if hasattr(lead, 'city') else '',
                    'source':         lead.source or '',
                    'email_type':     lead.email_type or '',
                    'buying_intent':  lead.buying_intent or 'none',
                    # ML v5 features — pulled from data_points where enrichment stored them
                    'employee_count': _dp_ml.get('employee_count') or getattr(lead, 'company_size_int', None),
                    'hiring_score':   _dp_ml.get('hiring_score', 0),
                    'data_points':    _dp_ml,
                }
                if _dp_ml:
                    _lead_data_for_scoring.update(_dp_ml)
                result = _qualify_fast(_lead_data_for_scoring)
                lead.qualification_score = result['score']
                new_status = _derive_status(result)
                if lead.status in ('pending', '', None) or lead.status != 'hot':
                    lead.status = new_status
                flag_modified(lead, 'data_points')
                db.session.commit()
                logger.info(
                    f"[auto-qualify] lead {lead_id} ({lead.name}) → "
                    f"{result['score']}% {result['category']}"
                )
            except Exception as _qe:
                logger.warning(f"[auto-qualify] lead {lead_id} score failed: {_qe}")

            # ── Hiring signal detection (free, no API, runs from website text) ─
            # Only runs if we have a website and haven't computed it before.
            _dp_check = lead.data_points or {}
            if lead.website and not _dp_check.get('hiring_score'):
                try:
                    from app.intelligence.hiring_signal_detector import HiringSignalDetector as _HSD
                    _hsd_result = _HSD().detect(
                        company=lead.company or '',
                        domain=lead.website,
                        lead={
                            'website':    lead.website,
                            'company':    lead.company or '',
                            'name':       lead.name or '',
                            'data_points': lead.data_points or {},
                        },
                    )
                    _hs = _hsd_result.get('hiring_score', 0)
                    if _hs > 0:
                        _dp_upd = dict(lead.data_points or {})
                        _dp_upd['hiring_score'] = _hs
                        _dp_upd['hiring_roles']  = _hsd_result.get('hiring_roles', [])
                        lead.data_points = _dp_upd
                        flag_modified(lead, 'data_points')
                        db.session.commit()
                        logger.info(f"[hiring-signal] lead {lead_id} hiring_score={_hs}")
                except Exception as _hse:
                    logger.debug(f"[hiring-signal] lead {lead_id} skipped: {_hse}")

            # ── Intelligence Engine — deep analysis (runs only when worthwhile) ──
            # Conditions: AI is available, lead has a company + at least one
            # contact signal, and has NOT been through intelligence analysis yet.
            _dp_check = lead.data_points or {}
            _already_analyzed = bool(_dp_check.get('intelligence_report'))
            _has_business_signal = bool(lead.company and (lead.email or lead.website))
            _score_worth_analyzing = (lead.qualification_score or 0) >= 25

            if (not _already_analyzed and _has_business_signal and _score_worth_analyzing):
                try:
                    _intel_svc = get_ai_service()
                    if _intel_svc.is_available:
                        _intel_data = {
                            'id':           lead.id,
                            'name':         lead.name or '',
                            'email':        lead.email or '',
                            'email_type':   lead.email_type or '',
                            'phone':        lead.phone or '',
                            'company':      lead.company or '',
                            'position':     lead.position or '',
                            'industry':     lead.industry or '',
                            'country':      lead.country or '',
                            'city':         getattr(lead, 'city', '') or '',
                            'website':      lead.website or '',
                            'linkedin_url': lead.linkedin_url or '',
                            'source':       lead.source or '',
                            'notes':        lead.notes or '',
                            'interests':    lead.interests or [],
                            'data_points':  lead.data_points or {},
                        }
                        _intel_report = _intel_svc.lead_intelligence_analysis(_intel_data)
                        _intel_score  = _intel_report.get('qualification_score', 0)
                        _intel_action = _intel_report.get('recommended_action', 'REVIEW')

                        # Apply db_updates: fill blank fields only
                        _changed_intel = False
                        for _f, _v in (_intel_report.get('db_updates') or {}).items():
                            if _v and not getattr(lead, _f, None):
                                setattr(lead, _f, _v)
                                _changed_intel = True

                        # Blend intelligence score with ML score (60/40 when both present)
                        _prev = lead.qualification_score or 0
                        _blended = round(0.6 * _intel_score + 0.4 * _prev)
                        lead.qualification_score = _blended

                        # Apply intelligence verdict to lead status.
                        # Only update if the lead hasn't been manually promoted.
                        _current_status = lead.status or 'pending'
                        _auto_status_eligible = _current_status in ('pending', 'cold', '', None)
                        if _intel_action == 'DISCARD':
                            lead.status = 'low_quality'
                        elif _intel_action == 'SAVE' and _blended >= 70 and _auto_status_eligible:
                            lead.status = 'hot' if _blended >= 80 else 'warm'
                        elif _intel_action == 'REVIEW' and _current_status == 'pending':
                            lead.status = 'cold'  # signal it needs human review

                        # Persist intelligence report in data_points
                        _dp_intel = dict(lead.data_points or {})
                        _dp_intel['intelligence_report'] = {
                            'is_lead':            _intel_report.get('is_lead'),
                            'buying_intent':      _intel_report.get('buying_intent'),
                            'buying_intent_signals': _intel_report.get('buying_intent_signals', []),
                            'quality_tier':       _intel_report.get('quality_tier'),
                            'source_quality':     _intel_report.get('source_quality'),
                            'recommended_action': _intel_action,
                            'decision_makers':    _intel_report.get('decision_makers', []),
                            'emails':             _intel_report.get('emails', []),
                            'reasons':            _intel_report.get('reasons', []),
                            'ai_provider':        _intel_report.get('ai_provider'),
                            'prompt_version':     _intel_report.get('prompt_version'),
                            'analyzed_at':        _intel_report.get('analyzed_at'),
                        }
                        lead.data_points = _dp_intel
                        flag_modified(lead, 'data_points')
                        db.session.commit()
                        logger.info(
                            f"[intelligence] lead {lead_id} ({lead.name}): "
                            f"score={_intel_score} blended={_blended} "
                            f"action={_intel_action} "
                            f"intent={_intel_report.get('buying_intent')} "
                            f"provider={_intel_report.get('provider_key')}"
                        )
                except Exception as _ie:
                    logger.debug(f"[intelligence] lead {lead_id} analysis skipped: {_ie}")

        except Exception as exc:
            logger.warning(f"[auto-enrich] lead {lead_id} failed: {exc}")


# ---------------------------------------------------------------------------
# BULK RE-ENRICH ENDPOINT — fills missing fields on all all_leads leads
# ---------------------------------------------------------------------------

@ai_bp.route('/enrich/batch', methods=['POST'])
@token_required
@limiter.limit("5 per hour")
@handle_exceptions
def enrich_leads_batch():
    """
    Batch-enrich all leads that have missing fields (no company, industry,
    country, or position). Runs in background; returns a task-id to poll.

    Body (optional JSON):
      limit  — max leads to process (default 50)
    """
    from app.models.models import db, Lead

    data = request.get_json(silent=True) or {}
    max_leads = min(int(data.get('limit', 1000)), 1000)

    # Enrich ALL leads — individual field checks below decide what to overwrite
    # MySQL doesn't support NULLS FIRST; use CASE to sort nulls to the front
    from sqlalchemy import case as sa_case
    _null_last = sa_case((Lead.completeness_score.is_(None), 0), else_=1)
    all_leads = Lead.query.order_by(_null_last, Lead.completeness_score.asc()).limit(max_leads).all()

    if not all_leads:
        return jsonify({'status': 'success', 'message': 'No leads found', 'processed': 0}), 200

    task_id = f"batch_enrich_{int(__import__('time').time())}"
    with _tasks_lock:
        _collection_tasks[task_id] = {
            'id': task_id,
            'status': 'running',
            'percent': 0,
            'processed': 0,
            'updated': 0,
            'total': len(all_leads),
        }

    app_ctx = current_app.app_context()

    def _run_batch():
        processed = 0
        updated = 0
        _PLACEHOLDER = {'', 'N/A', 'n/a', 'NA', 'na', 'null', 'None', 'unknown'}
        _GENERIC_INDUSTRIES = {'technology', 'tech', 'other', 'general', 'services', 'business'}

        def _needs(val):
            return not val or str(val).strip() in _PLACEHOLDER

        def _needs_industry(val):
            return _needs(val) or str(val).strip().lower() in _GENERIC_INDUSTRIES

        ai_svc = get_ai_service()
        with app_ctx:
            for lead in all_leads:
                try:
                    lead_data = {
                        'name': lead.name or '',
                        'email': lead.email or '',
                        'company': lead.company or '',
                        'position': lead.position or '',
                        'industry': lead.industry or '',
                        'website': lead.website or '',
                        'country': lead.country or '',
                        'city': lead.city or '' if hasattr(lead, 'city') else '',
                        'interests': lead.interests or [],
                    }
                    enriched = ai_svc.enrich_lead(lead_data)
                    changed = False

                    if enriched.get('company') and _needs(lead.company):
                        lead.company = enriched['company'][:255]
                        changed = True
                    if enriched.get('industry') and _needs_industry(lead.industry):
                        lead.industry = enriched['industry']
                        changed = True
                    if enriched.get('position') and _needs(lead.position):
                        lead.position = enriched['position']
                        changed = True
                    if enriched.get('country') and _needs(lead.country):
                        lead.country = enriched['country']
                        changed = True
                    if enriched.get('city') and hasattr(lead, 'city') and _needs(lead.city):
                        lead.city = enriched['city']
                        changed = True
                    if changed:
                        if not lead.location and (lead.city or lead.country):
                            parts = [p for p in [lead.city, lead.country] if p]
                            lead.location = ', '.join(parts)
                        # Recompute completeness now that new fields are filled
                        _cs_fields = ('name', 'email', 'phone', 'company', 'position',
                                      'linkedin_url', 'website', 'industry', 'country')
                        new_cs = sum(1 for f in _cs_fields if getattr(lead, f, None)) / len(_cs_fields) * 100
                        if new_cs > (lead.completeness_score or 0):
                            lead.completeness_score = round(new_cs, 1)

                    # Always re-qualify with ML (fast, no LLM calls)
                    try:
                        _ld = {
                            'name': lead.name or '', 'email': lead.email or '',
                            'company': lead.company or '', 'position': lead.position or '',
                            'industry': lead.industry or '', 'website': lead.website or '',
                            'linkedin_url': lead.linkedin_url or '', 'country': lead.country or '',
                            'city': lead.city or '' if hasattr(lead, 'city') else '',
                            'source': lead.source or '', 'email_type': lead.email_type or '',
                        }
                        if lead.data_points:
                            _ld.update(lead.data_points)
                        _res = _qualify_fast(_ld)
                        lead.qualification_score = _res['score']
                        if lead.status in ('pending', '', None):
                            lead.status = _derive_status(_res)
                    except Exception as _qe:
                        logger.debug(f"[batch-enrich] qualify skipped for {lead.id}: {_qe}")

                    db.session.commit()
                    if changed:
                        updated += 1
                except Exception as exc:
                    logger.warning(f"[batch-enrich] lead {lead.id} error: {exc}")
                    db.session.rollback()
                finally:
                    processed += 1
                    pct = int(processed / len(all_leads) * 100)
                    _update_task(task_id, percent=pct, status='running',
                                 processed=processed, updated=updated, total=len(all_leads))

        _update_task(task_id, percent=100, status='done',
                     processed=processed, updated=updated, total=len(all_leads))
        _add_log('Batch enrichment complete', 'success',
                 f"Processed {processed} leads, updated {updated}")
        logger.info(f"[batch-enrich] done: {updated}/{processed} leads updated")

    thread = threading.Thread(target=_run_batch, daemon=True)
    thread.start()

    return jsonify({
        'status': 'started',
        'task_id': task_id,
        'total': len(all_leads),
        'message': f'Enriching {len(all_leads)} leads in background',
    }), 202


@ai_bp.route('/qualify/batch', methods=['POST'])
@token_required
@limiter.limit("10 per hour")
@handle_exceptions
def qualify_leads_batch():
    """
    Re-qualify all pending leads with the ML model (no LLM API calls).
    Useful for fixing leads that were saved before auto-qualify ran correctly.

    Body (optional JSON):
      limit       — max leads to process (default 500)
      status      — only re-qualify leads with this status (default 'pending')
      force       — if true, re-qualify all leads regardless of status
    """
    from app.models.models import db, Lead

    data = request.get_json(silent=True) or {}
    max_leads = min(int(data.get('limit', 500)), 2000)
    target_status = data.get('status', 'pending')
    force = bool(data.get('force', False))

    query = Lead.query
    if not force:
        query = query.filter(Lead.status == target_status)
    leads = query.order_by(Lead.id.desc()).limit(max_leads).all()

    if not leads:
        return jsonify({'status': 'success', 'message': 'No matching leads', 'processed': 0}), 200

    task_id = f"batch_qualify_{int(__import__('time').time())}"
    with _tasks_lock:
        _collection_tasks[task_id] = {
            'id': task_id, 'status': 'running', 'percent': 0,
            'processed': 0, 'updated': 0, 'total': len(leads),
        }

    app_ctx = current_app.app_context()

    def _run_qualify():
        processed = 0
        updated = 0
        with app_ctx:
            for lead in leads:
                try:
                    _ld = {
                        'name': lead.name or '', 'email': lead.email or '',
                        'company': lead.company or '', 'position': lead.position or '',
                        'industry': lead.industry or '', 'website': lead.website or '',
                        'linkedin_url': lead.linkedin_url or '', 'country': lead.country or '',
                        'city': lead.city or '' if hasattr(lead, 'city') else '',
                        'source': lead.source or '', 'email_type': lead.email_type or '',
                    }
                    if lead.data_points:
                        _ld.update(lead.data_points)
                    _res = _qualify_fast(_ld)
                    old_score = lead.qualification_score or 0
                    lead.qualification_score = _res['score']
                    if force or lead.status in ('pending', '', None):
                        lead.status = _derive_status(_res)
                    db.session.commit()
                    if abs(_res['score'] - old_score) >= 1:
                        updated += 1
                except Exception as exc:
                    logger.warning(f"[batch-qualify] lead {lead.id} error: {exc}")
                    db.session.rollback()
                finally:
                    processed += 1
                    _update_task(task_id, percent=int(processed / len(leads) * 100),
                                 status='running', processed=processed, updated=updated,
                                 total=len(leads))

        _update_task(task_id, percent=100, status='done',
                     processed=processed, updated=updated, total=len(leads))
        logger.info(f"[batch-qualify] done: {updated}/{processed} leads rescored")

    threading.Thread(target=_run_qualify, daemon=True).start()

    return jsonify({
        'status': 'started', 'task_id': task_id,
        'total': len(leads),
        'message': f'Re-qualifying {len(leads)} leads in background',
    }), 202


@ai_bp.route('/enrich/batch/status/<task_id>', methods=['GET'])
@token_required
@limiter.exempt
@handle_exceptions
def enrich_batch_status(task_id):
    """Poll the progress of a running batch-enrich task."""
    with _tasks_lock:
        task = _collection_tasks.get(task_id)
    if not task:
        return jsonify({'status': 'not_found'}), 404
    return jsonify(task), 200


# ============================================================================
# § 15 · AUTO-COLLECT PIPELINE  (/collect/auto)
# Apollo + Hunter + PDL + Web — multi-source parallel collection
# ============================================================================

@ai_bp.route('/collect/auto/sources', methods=['GET'])
@token_required
@handle_exceptions
def auto_collect_sources():
    """Return which data sources are currently configured."""
    from app.services.apollo_service   import is_apollo_configured
    from app.services.hunter_service   import is_hunter_configured
    from app.services.pdl_service      import is_pdl_configured
    from app.services.clearbit_service import is_clearbit_configured
    return jsonify({
        'apollo':   {'configured': is_apollo_configured(),   'label': 'Apollo.io (paid plan required for search)', 'description': 'B2B people search — requires paid Apollo plan. Free plan only supports enrichment.'},
        'hunter':   {'configured': is_hunter_configured(),   'label': 'Hunter.io',          'description': 'Corporate email finder by domain'},
        'pdl':      {'configured': is_pdl_configured(),      'label': 'People Data Labs',   'description': 'Person & company enrichment — 100 free/month'},
        'clearbit': {'configured': is_clearbit_configured(), 'label': 'Clearbit',           'description': 'Company & person enrichment via HubSpot'},
        'ai':       {'configured': True,                     'label': 'AI Enrichment',      'description': 'Gemini/Groq fills any remaining gaps'},
    })


@ai_bp.route('/collect/auto', methods=['POST'])
@token_required
@limiter.limit("10 per hour")
@handle_exceptions
def auto_collect():
    """
    Fully automated lead collection pipeline.
    1. Apollo.io  — search people by keyword/title/location
    2. Hunter.io  — find missing emails by domain
    3. PDL        — enrich remaining gaps
    4. AI         — fill any still-missing fields
    5. Save to DB (deduplicated by email)

    Body (JSON):
      keywords   str   — search terms e.g. "SaaS founder"
      titles     list  — e.g. ["CEO","CTO","VP Sales"]
      locations  list  — e.g. ["Australia","United Kingdom"]
      industries list  — e.g. ["Technology","SaaS"]
      domains    list  — specific company domains for Hunter domain search
      limit      int   — max leads to collect (default 25, max 100)
    """
    from app.models.models import db, Lead
    from app.services.apollo_service   import get_apollo_service
    from app.services.hunter_service   import get_hunter_service
    from app.services.pdl_service      import get_pdl_service
    from app.services.clearbit_service import get_clearbit_service

    data       = request.get_json(silent=True) or {}
    keywords   = data.get('keywords', '')
    titles     = data.get('titles',     [])
    locations  = data.get('locations',  [])
    industries = data.get('industries', [])
    domains    = data.get('domains',    [])
    limit      = min(int(data.get('limit', 25)), 100)
    interest_product_category = data.get('interest_product_category', '')
    interest_target_industry   = data.get('interest_target_industry', '')
    interest_buying_intent     = data.get('interest_buying_intent', '')
    interest_country           = data.get('interest_country', '')
    interest_city              = data.get('interest_city', '')

    _cleanup_old_tasks()
    task_id = f"auto_collect_{int(__import__('time').time())}"
    with _tasks_lock:
        _collection_tasks[task_id] = {
            'id':         task_id,
            'status':     'running',
            'percent':    0,
            'collected':  0,
            'saved':      0,
            'skipped':    0,
            'sources':    [],
            'started_at': datetime.now(timezone.utc).isoformat(),
        }

    app_ctx = current_app.app_context()
    _notify_user_id = g.user_id  # captured here; g is request-scoped and unavailable inside the thread

    # Read data collection preferences before entering thread (g is unavailable inside)
    try:
        from app.routes.settings import _get_user_settings as _get_coll_prefs
        _coll_prefs  = _get_coll_prefs(g.user_id)
    except Exception:
        _coll_prefs  = {}
    _pref_linkedin = bool(_coll_prefs.get('auto_collect_linkedin', True))
    _pref_emails   = bool(_coll_prefs.get('auto_collect_emails',   True))
    _pref_company  = bool(_coll_prefs.get('auto_collect_company',  True))

    def _run():
      with app_ctx:
        apollo    = get_apollo_service()
        hunter    = get_hunter_service()
        pdl       = get_pdl_service()
        clearbit  = get_clearbit_service()
        ai_svc    = get_ai_service()

        raw_leads: list = []
        sources_used: list = []

        # ── Interest-boost: strengthen query when interest fields are present ──
        _effective_keywords = keywords
        if interest_product_category or interest_target_industry:
            _interest_boost = ' '.join(filter(None, [
                interest_product_category,
                interest_target_industry,
                interest_buying_intent,
                interest_country or (locations[0] if locations else ''),
            ]))
            if _interest_boost:
                _effective_keywords = (
                    f"{_effective_keywords} {_interest_boost}".strip()
                    if _effective_keywords else _interest_boost
                )
                logger.info(f"[auto_collect] interest-boosted query: {_effective_keywords!r}")

        # ── QueryPlanner — merge filters into targeted plan ───────────────
        from app.search.query_planner import QueryPlanner as _QP
        _auto_plan = _QP.build(_effective_keywords, {
            'country':   interest_country or (locations[0] if locations else ''),
            'city':      interest_city,
            'industry':  (industries[0] if industries else ''),
            'lead_type': 'person',
            'titles':    titles,
        })
        # Use plan titles when caller didn't specify any
        _effective_titles = titles or _auto_plan.titles
        logger.info(
            f"[auto_collect] QueryPlan: titles={_effective_titles[:4]} "
            f"google_q={len(_auto_plan.google_queries)}"
        )

        # ── Step 1: Apollo people search ─────────────────────────────────
        if apollo.is_configured() and (_effective_keywords or _effective_titles or locations or industries):
            apollo_leads = apollo.search_people(
                keywords   = _effective_keywords,
                titles     = _effective_titles,
                locations  = locations,
                industries = industries,
                per_page   = limit,
            )
            raw_leads.extend(apollo_leads)
            if apollo_leads:
                sources_used.append(f"Apollo ({len(apollo_leads)})")
            elif apollo.needs_upgrade():
                sources_used.append("Apollo (free plan — upgrade required for people search)")
            _update_task(task_id, percent=20, collected=len(raw_leads), sources=sources_used)

        # Track Apollo result count for fallback decision
        _apollo_count    = len(raw_leads)
        _fallback_used   = False
        _fallback_reason = None
        _fallback_counts: dict = {}

        # ── Step 2: Hunter domain search ──────────────────────────────────
        if _pref_emails and hunter.is_configured() and domains:
            for domain in domains:
                h_leads = hunter.domain_search(domain, limit=min(limit, 10))
                for _hl in h_leads:
                    _hl.setdefault('data_points', {})['auto_source_origin'] = 'hunter_domain'
                raw_leads.extend(h_leads)
            if domains:
                sources_used.append(f"Hunter ({len(domains)} domain(s))")
            _update_task(task_id, percent=35, collected=len(raw_leads), sources=sources_used)

        # ── Step 2b: Fallback sources when Apollo returns too few ─────────
        _MIN_APOLLO_THRESHOLD = 3
        if _apollo_count < _MIN_APOLLO_THRESHOLD:
            _fallback_used   = True
            _fallback_reason = "apollo_empty" if _apollo_count == 0 else "apollo_low_results"
            logger.info(
                "[auto_collect] Apollo returned %d leads (< %d) — activating fallback sources",
                _apollo_count, _MIN_APOLLO_THRESHOLD,
            )
            _update_task(task_id, percent=36, status='running',
                         fallback_used=True, fallback_reason=_fallback_reason)

            _fb_location = _auto_plan.country or (locations[0].split(',')[-1].strip() if locations else '')

            # ── Fallback 1: LinkedIn via Serper ───────────────────────────
            if _pref_linkedin:
                try:
                    from app.services.social_media_collector import get_social_collector as _get_sc
                    _sc_fb = _get_sc()
                    _li_leads = _sc_fb._collect_from_linkedin(
                        _effective_keywords or ' '.join(_effective_titles[:2]),
                        industry=(industries[0] if industries else ''),
                        max_leads=min(limit, 15),
                        custom_queries=_auto_plan.linkedin_queries or None,
                    )
                    for _ll in _li_leads:
                        _ll.setdefault('data_points', {}).update({
                            'auto_source_origin': 'linkedin_fallback',
                            'fallback_used': True,
                            'fallback_reason': _fallback_reason,
                        })
                        _ll.setdefault('lead_type', 'person')
                    raw_leads.extend(_li_leads)
                    _fallback_counts['linkedin_fallback'] = len(_li_leads)
                    if _li_leads:
                        sources_used.append(f"LinkedIn fallback ({len(_li_leads)})")
                    logger.info("[auto_collect] LinkedIn fallback: %d leads", len(_li_leads))
                except Exception as _fb_li_err:
                    logger.debug("[auto_collect] LinkedIn fallback error: %s", _fb_li_err)
            else:
                logger.info("[auto_collect] LinkedIn fallback skipped (auto_collect_linkedin=False)")

            _update_task(task_id, percent=45, collected=len(raw_leads),
                         fallback_counts=_fallback_counts)

            # ── Fallback 2: Google / web ──────────────────────────────────
            try:
                from app.services.public_web_collector import get_collector as _get_wc
                _wc_fb = _get_wc()
                _web_fb_leads: list = []
                _wc_fb_ccode = _auto_plan.country[:2].upper() if _auto_plan.country else ''
                # Use simple keyword query — search_businesses builds its own strategies
                _web_fb_q = (_effective_keywords or ' '.join(industries[:2])).strip()
                try:
                    _gq_res = _wc_fb.search_businesses(
                        _web_fb_q,
                        country_code=_wc_fb_ccode,
                        max_results=15,
                    )
                    _web_fb_leads.extend(_gq_res or [])
                except Exception:
                    pass
                for _wl in _web_fb_leads:
                    _wl.setdefault('data_points', {}).update({
                        'auto_source_origin': 'web_fallback',
                        'fallback_used': True,
                        'fallback_reason': _fallback_reason,
                    })
                    _wl.setdefault('lead_type', 'company')
                raw_leads.extend(_web_fb_leads)
                _fallback_counts['web_fallback'] = len(_web_fb_leads)
                if _web_fb_leads:
                    sources_used.append(f"Web fallback ({len(_web_fb_leads)})")
                logger.info("[auto_collect] Web fallback: %d leads", len(_web_fb_leads))
            except Exception as _fb_web_err:
                logger.debug("[auto_collect] Web fallback error: %s", _fb_web_err)

            _update_task(task_id, percent=52, collected=len(raw_leads),
                         fallback_counts=_fallback_counts)

            # ── Fallback 3: News ──────────────────────────────────────────
            try:
                from app.services.news_collector import NewsCollector as _NC_fb
                _news_fb = _NC_fb()
                _news_leads_fb = _news_fb.collect(
                    keywords=_effective_keywords or ' '.join(_effective_titles[:2]),
                    max_results=min(limit, 10),
                )
                for _nl in _news_leads_fb:
                    _nl.setdefault('data_points', {}).update({
                        'auto_source_origin': 'news_fallback',
                        'fallback_used': True,
                        'fallback_reason': _fallback_reason,
                    })
                    _nl.setdefault('lead_type', 'company')
                raw_leads.extend(_news_leads_fb)
                _fallback_counts['news_fallback'] = len(_news_leads_fb)
                if _news_leads_fb:
                    sources_used.append(f"News fallback ({len(_news_leads_fb)})")
                logger.info("[auto_collect] News fallback: %d leads", len(_news_leads_fb))
            except Exception as _fb_news_err:
                logger.debug("[auto_collect] News fallback error: %s", _fb_news_err)

            _update_task(task_id, percent=58, collected=len(raw_leads),
                         fallback_counts=_fallback_counts)

            # ── Fallback 4: GitHub ────────────────────────────────────────
            try:
                from app.services.github_collector import GitHubCollector as _GH_fb
                _gh_fb = _GH_fb()
                _gh_leads_fb = _gh_fb.collect(
                    keywords=_effective_keywords or ' '.join(_effective_titles[:2]),
                    locations=[_fb_location] if _fb_location else None,
                    topics=_auto_plan.github_queries[:2] if _auto_plan.github_queries else None,
                    max_results=min(limit, 10),
                )
                for _gl in _gh_leads_fb:
                    _gl.setdefault('data_points', {}).update({
                        'auto_source_origin': 'github_fallback',
                        'fallback_used': True,
                        'fallback_reason': _fallback_reason,
                    })
                    _gl.setdefault('lead_type', 'person')
                raw_leads.extend(_gh_leads_fb)
                _fallback_counts['github_fallback'] = len(_gh_leads_fb)
                if _gh_leads_fb:
                    sources_used.append(f"GitHub fallback ({len(_gh_leads_fb)})")
                logger.info("[auto_collect] GitHub fallback: %d leads", len(_gh_leads_fb))
            except Exception as _fb_gh_err:
                logger.debug("[auto_collect] GitHub fallback error: %s", _fb_gh_err)

            _update_task(task_id, percent=63, collected=len(raw_leads),
                         fallback_counts=_fallback_counts)

        # Tag Apollo leads with source origin
        for _rl in raw_leads:
            if not (_rl.get('data_points') or {}).get('auto_source_origin'):
                _rl.setdefault('data_points', {})['auto_source_origin'] = 'apollo'

        # Deduplicate by email before enrichment
        seen_emails: set = set()
        unique_leads = []
        for lead in raw_leads:
            key = (lead.get('email') or '').lower().strip()
            if key and key in seen_emails:
                continue
            if key:
                seen_emails.add(key)
            unique_leads.append(lead)

        unique_leads = unique_leads[:limit]
        _update_task(task_id, percent=40, collected=len(unique_leads))

        total = len(unique_leads)
        _BLANK = {'', 'N/A', 'n/a', 'unknown', 'null', 'None', None}

        def _empty(v):
            return v is None or str(v).strip() in _BLANK

        # ── Step 3 & 4: Hunter email-find + PDL + AI enrichment ──────────
        from app.services.lead_quality_engine import evaluate_lead_quality, CollectionQualityReport
        from app.services.intent_detector import detect_intent as _auto_detect_intent
        try:
            from app.services.name_validator import pre_filter_lead as _auto_pre_filter
        except ImportError:
            def _auto_pre_filter(lead) -> "tuple[bool, str]": return True, ''  # type: ignore[misc]

        auto_report = CollectionQualityReport(source='auto_collect')
        enriched_leads = []
        # ── Step 3 & 4: Premium enrichment (company data only) ───────────
        # Hunter email-finding is intentionally EXCLUDED here.
        # Hunter runs ONLY after company passes intelligence (Stage 8, ContactResolver).
        for idx, lead in enumerate(unique_leads):
            auto_report.raw_candidates += 1
            # Pre-filter: CDN emails, URL-as-name, all-caps handles
            _pf_ok, _pf_reason = _auto_pre_filter(lead)
            if not _pf_ok:
                auto_report.rejected += 1
                continue

            # PDL enrichment (company data: website, industry, location)
            if _pref_company and pdl.is_configured():
                lead = pdl.enrich_lead(lead)

            # Clearbit enrichment (company data: size, industry, founded)
            if _pref_company and clearbit.is_configured():
                lead = clearbit.enrich_lead(lead)
                if 'clearbit' not in sources_used:
                    sources_used.append('clearbit')

            # AI enrichment for blank company/industry/country fields only
            missing = [f for f in ('company', 'industry', 'country') if _empty(lead.get(f))]
            if _pref_company and missing:
                try:
                    ai_result = ai_svc.enrich_lead(lead)
                    for field in missing:
                        if ai_result.get(field) and _empty(lead.get(field)):
                            lead[field] = ai_result[field]
                except Exception:
                    pass

            # Intent detection for data_points context
            _intent_text = ' '.join(filter(None, [
                lead.get('position', ''), lead.get('industry', ''),
                ' '.join(lead.get('interests', [])) if isinstance(lead.get('interests'), list) else '',
            ]))
            _intent = _auto_detect_intent(_intent_text, company=lead.get('company'),
                                          industry=lead.get('industry'))
            lead.setdefault('data_points', {})['intent'] = _intent
            if _intent.get('buying_intent') not in ('none', ''):
                auto_report.intent_detected = getattr(auto_report, 'intent_detected', 0) + 1

            # Tag with collection button for audit trail
            lead.setdefault('_button', 'auto_collect')

            # Location fallback before intelligence scoring
            if not lead.get('country') and locations:
                _loc_parts = [p.strip() for p in locations[0].split(',')]
                lead['country'] = _loc_parts[-1]
                if not lead.get('city') and len(_loc_parts) > 1:
                    lead['city'] = _loc_parts[0]

            enriched_leads.append(lead)
            pct = 40 + int((idx + 1) / max(total, 1) * 40)
            _update_task(task_id, percent=pct, collected=len(enriched_leads))

        # ── Step 5: Company-first intelligence pipeline ───────────────────
        # All candidates flow through 7 hard gates before any contact is resolved.
        # Hunter / ZeroBounce are called ONLY inside Stage 8 (ContactResolver)
        # after the company passes all intelligence gates.
        saved_auto_leads = []
        _auto_location = locations[0] if locations else ''

        # NOTE: already inside outer `with app_ctx:` — do NOT re-enter the same instance
        from app.models.models import db, Lead  # noqa (available via closure but explicit for clarity)
        from app.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
        if True:  # structural block to preserve indentation of the save/pipeline code below

            _validated_count    = 0
            _semi_validated_count = 0
            _dropped_count      = 0

            def _auto_save_fn(lead_data: dict) -> bool:
                """Called by IntelligenceOrchestrator after company passes all 7 gates."""
                nonlocal _validated_count, _semi_validated_count, _dropped_count
                _co = (lead_data.get('company') or '').strip().rstrip('.')
                if not _co:
                    return False

                _interests = lead_data.get('interests') or []
                if isinstance(_interests, str):
                    try:
                        import json as _j
                        _interests = _j.loads(_interests)
                    except Exception:
                        _interests = [_interests] if _interests else []

                # DB dedup: scoped to current user so other users can collect same lead
                logger.info("[auto_save] attempting save: company=%r country=%r email=%r",
                            _co, lead_data.get('country'), lead_data.get('email'))
                try:
                    _uid = getattr(g, 'user_id', None)
                    _em = (lead_data.get('email') or '').strip().lower()
                    if _em and _uid and Lead.query.filter_by(email=_em, collected_by=_uid).first():
                        logger.warning("[auto_save] SKIP duplicate email for user %s: %s", _uid, _em)
                        auto_report.record_duplicate()
                        return False
                    if lead_data.get('company') and lead_data.get('country') and _uid:
                        if Lead.query.filter_by(
                            company=lead_data['company'], country=lead_data['country'], collected_by=_uid
                        ).first():
                            logger.warning("[auto_save] SKIP duplicate company+country for user %s: %s / %s", _uid, lead_data['company'], lead_data['country'])
                            auto_report.record_duplicate()
                            return False
                except Exception as _dedup_exc:
                    logger.warning("[auto_save] dedup check error: %s", _dedup_exc)

                # Score-based status with counters
                _auto_final_score = float(
                    (lead_data.get('_intelligence_decision') or {}).get('final_score', 0)
                    or lead_data.get('final_company_score', 0) or 0
                )
                _auto_suggested_status = lead_data.get('_suggested_status', '')
                if not _auto_suggested_status:
                    if _auto_final_score >= 70:
                        _auto_suggested_status = 'validated'
                    elif _auto_final_score >= 50:
                        _auto_suggested_status = 'semi_validated'
                    else:
                        _auto_suggested_status = 'semi_validated'
                if _auto_suggested_status == 'validated':
                    _validated_count += 1
                else:
                    _semi_validated_count += 1

                try:
                    _dp_auto = dict(lead_data.get('data_points') or {})
                    _intent_auto  = _dp_auto.get('intent') or {}
                    _bi_auto = (lead_data.get('buying_intent') or _intent_auto.get('buying_intent') or 'none')[:20]
                    _ic_auto = float(lead_data.get('intent_confidence') or _intent_auto.get('confidence') or 0.0)
                    _auto_score = float(lead_data.get('final_company_score') or
                                        lead_data.get('qualification_score') or 0.0)
                    # Fallback interests: inject search keywords when lead has none
                    if not _interests:
                        _kw_parts = [k for k in ([_effective_keywords] + industries) if k]
                        _interests = _kw_parts[:5]
                    new_lead = Lead(
                        name              = (lead_data.get('name') or _co or '')[:255] or None,
                        email             = (lead_data.get('email') or None),
                        company           = _co[:255],
                        position          = (lead_data.get('position') or '')[:255] or None,
                        industry          = lead_data.get('industry') or None,
                        website           = _sanitize_url(lead_data.get('website') or ''),
                        linkedin_url      = (lead_data.get('linkedin_url') or '')[:500] or None,
                        country           = (lead_data.get('country') or '')[:100] or None,
                        city              = (lead_data.get('city') or '')[:100] or None,
                        location          = (lead_data.get('location') or '')[:255] or None,
                        phone             = lead_data.get('phone') or None,
                        interests         = _interests,
                        lead_type         = lead_data.get('lead_type') or (
                            'person' if lead_data.get('position') or lead_data.get('linkedin_url')
                            else 'company'
                        ),
                        source            = lead_data.get('source', 'auto_collect'),
                        status            = _auto_suggested_status,
                        qualification_score  = _auto_score,
                        completeness_score   = _auto_score,
                        buying_intent     = _bi_auto,
                        intent_confidence = _ic_auto,
                        email_type        = lead_data.get('email_type') or _dp_auto.get('email_type'),
                        data_points       = _dp_auto,
                        collected_by      = _notify_user_id,
                    )
                    db.session.add(new_lead)
                    db.session.commit()
                    saved_auto_leads.append(new_lead.id)
                    auto_report.record_source(lead_data.get('source', 'auto_collect'))
                    return True
                except Exception as exc:
                    logger.warning("[auto_save] DB save error for %r: %s — %s", _co, type(exc).__name__, exc)
                    db.session.rollback()
                    return False

            if _fallback_used:
                from app.services.collection_policy import BALANCED_INTELLIGENCE as _AUTO_POLICY
                _auto_allowed_types = frozenset({'b2b_saas', 'b2b_services', 'ecommerce', 'unknown'})
            else:
                from app.services.collection_policy import STRICT_INTELLIGENCE as _AUTO_POLICY
                _auto_allowed_types = frozenset({'b2b_saas', 'b2b_services'})
            _auto_orch = IntelligenceOrchestrator(
                allowed_types=_auto_allowed_types,
                use_hunter=True,
                use_zerobounce=True,
                policy=_AUTO_POLICY,
            )
            _auto_intel_report = _auto_orch.run_pipeline(
                candidates=enriched_leads,
                query=_effective_keywords or ' '.join(industries[:2]),
                location=_auto_location,
                save_lead_fn=_auto_save_fn,
                collection_button='auto_collect',
            )
            saved   = _auto_intel_report.n_saved
            skipped = _auto_intel_report.n_rejected + _auto_intel_report.n_needs_review

        # Background enrichment for every saved lead
        for _al_id in saved_auto_leads:
            if _al_id:
                threading.Thread(
                    target=_auto_enrich_lead_async,
                    args=(_al_id, current_app.app_context()),
                    daemon=True,
                ).start()

        _final_msg = (
            "Apollo returned 0 and fallback sources found no qualified leads."
            if _fallback_used and saved == 0
            else f"Saved {saved} leads"
        )
        _update_task(
            task_id, percent=100, status='done',
            collected=len(enriched_leads), saved=saved,
            skipped=skipped, sources=sources_used,
            apollo_count=_apollo_count,
            fallback_used=_fallback_used,
            fallback_reason=_fallback_reason,
            fallback_counts=_fallback_counts,
            validated_count=_validated_count,
            semi_validated_count=_semi_validated_count,
            dropped_count=_dropped_count,
            message=_final_msg,
            quality_report=auto_report.to_dict(),
            intelligence_report=_auto_intel_report.to_dict(),
        )
        logger.info(
            "[auto_collect] done — saved=%d rejected=%d apollo=%d fallback=%s sources=%s",
            saved, skipped, _apollo_count, _fallback_used, sources_used,
        )

        # ── Push notification (fire-and-forget, never blocks collection) ─────
        if saved > 0:
            try:
                from app.services.fcm_service import get_fcm_service as _get_fcm
                _fcm = _get_fcm()
                if _fcm.is_configured():
                    _lead_word = 'lead' if saved == 1 else 'leads'
                    _fcm.send_to_user(
                        user_id=_notify_user_id,
                        title=f'⚡ {saved} new {_lead_word} collected',
                        body='AI pipeline complete · tap to review',
                        data={
                            'type':   'collection_complete',
                            'source': 'auto_collect',
                            'saved':  str(saved),
                        },
                    )
            except Exception as _notif_err:
                logger.debug("[auto_collect] push notification skipped (non-fatal): %s", _notif_err)

    threading.Thread(target=_run, daemon=True).start()

    return jsonify({
        'status':  'started',
        'task_id': task_id,
        'message': 'Auto-collection pipeline started (Apollo → Hunter → PDL → Clearbit → AI)',
    }), 202


@ai_bp.route('/collect/auto/status/<task_id>', methods=['GET'])
@token_required
@limiter.exempt
@handle_exceptions
def auto_collect_status(task_id):
    """Poll auto-collect task progress."""
    with _tasks_lock:
        task = _collection_tasks.get(task_id)
    if not task:
        return jsonify({'status': 'not_found'}), 404
    return jsonify(task), 200


# ============================================================================
# § 16 · EXTENDED MULTI-SOURCE COLLECTION  (/collect-extended)
# More sources → More candidates → Merge → Enrich → Verify → Quality filter
# ============================================================================

@ai_bp.route('/collect-extended', methods=['POST'])
@token_required
@handle_exceptions
def collect_extended():
    """
    Extended collection pipeline:
      GitHub + Crunchbase + News + public web + Apollo search
          ↓
      Candidate merge  (same person from N sources → one record)
          ↓
      Enrichment cascade  (Hunter → PDL → Apollo enrich → Clearbit)
          ↓
      Email verification  (ZeroBounce / DNS-MX)
          ↓
      evaluate_lead_quality()  — unchanged strict gate
          ↓
      Save high_quality + qualified only

    POST body (all optional):
      {
        "query":       "SaaS CTO",       // keyword for all collectors
        "locations":   ["San Francisco", "New York"],
        "topics":      ["saas","fintech"],  // GitHub topic search
        "max_results": 100,              // target candidates before filter
        "sources":     ["github","crunchbase","news","web","apollo"],
        "verify_emails": true            // run email verification (uses quota)
      }
    """
    import uuid

    try:
        data         = request.get_json(force=True, silent=True) or {}
        query        = data.get('query', '').strip()
        locations    = data.get('locations') or []
        topics       = data.get('topics') or []
        max_results  = min(int(data.get('max_results', 80)), 200)
        sources_req  = set(data.get('sources') or ['github', 'crunchbase', 'news', 'explorium', 'apollo'])
        verify_flag  = bool(data.get('verify_emails', True))

        task_id = str(uuid.uuid4())
        _cleanup_old_tasks()
        with _tasks_lock:
            _collection_tasks[task_id] = {
                'id':         task_id,
                'status':     'running',
                'query':      query,
                'phase':      'collecting',
                'candidates': 0,
                'merged':     0,
                'verified':   0,
                'saved':      0,
                'rejected':   0,
                'percent':    0,
                'started_at': datetime.now(timezone.utc).isoformat(),
                'sources_run': [],
                'quality_report': {},
            }

        app = current_app._get_current_object()  # type: ignore[attr-defined]

        def _run():
            with app.app_context():
                from app.models.models import db, Lead
                from app.services.lead_quality_engine import (
                    evaluate_lead_quality, CollectionQualityReport,
                )
                from app.services.lead_merger import merge_candidates
                from app.services.email_verifier import bulk_verify
                from app.services.lead_fallback import enrich_lead_fallbacks

                all_candidates = []
                sources_run    = []

                # ── PHASE 1: Collection ──────────────────────────────────
                _update_task(task_id, phase='collecting', percent=5)

                if 'github' in sources_req:
                    try:
                        from app.services.github_collector import get_github_collector
                        gh = get_github_collector()
                        gh_leads = gh.collect(
                            keywords=query,
                            locations=locations or None,
                            topics=topics or None,
                            max_results=max_results // 3,
                        )
                        all_candidates.extend(gh_leads)
                        sources_run.append('github')
                        logger.info(f"[extended] GitHub → {len(gh_leads)} candidates")
                    except Exception as exc:
                        logger.warning(f"[extended] GitHub collector error: {exc}")

                _update_task(task_id, percent=20, candidates=len(all_candidates))

                if 'crunchbase' in sources_req:
                    try:
                        from app.services.crunchbase_collector import get_crunchbase_collector
                        cb = get_crunchbase_collector()
                        cb_leads = cb.collect(
                            keywords=query,
                            locations=locations or None,
                            max_results=max_results // 3,
                        )
                        all_candidates.extend(cb_leads)
                        sources_run.append('crunchbase')
                        logger.info(f"[extended] Crunchbase → {len(cb_leads)} candidates")
                    except Exception as exc:
                        logger.warning(f"[extended] Crunchbase collector error: {exc}")

                _update_task(task_id, percent=35, candidates=len(all_candidates))

                if 'news' in sources_req:
                    try:
                        from app.services.news_collector import get_news_collector
                        nc = get_news_collector()
                        news_leads = nc.collect(
                            keywords=query,
                            max_results=max_results // 2,
                        )
                        all_candidates.extend(news_leads)
                        sources_run.append('news')
                        logger.info(f"[extended] News → {len(news_leads)} candidates")
                    except Exception as exc:
                        logger.warning(f"[extended] News collector error: {exc}")

                _update_task(task_id, percent=50, candidates=len(all_candidates),
                             sources_run=sources_run)

                if 'apollo' in sources_req:
                    try:
                        from app.services.apollo_service import get_apollo_service
                        apollo = get_apollo_service()
                        if apollo.is_configured():
                            ap_leads = apollo.search_people(
                                keywords=query,
                                locations=locations or None,
                                per_page=min(max_results // 4, 25),
                            )
                            all_candidates.extend(ap_leads)
                            sources_run.append('apollo')
                            logger.info(f"[extended] Apollo → {len(ap_leads)} candidates")
                    except Exception as exc:
                        logger.warning(f"[extended] Apollo search error: {exc}")

                if 'explorium' in sources_req:
                    try:
                        from app.services.explorium_service import get_explorium_service
                        expl = get_explorium_service()
                        if expl.is_configured():
                            expl_leads = expl.search_prospects(
                                keywords=query,
                                locations=locations or None,
                                per_page=min(max_results // 3, 25),
                            )
                            all_candidates.extend(expl_leads)
                            sources_run.append('explorium')
                            logger.info(f"[extended] Explorium → {len(expl_leads)} candidates")
                    except Exception as exc:
                        logger.warning(f"[extended] Explorium search error: {exc}")

                logger.info(
                    f"[extended] Phase 1 complete: {len(all_candidates)} raw candidates "
                    f"from {sources_run}"
                )
                _update_task(task_id, percent=55, candidates=len(all_candidates))

                # ── PHASE 2: Merge duplicates ────────────────────────────
                _update_task(task_id, phase='merging', percent=58)
                merged = merge_candidates(all_candidates)
                _update_task(task_id, merged=len(merged), percent=62)
                logger.info(
                    f"[extended] Phase 2: {len(all_candidates)} → {len(merged)} after merge"
                )

                # ── PHASE 3: Enrichment cascade ──────────────────────────
                # Order: scrape → Hunter → Explorium → email_verifier → Clearbit/PDL
                # (Explorium is wired inside enrich_lead_fallbacks as step 2.5)
                _update_task(task_id, phase='enriching', percent=65)
                enriched = []
                for lead in merged:
                    try:
                        enriched_lead = enrich_lead_fallbacks(lead)
                        enriched.append(enriched_lead)
                    except Exception as exc:
                        logger.debug(f"[extended] enrich error: {exc}")
                        enriched.append(lead)

                logger.info(f"[extended] Phase 3: enrichment cascade complete")
                _update_task(task_id, phase='verifying', percent=75)

                # ── PHASE 4: Email verification ──────────────────────────
                if verify_flag:
                    bulk_verify(enriched, max_to_verify=50)
                    n_verified = sum(
                        1 for ld in enriched
                        if ld.get('data_points', {}).get('email_verified')
                    )
                    _update_task(task_id, verified=n_verified, percent=82)
                    logger.info(f"[extended] Phase 4: {n_verified} emails verified")

                # ── PHASE 5: Quality gate + save ─────────────────────────
                _update_task(task_id, phase='saving', percent=85)

                report  = CollectionQualityReport(source='extended')
                saved   = 0
                rejected = 0

                for lead_data in enriched:
                    report.raw_candidates += 1
                    try:
                        _qd = evaluate_lead_quality(
                            lead_data, source=lead_data.get('source', 'extended'),
                            report=report,
                        )
                        if not _qd.should_save:
                            rejected += 1
                            continue

                        lead_data.setdefault('data_points', {}).update(_qd.metadata)
                        lead_data['qualification_score'] = _qd.quality_score
                        lead_data['completeness_score']  = _qd.quality_score
                        report.record_score(_qd.quality_score)
                        report.record_email(
                            _qd.metadata.get('email_type', ''),
                            _qd.metadata.get('email_verified', False),
                        )
                        report.parsed_candidates += 1

                        # DB dedup: scoped to current user so other users can collect same lead
                        existing = None
                        _uid = getattr(g, 'user_id', None)
                        dp = lead_data.get('data_points') or {}
                        if lead_data.get('email') and dp.get('email_verified') and _uid:
                            existing = Lead.query.filter_by(email=lead_data['email'], collected_by=_uid).first()
                        if not existing and lead_data.get('name') and lead_data.get('company') and _uid:
                            existing = Lead.query.filter_by(
                                name=lead_data['name'],
                                company=lead_data['company'],
                                collected_by=_uid,
                            ).first()
                        if existing:
                            report.record_duplicate()
                            continue

                        _co = (lead_data.get('company') or '').strip().rstrip('.')
                        if len(_co.split()) > 8:
                            rejected += 1
                            continue

                        # Location fallback: news/github leads rarely carry location;
                        # fill from the user-specified locations list when blank.
                        if not lead_data.get('country') and locations:
                            _loc_parts = [p.strip() for p in locations[0].split(',')]
                            lead_data['country'] = _loc_parts[-1]
                            if not lead_data.get('city') and len(_loc_parts) > 1:
                                lead_data['city'] = _loc_parts[0]
                        if not lead_data.get('location') and (lead_data.get('country') or lead_data.get('city')):
                            lead_data['location'] = ', '.join(
                                p for p in [lead_data.get('city', ''), lead_data.get('country', '')] if p
                            )

                        lead_obj = Lead(
                            name=(lead_data.get('name') or _co or '')[:255] or None,
                            email=lead_data.get('email') or None,
                            phone=lead_data.get('phone') or None,
                            company=_co[:255] or None,
                            position=(lead_data.get('position') or '')[:255] or None,
                            location=(lead_data.get('location') or '')[:255] or None,
                            country=(lead_data.get('country') or '')[:100] or None,
                            city=(lead_data.get('city') or '')[:100] or None,
                            industry=(lead_data.get('industry') or '')[:100] or None,
                            website=_sanitize_url(lead_data.get('website') or ''),
                            linkedin_url=(lead_data.get('linkedin_url') or '')[:500] or None,
                            source=lead_data.get('source', 'extended'),
                            status='pending',
                            qualification_score=lead_data.get('qualification_score', 0.0),
                            completeness_score=lead_data.get('completeness_score', 0.0),
                            email_type=lead_data.get('email_type'),
                            data_points=lead_data.get('data_points', {}),
                        )
                        db.session.add(lead_obj)
                        db.session.commit()
                        saved += 1
                    except Exception as exc:
                        logger.warning(f"[extended] save error: {exc}", exc_info=True)
                        db.session.rollback()

                report.log_summary()
                logger.info(
                    f"[extended] done — candidates={len(all_candidates)} "
                    f"merged={len(merged)} saved={saved} rejected={rejected}"
                )
                _update_task(
                    task_id, phase='done', percent=100, status='done',
                    saved=saved, rejected=rejected,
                    quality_report=report.to_dict(),
                    sources_run=sources_run,
                )

        threading.Thread(target=_run, daemon=True).start()

        return jsonify({
            'status':  'started',
            'task_id': task_id,
            'message': (
                f'Extended collection started '
                f'(sources: {", ".join(sources_req)})'
            ),
        }), 202

    except Exception as exc:
        logger.error(f"[extended] startup error: {exc}")
        raise APIException(f"Failed to start extended collection: {exc}", status_code=500)


@ai_bp.route('/collect-extended/status/<task_id>', methods=['GET'])
@token_required
@limiter.exempt
@handle_exceptions
def collect_extended_status(task_id):
    """Poll extended collection task progress."""
    with _tasks_lock:
        task = _collection_tasks.get(task_id)
    if not task:
        return jsonify({'status': 'not_found'}), 404
    return jsonify(task), 200
