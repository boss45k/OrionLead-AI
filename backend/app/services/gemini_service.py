"""
AIService — PRIMARY AI PATH for all /api/v1/ai/* endpoints
===========================================================
This is the main AI service used by routes/ai.py for every user-facing AI
operation: lead qualification, email generation, pipeline chat, insights.

Fallback chain (tried in order):
  1. Gemini 2.5 Flash  (GEMINI_API_KEY)   — primary, best reasoning quality
  2. Groq llama-3.1-8b (GROQ_API_KEY)     — ultra-fast fallback
  3. Rule-based scoring                    — always available, no API required

This is NOT the QueryAgent AI path.
For agent natural-language queries see: app/llm/integration.py (LLMIntegration).
For ML scoring see: services/ml_model.py (XGBLeadScoringModel).
"""

import json
import logging
import os
import re
import time
import requests
import urllib3
from typing import Dict, Any, Optional, List

# SSL verification: disabled only in development (Windows SSL chain issues with Google APIs).
# Production always verifies — never disable globally across the process.
_SSL_VERIFY = os.getenv('FLASK_ENV', 'production') != 'development'
if not _SSL_VERIFY:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Bump when the qualify_lead prompt changes so dataset records stay traceable.
QUALIFY_PROMPT_VERSION = "v2_reasoning"


class AIService:
    """
    AI service with Gemini primary and Groq fallback.
    Falls back to rule-based responses when neither API is available.
    """

    def __init__(self):
        # Gemini (primary)
        self._gemini_key = os.getenv('GEMINI_API_KEY', '')
        self._gemini_model = 'gemini-2.5-flash'
        self._gemini_available = False

        # Groq (fallback)
        self._groq_key = os.getenv('GROQ_API_KEY', '')
        self._groq_model = 'llama-3.3-70b-versatile'
        self._groq_available = False

        # HuggingFace (last-resort fallback — simple classification tasks only)
        self._hf_key = os.getenv('HF_TOKEN', '').strip()
        self._hf_model = 'mistralai/Mistral-7B-Instruct-v0.3'
        self._hf_available = False
        self._timeout_hf = 20

        # Separate timeouts: Gemini needs thinking time, Groq is ultra-fast.
        # Gemini 2.5 Flash is a thinking model — complex prompts (lead collection,
        # full qualification) regularly take 30-60s under load.
        # Override via GEMINI_TIMEOUT / GROQ_TIMEOUT env vars if needed.
        self._timeout_gemini = int(os.getenv('GEMINI_TIMEOUT', 60))
        self._timeout_groq   = int(os.getenv('GROQ_TIMEOUT',   15))
        self._active_provider = 'rules'
        # Set by MLDecisionLayer for TIER_2 (ml_groq) routing — skip Gemini, go Groq-first
        self.prefer_fast = False
        self._init()

    def _init(self):
        if self._gemini_key:
            self._gemini_available = True
            self._active_provider = 'gemini'
            logger.info(f"AIService: Gemini PRIMARY ready (model={self._gemini_model})")
        if self._groq_key:
            self._groq_available = True
            if not self._gemini_available:
                self._active_provider = 'groq'
            logger.info(f"AIService: Groq {'FALLBACK' if self._gemini_available else 'PRIMARY'} ready (model={self._groq_model})")
        if self._hf_key:
            self._hf_available = True
            if not self._gemini_available and not self._groq_available:
                self._active_provider = 'huggingface'
            logger.info(f"AIService: HuggingFace {'LAST-RESORT' if (self._gemini_available or self._groq_available) else 'PRIMARY'} ready (model={self._hf_model})")
        if not self._gemini_available and not self._groq_available and not self._hf_available:
            logger.warning("AIService: No API keys set — using rule-based fallback")

    @property
    def is_available(self) -> bool:
        return self._gemini_available or self._groq_available or self._hf_available

    @property
    def model_name(self) -> str:
        if self._active_provider == 'gemini':
            return self._gemini_model
        if self._active_provider == 'groq':
            return self._groq_model
        return 'rules'

    @property
    def provider_name(self) -> str:
        if self._active_provider == 'gemini':
            return f'Gemini ({self._gemini_model})'
        if self._active_provider == 'groq':
            return f'Groq ({self._groq_model})'
        return 'Smart Rules'

    def health_check(self, force: bool = False) -> Dict[str, Any]:
        """Check AI API connectivity. Result is cached for 60 s to avoid blocking page loads."""
        _CACHE_TTL = 60.0
        now = time.time()
        cached = getattr(self, '_health_cache', None)
        if not force and cached is not None and (now - getattr(self, '_health_cache_ts', 0)) < _CACHE_TTL:
            return {**cached, 'cached': True}

        if not self.is_available:
            result = {
                'status': 'no_key',
                'model': None,
                'provider': 'Smart Rules',
                'note': 'Set GEMINI_API_KEY or GROQ_API_KEY in .env to enable AI',
            }
        else:
            try:
                start = time.time()
                text = self._generate('Say "ok"', max_tokens=5)
                latency = round((time.time() - start) * 1000)
                if text:
                    result = {
                        'status': 'healthy',
                        'model': self.model_name,
                        'provider': self._active_provider.capitalize(),
                        'latency_ms': latency,
                        'gemini_available': self._gemini_available,
                        'groq_available': self._groq_available,
                    }
                else:
                    result = {
                        'status': 'offline',
                        'model': self.model_name,
                        'provider': self._active_provider.capitalize(),
                        'error': 'API unreachable — using fallback',
                    }
            except Exception as e:
                _err = str(e).lower()
                if any(w in _err for w in ('connection', 'network', 'timeout', 'unreachable',
                                           'refused', 'socket', 'ssl', 'dns', 'nodename',
                                           'temporary failure', 'cannot connect')):
                    _status = 'offline'
                elif any(w in _err for w in ('api key', 'unauthorized', '401', 'invalid key',
                                              'authentication', 'permission', 'api_key')):
                    _status = 'unauthorized'
                else:
                    _status = 'error'
                result = {
                    'status': _status,
                    'model': self.model_name,
                    'provider': self._active_provider.capitalize(),
                    'error': str(e),
                }

        self._health_cache = result
        self._health_cache_ts = now
        return result

    # ========================================================================
    # LOW-LEVEL GENERATION
    # ========================================================================

    @property
    def provider_key(self) -> str:
        """Normalized short key for the active provider ('gemini', 'groq', 'rules')."""
        return self._active_provider

    def _generate(self, prompt: str, system: str = '', temperature: float = 0.7,
                  max_tokens: int = 256, thinking: bool = False,
                  prefer_fast: Optional[bool] = None) -> Optional[str]:
        """
        Generate text. Routing:
          prefer_fast=True  → Groq first (TIER_2 speed path), Gemini as backup
          prefer_fast=False → Gemini first (brain), Groq as timeout/failure fallback
        Pass prefer_fast as a parameter to avoid mutating the shared singleton.
        """
        _fast = self.prefer_fast if prefer_fast is None else prefer_fast
        if _fast:
            # TIER_2: speed path — Groq → Gemini → HuggingFace
            if self._groq_available:
                text = self._generate_groq(prompt, system, temperature, max_tokens)
                if text:
                    self._active_provider = 'groq'
                    return text
                logger.warning("Groq (fast-mode) failed — trying Gemini as rescue")
            if self._gemini_available:
                text = self._generate_gemini(prompt, system, temperature, max_tokens, thinking=False)
                if text:
                    self._active_provider = 'gemini'
                    return text
            if self._hf_available:
                text = self._generate_huggingface(prompt, system, max_tokens)
                if text:
                    self._active_provider = 'huggingface'
                    return text
        else:
            # Normal: Gemini brain first, Groq safety fallback, HuggingFace last resort
            if self._gemini_available:
                text = self._generate_gemini(prompt, system, temperature, max_tokens, thinking=thinking)
                if text:
                    self._active_provider = 'gemini'
                    return text
                logger.warning("Gemini timed out / failed — Groq safety fallback activating")
            if self._groq_available:
                text = self._generate_groq(prompt, system, temperature, max_tokens)
                if text:
                    self._active_provider = 'groq'
                    return text
                logger.warning("Groq safety fallback also failed")
            if self._hf_available:
                text = self._generate_huggingface(prompt, system, max_tokens)
                if text:
                    self._active_provider = 'huggingface'
                    return text

        return None

    # Ordered list of models to try — first available wins
    _GEMINI_MODEL_FALLBACKS = [
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-flash',
    ]

    def _generate_gemini(self, prompt: str, system: str = '', temperature: float = 0.7,
                         max_tokens: int = 256, thinking: bool = False) -> Optional[str]:
        """Call Gemini API. Returns text or None on failure.
        Tries model fallbacks automatically if the primary model returns 404/400.
        thinkingConfig is only sent for models that support it (2.5+).
        """
        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": system}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        models_to_try = (
            [self._gemini_model] +
            [m for m in self._GEMINI_MODEL_FALLBACKS if m != self._gemini_model]
        )

        for model in models_to_try:
            url = f"{GEMINI_API_URL}/{model}:generateContent?key={self._gemini_key}"

            gen_config: Dict[str, Any] = {
                "temperature": temperature,
                "maxOutputTokens": max(max_tokens * 4, 2048) if thinking else max_tokens,
            }

            # thinkingConfig (thinkingBudget: 0) is only valid for gemini-2.5+ models.
            # Sending it to older models or free-tier quotas causes a 400 error.
            if not thinking and '2.5' in model:
                gen_config["thinkingConfig"] = {"thinkingBudget": 0}

            payload = {
                "contents": contents,
                "generationConfig": gen_config,
            }

            try:
                resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"},
                                     timeout=self._timeout_gemini, verify=_SSL_VERIFY)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get('candidates', [])
                    if candidates:
                        parts = candidates[0].get('content', {}).get('parts', [])
                        text_parts = [p.get('text', '') for p in parts if 'text' in p]
                        text = ''.join(text_parts).strip()
                        if text:
                            if model != self._gemini_model:
                                logger.info(f"Gemini: using fallback model {model}")
                            return text
                    return None
                elif resp.status_code in (400, 404):
                    # Bad model name or unsupported config — try next fallback
                    logger.warning(f"Gemini model {model} error {resp.status_code}: {resp.text[:300]}")
                    continue
                else:
                    logger.warning(f"Gemini API error {resp.status_code}: {resp.text[:300]}")
                    return None
            except requests.Timeout:
                logger.warning(f"Gemini API timed out after {self._timeout_gemini}s (model={model})")
                return None
            except Exception as e:
                logger.warning(f"Gemini API call failed (model={model}): {e}")
                return None

        return None

    # Fallback model when the primary Groq model hits rate limits (higher TPM ceiling)
    _GROQ_RATELIMIT_FALLBACK = 'llama-3.1-8b-instant'

    def _generate_groq(self, prompt: str, system: str = '', temperature: float = 0.7,
                       max_tokens: int = 256) -> Optional[str]:
        """Call Groq API. Returns text or None on failure.

        On 429 (TPM rate-limit): waits 2 s then retries once with the higher-limit
        8B fallback model before giving up and letting Gemini take over.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self._groq_key}",
            "Content-Type": "application/json",
        }

        models_to_try = [self._groq_model]
        if self._groq_model != self._GROQ_RATELIMIT_FALLBACK:
            models_to_try.append(self._GROQ_RATELIMIT_FALLBACK)

        for idx, model in enumerate(models_to_try):
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            try:
                resp = requests.post(GROQ_API_URL, json=payload, headers=headers,
                                     timeout=self._timeout_groq, verify=_SSL_VERIFY)
                if resp.status_code == 429:
                    # Rate-limited: wait then try the fallback model
                    wait = 2 * (idx + 1)
                    logger.warning(
                        f"Groq 429 on {model} (TPM limit) — "
                        f"{'waiting %ds then retrying with %s' % (wait, self._GROQ_RATELIMIT_FALLBACK) if idx == 0 else 'giving up'}"
                    )
                    if idx == 0:
                        time.sleep(wait)
                    continue  # try next model in list

                if resp.status_code != 200:
                    logger.warning(f"Groq API error {resp.status_code}: {resp.text[:200]}")
                    return None

                data = resp.json()
                choices = data.get('choices', [])
                if choices:
                    if model != self._groq_model:
                        logger.info(f"Groq: used fallback model {model} (primary rate-limited)")
                    return choices[0].get('message', {}).get('content', '').strip()
                return None

            except requests.Timeout:
                logger.warning(f"Groq API timed out after {self._timeout_groq}s (model={model})")
                return None
            except Exception as e:
                logger.warning(f"Groq API call failed (model={model}): {e}")
                return None

        return None

    def _generate_huggingface(self, prompt: str, system: str = '',
                               max_tokens: int = 256) -> Optional[str]:
        """Call HuggingFace Inference API. Last-resort fallback for simple tasks.

        Uses Mistral-7B-Instruct which is usually warm and responds in <5s.
        Only suitable for short classification/extraction tasks (industry, position).
        """
        if not self._hf_key:
            return None
        # Build instruct-format prompt
        full_prompt = f"<s>[INST] {(system + chr(10)) if system else ''}{prompt} [/INST]"
        try:
            resp = requests.post(
                f'https://api-inference.huggingface.co/models/{self._hf_model}',
                headers={'Authorization': f'Bearer {self._hf_key}'},
                json={
                    'inputs': full_prompt,
                    'parameters': {
                        'max_new_tokens': min(max_tokens, 200),
                        'temperature': 0.1,
                        'return_full_text': False,
                    },
                },
                timeout=self._timeout_hf,
                verify=_SSL_VERIFY,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Response is either a list of generated_text dicts or a dict
                if isinstance(data, list) and data:
                    text = data[0].get('generated_text', '').strip()
                    return text or None
                if isinstance(data, dict):
                    return data.get('generated_text', '').strip() or None
            elif resp.status_code == 503:
                logger.warning('[hf] model loading — cold start, skipping')
            else:
                logger.warning('[hf] API error %s: %s', resp.status_code, resp.text[:120])
        except requests.Timeout:
            logger.warning('[hf] inference timed out after %ds', self._timeout_hf)
        except Exception as exc:
            logger.warning('[hf] inference error: %s', exc)
        return None

    def _parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response (handles markdown fences)"""
        if not text:
            return None
        cleaned = text.strip()
        # Strip markdown code fences
        if cleaned.startswith('```'):
            lines = cleaned.split('\n')
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip() == '```':
                    end = i
                    break
            cleaned = '\n'.join(lines[start:end])
            if cleaned.startswith('json'):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Last resort: join lines
        try:
            lines = cleaned.split('\n')
            single_line = ' '.join(l.strip() for l in lines)
            return json.loads(single_line)
        except json.JSONDecodeError:
            pass

        return None

    # ========================================================================
    # LEAD QUALIFICATION
    # ========================================================================

    def qualify_lead_fast(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Fast qualification — uses AI when available, rules as fallback."""
        if self.is_available:
            return self.qualify_lead(lead)
        return self._rule_based_qualify(lead)

    def qualify_lead(self, lead: Dict[str, Any], prefer_fast: Optional[bool] = None) -> Dict[str, Any]:
        """AI-powered lead qualification."""
        interests = lead.get('interests', [])
        if isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except (json.JSONDecodeError, TypeError):
                interests = [interests] if interests else []
        interests_str = ', '.join(str(i) for i in interests) if interests else 'None'

        email_type   = lead.get('email_type', '') or ''
        has_website  = bool(lead.get('website'))
        has_phone    = bool(lead.get('phone'))
        has_linkedin = bool(lead.get('linkedin_url'))
        source       = lead.get('source', '') or ''
        completeness = lead.get('completeness_score', 0) or 0

        # Derive honest contact quality descriptor for the prompt
        _contact_parts = []
        if email_type in ('generated', 'generated_personal', 'generated_generic'):
            _contact_parts.append('generated/fake email (not a real contact)')
        elif email_type == 'generic':
            _contact_parts.append('generic role email (info@/contact@ — not a personal contact)')
        elif email_type in ('personal', 'personal_business', 'company'):
            _contact_parts.append('personal business email (direct contact)')
        elif email_type == 'free':
            _contact_parts.append('free email (gmail/yahoo — lower quality)')
        else:
            _contact_parts.append('no email')
        if has_phone:
            _contact_parts.append('phone number')
        if has_linkedin:
            _contact_parts.append('LinkedIn profile')
        if has_website:
            _contact_parts.append('company website')
        _contact_summary = ', '.join(_contact_parts) if _contact_parts else 'no contact data'

        prompt = f"""You are a B2B sales development expert qualifying a lead for a SaaS product.

Evaluate this lead honestly. A high score means the lead is genuinely reachable AND likely to buy. A low score means the data is too weak or the contact is not actionable.

LEAD:
- Name: {lead.get('name') or 'Unknown'}
- Title: {lead.get('position') or 'Unknown'}
- Company: {lead.get('company') or 'Unknown'}
- Industry: {lead.get('industry') or 'Unknown'}
- Country: {lead.get('country') or 'Unknown'}
- Contact channels: {_contact_summary}
- Interests / intent signals: {interests_str}
- Lead source: {source or 'unknown'} | Profile completeness: {int(completeness)}%

SCORING PRINCIPLES (think holistically, not as a checklist):
- A lead with ONLY a generic email (info@, contact@) and nothing else is NOT actionable — score 25-40
- A lead with no identifiable person (no name / no title) loses most of its value — score 30-50
- A C-suite or VP contact with a personal business email is the gold standard — score 70-90
- Missing industry or company info should lower confidence, not be assumed as neutral
- Interests and intent signals can push a borderline lead up if they match B2B SaaS buying patterns
- Be specific: say WHY this lead scores where it does, not just what data is present

THRESHOLDS: Hot ≥ 80 (ready for direct outreach), Warm 60-79 (needs nurturing), Cold < 60 (low priority or not actionable)

Return ONLY JSON:
{{"score": <0-100>, "category": "<Hot|Warm|Cold>", "confidence": <0.0-1.0>, "reasoning": "<2-3 specific sentences explaining the score based on THIS lead's actual data>", "strengths": ["<max 3 concrete strengths>"], "weaknesses": ["<max 3 concrete gaps or risks>"], "next_action": "<one specific, actionable sentence>"}}"""

        text = self._generate(prompt, system="B2B sales qualification expert. Be honest and specific. JSON only, no markdown.",
                              temperature=0.3, max_tokens=450, prefer_fast=prefer_fast)
        result = self._parse_json(text or '')

        if result and 'score' in result:
            score = max(0, min(100, int(result['score'])))
            return {
                'score': score,
                'category': result.get('category', 'Hot' if score >= 80 else 'Warm' if score >= 60 else 'Cold'),
                'confidence': float(result.get('confidence', 0.85)),
                'reasoning': result.get('reasoning', 'AI qualification'),
                'strengths': result.get('strengths', []),
                'weaknesses': result.get('weaknesses', []),
                'next_action': result.get('next_action', ''),
                'ai_provider': self.provider_name,
                'provider_key': self.provider_key,   # short key: 'gemini' | 'groq'
                'model': self.model_name,
                'prompt_version': QUALIFY_PROMPT_VERSION,
            }

        return self._rule_based_qualify(lead)

    def _rule_based_qualify(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based qualification fallback"""
        score = 30
        strengths = []
        weaknesses = []

        if lead.get('email'):
            score += 15
            domain = lead['email'].split('@')[-1] if '@' in lead['email'] else ''
            if domain and domain not in ('gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com'):
                score += 10
                strengths.append('Business email domain')
            else:
                weaknesses.append('Personal email address')

        if lead.get('phone'):
            score += 10
            strengths.append('Phone number available')

        position = str(lead.get('position', '')).lower()
        senior = ['ceo', 'cto', 'cfo', 'coo', 'vp', 'director', 'founder', 'head', 'chief', 'president']
        if any(t in position for t in senior):
            score += 15
            strengths.append('Senior decision-maker')
        elif position:
            score += 5

        if lead.get('company'):
            score += 10
            strengths.append('Company identified')
        else:
            weaknesses.append('No company information')

        if lead.get('linkedin_url'):
            score += 5
            strengths.append('LinkedIn profile available')

        if lead.get('website'):
            score += 5

        score = min(score, 100)
        category = 'Hot' if score >= 80 else 'Warm' if score >= 60 else 'Cold'

        return {
            'score': score,
            'category': category,
            'confidence': 0.6,
            'reasoning': 'Rule-based scoring — set GEMINI_API_KEY or GROQ_API_KEY for AI analysis',
            'strengths': strengths,
            'weaknesses': weaknesses,
            'next_action': 'Enrich lead data and verify contact information',
            'ai_provider': 'Smart Rules',
            'provider_key': 'rules',
            'model': 'none',
        }

    # ========================================================================
    # LEAD INTELLIGENCE ENGINE
    # ========================================================================

    # Prompt version — bump whenever the intelligence prompt changes so DB records stay traceable
    INTELLIGENCE_PROMPT_VERSION = "v1_full_pipeline"

    # Minimum score a lead must achieve to receive recommended_action=SAVE
    INTELLIGENCE_SAVE_THRESHOLD = 70

    def lead_intelligence_analysis(
        self,
        lead: Dict[str, Any],
        website_content: str = '',
    ) -> Dict[str, Any]:
        """
        Full 8-step B2B Lead Intelligence Engine.

        Transforms raw lead/company data into a sales-ready intelligence report.
        Works like Apollo.io / Clearbit combined: validates the company, extracts
        decision-makers, classifies emails, detects buying intent, and scores
        with a strict gate (score ≥ 70 AND intent ≠ low to SAVE).

        Args:
            lead:            Lead dict from DB or collector.
            website_content: Optional pre-fetched website text (passed to the
                             prompt to improve intent analysis).

        Returns dict with keys matching the prompt output schema plus
        db_updates (fields to write back to the Lead model) and
        prompt_version for traceability.
        """
        interests = lead.get('interests', [])
        if isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except (json.JSONDecodeError, TypeError):
                interests = [interests] if interests else []
        interests_str = ', '.join(str(i) for i in interests) if interests else 'None'

        email_raw  = lead.get('email') or ''
        email_type = lead.get('email_type') or ''
        dp         = lead.get('data_points') or {}
        email_verified = dp.get('email_verified', False)

        # Build an honest contact-quality descriptor
        _contact_lines = []
        if email_raw:
            _em_label = (
                f"{email_raw} [type={email_type or 'unknown'}, "
                f"verified={'yes' if email_verified else 'no'}]"
            )
            _contact_lines.append(f"  Email: {_em_label}")
        if lead.get('phone'):
            _contact_lines.append(f"  Phone: {lead['phone']}")
        if lead.get('linkedin_url'):
            _contact_lines.append(f"  LinkedIn: {lead['linkedin_url']}")
        if lead.get('website'):
            _contact_lines.append(f"  Website: {lead['website']}")
        _contact_block = '\n'.join(_contact_lines) if _contact_lines else '  (none)'

        _site_block = ''
        if website_content:
            _site_block = (
                f"\nWEBSITE CONTENT SAMPLE (first 600 chars):\n"
                f"{website_content[:600]}"
            )

        prompt = f"""You are an expert AI Lead Intelligence Engine used in a B2B data enrichment system similar to Apollo.io, Clearbit, and ZoomInfo.

Your job is to transform raw company/contact data into a HIGH-QUALITY, VERIFIED, SALES-READY lead report.
Think like a data analyst, sales intelligence system, and fraud filter combined.

---
INPUT DATA:
  Name:       {lead.get('name') or 'Unknown'}
  Position:   {lead.get('position') or 'Unknown'}
  Company:    {lead.get('company') or 'Unknown'}
  Industry:   {lead.get('industry') or 'Unknown (infer if possible)'}
  Country:    {lead.get('country') or 'Unknown'}
  City:       {lead.get('city') or 'Unknown'}
  Source:     {lead.get('source') or 'unknown'}
  Interests:  {interests_str}
  Notes:      {lead.get('notes') or 'None'}
  Contact data:
{_contact_block}{_site_block}

---
STEP 1 — COMPANY VALIDATION
Is this a real business?
- Accept: has official website OR LinkedIn company presence, offers services/products, has contact identity.
- Reject: blog/directory listing/forum post, no clear business activity, fake-looking source.

STEP 2 — BUSINESS INTELLIGENCE EXTRACTION
Extract ONLY what is available in the data above:
company_name, website, industry (infer if missing but mark as inferred), location, phone, emails, decision_makers.

STEP 3 — DECISION MAKER DETECTION (CRITICAL)
Identify only: CEO, Founder, Owner, CTO, CMO, Head of Sales, Marketing Director, Procurement Manager.
If the person in the data IS a decision maker, list them.  If no DM exists → reduce score.

STEP 4 — EMAIL INTELLIGENCE CLASSIFICATION
HIGH VALUE: firstname@company.com, firstname.lastname@company.com
LOW VALUE (penalise -35): info@, contact@, support@, admin@, sales@, hello@
FREE PROVIDER (penalise -40): gmail.com, yahoo.com, outlook.com, hotmail.com

STEP 5 — WEBSITE & INTENT ANALYSIS
HIGH INTENT signals: "Request a quote", "Book a demo", "Contact sales", "Pricing", "Get consultation"
MEDIUM INTENT: service pages, product descriptions, business offerings
LOW INTENT: informational content only
NO INTENT: no website / no content

STEP 6 — LINKEDIN ENRICHMENT LOGIC
If a LinkedIn URL exists, extract name/title/company.  Mark linkedin_found = true.

STEP 7 — SCORING ENGINE (STRICT)
Start at 0:
+30  decision maker confirmed
+25  valid business email (personal, company domain, verified)
+20  domain is a real verified business website
+15  LinkedIn profile found
+10  strong buying intent detected
+10  contact + services pages exist
-35  generic email (info/support/contact/etc.)
-40  free email provider
-20  no website or unverifiable domain
-20  no business signals at all

STEP 8 — FINAL QUALIFICATION GATE
SAVE only if:  qualification_score >= 70  AND  buying_intent != "low" AND buying_intent != "none"  AND  at least ONE business signal (website OR decision maker OR verified email domain) exists.
Otherwise: DISCARD if score < 50, REVIEW if 50 ≤ score < 70.

---
Return ONLY valid JSON (no markdown, no explanation):
{{
  "is_lead": true/false,
  "company": "<extracted company name>",
  "website": "<url or empty>",
  "industry": "<industry string>",
  "industry_inferred": true/false,
  "location": "<city, country>",
  "decision_makers": [
    {{"name": "", "title": "", "linkedin": ""}}
  ],
  "emails": [
    {{"email": "", "type": "business|generic|free_provider|generated"}}
  ],
  "buying_intent": "high|medium|low|none",
  "buying_intent_signals": ["<signal 1>", "<signal 2>"],
  "qualification_score": 0,
  "quality_tier": "high|medium|low",
  "source_quality": "high|medium|low",
  "reasons": ["<why this lead is good or bad>"],
  "recommended_action": "SAVE|DISCARD|REVIEW"
}}"""

        system_msg = (
            "B2B Lead Intelligence Engine. "
            "Analyze strictly and honestly. "
            "Return ONLY valid JSON — no markdown, no prose."
        )

        raw = self._generate(
            prompt,
            system=system_msg,
            temperature=0.1,
            max_tokens=700,
            thinking=False,
        )
        result = self._parse_json(raw or '')

        if result and 'qualification_score' in result:
            score = max(0, min(100, int(result.get('qualification_score', 0))))
            result['qualification_score'] = score

            # Enforce the gate: if score < threshold or intent is low/none, override to DISCARD
            intent = str(result.get('buying_intent', 'none')).lower()
            action = str(result.get('recommended_action', 'REVIEW')).upper()
            if score < self.INTELLIGENCE_SAVE_THRESHOLD or intent in ('low', 'none'):
                if action == 'SAVE':
                    result['recommended_action'] = 'REVIEW' if score >= 50 else 'DISCARD'

            # Build db_updates — fields to write back to the Lead model
            db_updates: Dict[str, Any] = {}
            if result.get('company') and not lead.get('company'):
                db_updates['company'] = result['company']
            if result.get('website') and not lead.get('website'):
                db_updates['website'] = result['website']
            if result.get('industry') and not lead.get('industry'):
                db_updates['industry'] = result['industry']
            if result.get('location') and not lead.get('country'):
                _loc_parts = result['location'].split(',')
                db_updates['country'] = _loc_parts[-1].strip() if _loc_parts else result['location']

            # Merge decision-maker data: if lead has no name/position but DM was found
            dms = result.get('decision_makers') or []
            if dms and not lead.get('name'):
                first_dm = dms[0]
                if first_dm.get('name'):
                    db_updates['name'] = first_dm['name']
                if first_dm.get('title'):
                    db_updates['position'] = first_dm['title']
                if first_dm.get('linkedin') and not lead.get('linkedin_url'):
                    db_updates['linkedin_url'] = first_dm['linkedin']

            result['db_updates']       = db_updates
            result['prompt_version']   = self.INTELLIGENCE_PROMPT_VERSION
            result['ai_provider']      = self.provider_name
            result['provider_key']     = self.provider_key
            result['analyzed_at']      = datetime.now(timezone.utc).isoformat()
            return result

        # Rule-based fallback when AI returns nothing usable
        return self._rule_based_intelligence(lead)

    def _rule_based_intelligence(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rule-based fallback for lead_intelligence_analysis().
        Applies the same scoring formula without LLM.
        """
        score = 0
        reasons: List[str] = []
        emails_out: List[Dict] = []
        dms: List[Dict] = []
        buying_intent = 'none'
        _GENERIC = frozenset({
            'info', 'contact', 'hello', 'support', 'sales', 'admin',
            'team', 'marketing', 'office', 'hr', 'press',
        })
        _FREE = frozenset({'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com'})

        email_raw  = (lead.get('email') or '').lower()

        if email_raw and '@' in email_raw:
            local  = email_raw.split('@')[0]
            domain = email_raw.split('@')[1]
            if domain in _FREE:
                emails_out.append({'email': email_raw, 'type': 'free_provider'})
                score -= 40
                reasons.append('Free email provider — not a business contact')
            elif local in _GENERIC:
                emails_out.append({'email': email_raw, 'type': 'generic'})
                score -= 35
                reasons.append('Generic role email (info@/contact@) — not a personal contact')
            else:
                emails_out.append({'email': email_raw, 'type': 'business'})
                score += 25
                reasons.append('Business email address')

        position = str(lead.get('position') or '').lower()
        _DM_TITLES = ('ceo', 'cto', 'cfo', 'founder', 'owner', 'president',
                      'director', 'vp', 'head of', 'chief', 'managing')
        is_dm = any(t in position for t in _DM_TITLES)
        if is_dm:
            score += 30
            dms.append({
                'name':    lead.get('name') or '',
                'title':   lead.get('position') or '',
                'linkedin': lead.get('linkedin_url') or '',
            })
            reasons.append(f"Decision maker identified: {lead.get('position')}")
        else:
            reasons.append('No confirmed decision maker — title unknown or non-DM')

        if lead.get('website'):
            score += 20
            buying_intent = 'medium'
            reasons.append('Business website present')
        else:
            score -= 20
            reasons.append('No website — cannot verify business identity')

        if lead.get('linkedin_url'):
            score += 15
            reasons.append('LinkedIn profile present')

        if lead.get('phone'):
            reasons.append('Phone number available')

        score = max(0, min(100, score))
        action = 'SAVE' if score >= 70 and buying_intent not in ('low', 'none') else (
            'REVIEW' if score >= 50 else 'DISCARD'
        )
        tier = 'high' if score >= 70 else 'medium' if score >= 50 else 'low'
        src_q = 'high' if lead.get('source') in ('hunter', 'pdl', 'apollo') else (
            'medium' if lead.get('source') in ('public_web', 'serper') else 'low'
        )

        return {
            'is_lead':               bool(lead.get('company') or lead.get('website')),
            'company':               lead.get('company') or '',
            'website':               lead.get('website') or '',
            'industry':              lead.get('industry') or '',
            'industry_inferred':     False,
            'location':              f"{lead.get('city') or ''}, {lead.get('country') or ''}".strip(', '),
            'decision_makers':       dms,
            'emails':                emails_out,
            'buying_intent':         buying_intent,
            'buying_intent_signals': [],
            'qualification_score':   score,
            'quality_tier':          tier,
            'source_quality':        src_q,
            'reasons':               reasons,
            'recommended_action':    action,
            'db_updates':            {},
            'prompt_version':        'rule_based',
            'ai_provider':           'Smart Rules',
            'provider_key':          'rules',
            'analyzed_at':           datetime.now(timezone.utc).isoformat(),
        }

    # ========================================================================
    # LEAD ANALYSIS
    # ========================================================================

    def analyze_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Deep AI analysis of a lead."""
        interests = lead.get('interests', [])
        if isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except (json.JSONDecodeError, TypeError):
                interests = [interests] if interests else []

        prompt = f"""Analyze this B2B lead and create an outreach strategy.

Lead:
- Name: {lead.get('name','Unknown')}
- Position: {lead.get('position','Unknown')}
- Company: {lead.get('company','Unknown')}
- Industry: {lead.get('industry','Unknown')}
- Country: {lead.get('country','Unknown')}, City: {lead.get('city','Unknown')}
- Email: {lead.get('email','None')}
- Website: {lead.get('website','None')}
- Interests: {', '.join(str(i) for i in interests) if interests else 'None'}
- Current Score: {lead.get('qualification_score', 'N/A')}

Return ONLY JSON: {{"company_analysis": "<1-2 sentences>", "decision_maker_assessment": "<1 sentence>", "pain_points": ["..."], "buying_signals": ["..."], "risk_factors": ["..."], "recommended_approach": "<2 sentences>", "talking_points": ["..."], "estimated_deal_size": "<Small|Medium|Large|Enterprise>", "sales_cycle_estimate": "<Short|Medium|Long>", "priority": "<High|Medium|Low>"}}"""

        text = self._generate(prompt, system="Senior B2B sales strategist. JSON only.", temperature=0.5, max_tokens=600, thinking=True)
        result = self._parse_json(text or '')

        if result:
            return {
                'analysis': result,
                'ai_provider': self.provider_name,
                'analyzed_at': datetime.now(timezone.utc).isoformat(),
            }

        # Rule-based fallback
        is_senior = any(t in str(lead.get('position', '')).lower() for t in ['ceo', 'cto', 'cfo', 'vp', 'director', 'founder', 'head', 'chief'])
        return {
            'analysis': {
                'company_analysis': f"{lead.get('company', 'This company')} operates in the {lead.get('industry', 'general business')} sector in {lead.get('country', 'an unspecified region')}.",
                'decision_maker_assessment': f"{lead.get('name', 'This contact')} holds the position of {lead.get('position', 'professional')} — {'a key decision-maker' if is_senior else 'a relevant contact for outreach'}.",
                'pain_points': [f'Industry-specific challenges in {lead.get("industry", "their sector")}', 'Operational efficiency and growth'],
                'buying_signals': ['Lead data completeness indicates engagement potential'] + (['Senior title suggests budget authority'] if is_senior else []),
                'risk_factors': ['Requires further qualification'],
                'recommended_approach': f'Reach out via {"email" if lead.get("email") else "LinkedIn"} with a personalized message referencing their role in {lead.get("industry", "the industry")}.',
                'talking_points': [f'Industry trends in {lead.get("industry", "their field")}', f'Solutions relevant to {lead.get("position", "their role")}'],
                'estimated_deal_size': 'Medium',
                'sales_cycle_estimate': 'Medium',
                'priority': 'High' if lead.get('qualification_score', 0) and lead.get('qualification_score', 0) >= 80 else 'Medium',
            },
            'ai_provider': 'Smart Rules',
            'analyzed_at': datetime.now(timezone.utc).isoformat(),
        }

    # ========================================================================
    # EMAIL GENERATION
    # ========================================================================

    def generate_email(self, lead: Dict[str, Any], email_type: str = 'cold_outreach',
                       tone: str = 'professional', custom_context: str = '') -> Dict[str, Any]:
        """Generate personalized outreach email."""
        type_descriptions = {
            'cold_outreach': 'First contact cold outreach. Be concise, show value quickly.',
            'follow_up': 'Follow-up after no response. Reference previous outreach.',
            'meeting_request': 'Request a meeting/call. Propose specific times.',
            'value_proposition': 'Present a value proposition tailored to their industry.',
        }
        tone_instructions = {
            'professional': 'Formal and business-like.',
            'friendly': 'Warm and conversational, still professional.',
            'urgent': 'Sense of urgency without being pushy.',
            'consultative': 'Position as advisor, ask insightful questions.',
        }

        interests = lead.get('interests', [])
        if isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except (json.JSONDecodeError, TypeError):
                interests = [interests] if interests else []

        prompt = f"""Write a short {email_type.replace('_',' ')} email in a {tone} tone.

Recipient:
- Name: {lead.get('name', 'there')}
- Position: {lead.get('position', 'Professional')}
- Company: {lead.get('company', 'their company')}
- Industry: {lead.get('industry', 'business')}
- Country: {lead.get('country', '')}
- Interests: {', '.join(str(i) for i in interests) if interests else 'business solutions'}
{f'Context: {custom_context}' if custom_context else ''}

Rules: {type_descriptions.get(email_type, type_descriptions['cold_outreach'])} {tone_instructions.get(tone, tone_instructions['professional'])} Under 150 words. Clear call to action.

Return ONLY JSON: {{"subject": "<subject line>", "body": "<email text>", "call_to_action": "<CTA>", "personalization_notes": "<notes>"}}"""

        text = self._generate(prompt, system="B2B sales copywriter. JSON only.", temperature=0.7, max_tokens=300, thinking=True)
        result = self._parse_json(text or '')

        if result and 'subject' in result:
            return {
                'email': result,
                'email_type': email_type,
                'tone': tone,
                'lead_name': lead.get('name', 'Unknown'),
                'ai_provider': self.provider_name,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }

        return {
            'email': {
                'subject': f"Opportunity for {lead.get('company', 'your team')}",
                'body': f"Hi {lead.get('name', 'there')},\n\nI noticed your work at {lead.get('company', 'your company')} and wanted to reach out.\n\nWould you be open to a brief conversation?\n\nBest regards",
                'call_to_action': 'Schedule a 15-minute call',
                'personalization_notes': 'Template email — set GEMINI_API_KEY or GROQ_API_KEY for AI-generated emails',
            },
            'email_type': email_type,
            'tone': tone,
            'lead_name': lead.get('name', 'Unknown'),
            'ai_provider': 'Smart Rules',
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

    # ========================================================================
    # AI CHAT
    # ========================================================================

    def chat(self, message: str, leads_context: Optional[List[Dict]] = None,
             history: Optional[List[Dict]] = None,
             pipeline_stats: Optional[Dict] = None) -> Dict[str, Any]:
        """AI chat about leads and pipeline. Supports multi-turn via history."""
        # Build pipeline stats section
        stats_text = ''
        if pipeline_stats:
            stats_text = (
                f"\n\nPipeline stats: {pipeline_stats.get('total', '?')} total leads, "
                f"{pipeline_stats.get('hot', '?')} hot, "
                f"{pipeline_stats.get('warm', '?')} warm, "
                f"{pipeline_stats.get('contacted', '?')} contacted, "
                f"{pipeline_stats.get('converted', '?')} converted."
            )

        # Build lead list section
        leads_text = ''
        if leads_context:
            summaries = []
            for ld in leads_context[:10]:
                summaries.append(
                    f"  {ld.get('name','?')} | {ld.get('company','?')} | "
                    f"{ld.get('country','?')} | Score:{ld.get('qualification_score','?')} | {ld.get('status','?')}"
                )
            leads_text = f"\n\nTop leads by score:\n" + '\n'.join(summaries)

        # Build conversation history section (last 6 turns max)
        history_text = ''
        if history:
            turns = history[-6:]
            lines = []
            for turn in turns:
                role = 'User' if turn.get('role') == 'user' else 'Assistant'
                text = (turn.get('text') or '').strip()
                if text:
                    lines.append(f"{role}: {text}")
            if lines:
                history_text = '\n\nConversation so far:\n' + '\n'.join(lines)

        prompt = (
            f"You are an AI sales assistant helping manage a B2B lead pipeline. "
            f"Be conversational, helpful, and specific. Vary your tone and phrasing."
            f"{stats_text}{leads_text}{history_text}"
            f"\n\nUser: {message}"
            f"\n\nRespond naturally. Reference specific lead names, companies, or numbers "
            "from the data when relevant. Keep it concise (3-5 sentences max) but insightful."
        )

        text = self._generate(prompt, system="You are a helpful AI sales assistant. Respond conversationally and vary your language.", temperature=0.75, max_tokens=350, thinking=False)

        if text:
            return {
                'response': text,
                'ai_provider': self.provider_name,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }

        # Rule-based chat fallback
        response = self._rule_based_chat(message, leads_context)
        return {
            'response': response,
            'ai_provider': 'Smart Rules',
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

    def _rule_based_chat(self, message: str, leads_context: Optional[List[Dict]] = None,
                         pipeline_stats: Optional[Dict] = None) -> str:
        """Helpful response using lead data without AI."""
        msg    = message.lower()
        leads  = leads_context or []
        stats  = pipeline_stats or {}

        total_real = stats.get('total') or len(leads)
        hot_cnt    = stats.get('hot',       len([l for l in leads if str(l.get('status','')).lower() == 'hot']))
        warm_cnt   = stats.get('warm',      len([l for l in leads if str(l.get('status','')).lower() == 'warm']))
        cont_cnt   = stats.get('contacted', 0)
        conv_cnt   = stats.get('converted', 0)
        scores     = [l.get('qualification_score', 0) for l in leads if l.get('qualification_score')]
        avg_score  = round(sum(scores) / len(scores), 1) if scores else 0
        conv_rate  = round(conv_cnt / total_real * 100, 1) if total_real > 0 else 0

        if not leads and not stats:
            return "No lead data available yet. Import some leads first to get insights."

        if any(w in msg for w in ['best', 'top', 'highest', 'priority', 'hot']):
            top = sorted(leads, key=lambda x: x.get('qualification_score', 0), reverse=True)[:5]
            if top:
                lines = [f"Your top leads by qualification score (out of {total_real} total):"]
                for i, l in enumerate(top, 1):
                    lines.append(f"{i}. {l.get('name','?')} at {l.get('company','?')} — Score: {l.get('qualification_score','?')}, Status: {l.get('status','?')}")
                lines.append("Focus your outreach on these high-value contacts first.")
                return '\n'.join(lines)
            return f"You have {hot_cnt} hot leads out of {total_real} total. Start reaching out to them today."

        if any(w in msg for w in ['summary', 'overview', 'pipeline', 'status', 'total', 'how many']):
            return (
                f"Pipeline summary: {total_real} total leads — {hot_cnt} hot, {warm_cnt} warm, "
                f"{cont_cnt} contacted, {conv_cnt} converted ({conv_rate}% conversion rate). "
                f"Average score: {avg_score}. "
                f"{'Strong pipeline — keep up the outreach.' if hot_cnt >= 5 else 'Tip: enrich warm leads to push more into hot.'}"
            )

        if any(w in msg for w in ['convert', 'conversion', 'deal', 'close', 'won', 'revenue']):
            return (
                f"You have {conv_cnt} converted leads with a {conv_rate}% conversion rate. "
                f"Out of {total_real} total leads, {cont_cnt} have been contacted. "
                "Hot leads convert at 5× the rate of cold ones — prioritise your top-scored contacts."
            )

        if any(w in msg for w in ['country', 'countries', 'region', 'where', 'location']):
            countries: Dict[str, int] = {}
            for l in leads:
                c = l.get('country', 'Unknown')
                if c: countries[c] = countries.get(c, 0) + 1
            top_c = sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5]
            if top_c:
                c_str = ', '.join(f"{c} ({n})" for c, n in top_c)
                return f"Top lead markets from your pipeline: {c_str}. Focus outreach on your strongest market first."
            return "Country data not yet available for your leads."

        if any(w in msg for w in ['industry', 'industries', 'sector', 'vertical']):
            industries: Dict[str, int] = {}
            for l in leads:
                ind = l.get('industry', '')
                if ind: industries[ind] = industries.get(ind, 0) + 1
            top_i = sorted(industries.items(), key=lambda x: x[1], reverse=True)[:5]
            if top_i:
                i_str = ', '.join(f"{i} ({n})" for i, n in top_i)
                return f"Top industries in your pipeline: {i_str}. SaaS and Finance typically convert best."
            return "Industry data not yet available for your leads."

        if any(w in msg for w in ['source', 'where from', 'linkedin', 'web', 'scraping']):
            sources: Dict[str, int] = {}
            for l in leads:
                s = l.get('source', '')
                if s: sources[s] = sources.get(s, 0) + 1
            top_s = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:4]
            if top_s:
                s_str = ', '.join(f"{s} ({n})" for s, n in top_s)
                return f"Your lead sources (top 10 shown): {s_str}. LinkedIn typically delivers the highest quality leads."
            return "Source data not yet available for your leads."

        # Generic fallback — vary by making it specific to the message
        top3 = sorted(leads, key=lambda x: x.get('qualification_score', 0), reverse=True)[:3]
        top_names = ', '.join(f"{l.get('name','?')} ({l.get('company','?')})" for l in top3) if top3 else 'none yet'
        return (
            f"I can see {total_real} leads in your pipeline — {hot_cnt} hot, {warm_cnt} warm. "
            f"Top contacts: {top_names}. "
            "Ask me about: top leads, pipeline summary, conversion rate, countries, industries, or sources."
        )

    # ========================================================================
    # LEAD ENRICHMENT
    # ========================================================================

    def enrich_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use AI to infer missing lead fields from what we already know.
        Returns a dict of inferred fields. Only non-empty fields should be
        written back — caller decides which to persist.
        """
        company = lead_data.get('company', '')
        position = lead_data.get('position', '')
        website = lead_data.get('website', '')
        email = lead_data.get('email', '')
        name = lead_data.get('name', '')
        interests_raw = lead_data.get('interests', [])
        if isinstance(interests_raw, str):
            try:
                interests_raw = json.loads(interests_raw)
            except (json.JSONDecodeError, TypeError):
                interests_raw = [interests_raw] if interests_raw else []
        interests = ', '.join(str(i) for i in interests_raw) if interests_raw else 'unknown'

        # Derive what's missing so the prompt can be focused
        missing_fields = []
        if not company:
            missing_fields.append('company')
        if not position:
            missing_fields.append('position')
        if not lead_data.get('industry'):
            missing_fields.append('industry')
        if not lead_data.get('country'):
            missing_fields.append('country')
        if not lead_data.get('city'):
            missing_fields.append('city')

        prompt = f"""Infer missing details for this B2B lead from the data available.

Known data:
- Name: {name or 'unknown'}
- Company: {company or 'unknown'}
- Position title: {position or 'unknown'}
- Website: {website or 'unknown'}
- Email: {email or 'unknown'}
- Email domain: {email.split('@')[-1] if '@' in email else 'unknown'}
- Interests/keywords: {interests}
- Country: {lead_data.get('country', 'unknown')}
- City: {lead_data.get('city', 'unknown')}

Missing fields to fill: {', '.join(missing_fields) if missing_fields else 'all'}

Return ONLY JSON (use "" if you cannot infer with confidence):
{{"company": "<company name from email domain or website, or empty>", "industry": "<SaaS|FinTech|Healthcare|E-commerce|Consulting|Manufacturing|Education|Real Estate|Marketing|Technology|Other>", "position": "<normalised job title if raw title is messy or blank, else empty>", "company_size": "<startup|small|mid|large|enterprise — or empty>", "country": "<country name if inferable from domain/email/website, or empty>", "city": "<city if inferable, or empty>", "pain_points": ["<likely pain point 1>", "<likely pain point 2>"]}}"""

        text = self._generate(
            prompt,
            system="B2B data enrichment expert. JSON only, no markdown.",
            temperature=0.2,
            max_tokens=250,
        )
        result = self._parse_json(text or '')

        if result:
            result['ai_provider'] = self.provider_name
            return result

        # Rule-based fallback: infer industry from email domain / company name
        inferred: Dict[str, Any] = {'ai_provider': 'Smart Rules'}
        domain = email.split('@')[-1].lower() if '@' in email else ''
        company_lower = (company or '').lower()

        # Infer company from email domain if missing
        if not company and domain and domain not in (
            'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
            'icloud.com', 'protonmail.com', 'proton.me',
        ):
            inferred['company'] = domain.split('.')[0].capitalize()
        else:
            inferred['company'] = ''

        if not lead_data.get('industry'):
            tech_signals = ['tech', 'software', 'digital', 'app', 'cloud', 'data', 'ai', 'saas', 'dev']
            fin_signals = ['bank', 'finance', 'fintech', 'capital', 'invest', 'insurance']
            health_signals = ['health', 'medical', 'pharma', 'clinic', 'care']
            if any(s in company_lower or s in domain for s in tech_signals):
                inferred['industry'] = 'Technology'
            elif any(s in company_lower or s in domain for s in fin_signals):
                inferred['industry'] = 'Finance'
            elif any(s in company_lower or s in domain for s in health_signals):
                inferred['industry'] = 'Healthcare'
            else:
                inferred['industry'] = ''

        inferred['position'] = ''
        inferred['company_size'] = ''
        inferred['country'] = ''
        inferred['city'] = ''
        inferred['pain_points'] = []
        return inferred

    # ========================================================================
    # PIPELINE SUMMARY
    # ========================================================================

    def generate_pipeline_summary(self, stats: Dict[str, Any],
                                   sample_leads: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """AI-powered pipeline summary."""
        leads_preview = ''
        if sample_leads:
            previews = []
            for ld in sample_leads[:5]:
                previews.append(
                    f"  {ld.get('name','?')} ({ld.get('company','?')}) - "
                    f"Score:{ld.get('qualification_score','?')}, {ld.get('status','?')}, "
                    f"{ld.get('country','?')}"
                )
            leads_preview = "\nSample:\n" + '\n'.join(previews)

        prompt = f"""Analyze this sales pipeline and provide strategic insights.

Pipeline:
- Total leads: {stats.get('total',0)}
- Hot: {stats.get('hot',0)}, Warm: {stats.get('warm',0)}, Cold: {stats.get('cold',0)}
- Average score: {stats.get('avg_score',0):.0f}
- With email: {stats.get('with_email',0)}, With phone: {stats.get('with_phone',0)}
- Countries: {stats.get('countries','N/A')}
- Industries: {stats.get('top_industries','N/A')}{leads_preview}

Return ONLY JSON: {{"executive_summary": "<2 sentences>", "key_insights": ["..."], "recommendations": ["..."], "pipeline_health": "<Excellent|Good|Fair|Poor>", "immediate_actions": ["..."], "focus_countries": ["..."], "focus_industries": ["..."]}}"""

        text = self._generate(prompt, system="VP of Sales. JSON only.", temperature=0.5, max_tokens=300, thinking=True)
        result = self._parse_json(text or '')

        if result:
            return {
                'summary': result,
                'stats': stats,
                'ai_provider': self.provider_name,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }

        return {
            'summary': {
                'executive_summary': f"Pipeline contains {stats.get('total', 0)} leads with {stats.get('hot', 0)} hot opportunities and average score of {stats.get('avg_score', 0):.0f}. {'Strong pipeline.' if stats.get('hot', 0) > stats.get('total', 1) * 0.2 else 'Focus on qualifying warm leads.'}",
                'key_insights': [
                    f"{stats.get('hot', 0)} hot leads ready for immediate outreach",
                    f"{stats.get('warm', 0)} warm leads need nurturing",
                    f"Data completeness: {stats.get('with_email', 0)} have email, {stats.get('with_phone', 0)} have phone",
                ],
                'recommendations': [
                    'Prioritize outreach to hot leads this week',
                    'Enrich data for warm leads to improve qualification',
                    'Review cold leads for re-engagement',
                ],
                'pipeline_health': 'Good' if stats.get('hot', 0) >= 5 else 'Fair' if stats.get('warm', 0) >= 10 else 'Needs Attention',
                'immediate_actions': [
                    f"Contact top {min(5, stats.get('hot', 0))} hot leads",
                    'Schedule follow-ups for warm leads',
                ],
                'focus_countries': [],
                'focus_industries': [],
            },
            'stats': stats,
            'ai_provider': 'Smart Rules',
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }


# ========================================================================
# SINGLETON
# ========================================================================
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get or create the singleton AIService"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service


# Backward compatibility alias
GroqService = AIService
