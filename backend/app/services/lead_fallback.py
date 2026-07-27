"""
Lead Fallback Strategies
========================
When primary extraction fails to find a field, these strategies provide
progressively weaker (but still useful) guesses.

Strategies (applied in order):
  1. Email — scrape /contact, /about, /impressum sub-pages
  2. Email — Hunter.io API (confidence ≥ 80 required)
  3. Email — generate common patterns (stored as CANDIDATES ONLY, never
             placed in lead['email'] — callers decide whether to use them)
  4. Name  — infer from email local part (john.smith → John Smith)
  5. Name  — fall back to company name
  6. Company — derive from domain name

CRITICAL RULE:
  Generated / guessed emails are NEVER placed in lead['email'].
  They are stored in data_points['email_candidates'] so the caller
  can display them as suggestions, but the system never treats a
  guessed email as a verified contact method.

  Hunter confidence threshold: ≥ 80 (was 50 — too permissive).
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Common email formats to try when we know firstname + lastname + domain
EMAIL_PATTERNS = [
    '{first}.{last}@{domain}',
    '{first}{last}@{domain}',
    '{first}@{domain}',
    '{f}{last}@{domain}',
    '{first}_{last}@{domain}',
    '{last}.{first}@{domain}',
    '{last}{first}@{domain}',
    '{last}@{domain}',
]

# Generic catch-all addresses — useful for company contact when no personal found
GENERIC_PATTERNS = [
    'info@{domain}',
    'contact@{domain}',
    'hello@{domain}',
    'sales@{domain}',
    'admin@{domain}',
]

# Contact sub-pages to scrape for emails
CONTACT_SUBPAGES = [
    '/contact', '/contact-us', '/contact_us',
    '/about', '/about-us', '/about-us/',
    '/team', '/our-team', '/meet-the-team',
    '/impressum', '/kontakt',          # German
    '/mentions-legales',               # French
    '/get-in-touch', '/reach-us',
    '/support', '/help',
]

# Hunter.io domain search endpoint
HUNTER_DOMAIN_SEARCH = 'https://api.hunter.io/v2/domain-search'
HUNTER_EMAIL_FINDER  = 'https://api.hunter.io/v2/email-finder'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _domain_from_url(url: str) -> str:
    """Extract bare domain (no www, no path) from a URL string."""
    try:
        parsed = urlparse(url if '://' in url else 'https://' + url)
        netloc = parsed.netloc or parsed.path.split('/')[0]
        domain = netloc.replace('www.', '').lower().strip()
        # Strip port
        domain = domain.split(':')[0]
        return domain
    except Exception:
        return ''


def _base_domain(domain: str) -> str:
    """
    Convert subdomain to root domain for email generation.
    blog.acme.co.uk → acme.co.uk
    """
    parts = domain.split('.')
    # Handle country-code second-level domains: co.uk, com.au, org.nz, etc.
    if len(parts) >= 3 and parts[-2] in ('co', 'com', 'org', 'net', 'ac', 'gov', 'edu'):
        return '.'.join(parts[-3:])
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain


def _split_name(full_name: str) -> Tuple[str, str]:
    """Split 'John Smith' → ('john', 'smith').  Returns ('', '') on failure."""
    parts = full_name.strip().lower().split()
    parts = [re.sub(r'[^a-z]', '', p) for p in parts]
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    if len(parts) == 1:
        return parts[0], ''
    return '', ''


def _fetch_html(url: str, timeout: int = 6) -> Tuple[Optional[str], int]:
    """
    Quick, silent HTML fetch for contact sub-page scraping.
    Returns (html_or_None, status_code).
    status_code=0 on network error, -1 on timeout.
    """
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,*/*;q=0.8',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout,
                            allow_redirects=True)
        if resp.status_code == 200:
            return resp.text, 200
        return None, resp.status_code
    except requests.exceptions.Timeout:
        return None, -1
    except Exception as exc:
        logger.debug(f"[fallback] fetch failed {url}: {exc}")
        return None, 0


def _extract_emails_basic(html_text: str) -> List[str]:
    """Minimal email extraction without importing lead_extractor (avoids circular imports)."""
    pattern = re.compile(
        r'[a-zA-Z0-9][a-zA-Z0-9._%+\-]{0,62}@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,18}',
    )
    found = []
    seen = set()
    # Priority: mailto: links first
    for m in re.finditer(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html_text):
        e = m.group(1).lower()
        if e not in seen:
            seen.add(e)
            found.append(e)
    # Obfuscated
    deobf = re.sub(r'\s*[\[({]?\s*at\s*[\])}]?\s*', '@',
                   html_text, flags=re.IGNORECASE)
    deobf = re.sub(r'\s*[\[({]?\s*dot\s*[\])}]?\s*', '.', deobf, flags=re.IGNORECASE)
    for m in pattern.finditer(deobf):
        e = m.group().lower().rstrip('.,;:!?)>')
        if e not in seen and '@' in e and '.' in e.split('@')[1]:
            seen.add(e)
            found.append(e)
    return found


# ---------------------------------------------------------------------------
# Strategy 1: Scrape contact sub-pages
# ---------------------------------------------------------------------------

def scrape_contact_pages(base_url: str, *, debug: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """
    Scrape common contact / about sub-pages for email and phone numbers.

    Returns:
        (email, phone)  — either may be None
    """
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    best_email: Optional[str] = None
    best_phone: Optional[str] = None

    _GENERIC_PREFIXES = {
        'info', 'contact', 'hello', 'support', 'sales', 'admin',
        'team', 'marketing', 'office',
    }

    def _pick_best(emails: List[str]) -> Optional[str]:
        personal = [e for e in emails
                    if e.split('@')[0] not in _GENERIC_PREFIXES]
        return (personal or emails or [None])[0]

    def _extract_phone(html_text: str) -> Optional[str]:
        # tel: href is most reliable
        m = re.search(r'href=["\']tel:([+\d\s\-().]+)["\']', html_text)
        if m:
            candidate = m.group(1).strip()
            digits = re.sub(r'[^\d]', '', candidate)
            if 7 <= len(digits) <= 15:
                return candidate
        # itemprop telephone
        m = re.search(
            r'itemprop=["\']telephone["\'][^>]*(?:content=["\']([^"\']+)["\']|>([^<]+)<)',
            html_text, re.IGNORECASE,
        )
        if m:
            return (m.group(1) or m.group(2) or '').strip() or None
        return None

    consecutive_403 = 0  # bail after 2 consecutive 403s — domain is blocked

    for subpath in CONTACT_SUBPAGES:
        url = origin + subpath
        if debug:
            logger.debug(f"[fallback] scraping contact sub-page: {url}")

        html_text, status = _fetch_html(url)

        if status == 403:
            consecutive_403 += 1
            logger.debug(f"[fallback] 403 on {url} ({consecutive_403} consecutive)")
            if consecutive_403 >= 2:
                logger.debug(f"[fallback] domain {origin} is blocking scrapers — aborting sub-page scan")
                break
            continue
        else:
            consecutive_403 = 0  # reset on any non-403 response

        if not html_text:
            continue

        emails = _extract_emails_basic(html_text)
        if emails:
            candidate = _pick_best(emails)
            if candidate:
                if candidate.split('@')[0] not in _GENERIC_PREFIXES:
                    best_email = candidate
                    logger.debug(f"[fallback] personal email from {url}: {candidate}")
                    break  # personal email is best — done
                elif not best_email:
                    best_email = candidate
                    logger.debug(f"[fallback] generic email from {url}: {candidate}")

        if not best_phone:
            best_phone = _extract_phone(html_text)
            if best_phone and debug:
                logger.debug(f"[fallback] phone from {url}: {best_phone}")

    return best_email, best_phone


# ---------------------------------------------------------------------------
# Strategy 2: Hunter.io API
# ---------------------------------------------------------------------------

def hunter_find_email(
    domain: str,
    first_name: str = '',
    last_name: str = '',
    *,
    debug: bool = False,
) -> Optional[str]:
    """
    Call Hunter.io to find an email.

    Uses email-finder endpoint when name is provided, otherwise
    domain-search to get the most common email in the domain.

    Requires HUNTER_API_KEY environment variable.
    Returns email string or None.
    """
    api_key = (
        os.environ.get('HUNTER_IO_API_KEY') or os.environ.get('HUNTER_API_KEY', '')
    ).strip()
    if not api_key or api_key == 'test-key-123':
        logger.debug("[fallback] Hunter API key not configured — skipping Hunter API")
        return None

    try:
        if first_name and last_name:
            url = HUNTER_EMAIL_FINDER
            params = {
                'domain': domain,
                'first_name': first_name,
                'last_name': last_name,
                'api_key': api_key,
            }
            if debug:
                logger.debug(f"[fallback] Hunter email-finder: {domain} {first_name} {last_name}")
        else:
            url = HUNTER_DOMAIN_SEARCH
            params = {
                'domain': domain,
                'api_key': api_key,
                'limit': 3,
            }
            if debug:
                logger.debug(f"[fallback] Hunter domain-search: {domain}")

        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()

        if resp.status_code == 200:
            if 'data' in data:
                email_data = data['data']
                if isinstance(email_data, dict):
                    # email-finder: require confidence >= 80 for production quality
                    email = email_data.get('email', '')
                    confidence = email_data.get('score', 0)
                    if email and confidence >= 80:
                        logger.info(f"[fallback] Hunter found email (confidence={confidence}): {email}")
                        return email
                    elif email:
                        logger.debug(f"[fallback] Hunter email rejected (confidence={confidence} < 80): {email}")
                    # domain-search — pick first with confidence >= 80
                    emails_list = email_data.get('emails', [])
                    for entry in emails_list:
                        top = entry.get('value', '')
                        conf = entry.get('confidence', 0)
                        if top and conf >= 80:
                            logger.info(f"[fallback] Hunter domain-search email (confidence={conf}): {top}")
                            return top
        else:
            logger.debug(f"[fallback] Hunter API error {resp.status_code}: {data.get('errors')}")

    except Exception as exc:
        logger.debug(f"[fallback] Hunter API exception: {exc}")

    return None


# ---------------------------------------------------------------------------
# Strategy 3: Generate common email patterns
# ---------------------------------------------------------------------------

def generate_emails(
    domain: str,
    first_name: str = '',
    last_name: str = '',
) -> List[Dict[str, str]]:
    """
    Generate a ranked list of email candidates for a domain.

    Returns list of dicts: [{'email': '...', 'type': 'personal'|'generic'}]
    Personal patterns (with name) come first, then generic catch-alls.
    """
    base = _base_domain(domain)
    candidates: List[Dict[str, str]] = []

    if first_name and last_name:
        f, l = first_name.lower(), last_name.lower()
        fl = f[0] if f else ''
        for pattern in EMAIL_PATTERNS:
            try:
                email = pattern.format(
                    first=f, last=l, domain=base, f=fl,
                )
                if email not in [c['email'] for c in candidates]:
                    candidates.append({'email': email, 'type': 'generated_personal'})
            except KeyError:
                pass

    for pattern in GENERIC_PATTERNS:
        email = pattern.format(domain=base)
        candidates.append({'email': email, 'type': 'generated_generic'})

    return candidates


# ---------------------------------------------------------------------------
# Strategy 4: Name inference from email
# ---------------------------------------------------------------------------

def infer_name_from_email(email: str) -> Optional[str]:
    """
    Convert email local part into a plausible contact name.

    john.smith@co.com → 'John Smith'
    j.doe@co.com      → 'J Doe'
    johnsmith@co.com  → None  (ambiguous, can't split)
    info@co.com       → None  (generic)
    """
    if not email or '@' not in email:
        return None
    local = email.split('@')[0].lower()

    _GENERIC = {
        'info', 'contact', 'hello', 'support', 'sales', 'admin',
        'team', 'marketing', 'office', 'hr', 'noreply', 'no-reply',
        'mail', 'billing', 'help', 'feedback', 'enquiry', 'enquiries',
    }
    if local in _GENERIC:
        return None

    # Split on common separators
    parts = re.split(r'[._\-+]', local)
    parts = [re.sub(r'[^a-z]', '', p) for p in parts]
    parts = [p for p in parts if len(p) >= 2]

    if len(parts) >= 2:
        return ' '.join(p.capitalize() for p in parts[:2])

    return None


# ---------------------------------------------------------------------------
# Strategy 5: Company from domain
# ---------------------------------------------------------------------------

def company_from_domain(url: str) -> Optional[str]:
    """
    Derive a human-readable company name from a URL.
    https://www.acme-corp.com/ → 'Acme Corp'
    """
    domain = _domain_from_url(url)
    if not domain:
        return None
    base = domain.split('.')[0]
    # Convert hyphens / underscores to spaces, title-case
    name = base.replace('-', ' ').replace('_', ' ').title()
    return name if len(name) >= 2 else None


# ---------------------------------------------------------------------------
# Main enrichment entry point
# ---------------------------------------------------------------------------

def enrich_lead_fallbacks(
    lead: Dict[str, Any],
    *,
    scrape_contact: bool = True,
    use_hunter: bool = True,
    generate_email: bool = True,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Apply all fallback strategies to fill missing fields in a lead dict.

    Mutates and returns the lead dict.
    Adds/updates data_points with fallback metadata.

    Args:
        lead:            Lead dict (from collector or empty dict)
        scrape_contact:  Whether to scrape contact sub-pages
        use_hunter:      Whether to call Hunter.io API
        generate_email:  Whether to generate email patterns
        debug:           Emit DEBUG log lines

    Returns:
        Enriched lead dict
    """
    dp = lead.setdefault('data_points', {})
    fallbacks_applied: List[str] = dp.get('fallbacks_applied', [])

    website = (lead.get('website') or '').strip()
    current_email = (lead.get('email') or '').strip()
    current_name = (lead.get('name') or '').strip()
    current_company = (lead.get('company') or '').strip()

    domain = _domain_from_url(website) if website else ''

    _GENERIC_PREFIXES = {
        'info', 'contact', 'hello', 'support', 'sales', 'admin',
        'team', 'marketing', 'office',
    }

    def _email_is_weak() -> bool:
        """True if we should try to find a better email."""
        if not current_email:
            return True
        local = current_email.split('@')[0].lower()
        return local in _GENERIC_PREFIXES

    # ── 1. Scrape contact sub-pages ──────────────────────────────────────────
    scraped_email: Optional[str] = None
    scraped_phone: Optional[str] = None

    if scrape_contact and website and _email_is_weak():
        if debug:
            logger.debug(f"[fallback] scraping contact pages for {website}")
        scraped_email, scraped_phone = scrape_contact_pages(website, debug=debug)

        if scraped_email and (not current_email or current_email.split('@')[0].lower() in _GENERIC_PREFIXES):
            lead['email'] = scraped_email
            # Scraped emails are found on the page but not delivery-verified.
            # Mark as scraped (not generated), email_verified stays False unless
            # Hunter/PDL separately confirms it.
            dp['email_verified'] = False
            dp['email_source'] = 'contact_page_scrape'
            fallbacks_applied.append('contact_page_scrape')
            logger.info(f"[fallback] email from contact page (unverified): {scraped_email}")

        if scraped_phone and not lead.get('phone'):
            lead['phone'] = scraped_phone
            fallbacks_applied.append('contact_page_phone')
            logger.info(f"[fallback] phone from contact page: {scraped_phone}")

    # Re-read email after scrape
    current_email = (lead.get('email') or '').strip()

    # ── 2. Hunter.io API ─────────────────────────────────────────────────────
    if use_hunter and domain and _email_is_weak():
        first, last = _split_name(current_name) if current_name else ('', '')
        hunter_email = hunter_find_email(domain, first, last, debug=debug)
        if hunter_email and (not current_email or current_email.split('@')[0].lower() in _GENERIC_PREFIXES):
            lead['email'] = hunter_email
            dp['email_verified'] = True
            dp['email_source'] = 'hunter_api'
            fallbacks_applied.append('hunter_api')
            logger.info(f"[fallback] email from Hunter API: {hunter_email}")

    # Re-read email
    current_email = (lead.get('email') or '').strip()

    # ── 2.5. Explorium enrichment ─────────────────────────────────────────────
    # Explorium returns verified work emails and phones for matched prospects.
    # Skip if this lead was already sourced from Explorium (avoid redundant call).
    _already_explorium = (lead.get('source') == 'explorium'
                          or dp.get('enrichment_source') == 'explorium')
    if _email_is_weak() and not _already_explorium:
        try:
            from app.services.explorium_service import get_explorium_service
            _expl = get_explorium_service()
            if _expl.is_configured():
                _expl_result = _expl.enrich_lead(lead)
                if _expl_result:
                    _expl_email = (_expl_result.get('email') or '').strip()
                    if _expl_email:
                        lead['email'] = _expl_email
                        dp['email_verified'] = True
                        dp['email_source']   = 'explorium'
                        fallbacks_applied.append('explorium')
                        logger.info(f"[fallback] email from Explorium (verified): {_expl_email}")
                    # Merge other enriched fields that are still empty
                    for _f in ('phone', 'position', 'industry', 'linkedin_url',
                               'company_size_int', 'country', 'city'):
                        if not lead.get(_f) and _expl_result.get(_f):
                            lead[_f] = _expl_result[_f]
        except Exception as _exc:
            logger.debug(f"[fallback] Explorium step error: {_exc}")

    # Re-read email
    current_email = (lead.get('email') or '').strip()

    # ── 2.6. Snov.io email finder ─────────────────────────────────────────────
    if _email_is_weak() and domain:
        try:
            from app.services.snov_service import get_snov_service
            _snov = get_snov_service()
            if _snov.is_configured():
                first, last = _split_name(current_name) if current_name else ('', '')
                _snov_email = (
                    _snov.find_email(first, last, domain)
                    if first else
                    _snov.domain_search(domain)
                )
                if _snov_email and (not current_email or current_email.split('@')[0].lower() in _GENERIC_PREFIXES):
                    lead['email'] = _snov_email
                    dp['email_verified'] = False
                    dp['email_source'] = 'snov'
                    fallbacks_applied.append('snov')
                    logger.info(f"[fallback] email from Snov.io: {_snov_email}")
                    current_email = _snov_email
        except Exception as _exc:
            logger.debug(f"[fallback] Snov step error: {_exc}")

    # ── 2.7. Lusha contact enrichment ─────────────────────────────────────────
    _need_phone = not lead.get('phone')
    if (_email_is_weak() or _need_phone) and current_name:
        try:
            from app.services.lusha_service import get_lusha_service
            _lusha = get_lusha_service()
            if _lusha.is_configured():
                first, last = _split_name(current_name)
                _lusha_result = _lusha.enrich_person(
                    first, last,
                    company=current_company,
                    domain=domain,
                )
                if _lusha_result:
                    if _lusha_result.get('email') and _email_is_weak():
                        lead['email'] = _lusha_result['email']
                        dp['email_verified'] = _lusha_result.get('email_verified', False)
                        dp['email_source'] = 'lusha'
                        fallbacks_applied.append('lusha_email')
                        logger.info(f"[fallback] email from Lusha: {_lusha_result['email']}")
                        current_email = lead['email']
                    if _lusha_result.get('phone') and not lead.get('phone'):
                        lead['phone'] = _lusha_result['phone']
                        fallbacks_applied.append('lusha_phone')
                        logger.info(f"[fallback] phone from Lusha: {_lusha_result['phone']}")
        except Exception as _exc:
            logger.debug(f"[fallback] Lusha step error: {_exc}")

    # ── 2.8. RocketReach contact enrichment ───────────────────────────────────
    _rr_worth_calling = (
        _email_is_weak()
        or not lead.get('phone')
        or not lead.get('linkedin_url')
    )
    if _rr_worth_calling and (current_name or lead.get('linkedin_url')):
        try:
            from app.services.rocketreach_service import get_rocketreach_service
            _rr = get_rocketreach_service()
            if _rr.is_configured():
                _rr_result = _rr.lookup_person(
                    name=current_name,
                    company=current_company,
                    linkedin_url=lead.get('linkedin_url', ''),
                )
                if _rr_result:
                    if _rr_result.get('email') and _email_is_weak():
                        lead['email'] = _rr_result['email']
                        dp['email_verified'] = _rr_result.get('email_verified', False)
                        dp['email_source'] = 'rocketreach'
                        fallbacks_applied.append('rocketreach_email')
                        logger.info(f"[fallback] email from RocketReach: {_rr_result['email']}")
                        current_email = lead['email']
                    if _rr_result.get('phone') and not lead.get('phone'):
                        lead['phone'] = _rr_result['phone']
                        fallbacks_applied.append('rocketreach_phone')
                    if _rr_result.get('linkedin_url') and not lead.get('linkedin_url'):
                        lead['linkedin_url'] = _rr_result['linkedin_url']
                    if _rr_result.get('position') and not lead.get('position'):
                        lead['position'] = _rr_result['position']
                    if _rr_result.get('company') and not lead.get('company'):
                        lead['company'] = _rr_result['company']
        except Exception as _exc:
            logger.debug(f"[fallback] RocketReach step error: {_exc}")

    # ── 2.9. LinkedIn API — company enrichment ────────────────────────────────
    # Uses LINKEDIN_API_KEY as a Bearer token to pull company page data for
    # leads that have a linkedin.com/company/ URL.
    _li_url = (lead.get('linkedin_url') or '').strip()
    if _li_url and '/company/' in _li_url and not lead.get('website'):
        try:
            import re as _re
            import os as _os
            _li_key = _os.environ.get('LINKEDIN_API_KEY', '').strip()
            if _li_key:
                _slug_match = _re.search(r'linkedin\.com/company/([a-zA-Z0-9_-]+)', _li_url)
                if _slug_match:
                    _slug = _slug_match.group(1)
                    import requests as _req
                    _li_resp = _req.get(
                        'https://api.linkedin.com/v2/organizations',
                        params={'q': 'vanityName', 'vanityName': _slug},
                        headers={'Authorization': f'Bearer {_li_key}'},
                        timeout=8,
                    )
                    if _li_resp.status_code == 200:
                        _li_data = _li_resp.json()
                        _li_elements = _li_data.get('elements', [])
                        if _li_elements:
                            _org = _li_elements[0]
                            _li_website = _org.get('websiteUrl', '')
                            if _li_website and not lead.get('website'):
                                lead['website'] = _li_website
                                fallbacks_applied.append('linkedin_api_website')
                            _li_name = (_org.get('localizedName') or
                                        _org.get('name', {}).get('localized', {}).get('en_US', ''))
                            if _li_name and not lead.get('company'):
                                lead['company'] = _li_name
                            _li_industry = _org.get('industries', [{}])
                            if _li_industry and not lead.get('industry'):
                                lead['industry'] = str(_li_industry[0]).replace('_', ' ').title()
                            logger.info(f"[fallback] LinkedIn API enriched company: {_slug}")
        except Exception as _exc:
            logger.debug(f"[fallback] LinkedIn API step error: {_exc}")

    # ── 2.10. Facebook Graph API — page enrichment ────────────────────────────
    # Uses FACEBOOK_API_KEY (page/app access token) to enrich leads from Facebook.
    # Only fires for leads sourced from Facebook pages/groups.
    _fb_source = (lead.get('source') or '').startswith('facebook')
    _fb_dp_url = (lead.get('data_points') or {}).get('facebook_url', '')
    if _fb_source and _fb_dp_url and (_email_is_weak() or not lead.get('phone')):
        try:
            import re as _re
            import os as _os
            _fb_key = _os.environ.get('FACEBOOK_API_KEY', '').strip()
            if _fb_key:
                _fb_slug_match = _re.search(r'facebook\.com/([a-zA-Z0-9._-]+)', _fb_dp_url)
                if _fb_slug_match:
                    _fb_slug = _fb_slug_match.group(1)
                    import requests as _req
                    _fb_resp = _req.get(
                        f'https://graph.facebook.com/v19.0/{_fb_slug}',
                        params={
                            'fields': 'name,emails,phone,website,about',
                            'access_token': _fb_key,
                        },
                        timeout=8,
                    )
                    if _fb_resp.status_code == 200:
                        _fb_data = _fb_resp.json()
                        _fb_emails = _fb_data.get('emails', [])
                        if _fb_emails and _email_is_weak():
                            lead['email'] = _fb_emails[0]
                            dp['email_verified'] = False
                            dp['email_source'] = 'facebook_graph'
                            fallbacks_applied.append('facebook_graph_email')
                            logger.info(f"[fallback] email from Facebook Graph: {_fb_emails[0]}")
                            current_email = lead['email']
                        _fb_phone = _fb_data.get('phone', '')
                        if _fb_phone and not lead.get('phone'):
                            lead['phone'] = _fb_phone
                            fallbacks_applied.append('facebook_graph_phone')
                        _fb_website = _fb_data.get('website', '')
                        if _fb_website and not lead.get('website'):
                            lead['website'] = _fb_website
        except Exception as _exc:
            logger.debug(f"[fallback] Facebook Graph step error: {_exc}")

    # Re-read email after all enrichment steps
    current_email = (lead.get('email') or '').strip()

    # ── 3. Generate email patterns ────────────────────────────────────────────
    # CRITICAL: Generated emails are stored as CANDIDATES ONLY.
    # They are NEVER placed in lead['email'] because they are unverified guesses.
    # The quality engine / validator will reject any lead that only has a
    # generated email as its sole contact method.
    if generate_email and domain and not current_email:
        first, last = _split_name(current_name) if current_name else ('', '')
        candidates = generate_emails(domain, first, last)
        if candidates:
            dp['email_candidates'] = [c['email'] for c in candidates[:5]]
            dp['email_source'] = 'generated'
            dp['email_verified'] = False
            fallbacks_applied.append('email_candidates_generated')
            logger.info(
                f"[fallback] generated email candidates (NOT saved as email): "
                f"{dp['email_candidates'][:2]}..."
            )
            # Do NOT set lead['email'] — callers that explicitly opt in can
            # pick from dp['email_candidates'] after manual verification.

    # ── 4. Infer name from email ─────────────────────────────────────────────
    current_email = (lead.get('email') or '').strip()
    if current_email and (not current_name or current_name.lower() in ('unknown contact', 'unknown', '')):
        inferred = infer_name_from_email(current_email)
        if inferred:
            lead['name'] = inferred
            dp['name_source'] = 'inferred_from_email'
            fallbacks_applied.append('name_from_email')
            logger.info(f"[fallback] name inferred from email: {inferred}")

    # ── 5. Company from domain ────────────────────────────────────────────────
    if not current_company and website:
        derived = company_from_domain(website)
        if derived:
            lead['company'] = derived
            dp['company_source'] = 'derived_from_domain'
            fallbacks_applied.append('company_from_domain')
            logger.info(f"[fallback] company derived from domain: {derived}")

    # Step 6 (name from company) intentionally removed — using the company name
    # as a person's name creates fake contacts that pass name validation but
    # represent no real individual. Leads without a person name will score lower
    # and surface as pending/low, which is accurate.

    # ── 6. AI field completion (Groq — fast, ~1-2s) ──────────────────────────
    # Fills industry / position when they're still blank after all HTTP enrichment.
    # Uses Groq (not Gemini) to avoid the 20-30s thinking-model latency.
    # Only fires when at least one valuable context field (company, website) is known.
    _need_ai = (
        not lead.get('industry')
        or not lead.get('position')
    )
    _has_context = bool(current_company or website)
    if _need_ai and _has_context:
        try:
            from app.services.gemini_service import get_ai_service as _get_ai
            _ai = _get_ai()
            if _ai and _ai.is_available:
                _missing = []
                if not lead.get('industry'):
                    _missing.append('industry')
                if not lead.get('position'):
                    _missing.append('position')
                _ctx = (
                    f"company={current_company or '?'}, "
                    f"website={website or '?'}, "
                    f"email={lead.get('email') or '?'}, "
                    f"name={current_name or '?'}"
                )
                _prompt = (
                    f"B2B lead data. Known: {_ctx}\n"
                    f"Infer: {', '.join(_missing)}\n"
                    f'Return ONLY JSON: {{"industry":"<Technology|Finance|Healthcare|'
                    f'Retail|Manufacturing|Education|Real Estate|Legal|Consulting|'
                    f'Marketing|Hospitality|Construction|Other>",'
                    f'"position":"<likely job title or empty string>"}}'
                )
                _raw = _ai._generate(
                    _prompt,
                    system="B2B data expert. JSON only, no explanation.",
                    temperature=0.05,
                    max_tokens=60,
                    prefer_fast=True,   # route through Groq (~1-2s) not Gemini (~20s)
                )
                _parsed = _ai._parse_json(_raw or '')
                if _parsed:
                    if not lead.get('industry') and _parsed.get('industry'):
                        lead['industry'] = _parsed['industry']
                        fallbacks_applied.append('ai_industry')
                    if not lead.get('position') and _parsed.get('position'):
                        lead['position'] = _parsed['position']
                        fallbacks_applied.append('ai_position')
        except Exception as _ai_exc:
            logger.debug(f"[fallback] AI field completion skipped: {_ai_exc}")

    # ── Persist fallback log ──────────────────────────────────────────────────
    dp['fallbacks_applied'] = fallbacks_applied

    return lead


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def enrich_leads_batch(
    leads: List[Dict[str, Any]],
    *,
    scrape_contact: bool = True,
    use_hunter: bool = True,
    generate_email: bool = True,
    debug: bool = False,
    delay: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Apply fallback enrichment to a list of leads.
    Adds a small delay between network requests to avoid rate-limiting.
    """
    enriched = []
    for i, lead in enumerate(leads):
        try:
            enriched_lead = enrich_lead_fallbacks(
                lead,
                scrape_contact=scrape_contact,
                use_hunter=use_hunter,
                generate_email=generate_email,
                debug=debug,
            )
            enriched.append(enriched_lead)
        except Exception as exc:
            logger.warning(f"[fallback] error enriching lead {i}: {exc}")
            enriched.append(lead)  # Keep original on error

        if delay > 0 and i < len(leads) - 1:
            time.sleep(delay)

    return enriched
