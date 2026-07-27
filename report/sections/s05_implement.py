"""
s05_implement.py — Chapter 5: System Implementation
Target: 12-14 pages
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import theme as T
from docx.shared import Cm


def build(doc):
    T.chapter_title(doc, 5, "System Implementation")

    T.body(doc,
        "This chapter describes the concrete implementation of OrionLead AI across "
        "all system components, translating the architectural design of Chapter 4 into "
        "working code. It covers the complete technology stacks, the backend directory "
        "structure and key implementation patterns, the AI engine's feature engineering "
        "and cascade orchestration, the web frontend's component and state management "
        "implementation, the mobile application's component architecture, the database "
        "schema creation and indexing strategy, the API endpoint surface, and the "
        "real-time synchronization pipeline.")

    # ── 5.1 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "5.1", "Development Environment")

    T.body(doc,
        "The development environment for OrionLead AI uses standard, widely-available "
        "open-source tools. All three components — backend, web frontend, and mobile "
        "application — are developed on Windows 11 with VS Code as the primary editor. "
        "Python dependencies are managed through a virtual environment (venv) with "
        "pip, Node.js dependencies through npm, and mobile development through the "
        "Expo CLI. Tables 5.1, 5.2, and 5.3 list the complete technology stacks.")

    T.subsection_h(doc, "5.1.1", "Backend Technology Stack")
    headers = ["Component", "Technology", "Version", "Purpose"]
    rows = [
        ["Language",           "Python",           "3.11+",    "Primary backend programming language"],
        ["Web Framework",      "Flask",             "2.3.2",    "RESTful API server with Blueprint routing"],
        ["ORM",                "SQLAlchemy",        "2.0.18",   "Database abstraction and model definitions"],
        ["Database",           "MySQL",             "8.0",      "Primary relational data store"],
        ["Cache / Broker",     "Redis",             "4.5.5",    "Celery message broker and response cache"],
        ["Task Queue",         "Celery",            "5.3.1",    "Background job processing and scheduling"],
        ["ML Framework",       "XGBoost",           ">=2.0",    "Gradient-boosted qualification model"],
        ["ML Support",         "scikit-learn",      "1.3.0",    "Model training, cross-validation, metrics"],
        ["Data Processing",    "pandas",            "2.0.3",    "Feature engineering and data manipulation"],
        ["NLP",                "NLTK",              "3.8.1",    "Text normalization for name/title features"],
        ["Authentication",     "PyJWT",             "2.8.0",    "JWT token signing and verification"],
        ["Password Hashing",   "flask-bcrypt",      "1.0.1",    "bcrypt password hashing with cost factor 12"],
        ["API Docs",           "Flasgger",          "0.9.7",    "Swagger UI generation from docstrings"],
        ["Push Notifications", "firebase-admin",    ">=6.2",    "FCM push notification dispatch"],
        ["HTTP Client",        "requests",          "2.31.0",   "Outbound API calls to external data sources"],
        ["Env Config",         "python-dotenv",     "1.0.0",    "Environment variable loading from .env files"],
        ["CORS",               "flask-cors",        "4.0.0",    "Cross-origin request handling for web/mobile"],
        ["Supabase",           "supabase-py",       "2.0+",     "Python client for Supabase sync writes"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(2.8), Cm(1.8), Cm(6.7)])
    T.caption(doc, "Table 5.1 — Backend Technology Stack")

    T.subsection_h(doc, "5.1.2", "Web Frontend Technology Stack")
    rows = [
        ["Language",        "JavaScript (ES2022+)",  "—",     "Primary frontend language"],
        ["UI Framework",    "React",                 "18.2",  "Component-based UI with concurrent rendering"],
        ["Build Tool",      "Vite",                  "4.4",   "Fast dev server with native ESM HMR"],
        ["UI Components",   "Ant Design",            "5.1",   "Enterprise component library"],
        ["State (global)",  "Redux Toolkit",         "1.9",   "Global UI state management"],
        ["State (server)",  "RTK Query",             "1.9",   "Server state caching and synchronization"],
        ["HTTP Client",     "axios",                 "1.3",   "API request handling with interceptors"],
        ["Charts",          "Chart.js",              "3.9",   "Analytics data visualization"],
        ["Chart Wrapper",   "react-chartjs-2",       "5.2",   "React bindings for Chart.js"],
        ["Icons",           "Ant Design Icons",      "5.0",   "Comprehensive icon library"],
        ["Routing",         "react-router-dom",      "6.4",   "Client-side routing with data router API"],
        ["Real-time",       "socket.io-client",      "4.5",   "WebSocket client for live event updates"],
        ["Date Handling",   "dayjs",                 "1.11",  "Lightweight date manipulation library"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(3.5), Cm(1.5), Cm(6.3)])
    T.caption(doc, "Table 5.2 — Web Frontend Technology Stack")

    T.subsection_h(doc, "5.1.3", "Mobile Technology Stack")
    rows = [
        ["Language",         "JavaScript (React Native)", "—",      "Cross-platform mobile language"],
        ["Framework",        "React Native",              "0.81.5", "Native mobile UI from JS components"],
        ["Build Platform",   "Expo",                      "SDK 54", "Managed native build and OTA updates"],
        ["Navigation",       "React Navigation",          "6.0",    "Stack and tab navigators"],
        ["Real-time Sync",   "@supabase/supabase-js",     "2.104",  "WebSocket real-time subscriptions"],
        ["Push Notif.",      "expo-notifications",        "0.32",   "FCM push notification reception"],
        ["Charts",           "react-native-chart-kit",    "6.12",   "Mobile-optimized chart components"],
        ["Icons",            "@expo/vector-icons",        "—",      "Ionicons and other icon sets"],
        ["Local Storage",    "AsyncStorage",              "1.21",   "Offline queue and preferences storage"],
        ["Secure Storage",   "expo-secure-store",         "13.0",   "Encrypted token and credential storage"],
        ["Connectivity",     "@react-native-netinfo",     "11.3",   "Network state monitoring"],
        ["HTTP Client",      "axios",                     "1.3",    "API communication with interceptors"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(3.5), Cm(1.8), Cm(6.0)])
    T.caption(doc, "Table 5.3 — Mobile Technology Stack")

    # ── 5.2 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "5.2", "Backend Implementation")

    T.subsection_h(doc, "5.2.1", "Directory Structure")
    T.body(doc,
        "The backend follows a structured directory layout that separates concerns "
        "across five primary directories. The app/ directory contains all application "
        "code organized into models, routes, services, ai, and utils subdirectories. "
        "The tests/ directory mirrors the routes structure with one test file per "
        "Blueprint. The models/ directory (at the project root) contains the trained "
        "XGBoost model pickle file. Figure 5.1 illustrates the complete structure.")

    T.caption(doc, "Figure 5.1 — Backend Directory Structure")

    T.body(doc,
        "The structure separates three layers of backend logic. Route handlers in "
        "app/routes/ are kept thin: they validate input, call service functions, and "
        "format responses. They contain no business logic. Service functions in "
        "app/services/ contain all business logic and orchestration: they call AI "
        "engines, interact with models, and coordinate multi-step operations. AI "
        "engines in app/ai/ are pure computation modules: they accept structured "
        "input, apply their specific algorithm or API, and return a result. This "
        "three-layer separation makes each component independently testable and "
        "replaceable.")

    T.subsection_h(doc, "5.2.2", "Application Factory and Configuration")
    T.body(doc,
        "The create_app() factory in app/__init__.py performs five initialization "
        "steps in a fixed order. First, it loads configuration from environment "
        "variables via python-dotenv, supporting separate .env files for development, "
        "testing, and production. Second, it initializes SQLAlchemy with the database "
        "URI, configures connection pooling (pool_size=10, max_overflow=20), and "
        "registers the before_insert event listener on the Lead model. Third, it "
        "initializes flask-bcrypt, PyJWT, and flask-cors with the allowed origins "
        "list. Fourth, it registers all eleven Blueprints with their URL prefixes. "
        "Fifth, it initializes the Celery instance with the Redis broker URL and "
        "configures the four task queues with their priority settings.")

    T.subsection_h(doc, "5.2.3", "Authentication Implementation")
    T.body(doc,
        "The authentication Blueprint (app/routes/auth.py) exposes four endpoints: "
        "POST /register, POST /login, GET /profile, and PUT /profile. The register "
        "endpoint validates input with a marshmallow schema, checks email uniqueness "
        "with a database query, hashes the password with bcrypt, and persists the "
        "User record in a dedicated database transaction. After the record is committed, "
        "a separate step generates a six-digit OTP code, stores it against the user "
        "row with a 10-minute expiry, and attempts to deliver it by email. If delivery "
        "succeeds the endpoint returns HTTP 201 with status 'verify_email', and the "
        "account becomes active only after the user submits the correct code to "
        "POST /verify-email. If email delivery fails the endpoint still returns HTTP "
        "201 but with status 'pending_approval', and an administrator must manually "
        "activate the account. The login endpoint checks email_verified before issuing "
        "a token, returning HTTP 401 with a descriptive message if verification is "
        "still pending. Once verified, credentials are confirmed with bcrypt's "
        "check_password_hash (constant-time comparison), and PyJWT's encode() returns "
        "the signed token in the response body.")

    T.body(doc,
        "A custom @jwt_required decorator is applied to every protected endpoint. "
        "It extracts the Bearer token from the Authorization header, decodes and "
        "verifies it with PyJWT (raising DecodeError for invalid signatures and "
        "ExpiredSignatureError for expired tokens), fetches the full user record from "
        "the database to ensure the account is still active, and stores the user "
        "object in Flask's g context for downstream handler access. The @require_role "
        "decorator wraps @jwt_required and additionally checks the user's role against "
        "the required minimum, returning 403 if insufficient.")

    T.subsection_h(doc, "5.2.4", "Lead Visibility Filter Implementation")
    T.body(doc,
        "The leads Blueprint (app/routes/leads.py) applies a role-scoped base query "
        "at the start of every GET handler before any additional filters are applied. "
        "For admin role, the base query is Lead.query with no additional filter. "
        "For manager role, the base query resolves the manager's company name and "
        "collects all user IDs sharing that company, then filters to leads whose "
        "collected_by is in that set (company-scoped visibility). For user role, "
        "the base query filters strictly to leads where collected_by equals the "
        "current user's ID. All subsequent filter parameters — status, score range, "
        "source, date range — are appended to this role-scoped base query as "
        "additional .filter() clauses, ensuring visibility isolation is maintained "
        "regardless of which filters are applied.")

    # ── 5.3 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "5.3", "AI Engine Implementation")

    T.subsection_h(doc, "5.3.1", "Feature Extraction")
    T.body(doc,
        "The ML engine (app/ai/ml_engine.py) implements a feature extraction function "
        "that accepts a raw lead dictionary and returns a 37-element NumPy array "
        "suitable for XGBoost inference. The function handles missing fields "
        "gracefully by substituting pre-defined default values rather than raising "
        "exceptions, ensuring that leads with sparse data are scored (conservatively) "
        "rather than rejected due to missing feature values.")

    headers = ["Category", "Count", "Features Included"]
    rows = [
        ["Contact Completeness", "8",
         "has_email, has_phone, has_linkedin, has_company, has_position, "
         "has_country, has_industry, has_website"],
        ["Firmographic Signals", "12",
         "country_tier (1–3), industry_score (0–1), company_name_length, "
         "domain_tld_score, website_path_depth, is_corporate_domain, "
         "company_word_count, has_numeric_in_company, domain_length, "
         "tld_is_country_code, industry_is_tech, industry_is_finance"],
        ["Behavioral / Intent", "9",
         "buying_intent_flag, source_quality_weight (0–1 per API), "
         "data_points_count, email_verified_flag, intent_confidence, "
         "has_buying_intent_text, source_is_premium, "
         "collection_recency_days, has_direct_dial"],
        ["Derived Composites", "8",
         "contact_richness_index (weighted sum), firmographic_completeness, "
         "cross_field_consistency, name_quality_score, position_seniority_score, "
         "email_domain_score, linkedin_completeness_score, overall_data_quality"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.5), Cm(1.3), Cm(9.5)])
    T.caption(doc, "Table 5.4 — XGBoost Feature Categories (37 Total Features)")

    T.subsection_h(doc, "5.3.2", "Model Loading and Inference")
    T.body(doc,
        "The XGBoost model (xgb_v5.pkl) is loaded once at application startup using "
        "Python's pickle module and cached in memory as a module-level variable. This "
        "avoids repeated disk I/O on every qualification request, which would add "
        "50–200ms of latency per inference on spinning disk storage. The model's "
        "predict_proba() method returns a two-class probability vector; the positive "
        "class probability (index 1) is multiplied by 100 to produce the base score "
        "in the [0, 100] range. The model handles missing values natively through "
        "XGBoost's built-in sparse-aware split finding, so no imputation is needed "
        "in the feature extraction pipeline.")

    T.subsection_h(doc, "5.3.3", "Cascade Orchestration")
    T.body(doc,
        "The cascade orchestrator (app/services/ai_service.py) implements the "
        "four-layer pipeline as a sequential function chain with explicit fallthrough "
        "logic. Each layer is called within a try/except block that catches all "
        "exceptions and logs them before triggering fallthrough to the next layer. "
        "The orchestrator maintains a qualification_log dictionary that records which "
        "layers were executed, which were skipped, and what score each layer produced. "
        "This log is stored in the lead's data_points JSON field for transparency and "
        "debugging.")

    T.body(doc,
        "The Gemini integration (app/ai/gemini_engine.py) constructs a structured "
        "prompt that provides the model with the lead's key fields and asks for a "
        "JSON-formatted response containing a quality_score (0–100), a confidence "
        "level ('high'/'medium'/'low'), and a brief justification string. The prompt "
        "explicitly instructs Gemini to focus on B2B sales qualification criteria "
        "and to consider role seniority, company relevance, and contact quality. "
        "The returned quality_score is blended with the XGBoost base score using a "
        "weighted average (60% XGBoost, 40% Gemini) to produce the final score.")

    T.subsection_h(doc, "5.3.4", "ML Retraining Pipeline")
    T.body(doc,
        "The retraining pipeline is triggered by a Celery task (tasks/ml_retrain.py) "
        "that is queued to the 'ml' queue when the count of new, unprocessed "
        "LeadOutcome records since the last training run exceeds a configurable "
        "threshold (default: 20 new labels). The task fetches all leads with "
        "associated outcomes, extracts the same 37-feature vector for each, and "
        "trains a new XGBoost model using 5-fold cross-validation. If the new model's "
        "cross-validation accuracy exceeds the current deployed model's accuracy by "
        "at least 2 percentage points, the new model is saved as the active model "
        "file and loaded into memory, replacing the previous version without a server "
        "restart. The training run metrics (accuracy, feature importances, training "
        "set size) are logged to the database for admin review.")

    # ── 5.4 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "5.4", "Web Frontend Implementation")

    T.subsection_h(doc, "5.4.1", "API Client and Interceptors")
    T.body(doc,
        "All API communication flows through a single axios instance configured in "
        "src/api/client.js. Two interceptors are registered at application startup. "
        "The request interceptor reads the JWT token from localStorage and attaches "
        "it as the Authorization: Bearer header on every outbound request, eliminating "
        "the need for individual components to handle token attachment. The response "
        "interceptor catches 401 Unauthorized responses, clears the stored token, "
        "dispatches a Redux logout action to clear the auth state, and redirects "
        "the user to the login page — providing automatic session expiry handling "
        "without any per-component logic.")

    T.subsection_h(doc, "5.4.2", "Lead List with Score Visualization")
    T.body(doc,
        "The LeadsPage component renders an Ant Design Table with server-side "
        "pagination. The score column uses a custom render function that displays "
        "a colored circular badge: green for Hot scores (>=80), amber for Warm "
        "(>=60), blue for Cold (>=30), and slate for Unqualified (<30). Adjacent "
        "to the score badge, a tier Tag component shows the text label (HOT / WARM "
        "/ COLD / NEW) with a matching background color. The filter panel above the "
        "table provides Score Range (a two-handle Ant Design Slider), Status "
        "(multi-select Select), Source (multi-select Select), Industry (text search), "
        "Country (Select), and Date Range (RangePicker). All filter values are stored "
        "in Redux state, allowing them to persist across navigation and be shared "
        "with the CSV export endpoint.")

    T.subsection_h(doc, "5.4.3", "Analytics Dashboard")
    T.body(doc,
        "The AnalyticsPage component fetches aggregated metrics from the "
        "/api/analytics endpoint and renders them using four Chart.js charts wrapped "
        "in react-chartjs-2 components. The Line chart uses the 'time' scale type "
        "with Day.js as the adapter, rendering daily lead collection counts over "
        "the selected date range with a smooth bezier curve and filled gradient area. "
        "The Pie chart renders score tier distribution with a legend listing the "
        "exact count and percentage for each tier. The Bar chart compares lead "
        "volume by source using horizontal bars for better readability with long "
        "source names. The Doughnut chart shows lead status distribution with a "
        "center text overlay displaying the total lead count.")

    T.subsection_h(doc, "5.4.4", "AI Collection Interface")
    T.body(doc,
        "The AI Collection page provides a full-width Ant Design TextArea for "
        "entering natural language queries, a CheckboxGroup for source selection, "
        "and a Collect button that triggers a POST to /api/ai/collect. The collection "
        "endpoint returns immediately with a task ID, and the frontend polls "
        "GET /api/ai/collect/status/{task_id} every two seconds using RTK Query's "
        "polling feature. As the task progresses, a real-time progress panel updates "
        "with counts of candidates found, passed the anti-junk filter, and qualified "
        "per tier. On completion, a results summary card appears with a 'View New "
        "Leads' button that navigates to the leads list pre-filtered to leads "
        "collected in the last hour.")

    T.subsection_h(doc, "5.4.5", "Dark and Light Mode")
    T.body(doc,
        "Theme switching is implemented through an Ant Design ConfigProvider at the "
        "application root that receives a dynamically computed theme object from the "
        "Redux theme state. The theme object maps all Ant Design design tokens — "
        "colorPrimary, colorBgContainer, colorText, colorBorder, and thirty-two "
        "others — to the active theme's specific color values. A useEffect hook in "
        "the root App component also sets a data-theme attribute on the HTML element, "
        "enabling custom CSS selectors for components that cannot be styled through "
        "Ant Design tokens alone. Theme preference is written to localStorage on "
        "every change and read back on initial load, before the first render, "
        "preventing the flash-of-wrong-theme that occurs when theme is set after mount.")

    # ── 5.5 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "5.5", "Mobile Application Implementation")

    T.subsection_h(doc, "5.5.1", "Directory Structure")
    T.body(doc,
        "The mobile application source code is organized under the mobile/src/ "
        "directory into six subdirectories. The screens/ directory contains one "
        "file per full-screen view. The components/ directory contains reusable "
        "UI components shared across screens. The navigation/ directory contains "
        "the AppNavigator which wires up all screen and tab configurations. The "
        "context/ directory contains the AuthContext and ThemeContext providers. "
        "The services/ directory contains the API client, Supabase client setup, "
        "and offline queue manager. The hooks/ directory contains custom React hooks "
        "for data fetching and analytics. Figure 5.2 illustrates the structure.")

    T.caption(doc, "Figure 5.2 — Mobile Application Directory Structure")

    T.subsection_h(doc, "5.5.2", "LeadCard Component")
    T.body(doc,
        "The LeadCard component (mobile/src/components/LeadCard.js) is the primary "
        "visual unit of the leads list. It renders as a TouchableOpacity with a "
        "4-pixel left border whose color is derived from the lead's qualification "
        "score: COLORS.green (#1a8c4e) for Hot, COLORS.amber (#c9a02c) for Warm, "
        "#3b82f6 (blue) for Cold, and #94a3b8 (slate) for Unqualified. The card "
        "body contains three zones: left (40x40 circular avatar with score-colored "
        "background showing the lead's name initial), center (name, company/position, "
        "and a tag row with tier pill, industry badge, and country label), and right "
        "(40x40 circular score badge with score-colored border and the numeric score, "
        "plus a StatusBadge component below it). The bottom of the card displays "
        "contact information chips for email (with a green checkmark if verified), "
        "phone, and a High Intent flame chip if buying_intent equals 'high'.")

    T.subsection_h(doc, "5.5.3", "QuickLabelBar Component")
    T.body(doc,
        "The QuickLabelBar component renders as a fixed horizontal row of four "
        "TouchableOpacity chips at the bottom of the LeadDetailScreen. The four "
        "outcome options are: Converted (green, checkmark icon), Replied (blue, "
        "mail icon), No Reply (gray, mail-unread icon), and Not a Fit (red, "
        "close-circle icon). When a chip is tapped, it immediately shows an active "
        "visual state (filled background color instead of transparent), triggers "
        "haptic feedback via expo-haptics, and dispatches an API call to "
        "POST /api/leads/{id}/label. If the device is offline, the action is "
        "serialized into the AsyncStorage offline queue instead of making an "
        "immediate API call. A loading spinner replaces the selected chip's icon "
        "while the API call is in flight, and a success animation confirms "
        "completion on resolution.")

    T.subsection_h(doc, "5.5.4", "Authentication Context and Token Management")
    T.body(doc,
        "The AuthContext (mobile/src/context/AuthContext.js) provides login, logout, "
        "and token refresh functions to all child components through React context. "
        "On application start, the context reads the stored JWT from "
        "expo-secure-store (which uses the device's native secure keychain, not "
        "plaintext AsyncStorage) and validates the token's expiry timestamp before "
        "considering the user authenticated. The axios instance in services/api.js "
        "has a request interceptor that reads the token from the secure store on "
        "every request and a response interceptor that handles 401 responses by "
        "triggering the AuthContext logout function, clearing the token and navigating "
        "the user to the Login screen.")

    # ── 5.6 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "5.6", "Database Implementation")

    T.body(doc,
        "The MySQL database schema is created and maintained through SQLAlchemy model "
        "definitions rather than manual SQL scripts. Running db.create_all() in the "
        "application context generates all tables from the model classes with the "
        "correct column types, constraints, and indexes. The following database-level "
        "optimizations are applied beyond the basic schema:")

    T.bullet(doc,
        "Compound index on leads(collected_by, created_at DESC): Serves the most "
        "common query pattern — fetching a specific user's leads sorted by recency — "
        "without a full table scan. This index reduces query time from O(n) to "
        "O(log n) as the leads table grows.",
        bold_prefix="Leads visibility index:")

    T.bullet(doc,
        "Index on seen_contacts(email): The anti-junk engine checks this table on "
        "every collected candidate. Without an index, each check requires a full "
        "table scan. The B-tree index on email reduces duplicate detection from "
        "O(n) to O(log n), supporting hundreds of checks per collection session "
        "without performance degradation.",
        bold_prefix="SeenContacts deduplication index:")

    T.bullet(doc,
        "Compound index on lead_activities(lead_id, created_at): Serves the activity "
        "timeline query on the lead detail page, which fetches all activities for a "
        "specific lead ordered by time.",
        bold_prefix="Activity timeline index:")

    T.bullet(doc,
        "MySQL 8.0's native JSON column type is used for leads.data_points and "
        "data_sources.config. The JSON type provides server-side JSON path queries "
        "(using ->> operator), JSON schema validation, and automatic syntax checking "
        "on insert, while storing data in an optimized binary format that is more "
        "space-efficient than TEXT columns storing JSON strings.",
        bold_prefix="JSON column type:")

    T.bullet(doc,
        "All tables use the utf8mb4 character set with the utf8mb4_unicode_ci "
        "collation. This supports the full Unicode range including emoji, Arabic, "
        "Chinese, and other non-ASCII characters in company names, contact names, "
        "and notes fields — critical for a system targeting international B2B markets.",
        bold_prefix="Unicode support:")

    # ── 5.7 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "5.7", "API Endpoints")

    T.body(doc,
        "The leads Blueprint provides eleven endpoints covering the complete "
        "lead lifecycle. Table 5.6 documents each endpoint with its HTTP method, "
        "path, authentication requirements, and description.")

    headers = ["Method", "Endpoint", "Auth / Role", "Description"]
    rows = [
        ["GET",    "/api/leads",              "JWT / Any",      "List leads — paginated, filtered, role-scoped visibility"],
        ["POST",   "/api/leads",              "JWT / Any",      "Create a new lead manually with validated fields"],
        ["GET",    "/api/leads/{id}",         "JWT / Any",      "Retrieve single lead with full field set and activities"],
        ["PUT",    "/api/leads/{id}",         "JWT / Any",      "Update lead fields; logs changes to LeadActivities"],
        ["DELETE", "/api/leads/{id}",         "JWT / Manager+", "Delete lead; logs deletion to LeadActivities"],
        ["GET",    "/api/leads/search",       "JWT / Any",      "Full-text search across name, email, company, position"],
        ["GET",    "/api/leads/export",       "JWT / Any",      "Export filtered leads as CSV file download"],
        ["GET",    "/api/leads/stats",        "JWT / Any",      "Aggregate stats for the caller's role-scoped lead set"],
        ["POST",   "/api/leads/{id}/label",   "JWT / Any",      "Submit QuickLabelBar outcome; creates LeadOutcome record"],
        ["POST",   "/api/leads/{id}/qualify", "JWT / Any",      "Re-run full AI cascade on existing lead; updates score"],
        ["GET",    "/api/leads/{id}/activities","JWT / Any",    "Retrieve full activity timeline for a lead in time order"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(1.5), Cm(4.5), Cm(2.8), Cm(5.5)])
    T.caption(doc, "Table 5.6 — Lead Management API Endpoints")

    T.body(doc,
        "The AI Blueprint provides three endpoints. POST /api/ai/collect accepts "
        "a natural language query and source list, enqueues the collection task to "
        "Celery, and returns a task ID immediately. GET /api/ai/collect/status/{id} "
        "returns the task's current state and progress counters. POST "
        "/api/ai/train triggers an immediate ML retraining job for administrators.")

    # ── 5.8 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "5.8", "Real-Time Synchronization")

    T.body(doc,
        "The real-time synchronization pipeline bridges the MySQL primary store "
        "with Supabase's PostgreSQL instance, enabling mobile clients to receive "
        "instant updates without polling. The pipeline operates in four stages.")

    T.body(doc,
        "Stage 1 — Change Detection: SQLAlchemy after_insert and after_update event "
        "listeners on the Lead and User models detect every write operation at the "
        "ORM layer. When a change is detected, the listener creates a SyncLog record "
        "with entity_type, entity_id, action, and status='pending', then enqueues "
        "a Celery sync task to the 'critical' queue.")

    T.body(doc,
        "Stage 2 — Supabase Write: The Celery sync task (tasks/sync_task.py) fetches "
        "the full entity record from MySQL, serializes it to a JSON-compatible "
        "dictionary using the model's to_dict() method, and writes it to the "
        "corresponding Supabase table using the supabase-py client's upsert() method "
        "(which inserts a new row or updates the existing row based on the UUID "
        "primary key). On success, the SyncLog record's status is updated to "
        "'success'. On failure, status is set to 'failed' and retry_count is "
        "incremented; the task is re-queued with exponential backoff up to three "
        "retry attempts.")

    T.body(doc,
        "Stage 3 — Mobile Event Reception: The mobile app's Supabase client "
        "maintains a persistent WebSocket channel subscription to the leads table "
        "with a row-level filter matching the current user's collected_by ID (or "
        "no filter for manager/admin roles). When Supabase's Realtime service "
        "broadcasts a change event from Stage 2, the mobile client's channel "
        "callback fires immediately, invalidating the affected React Query cache "
        "entry. React Query then automatically re-fetches the updated data in the "
        "background and updates the UI.")

    T.body(doc,
        "Stage 4 — Offline Queue Replay: When the mobile app detects network "
        "reconnection through the NetInfo event listener, the offline queue manager "
        "(services/offlineQueue.js) reads all pending actions from AsyncStorage, "
        "sorted by their queued timestamp. Each action is dispatched sequentially "
        "through the API client. If an action succeeds, it is removed from the "
        "queue. If it fails with a 409 Conflict (optimistic lock mismatch), the "
        "user is shown a conflict notification with the option to view the current "
        "server state. All other failures are logged and the action is retried "
        "on the next reconnection event.")

    T.body(doc,
        "Push notifications (Stage 2b) are dispatched in parallel with the Supabase "
        "write for certain event types: new leads being assigned to a specific user, "
        "lead status changing to 'qualified', and batch collection completing. The "
        "notification service (app/services/notification_service.py) uses the "
        "firebase-admin SDK to send FCM data messages (not display notifications) "
        "to all registered device tokens for the target user. Data messages allow "
        "the mobile app to handle the notification payload programmatically, "
        "updating the local cache and showing a native notification with custom "
        "content — including the lead's name, score, and tier.")
