# Unused Files Report
**Generated:** 2026-05-15  
**Project:** AI-Lead-Collection-System  
**Scan scope:** backend/ (Python) · web/src/ (React/JSX)  
**Total files scanned:** 160+ backend Python files, 21 frontend JS/JSX files  

---

## Methodology

1. Grep-based import scan — searched every Python/JS file for `import`, `from … import`, `require()`  
2. Blueprint registration audit — verified every route file against `backend/app/__init__.py`  
3. Celery/dynamic import audit — scanned for `importlib`, `__import__`, `getattr(module, …)`, `shared_task`, `autodiscover_tasks`  
4. Frontend router audit — verified every page/component against `web/src/App.js` route tree  
5. Test usage scan — verified every service against `backend/tests/`  

---

## HIGH CONFIDENCE UNUSED (90 %+)

### 1. `backend/app/services/ollama_service.py`
| Field | Value |
|-------|-------|
| **Lines** | ~700 |
| **Why flagged** | Defines `OllamaService` class and `get_ollama_service()` singleton — never imported by any other file |
| **Import count** | 0 (self-references only) |
| **Blueprint** | N/A (service) |
| **Celery task** | No |
| **Test usage** | No |
| **Dynamic import risk** | None found |
| **Note** | `advanced_ai.py` has its own Ollama integration (`initialize_ollama`, `qualify_with_ollama`) that uses the `ollama` package directly — `ollama_service.py` is a duplicate that was never wired |
| **Risk level** | LOW |
| **Confidence unused** | 95 % |

---

### 2. `backend/app/routes/leads_enrich.py`
| Field | Value |
|-------|-------|
| **Lines** | 147 |
| **Why flagged** | Defines `Blueprint('leads_enrich', …)` but is **never imported or registered** in `app/__init__.py` |
| **Import count** | 0 |
| **Blueprint registered** | NO — not present in any `app.register_blueprint()` call |
| **Celery task** | No |
| **Test usage** | No |
| **Dynamic import risk** | None found |
| **Note** | Shadow blueprint — endpoints are functional but permanently unreachable since no route is registered. Naming overlap (`leads_bp`) with the active `leads.py` blueprint could cause silent bugs if accidentally imported |
| **Risk level** | MEDIUM (naming conflict potential) |
| **Confidence unused** | 98 % |

---

### 3. `web/src/components/CollectionReport.jsx`
| Field | Value |
|-------|-------|
| **Lines** | ~100 |
| **Why flagged** | Exports `default function CollectionReport` — never imported by any page, App.js, or other component |
| **Import count** | 0 (verified via grep across entire web/src/) |
| **Route registration** | No |
| **Lazy-loaded** | No |
| **Test usage** | No |
| **Dynamic import risk** | None found |
| **Risk level** | LOW |
| **Confidence unused** | 99 % |

---

## LOWER PRIORITY — Manual-use root scripts (NOT quarantined per safety rule 9)

These files are not part of the formal pytest suite but may be manually useful to developers.  
Per Safety Rule 9 ("Do NOT remove: scripts used manually, utility scripts that may be manually executed"), they are **left in place** and documented only.

| File | Purpose | Notes |
|------|---------|-------|
| `backend/test_api.py` | Manual API smoke test | Not in tests/ directory, not in conftest |
| `backend/test_login.py` | Manual login test | Same as above |
| `backend/direct_login_test.py` | Manual login diagnostic | Same as above |
| `backend/check_user.py` | DB user lookup utility | DB admin utility |
| `backend/create_test_user.py` | DB user creation utility | Setup utility |
| `backend/diagnostic.py` | System diagnostic | General diagnostics |

---

## VERIFIED ACTIVE — Files investigated and confirmed USED

All items below were suspected at investigation start but confirmed actively referenced.

| File | Imported by | Confidence active |
|------|-------------|------------------|
| `backend/app/services/advanced_ai.py` | `ai.py` (7 refs) | 100 % |
| `backend/app/services/ml_model.py` | `ai.py`, `ml_decision_layer`, `advanced_ai`, `train_initial_model` | 100 % |
| `backend/app/services/ml_decision_layer.py` | `ai.py` (5+ refs), tested by `test_ml_decision_layer` | 100 % |
| `backend/app/services/dataset_manager.py` | `ai.py` (5 refs), `ml_decision_layer`, scripts | 100 % |
| `backend/app/services/data_generator.py` | `dataset_manager`, `ml_model`, `train_initial_model` | 100 % |
| `backend/app/services/qualification_agent.py` | `ai.py` (2 refs), `test_agents` | 100 % |
| `backend/app/agents/` (all 6 files) | `candidate_pipeline`, `orchestrator_agent`, `app/__init__` | 100 % |
| `backend/app/graph/` (all 3 files) | `graph_agent`, `graph/__init__` | 100 % |
| `backend/app/scoring/` (all 3 files) | `scoring_agent`, `context_scoring`, `score_optimizer`, learning | 100 % |
| `backend/app/learning/` (all 3 files) | `__init__`, `feedback_engine`, `outcome_tracker` | 100 % |
| `backend/app/intent/semantic_intent.py` | `intent/__init__` | 100 % |
| `backend/app/llm/` (all 3 files) | `llm/__init__`, `integration` | 100 % |
| `backend/app/monitoring/` (all 3 files) | `monitoring/__init__`, `app/__init__`, routes | 100 % |
| `backend/app/utils/` (all 7 files) | `app/__init__`, routes, services | 100 % |
| `backend/app/routes/debug.py` | `app/__init__` (dev/test conditional) | 95 % |
| `backend/app/routes/sync.py` | `app/__init__`, `test_sync` | 100 % |
| `backend/app/routes/sources.py` | `app/__init__`, `test_sources` | 100 % |
| `backend/app/routes/analytics.py` | `app/__init__` | 100 % |
| `web/src/components/CollectionReport.jsx` | **UNUSED** — see above | — |
| All other web/src/ files | Verified via App.js router + import scan | 100 % |
