"""
Intelligent Lead Agent Orchestrator
Integrates public data collection with the existing master orchestrator
Supports country-based web collection from public sources
"""

import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from intelligent_lead_agent import IntelligentLeadAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _get_reddit_collector():
    """Safely import Reddit collector with fallback"""
    try:
        from reddit_collector import get_reddit_collector, RedditCollector, MockRedditCollector
        return get_reddit_collector(), True
    except ImportError:
        logger.warning("Reddit collector not available, using mock data")
        return None, False


class IntelligentLeadOrchestrator:
    """Orchestrates intelligent lead collection from public sources"""
    
    def __init__(self):
        """Initialize orchestrator"""
        self.agent = IntelligentLeadAgent()
        self.reddit_collector, self._reddit_available = _get_reddit_collector()
        self.results = {}
    
    def collect_from_reddit(self, use_mock: bool = False) -> List[Dict[str, Any]]:
        """Collect leads from Reddit"""
        print("\n📌 SOURCE: Public Forums (Reddit)")
        print("-" * 70)
        
        if use_mock or not self._reddit_available or not self._is_reddit_enabled():
            logger.info("ℹ️  Using mock data for testing")
            try:
                from reddit_collector import MockRedditCollector
                content_list = MockRedditCollector.get_sample_data()
            except ImportError:
                content_list = []
                logger.warning("Reddit collector module not found, skipping")
        else:
            content_list = []
            
            # Collect from subreddits
            assert self.reddit_collector is not None  # guarded by _reddit_available check above
            for category, subreddits in self.reddit_collector.SUBREDDIT_MAP.items():
                for subreddit in subreddits[:2]:  # Limit to 2 per category
                    data = self.reddit_collector.collect_from_subreddit(subreddit, limit=10)
                    content_list.extend(data)
        
        print(f"✅ Collected {len(content_list)} public comments")
        return content_list

    def collect_from_web(self, query: str, country_codes: List[str],
                         city: Optional[str] = None,
                         max_per_country: int = 10) -> List[Dict[str, Any]]:
        """
        Collect leads from public web sources by country.
        
        Args:
            query: Search query (e.g. "software companies", "marketing agencies")
            country_codes: List of ISO country codes (e.g. ["US", "UK", "AE"])
            city: Optional city filter
            max_per_country: Max leads per country
        
        Returns:
            List of lead dictionaries
        """
        print(f"\n📌 SOURCE: Public Web ({', '.join(country_codes)})")
        print("-" * 70)
        
        try:
            from app.services.public_web_collector import get_collector
            
            collector = get_collector()
            all_leads = []
            
            for code in country_codes:
                leads = collector.collect_by_country(
                    query=query,
                    country_code=code,
                    city=city if len(country_codes) == 1 else None,
                    max_leads=max_per_country,
                )
                all_leads.extend(leads)
                print(f"  🌍 {code}: {len(leads)} leads collected")
            
            print(f"✅ Total web leads: {len(all_leads)}")
            return all_leads
            
        except ImportError:
            logger.error("Public web collector not available")
            return []
        except Exception as e:
            logger.error(f"Web collection error: {e}")
            return []
    
    def _is_reddit_enabled(self) -> bool:
        """Check if Reddit collector is enabled (has real credentials)"""
        if not self.reddit_collector:
            return False
        if hasattr(self.reddit_collector, 'enabled'):
            return self.reddit_collector.enabled
        return False
    
    def analyze_leads(self, content_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze collected content with intelligent agent"""
        print("\n📌 INTELLIGENT ANALYSIS")
        print("-" * 70)
        
        logger.info(f"🧠 Processing {len(content_list)} items with AI agent...")
        
        # Process with agent
        leads = self.agent.process_content(content_list)
        
        logger.info(f"✅ Processed {len(leads)} leads")
        
        # Display statistics
        premium_count = sum(1 for l in leads if l.get('scoring', {}).get('classification') == 'premium')
        quality_count = sum(1 for l in leads if l.get('scoring', {}).get('classification') == 'quality')
        
        print(f"\n📊 Analysis Results:")
        print(f"   Premium Leads (>0.80): {premium_count}")
        print(f"   Quality Leads (0.60-0.80): {quality_count}")
        print(f"   Potential Leads: {len(leads) - premium_count - quality_count}")
        
        return leads
    
    def format_for_database(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format leads for database storage"""
        print("\n📌 FORMATTING FOR DATABASE")
        print("-" * 70)
        
        formatted_leads = self.agent.format_for_database(leads)
        
        print(f"✅ Formatted {len(formatted_leads)} leads")
        
        return formatted_leads
    
    def save_to_database(self, leads: List[Dict[str, Any]]) -> int:
        """Save leads to database"""
        print("\n📌 SAVING TO DATABASE")
        print("-" * 70)
        
        try:
            from app import create_app
            from app.models.models import db, Lead
            
            app = create_app()
            saved_count = 0
            
            with app.app_context():  # type: ignore[union-attr]
                for lead_data in leads:
                    # Check if already exists
                    existing = Lead.query.filter(
                        Lead.name == lead_data.get('name')
                    ).first()
                    
                    if existing:
                        logger.debug(f"Skipping duplicate: {lead_data['name']}")
                        continue
                    
                    # Create new lead
                    lead = Lead(
                        name=lead_data['name'][:255],
                        email=lead_data.get('email'),
                        company=lead_data['company'][:255],
                        position=lead_data.get('position', 'Interested Contact'),
                        location=lead_data.get('location'),
                        country=lead_data.get('country'),
                        city=lead_data.get('city'),
                        industry=lead_data.get('industry'),
                        website=lead_data.get('website'),
                        linkedin_url=lead_data.get('linkedin_url'),
                        interests=lead_data.get('interests', []),
                        source=lead_data['source'],
                        status=lead_data.get('status', 'pending'),
                        qualification_score=lead_data['qualification_score'],
                        data_points=lead_data.get('data_points', {})
                    )
                    
                    db.session.add(lead)
                    saved_count += 1
                
                if saved_count > 0:
                    db.session.commit()
                    print(f"✅ Saved {saved_count} new leads to database")
                else:
                    print("ℹ️  No new leads to save")
            
            return saved_count
        
        except Exception as e:
            logger.error(f"❌ Failed to save to database: {e}")
            return 0
    
    def generate_report(self, leads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate collection report"""
        print("\n" + "="*70)
        print("📊 INTELLIGENT AGENT COLLECTION REPORT")
        print("="*70)
        
        # Stats
        total = len(leads)
        premium = sum(1 for l in leads if l.get('scoring', {}).get('classification') == 'premium')
        quality = sum(1 for l in leads if l.get('scoring', {}).get('classification') == 'quality')
        potential = sum(1 for l in leads if l.get('scoring', {}).get('classification') == 'potential')
        low = sum(1 for l in leads if l.get('scoring', {}).get('classification') == 'low')
        
        # Categories
        categories = {}
        for lead in leads:
            cat = lead.get('interest', {}).get('category', 'unknown')
            categories[cat] = categories.get(cat, 0) + 1
        
        # Intent distribution
        intents = {}
        for lead in leads:
            intent = lead.get('intent', {}).get('level', 'low')
            intents[intent] = intents.get(intent, 0) + 1
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_leads': total,
            'classification': {
                'premium': premium,
                'quality': quality,
                'potential': potential,
                'low': low
            },
            'by_category': categories,
            'by_intent': intents,
            'avg_score': sum(l.get('scoring', {}).get('final_score', 0) for l in leads) / total if total > 0 else 0
        }
        
        # Display
        print(f"\n📈 COLLECTION STATISTICS")
        print(f"{'─' * 70}")
        print(f"Total Leads Analyzed:        {total}")
        print(f"Premium (>0.80):             {premium} ({premium/total*100:.1f}%)")
        print(f"Quality (0.60-0.80):         {quality} ({quality/total*100:.1f}%)")
        print(f"Potential (0.40-0.60):       {potential} ({potential/total*100:.1f}%)")
        print(f"Low (<0.40):                 {low} ({low/total*100:.1f}%)")
        print(f"Average Score:               {report['avg_score']:.2%}")
        
        print(f"\n🎯 BY PRODUCT CATEGORY")
        print(f"{'─' * 70}")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            print(f"  {cat:20s}: {count:3d} leads")
        
        print(f"\n💭 BY PURCHASE INTENT")
        print(f"{'─' * 70}")
        for intent, count in sorted(intents.items(), key=lambda x: x[1], reverse=True):
            print(f"  {intent:20s}: {count:3d} leads")
        
        print(f"\n{'═' * 70}\n")
        
        return report
    
    def run_complete_pipeline(self, use_mock: bool = False,
                             web_query: str = '',
                             web_countries: Optional[List[str]] = None,
                             web_city: Optional[str] = None,
                             max_per_country: int = 10) -> Dict[str, Any]:
        """Run complete intelligent lead collection pipeline
        
        Args:
            use_mock: Use mock data for Reddit
            web_query: Search query for public web collection (optional)
            web_countries: List of country codes for web collection (optional)
            web_city: City filter for web collection (optional)
            max_per_country: Max leads per country for web collection
        """
        print("\n" + "="*70)
        print("🚀 INTELLIGENT LEAD AGENT ORCHESTRATOR")
        print("="*70)
        print(f"\n🧠 Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # 1. Collect from public forums (Reddit)
            content_list = self.collect_from_reddit(use_mock=use_mock)
            
            # 2. Collect from public web sources (country-based)
            web_leads = []
            if web_query and web_countries:
                web_leads = self.collect_from_web(
                    query=web_query,
                    country_codes=web_countries,
                    city=web_city,
                    max_per_country=max_per_country,
                )
            
            # 3. Analyze forum content with intelligent agent
            analyzed_leads = self.analyze_leads(content_list)
            
            # 4. Format forum leads for database
            formatted_leads = self.format_for_database(analyzed_leads)
            
            # 5. Combine with web leads (web leads already formatted)
            all_leads_for_db = formatted_leads + web_leads
            
            # 6. Save to database
            saved_count = self.save_to_database(all_leads_for_db)
            
            # 7. Generate report (for forum analyzed leads)
            report = self.generate_report(analyzed_leads)
            
            # Add web stats to report
            report['web_collection'] = {
                'query': web_query,
                'countries': web_countries or [],
                'leads_collected': len(web_leads),
            }
            
            total_saved = saved_count
            print(f"✅ Pipeline complete: {total_saved} leads saved "
                  f"({len(formatted_leads)} from forums, {len(web_leads)} from web)")
            
            return {
                'status': 'success',
                'collected': len(content_list) + len(web_leads),
                'analyzed': len(analyzed_leads),
                'web_collected': len(web_leads),
                'saved': total_saved,
                'report': report
            }
        
        except Exception as e:
            logger.error(f"❌ Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'status': 'failed',
                'error': str(e)
            }

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Intelligent Lead Agent Orchestrator')
    parser.add_argument('--mock', action='store_true', help='Use mock data for testing')
    parser.add_argument('--query', type=str, default='', help='Web search query (e.g. "technology companies")')
    parser.add_argument('--countries', type=str, nargs='*', default=[], help='Country codes (e.g. US UK AE)')
    parser.add_argument('--city', type=str, default='', help='City filter')
    parser.add_argument('--max-per-country', type=int, default=10, help='Max leads per country')
    args = parser.parse_args()
    
    orchestrator = IntelligentLeadOrchestrator()
    result = orchestrator.run_complete_pipeline(
        use_mock=args.mock,
        web_query=args.query,
        web_countries=args.countries if args.countries else None,
        web_city=args.city or None,
        max_per_country=args.max_per_country,
    )
    
    return 0 if result['status'] == 'success' else 1

if __name__ == '__main__':
    exit(main())
