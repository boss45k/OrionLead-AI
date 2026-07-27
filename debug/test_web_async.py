"""Test the new async web collection endpoint"""
import requests
import time

BASE = "http://localhost:5000/api/v1"

# Login
r = requests.post(f"{BASE}/auth/login", json={"email": "admin@example.com", "password": "admin123"})
token = r.json()["token"]
h = {"Authorization": f"Bearer {token}"}

# Get current count
r = requests.get(f"{BASE}/leads/", headers=h)
before = r.json()["total"]
print(f"Before: {before} leads")

# Start async web collection
r = requests.post(f"{BASE}/ai/collect-leads", headers=h, json={
    "query": "digital marketing agency",
    "countries": ["US"],
    "max_per_country": 3,
    "collection_type": "companies",
})
print(f"POST /collect-leads: {r.status_code}")
print(f"Response: {r.json()}")
data = r.json().get("data", {})
task_id = data.get("task_id")

if not task_id:
    print("ERROR: No task_id!")
    exit(1)

print(f"Task ID: {task_id}")

# Poll status
for i in range(120):
    time.sleep(1)
    try:
        sr = requests.get(f"{BASE}/ai/collect-leads/status/{task_id}", headers=h)
        task = sr.json().get("data", {})
        status = task.get("status", "unknown")
        pct = task.get("percent", 0)
        country = task.get("current_country", "")
        saved = task.get("saved", 0)
        collected = task.get("total_collected", 0)
        print(f"  [{i+1}s] {pct}% status={status} country={country} collected={collected} saved={saved}")
        
        if status in ("done", "error"):
            print(f"\nFinal: {status}")
            print(f"  Collected: {collected}, Saved: {saved}")
            print(f"  By country: {task.get('by_country', {})}")
            break
    except Exception as e:
        print(f"  [{i+1}s] Poll error: {e}")

# Check after
time.sleep(1)
r = requests.get(f"{BASE}/leads/", headers=h, params={"per_page": 50})
after = r.json()["total"]
print(f"\nAfter: {after} leads (was {before}, +{after - before})")
