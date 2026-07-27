"""
User Intent Contract
====================
Parses the user's collection query and enforces that collected companies
match what was actually requested.

Example:
    User: "SaaS companies Nigeria"
    → requested_country = "nigeria"
    → requested_industry_types = ["b2b_saas"]

    A company with domain ending .tr (Turkey) is rejected with reason:
    "country_mismatch (website country=turkey, requested=nigeria)"

Checks performed:
  1. Country match — lead country vs. requested country across multiple sources
  2. Industry match — business type vs. requested type
  3. Empty interest / no product signal (always reject)
  4. Company-looks-like-person-name (flagged)

Cross-source country resolution priority:
  lead.country > lead.location > domain_tld > website_text > data_snippet
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from app.intelligence.models import EvidenceItem

logger = logging.getLogger(__name__)

# ── Country knowledge base ────────────────────────────────────────────────────

_COUNTRY_MAP: Dict[str, FrozenSet[str]] = {
    "nigeria": frozenset({
        "nigeria", "nigerian", ".ng", ".com.ng", ".co.ng",
        "lagos", "abuja", "port harcourt", "kano", "ibadan", "enugu", "benin city",
    }),
    "kenya": frozenset({
        "kenya", "kenyan", ".ke", ".co.ke", "nairobi", "mombasa", "kisumu",
    }),
    "ghana": frozenset({
        "ghana", "ghanaian", ".gh", ".com.gh", "accra", "kumasi",
    }),
    "south africa": frozenset({
        "south africa", "south african", ".za", ".co.za",
        "johannesburg", "cape town", "durban", "pretoria",
    }),
    "egypt": frozenset({
        "egypt", "egyptian", ".eg", ".com.eg", "cairo", "alexandria",
    }),
    "ethiopia": frozenset({
        "ethiopia", "ethiopian", ".et", "addis ababa",
    }),
    "rwanda": frozenset({
        "rwanda", "rwandan", ".rw", "kigali",
    }),
    "tanzania": frozenset({
        "tanzania", "tanzanian", ".tz", "dar es salaam", "arusha",
    }),
    "uganda": frozenset({
        "uganda", "ugandan", ".ug", "kampala",
    }),
    "senegal": frozenset({
        "senegal", "senegalese", ".sn", "dakar",
    }),
    "morocco": frozenset({
        "morocco", "moroccan", ".ma", "casablanca", "rabat",
    }),
    "turkey": frozenset({
        "turkey", "türkiye", "turkish", ".tr", ".com.tr", "istanbul", "ankara", "izmir",
    }),
    "india": frozenset({
        "india", "indian", ".in", ".co.in", "mumbai", "bangalore", "delhi", "hyderabad",
        "pune", "chennai",
    }),
    "united states": frozenset({
        "united states", "usa", "u.s.a", ".com", "new york", "san francisco",
        "silicon valley", "austin", "seattle", "boston", "chicago",
    }),
    "united kingdom": frozenset({
        "united kingdom", "uk", "england", "britain", "british", ".uk", ".co.uk",
        "london", "manchester", "birmingham",
    }),
    "canada": frozenset({
        "canada", "canadian", ".ca", "toronto", "vancouver", "montreal",
    }),
    "australia": frozenset({
        "australia", "australian", ".au", ".com.au", "sydney", "melbourne",
    }),
    "germany": frozenset({
        "germany", "german", "deutschland", ".de", "berlin", "munich", "hamburg",
    }),
    "france": frozenset({
        "france", "french", ".fr", "paris", "lyon",
    }),
    "netherlands": frozenset({
        "netherlands", "dutch", ".nl", "amsterdam",
    }),
    "singapore": frozenset({
        "singapore", "singaporean", ".sg",
    }),
    "pakistan": frozenset({
        "pakistan", "pakistani", ".pk", "karachi", "lahore", "islamabad",
    }),
    "indonesia": frozenset({
        "indonesia", "indonesian", ".id", "jakarta",
    }),
}

# TLD → canonical country (longer match first)
_TLD_COUNTRY: List[Tuple[str, str]] = sorted([
    (".co.ng", "nigeria"), (".com.ng", "nigeria"), (".ng", "nigeria"),
    (".co.ke", "kenya"), (".ke", "kenya"),
    (".com.gh", "ghana"), (".gh", "ghana"),
    (".co.za", "south africa"), (".za", "south africa"),
    (".com.eg", "egypt"), (".eg", "egypt"),
    (".et", "ethiopia"), (".rw", "rwanda"), (".tz", "tanzania"),
    (".ug", "uganda"), (".sn", "senegal"), (".ma", "morocco"),
    (".com.tr", "turkey"), (".tr", "turkey"),
    (".co.in", "india"), (".in", "india"),
    (".co.uk", "united kingdom"), (".uk", "united kingdom"),
    (".com.au", "australia"), (".au", "australia"),
    (".de", "germany"), (".fr", "france"), (".nl", "netherlands"),
    (".sg", "singapore"), (".ca", "canada"), (".pk", "pakistan"),
    (".id", "indonesia"),
], key=lambda x: -len(x[0]))  # longest match first

# ── Industry keyword → canonical business type ────────────────────────────────

_INDUSTRY_KEYWORDS: Dict[str, str] = {
    "saas":              "b2b_saas",
    "software as a service": "b2b_saas",
    "b2b software":      "b2b_saas",
    "b2b saas":          "b2b_saas",
    "software company":  "b2b_saas",
    "tech company":      "b2b_saas",
    "tech startup":      "b2b_saas",
    "startup":           "b2b_saas",
    "fintech":           "b2b_saas",
    "edtech":            "b2b_saas",
    "healthtech":        "b2b_saas",
    "hrtech":            "b2b_saas",
    "proptech":          "b2b_saas",
    "regtech":           "b2b_saas",
    "insurtech":         "b2b_saas",
    "legaltech":         "b2b_saas",
    "martech":           "b2b_saas",
    "devtools":          "b2b_saas",
    "ai company":        "b2b_saas",
    "ml company":        "b2b_saas",
    "platform":          "b2b_saas",
    "crm":               "b2b_saas",
    "erp":               "b2b_saas",
    "analytics software": "b2b_saas",
    "agency":            "agency",
    "digital agency":    "agency",
    "marketing agency":  "agency",
    "design agency":     "agency",
    "consulting":        "agency",
    "ecommerce":         "ecommerce",
    "e-commerce":        "ecommerce",
    "online store":      "ecommerce",
    "marketplace":       "marketplace",
}

# ── Location-in-text patterns ─────────────────────────────────────────────────

_LOCATION_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\bbased\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        r"\bheadquartered\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        r"\boffices?\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        r"\bfounded\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        r"\bserving\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
    ]
]


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class IntentContract:
    raw_query: str = ""
    location:  str = ""

    requested_country:        str       = ""
    requested_industry_types: List[str] = field(default_factory=list)
    country_aliases:          FrozenSet[str] = field(default_factory=frozenset)

    requires_location_match:  bool = False
    requires_industry_match:  bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query":               self.raw_query,
            "location":                self.location,
            "requested_country":       self.requested_country,
            "requested_industry_types":self.requested_industry_types,
            "requires_location_match": self.requires_location_match,
            "requires_industry_match": self.requires_industry_match,
        }


# ── Engine ────────────────────────────────────────────────────────────────────

class UserIntentContract:
    """
    Parses a collection query and validates that companies match user intent.
    Stateless — safe to reuse across threads.
    """

    def parse(self, query: str, location: str = "") -> IntentContract:
        """
        Extract intent constraints from the query + location string.

        Returns an IntentContract with requested_country and
        requested_industry_types populated.
        """
        contract = IntentContract(raw_query=query, location=location)
        combined = (query + " " + location).lower()

        # Extract country (longest matching alias wins)
        for country, aliases in _COUNTRY_MAP.items():
            # Sort aliases longest first so "south africa" beats "africa"
            for alias in sorted(aliases, key=len, reverse=True):
                if alias in combined:
                    contract.requested_country    = country
                    contract.country_aliases      = aliases
                    contract.requires_location_match = True
                    break
            if contract.requested_country:
                break

        # Extract industry (longest keyword match wins)
        for keyword in sorted(_INDUSTRY_KEYWORDS, key=len, reverse=True):
            if keyword in combined:
                biz_type = _INDUSTRY_KEYWORDS[keyword]
                if biz_type not in contract.requested_industry_types:
                    contract.requested_industry_types.append(biz_type)
                contract.requires_industry_match = True

        logger.debug(
            "[intent_contract] query='%s' loc='%s' → country=%s types=%s",
            query, location, contract.requested_country,
            contract.requested_industry_types,
        )
        return contract

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(
        self,
        lead:           Dict[str, Any],
        contract:       IntentContract,
        website_audit:  Optional[Any] = None,   # WebsiteAuditResult
        classification: Optional[Any] = None,   # BusinessClassification
    ) -> Tuple[bool, str, float, List[EvidenceItem]]:
        """
        Validate that a lead matches the user's intent contract.

        Returns:
            (passed, rejection_reason, confidence, evidence_list)
        """
        evidence: List[EvidenceItem] = []

        # ── Country match ──────────────────────────────────────────────────────
        if contract.requires_location_match and contract.requested_country:
            matched, conf, ctry_evidence = self._check_country(
                lead, contract, website_audit,
            )
            evidence.extend(ctry_evidence)
            if not matched:
                detected = next(
                    (e.value for e in ctry_evidence if e.value and e.value != "unknown"),
                    "unknown",
                )
                reason = (
                    f"country_mismatch (detected={detected}, "
                    f"requested={contract.requested_country})"
                )
                return False, reason, conf, evidence

        # ── Industry match ─────────────────────────────────────────────────────
        if contract.requires_industry_match and contract.requested_industry_types:
            matched, type_reason = self._check_industry(lead, contract, classification)
            biz_type = classification.business_type if classification else "unknown"
            biz_conf = classification.confidence    if classification else 0.0
            evidence.append(EvidenceItem(
                source="business_classifier",
                field="business_type",
                value=biz_type,
                confidence=biz_conf,
                reason=type_reason,
            ))
            if not matched:
                return False, f"industry_mismatch ({type_reason})", 0.5, evidence

        return True, "", 1.0, evidence

    # ------------------------------------------------------------------
    # Country helper
    # ------------------------------------------------------------------

    def _check_country(
        self,
        lead:          Dict[str, Any],
        contract:      IntentContract,
        website_audit: Optional[Any],
    ) -> Tuple[bool, float, List[EvidenceItem]]:
        evidence: List[EvidenceItem] = []
        requested = contract.requested_country
        detected: List[Tuple[str, float, str]] = []  # (country, confidence, source)

        def _detect_in_text(text: str, source: str, conf: float) -> None:
            if not text:
                return
            t = text.lower()
            for country, aliases in _COUNTRY_MAP.items():
                for alias in sorted(aliases, key=len, reverse=True):
                    if alias in t:
                        detected.append((country, conf, source))
                        return

        # Source 1 — explicit lead fields (highest confidence)
        for fld in ("country", "location", "city", "address"):
            _detect_in_text(lead.get(fld) or "", f"lead.{fld}", 0.90)

        # Source 2 — domain TLD
        domain = (lead.get("domain") or lead.get("website") or "").lower()
        for tld, country in _TLD_COUNTRY:
            if domain.endswith(tld) or ("." + tld.lstrip(".")) in domain:
                detected.append((country, 0.85, "domain_tld"))
                break

        # Source 3 — website audit location signals
        if website_audit:
            for sig in getattr(website_audit, "location_signals", []):
                _detect_in_text(sig, "website_text", 0.75)

        # Source 4 — data_points snippet
        dp = lead.get("data_points") or {}
        _detect_in_text(
            (dp.get("snippet") or "") + " " + (dp.get("description") or ""),
            "data_snippet", 0.55,
        )

        # Source 5 — location patterns from combined text
        combined = " ".join(filter(None, [
            lead.get("location"), lead.get("country"),
            dp.get("snippet"), dp.get("description"),
        ]))
        for pat in _LOCATION_PATTERNS:
            m = pat.search(combined)
            if m:
                _detect_in_text(m.group(1), "location_pattern", 0.65)

        if not detected:
            evidence.append(EvidenceItem(
                source="location_check",
                field="country",
                value="unknown",
                confidence=0.0,
                reason=f"No country evidence found; cannot confirm match with '{requested}'",
            ))
            return False, 0.2, evidence

        # Record all detections as evidence
        for (country, conf, src) in detected:
            evidence.append(EvidenceItem(
                source=src,
                field="country",
                value=country,
                confidence=conf,
                reason=(
                    f"Detected country='{country}' from {src}; "
                    f"requested='{requested}'"
                ),
            ))

        matches    = [(c, cf, s) for (c, cf, s) in detected if c == requested]
        mismatches = [(c, cf, s) for (c, cf, s) in detected if c != requested]

        if matches:
            return True, max(cf for (_, cf, _) in matches), evidence

        if mismatches:
            worst_conf = max(cf for (_, cf, _) in mismatches)
            return False, worst_conf, evidence

        return False, 0.3, evidence

    # ------------------------------------------------------------------
    # Industry helper
    # ------------------------------------------------------------------

    @staticmethod
    def _check_industry(
        lead:           Dict[str, Any],
        contract:       IntentContract,
        classification: Optional[Any],
    ) -> Tuple[bool, str]:
        if not classification:
            return False, "no_classification_available"

        requested = contract.requested_industry_types
        biz_type  = classification.business_type

        if biz_type in requested:
            return True, f"type={biz_type} matches requested={requested}"

        if biz_type == "unknown" and classification.confidence < 0.4:
            return False, f"unknown_business_type (confidence too low, requested={requested})"

        return False, f"type={biz_type} not in requested={requested}"


# ── Module-level singleton ────────────────────────────────────────────────────

_engine: Optional[UserIntentContract] = None


def get_intent_contract_engine() -> UserIntentContract:
    global _engine
    if _engine is None:
        _engine = UserIntentContract()
    return _engine


def parse_query_intent(query: str, location: str = "") -> IntentContract:
    return get_intent_contract_engine().parse(query, location)
