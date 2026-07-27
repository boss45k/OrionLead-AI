"""
Data Sources routes — real persistent sources backed by the data_sources DB table.

Supported source types:
  API      — HTTP endpoint returning JSON leads (GET with Authorization header)
  CSV      — Uploaded CSV file parsed into leads
  Database — External PostgreSQL/MySQL DB queried via connection string (stored in config)
  Web      — Alias for the existing public_web_collector

Built-in integrations are auto-created on first GET /sources. Their lead counts
come from the actual leads table (not from a cached counter), and their sync
functions call the real service classes.
"""
import csv
import io
import logging
import os
import time
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, request
from sqlalchemy import func, text

from flask import g

from app.exceptions import APIException
from app.models.models import DataSource, Lead, User, db
from app.routes.auth import token_required, admin_required
from app.utils.error_handler import handle_exceptions
from app.utils.rate_limiter import get_limiter

logger = logging.getLogger(__name__)

sources_bp = Blueprint('sources', __name__, url_prefix='/api/v1/sources')
limiter = get_limiter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads')

# ── Validators / importers ────────────────────────────────────────────────────

try:
    from app.services.lead_validator import validate_and_score, DuplicateFilter
    from app.services.lead_extractor import _email_type
    _VALIDATOR_AVAILABLE = True
except ImportError:
    _VALIDATOR_AVAILABLE = False


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return 'sk_***_0000'
    return f"sk_***_{key[-4:]}"


def _now():
    return datetime.now(timezone.utc)


# ── CSV field mapping ─────────────────────────────────────────────────────────

_CSV_FIELD_MAP = {
    'name': 'name', 'full name': 'name', 'fullname': 'name',
    'full_name': 'name', 'contact name': 'name', 'contact': 'name',
    'first name': '_first', 'firstname': '_first', 'first_name': '_first',
    'last name': '_last', 'lastname': '_last', 'last_name': '_last',
    'email': 'email', 'email address': 'email', 'e-mail': 'email',
    'email_address': 'email',
    'phone': 'phone', 'phone number': 'phone', 'mobile': 'phone',
    'telephone': 'phone', 'phone_number': 'phone', 'cell': 'phone',
    'company': 'company', 'company name': 'company', 'organization': 'company',
    'organisation': 'company', 'account name': 'company', 'employer': 'company',
    'company_name': 'company',
    'title': 'position', 'job title': 'position', 'position': 'position',
    'role': 'position', 'job_title': 'position',
    'location': 'location', 'city': 'city', 'country': 'country',
    'state': 'city', 'region': 'city',
    'industry': 'industry', 'sector': 'industry', 'vertical': 'industry',
    'website': 'website', 'url': 'website', 'web': 'website',
    'linkedin': 'linkedin_url', 'linkedin url': 'linkedin_url',
    'linkedin_url': 'linkedin_url', 'profile': 'linkedin_url',
    'notes': 'notes', 'description': 'notes', 'comments': 'notes',
}


def _parse_csv_rows(file_obj) -> list[dict]:
    content = file_obj.read()
    if isinstance(content, bytes):
        try:
            text_content = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            text_content = content.decode('latin-1')
    else:
        text_content = content

    reader = csv.DictReader(io.StringIO(text_content))
    leads = []
    for row in reader:
        lead = {}
        first = ''
        last = ''
        for col, val in row.items():
            col_key = (col or '').strip().lower()
            mapped = _CSV_FIELD_MAP.get(col_key)
            if not mapped:
                continue
            val = (val or '').strip()
            if mapped == '_first':
                first = val
            elif mapped == '_last':
                last = val
            else:
                lead[mapped] = val

        if not lead.get('name') and (first or last):
            lead['name'] = f"{first} {last}".strip()

        if lead.get('name') or lead.get('email'):
            leads.append(lead)

    return leads


def _import_leads(leads_data: list[dict], source_name: str) -> tuple[int, int]:
    """Import lead dicts into the DB. Returns (saved, skipped)."""
    saved = 0
    skipped = 0
    dedup = DuplicateFilter() if _VALIDATOR_AVAILABLE else None
    _uid = getattr(g, 'user_id', None)

    for raw in leads_data:
        name = (raw.get('name') or '').strip() or 'Unknown'
        email = (raw.get('email') or '').strip().lower() or None

        if email:
            # Scope dedup to this user — other users can collect the same lead independently
            if _uid:
                exists = db.session.execute(
                    text("SELECT id FROM leads WHERE email = :e AND collected_by = :uid LIMIT 1"),
                    {'e': email, 'uid': _uid}
                ).fetchone()
            else:
                exists = db.session.execute(
                    text("SELECT id FROM leads WHERE email = :e LIMIT 1"),
                    {'e': email}
                ).fetchone()
            if exists:
                skipped += 1
                continue

        if _VALIDATOR_AVAILABLE:
            raw_lead = dict(raw)
            raw_lead.setdefault('name', name)
            scored_lead, should_save, _ = validate_and_score(raw_lead, debug=False)
            if not should_save:
                skipped += 1
                continue
            if dedup:
                is_dup, _ = dedup.is_duplicate(scored_lead)
                if is_dup:
                    skipped += 1
                    continue
                dedup.register(scored_lead)
            raw = scored_lead

        lead = Lead(
            name=name[:255],
            email=email,
            phone=(raw.get('phone') or '')[:20] or None,
            company=(raw.get('company') or '')[:255] or None,
            position=(raw.get('position') or '')[:255] or None,
            location=(raw.get('location') or '')[:255] or None,
            country=(raw.get('country') or '')[:100] or None,
            city=(raw.get('city') or '')[:255] or None,
            industry=(raw.get('industry') or '')[:255] or None,
            website=(raw.get('website') or '')[:500] or None,
            linkedin_url=(raw.get('linkedin_url') or '')[:500] or None,
            notes=raw.get('notes') or None,
            source=source_name,
            status=raw.get('status', 'pending'),
            completeness_score=raw.get('completeness_score', 0.0),
            email_type=raw.get('email_type') or (
                _email_type(email) if (email and _VALIDATOR_AVAILABLE) else None
            ),
            collected_by=_uid,
        )
        db.session.add(lead)
        saved += 1

        if saved % 100 == 0:
            try:
                db.session.flush()
            except Exception:
                db.session.rollback()
                break

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"[sources] DB commit failed: {e}")
        return saved, skipped

    return saved, skipped


# ── Built-in integration definitions ─────────────────────────────────────────

BUILTIN_SOURCE_DEFS = [
    {
        'key': 'hunter',
        'name': 'Hunter.io',
        'type': 'API',
        'env_var': 'HUNTER_API_KEY',
        'url': 'https://api.hunter.io/v2',
        'description': 'Email finder & verifier — enriches leads that are missing an email address',
        'action': 'enrich',
    },
    {
        'key': 'apollo',
        'name': 'Apollo.io',
        'type': 'API',
        'env_var': 'APOLLO_API_KEY',
        'url': 'https://api.apollo.io/v1',
        'description': 'B2B lead database — searches for people by title, location and industry',
        'action': 'collect',
    },
    {
        'key': 'pdl',
        'name': 'People Data Labs',
        'type': 'API',
        'env_var': 'PDL_API_KEY',
        'url': 'https://api.peopledatalabs.com/v5',
        'description': 'Person & company enrichment with 1.5B+ profiles',
        'action': 'enrich',
    },
    {
        'key': 'clearbit',
        'name': 'Clearbit',
        'type': 'API',
        'env_var': 'CLEARBIT_API_KEY',
        'url': 'https://person.clearbit.com/v2',
        'description': 'Company & person enrichment — adds industry, size and social profiles',
        'action': 'enrich',
    },
    {
        'key': 'explorium',
        'name': 'Explorium',
        'type': 'API',
        'env_var': 'EXPLORIUM_API_KEY',
        'url': 'https://api.explorium.ai/v1',
        'description': 'Advanced business enrichment & prospect discovery',
        'action': 'enrich',
    },
    {
        'key': 'github',
        'name': 'GitHub',
        'type': 'API',
        'env_var': 'GITHUB_TOKEN',
        'url': 'https://api.github.com',
        'description': 'Developer & open-source contributor lead collection',
        'action': 'collect',
    },
    {
        'key': 'crunchbase',
        'name': 'Crunchbase',
        'type': 'API',
        'env_var': 'CRUNCHBASE_API_KEY',
        'url': 'https://api.crunchbase.com/api/v4',
        'description': 'Startup founders & investors from Crunchbase',
        'action': 'collect',
    },
    {
        'key': 'web_public',
        'name': 'Public Web Collector',
        'type': 'Web',
        'env_var': None,
        'url': None,
        'description': 'Scrapes business directories & company websites for contact details',
        'action': 'collect',
    },
    {
        'key': 'social_media',
        'name': 'Social Media Collector',
        'type': 'Web',
        'env_var': None,
        'url': None,
        'description': 'LinkedIn, Twitter, Reddit and Facebook group lead collection',
        'action': 'collect',
    },
    {
        'key': 'news',
        'name': 'News & Press Collector',
        'type': 'Web',
        'env_var': None,
        'url': None,
        'description': 'Extracts contacts mentioned in news articles and press releases',
        'action': 'collect',
    },
]


def _ensure_builtin_sources():
    """Auto-create DB records for built-in integrations if they don't exist yet."""
    existing_keys: set[str] = set()
    for s in DataSource.query.filter(DataSource.config.isnot(None)).all():
        cfg = s.config or {}
        if cfg.get('system'):
            existing_keys.add(cfg.get('system_key', ''))

    added = 0
    for defn in BUILTIN_SOURCE_DEFS:
        if defn['key'] in existing_keys:
            continue
        env_var = defn.get('env_var')
        is_ready = bool(not env_var or os.environ.get(env_var))
        source = DataSource(
            name=defn['name'],
            source_type=defn['type'],
            url=defn.get('url'),
            enabled=True,
            sync_frequency='manual',
            status='active' if is_ready else 'inactive',
            config={
                'system': True,
                'system_key': defn['key'],
                'description': defn['description'],
                'action': defn['action'],
                'env_var': env_var,
            },
        )
        db.session.add(source)
        added += 1

    if added:
        try:
            db.session.commit()
            logger.info(f"[sources] Auto-created {added} built-in source records")
        except Exception as e:
            db.session.rollback()
            logger.warning(f"[sources] Failed to create built-in sources: {e}")


def _get_real_lead_counts() -> dict[str, int]:
    """Return real lead counts per integration by querying the leads table."""
    counts: dict[str, int] = {}

    # Collector sources — counted by source field prefix
    prefix_specs: dict[str, list[tuple[str, str]]] = {
        'apollo':       [('=', 'apollo')],
        'github':       [('=', 'github')],
        'crunchbase':   [('=', 'crunchbase')],
        'news':         [('=', 'news')],
        'web_public':   [('like', 'web_public%'), ('like', 'web_people%')],
        'social_media': [
            ('like', 'linkedin_%'), ('like', 'twitter%'),
            ('like', 'reddit_%'), ('like', 'facebook_%'),
            ('like', 'telegram_%'),
        ],
    }

    for key, clauses in prefix_specs.items():
        total = 0
        for op, val in clauses:
            q = db.session.query(func.count(Lead.id))
            if op == 'like':
                q = q.filter(Lead.source.like(val))
            else:
                q = q.filter(Lead.source == val)
            total += q.scalar() or 0
        counts[key] = total

    # Enrichment services — counted by data_points.enrichment_source in Python
    enrichment_keys = {'hunter': 0, 'pdl': 0, 'clearbit': 0, 'explorium': 0}
    try:
        rows = db.session.query(Lead.data_points).filter(Lead.data_points.isnot(None)).all()
        for (dp,) in rows:
            if not isinstance(dp, dict):
                continue
            src = dp.get('enrichment_source') or dp.get('email_source', '')
            if src in enrichment_keys:
                enrichment_keys[src] += 1
    except Exception as e:
        logger.debug(f"[sources] data_points count error: {e}")

    counts.update(enrichment_keys)
    return counts


# ── Built-in sync functions ───────────────────────────────────────────────────

def _sync_hunter_enrich(_source: DataSource, cfg: dict) -> tuple[int, str]:
    """Enrich leads missing email via Hunter.io domain search."""
    from app.services.hunter_service import HunterService
    svc = HunterService()
    if not svc.is_configured():
        raise APIException("HUNTER_API_KEY not configured in environment", status_code=400)

    max_leads = min(int(cfg.get('max_leads', 50)), 200)
    candidates = (
        Lead.query
        .filter(Lead.email.is_(None), Lead.company.isnot(None))
        .limit(max_leads)
        .all()
    )
    if not candidates:
        return 0, "No leads without email found to enrich"

    enriched = 0
    for lead in candidates:
        try:
            result = svc.enrich_lead({
                'name': lead.name,
                'company': lead.company,
                'website': lead.website,
                'email': lead.email,
            })
            if result.get('email') and result['email'] != lead.email:
                lead.email = result['email']
                dp = lead.data_points or {}
                dp['enrichment_source'] = 'hunter'
                dp['email_source'] = result.get('email_source', 'hunter')
                lead.data_points = dp
                enriched += 1
        except Exception as e:
            logger.debug(f"[hunter] Lead {lead.id}: {e}")

    if enriched:
        db.session.commit()

    return enriched, f"Hunter enriched {enriched}/{len(candidates)} leads with email addresses"


def _sync_apollo(_source: DataSource, cfg: dict) -> tuple[int, str]:
    """Collect leads from Apollo.io people search."""
    from app.services.apollo_service import ApolloService
    svc = ApolloService()
    if not svc.is_configured():
        raise APIException("APOLLO_API_KEY not configured in environment", status_code=400)

    keywords = cfg.get('keywords', '')
    titles = cfg.get('titles') or ['CEO', 'CTO', 'Founder', 'VP Sales', 'VP Marketing']
    locations = cfg.get('locations') or None
    industries = cfg.get('industries') or None
    limit = min(int(cfg.get('max_leads', 25)), 100)

    people = svc.search_people(
        keywords=keywords,
        titles=titles,
        locations=locations,
        industries=industries,
        per_page=limit,
    )
    if not people:
        return 0, "Apollo returned 0 results — check API key or adjust search params in source config"

    saved, skipped = _import_leads(people, 'apollo')
    return saved, f"Apollo: {len(people)} results, saved {saved} new leads, skipped {skipped} duplicates"


def _sync_pdl_enrich(_source: DataSource, cfg: dict) -> tuple[int, str]:
    """Enrich leads using People Data Labs."""
    from app.services.pdl_service import PDLService
    svc = PDLService()
    if not svc.is_configured():
        raise APIException("PDL_API_KEY not configured in environment", status_code=400)

    max_leads = min(int(cfg.get('max_leads', 50)), 200)
    candidates = (
        Lead.query
        .filter(Lead.email.isnot(None), Lead.company.is_(None))
        .limit(max_leads)
        .all()
    )
    if not candidates:
        return 0, "No leads needing PDL enrichment found"

    enriched = 0
    for lead in candidates:
        try:
            result = svc.enrich_lead({'name': lead.name, 'email': lead.email, 'company': lead.company})
            if result and result.get('name'):
                if result.get('company') and not lead.company:
                    lead.company = result['company']
                if result.get('position') and not lead.position:
                    lead.position = result['position']
                if result.get('linkedin_url') and not lead.linkedin_url:
                    lead.linkedin_url = result['linkedin_url']
                dp = lead.data_points or {}
                dp['enrichment_source'] = 'pdl'
                lead.data_points = dp
                enriched += 1
        except Exception as e:
            logger.debug(f"[pdl] Lead {lead.id}: {e}")

    if enriched:
        db.session.commit()

    return enriched, f"PDL enriched {enriched}/{len(candidates)} leads"


def _sync_clearbit_enrich(source: DataSource, cfg: dict) -> tuple[int, str]:
    """Enrich leads using Clearbit."""
    from app.services.clearbit_service import ClearbitService
    svc = ClearbitService()
    if not svc.is_configured():
        raise APIException("CLEARBIT_API_KEY not configured in environment", status_code=400)

    max_leads = min(int(cfg.get('max_leads', 50)), 200)
    candidates = (
        Lead.query
        .filter(Lead.email.isnot(None), Lead.industry.is_(None))
        .limit(max_leads)
        .all()
    )
    if not candidates:
        return 0, "No leads needing Clearbit enrichment found"

    enriched = 0
    for lead in candidates:
        try:
            result = svc.enrich_lead({'email': lead.email, 'name': lead.name, 'company': lead.company})
            if result:
                if result.get('industry') and not lead.industry:
                    lead.industry = result['industry']
                if result.get('company') and not lead.company:
                    lead.company = result['company']
                if result.get('position') and not lead.position:
                    lead.position = result['position']
                dp = lead.data_points or {}
                dp['enrichment_source'] = 'clearbit'
                lead.data_points = dp
                enriched += 1
        except Exception as e:
            logger.debug(f"[clearbit] Lead {lead.id}: {e}")

    if enriched:
        db.session.commit()

    return enriched, f"Clearbit enriched {enriched}/{len(candidates)} leads"


def _sync_explorium_enrich(source: DataSource, cfg: dict) -> tuple[int, str]:
    """Enrich leads using Explorium."""
    from app.services.explorium_service import ExploriumService
    svc = ExploriumService()
    if not svc.is_configured():
        raise APIException("EXPLORIUM_API_KEY not configured in environment", status_code=400)

    max_leads = min(int(cfg.get('max_leads', 50)), 200)
    candidates = Lead.query.filter(Lead.email.isnot(None)).limit(max_leads).all()
    if not candidates:
        return 0, "No leads found to enrich"

    enriched = 0
    for lead in candidates:
        try:
            result = svc.enrich_lead({'email': lead.email, 'name': lead.name, 'company': lead.company})
            if result:
                for field in ('company', 'position', 'industry', 'location', 'phone'):
                    if result.get(field) and not getattr(lead, field, None):
                        setattr(lead, field, result[field])
                dp = lead.data_points or {}
                dp['enrichment_source'] = 'explorium'
                lead.data_points = dp
                enriched += 1
        except Exception as e:
            logger.debug(f"[explorium] Lead {lead.id}: {e}")

    if enriched:
        db.session.commit()

    return enriched, f"Explorium enriched {enriched}/{len(candidates)} leads"


def _sync_github(source: DataSource, cfg: dict) -> tuple[int, str]:
    """Collect developer leads from GitHub."""
    from app.services.github_collector import GitHubCollector
    collector = GitHubCollector()
    if not collector.is_configured():
        raise APIException("GITHUB_TOKEN not configured in environment", status_code=400)

    keywords = cfg.get('keywords', 'developer engineer')
    locations = cfg.get('locations') or None
    max_results = min(int(cfg.get('max_leads', 40)), 200)

    leads = collector.collect(keywords=keywords, locations=locations, max_results=max_results)
    if not leads:
        return 0, "GitHub returned 0 results"

    saved, skipped = _import_leads(leads, 'github')
    return saved, f"GitHub: {len(leads)} profiles, saved {saved} new leads, skipped {skipped} duplicates"


def _sync_crunchbase(source: DataSource, cfg: dict) -> tuple[int, str]:
    """Collect startup leads from Crunchbase."""
    from app.services.crunchbase_collector import CrunchbaseCollector
    collector = CrunchbaseCollector()

    keywords = cfg.get('keywords', '')
    locations = cfg.get('locations') or None
    max_results = min(int(cfg.get('max_leads', 40)), 100)

    leads = collector.collect(keywords=keywords, locations=locations, max_results=max_results)
    if not leads:
        return 0, "Crunchbase returned 0 results — check CRUNCHBASE_API_KEY"

    saved, skipped = _import_leads(leads, 'crunchbase')
    return saved, f"Crunchbase: {len(leads)} leads, saved {saved} new, skipped {skipped} duplicates"


def _sync_news(source: DataSource, cfg: dict) -> tuple[int, str]:
    """Collect leads from news articles."""
    from app.services.news_collector import NewsCollector
    collector = NewsCollector()

    keywords = cfg.get('keywords', '')
    max_results = min(int(cfg.get('max_leads', 40)), 100)

    leads = collector.collect(keywords=keywords, max_results=max_results)
    if not leads:
        return 0, "News collector returned 0 results"

    saved, skipped = _import_leads(leads, 'news')
    return saved, f"News: {len(leads)} leads, saved {saved} new, skipped {skipped} duplicates"


def _sync_web_public(_source: DataSource, _cfg: dict) -> tuple[int, str]:
    raise APIException(
        "Public Web collection requires search parameters. "
        "Use the Leads page Collect button to run a targeted search.",
        status_code=400,
    )


def _sync_social_media(_source: DataSource, _cfg: dict) -> tuple[int, str]:
    raise APIException(
        "Social Media collection requires a platform and keyword configuration. "
        "Use the Leads page Collect button to run a targeted search.",
        status_code=400,
    )


_BUILTIN_SYNC_DISPATCH = {
    'hunter':       _sync_hunter_enrich,
    'apollo':       _sync_apollo,
    'pdl':          _sync_pdl_enrich,
    'clearbit':     _sync_clearbit_enrich,
    'explorium':    _sync_explorium_enrich,
    'github':       _sync_github,
    'crunchbase':   _sync_crunchbase,
    'news':         _sync_news,
    'web_public':   _sync_web_public,
    'social_media': _sync_social_media,
}


def _sync_builtin(source: DataSource) -> tuple[int, str]:
    cfg = source.config or {}
    key = cfg.get('system_key', '')
    sync_cfg = cfg.get('sync_config') or {}

    fn = _BUILTIN_SYNC_DISPATCH.get(key)
    if not fn:
        raise APIException(f"No sync handler for built-in source '{key}'", status_code=400)

    return fn(source, sync_cfg)


# ── User-defined source sync functions ───────────────────────────────────────

def _sync_csv(source: DataSource) -> tuple[int, str]:
    file_path = (source.config or {}).get('file_path') or source.url or ''
    if not file_path:
        raise ValueError("No file path configured. Upload a CSV file first.")
    if not os.path.isabs(file_path):
        file_path = os.path.join(UPLOAD_DIR, file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    with open(file_path, 'rb') as f:
        rows = _parse_csv_rows(f)

    if not rows:
        return 0, "CSV parsed but no valid lead rows found"

    saved, skipped = _import_leads(rows, source.name)
    return saved, f"Parsed {len(rows)} rows, saved {saved} new leads, skipped {skipped} duplicates"


def _sync_api(source: DataSource) -> tuple[int, str]:
    url = source.url or ''
    if not url:
        raise ValueError("No API URL configured.")

    cfg = source.config or {}
    api_key = cfg.get('api_key_plain') or ''
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f"Bearer {api_key}"
    for k, v in cfg.get('headers', {}).items():
        headers[k] = v

    resp = requests.get(url, headers=headers, timeout=cfg.get('timeout', 30))
    resp.raise_for_status()

    payload = resp.json()
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = (payload.get('data') or payload.get('leads') or
                payload.get('results') or payload.get('contacts') or [])
    else:
        raise ValueError(f"Unexpected API response type: {type(payload)}")

    if not rows:
        return 0, "API returned 0 records"

    normalised = []
    for r in rows:
        n = {}
        for k, v in r.items():
            mapped = _CSV_FIELD_MAP.get(k.lower().replace('_', ' ').strip())
            if mapped:
                n[mapped] = v
            else:
                n[k] = v
        normalised.append(n)

    saved, skipped = _import_leads(normalised, source.name)
    return saved, f"API returned {len(rows)} records, saved {saved} new leads, skipped {skipped} duplicates"


def _sync_database(source: DataSource) -> tuple[int, str]:
    from sqlalchemy import create_engine, text as sa_text

    cfg = source.config or {}
    conn_str = cfg.get('connection_string') or source.url or ''
    if not conn_str:
        raise ValueError("No connection string configured. Add it in source config.")

    query = cfg.get('query') or 'SELECT * FROM leads LIMIT 1000'
    limit = min(int(cfg.get('limit', 1000)), 5000)
    if 'limit' not in query.lower():
        query = f"{query.rstrip(';')} LIMIT {limit}"

    engine = create_engine(conn_str, pool_pre_ping=True, connect_args={'connect_timeout': 15})
    with engine.connect() as conn:
        result = conn.execute(sa_text(query))
        columns = list(result.keys())
        rows_raw = result.fetchall()

    rows = []
    for row in rows_raw:
        d = dict(zip(columns, row))
        normalised = {}
        for k, v in d.items():
            mapped = _CSV_FIELD_MAP.get(str(k).lower().replace('_', ' ').strip())
            if mapped:
                normalised[mapped] = str(v) if v is not None else ''
            else:
                normalised[str(k)] = str(v) if v is not None else ''
        rows.append(normalised)

    saved, skipped = _import_leads(rows, source.name)
    return saved, f"DB returned {len(rows)} rows, saved {saved} new leads, skipped {skipped} duplicates"


def _lead_count_for_role() -> int:
    """Count leads applying the same RBAC filter used by Dashboard and Analytics."""
    q = Lead.query
    if g.role == 'manager':
        mgr = User.query.get(g.user_id)
        co  = (mgr.company or '').strip().lower() if mgr else ''
        if co:
            tids = [r.id for r in User.query.filter(
                db.func.lower(db.func.trim(User.company)) == co
            ).with_entities(User.id).all()]
            q = q.filter(Lead.collected_by.in_(tids))
        else:
            q = q.filter(Lead.collected_by == g.user_id)
    elif g.role != 'admin':
        q = q.filter(Lead.collected_by == g.user_id)
    return q.count()


# ── Routes ────────────────────────────────────────────────────────────────────

@sources_bp.route('', methods=['GET'])
@limiter.limit("60 per minute")
@token_required
@handle_exceptions
def get_sources():
    """List all data sources, including auto-created built-in integrations."""
    _ensure_builtin_sources()

    sources = DataSource.query.order_by(DataSource.created_at.asc()).all()
    real_counts = _get_real_lead_counts()

    sources_list = []
    for s in sources:
        d = s.to_dict()
        cfg = s.config or {}

        if cfg.get('system'):
            sys_key = cfg.get('system_key', '')
            # Real lead count from leads table, not cached counter
            d['records'] = real_counts.get(sys_key, 0)
            # Reflect whether the required API key is actually set
            env_var = cfg.get('env_var')
            is_api_ready = bool(not env_var or os.environ.get(env_var))
            d['status'] = 'active' if is_api_ready else 'inactive'
            d['description'] = cfg.get('description', '')
            d['action'] = cfg.get('action', 'collect')

        sources_list.append(d)

    # System sources first, then user-added sources, both sorted by name
    sources_list.sort(key=lambda x: (
        0 if (x.get('config') or {}).get('system') else 1,
        x.get('name', ''),
    ))

    total_records = _lead_count_for_role()
    active = sum(1 for s in sources_list if s.get('status') == 'active')
    last_sync_dates = [s['last_sync'] for s in sources_list if s['last_sync']]

    return jsonify({
        'status': 'success',
        'data': sources_list,
        'stats': {
            'total_sources': len(sources_list),
            'active_sources': active,
            'total_records': total_records,
            'last_sync': max(last_sync_dates) if last_sync_dates else None,
            'average_performance': (
                round(sum(s['performance'] for s in sources_list) / len(sources_list), 1)
                if sources_list else 0
            ),
        }
    }), 200


@sources_bp.route('', methods=['POST'])
@limiter.limit("20 per hour")
@token_required
@admin_required
@handle_exceptions
def create_source():
    """Create a new user-defined data source."""
    data = request.get_json(force=True, silent=True) or {}

    name = (data.get('name') or '').strip()
    source_type = (data.get('type') or '').strip()
    if not name:
        raise APIException("name is required", status_code=400)
    if not source_type:
        raise APIException("type is required", status_code=400)
    if source_type not in ('API', 'CSV', 'Database', 'Web'):
        raise APIException("type must be one of: API, CSV, Database, Web", status_code=400)

    if DataSource.query.filter_by(name=name).first():
        raise APIException(f"A source named '{name}' already exists", status_code=409)

    api_key_plain = (data.get('api_key') or '').strip()
    cfg = data.get('config') or {}
    if api_key_plain:
        cfg['api_key_plain'] = api_key_plain

    source = DataSource(
        name=name,
        source_type=source_type,
        url=(data.get('url') or '').strip() or None,
        api_key_masked=_mask_key(api_key_plain) if api_key_plain else None,
        enabled=bool(data.get('enabled', True)),
        sync_frequency=data.get('sync_frequency', 'manual'),
        config=cfg if cfg else None,
    )
    db.session.add(source)
    db.session.commit()

    return jsonify({
        'status': 'success',
        'message': 'Data source created successfully',
        'data': source.to_dict(),
    }), 201


@sources_bp.route('/<int:source_id>', methods=['GET'])
@limiter.limit("60 per minute")
@token_required
@admin_required
@handle_exceptions
def get_source(source_id):
    source = DataSource.query.get(source_id)
    if not source:
        raise APIException(f"Data source {source_id} not found", status_code=404)
    d = source.to_dict()
    cfg = source.config or {}
    if cfg.get('system'):
        sys_key = cfg.get('system_key', '')
        real_counts = _get_real_lead_counts()
        d['records'] = real_counts.get(sys_key, 0)
        env_var = cfg.get('env_var')
        d['status'] = 'active' if (not env_var or os.environ.get(env_var)) else 'inactive'
        d['description'] = cfg.get('description', '')
        d['action'] = cfg.get('action', 'collect')
    return jsonify({'status': 'success', 'data': d}), 200


@sources_bp.route('/<int:source_id>', methods=['PUT'])
@limiter.limit("20 per hour")
@token_required
@admin_required
@handle_exceptions
def update_source(source_id):
    source = DataSource.query.get(source_id)
    if not source:
        raise APIException(f"Data source {source_id} not found", status_code=404)

    data = request.get_json(force=True, silent=True) or {}
    cfg = source.config or {}

    # Built-in sources: only allow updating sync_config (search params) and enabled
    if cfg.get('system'):
        if 'enabled' in data:
            source.enabled = bool(data['enabled'])
        if 'sync_config' in data and isinstance(data['sync_config'], dict):
            cfg['sync_config'] = data['sync_config']
            source.config = cfg
        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': 'Built-in source updated',
            'data': source.to_dict(),
        }), 200

    if 'name' in data:
        source.name = data['name'].strip()
    if 'type' in data:
        source.source_type = data['type'].strip()
    if 'url' in data:
        source.url = data['url'].strip() or None
    if 'sync_frequency' in data:
        source.sync_frequency = data['sync_frequency']
    if 'enabled' in data:
        source.enabled = bool(data['enabled'])
    if 'api_key' in data and data['api_key']:
        api_key_plain = data['api_key'].strip()
        source.api_key_masked = _mask_key(api_key_plain)
        cfg['api_key_plain'] = api_key_plain
        source.config = cfg
    if 'config' in data:
        cfg.update(data['config'])
        source.config = cfg

    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': 'Data source updated',
        'data': source.to_dict(),
    }), 200


@sources_bp.route('/<int:source_id>', methods=['DELETE'])
@limiter.limit("20 per hour")
@token_required
@admin_required
@handle_exceptions
def delete_source(source_id):
    source = DataSource.query.get(source_id)
    if not source:
        raise APIException(f"Data source {source_id} not found", status_code=404)

    cfg = source.config or {}
    if cfg.get('system'):
        raise APIException(
            "Built-in integration sources cannot be deleted. Disable them instead.",
            status_code=400,
        )

    name = source.name
    db.session.delete(source)
    db.session.commit()

    return jsonify({
        'status': 'success',
        'message': f'Data source "{name}" deleted',
    }), 200


@sources_bp.route('/<int:source_id>/sync', methods=['POST'])
@limiter.limit("10 per minute")
@token_required
@admin_required
@handle_exceptions
def sync_source(source_id):
    """Run a real sync on a data source."""
    source = DataSource.query.get(source_id)
    if not source:
        raise APIException(f"Data source {source_id} not found", status_code=404)
    if not source.enabled:
        raise APIException(f"Source '{source.name}' is disabled", status_code=400)

    start = time.time()
    synced_records = 0
    detail = ''

    try:
        cfg = source.config or {}
        stype = (source.source_type or '').upper()

        if cfg.get('system'):
            synced_records, detail = _sync_builtin(source)
        elif stype == 'CSV':
            synced_records, detail = _sync_csv(source)
        elif stype == 'API':
            synced_records, detail = _sync_api(source)
        elif stype == 'DATABASE':
            synced_records, detail = _sync_database(source)
        elif stype == 'WEB':
            raise APIException(
                "Web sources use the AI Collect endpoint — use /api/v1/ai/collect instead",
                status_code=400
            )
        else:
            raise APIException(f"Unknown source type '{source.source_type}'", status_code=400)

        source.records_count = (source.records_count or 0) + synced_records
        source.last_sync = _now()
        source.status = 'active'
        source.last_error = None
        elapsed = time.time() - start
        source.performance = min(100.0, round(
            100.0 if synced_records > 0 else max((source.performance or 0) - 5, 40), 1
        ))
        db.session.commit()

        # For built-in sources return real count from leads table
        total = source.records_count
        if cfg.get('system'):
            real_counts = _get_real_lead_counts()
            total = real_counts.get(cfg.get('system_key', ''), source.records_count)

        return jsonify({
            'status': 'success',
            'message': detail,
            'data': {
                'source_id': source_id,
                'source_name': source.name,
                'synced_records': synced_records,
                'total_records': total,
                'last_sync': source.last_sync.isoformat(),
                'duration_seconds': round(elapsed, 2),
            }
        }), 200

    except APIException:
        raise
    except Exception as e:
        err = str(e)
        logger.error(f"[sources] sync failed for '{source.name}': {err}", exc_info=True)
        source.status = 'error'
        source.last_error = err[:500]
        source.performance = max(0.0, (source.performance or 0) - 10)
        db.session.commit()
        raise APIException(f"Sync failed: {err}", status_code=500)


@sources_bp.route('/upload', methods=['POST'])
@limiter.limit("10 per hour")
@token_required
@admin_required
@handle_exceptions
def upload_csv():
    """Upload a CSV file for a CSV-type data source."""
    if 'file' not in request.files:
        raise APIException("No file provided. Send a multipart/form-data request with 'file' field.", status_code=400)

    f = request.files['file']
    if not f.filename:
        raise APIException("Empty filename", status_code=400)
    if not f.filename.lower().endswith('.csv'):
        raise APIException("Only .csv files are accepted", status_code=400)

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    safe_name = ''.join(c for c in f.filename if c.isalnum() or c in '._-')
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    f.save(file_path)

    source_id = request.form.get('source_id')
    source_name = request.form.get('source_name') or os.path.splitext(safe_name)[0]

    if source_id:
        source = DataSource.query.get(int(source_id))
        if not source:
            raise APIException(f"Source {source_id} not found", status_code=404)
    else:
        source = DataSource.query.filter_by(name=source_name).first()
        if not source:
            source = DataSource(
                name=source_name,
                source_type='CSV',
                url=file_path,
                enabled=True,
                sync_frequency='manual',
                config={'file_path': file_path},
            )
            db.session.add(source)
        else:
            cfg = source.config or {}
            cfg['file_path'] = file_path
            source.config = cfg
            source.url = file_path

    db.session.commit()

    try:
        with open(file_path, 'rb') as fp:
            rows = _parse_csv_rows(fp)
        row_count = len(rows)
    except Exception:
        row_count = 0

    return jsonify({
        'status': 'success',
        'message': f"CSV uploaded: {row_count} lead rows ready to import",
        'data': {
            'file_path': file_path,
            'row_count': row_count,
            'source': source.to_dict(),
        }
    }), 200


@sources_bp.route('/stats', methods=['GET'])
@limiter.limit("60 per minute")
@token_required
@handle_exceptions
def get_sources_stats():
    """Aggregate stats across all sources using real lead counts."""
    _ensure_builtin_sources()
    sources = DataSource.query.all()
    if not sources:
        return jsonify({
            'status': 'success',
            'stats': {
                'total_sources': 0, 'active_sources': 0,
                'total_records': 0, 'average_performance': 0,
            }
        }), 200

    real_counts = _get_real_lead_counts()
    sources_list = []
    for s in sources:
        d = s.to_dict()
        cfg = s.config or {}
        if cfg.get('system'):
            d['records'] = real_counts.get(cfg.get('system_key', ''), 0)
            env_var = cfg.get('env_var')
            d['status'] = 'active' if (not env_var or os.environ.get(env_var)) else 'inactive'
        sources_list.append(d)

    last_sync_dates = [s['last_sync'] for s in sources_list if s['last_sync']]

    return jsonify({
        'status': 'success',
        'stats': {
            'total_sources': len(sources_list),
            'active_sources': sum(1 for s in sources_list if s.get('status') == 'active'),
            'total_records': _lead_count_for_role(),
            'average_performance': round(
                sum(s['performance'] for s in sources_list) / len(sources_list), 1
            ),
            'last_sync': max(last_sync_dates) if last_sync_dates else None,
        }
    }), 200
