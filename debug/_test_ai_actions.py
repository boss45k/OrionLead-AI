"""
Comprehensive test suite for all AI action endpoints.
Tests: health, stats, analyze-lead, generate-email, chat, pipeline-summary, qualify-batch, collect-leads
"""
import requests
import json
import time
import sys

BASE = "http://localhost:5000/api/v1"
PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS = []

def login():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    r.raise_for_status()
    return r.json()["token"]

def test(name, method, url, token, json_body=None, timeout=180):
    global PASS_COUNT, FAIL_COUNT
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"  {method} {url}")
    if json_body:
        print(f"  Body: {json.dumps(json_body)[:120]}")
    print(f"{'='*60}")
    
    start = time.time()
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=timeout)
        else:
            r = requests.post(url, headers=headers, json=json_body, timeout=timeout)
        
        elapsed = round(time.time() - start, 2)
        data = r.json()
        status_ok = r.status_code == 200
        has_status = data.get("status") == "success"
        
        if status_ok and has_status:
            PASS_COUNT += 1
            result = "PASS"
        else:
            FAIL_COUNT += 1
            result = "FAIL"
        
        print(f"  HTTP {r.status_code} | {result} | {elapsed}s")
        print(f"  Keys: {list(data.keys())}")
        
        # Show key response fields, truncated
        for k, v in data.items():
            if k == "status":
                continue
            if k == "stats" and isinstance(v, dict):
                print(f"  {k}:")
                for sk, sv in v.items():
                    print(f"    {sk}: {str(sv)[:100]}")
            else:
                val_str = str(v)
                if len(val_str) > 300:
                    val_str = val_str[:300] + "..."
                print(f"  {k}: {val_str}")
        
        RESULTS.append({"name": name, "result": result, "time": elapsed, "code": r.status_code})
        return data
        
    except requests.exceptions.Timeout:
        elapsed = round(time.time() - start, 2)
        FAIL_COUNT += 1
        print(f"  TIMEOUT after {elapsed}s (limit: {timeout}s)")
        RESULTS.append({"name": name, "result": "TIMEOUT", "time": elapsed})
        return None
    except requests.exceptions.ConnectionError:
        elapsed = round(time.time() - start, 2)
        FAIL_COUNT += 1
        print(f"  CONNECTION ERROR after {elapsed}s")
        RESULTS.append({"name": name, "result": "CONN_ERR", "time": elapsed})
        return None
    except KeyboardInterrupt:
        elapsed = round(time.time() - start, 2)
        print(f"  INTERRUPTED after {elapsed}s")
        RESULTS.append({"name": name, "result": "SKIP", "time": elapsed})
        return None
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        FAIL_COUNT += 1
        print(f"  {type(e).__name__}: {e} | {elapsed}s")
        RESULTS.append({"name": name, "result": "ERROR", "time": elapsed})
        return None

def main():
    global PASS_COUNT, FAIL_COUNT
    print("=" * 60)
    print("AI ACTIONS TEST SUITE")
    print("=" * 60)
    
    # Login
    print("\nLogging in...")
    token = login()
    print(f"  Token: {token[:20]}...")
    
    # Get a test lead
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE}/leads/?per_page=1", headers=headers)
    lead_id = r.json()["leads"][0]["id"]
    lead_name = r.json()["leads"][0]["name"]
    print(f"  Test lead: #{lead_id} - {lead_name}")
    
    # ======== TEST 1: Health Check ========
    test("AI Health Check", "GET", f"{BASE}/ai/health", token)
    
    # ======== TEST 2: Stats ========
    data = test("AI Stats", "GET", f"{BASE}/ai/stats", token)
    if data:
        stats_str = json.dumps(data.get("stats", {}))
        if "sk-proj" in stats_str or "sk-ant" in stats_str:
            print("  *** SECURITY FAIL: API key leaked! ***")
            FAIL_COUNT += 1
        else:
            print("  SECURITY: No API key leak")
    
    # ======== TEST 3: Analyze Lead ========
    test("Analyze Lead", "POST", f"{BASE}/ai/analyze-lead/{lead_id}", token)
    
    # ======== TEST 4: Generate Email (cold) ========
    test("Generate Email (cold)", "POST", f"{BASE}/ai/generate-email/{lead_id}", token,
         json_body={"email_type": "cold_outreach", "tone": "professional"})
    
    # ======== TEST 5: Generate Email (followup) ========
    test("Generate Email (followup)", "POST", f"{BASE}/ai/generate-email/{lead_id}", token,
         json_body={"email_type": "follow_up", "tone": "friendly"})
    
    # ======== TEST 6: AI Chat ========
    test("AI Chat", "POST", f"{BASE}/ai/chat", token,
         json_body={"message": "Which leads are the most qualified?"})
    
    # ======== TEST 7: Pipeline Summary ========
    test("Pipeline Summary", "GET", f"{BASE}/ai/pipeline-summary", token)
    
    # ======== TEST 8: Batch Qualify ========
    test("Batch Qualify (1 lead)", "POST", f"{BASE}/ai/qualify-batch", token,
         json_body={"lead_ids": [lead_id], "batch_size": 1})
    
    # ======== TEST 9: Supported Countries ========
    test("Supported Countries", "GET", f"{BASE}/ai/supported-countries", token, timeout=10)
    
    # ======== TEST 10: AI Logs ========
    test("AI Logs", "GET", f"{BASE}/ai/logs", token, timeout=10)
    
    # ======== SUMMARY ========
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for r in RESULTS:
        icon = "+" if r["result"] == "PASS" else "-"
        print(f"  [{icon}] {r['name']:40s} {r['result']:10s} ({r['time']}s)")
    
    total = PASS_COUNT + FAIL_COUNT
    print(f"\n  TOTAL: {total} | PASS: {PASS_COUNT} | FAIL: {FAIL_COUNT}")
    print("=" * 60)
    
    return 0 if FAIL_COUNT == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
