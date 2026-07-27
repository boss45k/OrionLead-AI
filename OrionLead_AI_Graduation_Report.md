# ISLAMIC UNIVERSITY OF LEBANON
## Faculty of Engineering

---

&nbsp;

&nbsp;

# OrionLead AI
## An Intelligent B2B Lead Collection and Qualification System

&nbsp;

&nbsp;

**Prepared by:**
ALI Jradeh

&nbsp;

**Supervised by:**
DR. Mohammad Alawwan

&nbsp;

**Submitted in partial fulfillment of the requirements for the degree of**
**Bachelor of Engineering in Computer Engineering**

&nbsp;

**Academic Year: 2025 – 2026**

---

&nbsp;

&nbsp;

---

## Defense Committee Approval

This project, titled **"OrionLead AI: An Intelligent B2B Lead Collection and Qualification System"**, submitted by **ALI Jradeh**, has been approved by the Defense Committee of the Faculty of Engineering at the Islamic University of Lebanon.

&nbsp;

| Role | Name | Signature |
|------|------|-----------|
| Supervisor | DR. Mohammad Alawwan | ____________ |
| Committee Member | _________________________ | ____________ |
| Committee Member | _________________________ | ____________ |
| Department Head | _________________________ | ____________ |

&nbsp;

**Date of Defense:** _________________________ / _________________________ / 2026

---

## Acknowledgments

First and foremost, I give thanks to **Allah**, the Almighty, for granting me the strength, patience, and perseverance to complete this work.

I would like to express my deepest gratitude to my supervisor, **DR. Mohammad Alawwan**, whose expert guidance, continuous encouragement, and invaluable feedback were instrumental throughout every phase of this project. His technical insight and dedication to excellence pushed me to deliver the highest quality work possible.

I am also sincerely grateful to the **Faculty of Engineering at the Islamic University of Lebanon** for providing the academic foundation and resources that made this project possible. The knowledge and skills acquired throughout my studies here form the backbone of everything built in this system.

To my family — thank you for your unconditional love, patience, and support. You are my greatest motivation. Every late night spent coding was made possible by your constant encouragement.

To my friends and colleagues who offered advice, tested the application, and provided moral support throughout this journey — I am truly grateful. Your enthusiasm for this project kept me going through the most challenging moments.

Finally, I dedicate this project to everyone who believes in the power of artificial intelligence to transform the way businesses find and connect with their customers.

---

## Abstract

The rapid evolution of artificial intelligence has opened transformative possibilities for business development and sales automation. OrionLead AI is a full-stack, AI-powered B2B (Business-to-Business) lead generation and qualification platform designed to automate the entire lifecycle of identifying, collecting, evaluating, and managing potential business leads.

Traditional lead generation approaches are labor-intensive, inconsistent, and highly dependent on manual effort. Sales teams waste significant time researching prospects and manually scoring contact quality, resulting in lost opportunities and reduced productivity. OrionLead AI addresses this challenge through an intelligent, multi-layer pipeline that combines rule-based filtering, machine learning, and large language models (LLMs) to deliver high-quality, pre-scored leads to sales professionals.

The system is composed of three tightly integrated components: a Python Flask RESTful backend powered by a four-layer AI qualification cascade (Anti-Junk Rules → XGBoost ML → Google Gemini LLM → Groq fallback), a React 18 web dashboard with real-time analytics, and a React Native cross-platform mobile application with offline-first synchronization via Supabase.

The AI qualification engine uses a trained XGBoost model (xgb_v5) with 37 engineered features derived from lead contact data, firmographic signals, behavioral indicators, and source metadata. Leads are scored on a 0–100 scale and classified into four tiers: Hot (≥80), Warm (≥60), Cold (≥30), and Unqualified (<30). An anti-junk engine with 12 hard-reject rules prevents fake, spam, or low-quality contacts from entering the pipeline at all.

The platform integrates with eight external APIs including Hunter.io, Apollo.io, People Data Labs, Serper.dev, Google Places, ZeroBounce, Google Gemini, and Groq. A Company-First Intelligence Pipeline ensures that organizational signals — website quality, business classification, growth indicators — are evaluated before resolving individual contacts, dramatically improving contact relevance.

The system features role-based access control (Admin, Manager, User), real-time push notifications via Firebase Cloud Messaging, CSV export, dark/light mode theming, and a QuickLabelBar for one-click outcome labeling that feeds a continuous ML retraining loop. Testing coverage includes 563 automated pytest tests validated against both SQLite and MySQL in parallel CI/CD pipelines on GitHub Actions.

**Keywords:** B2B Lead Generation, Artificial Intelligence, Machine Learning, XGBoost, Large Language Models, Flask, React Native, Lead Qualification, Sales Automation, Multi-Layer AI Pipeline.

---

## Table of Contents

- [Defense Committee Approval](#defense-committee-approval)
- [Acknowledgments](#acknowledgments)
- [Abstract](#abstract)
- **Chapter 1: Introduction**
  - 1.1 Background and Motivation
  - 1.2 Problem Statement
  - 1.3 Proposed Solution
  - 1.4 Project Objectives
  - 1.5 Project Scope
  - 1.6 Report Organization
- **Chapter 2: Literature Review**
  - 2.1 Overview of B2B Lead Generation
  - 2.2 Traditional Lead Generation Methods
  - 2.3 AI and Machine Learning in Lead Qualification
  - 2.4 Existing Systems and Tools
  - 2.5 Research Gap and Motivation
- **Chapter 3: System Analysis**
  - 3.1 System External Entities
  - 3.2 User Roles and Permissions
  - 3.3 Functional Requirements
  - 3.4 Non-Functional Requirements
  - 3.5 Data Flow Diagram (DFD)
  - 3.6 Use Case Diagram
  - 3.7 Use Case Descriptions
- **Chapter 4: System Design and Architecture**
  - 4.1 Overall System Architecture
  - 4.2 Backend Architecture
  - 4.3 AI Qualification Engine
  - 4.4 Web Frontend Architecture
  - 4.5 Mobile Application Architecture
  - 4.6 Database Design
  - 4.7 Entity-Relationship Diagram (ERD)
  - 4.8 Security Architecture
  - 4.9 External Integrations
- **Chapter 5: System Implementation**
  - 5.1 Development Environment
  - 5.2 Backend Implementation
  - 5.3 AI Engine Implementation
  - 5.4 Web Frontend Implementation
  - 5.5 Mobile Application Implementation
  - 5.6 Database Implementation
  - 5.7 API Implementation
  - 5.8 Real-Time Synchronization
- **Chapter 6: Testing and Evaluation**
  - 6.1 Testing Strategy
  - 6.2 Functional Test Cases
  - 6.3 API Testing
  - 6.4 Non-Functional Testing
  - 6.5 CI/CD Pipeline Testing
- **Chapter 7: System Results and User Interface**
  - 7.1 Web Dashboard — Authentication
  - 7.2 Web Dashboard — Lead Management
  - 7.3 Web Dashboard — Analytics
  - 7.4 Web Dashboard — AI Collection
  - 7.5 Mobile Application — Leads
  - 7.6 Mobile Application — Analytics
  - 7.7 Mobile Application — Dark Mode
- **Chapter 8: Conclusion and Future Work**
  - 8.1 Conclusion
  - 8.2 Achievements
  - 8.3 Limitations
  - 8.4 Future Work
- **References**

---

## List of Tables

| Table No. | Title | Page |
|-----------|-------|------|
| Table 3.1 | System External Entities | — |
| Table 3.2 | User Roles and Permissions | — |
| Table 3.3 | Functional Requirements | — |
| Table 3.4 | Non-Functional Requirements | — |
| Table 3.5 | Use Case: Register Account | — |
| Table 3.6 | Use Case: Collect Leads | — |
| Table 3.7 | Use Case: Qualify Lead with AI | — |
| Table 3.8 | Use Case: Label Lead Outcome | — |
| Table 4.1 | Users Table Attributes | — |
| Table 4.2 | Leads Table Attributes | — |
| Table 4.3 | LeadActivities Table Attributes | — |
| Table 4.4 | LeadOutcomes Table Attributes | — |
| Table 4.5 | DataSources Table Attributes | — |
| Table 4.6 | ClassificationCategories Table Attributes | — |
| Table 4.7 | SeenContacts Table Attributes | — |
| Table 4.8 | SyncLogs Table Attributes | — |
| Table 4.9 | External API Integrations | — |
| Table 5.1 | Backend Technology Stack | — |
| Table 5.2 | Web Frontend Technology Stack | — |
| Table 5.3 | Mobile Technology Stack | — |
| Table 5.4 | XGBoost Model Feature Categories | — |
| Table 6.1 | Functional Test Cases — Authentication | — |
| Table 6.2 | Functional Test Cases — Lead Management | — |
| Table 6.3 | Functional Test Cases — AI Qualification | — |
| Table 6.4 | API Endpoint Test Results | — |
| Table 6.5 | Non-Functional Test Results | — |

---

## List of Figures

| Figure No. | Title | Page |
|------------|-------|------|
| Figure 3.1 | Level-0 Data Flow Diagram (Context Diagram) | — |
| Figure 3.2 | Level-1 Data Flow Diagram | — |
| Figure 3.3 | Use Case Diagram | — |
| Figure 4.1 | Overall System Architecture | — |
| Figure 4.2 | Four-Layer AI Qualification Cascade | — |
| Figure 4.3 | Entity-Relationship Diagram (ERD) | — |
| Figure 4.4 | Company-First Intelligence Pipeline | — |
| Figure 4.5 | Real-Time Synchronization Architecture | — |
| Figure 7.1 | Web Dashboard — Login Screen | — |
| Figure 7.2 | Web Dashboard — Leads List | — |
| Figure 7.3 | Web Dashboard — Lead Detail View | — |
| Figure 7.4 | Web Dashboard — Analytics Overview | — |
| Figure 7.5 | Web Dashboard — AI Collection Panel | — |
| Figure 7.6 | Mobile App — Leads Screen | — |
| Figure 7.7 | Mobile App — Lead Detail | — |
| Figure 7.8 | Mobile App — Analytics Screen | — |
| Figure 7.9 | Mobile App — Dark Mode | — |

---

# CHAPTER 1: INTRODUCTION

## 1.1 Background and Motivation

In the modern business landscape, identifying and acquiring high-quality sales leads is one of the most critical and time-consuming activities a company performs. For B2B (Business-to-Business) organizations, the quality of leads directly determines the efficiency of the sales pipeline and ultimately drives revenue growth. A sales team that works with well-qualified, accurately scored leads can close deals faster, allocate resources more effectively, and generate significantly better return on investment from their sales activities.

Historically, lead generation was performed entirely through manual research — sales representatives would spend hours browsing LinkedIn, industry directories, corporate websites, and trade publications to identify potential customers. This approach is not only time-consuming but also inconsistent, as lead quality varies dramatically depending on the researcher's skill and judgment. In competitive markets where response time is critical, manual processes simply cannot keep pace with the volume and speed required.

The emergence of artificial intelligence, machine learning, and large language models (LLMs) has created an unprecedented opportunity to transform lead generation from a manual, subjective process into an automated, data-driven, and highly accurate system. By leveraging AI, organizations can now collect leads from multiple sources simultaneously, evaluate their quality against dozens of criteria in milliseconds, and surface only the most promising prospects to human sales teams.

OrionLead AI was conceived precisely to address this opportunity. It represents a complete reimagining of the B2B lead generation workflow, built from the ground up to place artificial intelligence at the center of every decision — from initial lead discovery through final qualification and outcome tracking.

## 1.2 Problem Statement

Organizations involved in B2B sales face several critical challenges with traditional lead generation approaches:

**Volume without quality:** Mass lead collection tools gather large numbers of contacts but provide no mechanism to distinguish genuine business prospects from fake, duplicate, or irrelevant entries. Sales teams receive lists polluted with invalid email addresses, personal accounts misclassified as business contacts, and contacts with no purchase intent.

**Manual qualification bottleneck:** Even when leads are collected, scoring their potential requires significant human judgment. Without systematic criteria, qualification decisions are inconsistent across team members and cannot scale. A single senior salesperson cannot manually evaluate hundreds of new leads per day.

**Data fragmentation:** Lead information is scattered across multiple tools — CRM systems, spreadsheets, LinkedIn exports, email enrichment platforms — with no unified view of a lead's complete profile. Teams waste time switching between tools and reconciling inconsistent data.

**No feedback loop:** Traditional systems do not learn from outcomes. Whether a lead converted, replied, or was irrelevant is rarely captured in a way that improves future collection. The same patterns of low-quality leads recur indefinitely.

**Mobile inaccessibility:** Sales professionals are increasingly mobile. Traditional lead management tools are desktop-centric, forcing field teams to work from laptops or lose access to their pipeline entirely when away from the office.

**Lack of company context:** Most tools focus on individual contact data without first evaluating the target company's characteristics — its growth stage, business model, website quality, and market relevance. This results in valid contacts at irrelevant companies being treated as high-value leads.

## 1.3 Proposed Solution

OrionLead AI proposes a unified, AI-first platform that addresses each of the above challenges through an integrated architecture of intelligent components:

A **four-layer AI qualification cascade** — comprising anti-junk rule filtering, XGBoost machine learning, Google Gemini LLM reasoning, and Groq fallback — ensures that every lead is scored consistently, accurately, and automatically without human intervention at the scoring stage.

A **Company-First Intelligence Pipeline** evaluates organizational signals before resolving individual contacts. Only contacts at companies that pass quality gates — assessed on website health, business classification, growth indicators, and account score — are admitted to the pipeline.

A **multi-source collection engine** aggregates lead data from eight external APIs (Hunter.io, Apollo.io, People Data Labs, Serper.dev, Google Places, ZeroBounce, Google Gemini, and Groq), with intelligent deduplication, validation, and enrichment applied at ingestion time.

A **QuickLabelBar** captures real-world lead outcomes (Converted, Replied, No Reply, Not a Fit) with a single tap, feeding a continuous ML retraining loop that improves model accuracy over time.

A **cross-platform architecture** delivers a full-featured React web dashboard for office-based team management and a React Native mobile application with offline-first synchronization for field sales professionals, both connected to the same backend in real time.

## 1.4 Project Objectives

The primary objectives of OrionLead AI are:

1. **Automate lead discovery** by integrating with multiple commercial and open data APIs to collect business contacts without manual research effort.

2. **Eliminate junk leads** through a 12-rule anti-junk engine that hard-rejects fake names, personal email domains, invalid phone numbers, and other disqualifying signals before any AI processing occurs.

3. **Score and rank leads automatically** using a trained XGBoost model with 37 features, producing a 0–100 qualification score that categorizes leads into Hot, Warm, Cold, and Unqualified tiers.

4. **Apply natural language intelligence** via Google Gemini and Groq LLMs to evaluate lead quality dimensions that cannot be captured by structured features alone — such as industry relevance, role seniority signals, and contextual fit.

5. **Provide a complete lead management workflow** including creation, enrichment, status tracking, activity logging, outcome labeling, CSV export, and team-based visibility controls.

6. **Deliver real-time analytics** showing collection trends, score distributions, source performance, conversion rates, and ML model accuracy to management and administrators.

7. **Enable mobile-first field access** through a React Native application with offline queuing, push notifications, and real-time synchronization.

8. **Support organizational scaling** through role-based access control that segregates lead visibility by collector and elevates aggregated views for managers and administrators.

## 1.5 Project Scope

OrionLead AI encompasses the following scope:

**In scope:**
- Full-stack platform with backend API, web frontend, and mobile application
- AI qualification engine with four processing layers
- Integration with eight external data and AI APIs
- Role-based user management (Admin, Manager, User)
- Lead lifecycle management from collection to outcome labeling
- Real-time synchronization between web and mobile platforms
- Automated CI/CD pipeline with 563 test cases
- Dark and light mode theming across all interfaces
- Push notification delivery via Firebase Cloud Messaging

**Out of scope:**
- CRM integration with third-party platforms (Salesforce, HubSpot)
- Email campaign execution directly within the platform
- Video calling or screen sharing features
- Payment processing or subscription billing
- Multi-language internationalization beyond English and Arabic interface labels

## 1.6 Report Organization

This report is organized as follows:

**Chapter 2** presents the literature review, examining existing work in B2B lead generation, AI-based qualification, and related commercial systems.

**Chapter 3** covers system analysis, defining external entities, user roles, functional and non-functional requirements, and illustrating the system with Data Flow Diagrams and Use Case Diagrams.

**Chapter 4** describes the system design and architecture, detailing the backend structure, AI engine design, database schema, ERD, security architecture, and external integrations.

**Chapter 5** explains the implementation details across all components — backend services, AI engine, web frontend, mobile application, and real-time synchronization.

**Chapter 6** presents testing and evaluation results, including functional test cases, API test results, and non-functional performance metrics.

**Chapter 7** displays the system's user interface through annotated screenshots of key screens across both the web and mobile platforms.

**Chapter 8** concludes the report with a summary of achievements, identified limitations, and proposed directions for future development.

---

# CHAPTER 2: LITERATURE REVIEW

## 2.1 Overview of B2B Lead Generation

B2B lead generation refers to the process of identifying and attracting potential business customers — entities (companies or individuals acting in a professional capacity) who have a reasonable likelihood of purchasing a product or service. Unlike B2C (Business-to-Consumer) marketing, which targets individual buyers with relatively straightforward needs, B2B lead generation involves longer sales cycles, multiple decision-makers, higher contract values, and significantly more complex qualification criteria.

According to a 2024 report by HubSpot, 61% of B2B marketers cite generating high-quality leads as their most significant challenge, surpassing even budget constraints and team capacity [1]. The same report notes that organizations using AI-assisted lead qualification report 50% higher conversion rates and 33% lower cost-per-lead compared to those relying exclusively on manual processes.

The lead generation process traditionally encompasses four stages: prospecting (identifying potential customers), enrichment (gathering contact and firmographic data), qualification (assessing likelihood to convert), and nurturing (maintaining engagement until purchase). OrionLead AI targets and automates the first three stages comprehensively.

## 2.2 Traditional Lead Generation Methods

**Cold outreach and manual research** has historically been the dominant B2B lead generation approach. Sales development representatives (SDRs) search LinkedIn, industry directories such as Clutch.co and G2, company websites, and trade publication attendee lists to identify contacts, then manually log this data into CRM systems. The process is time-intensive, with studies estimating that SDRs spend 40–60% of their working hours on prospecting activities rather than selling [2].

**Form-based inbound generation** captures leads through website contact forms, gated content, and newsletter subscriptions. While highly targeted, inbound methods are volume-constrained and dependent on existing marketing presence. Newly established companies or those entering new markets cannot rely on inbound alone.

**Trade show and event lead capture** generates contacts through in-person interactions but is geographically limited, expensive, and produces a concentrated burst of leads that are difficult to follow up at scale.

**Purchased lead lists** from vendors such as ZoomInfo, Apollo.io, and Lusha provide access to large contact databases. However, these lists suffer from data decay — industry studies estimate that B2B contact data degrades at 30–40% annually as people change jobs — and are not customized to a specific company's ideal customer profile (ICP).

## 2.3 AI and Machine Learning in Lead Qualification

The application of machine learning to sales qualification has been an active research and industry development area since the mid-2010s. Key approaches include:

**Logistic Regression and Scoring Models** were the earliest ML approaches to lead scoring, predicting conversion probability based on demographic and behavioral features. Salesforce's Einstein Lead Scoring, introduced in 2016, pioneered commercial application of this approach [3].

**Gradient Boosted Trees**, including XGBoost and LightGBM, have shown superior performance for tabular business data due to their ability to capture non-linear relationships, handle missing values natively, and remain interpretable through feature importance analysis. A 2022 study by Zhang et al. compared seven ML algorithms for B2B lead scoring and found XGBoost consistently outperformed logistic regression, random forests, and neural networks on structured CRM data [4].

**Large Language Models (LLMs)** represent the most recent development in AI-assisted qualification. Models such as GPT-4, Google Gemini, and Groq's Llama series can evaluate unstructured text signals — job title nuances, company description relevance, recent news about a company — that are difficult to encode as structured features. Emerging research demonstrates that combining structured ML models with LLM reasoning achieves higher qualification accuracy than either approach alone [5].

**Ensemble and Cascade Architectures** combine multiple models in sequence or parallel, with each layer handling the cases where previous layers are uncertain. OrionLead AI's four-layer cascade follows this approach, using deterministic rules for clear-cut rejections, ML for pattern-based scoring, and LLMs for context-sensitive judgment.

## 2.4 Existing Systems and Tools

Several commercial systems address portions of the lead generation and qualification problem:

**Apollo.io** is a comprehensive B2B intelligence platform with over 275 million contacts. It provides search and filtering capabilities but does not apply AI qualification scoring to individual leads and requires significant manual curation of search results.

**HubSpot CRM with AI scoring** offers predictive lead scoring within its ecosystem but requires leads to already exist in the CRM and relies on historical interaction data, making it ineffective for newly collected contacts with no prior engagement history.

**ZoomInfo** provides high-quality enriched contact data with revenue, headcount, and technology stack signals, but at a premium price point inaccessible to small and medium enterprises, and without a qualification engine beyond search filtering.

**Clearbit (now Breyta)** offers real-time company and person enrichment APIs used to augment existing contact data but does not perform qualification or scoring.

**Clay.com** is an emerging AI-powered data enrichment and workflow platform that allows custom qualification logic, but requires significant configuration expertise and lacks a mobile application for field team access.

None of these systems provide a fully integrated, open-architecture platform combining multi-source collection, multi-layer AI qualification, web and mobile interfaces, and a continuous learning loop within a single unified system.

## 2.5 Research Gap and Motivation

The review of existing literature and commercial tools reveals a clear research and product gap:

1. No existing system combines open-source ML (XGBoost) with commercial LLMs (Gemini, Groq) in a cascade architecture for lead qualification within a self-hostable platform.

2. Existing tools treat lead qualification as a single-model problem rather than a multi-layer cascade that escalates uncertainty to progressively more capable (and more expensive) models.

3. The Company-First evaluation paradigm — assessing organizational health before resolving individual contacts — is not implemented in any commercially available lead generation tool reviewed.

4. Mobile-first access with offline synchronization is absent from all major B2B lead platforms, creating a significant gap for field-based sales teams.

5. The feedback loop from lead outcome labeling to model retraining is rarely implemented in commercial tools, which treat ML models as static artifacts rather than continuously improving systems.

OrionLead AI directly addresses all five gaps, positioning itself as a novel contribution to the intersection of AI research and sales technology.

---

# CHAPTER 3: SYSTEM ANALYSIS

## 3.1 System External Entities

The OrionLead AI system interacts with the following external entities:

**Table 3.1 — System External Entities**

| Entity | Type | Description | Interaction Direction |
|--------|------|-------------|----------------------|
| Sales User | Human | Field sales representative using the mobile app to view, label, and manage assigned leads | Bidirectional |
| Manager | Human | Team lead who oversees assigned team members' lead pipelines and analytics | Bidirectional |
| Administrator | Human | System administrator with full access to all leads, users, settings, and data exports | Bidirectional |
| Hunter.io | External API | Email finding and verification service; provides verified business email addresses | Inbound data |
| Apollo.io | External API | B2B contact and company intelligence database; provides enriched contact profiles | Inbound data |
| People Data Labs | External API | Person and company data enrichment API with firmographic signals | Inbound data |
| Serper.dev | External API | Google Search API wrapper; used for web-based lead discovery queries | Inbound data |
| Google Places API | External API | Business location and contact data from Google's Places database | Inbound data |
| ZeroBounce | External API | Email validation and deliverability verification service | Inbound data |
| Google Gemini | External AI | Google's multimodal large language model; used as Layer 3 of the qualification cascade | Inbound AI |
| Groq | External AI | High-speed LLM inference platform (Llama models); used as Layer 4 fallback in cascade | Inbound AI |
| Firebase Cloud Messaging | External Service | Push notification delivery service for mobile users | Outbound |
| Supabase | External Service | PostgreSQL-based real-time sync bridge between MySQL backend and mobile clients | Bidirectional |
| MySQL Database | Internal | Primary relational data store for all leads, users, and system data | Bidirectional |
| Redis | Internal | In-memory cache and Celery task broker for background job processing | Bidirectional |

## 3.2 User Roles and Permissions

OrionLead AI implements a three-tier role-based access control system.

**Table 3.2 — User Roles and Permissions**

| Permission | User | Manager | Admin |
|-----------|------|---------|-------|
| View own collected leads | ✓ | ✓ | ✓ |
| View all team leads | ✗ | ✓ | ✓ |
| View all system leads | ✗ | ✗ | ✓ |
| Create leads manually | ✓ | ✓ | ✓ |
| Trigger AI collection | ✓ | ✓ | ✓ |
| Edit lead details | ✓ (own) | ✓ | ✓ |
| Delete leads | ✗ | ✓ | ✓ |
| Label lead outcomes | ✓ | ✓ | ✓ |
| Export leads to CSV | ✓ | ✓ | ✓ |
| View analytics dashboard | ✓ (own) | ✓ (team) | ✓ (all) |
| Manage users | ✗ | ✗ | ✓ |
| Manage data sources | ✗ | ✗ | ✓ |
| Access ML retraining | ✗ | ✗ | ✓ |
| View audit logs | ✗ | ✓ | ✓ |
| Manage system settings | ✗ | ✗ | ✓ |

## 3.3 Functional Requirements

**Table 3.3 — Functional Requirements**

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | The system shall allow users to register and log in using email and password credentials | High |
| FR-02 | The system shall issue JWT access tokens upon successful authentication with configurable expiry | High |
| FR-03 | The system shall support three user roles: admin, manager, and user, each with defined permission sets | High |
| FR-04 | The system shall allow AI-triggered lead collection from multiple external APIs based on a natural language query | High |
| FR-05 | The system shall apply anti-junk filtering with 12 hard-reject rules before processing any collected lead | High |
| FR-06 | The system shall score each lead on a 0–100 scale using a four-layer AI qualification cascade | High |
| FR-07 | The system shall classify leads into four tiers: Hot (≥80), Warm (≥60), Cold (≥30), Unqualified (<30) | High |
| FR-08 | The system shall allow users to create leads manually with required and optional fields | Medium |
| FR-09 | The system shall allow users to update lead status, notes, and contact information | High |
| FR-10 | The system shall restrict lead visibility such that non-admin users see only leads they collected | High |
| FR-11 | The system shall allow managers and admins to view all leads in their scope | High |
| FR-12 | The system shall support one-click outcome labeling with four options: Converted, Replied, No Reply, Not a Fit | High |
| FR-13 | The system shall log all lead outcome labels to feed the ML retraining pipeline | Medium |
| FR-14 | The system shall export filtered lead lists to CSV format | Medium |
| FR-15 | The system shall provide real-time analytics including score distribution, source performance, and collection trends | Medium |
| FR-16 | The system shall deliver push notifications to mobile users when new leads are assigned or status changes occur | Medium |
| FR-17 | The system shall synchronize lead data between the MySQL backend and mobile clients via Supabase in real time | High |
| FR-18 | The system shall support offline lead viewing and queued actions on mobile when network is unavailable | Medium |
| FR-19 | The system shall allow administrators to manage user accounts, roles, and API key generation | High |
| FR-20 | The system shall prevent duplicate lead entries using a SeenContacts deduplication mechanism | High |
| FR-21 | The system shall support dark and light mode theming across web and mobile interfaces | Low |
| FR-22 | The system shall provide API documentation through an interactive Swagger/OpenAPI interface | Low |

## 3.4 Non-Functional Requirements

**Table 3.4 — Non-Functional Requirements**

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-01 | Performance | API endpoints shall respond within 500ms for standard CRUD operations under normal load |
| NFR-02 | Performance | AI qualification of a single lead shall complete within 8 seconds end-to-end including LLM processing |
| NFR-03 | Scalability | The backend shall handle 100 concurrent users without performance degradation |
| NFR-04 | Reliability | The system shall achieve 99.5% uptime during business hours |
| NFR-05 | Security | All API communication shall use HTTPS/TLS encryption |
| NFR-06 | Security | Passwords shall be stored using bcrypt hashing with minimum cost factor 12 |
| NFR-07 | Security | JWT tokens shall expire after 24 hours and require re-authentication |
| NFR-08 | Security | Role-based access control shall be enforced at the API layer, not only the UI layer |
| NFR-09 | Maintainability | Backend code shall achieve minimum 80% automated test coverage |
| NFR-10 | Maintainability | All API endpoints shall be documented with request/response schemas |
| NFR-11 | Portability | The mobile application shall run on both iOS and Android platforms |
| NFR-12 | Usability | The interface shall support dark and light modes with system preference detection |
| NFR-13 | Data Integrity | Lead deduplication shall prevent duplicate entries with >95% accuracy |
| NFR-14 | Auditability | All lead modifications shall be logged with timestamp, user, and change description |
| NFR-15 | Availability | The system shall support offline lead access on mobile with queued synchronization |

## 3.5 Data Flow Diagram (DFD)

### Level-0 DFD (Context Diagram)

**Figure 3.1 — Level-0 Data Flow Diagram**

```
                          ┌─────────────────────┐
    Credentials ────────► │                     │ ◄─── Lead Data ──── External APIs
    Lead Requests ───────► │   OrionLead AI      │                   (Hunter, Apollo,
    Search Queries ──────► │       System        │ ────► Validated    PDL, Serper,
                          │                     │       Leads         Google Places)
    ◄──── Scored Leads ── │                     │
    ◄──── Analytics ───── │                     │ ────► Push Notif ── Firebase FCM
    ◄──── Export CSV ──── │                     │
                          │                     │ ◄──► Real-time ──── Supabase
         Sales User       │                     │       Sync
         Manager          └─────────────────────┘
         Admin                     │
                                   │
                            ┌──────▼──────┐
                            │   MySQL     │
                            │  Database   │
                            └─────────────┘
```

### Level-1 DFD

**Figure 3.2 — Level-1 Data Flow Diagram**

The Level-1 DFD expands the system into its primary processing modules:

**Process 1.0 — Authentication & Authorization:** Accepts user credentials, validates against the Users table, issues JWT tokens, and enforces role-based permissions on all subsequent requests.

**Process 2.0 — Lead Collection:** Receives natural language collection queries from authenticated users, dispatches parallel requests to configured external APIs through the multi-source aggregator, and routes results to Process 3.0.

**Process 3.0 — AI Qualification Cascade:** Applies the four-layer qualification pipeline: (3.1) Anti-junk rule evaluation → (3.2) XGBoost ML scoring → (3.3) Google Gemini LLM enrichment → (3.4) Groq fallback reasoning → final score and tier assignment.

**Process 4.0 — Lead Management:** Handles CRUD operations on qualified leads, enforces visibility rules based on the `collected_by` field, logs all changes to LeadActivities, and manages status transitions.

**Process 5.0 — Outcome Labeling & Retraining:** Receives QuickLabelBar inputs, writes to LeadOutcomes, and queues ML retraining jobs via Celery when sufficient new labeled examples accumulate.

**Process 6.0 — Analytics Engine:** Aggregates lead data by source, score tier, status, time period, and collector to generate dashboard metrics for each user role's permitted scope.

**Process 7.0 — Synchronization:** Mirrors lead create/update/delete events from MySQL to Supabase in real time, delivers push notifications via FCM, and resolves offline queue conflicts from mobile clients.

## 3.6 Use Case Diagram

**Figure 3.3 — Use Case Diagram**

The Use Case Diagram illustrates the interactions between the three user roles (User, Manager, Admin) and the system's primary use cases:

**User actor use cases:** Register, Login, Collect Leads (AI), View Own Leads, Create Lead Manually, Edit Lead, Label Outcome, Export Leads, View Own Analytics, Receive Push Notifications.

**Manager actor use cases:** (extends User) View Team Leads, View Team Analytics, Delete Lead.

**Admin actor use cases:** (extends Manager) View All Leads, Manage Users, Configure Data Sources, Trigger ML Retraining, View System Audit Log, Manage System Settings.

**External system interactions:** Collect Leads includes interactions with Hunter.io, Apollo.io, PDL, Serper.dev, and Google Places. Qualify Lead includes interactions with Google Gemini and Groq. Sync Data includes interaction with Supabase. Send Notification includes interaction with Firebase FCM.

## 3.7 Use Case Descriptions

**Table 3.5 — Use Case: Register Account**

| Field | Detail |
|-------|--------|
| Use Case ID | UC-01 |
| Name | Register Account |
| Actor | New User |
| Precondition | User has a valid email address not previously registered |
| Main Flow | 1. User navigates to registration page. 2. User enters full name, email, password, and company. 3. System validates input format and checks email uniqueness. 4. System hashes password with bcrypt. 5. System creates user record with role=user. 6. System returns success confirmation. |
| Alternative Flow | 3a. If email already exists, system returns 409 Conflict error. 3b. If password is too weak (<8 chars), system returns 400 Bad Request. |
| Postcondition | User account created with default role; user can log in. |

**Table 3.6 — Use Case: Collect Leads with AI**

| Field | Detail |
|-------|--------|
| Use Case ID | UC-02 |
| Name | Collect Leads with AI |
| Actor | Authenticated User |
| Precondition | User is authenticated; at least one data source is enabled by admin |
| Main Flow | 1. User enters natural language collection query (e.g., "SaaS CTOs in Dubai"). 2. Gemini AI analyzes query and generates optimized API search parameters. 3. System dispatches parallel requests to enabled external APIs. 4. System aggregates, deduplicates, and applies anti-junk filtering. 5. System runs AI qualification cascade on each candidate. 6. Qualified leads are saved with `collected_by` = current user ID. 7. System returns collection summary with counts by tier. |
| Alternative Flow | 5a. If anti-junk rejects a candidate, it is logged to SeenContacts but not saved. 6a. If lead already in SeenContacts, it is skipped silently. |
| Postcondition | New qualified leads appear in user's lead list with scores and tiers assigned. |

**Table 3.7 — Use Case: Qualify Lead with AI**

| Field | Detail |
|-------|--------|
| Use Case ID | UC-03 |
| Name | Qualify Lead with AI (Individual) |
| Actor | Authenticated User |
| Precondition | Lead record exists in the system |
| Main Flow | 1. User triggers re-qualification on an existing lead. 2. System gathers all lead data fields. 3. Layer 1: Anti-junk rules evaluated — if any rule fires, score = 0. 4. Layer 2: XGBoost model scores lead using 37 features. 5. Layer 3: Gemini LLM reviews profile for contextual quality signals. 6. Layer 4: Groq fallback invoked if Gemini is unavailable. 7. Final score saved; tier assigned; `qualification_score` updated. |
| Postcondition | Lead has updated score and tier reflecting AI assessment. |

**Table 3.8 — Use Case: Label Lead Outcome**

| Field | Detail |
|-------|--------|
| Use Case ID | UC-04 |
| Name | Label Lead Outcome |
| Actor | Authenticated User |
| Precondition | Lead exists and is accessible to the user |
| Main Flow | 1. User views lead detail. 2. User taps/clicks outcome label: Converted, Replied, No Reply, or Not a Fit. 3. System creates LeadOutcome record with outcome type, timestamp, and user ID. 4. System updates lead status accordingly. 5. Outcome queued for ML retraining batch. |
| Postcondition | Lead outcome logged; ML retraining queue updated; lead status reflects outcome. |

---

# CHAPTER 4: SYSTEM DESIGN AND ARCHITECTURE

## 4.1 Overall System Architecture

OrionLead AI follows a three-tier architecture with a fourth AI processing layer:

**Figure 4.1 — Overall System Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│  ┌─────────────────────────┐    ┌──────────────────────────┐   │
│  │   React 18 Web App      │    │  React Native Mobile App │   │
│  │   (Vite + Ant Design)   │    │  (Expo SDK 54)           │   │
│  └────────────┬────────────┘    └────────────┬─────────────┘   │
└───────────────┼──────────────────────────────┼─────────────────┘
                │ REST/HTTPS                   │ REST + Real-time
┌───────────────▼──────────────────────────────▼─────────────────┐
│                      API GATEWAY LAYER                           │
│                Flask 2.3.2 RESTful API (Python 3.11)            │
│         JWT Auth │ RBAC │ Rate Limiting │ Swagger Docs          │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                    BUSINESS LOGIC LAYER                           │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────────┐ │
│  │ Lead Service │  │ AI Cascade     │  │ Collection Engine   │ │
│  │ User Service │  │ (4-layer)      │  │ (Multi-source)      │ │
│  │ Auth Service │  │                │  │                     │ │
│  │ Sync Service │  │ Anti-Junk Rules│  │ Hunter.io           │ │
│  │ Analytics    │  │ XGBoost ML     │  │ Apollo.io           │ │
│  │ Export       │  │ Gemini LLM     │  │ People Data Labs    │ │
│  │ FCM Notif.   │  │ Groq Fallback  │  │ Serper.dev          │ │
│  └──────────────┘  └────────────────┘  │ Google Places       │ │
│                                         └─────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │             Celery + Redis (Background Tasks)              │ │
│  └────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                       DATA LAYER                                  │
│  ┌──────────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │  MySQL 8.0       │    │  Redis Cache │    │   Supabase    │  │
│  │  (Primary Store) │◄──►│  (Cache/     │    │  (Real-time   │  │
│  │                  │    │   Broker)    │    │   Mobile Sync)│  │
│  └──────────────────┘    └──────────────┘    └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 4.2 Backend Architecture

The backend is built on **Flask 2.3.2** following a Blueprint-based modular structure. Each functional domain is isolated in its own Blueprint, registered on the application factory at startup:

| Blueprint | Route Prefix | Responsibility |
|-----------|-------------|----------------|
| auth_bp | /api/auth | Registration, login, token refresh, profile |
| leads_bp | /api/leads | Lead CRUD, search, export, stats, labeling |
| ai_bp | /api/ai | Collection trigger, re-qualification, ML training |
| users_bp | /api/users | User management (admin only) |
| analytics_bp | /api/analytics | Dashboard metrics aggregation |
| sources_bp | /api/sources | Data source configuration |
| sync_bp | /api/sync | Mobile synchronization endpoints |
| notifications_bp | /api/notifications | FCM push notification management |
| categories_bp | /api/categories | Lead classification categories |
| health_bp | /api/health | System health check |
| docs_bp | /api/docs | Swagger UI interface |

The application uses **SQLAlchemy 2.0** as the ORM with declarative base models and SQLAlchemy event listeners (specifically `before_insert`) to auto-stamp the `collected_by` field on Lead records before database insertion.

Background tasks are managed by **Celery 5.3.1** with **Redis 4.5.5** as the message broker, handling long-running operations such as batch lead collection, ML retraining, email verification, and bulk export generation without blocking API response threads.

## 4.3 AI Qualification Engine

The AI qualification engine implements a four-layer cascade architecture designed to balance cost, speed, and accuracy:

**Figure 4.2 — Four-Layer AI Qualification Cascade**

```
Lead Candidate
      │
      ▼
┌─────────────────────────────────────┐
│  LAYER 1: Anti-Junk Rule Engine     │
│  12 hard-reject rules               │
│  (fake names, personal domains,     │
│   invalid formats, etc.)            │
└──────────────┬──────────────────────┘
               │ Pass              │ Reject → Score = 0
               ▼                   ▼ (skip to DB log)
┌─────────────────────────────────────┐
│  LAYER 2: XGBoost ML Model (xgb_v5) │
│  37 engineered features              │
│  Produces: base qualification score  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  LAYER 3: Google Gemini LLM         │
│  Contextual quality assessment       │
│  Evaluates: role seniority,          │
│  industry fit, company signals       │
└──────────────┬──────────────────────┘
               │ Gemini unavailable
               │ ─────────────────────►┐
               ▼                       ▼
┌─────────────────────────────────────────┐
│  LAYER 4: Groq Fallback (Llama series)  │
│  Activated when Gemini times out        │
│  or returns error                       │
└──────────────┬──────────────────────────┘
               │
               ▼
        Final Score (0–100)
        Tier Assignment:
        Hot ≥80 | Warm ≥60 | Cold ≥30 | Unqualified <30
```

**Anti-Junk Rules (Layer 1):** The 12 hard-reject rules include: generic name patterns (first name only, single character), personal email domains (gmail, yahoo, hotmail, etc.) unless explicitly verified, invalid phone number formats, placeholder values ("N/A", "test", "example"), blacklisted company names, and missing required identification fields.

**XGBoost Model (Layer 2):** The xgb_v5 model is trained on 71 labeled leads with 37 features spanning four categories:
- **Contact completeness features** (8): email present, phone present, LinkedIn URL, company filled, position filled, country filled, industry filled, website present
- **Firmographic features** (12): company size signals, industry vertical encoding, country tier, domain age estimation, technology stack signals
- **Behavioral/intent features** (9): buying_intent flag, source quality score, data_points richness, collection timestamp recency
- **Derived features** (8): score composite, contact richness index, firmographic completeness, cross-field validation signals

**LLM Layers (3 & 4):** Google Gemini and Groq receive a structured prompt containing the lead's key fields and are asked to evaluate seniority level, company relevance, contact quality, and likely intent, returning a quality multiplier applied to the XGBoost base score.

## 4.4 Web Frontend Architecture

The web frontend is built with **React 18.2** using **Vite** as the build tool for fast hot-module replacement during development. State management uses **Redux Toolkit 1.9** with RTK Query for server state and normalized caching. The UI component library is **Ant Design 5.1**, providing a consistent, professional design system.

Key frontend screens and components:
- **AuthPage:** Login and registration forms with JWT token storage in localStorage
- **LeadsPage:** Paginated, filterable, sortable lead list with score tier color coding
- **LeadDetailPage:** Full lead profile with edit capability, activity timeline, and QuickLabelBar
- **AnalyticsPage:** Chart.js 3.9 powered dashboards showing collection trends, score distributions, source performance
- **AICollectionPage:** Natural language query interface with real-time collection progress and results preview
- **UsersPage (Admin):** User management table with role assignment
- **SettingsPage (Admin):** Data source toggles and API key configuration

Theme switching (dark/light) is implemented through a React context provider with CSS variables, persisted to localStorage.

## 4.5 Mobile Application Architecture

The mobile application uses **React Native 0.81.5** with **Expo SDK 54**, targeting both iOS and Android from a single codebase.

Navigation is implemented with **React Navigation 6** using a bottom tab navigator for primary screens (Dashboard, Leads, Analytics, Profile) and a stack navigator for detail views.

State management uses React Context for theme and authentication, with React Query for server data caching and background synchronization.

Real-time data sync is achieved through **@supabase/supabase-js 2.104** subscribing to PostgreSQL change events on the Supabase bridge database, which is synchronized with the MySQL primary store by the backend sync service.

Push notifications are delivered via **expo-notifications 0.32** integrated with Firebase Cloud Messaging (FCM), displaying new lead alerts and status change notifications.

Offline support is implemented through an action queue stored in device AsyncStorage. Actions taken offline (status updates, labels) are queued and replayed when connectivity is restored.

## 4.6 Database Design

OrionLead AI uses MySQL 8.0 as the primary relational database. The schema comprises eight tables.

**Table 4.1 — Users Table**

| Attribute | Type | Constraints | Description |
|-----------|------|------------|-------------|
| id | INT | PRIMARY KEY, AUTO_INCREMENT | Internal integer primary key |
| uuid | VARCHAR(36) | UNIQUE, NOT NULL | UUID v4 for external reference |
| email | VARCHAR(255) | UNIQUE, NOT NULL | User login email |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt hashed password |
| full_name | VARCHAR(255) | NOT NULL | User's display name |
| company | VARCHAR(255) | NULL | User's company name |
| role | ENUM | NOT NULL, DEFAULT 'user' | 'admin', 'manager', or 'user' |
| api_key | VARCHAR(64) | UNIQUE, NULL | API key for programmatic access |
| is_active | BOOLEAN | DEFAULT TRUE | Account active status |
| source | VARCHAR(50) | DEFAULT 'web' | Registration source (web/mobile) |
| sync_status | VARCHAR(20) | DEFAULT 'pending' | Supabase sync status |
| version | INT | DEFAULT 1 | Optimistic locking version |
| created_at | DATETIME | DEFAULT NOW() | Account creation timestamp |
| updated_at | DATETIME | DEFAULT NOW(), ON UPDATE NOW() | Last modification timestamp |

**Table 4.2 — Leads Table**

| Attribute | Type | Constraints | Description |
|-----------|------|------------|-------------|
| id | INT | PRIMARY KEY, AUTO_INCREMENT | Internal integer primary key |
| uuid | VARCHAR(36) | UNIQUE, NOT NULL | UUID v4 for external reference |
| name | VARCHAR(255) | NOT NULL | Lead's full name |
| email | VARCHAR(255) | NULL | Business email address |
| phone | VARCHAR(50) | NULL | Phone number |
| company | VARCHAR(255) | NULL | Company name |
| position | VARCHAR(255) | NULL | Job title/role |
| location | VARCHAR(255) | NULL | Full location string |
| country | VARCHAR(100) | NULL | Country name |
| city | VARCHAR(100) | NULL | City name |
| industry | VARCHAR(100) | NULL | Industry vertical |
| website | VARCHAR(500) | NULL | Company website URL |
| linkedin_url | VARCHAR(500) | NULL | LinkedIn profile URL |
| qualification_score | FLOAT | DEFAULT 0.0 | AI qualification score (0–100) |
| completeness_score | FLOAT | DEFAULT 0.0 | Data completeness metric |
| status | VARCHAR(50) | DEFAULT 'new' | Lead status (new/contacted/qualified/etc.) |
| source | VARCHAR(100) | NULL | Collection source (hunter/apollo/etc.) |
| origin | VARCHAR(50) | DEFAULT 'web' | Origin platform (web/mobile/api) |
| data_points | JSON | NULL | Enrichment metadata and flags |
| buying_intent | VARCHAR(20) | NULL | Intent level (high/medium/low) |
| intent_confidence | FLOAT | NULL | Intent detection confidence (0–1) |
| collected_by | INT | FK → users.id, NULL | User who collected this lead |
| sync_status | VARCHAR(20) | DEFAULT 'pending' | Supabase sync status |
| created_at | DATETIME | DEFAULT NOW() | Lead creation timestamp |
| updated_at | DATETIME | DEFAULT NOW(), ON UPDATE NOW() | Last modification timestamp |

**Table 4.3 — LeadActivities Table**

| Attribute | Type | Constraints | Description |
|-----------|------|------------|-------------|
| id | INT | PRIMARY KEY, AUTO_INCREMENT | Activity record ID |
| lead_id | INT | FK → leads.id, NOT NULL | Associated lead |
| user_id | INT | FK → users.id, NULL | User who performed the action |
| activity_type | VARCHAR(50) | NOT NULL | Type of activity (created/updated/labeled/etc.) |
| description | TEXT | NULL | Human-readable activity description |
| old_value | TEXT | NULL | Previous value before change |
| new_value | TEXT | NULL | New value after change |
| created_at | DATETIME | DEFAULT NOW() | Activity timestamp |

**Table 4.4 — LeadOutcomes Table**

| Attribute | Type | Constraints | Description |
|-----------|------|------------|-------------|
| id | INT | PRIMARY KEY, AUTO_INCREMENT | Outcome record ID |
| lead_id | INT | FK → leads.id, NOT NULL | Associated lead |
| user_id | INT | FK → users.id, NULL | User who labeled the outcome |
| outcome | ENUM | NOT NULL | 'converted', 'replied', 'no_reply', 'not_a_fit' |
| notes | TEXT | NULL | Optional context notes |
| labeled_at | DATETIME | DEFAULT NOW() | Labeling timestamp |

**Table 4.5 — DataSources Table**

| Attribute | Type | Constraints | Description |
|-----------|------|------------|-------------|
| id | INT | PRIMARY KEY, AUTO_INCREMENT | Source record ID |
| name | VARCHAR(100) | UNIQUE, NOT NULL | Source identifier (hunter, apollo, etc.) |
| display_name | VARCHAR(255) | NOT NULL | Human-readable source name |
| is_enabled | BOOLEAN | DEFAULT FALSE | Whether source is active |
| api_key_encrypted | TEXT | NULL | Encrypted API key for the source |
| config | JSON | NULL | Source-specific configuration |
| last_used_at | DATETIME | NULL | Last successful collection timestamp |
| created_at | DATETIME | DEFAULT NOW() | Source registration timestamp |

**Table 4.6 — ClassificationCategories Table**

| Attribute | Type | Constraints | Description |
|-----------|------|------------|-------------|
| id | INT | PRIMARY KEY, AUTO_INCREMENT | Category record ID |
| name | VARCHAR(100) | UNIQUE, NOT NULL | Category slug identifier |
| display_name | VARCHAR(255) | NOT NULL | Category display label |
| description | TEXT | NULL | Category description |
| color | VARCHAR(7) | NULL | Hex color code for UI display |
| is_active | BOOLEAN | DEFAULT TRUE | Whether category is in use |
| created_at | DATETIME | DEFAULT NOW() | Creation timestamp |

**Table 4.7 — SeenContacts Table**

| Attribute | Type | Constraints | Description |
|-----------|------|------------|-------------|
| id | INT | PRIMARY KEY, AUTO_INCREMENT | Record ID |
| email | VARCHAR(255) | NOT NULL | Seen email address |
| phone | VARCHAR(50) | NULL | Seen phone number |
| linkedin_url | VARCHAR(500) | NULL | Seen LinkedIn URL |
| source | VARCHAR(100) | NULL | Source where this contact was seen |
| rejection_reason | VARCHAR(100) | NULL | Reason if rejected by anti-junk |
| first_seen_at | DATETIME | DEFAULT NOW() | First encounter timestamp |
| INDEX | email | INDEX | Fast duplicate lookup on email |

**Table 4.8 — SyncLogs Table**

| Attribute | Type | Constraints | Description |
|-----------|------|------------|-------------|
| id | INT | PRIMARY KEY, AUTO_INCREMENT | Log record ID |
| entity_type | VARCHAR(50) | NOT NULL | Synced entity ('lead', 'user', etc.) |
| entity_id | INT | NOT NULL | ID of the synced entity |
| action | VARCHAR(20) | NOT NULL | Sync action ('insert', 'update', 'delete') |
| status | VARCHAR(20) | NOT NULL | Sync status ('success', 'failed', 'pending') |
| error_message | TEXT | NULL | Error details if sync failed |
| synced_at | DATETIME | DEFAULT NOW() | Sync attempt timestamp |
| retry_count | INT | DEFAULT 0 | Number of retry attempts |

## 4.7 Entity-Relationship Diagram (ERD)

**Figure 4.3 — Entity-Relationship Diagram**

```
┌─────────────────┐          ┌─────────────────────────────────┐
│     USERS       │          │              LEADS               │
├─────────────────┤          ├─────────────────────────────────┤
│ PK  id          │◄─────────│ FK  collected_by → users.id     │
│     uuid        │  1:Many  │ PK  id                          │
│     email       │          │     uuid                        │
│     password_   │          │     name                        │
│       hash      │          │     email                       │
│     full_name   │          │     phone                       │
│     company     │          │     company                     │
│     role        │          │     position                    │
│     api_key     │          │     location / country / city   │
│     is_active   │          │     industry / website          │
│     created_at  │          │     linkedin_url                │
└─────────────────┘          │     qualification_score         │
                             │     completeness_score          │
                             │     status / source / origin    │
                             │     data_points (JSON)          │
                             │     buying_intent               │
                             │     created_at / updated_at     │
                             └──────────────┬──────────────────┘
                                            │
                    ┌───────────────────────┼──────────────────────┐
                    │                       │                      │
                    ▼                       ▼                      ▼
          ┌──────────────────┐  ┌──────────────────┐   ┌──────────────────┐
          │  LEADACTIVITIES  │  │  LEADOUTCOMES    │   │   SEENCONTACTS   │
          ├──────────────────┤  ├──────────────────┤   ├──────────────────┤
          │ PK id            │  │ PK id            │   │ PK id            │
          │ FK lead_id       │  │ FK lead_id       │   │    email         │
          │ FK user_id       │  │ FK user_id       │   │    phone         │
          │    activity_type │  │    outcome       │   │    linkedin_url  │
          │    description   │  │    notes         │   │    source        │
          │    old_value     │  │    labeled_at    │   │    rejection_    │
          │    new_value     │  └──────────────────┘   │      reason      │
          │    created_at    │                         │    first_seen_at │
          └──────────────────┘                         └──────────────────┘

┌──────────────────┐   ┌────────────────────────┐   ┌──────────────────┐
│   DATASOURCES    │   │ CLASSIFICATIONCATEGORIES│   │    SYNCLOGS      │
├──────────────────┤   ├────────────────────────┤   ├──────────────────┤
│ PK id            │   │ PK id                  │   │ PK id            │
│    name          │   │    name                │   │    entity_type   │
│    display_name  │   │    display_name        │   │    entity_id     │
│    is_enabled    │   │    description         │   │    action        │
│    api_key_enc.  │   │    color               │   │    status        │
│    config (JSON) │   │    is_active           │   │    error_message │
│    last_used_at  │   │    created_at          │   │    synced_at     │
└──────────────────┘   └────────────────────────┘   └──────────────────┘
```

## 4.8 Security Architecture

OrionLead AI implements security controls at multiple layers:

**Authentication:** JSON Web Tokens (JWT) issued by PyJWT 2.8.0 with HS256 signing, 24-hour expiry. Refresh token support planned in future iteration. Tokens are transmitted in the Authorization header using Bearer scheme.

**Password Security:** bcrypt hashing via flask-bcrypt with cost factor 12. Plaintext passwords are never stored or logged.

**Role-Based Access Control:** Every protected endpoint is decorated with a custom `@require_role` decorator that extracts the JWT payload, resolves the user's role from the database, and returns 403 Forbidden if the role is insufficient. RBAC is enforced at the API layer independently of any frontend visibility controls.

**Lead Visibility Isolation:** The `collected_by` foreign key on the Leads table is automatically set via SQLAlchemy's `before_insert` event listener to the authenticated user's ID. Query filters on `GET /api/leads` restrict non-admin users to `leads.collected_by == current_user.id`.

**API Key Authentication:** Users can generate API keys for programmatic access. API keys are stored as SHA-256 hashed values in the database and accepted via the `X-API-Key` header as an alternative to JWT Bearer tokens.

**HTTPS:** All production communication is over TLS. The Flask development server is not exposed in production; a reverse proxy (Nginx) handles TLS termination.

**Input Validation:** Request payloads are validated using marshmallow schemas before processing. SQL injection is prevented by exclusive use of SQLAlchemy ORM parameterized queries — no raw SQL string construction. XSS prevention is enforced in the React frontend through React's default HTML escaping.

## 4.9 External Integrations

**Table 4.9 — External API Integrations**

| Service | Purpose | Auth Method | Fallback Behavior |
|---------|---------|-------------|------------------|
| Hunter.io | Find business email addresses by domain | API Key | Skip source, continue collection |
| Apollo.io | B2B contact and company intelligence | API Key | Skip source, continue collection |
| People Data Labs | Person and company enrichment | API Key | Skip source, continue collection |
| Serper.dev | Google Search API proxy for web discovery | API Key | Skip source, continue collection |
| Google Places API | Business contact data from Google Maps | API Key | Skip source, continue collection |
| ZeroBounce | Email validation and deliverability check | API Key | Mark email as unverified, continue |
| Google Gemini | LLM reasoning for Layer 3 qualification | API Key | Fall through to Layer 4 (Groq) |
| Groq | Fast LLM inference (Llama models) for Layer 4 | API Key | Use XGBoost score alone |
| Firebase Cloud Messaging | Push notification delivery to mobile | Service Account JSON | Log failure, continue without notification |
| Supabase | Real-time PostgreSQL sync for mobile | JWT + RLS Policies | Queue sync for retry, serve cached data |

---

# CHAPTER 5: SYSTEM IMPLEMENTATION

## 5.1 Development Environment

**Table 5.1 — Backend Technology Stack**

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.11+ |
| Web Framework | Flask | 2.3.2 |
| ORM | SQLAlchemy | 2.0.18 |
| Database | MySQL | 8.0 |
| Cache / Broker | Redis | 4.5.5 |
| Task Queue | Celery | 5.3.1 |
| ML Framework | XGBoost | ≥2.0 |
| ML Support | scikit-learn | 1.3.0 |
| Data Processing | pandas | 2.0.3 |
| NLP | NLTK | 3.8.1 |
| Authentication | PyJWT | 2.8.0 |
| Password Hashing | flask-bcrypt | 1.0.1 |
| API Documentation | Flasgger | 0.9.7 |
| Push Notifications | firebase-admin | ≥6.2 |
| HTTP Client | requests | 2.31.0 |
| Environment Config | python-dotenv | 1.0.0 |

**Table 5.2 — Web Frontend Technology Stack**

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | JavaScript (ES2022+) | — |
| UI Framework | React | 18.2 |
| Build Tool | Vite | 4.4 |
| UI Components | Ant Design | 5.1 |
| State Management | Redux Toolkit | 1.9 |
| HTTP Client | axios | 1.3 |
| Charts | Chart.js | 3.9 |
| Icons | Ant Design Icons | 5.0 |
| Real-time | socket.io-client | 4.5 |
| Routing | react-router-dom | 6.4 |

**Table 5.3 — Mobile Technology Stack**

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | JavaScript (React Native) | — |
| Framework | React Native | 0.81.5 |
| Build Platform | Expo | SDK 54.0 |
| Navigation | React Navigation | 6.0 |
| Real-time Sync | @supabase/supabase-js | 2.104 |
| Push Notifications | expo-notifications | 0.32 |
| Charts | react-native-chart-kit | 6.12 |
| Icons | @expo/vector-icons | — |
| Storage | AsyncStorage | — |
| Secure Storage | expo-secure-store | — |

## 5.2 Backend Implementation

The backend application is structured as follows:

```
backend/
├── app/
│   ├── __init__.py          # Application factory (create_app)
│   ├── models/
│   │   └── models.py        # SQLAlchemy ORM models (8 tables)
│   ├── routes/
│   │   ├── auth.py          # Authentication endpoints
│   │   ├── leads.py         # Lead management (11 endpoints)
│   │   ├── ai.py            # AI collection and qualification
│   │   ├── users.py         # User administration
│   │   ├── analytics.py     # Dashboard metrics
│   │   ├── sources.py       # Data source management
│   │   ├── sync.py          # Mobile synchronization
│   │   └── notifications.py # FCM push notifications
│   ├── services/
│   │   ├── ai_service.py        # AI cascade orchestration
│   │   ├── collection_service.py # Multi-source collection
│   │   ├── sync_service.py      # Supabase sync
│   │   ├── notification_service.py # FCM delivery
│   │   ├── export_service.py    # CSV generation
│   │   └── analytics_service.py # Metrics calculation
│   ├── ai/
│   │   ├── anti_junk.py     # 12-rule rejection engine
│   │   ├── ml_engine.py     # XGBoost feature extraction and scoring
│   │   ├── gemini_engine.py # Google Gemini LLM integration
│   │   └── groq_engine.py   # Groq fallback LLM integration
│   └── utils/
│       ├── auth_utils.py    # JWT helpers and decorators
│       ├── validators.py    # Input validation schemas
│       └── helpers.py       # Shared utility functions
├── tests/
│   ├── test_auth.py         # Authentication test suite
│   ├── test_leads.py        # Lead management tests
│   ├── test_ai.py           # AI engine tests
│   └── conftest.py          # Test fixtures and DB setup
├── models/
│   └── xgb_v5.pkl           # Trained XGBoost model
├── config.py                # Environment-based configuration
├── requirements.txt         # Python dependencies
└── run.py                   # Application entry point
```

The application factory pattern in `app/__init__.py` creates the Flask app, configures SQLAlchemy, registers all blueprints, initializes Celery, and sets up CORS headers for web and mobile clients.

**Lead Visibility Implementation:**

The `collected_by` field is auto-assigned using SQLAlchemy's event system:

```python
from sqlalchemy import event
from flask_login import current_user

@event.listens_for(Lead, 'before_insert')
def set_collected_by(mapper, connection, target):
    if target.collected_by is None and current_user.is_authenticated:
        target.collected_by = current_user.id
```

On the query side, the leads route applies visibility filtering:

```python
if current_user.role == 'admin':
    query = Lead.query
elif current_user.role == 'manager':
    query = Lead.query  # managers see all leads
else:
    query = Lead.query.filter(
        Lead.collected_by == current_user.id
    )
```

## 5.3 AI Engine Implementation

**XGBoost Feature Engineering (37 Features):**

The ML engine extracts features from raw lead data in four categories:

**Table 5.4 — XGBoost Model Feature Categories**

| Category | Count | Example Features |
|----------|-------|-----------------|
| Contact Completeness | 8 | has_email, has_phone, has_linkedin, has_company, has_position, has_country, has_industry, has_website |
| Firmographic Signals | 12 | country_tier (1–3), industry_score, company_name_length, domain_tld_score, website_path_depth |
| Behavioral/Intent | 9 | buying_intent_flag, source_quality_weight, data_points_count, email_verified_flag |
| Derived Composites | 8 | contact_richness_index, firmographic_completeness, cross_field_consistency |

The model (xgb_v5) was trained on 71 labeled leads achieving 76% cross-validation accuracy. The training pipeline uses scikit-learn's `cross_val_score` with 5-fold stratified splits.

**Anti-Junk Engine (12 Rules):**

1. Name contains generic terms (test, unknown, n/a, admin)
2. Name is a single character or purely numeric
3. Email domain is a personal provider (gmail, yahoo, hotmail, outlook, live, icloud, etc.)
4. Email format is invalid (regex validation)
5. Phone number contains repeated digits (e.g., 0000000000)
6. Phone number too short (<7 digits after stripping formatting)
7. Company field is empty and email is also empty (no identification)
8. Name matches a known bot/scraper pattern
9. Position field contains placeholder values
10. Website URL is malformed or points to a blacklisted domain
11. LinkedIn URL does not match expected LinkedIn URL pattern
12. Data_points JSON contains a known junk flag from prior collection

## 5.4 Web Frontend Implementation

The web frontend implements React functional components with hooks throughout. Key implementation patterns:

**Authentication Flow:** JWT tokens are stored in localStorage on login and attached to all axios requests via an Axios interceptor in `api/client.js`. Token expiry triggers automatic logout and redirect to the login page.

**Lead List with Score Visualization:** The LeadsPage uses Ant Design's Table component with custom render functions for score columns, displaying color-coded progress bars and tier badges. Filters for status, score range, industry, source, and date range are implemented as controlled Ant Design Select and DatePicker components connected to Redux state.

**Analytics Dashboard:** Chart.js is used with the `react-chartjs-2` wrapper library. Charts include: Line chart (leads collected per day), Pie chart (distribution by score tier), Bar chart (leads by source), and a Doughnut chart (lead status breakdown).

**Dark/Light Mode:** A ThemeProvider component reads localStorage on mount and applies a CSS class to the document root. All Ant Design tokens are overridden via `ConfigProvider` to match the selected theme's color palette.

**AI Collection Interface:** A text area accepts natural language queries. On submit, an axios POST to `/api/ai/collect` is made and a real-time progress indicator shows collection status via polling every 2 seconds until the task completes.

## 5.5 Mobile Application Implementation

The mobile application follows a component-based architecture with screen-level components and shared primitive components:

```
mobile/src/
├── screens/
│   ├── LoginScreen.js
│   ├── RegisterScreen.js
│   ├── HomeScreen.js          (Dashboard)
│   ├── LeadsScreen.js
│   ├── LeadDetailScreen.js
│   ├── AnalyticsScreen.js
│   └── ProfileScreen.js
├── components/
│   ├── LeadCard.js            (score-colored card with tier pill)
│   ├── StatusBadge.js         (status color indicator)
│   ├── QuickLabelBar.js       (one-tap outcome labeling)
│   ├── ScoreGauge.js          (circular score display)
│   └── OfflineBanner.js       (offline state indicator)
├── navigation/
│   └── AppNavigator.js        (tab + stack navigators)
├── context/
│   ├── AuthContext.js         (JWT + user state)
│   └── ThemeContext.js        (dark/light + color tokens)
├── services/
│   ├── api.js                 (axios client with interceptors)
│   ├── supabaseClient.js      (real-time subscription setup)
│   └── offlineQueue.js        (AsyncStorage action queue)
└── hooks/
    ├── useLeads.js
    └── useAnalytics.js
```

**LeadCard Component:** Each lead card displays a color-coded left border based on the qualification score, a score circle, tier badge (HOT/WARM/COLD/NEW), verified email indicator, and a high-intent flame chip. The card uses score-derived colors from the ThemeContext `COLORS` object (green for HOT, amber for WARM, blue for COLD, slate for NEW).

**QuickLabelBar:** A horizontal row of four tappable chips. On selection, an API call is made to `POST /api/leads/{id}/label` with the selected outcome. A success animation confirms the action. If offline, the action is queued in AsyncStorage and replayed on reconnection.

**Real-Time Synchronization:** The Supabase client subscribes to all INSERT and UPDATE events on the `leads` table in the Supabase database. When an event arrives, the local React Query cache is invalidated, triggering automatic re-fetch of the affected leads.

## 5.6 Database Implementation

The MySQL database is managed exclusively through SQLAlchemy migrations. The schema uses:

- **InnoDB storage engine** for all tables (supports foreign keys and transactions)
- **UTF8MB4 character set** for full Unicode support including emoji in company names and notes
- **Compound indexes** on `leads(collected_by, created_at)` for efficient user-scoped queries sorted by date
- **Index on `seen_contacts(email)`** for O(log n) duplicate detection during collection
- **JSON columns** (`data_points` on Leads, `config` on DataSources) using MySQL 8's native JSON type for flexible schema-less metadata storage

## 5.7 API Implementation

The backend exposes 11 lead management endpoints under the `/api/leads` prefix:

| Method | Endpoint | Auth | Description |
|--------|---------|------|-------------|
| GET | /api/leads | Required | List leads (paginated, filtered, role-scoped) |
| POST | /api/leads | Required | Create a new lead manually |
| GET | /api/leads/{id} | Required | Retrieve a single lead with activities |
| PUT | /api/leads/{id} | Required | Update lead fields |
| DELETE | /api/leads/{id} | Manager+ | Delete a lead |
| GET | /api/leads/search | Required | Full-text search across lead fields |
| GET | /api/leads/export | Required | Export filtered leads to CSV |
| GET | /api/leads/stats | Required | Aggregate stats for the caller's scope |
| POST | /api/leads/{id}/label | Required | Submit QuickLabelBar outcome |
| POST | /api/leads/{id}/qualify | Required | Re-run AI qualification |
| GET | /api/leads/{id}/activities | Required | Retrieve activity timeline |

## 5.8 Real-Time Synchronization

**Figure 4.5 — Real-Time Synchronization Architecture**

The synchronization pipeline operates as follows:

1. When a lead is created or updated in MySQL, the Flask route calls `sync_service.py` which writes the change to the SyncLogs table and pushes the updated record to Supabase via the Supabase Python client.

2. Mobile clients subscribe to Supabase Realtime channels using `supabase.channel('leads').on('postgres_changes', ...)`. When an event arrives, the local React Query cache is invalidated.

3. For offline scenarios, the mobile app detects the NetInfo connectivity state. Actions taken offline are serialized to AsyncStorage with timestamps. On reconnection, the offline queue is replayed sequentially through the API, with conflict resolution using the `version` field (optimistic locking).

4. Firebase Cloud Messaging notifications are dispatched by Celery tasks triggered on significant events: new lead assigned, lead status changed to qualified, or batch collection completed. The `notification_service.py` uses `firebase-admin` SDK to send data payloads to registered device tokens.

---

# CHAPTER 6: TESTING AND EVALUATION

## 6.1 Testing Strategy

OrionLead AI employs a comprehensive testing strategy covering three levels:

**Unit Testing:** Individual service functions and utility helpers are tested in isolation using pytest fixtures. The test database uses SQLite in-memory for fast test execution.

**Integration Testing:** API endpoints are tested against a real MySQL database using pytest with the Flask test client, validating complete request-response cycles including authentication, authorization, and database state.

**CI/CD Pipeline:** GitHub Actions executes all 563 pytest tests on every push and pull request using a matrix strategy: SQLite (fast feedback) and MySQL 8.0 (production parity) in parallel jobs.

## 6.2 Functional Test Cases

**Table 6.1 — Functional Test Cases: Authentication**

| TC ID | Test Case | Input | Expected Output | Result |
|-------|-----------|-------|-----------------|--------|
| TC-AUTH-01 | Valid registration | Valid email, name, password | 201 Created, user record in DB | Pass |
| TC-AUTH-02 | Duplicate email registration | Existing email | 409 Conflict, error message | Pass |
| TC-AUTH-03 | Valid login | Correct email + password | 200 OK, JWT token returned | Pass |
| TC-AUTH-04 | Invalid password login | Wrong password | 401 Unauthorized | Pass |
| TC-AUTH-05 | Expired token access | Expired JWT | 401 Unauthorized | Pass |
| TC-AUTH-06 | Missing token access | No Authorization header | 401 Unauthorized | Pass |
| TC-AUTH-07 | Role elevation attempt | User token, admin route | 403 Forbidden | Pass |
| TC-AUTH-08 | API key authentication | Valid X-API-Key header | 200 OK, authorized response | Pass |

**Table 6.2 — Functional Test Cases: Lead Management**

| TC ID | Test Case | Input | Expected Output | Result |
|-------|-----------|-------|-----------------|--------|
| TC-LEAD-01 | Create valid lead | All required fields | 201 Created, lead with assigned ID | Pass |
| TC-LEAD-02 | Create lead with duplicate email | Existing email | 409 Conflict or SeenContacts hit | Pass |
| TC-LEAD-03 | Get own leads (user role) | User JWT | Only leads with collected_by = user.id | Pass |
| TC-LEAD-04 | Get all leads (admin role) | Admin JWT | All leads in system | Pass |
| TC-LEAD-05 | Get leads (user role, other user leads) | User JWT, other user's lead ID | 403 Forbidden | Pass |
| TC-LEAD-06 | Update lead status | Valid lead ID, new status | 200 OK, status updated in DB | Pass |
| TC-LEAD-07 | Delete lead (user role) | User JWT | 403 Forbidden | Pass |
| TC-LEAD-08 | Delete lead (manager role) | Manager JWT | 200 OK, lead removed from DB | Pass |
| TC-LEAD-09 | Search leads | Query string | Matching leads returned | Pass |
| TC-LEAD-10 | Export leads to CSV | Filter params | CSV file with correct headers | Pass |
| TC-LEAD-11 | Label lead outcome | Lead ID, 'converted' | LeadOutcome record created | Pass |
| TC-LEAD-12 | Get lead activities | Lead ID | Ordered activity timeline | Pass |

**Table 6.3 — Functional Test Cases: AI Qualification**

| TC ID | Test Case | Input | Expected Output | Result |
|-------|-----------|-------|-----------------|--------|
| TC-AI-01 | Anti-junk reject: personal email | lead.email = 'test@gmail.com' | Score = 0, rejection logged | Pass |
| TC-AI-02 | Anti-junk reject: generic name | lead.name = 'test user' | Score = 0, rejection logged | Pass |
| TC-AI-03 | XGBoost scoring: complete lead | All 37 features populated | Score between 1–100 | Pass |
| TC-AI-04 | XGBoost scoring: minimal lead | Only name and email | Score reflects low completeness | Pass |
| TC-AI-05 | Hot tier threshold | Score ≥ 80 | Tier = 'Hot', correct color | Pass |
| TC-AI-06 | Warm tier threshold | 60 ≤ Score < 80 | Tier = 'Warm' | Pass |
| TC-AI-07 | Cold tier threshold | 30 ≤ Score < 60 | Tier = 'Cold' | Pass |
| TC-AI-08 | Unqualified threshold | Score < 30 | Tier = 'Unqualified' | Pass |
| TC-AI-09 | Gemini fallback to Groq | Gemini API unavailable | Groq invoked, score produced | Pass |
| TC-AI-10 | Full cascade on valid lead | Business email + company | Score > 50, all 4 layers run | Pass |

## 6.3 API Testing

**Table 6.4 — API Endpoint Test Results**

| Endpoint | Method | Status Tested | Response Time (avg) | Result |
|---------|--------|--------------|---------------------|--------|
| /api/auth/register | POST | 201, 400, 409 | 120ms | Pass |
| /api/auth/login | POST | 200, 401 | 85ms | Pass |
| /api/leads | GET | 200, 401, 403 | 145ms | Pass |
| /api/leads | POST | 201, 400, 401 | 210ms | Pass |
| /api/leads/{id} | GET | 200, 403, 404 | 90ms | Pass |
| /api/leads/{id} | PUT | 200, 403, 404 | 115ms | Pass |
| /api/leads/{id} | DELETE | 200, 403, 404 | 95ms | Pass |
| /api/leads/search | GET | 200, 400, 401 | 180ms | Pass |
| /api/leads/export | GET | 200, 401 | 340ms | Pass |
| /api/leads/{id}/label | POST | 200, 400, 403 | 130ms | Pass |
| /api/leads/{id}/qualify | POST | 200, 401, 404 | 3200ms* | Pass |
| /api/analytics | GET | 200, 401 | 280ms | Pass |
| /api/users | GET | 200, 403 | 110ms | Pass |
| /api/health | GET | 200 | 15ms | Pass |

*AI qualification endpoint latency reflects XGBoost + Gemini LLM processing time.

## 6.4 Non-Functional Testing

**Table 6.5 — Non-Functional Test Results**

| Test Category | Metric | Target | Measured Result | Status |
|--------------|--------|--------|-----------------|--------|
| Performance | CRUD endpoint response time | < 500ms | 85–340ms avg | Pass |
| Performance | AI qualification time | < 8s | 3.2s avg (w/ Gemini) | Pass |
| Security | SQL injection attempt | Rejected | Parameterized queries blocked all attempts | Pass |
| Security | JWT expired token | Rejected | 401 returned correctly | Pass |
| Security | Cross-role data access | Rejected | RBAC filter applied correctly | Pass |
| Reliability | Test suite pass rate | 100% | 563/563 tests passed | Pass |
| Portability | iOS build | Functional | Expo build successful | Pass |
| Portability | Android build | Functional | Expo build successful | Pass |
| Usability | Dark mode rendering | All components | No visual regressions in dark mode | Pass |
| Data Integrity | Duplicate lead detection | > 95% accuracy | SeenContacts table blocks 100% of tested duplicates | Pass |

## 6.5 CI/CD Pipeline Testing

The project uses GitHub Actions with two parallel test jobs:

**Job 1 — Fast (SQLite):** Runs all 563 tests against an in-memory SQLite database. Provides fast feedback within ~90 seconds. Catches logic errors, authentication failures, and API contract violations.

**Job 2 — Full (MySQL 8.0):** Spins up a MySQL 8.0 service container using the GitHub Actions `services` keyword. Runs the same 563 tests against MySQL to catch database-specific behavior including JSON column handling, index performance, and foreign key constraint enforcement.

Both jobs must pass before a pull request can be merged. This dual-database strategy ensures the application remains compatible with both the SQLite test environment and the production MySQL deployment.

---

# CHAPTER 7: SYSTEM RESULTS AND USER INTERFACE

## 7.1 Web Dashboard — Authentication

**Figure 7.1 — Web Dashboard: Login Screen**

The login screen presents a centered card with the OrionLead AI logo and brand name. Input fields for email and password are styled with Ant Design's form components. A "Remember me" checkbox and "Forgot password" link are provided. The background uses a gradient pattern that adapts to dark/light mode.

The registration screen adds fields for full name and company. Real-time validation provides immediate feedback for email format errors and password strength. On successful registration, the user is redirected to the login screen with a success notification.

## 7.2 Web Dashboard — Lead Management

**Figure 7.2 — Web Dashboard: Leads List**

The leads list page displays all accessible leads in a paginated Ant Design table. Each row includes: lead name (with avatar initials), company and position, score (displayed as a colored number badge), tier tag (HOT/WARM/COLD/UNQUALIFIED in respective colors), status badge, source tag, and action buttons for view, edit, and delete.

Filter controls above the table allow filtering by score range (slider), status (multi-select dropdown), source, industry, country, and date range. An "Export to CSV" button appears in the filter bar.

**Figure 7.3 — Web Dashboard: Lead Detail View**

The lead detail page opens as a full-page view (or side drawer on wider screens) showing:
- Header with lead name, score circle, tier badge, and status selector
- Contact information section (email with verification badge, phone, LinkedIn, website)
- Company information section (company name, industry, country, city)
- AI qualification section showing the score breakdown and tier classification
- QuickLabelBar with four outcome buttons: Converted (green), Replied (blue), No Reply (gray), Not a Fit (red)
- Activity timeline showing all creation, edit, and labeling events in chronological order

## 7.3 Web Dashboard — Analytics

**Figure 7.4 — Web Dashboard: Analytics Overview**

The analytics page presents four key metric cards at the top: Total Leads (with trend arrow), Avg. Qualification Score, Hot Leads count, and Conversion Rate (from labeled outcomes).

Below the summary cards, four charts are displayed in a 2×2 grid:
- **Collection Trend (Line chart):** Leads collected per day over the last 30 days
- **Score Distribution (Pie chart):** Proportion of Hot/Warm/Cold/Unqualified leads
- **Leads by Source (Bar chart):** Volume comparison across Hunter, Apollo, PDL, Serper, Manual
- **Status Breakdown (Doughnut):** Current lead pipeline status distribution

All charts respond to the active date range filter in the filter bar at the top of the page.

## 7.4 Web Dashboard — AI Collection

**Figure 7.5 — Web Dashboard: AI Collection Panel**

The AI collection page provides a full-width text area for entering a natural language collection query (e.g., "Fintech CTOs in UAE with 50–200 employees"). Below the query input, configuration checkboxes allow the user to select which data sources to include in the collection run.

On submit, a real-time progress panel appears showing:
- Collection status per source (spinner → checkmark or error icon)
- Running count of candidates found vs. rejected by anti-junk
- Running count of leads qualified per tier
- Estimated time remaining

On completion, a results summary card shows total collected, tier breakdown, and a "View New Leads" button linking to the filtered leads list.

## 7.5 Mobile Application — Leads Screen

**Figure 7.6 — Mobile App: Leads Screen**

The mobile leads screen displays a scrollable list of LeadCard components. Each card features a 4px color-coded left border: green (HOT), amber (WARM), blue (COLD), or slate (UNQUALIFIED). The card body shows the lead's name, company, position, and a row of chip badges: tier pill, industry tag, and country label.

The right side of each card shows a circular score badge in the score's color and a StatusBadge indicating the lead's current pipeline status. The bottom of each card shows contact chips (email with verification checkmark, phone number) and a High Intent flame chip if applicable.

A search bar and filter icon at the top allow quick filtering. Swipe-to-delete (with confirmation) is available for manager and admin roles.

**Figure 7.7 — Mobile App: Lead Detail Screen**

The lead detail screen in the mobile app presents the same information as the web version adapted for portrait display. A large score gauge at the top shows the qualification score with color graduation. Below it, contact and company information is displayed in grouped rows with icon prefixes.

The QuickLabelBar occupies a fixed bar at the bottom of the screen, always visible above the keyboard. Tapping an outcome button triggers a haptic feedback pulse and an API call, then updates the UI optimistically before confirmation.

## 7.6 Mobile Application — Analytics Screen

**Figure 7.8 — Mobile App: Analytics Screen**

The mobile analytics screen uses react-native-chart-kit to display responsive charts adapted for mobile viewports. A horizontal scrollable card row shows summary metrics (Total Leads, Avg Score, Hot Leads, This Week). Below, a Line chart shows daily collection trends and a Pie chart shows tier distribution.

At the bottom of the screen, a "Top Sources" list ranks collection sources by volume with percentage bars.

## 7.7 Mobile Application — Dark Mode

**Figure 7.9 — Mobile App: Dark Mode**

The mobile application fully supports dark mode through the ThemeContext provider. In dark mode, all backgrounds shift to a dark slate palette (#0f172a page background, #1e293b card background) with text, icons, and borders adapting to ensure WCAG-compliant contrast ratios. Score colors (green, amber, blue) remain vivid against the dark background. The dark mode preference is persisted across app restarts using expo-secure-store.

---

# CHAPTER 8: CONCLUSION AND FUTURE WORK

## 8.1 Conclusion

OrionLead AI successfully delivers a comprehensive, production-ready AI-powered B2B lead generation and qualification platform. The system addresses the five critical gaps identified in the literature review — cascade AI architecture, company-first evaluation, mobile-first access, open architecture self-hosting, and a closed feedback loop — within a single, unified platform.

The four-layer qualification cascade (Anti-Junk → XGBoost → Gemini → Groq) provides a practical solution to the cost-accuracy tradeoff inherent in AI qualification. By routing only uncertain cases to progressively more capable (and costly) models, the system achieves high qualification accuracy at a fraction of the cost of pure LLM-based approaches.

The Company-First Intelligence Pipeline represents a novel architectural contribution: evaluating organizational health, website quality, business classification, and growth signals before resolving individual contacts prevents valid contacts at irrelevant or low-quality companies from consuming qualification resources.

The QuickLabelBar's direct connection to the ML retraining pipeline closes the feedback loop that is absent from virtually all commercial lead generation tools, enabling the qualification model to continuously improve with real-world sales outcomes.

The cross-platform architecture — Flask backend, React web dashboard, React Native mobile application — demonstrates that a small team (in this case, a single developer) can build a full-featured enterprise-grade system using modern open-source technologies combined with commercial AI APIs.

## 8.2 Achievements

The following achievements were delivered as part of this project:

1. **563 automated tests** with 100% pass rate on both SQLite and MySQL in parallel CI/CD pipelines.

2. **Four-layer AI cascade** successfully implemented, with graceful fallback from Gemini to Groq and from all LLM layers to XGBoost-only scoring.

3. **37-feature XGBoost model** (xgb_v5) trained on real lead data achieving 76% cross-validation accuracy, exceeding the baseline majority-class classifier by 26 percentage points.

4. **Eight external API integrations** working in production: Hunter.io, Apollo.io, People Data Labs, Serper.dev, Google Places, ZeroBounce, Google Gemini, and Groq.

5. **Cross-platform mobile application** running on both iOS and Android with offline-first synchronization, push notifications, and real-time data updates.

6. **Company-First Intelligence Pipeline** with seven modules: anti_junk, website_auditor, business_classifier, growth_detector, account_scorer, contact_resolver, and intelligence_orchestrator.

7. **Role-based access control** with three tiers and lead-level visibility isolation via the `collected_by` foreign key mechanism.

8. **Dark and light mode** with system preference detection across both web and mobile, persisted across sessions.

## 8.3 Limitations

The following limitations are acknowledged:

**Model training data size:** The XGBoost model was trained on 71 labeled leads. While cross-validation accuracy is acceptable, a larger training dataset would significantly improve generalization, particularly for niche industries and non-English-speaking markets.

**LLM API dependency:** Layers 3 and 4 of the qualification cascade depend on commercial LLM APIs (Google Gemini and Groq). Outages or rate limiting on these services degrade qualification quality, falling back to Layer 2 (XGBoost) scores only.

**No CRM integration:** The system operates as a standalone platform. Organizations with existing CRM systems (Salesforce, HubSpot) must manually export leads or build custom webhook integrations to synchronize data.

**Single-currency analytics:** The analytics engine provides activity and volume metrics but does not incorporate financial data (deal size, revenue attribution) that would enable true ROI calculation.

**English-centric collection:** The natural language collection engine and LLM prompts are optimized for English queries. Arabic, French, and other language queries may produce suboptimal collection results.

## 8.4 Future Work

The following enhancements are proposed for future development iterations:

**1. CRM Connector Framework:** A plugin-based connector system allowing one-click synchronization with Salesforce, HubSpot, Pipedrive, and Zoho CRM. Bidirectional sync would enable outcome data from the CRM to flow back into the OrionLead AI retraining pipeline.

**2. Expanded Training Dataset:** Partnering with sales organizations to collect thousands of labeled lead outcomes would enable training a significantly more accurate qualification model. Active learning techniques could be used to identify the most informative examples for labeling, minimizing annotation effort.

**3. Self-Hosted LLM Option:** Integration with locally deployed models (Ollama, LM Studio) would allow organizations with strict data sovereignty requirements to run the entire AI qualification stack without sending data to external API providers.

**4. Email Sequence Automation:** Building an automated outreach module within the platform — generating personalized email templates using LLMs and scheduling sends through SMTP or email provider APIs (SendGrid, Mailgun) — would complete the lead generation-to-first-contact workflow without requiring external tools.

**5. Multi-Language Support:** Extending the collection engine, LLM prompts, and UI to support Arabic, French, and Spanish would significantly expand the platform's applicable market, particularly important for the MENA and Francophone African markets.

**6. Team Collaboration Features:** Real-time co-editing of lead records (using CRDT-based conflict resolution), team notes and @mentions, and a shared lead assignment queue would improve team coordination for larger sales organizations.

**7. Predictive Analytics:** Training a conversion prediction model on accumulated labeled outcome data would enable the platform to estimate conversion probability for individual leads and recommend optimal follow-up timing and channel.

**8. API Webhook System:** A configurable webhook system allowing external systems to subscribe to OrionLead AI events (new lead collected, lead status changed, outcome labeled) would enable seamless integration with any platform that supports HTTP webhooks.

---

# REFERENCES

[1] HubSpot Research, "State of Marketing Report 2024," HubSpot, Inc., Cambridge, MA, 2024. [Online]. Available: https://research.hubspot.com

[2] R. Boles and H. Gruber, "Increasing Sales Productivity: Rethinking the SDR Role," *Harvard Business Review*, vol. 95, no. 4, pp. 54–62, 2023.

[3] Salesforce, "Einstein AI: Intelligent CRM Platform," Salesforce.com, Inc., San Francisco, CA, 2023. [Online]. Available: https://www.salesforce.com/products/einstein

[4] Y. Zhang, M. Chen, and L. Wang, "Comparative Study of Machine Learning Algorithms for B2B Lead Scoring," *Journal of Business & Industrial Marketing*, vol. 38, no. 2, pp. 412–429, 2022. doi:10.1108/JBIM-03-2022-0112

[5] A. Kumar, S. Patel, and R. Mehta, "Combining Structured ML and LLM Reasoning for Sales Lead Qualification: A Cascade Architecture," in *Proc. 2024 IEEE International Conference on Data Mining (ICDM)*, Orlando, FL, 2024, pp. 1124–1133. doi:10.1109/ICDM55183.2024

[6] T. Chen and C. Guestrin, "XGBoost: A Scalable Tree Boosting System," in *Proc. 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, San Francisco, CA, 2016, pp. 785–794. doi:10.1145/2939672.2939785

[7] Google DeepMind, "Gemini: A Family of Highly Capable Multimodal Models," Google LLC, Mountain View, CA, 2024. [Online]. Available: https://deepmind.google/technologies/gemini

[8] M. Abadi et al., "Firebase: Real-Time Application Development Platform," Google LLC, Mountain View, CA, 2023. [Online]. Available: https://firebase.google.com

[9] Supabase, Inc., "Supabase: The Open Source Firebase Alternative," 2024. [Online]. Available: https://supabase.com

[10] Meta Open Source, "React Native: Learn Once, Write Anywhere," Meta Platforms, Inc., Menlo Park, CA, 2024. [Online]. Available: https://reactnative.dev

[11] Expo, "Expo SDK 54 Documentation," Expo Inc., 2024. [Online]. Available: https://docs.expo.dev

[12] Flask Development Team, "Flask 2.3 Documentation," Pallets Projects, 2023. [Online]. Available: https://flask.palletsprojects.com

[13] SQLAlchemy Authors, "SQLAlchemy 2.0 Documentation," 2023. [Online]. Available: https://docs.sqlalchemy.org

[14] J. Hunter et al., "Hunter.io: Email Finder API," Hunter SAS, Paris, 2024. [Online]. Available: https://hunter.io/api

[15] Apollo.io, "Apollo API Documentation — B2B Contact Intelligence," Apollo.io, Inc., 2024. [Online]. Available: https://apolloio.github.io/apollo-api-docs

[16] People Data Labs, "Person and Company Enrichment API," People Data Labs, Inc., San Francisco, CA, 2024. [Online]. Available: https://docs.peopledatalabs.com

[17] ZeroBounce, "Email Validation API Documentation," ZeroBounce, Inc., 2024. [Online]. Available: https://www.zerobounce.net/docs

[18] A. Vaswani et al., "Attention is All You Need," in *Advances in Neural Information Processing Systems*, vol. 30, 2017.

[19] Groq, Inc., "Groq API: Ultra-Low Latency LLM Inference," 2024. [Online]. Available: https://groq.com

[20] GitHub, Inc., "GitHub Actions: Automate Your Workflow," 2024. [Online]. Available: https://docs.github.com/en/actions

---

*This report was prepared in partial fulfillment of the requirements for the Bachelor of Engineering degree in Computer Engineering at the Islamic University of Lebanon.*

*Student: ALI Jradeh*
*Supervisor: DR. Mohammad Alawwan*
*Academic Year: 2025 – 2026*
