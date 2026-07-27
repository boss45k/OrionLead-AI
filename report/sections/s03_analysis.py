"""
s03_analysis.py — Chapter 3: System Analysis
Target: 12-14 pages
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import theme as T
from docx.shared import Cm


def build(doc):
    T.chapter_title(doc, 3, "System Analysis")

    T.body(doc,
        "System analysis is the process of decomposing a complex problem into its "
        "constituent parts, formally specifying the behavior expected of a proposed "
        "solution, and establishing the boundaries within which that solution must "
        "operate. This chapter presents the complete system analysis for OrionLead AI, "
        "covering the external entities that interact with the system, the user roles "
        "and their permission boundaries, the functional and non-functional "
        "requirements, the data flow across system processes, and the use cases that "
        "define the system's behavior from the perspective of each actor.")

    # ── 3.1 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "3.1", "System External Entities")

    T.body(doc,
        "External entities are persons, organizations, or systems that interact with "
        "OrionLead AI by sending data to it, receiving data from it, or both — but "
        "are themselves outside the system boundary. Identifying all external entities "
        "is a prerequisite for correctly scoping the system and specifying its "
        "interfaces. Table 3.1 enumerates all entities that interact with OrionLead AI.")

    headers = ["Entity", "Type", "Description", "Direction"]
    rows = [
        ["Sales User",          "Human",    "Field sales rep using the mobile or web app to view, label, and manage assigned leads",                             "Bidirectional"],
        ["Manager",             "Human",    "Team lead who oversees team members' lead pipelines, analytics, and can delete leads",                               "Bidirectional"],
        ["Administrator",       "Human",    "System admin with unrestricted access to all leads, users, data sources, and ML retraining",                         "Bidirectional"],
        ["Hunter.io",           "Ext. API", "Email finding service — discovers verified business email addresses by domain or name",                               "Inbound data"],
        ["Apollo.io",           "Ext. API", "B2B contact and company intelligence database with 275M+ enriched professional profiles",                            "Inbound data"],
        ["People Data Labs",    "Ext. API", "Person and company enrichment API providing firmographic and demographic signals",                                    "Inbound data"],
        ["Serper.dev",          "Ext. API", "Google Search API proxy used for web-based lead discovery and company research queries",                              "Inbound data"],
        ["Google Places API",   "Ext. API", "Business location and contact data from Google Maps database for local business leads",                               "Inbound data"],
        ["ZeroBounce",          "Ext. API", "Email validation and deliverability verification; confirms email is active and deliverable",                          "Inbound data"],
        ["Google Gemini",       "Ext. AI",  "Google's multimodal LLM; used as Layer 3 of the qualification cascade for contextual scoring",                       "Inbound AI"],
        ["Groq",                "Ext. AI",  "Ultra-fast Llama LLM inference; used as Layer 4 fallback when Gemini is unavailable",                                "Inbound AI"],
        ["Firebase FCM",        "Ext. Svc", "Firebase Cloud Messaging; delivers push notifications to mobile devices for lead events",                             "Outbound"],
        ["Supabase",            "Ext. Svc", "PostgreSQL real-time bridge syncing MySQL backend changes to mobile clients instantly",                               "Bidirectional"],
        ["MySQL 8.0",           "Internal", "Primary relational data store for all leads, users, activities, outcomes, and system data",                           "Bidirectional"],
        ["Redis",               "Internal", "In-memory cache and Celery message broker for background job queuing and task management",                            "Bidirectional"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(2.8), Cm(2.0), Cm(7.5), Cm(2.6)])
    T.caption(doc, "Table 3.1 — System External Entities")

    # ── 3.2 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "3.2", "User Roles and Permissions")

    T.body(doc,
        "OrionLead AI implements a three-tier Role-Based Access Control (RBAC) model. "
        "Each role inherits all permissions of the role below it and adds additional "
        "capabilities. The role hierarchy from least to most privileged is: User → "
        "Manager → Admin. All role enforcement is implemented at the API layer through "
        "a custom @require_role decorator applied to every protected endpoint, "
        "independent of any frontend visibility controls.")

    headers = ["Permission", "User", "Manager", "Admin"]
    rows = [
        ["View own collected leads",           "Yes", "Yes", "Yes"],
        ["View all leads in the system",       "No",  "Yes", "Yes"],
        ["Create leads manually",              "Yes", "Yes", "Yes"],
        ["Trigger AI lead collection",         "Yes", "Yes", "Yes"],
        ["Edit own lead details",              "Yes", "Yes", "Yes"],
        ["Edit any lead in the system",        "No",  "Yes", "Yes"],
        ["Delete leads",                       "No",  "Yes", "Yes"],
        ["Label lead outcomes (QuickLabel)",   "Yes", "Yes", "Yes"],
        ["Export filtered leads to CSV",       "Yes", "Yes", "Yes"],
        ["Re-run AI qualification on a lead",  "Yes", "Yes", "Yes"],
        ["View own analytics",                 "Yes", "Yes", "Yes"],
        ["View team-wide analytics",           "No",  "Yes", "Yes"],
        ["View all-system analytics",          "No",  "No",  "Yes"],
        ["Manage user accounts and roles",     "No",  "No",  "Yes"],
        ["Configure data sources and API keys","No",  "No",  "Yes"],
        ["Trigger ML model retraining",        "No",  "No",  "Yes"],
        ["View system audit/activity logs",    "No",  "Yes", "Yes"],
        ["Generate personal API keys",         "Yes", "Yes", "Yes"],
        ["Manage push notification tokens",    "Yes", "Yes", "Yes"],
        ["Access Swagger API documentation",   "Yes", "Yes", "Yes"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(7.2), Cm(1.8), Cm(2.0), Cm(1.8)],
                   center_cols={1, 2, 3})
    T.caption(doc, "Table 3.2 — User Roles and Permissions Matrix")

    # ── 3.3 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "3.3", "Functional Requirements")

    T.body(doc,
        "Functional requirements specify what the system must do — the behaviors, "
        "functions, and capabilities it must provide to its users and external "
        "systems. Each functional requirement is assigned a unique identifier, a "
        "priority level (High / Medium / Low), and a clear description of the "
        "expected system behavior.")

    headers = ["ID", "Requirement Description", "Priority"]
    rows = [
        ["FR-01", "The system shall allow users to register using a unique email address, full name, company, and password with minimum length enforcement.", "High"],
        ["FR-02", "The system shall authenticate users with email and password, issuing a signed JWT access token with a 24-hour expiry on success.", "High"],
        ["FR-03", "The system shall support three user roles (admin, manager, user) with permissions enforced at the API layer on every request.", "High"],
        ["FR-04", "The system shall allow authenticated users to trigger AI-powered lead collection using a natural language query and configurable source selection.", "High"],
        ["FR-05", "The system shall apply an anti-junk rule engine with 12 hard-reject rules to every collected candidate before any ML or LLM processing.", "High"],
        ["FR-06", "The system shall score each passing candidate using a four-layer AI cascade: Anti-Junk → XGBoost (37 features) → Gemini LLM → Groq fallback.", "High"],
        ["FR-07", "The system shall assign each lead a qualification tier: Hot (score ≥80), Warm (≥60), Cold (≥30), or Unqualified (<30).", "High"],
        ["FR-08", "The system shall prevent duplicate lead entries using a SeenContacts table indexed on email, phone, and LinkedIn URL.", "High"],
        ["FR-09", "The system shall auto-stamp the collected_by field on every new lead with the authenticated user's ID before database insertion.", "High"],
        ["FR-10", "The system shall restrict non-admin users to viewing only leads where collected_by equals their own user ID.", "High"],
        ["FR-11", "The system shall allow managers and admins to view all leads within their scope without collected_by filtering.", "High"],
        ["FR-12", "The system shall allow users to create leads manually with all available fields through a validated API endpoint.", "Medium"],
        ["FR-13", "The system shall allow users to update lead status, contact details, notes, and other fields through a PUT endpoint.", "High"],
        ["FR-14", "The system shall allow managers and admins to delete leads, with soft-delete logging the action in LeadActivities.", "Medium"],
        ["FR-15", "The system shall log all lead field changes, status transitions, and outcome labels to the LeadActivities table with user and timestamp.", "High"],
        ["FR-16", "The system shall provide one-click outcome labeling (Converted / Replied / No Reply / Not a Fit) through the QuickLabelBar interface.", "High"],
        ["FR-17", "The system shall persist each outcome label to the LeadOutcomes table and queue it for ML retraining via Celery.", "High"],
        ["FR-18", "The system shall support full-text search across lead name, email, company, position, and industry fields.", "Medium"],
        ["FR-19", "The system shall export all leads matching active filters to a CSV file with complete field headers.", "Medium"],
        ["FR-20", "The system shall deliver real-time analytics for score distribution, collection trends, source performance, and conversion rates.", "Medium"],
        ["FR-21", "The system shall synchronize lead create, update, and delete events from MySQL to Supabase in real time for mobile clients.", "High"],
        ["FR-22", "The system shall support offline lead action queuing on mobile, replaying queued actions in order when connectivity is restored.", "Medium"],
        ["FR-23", "The system shall send push notifications via FCM when new leads are collected or lead status changes to a significant state.", "Medium"],
        ["FR-24", "The system shall allow administrators to enable, disable, and configure API keys for each data source independently.", "High"],
        ["FR-25", "The system shall expose interactive API documentation through a Swagger UI accessible at /api/docs.", "Low"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(1.6), Cm(10.8), Cm(1.8)],
                   center_cols={0, 2})
    T.caption(doc, "Table 3.3 — Functional Requirements")

    # ── 3.4 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "3.4", "Non-Functional Requirements")

    T.body(doc,
        "Non-functional requirements specify the quality attributes, constraints, and "
        "operational characteristics the system must exhibit. They define how well the "
        "system performs its functions rather than what functions it performs.")

    headers = ["ID", "Category", "Requirement", "Metric / Target"]
    rows = [
        ["NFR-01", "Performance",    "Standard CRUD API endpoints shall respond within acceptable time under normal load",           "< 500 ms average"],
        ["NFR-02", "Performance",    "AI qualification of a single lead shall complete end-to-end including LLM processing",         "< 8 seconds"],
        ["NFR-03", "Performance",    "Batch lead collection of up to 50 candidates shall complete as a background task",             "< 120 seconds"],
        ["NFR-04", "Scalability",    "The backend shall handle concurrent users without degradation in response time",               "100 concurrent users"],
        ["NFR-05", "Reliability",    "The system shall maintain service availability during business hours",                          "99.5% uptime"],
        ["NFR-06", "Reliability",    "Failed Supabase sync events shall be retried automatically with exponential backoff",          "Max 3 retries"],
        ["NFR-07", "Security",       "All API communication in production shall use encrypted transport",                             "HTTPS / TLS 1.2+"],
        ["NFR-08", "Security",       "Passwords shall be stored using adaptive hashing with a high cost factor",                     "bcrypt, cost ≥ 12"],
        ["NFR-09", "Security",       "JWT tokens shall have a defined expiry and require re-authentication after expiry",             "24-hour TTL"],
        ["NFR-10", "Security",       "Role-based access control shall be enforced at the API layer on every protected endpoint",     "100% coverage"],
        ["NFR-11", "Security",       "All database queries shall use parameterized statements to prevent SQL injection",              "No raw SQL strings"],
        ["NFR-12", "Maintainability","Backend test suite shall achieve a high automated test coverage rate",                          ">= 80% coverage"],
        ["NFR-13", "Maintainability","All API endpoints shall be documented with request schemas, response schemas, and examples",   "Swagger/OpenAPI 3.0"],
        ["NFR-14", "Portability",    "The mobile application shall run on both major mobile operating systems from one codebase",    "iOS 15+ and Android 11+"],
        ["NFR-15", "Portability",    "The backend shall be deployable on any Linux server with Python 3.11+ and MySQL 8.0",         "No OS-specific dependencies"],
        ["NFR-16", "Usability",      "The UI shall support both dark and light color themes with system preference auto-detection",  "Web and mobile both"],
        ["NFR-17", "Data Integrity", "The deduplication mechanism shall prevent insertion of leads already seen in prior sessions",  ">= 95% duplicate block rate"],
        ["NFR-18", "Auditability",   "All lead field modifications shall be logged with the responsible user ID and timestamp",      "LeadActivities table"],
        ["NFR-19", "Availability",   "Mobile clients shall support full lead viewing while offline with queued write-back",          "Offline-first with AsyncStorage"],
        ["NFR-20", "Testability",    "CI/CD pipeline shall validate all tests against two database engines on every code push",      "SQLite + MySQL in parallel"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(1.5), Cm(2.8), Cm(7.0), Cm(3.0)],
                   center_cols={0})
    T.caption(doc, "Table 3.4 — Non-Functional Requirements")

    # ── 3.5 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "3.5", "Data Flow Diagram (DFD)")

    T.body(doc,
        "Data Flow Diagrams illustrate how data moves through the system — from external "
        "entities, through processes, and into data stores. Two levels of DFD are "
        "presented: the Level-0 context diagram, which shows the system as a single "
        "process with all external interactions, and the Level-1 diagram, which "
        "decomposes the system into its primary processing modules.")

    T.subsection_h(doc, "3.5.1", "Level-0 DFD — Context Diagram")
    T.body(doc,
        "The Level-0 context diagram (Figure 3.1) represents OrionLead AI as a single "
        "process box at the center of all external entity interactions. Three categories "
        "of interaction are visible at this level:")

    T.bullet(doc,
        "Human actors (Sales User, Manager, Administrator) send authentication "
        "credentials, lead requests, collection queries, and management commands to "
        "the system, and receive scored leads, analytics data, export files, and "
        "push notifications in return.")

    T.bullet(doc,
        "External data APIs (Hunter.io, Apollo.io, People Data Labs, Serper.dev, "
        "Google Places, ZeroBounce) supply raw contact and company data in response "
        "to collection queries dispatched by the system.")

    T.bullet(doc,
        "External AI and service providers (Google Gemini, Groq, Firebase FCM, "
        "Supabase) receive structured qualification requests from the system and "
        "return qualification assessments, push notification acknowledgements, and "
        "real-time event confirmations.")

    T.caption(doc, "Figure 3.1 — Level-0 Data Flow Diagram (Context Diagram)")

    T.subsection_h(doc, "3.5.2", "Level-1 DFD")
    T.body(doc,
        "The Level-1 DFD (Figure 3.2) decomposes the system into seven primary "
        "processes, revealing how data flows between them and which data stores each "
        "process reads from or writes to.")

    T.body(doc,
        "Process 1.0 — Authentication and Authorization: Receives login credentials "
        "from human actors, validates them against the Users data store using bcrypt "
        "comparison, issues signed JWT tokens on success, and validates tokens on "
        "every subsequent request to enforce role-based permission boundaries before "
        "passing requests to downstream processes.")

    T.body(doc,
        "Process 2.0 — Lead Collection Orchestrator: Receives a natural language "
        "collection query and source configuration from an authenticated user. Sends "
        "the query to Google Gemini for parameter optimization, then dispatches "
        "parallel API calls to all enabled external data sources. Aggregates returned "
        "candidates and routes each one to Process 3.0 for qualification.")

    T.body(doc,
        "Process 3.0 — AI Qualification Cascade: Receives raw lead candidates from "
        "Process 2.0. Applies the four-layer qualification pipeline sequentially: "
        "anti-junk rule evaluation (12 rules), XGBoost ML scoring (37 features), "
        "Google Gemini LLM contextual assessment, and Groq fallback reasoning. Writes "
        "qualified leads with final scores to the Leads data store and rejected "
        "candidates to the SeenContacts data store.")

    T.body(doc,
        "Process 4.0 — Lead Management: Handles all CRUD operations on lead records. "
        "Reads and writes the Leads data store, enforces collected_by visibility "
        "filtering, and logs all field changes and status transitions to the "
        "LeadActivities data store.")

    T.body(doc,
        "Process 5.0 — Outcome Labeling and ML Feedback: Receives QuickLabelBar "
        "outcome selections from authenticated users. Writes outcome records to the "
        "LeadOutcomes data store. Queues ML retraining jobs to Redis via Celery when "
        "a sufficient batch of new labeled examples has accumulated.")

    T.body(doc,
        "Process 6.0 — Analytics Engine: Reads aggregated data from the Leads, "
        "LeadActivities, and LeadOutcomes data stores. Computes role-scoped metrics "
        "including collection trends, score tier distributions, source performance, "
        "and conversion rates. Returns structured analytics data to authenticated "
        "human actors according to their role's data scope.")

    T.body(doc,
        "Process 7.0 — Synchronization and Notifications: Monitors the SyncLogs "
        "data store for pending sync events. Mirrors lead changes to Supabase for "
        "real-time mobile delivery. Dispatches FCM push notification payloads to "
        "Firebase Cloud Messaging for significant lead events. Resolves incoming "
        "offline action queues from mobile clients.")

    T.caption(doc, "Figure 3.2 — Level-1 Data Flow Diagram")

    # ── 3.6 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "3.6", "Use Case Diagram")

    T.body(doc,
        "The Use Case Diagram (Figure 3.3) illustrates the interactions between the "
        "three system actors and the system's primary use cases. It uses the standard "
        "UML notation: actors are represented as stick figures, use cases as ovals, "
        "and the system boundary as a rectangle enclosing all use cases.")

    T.body(doc,
        "The three actors are: User (leftmost), Manager (which extends User via "
        "generalization, inheriting all User use cases plus Manager-specific ones), "
        "and Admin (which extends Manager, inheriting all Manager use cases plus "
        "Admin-exclusive ones). External systems — data APIs, AI providers, FCM, "
        "and Supabase — are shown as secondary actors on the right side of the diagram "
        "connected to the use cases they participate in.")

    T.body(doc,
        "The primary use cases visible in the diagram are: Register Account, Login, "
        "Collect Leads with AI, View Leads, Create Lead Manually, Edit Lead, "
        "Label Outcome, Export to CSV, Search Leads, View Analytics, Receive "
        "Push Notification (User-level); Delete Lead, View Team Analytics, "
        "View All Leads (Manager-level); Manage Users, Configure Data Sources, "
        "Trigger ML Retraining, View Audit Logs (Admin-level).")

    T.caption(doc, "Figure 3.3 — Use Case Diagram")

    # ── 3.7 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "3.7", "Use Case Descriptions")

    T.body(doc,
        "The following tables provide structured descriptions of the five most "
        "critical use cases in the system. Each description specifies the involved "
        "actor, preconditions, main success flow, alternative flows, and postconditions "
        "following the standard IEEE use case description format.")

    # UC-01
    T.subsection_h(doc, "3.7.1", "UC-01: Register Account")
    headers = ["Field", "Detail"]
    rows = [
        ["Use Case ID",     "UC-01"],
        ["Name",            "Register Account"],
        ["Actor",           "Unauthenticated User (new)"],
        ["Precondition",    "User has a valid email address not previously registered in the system"],
        ["Trigger",         "User navigates to the registration page and submits the registration form"],
        ["Main Flow",
         "1. User enters full name, email address, password (min 8 characters), and company name.\n"
         "2. System validates all input fields for format correctness and completeness.\n"
         "3. System queries the Users table to verify the email address is unique.\n"
         "4. System hashes the password using bcrypt with cost factor 12.\n"
         "5. System creates a new User record with role='user', is_active=True, and a generated UUID.\n"
         "6. System returns HTTP 201 Created with a success confirmation message."],
        ["Alternative Flow A",
         "Step 3: If the email already exists in the database, the system returns HTTP 409 Conflict "
         "with the error message 'Email address is already registered.'"],
        ["Alternative Flow B",
         "Step 2: If any required field is missing or the password is shorter than 8 characters, "
         "the system returns HTTP 400 Bad Request with field-level validation error details."],
        ["Postcondition",   "A new user account exists in the Users table with role='user'. The user can immediately log in."],
    ]
    T.styled_table(doc, headers, rows, col_widths=[Cm(3.2), Cm(11.1)])
    T.caption(doc, "Table 3.5 — Use Case: UC-01 Register Account")

    # UC-02
    T.subsection_h(doc, "3.7.2", "UC-02: Collect Leads with AI")
    rows = [
        ["Use Case ID",     "UC-02"],
        ["Name",            "Collect Leads with AI"],
        ["Actor",           "Authenticated User (any role)"],
        ["Precondition",    "User is authenticated with a valid JWT. At least one data source is enabled and configured by an admin."],
        ["Trigger",         "User enters a natural language collection query and submits the collection form"],
        ["Main Flow",
         "1. User enters a natural language query (e.g., 'Fintech CTOs in the UAE with 50-200 employees').\n"
         "2. User selects which data sources to include in the collection run.\n"
         "3. Google Gemini analyzes the query and generates optimized, source-specific search parameters.\n"
         "4. System dispatches parallel API requests to all selected enabled data sources.\n"
         "5. Results are aggregated and checked against the SeenContacts table for prior occurrences.\n"
         "6. Each unseen candidate is passed through the four-layer AI qualification cascade.\n"
         "7. Candidates passing the cascade are saved as Lead records with collected_by = current user ID.\n"
         "8. Anti-junk rejections are logged to SeenContacts to prevent future re-collection.\n"
         "9. System returns a collection summary: total found, passed, rejected, and breakdown by tier."],
        ["Alternative Flow A",
         "Step 4: If a specific data source returns an API error, that source is skipped and collection "
         "continues with the remaining sources. The summary notes which sources failed."],
        ["Alternative Flow B",
         "Step 6, Layer 3: If Google Gemini is unavailable or times out, the cascade falls through to "
         "Layer 4 (Groq) automatically. If Groq also fails, the XGBoost score alone is used."],
        ["Alternative Flow C",
         "Step 5: If a candidate's email, phone, or LinkedIn URL exists in SeenContacts, the candidate "
         "is silently skipped without any AI processing."],
        ["Postcondition",   "New qualified leads appear in the user's lead list with qualification scores, tiers, and source metadata assigned."],
    ]
    T.styled_table(doc, headers, rows, col_widths=[Cm(3.2), Cm(11.1)])
    T.caption(doc, "Table 3.6 — Use Case: UC-02 Collect Leads with AI")

    # UC-03
    T.subsection_h(doc, "3.7.3", "UC-03: Qualify Lead with AI (Individual)")
    rows = [
        ["Use Case ID",     "UC-03"],
        ["Name",            "Qualify Lead with AI (Individual Re-qualification)"],
        ["Actor",           "Authenticated User (any role)"],
        ["Precondition",    "A lead record exists in the system and is accessible to the requesting user based on their role"],
        ["Trigger",         "User clicks the 'Re-qualify' button on a lead's detail view"],
        ["Main Flow",
         "1. System retrieves the full lead record from the database.\n"
         "2. Layer 1 (Anti-Junk): All 12 rejection rules are evaluated against the lead's fields.\n"
         "3. If no rule fires, Layer 2 (XGBoost): 37 features are extracted and the model produces a base score.\n"
         "4. Layer 3 (Gemini): The lead's key fields are sent to Google Gemini with a qualification prompt.\n"
         "   Gemini returns a quality assessment and score modifier.\n"
         "5. The base score is adjusted by the Gemini modifier to produce the final score.\n"
         "6. The lead's qualification_score and tier are updated in the database.\n"
         "7. A LeadActivity record is created logging the re-qualification event with old and new scores."],
        ["Alternative Flow A",
         "Step 2: If any anti-junk rule fires, the final score is set to 0, tier is set to 'Unqualified', "
         "and the disqualifying rule is logged. Layers 2, 3, and 4 are skipped."],
        ["Alternative Flow B",
         "Step 4: If Google Gemini is unavailable, Layer 4 (Groq) is invoked as fallback. "
         "If Groq also fails, the XGBoost base score is used as the final score without LLM adjustment."],
        ["Postcondition",   "The lead has an updated qualification_score and tier. A LeadActivity record documents the re-qualification."],
    ]
    T.styled_table(doc, headers, rows, col_widths=[Cm(3.2), Cm(11.1)])
    T.caption(doc, "Table 3.7 — Use Case: UC-03 Qualify Lead with AI")

    # UC-04
    T.subsection_h(doc, "3.7.4", "UC-04: Label Lead Outcome")
    rows = [
        ["Use Case ID",     "UC-04"],
        ["Name",            "Label Lead Outcome (QuickLabelBar)"],
        ["Actor",           "Authenticated User (any role)"],
        ["Precondition",    "A lead record exists and is accessible to the requesting user. The lead has not been previously labeled with the same outcome."],
        ["Trigger",         "User taps or clicks one of the four QuickLabelBar buttons on a lead's detail view"],
        ["Main Flow",
         "1. User selects an outcome: Converted, Replied, No Reply, or Not a Fit.\n"
         "2. System creates a LeadOutcome record with: lead_id, user_id, outcome type, and labeled_at timestamp.\n"
         "3. System updates the lead's status field to reflect the outcome (e.g., 'converted', 'replied').\n"
         "4. System creates a LeadActivity log entry describing the labeling action.\n"
         "5. The new outcome is queued to the ML retraining batch via Redis/Celery.\n"
         "6. The UI updates optimistically to show the selected outcome as active.\n"
         "7. If on mobile with no connectivity, the action is queued in AsyncStorage for replay on reconnection."],
        ["Alternative Flow A",
         "Step 7 (offline): When connectivity is restored, the queued action is replayed sequentially. "
         "If a conflict is detected (another user has already labeled the same lead), the server's "
         "version takes precedence and the mobile UI is updated accordingly."],
        ["Postcondition",   "A LeadOutcome record exists. Lead status reflects the outcome. The outcome is queued for ML retraining. Activity log updated."],
    ]
    T.styled_table(doc, headers, rows, col_widths=[Cm(3.2), Cm(11.1)])
    T.caption(doc, "Table 3.8 — Use Case: UC-04 Label Lead Outcome")

    # UC-05
    T.subsection_h(doc, "3.7.5", "UC-05: Export Leads to CSV")
    rows = [
        ["Use Case ID",     "UC-05"],
        ["Name",            "Export Leads to CSV"],
        ["Actor",           "Authenticated User (any role)"],
        ["Precondition",    "User is authenticated. At least one lead exists within the user's visible scope."],
        ["Trigger",         "User clicks the 'Export CSV' button with optional filters active"],
        ["Main Flow",
         "1. System reads the user's currently active filter parameters (status, score range, source, date range, industry).\n"
         "2. System queries the Leads table applying the same role-based visibility filter as the leads list.\n"
         "3. The result set is serialized to CSV format with all available lead fields as column headers.\n"
         "4. The CSV file is returned as a file download response with appropriate Content-Disposition headers.\n"
         "5. The user's browser or mobile app saves the file locally."],
        ["Alternative Flow A",
         "Step 2: If the filtered result set contains zero leads, the system returns an empty CSV file "
         "containing only the header row, with HTTP 200 OK."],
        ["Alternative Flow B",
         "Step 2: For very large result sets (>10,000 leads), the export is processed as a background "
         "Celery task and the user is notified via push notification when the file is ready for download."],
        ["Postcondition",   "A CSV file containing all leads matching the active filters and the user's role-scoped visibility is delivered to the user."],
    ]
    T.styled_table(doc, headers, rows, col_widths=[Cm(3.2), Cm(11.1)])
    T.caption(doc, "Table 3.9 — Use Case: UC-05 Export Leads to CSV")
