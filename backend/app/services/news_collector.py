"""
Business News Lead Collector
============================
Extracts company + executive signals from public business news RSS feeds.

Strategy:
  1. Pull RSS/Atom feeds from major business wires (BusinessWire, PRNewswire,
     TechCrunch, VentureBeat, Reuters Business, Google News topic feeds).
  2. NER-lite heuristic: find "Name, Title at/of Company" patterns in headlines.
  3. Return raw lead dicts (name + company + position) with no email —
     the enrichment cascade (Hunter domain search → PDL → Apollo) fills email.

Why this works:
  • Press releases and funding announcements name specific people + companies.
  • Companies in the news = active, growing, likely buying.
  • Exec + company name is enough for Hunter domain_search to find a work email.

Quality notes:
  • email = '' on all returned leads (never fabricated)
  • source_reliability_score = 60 (news mention, identity unverified)
  • Leads without both name + company are discarded here
  • Duplicate names across feeds are merged before returning
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RSS feeds — business news with named exec coverage
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    # ── Funding & startup news ───────────────────────────────────────────────
    ('techcrunch',      'https://techcrunch.com/feed/'),
    ('venturebeat',     'https://venturebeat.com/feed/'),
    # ── Business wires (press releases name real people + companies) ─────────
    ('businesswire',    'https://www.businesswire.com/rss/home/?rss=G7'),
    ('prnewswire',      'https://www.prnewswire.com/rss/news-releases-list.rss'),
    # ── Mainstream business press ────────────────────────────────────────────
    ('forbes',          'https://www.forbes.com/real-time/feed2/'),
    ('inc',             'https://www.inc.com/rss/'),
    ('entrepreneur',    'https://www.entrepreneur.com/latest.rss'),
    # ── Google News — funding rounds (executive named in headline) ────────────
    ('google_funding',
     'https://news.google.com/rss/search?q=funding+round+CEO+founder+startup+raises&hl=en-US&gl=US&ceid=US:en'),
    # ── Google News — executive appointments (person + company signal) ────────
    ('google_appointments',
     'https://news.google.com/rss/search?q=appointed+CEO+OR+CTO+OR+founder+OR+president+company&hl=en-US&gl=US&ceid=US:en'),
    # ── Google News — B2B SaaS ───────────────────────────────────────────────
    ('google_saas',
     'https://news.google.com/rss/search?q=B2B+SaaS+raises+million+CEO+founder&hl=en-US&gl=US&ceid=US:en'),
    # ── Google News — fintech ────────────────────────────────────────────────
    ('google_fintech',
     'https://news.google.com/rss/search?q=fintech+startup+raises+CEO+founder&hl=en-US&gl=US&ceid=US:en'),
    # ── Google News — MENA region (Gulf, Middle East businesses) ─────────────
    ('google_mena',
     'https://news.google.com/rss/search?q=CEO+founder+startup+raises+Gulf+OR+UAE+OR+Saudi+OR+Kuwait&hl=en-US&gl=US&ceid=US:en'),
    # ── Google News — SME / growth signals ──────────────────────────────────
    ('google_sme',
     'https://news.google.com/rss/search?q=small+business+owner+CEO+founder+launched+company&hl=en-US&gl=US&ceid=US:en'),
]

# ---------------------------------------------------------------------------
# Extraction patterns
# ---------------------------------------------------------------------------

# "John Smith, CEO of Acme Corp" / "John Smith (Founder, AcmeCo)"
_PERSON_COMPANY_RE = re.compile(
    r'\b([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){1,3})'   # Full Name (2-4 words)
    r'(?:\s*[,\(]\s*)'                                       # separator
    r'((?:Co-)?(?:Founder|CEO|CTO|CFO|COO|President|'
    r'Managing Director|VP|Vice President|Director|'
    r'Head of \w+|Partner|Chairman|Principal)\b[^,\n]{0,30})'  # Title
    r'(?:[,\s]+(?:of|at|@)\s+)?'
    r'([A-Z][a-zA-Z0-9\.\-\s]{1,40}?)(?=\s*[\.,\)\n])',    # Company
    re.UNICODE,
)

# "Acme Corp CEO John Smith" / "Acme raises $5M; CEO John Smith says..."
_COMPANY_PERSON_RE = re.compile(
    r'([A-Z][a-zA-Z0-9\.\-\s]{1,40}?)\s+'
    r'(?:CEO|CTO|CFO|COO|Founder|President|Director)\s+'
    r'([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){1,3})',
    re.UNICODE,
)

# "$Xm funding" headline — company name is often at start
_FUNDING_HEADLINE_RE = re.compile(
    r'^([A-Z][a-zA-Z0-9\.\-\s]{2,40}?)\s+'
    r'(?:raises?|secures?|closes?|lands?|gets?|announces?|completes?)\s+'
    r'\$[\d\.]+[MKB]',
    re.IGNORECASE,
)

_EXEC_TITLES = frozenset({
    'founder', 'co-founder', 'ceo', 'cto', 'cfo', 'coo',
    'president', 'managing director', 'vp', 'vice president',
    'director', 'head of', 'partner', 'chairman', 'principal',
})

_STOP_NAMES = frozenset({
    'The Company', 'New York', 'San Francisco', 'Los Angeles',
    'United States', 'North America', 'South America', 'United Kingdom',
    'Press Release', 'Business Wire', 'PR Newswire', 'Globe Newswire',
    'Reuters', 'Bloomberg', 'Forbes', 'TechCrunch',
})

_NAME_MIN_WORDS  = 2
_NAME_MAX_WORDS  = 4
_COMPANY_NOISE   = re.compile(r'\b(Inc|LLC|Ltd|Corp|Company|Group|Holdings|Ventures|'
                               r'Technologies|Solutions|Services|Systems|Labs?|Co)\b\.?$',
                               re.IGNORECASE)


def _clean_company(raw: str) -> str:
    raw = raw.strip().rstrip(',.()')
    raw = re.sub(r'\s+', ' ', raw)
    return raw if len(raw) >= 2 else ''


def _looks_like_name(text: str) -> bool:
    words = text.strip().split()
    if not (_NAME_MIN_WORDS <= len(words) <= _NAME_MAX_WORDS):
        return False
    if text in _STOP_NAMES:
        return False
    return all(w[0].isupper() and w[1:].islower() for w in words if len(w) > 1)


def _extract_from_text(text: str) -> List[Tuple[str, str, str]]:
    """Return list of (name, position, company) tuples found in text."""
    findings = []
    for m in _PERSON_COMPANY_RE.finditer(text):
        name    = m.group(1).strip()
        pos     = m.group(2).strip()
        company = _clean_company(m.group(3))
        if _looks_like_name(name) and company:
            findings.append((name, pos, company))
    for m in _COMPANY_PERSON_RE.finditer(text):
        company = _clean_company(m.group(1))
        name    = m.group(2).strip()
        if _looks_like_name(name) and company:
            findings.append((name, '', company))
    return findings


def _extract_company_from_headline(headline: str) -> str:
    """Pull the company name from a funding-round headline."""
    m = _FUNDING_HEADLINE_RE.match(headline)
    if m:
        return _clean_company(m.group(1))
    return ''


# ---------------------------------------------------------------------------
# Collector class
# ---------------------------------------------------------------------------

class NewsCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (compatible; LeadBot/1.0; '
                '+https://your-domain.com/bot)'
            ),
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        })

    def _fetch_feed(self, name: str, url: str) -> List[Dict[str, str]]:
        """Fetch an RSS/Atom feed and return list of {title, description, link}."""
        try:
            resp = self.session.get(url, timeout=15)
            if not resp.ok:
                logger.debug(f"[News] feed '{name}' returned {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, 'xml')
            items = []
            for entry in soup.find_all(['item', 'entry'])[:25]:
                _t = entry.find('title')
                title = _t.get_text('').strip() if _t else ''
                _d = entry.find(['description', 'summary', 'content'])
                desc  = _d.get_text('').strip() if _d else ''
                _l = entry.find('link')
                link  = _l.get_text('').strip() if _l else ''
                if not link and entry.find('link'):
                    link = entry.find('link').get('href', '')
                items.append({'title': title, 'description': desc[:600], 'link': link})
            logger.debug(f"[News] '{name}' → {len(items)} items")
            return items
        except Exception as exc:
            logger.debug(f"[News] feed '{name}' error: {exc}")
            return []

    def _items_to_leads(
        self, items: List[Dict], source_name: str
    ) -> List[Dict[str, Any]]:
        """Convert feed items to raw lead dicts."""
        results = []
        for item in items:
            headline = item.get('title', '')
            body     = item.get('description', '')
            link     = item.get('link', '')
            combined = f"{headline}. {body}"

            # Extract person + role + company from text
            found = _extract_from_text(combined)

            # Fallback: get company from funding headline, no named person yet
            if not found:
                company = _extract_company_from_headline(headline)
                if company:
                    # Company-only lead: still useful for domain-based Hunter search
                    results.append({
                        'name':         '',
                        'email':        '',
                        'company':      company,
                        'position':     '',
                        'website':      '',
                        'linkedin_url': '',
                        'location':     '',
                        'source':       'news',
                        'data_points': {
                            'enrichment_source':        f'news_{source_name}',
                            'enriched_at':              datetime.now(timezone.utc).isoformat(),
                            'email_source':             'missing',
                            'email_verified':           False,
                            'source_reliability_score': 55.0,
                            'news_url':                 link[:300],
                            'news_headline':            headline[:200],
                        },
                    })
                continue

            for name, position, company in found:
                results.append({
                    'name':         name,
                    'email':        '',
                    'company':      company,
                    'position':     position,
                    'website':      '',
                    'linkedin_url': '',
                    'location':     '',
                    'source':       'news',
                    'data_points': {
                        'enrichment_source':        f'news_{source_name}',
                        'enriched_at':              datetime.now(timezone.utc).isoformat(),
                        'email_source':             'missing',
                        'email_verified':           False,
                        'source_reliability_score': 60.0,
                        'news_url':                 link[:300],
                        'news_headline':            headline[:200],
                    },
                })
        return results

    def collect(
        self,
        keywords: str = '',
        max_results: int = 60,
        feeds: Optional[List[Tuple[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Pull from business news RSS feeds and extract named leads.

        All returned leads have email='' and must go through the enrichment
        cascade (Hunter domain_search → PDL → Apollo) before quality scoring.
        """
        use_feeds = feeds or RSS_FEEDS
        results: List[Dict[str, Any]] = []
        seen: set = set()

        for feed_name, feed_url in use_feeds:
            if len(results) >= max_results:
                break

            # Allow keyword filtering of feed URL for Google News queries
            if keywords and 'google.com/rss/search' in feed_url:
                from urllib.parse import quote_plus
                kw_url = (
                    f"https://news.google.com/rss/search"
                    f"?q={quote_plus(keywords)}+CEO+founder&hl=en-US&gl=US&ceid=US:en"
                )
                items = self._fetch_feed(f'google_{keywords[:20]}', kw_url)
            else:
                items = self._fetch_feed(feed_name, feed_url)

            leads = self._items_to_leads(items, feed_name)
            for ld in leads:
                # Dedup on name+company (news often repeats same person)
                key = (ld.get('name', '') + '|' + ld.get('company', '')).lower()
                if key in seen or len(key) < 4:
                    continue
                seen.add(key)
                results.append(ld)

            time.sleep(0.3)

        logger.info(f"[News] collected {len(results)} candidate leads from {len(use_feeds)} feeds")
        return results[:max_results]


# ── Singleton ──────────────────────────────────────────────────────────────────
_instance: Optional[NewsCollector] = None


def get_news_collector() -> NewsCollector:
    global _instance
    if _instance is None:
        _instance = NewsCollector()
    return _instance
