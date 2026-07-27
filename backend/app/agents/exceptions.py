"""
Agent-specific exception classes
"""

from app.exceptions import APIException
from typing import Optional, Dict, Any


class AgentException(APIException):
    """Base exception for all agent-related errors"""
    
    def __init__(
        self,
        message: str,
        agent_name: str = "Unknown",
        status_code: int = 500,
        error_code: str = "AGENT_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        details = details or {}
        details['agent'] = agent_name
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details,
        )


class AgentValidationError(AgentException):
    """Raised when agent input validation fails"""
    
    def __init__(self, message: str, agent_name: str = "Unknown", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            agent_name=agent_name,
            status_code=400,
            error_code="AGENT_VALIDATION_ERROR",
            details=details,
        )


class AgentExecutionError(AgentException):
    """Raised when agent execution fails"""
    
    def __init__(self, message: str, agent_name: str = "Unknown", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            agent_name=agent_name,
            status_code=500,
            error_code="AGENT_EXECUTION_ERROR",
            details=details,
        )


class AgentNotFoundError(AgentException):
    """Raised when agent is not registered"""
    
    def __init__(self, agent_name: str):
        super().__init__(
            message=f"Agent '{agent_name}' not found in registry",
            agent_name=agent_name,
            status_code=404,
            error_code="AGENT_NOT_FOUND",
        )


class AgentTimeoutError(AgentException):
    """Raised when agent execution times out"""
    
    def __init__(self, message: str, agent_name: str = "Unknown", timeout_seconds: float = 0):
        super().__init__(
            message=message,
            agent_name=agent_name,
            status_code=408,
            error_code="AGENT_TIMEOUT",
            details={'timeout_seconds': timeout_seconds},
        )
