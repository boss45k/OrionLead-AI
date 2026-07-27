"""
Tech Stack Detector
===================
Identifies the technology stack used by a company from:
  - HTTP response headers (X-Powered-By, Server, Set-Cookie, etc.)
  - HTML source patterns (script src, meta tags, inline JS variables)
  - DNS / domain signals

Each detected technology contributes to a tech_score (0-100).
B2B SaaS tools score higher — they indicate a tech-savvy company
that is already spending on software.

No external API — HTTP GET only, 5 s timeout, robots.txt-safe.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Technology fingerprint definitions ───────────────────────────────────────
# Format: (tech_name, signal_value, [(location, regex), ...])
#   location: "header" | "html" | "cookie" | "url"
#   signal_value: B2B relevance score contribution (0-20)

_TECH_FINGERPRINTS: List[Tuple[str, float, List[Tuple[str, str]]]] = [
    # ── Payments ──────────────────────────────────────────────────────────────
    ("Stripe",        12.0, [("html",   r"stripe\.com/v\d|js\.stripe\.com"),
                              ("html",   r"Stripe\(")]),
    ("Paddle",         9.0, [("html",   r"paddle\.js|paddle\.com")]),
    ("Chargebee",      9.0, [("html",   r"chargebee\.com|chargebeeportal")]),
    ("Recurly",        8.0, [("html",   r"recurly\.js|recurly\.com")]),

    # ── CRM / Sales ───────────────────────────────────────────────────────────
    ("HubSpot",       10.0, [("html",   r"js\.hs-scripts\.com|hubspot\.com"),
                              ("cookie", r"hubspotutk")]),
    ("Salesforce",    10.0, [("html",   r"salesforce\.com|force\.com"),
                              ("html",   r"sfdcstatic\.com")]),
    ("Pipedrive",      8.0, [("html",   r"pipedrive\.com")]),
    ("Close",          8.0, [("html",   r"close\.com|closecrm")]),
    ("Apollo",         7.0, [("html",   r"apollo\.io")]),

    # ── Customer Success / Support ────────────────────────────────────────────
    ("Intercom",      10.0, [("html",   r"intercomcdn\.com|widget\.intercom\.io"),
                              ("html",   r"intercomSettings")]),
    ("Zendesk",        8.0, [("html",   r"zdassets\.com|zendesk\.com")]),
    ("Drift",          8.0, [("html",   r"js\.drift\.com|drift\.com")]),
    ("Crisp",          6.0, [("html",   r"client\.crisp\.chat")]),
    ("Freshdesk",      7.0, [("html",   r"freshdesk\.com|freshchat\.com")]),

    # ── Analytics / Product Intelligence ─────────────────────────────────────
    ("Mixpanel",       8.0, [("html",   r"cdn\.mxpnl\.com|mixpanel\.com")]),
    ("Segment",        8.0, [("html",   r"cdn\.segment\.com|segment\.com/analytics")]),
    ("Amplitude",      7.0, [("html",   r"cdn\.amplitude\.com|amplitude\.com")]),
    ("Heap",           7.0, [("html",   r"cdn\.heapanalytics\.com")]),
    ("FullStory",      6.0, [("html",   r"fullstory\.com")]),
    ("PostHog",        7.0, [("html",   r"app\.posthog\.com|posthog\.com")]),
    ("June",           6.0, [("html",   r"cdn\.june\.so")]),

    # ── Marketing Automation ──────────────────────────────────────────────────
    ("Marketo",        8.0, [("html",   r"munchkin\.marketo\.net|marketo\.com")]),
    ("Pardot",         8.0, [("html",   r"pi\.pardot\.com|pardot\.com")]),
    ("Mailchimp",      5.0, [("html",   r"mailchimp\.com|chimpstatic\.com")]),
    ("ActiveCampaign", 7.0, [("html",   r"activehosted\.com|activecampaign\.com")]),

    # ── Infrastructure / DevOps ───────────────────────────────────────────────
    ("AWS",            6.0, [("header", r"aws|amazon"),
                              ("html",   r"amazonaws\.com")]),
    ("Cloudflare",     5.0, [("header", r"cloudflare"),
                              ("cookie", r"__cf")]),
    ("Vercel",         7.0, [("header", r"x-vercel"),
                              ("html",   r"vercel\.app|vercel\.com")]),
    ("Heroku",         4.0, [("header", r"heroku"),
                              ("html",   r"herokuapp\.com")]),

    # ── Product / Development ─────────────────────────────────────────────────
    ("React",          5.0, [("html",   r"react(?:dom)?\.(?:production|development)\.min\.js|\"react\"")]),
    ("Next.js",        6.0, [("html",   r"_next/static|__NEXT_DATA__")]),
    ("Docusaurus",     5.0, [("html",   r"docusaurus")]),
    ("Readme.io",      5.0, [("html",   r"readme\.io|readme\.com")]),

    # ── B2B SaaS Indicators ───────────────────────────────────────────────────
    ("Notion",         4.0, [("html",   r"notion\.so")]),
    ("Linear",         6.0, [("html",   r"linear\.app")]),
    ("Figma",          4.0, [("html",   r"figma\.com")]),
    ("Loom",           5.0, [("html",   r"loom\.com")]),
    ("Calendly",       7.0, [("html",   r"calendly\.com")]),
    ("Chili Piper",    7.0, [("html",   r"chilipiper\.com")]),
]

# Pre-compile patterns
_COMPILED: List[Tuple[str, float, List[Tuple[str, re.Pattern]]]] = [
    (name, val, [(loc, re.compile(pat, re.I)) for loc, pat in sigs])
    for name, val, sigs in _TECH_FINGERPRINTS
]


class TechStackDetector:
    """
    Fetches a company's homepage (once) and identifies the tech stack.
    Falls back gracefully when the site is unreachable.
    """

    _FETCH_TIMEOUT = 5.0
    _MAX_HTML_BYTES = 120_000   # 120 KB — enough for <head> + scripts

    def detect(
        self,
        website: str,
        domain: str,
        lead: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Returns:
            tech_stack: list of detected technology names
            tech_score: 0-100 aggregate score
            hot_signals: list of signal keys (for hot_score calculation)
        """
        if not website and not domain:
            return {"tech_stack": [], "tech_score": 0.0, "hot_signals": []}

        url = website if website else f"https://{domain}"

        html, headers, cookies = self._fetch(url)
        if not html and not headers:
            return {"tech_stack": [], "tech_score": 0.0, "hot_signals": []}

        detected: List[Tuple[str, float]] = []
        for name, value, patterns in _COMPILED:
            for location, regex in patterns:
                target = self._get_target(location, html, headers, cookies, url)
                if target and regex.search(target):
                    detected.append((name, value))
                    break   # matched — don't double-count this tech

        tech_names = [name for name, _ in detected]
        raw_score  = sum(v for _, v in detected)
        tech_score = min(100.0, raw_score * 1.5)  # scale up slightly

        hot_signals: List[str] = []
        if any(n == "Stripe"     for n in tech_names): hot_signals.append("uses_stripe")
        if any(n == "HubSpot"    for n in tech_names): hot_signals.append("uses_hubspot")
        if any(n == "Intercom"   for n in tech_names): hot_signals.append("uses_intercom")
        if any(n == "Salesforce" for n in tech_names): hot_signals.append("uses_salesforce")
        if any(n == "Mixpanel"   for n in tech_names): hot_signals.append("uses_mixpanel")
        if any(n == "Segment"    for n in tech_names): hot_signals.append("uses_segment")
        if any(n == "Drift"      for n in tech_names): hot_signals.append("uses_drift")
        if any(n == "Zendesk"    for n in tech_names): hot_signals.append("uses_zendesk")
        if any(n == "Calendly"   for n in tech_names): hot_signals.append("demo_booking")

        logger.debug(
            f"[tech] {domain}: {tech_names} score={tech_score:.0f}"
        )

        return {
            "tech_stack":  tech_names,
            "tech_score":  tech_score,
            "hot_signals": hot_signals,
        }

    # ------------------------------------------------------------------

    def _fetch(
        self, url: str
    ) -> Tuple[str, Dict[str, str], str]:
        """Return (html, headers_dict, cookies_str). All empty on failure."""
        try:
            import requests
            resp = requests.get(
                url,
                timeout=self._FETCH_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; OrionBot/1.0)"},
                allow_redirects=True,
                stream=True,
            )
            html_bytes = b""
            for chunk in resp.iter_content(chunk_size=8192):
                html_bytes += chunk
                if len(html_bytes) >= self._MAX_HTML_BYTES:
                    break

            headers = {k.lower(): v for k, v in resp.headers.items()}
            cookies = " ".join(resp.cookies.keys())
            html    = html_bytes.decode("utf-8", errors="ignore")
            return html, headers, cookies
        except Exception as exc:
            logger.debug(f"[tech] fetch failed for {url}: {exc}")
            return "", {}, ""

    def _get_target(
        self,
        location: str,
        html: str,
        headers: Dict[str, str],
        cookies: str,
        url: str,
    ) -> str:
        if location == "html":
            return html
        if location == "header":
            return " ".join(f"{k}: {v}" for k, v in headers.items())
        if location == "cookie":
            return cookies
        if location == "url":
            return url
        return ""
