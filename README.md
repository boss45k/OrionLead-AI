# OrionLead AI — Intelligent Lead Collection System

An end-to-end AI-powered B2B lead collection and qualification platform. It combines multi-source web collection, LLM-based enrichment, an XGBoost scoring model, and a real-time React dashboard with a companion React Native mobile app.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React Web Dashboard                   │
│         (Ant Design · Chart.js · Dark / Light mode)     │
└────────────────────────┬────────────────────────────────┘
                         │ REST / JWT
┌────────────────────────▼────────────────────────────────┐
│                  Flask REST API (Python)                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Auth / JWT │  │  Leads CRUD  │  │   AI Engine    │  │
│  └─────────────┘  └──────────────┘  └────────────────┘  │
│  ┌──────────────────────────────────────────────────┐    │
│  │           Intelligence Pipeline                  │    │
│  │  Gemini → Anti-Junk → Validator → XGBoost ML    │    │
│  └──────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────┘
                         │
       ┌─────────────────┼──────────────────┐
       ▼                 ▼                  ▼
  MySQL / SQLite    Supabase Sync     External APIs
                   (mobile bridge)   Hunter · Apollo
                                     Gemini · Groq
                                     Google Places
                                     Serper · PDL
                         │
┌────────────────────────▼────────────────────────────────┐
│                React Native Mobile App                   │
│              (Expo · offline-first · FCM push)           │
└─────────────────────────────────────────────────────────┘
```

---

## Key Features

| Feature | Details |
|---|---|
| Multi-source collection | Apollo.io, Hunter.io, Google Places, LinkedIn scraping, Serper web search, public directories |
| AI qualification | 4-layer cascade: rules → XGBoost ML (37 features) → Gemini LLM → Groq fallback |
| Anti-junk engine | 12 hard-reject rules: fake names, URLs-as-company, NGOs, person-as-company, generic emails |
| Lead outcome labeling | One-click QuickLabelBar (Converted / Replied / No Reply / Not a Fit) feeds ML training loop |
| ML retrain | `POST /ai/retrain` — XGBoost retrains on human-labeled outcomes; CV accuracy returned live |
| CSV export | Full filtered export via `GET /leads/export` — all leads, not just current page |
| Mobile sync | Supabase bridge pushes qualified leads to the React Native app in real time |
| Analytics dashboard | Lead Activity, Sales Funnel, Score Distribution, By Source / Industry / Country charts |
| GitHub Actions CI | 563-test pytest suite runs on every push against SQLite in-memory |

---

## Tech Stack

### Backend
| Layer | Technology |
|---|---|
| Web framework | Flask 3 + Blueprints |
| Database ORM | SQLAlchemy + PyMySQL |
| Auth | JWT (PyJWT) + bcrypt |
| ML model | **XGBoost** (`XGBClassifier`, 37 features, model version `xgb_v5`) |
| LLM enrichment | **Google Gemini** (`gemini-1.5-flash`) |
| LLM fallback | **Groq** (`llama-3-8b-8192`) |
| Lead APIs | Hunter.io, Apollo.io, People Data Labs, ZeroBounce |
| Search APIs | Google Places (New), Serper.dev |
| Mobile sync | Supabase (PostgreSQL + Realtime) |
| Rate limiting | Flask-Limiter |
| Tests | pytest — **563 passed, 0 failures** |

### Frontend (Web)
| Layer | Technology |
|---|---|
| Framework | React 18 + Vite |
| UI library | Ant Design 5 |
| Charts | Chart.js 4 + react-chartjs-2 |
| Routing | React Router v6 |
| HTTP | Axios |
| Auth | Google OAuth 2.0 + JWT |

### Mobile
| Layer | Technology |
|---|---|
| Framework | React Native + Expo |
| Sync | Supabase Realtime |
| Push | Firebase Cloud Messaging (FCM) |

---

## Project Structure

```
AI-Lead-Collection-System/
├── .github/workflows/test.yml   # CI: pytest on every push
├── backend/
│   ├── app/
│   │   ├── routes/              # Blueprints: auth, leads, ai, sources, sync, analytics
│   │   ├── services/            # ml_model, qualification_agent, lead_extractor
│   │   ├── intelligence/        # anti_junk_engine, business_classifier, contact_resolver
│   │   ├── validation/          # fake_lead_detector, lead_validator
│   │   └── models/              # SQLAlchemy: Lead, User, LeadOutcome, DataSource
│   ├── tests/                   # 563 pytest tests (SQLite in-memory)
│   └── config/                  # Environment-validated configuration
├── web/                         # React dashboard
│   └── src/
│       ├── pages/               # Dashboard, LeadsPage, AIEngine, Analytics, Settings
│       └── services/            # Axios API client with JWT interceptors
├── mobile/                      # React Native app (Expo)
└── database/                    # MySQL schema and migrations
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- MySQL 8+ (SQLite used automatically for tests)

### 1 — Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows (use source venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
cp ../.env.example ../.env     # fill in your API keys
python run.py                  # starts on http://localhost:5000
```

### 2 — Web Dashboard

```bash
cd web
npm install
npm start                      # opens http://localhost:3000
```

### 3 — Run Tests

```bash
cd backend
python -m pytest tests/ -q
# Expected: 563 passed, 7 skipped, 0 failed
```

---

## Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | MySQL connection string |
| `SECRET_KEY` | Yes | Flask session secret (minimum 32 chars) |
| `JWT_SECRET_KEY` | Yes | JWT signing secret (minimum 32 chars) |
| `GEMINI_API_KEY` | Recommended | Google Gemini LLM for lead enrichment |
| `GROQ_API_KEY` | Recommended | Groq fallback LLM |
| `HUNTER_API_KEY` | Optional | Hunter.io email finder |
| `APOLLO_API_KEY` | Optional | Apollo.io people search |
| `GOOGLE_PLACES_API_KEY` | Optional | Local business discovery |
| `SERPER_API_KEY` | Optional | Google Search results API |
| `SUPABASE_URL` | Optional | Mobile sync bridge |
| `SUPABASE_SERVICE_KEY` | Optional | Mobile sync (service role key) |
| `ZEROBOUNCE_API_KEY` | Optional | Email verification |

> A startup config validator logs which APIs are configured or missing when the server starts.

---

## ML Model

The scoring model is `XGBLeadScoringModel` (`xgb_v5`, 37 features):

- **Score tiers**: Hot ≥ 80 · Warm ≥ 60 · Cold ≥ 30 · Unqualified < 30
- **ML weight**: 0% at start (rules-only) → ramps to 40% once 50+ human labels exist
- **Retrain**: `POST /api/v1/ai/retrain` — cross-validated accuracy returned in response
- **Label leads**: Use the QuickLabelBar in the web dashboard → every label improves the model

---

## API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Public | Login, returns JWT |
| GET | `/api/v1/leads` | JWT | List leads (paginated + filtered) |
| GET | `/api/v1/leads/export` | JWT | Export all filtered leads as CSV |
| GET | `/api/v1/leads/stats` | JWT | Stats + score distribution |
| POST | `/api/v1/ai/collect/interest` | JWT | Collect leads by keyword/interest |
| POST | `/api/v1/ai/feedback` | JWT | Label a lead outcome (feeds ML training) |
| POST | `/api/v1/ai/retrain` | JWT Admin | Retrain XGBoost on all labeled data |
| GET | `/api/v1/analytics` | JWT | Time-series analytics |
| POST | `/api/v1/sync/web-to-mobile` | JWT Mobile | Push leads to Supabase / mobile app |

---

## CI/CD

Every push and pull request to `main` runs the full test suite automatically:

```yaml
# .github/workflows/test.yml
- Python 3.11 + pip cache
- pip install -r backend/requirements.txt
- pytest backend/tests/ (SQLite in-memory — no database server needed)
- PR blocked if any test fails
```

---

## Ethical Considerations

- Collects only publicly available business contact data
- Respects robots.txt and platform rate limits
- Compliant with GDPR / CCPA data minimisation principles
- No personal data stored without a legitimate B2B business purpose
