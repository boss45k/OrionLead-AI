"""
Intelligent Lead Data Collection Agent
Collects leads from public sources and classifies them by intent and product interest
Uses public APIs and ethical scraping only
"""

import re
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ProductCategories:
    """Product category definitions with keywords and signals"""
    
    CATEGORIES = {
        'laptops': {
            'keywords': ['laptop', 'notebook', 'macbook', 'computer', 'ultrabook'],
            'signals': ['gaming', 'cpu', 'gpu', 'ssd', 'ram', 'performance', 'battery'],
            'price_range': (300, 5000),
            'intent_words': ['buy', 'purchase', 'looking for', 'need', 'recommend'],
        },
        'electronics': {
            'keywords': ['phone', 'smartphone', 'tablet', 'iphone', 'android', 'headphones', 'earbuds'],
            'signals': ['5g', '4g', 'battery life', 'camera', 'specs', 'wireless'],
            'price_range': (50, 2000),
            'intent_words': ['buy', 'switch to', 'upgrade', 'get', 'considering'],
        },
        'clothing': {
            'keywords': ['clothes', 'fashion', 'apparel', 'shirt', 'pants', 'dress', 'outfit'],
            'signals': ['size', 'style', 'brand', 'material', 'color', 'fit'],
            'price_range': (10, 500),
            'intent_words': ['buy', 'looking for', 'need', 'recommend', 'suggest'],
        },
        'smart_devices': {
            'keywords': ['smart home', 'iot', 'ring', 'echo', 'google home', 'automation', 'connected'],
            'signals': ['wifi', 'voice control', 'app', 'integration', 'compatible'],
            'price_range': (20, 1000),
            'intent_words': ['setup', 'looking for', 'buy', 'install', 'recommend'],
        },
        'home_appliances': {
            'keywords': ['refrigerator', 'oven', 'microwave', 'dishwasher', 'washing machine', 'appliance'],
            'signals': ['energy efficient', 'warranty', 'capacity', 'size', 'features'],
            'price_range': (100, 3000),
            'intent_words': ['need', 'looking for', 'buy', 'replace', 'recommend'],
        },
        'gaming': {
            'keywords': ['gaming', 'game', 'console', 'ps5', 'xbox', 'gpu', 'gamer', 'fps', 'rpg'],
            'signals': ['fps', 'graphics', 'performance', 'speedrun', 'multiplayer', 'mods'],
            'price_range': (20, 2000),
            'intent_words': ['looking for', 'recommend', 'best', 'should i', 'worth it'],
        },
        'fitness': {
            'keywords': ['fitness', 'gym', 'workout', 'exercise', 'training', 'running', 'yoga'],
            'signals': ['calories', 'weight loss', 'strength', 'endurance', 'routine', 'equipment'],
            'price_range': (10, 500),
            'intent_words': ['looking for', 'recommend', 'trying', 'need', 'best for'],
        },
        'beauty': {
            'keywords': ['beauty', 'skincare', 'makeup', 'cosmetic', 'moisturizer', 'serum', 'lotion'],
            'signals': ['ingredients', 'skin type', 'reviews', 'cruelty-free', 'natural', 'sensitive'],
            'price_range': (5, 500),
            'intent_words': ['looking for', 'recommend', 'need', 'trying', 'best for'],
        }
    }

class IntentClassifier:
    """Classifies user intent based on text analysis"""
    
    # High intent signals
    HIGH_INTENT_PATTERNS = [
        r'\bi\s+want\s+to\s+buy\b',
        r'\blooking\s+to\s+purchase\b',
        r'\bplanning\s+to\s+get\b',
        r'\bshould\s+i\s+buy\b',
        r'\bis\s+it\s+worth\s+the\s+price\b',
        r'\bbest\s+value\s+for\b',
        r'\bwhere\s+can\s+i\s+buy\b',
        r'\banyone\s+bought\b',
        r'\bhow\s+much\s+does\b.*\bcost\b',
        r'\bugrading?\s+to\b',
    ]
    
    # Medium intent signals
    MEDIUM_INTENT_PATTERNS = [
        r'\blooking\s+for\s+recommendations\b',
        r'\bwhat\s+do\s+you\s+think\s+about\b',
        r'\bhow\s+does\b.*\bcompare\s+to\b',
        r'\banyone\s+have\s+experience\s+with\b',
        r'\btrying\s+to\s+decide\b',
        r'\bwhich\s+one\s+should\s+i\s+get\b',
        r'\brecently\s+bought\b',
        r'\bhas\s+anyone\s+tried\b',
    ]
    
    # Low intent signals  
    LOW_INTENT_PATTERNS = [
        r'\banyone\s+know\s+about\b',
        r'\bjust\s+curious\b',
        r'\binteresting\s+product\b',
        r'\bnever\s+heard\s+of\b',
        r'\bthat\s+sounds\s+cool\b',
        r'\bcasual\s+discussion\b',
    ]
    
    @staticmethod
    def classify_intent(text: str) -> Dict[str, Any]:
        """
        Classify user intent from text
        
        Returns:
            {
                'level': 'high' | 'medium' | 'low',
                'score': float (0.0 - 1.0),
                'confidence': float,
                'matched_pattern': str
            }
        """
        text_lower = text.lower()
        
        # Check high intent patterns
        for pattern in IntentClassifier.HIGH_INTENT_PATTERNS:
            if re.search(pattern, text_lower):
                return {
                    'level': 'high',
                    'score': 0.85,
                    'confidence': 0.9,
                    'matched_pattern': pattern
                }
        
        # Check medium intent patterns
        for pattern in IntentClassifier.MEDIUM_INTENT_PATTERNS:
            if re.search(pattern, text_lower):
                return {
                    'level': 'medium',
                    'score': 0.55,
                    'confidence': 0.8,
                    'matched_pattern': pattern
                }
        
        # Check low intent patterns
        for pattern in IntentClassifier.LOW_INTENT_PATTERNS:
            if re.search(pattern, text_lower):
                return {
                    'level': 'low',
                    'score': 0.25,
                    'confidence': 0.7,
                    'matched_pattern': pattern
                }
        
        # Default: analyze keyword frequency
        words = text_lower.split()
        if len(words) > 50:  # Long detailed discussion
            intent_score = 0.4
        elif len(words) > 20:  # Medium length
            intent_score = 0.3
        else:  # Short
            intent_score = 0.15
        
        return {
            'level': 'low',
            'score': intent_score,
            'confidence': 0.5,
            'matched_pattern': 'default_analysis'
        }

class InterestDetector:
    """Detects product interest from text"""
    
    @staticmethod
    def detect_interests(text: str) -> Dict[str, Any]:
        """
        Detect product interests from text
        
        Returns:
            {
                'category': str,
                'confidence': float,
                'keywords_found': List[str],
                'signals': List[str],
                'budget_mentioned': bool,
                'budget_amount': Optional[int],
                'specificity_score': float
            }
        """
        text_lower = text.lower()
        detected = {
            'category': None,
            'confidence': 0.0,
            'keywords_found': [],
            'signals': [],
            'budget_mentioned': False,
            'budget_amount': None,
            'specificity_score': 0.0
        }
        
        best_match = None
        best_score = 0.0
        
        # Find best matching category
        for category, config in ProductCategories.CATEGORIES.items():
            keywords_found = []
            signals_found = []
            
            # Check keywords
            for keyword in config['keywords']:
                if keyword in text_lower:
                    keywords_found.append(keyword)
            
            # Check signals
            for signal in config['signals']:
                if signal in text_lower:
                    signals_found.append(signal)
            
            # Calculate match score
            keyword_hits = len(keywords_found)
            signal_hits = len(signals_found)
            match_score = (keyword_hits * 0.6) + (signal_hits * 0.4)
            
            if match_score > best_score:
                best_score = match_score
                best_match = category
                detected['keywords_found'] = keywords_found
                detected['signals'] = signals_found
        
        if best_match:
            detected['category'] = best_match
            detected['confidence'] = min(0.95, best_score / 10)  # Normalize to 0-0.95
        
        # Detect budget mention
        budget_pattern = r'\$[\d,]+|\b\d+\s*(?:dollars?|bucks?|usd)\b'
        budget_match = re.search(budget_pattern, text_lower)
        if budget_match:
            detected['budget_mentioned'] = True
            # Extract amount
            amount_str = re.findall(r'\d+', budget_match.group())
            if amount_str:
                detected['budget_amount'] = int(amount_str[0])
        
        # Calculate specificity score
        specificity_elements = [
            len(detected['keywords_found']) > 0,
            len(detected['signals']) > 0,
            detected['budget_mentioned'],
            len(text) > 100
        ]
        detected['specificity_score'] = sum(specificity_elements) / len(specificity_elements)
        
        return detected

class LeadScorer:
    """Scores leads based on multiple factors"""
    
    @staticmethod
    def score_lead(lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score a lead using weighted factors
        
        Weights:
        - Intent: 40%
        - Specificity: 40%
        - Recency: 15%
        - Activity: 5%
        
        Returns:
            {
                'final_score': float (0.0 - 1.0),
                'intent_score': float,
                'specificity_score': float,
                'recency_score': float,
                'activity_score': float,
                'classification': 'premium' | 'quality' | 'potential' | 'low'
            }
        """
        
        # Intent score (40%)
        intent_data = lead_data.get('intent', {})
        intent_score = intent_data.get('score', 0.0)
        
        # Specificity score (40%)
        interest_data = lead_data.get('interest', {})
        specificity_score = interest_data.get('specificity_score', 0.0)
        
        # Recency score (15%)
        activity_date = lead_data.get('source', {}).get('date_activity')
        recency_score = LeadScorer._calculate_recency_score(activity_date)
        
        # Activity score (5%)
        activity_level = lead_data.get('activity_level', 0.5)
        activity_score = min(1.0, activity_level)
        
        # Calculate weighted final score
        final_score = (
            (intent_score * 0.40) +
            (specificity_score * 0.40) +
            (recency_score * 0.15) +
            (activity_score * 0.05)
        )
        
        # Classify lead quality
        if final_score >= 0.80:
            classification = 'premium'
        elif final_score >= 0.60:
            classification = 'quality'
        elif final_score >= 0.40:
            classification = 'potential'
        else:
            classification = 'low'
        
        return {
            'final_score': final_score,
            'intent_score': intent_score,
            'specificity_score': specificity_score,
            'recency_score': recency_score,
            'activity_score': activity_score,
            'classification': classification
        }
    
    @staticmethod
    def _calculate_recency_score(activity_date: Optional[str]) -> float:
        """Calculate recency score (1.0 = today, 0.0 = >30 days old)"""
        if not activity_date:
            return 0.5
        
        try:
            activity = datetime.fromisoformat(activity_date.replace('Z', '+00:00'))
            days_old = (datetime.utcnow() - activity).days
            
            if days_old == 0:
                return 1.0
            elif days_old <= 7:
                return 0.9
            elif days_old <= 14:
                return 0.7
            elif days_old <= 30:
                return 0.4
            else:
                return 0.1
        except:
            return 0.5

class PublicLeadExtractor:
    """Extracts lead data from public content"""
    
    @staticmethod
    def extract_lead_info(content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured lead information from content
        
        Input content structure:
            {
                'author': str,
                'text': str,
                'source': 'reddit' | 'forum' | 'blog',
                'url': str,
                'date': str,
                'subreddit/forum': str (optional)
            }
        """
        
        text = content.get('text', '')
        
        # Detect interests
        interest_detector = InterestDetector()
        interests = interest_detector.detect_interests(text)
        
        # Classify intent
        intent_classifier = IntentClassifier()
        intent = intent_classifier.classify_intent(text)
        
        # Structure lead
        lead = {
            'name': content.get('author'),
            'source': {
                'platform': content.get('source', 'unknown'),
                'url': content.get('url'),
                'date_activity': content.get('date'),
                'forum_topic': content.get('forum', content.get('subreddit'))
            },
            'interest': interests,
            'intent': intent,
            'activity_level': 0.6,  # Default, would be calculated from historical data
            'raw_content': text[:500]  # First 500 chars for reference
        }
        
        # Score the lead
        scorer = LeadScorer()
        scoring = scorer.score_lead(lead)
        lead['scoring'] = scoring
        
        # Determine if lead is quality
        lead['is_quality'] = scoring['classification'] in ['premium', 'quality']
        
        return lead

class IntelligentLeadAgent:
    """Main agent that coordinates lead collection"""
    
    def __init__(self):
        self.extractor = PublicLeadExtractor()
        self.seen_urls = set()
    
    def process_content(self, content_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a batch of content and extract leads
        
        Args:
            content_list: List of content dictionaries from public sources
            
        Returns:
            List of structured leads with scores
        """
        leads = []
        
        for content in content_list:
            # Skip if already processed
            url = content.get('url')
            if url and url in self.seen_urls:
                continue
            
            if url:
                self.seen_urls.add(url)
            
            # Extract lead
            lead = self.extractor.extract_lead_info(content)
            leads.append(lead)
        
        # Sort by score (highest first)
        leads.sort(key=lambda x: x.get('scoring', {}).get('final_score', 0), reverse=True)
        
        return leads
    
    def format_for_database(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert intelligent agent leads to database format"""
        formatted = []
        
        for lead in leads:
            scoring = lead.get('scoring', {})
            interest = lead.get('interest', {})
            intent = lead.get('intent', {})
            
            formatted_lead = {
                'name': lead.get('name', 'Unknown'),
                'email': None,  # Not publicly scraped
                'company': interest.get('category', 'Unknown'),
                'position': 'Interested Contact',
                'location': lead.get('source', {}).get('forum_topic', ''),
                'country': '',
                'city': '',
                'industry': interest.get('category', ''),
                'website': lead.get('source', {}).get('url', ''),
                'linkedin_url': None,
                'interests': interest.get('keywords_found', []),
                'source': 'intelligent_agent',
                'status': 'pending',
                'qualification_score': scoring.get('final_score', 0.0) * 100,
                'data_points': {
                    'agent_analysis': {
                        'category': interest.get('category'),
                        'intent_level': intent.get('level'),
                        'budget_mentioned': interest.get('budget_mentioned'),
                        'budget_amount': interest.get('budget_amount'),
                        'specificity_score': interest.get('specificity_score'),
                        'source_url': lead.get('source', {}).get('url'),
                        'platform': lead.get('source', {}).get('platform'),
                    },
                    'classification': scoring.get('classification'),
                    'scoring_breakdown': {
                        'intent': scoring.get('intent_score'),
                        'specificity': scoring.get('specificity_score'),
                        'recency': scoring.get('recency_score'),
                        'activity': scoring.get('activity_score'),
                    }
                }
            }
            
            formatted.append(formatted_lead)
        
        return formatted

# Example usage for testing
if __name__ == '__main__':
    # Test with sample content
    sample_content = [
        {
            'author': 'tech_enthusiast',
            'text': 'Looking for a gaming laptop under $1500. I need something with good CPU and GPU for AAA games. Anyone have recommendations?',
            'source': 'reddit',
            'url': 'https://reddit.com/r/gaming/...',
            'date': '2026-03-31T10:30:00Z',
            'subreddit': 'r/gaming'
        },
        {
            'author': 'fitness_user',
            'text': 'Just started my fitness journey. Looking for recommendations on workout equipment and training routines.',
            'source': 'forum',
            'url': 'https://forum.fitness.com/...',
            'date': '2026-03-31T09:15:00Z',
            'forum': 'Fitness Discussion'
        }
    ]
    
    # Process content
    agent = IntelligentLeadAgent()
    leads = agent.process_content(sample_content)
    
    print(f"✅ Processed {len(leads)} leads")
    for lead in leads:
        print(f"\n📊 Lead: {lead['name']}")
        print(f"   Category: {lead['interest']['category']}")
        print(f"   Intent: {lead['intent']['level']}")
        print(f"   Score: {lead['scoring']['final_score']:.2%}")
