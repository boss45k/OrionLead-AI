"""Quick test: collect from reddit, verify leads save to DB."""
import requests, time

BASE = 'http://127.0.0.1:5000/api/v1'

# Login
login = requests.post(f'{BASE}/auth/login', json={'email': 'admin@example.com', 'password': 'admin123'})
lr = login.json()
token = lr.get('token') or lr.get('data', {}).get('access_token') or lr.get('access_token')
if not token:
    print('Login failed:', login.json())
    exit(1)
print('Logged in OK')
headers = {'Authorization': f'Bearer {token}'}

# Count leads before
resp = requests.get(f'{BASE}/leads/', headers=headers)
count_before = resp.json().get('data', {}).get('total', 0) if resp.ok else 0
print(f'Leads before: {count_before}')

# Start social collection
resp = requests.post(f'{BASE}/ai/collect-social', headers=headers, json={
    'query': 'SaaS startup founder',
    'platforms': ['reddit'],
    'industry': 'technology',
    'max_per_platform': 5,
    'collect_type': 'both',
    'location': '',
})
msg = resp.json().get('message', '')
print(f'Collect: {resp.status_code} {msg}')
task_id = resp.json().get('data', {}).get('task_id')
if not task_id:
    print('No task_id!')
    exit(1)

# Poll progress
for i in range(90):
    time.sleep(2)
    st = requests.get(f'{BASE}/ai/collect-social/status/{task_id}', headers=headers)
    task = st.json().get('data', {})
    pct = task.get('percent', 0)
    status = task.get('status', '')
    saved = task.get('saved', 0)
    collected = task.get('total_collected', 0)
    platform = task.get('current_platform', '')
    print(f'  [{i*2}s] {pct}% status={status} plat={platform} coll={collected} saved={saved}')
    if task.get('debug_errors'):
        print(f'    DEBUG ERRORS: {task["debug_errors"]}')
    if task.get('debug_leads_after_filter') is not None:
        print(f'    LEADS AFTER FILTER: {task["debug_leads_after_filter"]}')
    if task.get('debug_skipped'):
        print(f'    SKIPPED: {task["debug_skipped"]}')
    if status in ('done', 'error') or pct >= 100:
        break

time.sleep(1)
# Count leads after
resp = requests.get(f'{BASE}/leads/', headers=headers)
count_after = resp.json().get('data', {}).get('total', 0) if resp.ok else 0
print(f'Leads after: {count_after}')
diff = count_after - count_before
print(f'NEW LEADS SAVED: {diff}')
if diff > 0:
    print('SUCCESS - leads are saving to database!')
else:
    print('PROBLEM - no new leads saved')
