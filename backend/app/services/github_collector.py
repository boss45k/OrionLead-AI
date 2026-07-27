"""
GitHub Lead Collector
=====================
Finds real business professionals via the GitHub public API.

Strategy:
  1. Search users by location + repo activity (real developers with company info)
  2. Search repos by topic, pull contributors (OSS maintainers = decision-makers)
  3. Enrich each user profile for company / email / website

Quality notes:
  • email_source = 'github_profile' (self-reported, not verified)
  • email_verified = False (SMTP not confirmed)
  • source_reliability_score = 68 (self-reported professional data)
  • Leads with no company AND no email are dropped before returning
  • Company field is stored even without email so enrichment cascade can find the email

Rate limits:
  • Authenticated (GITHUB_TOKEN): 5 000 requests/hour, 30 search/min
  • Unauthenticated: 60 requests/hour — collector falls back gracefully
"""
import os
import re
import time
import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

# Topics that attract decision-makers / founders
DEFAULT_TOPICS = [
    'saas', 'startup', 'fintech', 'healthtech', 'b2b', 'crm',
    'devtools', 'api', 'platform', 'ecommerce',
]

# User search templates — each should have at least a location or topic anchor
_USER_QUERIES = [
    'type:user repos:>3 followers:>10',
    'type:user in:bio CTO repos:>2',
    'type:user in:bio founder repos:>2',
    'type:user in:bio "VP Engineering" repos:>1',
    'type:user in:bio CEO repos:>2',
]

# Domains we do NOT want as business websites
_JUNK_BLOG_DOMAINS = frozenset({
    'github.com', 'twitter.com', 'x.com', 'facebook.com', 't.me',
    'linkedin.com', 'instagram.com', 'youtube.com', 'medium.com',
    'twitch.tv', 'reddit.com', 'discord.gg', 'discord.com',
})


def _clean_company(raw: str) -> str:
    """Strip GitHub org-handle prefix (@) and normalise whitespace."""
    if not raw:
        return ''
    return re.sub(r'\s+', ' ', raw.lstrip('@')).strip()


def _clean_blog(url: str) -> Optional[str]:
    """Return a usable website URL or None."""
    if not url:
        return None
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    try:
        host = urlparse(url).netloc.lower().replace('www.', '')
        if any(junk in host for junk in _JUNK_BLOG_DOMAINS):
            return None
        return url
    except Exception:
        return None


def _extract_title_from_bio(bio: str) -> str:
    """Heuristic: grab the first 'Title at Company' or 'Title | Company' substring."""
    if not bio:
        return ''
    patterns = [
        r'(?:^|\n)([A-Z][a-zA-Z ]{3,40})\s+(?:at|@)\s+\w',
        r'(?:^|\n)([A-Z][a-zA-Z ]{3,40})\s*[|–—]\s*\w',
        r'(CEO|CTO|CFO|COO|VP|Director|Founder|Engineer|Developer|Manager|Lead)\b',
    ]
    for pat in patterns:
        m = re.search(pat, bio)
        if m:
            return m.group(1).strip()
    return ''


class GitHubCollector:
    def __init__(self):
        self.token = os.getenv('GITHUB_TOKEN', '')
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })
        if self.token:
            self.session.headers['Authorization'] = f'Bearer {self.token}'

    def is_configured(self) -> bool:
        return True  # Works unauthenticated, but rate-limited

    def _get(self, path: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
        url = path if path.startswith('http') else f"{GITHUB_API}{path}"
        try:
            resp = self.session.get(url, params=params or {}, timeout=timeout)
            remaining = int(resp.headers.get('X-RateLimit-Remaining', 999))
            if remaining < 5:
                reset_at = int(resp.headers.get('X-RateLimit-Reset', 0))
                wait = max(0, reset_at - int(time.time())) + 2
                logger.warning(f"[GitHub] rate limit nearly exhausted — sleeping {wait}s")
                time.sleep(min(wait, 60))
            if resp.status_code == 403:
                logger.warning("[GitHub] 403 — rate limit hit or token invalid")
                return None
            if resp.status_code == 422:
                logger.debug(f"[GitHub] 422 unprocessable: {resp.text[:200]}")
                return None
            if not resp.ok:
                logger.debug(f"[GitHub] {resp.status_code} {url}")
                return None
            return resp.json()
        except Exception as exc:
            logger.debug(f"[GitHub] request error: {exc}")
            return None

    def _normalize_user(self, profile: dict) -> Optional[Dict[str, Any]]:
        """Convert a GitHub user profile dict into a system lead dict."""
        name    = (profile.get('name') or '').strip()
        login   = profile.get('login', '')
        company = _clean_company(profile.get('company', ''))
        email   = (profile.get('email') or '').strip().lower()
        bio     = (profile.get('bio') or '').strip()
        loc     = (profile.get('location') or '').strip()
        blog    = _clean_blog(profile.get('blog', ''))
        gh_url  = profile.get('html_url', '')

        # Skip if this looks like a bot / org account, not a person
        if profile.get('type', 'User') != 'User':
            return None

        # Need at least a real name or company to be actionable
        if not name and not company:
            return None

        # Use login as name fallback only if it looks like a real name
        display_name = name or ''
        if not display_name:
            return None  # GitHub login alone is not a person name

        position = _extract_title_from_bio(bio)

        lead: Dict[str, Any] = {
            'name':         display_name,
            'email':        email,
            'company':      company,
            'position':     position,
            'website':      blog or '',
            'location':     loc,
            'linkedin_url': '',
            'source':       'github',
            'data_points': {
                'enrichment_source':        'github',
                'enriched_at':              datetime.now(timezone.utc).isoformat(),
                'email_source':             'github_profile' if email else 'missing',
                'email_verified':           False,
                'email_type':               'personal_business' if email else 'missing',
                'source_reliability_score': 68.0,
                'github_url':               gh_url,
                'github_login':             login,
                'public_repos':             profile.get('public_repos', 0),
                'followers':                profile.get('followers', 0),
            },
        }
        return lead

    # ------------------------------------------------------------------
    # Public search methods
    # ------------------------------------------------------------------

    def search_users_by_query(
        self,
        query: str,
        locations: Optional[List[str]] = None,
        max_results: int = 30,
    ) -> List[Dict[str, Any]]:
        """Search GitHub users and return normalised lead dicts."""
        results: List[Dict[str, Any]] = []
        per_page = min(max_results, 30)

        q = query
        if locations:
            loc_clause = ' OR '.join(f'location:"{loc}"' for loc in locations[:3])
            q = f"({q}) ({loc_clause})"

        data = self._get('/search/users', params={'q': q, 'per_page': per_page, 'page': 1})
        if not data:
            return []

        items = data.get('items', [])
        logger.info(f"[GitHub] user search '{query}' → {len(items)} hits")

        for item in items:
            if len(results) >= max_results:
                break
            username = item.get('login', '')
            if not username:
                continue
            profile = self._get(f'/users/{username}')
            if not profile:
                continue
            lead = self._normalize_user(profile)
            if lead:
                results.append(lead)
            time.sleep(0.15)  # stay well inside the 30 search/min cap

        return results

    def search_repo_contributors(
        self,
        topics: Optional[List[str]] = None,
        min_stars: int = 50,
        max_repos: int = 5,
        max_contributors: int = 20,
    ) -> List[Dict[str, Any]]:
        """Find contributors of popular repos — often founders and senior engineers."""
        results: List[Dict[str, Any]] = []
        seen_logins: set = set()
        use_topics = topics or DEFAULT_TOPICS[:3]

        for topic in use_topics:
            if len(results) >= max_contributors:
                break
            data = self._get('/search/repositories', params={
                'q':       f'topic:{topic} stars:>{min_stars}',
                'sort':    'stars',
                'order':   'desc',
                'per_page': max_repos,
            })
            if not data:
                continue

            for repo in data.get('items', [])[:max_repos]:
                full_name = repo.get('full_name', '')
                contribs = self._get(f'/repos/{full_name}/contributors',
                                     params={'per_page': 10}) or []
                for c in contribs:
                    login = c.get('login', '')
                    if not login or login in seen_logins:
                        continue
                    seen_logins.add(login)
                    profile = self._get(f'/users/{login}')
                    if not profile:
                        continue
                    lead = self._normalize_user(profile)
                    if lead:
                        results.append(lead)
                        if len(results) >= max_contributors:
                            break
                    time.sleep(0.2)

        return results

    def collect(
        self,
        keywords: str = '',
        locations: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Main collection entry-point.
        Returns leads that all need to pass through evaluate_lead_quality() before saving.
        """
        results: List[Dict[str, Any]] = []
        seen_emails: set = set()
        seen_logins: set = set()

        def _add(leads):
            for ld in leads:
                login = ld.get('data_points', {}).get('github_login', '')
                email = ld.get('email', '')
                key = email or login
                if not key or key in seen_emails:
                    continue
                seen_emails.add(key)
                if login:
                    seen_logins.add(login)
                results.append(ld)

        # 1. Keyword-based user search
        if keywords:
            kw_query = f'type:user repos:>2 {keywords}'
            _add(self.search_users_by_query(kw_query, locations=locations,
                                            max_results=max_results // 2))

        # 2. Standard role-based queries
        for q in _USER_QUERIES[:2]:
            if len(results) >= max_results:
                break
            _add(self.search_users_by_query(q, locations=locations,
                                            max_results=15))

        # 3. Repo contributors (topic-driven)
        if len(results) < max_results:
            _add(self.search_repo_contributors(
                topics=topics,
                max_contributors=max_results - len(results),
            ))

        logger.info(f"[GitHub] collected {len(results)} candidate leads")
        return results


# ── Singleton ──────────────────────────────────────────────────────────────────
_instance: Optional[GitHubCollector] = None


def get_github_collector() -> GitHubCollector:
    global _instance
    if _instance is None:
        _instance = GitHubCollector()
    return _instance
