"""
s01_intro.py — Chapter 1: Introduction
Target: 9-10 pages
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import theme as T


def build(doc):
    T.chapter_title(doc, 1, "Introduction")

    T.section_h(doc, "1.1", "Background and Motivation")
    T.body(doc,
        "In the modern business landscape, identifying and acquiring high-quality sales "
        "leads is one of the most critical and time-consuming activities a company "
        "undertakes. For B2B (Business-to-Business) organizations — those that sell "
        "products or services to other companies rather than individual consumers — the "
        "quality and relevance of leads directly determines the efficiency of the entire "
        "sales pipeline and ultimately drives revenue growth. A sales team that works "
        "with well-qualified, accurately scored prospects can close deals faster, allocate "
        "resources more effectively, and generate significantly better return on investment "
        "from their sales activities.")

    T.body(doc,
        "Historically, B2B lead generation was performed entirely through manual research. "
        "Sales development representatives (SDRs) would spend hours — sometimes entire "
        "working days — browsing professional networks such as LinkedIn, industry "
        "directories like Clutch.co, G2, and Crunchbase, corporate websites, and trade "
        "publication attendee lists in order to identify potential customers. Each contact "
        "found was then manually researched, assessed for relevance, and logged into a "
        "spreadsheet or customer relationship management (CRM) system. This process is "
        "not only extraordinarily time-intensive but also deeply inconsistent, as the "
        "quality of leads produced varies dramatically depending on the individual "
        "researcher's experience, judgment, and industry familiarity.")

    T.body(doc,
        "In competitive markets where response time to emerging opportunities is critical, "
        "manual lead generation processes simply cannot keep pace with the volume, speed, "
        "and precision required. A startup entering a new geographic market, a SaaS "
        "company expanding into an adjacent industry, or an agency seeking enterprise "
        "clients — all face the same fundamental constraint: the number of qualified "
        "prospects they can engage is bounded by the capacity of their research team, "
        "not by the true size of their addressable market.")

    T.body(doc,
        "The emergence and rapid maturation of artificial intelligence (AI), machine "
        "learning (ML), and large language models (LLMs) has created an unprecedented "
        "opportunity to transform lead generation from a manual, subjective, and "
        "resource-constrained process into an automated, data-driven, and highly "
        "accurate system. By leveraging AI, organizations can now collect leads from "
        "multiple sources simultaneously, evaluate their quality against dozens of "
        "criteria in milliseconds, and surface only the most promising prospects to "
        "human sales teams — freeing those teams to focus entirely on what humans do "
        "best: building relationships and closing deals.")

    T.body(doc,
        "The convergence of several enabling technologies in recent years has made this "
        "vision practically achievable at relatively low cost. The commercial availability "
        "of powerful B2B data APIs (Hunter.io, Apollo.io, People Data Labs), the "
        "accessibility of gradient-boosted machine learning frameworks (XGBoost, "
        "LightGBM), the emergence of general-purpose LLM APIs (Google Gemini, OpenAI "
        "GPT, Groq Llama), and the maturation of cross-platform mobile development tools "
        "(React Native, Expo) have collectively lowered the barriers to building "
        "sophisticated AI-powered sales tools to the point where a motivated individual "
        "developer can build and deploy a production-grade system.")

    T.body(doc,
        "OrionLead AI was conceived precisely to leverage this convergence. It represents "
        "a complete reimagining of the B2B lead generation workflow, built from the ground "
        "up to place artificial intelligence at the center of every decision — from "
        "initial lead discovery and multi-source aggregation, through intelligent "
        "qualification and scoring, to real-time team management and continuous model "
        "improvement through outcome feedback. The system is designed not merely as an "
        "academic proof-of-concept but as a production-ready platform capable of "
        "delivering immediate, measurable value to real sales organizations.")

    T.section_h(doc, "1.2", "Problem Statement")
    T.body(doc,
        "Organizations involved in B2B sales face several critical and interconnected "
        "challenges with traditional lead generation approaches. These challenges "
        "collectively represent a significant drag on sales productivity, pipeline quality, "
        "and ultimately revenue outcomes. The following five problems are the core "
        "deficiencies that OrionLead AI was designed to address:")

    T.bullet(doc,
        "Sales teams collect large numbers of contacts from mass-collection "
        "tools and purchased lists, but receive no systematic mechanism to distinguish "
        "genuine business prospects from fake entries, duplicate records, personal "
        "accounts misclassified as business contacts, or contacts with no relevant "
        "purchase intent. The result is pipeline pollution: sales representatives waste "
        "hours pursuing contacts that were never viable prospects.",
        bold_prefix="Volume without quality:")

    T.bullet(doc,
        "Even when leads are collected, evaluating their potential "
        "requires significant human judgment applied consistently across hundreds or "
        "thousands of contacts. Without systematic, quantitative qualification criteria, "
        "decisions are inconsistent across team members, biased by individual "
        "experience gaps, and impossible to scale. A senior salesperson cannot manually "
        "evaluate and score 500 new leads per week while also managing their active "
        "pipeline.",
        bold_prefix="Manual qualification bottleneck:")

    T.bullet(doc,
        "Lead information is scattered across multiple tools — "
        "CRM systems, spreadsheets, LinkedIn exports, email enrichment platforms, "
        "browser bookmarks — with no unified view of a contact's complete profile. "
        "Teams waste substantial time switching between tools, reconciling inconsistent "
        "data from multiple sources, and manually merging duplicate entries that "
        "represent the same person discovered through different channels.",
        bold_prefix="Data fragmentation:")

    T.bullet(doc,
        "Traditional lead generation systems do not learn from real-world "
        "outcomes. Whether a specific lead converted into a paying customer, replied "
        "positively to outreach, ignored all contact attempts, or turned out to be "
        "entirely irrelevant is rarely captured in a way that systematically improves "
        "future collection and scoring. The same patterns of low-quality leads recur "
        "indefinitely because no feedback loop connects outcomes to collection strategy.",
        bold_prefix="No learning feedback loop:")

    T.bullet(doc,
        "Modern sales professionals are increasingly mobile, conducting "
        "research, managing prospects, and closing deals from smartphones and tablets "
        "while traveling, in client meetings, or working remotely. Traditional lead "
        "management platforms are desktop-centric, forcing field teams to use laptops "
        "for any meaningful interaction with their pipeline or lose access entirely when "
        "away from the office.",
        bold_prefix="Mobile inaccessibility:")

    T.body(doc,
        "A sixth, more subtle problem compounds all of the above: most tools focus "
        "exclusively on individual contact data without first evaluating the "
        "characteristics of the target company. A technically valid contact — correct "
        "email format, verified deliverability, genuine business role — at a company "
        "that is dormant, misaligned with the seller's ideal customer profile, or "
        "operating in an irrelevant industry consumes exactly as much sales effort as a "
        "perfect prospect. Without company-level intelligence as a prerequisite filter, "
        "teams expend significant resources on contacts that were never going to convert "
        "regardless of contact quality.")

    T.section_h(doc, "1.3", "Proposed Solution")
    T.body(doc,
        "OrionLead AI proposes a unified, AI-first platform that addresses each of the "
        "identified challenges through a tightly integrated architecture of intelligent "
        "components working together as a coordinated system rather than as isolated tools.")

    T.body(doc,
        "At the core of the solution is a four-layer AI qualification cascade. This "
        "cascade processes every candidate lead through four sequential evaluation stages: "
        "a deterministic anti-junk rule engine (12 hard-reject rules for instant "
        "disqualification of obviously invalid contacts), a trained XGBoost machine "
        "learning model (37 engineered features producing a base qualification score), "
        "a Google Gemini large language model (contextual reasoning about role seniority, "
        "company relevance, and industry fit), and a Groq fallback LLM (activated when "
        "Gemini is unavailable). This cascade architecture balances cost, speed, and "
        "accuracy by routing only uncertain or complex cases to progressively more "
        "capable and expensive evaluation layers.")

    T.body(doc,
        "Complementing the qualification cascade is a Company-First Intelligence "
        "Pipeline that evaluates seven organizational signals — website quality, "
        "business classification, growth indicators, account score, and contact "
        "resolution — before individual contacts are admitted to the pipeline. This "
        "ensures that only contacts at companies meeting minimum quality thresholds "
        "consume qualification resources, dramatically improving the signal-to-noise "
        "ratio of the collected lead pool.")

    T.body(doc,
        "A multi-source collection engine aggregates lead data from up to eight "
        "external APIs simultaneously (Hunter.io, Apollo.io, People Data Labs, "
        "Serper.dev, Google Places, ZeroBounce, Google Gemini, and Groq), with "
        "intelligent deduplication through a SeenContacts tracking mechanism, "
        "validation, and enrichment applied at ingestion time before any AI processing "
        "begins. Natural language queries entered by users are analyzed by the Gemini "
        "AI before collection begins, generating optimized search parameters tailored "
        "to each data source's specific API capabilities.")

    T.body(doc,
        "A QuickLabelBar component captures real-world lead outcomes with a single "
        "interaction — Converted, Replied, No Reply, or Not a Fit — feeding a "
        "continuous ML retraining loop that improves the XGBoost model's accuracy "
        "over time as labeled outcome data accumulates. This closes the feedback loop "
        "that is absent from virtually all commercial lead generation tools.")

    T.body(doc,
        "A cross-platform delivery architecture ensures that the platform serves both "
        "office-based team managers (through a full-featured React 18 web dashboard) "
        "and field sales professionals (through a React Native mobile application with "
        "offline-first synchronization). Both interfaces connect to the same Flask "
        "backend in real time via REST APIs and Supabase real-time subscriptions, "
        "ensuring that data is always consistent regardless of which platform a user "
        "accesses.")

    T.section_h(doc, "1.4", "Project Objectives")
    T.body(doc,
        "The primary objectives of OrionLead AI are formally stated as follows:")

    T.numbered(doc, 1,
        "Automate lead discovery by integrating with multiple commercial and open data "
        "APIs to collect business contacts at scale without manual research effort, "
        "using AI-optimized search parameters derived from natural language user queries.")

    T.numbered(doc, 2,
        "Eliminate junk leads at the earliest possible stage through a 12-rule "
        "anti-junk engine that hard-rejects fake names, personal email domains, "
        "invalid phone number formats, placeholder values, and other disqualifying "
        "signals before any ML or LLM processing is invoked.")

    T.numbered(doc, 3,
        "Score and rank leads automatically and consistently using a trained XGBoost "
        "model with 37 features, producing a deterministic 0–100 qualification score "
        "that categorizes every lead into one of four actionable tiers: Hot (≥80), "
        "Warm (≥60), Cold (≥30), or Unqualified (<30).")

    T.numbered(doc, 4,
        "Apply natural language intelligence through Google Gemini and Groq LLMs to "
        "evaluate lead quality dimensions that cannot be captured by structured features "
        "alone — including role seniority signals, company description relevance, "
        "contextual industry fit, and buying intent indicators present in unstructured text.")

    T.numbered(doc, 5,
        "Evaluate company-level quality signals before resolving individual contacts, "
        "ensuring that the system invests qualification resources only in contacts at "
        "organizations that meet minimum relevance, authenticity, and growth thresholds.")

    T.numbered(doc, 6,
        "Provide a complete lead management workflow including manual creation, "
        "AI-driven enrichment, status tracking, activity logging, outcome labeling, "
        "team-based visibility controls, CSV export, and full-text search.")

    T.numbered(doc, 7,
        "Deliver real-time analytics showing collection trends, score distributions, "
        "source performance, conversion rates, and ML model accuracy metrics to "
        "management and administrators at the appropriate scope for their role.")

    T.numbered(doc, 8,
        "Enable mobile-first field access through a React Native application with "
        "offline action queuing, push notifications via Firebase Cloud Messaging, "
        "and real-time synchronization via Supabase, ensuring field sales professionals "
        "maintain full pipeline access regardless of connectivity status.")

    T.numbered(doc, 9,
        "Support organizational scaling through role-based access control (Admin, "
        "Manager, User) that segregates lead visibility by collector, elevates "
        "aggregated views for managers, and provides complete system access for "
        "administrators — all enforced at the API layer.")

    T.numbered(doc, 10,
        "Implement a continuous improvement loop that captures real-world lead outcome "
        "labels from the QuickLabelBar, persists them to a dedicated LeadOutcomes table, "
        "and feeds them into periodic XGBoost model retraining jobs executed via Celery "
        "background workers.")

    T.section_h(doc, "1.5", "Project Scope")
    T.body(doc,
        "The scope of OrionLead AI defines the boundaries of what is and is not "
        "included in this project. These boundaries were determined based on time "
        "constraints, available resources, and the prioritization of core functionality "
        "over peripheral features.")

    T.subsection_h(doc, "1.5.1", "In Scope")
    T.bullet(doc, "Full-stack platform with Flask RESTful backend, React 18 web frontend, and React Native mobile application")
    T.bullet(doc, "Four-layer AI qualification cascade (Anti-Junk → XGBoost → Gemini → Groq)")
    T.bullet(doc, "Company-First Intelligence Pipeline with seven evaluation modules")
    T.bullet(doc, "Integration with eight external data and AI APIs")
    T.bullet(doc, "Role-based user management (Admin, Manager, User) with JWT authentication")
    T.bullet(doc, "Complete lead lifecycle management from collection to outcome labeling")
    T.bullet(doc, "Real-time synchronization between web and mobile platforms via Supabase")
    T.bullet(doc, "Offline-first mobile operation with AsyncStorage action queue")
    T.bullet(doc, "Push notification delivery via Firebase Cloud Messaging")
    T.bullet(doc, "Automated CI/CD pipeline with 563 pytest tests on GitHub Actions")
    T.bullet(doc, "Dark and light mode theming across all interfaces")
    T.bullet(doc, "CSV export with configurable filters")
    T.bullet(doc, "Interactive API documentation via Swagger/Flasgger")
    T.bullet(doc, "SeenContacts deduplication to prevent duplicate lead ingestion")

    T.subsection_h(doc, "1.5.2", "Out of Scope")
    T.bullet(doc, "Native CRM integration with third-party platforms (Salesforce, HubSpot, Pipedrive)")
    T.bullet(doc, "Email campaign execution or marketing automation within the platform")
    T.bullet(doc, "Video calling, screen sharing, or real-time meeting features")
    T.bullet(doc, "Payment processing, subscription billing, or multi-tenant SaaS infrastructure")
    T.bullet(doc, "Full multi-language internationalization beyond English interface and Arabic label support")
    T.bullet(doc, "Native iOS/Android binary publishing to App Store or Google Play")
    T.bullet(doc, "ERP or accounting system integration")

    T.section_h(doc, "1.6", "Report Organization")
    T.body(doc,
        "This report is organized into eight chapters, each addressing a distinct phase "
        "of the software engineering lifecycle applied to OrionLead AI. The structure "
        "follows the conventions established by the Faculty of Engineering at the "
        "Islamic University of Lebanon and mirrors the development lifecycle of the "
        "system itself.")

    T.body(doc,
        "Chapter 2 presents the literature review, critically examining existing academic "
        "research and commercial systems in the domains of B2B lead generation, machine "
        "learning-based lead scoring, LLM applications in sales, and the identified "
        "research gaps that motivated this project.")

    T.body(doc,
        "Chapter 3 covers system analysis, defining all external entities that interact "
        "with the system, specifying user roles and permission boundaries, enumerating "
        "functional and non-functional requirements, and illustrating system behavior "
        "through Data Flow Diagrams and Use Case Diagrams with detailed descriptions.")

    T.body(doc,
        "Chapter 4 describes the complete system design and architecture, covering the "
        "three-tier architecture overview, backend Blueprint structure, AI engine design "
        "with cascade details, web and mobile frontend architectures, full database "
        "schema with entity-relationship diagram, security architecture, and all external "
        "API integrations.")

    T.body(doc,
        "Chapter 5 explains the implementation details across all system components, "
        "including the complete technology stacks for backend, web, and mobile, "
        "backend service and route implementations, AI engine feature engineering and "
        "anti-junk rule details, mobile component architecture, and the real-time "
        "synchronization pipeline.")

    T.body(doc,
        "Chapter 6 presents the testing and evaluation results, covering the three-level "
        "testing strategy, 30 functional test cases across authentication, lead "
        "management, and AI qualification domains, API endpoint test results with "
        "response time measurements, non-functional performance and security test "
        "outcomes, and the CI/CD pipeline configuration.")

    T.body(doc,
        "Chapter 7 displays the system's user interface through detailed descriptions "
        "of all key screens across both the web dashboard and mobile application, "
        "including screenshots with explanatory captions covering authentication flows, "
        "lead management, analytics dashboards, AI collection, and dark mode rendering.")

    T.body(doc,
        "Chapter 8 concludes the report with a summary of achieved objectives, a "
        "quantified list of technical accomplishments, an honest assessment of current "
        "limitations, and eight concrete proposals for future development that build "
        "directly on the platform's existing architecture.")
