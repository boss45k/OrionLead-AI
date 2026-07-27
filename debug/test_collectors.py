"""Quick test for web and social collectors."""
import sys
sys.path.insert(0, 'backend')

print("=" * 60)
print("TEST 1: Web Collector")
print("=" * 60)
from app.services.public_web_collector import PublicWebCollector
c = PublicWebCollector(rate_limit=1.0, timeout=10)
leads = c.collect_by_country('technology companies', 'US', city='New York', max_leads=3)
print(f"Web collector returned: {len(leads)} leads")
for l in leads:
    company = l.get('company', '?')
    email = l.get('email', '?')
    industry = l.get('industry', '?')
    score = l.get('qualification_score', 0)
    has_structured = bool(l.get('data_points', {}).get('structured_data'))
    print(f"  [{score:.0f}] {company} | {email} | {industry} | structured_data={has_structured}")

print()
print("=" * 60)
print("TEST 2: Social Media Collector (Reddit)")
print("=" * 60)
from app.services.social_media_collector import SocialMediaCollector
s = SocialMediaCollector(rate_limit=1.5, timeout=10)
social_leads = s.collect_from_social('SaaS startup', platforms=['reddit'], industry='startups', max_per_platform=3)
print(f"Social collector returned: {len(social_leads)} leads")
for l in social_leads:
    name = l.get('name', '?')
    company = l.get('company', '?')
    email = l.get('email', '?')
    source = l.get('source', '?')
    score = l.get('qualification_score', 0)
    print(f"  [{score:.0f}] {name} | {company} | {email} | {source}")

print()
print("=" * 60)
print("TEST 3: Social Media Collector (LinkedIn)")
print("=" * 60)
li_leads = s.collect_from_social('artificial intelligence', platforms=['linkedin'], industry='ai', max_per_platform=3)
print(f"LinkedIn collector returned: {len(li_leads)} leads")
for l in li_leads:
    name = l.get('name', '?')
    company = l.get('company', '?')
    position = l.get('position', '?')
    source = l.get('source', '?')
    score = l.get('qualification_score', 0)
    print(f"  [{score:.0f}] {name} | {company} | {position} | {source}")

print()
print("ALL TESTS COMPLETE")
