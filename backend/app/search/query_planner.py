"""
Search Query Planner
====================
Builds deterministic, targeted search queries for every collection source.
Merges structured UI filters with the user's free-text query.

Design principles
-----------------
- UI filter values ALWAYS override anything inferred from query text.
- Query text is kept as-is (no NLP stripping); filters handle location/industry.
- Negative terms are always appended to reduce junk results.
- No LLM, no network calls — completes in < 1 ms.

Usage
-----
    from app.search.query_planner import QueryPlanner

    plan = QueryPlanner.build(
        query="SaaS companies",
        filters={
            "country": "Nigeria",
            "city": "Lagos",
            "industry": "Technology",
            "lead_type": "person",
            "titles": ["CEO", "Founder", "CTO"],
            "sources": ["linkedin", "web", "news", "github"],
            "email_required": True,
        },
    )
    # plan.google_queries   -> targeted Google/Bing/DDG query strings
    # plan.linkedin_queries -> LinkedIn-specific queries
    # plan.news_queries     -> press-release / funding queries
    # plan.github_queries   -> GitHub founder/dev queries
    # plan.negative_terms   -> operator-prefixed negatives ("-inurl:jobs" etc.)
    # plan.negative_words   -> raw words for post-collection text filtering
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Negative terms
# ---------------------------------------------------------------------------

# Operator-prefixed — append to Google / Bing / DDG query strings
_NEG_WEB: List[str] = [
    # ── Directory / listing sites (highest priority) ──
    "-site:clutch.co",
    "-site:goodfirms.co",
    "-site:g2.com",
    "-site:capterra.com",
    "-site:yelp.com",
    "-site:yellowpages.com",
    "-site:crunchbase.com",
    "-site:trustpilot.com",
    "-site:wikipedia.org",
    # ── Job boards ──
    "-inurl:jobs",
    "-inurl:careers",
    "-inurl:hiring",
    "-site:glassdoor.com",
    "-site:indeed.com",
    "-site:monster.com",
    "-site:linkedin.com/jobs",
    # ── Content keywords ──
    '"-directory"',
    '"-top 10"',
    '"-top 50"',
    '"-list of"',
    '"-university"',
    '"-government"',
    '"-ngo"',
]

# Raw words — used for post-collection text filtering (no operator prefix)
_NEG_WORDS: List[str] = [
    "university",
    "polytechnic",
    "ministry",
    "government",
    "hospital",
    "school",
    "charity",
    "ngo",
    "embassy",
    "glassdoor",
    "indeed",
    "top 10 list",
    "top 50 list",
    "directory of",
    "wikipedia",
    "courses",
    "job board",
]

# Default B2B decision-maker titles for people searches
_DEFAULT_TITLES: List[str] = [
    "CEO",
    "Founder",
    "CTO",
    "CMO",
    "COO",
    "Director",
    "VP",
    "Owner",
]

# Query words that suggest person-type leads
_PERSON_SIGNALS = frozenset(
    {
        "ceo",
        "founder",
        "co-founder",
        "cto",
        "cmo",
        "coo",
        "cfo",
        "director",
        "vp",
        "vice president",
        "owner",
        "manager",
        "head of",
        "president",
        "partner",
        "executive",
        "contact",
        "decision maker",
        "professional",
        "talent",
    }
)

# Query words that suggest company-type leads
_COMPANY_SIGNALS = frozenset(
    {
        "company",
        "companies",
        "business",
        "businesses",
        "firm",
        "firms",
        "startup",
        "startups",
        "agency",
        "agencies",
        "vendor",
        "vendors",
        "supplier",
        "suppliers",
        "provider",
        "providers",
        "saas",
        "software",
        "technology",
        "tech",
    }
)


# ---------------------------------------------------------------------------
# SearchPlan — output of QueryPlanner.build()
# ---------------------------------------------------------------------------


@dataclass
class SearchPlan:
    """Ready-to-use queries per source + resolved filter values."""

    # Resolved fields (UI filters take priority over query)
    keywords: str
    country: str
    city: str
    industry: str
    lead_type: str           # 'person' | 'company' | 'both'
    titles: List[str]        # decision-maker titles for person searches
    sources: List[str]       # ordered source list
    must_have_email: bool

    # Generated queries per source
    google_queries: List[str] = field(default_factory=list)
    linkedin_queries: List[str] = field(default_factory=list)
    news_queries: List[str] = field(default_factory=list)
    github_queries: List[str] = field(default_factory=list)

    # Negative terms in Google operator format  (e.g. "-inurl:jobs")
    negative_terms: List[str] = field(default_factory=list)

    # Raw negative words for post-collection text filtering
    negative_words: List[str] = field(default_factory=list)

    # Provenance — records where each resolved field came from
    resolved_from: Dict[str, str] = field(default_factory=dict)

    def as_debug_dict(self) -> Dict:
        """Compact serialisable summary for logging / task-status payloads."""
        return {
            "keywords": self.keywords,
            "country": self.country,
            "city": self.city,
            "industry": self.industry,
            "lead_type": self.lead_type,
            "titles": self.titles[:5],
            "sources": self.sources,
            "must_have_email": self.must_have_email,
            "google_queries": self.google_queries[:3],
            "linkedin_queries": self.linkedin_queries[:2],
            "news_queries": self.news_queries[:2],
            "github_queries": self.github_queries[:2],
            "negatives_count": len(self.negative_terms),
            "resolved_from": self.resolved_from,
        }


# ---------------------------------------------------------------------------
# QueryPlanner
# ---------------------------------------------------------------------------


class QueryPlanner:
    """
    Combine a free-text user query with structured UI filters into a
    SearchPlan that every collection source can consume directly.

    Priority rule: explicit filter values always override anything
    inferred or guessed from the free-text query.
    """

    @classmethod
    def build(cls, query: str, filters: Optional[Dict] = None) -> "SearchPlan":
        """
        Build a SearchPlan.

        Parameters
        ----------
        query   : str   — user's free-text search term
        filters : dict  — optional structured UI filters:
            country        str        — target country name (overrides query)
            city           str        — target city (overrides query)
            industry       str        — industry / niche
            lead_type      str        — 'person' | 'company' | 'both'
            titles         list[str]  — target job titles for person searches
            sources        list[str]  — which sources to use
            email_required bool       — only include leads with email
        """
        f = filters or {}
        q = (query or "").strip()

        # ── Resolve each field (filter wins over inferred) ───────────────
        country = (f.get("country") or "").strip()
        city = (f.get("city") or "").strip()
        industry = (f.get("industry") or "").strip()
        titles = [str(t).strip() for t in (f.get("titles") or []) if str(t).strip()]
        sources = [
            str(s).strip().lower() for s in (f.get("sources") or []) if str(s).strip()
        ]
        must_have_email = bool(f.get("email_required", False))

        raw_lt = (f.get("lead_type") or "").strip().lower()
        if raw_lt in ("person", "people"):
            lead_type, lt_src = "person", "filter"
        elif raw_lt in ("company", "companies"):
            lead_type, lt_src = "company", "filter"
        else:
            lead_type, lt_src = cls._detect_lead_type(q), "detected"

        if not titles and lead_type == "person":
            titles = list(_DEFAULT_TITLES)

        if not sources:
            sources = ["linkedin", "web", "news", "github"]

        resolved_from = {
            "country": "filter" if f.get("country") else "none",
            "city": "filter" if f.get("city") else "none",
            "industry": "filter" if f.get("industry") else "none",
            "lead_type": lt_src,
            "titles": "filter" if f.get("titles") else "default",
            "sources": "filter" if f.get("sources") else "default",
        }

        return SearchPlan(
            keywords=q,
            country=country,
            city=city,
            industry=industry,
            lead_type=lead_type,
            titles=titles,
            sources=sources,
            must_have_email=must_have_email,
            google_queries=cls._build_google(
                q, country, city, industry, lead_type, titles, must_have_email
            ),
            linkedin_queries=cls._build_linkedin(q, country, city, lead_type, titles),
            news_queries=cls._build_news(q, country, city),
            github_queries=cls._build_github(q, country, lead_type, titles),
            negative_terms=list(_NEG_WEB),
            negative_words=list(_NEG_WORDS),
            resolved_from=resolved_from,
        )

    # ------------------------------------------------------------------
    # Lead type detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_lead_type(query: str) -> str:
        ql = query.lower()
        p = sum(1 for s in _PERSON_SIGNALS if s in ql)
        c = sum(1 for s in _COMPANY_SIGNALS if s in ql)
        if p > c:
            return "person"
        if c > p:
            return "company"
        return "both"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _q(s: str) -> str:
        """Wrap a non-empty string in double quotes for exact-phrase matching."""
        return f'"{s}"' if s else ""

    @staticmethod
    def _loc(country: str, city: str) -> str:
        """Compact location fragment with quoted parts."""
        parts = []
        if city:
            parts.append(f'"{city}"')
        if country:
            parts.append(f'"{country}"')
        return " ".join(parts)

    @staticmethod
    def _dedup(queries: List[str], cap: int = 8) -> List[str]:
        """Deduplicate and normalise whitespace; cap at `cap` items."""
        seen: set = set()
        out: List[str] = []
        for q in queries:
            clean = " ".join(q.split())
            if clean and clean not in seen:
                seen.add(clean)
                out.append(clean)
            if len(out) >= cap:
                break
        return out

    @classmethod
    def _neg(cls, n: int = 10) -> str:
        """Return the first n negative operator terms as a space-joined string."""
        return " ".join(_NEG_WEB[:n])

    # ------------------------------------------------------------------
    # Google / web query builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_google(
        cls,
        keywords: str,
        country: str,
        city: str,
        industry: str,
        lead_type: str,
        titles: List[str],
        must_have_email: bool,
    ) -> List[str]:
        kw = cls._q(keywords)
        loc = cls._loc(country, city)
        ind = cls._q(industry) if industry else ""
        neg = cls._neg(6)
        em = " email contact" if must_have_email else ""

        qs: List[str] = []

        if lead_type in ("person", "both"):
            ts = (
                " OR ".join(cls._q(t) for t in titles[:4])
                if titles
                else '"CEO" OR "Founder"'
            )
            qs += [
                f"site:linkedin.com/in {kw} {loc} {ts}",
                f"{kw} {ind} {ts} {loc}{em} {neg}",
                f"intitle:team {kw} {loc} {ind} {neg}",
                f'{kw} {loc} "leadership" OR "management team" {neg}',
            ]

        if lead_type in ("company", "both"):
            qs += [
                f"{kw} {ind} companies {loc} contact email {neg}",
                f"intitle:about {kw} {loc} {neg}",
                f"intitle:contact {kw} {loc} {ind} {neg}",
                f"{kw} {ind} {loc} phone website {neg}",
            ]

        if must_have_email:
            qs.append(f'{kw} {loc} "@" email contact {neg}')

        return cls._dedup(qs)

    # ------------------------------------------------------------------
    # LinkedIn query builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_linkedin(
        cls,
        keywords: str,
        country: str,
        city: str,
        lead_type: str,
        titles: List[str],
    ) -> List[str]:
        loc = country or city
        ts = (
            " OR ".join(cls._q(t) for t in titles[:4])
            if titles
            else '"CEO" OR "Founder"'
        )
        neg = "-inurl:jobs -inurl:search -inurl:feed"

        qs: List[str] = []

        if lead_type in ("person", "both"):
            qs += [
                f'site:linkedin.com/in "{keywords}" "{loc}" {ts} {neg}',
                f'site:linkedin.com/in {ts} "{keywords}" "{loc}"',
                f'linkedin.com/in/ "{keywords}" {ts} "{loc}" professional',
            ]

        if lead_type in ("company", "both"):
            qs += [
                f'site:linkedin.com/company "{keywords}" "{loc}"',
                f'linkedin.com/company "{keywords}" "{loc}"',
            ]

        return cls._dedup(qs, cap=5)

    # ------------------------------------------------------------------
    # News query builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_news(cls, keywords: str, country: str, city: str) -> List[str]:
        kw = cls._q(keywords)
        loc = cls._q(country) if country else (cls._q(city) if city else "")
        neg = '-"obituary" -"sports" -"weather" -site:facebook.com'

        qs = [
            f"{kw} startup {loc} founder funding {neg}",
            f"{kw} company raises funding {loc}",
            f"{kw} announces expansion {loc}",
            f"{kw} appoints CEO OR CTO {loc}",
            f"{kw} {loc} press release",
        ]
        return cls._dedup(qs, cap=5)

    # ------------------------------------------------------------------
    # GitHub query builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_github(
        cls,
        keywords: str,
        country: str,
        lead_type: str,
        titles: List[str],
    ) -> List[str]:
        kw = cls._q(keywords)
        loc = cls._q(country) if country else ""

        qs = [
            f"{kw} {loc} founder github",
            f"{kw} developer founder {loc}",
        ]
        if "CTO" in titles or lead_type == "person":
            qs.append(f"{kw} CTO {loc} github")
        if lead_type in ("company", "both"):
            qs.append(f"{kw} {loc} open source project github")

        return cls._dedup(qs, cap=4)
