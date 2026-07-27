"""Test social collection save - simulates exact frontend flow"""
import requests
import time

BASE = "http://localhost:5000/api/v1"

# Login
r = requests.post(f"{BASE}/auth/login", json={"email": "admin@example.com", "password": "admin123"})
token = r.json()["token"]
h = {"Authorization": f"Bearer {token}"}

# Get current lead count
r = requests.get(f"{BASE}/leads/", headers=h)
before = r.json()["total"]
print(f"Before collection: {before} leads")

# Start social collection with unique query
r = requests.post(f"{BASE}/ai/collect-social", headers=h, json={
    "query": "artificial intelligence startup funding",
    "platforms": ["reddit"],
    "industry": "technology",
    "max_per_platform": 5,
    "collect_type": "both",
    "location": "",
})
print(f"POST /collect-social: {r.status_code}")
data = r.json().get("data", {})
task_id = data.get("task_id")
print(f"Task ID: {task_id}")

if not task_id:
    print("ERROR: No task_id returned!")
    exit(1)

# Poll status like the frontend does
for i in range(60):
    time.sleep(1)
    try:
        sr = requests.get(f"{BASE}/ai/collect-social/status/{task_id}", headers=h)
        task = sr.json().get("data", {})
        status = task.get("status", "unknown")
        pct = task.get("percent", 0)
        platform = task.get("current_platform", "")
        saved = task.get("saved", 0)
        collected = task.get("total_collected", 0)
        print(f"  [{i+1}s] {pct}% status={status} platform={platform} collected={collected} saved={saved}")
        
        if status in ("done", "error"):
            print(f"\nFinal status: {status}")
            print(f"  Collected: {collected}")
            print(f"  Saved: {saved}")
            break
    except Exception as e:
        print(f"  [{i+1}s] Poll error: {e}")

# Check leads after
time.sleep(1)
r = requests.get(f"{BASE}/leads/", headers=h, params={"per_page": 100})
after_data = r.json()
after = after_data["total"]
print(f"\nAfter collection: {after} leads (was {before})")
print(f"New leads: {after - before}")

if after > before:
    # Show the newest leads
    leads = after_data.get("leads", [])
    print("\nNewest leads:")
    for lead in leads[:5]:
        print(f"  ID={lead['id']} name={lead.get('name','')} email={lead.get('email','')} source={lead.get('source','')}")
else:
    print("\n⚠ NO NEW LEADS SAVED!")
    # Check all leads to see what's in there
    leads = after_data.get("leads", [])
    print(f"Existing leads ({len(leads)}):")
    for lead in leads[:15]:
        print(f"  ID={lead['id']} name={lead.get('name','')} email={lead.get('email','')} source={lead.get('source','')}")
