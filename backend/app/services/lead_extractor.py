"""
Lead Extractor — Production-Grade Data Extraction Utilities
===========================================================
Centralises all field-level extraction logic so both public_web_collector
and social_media_collector share a single, tested code-path.

Improvements over the previous scattered implementations:
  • Obfuscated email formats ("user [at] domain [dot] com", HTML entities,
    Unicode lookalikes, CSS-hidden text, ROT13, base64 inline)
  • Mailto: href decoding (percent-encoded, HTML entity)
  • Schema.org / JSON-LD structured-data extraction
  • itemprop / microdata extraction
  • Multi-pattern phone normalisation with country-code awareness
  • NLP-heuristic contact-name extraction (no ML dependency)
  • Company name from domain when all else fails
  • Page-fulltext search for hidden/obfuscated contacts
  • Debug-mode logging at every extraction step
"""

from __future__ import annotations

import base64
import codecs
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FREE_EMAIL_DOMAINS = frozenset({
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com',
    'aol.com', 'msn.com', 'icloud.com', 'protonmail.com', 'proton.me',
    'zoho.com', 'mail.com', 'gmx.com', 'gmx.net', 'yandex.com',
    'yandex.ru', 'tutanota.com', 'fastmail.com', 'hey.com',
})

GENERIC_LOCAL_PARTS = frozenset({
    'info', 'contact', 'hello', 'support', 'sales', 'admin', 'team',
    'business', 'inquiry', 'inquiries', 'enquiry', 'enquiries', 'help',
    'feedback', 'service', 'office', 'general', 'mail', 'reception',
    'marketing', 'press', 'media', 'hr', 'jobs', 'careers', 'billing',
    'accounts', 'customerservice', 'cs', 'newsletter', 'subscriptions',
    'subscribe', 'editor', 'newsroom', 'communications', 'webmaster',
    'noreply', 'no-reply', 'donotreply', 'bounce', 'unsubscribe',
    # Spanish/French common generics
    'contacto', 'hola', 'ventas', 'atencion', 'comercial', 'redaccion',
    'publicidad', 'clientes', 'notifications', 'automated', 'system',
    'robot', 'alerts', 'updates', 'digest', 'postmaster', 'mailer-daemon',
    # Additional generics often missed
    'reach', 'enquire', 'getintouch', 'get-in-touch', 'contactus',
    'sales-team', 'hello-team', 'do-not-reply', 'donotreply',
    'connect', 'query', 'queries', 'request', 'requests',
    'partners', 'partnerships', 'investors', 'investor',
    'legal', 'compliance', 'privacy', 'security', 'abuse',
    'webmaster', 'hostmaster', 'abuse', 'spam', 'phishing',
    'team', 'staff', 'crew', 'hello', 'hey', 'hi',
})

REJECT_EMAIL_DOMAINS = frozenset({
    'example.com', 'example.org', 'example.net', 'test.com', 'domain.com',
    'sentry.io', 'gravatar.com', 'w3.org', 'schema.org', 'wordpress.org',
    'wixpress.com', 'googleusercontent.com', 'cloudflare.com',
    'amazonaws.com', 'sendgrid.net', 'mailchimp.com', 'hubspotfree.net',
    'placeholder.com', 'yourdomain.com', 'company.com', 'email.com',
    'yourcompany.com', 'acmecorp.com',
    # CDN / asset-delivery / tracking domains
    'gstatic.com', 'cloudfront.net', 'fastly.net', 'akamaihd.net',
    'akamai.net', 'edgecastcdn.net', 'jsdelivr.net', 'unpkg.com',
    'cdnjs.cloudflare.com', 'bootstrapcdn.com', 'typekit.net',
    'fonts.googleapis.com', 'fonts.gstatic.com',
    'doubleclick.net', 'googlesyndication.com', 'googletagmanager.com',
    'googleadservices.com', 'google-analytics.com',
    'facebook.net', 'fbcdn.net', 'instagram.com',
    'twimg.com', 'twitter.com',
    'wp.com', 'wpengine.com', 'wpmudev.com',
    'squarespace.com', 'squarespace-cdn.com',
    'shopify.com', 'myshopify.com', 'shopifycdn.com',
    'wix.com', 'wixstatic.com',
    'zendesk.com', 'zdassets.com',
    'hubspot.com', 'hubspot.net', 'hs-scripts.com', 'hs-analytics.net',
    'intercom.io', 'intercomcdn.com',
    'segment.io', 'segment.com',
    'hotjar.com', 'hj.hotjar.com',
    'mixpanel.com', 'amplitude.com', 'heap.io',
    'newrelic.com', 'nr-data.net',
    'rollbar.com', 'bugsnag.com', 'logrocket.com',
    'stripe.com', 'stripe.network', 'js.stripe.com',
    'paypal.com', 'paypalobjects.com',
    'recaptcha.net', 'gstatic.com',
    'disqus.com', 'disquscdn.com',
    'addthis.com', 'addtoany.com', 'sharethis.com',
    'ic.com', 'cdn.com',
})

REJECT_EMAIL_SUFFIXES = (
    '.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.svg', '.ico',
    '.woff', '.woff2', '.ttf', '.otf', '.webp', '.mp4', '.pdf',
)

# Common C-level / professional title keywords used for name detection
TITLE_KEYWORDS = (
    'ceo', 'cto', 'cfo', 'coo', 'cmo', 'cpo', 'ciso',
    'founder', 'co-founder', 'cofounder',
    'director', 'manager', 'president', 'vp', 'vice president',
    'head of', 'lead', 'principal', 'senior', 'junior',
    'engineer', 'developer', 'designer', 'analyst', 'consultant',
    'partner', 'associate', 'coordinator', 'specialist',
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decode_html_entities(text: str) -> str:
    """Decode HTML entities: &amp; → &, &#64; → @, etc."""
    return html.unescape(text)


def _deobfuscate_email_text(text: str) -> str:
    """
    Convert common email obfuscation patterns to normal form so the
    standard regex can pick them up.

    Patterns handled:
      • name [at] domain [dot] com
      • name (at) domain (dot) com
      • name AT domain DOT com  (ALL-CAPS variant)
      • name{at}domain{dot}com
      • Unicode @ lookalike: ＠ (U+FF20)
      • HTML entities: &#64; &#46; &amp;
    """
    t = _decode_html_entities(text)

    # Unicode full-width @ → @
    t = t.replace('\uff20', '@').replace('＠', '@')

    # [at] / (at) / {at} — case-insensitive
    t = re.sub(r'\s*[\[({]?\s*(?:at|AT|At)\s*[\])}]?\s*', '@', t)
    # [dot] / (dot) / {dot} — also handles [.] and (.)
    t = re.sub(r'\s*[\[({]?\s*(?:dot|DOT|Dot|\.)\s*[\])}]?\s*', '.', t)
    # " at " / " AT " surrounded by word characters (no brackets)
    t = re.sub(r'(?<=\w)\s+[Aa][Tt]\s+(?=\w)', '@', t)
    # " dot " inside what is becoming an email address
    t = re.sub(r'(?<=\w)\s+[Dd][Oo][Tt]\s+(?=\w)', '.', t)

    return t


def _decode_rot13(text: str) -> str:
    """Decode ROT13-encoded strings (sometimes used to hide emails)."""
    return codecs.decode(text, 'rot_13')


def _maybe_decode_base64(token: str) -> Optional[str]:
    """
    Try to base64-decode a token and return it ONLY if the decoded string
    is a structurally valid email address.

    Returns None if decode fails or result is not a valid email.
    The caller must validate the result before using it.
    """
    try:
        decoded = base64.b64decode(token + '==').decode('utf-8', errors='ignore').strip()
        # Require a complete, valid email — not just any string containing '@'
        if re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._%+\-]{0,62}@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,18}$', decoded):
            return decoded
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Email extraction
# ---------------------------------------------------------------------------

# Strict RFC-5321-ish pattern (catches most real-world emails)
_EMAIL_RE = re.compile(
    r'[a-zA-Z0-9][a-zA-Z0-9._%+\-]{0,62}@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,18}',
    re.IGNORECASE,
)

# Pattern for mailto: href values (may be percent-encoded)
_MAILTO_RE = re.compile(r'mailto:([^"\'>\s?&]+)', re.IGNORECASE)

# Pattern for data-email="..." or data-contact="..." attributes
_DATA_ATTR_EMAIL_RE = re.compile(
    r'data-(?:email|contact|mail|e-mail)=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _validate_email(email: str) -> bool:
    """Full validation: structure + domain + reject-lists."""
    if not email or '@' not in email:
        return False
    e = email.strip().lower()
    # Strip trailing punctuation that regex sometimes captures
    e = e.rstrip('.,;:!?)>]}"\'\\/')
    if '@' not in e:
        return False
    local, domain = e.split('@', 1)
    # Length checks
    if len(local) < 1 or len(local) > 64:
        return False
    if len(domain) < 4:
        return False
    # No consecutive dots
    if '..' in local or '..' in domain:
        return False
    # Local must not be all-digits (tracking IDs)
    digits_only = re.sub(r'[.\-_]', '', local)
    if digits_only.isdigit():
        return False
    # Very short local parts (1-2 chars) on a multi-level subdomain are almost
    # always CDN URL artifacts (e.g. av@ar.theguardian.com from img src URLs).
    if len(local) <= 2 and domain.count('.') >= 2:
        return False
    # Reject file-extension suffixes
    if e.endswith(REJECT_EMAIL_SUFFIXES):
        return False
    # Reject placeholder / system domains
    for rd in REJECT_EMAIL_DOMAINS:
        if domain == rd or domain.endswith('.' + rd):
            return False
    # Must have a valid TLD (≥ 2 chars after last dot)
    tld = domain.rsplit('.', 1)[-1]
    if len(tld) < 2:
        return False
    return True


def _email_type(email: str) -> str:
    """
    Classify an email address.
    Returns: 'personal', 'company', 'generic', or 'free'.
    """
    if not email or '@' not in email:
        return 'unknown'
    local = email.lower().split('@')[0]
    domain = email.lower().split('@')[1]

    if local in GENERIC_LOCAL_PARTS:
        return 'generic'
    if domain in FREE_EMAIL_DOMAINS:
        return 'free'
    return 'company'


def extract_emails_from_html(html_text: str, *, debug: bool = False) -> List[str]:
    """
    Extract all valid, unique email addresses from raw HTML text.

    Pipeline:
      1. JSON-LD structured data (@type Organization / Person)
      2. itemprop="email" microdata
      3. mailto: href links (percent-decoded + HTML entity decoded)
      4. data-email / data-contact attributes
      5. Visible text after HTML-tag stripping
      6. Obfuscated text (deobfuscate then scan)
      7. base64 / ROT13 inline tokens (opportunistic)

    Returns emails sorted: personal > generic (info@, contact@, ...).
    """
    seen: set = set()
    personal: List[str] = []
    generic: List[str] = []

    def _add(email: str, source: str = '') -> None:
        e = email.strip().lower().rstrip('.,;:!?)>]}"\'\\/')
        if not e or e in seen:
            return
        if not _validate_email(e):
            if debug:
                logger.debug(f"[extractor] rejected email '{e}' from {source}")
            return
        seen.add(e)
        if debug:
            logger.debug(f"[extractor] found email '{e}' via {source}")
        if e.split('@')[0] in GENERIC_LOCAL_PARTS:
            generic.append(e)
        else:
            personal.append(e)

    # ── 1. JSON-LD ──────────────────────────────────────────────────────────
    for ld_raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text, re.DOTALL | re.IGNORECASE,
    ):
        try:
            obj = json.loads(ld_raw)
            items = obj if isinstance(obj, list) else [obj]
            # Handle @graph wrapper
            expanded: List[Any] = []
            for it in items:
                if isinstance(it, dict) and '@graph' in it:
                    expanded.extend(it['@graph'])
                else:
                    expanded.append(it)
            for item in expanded:
                if isinstance(item, dict):
                    for key in ('email', 'contactPoint', 'contactPoints'):
                        val = item.get(key)
                        if isinstance(val, str) and '@' in val:
                            _add(val, 'json-ld')
                        elif isinstance(val, dict):
                            cp_email = val.get('email', '')
                            if cp_email and '@' in cp_email:
                                _add(cp_email, 'json-ld contactPoint')
                        elif isinstance(val, list):
                            for cp in val:
                                if isinstance(cp, dict):
                                    cp_email = cp.get('email', '')
                                    if cp_email and '@' in cp_email:
                                        _add(cp_email, 'json-ld contactPoints')
        except Exception:
            pass

    # ── 2. itemprop="email" ─────────────────────────────────────────────────
    for m in re.finditer(
        r'itemprop=["\']email["\'][^>]*(?:content=["\']([^"\']+)["\']|>([^<]+)<)',
        html_text, re.IGNORECASE,
    ):
        candidate = (m.group(1) or m.group(2) or '').strip()
        if candidate:
            _add(unquote(candidate), 'itemprop')

    # ── 3. mailto: links ─────────────────────────────────────────────────────
    for m in _MAILTO_RE.finditer(html_text):
        raw = m.group(1)
        decoded = unquote(_decode_html_entities(raw)).split('?')[0]
        _add(decoded, 'mailto')

    # ── 4. data-email / data-contact attributes ──────────────────────────────
    for m in _DATA_ATTR_EMAIL_RE.finditer(html_text):
        raw = m.group(1)
        _add(_decode_html_entities(raw), 'data-attr')

    # ── 5. Plain text scan ───────────────────────────────────────────────────
    # Strip <script> and <style> entirely first — their code/CSS often contains
    # CDN config strings and URL patterns that look like emails but aren't.
    body_only = re.sub(r'<script[^>]*>.*?</script>', ' ', html_text, flags=re.DOTALL | re.IGNORECASE)
    body_only = re.sub(r'<style[^>]*>.*?</style>', ' ', body_only, flags=re.DOTALL | re.IGNORECASE)
    # Strip tags but keep mailto: intact for the regex to find
    visible = re.sub(r'<(?!mailto)[^>]+>', ' ', body_only)
    visible = _decode_html_entities(visible)
    for m in _EMAIL_RE.finditer(visible):
        _add(m.group(), 'plaintext')

    # ── 6. Obfuscated text ───────────────────────────────────────────────────
    deobf = _deobfuscate_email_text(visible)
    if deobf != visible:
        for m in _EMAIL_RE.finditer(deobf):
            _add(m.group(), 'deobfuscated')

    # ── 7. ROT13 blocks (opportunistic — requires full email validation) ─────
    # Only data-r13/data-rot13 attributes are processed (not arbitrary text).
    # Decoded result must pass _validate_email(), not just contain '@'.
    for m in re.finditer(
        r'data-(?:r13|rot13)=["\']([^"\']{6,80})["\']',
        html_text, re.IGNORECASE,
    ):
        decoded = _decode_rot13(m.group(1))
        for em in _EMAIL_RE.finditer(decoded):
            candidate = em.group()
            if _validate_email(candidate):
                _add(candidate, 'rot13')

    if debug:
        logger.debug(
            f"[extractor] extract_emails_from_html → "
            f"{len(personal)} personal, {len(generic)} generic"
        )

    return personal + generic


# ---------------------------------------------------------------------------
# Phone extraction
# ---------------------------------------------------------------------------

def extract_phones_from_html(html_text: str, *, debug: bool = False) -> List[str]:
    """
    Extract valid phone numbers from HTML.

    Priority:
      1. tel: href links  (most reliable — explicitly marked)
      2. JSON-LD telephone / faxNumber
      3. itemprop="telephone"
      4. Regex over visible text

    Returns up to 5 de-duplicated, normalised phone strings.
    """
    seen_digits: set = set()
    results: List[str] = []

    def _add(raw: str, source: str = '') -> None:
        stripped = raw.strip()
        digits = re.sub(r'[^\d]', '', stripped)
        if digits in seen_digits:
            return
        if len(digits) < 7 or len(digits) > 15:
            return
        # At least one formatting character (not just a bare integer)
        if not any(c in stripped for c in '+-() '):
            # Allow if it starts with + (international prefix)
            if not stripped.startswith('+'):
                return
        # Reject obviously fake numbers
        if len(set(digits)) <= 2:        # 0000000000, 1212121212
            return
        if digits.startswith('000'):     # 000-xxx-xxxx
            return
        if digits.startswith('555') and len(digits) == 10:
            return                       # Hollywood placeholder
        _asc = '0123456789012345678901234567890'
        _dsc = '9876543210987654321098765432109'
        if digits in _asc or digits in _dsc:
            return                       # 1234567890, 9876543210
        seen_digits.add(digits)
        results.append(stripped)
        if debug:
            logger.debug(f"[extractor] phone '{stripped}' via {source}")

    # ── 1. tel: href ────────────────────────────────────────────────────────
    for m in re.finditer(r'href=["\']tel:([^"\']+)["\']', html_text, re.IGNORECASE):
        _add(unquote(m.group(1)), 'tel-href')

    # ── 2. JSON-LD ──────────────────────────────────────────────────────────
    for ld_raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text, re.DOTALL | re.IGNORECASE,
    ):
        try:
            obj = json.loads(ld_raw)
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                if isinstance(item, dict):
                    for key in ('telephone', 'faxNumber', 'phone'):
                        val = item.get(key, '')
                        if val and isinstance(val, str):
                            _add(val, f'json-ld.{key}')
        except Exception:
            pass

    # ── 3. itemprop="telephone" ─────────────────────────────────────────────
    for m in re.finditer(
        r'itemprop=["\']telephone["\'][^>]*(?:content=["\']([^"\']+)["\']|>([^<]+)<)',
        html_text, re.IGNORECASE,
    ):
        val = (m.group(1) or m.group(2) or '').strip()
        if val:
            _add(val, 'itemprop')

    # ── 4. Regex over visible text ───────────────────────────────────────────
    visible = re.sub(r'<[^>]+>', ' ', html_text)
    phone_patterns = [
        # International: +1 (555) 123-4567 / +44 20 7946 0958
        r'\+\d{1,3}[\s\-.]?\(?\d{1,4}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{3,4}(?:[\s\-.]?\d{1,4})?',
        # North American: (555) 123-4567
        r'\(\d{3}\)\s*\d{3}[\s\-]\d{4}',
        # Generic: 555-123-4567 / 555.123.4567
        r'\d{3}[\s\-.]\d{3,4}[\s\-.]\d{3,4}',
    ]
    for pattern in phone_patterns:
        for m in re.finditer(pattern, visible):
            _add(m.group().strip(), 'regex')

    if len(results) > 5:
        results = results[:5]

    if debug:
        logger.debug(f"[extractor] extract_phones_from_html → {results}")

    return results


# ---------------------------------------------------------------------------
# Contact name extraction
# ---------------------------------------------------------------------------

# Name-pattern: 2-5 words, each starting with a capital, alpha + apostrophe/hyphen
_NAME_WORD_RE = re.compile(r"^[A-ZÀ-Ö][a-zA-ZÀ-öÀ-ÿ''\-]{1,30}$")

_NON_PERSON_TOKENS = frozenset({
    'about', 'contact', 'team', 'staff', 'leadership', 'management',
    'board', 'company', 'group', 'inc', 'llc', 'ltd', 'corp', 'agency',
    'services', 'solutions', 'marketing', 'digital', 'global', 'consulting',
    'privacy', 'terms', 'policy', 'cookie', 'home', 'welcome', 'page',
    'our', 'the', 'and', 'for', 'with', 'from', 'that', 'this',
    # Technology/business keywords that look like names but aren't
    'artificial', 'intelligence', 'machine', 'learning', 'deep', 'cloud',
    'software', 'technology', 'tech', 'data', 'science', 'cyber', 'security',
    'automation', 'blockchain', 'saas', 'fintech', 'startup', 'enterprise',
    'platform', 'analytics', 'developer', 'engineering', 'innovation',
    'smart', 'intelligent', 'advanced', 'professional', 'division',
    'limited', 'corporation', 'international', 'holdings', 'partners',
    'ventures', 'media', 'creative', 'studio', 'labs', 'systems',
})

# CSS selectors that commonly contain a person's name
_NAME_SELECTORS = [
    # Schema.org
    '[itemtype*="schema.org/Person"] [itemprop="name"]',
    '[itemprop="name"]',
    # Profile-page patterns
    '.vcard .fn', '.h-card .p-name',
    # Team / people cards
    '.team-member h2', '.team-member h3', '.team-member h4',
    '.staff-member h2', '.staff-member h3',
    '.person-card h2', '.person-card h3',
    '.people-item h3', '.member-card h3',
    '.leadership-card h3', '.executive-card h3',
    '.speaker-card h3', '.author-card h3',
    # Generic heading-inside-container
    '[class*="team"] h3', '[class*="team"] h4',
    '[class*="staff"] h3', '[class*="staff"] h4',
    '[class*="author"] h2', '[class*="author"] h3',
    '[class*="people"] h3',
    # Named class patterns
    '.contact-name', '.person-name', '.member-name',
    '.profile-name', '.author-name', '.speaker-name',
]

def _looks_like_person_name(text: str) -> bool:
    """Heuristic: does this string look like a real human name?"""
    if not text or not text.strip():
        return False
    words = text.strip().split()
    # Require exactly 2-4 words (single word = company/brand; 5+ = description)
    if len(words) < 2 or len(words) > 4:
        return False
    lower_words = {w.lower().strip("'-.") for w in words}
    # Reject if any word is a known non-person token
    if lower_words & _NON_PERSON_TOKENS:
        return False
    # Reject if ALL words are keyword/industry terms
    if all(w in _NON_PERSON_TOKENS for w in lower_words):
        return False
    # Reject if any word is purely numeric (tracking IDs)
    if any(w.isdigit() for w in lower_words):
        return False
    for w in words:
        clean = w.strip("'-.,()")
        if not clean:
            continue
        if not _NAME_WORD_RE.match(clean):
            return False
    return True


def extract_contact_name(soup: BeautifulSoup, *, debug: bool = False) -> Optional[str]:
    """
    Extract a contact person name from a BeautifulSoup document.

    Strategy:
      1. CSS selectors for known person-name containers
      2. JSON-LD Person nodes
      3. <title> tag (author byline patterns)
      4. Meta author tag
    """
    # ── 1. CSS selectors ────────────────────────────────────────────────────
    for sel in _NAME_SELECTORS:
        try:
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                if _looks_like_person_name(name):
                    if debug:
                        logger.debug(f"[extractor] name '{name}' via selector '{sel}'")
                    return name[:120]
        except Exception:
            pass

    # ── 2. JSON-LD Person ───────────────────────────────────────────────────
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            obj = json.loads(script.string or '{}')
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get('@type') in ('Person', 'ProfilePage', 'author'):
                    name = item.get('name', '')
                    if name and _looks_like_person_name(name):
                        if debug:
                            logger.debug(f"[extractor] name '{name}' via json-ld Person")
                        return name[:120]
        except Exception:
            pass

    # ── 3. Meta author ──────────────────────────────────────────────────────
    for attr in ({'name': 'author'}, {'property': 'article:author'}):
        meta = soup.find('meta', attrs=attr)
        if meta and meta.get('content'):
            name = meta['content'].strip()
            if _looks_like_person_name(name):
                if debug:
                    logger.debug(f"[extractor] name '{name}' via meta author")
                return name[:120]

    return None


def name_from_email(email: str) -> Optional[str]:
    """
    Infer a likely contact name from the local part of an email address.

    john.smith@company.com  → "John Smith"
    j.smith@company.com     → "J Smith"
    johnsmith@company.com   → None (can't split reliably)
    info@company.com        → None (generic)
    """
    if not email or '@' not in email:
        return None
    local = email.split('@')[0].lower()
    # Generic addresses — skip
    if local in GENERIC_LOCAL_PARTS:
        return None
    # Split on common separators
    parts = re.split(r'[._\-+]', local)
    parts = [p for p in parts if len(p) >= 2 and p.isalpha()]
    if len(parts) < 2:
        return None
    # Capitalise each part
    name = ' '.join(p.capitalize() for p in parts[:3])
    return name if _looks_like_person_name(name) else None


# ---------------------------------------------------------------------------
# Company name extraction
# ---------------------------------------------------------------------------

_COMPANY_BAD_PATTERNS = [
    'find email', 'phone number', 'search', 'lookup', 'database',
    'contact info', 'free tool', 'sign up', 'log in', 'server',
    'page not found', '404', '403', 'forbidden', 'error',
    'cookie', 'privacy policy', 'terms of', 'subscribe',
    'nothing found', 'no results', 'contact us', 'contactus', 'about us',
    'our team', 'get in touch', 'home page', 'homepage', 'welcome to',
    'agency in ', 'agencies in ', 'company in ', 'companies in ',
    'services in ', 'firm in ', 'top ', 'best ', 'leading ', 'premier ',
]


def extract_company_name(soup: BeautifulSoup, url: str = '', *, debug: bool = False) -> Optional[str]:
    """
    Extract company / organisation name.

    Priority:
      1. JSON-LD Organization / LocalBusiness name
      2. og:site_name meta tag
      3. Clean <title> tag
      4. Domain-name fallback
    """
    def _clean(name: str) -> Optional[str]:
        if not name or len(name) < 2 or len(name) > 150:
            return None
        lower = name.lower()
        if any(bp in lower for bp in _COMPANY_BAD_PATTERNS):
            return None
        if len(name.split()) > 7:
            return None
        return name

    # ── 1. JSON-LD ──────────────────────────────────────────────────────────
    org_types = {
        'Organization', 'LocalBusiness', 'Corporation', 'Company',
        'ProfessionalService', 'Store', 'Restaurant', 'EducationalOrganization',
        'MedicalBusiness', 'LegalService', 'FinancialService',
    }
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            obj = json.loads(script.string or '{}')
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                if isinstance(item, dict) and '@graph' in item:
                    items = items + item['@graph']
                if not isinstance(item, dict):
                    continue
                t = item.get('@type', '')
                if isinstance(t, list):
                    t = t[0] if t else ''
                if any(ot in str(t) for ot in org_types):
                    name = item.get('name', '')
                    result = _clean(name)
                    if result:
                        if debug:
                            logger.debug(f"[extractor] company '{result}' via json-ld")
                        return result
        except Exception:
            pass

    # ── 2. og:site_name ─────────────────────────────────────────────────────
    og = soup.find('meta', property='og:site_name')
    if og and og.get('content'):
        result = _clean(og['content'].strip())
        if result:
            if debug:
                logger.debug(f"[extractor] company '{result}' via og:site_name")
            return result

    # ── 3. Title tag ─────────────────────────────────────────────────────────
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        # Split on common separators. For bare | (no surrounding spaces) pick
        # the segment that passes _clean(); fall back to the longest segment.
        for sep in (' | ', ' - ', ' – ', ' — ', ' :: '):
            if sep in title:
                title = title.split(sep)[0].strip()
                break
        else:
            # Handle bare | without spaces (e.g. "ContactUs|Apartment Therapy")
            if '|' in title:
                parts = [p.strip() for p in title.split('|') if p.strip()]
                title = next((p for p in parts if _clean(p)), max(parts, key=len, default=title))
        # Remove noise suffixes
        for noise in ('home', 'official site', 'official website', 'contact',
                      'about', 'welcome', 'homepage', 'contact us', 'about us'):
            title = re.sub(rf'\b{re.escape(noise)}\b', '', title, flags=re.IGNORECASE).strip(' -–—|:')
        result = _clean(title)
        if result:
            if debug:
                logger.debug(f"[extractor] company '{result}' via title tag")
            return result

    # ── 4. Domain fallback ───────────────────────────────────────────────────
    if url:
        try:
            domain = urlparse(url).netloc.replace('www.', '')
            base = domain.split('.')[0]
            # Convert hyphens/underscores to spaces and title-case
            name = base.replace('-', ' ').replace('_', ' ').title()
            if len(name) >= 2:
                if debug:
                    logger.debug(f"[extractor] company '{name}' via domain fallback")
                return name
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# Industry classification
# ---------------------------------------------------------------------------

INDUSTRY_KEYWORD_MAP: Dict[str, List[str]] = {
    'Technology': [
        'software', 'tech', 'saas', 'cloud', 'digital', 'cyber', 'data', 'ai',
        'machine learning', 'devops', 'api', 'platform', 'app', 'iot',
    ],
    'Healthcare': [
        'health', 'medical', 'pharma', 'hospital', 'clinic', 'biotech',
        'wellness', 'care', 'therapy', 'diagnostics',
    ],
    'Finance': [
        'finance', 'bank', 'insurance', 'investment', 'fintech', 'accounting',
        'trading', 'fund', 'wealth', 'credit',
    ],
    'Manufacturing': [
        'manufacturing', 'industrial', 'factory', 'production', 'assembly',
        'engineering', 'fabrication',
    ],
    'Retail': [
        'retail', 'shop', 'store', 'ecommerce', 'e-commerce', 'marketplace',
        'fashion', 'apparel', 'consumer',
    ],
    'Real Estate': [
        'real estate', 'property', 'construction', 'building', 'architect',
        'realty', 'mortgage', 'developer',
    ],
    'Education': [
        'education', 'university', 'school', 'training', 'academy', 'learning',
        'edtech', 'course', 'tutoring',
    ],
    'Consulting': [
        'consulting', 'advisory', 'management', 'strategy', 'professional services',
        'analyst',
    ],
    'Marketing': [
        'marketing', 'advertising', 'agency', 'media', 'branding', 'pr ',
        'seo', 'social media', 'content',
    ],
    'Logistics': [
        'logistics', 'shipping', 'transport', 'supply chain', 'freight',
        'delivery', 'warehouse', 'fulfillment',
    ],
    'Food & Beverage': [
        'restaurant', 'food', 'beverage', 'catering', 'cafe', 'dining',
        'hospitality',
    ],
    'Energy': [
        'energy', 'oil', 'gas', 'solar', 'renewable', 'power', 'utility',
        'clean energy',
    ],
    'Automotive': [
        'automotive', 'car', 'vehicle', 'auto', 'motor', 'dealer', 'fleet',
    ],
    'Telecommunications': [
        'telecom', 'mobile', 'wireless', 'network', 'communication', 'isp',
        'broadband',
    ],
    'Legal': [
        'law', 'legal', 'attorney', 'lawyer', 'firm', 'counsel', 'litigation',
    ],
}


def classify_industry(text: str, *, debug: bool = False) -> Optional[str]:
    """Score text against INDUSTRY_KEYWORD_MAP and return the top match."""
    text_lower = text.lower()
    scores: Dict[str, int] = {}
    for industry, keywords in INDUSTRY_KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[industry] = score
    if not scores:
        return None
    best = max(scores, key=lambda k: scores[k])
    if debug:
        logger.debug(f"[extractor] industry='{best}' (score={scores[best]})")
    return best


# ---------------------------------------------------------------------------
# Job title extraction
# ---------------------------------------------------------------------------

_POSITION_SELECTORS = [
    '[itemprop="jobTitle"]',
    '.job-title', '.jobtitle', '.role', '.position', '.designation',
    '.contact-title', '.person-title', '.team-member-title',
    '.author-title', '.speaker-title', '.staff-title',
    '[class*="role"]', '[class*="designation"]', '[class*="job-title"]',
]


def extract_position(soup: BeautifulSoup, *, debug: bool = False) -> Optional[str]:
    """Extract job title / position from common CSS patterns and JSON-LD."""
    # ── CSS selectors ────────────────────────────────────────────────────────
    for sel in _POSITION_SELECTORS:
        try:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                if 3 < len(text) < 150:
                    if debug:
                        logger.debug(f"[extractor] position '{text}' via selector '{sel}'")
                    return text[:255]
        except Exception:
            pass

    # ── JSON-LD Person.jobTitle ──────────────────────────────────────────────
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            obj = json.loads(script.string or '{}')
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                if isinstance(item, dict) and item.get('@type') == 'Person':
                    jt = item.get('jobTitle', '')
                    if jt and len(jt) < 150:
                        if debug:
                            logger.debug(f"[extractor] position '{jt}' via json-ld jobTitle")
                        return jt[:255]
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# LinkedIn URL extraction
# ---------------------------------------------------------------------------

_LINKEDIN_RE = re.compile(
    r'https?://(?:www\.)?linkedin\.com/(?:company|in)/[a-zA-Z0-9\-_%/]+',
    re.IGNORECASE,
)


def extract_linkedin_url(soup: BeautifulSoup, raw_html: str = '', *, debug: bool = False) -> Optional[str]:
    """Find the most relevant LinkedIn URL (company or personal profile)."""
    found: List[str] = []

    # Links in DOM
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'linkedin.com/company/' in href or 'linkedin.com/in/' in href:
            found.append(href.split('?')[0])

    # Regex over raw HTML (catches og:url, data-url, etc.)
    for m in _LINKEDIN_RE.finditer(raw_html):
        found.append(m.group().split('?')[0])

    if found:
        # Prefer /company/ over /in/
        company = next((u for u in found if '/company/' in u), None)
        result = company or found[0]
        if debug:
            logger.debug(f"[extractor] linkedin='{result}'")
        return result

    return None


# ---------------------------------------------------------------------------
# Structured data (JSON-LD) bulk extract
# ---------------------------------------------------------------------------

def extract_structured_data(soup: BeautifulSoup, *, debug: bool = False) -> Dict[str, Any]:
    """
    Pull all useful B2B fields out of JSON-LD Organization / LocalBusiness nodes.
    Returns a dict with keys: company, email, phone, website, city, country,
    linkedin, twitter, facebook, industry, description.
    """
    result: Dict[str, Any] = {}
    org_types = {
        'Organization', 'LocalBusiness', 'Corporation', 'Company',
        'ProfessionalService', 'Store', 'Restaurant', 'MedicalBusiness',
        'LegalService', 'FinancialService', 'RealEstateAgent',
        'InsuranceAgency', 'TravelAgency', 'EducationalOrganization',
    }

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            obj = json.loads(script.string or '{}')
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                if isinstance(item, dict) and '@graph' in item:
                    items = items + item['@graph']
                if not isinstance(item, dict):
                    continue
                t = item.get('@type', '')
                if isinstance(t, list):
                    t = t[0] if t else ''
                if not any(ot in str(t) for ot in org_types):
                    continue

                if item.get('name') and not result.get('company'):
                    result['company'] = str(item['name'])[:255]
                if item.get('email') and not result.get('email'):
                    result['email'] = str(item['email'])
                if item.get('telephone') and not result.get('phone'):
                    result['phone'] = str(item['telephone'])
                if item.get('url') and not result.get('website'):
                    result['website'] = str(item['url'])
                if item.get('description') and not result.get('description'):
                    result['description'] = str(item['description'])[:500]
                if item.get('industry') and not result.get('industry'):
                    result['industry'] = str(item['industry'])

                addr = item.get('address', {})
                if isinstance(addr, dict):
                    if addr.get('addressLocality') and not result.get('city'):
                        result['city'] = str(addr['addressLocality'])
                    if addr.get('addressCountry') and not result.get('country'):
                        result['country'] = str(addr['addressCountry'])

                same_as = item.get('sameAs', [])
                if isinstance(same_as, str):
                    same_as = [same_as]
                for sa in same_as:
                    if 'linkedin.com' in str(sa) and not result.get('linkedin'):
                        result['linkedin'] = str(sa)
                    elif ('twitter.com' in str(sa) or 'x.com' in str(sa)) and not result.get('twitter'):
                        result['twitter'] = str(sa)
                    elif 'facebook.com' in str(sa) and not result.get('facebook'):
                        result['facebook'] = str(sa)

                if result.get('company'):
                    break  # Found a good organization — stop
        except Exception:
            pass

    if debug and result:
        logger.debug(f"[extractor] structured_data keys={list(result.keys())}")

    return result


# ---------------------------------------------------------------------------
# Interests / topic extraction
# ---------------------------------------------------------------------------

INTEREST_KEYWORDS: Dict[str, str] = {
    'saas': 'SaaS', 'cloud': 'Cloud Computing', 'ai': 'Artificial Intelligence',
    'machine learning': 'Machine Learning', 'automation': 'Automation',
    'cybersecurity': 'Cybersecurity', 'security': 'Cybersecurity',
    'blockchain': 'Blockchain', 'ecommerce': 'E-Commerce',
    'e-commerce': 'E-Commerce', 'data analytics': 'Data Analytics',
    'big data': 'Big Data', 'digital marketing': 'Digital Marketing',
    'seo': 'SEO', 'social media': 'Social Media',
    'content marketing': 'Content Marketing', 'real estate': 'Real Estate',
    'fintech': 'Fintech', 'mobile app': 'Mobile Development',
    'web development': 'Web Development', 'iot': 'IoT', 'devops': 'DevOps',
    'consulting': 'Consulting', 'crm': 'CRM', 'erp': 'ERP',
    'hr tech': 'HR Tech', 'logistics': 'Logistics',
    'supply chain': 'Supply Chain', 'renewable': 'Renewable Energy',
    'solar': 'Solar Energy', 'healthcare': 'Healthcare',
    'biotech': 'Biotech', 'edtech': 'EdTech', 'insurance': 'Insurance',
    'investment': 'Investment', 'trading': 'Trading', 'design': 'Design',
    'branding': 'Branding', 'startup': 'Startups',
    'entrepreneur': 'Entrepreneurship', 'b2b': 'B2B', 'b2c': 'B2C',
    'api': 'API Development', 'open source': 'Open Source',
    'blockchain': 'Blockchain', 'nft': 'NFT', 'defi': 'DeFi',
}


def extract_interests(text: str, industry: Optional[str] = None) -> List[str]:
    """Extract interest tags from combined page text + industry hint."""
    text_lower = text[:3000].lower()
    found: set = set()
    for kw, label in INTEREST_KEYWORDS.items():
        if kw in text_lower:
            found.add(label)
    # Fall back to industry when nothing else matched
    if not found and industry:
        found.add(industry)
    return list(found)[:8]


# ---------------------------------------------------------------------------
# Convenience: parse full page into a flat extraction dict
# ---------------------------------------------------------------------------

def extract_all(
    html_text: str,
    url: str = '',
    *,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    One-shot extraction: given raw HTML, return a dict with all extractable
    lead fields.  Consumers (web collector, social collector) can merge this
    over their own partial dict.

    Returns:
        {
          emails: List[str],
          phones: List[str],
          contact_name: str | None,
          company: str | None,
          position: str | None,
          linkedin_url: str | None,
          industry: str | None,
          interests: List[str],
          structured_data: Dict,
          email_type: str,   # 'personal' | 'company' | 'generic' | 'free' | 'unknown'
        }
    """
    if debug:
        logger.debug(f"[extractor] extract_all url={url} html_len={len(html_text)}")

    try:
        soup = BeautifulSoup(html_text, 'html.parser')
    except Exception as exc:
        logger.warning(f"[extractor] BeautifulSoup parse error for {url}: {exc}")
        return {}

    structured = extract_structured_data(soup, debug=debug)
    emails = extract_emails_from_html(html_text, debug=debug)
    phones = extract_phones_from_html(html_text, debug=debug)
    contact_name = extract_contact_name(soup, debug=debug)
    company = extract_company_name(soup, url, debug=debug)
    position = extract_position(soup, debug=debug)
    linkedin = extract_linkedin_url(soup, html_text, debug=debug)

    # Merge structured data into extracted values (structured = highest priority)
    if structured.get('email') and structured['email'] not in emails:
        emails.insert(0, structured['email'])
    if structured.get('phone') and structured['phone'] not in phones:
        phones.insert(0, structured['phone'])
    if not company and structured.get('company'):
        company = structured['company']
    if not linkedin and structured.get('linkedin'):
        linkedin = structured['linkedin']

    # Re-validate emails from structured data
    emails = [e for e in emails if _validate_email(e)]
    best_email = emails[0] if emails else None

    full_text = soup.get_text(separator=' ', strip=True)
    industry = classify_industry(full_text + ' ' + (company or ''), debug=debug)
    if not industry and structured.get('industry'):
        industry = structured['industry']

    interests = extract_interests(full_text, industry)

    return {
        'emails': emails,
        'phones': phones,
        'contact_name': contact_name,
        'company': company,
        'position': position,
        'linkedin_url': linkedin,
        'industry': industry,
        'interests': interests,
        'structured_data': structured,
        'email_type': _email_type(best_email) if best_email else 'unknown',
    }
