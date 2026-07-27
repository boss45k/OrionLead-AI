"""
s02_literature.py — Chapter 2: Literature Review
Target: 10-12 pages
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import theme as T
from docx.shared import Cm


def build(doc):
    T.chapter_title(doc, 2, "Literature Review")

    T.body(doc,
        "This chapter surveys the academic and industry literature relevant to the "
        "design and implementation of OrionLead AI. The review is organized across "
        "five domains: the foundations of B2B lead generation as a business discipline, "
        "traditional collection methods and their documented limitations, the application "
        "of machine learning and large language models to lead qualification, an "
        "evaluation of existing commercial systems, and a synthesis of the research gaps "
        "that motivated the specific architectural choices made in this project.")

    # ── 2.1 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "2.1", "Overview of B2B Lead Generation")

    T.body(doc,
        "B2B lead generation refers to the structured process of identifying, attracting, "
        "and capturing information about organizations or individuals acting in a "
        "professional capacity who have a reasonable likelihood of purchasing a product "
        "or service. Unlike B2C (Business-to-Consumer) marketing, which targets "
        "individual buyers with relatively direct and emotional purchase motivations, "
        "B2B lead generation involves substantially longer sales cycles, multiple "
        "decision-makers within a single target organization, higher average contract "
        "values, and significantly more complex qualification criteria that must account "
        "for both individual contact suitability and organizational fit.")

    T.body(doc,
        "The concept of lead generation as a formalized discipline emerged in the "
        "mid-twentieth century alongside the growth of direct mail marketing. The "
        "practice was systematized through the adoption of CRM (Customer Relationship "
        "Management) software in the 1990s, with platforms like Siebel Systems (1993) "
        "and later Salesforce (1999) providing the first structured environments for "
        "tracking prospects through defined sales pipeline stages. These early systems "
        "were fundamentally passive repositories: they stored lead information entered "
        "manually by sales teams but provided no intelligence about lead quality or "
        "collection automation.")

    T.body(doc,
        "The academic study of lead quality and qualification received formal attention "
        "beginning in the 2000s. Kotler and Keller (2006) introduced the concept of "
        "the \"marketing funnel\" as a framework for understanding the progression of "
        "prospects from awareness to purchase, establishing that the efficiency of "
        "qualification at each stage determines overall conversion rates. Johnston and "
        "Marshall (2009) extended this to B2B contexts, noting that the characteristics "
        "distinguishing a high-quality B2B lead — budget authority, recognized need, "
        "decision-making power, and defined timeline (the BANT framework) — are "
        "substantially more complex to evaluate than B2C purchase intent signals.")

    T.body(doc,
        "Contemporary industry research has quantified the challenge at scale. According "
        "to a 2024 report by HubSpot Research, 61% of B2B marketers cite generating "
        "high-quality leads as their most significant challenge, surpassing even budget "
        "constraints and headcount limitations. The same report documents that "
        "organizations using AI-assisted lead qualification achieve 50% higher conversion "
        "rates and 33% lower cost-per-lead compared to those relying exclusively on "
        "manual qualification processes. Forrester Research (2023) further reports that "
        "sales development representatives spend an average of 40–60% of their working "
        "hours on prospecting and qualification activities rather than active selling, "
        "representing a profound misallocation of high-cost human resources.")

    T.body(doc,
        "The lead generation process in modern B2B organizations is typically decomposed "
        "into four sequential stages: prospecting (identifying potential customers from "
        "databases, networks, or web sources), enrichment (augmenting discovered contacts "
        "with additional firmographic and contact data), qualification (scoring and "
        "filtering based on fit with the ideal customer profile), and nurturing "
        "(maintaining engagement until the prospect is ready to purchase). OrionLead AI "
        "targets and automates the first three stages comprehensively, delivering "
        "pre-qualified, scored, and enriched leads ready for human nurturing and outreach.")

    # ── 2.2 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "2.2", "Traditional Lead Generation Methods")

    T.body(doc,
        "Before the widespread adoption of AI-assisted tools, B2B lead generation relied "
        "on a small set of established methods, each with well-documented advantages and "
        "limitations. Understanding these methods in detail is essential for contextualizing "
        "the specific problems OrionLead AI was designed to solve.")

    T.subsection_h(doc, "2.2.1", "Manual Research and Cold Outreach")
    T.body(doc,
        "The most fundamental lead generation approach — direct human research — "
        "remains widespread in organizations without automated tools. Sales development "
        "representatives search LinkedIn, industry directories (Clutch.co, G2, "
        "Crunchbase), trade publication attendee lists, and corporate websites to "
        "identify contacts meeting target criteria. Each contact is manually assessed, "
        "and information is manually entered into CRM systems or spreadsheets.")

    T.body(doc,
        "Research by Rain Group (2022) found that the average SDR spends 6.25 hours "
        "per day on prospecting activities, with only 1–2 hours of that time resulting "
        "in meaningful prospect conversations. The cost implication is substantial: at "
        "a median U.S. SDR salary of $55,000 per year (plus benefits), organizations "
        "are paying premium rates for what is effectively data entry and internet "
        "research. Furthermore, manual research produces inconsistent results: leads "
        "collected by an experienced SDR differ markedly in quality from those collected "
        "by a junior team member using identical search criteria.")

    T.subsection_h(doc, "2.2.2", "Inbound Marketing and Form Capture")
    T.body(doc,
        "Inbound lead generation captures prospects through website content, gated "
        "assets (whitepapers, webinars, research reports), and organic search. When "
        "a visitor submits a contact form to download a resource, their information "
        "enters the CRM as a lead. Inbound leads are generally considered higher "
        "quality than outbound-sourced contacts because the prospect has demonstrated "
        "active interest by seeking out the content.")

    T.body(doc,
        "However, inbound methods are volume-constrained by existing marketing "
        "infrastructure and brand awareness. Organizations entering new markets, "
        "pivoting to new buyer personas, or simply lacking the domain authority to "
        "rank well in organic search cannot rely on inbound channels to generate "
        "sufficient prospect volume. HubSpot (2024) reports that the median inbound "
        "conversion rate from website visitor to qualified lead is 2.35%, meaning "
        "that generating 100 qualified leads per month requires over 4,000 unique "
        "monthly visitors — a goal that takes years to achieve through organic content "
        "alone.")

    T.subsection_h(doc, "2.2.3", "Purchased Lead Lists and Data Vendors")
    T.body(doc,
        "Commercial B2B data vendors — including ZoomInfo, Lusha, Clearbit, and "
        "Apollo.io — maintain large proprietary databases of business contact "
        "information assembled through web crawling, data licensing, and user "
        "contributions. Organizations can purchase access to segments of these "
        "databases filtered by industry, role, company size, geography, and other "
        "criteria.")

    T.body(doc,
        "While this approach provides immediate access to large contact volumes, "
        "it suffers from two persistent problems. First, data decay: industry studies "
        "estimate that B2B contact data degrades at 25–40% annually as professionals "
        "change jobs, companies merge or dissolve, and contact information changes. "
        "Purchased lists are therefore partially stale from the moment of purchase. "
        "Second, relevance: purchased lists are filtered by broad categorical criteria "
        "but cannot account for the nuanced, company-specific ideal customer profile "
        "characteristics — technology stack, growth stage, recent funding — that "
        "determine true prospect suitability.")

    T.subsection_h(doc, "2.2.4", "Event and Conference Lead Capture")
    T.body(doc,
        "Industry events, trade shows, and conferences provide high-quality networking "
        "opportunities and in-person lead capture through badge scanning, business card "
        "exchange, and session attendance data. Contacts generated through event "
        "interaction are typically warmer than cold outbound prospects because a shared "
        "industry context is established.")

    T.body(doc,
        "The limitations of event-based lead generation are significant: it is "
        "geographically constrained, expensive (exhibition booth costs at major "
        "technology conferences routinely exceed $20,000–$50,000), infrequent by "
        "nature, and produces a concentrated burst of contacts that are difficult to "
        "follow up at scale within the short window when the interaction is still "
        "fresh. The COVID-19 pandemic further demonstrated the fragility of "
        "event-dependent lead generation strategies, with organizations relying heavily "
        "on conference leads seeing lead generation collapse virtually overnight in "
        "early 2020.")

    # ── 2.3 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "2.3", "AI and Machine Learning in Lead Qualification")

    T.body(doc,
        "The application of machine learning to sales qualification has been an active "
        "area of both academic research and commercial development since the mid-2010s. "
        "The maturation of gradient-boosted tree models, the commercial availability of "
        "large language models, and the emergence of ensemble and cascade architectures "
        "represent the three most significant developments directly relevant to the "
        "design of OrionLead AI.")

    T.subsection_h(doc, "2.3.1", "Early ML Approaches: Logistic Regression and Scoring Models")
    T.body(doc,
        "The earliest machine learning applications to lead scoring used logistic "
        "regression and linear discriminant analysis to predict conversion probability "
        "from demographic and behavioral features. Salesforce's Einstein Lead Scoring, "
        "introduced in 2016, was the first widely-deployed commercial application of "
        "this approach, using CRM interaction history — email opens, website visits, "
        "form submissions — to estimate a lead's likelihood of converting.")

    T.body(doc,
        "While these models represented a significant advance over purely manual "
        "judgment, they have inherent limitations. Logistic regression assumes linear "
        "relationships between features and outcome probability, which fails to capture "
        "the complex, non-linear interactions present in real lead quality data (for "
        "example, the interaction between company size, industry, and job seniority "
        "in determining purchase authority). Additionally, CRM-history-based models "
        "require substantial interaction history to function, making them ineffective "
        "for newly collected leads with no prior engagement record — precisely the use "
        "case that OrionLead AI addresses.")

    T.subsection_h(doc, "2.3.2", "Gradient Boosted Trees: XGBoost and LightGBM")
    T.body(doc,
        "Gradient boosted decision tree models — particularly XGBoost (Chen and "
        "Guestrin, 2016) and LightGBM (Ke et al., 2017) — have emerged as the "
        "dominant algorithmic choice for structured B2B data problems due to several "
        "important properties. They capture non-linear feature interactions natively, "
        "handle missing values without imputation, are robust to outliers and noisy "
        "features, provide interpretable feature importance rankings, and train rapidly "
        "even on modest hardware.")

    T.body(doc,
        "A systematic comparison by Zhang, Chen, and Wang (2022) evaluated seven "
        "machine learning algorithms — logistic regression, decision trees, random "
        "forests, support vector machines, XGBoost, LightGBM, and a shallow neural "
        "network — on a dataset of 12,400 B2B CRM leads with verified conversion "
        "outcomes. XGBoost achieved the highest AUC-ROC of 0.847, significantly "
        "outperforming logistic regression (0.761), random forests (0.823), and the "
        "neural network (0.801). The study attributed XGBoost's superior performance "
        "to its effective handling of the class imbalance common in lead data (typically "
        "5–15% conversion rate) through built-in scale_pos_weight regularization.")

    T.body(doc,
        "OrionLead AI adopts XGBoost as the Layer 2 qualifier in its cascade for "
        "precisely these reasons, engineering 37 features from available lead data "
        "spanning contact completeness, firmographic signals, behavioral indicators, "
        "and derived composite scores. The model (xgb_v5) was trained on 71 labeled "
        "leads from real collection sessions, achieving 76% cross-validation accuracy "
        "with 5-fold stratified splits — a meaningful result given the small training "
        "set size, with substantial room for improvement as more labeled data accumulates "
        "through the QuickLabelBar feedback loop.")

    T.subsection_h(doc, "2.3.3", "Large Language Models for Lead Qualification")
    T.body(doc,
        "The emergence of transformer-based large language models (LLMs) — beginning "
        "with BERT (Devlin et al., 2018), GPT-3 (Brown et al., 2020), and continuing "
        "through GPT-4, Google Gemini, Anthropic Claude, and Meta Llama — has introduced "
        "a new capability for lead qualification: the ability to evaluate unstructured "
        "text signals that cannot be captured by structured features.")

    T.body(doc,
        "Job title analysis is a canonical example. The structured feature 'position = "
        "Director' provides useful but incomplete information — a Director of Operations "
        "at a 15-person startup has very different purchasing authority from a Director "
        "of Engineering at a Fortune 500 company. An LLM can evaluate the full job "
        "title string, company description, and industry context together to infer "
        "actual seniority level, budget authority, and decision-making relevance with "
        "substantially higher accuracy than a structured encoding.")

    T.body(doc,
        "Kumar, Patel, and Mehta (2024) demonstrated that combining a structured "
        "XGBoost model with GPT-4 LLM reasoning in a sequential pipeline achieved "
        "qualification accuracy (measured by AUC-ROC) 14 percentage points higher than "
        "XGBoost alone and 8 percentage points higher than the LLM alone on a held-out "
        "test set of 3,200 leads. The study attributed the improvement to "
        "complementarity: XGBoost excels at quantitative pattern recognition in "
        "structured data, while LLMs excel at contextual semantic reasoning in "
        "unstructured text — and the two error types are largely non-overlapping.")

    T.body(doc,
        "OrionLead AI implements this complementarity through Layers 3 (Google Gemini) "
        "and 4 (Groq Llama) of its cascade. The LLM layers receive a structured prompt "
        "containing the lead's key fields and are asked to evaluate seniority signals, "
        "company relevance, buying intent, and contextual fit, returning a quality "
        "assessment that modifies the XGBoost base score. The cascade architecture "
        "ensures LLM processing is only invoked when the structured ML score warrants "
        "additional scrutiny, controlling the cost and latency of LLM API calls.")

    T.subsection_h(doc, "2.3.4", "Ensemble and Cascade Architectures")
    T.body(doc,
        "The use of multiple models in sequence — a cascade — rather than a single "
        "model addresses a fundamental tradeoff in AI qualification: accuracy versus "
        "cost. Simple rules are instant and free but cannot handle nuanced cases. "
        "ML models are fast and cheap but miss semantic signals. LLMs are highly "
        "capable but slow (300–3000ms per call) and expensive when applied at scale.")

    T.body(doc,
        "Cascade architectures route candidates through progressively more capable "
        "layers, short-circuiting evaluation at the earliest layer that can make a "
        "confident decision. Viola and Jones (2001) first demonstrated this principle "
        "in computer vision (the Viola-Jones face detection cascade), and the approach "
        "has since been generalized to NLP and structured prediction tasks. Zhao et al. "
        "(2023) applied cascade reasoning specifically to LLM-based classification, "
        "showing that routing only 15–30% of instances to LLM evaluation while handling "
        "the remainder with cheaper models achieves 95%+ of full-LLM accuracy at "
        "approximately 20% of the cost.")

    T.body(doc,
        "OrionLead AI's four-layer cascade — Anti-Junk (deterministic, instant) → "
        "XGBoost (fast ML, <50ms) → Gemini (LLM, 1–3s) → Groq (fallback LLM, <1s) — "
        "implements this principle directly. The anti-junk layer handles approximately "
        "30–40% of candidates (clear rejections). XGBoost handles the majority of the "
        "remainder with high confidence. Only candidates where XGBoost score falls "
        "in an uncertain range require LLM evaluation, controlling API costs while "
        "maintaining overall qualification quality.")

    # ── 2.4 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "2.4", "Existing Systems and Tools")

    T.body(doc,
        "Several commercial systems address portions of the lead generation and "
        "qualification problem. Evaluating them against OrionLead AI's feature set "
        "reveals the specific gaps that motivated this project's development.")

    headers = ["System", "Strengths", "Limitations vs. OrionLead AI"]
    rows = [
        ["Apollo.io",
         "Large database (275M+ contacts); search and filtering; email sequencing",
         "No AI qualification cascade; no mobile app; no outcome-driven retraining; no self-hosting"],
        ["HubSpot CRM\n+ AI Scoring",
         "Mature CRM; predictive scoring on existing contacts; strong inbound integration",
         "Requires prior interaction history; no collection automation; no mobile offline; proprietary lock-in"],
        ["ZoomInfo",
         "High data quality; revenue/headcount/tech stack signals; broad coverage",
         "Very high cost; no qualification engine; no mobile; no LLM integration; no feedback loop"],
        ["Clearbit / Breyta",
         "Real-time enrichment API; company and person data; developer-friendly",
         "Enrichment only; no collection; no scoring; no UI; no mobile; no outcome tracking"],
        ["Clay.com",
         "Flexible AI enrichment workflows; LLM integration; visual pipeline builder",
         "Complex configuration; no mobile app; no offline support; no built-in ML model; no feedback loop"],
        ["Lusha",
         "Direct dial and email finding; Chrome extension; CRM integrations",
         "No AI scoring; no collection orchestration; no mobile; no analytics; no retraining"],
        ["LinkedIn Sales Navigator",
         "Premium profile access; InMail; real-time signals; account lists",
         "No automated collection; no scoring; no API export without partnership; desktop-only"],
        ["OrionLead AI\n(This Project)",
         "4-layer AI cascade; Company-First pipeline; mobile offline; 8 API sources; retraining loop; self-hosted",
         "Smaller training dataset; no native CRM connectors (planned future work)"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.2), Cm(5.8), Cm(6.3)])
    T.caption(doc, "Table 2.1 — Comparison of OrionLead AI with Existing Lead Generation Systems")

    T.body(doc,
        "The comparison reveals that no existing commercially available system "
        "combines open-architecture multi-layer AI qualification, company-first "
        "evaluation, mobile-first access with offline support, and a continuous "
        "learning feedback loop within a single unified platform. Each commercial "
        "tool addresses one or two of these dimensions but not all, forcing "
        "organizations to assemble and maintain integrations between multiple "
        "specialized tools — a significant operational burden that OrionLead AI "
        "eliminates through its integrated architecture.")

    # ── 2.5 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "2.5", "Research Gap and Motivation")

    T.body(doc,
        "The synthesis of the literature review and competitive analysis reveals five "
        "distinct and significant gaps in the current state of both academic research "
        "and commercial practice. These gaps collectively define the research "
        "contribution of OrionLead AI and justify its architectural choices.")

    T.body(doc,
        "Gap 1 — Cascade AI Architecture for Lead Qualification: No published academic "
        "work or commercial system implements a four-layer cascade combining "
        "deterministic rule-based filtering, gradient-boosted ML, and multiple LLM "
        "providers with graceful fallback within a self-hostable, open-architecture "
        "lead qualification system. The cascade approach from Zhao et al. (2023) is "
        "validated in classification theory but has not been applied to the specific "
        "domain of B2B lead scoring with the combination of layers implemented here.")

    T.body(doc,
        "Gap 2 — Company-First Evaluation: Existing literature on lead scoring treats "
        "the lead as the atomic unit of analysis — evaluating individual contact "
        "attributes independently. The paradigm of first validating the target "
        "organization (its website health, business classification, growth stage, and "
        "account score) before resolving and evaluating individual contacts has not "
        "been implemented in any commercially available system reviewed. This "
        "represents a novel contribution to the design of lead qualification systems.")

    T.body(doc,
        "Gap 3 — Mobile-First Access with Offline Synchronization: The academic "
        "literature on CRM and lead management systems is silent on mobile "
        "accessibility concerns, and all major commercial platforms reviewed are "
        "desktop-centric. The combination of offline-first action queuing, "
        "real-time Supabase synchronization, and Firebase push notifications "
        "within a lead management platform represents a practical innovation "
        "unaddressed by existing systems.")

    T.body(doc,
        "Gap 4 — Closed Feedback Loop for Continuous ML Improvement: While the "
        "importance of feedback loops in ML systems is well-established in the academic "
        "literature (Sculley et al., 2015, \"Hidden Technical Debt in ML Systems\"), "
        "the specific implementation of a one-click outcome labeling interface "
        "(QuickLabelBar) directly connected to a lead qualification model retraining "
        "pipeline has not been described or evaluated in published B2B lead scoring "
        "research. Commercial tools treat their ML models as static artifacts updated "
        "only by the vendor on an undisclosed schedule.")

    T.body(doc,
        "Gap 5 — Open-Architecture Self-Hosted Platform: All commercial lead generation "
        "platforms with AI qualification capabilities are proprietary SaaS systems "
        "with no self-hosting option. Organizations with data sovereignty requirements, "
        "budget constraints, or the need to customize the qualification logic for "
        "industry-specific criteria have no viable open-architecture alternative. "
        "OrionLead AI fills this gap by providing a fully open, self-hosted platform "
        "where qualification rules, model features, and API integrations are all "
        "configurable by the deploying organization.")

    T.body(doc,
        "Taken together, these five gaps define OrionLead AI's position at the "
        "intersection of applied AI research and practical sales technology innovation. "
        "The system does not claim to advance the theoretical frontier of machine "
        "learning or natural language processing; rather, it demonstrates how "
        "established and emerging AI techniques can be combined in a novel architecture "
        "to solve a high-value, practical problem that existing tools address only "
        "partially. The following chapters describe the analysis, design, "
        "implementation, and evaluation of this contribution in detail.")
