"""
Clearbit enrichment service.

Quality rules:
  • All returned data is tagged with enrichment_source='clearbit'
  • enrichment_completeness is calculated from non-empty fields
  • enriched_at timestamp is added for freshness tracking
  • LinkedIn URL is built from handle only when handle is non-empty
  • company_size stores the integer count (not stringified, not empty string)
  • enrich_lead() only fills blank fields — never overwrites verified data
  • Returns None / {} when the API call fails — never fabricates data
"""
import os
import logging
import requests
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CLEARBIT_BASE = "https://api.clearbit.com/v2"

_BLANK = frozenset(("", "N/A", "n/a", "NA", "na", "null", "None", "none", "unknown"))


def _key() -> str:
    return os.getenv("CLEARBIT_API_KEY", "").strip()


def is_clearbit_configured() -> bool:
    return bool(_key())


def _blank(v: Any) -> bool:
    return not v or str(v).strip() in _BLANK


def _enrichment_completeness(data: Dict[str, Any], fields: List[str]) -> float:
    """Return 0-1 fraction of expected fields that are non-empty."""
    if not fields:
        return 0.0
    filled = sum(1 for f in fields if not _blank(data.get(f)))
    return round(filled / len(fields), 2)


class ClearbitService:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "AI-Lead-Collection-System/1.0"

    def is_configured(self) -> bool:
        return is_clearbit_configured()

    def _auth(self):
        return (_key(), "")

    # ── Person enrichment ────────────────────────────────────────────────────

    def enrich_person(self, email: str) -> Dict[str, Any]:
        if not self.is_configured() or not email:
            return {}
        try:
            r = self.session.get(
                f"{CLEARBIT_BASE}/people/find",
                params={"email": email},
                auth=self._auth(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404, 422):
                return {}
            logger.warning(f"[Clearbit] person lookup {r.status_code}: {r.text[:120]}")
        except Exception as exc:
            logger.warning(f"[Clearbit] enrich_person error: {exc}")
        return {}

    # ── Company enrichment ───────────────────────────────────────────────────

    def enrich_company(self, domain: str) -> Dict[str, Any]:
        if not self.is_configured() or not domain:
            return {}
        try:
            r = self.session.get(
                f"{CLEARBIT_BASE}/companies/find",
                params={"domain": domain},
                auth=self._auth(),
                timeout=10,
            )
            if r.status_code == 200:
                return self._normalize_company(r.json())
            if r.status_code in (404, 422):
                return {}
            logger.warning(f"[Clearbit] company lookup {r.status_code}: {r.text[:120]}")
        except Exception as exc:
            logger.warning(f"[Clearbit] enrich_company error: {exc}")
        return {}

    def _normalize_company(self, data: Dict[str, Any]) -> Dict[str, Any]:
        geo = data.get("geo") or {}
        loc_parts = [geo.get("city", ""), geo.get("country", "")]

        # Company size: keep as int, don't stringify, don't default to empty
        employees = (data.get("metrics") or {}).get("employees")
        company_size = int(employees) if employees and int(employees) > 0 else None

        # LinkedIn: only build URL if we have a real handle, not just a '/'
        li_handle = (data.get("linkedin") or {}).get("handle", "").strip().strip('/')
        linkedin_url = f"https://linkedin.com/company/{li_handle}" if li_handle else ""

        return {
            "company":          data.get("name", ""),
            "industry":         (data.get("category") or {}).get("sector", ""),
            "company_size":     company_size,
            "company_size_str": _size_label(company_size),
            "website":          data.get("domain", ""),
            "location":         ", ".join(p for p in loc_parts if p),
            "country":          geo.get("country", ""),
            "city":             geo.get("city", ""),
            "linkedin_url":     linkedin_url,
            "phone":            data.get("phone", ""),
            "enrichment_source": "clearbit",
            "enriched_at":      datetime.now(timezone.utc).isoformat(),
        }

    # ── Lead enrichment (fills only blank fields) ────────────────────────────

    def enrich_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a lead dict using Clearbit.  Only fills blank / placeholder
        fields — existing good values are never overwritten.
        Tags data_points with enrichment metadata.
        Returns the (potentially updated) lead dict.
        """
        if not self.is_configured():
            return lead

        updated = dict(lead)
        dp = updated.setdefault('data_points', {})
        enriched_fields: List[str] = []

        # ── Person enrichment via email ──────────────────────────────────────
        email = lead.get("email", "")
        person = self.enrich_person(email) if email else {}
        if person:
            emp = (person.get("employment") or {})
            if _blank(updated.get("position")) and emp.get("title"):
                updated["position"] = emp["title"]
                enriched_fields.append("position")
            if _blank(updated.get("company")) and emp.get("name"):
                updated["company"] = emp["name"]
                enriched_fields.append("company")

            geo = (person.get("geo") or {})
            if _blank(updated.get("city")) and geo.get("city"):
                updated["city"] = geo["city"]
                enriched_fields.append("city")
            if _blank(updated.get("country")) and geo.get("country"):
                updated["country"] = geo["country"]
                enriched_fields.append("country")
            if _blank(updated.get("location")) and geo.get("city"):
                updated["location"] = ", ".join(
                    p for p in [geo.get("city"), geo.get("country")] if p
                )
                enriched_fields.append("location")

            # LinkedIn: only from a real, non-empty handle
            li_handle = (person.get("linkedin") or {}).get("handle", "").strip().strip('/')
            if li_handle and _blank(updated.get("linkedin_url")):
                updated["linkedin_url"] = f"https://linkedin.com/in/{li_handle}"
                enriched_fields.append("linkedin_url")

        # ── Company enrichment via domain ────────────────────────────────────
        website = lead.get("website", "")
        domain  = website.replace("https://", "").replace("http://", "").split("/")[0] if website else ""
        if not domain and email and "@" in email:
            domain = email.split("@")[1]

        if domain:
            company_data = self.enrich_company(domain)
            if company_data:
                for field in ("company", "industry", "website", "location",
                              "country", "city", "linkedin_url", "phone"):
                    val = company_data.get(field)
                    if not _blank(val) and _blank(updated.get(field)):
                        updated[field] = val
                        enriched_fields.append(field)

                # Company size: store int version and string label separately
                if company_data.get("company_size") is not None and _blank(updated.get("company_size")):
                    updated["company_size"] = company_data["company_size"]
                    updated["company_size_str"] = company_data.get("company_size_str", "")
                    enriched_fields.append("company_size")

        # ── Record enrichment metadata in data_points ─────────────────────────
        if enriched_fields:
            dp['enrichment_source'] = 'clearbit'
            dp['enriched_at']       = datetime.now(timezone.utc).isoformat()
            dp['enriched_fields']   = list(set(enriched_fields))
            dp['enrichment_completeness'] = _enrichment_completeness(
                updated,
                ['email', 'phone', 'company', 'position', 'country', 'industry', 'linkedin_url'],
            )
            logger.info(
                f"[Clearbit] enriched {len(enriched_fields)} fields for "
                f"'{lead.get('name') or lead.get('email')}': {enriched_fields}"
            )

        return updated


def _size_label(n: Optional[int]) -> str:
    if not n:
        return ''
    if n < 10:
        return '1-9'
    if n < 50:
        return '10-49'
    if n < 200:
        return '50-199'
    if n < 500:
        return '200-499'
    if n < 1000:
        return '500-999'
    if n < 5000:
        return '1000-4999'
    return '5000+'


# ── Singleton ────────────────────────────────────────────────────────────────
_instance: Optional[ClearbitService] = None


def get_clearbit_service() -> ClearbitService:
    global _instance
    if _instance is None:
        _instance = ClearbitService()
    return _instance


def get_clearbit_client():
    return get_clearbit_service()


clearbit_client = get_clearbit_service()
