"""
Ollama AI Service
Central service for all Ollama LLM operations.
Provides lead qualification, analysis, email generation, chat, and pipeline insights.
"""

import json
import logging
import os
import time
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class OllamaService:
    """
    Wrapper around the local Ollama LLM providing all AI capabilities.
    Auto-detects available models, supports retries, structured JSON output.
    """

    # Preferred models — fast CPU-friendly models first
    PREFERRED_MODELS = ['qwen2', 'tinyllama', 'phi3', 'gemma', 'mistral', 'llama3', 'llama2']

    # Set OLLAMA_FAST_MODE=true in .env to skip Ollama and use instant rule-based responses.
    # Default is False — Ollama is used when available.
    FAST_MODE = os.getenv('OLLAMA_FAST_MODE', 'false').lower() in ('true', '1', 'yes')

    def __init__(self, model: Optional[str] = None, timeout: int = 8):
        self._ollama = None
        self._model = model
        self._timeout = timeout
        self._available = False
        self._available_models: List[str] = []
        self._init()

    def _init(self):
        try:
            import ollama
            # Use Client with explicit timeout to avoid hung requests
            self._ollama = ollama.Client(timeout=self._timeout)
            # Detect available models — keep full tags (e.g. qwen2:1.5b)
            models_resp = self._ollama.list()
            raw_models = [
                (getattr(m, 'model', '') or '')
                for m in (getattr(models_resp, 'models', None) or [])
            ]
            if not raw_models and hasattr(models_resp, 'models'):
                raw_models = [
                    (getattr(m, 'model', '') or '')
                    for m in models_resp.models
                ]
            self._available_models = [m for m in raw_models if m]
            if not self._model:
                # Pick best available model — match by prefix
                for pref in self.PREFERRED_MODELS:
                    for full_name in self._available_models:
                        if full_name == pref or full_name.startswith(pref + ':'):
                            self._model = full_name
                            break
                    if self._model:
                        break
                if not self._model and self._available_models:
                    self._model = self._available_models[0]
            self._available = bool(self._model)
            if self._available:
                logger.info(f"OllamaService ready: model={self._model}, available={self._available_models}")
            else:
                logger.warning("OllamaService: no models available")
        except Exception as e:
            logger.warning(f"OllamaService init failed: {e}")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def model_name(self) -> str:
        return self._model or 'none'

    @property
    def available_models(self) -> List[str]:
        return self._available_models

    def health_check(self) -> Dict[str, Any]:
        """Check Ollama connectivity and model status"""
        if self.FAST_MODE:
            return {
                'status': 'healthy',
                'model': self._model or 'Smart Rules',
                'mode': 'fast',
                'available_models': self._available_models,
                'note': 'Running in Fast Mode (instant rule-based AI)',
            }
        if not self._available:
            return {
                'status': 'unavailable',
                'model': None,
                'available_models': [],
                'error': 'Ollama not connected',
            }
        try:
            assert self._ollama is not None
            start = time.time()
            resp = self._ollama.generate(model=self._model or 'mistral', prompt='Say "ok"', stream=False)
            latency = round((time.time() - start) * 1000)
            # Verify we got a response (Client returns GenerateResponse object)
            _ = getattr(resp, 'response', '') or resp.get('response', '') if isinstance(resp, dict) else getattr(resp, 'response', '')
            return {
                'status': 'healthy',
                'model': self._model,
                'available_models': self._available_models,
                'latency_ms': latency,
            }
        except Exception as e:
            return {
                'status': 'error',
                'model': self._model,
                'available_models': self._available_models,
                'error': str(e),
            }

    def _generate(self, prompt: str, system: str = '', temperature: float = 0.7,
                  max_retries: int = 1, max_tokens: int = 256) -> Optional[str]:
        """Low-level generate with retry logic and thread-based timeout"""
        if self.FAST_MODE:
            return None  # Skip Ollama entirely — use rule-based fallbacks
        if not self._available:
            return None

        import threading

        for attempt in range(max_retries + 1):
            result_holder: Dict[str, Any] = {'text': None, 'error': None}

            def _do_generate() -> None:
                try:
                    kwargs: Dict[str, Any] = {
                        'model': self._model,
                        'prompt': prompt,
                        'stream': False,
                        'options': {'temperature': temperature, 'num_predict': max_tokens},
                    }
                    if system:
                        kwargs['system'] = system
                    assert self._ollama is not None
                    resp = self._ollama.generate(**kwargs)
                    if isinstance(resp, dict):
                        result_holder['text'] = resp.get('response', '').strip()
                    else:
                        result_holder['text'] = getattr(resp, 'response', '').strip()
                except Exception as e:
                    result_holder['error'] = str(e)

            thread = threading.Thread(target=_do_generate)
            thread.start()
            thread.join(timeout=self._timeout)

            if thread.is_alive():
                logger.warning(f"Ollama generate timed out after {self._timeout}s (attempt {attempt+1})")
                # Thread will finish in background; we don't block further
                if attempt < max_retries:
                    time.sleep(1)
                continue

            if result_holder['error']:
                logger.warning(f"Ollama generate attempt {attempt+1} failed: {result_holder['error']}")
                if attempt < max_retries:
                    time.sleep(1)
                continue

            if result_holder['text']:
                return result_holder['text']

        return None

    def _parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response (handles markdown fences)"""
        if not text:
            return None
        # Strip markdown code fences
        cleaned = text.strip()
        if cleaned.startswith('```'):
            lines = cleaned.split('\n')
            start = 1 if lines[0].strip().startswith('```') else 0
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

        # Fix common LLM JSON issues: unescaped newlines in string values
        # Replace actual newlines inside quoted strings with \n
        try:
            fixed = re.sub(r'(?<=": ")(.*?)(?="[,\s*}])', 
                          lambda m: m.group(0).replace('\n', '\\n').replace('\r', ''),
                          cleaned, flags=re.DOTALL)
            return json.loads(fixed)
        except (json.JSONDecodeError, Exception):
            pass

        # Try to find JSON object in text
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                # Try fixing newlines in matched JSON too
                try:
                    fixed = match.group().replace('\n', '\\n').replace('\r', '')
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        # Last resort: try to extract key-value pairs manually
        try:
            # Handle case where model outputs JSON with actual newlines in values
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
        """Fast rule-based qualification for batch processing (no LLM call)."""
        return self._rule_based_qualify(lead)

    def qualify_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        AI-powered lead qualification with detailed reasoning.
        Returns score, category, reasoning, and recommended actions.
        """
        interests = lead.get('interests', [])
        if isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except (json.JSONDecodeError, TypeError):
                interests = [interests] if interests else []
        interests_str = ', '.join(str(i) for i in interests) if interests else 'None'

        prompt = f"""Rate this B2B lead on a scale of 0-100 for sales potential. Hot=80+, Warm=60-79, Cold=0-59.

Lead info:
- Name: {lead.get('name','Unknown')}
- Position: {lead.get('position','Unknown')}
- Company: {lead.get('company','Unknown')}
- Industry: {lead.get('industry','Unknown')}
- Country: {lead.get('country','Unknown')}
- Email: {lead.get('email','None')}
- Phone: {'Yes' if lead.get('phone') else 'No'}
- LinkedIn: {'Yes' if lead.get('linkedin_url') else 'No'}
- Interests: {interests_str}

Return ONLY a JSON object with these fields (fill in real values based on your analysis):
{{"score": <number 0-100>, "category": "<Hot or Warm or Cold>", "confidence": <number 0.0-1.0>, "reasoning": "<your 2-sentence explanation>", "strengths": ["<strength1>", "<strength2>"], "weaknesses": ["<weakness1>"], "next_action": "<recommended next step>"}}"""

        system = "B2B sales analyst. JSON only, no markdown."

        text = self._generate(prompt, system=system, temperature=0.3, max_retries=0, max_tokens=200)
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
                'ai_provider': f'Ollama ({self._model})',
                'model': self._model,
            }

        # Fallback: rule-based scoring
        return self._rule_based_qualify(lead)

    def _rule_based_qualify(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback rule-based qualification when LLM is unavailable"""
        score = 30
        strengths = []
        weaknesses = []

        if lead.get('email'):
            score += 15
            email_domain = lead['email'].split('@')[-1] if '@' in lead['email'] else ''
            if email_domain and email_domain not in ('gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com'):
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
            'reasoning': 'Rule-based qualification (Ollama unavailable)',
            'strengths': strengths,
            'weaknesses': weaknesses,
            'next_action': 'Enrich lead data and verify contact information',
            'ai_provider': 'Rule-based fallback',
            'model': 'none',
        }

    # ========================================================================
    # LEAD ANALYSIS
    # ========================================================================

    def analyze_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep AI analysis of a lead — company research, fit assessment,
        personalized approach strategy.
        """
        interests = lead.get('interests', [])
        if isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except (json.JSONDecodeError, TypeError):
                interests = [interests] if interests else []

        prompt = f"""Analyze this B2B lead and create an outreach strategy.

Lead info:
- Name: {lead.get('name','Unknown')}
- Position: {lead.get('position','Unknown')}
- Company: {lead.get('company','Unknown')}
- Industry: {lead.get('industry','Unknown')}
- Country: {lead.get('country','Unknown')}, City: {lead.get('city','Unknown')}
- Email: {lead.get('email','None')}
- Website: {lead.get('website','None')}
- Interests: {', '.join(str(i) for i in interests) if interests else 'None'}
- Current Score: {lead.get('qualification_score', 'N/A')}

Return ONLY a JSON object with these fields (fill in real values based on your analysis):
{{"company_analysis": "<your 1-2 sentence analysis of the company>", "decision_maker_assessment": "<your 1 sentence assessment>", "pain_points": ["<likely pain point 1>", "<likely pain point 2>"], "buying_signals": ["<signal>"], "risk_factors": ["<risk>"], "recommended_approach": "<your 2-sentence recommendation>", "talking_points": ["<point1>", "<point2>"], "estimated_deal_size": "<Small or Medium or Large or Enterprise>", "sales_cycle_estimate": "<Short or Medium or Long>", "priority": "<High or Medium or Low>"}}"""

        system = "Senior B2B sales strategist. JSON only, no markdown."

        text = self._generate(prompt, system=system, temperature=0.5, max_retries=0, max_tokens=256)
        result = self._parse_json(text or '')

        if result:
            return {
                'analysis': result,
                'ai_provider': f'Ollama ({self._model})',
                'analyzed_at': datetime.utcnow().isoformat(),
            }

        return {
            'analysis': {
                'company_analysis': f"{lead.get('company', 'This company')} operates in the {lead.get('industry', 'general business')} sector in {lead.get('country', 'an unspecified region')}.",
                'decision_maker_assessment': f"{lead.get('name', 'This contact')} holds the position of {lead.get('position', 'professional')} — {'a key decision-maker' if any(t in str(lead.get('position','')).lower() for t in ['ceo','cto','cfo','vp','director','founder','head','chief']) else 'a relevant contact for outreach'}.",
                'pain_points': [f'Industry-specific challenges in {lead.get("industry", "their sector")}', 'Operational efficiency and growth'],
                'buying_signals': ["Lead data completeness indicates engagement potential"] + (['Senior title suggests budget authority'] if any(t in str(lead.get('position','')).lower() for t in ['ceo','cto','cfo','vp','director','founder']) else []),
                'risk_factors': ['Requires further qualification'],
                'recommended_approach': f'Reach out via {"email" if lead.get("email") else "LinkedIn"} with a personalized message referencing their role in {lead.get("industry", "the industry")}.',
                'talking_points': [f'Industry trends in {lead.get("industry", "their field")}', f'Solutions relevant to {lead.get("position", "their role")}'],
                'estimated_deal_size': 'Medium',
                'sales_cycle_estimate': 'Medium',
                'priority': 'High' if lead.get('qualification_score', 0) and lead.get('qualification_score', 0) >= 80 else 'Medium',
            },
            'ai_provider': 'Smart Rules',
            'analyzed_at': datetime.utcnow().isoformat(),
        }

    # ========================================================================
    # EMAIL GENERATION
    # ========================================================================

    def generate_email(self, lead: Dict[str, Any], email_type: str = 'cold_outreach',
                       tone: str = 'professional', custom_context: str = '') -> Dict[str, Any]:
        """
        Generate a personalized outreach email for a lead.
        
        email_type: cold_outreach | follow_up | meeting_request | value_proposition
        tone: professional | friendly | urgent | consultative
        """
        type_descriptions = {
            'cold_outreach': 'First contact cold outreach email. Be concise, show value quickly.',
            'follow_up': 'Follow-up email after no response. Reference the previous outreach.',
            'meeting_request': 'Request a meeting/call. Propose specific times and agenda.',
            'value_proposition': 'Present a specific value proposition tailored to their industry.',
        }
        type_desc = type_descriptions.get(email_type, type_descriptions['cold_outreach'])

        tone_instructions = {
            'professional': 'Keep it formal and business-like.',
            'friendly': 'Be warm and conversational, but still professional.',
            'urgent': 'Create a sense of urgency without being pushy.',
            'consultative': 'Position yourself as an advisor, ask insightful questions.',
        }
        tone_desc = tone_instructions.get(tone, tone_instructions['professional'])

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
{f'Additional context: {custom_context}' if custom_context else ''}

Rules: {type_desc} {tone_desc} Keep under 150 words. Include a clear call to action.

Return ONLY a JSON object with these fields:
{{"subject": "<compelling email subject line>", "body": "<the full email text with newlines as backslash-n>", "call_to_action": "<specific call to action>", "personalization_notes": "<what you personalized and why>"}}"""

        system = "B2B sales copywriter. JSON only, no markdown."

        text = self._generate(prompt, system=system, temperature=0.7, max_retries=0, max_tokens=256)
        result = self._parse_json(text or '')

        if result and 'subject' in result:
            return {
                'email': result,
                'email_type': email_type,
                'tone': tone,
                'lead_name': lead.get('name', 'Unknown'),
                'ai_provider': f'Ollama ({self._model})',
                'generated_at': datetime.utcnow().isoformat(),
            }

        return {
            'email': {
                'subject': f"Opportunity for {lead.get('company', 'your team')}",
                'body': f"Hi {lead.get('name', 'there')},\n\nI noticed your work at {lead.get('company', 'your company')} and wanted to reach out.\n\nWould you be open to a brief conversation?\n\nBest regards",
                'call_to_action': 'Schedule a 15-minute call',
                'personalization_notes': 'Fallback template — AI unavailable',
            },
            'email_type': email_type,
            'tone': tone,
            'lead_name': lead.get('name', 'Unknown'),
            'ai_provider': 'Smart Rules',
            'generated_at': datetime.utcnow().isoformat(),
        }

    # ========================================================================
    # AI CHAT / Q&A
    # ========================================================================

    def chat(self, message: str, leads_context: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        AI chat about leads and pipeline.
        Accepts a natural language question and optional leads context.
        """
        context_text = ''
        if leads_context:
            summaries = []
            for ld in leads_context[:10]:  # Limit to 10 leads for speed
                summaries.append(
                    f"  {ld.get('name','?')} | {ld.get('company','?')} | "
                    f"{ld.get('country','?')} | Score:{ld.get('qualification_score','?')} | {ld.get('status','?')}"
                )
            context_text = f"\n\nLeads ({len(leads_context)} total, showing 10):\n" + '\n'.join(summaries)

        prompt = f"""Answer this question about my sales leads and pipeline.

Question: {message}{context_text}

Give a helpful, specific answer in 3-5 sentences. Reference leads by name when relevant. Be actionable."""

        system = "AI sales assistant for lead management. Be specific and data-driven."

        text = self._generate(prompt, system=system, temperature=0.6, max_retries=0, max_tokens=200)

        if text:
            return {
                'response': text,
                'ai_provider': f'Ollama ({self._model})',
                'timestamp': datetime.utcnow().isoformat(),
            }

        # Smart rule-based chat fallback using leads context
        response = self._rule_based_chat(message, leads_context)
        return {
            'response': response,
            'ai_provider': 'Smart Rules',
            'timestamp': datetime.utcnow().isoformat(),
        }

    def _rule_based_chat(self, message: str, leads_context: Optional[List[Dict]] = None) -> str:
        """Generate a helpful response using lead data without LLM."""
        msg = message.lower()
        leads = leads_context or []

        if not leads:
            return "No lead data available. Import some leads first to get AI-powered insights."

        total = len(leads)
        hot = [l for l in leads if str(l.get('status', '')).lower() == 'hot']
        warm = [l for l in leads if str(l.get('status', '')).lower() == 'warm']
        cold = [l for l in leads if str(l.get('status', '')).lower() == 'cold']
        scores = [l.get('qualification_score', 0) for l in leads if l.get('qualification_score')]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0

        # Best / top leads
        if any(w in msg for w in ['best', 'top', 'highest', 'priority']):
            top = sorted(leads, key=lambda x: x.get('qualification_score', 0), reverse=True)[:5]
            lines = [f"Here are your top leads by qualification score:"]
            for i, l in enumerate(top, 1):
                lines.append(f"{i}. {l.get('name','?')} at {l.get('company','?')} — Score: {l.get('qualification_score','?')}, Status: {l.get('status','?')}")
            lines.append(f"\nFocus outreach on these high-value contacts first.")
            return '\n'.join(lines)

        # Summary / overview
        if any(w in msg for w in ['summary', 'overview', 'pipeline', 'status', 'how']):
            return (
                f"Pipeline Overview: {total} leads shown (top by score). "
                f"Hot: {len(hot)}, Warm: {len(warm)}, Cold: {len(cold)}. "
                f"Average score: {avg_score}. "
                f"{'Your pipeline looks healthy with strong hot leads.' if len(hot) >= 3 else 'Consider enriching warm leads to move them to hot status.'}"
            )

        # Country question
        if any(w in msg for w in ['country', 'countries', 'region', 'where']):
            countries = {}
            for l in leads:
                c = l.get('country', 'Unknown')
                if c:
                    countries[c] = countries.get(c, 0) + 1
            sorted_c = sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5]
            lines = ["Lead distribution by country:"]
            for c, cnt in sorted_c:
                lines.append(f"  {c}: {cnt} leads")
            return '\n'.join(lines)

        # Industry question
        if any(w in msg for w in ['industry', 'industries', 'sector']):
            industries = {}
            for l in leads:
                ind = l.get('industry', 'Unknown')
                if ind:
                    industries[ind] = industries.get(ind, 0) + 1
            sorted_i = sorted(industries.items(), key=lambda x: x[1], reverse=True)[:5]
            lines = ["Lead distribution by industry:"]
            for ind, cnt in sorted_i:
                lines.append(f"  {ind}: {cnt} leads")
            return '\n'.join(lines)

        # Default helpful response
        top = sorted(leads, key=lambda x: x.get('qualification_score', 0), reverse=True)[:3]
        top_names = ', '.join(f"{l.get('name','?')} ({l.get('company','?')})" for l in top)
        return (
            f"Based on your lead data: you have {total} leads shown with an average score of {avg_score}. "
            f"Top leads: {top_names}. "
            f"Try asking about 'best leads', 'pipeline summary', 'top countries', or 'industries'."
        )

    # ========================================================================
    # PIPELINE SUMMARY
    # ========================================================================

    def generate_pipeline_summary(self, stats: Dict[str, Any],
                                   sample_leads: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Generate an AI-powered summary of the entire lead pipeline.
        """
        leads_preview = ''
        if sample_leads:
            previews = []
            for ld in sample_leads[:5]:  # Only 5 sample leads for speed
                previews.append(
                    f"  {ld.get('name','?')} ({ld.get('company','?')}) — "
                    f"Score:{ld.get('qualification_score','?')}, {ld.get('status','?')}, "
                    f"{ld.get('country','?')}"
                )
            leads_preview = "\nSample:\n" + '\n'.join(previews)

        prompt = f"""Analyze this sales pipeline and provide strategic insights.

Pipeline data:
- Total leads: {stats.get('total',0)}
- Hot leads: {stats.get('hot',0)}
- Warm leads: {stats.get('warm',0)}
- Cold leads: {stats.get('cold',0)}
- Average score: {stats.get('avg_score',0):.0f}
- Leads with email: {stats.get('with_email',0)}
- Leads with phone: {stats.get('with_phone',0)}
- Top countries: {stats.get('countries','N/A')}
- Top industries: {stats.get('top_industries','N/A')}{leads_preview}

Return ONLY a JSON object with these fields (fill in real values based on the data above):
{{"executive_summary": "<your 2-sentence summary of pipeline health>", "key_insights": ["<insight 1>", "<insight 2>"], "recommendations": ["<recommendation 1>", "<recommendation 2>"], "pipeline_health": "<Excellent or Good or Fair or Poor>", "immediate_actions": ["<action 1>", "<action 2>"], "focus_countries": ["<country1>"], "focus_industries": ["<industry1>"]}}"""

        system = "VP of Sales. JSON only, no markdown."

        text = self._generate(prompt, system=system, temperature=0.5, max_retries=0, max_tokens=256)
        result = self._parse_json(text or '')

        if result:
            return {
                'summary': result,
                'stats': stats,
                'ai_provider': f'Ollama ({self._model})',
                'generated_at': datetime.utcnow().isoformat(),
            }

        return {
            'summary': {
                'executive_summary': f"Pipeline contains {stats.get('total', 0)} leads with {stats.get('hot', 0)} hot opportunities and an average score of {stats.get('avg_score', 0):.0f}. {'Strong pipeline with good hot lead ratio.' if stats.get('hot', 0) > stats.get('total', 1) * 0.2 else 'Focus on qualifying warm leads to increase hot opportunities.'}",
                'key_insights': [
                    f"{stats.get('hot', 0)} hot leads ready for immediate outreach",
                    f"{stats.get('warm', 0)} warm leads need nurturing to convert",
                    f"Data completeness: {stats.get('with_email', 0)} leads have email, {stats.get('with_phone', 0)} have phone",
                ],
                'recommendations': [
                    'Prioritize outreach to hot leads this week',
                    'Enrich data for warm leads to improve qualification',
                    'Review cold leads for re-engagement opportunities',
                ],
                'pipeline_health': 'Good' if stats.get('hot', 0) >= 5 else 'Fair' if stats.get('warm', 0) >= 10 else 'Needs Attention',
                'immediate_actions': [
                    f"Contact top {min(5, stats.get('hot', 0))} hot leads",
                    'Schedule follow-ups for warm leads without recent activity',
                ],
                'focus_countries': list(stats.get('countries', {}).keys())[:3] if isinstance(stats.get('countries'), dict) else [],
                'focus_industries': list(stats.get('top_industries', {}).keys())[:3] if isinstance(stats.get('top_industries'), dict) else [],
            },
            'stats': stats,
            'ai_provider': 'Smart Rules',
            'generated_at': datetime.utcnow().isoformat(),
        }


# ========================================================================
# SINGLETON
# ========================================================================
_ollama_service: Optional[OllamaService] = None


def get_ollama_service() -> OllamaService:
    """Get or create the singleton OllamaService"""
    global _ollama_service
    if _ollama_service is None:
        _ollama_service = OllamaService()
    return _ollama_service
