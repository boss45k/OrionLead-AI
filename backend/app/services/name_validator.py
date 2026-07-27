"""
Name & Email Validator
======================
Centralises all "is this a real person name?" and "is this a real email?"
checks that were previously scattered across collectors.

Catches the failure modes visible in the screenshot:
  • URL saved as contact name  (https://www.wholesalemotorgroup.com.au/)
  • Page title saved as name   (Contact Us, About Us, Home)
  • CDN / pixel tracker email  (st@ic.cloudflareinsights.com)
  • Hotmail regional variants  (wmgroup@live.com.au, user@hotmail.co.uk)
"""

from __future__ import annotations

import re
from typing import Tuple

# ---------------------------------------------------------------------------
# CDN / analytics / tracking pixel domains — never real contacts
# ---------------------------------------------------------------------------

CDN_AND_TRACKER_DOMAINS: frozenset[str] = frozenset({
    # Cloudflare
    'cloudflareinsights.com', 'cloudflare.com', 'cloudflare.net',
    # Google analytics / ads
    'googletagmanager.com', 'google-analytics.com', 'googleadservices.com',
    'doubleclick.net', 'googlesyndication.com', 'gstatic.com',
    'analytics.google.com', 'stats.g.doubleclick.net',
    # Facebook / Meta pixel
    'facebook.com', 'fbcdn.net', 'connect.facebook.net',
    # CDN / hosting
    'cloudfront.net', 'fastly.net', 'akamaihd.net', 'akamai.net',
    'edgecastcdn.net', 'maxcdn.com', 'bootstrapcdn.com',
    'cdn.jsdelivr.net', 'unpkg.com', 'cdnjs.cloudflare.com',
    # Marketing automation
    'hotjar.com', 'heapanalytics.com', 'mixpanel.com', 'segment.com',
    'segment.io', 'amplitude.com', 'kissmetrics.com',
    # CRM / chat
    'intercom.io', 'intercom.com', 'hubspot.com', 'hubspot.net',
    'marketo.com', 'pardot.com', 'salesforce.com',
    'drift.com', 'driftt.com', 'crisp.chat', 'zendesk.com',
    # Social trackers
    'twitter.com', 't.co', 'linkedin.com', 'instagram.com',
    # Other known tracking
    'scorecardresearch.com', 'quantserve.com', 'chartbeat.com',
    'newrelic.com', 'datadog-browser-agent.com', 'adoghq-browser-agent.com',
    'datadoghq.com', 'sentry.io', 'bugsnag.com', 'loggly.com',
    'onesignal.com', 'pusher.com', 'pushwoosh.com',
    # Ad networks
    'bing.com', 'bat.bing.com', 'adroll.com', 'criteo.com',
    'outbrain.com', 'taboola.com', 'revcontent.com',
    # Email service providers (transactional / marketing, not contacts)
    'sendgrid.net', 'mailchimp.com', 'amazonses.com',
    'sparkpostmail.com', 'mandrillapp.com', 'mailgun.org',
    'constantcontact.com', 'campaignmonitor.com',
    # CDN asset hosts
    'assets.squarespace.com', 'static.wixstatic.com',
    'images.unsplash.com', 'media.giphy.com',
    # B2B data / enrichment tools — these are competitors, never real leads
    'contactout.com', 'zoominfo.com', 'lusha.com', 'lusha.co',
    'apollo.io', 'hunter.io', 'rocketreach.co', 'snov.io',
    'leadiq.com', 'clearbit.com', 'peopledatalabs.com', 'pdl.io',
    'signalhire.com', 'kendo.email', 'skrapp.io', 'voilanorbert.com',
    'findthatlead.com', 'anymailfinder.com', 'dropcontact.com',
    'seamless.ai', 'uplead.com', 'leadgenius.com',
    # Consumer email services (emails like info@outlook.live.com)
    'outlook.live.com',
    # Classifieds / marketplace platforms — listing pages, not real companies
    'opensooq.com', 'olx.com', 'dubizzle.com', 'avito.ru', 'avito.com',
    'craigslist.org', 'gumtree.com', 'classified.com', 'oodle.com',
    'kijiji.ca', 'locanto.com', 'adpost.com', 'expatriates.com',
    'hatla2ee.com', 'yallakorah.com', 'motory.com', 'syarah.com',
})

# Substrings that appear in CDN subdomains — used as a secondary check
_CDN_SUBSTRINGS = (
    'cloudflareinsights', 'doubleclick', 'googletagmanager',
    'google-analytics', 'fbcdn', 'akamaihd', 'fastly.net',
    'cloudfront.net', 'hotjar', 'mixpanel', 'segment.io',
    'intercom.io', 'hubspot', 'marketo', 'pardot',
    'sentry.io', 'newrelic', 'datadog', 'adoghq',
)


def is_cdn_email(email: str) -> bool:
    """
    Return True if the email domain belongs to a CDN, analytics pixel,
    ad network, or marketing automation platform — never a real contact.

    Catches st@ic.cloudflareinsights.com and similar tracker emails.
    """
    if not email or '@' not in email:
        return False
    domain = email.lower().split('@', 1)[1]
    # Exact domain match
    if domain in CDN_AND_TRACKER_DOMAINS:
        return True
    # Subdomain match (e.g. ic.cloudflareinsights.com → cloudflareinsights.com)
    parts = domain.split('.')
    for i in range(len(parts) - 1):
        parent = '.'.join(parts[i:])
        if parent in CDN_AND_TRACKER_DOMAINS:
            return True
    # Substring heuristic for unknown CDN subdomains
    return any(s in domain for s in _CDN_SUBSTRINGS)


# ---------------------------------------------------------------------------
# Extended free-email domain check
# Includes regional Hotmail / Yahoo / Live variants that FREE_EMAIL_DOMAINS
# in lead_quality_engine.py currently misses.
# ---------------------------------------------------------------------------

# Exact additional domains not covered by the base set
_EXTRA_FREE_DOMAINS: frozenset[str] = frozenset({
    # Microsoft regional live / hotmail
    'live.com.au', 'live.co.uk', 'live.ca', 'live.com.mx',
    'live.com.ar', 'live.com.br', 'live.fr', 'live.de',
    'live.it', 'live.nl', 'live.es', 'live.jp', 'live.in',
    'live.com.sa', 'live.com.eg', 'live.com.ph', 'live.com.sg',
    'hotmail.co.uk', 'hotmail.com.au', 'hotmail.fr', 'hotmail.de',
    'hotmail.it', 'hotmail.es', 'hotmail.nl', 'hotmail.be',
    'hotmail.ca', 'hotmail.com.br', 'hotmail.com.ar',
    'hotmail.com.mx', 'hotmail.co.jp', 'hotmail.co.in',
    # Yahoo regional
    'yahoo.co.uk', 'yahoo.com.au', 'yahoo.co.jp', 'yahoo.co.in',
    'yahoo.fr', 'yahoo.de', 'yahoo.it', 'yahoo.es', 'yahoo.com.br',
    'yahoo.com.ar', 'yahoo.com.mx', 'yahoo.com.ph', 'yahoo.com.sg',
    # Other free providers
    'outlook.com.au', 'outlook.co.uk',
    'rocketmail.com', 'ymail.com',
    'rediffmail.com', 'inbox.com',
    'mail.ru', 'bk.ru', 'list.ru',
    'qq.com', '163.com', '126.com', 'sina.com', 'sohu.com',
    'naver.com', 'daum.net', 'hanmail.net',
    'wp.pl', 'o2.pl', 'interia.pl',
    'libero.it', 'virgilio.it', 'tiscali.it',
    'orange.fr', 'wanadoo.fr', 'sfr.fr', 'free.fr',
    'web.de', 'gmx.de', 't-online.de',
    'terra.com.br', 'uol.com.br', 'bol.com.br',
    'seznam.cz', 'centrum.cz',
})

# Registrable-domain patterns for free providers (covers *.live.com etc.)
_FREE_PROVIDER_PATTERNS = (
    re.compile(r'^(?:live|hotmail|outlook)\.[a-z]{2,3}(?:\.[a-z]{2})?$'),
    re.compile(r'^yahoo\.[a-z]{2,3}(?:\.[a-z]{2})?$'),
)


def is_free_email_extended(email: str) -> bool:
    """
    Return True if the email is from a free / consumer provider.
    Extends the base FREE_EMAIL_DOMAINS to include regional variants
    such as live.com.au, hotmail.co.uk, yahoo.co.jp.
    """
    if not email or '@' not in email:
        return False
    domain = email.lower().split('@', 1)[1]
    if domain in _EXTRA_FREE_DOMAINS:
        return True
    return any(p.match(domain) for p in _FREE_PROVIDER_PATTERNS)


# ---------------------------------------------------------------------------
# Page-title / URL name detection
# Blocks names like "Contact Us", "https://…", "Home", "About"
# ---------------------------------------------------------------------------

# Exact phrases that are definitely NOT a person name
_BLOCKED_NAME_EXACT: frozenset[str] = frozenset({
    'contact us', 'contact', 'about us', 'about', 'home', 'homepage',
    'team', 'our team', 'meet the team', 'meet our team', 'the team',
    'staff', 'our staff', 'untitled', 'page not found', '404',
    'error', 'welcome', 'index', 'main', 'menu', 'navigation',
    'privacy policy', 'privacy', 'terms', 'terms and conditions',
    'cookie policy', 'sitemap', 'careers', 'jobs', 'login', 'sign in',
    'sign up', 'register', 'subscribe', 'newsletter', 'blog', 'news',
    'press', 'media', 'events', 'partners', 'clients', 'portfolio',
    'services', 'products', 'solutions', 'pricing', 'faq',
    'help', 'support', 'documentation', 'docs', 'api', 'developers',
    'get in touch', 'reach us', 'find us', 'directions',
    'enquire now', 'enquire', 'inquiry', 'request a quote',
})

# Prefixes that indicate the "name" is actually a URL or file path
_URL_PREFIXES = ('http://', 'https://', 'www.', 'ftp://')

# A "name" that matches this is a URL slug / path fragment, not a person
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:[-_][a-z0-9]+){2,}$')

# Words that should not appear in a real person name
_NON_NAME_WORDS: frozenset[str] = frozenset({
    'com', 'org', 'net', 'www', 'http', 'https', 'html', 'php',
    'page', 'site', 'website', 'web', 'link', 'click', 'here',
    'read', 'more', 'view', 'see', 'visit', 'go', 'to',
    'copyright', '©', 'all', 'rights', 'reserved',
})

# Suffixes that mark a "name" as a data-product description, not a real company/person.
# e.g. "Importers and Exporters Email List", "B2B CEO Email Database"
_DATA_PRODUCT_SUFFIXES: tuple = (
    'email list', 'email database', 'email addresses', 'mailing list',
    'email directory', 'contact list', 'contact database',
    'leads list', 'leads database', 'company list', 'company database',
    'b2b list', 'b2b database', 'phone list', 'phone database',
    'data list', 'data directory',
)

# Phrases that appear in marketplace/classifieds listing titles — not real companies.
# e.g. "Vehicles, Automobiles & Accessories for Sale in Egypt"
_MARKETPLACE_PHRASES: tuple = (
    ' for sale in ', ' for sale - ', 'for sale|', ' cars for sale',
    ' vehicles for sale', ' properties for sale', ' apartments for rent',
    ' jobs in ', ' vacancies in ', ' used cars in ',
)

# Max words allowed in a company/person name before it's treated as a page title.
# Real companies: "Google LLC" (2), "Deutsche Bank" (2), "New York Digital Group" (4).
# Page titles: "Car marketplace : used and new cars in Egypt" (9 words).
_NAME_MAX_WORDS_HARD = 7


def is_valid_person_name(name: str) -> Tuple[bool, str]:
    """
    Return (is_valid, rejection_reason).

    Catches:
    • URL-shaped names  → 'url_as_name'
    • Page-title names  → 'page_title_as_name'
    • Single-word slugs → 'slug_as_name'
    • Known placeholders→ 'placeholder_name'
    """
    if not name:
        return False, 'empty_name'

    stripped = name.strip()
    lower = stripped.lower()

    # URL check — fast path
    if any(lower.startswith(p) for p in _URL_PREFIXES):
        return False, 'url_as_name'

    # Contains a dot-domain pattern (.com, .com.au, .co.uk, etc.)
    if re.search(r'\.[a-z]{2,3}(?:\.[a-z]{2})?(?:/|$)', lower):
        return False, 'url_as_name'

    # Exact blocked phrase
    if lower in _BLOCKED_NAME_EXACT:
        return False, 'page_title_as_name'

    # Blocked phrase as prefix (e.g. "Contact Us - Acme Corp")
    for phrase in _BLOCKED_NAME_EXACT:
        if lower.startswith(phrase + ' ') or lower.startswith(phrase + ' -'):
            return False, 'page_title_as_name'

    # URL slug (e.g. "wholesale-motor-group", "john-doe-ceo")
    if _SLUG_RE.match(lower):
        return False, 'slug_as_name'

    # Contains non-name words like 'www', 'html', 'copyright'
    words_in_name = set(re.sub(r'[^\w\s]', ' ', lower).split())
    if words_in_name & _NON_NAME_WORDS:
        return False, 'url_as_name'

    # All-lowercase-alphanumeric = username pattern (john_smith123)
    if re.match(r'^[a-z0-9_\-\.]+$', stripped):
        return False, 'username_only'

    # Must have 2–5 words
    word_list = stripped.split()
    if len(word_list) < 2:
        return False, 'single_word_name'
    if len(word_list) > 5:
        return False, 'name_too_long'

    return True, ''


# ---------------------------------------------------------------------------
# Convenience: pre-filter a raw lead dict before the quality gate
# ---------------------------------------------------------------------------

def _is_url_name(name: str) -> bool:
    """Return True if the name string is clearly a URL or domain, not a real name."""
    lower = name.strip().lower()
    if any(lower.startswith(p) for p in _URL_PREFIXES):
        return True
    # Dot-domain pattern: acme.com, example.co.uk, site.com/path
    if re.search(r'\.[a-z]{2,3}(?:\.[a-z]{2})?(?:/|$)', lower):
        return True
    return False


def pre_filter_lead(lead: dict) -> Tuple[bool, str]:
    """
    Fast pre-filter that catches the worst offenders before calling
    evaluate_lead_quality().  Returns (should_continue, rejection_reason).

    Checks (in order):
      1. CDN / tracker email
      2. URL-shaped name (applies to ALL lead types)
      3. Page-title name like "Contact Us" (applies to ALL lead types)
      4. Full person-name validation (only for person / people leads)
      5. No anchor data at all (no email, website, company, phone)
    """
    email = (lead.get('email') or '').strip()
    if email and is_cdn_email(email):
        return False, 'cdn_tracker_email'

    name = (lead.get('name') or '').strip()
    lead_type = (lead.get('lead_type') or '').lower()
    is_person = lead_type in ('person', 'people', 'individual', '')

    if name:
        # URL-shaped name is invalid for any lead type
        if _is_url_name(name):
            return False, 'url_as_name'

        lower = name.lower()
        # Page-title name is invalid for any lead type
        if lower in _BLOCKED_NAME_EXACT:
            return False, 'page_title_as_name'
        for phrase in _BLOCKED_NAME_EXACT:
            if lower.startswith(phrase + ' ') or lower.startswith(phrase + ' -'):
                return False, 'page_title_as_name'

        # Data-product description used as name/company — e.g. "Importers and Exporters Email List"
        if any(lower.endswith(suffix) for suffix in _DATA_PRODUCT_SUFFIXES):
            return False, 'data_product_name'

        # Marketplace / classifieds listing title — e.g. "Vehicles for Sale in Egypt"
        if any(phrase in lower for phrase in _MARKETPLACE_PHRASES):
            return False, 'marketplace_listing'

        # Page-title colon separator + long name — e.g. "Car marketplace : used and new cars in Egypt"
        if ' : ' in name and len(name.split()) > 4:
            return False, 'page_title_as_name'

        # Hard word-count cap — real company names are almost never > 7 words
        if len(name.split()) > _NAME_MAX_WORDS_HARD:
            return False, 'name_too_long'

        # All-caps single-word handle (e.g. BARAMJK, TECHKW) — username, not a real name
        stripped = name.strip()
        if (re.match(r'^[A-Z0-9]{3,12}$', stripped) and
                not stripped.isdigit() and
                stripped not in ('CEO', 'CTO', 'CFO', 'COO', 'MD', 'VP', 'HR', 'PR', 'IT', 'AI')):
            return False, 'username_only'

        # Strict person-name checks only for person leads
        if is_person:
            ok, reason = is_valid_person_name(name)
            if not ok:
                return False, reason

    # Apply page-title / marketplace checks to the company field too,
    # since collectors often set company = page title independently of name.
    company = (lead.get('company') or '').strip()
    if company and company != name:
        co_lower = company.lower()
        if any(co_lower.endswith(suffix) for suffix in _DATA_PRODUCT_SUFFIXES):
            return False, 'data_product_name'
        if any(phrase in co_lower for phrase in _MARKETPLACE_PHRASES):
            return False, 'marketplace_listing'
        if ' : ' in company and len(company.split()) > 4:
            return False, 'page_title_as_name'
        if len(company.split()) > _NAME_MAX_WORDS_HARD:
            return False, 'name_too_long'

    # Reject if there is literally no company, no email, no website, no phone
    has_any_anchor = (
        bool(company)
        or bool(email)
        or bool(lead.get('website'))
        or bool(lead.get('phone'))
    )
    if not has_any_anchor:
        return False, 'no_anchor_data'

    return True, ''
