import time
import logging

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class WebScraper:
    """Web scraping service for data collection"""
    
    def __init__(self, rate_limit=10, timeout=30):
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_url(self, url):
        """Fetch content from URL"""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            time.sleep(1 / self.rate_limit)
            return response.text
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None
    
    def extract_emails(self, html_content):
        """Extract email addresses from HTML"""
        import re
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, html_content)
        return list(set(emails))
    
    def extract_phones(self, html_content):
        """Extract phone numbers from HTML"""
        import re
        phone_pattern = r'[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}'
        phones = re.findall(phone_pattern, html_content)
        return list(set(phones))

class DataCollector:
    """Main data collection service"""
    
    def __init__(self):
        self.scraper = WebScraper()
    
    def collect_from_url(self, url):
        """Collect data from a single URL"""
        try:
            html = self.scraper.fetch_url(url)
            if not html:
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            
            data = {
                'url': url,
                'emails': self.scraper.extract_emails(html),
                'phones': self.scraper.extract_phones(html),
                'title': soup.title.string if soup.title else '',
                'text': soup.get_text()[:500]
            }
            
            return data
        except Exception as e:
            logger.error(f"Error collecting from {url}: {str(e)}")
            return None

class AIClassifier:
    """AI-based lead classification service using keyword-NLP analysis"""

    CATEGORY_KEYWORDS = {
        'technology': [
            'software', 'hardware', 'tech', 'app', 'platform', 'saas', 'cloud',
            'api', 'devops', 'ai', 'machine learning', 'data', 'database',
            'programming', 'developer', 'code', 'system', 'network', 'security',
            'cyber', 'automation', 'integration', 'analytics', 'infrastructure',
        ],
        'marketing': [
            'marketing', 'advertising', 'seo', 'content', 'social media', 'brand',
            'campaign', 'lead generation', 'digital marketing', 'analytics',
            'crm', 'email marketing', 'growth', 'funnel', 'conversion',
        ],
        'sales': [
            'sales', 'revenue', 'pipeline', 'crm', 'outreach', 'closing',
            'prospects', 'b2b', 'cold calling', 'quota', 'deal', 'account',
            'business development', 'partnership',
        ],
        'finance': [
            'finance', 'accounting', 'investment', 'banking', 'fintech', 'payment',
            'revenue', 'budget', 'roi', 'valuation', 'fundraising', 'capital',
            'trading', 'portfolio', 'insurance',
        ],
        'healthcare': [
            'health', 'medical', 'pharma', 'clinical', 'patient', 'hospital',
            'healthcare', 'biotech', 'wellness', 'telemedicine', 'diagnostics',
            'therapeutics', 'life sciences',
        ],
        'ecommerce': [
            'ecommerce', 'e-commerce', 'retail', 'online store', 'shopify',
            'woocommerce', 'product', 'inventory', 'fulfillment', 'marketplace',
            'wholesale', 'dropshipping', 'logistics',
        ],
        'education': [
            'education', 'learning', 'training', 'edtech', 'course', 'university',
            'school', 'students', 'e-learning', 'curriculum', 'certification',
            'coaching', 'tutoring',
        ],
        'consulting': [
            'consulting', 'advisory', 'strategy', 'management', 'operations',
            'transformation', 'outsourcing', 'process improvement', 'change management',
        ],
        'real_estate': [
            'real estate', 'property', 'realty', 'mortgage', 'construction',
            'architecture', 'commercial property', 'residential', 'leasing',
        ],
        'manufacturing': [
            'manufacturing', 'production', 'factory', 'supply chain', 'industrial',
            'engineering', 'quality control', 'procurement', 'assembly',
        ],
    }

    def __init__(self, confidence_threshold: float = 0.3):
        self.confidence_threshold = confidence_threshold

    def classify_interest(self, text: str, categories: list = None) -> dict:  # type: ignore[assignment]
        """
        Classify lead interests/text into a category using keyword matching.
        Returns the best matching category, confidence (0-1), and matched keywords.
        """
        if not text:
            return {'category': 'unknown', 'confidence': 0.0, 'keywords': []}

        text_lower = text.lower()
        target_cats = categories if categories else list(self.CATEGORY_KEYWORDS.keys())

        best_category = 'unknown'
        best_count = 0
        best_keywords: list = []

        for category in target_cats:
            kw_list = self.CATEGORY_KEYWORDS.get(category, [])
            if not kw_list:
                continue
            found = [kw for kw in kw_list if kw in text_lower]
            if len(found) > best_count:
                best_count = len(found)
                best_category = category
                best_keywords = found

        # Confidence: scale match density (0→0, 1 match→~0.4, 3+→capped at 1.0)
        if best_count == 0:
            confidence = 0.0
            best_category = 'unknown'
        else:
            confidence = min(best_count / 3.0, 1.0)

        if confidence < self.confidence_threshold:
            best_category = 'unknown'

        return {
            'category': best_category,
            'confidence': round(confidence, 2),
            'keywords': best_keywords[:5],
        }

    def calculate_lead_score(self, lead_data: dict) -> int:
        """Calculate a data-completeness + seniority qualification score (0-100)"""
        score = 0

        # Email (25 pts base, +10 bonus for corporate domain)
        email = lead_data.get('email', '')
        if email:
            score += 25
            domain = email.split('@')[-1].lower() if '@' in email else ''
            generic = ('gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
                       'icloud.com', 'live.com', 'aol.com')
            if domain and domain not in generic:
                score += 10  # corporate email bonus

        # Phone (20 pts)
        if lead_data.get('phone'):
            score += 20

        # Company (15 pts)
        if lead_data.get('company'):
            score += 15

        # Position (up to 15 pts based on seniority)
        position = str(lead_data.get('position', '')).lower()
        if position:
            if any(t in position for t in ['ceo', 'cto', 'cfo', 'coo', 'founder', 'president', 'chief']):
                score += 15
            elif any(t in position for t in ['vp', 'vice president', 'director', 'head of']):
                score += 12
            elif any(t in position for t in ['manager', 'lead', 'senior', 'principal']):
                score += 8
            else:
                score += 4

        # Interests (5 pts)
        if lead_data.get('interests'):
            score += 5

        # LinkedIn (5 pts)
        if lead_data.get('linkedin_url'):
            score += 5

        # Website (5 pts)
        if lead_data.get('website'):
            score += 5

        return min(score, 100)
