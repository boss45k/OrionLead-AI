"""
s07_ui.py — Chapter 7: System Results and User Interface
Target: 6-8 pages
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import theme as T
from docx.shared import Cm


def build(doc):
    T.chapter_title(doc, 7, "System Results and User Interface")

    T.body(doc,
        "This chapter presents the OrionLead AI system through its user interfaces, "
        "describing the key screens of both the web dashboard and the mobile "
        "application. Each interface section describes the layout, interactive "
        "elements, visual design decisions, and the user experience flow. Screenshots "
        "with captions illustrate each screen in its operational context. The "
        "interfaces are presented in the order a typical user would encounter them: "
        "authentication, lead management, analytics, AI collection, and mobile access.")

    # ── 7.1 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "7.1", "Web Dashboard — Authentication Screens")

    T.subsection_h(doc, "7.1.1", "Login Screen")
    T.body(doc,
        "The login screen is the entry point to the OrionLead AI web dashboard. It "
        "presents a centered card on a gradient background that adapts between dark "
        "navy and light gray depending on the active theme. The card contains the "
        "OrionLead AI logo and brand name at the top, followed by an Ant Design Form "
        "with Email and Password fields, a 'Remember me' checkbox, and a primary "
        "'Sign In' button. A secondary link below the button navigates to the "
        "registration page.")

    T.body(doc,
        "The login form implements real-time field validation using Ant Design Form's "
        "built-in validation rules: the email field requires a valid email format and "
        "shows an inline error message if the format is incorrect before the form is "
        "submitted. On submit, the Sign In button transitions to a loading spinner "
        "state while the authentication request is in flight, preventing double "
        "submission. On a failed login attempt, a red Alert component appears above "
        "the form with the error message from the API. On success, the JWT token is "
        "stored in localStorage and the user is redirected to the leads list.")

    T.caption(doc, "Figure 7.1 — Web Dashboard: Login Screen")

    T.subsection_h(doc, "7.1.2", "Registration Screen")
    T.body(doc,
        "The registration screen uses the same centered card layout as the login "
        "screen, with a four-field form: Full Name, Email Address, Password (with "
        "a strength indicator bar), and Company Name. A fifth optional field for "
        "the user's role is hidden from self-registration and only accessible to "
        "administrators through the user management panel. Password strength is "
        "evaluated client-side using a simple entropy calculation and displayed "
        "as a four-segment colored bar (red → orange → yellow → green) below the "
        "password field, providing immediate visual feedback without submitting "
        "the form.")

    # ── 7.2 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "7.2", "Web Dashboard — Lead Management")

    T.subsection_h(doc, "7.2.1", "Leads List View")
    T.body(doc,
        "The leads list is the primary working screen of the web dashboard. It "
        "presents all leads accessible to the current user in a paginated Ant Design "
        "Table with server-side data fetching. The table displays eight columns: "
        "Lead Name (with a circular avatar showing the name initial), Company and "
        "Position (two lines of text), Qualification Score (a colored circular badge), "
        "Tier (a colored Tag component: HOT in green, WARM in amber, COLD in blue, "
        "UNQUALIFIED in slate), Status (an Ant Design Tag with status-appropriate "
        "color), Source (a secondary Tag), and Actions (View, Edit, Delete buttons).")

    T.body(doc,
        "Above the table, a collapsible filter panel provides seven filter controls: "
        "Score Range (a two-handle Ant Design Slider from 0 to 100), Status "
        "(multi-select), Source (multi-select), Industry (text input with "
        "autocomplete), Country (Select with search), Date Range (RangePicker for "
        "created_at), and a Search bar for full-text search. The filter panel state "
        "is preserved in Redux, ensuring filters persist when the user navigates away "
        "and returns. A results counter above the table shows the total number of "
        "leads matching the active filters, and an 'Export CSV' button downloads the "
        "filtered result set.")

    T.caption(doc, "Figure 7.2 — Web Dashboard: Leads List View")

    T.subsection_h(doc, "7.2.2", "Lead Detail View")
    T.body(doc,
        "Clicking a lead row opens the lead detail view as a full-page layout divided "
        "into three panels. The left panel shows the lead's avatar (a large circle "
        "with the name initial and score-based background color), qualification score "
        "as a large number with its tier label, and a Status selector that allows "
        "direct status updates. The center panel contains four expandable sections: "
        "Contact Information (email with verification badge, phone, LinkedIn URL, "
        "website), Company Information (company name, position, industry, country, "
        "city), AI Qualification Details (score breakdown by cascade layer, tier "
        "assignment, buying intent), and Notes (a rich-text area for free-form notes).")

    T.body(doc,
        "The right panel contains two components. The QuickLabelBar presents four "
        "colored buttons — Converted (green), Replied (blue), No Reply (gray), "
        "Not a Fit (red) — for one-click outcome recording. Below the QuickLabelBar, "
        "a chronological Activity Timeline shows all events related to this lead: "
        "creation, field updates, status changes, re-qualifications, and outcome "
        "labels. Each timeline entry shows the event type icon, description text, "
        "the responsible user's name, and the timestamp. A 'Re-qualify with AI' "
        "button above the timeline triggers a fresh cascade evaluation.")

    T.caption(doc, "Figure 7.3 — Web Dashboard: Lead Detail View and QuickLabelBar")

    # ── 7.3 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "7.3", "Web Dashboard — Analytics")

    T.body(doc,
        "The analytics dashboard provides management-level visibility into the lead "
        "pipeline's performance. The page opens with a row of four KPI summary cards: "
        "Total Leads (showing the count within the current user's role scope, with "
        "a trend arrow and percentage change versus the previous period), Average "
        "Qualification Score (the mean score across all leads in scope, shown as a "
        "large number with a color-coded indicator), Hot Leads Count (leads with "
        "score >= 80, with a trend indicator), and Conversion Rate (percentage of "
        "labeled leads with outcome 'converted', calculated from LeadOutcome records).")

    T.body(doc,
        "Below the KPI row, four Chart.js charts are arranged in a 2x2 grid. The "
        "Collection Trend Line chart displays daily lead collection counts over the "
        "selected date range, with a smooth bezier curve and a gradient fill below "
        "the line that fades from the primary blue at the top to transparent at the "
        "bottom. The Score Distribution Pie chart shows the proportion of Hot, Warm, "
        "Cold, and Unqualified leads with a legend listing exact counts and "
        "percentages. The Leads by Source Bar chart uses horizontal bars for "
        "readability, comparing lead volume across Hunter.io, Apollo.io, People "
        "Data Labs, Serper.dev, Manual entry, and other sources. The Status "
        "Breakdown Doughnut chart shows the current pipeline status distribution "
        "with a center text label displaying the total lead count. A global date "
        "range picker at the top of the page controls the time window for all "
        "four charts simultaneously.")

    T.caption(doc, "Figure 7.4 — Web Dashboard: Analytics Overview Dashboard")

    # ── 7.4 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "7.4", "Web Dashboard — AI Collection Panel")

    T.body(doc,
        "The AI Collection page is the primary lead intake interface. It is divided "
        "into three zones. The Query Zone at the top contains a large TextArea with "
        "the placeholder 'Describe the leads you want to collect — e.g., SaaS CTOs "
        "in the UAE with 50–200 employees' and a row of CheckboxGroup controls for "
        "selecting which data sources to include. Only sources that have been enabled "
        "and configured by an administrator are shown as selectable options; disabled "
        "sources appear grayed out with a tooltip explaining they need configuration.")

    T.body(doc,
        "The Configuration Zone below the query area shows advanced options in a "
        "collapsed Ant Design Collapse panel: maximum candidates per source (default "
        "20), minimum qualification score threshold for saving leads (default 30), "
        "and a toggle to enable or disable the Company-First pipeline evaluation. "
        "A prominent 'Start Collection' button triggers the collection job.")

    T.body(doc,
        "The Progress Zone appears after collection starts, replacing the "
        "configuration area. It shows a real-time progress display with source-by-"
        "source status indicators (spinner while collecting, green checkmark on "
        "success, red X on API error), running counters for candidates found, "
        "rejected by anti-junk, and qualified per tier (Hot / Warm / Cold / "
        "Unqualified). A timeline log at the bottom of the progress zone shows "
        "text events as they occur. On completion, a results summary card replaces "
        "the progress display, showing the final collection statistics and a "
        "'View New Leads' button that navigates to the leads list filtered to "
        "leads collected in the last hour.")

    T.caption(doc, "Figure 7.5 — Web Dashboard: AI Collection Panel")

    # ── 7.5 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "7.5", "Mobile Application — Leads Screen")

    T.subsection_h(doc, "7.5.1", "Leads List")
    T.body(doc,
        "The mobile leads screen displays a scrollable FlatList of LeadCard "
        "components, each occupying the full screen width with a 16-pixel horizontal "
        "margin. At the top of the screen, a search bar with a filter icon provides "
        "quick access to the filter sheet (a bottom-up modal with status, score "
        "range, and source filters). A pull-to-refresh gesture triggers a fresh "
        "API fetch; the RefreshControl component shows a native platform spinner "
        "during the refresh.")

    T.body(doc,
        "Each LeadCard renders with the complete visual design described in Section "
        "5.5.2: a 4-pixel left border in the score's tier color (green, amber, blue, "
        "or slate), a circular avatar with the name initial, the lead's name and "
        "company/position information, a tier pill badge, an industry tag, a circular "
        "score badge, a StatusBadge, email and phone chips at the bottom, and a High "
        "Intent flame chip if applicable. The cards use shadow elevation on both iOS "
        "and Android for a card-like depth appearance. Tapping a card navigates to "
        "the LeadDetailScreen via the stack navigator push animation.")

    T.caption(doc, "Figure 7.6 — Mobile App: Leads Screen (Light Mode)")

    T.subsection_h(doc, "7.5.2", "Lead Detail Screen")
    T.body(doc,
        "The mobile lead detail screen is a vertically scrollable view. At the top, "
        "a large circular ScoreGauge component displays the qualification score as a "
        "colored arc gauge (green for Hot, amber for Warm, blue for Cold, slate for "
        "Unqualified) with the numeric score at the center and the tier label below "
        "it. Below the gauge, the contact information section lists email (with "
        "verification checkmark), phone, LinkedIn, and website in rows with "
        "appropriate Ionicons prefix icons. Tapping email or phone triggers the "
        "native dialer or mail app through React Native's Linking API.")

    T.body(doc,
        "The company section below the contact row shows company name, position, "
        "industry, country, and city. A buying intent indicator row shows the "
        "detected intent level and confidence score if available. The status "
        "selector allows the user to update the lead's pipeline status directly "
        "from the detail screen. At the very bottom of the screen, the QuickLabelBar "
        "is rendered in a fixed-position container above the bottom safe area inset, "
        "always visible regardless of scroll position.")

    T.caption(doc, "Figure 7.7 — Mobile App: Lead Detail Screen and QuickLabelBar")

    # ── 7.6 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "7.6", "Mobile Application — Analytics Screen")

    T.body(doc,
        "The mobile analytics screen opens with a horizontally scrollable row of "
        "summary metric cards, each displaying a KPI label, a large metric value, "
        "and a small trend indicator. The cards cover: Total Leads (in scope), "
        "Average Score, Hot Leads, Collected This Week, and Conversion Rate. The "
        "horizontal scroll allows additional metrics to be added without crowding "
        "the fixed-width screen.")

    T.body(doc,
        "Below the metric cards, a react-native-chart-kit LineChart displays daily "
        "collection trends over the last 14 days, adapted for mobile viewports with "
        "a compact x-axis label format (D/M) and a scrollable chart container for "
        "longer date ranges. Below the line chart, a PieChart component renders the "
        "score tier distribution with a legend positioned below the chart rather "
        "than beside it, preserving readability on narrow screens. At the bottom, a "
        "Top Sources section lists collection sources by volume with percentage "
        "contribution bars rendered using React Native's View width percentage styling.")

    T.caption(doc, "Figure 7.8 — Mobile App: Analytics Screen")

    # ── 7.7 ──────────────────────────────────────────────────────────────────
    T.section_h(doc, "7.7", "Mobile Application — Dark Mode")

    T.body(doc,
        "The mobile application provides a complete dark mode implementation through "
        "the ThemeContext provider. Dark mode uses a dark slate color palette "
        "throughout: the page background is #0f172a (very dark navy), card "
        "backgrounds are #1e293b (dark slate), input fields use #1e293b with a "
        "#334155 border, and muted text uses #94a3b8 (slate-400). The dark palette "
        "is carefully chosen to maintain WCAG 2.1 AA contrast ratios (minimum 4.5:1 "
        "for body text, 3:1 for large text) across all text-background combinations.")

    T.body(doc,
        "Score tier colors (green for Hot, amber for Warm, blue for Cold, slate for "
        "Unqualified) are preserved at their same hue in dark mode but are rendered "
        "with slightly higher saturation to maintain visual prominence against the "
        "dark background. Shadows are removed in dark mode (since dark surfaces do "
        "not naturally produce visible shadows) and replaced with subtle border "
        "highlights using semi-transparent white (#ffffff14) to define card edges.")

    T.body(doc,
        "The theme preference is stored in expo-secure-store and read on application "
        "startup before the first render, eliminating the flash-of-wrong-theme "
        "antipattern. The ThemeContext also reads the device's system color scheme "
        "preference through React Native's Appearance API on first launch, defaulting "
        "to the system preference if no stored preference exists. Users can override "
        "the system preference at any time through the Profile screen's appearance "
        "settings toggle, which writes the preference to secure storage.")

    T.caption(doc, "Figure 7.9 — Mobile App: Dark Mode (Lead List and Detail Screens)")

    # ── 7.8 Summary table ────────────────────────────────────────────────────
    T.section_h(doc, "7.8", "Interface Summary")

    T.body(doc,
        "Table 7.1 provides a consolidated summary of all screens implemented across "
        "the web dashboard and mobile application, confirming that all functional "
        "requirements related to user interface (FR-01 through FR-25) are addressed "
        "by at least one screen or component.")

    headers = ["Screen / Component", "Platform", "Key Features", "FR Coverage"]
    rows = [
        ["Login Screen",          "Web + Mobile", "JWT auth, validation, error display",                          "FR-01, FR-02"],
        ["Registration Screen",   "Web + Mobile", "User creation, password strength, role assignment",            "FR-01"],
        ["Leads List",            "Web + Mobile", "Paginated list, filters, search, score visualization, export", "FR-03, FR-10, FR-11, FR-18, FR-19"],
        ["Lead Detail",           "Web + Mobile", "Full profile, status update, activity timeline, re-qualify",   "FR-13, FR-14, FR-15"],
        ["QuickLabelBar",         "Web + Mobile", "One-tap outcome labeling (4 outcomes), offline queue",         "FR-16, FR-17"],
        ["AI Collection Panel",   "Web",          "NL query, source selection, real-time progress, results",      "FR-04, FR-05, FR-06, FR-07"],
        ["Analytics Dashboard",   "Web + Mobile", "KPI cards, 4 chart types, date range filter, trend lines",     "FR-20"],
        ["Users Management",      "Web (Admin)",  "User list, role assignment, API key generation",               "FR-24"],
        ["Data Sources Config",   "Web (Admin)",  "Source enable/disable, API key entry, last-used timestamp",    "FR-24"],
        ["Profile Screen",        "Mobile",       "User details, theme toggle, logout, notification settings",    "FR-21"],
        ["Offline Banner",        "Mobile",       "Persistent indicator when device is offline",                  "FR-22"],
        ["Push Notifications",    "Mobile",       "FCM delivery, new lead alerts, status change alerts",          "FR-23"],
    ]
    T.styled_table(doc, headers, rows,
                   col_widths=[Cm(3.5), Cm(2.5), Cm(6.0), Cm(2.3)])
    T.caption(doc, "Table 7.1 — Interface Summary and Functional Requirement Coverage")
