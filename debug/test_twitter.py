"""Quick test for Twitter + Facebook collectors."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.social_media_collector import SocialMediaCollector

c = SocialMediaCollector()

print("=" * 60)
print(" TWITTER: SaaS startup founder (industry=startups)")
print("=" * 60)
leads = c._collect_from_twitter('SaaS startup founder', 'startups', 5)
print(f"Collected {len(leads)} leads\n")
for i, l in enumerate(leads):
    ev = l.get('data_points', {}).get('email_verified', False)
    email = l.get('email', '')
    if ev:
        tag = 'VERIFIED'
    elif email and 'info@' in email:
        tag = 'INFERRED'
    elif email:
        tag = 'FOUND'
    else:
        tag = 'MISSING'
    print(f"  #{i+1}:")
    print(f"    Name:    {l['name']}")
    print(f"    Company: {l.get('company', '')}")
    print(f"    Email:   {email}  [{tag}]")
    print(f"    Website: {l.get('website', '')}")
    print(f"    Score:   {l.get('qualification_score', 0)}")
    print(f"    Handle:  {l.get('data_points', {}).get('twitter_handle', '')}")
    print()
