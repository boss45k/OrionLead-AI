"""
Qualification Rules Engine
Rule-based lead qualification system using configurable scoring rules
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RuleType(Enum):
    """Rule types for qualification"""
    FIELD_MATCH = "field_match"  # Exact field matching
    PATTERN_MATCH = "pattern_match"  # Regex pattern matching
    SCORE_THRESHOLD = "score_threshold"  # Score comparisons
    STRING_CONTAINS = "string_contains"  # Substring matching
    NUMERIC_RANGE = "numeric_range"  # Numeric range checking
    LIST_CONTAINS = "list_contains"  # Check if value in list


class RuleOperator(Enum):
    """Operators for rule conditions"""
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_EQUAL = "ge"
    LESS_EQUAL = "le"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


@dataclass
class Rule:
    """Individual qualification rule"""
    
    name: str
    rule_type: RuleType
    field: str
    operator: RuleOperator
    value: Any
    score: float  # Points to add if rule matches
    weight: float = 1.0  # Rule importance weight
    priority: int = 0  # Higher priority rules evaluated first
    enabled: bool = True

    def apply(self, lead_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Apply rule to lead data
        
        Args:
            lead_data: Lead data dictionary
            
        Returns:
            Tuple of (rule_matched, explanation)
        """
        if not self.enabled:
            return False, "Rule disabled"
        
        field_value = lead_data.get(self.field)
        
        if field_value is None:
            return False, f"Field '{self.field}' not found"
        
        try:
            if self.operator == RuleOperator.EQUALS:
                matched = field_value == self.value
            elif self.operator == RuleOperator.NOT_EQUALS:
                matched = field_value != self.value
            elif self.operator == RuleOperator.GREATER_THAN:
                matched = float(field_value) > float(self.value)
            elif self.operator == RuleOperator.LESS_THAN:
                matched = float(field_value) < float(self.value)
            elif self.operator == RuleOperator.GREATER_EQUAL:
                matched = float(field_value) >= float(self.value)
            elif self.operator == RuleOperator.LESS_EQUAL:
                matched = float(field_value) <= float(self.value)
            elif self.operator == RuleOperator.IN:
                matched = field_value in self.value
            elif self.operator == RuleOperator.NOT_IN:
                matched = field_value not in self.value
            elif self.operator == RuleOperator.CONTAINS:
                matched = str(self.value).lower() in str(field_value).lower()
            elif self.operator == RuleOperator.NOT_CONTAINS:
                matched = str(self.value).lower() not in str(field_value).lower()
            elif self.operator == RuleOperator.STARTS_WITH:
                matched = str(field_value).lower().startswith(str(self.value).lower())
            elif self.operator == RuleOperator.ENDS_WITH:
                matched = str(field_value).lower().endswith(str(self.value).lower())
            else:
                return False, f"Unknown operator: {self.operator}"
            
            explanation = f"Rule '{self.name}' {'matched' if matched else 'not matched'}"
            return matched, explanation
            
        except Exception as e:
            logger.error(f"Error applying rule '{self.name}': {str(e)}")
            return False, f"Error: {str(e)}"


@dataclass
class RuleResult:
    """Result of rule evaluation"""
    
    rule_name: str
    matched: bool
    score: float
    explanation: str


class QualificationRulesEngine:
    """
    Rule-based lead qualification engine
    Evaluates leads against configurable rules with scoring
    """
    
    def __init__(self, min_confidence: float = 0.5):
        """
        Initialize rules engine
        
        Args:
            min_confidence: Minimum confidence score (0-1) for qualification
        """
        self.rules: List[Rule] = []
        self.min_confidence = min_confidence
        self.logger = logging.getLogger(f"{__name__}.engine")
    
    def add_rule(self, rule: Rule) -> None:
        """Add a rule to the engine"""
        self.rules.append(rule)
        logger.info(f"Added rule: {rule.name}")
    
    def add_rules_batch(self, rules: List[Rule]) -> None:
        """Add multiple rules"""
        for rule in rules:
            self.add_rule(rule)
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove rule by name"""
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                self.rules.pop(i)
                logger.info(f"Removed rule: {rule_name}")
                return True
        return False
    
    def get_rule(self, rule_name: str) -> Optional[Rule]:
        """Get rule by name"""
        for rule in self.rules:
            if rule.name == rule_name:
                return rule
        return None
    
    def qualify_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Qualify lead using rules engine
        
        Args:
            lead_data: Lead data to evaluate
            
        Returns:
            Qualification result with score and matched rules
        """
        if not self.rules:
            return {
                'qualified': False,
                'score': 0.0,
                'confidence': 0.0,
                'matched_rules': [],
                'message': 'No rules configured',
            }
        
        total_score = 0.0
        max_possible_score = 0.0
        matched_rules: List[Dict[str, Any]] = []
        
        # Sort rules by priority (higher first)
        sorted_rules = sorted(self.rules, key=lambda r: r.priority, reverse=True)
        
        for rule in sorted_rules:
            max_possible_score += abs(rule.score) * rule.weight
            
            matched, explanation = rule.apply(lead_data)
            
            if matched:
                score_contribution = rule.score * rule.weight
                total_score += score_contribution
                
                matched_rules.append({
                    'name': rule.name,
                    'score': score_contribution,
                    'explanation': explanation,
                })
                
                logger.debug(
                    f"Rule matched: {rule.name} (+{score_contribution})",
                    extra={'lead_id': lead_data.get('id', 'unknown')},
                )
        
        # Calculate confidence score (0-1)
        confidence = 0.0
        if max_possible_score > 0:
            confidence = min(1.0, max(0.0, total_score / max_possible_score))
        
        qualified = confidence >= self.min_confidence
        
        result = {
            'qualified': qualified,
            'score': total_score,
            'confidence': confidence,
            'max_possible_score': max_possible_score,
            'matched_rules': matched_rules,
            'total_rules': len(self.rules),
            'rules_matched': len(matched_rules),
            'message': f"Lead {'qualified' if qualified else 'not qualified'} with {confidence:.2%} confidence",
        }
        
        self.logger.info(
            result['message'],
            extra={
                'lead_id': lead_data.get('id', 'unknown'),
                'confidence': confidence,
                'rules_matched': len(matched_rules),
            },
        )
        
        return result
    
    @staticmethod
    def create_default_rules() -> List[Rule]:
        """Create default qualification rules for B2B SaaS"""
        return [
            # Company size rules
            Rule(
                name="company_size_large",
                rule_type=RuleType.NUMERIC_RANGE,
                field="company_size",
                operator=RuleOperator.GREATER_EQUAL,
                value=501,
                score=30.0,
                weight=1.0,
                priority=1,
            ),
            Rule(
                name="company_size_medium",
                rule_type=RuleType.NUMERIC_RANGE,
                field="company_size",
                operator=RuleOperator.GREATER_EQUAL,
                value=101,
                score=15.0,
                weight=1.0,
                priority=2,
            ),
            
            # Industry rules
            Rule(
                name="target_industry",
                rule_type=RuleType.LIST_CONTAINS,
                field="industry",
                operator=RuleOperator.IN,
                value=["Technology", "Finance", "Healthcare", "SaaS", "Enterprise"],
                score=25.0,
                weight=1.0,
                priority=1,
            ),
            
            # Decision maker rules
            Rule(
                name="is_decision_maker",
                rule_type=RuleType.FIELD_MATCH,
                field="job_title",
                operator=RuleOperator.IN,
                value=["CTO", "VP of Engineering", "Director", "Manager", "Head"],
                score=40.0,
                weight=1.0,
                priority=0,
            ),
            
            # Budget indicator
            Rule(
                name="has_budget",
                rule_type=RuleType.FIELD_MATCH,
                field="budget_available",
                operator=RuleOperator.EQUALS,
                value=True,
                score=35.0,
                weight=1.0,
                priority=0,
            ),
            
            # Timeline indicator
            Rule(
                name="active_timeline",
                rule_type=RuleType.FIELD_MATCH,
                field="timeline",
                operator=RuleOperator.IN,
                value=["This Month", "This Quarter", "This Year"],
                score=20.0,
                weight=1.0,
                priority=2,
            ),
            
            # Contact quality
            Rule(
                name="verified_email",
                rule_type=RuleType.FIELD_MATCH,
                field="email_verified",
                operator=RuleOperator.EQUALS,
                value=True,
                score=10.0,
                weight=1.0,
                priority=3,
            ),
            
            # Engagement signals
            Rule(
                name="high_engagement",
                rule_type=RuleType.NUMERIC_RANGE,
                field="engagement_score",
                operator=RuleOperator.GREATER_EQUAL,
                value=70,
                score=25.0,
                weight=1.0,
                priority=1,
            ),
        ]
