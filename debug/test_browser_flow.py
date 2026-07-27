"""Full browser-flow simulation test"""
import requests
import time

s = requests.Session()

# Step 1: Login
r = s.post('http://localhost:5000/api/v1/auth/login', json={'email':'admin@example.com','password':'admin123'})
token = r.json()['token']
headers = {'Authorization': f'Bearer {token}', 'Origin': 'http://localhost:3000'}
print(f'Login: {r.status_code}')

# Step 2: Fetch leads before
r = s.get('http://localhost:5000/api/v1/leads/', headers=headers, params={'page': 1, 'per_page': 5})
data = r.json()
before_total = data.get('total', 0)
print(f'Before: {before_total} total leads, {len(data.get("leads",[]))} on page')

# Step 3: Start social collection
r = s.post('http://localhost:5000/api/v1/ai/collect-social', headers=headers, json={
    'query': 'cybersecurity startup SaaS',
    'platforms': ['reddit'],
    'industry': 'technology',
    'max_per_platform': 3
})
task_id = r.json().get('data', {}).get('task_id', '')
print(f'Collection started: {r.status_code}, task={task_id[:8]}')

# Step 4: Poll status
for i in range(30):
    time.sleep(1)
    r = s.get(f'http://localhost:5000/api/v1/ai/collect-social/status/{task_id}', headers=headers)
    t = r.json().get('data', {})
    status = t.get('status', '')
    if status in ('done', 'error'):
        collected = t.get('total_collected', 0)
        saved = t.get('saved', 0)
        print(f'Finished: status={status}, collected={collected}, saved={saved}')
        break
    print(f'  [{i+1}s] {t.get("percent",0)}% platform={t.get("current_platform","")}')

# Step 5: Fetch leads after (exactly like fetchLeads() does)
r = s.get('http://localhost:5000/api/v1/leads/', headers=headers, params={'page': 1, 'per_page': 5})
data = r.json()
after_total = data.get('total', 0)
print(f'After: {after_total} total leads, {len(data.get("leads",[]))} on page')
print(f'New leads: {after_total - before_total}')

for lead in data.get('leads', []):
    print(f'  ID={lead["id"]} name={lead.get("name","")} source={lead.get("source","")}')
