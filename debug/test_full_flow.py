"""Test the exact API flow the frontend uses"""
import requests

BASE = 'http://127.0.0.1:5000/api/v1'

# 1. Login
login = requests.post(f'{BASE}/auth/login', json={'email': 'admin@example.com', 'password': 'admin123'})
lr = login.json()
token = lr.get('token')
if not token:
    print('Login failed:', lr)
    exit(1)
print(f'Login OK, token starts with: {token[:20]}...')
headers = {'Authorization': f'Bearer {token}'}

# 2. GET /leads/ - exactly as frontend does
resp = requests.get(f'{BASE}/leads/', headers=headers, params={'page': 1, 'per_page': 10})
print(f'\nGET /leads/ status: {resp.status_code}')

if resp.status_code != 200:
    print(f'ERROR: {resp.text[:500]}')
    exit(1)

data = resp.json()
print(f'Response keys: {list(data.keys())}')

leads = data.get('leads', [])
total = data.get('total', 0)
print(f'Total: {total}, Leads on page: {len(leads)}')

for i, l in enumerate(leads):
    print(f'  [{i+1}] {l.get("name", "?")} | {l.get("email", "?")} | {l.get("source", "?")} | type={l.get("lead_type", "?")}')

# 3. Test collect-social with a new query to avoid duplicates
print('\n--- Testing new collection ---')
resp = requests.post(f'{BASE}/ai/collect-social', headers=headers, json={
    'query': 'marketing agency digital',
    'platforms': ['reddit'],
    'industry': 'marketing',
    'max_per_platform': 5,
    'collect_type': 'both',
    'location': '',
})
print(f'Collect: {resp.status_code} {resp.json().get("message", "")}')
task_id = resp.json().get('data', {}).get('task_id')

if task_id:
    import time
    for i in range(60):
        time.sleep(2)
        st = requests.get(f'{BASE}/ai/collect-social/status/{task_id}', headers=headers)
        task = st.json().get('data', {})
        pct = task.get('percent', 0)
        status = task.get('status', '')
        saved = task.get('saved', 0)
        collected = task.get('total_collected', 0)
        plat = task.get('current_platform', '')
        print(f'  [{i*2}s] {pct}% status={status} plat={plat} coll={collected} saved={saved}')
        if status in ('done', 'error') or pct >= 100:
            break
    
    time.sleep(1)
    # Check leads again
    resp2 = requests.get(f'{BASE}/leads/', headers=headers, params={'page': 1, 'per_page': 50})
    data2 = resp2.json()
    total2 = data2.get('total', 0)
    leads2 = data2.get('leads', [])
    print(f'\nAfter collection: Total={total2}, On page={len(leads2)}')
    print(f'New leads: {total2 - total}')
