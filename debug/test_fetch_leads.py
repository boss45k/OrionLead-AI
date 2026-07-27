"""Simulate the EXACT frontend fetchLeads call after a social collection"""
import requests

BASE = "http://localhost:5000/api/v1"

# Login
r = requests.post(f"{BASE}/auth/login", json={"email": "admin@example.com", "password": "admin123"})
token = r.json()["token"]
h = {"Authorization": f"Bearer {token}"}

# Call GET /leads/ with the same params the frontend sends (page=1, per_page=5, no filters)
r = requests.get(f"{BASE}/leads/", headers=h, params={"page": 1, "per_page": 5})
data = r.json()

print(f"Status: {r.status_code}")
print(f"Total: {data.get('total')}")
print(f"Current Page: {data.get('current_page')}")
print(f"Total Pages: {data.get('total_pages')}")
print(f"Per Page: {data.get('per_page')}")
print(f"Leads on this page: {len(data.get('leads', []))}")
print()

for lead in data.get("leads", []):
    print(f"  ID={lead['id']} name={lead.get('name','')} email={lead.get('email','')} source={lead.get('source','')} status={lead.get('status','')}")

# Also test with per_page=10 (API default)
print("\n--- With per_page=10 ---")
r2 = requests.get(f"{BASE}/leads/", headers=h, params={"page": 1, "per_page": 10})
data2 = r2.json()
print(f"Total: {data2.get('total')}, Leads on page: {len(data2.get('leads', []))}")
for lead in data2.get("leads", []):
    print(f"  ID={lead['id']} name={lead.get('name','')} source={lead.get('source','')} status={lead.get('status','')}")
