"""
Smart Filtering Engine - Evaluates and filters leads against client requirements
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class SmartFilterEngine:
    """Intelligent lead filtering based on client requirements"""
    
    def __init__(self, config_path: str = 'CLIENT_REQUIREMENTS.json'):
        """Initialize with client requirements"""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.stats = {
            'total_leads': 0,
            'filtered_leads': 0,
            'failed_filters': [],
            'duplicates_removed': 0
        }
    
    def filter_leads(self, leads: List[Dict]) -> Dict[str, Any]:
        """
        Process and filter leads against all criteria
        
        Returns:
            {
                'hot': [...],      # 70%+ qualification
                'warm': [...],     # 40-70% qualification
                'cold': [...],     # <40% qualification
                'rejected': [...], # Did not meet requirements
                'stats': {...}
            }
        """
        self.stats['total_leads'] = len(leads)
        
        # Step 1: Deduplication
        leads = self._deduplicate(leads)
        self.stats['duplicates_removed'] = self.stats['total_leads'] - len(leads)
        
        # Step 2: Apply filters
        accepted_leads = []
        rejected_leads = []
        
        for lead in leads:
            result = self._evaluate_lead(lead)
            if result['accepted']:
                accepted_leads.append(result['lead'])
            else:
                result['lead']['rejection_reason'] = result['reason']
                rejected_leads.append(result['lead'])
        
        self.stats['filtered_leads'] = len(accepted_leads)
        
        # Step 3: Categorize by qualification score
        hot = [l for l in accepted_leads if l.get('qualification_score', 0) >= 70]
        warm = [l for l in accepted_leads if 40 <= l.get('qualification_score', 0) < 70]
        cold = [l for l in accepted_leads if l.get('qualification_score', 0) < 40]
        
        logger.info(f"✅ Filtering complete: {len(hot)} hot, {len(warm)} warm, {len(cold)} cold")
        
        return {
            'hot': sorted(hot, key=lambda x: x.get('qualification_score', 0), reverse=True),
            'warm': sorted(warm, key=lambda x: x.get('qualification_score', 0), reverse=True),
            'cold': cold,
            'rejected': rejected_leads,
            'stats': {
                'total_processed': self.stats['total_leads'],
                'duplicates_removed': self.stats['duplicates_removed'],
                'accepted': len(accepted_leads),
                'rejected': len(rejected_leads),
                'hot_count': len(hot),
                'warm_count': len(warm),
                'cold_count': len(cold)
            }
        }
    
    def _evaluate_lead(self, lead: Dict) -> Dict[str, Any]:
        """
        Comprehensive lead evaluation
        
        Returns:
            {
                'accepted': bool,
                'reason': str (if rejected),
                'lead': Dict (with updated scores/status)
            }
        """
        lead_copy = lead.copy()
        score = 0
        reasons = []
        
        # 1. Check job title
        if lead.get('position'):
            title_score, title_reason = self._check_job_title(lead['position'])
            score += title_score
            if title_reason:
                reasons.append(title_reason)
        
        # 2. Check company size
        if lead.get('company_size'):
            size_score, size_reason = self._check_company_size(lead['company_size'])
            score += size_score
            if size_reason:
                reasons.append(size_reason)
        
        # 3. Check industry
        if lead.get('industry'):
            ind_score, ind_reason = self._check_industry(lead['industry'])
            score += ind_score
            if ind_reason:
                reasons.append(ind_reason)
        
        # 4. Check interests against requirements
        if lead.get('interests'):
            int_score, int_reason = self._check_interests(lead['interests'])
            score += int_score
            if int_reason:
                reasons.append(int_reason)
        
        # 5. Check geographic location
        if lead.get('location'):
            geo_score, geo_reason = self._check_geography(lead['location'])
            score += geo_score
            if geo_reason:
                reasons.append(geo_reason)
        
        # 6. Check experience level
        if lead.get('years_experience'):
            exp_score, exp_reason = self._check_experience(lead['years_experience'])
            score += exp_score
            if exp_reason:
                reasons.append(exp_reason)
        
        # Normalize score to 0-100
        lead_copy['calculated_score'] = min(100, max(0, score))
        
        # Combine with existing qualification score
        existing_score = lead_copy.get('qualification_score', 0)
        final_score = (lead_copy['calculated_score'] + existing_score) / 2
        lead_copy['qualification_score'] = final_score
        
        # Set status
        if final_score >= 70:
            lead_copy['status'] = 'hot'
        elif final_score >= 40:
            lead_copy['status'] = 'warm'
        else:
            lead_copy['status'] = 'cold'
        
        # Decide acceptance
        min_score = self.config['qualification_settings']['min_qualification_score']
        
        if final_score >= min_score:
            return {'accepted': True, 'lead': lead_copy}
        else:
            return {
                'accepted': False,
                'reason': f"Score {final_score:.0f}% below minimum {min_score}%",
                'lead': lead_copy
            }
    
    def _check_job_title(self, title: str) -> tuple:
        """Check if job title matches target positions"""
        target_titles = self.config['data_requirements']['target_job_titles']
        
        title_lower = title.lower()
        for target in target_titles:
            if target.lower() in title_lower:
                return (20, f"✓ Title match: {target}")
        
        # Partial match for seniority
        if any(word in title_lower for word in ['senior', 'lead', 'manager', 'director', 'head']):
            return (10, f"◐ Senior role: {title}")
        
        return (0, f"✗ Title not target: {title}")
    
    def _check_company_size(self, size: int) -> tuple:
        """Check company size against requirements"""
        min_size = self.config['data_requirements']['target_company_size']['min_employees']
        max_size = self.config['data_requirements']['target_company_size']['max_employees']
        
        if min_size <= size <= max_size:
            return (15, f"✓ Company size {size} in range")
        elif size < min_size:
            return (0, f"✗ Too small: {size}")
        else:
            return (5, f"◐ Larger than ideal: {size}")
    
    def _check_industry(self, industry: str) -> tuple:
        """Check industry match"""
        target_industries = self.config['data_requirements']['target_industries']
        
        industry_lower = industry.lower()
        for target in target_industries:
            if target.lower() in industry_lower or industry_lower in target.lower():
                return (20, f"✓ Industry match: {target}")
        
        return (0, f"✗ Industry not target: {industry}")
    
    def _check_interests(self, interests: List[str]) -> tuple:
        """Smart interest matching"""
        if isinstance(interests, str):
            interests = [interests]
        
        interests_lower = [i.lower() for i in interests]
        
        # Must-have interests
        must_have = [i.lower() for i in self.config['interest_filters']['must_have_interests']]
        should_have = [i.lower() for i in self.config['interest_filters']['should_have_interests']]
        exclude = [i.lower() for i in self.config['interest_filters']['exclude_interests']]
        
        # Check exclusions
        for excl in exclude:
            if any(excl in interest for interest in interests_lower):
                return (0, f"✗ Excluded interest found: {excl}")
        
        score = 0
        matched = []
        
        # Check must-have
        for must in must_have:
            if any(must in interest for interest in interests_lower):
                score += 10
                matched.append(must)
        
        # Check should-have
        for should in should_have:
            if any(should in interest for interest in interests_lower):
                score += 5
                matched.append(should)
        
        reason = f"✓ Interests: {', '.join(matched)}" if matched else "◐ Some interests"
        return (score, reason)
    
    def _check_geography(self, location: str) -> tuple:
        """Check geographic location"""
        target_regions = self.config['data_requirements']['geographic_regions']
        
        location_lower = location.lower()
        for region in target_regions:
            if region.lower() in location_lower or location_lower in region.lower():
                return (10, f"✓ Location: {region}")
        
        return (0, f"✗ Location not target: {location}")
    
    def _check_experience(self, years: int) -> tuple:
        """Check experience level"""
        min_years = self.config['data_requirements']['experience_level']['min_years']
        prefer_senior = self.config['data_requirements']['experience_level']['prefer_senior']
        
        if years >= min_years:
            if prefer_senior and years >= 10:
                return (15, f"✓ Senior: {years}+ years")
            else:
                return (10, f"✓ Experience: {years} years")
        else:
            return (0, f"✗ Too junior: {years} years")
    
    def _deduplicate(self, leads: List[Dict]) -> List[Dict]:
        """Remove duplicate leads"""
        if not self.config['deduplication']['enabled']:
            return leads
        
        seen = {}
        unique_leads = []
        
        for lead in leads:
            # Create fingerprint from key fields
            fingerprint = self._create_fingerprint(lead)
            
            if fingerprint not in seen:
                seen[fingerprint] = lead
                unique_leads.append(lead)
            else:
                # Keep the one with higher score
                existing = seen[fingerprint]
                if lead.get('qualification_score', 0) > existing.get('qualification_score', 0):
                    unique_leads.remove(existing)
                    unique_leads.append(lead)
                    seen[fingerprint] = lead
        
        return unique_leads
    
    def _create_fingerprint(self, lead: Dict) -> str:
        """Create unique fingerprint for deduplication"""
        email = lead.get('email', '').lower().strip()
        name = lead.get('name', '').lower().strip()
        company = lead.get('company', '').lower().strip()
        
        return f"{email}|{name}|{company}"


# Export for use
__all__ = ['SmartFilterEngine']
