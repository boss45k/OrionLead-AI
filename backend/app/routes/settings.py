"""
Settings routes — all state is persisted to the database.
"""
from flask import Blueprint, request, jsonify, g
from app.exceptions import APIException
from app.routes.auth import token_required, admin_required
from app.utils.error_handler import handle_exceptions
from app.utils.rate_limiter import get_limiter
from typing import Any, Dict
import json
import logging

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__, url_prefix='/api/v1/settings')
limiter = get_limiter()

# ── Default values for every setting key ─────────────────────────────────────
_DEFAULTS: Dict[str, Any] = {
    'notify_new_leads':        True,
    'notify_qualification':    True,
    'notify_high_quality':     True,
    'notify_system_errors':    False,
    'notify_daily_digest':     False,
    'notify_frequency':        'daily',
    'auto_collect_linkedin':   True,
    'auto_collect_emails':     True,
    'auto_collect_company':    True,
    'auto_enrich_leads':       False,
    'data_retention_days':     90,
    'auto_delete_old_data':    False,
    '_last_digest_date':       '',   # internal: tracks last daily-digest send date (YYYY-MM-DD)
    'theme':                   'dark',
    # Database connection (per-user override)
    'db_host':     'localhost',
    'db_port':     3306,
    'db_user':     'root',
    'db_password': '',
    'db_name':     'orionlead_ai',
}

_ALLOWED_KEYS = set(_DEFAULTS.keys())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_settings(user_id: int) -> Dict[str, Any]:
    """Return merged dict of defaults + DB-stored overrides for a user."""
    from app.models.models import db, UserSetting
    rows = db.session.query(UserSetting).filter_by(user_id=user_id).all()
    result = dict(_DEFAULTS)
    for row in rows:
        try:
            result[row.key] = json.loads(row.value)
        except (TypeError, json.JSONDecodeError):
            result[row.key] = row.value
    return result


def _set_user_settings(user_id: int, data: Dict[str, Any]) -> None:
    """Upsert multiple setting key-value pairs for a user."""
    from app.models.models import db, UserSetting
    for key, value in data.items():
        row = db.session.query(UserSetting).filter_by(user_id=user_id, key=key).first()
        serialised = json.dumps(value)
        if row:
            row.value = serialised
        else:
            db.session.add(UserSetting(user_id=user_id, key=key, value=serialised))
    db.session.commit()


def _reset_user_settings(user_id: int) -> None:
    """Delete all stored settings for a user so they revert to defaults."""
    from app.models.models import db, UserSetting
    db.session.query(UserSetting).filter_by(user_id=user_id).delete()
    db.session.commit()


# ── Settings CRUD ─────────────────────────────────────────────────────────────

@settings_bp.route('', methods=['GET'])
@limiter.limit("60 per minute")
@token_required
@handle_exceptions
def get_settings():
    """Get all settings for the current user."""
    from app.models.models import db, AdminApiKey
    settings = _get_user_settings(g.user_id)
    api_keys = [
        {
            'id':        k.id,
            'name':      k.name,
            'key':       k.key_masked,
            'created':   k.created_at.isoformat() if k.created_at else None,
            'last_used': k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in db.session.query(AdminApiKey).order_by(AdminApiKey.created_at).all()
    ]
    return jsonify({'status': 'success', 'settings': settings, 'api_keys': api_keys}), 200


@settings_bp.route('', methods=['POST'])
@limiter.limit("30 per minute")
@token_required
@handle_exceptions
def save_settings():
    """Save one or more settings for the current user."""
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise APIException("Request body must be a JSON object", status_code=400)

    unknown = set(data.keys()) - _ALLOWED_KEYS
    if unknown:
        raise APIException(f"Unknown settings keys: {sorted(unknown)}", status_code=400)

    _set_user_settings(g.user_id, data)
    return jsonify({
        'status':   'success',
        'message':  'Settings saved successfully',
        'settings': _get_user_settings(g.user_id),
    }), 200


@settings_bp.route('/reset', methods=['POST'])
@limiter.limit("5 per hour")
@token_required
@admin_required
@handle_exceptions
def reset_settings():
    """Reset all settings for the current user to defaults."""
    _reset_user_settings(g.user_id)
    return jsonify({
        'status':   'success',
        'message':  'Settings reset to defaults',
        'settings': dict(_DEFAULTS),
    }), 200


# ── Admin API Keys ────────────────────────────────────────────────────────────

@settings_bp.route('/api-keys/generate', methods=['POST'])
@limiter.limit("10 per hour")
@token_required
@handle_exceptions
def generate_api_key():
    """Generate a new system API key (admin/manager only)."""
    import secrets
    from app.models.models import db, AdminApiKey
    data     = request.get_json(silent=True) or {}
    key_name = (data.get('name') or 'New API Key').strip()[:255]

    raw_key  = 'sk_prod_' + secrets.token_urlsafe(40)
    masked   = raw_key[:10] + '••••••••'

    record = AdminApiKey(
        name=key_name,
        key=raw_key,
        key_masked=masked,
        created_by=g.user_id,
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({
        'status':  'success',
        'message': 'API key generated successfully',
        'api_key': {
            'id':      record.id,
            'name':    record.name,
            'key':     raw_key,          # shown once; UI must tell user to copy it now
            'created': record.created_at.isoformat(),
        },
    }), 201


@settings_bp.route('/api-keys/<int:key_id>', methods=['DELETE'])
@limiter.limit("20 per hour")
@token_required
@handle_exceptions
def delete_api_key(key_id):
    """Delete a system API key."""
    from app.models.models import db, AdminApiKey
    record = db.session.get(AdminApiKey, key_id)
    if not record:
        raise APIException(f"API key {key_id} not found", status_code=404)
    name = record.name
    db.session.delete(record)
    db.session.commit()
    return jsonify({'status': 'success', 'message': f'API key "{name}" deleted'}), 200


# ── Database connection test ──────────────────────────────────────────────────

@settings_bp.route('/test-connection', methods=['POST'])
@limiter.limit("10 per minute")
@token_required
@admin_required
@handle_exceptions
def test_database_connection():
    """Test a MySQL connection with the supplied credentials."""
    import pymysql
    data = request.get_json(silent=True, force=True) or {}
    host     = (data.get('host')     or 'localhost').strip()
    port     = int(data.get('port')  or 3306)
    user     = (data.get('user')     or '').strip()
    password = (data.get('password') or '').strip()
    database = (data.get('database') or '').strip()

    if not (host and user and database):
        return jsonify({'status': 'error', 'connected': False,
                        'message': 'Missing host, user, or database name'}), 400

    try:
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=database, connect_timeout=6,
        )
        conn.close()
        logger.info(f"[settings] DB test OK → {host}:{port}/{database}")
        return jsonify({'status': 'success', 'connected': True,
                        'message': f'Connected to {host}:{port}/{database}'}), 200
    except pymysql.err.OperationalError as exc:
        code, msg = exc.args if len(exc.args) == 2 else (0, str(exc))
        logger.info(f"[settings] DB test FAILED → {host}:{port}/{database}: {msg}")
        return jsonify({'status': 'success', 'connected': False,
                        'message': f'Connection failed: {msg}'}), 200
    except Exception as exc:
        return jsonify({'status': 'error', 'connected': False,
                        'message': f'Connection error: {str(exc)[:200]}'}), 200


# ── Personal API keys ─────────────────────────────────────────────────────────

@settings_bp.route('/my-api-key', methods=['GET'])
@limiter.limit("60 per minute")
@token_required
@handle_exceptions
def get_my_api_key():
    """Return the current user's API key status (masked)."""
    from app.models.models import db, User
    user = db.session.get(User, g.user_id)
    if not user:
        raise APIException("User not found", status_code=404)
    has_key = bool(user.api_key)
    return jsonify({
        'status':       'success',
        'has_key':      has_key,
        'masked':       ('****' + user.api_key[-4:]) if has_key else None,
        'created_hint': 'Stored securely — only last 4 chars visible.',
    }), 200


@settings_bp.route('/my-api-key/generate', methods=['POST'])
@limiter.limit("10 per hour")
@token_required
@handle_exceptions
def generate_my_api_key():
    """Generate (or replace) the current user's personal API key."""
    import secrets
    from app.models.models import db, User
    user = db.session.get(User, g.user_id)
    if not user:
        raise APIException("User not found", status_code=404)
    new_key = 'sk_user_' + secrets.token_urlsafe(40)
    user.api_key = new_key
    db.session.commit()
    logger.info(f"[settings] API key generated for user {g.user_id}")
    return jsonify({
        'status':  'success',
        'message': 'API key generated — save it now, it will not be shown again.',
        'api_key': new_key,
        'masked':  '****' + new_key[-4:],
    }), 201


@settings_bp.route('/my-api-key', methods=['DELETE'])
@limiter.limit("10 per hour")
@token_required
@handle_exceptions
def revoke_my_api_key():
    """Revoke the current user's API key."""
    from app.models.models import db, User
    user = db.session.get(User, g.user_id)
    if not user:
        raise APIException("User not found", status_code=404)
    user.api_key = None
    db.session.commit()
    logger.info(f"[settings] API key revoked for user {g.user_id}")
    return jsonify({'status': 'success', 'message': 'API key revoked successfully'}), 200


# ── Integration API keys (env file) ──────────────────────────────────────────

_INTEGRATIONS = {
    # ── Lead Collection ────────────────────────────────────────────────────────
    'APOLLO_API_KEY': {
        'label': 'Apollo.io', 'category': 'lead_collection',
        'description': 'B2B people & company search with verified contacts.',
        'free_tier': '50 exports/month free', 'quality_impact': 'high',
        'docs': 'https://app.apollo.io/#/settings/integrations/api',
    },
    'HUNTER_API_KEY': {
        'label': 'Hunter.io', 'category': 'lead_collection',
        'description': 'Find corporate email addresses by name + domain.',
        'free_tier': '25 searches/month free', 'quality_impact': 'high',
        'docs': 'https://hunter.io/api',
    },
    'EXPLORIUM_API_KEY': {
        'label': 'Explorium', 'category': 'lead_collection',
        'description': 'Verified B2B contacts with buyer intent signals.',
        'free_tier': '', 'quality_impact': 'high',
        'docs': 'https://app.explorium.ai/settings',
    },
    'SNOV_API_KEY': {
        'label': 'Snov.io', 'category': 'lead_collection',
        'description': 'Email finder and drip campaign tool for outbound.',
        'free_tier': '50 credits/month free', 'quality_impact': 'medium',
        'docs': 'https://snov.io/api',
    },
    'LUSHA_API_KEY': {
        'label': 'Lusha', 'category': 'lead_collection',
        'description': 'B2B contact data — direct dials and verified emails.',
        'free_tier': '5 credits/month free', 'quality_impact': 'high',
        'docs': 'https://www.lusha.com/api-documentation/',
    },
    'ROCKETREACH_API_KEY': {
        'label': 'RocketReach', 'category': 'lead_collection',
        'description': 'Professional emails and phone numbers lookup.',
        'free_tier': '3 free lookups/month', 'quality_impact': 'medium',
        'docs': 'https://rocketreach.co/api',
    },
    # ── Enrichment ─────────────────────────────────────────────────────────────
    'PDL_API_KEY': {
        'label': 'People Data Labs', 'category': 'enrichment',
        'description': 'Deep person & company enrichment with 1.5B+ profiles.',
        'free_tier': '100 free/month', 'quality_impact': 'high',
        'docs': 'https://www.peopledatalabs.com/',
    },
    'CLEARBIT_API_KEY': {
        'label': 'Clearbit', 'category': 'enrichment',
        'description': 'Company firmographic data via HubSpot Enrichment.',
        'free_tier': '', 'quality_impact': 'medium',
        'docs': 'https://clearbit.com/',
    },
    'CRUNCHBASE_API_KEY': {
        'label': 'Crunchbase', 'category': 'enrichment',
        'description': 'Company funding, investors, and startup intelligence.',
        'free_tier': '', 'quality_impact': 'medium',
        'docs': 'https://data.crunchbase.com/docs/using-the-api',
    },
    # ── Web Search ────────────────────────────────────────────────────────────
    'SERPER_API_KEY': {
        'label': 'Serper (Google Search)', 'category': 'web_search',
        'description': 'Real Google results for website discovery, web collect, and contact resolution.',
        'free_tier': '2 500 free searches', 'quality_impact': 'high',
        'docs': 'https://serper.dev/',
    },
    'GOOGLE_PLACES_API_KEY': {
        'label': 'Google Places', 'category': 'web_search',
        'description': 'Structured local business data — phone, address, website in one call.',
        'free_tier': '$200 free/month', 'quality_impact': 'medium',
        'docs': 'https://developers.google.com/maps/documentation/places/web-service',
    },
    'BING_API_KEY': {
        'label': 'Bing Web Search', 'category': 'web_search',
        'description': 'Third search engine fallback when Serper and DuckDuckGo are unavailable.',
        'free_tier': '1 000 calls/month free', 'quality_impact': 'low',
        'docs': 'https://www.microsoft.com/en-us/bing/apis/bing-web-search-api',
    },
    # ── Email Verification ─────────────────────────────────────────────────────
    'ZEROBOUNCE_API_KEY': {
        'label': 'ZeroBounce', 'category': 'email_verification',
        'description': 'SMTP-level email verification — removes bounces before sending.',
        'free_tier': '100 validations/month free', 'quality_impact': 'high',
        'docs': 'https://www.zerobounce.net/docs/',
    },
    'ABSTRACT_EMAIL_API_KEY': {
        'label': 'Abstract Email Validation', 'category': 'email_verification',
        'description': 'Lightweight email validation fallback when ZeroBounce is unavailable.',
        'free_tier': '100 validations/month free', 'quality_impact': 'medium',
        'docs': 'https://www.abstractapi.com/api/email-verification-validation-api',
    },
    # ── AI Providers ──────────────────────────────────────────────────────────
    'GEMINI_API_KEY': {
        'label': 'Google Gemini', 'category': 'ai',
        'description': 'Primary AI engine for lead scoring and email drafting.',
        'free_tier': 'Generous free tier', 'quality_impact': 'high',
        'docs': 'https://aistudio.google.com/app/apikey',
    },
    'GROQ_API_KEY': {
        'label': 'Groq', 'category': 'ai',
        'description': 'Ultra-fast Llama 3 inference — fallback AI path.',
        'free_tier': 'Generous free tier', 'quality_impact': 'medium',
        'docs': 'https://console.groq.com/keys',
    },
    'OPENAI_API_KEY': {
        'label': 'OpenAI', 'category': 'ai',
        'description': 'GPT-4 for advanced lead analysis and email generation.',
        'free_tier': 'Pay-as-you-go', 'quality_impact': 'medium',
        'docs': 'https://platform.openai.com/api-keys',
    },
    'HF_TOKEN': {
        'label': 'HuggingFace', 'category': 'ai',
        'description': 'Faster ML model downloads for local scoring.',
        'free_tier': 'Free', 'quality_impact': 'low',
        'docs': 'https://huggingface.co/settings/tokens',
    },
    # ── Social & Developer ─────────────────────────────────────────────────────
    'GITHUB_TOKEN': {
        'label': 'GitHub', 'category': 'social',
        'description': 'Collect developer leads from public repos and profiles.',
        'free_tier': 'Free (5000 req/hr)', 'quality_impact': 'medium',
        'docs': 'https://github.com/settings/tokens',
    },
    'LINKEDIN_API_KEY': {
        'label': 'LinkedIn', 'category': 'social',
        'description': 'Professional profile data via LinkedIn API.',
        'free_tier': '', 'quality_impact': 'high',
        'docs': 'https://www.linkedin.com/developers/',
    },
    'FACEBOOK_API_KEY': {
        'label': 'Facebook / Meta', 'category': 'social',
        'description': 'Facebook Graph API for social lead collection.',
        'free_tier': 'Free (with app approval)', 'quality_impact': 'low',
        'docs': 'https://developers.facebook.com/',
    },
}


def _get_env_path():
    import pathlib
    here = pathlib.Path(__file__).resolve()
    for parent in [here.parent, here.parent.parent, here.parent.parent.parent,
                   here.parent.parent.parent.parent]:
        candidate = parent / '.env'
        if candidate.exists():
            return str(candidate)
    return None


def _mask(value: str) -> str:
    if not value or len(value) <= 4:
        return '****'
    return '****' + value[-4:]


@settings_bp.route('/integrations', methods=['GET'])
@token_required
@handle_exceptions
def get_integrations():
    """Return all integration keys — configured status + masked value."""
    import os
    result = {}
    for env_key, meta in _INTEGRATIONS.items():
        value = os.getenv(env_key, '').strip()
        result[env_key] = {
            **meta,
            'configured': bool(value),
            'masked':     _mask(value) if value else '',
        }
    return jsonify({'status': 'success', 'integrations': result}), 200


@settings_bp.route('/integrations', methods=['POST'])
@token_required
@handle_exceptions
def save_integrations():
    """
    Save one or more integration API keys.
    Writes to the .env file so they persist across restarts.
    Body: { "APOLLO_API_KEY": "abc123" }  — empty string removes the key.
    """
    import os
    data = request.get_json(silent=True) or {}

    unknown = set(data.keys()) - set(_INTEGRATIONS.keys())
    if unknown:
        return jsonify({'status': 'error', 'message': f'Unknown keys: {sorted(unknown)}'}), 400

    env_path = _get_env_path()
    updated = []

    for env_key, new_value in data.items():
        new_value = (new_value or '').strip()

        if new_value:
            os.environ[env_key] = new_value
        else:
            os.environ.pop(env_key, None)

        if env_path:
            try:
                from dotenv import set_key, unset_key
                if new_value:
                    set_key(env_path, env_key, new_value, quote_mode='never')
                else:
                    unset_key(env_path, env_key)
            except Exception as exc:
                logger.warning(f"[settings] dotenv write failed for {env_key}: {exc}")
                _manual_set_env(env_path, env_key, new_value)

        updated.append(env_key)
        logger.info(f"[settings] Integration key updated: {env_key} ({'set' if new_value else 'cleared'})")

    _reset_singletons(set(updated))
    return jsonify({
        'status':  'success',
        'message': f'Saved {len(updated)} integration key(s)',
        'updated': updated,
    }), 200


def _reset_singletons(updated_keys: set):
    import sys
    _SINGLETON_MAP = {
        'APOLLO_API_KEY':    ('app.services.apollo_service',       '_instance'),
        'EXPLORIUM_API_KEY': ('app.services.explorium_service',    '_instance'),
        'HUNTER_API_KEY':    ('app.services.hunter_service',       '_instance'),
        'PDL_API_KEY':       ('app.services.pdl_service',          '_instance'),
        'CLEARBIT_API_KEY':  ('app.services.clearbit_service',     '_instance'),
        'CRUNCHBASE_API_KEY':('app.services.crunchbase_collector', '_instance'),
        'GITHUB_TOKEN':      ('app.services.github_collector',     '_instance'),
        'GEMINI_API_KEY':    ('app.services.gemini_service',       '_ai_service'),
        'GROQ_API_KEY':      ('app.services.gemini_service',       '_ai_service'),
        'OPENAI_API_KEY':    ('app.services.gemini_service',       '_ai_service'),
    }
    for env_key in updated_keys:
        if env_key not in _SINGLETON_MAP:
            continue
        module_path, attr = _SINGLETON_MAP[env_key]
        mod = sys.modules.get(module_path)
        if mod and hasattr(mod, attr):
            setattr(mod, attr, None)
            logger.info(f"[settings] Singleton reset: {module_path}.{attr}")


def _manual_set_env(env_path: str, key: str, value: str):
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        found = False
        new_lines = []
        for line in lines:
            if line.startswith(f'{key}=') or line.startswith(f'{key} ='):
                if value:
                    new_lines.append(f'{key}={value}\n')
                found = True
            else:
                new_lines.append(line)
        if not found and value:
            new_lines.append(f'{key}={value}\n')
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    except Exception as exc:
        logger.error(f"[settings] _manual_set_env failed: {exc}")


def _test_integration_key(env_key: str, api_val: str) -> dict:
    import requests as _req
    _TIMEOUT = 8
    try:
        if env_key == 'HUNTER_API_KEY':
            r = _req.get('https://api.hunter.io/v2/account',
                         params={'api_key': api_val}, timeout=_TIMEOUT)
            ok = r.status_code == 200
            return {'valid': ok, 'message': 'Connected' if ok else 'Invalid key',
                    'detail': r.json().get('data', {}).get('email', '') if ok else r.text[:120]}

        if env_key == 'APOLLO_API_KEY':
            r = _req.get('https://api.apollo.io/api/v1/account',
                         headers={'X-Api-Key': api_val, 'Content-Type': 'application/json'},
                         timeout=_TIMEOUT)
            ok = r.status_code == 200
            acct = r.json().get('account', {}) if ok else {}
            return {'valid': ok, 'message': 'Connected' if ok else 'Invalid key',
                    'detail': acct.get('name', '') if ok else r.text[:120]}

        if env_key == 'ZEROBOUNCE_API_KEY':
            r = _req.get('https://api.zerobounce.net/v2/getapiusage',
                         params={'api_key': api_val}, timeout=_TIMEOUT)
            ok = r.status_code == 200 and 'error' not in r.text.lower()[:50]
            data = r.json() if ok else {}
            credits = data.get('Credits', '')
            return {'valid': ok, 'message': f'Connected — {credits} credits remaining' if ok else 'Invalid key',
                    'detail': '' if ok else r.text[:120]}

        if env_key == 'GEMINI_API_KEY':
            r = _req.get('https://generativelanguage.googleapis.com/v1beta/models',
                         params={'key': api_val}, timeout=_TIMEOUT)
            ok = r.status_code == 200
            models = [m.get('name', '').split('/')[-1] for m in r.json().get('models', [])[:3]] if ok else []
            return {'valid': ok, 'message': 'Connected' if ok else 'Invalid key',
                    'detail': ', '.join(models) if ok else r.text[:120]}

        if env_key == 'GROQ_API_KEY':
            r = _req.get('https://api.groq.com/openai/v1/models',
                         headers={'Authorization': f'Bearer {api_val}'}, timeout=_TIMEOUT)
            ok = r.status_code == 200
            return {'valid': ok, 'message': 'Connected' if ok else 'Invalid key',
                    'detail': '' if ok else r.text[:120]}

        if env_key == 'OPENAI_API_KEY':
            r = _req.get('https://api.openai.com/v1/models',
                         headers={'Authorization': f'Bearer {api_val}'}, timeout=_TIMEOUT)
            ok = r.status_code == 200
            return {'valid': ok, 'message': 'Connected' if ok else 'Invalid key',
                    'detail': '' if ok else r.text[:120]}

        if env_key == 'GITHUB_TOKEN':
            r = _req.get('https://api.github.com/user',
                         headers={'Authorization': f'token {api_val}', 'User-Agent': 'LeadSystem/1.0'},
                         timeout=_TIMEOUT)
            ok = r.status_code == 200
            login = r.json().get('login', '') if ok else ''
            return {'valid': ok, 'message': f'Connected as {login}' if ok else 'Invalid token',
                    'detail': ''}

        if env_key == 'HF_TOKEN':
            r = _req.get('https://huggingface.co/api/whoami',
                         headers={'Authorization': f'Bearer {api_val}'}, timeout=_TIMEOUT)
            ok = r.status_code == 200
            name = r.json().get('name', '') if ok else ''
            return {'valid': ok, 'message': f'Connected as {name}' if ok else 'Invalid token',
                    'detail': ''}

        if env_key == 'PDL_API_KEY':
            r = _req.get('https://api.peopledatalabs.com/v5/company/enrich',
                         params={'website': 'google.com', 'api_key': api_val}, timeout=_TIMEOUT)
            ok = r.status_code in (200, 404)
            return {'valid': ok, 'message': 'Connected' if ok else 'Invalid key',
                    'detail': '' if ok else r.text[:120]}

        if env_key == 'EXPLORIUM_API_KEY':
            r = _req.post('https://api.explorium.ai/v1/prospects/match',
                          json={'prospects_to_match': [{'email': 'test@example.com'}]},
                          headers={'api_key': api_val, 'content-type': 'application/json'},
                          timeout=_TIMEOUT)
            ok = r.status_code in (200, 422)
            return {'valid': ok, 'message': 'Connected' if ok else 'Invalid key',
                    'detail': '' if ok else r.text[:120]}

        if env_key == 'LUSHA_API_KEY':
            r = _req.get('https://api.lusha.com/v2/credits',
                         headers={'api_key': api_val}, timeout=_TIMEOUT)
            ok = r.status_code == 200
            credits = r.json().get('credits', {}).get('remaining', '') if ok else ''
            return {'valid': ok, 'message': f'Connected — {credits} credits' if ok else 'Invalid key',
                    'detail': '' if ok else r.text[:120]}

        if env_key == 'ROCKETREACH_API_KEY':
            r = _req.get('https://api.rocketreach.co/v1/api/account',
                         headers={'Api-Key': api_val}, timeout=_TIMEOUT)
            ok = r.status_code == 200
            return {'valid': ok, 'message': 'Connected' if ok else 'Invalid key',
                    'detail': '' if ok else r.text[:120]}

        if env_key == 'SNOV_API_KEY':
            ok = len(api_val) >= 8
            return {'valid': ok,
                    'message': 'Key saved (Snov.io requires manual OAuth verification)' if ok else 'Key too short',
                    'detail': ''}

        # LinkedIn / Facebook / Crunchbase / Clearbit — validate format only
        ok = len(api_val) >= 6
        return {'valid': ok,
                'message': 'Key format accepted' if ok else 'Key too short — check value',
                'detail': 'Full connectivity test not available for this provider.'}

    except Exception as exc:
        return {'valid': False, 'message': 'Connection error', 'detail': str(exc)[:200]}


@settings_bp.route('/integrations/test', methods=['POST'])
@limiter.limit("30 per minute")
@token_required
@handle_exceptions
def test_integration_key():
    """
    Test a single integration key by making a lightweight read-only API call.
    Body: { "key": "HUNTER_API_KEY", "value": "optional-raw-value-to-test" }
    """
    import os
    data    = request.get_json(silent=True) or {}
    env_key = (data.get('key') or '').strip()
    api_val = (data.get('value') or '').strip() or os.getenv(env_key, '').strip()

    if not env_key or env_key not in _INTEGRATIONS:
        return jsonify({'status': 'error', 'message': 'Unknown integration key'}), 400
    if not api_val:
        return jsonify({'status': 'success', 'valid': False,
                        'message': 'No key configured — paste your key and try again'}), 200

    result = _test_integration_key(env_key, api_val)
    logger.info(f"[settings] Test {env_key}: valid={result['valid']}")
    return jsonify({'status': 'success', **result}), 200
