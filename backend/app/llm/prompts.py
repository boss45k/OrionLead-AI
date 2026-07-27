"""
LLM Prompt Templates
Pre-engineered prompts for various agent tasks
"""

from typing import Dict, Any


class PromptTemplates:
    """Collection of prompt templates for LLM tasks"""
    
    # Lead Qualification Prompts
    LEAD_QUALIFICATION_ANALYSIS = """
    Analyze the following lead information and provide a detailed qualification assessment.
    
    Lead Information:
    {lead_data}
    
    Company Profile:
    {company_data}
    
    Engagement History:
    {engagement_data}
    
    Please provide:
    1. Overall qualification score (0-100)
    2. Key strengths as a potential customer
    3. Key concerns or red flags
    4. Recommended next steps
    5. Estimated sales cycle timeline
    6. Suggested personalized approach
    
    Format your response as JSON with keys: score, strengths, concerns, next_steps, timeline, approach
    """
    
    LEAD_QUALIFICATION_BRIEF = """
    Is this lead qualified for our product? Provide a quick assessment.
    
    Lead: {lead_name} from {company}
    Industry: {industry}
    Company Size: {company_size}
    Engagement Score: {engagement_score}
    
    Just answer: QUALIFIED / PARTIALLY_QUALIFIED / NOT_QUALIFIED with brief reasoning (1-2 sentences).
    """
    
    # Intent Detection Prompts
    INTENT_DETECTION = """
    Analyze this lead's communication and engagement to determine their buying intent.
    
    Recent Messages:
    {messages}
    
    Page Views on Topics:
    {page_views}
    
    Actions Taken:
    {actions}
    
    Provide:
    1. Intent level: HIGH / MEDIUM / LOW / NONE
    2. Primary pain points mentioned
    3. Urgency indicators
    4. Next likely action
    
    Format as JSON with keys: intent_level, pain_points, urgency, next_action
    """
    
    # Enrichment Prompts
    LEAD_ENRICHMENT = """
    Using the available data about this company, suggest relevant enrichment data points.
    
    Company: {company_name}
    Industry: {industry}
    Current Data: {current_data}
    
    Suggest:
    1. Key data gaps to fill
    2. Recommended data sources
    3. Most relevant firmographic fields
    4. Relevant questions to ask
    
    Format as JSON with keys: data_gaps, sources, key_fields, questions
    """
    
    # Recommendation Prompts
    NEXT_BEST_ACTION = """
    Based on this lead's profile and engagement, what should the sales team do next?
    
    Lead Profile:
    {lead_profile}
    
    Sales History:
    {sales_history}
    
    Current Stage: {current_stage}
    Days in Stage: {days_in_stage}
    
    Recommend:
    1. Immediate next action (specific, actionable)
    2. Owner/role who should take action
    3. Content to share (if any)
    4. Timing (ASAP / This week / This month)
    5. Success criteria
    
    Format as JSON with keys: action, owner, content, timing, success_criteria
    """
    
    # Competition Analysis Prompts
    COMPETITOR_ANALYSIS = """
    Compare this company's technology stack and needs with our product fit.
    
    Company Competitors/Tools:
    {company_tools}
    
    Our Solution:
    {our_solution}
    
    Lead's Stated Challenges:
    {challenges}
    
    Analyze:
    1. How we compare to their current tools
    2. Key competitive advantages
    3. Why they should switch
    4. Potential objections we'll face
    5. Differentiation angles
    
    Format as JSON with keys: comparison, advantages, switch_reasons, objections, differentiation
    """
    
    # Query Response Prompts
    GENERAL_QUERY = """
    Answer this question about the lead using the provided context.
    
    Question: {query}
    
    Lead Information:
    {lead_data}
    
    Provide a clear, relevant answer based on available data.
    If the information isn't available, say so explicitly.
    """
    
    @staticmethod
    def format_prompt(template: str, **kwargs) -> str:
        """Format a prompt template with variables"""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing required variable in prompt: {str(e)}")
    
    @staticmethod
    def get_template(template_name: str) -> str:
        """Get a prompt template by name"""
        templates = {
            'lead_qualification_analysis': PromptTemplates.LEAD_QUALIFICATION_ANALYSIS,
            'lead_qualification_brief': PromptTemplates.LEAD_QUALIFICATION_BRIEF,
            'intent_detection': PromptTemplates.INTENT_DETECTION,
            'lead_enrichment': PromptTemplates.LEAD_ENRICHMENT,
            'next_best_action': PromptTemplates.NEXT_BEST_ACTION,
            'competitor_analysis': PromptTemplates.COMPETITOR_ANALYSIS,
            'general_query': PromptTemplates.GENERAL_QUERY,
        }
        
        if template_name not in templates:
            raise ValueError(f"Unknown template: {template_name}")
        
        return templates[template_name]


# System prompts for different roles
SYSTEM_PROMPTS = {
    'qualification_expert': """
        You are an expert B2B sales qualification specialist with deep knowledge of SaaS sales cycles.
        You analyze lead data and provide accurate qualification assessments.
        You consider multiple factors: company size, industry, engagement, budget indicators, and timeline.
        Your assessments are data-driven and explain the reasoning.
        Always provide actionable insights.
        """.strip(),
    
    'intent_analyzer': """
        You are an expert at analyzing buyer intent signals from various data sources.
        You recognize subtle signals of purchasing intent in communications and behaviors.
        You understand different buying stages and can identify where a prospect is in their journey.
        You evaluate urgency indicators accurately.
        """.strip(),
    
    'sales_strategist': """
        You are a seasoned sales strategist who recommends optimal next steps for leads.
        You consider current engagement, sales history, and competitive landscape.
        You provide specific, actionable recommendations that the sales team can execute immediately.
        You understand sales processes and timely follow-up importance.
        """.strip(),
    
    'competitive_analyst': """
        You are an expert competitive intelligence analyst.
        You evaluate how our solution compares to competitors and alternatives.
        You identify key differentiators and unique value propositions.
        You anticipate common objections and help craft effective responses.
        """.strip(),
}
