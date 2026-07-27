"""
Agent Registry
Central registry for managing and retrieving agent instances
"""

from typing import Dict, Type, Optional, Any, List
import logging
from app.agents.config import AgentType, AgentStatus, AGENT_METADATA
from app.agents.base_agent import BaseAgent
from app.agents.exceptions import AgentNotFoundError, AgentValidationError

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Registry for managing agent instances and their metadata.
    Handles registration, retrieval, and lifecycle of agents.
    """
    
    def __init__(self):
        """Initialize the agent registry"""
        self._agents: Dict[AgentType, Type[BaseAgent]] = {}
        self._instances: Dict[str, BaseAgent] = {}
    
    def register_agent(
        self,
        agent_type: AgentType,
        agent_class: Type[BaseAgent],
    ) -> None:
        """
        Register an agent class for a specific agent type
        
        Args:
            agent_type: The AgentType enum value
            agent_class: The agent class to register
            
        Raises:
            AgentValidationError: If agent_class is invalid
        """
        if not issubclass(agent_class, BaseAgent):
            raise AgentValidationError(
                message=f"Agent class {agent_class.__name__} must inherit from BaseAgent",
                agent_type=agent_type,
            )
        
        self._agents[agent_type] = agent_class
        logger.info(f"Registered agent: {agent_type.value} -> {agent_class.__name__}")
    
    def get_agent(
        self,
        agent_type: AgentType,
        trace_id: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseAgent:
        """
        Get or create an agent instance
        
        Args:
            agent_type: The type of agent to retrieve
            trace_id: Optional trace ID for logging
            **kwargs: Additional arguments to pass to agent constructor
            
        Returns:
            Agent instance
            
        Raises:
            AgentNotFoundError: If agent type not registered
        """
        if agent_type not in self._agents:
            raise AgentNotFoundError(
                agent_name=agent_type.value
            )
        
        # Create a new instance with the provided kwargs
        agent_class = self._agents[agent_type]
        metadata = AGENT_METADATA.get(agent_type, {})
        
        # Prepare constructor arguments without agent_type (handled by subclass)
        constructor_kwargs = {
            'name': metadata.get('name', agent_type.value),
            'trace_id': trace_id,
        }
        # Merge with any additional kwargs provided
        constructor_kwargs.update(kwargs)
        
        agent = agent_class(**constructor_kwargs)
        
        logger.debug(
            f"Created agent instance: {agent_type.value}",
            extra={'trace_id': trace_id},
        )
        
        return agent
    
    def list_agents(self) -> List[Dict[str, Any]]:
        """
        List all registered agents with their metadata
        
        Returns:
            List of agent information dictionaries
        """
        agents_list = []
        
        for agent_type in AgentType:
            is_registered = agent_type in self._agents
            metadata = AGENT_METADATA.get(agent_type, {})
            
            agent_info = {
                'type': agent_type.value,
                'name': metadata.get('name', agent_type.value),
                'description': metadata.get('description', ''),
                'version': metadata.get('version', '1.0.0'),
                'registered': is_registered,
                'instantiated': is_registered,
                'supported_inputs': metadata.get('supported_inputs', []),
            }
            
            agents_list.append(agent_info)
        
        return agents_list
    
    def unregister_agent(self, agent_type: AgentType) -> None:
        """
        Unregister an agent type
        
        Args:
            agent_type: The agent type to unregister
        """
        if agent_type in self._agents:
            del self._agents[agent_type]
            logger.info(f"Unregistered agent: {agent_type.value}")
    
    def is_registered(self, agent_type: AgentType) -> bool:
        """
        Check if an agent type is registered
        
        Args:
            agent_type: The agent type to check
            
        Returns:
            True if registered, False otherwise
        """
        return agent_type in self._agents
    
    def clear(self) -> None:
        """Clear all registered agents and instances"""
        self._agents.clear()
        self._instances.clear()
        logger.info("Cleared agent registry")
