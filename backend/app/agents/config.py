"""
Agent Configuration and Enums
Core definitions for the agent system
"""

from enum import Enum
import os

# Agent types
class AgentType(Enum):
    """Enumeration of available agent types"""
    QUALIFICATION = "qualification"
    ENRICHMENT = "enrichment"
    INTENT_PREDICTION = "intent_prediction"
    RECOMMENDATION = "recommendation"
    QUERY = "query"


# Agent status
class AgentStatus(Enum):
    """Enumeration of agent execution states"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


# Agent configuration
class AgentConfig:
    """Agent system configuration"""
    
    # Execution
    DEFAULT_TIMEOUT = int(os.getenv('AGENT_DEFAULT_TIMEOUT', 30))
    MAX_RETRIES = int(os.getenv('AGENT_MAX_RETRIES', 3))
    BATCH_SIZE = int(os.getenv('AGENT_BATCH_SIZE', 32))
    
    # Thresholds
    CONFIDENCE_THRESHOLD = float(os.getenv('AGENT_CONFIDENCE_THRESHOLD', 0.5))
    MIN_SCORE_THRESHOLD = float(os.getenv('AGENT_MIN_SCORE_THRESHOLD', 0.3))
    
    # Models
    MODEL_PATH = os.getenv('MODEL_PATH', './models/')
    
    # Feature extraction
    MAX_TEXT_LENGTH = int(os.getenv('AGENT_MAX_TEXT_LENGTH', 1000))
    
    # Logging
    LOG_AGENT_METRICS = os.getenv('AGENT_LOG_METRICS', 'true').lower() == 'true'
    LOG_AGENT_INPUTS = os.getenv('AGENT_LOG_INPUTS', 'false').lower() == 'true'
    
    # Cache
    AGENT_CACHE_TTL = int(os.getenv('AGENT_CACHE_TTL', 3600))  # 1 hour
    USE_AGENT_CACHE = os.getenv('AGENT_CACHE_ENABLED', 'true').lower() == 'true'


# Agent metadata
AGENT_METADATA = {
    AgentType.QUALIFICATION: {
        'name': 'Qualification Agent',
        'description': 'Qualifies leads based on scoring rules and ML models',
        'version': '1.0.0',
        'supported_inputs': ['lead_id', 'lead_data', 'evaluation_mode'],
    },
    AgentType.ENRICHMENT: {
        'name': 'Enrichment Agent',
        'description': 'Enriches lead data with external information',
        'version': '1.0.0',
        'supported_inputs': ['lead_id', 'data_sources', 'depth'],
    },
    AgentType.INTENT_PREDICTION: {
        'name': 'Intent Prediction Agent',
        'description': 'Predicts purchase intent from lead signals',
        'version': '1.0.0',
        'supported_inputs': ['lead_id', 'interaction_data', 'time_period'],
    },
    AgentType.RECOMMENDATION: {
        'name': 'Recommendation Agent',
        'description': 'Recommends next best action for a lead',
        'version': '1.0.0',
        'supported_inputs': ['lead_id', 'context', 'priority'],
    },
    AgentType.QUERY: {
        'name': 'Query Agent',
        'description': 'Processes natural language queries about leads',
        'version': '1.0.0',
        'supported_inputs': ['query_text', 'lead_ids', 'response_format'],
    },
}
