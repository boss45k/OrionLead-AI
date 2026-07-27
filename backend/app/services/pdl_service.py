"""
People Data Labs (PDL) person enrichment service.

Quality rules:
  • All returned data is tagged with enrichment_source='pdl'
  • enrichment_completeness is calculated from non-empty fields
  • enriched_at timestamp is added for freshness tracking
  • enrich_lead() only fills blank fields — never overwrites verified data
  • Returns None when not found — never fabricates data
  • LinkedIn URL returned as-is from PDL (authoritative)
  • Email from PDL tagged with email_source='pdl' and email_verified=True
    (PDL databases are sourced from professional networks — high confidence)
"""
import os
import logging
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

PDL_BASE_URL = "https://api.peopledatalabs.com/v5"

_BLANK = frozenset(("", "N/A", "n/a", "unknown", "null", "None", "none"))


def _blank(v: Any) -> bool:
    return not v or str(v).strip() in _BLANK


def _enrichment_completeness(data: Dict[str, Any], fields: List[str]) -> float:
    if not fields:
        return 0.0
    filled = sum(1 for f in fields if not _blank(data.get(f)))
    return round(filled / len(fields), 2)


class PDLService:
    def __init__(self):
        self.api_key = os.getenv('PDL_API_KEY', '').strip()
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({'X-Api-Key': self.api_key})

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def enrich_person(
        self,
        email: str = '',
        linkedin_url: str = '',
        name: str = '',
        company: str = '',
    ) -> Optional[Dict[str, Any]]:
        """
        Enrich a person from email, LinkedIn URL, or name+company.

        Returns a structured dict with enrichment metadata, or None.
        """
        if not self.is_configured():
            return None

        params: Dict[str, Any] = {'pretty': 'false'}
        if email:
            params['email'] = email
        elif linkedin_url:
            params['linkedin_url'] = linkedin_url
        elif name and company:
            params['name']    = name
            params['company'] = company
        else:
            return None

        try:
            resp = self.session.get(
                f"{PDL_BASE_URL}/person/enrich",
                params=params,
                timeout=10,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            d = resp.json()

            emails   = d.get('emails') or []
            email_v  = emails[0].get('address', '') if emails else ''
            loc_list = d.get('location_names') or []

            result = {
                'name':              d.get('full_name', ''),
                'email':             email_v,
                'company':           d.get('job_company_name', ''),
                'position':          d.get('job_title', ''),
                'industry':          d.get('industry', ''),
                'linkedin_url':      d.get('linkedin_url', ''),
                'country':           d.get('location_country', ''),
                'city':              d.get('location_locality', ''),
                'location':          loc_list[0] if loc_list else '',
                'company_size':      d.get('job_company_size', ''),
                'source':            'pdl',
                # Enrichment metadata
                'enrichment_source': 'pdl',
                'enriched_at':       datetime.now(timezone.utc).isoformat(),
                'enrichment_completeness': _enrichment_completeness(
                    {
                        'email': email_v, 'company': d.get('job_company_name'),
                        'position': d.get('job_title'), 'industry': d.get('industry'),
                        'linkedin_url': d.get('linkedin_url'), 'country': d.get('location_country'),
                    },
                    ['email', 'company', 'position', 'industry', 'linkedin_url', 'country'],
                ),
            }
            # Email metadata: PDL emails are from professional profiles — mark as verified
            if email_v:
                result['email_source']   = 'pdl'
                result['email_verified'] = True
                result['email_type']     = 'personal_business'

            return result
        except Exception as exc:
            logger.warning(f"[PDL] enrich_person error: {exc}")
            return None

    def enrich_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fill missing fields on an existing lead dict using PDL.
        Only overwrites blank / placeholder fields.
        Tags data_points with enrichment metadata.
        """
        enriched = self.enrich_person(
            email        = lead.get('email', ''),
            linkedin_url = lead.get('linkedin_url', ''),
            name         = lead.get('name', ''),
            company      = lead.get('company', ''),
        )
        if not enriched:
            return lead

        result = dict(lead)
        enriched_fields: List[str] = []

        for field in ('email', 'company', 'position', 'industry',
                      'linkedin_url', 'country', 'city', 'location', 'company_size'):
            if _blank(result.get(field)) and not _blank(enriched.get(field)):
                result[field] = enriched[field]
                enriched_fields.append(field)

        # Propagate email metadata to data_points if email was filled
        dp = result.setdefault('data_points', {})
        if 'email' in enriched_fields and enriched.get('email_verified'):
            dp['email_verified'] = True
            dp['email_source']   = 'pdl'
            dp['email_type']     = 'personal_business'

        if enriched_fields:
            dp['enrichment_source']       = 'pdl'
            dp['enriched_at']             = enriched['enriched_at']
            dp['enriched_fields']         = list(set(enriched_fields))
            dp['enrichment_completeness'] = enriched['enrichment_completeness']
            logger.info(
                f"[PDL] enriched {len(enriched_fields)} fields for "
                f"'{lead.get('name') or lead.get('email')}': {enriched_fields}"
            )

        return result


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[PDLService] = None


def get_pdl_service() -> PDLService:
    global _instance
    if _instance is None:
        _instance = PDLService()
    return _instance


def is_pdl_configured() -> bool:
    return bool(os.getenv('PDL_API_KEY', '').strip())
