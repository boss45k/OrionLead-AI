"""
Master Data Collection Orchestrator
Coordinates all data sources, applies smart filtering, and saves to database
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import os

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from smart_filter_engine import SmartFilterEngine
from scrape_github_developers import fetch_github_developers
from scrape_hunter import HunterCollector
from scrape_apollo import ApolloCollector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataCollectionOrchestrator:
    """Master orchestrator for intelligent data collection"""
    
    def __init__(self, config_path: str = 'CLIENT_REQUIREMENTS.json'):
        """Initialize orchestrator"""
        self.config = self._load_config(config_path)
        self.filter_engine = SmartFilterEngine(config_path)
        self.collected_leads = []
        self.results = {}
    
    def _load_config(self, config_path: str) -> Dict:
        """Load client configuration"""
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def collect_from_all_sources(self) -> Dict[str, List[Dict]]:
        """
        Collect leads from all enabled data sources
        
        Returns:
            {
                'github': [...],
                'hunter': [...],
                'apollo': [...],
                'total': int
            }
        """
        print("\n" + "="*70)
        print("🚀 MASTER DATA COLLECTION ORCHESTRATOR")
        print("="*70)
        print(f"\n📋 Client: {self.config['client']['name']}")
        print(f"🎯 Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        sources_data = {}
        
        # 1. GitHub
        if self.config['data_sources']['github']['enabled']:
            sources_data['github'] = self._collect_github()
        
        # 2. Hunter.io
        if self.config['data_sources']['hunter']['enabled']:
            sources_data['hunter'] = self._collect_hunter()
        
        # 3. Apollo.io
        if self.config['data_sources']['apollo']['enabled']:
            sources_data['apollo'] = self._collect_apollo()
        
        # 4. RocketReach (not implemented, placeholder)
        if self.config['data_sources']['rocketreach']['enabled']:
            logger.info("⚠️ RocketReach: Not implemented yet")
        
        # 5. Crunchbase (not implemented, placeholder)
        if self.config['data_sources']['crunchbase']['enabled']:
            logger.info("⚠️ Crunchbase: Not implemented yet")
        
        # Combine all leads
        all_leads = []
        for source, leads in sources_data.items():
            all_leads.extend(leads)
        
        sources_data['total'] = len(all_leads)
        self.collected_leads = all_leads
        
        return sources_data
    
    def _collect_github(self) -> List[Dict]:
        """Collect from GitHub"""
        print("\n📌 SOURCE 1: GitHub Developers")
        print("-" * 70)
        
        github_config = self.config['data_sources']['github']
        
        try:
            leads = fetch_github_developers(
                searches=github_config['searches'],
                limit=github_config['limit']
            )
            print(f"✅ GitHub: Collected {len(leads)} developers\n")
            return leads
        except Exception as e:
            logger.error(f"✗ GitHub collection failed: {str(e)}")
            return []
    
    def _collect_hunter(self) -> List[Dict]:
        """Collect from Hunter.io"""
        print("\n📌 SOURCE 2: Hunter.io")
        print("-" * 70)
        
        hunter_config = self.config['data_sources']['hunter']
        hunter = HunterCollector(hunter_config['api_key'])
        
        if not hunter.enabled:
            print("⚠️ Hunter.io not configured")
            print("   Setup: https://hunter.io/")
            return []
        
        try:
            leads = hunter.search_by_criteria(
                job_titles=self.config['data_requirements']['target_job_titles'],
                company_domains=hunter_config['companies']
            )
            print(f"✅ Hunter: Collected {len(leads)} contacts\n")
            return leads
        except Exception as e:
            logger.error(f"✗ Hunter collection failed: {str(e)}")
            return []
    
    def _collect_apollo(self) -> List[Dict]:
        """Collect from Apollo.io"""
        print("\n📌 SOURCE 3: Apollo.io")
        print("-" * 70)
        
        apollo_config = self.config['data_sources']['apollo']
        apollo = ApolloCollector(apollo_config['api_key'])
        
        if not apollo.enabled:
            print("⚠️ Apollo.io not configured")
            print("   Setup: https://apollo.io/")
            return []
        
        try:
            leads = apollo.search_people(
                job_titles=['VP of Engineering', 'CTO'],
                limit=apollo_config['limit']
            )
            print(f"✅ Apollo: Collected {len(leads)} people\n")
            return leads
        except Exception as e:
            logger.error(f"✗ Apollo collection failed: {str(e)}")
            return []
    
    def apply_smart_filtering(self) -> Dict[str, Any]:
        """Apply smart filtering engine to all collected leads"""
        print("\n" + "="*70)
        print("🔥 APPLYING SMART FILTERING")
        print("="*70 + "\n")
        
        if not self.collected_leads:
            logger.warning("No leads collected!")
            return {}
        
        filtered = self.filter_engine.filter_leads(self.collected_leads)
        self.results = filtered
        
        # Display results
        print(f"📊 FILTERING RESULTS:")
        print(f"  Total Processed: {filtered['stats']['total_processed']}")
        print(f"  Duplicates Removed: {filtered['stats']['duplicates_removed']}")
        print(f"  Accepted: {filtered['stats']['accepted']}")
        print(f"  Rejected: {filtered['stats']['rejected']}")
        print()
        print(f"  🔴 Hot (70%+ qualified): {filtered['stats']['hot_count']}")
        print(f"  🟡 Warm (40-70%): {filtered['stats']['warm_count']}")
        print(f"  🔵 Cold (<40%): {filtered['stats']['cold_count']}\n")
        
        return filtered
    
    def save_to_database(self) -> int:
        """Save filtered leads to database"""
        print("\n" + "="*70)
        print("💾 SAVING TO DATABASE")
        print("="*70 + "\n")
        
        from app import create_app
        from app.models.models import db, Lead
        
        os.environ['FLASK_ENV'] = 'production'
        app = create_app()
        
        saved_count = 0
        
        with app.app_context():
            # Combine all results
            all_results = (
                self.results.get('hot', []) +
                self.results.get('warm', []) +
                self.results.get('cold', [])
            )
            
            for lead_data in all_results:
                try:
                    # Check for duplicates
                    existing = Lead.query.filter_by(email=lead_data.get('email')).first()
                    
                    if existing:
                        # Update existing
                        if lead_data.get('qualification_score', 0) > existing.qualification_score:
                            existing.qualification_score = lead_data['qualification_score']
                            existing.status = lead_data.get('status', 'pending')
                            db.session.merge(existing)
                            saved_count += 1
                    else:
                        # Create new
                        new_lead = Lead(
                            name=lead_data.get('name', 'Unknown'),
                            email=lead_data.get('email'),
                            company=lead_data.get('company'),
                            position=lead_data.get('position'),
                            interests=lead_data.get('interests', []),
                            qualification_score=lead_data.get('qualification_score', 0),
                            status=lead_data.get('status', 'pending'),
                            source=lead_data.get('source', 'orchestrator'),
                            data_points=lead_data.get('data_points', {})
                        )
                        db.session.add(new_lead)
                        saved_count += 1
                
                except Exception as e:
                    logger.error(f"✗ Failed to save lead {lead_data.get('name')}: {str(e)}")
            
            try:
                db.session.commit()
                logger.info(f"✅ Saved {saved_count} leads to database")
            except Exception as e:
                logger.error(f"✗ Database commit failed: {str(e)}")
                db.session.rollback()
        
        return saved_count
    
    def export_to_csv(self, output_path: str = 'exports/leads_export.csv') -> str:
        """Export results to CSV"""
        import csv
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        all_results = (
            self.results.get('hot', []) +
            self.results.get('warm', []) +
            self.results.get('cold', [])
        )
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'name', 'email', 'company', 'position', 'interests',
                'qualification_score', 'status', 'source', 'location'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for lead in all_results:
                writer.writerow({
                    'name': lead.get('name', ''),
                    'email': lead.get('email', ''),
                    'company': lead.get('company', ''),
                    'position': lead.get('position', ''),
                    'interests': '|'.join(lead.get('interests', [])) if lead.get('interests') else '',
                    'qualification_score': f"{lead.get('qualification_score', 0):.0f}",
                    'status': lead.get('status', ''),
                    'source': lead.get('source', ''),
                    'location': lead.get('location', '')
                })
        
        logger.info(f"✅ Exported to: {output_path}")
        return output_path
    
    def generate_report(self) -> str:
        """Generate professional collection report"""
        report = f"""
╔══════════════════════════════════════════════════════════════════════╗
║                  DATA COLLECTION REPORT                             ║
║              Professional Lead Collection System                    ║
╚══════════════════════════════════════════════════════════════════════╝

📋 CLIENT INFORMATION
────────────────────
Name:                {self.config['client']['name']}
Email:               {self.config['client']['email']}
Industry:            {self.config['client']['industry']}
Report Generated:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🎯 COLLECTION TARGETS
─────────────────────
Job Titles:          {', '.join(self.config['data_requirements']['target_job_titles'][:3])}...
Company Size:        {self.config['data_requirements']['target_company_size']['min_employees']}-{self.config['data_requirements']['target_company_size']['max_employees']} employees
Industries:          {', '.join(self.config['data_requirements']['target_industries'][:3])}...
Key Interests:       {', '.join(self.config['interest_filters']['must_have_interests'][:3])}...

📊 COLLECTION RESULTS
──────────────────────
Total Leads Collected:     {len(self.collected_leads)}
Duplicates Removed:        {self.results.get('stats', {}).get('duplicates_removed', 0)}
Leads After Filtering:     {self.results.get('stats', {}).get('accepted', 0)}
Leads Rejected:            {self.results.get('stats', {}).get('rejected', 0)}

🔴 HOT LEADS (70%+ qualified):
   Count: {self.results.get('stats', {}).get('hot_count', 0)}
   Status: Ready for immediate outreach
   
🟡 WARM LEADS (40-70% qualified):
   Count: {self.results.get('stats', {}).get('warm_count', 0)}
   Status: Good potential, nurture needed
   
🔵 COLD LEADS (<40% qualified):
   Count: {self.results.get('stats', {}).get('cold_count', 0)}
   Status: Research needed

💡 NEXT STEPS
─────────────
1. Review hot leads in database
2. Filter warm leads by specific interests
3. Plan outreach campaign
4. Set up email sequences
5. Track engagement metrics

═══════════════════════════════════════════════════════════════════════
"""
        print(report)
        return report


def main():
    """Main execution"""
    try:
        # Initialize orchestrator
        orchestrator = DataCollectionOrchestrator('CLIENT_REQUIREMENTS.json')
        
        # Step 1: Collect from all sources
        orchestrator.collect_from_all_sources()
        
        # Step 2: Apply smart filtering
        orchestrator.apply_smart_filtering()
        
        # Step 3: Save to database
        saved = orchestrator.save_to_database()
        
        # Step 4: Export to CSV
        orchestrator.export_to_csv()
        
        # Step 5: Generate report
        orchestrator.generate_report()
        
        print("✅ Data collection pipeline complete!")
        
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
