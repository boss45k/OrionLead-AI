import requests, json, time

base = 'http://localhost:5000/api/v1'

# Login
r = requests.post(f'{base}/auth/login', json={'email':'admin@example.com','password':'admin123'}, timeout=10)
print(f'Login: {r.status_code}')
data = r.json()
token = data.get('access_token') or data.get('token')
if not token:
    print(f'Login failed: {data}')
    exit(1)
h = {'Authorization': f'Bearer {token}'}

# 1. Health
t=time.time()
r=requests.get(f'{base}/ai/health', headers=h, timeout=15)
d=r.json()
print(f"\n1. Health: {time.time()-t:.1f}s | status={d.get('ai_status')} | provider={d.get('provider')} | model={d.get('model')}")

# 2. Qualify
t=time.time()
r=requests.post(f'{base}/ai/qualify/366', headers=h, timeout=30)
d=r.json()
prov = d.get('ai_provider', '?')
score = d.get('score', d.get('qualification_score', '?'))
cat = d.get('category', '?')
print(f"2. Qualify: {time.time()-t:.1f}s | {r.status_code} | provider={prov} | score={score} | {cat}")

# 3. Analyze
t=time.time()
r=requests.post(f'{base}/ai/analyze-lead/366', headers=h, timeout=30)
d=r.json()
prov = d.get('provider', d.get('ai_provider', '?'))
print(f"3. Analyze: {time.time()-t:.1f}s | {r.status_code} | provider={prov}")

# 4. Email
t=time.time()
r=requests.post(f'{base}/ai/generate-email/366', headers=h, timeout=30)
d=r.json()
prov = d.get('provider', d.get('ai_provider', '?'))
subj = d.get('subject', '')
if not subj and 'email' in d:
    subj = d['email'].get('subject', '')
print(f"4. Email: {time.time()-t:.1f}s | {r.status_code} | provider={prov} | subject={subj[:60]}")

# 5. Chat
t=time.time()
r=requests.post(f'{base}/ai/chat', headers=h, json={'message':'Who are the top 3 best leads?'}, timeout=45)
d=r.json()
prov = d.get('ai_provider', '?')
resp = d.get('response', '?')
print(f"5. Chat: {time.time()-t:.1f}s | {r.status_code} | provider={prov} | response={resp[:100]}")

print("\nDone!")
