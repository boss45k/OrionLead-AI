"""Test the API endpoint for web collection"""
import requests

# Login first
login = requests.post("http://localhost:5000/api/v1/auth/login", 
                       json={"email":"admin@test.com","password":"admin123"})
token = login.json().get("token","")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Test supported countries
r = requests.get("http://localhost:5000/api/v1/ai/supported-countries", headers=headers)
countries = r.json()
print(f"Supported countries: {countries.get('total', 0)}")

# Test sync collection
print("\nStarting sync collection (UK consulting firms, London, max 3)...")
r2 = requests.post("http://localhost:5000/api/v1/ai/collect-leads/sync", 
                    headers=headers, 
                    json={
                        "query": "consulting firms",
                        "countries": ["UK"],
                        "city": "London",
                        "max_per_country": 3
                    }, 
                    timeout=120)
data = r2.json()
print(f"Status: {data.get('status')}")
print(f"Message: {data.get('message')}")
if data.get("data"):
    d = data["data"]
    print(f"Total collected: {d.get('total_collected', 0)}")
    print(f"Total saved: {d.get('total_saved', 0)}")
    for lead in d.get("leads", []):
        name = str(lead.get("name", ""))[:40]
        email = lead.get("email", "N/A")
        company = str(lead.get("company", ""))[:30]
        country = lead.get("country", "")
        industry = lead.get("industry", "")
        print(f"  - {name} | {email} | {company} | {country} | {industry}")
else:
    print(f"Full response: {data}")
