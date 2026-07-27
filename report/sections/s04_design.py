"""
s04_design.py — Chapter 4: System Design and Architecture
Target: 16-18 pages
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import theme as T
from docx.shared import Cm


def build(doc):
    T.chapter_title(doc, 4, "System Design and Architecture")

    T.body(doc,
        "System design translates the requirements established in Chapter 3 into a "
        "concrete technical blueprint for implementation. This chapter presents the "
        "complete architectural design of OrionLead AI across all layers: the overall "
        "three-tier system architecture, the Flask backend Blueprint structure, the "
        "four-layer AI qualification engine, the web and mobile frontend architectures, "
        "the full relational database schema with entity-relationship diagram, the "
        "security architecture, and the external API integration design.")

    # ── 4.1 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "4.1", "Overall System Architecture")

    T.body(doc,
        "OrionLead AI follows a three-tier architecture — Presentation Layer, "
        "Application Logic Layer, and Data Layer — with a fourth cross-cutting AI "
        "Processing Layer that operates within the Application Logic tier. This "
        "separation of concerns ensures that each layer can evolve independently, "
        "be scaled horizontally without affecting other layers, and be tested in "
        "isolation. Figure 4.1 illustrates the complete architecture.")

    T.caption(doc, "Figure 4.1 — Overall Three-Tier System Architecture")

    T.subsection_h(doc, "4.1.1", "Presentation Layer")
    T.body(doc,
        "The Presentation Layer consists of two independent client applications that "
        "serve different user contexts. The React 18 web application, built with Vite "
        "and Ant Design 5, serves office-based users who need rich data management, "
        "bulk operations, analytics, and administrative functions on large desktop "
        "screens. The React Native mobile application, built with Expo SDK 54, serves "
        "field sales professionals who need quick lead access, outcome labeling, and "
        "push notifications on smartphones and tablets.")

    T.body(doc,
        "Both clients communicate with the Application Logic Layer exclusively through "
        "the REST API over HTTPS, using JWT Bearer tokens in the Authorization header "
        "for authentication. The mobile client additionally maintains a persistent "
        "real-time subscription to Supabase for instant data updates without polling.")

    T.subsection_h(doc, "4.1.2", "Application Logic Layer")
    T.body(doc,
        "The Application Logic Layer is the Flask 2.3.2 RESTful API server running on "
        "Python 3.11+. It is organized into eleven Blueprint modules, each responsible "
        "for a specific functional domain. It hosts the complete business logic: "
        "authentication, role-based access control, lead lifecycle management, AI "
        "qualification orchestration, multi-source collection, analytics aggregation, "
        "synchronization, and notification dispatch.")

    T.body(doc,
        "Background and long-running tasks are offloaded from the request-response "
        "cycle to Celery 5.3.1 workers, which consume jobs from a Redis 4.5.5 message "
        "broker. This ensures that operations such as batch lead collection, ML model "
        "retraining, bulk CSV export, and large-scale email verification never block "
        "API response threads and cannot cause user-facing timeouts.")

    T.subsection_h(doc, "4.1.3", "Data Layer")
    T.body(doc,
        "The Data Layer consists of three storage systems with distinct roles. MySQL 8.0 "
        "serves as the primary authoritative data store for all leads, users, activities, "
        "outcomes, and configuration data, providing ACID-compliant transactions and "
        "relational integrity through foreign key constraints. Redis provides both the "
        "Celery task queue and a response cache for frequently accessed analytics "
        "aggregations, reducing repeated computation on hot endpoints. Supabase acts as "
        "a real-time PostgreSQL bridge, receiving mirrored writes from MySQL via the "
        "sync service and broadcasting change events to subscribing mobile clients "
        "through its WebSocket-based Realtime protocol.")

    # ── 4.2 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "4.2", "Backend Architecture")

    T.body(doc,
        "The Flask backend uses the Application Factory pattern: a create_app() "
        "function in app/__init__.py receives a configuration object, initializes all "
        "extensions (SQLAlchemy, Bcrypt, JWT, Celery, CORS), registers all Blueprint "
        "modules, attaches SQLAlchemy event listeners, and returns the configured "
        "application instance. This pattern enables independent test configurations "
        "and avoids circular import issues in large Blueprint-based applications.")

    T.body(doc,
        "Eleven Blueprint modules partition the API surface. Each Blueprint is defined "
        "in its own file under app/routes/, registered with a URL prefix, and "
        "responsible for a clearly bounded functional domain. Table 4.1 lists all "
        "Blueprints with their route prefixes and responsibilities.")

    headers = ["Blueprint", "URL Prefix", "Responsibility"]
    rows = [
        ["auth_bp",          "/api/auth",          "Registration, login, token refresh, profile management"],
        ["leads_bp",         "/api/leads",         "Lead CRUD, search, export, stats, labeling, re-qualification"],
        ["ai_bp",            "/api/ai",            "Collection trigger, cascade qualification, ML training"],
        ["users_bp",         "/api/users",         "User account management — admin only"],
        ["analytics_bp",     "/api/analytics",     "Dashboard metrics aggregation by role scope"],
        ["sources_bp",       "/api/sources",       "Data source configuration and API key management"],
        ["sync_bp",          "/api/sync",          "Mobile synchronization endpoints and offline queue replay"],
        ["notifications_bp", "/api/notifications", "FCM device token registration and push dispatch"],
        ["categories_bp",    "/api/categories",    "Lead classification category management"],
        ["health_bp",        "/api/health",        "System health check — no auth required"],
        ["docs_bp",          "/api/docs",          "Flasgger Swagger UI — interactive API documentation"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.2), Cm(3.2), Cm(7.9)])
    T.caption(doc, "Table 4.1 — API Blueprints and Route Prefixes")

    T.subsection_h(doc, "4.2.1", "SQLAlchemy Event Listener — Lead Visibility")
    T.body(doc,
        "A critical architectural decision is the auto-assignment of the collected_by "
        "field on Lead records. Rather than relying on individual route handlers to "
        "remember to set this field, a SQLAlchemy before_insert event listener is "
        "attached to the Lead model at application startup. Every time a Lead is "
        "inserted into the database, the listener fires and sets collected_by to the "
        "currently authenticated user's ID if it has not already been explicitly set. "
        "This makes lead ownership assignment automatic, consistent, and impossible "
        "to accidentally bypass.")

    T.body(doc,
        "On the query side, every GET request to /api/leads applies a visibility "
        "filter based on the authenticated user's role: Admin role receives unfiltered "
        "access to all leads; Manager role receives leads belonging to any user sharing "
        "the same company name (company-scoped visibility); User role receives only "
        "leads where collected_by equals their own user ID. All subsequent filter "
        "parameters — status, score range, source, date range — are appended to this "
        "role-scoped base query, ensuring visibility isolation is maintained regardless "
        "of which filters are applied.")

    T.subsection_h(doc, "4.2.2", "Background Task Architecture")
    T.body(doc,
        "Celery workers are configured with Redis as both broker and result backend. "
        "Four task queues are defined with different priority levels: 'critical' for "
        "real-time sync events, 'default' for collection and qualification jobs, "
        "'analytics' for report generation, and 'ml' for model retraining. This "
        "queue separation ensures that a large batch collection job cannot delay "
        "real-time sync events, which must propagate to mobile clients within seconds.")

    # ── 4.3 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "4.3", "AI Qualification Engine")

    T.body(doc,
        "The AI qualification engine is the technical centerpiece of OrionLead AI. "
        "It implements a four-layer cascade architecture that processes every lead "
        "candidate through sequentially more capable evaluation layers, short-circuiting "
        "at the earliest layer that can make a confident qualification decision. "
        "Figure 4.2 illustrates the complete cascade flow.")

    T.caption(doc, "Figure 4.2 — Four-Layer AI Qualification Cascade")

    T.subsection_h(doc, "4.3.1", "Layer 1 — Anti-Junk Rule Engine")
    T.body(doc,
        "The anti-junk engine applies twelve deterministic hard-reject rules to every "
        "candidate before any machine learning processing occurs. Rules are evaluated "
        "in order of computational cost (cheapest first) and short-circuit on the first "
        "match. A candidate that triggers any rule receives a final score of 0, is "
        "classified as Unqualified, and is written to the SeenContacts table with the "
        "rejection reason logged — preventing the same contact from being re-collected "
        "in future sessions. The twelve rules are:")

    rules = [
        ("Rule 1",  "Generic name patterns",       "Name contains 'test', 'unknown', 'n/a', 'admin', 'user', or similar placeholder values"),
        ("Rule 2",  "Single token name",            "Name consists of a single word with fewer than 3 characters, or is purely numeric"),
        ("Rule 3",  "Personal email domain",        "Email domain is a known personal provider: gmail, yahoo, hotmail, outlook, live, icloud, protonmail, etc."),
        ("Rule 4",  "Invalid email format",         "Email does not match RFC 5322 format validated by regex (local@domain.tld structure)"),
        ("Rule 5",  "Repeated digit phone",         "Phone number contains 7+ consecutive identical digits (e.g., 0000000000)"),
        ("Rule 6",  "Too-short phone number",       "Phone number has fewer than 7 digits after stripping all formatting characters"),
        ("Rule 7",  "No identification fields",     "Both email and phone are absent and LinkedIn URL is also absent — no way to contact"),
        ("Rule 8",  "Bot/scraper name pattern",     "Name matches known bot or scraper patterns: all-caps random strings, UUID-like strings"),
        ("Rule 9",  "Placeholder position",         "Job title/position contains placeholder values: 'N/A', 'None', 'Employee', 'Staff'"),
        ("Rule 10", "Malformed website URL",        "Website URL is present but cannot be parsed as a valid HTTP/HTTPS URL"),
        ("Rule 11", "Invalid LinkedIn URL pattern", "LinkedIn URL is present but does not match the expected linkedin.com/in/ or linkedin.com/company/ pattern"),
        ("Rule 12", "Prior junk flag in metadata", "data_points JSON field contains a junk_flag=true marker set by a previous collection session"),
    ]
    T.styled_table(doc,
                   ["Rule", "Name", "Rejection Criterion"],
                   rules,
                   col_widths=[Cm(1.5), Cm(3.5), Cm(9.3)])
    T.caption(doc, "Table 4.2 (referenced as Table 5.5 in Ch.5) — Anti-Junk Rule Descriptions")

    T.subsection_h(doc, "4.3.2", "Layer 2 — XGBoost Machine Learning Model")
    T.body(doc,
        "Candidates passing Layer 1 are scored by the XGBoost model (xgb_v5), a "
        "gradient-boosted decision tree ensemble trained on 71 human-labeled leads "
        "with verified real-world outcomes. The model accepts a 37-dimensional feature "
        "vector extracted from the candidate's raw data and produces a continuous "
        "score in the range [0, 100] representing the model's confidence that the "
        "candidate is a qualified B2B lead.")

    T.body(doc,
        "The 37 features are organized into four categories. Contact completeness "
        "features (8 features) encode the presence or absence of each contact field "
        "as binary indicators: has_email, has_phone, has_linkedin, has_company, "
        "has_position, has_country, has_industry, and has_website. Firmographic "
        "features (12 features) encode company-level quality signals: country_tier "
        "(1=tier-1 market, 2=emerging, 3=other), industry_score (a pre-computed "
        "relevance weight by industry vertical), company_name_length, "
        "domain_tld_score (commercial TLDs score higher than free ones), and "
        "website_path_depth. Behavioral and intent features (9 features) include: "
        "buying_intent_flag, source_quality_weight (different APIs have different "
        "average data quality), data_points_count, and email_verified_flag. "
        "Derived composite features (8 features) include: contact_richness_index "
        "(weighted sum of contact completeness flags), firmographic_completeness, "
        "and cross_field_consistency score.")

    T.body(doc,
        "The model was trained using scikit-learn's cross_val_score with 5-fold "
        "stratified splits to preserve class proportions across folds, achieving "
        "76% cross-validation accuracy. Feature importance analysis reveals that "
        "has_email, email_verified_flag, source_quality_weight, has_company, "
        "and buying_intent_flag are the five most predictive features, collectively "
        "accounting for approximately 58% of the model's predictive power.")

    T.subsection_h(doc, "4.3.3", "Layer 3 — Google Gemini LLM")
    T.body(doc,
        "Candidates that receive a Layer 2 score in the uncertain range (approximately "
        "30–75, where the model is less confident) are passed to Google Gemini for "
        "contextual quality assessment. The Gemini integration constructs a structured "
        "prompt containing the candidate's name, position, company, industry, country, "
        "email domain, and LinkedIn URL, then asks the model to evaluate four dimensions: "
        "role seniority level (1–5 scale), company relevance to B2B software sales "
        "(1–5 scale), contact quality signals (email domain professionalism, LinkedIn "
        "completeness), and any negative signals (generic role titles, mismatched "
        "industry). Gemini returns a structured JSON response containing a quality "
        "multiplier (0.5–1.5) that is applied to the Layer 2 base score.")

    T.body(doc,
        "The Gemini integration includes a configurable timeout (default 6 seconds) "
        "and structured error handling that catches API unavailability, rate limit "
        "responses, and malformed JSON outputs. Any failure in Layer 3 triggers "
        "automatic fallthrough to Layer 4 rather than causing the qualification "
        "pipeline to fail.")

    T.subsection_h(doc, "4.3.4", "Layer 4 — Groq Fallback LLM")
    T.body(doc,
        "Groq provides ultra-fast LLM inference (typically <1 second per call) using "
        "Meta's Llama model series. It serves as the fallback for Layer 3 when Gemini "
        "is unavailable, rate-limited, or returns an error. The Groq integration uses "
        "an identical prompt structure to the Gemini integration, ensuring consistent "
        "quality assessment semantics across both providers. If both Layer 3 and "
        "Layer 4 are unavailable, the system uses the Layer 2 XGBoost score directly "
        "as the final qualification score without LLM adjustment, with a flag in the "
        "lead's data_points JSON noting that LLM assessment was skipped.")

    T.subsection_h(doc, "4.3.5", "Score Tier Assignment")
    T.body(doc,
        "After the cascade completes, the final score is mapped to one of four "
        "qualification tiers using fixed thresholds: Hot (score >= 80) represents "
        "leads with strong contact information, verified business email, relevant "
        "industry, and senior decision-making role signals; Warm (60 <= score < 80) "
        "represents solid prospects with good but not exceptional quality signals; "
        "Cold (30 <= score < 60) represents contacts that may be worth pursuing "
        "with lower priority or additional research; Unqualified (score < 30) "
        "represents contacts that should not be actively pursued and are typically "
        "contacts that narrowly passed the anti-junk rules but showed weak signals "
        "on all other dimensions.")

    # ── 4.4 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "4.4", "Web Frontend Architecture")

    T.body(doc,
        "The web frontend is a single-page application (SPA) built with React 18.2 "
        "using Vite 4.4 as the build tool. Vite's native ES module-based development "
        "server provides sub-100ms hot module replacement (HMR) during development, "
        "dramatically improving iteration speed compared to webpack-based setups.")

    T.subsection_h(doc, "4.4.1", "State Management")
    T.body(doc,
        "Application state is managed through two complementary systems. Redux Toolkit "
        "1.9 manages global UI state: the authenticated user object, active theme "
        "(dark/light), global notification messages, and filter panel state shared "
        "across views. RTK Query (included with Redux Toolkit) manages server state: "
        "API response caching, automatic background refetch on window focus, "
        "optimistic updates for mutation operations, and normalized cache invalidation "
        "when related data changes. This separation avoids the antipattern of storing "
        "server data in Redux, which leads to synchronization bugs and stale cache issues.")

    T.subsection_h(doc, "4.4.2", "Component Architecture")
    T.body(doc,
        "The UI component library is Ant Design 5.1, which provides a comprehensive "
        "set of enterprise-grade components including data tables, form inputs, modals, "
        "charts, date pickers, and notification systems. Ant Design's design token "
        "system is used to implement the dark/light theme toggle: a custom "
        "ConfigProvider wraps the entire application with a theme object that maps "
        "all Ant Design tokens to the active theme's color palette. Theme preference "
        "is persisted to localStorage and restored on application load.")

    T.body(doc,
        "Data visualization uses Chart.js 3.9 through the react-chartjs-2 wrapper. "
        "Four chart types are used in the analytics dashboard: Line chart for "
        "collection trends over time, Pie chart for score tier distribution, "
        "Bar chart for leads by source, and Doughnut chart for lead status breakdown. "
        "All charts respond to the active date range filter and update automatically "
        "when the underlying RTK Query cache is invalidated.")

    T.subsection_h(doc, "4.4.3", "Routing and Navigation")
    T.body(doc,
        "Client-side routing uses React Router DOM 6.4 with the new Data Router "
        "API that supports route-level data loading and error boundaries. Protected "
        "routes are implemented through a ProtectedRoute wrapper component that checks "
        "the Redux auth state and redirects to the login page if no valid token is "
        "present. Role-specific routes (admin-only pages) additionally check the "
        "user's role and redirect to a 403 Forbidden page for insufficient permissions.")

    # ── 4.5 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "4.5", "Mobile Application Architecture")

    T.body(doc,
        "The mobile application is built with React Native 0.81.5 and Expo SDK 54, "
        "targeting both iOS (15+) and Android (11+) from a single JavaScript codebase. "
        "Expo's managed workflow handles native build configuration, OTA update "
        "delivery, and native module management, eliminating the need for Xcode or "
        "Android Studio for routine development and testing.")

    T.subsection_h(doc, "4.5.1", "Navigation Architecture")
    T.body(doc,
        "Navigation uses React Navigation 6.0 with a hybrid navigator structure. "
        "The root navigator is a Stack navigator that handles authentication flow "
        "(Login and Register screens). After authentication, a Bottom Tab navigator "
        "presents the four primary destinations: Dashboard (HomeScreen), Leads "
        "(LeadsScreen), Analytics (AnalyticsScreen), and Profile (ProfileScreen). "
        "From the Leads tab, a nested Stack navigator handles the detail flow: "
        "LeadsScreen -> LeadDetailScreen -> EditLeadScreen.")

    T.subsection_h(doc, "4.5.2", "Offline-First Design")
    T.body(doc,
        "The mobile application implements an offline-first architecture using "
        "React Native's NetInfo library to monitor connectivity state in real time. "
        "When offline, the application serves cached lead data from the React Query "
        "in-memory cache (populated during the last successful fetch). Write operations "
        "— status updates, outcome labels, note edits — are serialized as action "
        "objects and stored in AsyncStorage with a timestamp and retry counter.")

    T.body(doc,
        "When connectivity is restored, the offline queue is drained sequentially "
        "through the API. Conflict resolution uses optimistic locking via the version "
        "field on Lead records: if a lead's version on the server is higher than the "
        "version recorded when the offline action was queued, the action is rejected "
        "and the user is notified to review the conflict. An OfflineBanner component "
        "displays a persistent indicator when the application is operating in offline "
        "mode, preventing user confusion about data currency.")

    T.subsection_h(doc, "4.5.3", "Real-Time Synchronization")
    T.body(doc,
        "The Supabase JavaScript client (@supabase/supabase-js 2.104) establishes a "
        "persistent WebSocket connection to the Supabase Realtime service on "
        "application startup. A channel subscription listens for all INSERT and UPDATE "
        "events on the leads table filtered to records accessible to the current user. "
        "When an event arrives, the corresponding React Query cache entry is "
        "invalidated, triggering an automatic background refetch of the affected data. "
        "This architecture delivers sub-second lead updates to mobile clients without "
        "any polling.")

    # ── 4.6 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "4.6", "Database Design")

    T.body(doc,
        "OrionLead AI uses MySQL 8.0 as its primary relational database, managed "
        "exclusively through SQLAlchemy 2.0 ORM models with no raw SQL. The schema "
        "comprises eight tables organized around the central Leads entity. All tables "
        "use the InnoDB storage engine for foreign key constraint support and ACID "
        "transaction guarantees, the utf8mb4 character set for full Unicode support, "
        "and auto-incrementing integer primary keys with a separate UUID column for "
        "external-facing reference (preventing enumeration attacks on sequential IDs).")

    T.subsection_h(doc, "4.6.1", "Users Table")
    headers = ["Column", "Type", "Constraints", "Description"]
    rows = [
        ["id",               "INT",          "PK, AUTO_INCREMENT",       "Internal integer primary key"],
        ["uuid",             "VARCHAR(36)",  "UNIQUE, NOT NULL",          "UUID v4 for external references"],
        ["email",            "VARCHAR(255)", "UNIQUE, NOT NULL",          "User login email address"],
        ["password_hash",    "VARCHAR(255)", "NOT NULL",                  "bcrypt-hashed password (cost 12)"],
        ["full_name",        "VARCHAR(255)", "NOT NULL",                  "User display name"],
        ["company",          "VARCHAR(255)", "NULL",                      "User's organization name"],
        ["role",             "ENUM",         "NOT NULL, DEFAULT 'user'",  "'admin', 'manager', or 'user'"],
        ["api_key",          "VARCHAR(64)",  "UNIQUE, NULL",              "SHA-256 hashed API key"],
        ["is_active",        "BOOLEAN",      "DEFAULT TRUE",              "Account enabled status"],
        ["source",           "VARCHAR(50)",  "DEFAULT 'web'",             "Registration origin (web / mobile)"],
        ["sync_status",      "VARCHAR(20)",  "DEFAULT 'pending'",         "Supabase synchronization status"],
        ["version",          "INT",          "DEFAULT 1",                 "Optimistic locking version counter"],
        ["created_at",       "DATETIME",     "DEFAULT NOW()",             "Account creation timestamp"],
        ["updated_at",       "DATETIME",     "DEFAULT NOW(), ON UPDATE",  "Last modification timestamp"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(2.8), Cm(3.4), Cm(5.1)])
    T.caption(doc, "Table 4.2 — Users Table Attributes")

    T.subsection_h(doc, "4.6.2", "Leads Table")
    rows = [
        ["id",                   "INT",          "PK, AUTO_INCREMENT",       "Internal integer primary key"],
        ["uuid",                 "VARCHAR(36)",  "UNIQUE, NOT NULL",          "UUID v4 for external references"],
        ["name",                 "VARCHAR(255)", "NOT NULL",                  "Lead's full name"],
        ["email",                "VARCHAR(255)", "NULL",                      "Business email address"],
        ["phone",                "VARCHAR(50)",  "NULL",                      "Phone number with country code"],
        ["company",              "VARCHAR(255)", "NULL",                      "Company or organization name"],
        ["position",             "VARCHAR(255)", "NULL",                      "Job title or role"],
        ["location",             "VARCHAR(255)", "NULL",                      "Full location string"],
        ["country",              "VARCHAR(100)", "NULL",                      "Country name"],
        ["city",                 "VARCHAR(100)", "NULL",                      "City name"],
        ["industry",             "VARCHAR(100)", "NULL",                      "Industry vertical label"],
        ["website",              "VARCHAR(500)", "NULL",                      "Company website URL"],
        ["linkedin_url",         "VARCHAR(500)", "NULL",                      "LinkedIn profile or company URL"],
        ["qualification_score",  "FLOAT",        "DEFAULT 0.0",               "AI qualification score (0–100)"],
        ["completeness_score",   "FLOAT",        "DEFAULT 0.0",               "Data completeness metric (0–100)"],
        ["status",               "VARCHAR(50)",  "DEFAULT 'new'",             "Pipeline status (new/contacted/etc.)"],
        ["source",               "VARCHAR(100)", "NULL",                      "Collection source (hunter/apollo/etc.)"],
        ["origin",               "VARCHAR(50)",  "DEFAULT 'web'",             "Origin platform (web/mobile/api)"],
        ["data_points",          "JSON",         "NULL",                      "Enrichment metadata and verification flags"],
        ["buying_intent",        "VARCHAR(20)",  "NULL",                      "Detected intent level (high/medium/low)"],
        ["intent_confidence",    "FLOAT",        "NULL",                      "Intent detection confidence score (0–1)"],
        ["collected_by",         "INT",          "FK -> users.id, NULL",      "ID of user who collected this lead"],
        ["sync_status",          "VARCHAR(20)",  "DEFAULT 'pending'",         "Supabase sync status"],
        ["created_at",           "DATETIME",     "DEFAULT NOW()",             "Creation timestamp"],
        ["updated_at",           "DATETIME",     "DEFAULT NOW(), ON UPDATE",  "Last modification timestamp"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(2.8), Cm(3.4), Cm(5.1)])
    T.caption(doc, "Table 4.3 — Leads Table Attributes")

    T.subsection_h(doc, "4.6.3", "LeadActivities Table")
    rows = [
        ["id",            "INT",          "PK, AUTO_INCREMENT",  "Activity record primary key"],
        ["lead_id",       "INT",          "FK -> leads.id",      "Associated lead reference"],
        ["user_id",       "INT",          "FK -> users.id, NULL","User who performed the action"],
        ["activity_type", "VARCHAR(50)",  "NOT NULL",            "Type: created / updated / labeled / qualified / deleted"],
        ["description",   "TEXT",         "NULL",                "Human-readable activity description"],
        ["old_value",     "TEXT",         "NULL",                "Previous field value before change"],
        ["new_value",     "TEXT",         "NULL",                "New field value after change"],
        ["created_at",    "DATETIME",     "DEFAULT NOW()",       "Activity occurrence timestamp"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(2.8), Cm(3.4), Cm(5.1)])
    T.caption(doc, "Table 4.4 — LeadActivities Table Attributes")

    T.subsection_h(doc, "4.6.4", "LeadOutcomes Table")
    rows = [
        ["id",         "INT",         "PK, AUTO_INCREMENT", "Outcome record primary key"],
        ["lead_id",    "INT",         "FK -> leads.id",     "Associated lead reference"],
        ["user_id",    "INT",         "FK -> users.id",     "User who submitted the label"],
        ["outcome",    "ENUM",        "NOT NULL",           "'converted' / 'replied' / 'no_reply' / 'not_a_fit'"],
        ["notes",      "TEXT",        "NULL",               "Optional context or reasoning notes"],
        ["labeled_at", "DATETIME",    "DEFAULT NOW()",      "Timestamp when label was applied"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(2.8), Cm(3.4), Cm(5.1)])
    T.caption(doc, "Table 4.5 — LeadOutcomes Table Attributes")

    T.subsection_h(doc, "4.6.5", "DataSources Table")
    rows = [
        ["id",                "INT",          "PK, AUTO_INCREMENT", "Source record primary key"],
        ["name",              "VARCHAR(100)", "UNIQUE, NOT NULL",   "Source slug (hunter / apollo / pdl / etc.)"],
        ["display_name",      "VARCHAR(255)", "NOT NULL",           "Human-readable source label"],
        ["is_enabled",        "BOOLEAN",      "DEFAULT FALSE",      "Whether this source is active for collection"],
        ["api_key_encrypted", "TEXT",         "NULL",               "AES-encrypted API key for this source"],
        ["config",            "JSON",         "NULL",               "Source-specific configuration parameters"],
        ["last_used_at",      "DATETIME",     "NULL",               "Timestamp of last successful collection run"],
        ["created_at",        "DATETIME",     "DEFAULT NOW()",      "Source registration timestamp"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(2.8), Cm(3.4), Cm(5.1)])
    T.caption(doc, "Table 4.6 — DataSources Table Attributes")

    T.subsection_h(doc, "4.6.6", "ClassificationCategories Table")
    rows = [
        ["id",           "INT",          "PK, AUTO_INCREMENT", "Category primary key"],
        ["name",         "VARCHAR(100)", "UNIQUE, NOT NULL",   "Category slug identifier"],
        ["display_name", "VARCHAR(255)", "NOT NULL",           "Category display label shown in UI"],
        ["description",  "TEXT",         "NULL",               "Category description and criteria"],
        ["color",        "VARCHAR(7)",   "NULL",               "Hex color code for UI badge display"],
        ["is_active",    "BOOLEAN",      "DEFAULT TRUE",       "Whether category appears in selection lists"],
        ["created_at",   "DATETIME",     "DEFAULT NOW()",      "Category creation timestamp"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(2.8), Cm(3.4), Cm(5.1)])
    T.caption(doc, "Table 4.7 — ClassificationCategories Table Attributes")

    T.subsection_h(doc, "4.6.7", "SeenContacts Table")
    rows = [
        ["id",               "INT",          "PK, AUTO_INCREMENT", "Record primary key"],
        ["email",            "VARCHAR(255)", "NOT NULL, INDEX",    "Email address — indexed for fast duplicate lookup"],
        ["phone",            "VARCHAR(50)",  "NULL",               "Phone number for cross-field deduplication"],
        ["linkedin_url",     "VARCHAR(500)", "NULL",               "LinkedIn URL for cross-field deduplication"],
        ["source",           "VARCHAR(100)", "NULL",               "Source where this contact was first seen"],
        ["rejection_reason", "VARCHAR(100)", "NULL",               "Anti-junk rule name if contact was rejected"],
        ["first_seen_at",    "DATETIME",     "DEFAULT NOW()",      "Timestamp of first encounter with this contact"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(2.8), Cm(3.4), Cm(5.1)])
    T.caption(doc, "Table 4.8 — SeenContacts Table Attributes")

    T.subsection_h(doc, "4.6.8", "SyncLogs Table")
    rows = [
        ["id",            "INT",         "PK, AUTO_INCREMENT", "Log record primary key"],
        ["entity_type",   "VARCHAR(50)", "NOT NULL",           "Synced entity type ('lead' / 'user')"],
        ["entity_id",     "INT",         "NOT NULL",           "Primary key of the synced entity"],
        ["action",        "VARCHAR(20)", "NOT NULL",           "Sync action: 'insert' / 'update' / 'delete'"],
        ["status",        "VARCHAR(20)", "NOT NULL",           "Result: 'success' / 'failed' / 'pending'"],
        ["error_message", "TEXT",        "NULL",               "Error details if synchronization failed"],
        ["synced_at",     "DATETIME",    "DEFAULT NOW()",      "Timestamp of sync attempt"],
        ["retry_count",   "INT",         "DEFAULT 0",          "Number of retry attempts made"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(2.8), Cm(3.4), Cm(5.1)])
    T.caption(doc, "Table 4.9 — SyncLogs Table Attributes")

    # ── 4.7 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "4.7", "Entity-Relationship Diagram (ERD)")

    T.body(doc,
        "Figures 4.3a and 4.3b present the Entity-Relationship Diagrams for the OrionLead AI "
        "database schema. The diagrams use standard crow's foot notation to represent "
        "cardinality and participation constraints between entities. The schema is split "
        "into two sub-diagrams for readability: Figure 4.3a covers the core domain tables "
        "with their foreign key relationships, while Figure 4.3b covers the independent "
        "supporting tables.")

    T.body(doc,
        "The central entity is Leads, which has mandatory many-to-one relationships "
        "with Users through the collected_by foreign key (each lead is optionally "
        "collected by one user; one user can collect many leads). Leads has "
        "one-to-many relationships with LeadActivities (each lead can have many "
        "activity log entries) and LeadOutcomes (each lead can have multiple outcome "
        "labels over time, though in practice typically one primary outcome).")

    T.body(doc,
        "The Users entity is also referenced by LeadActivities (recording which user "
        "performed each action) and LeadOutcomes (recording which user applied each "
        "label). DataSources, ClassificationCategories, SeenContacts, and SyncLogs "
        "are independent supporting entities with no foreign key relationships to the "
        "core Lead-User graph, making them independently queryable and maintainable.")

    T.caption(doc, "Figure 4.3a — Core Domain Entity-Relationship Diagram (ERD)")

    T.caption(doc, "Figure 4.3b — Supporting Tables Entity-Relationship Diagram")

    # ── 4.8 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "4.8", "Security Architecture")

    T.body(doc,
        "Security is enforced at multiple layers throughout the system, following the "
        "defense-in-depth principle. No single layer is trusted as the sole security "
        "boundary; each layer provides independent protection that remains effective "
        "even if another layer is compromised or misconfigured.")

    T.subsection_h(doc, "4.8.1", "Authentication")
    T.body(doc,
        "Authentication uses JSON Web Tokens (JWT) issued by PyJWT 2.8.0 with the "
        "HS256 signing algorithm and a server-held secret key. Tokens include the "
        "user's ID, role, and email in the payload, signed with the secret to prevent "
        "tampering. Tokens expire after 24 hours, requiring re-authentication. Tokens "
        "are transmitted in the Authorization header using the Bearer scheme and never "
        "in URL query parameters (preventing logging exposure).")

    T.body(doc,
        "An alternative authentication path using API keys is provided for programmatic "
        "access by integrations and scripts. API keys are generated as cryptographically "
        "random 64-character strings, stored in the database as SHA-256 hashes, and "
        "accepted via the X-API-Key request header. The plaintext key is shown only "
        "once at generation time and cannot be recovered from the hash.")

    T.subsection_h(doc, "4.8.2", "Password Security")
    T.body(doc,
        "Passwords are hashed using bcrypt via flask-bcrypt with a work factor of 12, "
        "which produces a hash computation time of approximately 300ms on commodity "
        "hardware. This cost makes offline brute-force attacks computationally "
        "infeasible for any reasonably complex password. Plaintext passwords are never "
        "stored, logged, or transmitted after the initial hashing operation at "
        "registration. Password validation at login compares the submitted password "
        "against the stored hash using bcrypt's constant-time comparison to prevent "
        "timing-based side-channel attacks.")

    T.subsection_h(doc, "4.8.3", "Role-Based Access Control")
    T.body(doc,
        "RBAC is enforced at the API layer using a custom @require_role(min_role) "
        "decorator applied to every protected endpoint. The decorator extracts the "
        "JWT payload, resolves the user's current role from the database (not from "
        "the token, preventing stale role escalation), compares it against the "
        "required minimum role, and returns 403 Forbidden for insufficient permissions. "
        "This enforcement is independent of any frontend visibility controls, ensuring "
        "that access restrictions cannot be bypassed by manipulating the client application.")

    T.subsection_h(doc, "4.8.4", "SQL Injection Prevention")
    T.body(doc,
        "All database interactions use SQLAlchemy ORM methods, which internally use "
        "parameterized queries for all value substitution. No raw SQL string "
        "concatenation is used anywhere in the codebase. This categorically prevents "
        "SQL injection regardless of input content. Input validation using marshmallow "
        "schemas at API boundaries provides an additional layer that rejects malformed "
        "inputs before they reach the database layer.")

    T.subsection_h(doc, "4.8.5", "Transport Security")
    T.body(doc,
        "All production API communication uses HTTPS with TLS 1.2 or higher, enforced "
        "at the reverse proxy layer (Nginx). The Flask development server is never "
        "exposed in production. Cross-Origin Resource Sharing (CORS) is configured "
        "with an explicit allowlist of trusted origins rather than a wildcard, "
        "preventing unauthorized cross-origin API access from malicious web pages.")

    # ── 4.9 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "4.9", "External Integrations")

    T.body(doc,
        "OrionLead AI integrates with ten external services. Each integration is "
        "implemented as an independent, fault-isolated module in the services/ "
        "directory. API keys are stored encrypted in the DataSources table and "
        "decrypted at runtime. Table 4.10 summarizes all external integrations with "
        "their purpose, authentication method, and fallback behavior.")

    headers = ["Service", "Purpose", "Auth", "Fallback on Failure"]
    rows = [
        ["Hunter.io",         "Find business email addresses by domain or person name",   "API Key", "Skip source; continue with others"],
        ["Apollo.io",         "B2B contact and company intelligence — 275M+ profiles",    "API Key", "Skip source; continue with others"],
        ["People Data Labs",  "Person and company enrichment — firmographic signals",      "API Key", "Skip source; continue with others"],
        ["Serper.dev",        "Google Search proxy for web-based lead discovery",          "API Key", "Skip source; continue with others"],
        ["Google Places",     "Business contacts from Google Maps database",               "API Key", "Skip source; continue with others"],
        ["ZeroBounce",        "Email deliverability validation — active/inactive/risky",   "API Key", "Mark email unverified; continue"],
        ["Google Gemini",     "LLM contextual scoring — Layer 3 of AI cascade",           "API Key", "Fall through to Layer 4 (Groq)"],
        ["Groq",              "Fast Llama LLM inference — Layer 4 fallback",               "API Key", "Use XGBoost score alone (Layer 2)"],
        ["Firebase FCM",      "Push notification delivery to mobile device tokens",        "Service Account JSON", "Log failure; continue silently"],
        ["Supabase",          "Real-time PostgreSQL event streaming to mobile clients",    "JWT + RLS Policies", "Queue sync; serve cached data"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.0), Cm(5.0), Cm(2.8), Cm(3.5)])
    T.caption(doc, "Table 4.10 — External API Integrations")

    T.body(doc,
        "All external API calls include a configurable timeout (default 8 seconds for "
        "data APIs, 6 seconds for LLM APIs) and structured exception handling that "
        "catches connection errors, timeouts, HTTP error responses, and malformed "
        "response bodies. Failures are logged with full context (service name, "
        "endpoint, error type, response code) for debugging, but never propagated "
        "as user-facing errors when the overall operation can continue with degraded "
        "functionality. This fault isolation ensures that a single unavailable "
        "external service cannot halt the entire lead collection or qualification pipeline.")

    T.body(doc,
        "The Company-First Intelligence Pipeline (Figure 4.4) adds a pre-contact "
        "evaluation stage that assesses organizational quality before individual "
        "contacts are resolved. Seven modules execute in sequence: anti_junk "
        "(company-level rejection rules), website_auditor (checks website "
        "availability, SSL validity, and content quality), business_classifier "
        "(categorizes the company's business model using LLM reasoning), "
        "growth_detector (identifies growth signals: recent funding, job postings, "
        "technology adoption), account_scorer (produces a company-level "
        "quality score), contact_resolver (fetches individual contacts only for "
        "companies that pass the account score threshold), and "
        "intelligence_orchestrator (coordinates all modules and manages their "
        "sequential execution with fault isolation between stages).")

    T.caption(doc, "Figure 4.4 — Company-First Intelligence Pipeline")
