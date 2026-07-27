"""
Agent Pool Manager
Manages a pool of reusable agent instances for improved memory efficiency
and reduced initialization overhead.

Design:
- Singleton pattern for pool management
- Thread-safe instance reuse
- Lazy initialization of agents
- Support for multiple agent types
"""

import threading
import logging
from typing import Dict, Optional, Type, Any
from datetime import datetime

from app.agents.base_agent import BaseAgent
from app.agents.config import AgentType
from app.agents.exceptions import AgentNotFoundError, AgentValidationError


logger = logging.getLogger(__name__)


class AgentPool:
    """Thread-safe pool for managing reusable agent instances"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the agent pool"""
        self.agents: Dict[str, BaseAgent] = {}
        self.agent_classes: Dict[AgentType, Type[BaseAgent]] = {}
        self.creation_lock = threading.Lock()
        self.usage_stats: Dict[str, dict] = {}
        logger.info("Agent pool initialized")
    
    def register_agent_class(
        self,
        agent_type: AgentType,
        agent_class: Type[BaseAgent]
    ):
        """
        Register an agent class that can be pooled
        
        Args:
            agent_type: Type of agent (QUALIFICATION, QUERY, etc.)
            agent_class: The agent class to instantiate from
        """
        if not issubclass(agent_class, BaseAgent):
            raise AgentValidationError(
                message=f"Agent class must inherit from BaseAgent",
                agent_name=agent_type.value
            )
        
        self.agent_classes[agent_type] = agent_class
        pool_key = agent_type.value
        self.usage_stats[pool_key] = {
            'created': datetime.utcnow(),
            'instances': 0,
            'acquisitions': 0,
            'releases': 0,
        }
        logger.info(f"Registered agent class: {agent_type.value}")
    
    def get_agent(self, agent_type: AgentType) -> BaseAgent:
        """
        Get an agent from the pool (reused across requests)
        
        Args:
            agent_type: Type of agent to retrieve
            
        Returns:
            An agent instance (same instance reused for this type)
            
        Raises:
            AgentNotFoundError: If agent type not registered
        """
        pool_key = agent_type.value
        
        if pool_key in self.agents:
            # Reuse existing pooled agent
            self.usage_stats[pool_key]['acquisitions'] += 1
            return self.agents[pool_key]
        
        # Create new agent on first request
        with self.creation_lock:
            # Double-check pattern for thread safety
            if pool_key in self.agents:
                self.usage_stats[pool_key]['acquisitions'] += 1
                return self.agents[pool_key]
            
            if agent_type not in self.agent_classes:
                raise AgentNotFoundError(
                    agent_name=agent_type.value
                )
            
            # Instantiate and pool the agent
            agent_class = self.agent_classes[agent_type]
            agent = agent_class(
                agent_type=agent_type,
                name=agent_type.value
            )
            self.agents[pool_key] = agent
            
            self.usage_stats[pool_key]['instances'] += 1
            self.usage_stats[pool_key]['acquisitions'] += 1
            
            logger.info(f"Created and pooled agent: {agent_type.value}")
            return agent
    
    def get_stats(self) -> Dict[str, dict]:
        """
        Get pool statistics for monitoring
        
        Returns:
            Dictionary with usage stats for each agent type
        """
        return {
            key: {
                **stats,
                'created': stats['created'].isoformat()
            }
            for key, stats in self.usage_stats.items()
        }
    
    def get_health(self) -> Dict[str, Any]:
        """Get health status of agent pool"""
        return {
            'status': 'ok',
            'agents_pooled': len(self.agents),
            'agent_types': [t.value for t in self.agent_classes.keys()],
            'stats': self.get_stats()
        }
    
    def clear_pool(self):
        """Clear all pooled agents (use with caution)"""
        with self.creation_lock:
            self.agents.clear()
            logger.warning("Agent pool cleared")
    
    def get_pooled_agents_count(self) -> int:
        """Get count of pooled agent instances"""
        return len(self.agents)


def get_agent_pool() -> AgentPool:
    """Get the global agent pool instance"""
    return AgentPool()
