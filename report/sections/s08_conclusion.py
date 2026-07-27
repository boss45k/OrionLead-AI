"""
s08_conclusion.py — Chapter 8: Conclusion and Future Work
Target: 4-5 pages
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import theme as T


def build(doc):
    T.chapter_title(doc, 8, "Conclusion and Future Work")

    T.body(doc,
        "This final chapter summarizes the contributions of the OrionLead AI project, "
        "reflects on the extent to which the stated objectives were achieved, discusses "
        "the limitations encountered during development and evaluation, and outlines "
        "directions for future research and engineering work that would extend the "
        "system's capabilities.")

    # ── 8.1 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "8.1", "Summary of Achievements")

    T.body(doc,
        "OrionLead AI was designed to address the critical inefficiencies of manual "
        "B2B lead generation: slow sourcing, inconsistent qualification, and the "
        "absence of a unified interface for both desktop and mobile contexts. The "
        "project has fully delivered on this design intent, producing a production-"
        "ready system with the following concrete achievements.")

    T.body(doc,
        "A multi-source collection engine was built that queries Hunter.io, Apollo.io, "
        "People Data Labs, and Serper.dev in parallel, consolidating candidates into "
        "a single enriched pipeline. The natural-language query interface — powered "
        "by the Google Gemini LLM — translates a plain-English description of a "
        "target audience into structured API parameters, removing the need for users "
        "to understand each data source's query syntax.")

    T.body(doc,
        "The four-layer qualification cascade — Anti-Junk Rules, XGBoost ML, Gemini "
        "LLM, and Groq fallback — demonstrated a cross-validation accuracy of 76 % "
        "against a labeled dataset of 71 leads. The cascade's layered design ensures "
        "that computationally inexpensive rules are applied first, reserving the "
        "higher-cost LLM calls for candidates that pass structural validation. This "
        "produces qualification decisions that are both consistent and explainable: "
        "every lead's score is accompanied by a per-layer breakdown visible in the "
        "Lead Detail screen.")

    T.body(doc,
        "The Company-First Intelligence Pipeline extended the basic qualification "
        "architecture with seven specialized modules — anti_junk, website_auditor, "
        "business_classifier, growth_detector, account_scorer, contact_resolver, and "
        "intelligence_orchestrator — that evaluate the employer organization before "
        "resolving individual contacts. This inversion of the traditional contact-"
        "first approach eliminates a category of false positives in which a "
        "well-qualified individual is attached to an unsuitable company.")

    T.body(doc,
        "The web dashboard (React 18 + Ant Design 5) and mobile application (React "
        "Native 0.81.5 + Expo SDK 54) provide feature-equivalent access to the lead "
        "pipeline. Real-time synchronization between the MySQL backend and the mobile "
        "client is achieved through a Supabase PostgreSQL bridge with WebSocket "
        "subscriptions, eliminating the need for polling. Push notifications via "
        "Firebase Cloud Messaging alert mobile users to new hot leads and status "
        "changes in the field.")

    T.body(doc,
        "A role-based access control layer (Admin / Manager / User) enforces data "
        "visibility and action permissions consistently at the API layer. The QuickLabelBar "
        "component records four outcome labels — Converted, Replied, No Reply, Not a "
        "Fit — whose data feeds directly into the ML retraining pipeline, creating a "
        "closed feedback loop between field outcomes and model improvement.")

    T.body(doc,
        "On the engineering quality front, the project achieved 563 pytest tests "
        "executed in two parallel CI/CD jobs (SQLite for speed, MySQL 8.0 for parity), "
        "enforced via GitHub Actions with merge protection on the main branch. All "
        "25 functional requirements and 20 non-functional requirements defined in "
        "Chapter 3 were verified against their acceptance criteria.")

    # ── 8.2 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "8.2", "Objectives Revisited")

    T.body(doc,
        "The ten objectives stated in Section 1.4 are evaluated below against the "
        "delivered system.")

    items = [
        ("Automate B2B lead collection from multiple external APIs",
         "Delivered. Four live data sources with Celery-based parallel collection."),
        ("Apply AI qualification to every collected lead",
         "Delivered. Four-layer cascade applied to 100% of candidates before save."),
        ("Provide a natural-language collection interface",
         "Delivered. Gemini LLM parses user query into structured source parameters."),
        ("Implement role-based access control",
         "Delivered. Admin / Manager / User roles with @require_role decorators on all endpoints."),
        ("Build a responsive web dashboard",
         "Delivered. React + Ant Design dashboard with 11 screens tested across browsers."),
        ("Build a cross-platform mobile application",
         "Delivered. Expo-managed React Native app supporting iOS and Android, with dark mode."),
        ("Implement real-time data synchronization",
         "Delivered. Supabase WebSocket bridge with < 2 s end-to-end latency."),
        ("Record lead outcomes and feed them back to the ML model",
         "Delivered. QuickLabelBar stores LeadOutcome records used in XGBoost retraining."),
        ("Provide analytics visibility across the lead pipeline",
         "Delivered. Four Chart.js charts on web, react-native-chart-kit on mobile."),
        ("Meet non-functional targets for latency, uptime, and security",
         "Delivered. API p95 < 400 ms, 99.8 % uptime in staging, OWASP Top 10 mitigated."),
    ]
    for i, (obj, result) in enumerate(items, 1):
        T.numbered(doc, i, f"{obj} — {result}")

    # ── 8.3 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "8.3", "Limitations")

    T.body(doc,
        "Despite meeting all stated objectives, OrionLead AI has several limitations "
        "that are important to acknowledge honestly.")

    T.subsection_h(doc, "8.3.1", "Training Dataset Size")
    T.body(doc,
        "The XGBoost model was trained on 71 labeled leads — a dataset that is "
        "sufficient for a proof-of-concept but small by production ML standards. "
        "The 76 % cross-validation accuracy, while promising, has a wide confidence "
        "interval at this sample size. Model performance on industry segments or "
        "geographic regions not represented in the training set is unknown. Sustained "
        "use of the QuickLabelBar will grow the labeled set, and periodic retraining "
        "is expected to improve accuracy materially over the first several months of "
        "production operation.")

    T.subsection_h(doc, "8.3.2", "API Rate Limits and Cost")
    T.body(doc,
        "The collection engine depends on four commercial APIs (Hunter.io, Apollo.io, "
        "People Data Labs, Serper.dev) and two AI inference APIs (Google Gemini, Groq). "
        "Each carries rate limits and per-request costs that are not within the system's "
        "control. A high-volume collection job can exhaust monthly API quotas, temporarily "
        "disabling a source. The current implementation handles this gracefully by "
        "degrading to available sources, but it cannot substitute for a missing source's "
        "data coverage. Organizations considering production deployment should budget "
        "for API costs as a function of monthly collection volume.")

    T.subsection_h(doc, "8.3.3", "Real-Time Sync Dependency on Supabase")
    T.body(doc,
        "The mobile real-time synchronization architecture relies on the Supabase "
        "PostgreSQL bridge as an intermediary layer between the MySQL primary database "
        "and mobile WebSocket clients. This introduces a third-party dependency in the "
        "critical path for mobile data freshness. If the Supabase bridge experiences "
        "downtime, the mobile application falls back to pull-based refresh, which "
        "introduces latency but does not break core functionality. A fully self-hosted "
        "architecture would eliminate this dependency at the cost of additional "
        "infrastructure complexity.")

    T.subsection_h(doc, "8.3.4", "Absence of CRM Integration")
    T.body(doc,
        "The current system operates as a standalone lead management platform. It does "
        "not natively integrate with CRM systems such as HubSpot, Salesforce, or Zoho. "
        "Leads must be exported as CSV and imported manually into a downstream CRM. "
        "For organizations that use a CRM as their primary sales workflow tool, this "
        "creates a data handoff step that reduces the value of the automation.")

    T.subsection_h(doc, "8.3.5", "Email Verification Coverage")
    T.body(doc,
        "Email verification is performed via ZeroBounce on leads with a real email "
        "address. However, a fraction of leads collected from Serper.dev and People "
        "Data Labs arrive without an email address, relying solely on LinkedIn URL "
        "or phone for contact. These leads receive a qualification score and tier "
        "assignment but cannot be verified for deliverability, which reduces their "
        "actionability for email outreach campaigns.")

    # ── 8.4 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "8.4", "Future Work")

    T.body(doc,
        "The following eight directions represent the most impactful extensions to "
        "OrionLead AI identified during the project. They are ordered roughly by "
        "implementation effort, from lowest to highest.")

    T.subsection_h(doc, "8.4.1", "CRM Integration via Webhooks")
    T.body(doc,
        "A webhook-based outbound integration layer would allow OrionLead AI to push "
        "newly qualified leads directly to HubSpot, Salesforce, or Pipedrive without "
        "manual CSV export. This would require adding an Integrations configuration "
        "panel to the admin dashboard and a background task that serializes leads "
        "matching a user-defined score threshold into the target CRM's API format. "
        "Zapier or Make.com compatibility would extend this to hundreds of downstream "
        "tools with minimal additional development.")

    T.subsection_h(doc, "8.4.2", "Continuous ML Retraining Pipeline")
    T.body(doc,
        "The current retraining workflow is manual: a developer runs the training "
        "script after accumulating new QuickLabelBar outcomes. A fully automated "
        "retraining pipeline would monitor the LeadOutcome table for a configurable "
        "number of new labels, trigger a Celery retraining task when the threshold "
        "is reached, evaluate the new model against a held-out validation set, and "
        "promote it to production only if it improves on the current model's F1 "
        "score. This would transform the ML component from a static artifact into "
        "a continually improving system.")

    T.subsection_h(doc, "8.4.3", "Sequence Intelligence and Multi-Touch Scoring")
    T.body(doc,
        "The current qualification model scores each lead in isolation at the moment "
        "of collection. A multi-touch scoring model would incorporate post-collection "
        "signals — email opens (via tracking pixel), LinkedIn connection responses, "
        "website visit events (via UTM-tagged links) — to update a lead's score "
        "dynamically over time. This would shift OrionLead AI from a collection-time "
        "qualification tool to a full sales-cycle intelligence platform.")

    T.subsection_h(doc, "8.4.4", "LinkedIn Organic Collection Module")
    T.body(doc,
        "The current data sources cover API-accessible databases. A LinkedIn-native "
        "collection module — using LinkedIn's Official Marketing API or a compliant "
        "browser automation approach — would add the largest professional network as "
        "a data source. Given LinkedIn's strict Terms of Service, this module would "
        "require careful implementation within the permitted API scope, focusing on "
        "Company Pages and lead gen form integrations rather than profile scraping.")

    T.subsection_h(doc, "8.4.5", "Explainable AI Score Breakdown")
    T.body(doc,
        "The XGBoost model produces a single qualification score but does not "
        "currently surface per-feature contribution values to the end user. Integrating "
        "SHAP (SHapley Additive exPlanations) values into the qualification response "
        "would allow the Lead Detail screen to display a ranked list of the specific "
        "features that most influenced each lead's score — for example, 'seniority "
        "level contributed +12 points; missing email reduced score by 8 points.' "
        "This would increase user trust in the model and guide manual enrichment "
        "efforts toward the most impactful missing fields.")

    T.subsection_h(doc, "8.4.6", "Team Collaboration Features")
    T.body(doc,
        "The current RBAC model defines roles but does not support team-based lead "
        "assignment workflows. Future work could introduce a lead assignment system "
        "where managers assign leads to specific sales representatives, track "
        "per-representative conversion rates, and receive aggregated performance "
        "reports. An in-app notification system — distinct from the mobile push "
        "notifications — would alert representatives to newly assigned leads and "
        "approaching follow-up deadlines.")

    T.subsection_h(doc, "8.4.7", "Advanced Analytics and Predictive Forecasting")
    T.body(doc,
        "The current analytics dashboard provides descriptive metrics (counts, "
        "distributions, trends). A predictive analytics extension would use historical "
        "collection and conversion data to forecast pipeline health: predicted "
        "conversions in the next 30 days, estimated deal value weighted by tier "
        "and industry, and alerts when the collection rate drops below the level "
        "needed to achieve a monthly conversion target. These forecasts would "
        "transform the analytics screen from a reporting tool into a sales planning "
        "instrument.")

    T.subsection_h(doc, "8.4.8", "Self-Hosted Deployment Package")
    T.body(doc,
        "The current deployment assumes cloud hosting with managed services. A "
        "self-hosted deployment package — comprising Docker Compose configuration, "
        "a Helm chart for Kubernetes, and a setup wizard for API key configuration "
        "— would make OrionLead AI accessible to organizations with data residency "
        "requirements that prohibit cloud-hosted lead data. The Supabase bridge "
        "dependency would be replaced by a self-hosted Postgres replica with the "
        "Supabase Realtime server running in the same Docker network.")

    # ── 8.5 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "8.5", "Closing Remarks")

    T.body(doc,
        "OrionLead AI demonstrates that modern AI capabilities — large language models, "
        "gradient boosting, structured data enrichment APIs — can be combined into a "
        "practical, deployable system that delivers measurable value for B2B sales "
        "teams. The architecture is intentionally modular: each layer of the "
        "qualification cascade, each data source adapter, and each frontend application "
        "can be extended or replaced independently without restructuring the system.")

    T.body(doc,
        "The project also illustrates the engineering discipline required to build "
        "AI-powered applications responsibly: test coverage that reaches the data "
        "layer, explicit fallback paths when external services fail, role-based "
        "access enforcement at the API boundary, and a feedback loop that connects "
        "field outcomes back to model training. These practices are as important as "
        "the AI components themselves in producing a system that is trustworthy in "
        "production.")

    T.body(doc,
        "The limitations identified in Section 8.3 — dataset size, API dependencies, "
        "and the absence of CRM integration — are engineering challenges with clear "
        "solution paths, not fundamental constraints on the approach. The future work "
        "directions in Section 8.4 represent a roadmap for evolving OrionLead AI from "
        "a graduation project into a commercially viable product. The foundation built "
        "in this project is designed to support that evolution.")
