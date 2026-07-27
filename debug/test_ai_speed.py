import requests, time

r = requests.post('http://localhost:5000/api/v1/auth/login', json={'email':'admin@example.com','password':'admin123'}, timeout=10)
tok = r.json()['token']
h = {'Authorization': f'Bearer {tok}'}

# Test health
t = time.time()
r1 = requests.get('http://localhost:5000/api/v1/ai/health', headers=h, timeout=15)
d1 = r1.json()
print(f"Health: {round(time.time()-t,1)}s, status={r1.status_code}, ai_status={d1.get('ai_status','?')}, provider={d1.get('provider','?')}")

# Test analyze
t = time.time()
r2 = requests.post('http://localhost:5000/api/v1/ai/analyze-lead/366', headers=h, timeout=30)
d2 = r2.json()
print(f"Analyze: {round(time.time()-t,1)}s, status={r2.status_code}, provider={d2.get('ai_provider','?')}")

# Test generate email
t = time.time()
r3 = requests.post('http://localhost:5000/api/v1/ai/generate-email/366', headers=h, json={'email_type':'cold_outreach'}, timeout=30)
d3 = r3.json()
print(f"Email: {round(time.time()-t,1)}s, status={r3.status_code}, provider={d3.get('ai_provider','?')}")

# Test chat
t = time.time()
r4 = requests.post('http://localhost:5000/api/v1/ai/chat', headers=h, json={'message':'Who are the top 3 leads?'}, timeout=30)
d4 = r4.json()
print(f"Chat: {round(time.time()-t,1)}s, status={r4.status_code}, provider={d4.get('ai_provider','?')}")

# Test batch qualify
t = time.time()
r5 = requests.post('http://localhost:5000/api/v1/ai/qualify-batch', headers=h, json={'limit':50}, timeout=30)
d5 = r5.json()
print(f"Batch: {round(time.time()-t,1)}s, status={r5.status_code}, processed={d5.get('total_processed',0)}")

# Test pipeline summary
t = time.time()
r6 = requests.get('http://localhost:5000/api/v1/ai/pipeline-summary', headers=h, timeout=30)
d6 = r6.json()
print(f"Pipeline: {round(time.time()-t,1)}s, status={r6.status_code}, provider={d6.get('ai_provider','?')}")

# Test stats
t = time.time()
r7 = requests.get('http://localhost:5000/api/v1/ai/stats', headers=h, timeout=15)
d7 = r7.json()
s = d7.get('stats', {})
print(f"Stats: {round(time.time()-t,1)}s, status={r7.status_code}, ai_provider={s.get('ai_provider','?')}")
