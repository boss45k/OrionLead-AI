import requests, json, time

token = requests.post('http://localhost:5000/api/v1/auth/login',
    json={'email': 'admin@example.com', 'password': 'admin123'}, timeout=10).json()['token']
h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

for platform in ['reddit', 'telegram', 'twitter', 'facebook']:
    print(f"\n=== Testing {platform.upper()} ===")
    s = time.time()
    r = requests.post('http://localhost:5000/api/v1/ai/collect-social',
        json={
            'query': 'AI startups',
            'platforms': [platform],
            'industry': 'ai',
            'max_per_platform': 3,
        }, headers=h, timeout=120)
    e = time.time()
    d = r.json()
    data = d.get('data', {})
    print(f"  Status: {r.status_code}, Time: {e-s:.1f}s")
    print(f"  Collected: {data.get('total_collected')}, Saved: {data.get('total_saved')}")
    for lead in data.get('leads', [])[:3]:
        print(f"    - {lead.get('name')} | {lead.get('company')} | {lead.get('source')} | score: {lead.get('score')}")
