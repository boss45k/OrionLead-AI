"""
LLM Configuration — SECONDARY AI PATH (QueryAgent / LLMIntegration only)
=========================================================================
Configures OpenAI and Anthropic clients used by LLMIntegration.
This module is NOT used by the main AI path (gemini_service.py).

See llm/integration.py for the full AI provider map.
"""

import os
import logging


logger = logging.getLogger(__name__)

# LLM Provider settings
class LLMConfig:
    """Configuration for LLM services"""
    
    # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')
    OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', 0.7))
    OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', 2000))
    OPENAI_TIMEOUT = int(os.getenv('OPENAI_TIMEOUT', 30))
    
    # Alternative providers
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
    ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-3-opus-20240229')
    
    # LLM Features
    ENABLE_LLM = os.getenv('ENABLE_LLM', 'true').lower() == 'true'
    LLM_CACHE_ENABLED = os.getenv('LLM_CACHE_ENABLED', 'true').lower() == 'true'
    LLM_CACHE_TTL = int(os.getenv('LLM_CACHE_TTL', 3600))  # 1 hour
    
    # Costs and limits
    LLM_MAX_COST_PER_REQUEST = float(os.getenv('LLM_MAX_COST_PER_REQUEST', 1.0))  # $1.00
    LLM_DAILY_BUDGET = float(os.getenv('LLM_DAILY_BUDGET', 100.0))  # $100/day
    LLM_MAX_REQUESTS_PER_MINUTE = int(os.getenv('LLM_MAX_REQUESTS_PER_MINUTE', 60))


# Verify LLM availability
def check_llm_availability() -> bool:
    """Check if LLM is properly configured"""
    if not LLMConfig.ENABLE_LLM:
        logger.warning("LLM support is disabled")
        return False
    
    if not LLMConfig.OPENAI_API_KEY and not LLMConfig.ANTHROPIC_API_KEY:
        logger.warning("No LLM API key configured")
        return False
    
    logger.info("LLM support is available")
    return True


# LLM Models
AVAILABLE_MODELS = {
    'gpt-4': {
        'provider': 'openai',
        'name': 'gpt-4',
        'max_tokens': 8192,
        'cost_per_1k_input': 0.03,
        'cost_per_1k_output': 0.06,
    },
    'gpt-4-turbo': {
        'provider': 'openai',
        'name': 'gpt-4-turbo-preview',
        'max_tokens': 128000,
        'cost_per_1k_input': 0.01,
        'cost_per_1k_output': 0.03,
    },
    'gpt-3.5-turbo': {
        'provider': 'openai',
        'name': 'gpt-3.5-turbo',
        'max_tokens': 4096,
        'cost_per_1k_input': 0.0005,
        'cost_per_1k_output': 0.0015,
    },
    'claude-3-opus': {
        'provider': 'anthropic',
        'name': 'claude-3-opus-20240229',
        'max_tokens': 200000,
        'cost_per_1k_input': 0.015,
        'cost_per_1k_output': 0.075,
    },
    'claude-3-sonnet': {
        'provider': 'anthropic',
        'name': 'claude-3-sonnet-20240229',
        'max_tokens': 200000,
        'cost_per_1k_input': 0.003,
        'cost_per_1k_output': 0.015,
    },
}
