"""
QueryAgent — SECONDARY AI PATH via LLMIntegration (OpenAI / Anthropic)
=======================================================================
Handles natural-language questions about leads through /api/v1/agents/*.
Uses LLMIntegration (llm/integration.py) which calls OpenAI gpt-4 by default.

This is separate from the main AI path (gemini_service.py / Gemini → Groq)
which powers all /api/v1/ai/* endpoints.
"""

from typing import Dict, Any, Optional
import json
import logging

from app.agents.base_agent import BaseAgent
from app.agents.config import AgentType
from app.agents.exceptions import AgentValidationError, AgentExecutionError
from app.llm.integration import LLMIntegration
from app.llm.prompts import PromptTemplates

logger = logging.getLogger(__name__)


class QueryAgent(BaseAgent):
    """
    Query Agent for natural language questions about leads
    Uses LLM to provide insights and analysis
    """
    
    def __init__(
        self,
        name: str = "Query Agent",
        version: str = "1.0.0",
        timeout: int = 45,
        llm_provider: str = 'openai',
        trace_id: Optional[str] = None,
    ):
        """
        Initialize query agent
        
        Args:
            name: Agent name
            version: Agent version
            timeout: Execution timeout
            llm_provider: LLM provider to use
            trace_id: Trace ID for request tracking
        """
        super().__init__(
            agent_type=AgentType.QUERY,
            name=name,
            version=version,
            timeout=timeout,
            trace_id=trace_id,
        )
        
        self.llm = LLMIntegration(provider=llm_provider)
        logger.info(f"Query Agent initialized with {llm_provider} provider")
    
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """
        Validate input data for query
        
        Args:
            input_data: Input data to validate
            
        Returns:
            True if valid
            
        Raises:
            AgentValidationError: If validation fails
        """
        required_fields = ['query']
        for field in required_fields:
            if field not in input_data:
                raise AgentValidationError(
                    message=f"Missing required field: {field}",
                    agent_name=self.name,
                    details={'required_fields': required_fields},
                )
        
        query = input_data.get('query', '').strip()
        if not query:
            raise AgentValidationError(
                message="Query cannot be empty",
                agent_name=self.name,
            )
        
        if len(query) > 2000:
            raise AgentValidationError(
                message="Query too long (max 2000 characters)",
                agent_name=self.name,
            )
        
        return True
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute natural language query
        
        Args:
            input_data: Query and context
            
        Returns:
            Analysis result from LLM
        """
        query = input_data.get('query', '').strip()
        lead_ids = input_data.get('lead_ids', [])
        lead_data = input_data.get('lead_data', {})
        response_format = input_data.get('response_format', 'text')
        
        self.logger.info(
            f"Executing query: {query[:100]}...",
            extra={'trace_id': self.trace_id},
        )
        
        # Prepare context
        context_prompt = PromptTemplates.GENERAL_QUERY.format(
            query=query,
            lead_data=json.dumps(lead_data or {}, indent=2),
        )
        
        # Call LLM
        try:
            llm_result = self.llm.generate_response(
                prompt=context_prompt,
                response_format=response_format,
            )
            
            if llm_result.get('status') != 'success':
                raise AgentExecutionError(
                    message=f"LLM failed: {llm_result.get('error', 'Unknown error')}",
                    agent_name=self.name,
                    details=llm_result,
                )
            
            self.logger.info(
                "Query execution successful",
                extra={
                    'trace_id': self.trace_id,
                    'tokens_used': llm_result.get('usage', {}).get('total_tokens'),
                },
            )
            
            result = {
                'query': query,
                'response': llm_result.get('content'),
                'analysis': self._extract_analysis(llm_result.get('content')),
                'model': llm_result.get('model'),
                'cost': llm_result.get('cost'),
                'cached': llm_result.get('cached', False),
                'lead_ids': lead_ids,
            }
            
            return result
            
        except Exception as e:
            self.logger.error(
                f"Query execution error: {str(e)}",
                extra={'trace_id': self.trace_id},
            )
            raise AgentExecutionError(
                message=f"Query execution failed: {str(e)}",
                agent_name=self.name,
                details={'query': query},
            )
    
    def _extract_analysis(self, content: Any) -> Dict[str, Any]:
        """Extract structured analysis from LLM response"""
        if isinstance(content, dict):
            return content
        
        # Try to parse as JSON
        try:
            if isinstance(content, str):
                return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Return as text
        return {'text': str(content)}
    
    def analyze_lead_insights(
        self,
        lead_data: Dict[str, Any],
        insight_type: str = 'general',
    ) -> Dict[str, Any]:
        """
        Get AI insights about a lead
        
        Args:
            lead_data: Lead information
            insight_type: Type of insight to generate
            
        Returns:
            AI-generated insights
        """
        if insight_type == 'general':
            query = f"""
            Provide a brief executive summary of this lead:
            - Who they are and what they do
            - Why they might need our product
            - Key next steps for engagement
            """
        
        elif insight_type == 'competitive':
            query = f"""
            Analyze the competitive landscape for this lead:
            - What competitors might they use
            - Our competitive advantages
            - Key messaging angles
            """
        
        elif insight_type == 'objection_handling':
            query = f"""
            What objections might this lead raise?
            - Likely concerns based on their profile
            - Recommended responses
            - Evidence/proof points to address each
            """
        
        else:
            query = f"Provide insights about: {insight_type}"
        
        input_data = {
            'query': query,
            'lead_data': lead_data,
            'response_format': 'json',
        }
        
        results = self.execute(input_data)
        
        return {
            'insight_type': insight_type,
            'insights': results.get('analysis'),
            'generated_by': 'QueryAgent',
            'model': results.get('model'),
            'cost': results.get('cost'),
        }
