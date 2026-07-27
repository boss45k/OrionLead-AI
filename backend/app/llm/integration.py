"""
LLM Integration — SECONDARY AI PATH (QueryAgent only)
======================================================
This module is used exclusively by QueryAgent (agents/query_agent.py) for
natural-language queries about leads via the /api/v1/agents/* endpoints.

Provider: OpenAI (default gpt-4) or Anthropic Claude.
Configured via: OPENAI_API_KEY / ANTHROPIC_API_KEY in .env.

⚠️  This is NOT the main AI path.
    For lead qualification, email generation, chat, and all /api/v1/ai/*
    endpoints, see: services/gemini_service.py (Gemini → Groq → rules).

AI provider map for this project:
  /api/v1/ai/*       → services/gemini_service.AIService
                         Layer 1: Gemini 2.5 Flash
                         Layer 2: Groq llama-3.1-8b-instant (fallback)
                         Layer 3: Rule-based scoring (last resort)

  /api/v1/agents/*   → agents/query_agent.QueryAgent → llm/integration.LLMIntegration
                         Layer 1: OpenAI gpt-4  (or Anthropic if configured)

  ML scoring         → services/advanced_ai.py + services/ml_model.XGBLeadScoringModel
                         XGBoost (35 features), SHAP explanations, Optuna-tuned
                         Ollama (Mistral 7B) for local embedding/NLP

  Dedup              → services/advanced_ai.py → FAISS vector index
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import hashlib

from app.llm.config import LLMConfig, check_llm_availability, AVAILABLE_MODELS
from app.llm.prompts import PromptTemplates, SYSTEM_PROMPTS

logger = logging.getLogger(__name__)


class LLMIntegration:
    """
    Main LLM integration class
    Handles calls to various LLM providers with caching and cost tracking
    """
    
    def __init__(
        self,
        provider: str = 'openai',
        model: Optional[str] = None,
        cache_enabled: bool = True,
    ):
        """
        Initialize LLM integration
        
        Args:
            provider: LLM provider ('openai', 'anthropic')
            model: Model name (defaults to configured model)
            cache_enabled: Whether to cache responses
        """
        self.provider = provider
        self.model = model or LLMConfig.OPENAI_MODEL
        self.cache_enabled = cache_enabled and LLMConfig.LLM_CACHE_ENABLED
        self.is_available = check_llm_availability()
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"LLM Integration initialized: {provider}/{self.model}")
    
    def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: str = 'text',
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate LLM response
        
        Args:
            prompt: User prompt
            system_prompt: System prompt for context
            response_format: 'text' or 'json'
            temperature: Override default temperature
            max_tokens: Override default max tokens
            
        Returns:
            Response with status, content, cost, usage
        """
        if not self.is_available:
            logger.warning("LLM not available - returning fallback response")
            return {
                'status': 'unavailable',
                'content': None,
                'error': 'LLM service not configured',
                'model': self.model,
            }
        
        # Check cache
        cache_key = self._get_cache_key(prompt, system_prompt)
        if self.cache_enabled and cache_key in self._cache:
            logger.debug("Cache hit for LLM response")
            cached = self._cache[cache_key]
            cached['cached'] = True
            return cached
        
        try:
            # Call appropriate provider
            if self.provider == 'openai':
                response = self._call_openai(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            elif self.provider == 'anthropic':
                response = self._call_anthropic(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            else:
                raise ValueError(f"Unknown provider: {self.provider}")
            
            # Cache successful response
            if self.cache_enabled and response.get('status') == 'success':
                self._cache[cache_key] = response.copy()
            
            response['cached'] = False
            return response
            
        except Exception as e:
            logger.error(f"LLM generation error: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'model': self.model,
                'provider': self.provider,
            }
    
    def _call_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: str = 'text',
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Call OpenAI API"""
        try:
            import openai
        except ImportError:
            logger.error("openai package not installed")
            return {
                'status': 'error',
                'error': 'openai package not installed',
            }
        
        try:
            openai.api_key = LLMConfig.OPENAI_API_KEY
            
            messages = []
            if system_prompt:
                messages.append({
                    'role': 'system',
                    'content': system_prompt,
                })
            
            messages.append({
                'role': 'user',
                'content': prompt,
            })
            
            kwargs = {
                'model': self.model,
                'messages': messages,
                'temperature': temperature or LLMConfig.OPENAI_TEMPERATURE,
                'max_tokens': max_tokens or LLMConfig.OPENAI_MAX_TOKENS,
            }
            
            if response_format == 'json':
                kwargs['response_format'] = {'type': 'json_object'}
            
            logger.debug(f"Calling OpenAI: {self.model}")
            
            # Use new OpenAI client API (v1.x+)
            from openai import OpenAI
            client = OpenAI(api_key=LLMConfig.OPENAI_API_KEY)
            response = client.chat.completions.create(**kwargs)
            
            content = response.choices[0].message.content
            
            # Calculate cost
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            model_info = AVAILABLE_MODELS.get(self.model, {})
            
            input_cost = (input_tokens / 1000) * model_info.get('cost_per_1k_input', 0)
            output_cost = (output_tokens / 1000) * model_info.get('cost_per_1k_output', 0)
            total_cost = input_cost + output_cost
            
            # Parse JSON if requested
            if response_format == 'json':
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse JSON response from OpenAI")
            
            return {
                'status': 'success',
                'content': content,
                'model': self.model,
                'provider': 'openai',
                'usage': {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': input_tokens + output_tokens,
                },
                'cost': {
                    'input_cost': round(input_cost, 4),
                    'output_cost': round(output_cost, 4),
                    'total_cost': round(total_cost, 4),
                },
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise
    
    def _call_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: str = 'text',
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Call Anthropic API (Claude)"""
        try:
            import anthropic
        except ImportError:
            logger.error("anthropic package not installed")
            return {
                'status': 'error',
                'error': 'anthropic package not installed',
            }
        
        try:
            client = anthropic.Anthropic(api_key=LLMConfig.ANTHROPIC_API_KEY)
            
            logger.debug(f"Calling Anthropic: {self.model}")
            
            message = client.messages.create(
                model=self.model,
                max_tokens=max_tokens or 2000,
                system=system_prompt or '',
                messages=[
                    {
                        'role': 'user',
                        'content': prompt,
                    }
                ],
                temperature=temperature or 0.7,
            )
            
            content = message.content[0].text
            
            # Parse JSON if requested
            if response_format == 'json':
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse JSON response from Anthropic")
            
            # Calculate cost
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            model_info = AVAILABLE_MODELS.get(self.model, {})
            
            input_cost = (input_tokens / 1000) * model_info.get('cost_per_1k_input', 0)
            output_cost = (output_tokens / 1000) * model_info.get('cost_per_1k_output', 0)
            total_cost = input_cost + output_cost
            
            return {
                'status': 'success',
                'content': content,
                'model': self.model,
                'provider': 'anthropic',
                'usage': {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': input_tokens + output_tokens,
                },
                'cost': {
                    'input_cost': round(input_cost, 4),
                    'output_cost': round(output_cost, 4),
                    'total_cost': round(total_cost, 4),
                },
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Anthropic API error: {str(e)}")
            raise
    
    @staticmethod
    def _get_cache_key(prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate cache key for prompt"""
        key_data = f"{prompt}:{system_prompt or ''}"
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def analyze_lead_with_llm(
        self,
        lead_data: Dict[str, Any],
        analysis_type: str = 'qualification',
    ) -> Dict[str, Any]:
        """
        Analyze lead using LLM
        
        Args:
            lead_data: Lead information
            analysis_type: Type of analysis to perform
            
        Returns:
            LLM analysis result
        """
        if analysis_type == 'qualification':
            template = PromptTemplates.LEAD_QUALIFICATION_ANALYSIS
            system_prompt = SYSTEM_PROMPTS['qualification_expert']
            
            formatted_prompt = PromptTemplates.format_prompt(
                template,
                lead_data=json.dumps(lead_data, indent=2),
                company_data=json.dumps({
                    'name': lead_data.get('company'),
                    'size': lead_data.get('company_size'),
                    'industry': lead_data.get('industry'),
                }, indent=2),
                engagement_data=json.dumps({
                    'score': lead_data.get('engagement_score'),
                    'page_views': lead_data.get('page_views'),
                    'email_opens': lead_data.get('email_opens'),
                }, indent=2),
            )
            
            return self.generate_response(
                prompt=formatted_prompt,
                system_prompt=system_prompt,
                response_format='json',
            )
        
        elif analysis_type == 'intent':
            template = PromptTemplates.INTENT_DETECTION
            system_prompt = SYSTEM_PROMPTS['intent_analyzer']
            
            formatted_prompt = PromptTemplates.format_prompt(
                template,
                messages=json.dumps(lead_data.get('messages', []), indent=2),
                page_views=json.dumps(lead_data.get('page_views', []), indent=2),
                actions=json.dumps(lead_data.get('actions', []), indent=2),
            )
            
            return self.generate_response(
                prompt=formatted_prompt,
                system_prompt=system_prompt,
                response_format='json',
            )
        
        else:
            raise ValueError(f"Unknown analysis type: {analysis_type}")
