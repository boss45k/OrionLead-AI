"""
Base agent abstract class and result types
Provides foundation for all specialized agents
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Optional, List
import logging
import time
from enum import Enum

from app.agents.config import AgentStatus, AgentType, AgentConfig
from app.agents.exceptions import (
    AgentValidationError,
    AgentExecutionError,
    AgentTimeoutError,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentMetrics:
    """Execution metrics for an agent run"""
    
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    confidence_score: float = 0.0
    retry_count: int = 0
    cache_hit: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class AgentResult:
    """Standardized result format for all agent outputs"""
    
    status: AgentStatus
    agent_type: AgentType
    agent_name: str
    data: Dict[str, Any]
    error: Optional[str] = None
    error_code: Optional[str] = None
    metrics: Optional[AgentMetrics] = field(default_factory=AgentMetrics)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trace_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization"""
        return {
            'status': self.status.value,
            'agent_type': self.agent_type.value,
            'agent_name': self.agent_name,
            'data': self.data,
            'error': self.error,
            'error_code': self.error_code,
            'metrics': self.metrics.to_dict() if self.metrics else None,
            'timestamp': self.timestamp.isoformat(),
            'trace_id': self.trace_id,
        }
    
    def is_success(self) -> bool:
        """Check if execution was successful"""
        return self.status == AgentStatus.SUCCESS
    
    def is_partial(self) -> bool:
        """Check if execution was partially successful"""
        return self.status == AgentStatus.PARTIAL


class BaseAgent(ABC):
    """
    Abstract base class for all AI agents
    Provides lifecycle management, error handling, and standardized execution
    """
    
    def __init__(
        self,
        agent_type: AgentType,
        name: str,
        version: str = "1.0.0",
        timeout: Optional[int] = None,
        enable_cache: bool = True,
        trace_id: Optional[str] = None,
    ):
        """
        Initialize base agent
        
        Args:
            agent_type: Type of agent from AgentType enum
            name: Human-readable agent name
            version: Agent version
            timeout: Execution timeout in seconds
            enable_cache: Whether to use caching
            trace_id: Unique trace ID for request tracking
        """
        self.agent_type = agent_type
        self.name = name
        self.version = version
        self.timeout = timeout or AgentConfig.DEFAULT_TIMEOUT
        self.enable_cache = enable_cache and AgentConfig.USE_AGENT_CACHE
        self.trace_id = trace_id or self._generate_trace_id()
        self.logger = logging.getLogger(f"agent.{self.name.lower()}")
    
    @staticmethod
    def _generate_trace_id() -> str:
        """Generate unique trace ID for request tracking"""
        import uuid
        return str(uuid.uuid4())
    
    @abstractmethod
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """
        Validate input data
        
        Args:
            input_data: Input data to validate
            
        Returns:
            True if valid
            
        Raises:
            AgentValidationError: If validation fails
        """
        pass
    
    @abstractmethod
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent logic
        
        Args:
            input_data: Validated input data
            
        Returns:
            Result data dictionary
            
        Raises:
            AgentExecutionError: If execution fails
        """
        pass
    
    def run(
        self,
        input_data: Dict[str, Any],
        skip_validation: bool = False,
    ) -> AgentResult:
        """
        Main entry point for agent execution
        Handles lifecycle, error handling, metrics, and retry logic
        
        Args:
            input_data: Input data for agent
            skip_validation: Skip validation if True
            
        Returns:
            AgentResult with status, data, and metrics
        """
        metrics = AgentMetrics()
        result = None
        retry_count = 0
        
        try:
            self.logger.info(
                f"Agent execution started",
                extra={
                    'agent_name': self.name,
                    'trace_id': self.trace_id,
                    'input_keys': list(input_data.keys()),
                },
            )
            
            # Step 1: Validate input
            if not skip_validation:
                try:
                    self.validate_input(input_data)
                except AgentValidationError as e:
                    self.logger.error(
                        f"Input validation failed: {str(e)}",
                        extra={'agent_name': self.name, 'trace_id': self.trace_id},
                    )
                    result = AgentResult(
                        status=AgentStatus.FAILED,
                        agent_type=self.agent_type,
                        agent_name=self.name,
                        data={},
                        error=str(e),
                        error_code='VALIDATION_ERROR',
                        metrics=metrics,
                        trace_id=self.trace_id,
                    )
                    return result
            
            # Step 2: Check cache
            if self.enable_cache:
                cached_result = self._get_cached_result(input_data)
                if cached_result:
                    metrics.cache_hit = True
                    self.logger.info(
                        "Cache hit for agent execution",
                        extra={'agent_name': self.name, 'trace_id': self.trace_id},
                    )
                    return cached_result
            
            # Step 3: Execute with retry logic
            max_retries = AgentConfig.MAX_RETRIES
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    metrics.retry_count = attempt
                    
                    self.logger.debug(
                        f"Attempting execution",
                        extra={
                            'agent_name': self.name,
                            'attempt': attempt + 1,
                            'max_retries': max_retries,
                            'trace_id': self.trace_id,
                        },
                    )
                    
                    # Execute with timeout
                    start_time = time.time()
                    execution_data = self._execute_with_timeout(input_data)
                    duration = time.time() - start_time
                    
                    metrics.end_time = datetime.utcnow()
                    metrics.duration_seconds = duration
                    
                    # Success
                    result = AgentResult(
                        status=AgentStatus.SUCCESS,
                        agent_type=self.agent_type,
                        agent_name=self.name,
                        data=execution_data,
                        metrics=metrics,
                        trace_id=self.trace_id,
                    )
                    
                    # Cache result
                    if self.enable_cache:
                        self._cache_result(input_data, result)
                    
                    self.logger.info(
                        f"Agent execution completed successfully",
                        extra={
                            'agent_name': self.name,
                            'duration': duration,
                            'trace_id': self.trace_id,
                        },
                    )
                    
                    return result
                    
                except AgentTimeoutError as e:
                    last_error = e
                    if attempt == max_retries - 1:
                        raise
                    self.logger.warning(
                        f"Agent execution timeout (attempt {attempt + 1}/{max_retries})",
                        extra={'agent_name': self.name, 'trace_id': self.trace_id},
                    )
                    
                except AgentExecutionError as e:
                    last_error = e
                    if attempt == max_retries - 1:
                        raise
                    self.logger.warning(
                        f"Agent execution failed (attempt {attempt + 1}/{max_retries}): {str(e)}",
                        extra={'agent_name': self.name, 'trace_id': self.trace_id},
                    )
            
            # All retries exhausted
            raise last_error or AgentExecutionError(
                message="Agent execution failed after all retries",
                agent_name=self.name,
            )
            
        except AgentTimeoutError as e:
            self.logger.error(
                f"Agent execution timeout: {str(e)}",
                extra={'agent_name': self.name, 'trace_id': self.trace_id},
            )
            result = AgentResult(
                status=AgentStatus.TIMEOUT,
                agent_type=self.agent_type,
                agent_name=self.name,
                data={},
                error=str(e),
                error_code='TIMEOUT',
                metrics=metrics,
                trace_id=self.trace_id,
            )
            
        except AgentExecutionError as e:
            self.logger.error(
                f"Agent execution error: {str(e)}",
                extra={'agent_name': self.name, 'trace_id': self.trace_id},
            )
            result = AgentResult(
                status=AgentStatus.FAILED,
                agent_type=self.agent_type,
                agent_name=self.name,
                data={},
                error=str(e),
                error_code='EXECUTION_ERROR',
                metrics=metrics,
                trace_id=self.trace_id,
            )
            
        except Exception as e:
            self.logger.error(
                f"Unexpected agent error: {type(e).__name__}: {str(e)}",
                extra={'agent_name': self.name, 'trace_id': self.trace_id},
                exc_info=True,
            )
            result = AgentResult(
                status=AgentStatus.FAILED,
                agent_type=self.agent_type,
                agent_name=self.name,
                data={},
                error=str(e),
                error_code='UNEXPECTED_ERROR',
                metrics=metrics,
                trace_id=self.trace_id,
            )
        
        return result or AgentResult(
            status=AgentStatus.FAILED,
            agent_type=self.agent_type,
            agent_name=self.name,
            data={},
            error="Unknown error",
            error_code='UNKNOWN_ERROR',
            metrics=metrics,
            trace_id=self.trace_id,
        )
    
    def _execute_with_timeout(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute with timeout protection"""
        import signal
        
        def timeout_handler(signum, frame):
            raise AgentTimeoutError(
                message=f"Agent execution exceeded {self.timeout}s timeout",
                agent_name=self.name,
                timeout_seconds=self.timeout,
            )
        
        try:
            # Set timeout (Unix only, Windows will skip)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)  # type: ignore[attr-defined]
                signal.alarm(int(self.timeout))  # type: ignore[attr-defined]
            
            data = self.execute(input_data)
            
            # Cancel timeout
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)  # type: ignore[attr-defined]
            
            return data
            
        except AgentTimeoutError:
            raise
        except Exception as e:
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)  # type: ignore[attr-defined]
            raise AgentExecutionError(
                message=f"Execution error: {str(e)}",
                agent_name=self.name,
                details={'error_type': type(e).__name__},
            )
    
    def _get_cached_result(self, input_data: Dict[str, Any]) -> Optional[AgentResult]:
        """Get cached result if available"""
        # Placeholder for cache implementation
        # Will be connected to Redis in Phase 2
        return None
    
    def _cache_result(self, input_data: Dict[str, Any], result: AgentResult) -> None:
        """Cache execution result"""
        # Placeholder for cache implementation
        # Will be connected to Redis in Phase 2
        pass
