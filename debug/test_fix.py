"""Quick test to verify email + interests fix in collectors."""
import requests
import json

# Login first
login = requests.post('http://localhost:5000/api/v1/auth/login', json={
    'email': 'admin@example.com', 'password': 'admin123'
})
token = login.json()['token']
headers = {'Authorization': f'Bearer {token}'}

# Clear all leads
requests.delete('http://localhost:5000/api/v1/leads/all', headers=headers)
print("Cleared all leads")

# Test web collection (sync)
print("\n=== WEB COLLECTION TEST ===")
resp = requests.post('http://localhost:5000/api/v1/ai/collect-leads/sync', json={
    'query': 'software companies',
    'countries': ['US'],
    'max_per_country': 3
}, headers=headers, timeout=120)

data = resp.json()
print("Status:", resp.status_code)
print("Saved:", data.get('data', {}).get('total_saved', 0))

# Check leads in DB  
print("\n=== LEADS IN DATABASE ===")
r = requests.get('http://localhost:5000/api/v1/leads', headers=headers)
rdata = r.json()
leads = rdata.get('leads', [])
if not leads and 'data' in rdata:
    leads = rdata['data'].get('leads', rdata['data']) if isinstance(rdata['data'], dict) else rdata['data']
print("Total leads:", len(leads))
for lead in leads[:5]:
    name = lead.get('name', 'N/A')
    email = lead.get('email', 'N/A') 
    interests = lead.get('interests', [])
    industry = lead.get('industry', 'N/A')
    website = lead.get('website', 'N/A')
    print("  Name:", name)
    print("  Email:", email)
    print("  Interests:", interests)
    print("  Industry:", industry)
    print("  Website:", website)
    print("  ---")

