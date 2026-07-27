"""Test people collection pipeline."""
import sys, os
sys.path.insert(0, 'backend')
os.environ.setdefault('FLASK_ENV', 'development')

from app.services.public_web_collector import PublicWebCollector

c = PublicWebCollector()

print("=== Test 1: US CTO technology (New York) ===")
leads = c.collect_people_by_country('CTO technology', 'US', city='New York', max_leads=8)
print(f"Got {len(leads)} leads\n")
for i, lead in enumerate(leads):
    print(f"  {i+1}. {lead.get('name','')}")
    print(f"     Position: {lead.get('position','')}")
    print(f"     Company:  {lead.get('company','')}")
    print(f"     Email:    {lead.get('email','')}")
    print(f"     Phone:    {lead.get('phone','')}")
    print(f"     LinkedIn: {lead.get('linkedin_url','')}")
    print(f"     Source:   {lead.get('source','')}")
    print()

print("\n=== Test 2: AE marketing director (Dubai) ===")
leads2 = c.collect_people_by_country('marketing director', 'AE', city='Dubai', max_leads=5)
print(f"Got {len(leads2)} leads\n")
for i, lead in enumerate(leads2):
    print(f"  {i+1}. {lead.get('name','')}")
    print(f"     Position: {lead.get('position','')}")
    print(f"     Company:  {lead.get('company','')}")
    print(f"     Email:    {lead.get('email','')}")
    print(f"     LinkedIn: {lead.get('linkedin_url','')}")
    print()
