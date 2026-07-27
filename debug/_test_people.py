import sys
sys.path.insert(0, 'backend')
from app.services.public_web_collector import PublicWebCollector

c = PublicWebCollector(rate_limit=1.5, timeout=12)
leads = c.collect_people_by_country('CEO technology', 'US', city='San Francisco', max_leads=8)
print(f"Collected {len(leads)} people")
for i, l in enumerate(leads, 1):
    name = l.get('name', 'N/A')
    position = l.get('position', 'N/A')
    company = l.get('company', 'N/A')
    email = l.get('email', 'N/A')
    linkedin = l.get('linkedin_url', 'N/A')
    source = l.get('source', 'N/A')
    score = l.get('qualification_score', 0)
    print(f"\n  [{i}] {name}")
    print(f"      Position: {position}")
    print(f"      Company:  {company}")
    print(f"      Email:    {email}")
    print(f"      LinkedIn: {linkedin}")
    print(f"      Source:   {source}")
    print(f"      Score:    {score}")
