"""
AI Lead Qualification Agent
Evaluates and scores leads based on multiple criteria
Uses rule-based scoring + text analysis for intelligent lead assessment
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class QualificationCategory(Enum):
    """Lead qualification categories"""
    HOT = "hot"          # Score 80-100: Ready to close
    WARM = "warm"        # Score 60-79: Needs nurturing
    COLD = "cold"        # Score 40-59: Long-term potential
    UNQUALIFIED = "unqualified"  # Score 0-39: Not a fit


@dataclass
class QualificationResult:
    """Result of lead qualification"""
    lead_id: int
    score: float  # 0-100
    category: str  # hot, warm, cold, unqualified
    reasoning: Dict[str, Any]
    recommendations: List[str]
    confidence: float  # 0-1
    analyzed_at: str


class CompanyFitAnalyzer:
    """Analyzes company fit based on size, industry, location"""
    
    # Industry interest mapping (industries we target)
    # Industry fit scores (0-100): how well each industry matches a B2B SaaS target market.
    # Previously these were 10-30, which is far too low (effective final impact was <4 pts).
    # Now calibrated so a top-tier industry (SaaS/AI) can contribute ~22 pts to the final score.
    TARGET_INDUSTRIES = {
        # Tier 1 — primary B2B SaaS targets
        'saas': 92,
        'software': 88,
        'technology': 88,
        'artificial intelligence': 92,
        'machine learning': 88,
        ' ai': 92,              # space-prefixed to avoid matching "email" etc.
        'data science': 85,
        'cybersecurity': 85,
        'cloud': 82,
        'devops': 78,
        # Tier 2 — strong secondary targets
        'fintech': 82,
        'healthtech': 78,
        'edtech': 78,
        'iot': 75,
        'blockchain': 70,
        'it services': 72,
        'erp': 72,
        # Tier 3 — moderate fit
        'enterprise': 72,
        'startup': 80,          # startups adopt SaaS quickly
        'b2b': 75,
        'ecommerce': 68,
        'marketing': 62,
        'digital': 62,
        'sales': 70,
        'consulting': 58,
        'agency': 58,
        'finance': 65,
        'analytics': 75,
        'media': 55,
        'social media': 55,
        'education': 60,
        'healthcare': 62,
        'health': 48,
        # Tier 4 — lower B2B fit
        'insurance': 50,
        'real estate': 42,
        'retail': 45,
        'b2c': 35,
    }
    
    # Company size tiers (larger = better fit for enterprise)
    COMPANY_SIZE_SCORES = {
        'enterprise': 30,  # 5000+ employees
        'large': 25,       # 500-5000 employees
        'mid': 25,         # 50-500 employees
        'small': 20,       # <50 employees
        'startup': 30,     # Early stage
    }
    
    def __init__(self):
        self.max_score = 100
    
    def analyze(self, company: str, industry: str, size: Optional[str] = None) -> Dict:
        """Analyze company fit"""
        score = 0
        factors = {}
        
        # Industry analysis (40 points max)
        industry_score = self._score_industry(industry)
        score += industry_score * 0.4
        factors['industry'] = {
            'score': industry_score,
            'weight': 0.4,
            'value': industry or 'unknown',
            'reasoning': f"Industry '{industry}' fit"
        }
        
        # Company size analysis (30 points max)
        size_score = self._score_company_size(size, company)
        score += size_score * 0.3
        factors['company_size'] = {
            'score': size_score,
            'weight': 0.3,
            'value': size or 'unknown',
            'reasoning': f"Company size '{size}' is target market"
        }
        
        # Company name power analysis (30 points max)
        # Known companies get higher scores (brand recognition)
        name_score = self._score_company_name(company)
        score += name_score * 0.3
        factors['company_reputation'] = {
            'score': name_score,
            'weight': 0.3,
            'value': company or 'unknown',
            'reasoning': f"Company '{company}' has market presence"
        }
        
        return {
            'total': min(score, 100),
            'factors': factors,
            'category': 'strong' if score >= 70 else 'moderate' if score >= 40 else 'weak'
        }
    
    def _score_industry(self, industry: str) -> float:
        """Score industry match (0-100)"""
        if not industry:
            return 25  # Unknown industry = can't target = weak signal

        industry_lower = industry.lower()

        # Direct match
        for key, value in self.TARGET_INDUSTRIES.items():
            if key in industry_lower:
                return value

        # Partial keyword matches — tech-adjacent
        keywords = ['tech', 'digital', 'online', 'software', 'app', 'cloud',
                    'intelligence', 'learn', 'data', 'cyber', 'analytic']
        for keyword in keywords:
            if keyword in industry_lower:
                return 65  # Tech-adjacent, decent fit

        return 40  # Industry present but not a known target
    
    def _score_company_size(self, size: Optional[str], company: str) -> float:
        """Score company size (0-100)"""
        if not size:
            # Try to infer from company name
            if company:
                c = company.lower()
                if any(w in c for w in ['enterprise', 'corporation', 'global', 'international']):
                    return 28
                if any(w in c for w in ['inc', 'corp', 'group', 'holdings']):
                    return 22
            return 20  # Unknown size — no positive signal, keep score honest

        size_lower = size.lower()
        for key, value in self.COMPANY_SIZE_SCORES.items():
            if key in size_lower:
                return value

        return 20
    
    def _score_company_name(self, company: str) -> float:
        """Score company based on name (0-100)"""
        if not company:
            return 15

        company_lower = company.lower()

        # Known/Fortune 500 patterns
        fortune500_keywords = [
            'amazon', 'google', 'microsoft', 'apple', 'facebook', 'meta',
            'tesla', 'walmart', 'uber', 'airbnb', 'netflix',
            'adobe', 'salesforce', 'oracle', 'ibm', 'intel', 'cisco',
        ]
        for keyword in fortune500_keywords:
            if keyword in company_lower:
                return 80

        # Formal legal entity → some size signal
        if any(w in company_lower for w in ['enterprise', 'corporation', 'global', 'international']):
            return 55
        if any(w in company_lower for w in ['corp', 'inc', 'group', 'holdings', 'ltd', 'llc', 'gmbh']):
            return 45

        # Has a company name that looks real (2+ words or mixed case)
        words = [w for w in company.split() if len(w) > 1]
        if len(words) >= 2:
            return 38

        # Single-word company name — minimal signal
        if len(company) > 3:
            return 28

        return 15


class BudgetIndicatorAnalyzer:
    """Analyzes budget indicators from lead data"""
    
    def __init__(self):
        self.budget_keywords = {
            'high': ['enterprise', 'unlimited', 'premium', 'dedicated', 'custom'],
            'medium': ['professional', 'business', 'plus', 'standard', 'team'],
            'low': ['free', 'basic', 'trial', 'starter', 'limited'],
        }
        
        self.revenue_patterns = {
            'high': [r'\$\d{3,}[mM]', r'billion', r'[mM]ultibillion'],
            'medium': [r'\$\d{1,2}[mM]', r'million'],
            'low': [r'\$\d{3,6}', r'thousand'],
        }
        
        self.decision_maker_keywords = [
            'ceo', 'cfo', 'cto', 'director', 'vp', 'vice president',
            'c-level', 'executive', 'founder', 'manager'
        ]
    
    def analyze(self, lead_data: Dict) -> Dict:
        """Analyze budget indicators"""
        score = 0
        factors = {}
        
        # Analyze from notes/interests
        text_data = {
            'notes': str(lead_data.get('notes', '')),
            'interests': str(lead_data.get('interests', '')),
            'position': str(lead_data.get('position', '')),
        }
        combined_text = ' '.join(text_data.values()).lower()
        
        # Budget level analysis (40 points)
        budget_score, budget_level = self._score_budget_level(combined_text)
        score += budget_score * 0.4
        factors['budget_level'] = {
            'score': budget_score,
            'weight': 0.4,
            'value': budget_level,
            'reasoning': f"Budget indicators suggest {budget_level} spend capacity"
        }
        
        # Decision maker analysis (40 points)
        decision_score = self._score_decision_maker(text_data['position'])
        score += decision_score * 0.4
        factors['decision_authority'] = {
            'score': decision_score,
            'weight': 0.4,
            'value': text_data['position'],
            'reasoning': "Decision maker seniority level"
        }
        
        # Revenue indicators (20 points)
        revenue_score = self._score_revenue_indicators(combined_text)
        score += revenue_score * 0.2
        factors['revenue_level'] = {
            'score': revenue_score,
            'weight': 0.2,
            'value': 'extracted',
            'reasoning': "Company revenue indicators in text"
        }
        
        return {
            'total': min(score, 100),
            'factors': factors,
            'category': 'high_budget' if score >= 70 else 'medium_budget' if score >= 40 else 'budget_conscious'
        }
    
    def _score_budget_level(self, text: str) -> Tuple[float, str]:
        """Score budget level (0-100)"""
        text_lower = text.lower()
        
        # Check high budget indicators
        for keyword in self.budget_keywords['high']:
            if keyword in text_lower:
                return 90, 'high'
        
        # Check medium budget indicators
        for keyword in self.budget_keywords['medium']:
            if keyword in text_lower:
                return 60, 'medium'
        
        # Check low budget indicators
        for keyword in self.budget_keywords['low']:
            if keyword in text_lower:
                return 30, 'low'
        
        return 30, 'unknown'
    
    def _score_decision_maker(self, position: str) -> float:
        """Score if person is decision maker (0-100)"""
        if not position:
            return 40  # Neutral if unknown
        
        position_lower = position.lower()
        
        # C-level/executive (100)
        if any(title in position_lower for title in ['ceo', 'cfo', 'cto', 'c-level', 'president']):
            return 100
        
        # Director/VP (80)
        if any(title in position_lower for title in ['director', 'vp', 'vice president', 'head of']):
            return 80
        
        # Manager (60)
        if 'manager' in position_lower or 'lead' in position_lower or 'senior' in position_lower:
            return 60
        
        # Analyst/Staff (40)
        if any(title in position_lower for title in ['analyst', 'engineer', 'specialist', 'coordinator']):
            return 40
        
        # Other (30)
        return 30
    
    def _score_revenue_indicators(self, text: str) -> float:
        """Score company revenue indicators (0-100)"""
        text_lower = text.lower()

        for pattern in self.revenue_patterns['high']:
            if re.search(pattern, text_lower):
                return 90

        for pattern in self.revenue_patterns['medium']:
            if re.search(pattern, text_lower):
                return 60

        for pattern in self.revenue_patterns['low']:
            if re.search(pattern, text_lower):
                return 40

        return 25  # No revenue signals — don't assume budget


class PainPointAnalyzer:
    """Analyzes pain points and interests match"""
    
    # Problem/solution keywords
    PAIN_POINTS = {
        'efficiency': ['slow', 'manual', 'repetitive', 'tedious', 'time-consuming', 'bottleneck'],
        'cost': ['expensive', 'high-cost', 'reduce costs', 'cost saving', 'budget'],
        'scaling': ['grow', 'scale', 'expansion', 'growth phase', 'scale up'],
        'integration': ['integration', 'api', 'sync', 'connect', 'seamless'],
        'analytics': ['insight', 'data', 'analytics', 'dashboard', 'reporting'],
        'automation': ['automate', 'automation', 'workflow', 'process'],
        'collaboration': ['team', 'collaboration', 'communication', 'sharing'],
        'security': ['security', 'compliance', 'safe', 'protection', 'data security'],
    }
    
    def analyze(self, lead_data: Dict) -> Dict:
        """Analyze pain points"""
        text_data = {
            'notes': str(lead_data.get('notes', '')),
            'interests': str(lead_data.get('interests', '')),
            'position': str(lead_data.get('position', '')),
        }
        combined_text = ' '.join(text_data.values()).lower()
        
        score = 0
        factors = {}
        identified_pain_points = []
        
        # Analyze each pain point category
        pain_point_scores = {}
        for category, keywords in self.PAIN_POINTS.items():
            category_score = self._score_pain_point_category(combined_text, keywords)
            pain_point_scores[category] = category_score
            
            if category_score > 0:
                identified_pain_points.append({
                    'category': category,
                    'relevance': category_score
                })
        
        # Average pain point relevance.
        # When no text data is available at all (scraped/company leads), return neutral
        # instead of zero — zero would unfairly destroy the score with 30% weight.
        meaningful_text = combined_text.replace('none', '').replace('[]', '').strip()
        if pain_point_scores:
            avg_score = sum(pain_point_scores.values()) / len(pain_point_scores)
            if avg_score == 0 and not meaningful_text:
                score = 40  # No text to analyze — neutral assumption
            else:
                score = avg_score * 100
        else:
            score = 40  # No categories — neutral assumption
        
        factors['identified_pain_points'] = {
            'score': min(score, 100),
            'weight': 1.0,
            'value': identified_pain_points,
            'reasoning': f"Identified {len(identified_pain_points)} relevant pain points"
        }
        
        return {
            'total': min(score, 100),
            'factors': factors,
            'pain_points': identified_pain_points,
            'category': 'strong_fit' if score >= 70 else 'good_fit' if score >= 40 else 'weak_fit'
        }
    
    def _score_pain_point_category(self, text: str, keywords: List[str]) -> float:
        """Score pain point category (0-1)"""
        matches = sum(1 for keyword in keywords if keyword in text)
        return matches / len(keywords) if keywords else 0


class ContactQualityAnalyzer:
    """Analyzes contact information quality"""
    
    def analyze(self, lead_data: Dict) -> Dict:
        """Analyze contact quality — uses pre-computed email_type when available."""
        score = 0
        factors = {}
        issues = []

        # email_type from data_points takes priority over domain guessing
        dp = lead_data.get('data_points') or {}
        email_type = (dp.get('email_type') or lead_data.get('email_type') or '').lower()

        # Email validation (40 points)
        email = lead_data.get('email', '')
        email_score = self._score_email_with_type(email, email_type)
        score += email_score * 0.4
        if not email:
            issues.append("Missing email")
        elif email_type in ('generated', 'generated_personal', 'generated_generic'):
            issues.append("Generated/fake email")
        factors['email_quality'] = {
            'score': email_score,
            'weight': 0.4,
            'value': email_type or email or 'missing',
            'reasoning': f"Email type: {email_type or 'domain-checked'}",
        }

        # Phone validation (30 points)
        phone = lead_data.get('phone', '')
        phone_score = self._score_phone(phone)
        score += phone_score * 0.3
        if not phone:
            issues.append("Missing phone number")
        factors['phone_quality'] = {
            'score': phone_score,
            'weight': 0.3,
            'value': phone or 'missing',
            'reasoning': "Phone validity and format",
        }

        # Name quality (20 points)
        name = lead_data.get('name', '')
        name_score = self._score_name(name)
        score += name_score * 0.2
        if not name or len(name.split()) < 2:
            issues.append("Missing or incomplete name")
        factors['name_quality'] = {
            'score': name_score,
            'weight': 0.2,
            'value': name or 'missing',
            'reasoning': "Name completeness",
        }

        # Company info (10 points bonus)
        company = lead_data.get('company', '')
        if company and len(company) > 2:
            score += 10
            factors['company_info'] = {
                'score': 100,
                'value': company,
                'reasoning': "Company information provided",
            }

        return {
            'total': min(score, 100),
            'factors': factors,
            'issues': issues,
            'category': 'high_quality' if score >= 70 else 'medium_quality' if score >= 40 else 'low_quality',
        }
    
    def _score_email(self, email: str) -> float:
        """Score email (0-100)"""
        if not email:
            return 0
        if self._is_valid_email(email):
            # Additional check for corporate domain
            if not any(domain in email.lower() for domain in ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']):
                return 100  # Corporate email
            return 70  # Free email (less valuable but still valid)
        return 30  # Invalid format but present
    
    def _score_phone(self, phone: str) -> float:
        """Score phone (0-100)"""
        if not phone:
            return 0
        if len(phone) >= 10 and any(c.isdigit() for c in phone):
            return 100
        return 30
    
    def _score_name(self, name: str) -> float:
        """Score name (0-100)"""
        if not name:
            return 0
        if len(name) > 3 and ' ' in name:
            return 100  # Full name
        if len(name) > 3:
            return 70  # Single name
        return 30
    
    def _is_valid_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def _score_email_with_type(self, email: str, email_type: str) -> float:
        """Score email using pre-computed email_type from validator when available."""
        if not email:
            return 0
        _GENERATED = {'generated', 'generated_personal', 'generated_generic'}
        et = (email_type or '').strip().lower()
        if et in _GENERATED:
            return 5   # Generated/fake email — nearly worthless
        if et == 'company':
            return 100
        if et in ('personal_business', 'personal'):
            return 80
        if et == 'generic':
            return 55
        if et == 'free':
            return 60
        # Fallback: domain-based check
        if self._is_valid_email(email):
            domain = email.split('@')[-1].lower()
            _FREE = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com',
                     'protonmail.com', 'icloud.com', 'aol.com', 'ymail.com'}
            return 90 if domain not in _FREE else 65
        return 30


class MarketTargetAnalyzer:
    """
    Scores how well a lead's location and product interest
    match the configured target market.
    The presence of ANY location or product already signals intent,
    so partial matches still earn meaningful points.
    """

    # High-value market locations (add your own cities/regions here)
    HIGH_VALUE_LOCATIONS = [
        'usa', 'us', 'united states', 'canada', 'uk', 'united kingdom',
        'australia', 'germany', 'france', 'singapore', 'uae', 'dubai',
        'new york', 'san francisco', 'london', 'toronto', 'sydney',
        'berlin', 'amsterdam', 'dubai', 'riyadh', 'mumbai', 'bangalore',
    ]

    # Known in-demand product categories
    HIGH_VALUE_PRODUCTS = [
        'ai', 'machine learning', 'automation', 'saas', 'analytics',
        'cloud', 'data', 'security', 'crm', 'erp', 'integration',
        'marketing', 'ecommerce', 'fintech', 'healthtech', 'edtech',
    ]

    def analyze(self, location: Optional[str], product: Optional[str],
                interests: Optional[List[str]]) -> Dict:
        """Return a 0-100 market-target score plus reasoning."""
        score = 0.0
        factors: Dict[str, Any] = {}

        # --- Location score (50 pts) ---
        if location:
            loc_lower = location.lower()
            if any(hv in loc_lower for hv in self.HIGH_VALUE_LOCATIONS):
                loc_score = 100.0
                loc_reason = f"'{location}' is a high-value target market"
            else:
                # Any location given = at least 60 points (we know where they are)
                loc_score = 60.0
                loc_reason = f"Location '{location}' available (outside tier-1 markets)"
        else:
            loc_score = 0.0
            loc_reason = "No location provided — cannot geo-target"

        score += loc_score * 0.5
        factors['location'] = {
            'score': loc_score,
            'weight': 0.5,
            'value': location or 'unknown',
            'reasoning': loc_reason,
        }

        # --- Product/interest score (50 pts) ---
        product_text = ' '.join(filter(None, [
            product or '',
            ' '.join(interests or []),
        ])).lower()

        if product_text.strip():
            matched = [kw for kw in self.HIGH_VALUE_PRODUCTS if kw in product_text]
            if matched:
                prod_score = min(100.0, 60.0 + len(matched) * 10.0)
                prod_reason = f"Matched high-value products: {', '.join(matched)}"
            else:
                prod_score = 50.0  # Has a product/interest, just not a top keyword
                prod_reason = "Product interest captured; refine to match catalogue"
        else:
            prod_score = 30.0
            prod_reason = "No product or interest data — enrich to improve score"

        score += prod_score * 0.5
        factors['product_interest'] = {
            'score': prod_score,
            'weight': 0.5,
            'value': product or (interests[0] if interests else 'unknown'),
            'reasoning': prod_reason,
        }

        total = min(score, 100.0)
        return {
            'total': total,
            'factors': factors,
            'category': 'perfect_fit' if total >= 80 else 'good_fit' if total >= 50 else 'weak_fit',
        }


class QualificationAgent:
    """Main AI qualification agent"""

    def __init__(self):
        self.company_fit_analyzer = CompanyFitAnalyzer()
        self.budget_analyzer = BudgetIndicatorAnalyzer()
        self.pain_point_analyzer = PainPointAnalyzer()
        self.contact_analyzer = ContactQualityAnalyzer()
        self.market_target_analyzer = MarketTargetAnalyzer()

    def qualify_lead(self, lead_data: Dict) -> QualificationResult:
        """Qualify a lead and return score + category"""
        
        # Run all analyzers
        company_fit = self.company_fit_analyzer.analyze(
            lead_data.get('company', ''),
            lead_data.get('industry', ''),
            lead_data.get('company_size')
        )
        
        budget = self.budget_analyzer.analyze(lead_data)
        pain_points = self.pain_point_analyzer.analyze(lead_data)
        contact_quality = self.contact_analyzer.analyze(lead_data)
        market_target = self.market_target_analyzer.analyze(
            lead_data.get('location'),
            lead_data.get('product'),
            lead_data.get('interests') or [],
        )
        
        # Aggregate scoring — calibrated for real scraped/enriched B2B leads
        # pain_points reduced (30→15%) because most leads have no notes/text
        # contact_quality raised (15→25%) because email_type is a strong signal
        # company_fit raised (20→25%) because industry is primary B2B differentiator
        # data_richness bonus applied after weighted sum (LinkedIn, website, completeness)
        weights = {
            'company_fit':     0.25,
            'budget':          0.20,
            'pain_points':     0.15,
            'contact_quality': 0.25,
            'market_target':   0.15,
        }

        weighted_score = (
            company_fit['total']    * weights['company_fit'] +
            budget['total']         * weights['budget'] +
            pain_points['total']    * weights['pain_points'] +
            contact_quality['total'] * weights['contact_quality'] +
            market_target['total']  * weights['market_target']
        )

        # Data-richness bonus (up to +10 pts) — rewards leads with more signals
        dp_data = lead_data.get('data_points') or {}
        richness_bonus = 0.0
        if lead_data.get('linkedin_url'):
            richness_bonus += 4.0
        if lead_data.get('website'):
            richness_bonus += 3.0
        cs = float(lead_data.get('completeness_score') or 0)
        if cs > 50:
            richness_bonus += min((cs - 50) * 0.06, 3.0)

        # Penalty for generated/fake email
        email_type_val = (dp_data.get('email_type') or lead_data.get('email_type') or '').lower()
        generated_penalty = 15.0 if email_type_val in (
            'generated', 'generated_personal', 'generated_generic') else 0.0

        final_score = max(0.0, min(weighted_score + richness_bonus - generated_penalty, 100.0))

        # Hard cap: if the only contact signal is a non-personal email (generic/generated)
        # and there is no phone or LinkedIn, the lead is unreachable — clamp to COLD max (55).
        # A great company name should not rescue a lead that cannot actually be contacted.
        _NO_REAL_CONTACT_EMAIL_TYPES = {
            'generated', 'generated_personal', 'generated_generic', 'generic',
        }
        has_phone = bool(lead_data.get('phone', ''))
        has_linkedin = bool(lead_data.get('linkedin_url', ''))
        no_real_contact = (
            email_type_val in _NO_REAL_CONTACT_EMAIL_TYPES
            and not has_phone
            and not has_linkedin
        )
        if no_real_contact and final_score > 55.0:
            final_score = 55.0

        # Determine category — aligned with MLDecisionLayer thresholds (80/60)
        if final_score >= 80:
            category = QualificationCategory.HOT.value
        elif final_score >= 60:
            category = QualificationCategory.WARM.value
        elif final_score >= 30:
            category = QualificationCategory.COLD.value
        else:
            category = QualificationCategory.UNQUALIFIED.value
        
        # Build reasoning
        reasoning = {
            'company_fit': company_fit,
            'budget_indicators': budget,
            'pain_points': {
                'score': pain_points['total'],
                'identified': pain_points.get('pain_points', [])
            },
            'contact_quality': {
                'score': contact_quality['total'],
                'issues': contact_quality.get('issues', [])
            },
            'market_target': {
                'score': market_target['total'],
                'category': market_target['category'],
                'factors': market_target['factors'],
            },
            'weights': weights,
        }
        
        # Generate recommendations
        recommendations = self._generate_recommendations(category, reasoning)
        
        # Calculate confidence (0-1)
        confidence = self._calculate_confidence(lead_data)
        
        return QualificationResult(
            lead_id=lead_data.get('id') or 0,
            score=round(final_score, 1),
            category=category,
            reasoning=reasoning,
            recommendations=recommendations,
            confidence=round(confidence, 2),
            analyzed_at=datetime.now(timezone.utc).isoformat()
        )
    
    def _generate_recommendations(self, category: str, reasoning: Dict) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Category-based recommendations
        if category == 'hot':
            recommendations.append("🔥 PRIORITY: Contact immediately - high conversion potential")
            recommendations.append("Prepare customized demo focusing on identified pain points")
            recommendations.append("Escalate to senior sales rep for direct outreach")
        
        elif category == 'warm':
            recommendations.append("⚡ Schedule call within 48-72 hours")
            recommendations.append("Send personalized case study relevant to their industry")
            recommendations.append("Nurture with targeted content")
        
        elif category == 'cold':
            recommendations.append("❄️ Add to nurture campaign for long-term engagement")
            recommendations.append("Monitor for engagement signals")
            recommendations.append("Revisit in 30 days with updated content")
        
        else:
            recommendations.append("⛔ Not a fit - consider removing from active pipeline")
            recommendations.append("Keep in database for future re-qualification")
        
        # Data quality recommendations
        contact_issues = reasoning.get('contact_quality', {}).get('issues', [])
        if contact_issues:
            recommendations.append(f"⚠️ Data quality: {', '.join(contact_issues)}")
        
        # Market target recommendations
        market = reasoning.get('market_target', {})
        market_score = market.get('score', 0)
        if market_score >= 80:
            recommendations.append("📍 Exact location + product match — prioritise outreach NOW")
        elif market_score >= 50:
            recommendations.append("📍 Good market fit on location/product — personalise your pitch")
        elif market_score < 30:
            recommendations.append("📍 Location or product data missing — enrich before contacting")
        
        return recommendations
    
    def _calculate_confidence(self, lead_data: Dict) -> float:
        """Calculate confidence level (0-1)"""
        confidence = 0.5
        
        # More data = higher confidence
        filled_fields = sum(1 for v in lead_data.values() if v)
        confidence += (filled_fields / 10) * 0.3
        
        # Valid email/phone = higher confidence
        if self._has_valid_contact(lead_data):
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _has_valid_contact(self, lead_data: Dict) -> bool:
        """Check if lead has valid contact info — generated emails do not count."""
        dp = lead_data.get('data_points') or {}
        email_type = (dp.get('email_type') or lead_data.get('email_type') or '').lower()
        _FAKE = {'generated', 'generated_personal', 'generated_generic'}

        email = lead_data.get('email', '')
        phone = lead_data.get('phone', '')

        email_valid = (
            email_type not in _FAKE
            and bool(email and isinstance(email, str)
                     and re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))
        )
        phone_valid = len(str(phone).replace('-', '').replace(' ', '')) >= 10

        return email_valid or phone_valid
    
    def batch_qualify(self, leads: List[Dict]) -> List[QualificationResult]:
        """Qualify multiple leads"""
        results = []
        for lead in leads:
            try:
                result = self.qualify_lead(lead)
                results.append(result)
                logger.info(f"Qualified lead {lead.get('id')}: score={result.score}, category={result.category}")
            except Exception as e:
                logger.error(f"Error qualifying lead {lead.get('id')}: {str(e)}")
        
        return results
    
    def explain_score(self, result: QualificationResult) -> str:
        """Generate human-readable explanation of score"""
        explanation = f"""
🎯 LEAD QUALIFICATION REPORT
{'='*50}

Lead ID: {result.lead_id}
Score: {result.score}/100
Category: {result.category.upper()}
Confidence: {result.confidence * 100:.0f}%

SCORING BREAKDOWN:
{'-'*50}

Company Fit ({result.reasoning['company_fit']['total']:.0f}/100):
  {result.reasoning['company_fit']['factors']}

Budget Indicators ({result.reasoning['budget_indicators']['total']:.0f}/100):
  {result.reasoning['budget_indicators']['factors']}

Pain Points Match ({result.reasoning['pain_points']['score']:.0f}/100):
  {result.reasoning['pain_points']}

Contact Quality ({result.reasoning['contact_quality']['score']:.0f}/100):
  {result.reasoning['contact_quality']}

RECOMMENDATIONS:
{'-'*50}
"""
        for i, rec in enumerate(result.recommendations, 1):
            explanation += f"{i}. {rec}\n"
        
        return explanation
