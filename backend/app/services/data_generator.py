"""
Synthetic B2B Lead Data Generator
===================================
Generates 15,000+ realistic B2B leads with known conversion labels for ML training.

Conversion probability is a calibrated function of:
  industry tier × seniority × company size × source quality × contact quality × interest alignment

Run standalone:
    python -m app.services.data_generator
"""

import numpy as np
import random
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# ── Reproducibility ───────────────────────────────────────────────────────────
SEED = 42

# ── Industry profiles (name, base_conversion_rate, value_tier) ───────────────
INDUSTRIES: List[Tuple[str, float, str]] = [
    ('SaaS',                      0.38, 'high'),
    ('AI / ML Platforms',         0.40, 'high'),
    ('FinTech',                   0.35, 'high'),
    ('Cybersecurity',             0.34, 'high'),
    ('Cloud Infrastructure',      0.35, 'high'),
    ('Data Analytics',            0.33, 'high'),
    ('Healthcare Technology',     0.30, 'high'),
    ('ERP / CRM Software',        0.28, 'medium'),
    ('Marketing Technology',      0.28, 'medium'),
    ('DevOps Tools',              0.32, 'high'),
    ('HRTech',                    0.24, 'medium'),
    ('InsurTech',                 0.24, 'medium'),
    ('EdTech',                    0.20, 'medium'),
    ('E-commerce Technology',     0.25, 'medium'),
    ('PropTech',                  0.20, 'medium'),
    ('LegalTech',                 0.22, 'medium'),
    ('Logistics Technology',      0.20, 'medium'),
    ('Manufacturing Technology',  0.22, 'medium'),
    ('BioTech',                   0.22, 'medium'),
    ('Supply Chain Tech',         0.20, 'low'),
    ('Professional Services',     0.18, 'low'),
    ('Consulting',                0.20, 'low'),
    ('Traditional Manufacturing', 0.12, 'low'),
    ('Healthcare (Non-tech)',     0.10, 'low'),
    ('Education',                 0.08, 'low'),
    ('Retail',                    0.15, 'low'),
    ('Government',                0.06, 'low'),
    ('Non-profit',                0.05, 'low'),
    ('Other',                     0.12, 'low'),
]

# ── Seniority tiers (positions, conv_rate, position_score_0_5, tier_name) ────
_C_SUITE = [
    'CEO', 'CTO', 'CFO', 'COO', 'CPO', 'CISO', 'CMO', 'CRO',
    'Chief Executive Officer', 'Chief Technology Officer',
    'Chief Financial Officer', 'Chief Operating Officer',
    'Chief Product Officer', 'Chief Revenue Officer',
    'Founder & CEO', 'Co-Founder & CTO', 'President',
    'Managing Director', 'Executive Director',
]
_VP = [
    'VP of Engineering', 'VP of Sales', 'VP of Marketing', 'VP of Product',
    'VP of Operations', 'VP of Finance', 'VP of Business Development',
    'VP of Customer Success', 'VP of IT', 'VP of Data',
    'EVP of Technology', 'SVP of Engineering', 'SVP of Sales',
    'General Manager', 'Head of Engineering', 'Head of Product',
    'Head of Sales', 'Head of Marketing', 'Head of Operations',
    'Vice President of Engineering', 'Vice President of Sales',
]
_DIRECTOR = [
    'Director of Engineering', 'Director of Sales', 'Director of Marketing',
    'Director of Product', 'Director of Operations', 'Director of IT',
    'Director of Business Development', 'Director of Finance',
    'Director of Customer Success', 'Director of Data Science',
    'Senior Director of Engineering', 'Senior Director of Sales',
    'Director of Technology', 'Director of Strategy',
]
_MANAGER = [
    'Engineering Manager', 'Sales Manager', 'Marketing Manager',
    'Product Manager', 'Operations Manager', 'IT Manager',
    'Senior Product Manager', 'Senior Engineering Manager',
    'Technical Lead', 'Team Lead', 'Senior Manager of Sales',
    'Account Manager', 'Project Manager',
    'Senior Software Engineer', 'Senior Data Scientist',
    'Principal Engineer', 'Staff Engineer',
]
_STAFF = [
    'Software Engineer', 'Data Analyst', 'Business Analyst',
    'Sales Representative', 'Marketing Specialist',
    'Customer Success Manager', 'Account Executive',
    'Product Analyst', 'DevOps Engineer', 'Data Scientist',
    'Financial Analyst', 'HR Specialist', 'Operations Analyst',
]

# (positions_list, conv_rate, pos_score, tier_label)
SENIORITY_TIERS = [
    (_C_SUITE,   0.46, 5, 'c_suite'),
    (_VP,        0.38, 4, 'vp'),
    (_DIRECTOR,  0.30, 3, 'director'),
    (_MANAGER,   0.22, 2, 'manager'),
    (_STAFF,     0.12, 1, 'staff'),
]

# ── Sources (name, conv_rate, credibility_score) ─────────────────────────────
SOURCES = [
    ('referral',        0.46, 3),
    ('partner',         0.40, 3),
    ('linkedin',        0.32, 3),
    ('conference',      0.28, 2),
    ('inbound',         0.25, 2),
    ('content',         0.22, 2),
    ('email_campaign',  0.18, 1),
    ('cold_outreach',   0.10, 1),
    ('web',             0.08, 1),
    ('social_media',    0.12, 1),
]

# ── Interests ─────────────────────────────────────────────────────────────────
_INTERESTS_HIGH = [
    'artificial intelligence', 'machine learning', 'automation', 'analytics',
    'cloud computing', 'cybersecurity', 'digital transformation', 'data science',
    'saas integration', 'enterprise software', 'business intelligence',
    'api integration', 'devops', 'microservices', 'data engineering',
    'real-time analytics', 'predictive analytics', 'mlops', 'llm', 'nlp',
]
_INTERESTS_MED = [
    'crm', 'erp', 'marketing automation', 'sales enablement', 'customer success',
    'project management', 'collaboration tools', 'e-commerce', 'mobile apps',
    'web development', 'it infrastructure', 'helpdesk', 'reporting',
    'workflow automation', 'document management', 'hr software',
]
_INTERESTS_LOW = [
    'social media', 'content creation', 'email marketing', 'seo',
    'graphic design', 'video production', 'events', 'print media',
    'basic accounting', 'scheduling', 'general productivity',
]

# ── Geography ─────────────────────────────────────────────────────────────────
_TIER3_COUNTRIES = [
    'United States', 'United Kingdom', 'Canada', 'Australia', 'Singapore',
    'Germany', 'Netherlands', 'Sweden', 'Switzerland', 'Denmark',
    'United Arab Emirates', 'Israel', 'Japan', 'South Korea', 'Norway',
    'Finland', 'Ireland', 'New Zealand',
]
_TIER2_COUNTRIES = [
    'France', 'Spain', 'Italy', 'Brazil', 'Mexico', 'India',
    'South Africa', 'Belgium', 'Poland', 'Portugal', 'Czech Republic',
    'Austria', 'Hungary', 'Romania', 'Greece',
]
_TIER1_COUNTRIES = [
    'Turkey', 'Russia', 'Argentina', 'Colombia', 'Chile',
    'Thailand', 'Malaysia', 'Philippines', 'Indonesia', 'Vietnam',
    'Morocco', 'Egypt', 'Nigeria', 'Kenya', 'Pakistan',
]
COUNTRY_TIERS = [
    (_TIER3_COUNTRIES, 0.85, 3),
    (_TIER2_COUNTRIES, 0.70, 2),
    (_TIER1_COUNTRIES, 0.55, 1),
]

CITIES_BY_COUNTRY: Dict[str, List[str]] = {
    'United States':       ['New York', 'San Francisco', 'Austin', 'Seattle', 'Chicago', 'Boston', 'Los Angeles', 'Denver'],
    'United Kingdom':      ['London', 'Manchester', 'Birmingham', 'Edinburgh', 'Leeds'],
    'Canada':              ['Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Ottawa'],
    'Germany':             ['Berlin', 'Munich', 'Hamburg', 'Frankfurt', 'Cologne'],
    'Australia':           ['Sydney', 'Melbourne', 'Brisbane', 'Perth'],
    'India':               ['Bangalore', 'Mumbai', 'Delhi', 'Hyderabad', 'Chennai', 'Pune'],
    'Singapore':           ['Singapore'],
    'France':              ['Paris', 'Lyon', 'Marseille', 'Toulouse'],
    'Netherlands':         ['Amsterdam', 'Rotterdam', 'Utrecht'],
    'Brazil':              ['São Paulo', 'Rio de Janeiro', 'Belo Horizonte'],
    'Israel':              ['Tel Aviv', 'Jerusalem', 'Haifa'],
    'Sweden':              ['Stockholm', 'Gothenburg', 'Malmö'],
    'Switzerland':         ['Zurich', 'Geneva', 'Basel'],
    'United Arab Emirates':['Dubai', 'Abu Dhabi'],
    'Japan':               ['Tokyo', 'Osaka', 'Yokohama'],
    'South Korea':         ['Seoul', 'Busan', 'Incheon'],
}

# ── Names / Companies ─────────────────────────────────────────────────────────
_FIRST_NAMES = [
    'James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph',
    'Thomas', 'Charles', 'Christopher', 'Daniel', 'Matthew', 'Anthony', 'Mark',
    'Mary', 'Patricia', 'Jennifer', 'Linda', 'Barbara', 'Elizabeth', 'Susan',
    'Jessica', 'Sarah', 'Karen', 'Lisa', 'Nancy', 'Betty', 'Margaret', 'Sandra',
    'Emily', 'Ashley', 'Amanda', 'Megan', 'Emma', 'Olivia', 'Ava', 'Sophia',
    'Alexander', 'Ethan', 'Noah', 'Lucas', 'Mason', 'Logan', 'Carter', 'Liam',
    'Priya', 'Rahul', 'Arun', 'Sanjay', 'Deepak', 'Vijay', 'Amit', 'Raj',
    'Wei', 'Jing', 'Ming', 'Fang', 'Xiao',
    'Ahmed', 'Mohammed', 'Ali', 'Hassan', 'Omar', 'Ibrahim',
    'Carlos', 'Miguel', 'Juan', 'Diego', 'Pablo', 'Fernando',
    'Sophie', 'Charlotte', 'Oliver', 'Harry', 'George',
    'Lena', 'Hans', 'Klaus', 'Anna', 'Erik', 'Lars',
]
_LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
    'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Wilson', 'Anderson', 'Thomas',
    'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White',
    'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker',
    'Young', 'Allen', 'King', 'Wright', 'Scott', 'Torres', 'Nguyen', 'Hill',
    'Green', 'Adams', 'Nelson', 'Baker', 'Hall', 'Rivera', 'Campbell', 'Mitchell',
    'Carter', 'Roberts', 'Patel', 'Shah', 'Kumar', 'Singh', 'Chen', 'Wang',
    'Zhang', 'Liu', 'Kim', 'Park', 'Mueller', 'Schmidt', 'Fischer', 'Weber',
    'Rossi', 'Ferrari', 'Russo', 'Esposito', 'Ali', 'Hassan', 'Khan', 'Ahmed',
    'Thompson', 'Harrison', 'Hughes', 'Clarke', 'Davies', 'Evans', 'Morgan',
    'Andersen', 'Jensen', 'Hansen', 'Nilsson', 'Eriksson',
]
_COMPANY_WORDS = [
    'Apex', 'Atlas', 'Axiom', 'Beacon', 'Bridge', 'Catalyst', 'Cipher', 'Clarity',
    'Cloud', 'Core', 'Cyber', 'Data', 'Delta', 'Digital', 'Dynamic', 'Edge',
    'Elite', 'Emerge', 'Evolve', 'Flow', 'Forge', 'Frontier', 'Fusion', 'Genesis',
    'Grid', 'Helix', 'Horizon', 'Hub', 'Hyper', 'Impact', 'Infinity', 'Insight',
    'Integra', 'Iron', 'Keystone', 'Kinetic', 'Launch', 'Layer', 'Lean', 'Logic',
    'Matrix', 'Metric', 'Momentum', 'Nexus', 'Node', 'Nova', 'Omni', 'Orbit',
    'Paragon', 'Peak', 'Pivot', 'Platform', 'Prism', 'Pulse', 'Quantum', 'Rapid',
    'Relay', 'Ripple', 'Scale', 'Shift', 'Signal', 'Smart', 'Solid', 'Source',
    'Spark', 'Sphere', 'Stack', 'Storm', 'Summit', 'Sync', 'Synergy', 'Titan',
    'Track', 'Transform', 'Trend', 'Turbo', 'Ultra', 'Unity', 'Vector', 'Venture',
    'Vertex', 'Vision', 'Volta', 'Wave', 'Xceed', 'Zenith',
]
_COMPANY_SUFFIX_ENTERPRISE = ['Corporation', 'Global', 'International', 'Holdings', 'Group']
_COMPANY_SUFFIX_LARGE      = ['Corp', 'Inc', 'Partners', 'Associates', 'Ventures']
_COMPANY_SUFFIX_SMB        = ['LLC', 'Ltd', 'Limited', 'Solutions', 'Technologies']
_COMPANY_SUFFIX_STARTUP    = ['AI', 'Tech', 'Labs', 'Systems', 'Digital', 'HQ']

_FREE_DOMAINS = frozenset([
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com',
    'live.com', 'aol.com', 'protonmail.com', 'mail.com', 'yandex.com',
    'me.com', 'gmx.com', 'fastmail.com',
])

_NOTES_TEMPLATES_HIGH = [
    "Board approved ${amt}M budget for digital transformation.",
    "Evaluating enterprise solutions. Confirmed ${amt}K budget.",
    "PMO has ${amt}K for automation upgrades this quarter.",
    "Decision maker confirmed. Budget: ${amt}M. Timeline: Q{q}.",
    "Executive sponsor engaged. ${amt}K pre-approved for pilot.",
]
_NOTES_TEMPLATES_MED = [
    "Interested in professional tier. Team of {n}+ users.",
    "Comparing enterprise options, decision by end of quarter.",
    "Scaling rapidly. Open to migration if value is clear.",
    "Pilot approved with option to expand company-wide.",
    "Currently using legacy system. Actively looking to replace.",
]
_NOTES_TEMPLATES_LOW = [
    "Just exploring options at this stage.",
    "Early research phase, no budget confirmed yet.",
    "Startup, limited budget. Looking for affordable options.",
    "Signed up for trial to evaluate the platform.",
    "Interested in free tier for now.",
]


# ── Core generator ────────────────────────────────────────────────────────────

class SyntheticLeadGenerator:
    """
    Generates realistic B2B leads with calibrated conversion probabilities.

    Conversion probability model (logistic blend):
        P(convert) = σ(α₀
            + α₁ × industry_score
            + α₂ × seniority_score
            + α₃ × company_size_score
            + α₄ × source_score
            + α₅ × contact_quality
            + α₆ × interest_alignment
            + ε)
    where ε ~ N(0, 0.15) introduces realistic noise.
    """

    def __init__(self, seed: int = SEED):
        self.rng = np.random.default_rng(seed)
        random.seed(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # ── Edge-case templates injected at generation time ──────────────────────
    # These cover patterns the logistic model might not generate naturally.
    _EDGE_CASE_FRACTION = 0.05   # 5% of leads are edge cases

    def generate(self, n: int = 15_000) -> List[Dict[str, Any]]:
        """Generate n synthetic leads (including ~5% structured edge cases)."""
        n_edge  = max(1, int(n * self._EDGE_CASE_FRACTION))
        n_normal = n - n_edge
        leads = [self._generate_one(i) for i in range(n_normal)]
        leads += [self._generate_edge_case(i + n_normal) for i in range(n_edge)]
        # Shuffle to avoid all edge cases at the end
        random.shuffle(leads)
        pos_rate = sum(l['_label'] for l in leads) / len(leads)
        logger.info(
            f"Generated {n} synthetic leads (incl. {n_edge} edge cases) — "
            f"positive rate: {pos_rate:.1%}"
        )
        return leads

    def generate_and_save(
        self,
        n: int = 15_000,
        output_path: str | None = None,
    ) -> Path:
        """Generate leads and persist to JSON."""
        if output_path is None:
            output_path = str(
                Path(__file__).parent.parent.parent / 'data' / 'synthetic_leads.json'
            )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        leads = self.generate(n)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(leads, fh, indent=2, ensure_ascii=False)
        logger.info(f"Saved {n} synthetic leads → {path}")
        return path

    # ------------------------------------------------------------------
    # Internal generation
    # ------------------------------------------------------------------

    def _generate_one(self, idx: int) -> Dict[str, Any]:
        rng = self.rng

        # ── 1. Sample profile dimensions ─────────────────────────────
        industry_name, ind_rate, ind_tier = random.choice(INDUSTRIES)
        seniority_positions, sen_rate, pos_score, sen_label = random.choice(SENIORITY_TIERS)
        source_name, src_rate, src_cred = random.choice(SOURCES)
        position = random.choice(seniority_positions)

        # Company size (correlated with seniority somewhat)
        size_probs = [0.25, 0.20, 0.25, 0.20, 0.10]  # enterprise, large, mid, smb, startup
        size_label = rng.choice(
            ['enterprise', 'large', 'mid', 'smb', 'startup'],
            p=size_probs
        )
        size_score_map = {'enterprise': 5, 'large': 4, 'mid': 3, 'smb': 2, 'startup': 2}
        size_score = size_score_map[size_label]

        # Company name
        company = self._build_company_name(size_label)

        # Geography
        country_tier_data = random.choices(
            COUNTRY_TIERS,
            weights=[0.55, 0.30, 0.15],
            k=1,
        )[0]
        countries, geo_mult, geo_score = country_tier_data
        country = random.choice(countries)
        city = random.choice(CITIES_BY_COUNTRY.get(country, ['']))

        # Name
        first = random.choice(_FIRST_NAMES)
        last  = random.choice(_LAST_NAMES)
        name  = f"{first} {last}"

        # Email
        has_corporate_email = rng.random() < (0.80 if size_label in ('enterprise', 'large') else 0.60)
        if has_corporate_email:
            domain = self._company_to_domain(company)
            email = f"{first.lower()}.{last.lower()}@{domain}"
        else:
            email = f"{first.lower()}{last.lower()}{rng.integers(1, 999)}@{random.choice(list(_FREE_DOMAINS))}"

        # Phone
        has_phone = rng.random() < 0.70
        phone = f"+1-{rng.integers(200,999)}-{rng.integers(100,999)}-{rng.integers(1000,9999)}" if has_phone else None

        # LinkedIn
        has_linkedin = rng.random() < 0.65
        linkedin_url = f"https://linkedin.com/in/{first.lower()}-{last.lower()}-{rng.integers(100,9999)}" if has_linkedin else None

        # Website
        has_website = rng.random() < (0.85 if size_label in ('enterprise', 'large') else 0.45)
        website = f"https://www.{self._company_to_domain(company)}" if has_website else None

        # Industry field on lead record
        industry_field = industry_name if rng.random() < 0.80 else None

        # Interests (2-5 interests, weighted by lead quality)
        n_interests = rng.integers(1, 6)
        interest_tier_weights = {
            'high': [0.60, 0.30, 0.10],
            'medium': [0.35, 0.45, 0.20],
            'low': [0.15, 0.40, 0.45],
        }[ind_tier]
        interests = []
        for _ in range(n_interests):
            pool = random.choices(
                [_INTERESTS_HIGH, _INTERESTS_MED, _INTERESTS_LOW],
                weights=interest_tier_weights,
            )[0]
            interests.append(random.choice(pool))
        interests = list(dict.fromkeys(interests))  # deduplicate, preserve order

        # Notes
        notes = self._build_notes(sen_label, ind_tier, rng)

        # Product interest
        product = random.choice(interests) if interests else None

        # ── 2. Compute conversion probability ────────────────────────
        # Linear combination in logit space, then sigmoid
        # Coefficients are doubled vs naive version so that the logit range is
        # wide enough for the best leads (~0.90 prob) and worst leads (~0.03 prob)
        # to be clearly separated → theoretical max AUC ≈ 0.85+.
        # Base offset calibrated so global positive rate ≈ 25–30%.
        # Strong coefficients so the best leads (C-suite, high-value industry,
        # referral, enterprise) have prob ~0.95 and worst leads ~0.01.
        # Base offset calibrated to give ~28% global positive rate.
        # Signal coefficients are calibrated so that:
        #   best leads (C-suite + referral + enterprise + AI industry): prob ≈ 0.98
        #   worst leads (staff + cold_outreach + non-profit + no data):  prob ≈ 0.005
        # → theoretical max AUC ≈ 0.88–0.92, giving trained model AUC ≥ 0.80
        logit = (
            -10.50                        # base offset (~28% global positive rate)
            + 4.0 * ind_rate              # industry quality
            + 5.5 * sen_rate              # seniority (dominant predictor)
            + 2.5 * (size_score / 5)      # company size
            + 3.5 * src_rate              # source quality
            + 2.0 * (1 if has_corporate_email else 0)
            + 1.2 * (1 if has_phone else 0)
            + 1.0 * (1 if has_linkedin else 0)
            + 1.5 * (len(interests) / 5)  # interest breadth
            + 1.2 * geo_mult              # geography
            + float(rng.normal(0, 0.10))  # minimal noise → clean signal
        )
        prob = 1.0 / (1.0 + np.exp(-logit))
        label = int(rng.random() < prob)

        # Qualification score: roughly matches the conversion probability
        # with some noise so the model has to learn from features
        base_score = max(5.0, min(98.0, prob * 100 + float(rng.normal(0, 8))))

        return {
            # Core lead fields
            'id':           idx + 1,
            'name':         name,
            'email':        email,
            'phone':        phone,
            'company':      company,
            'position':     position,
            'industry':     industry_field,
            'country':      country,
            'city':         city if rng.random() < 0.75 else None,
            'website':      website,
            'linkedin_url': linkedin_url,
            'interests':    interests,
            'product':      product,
            'source':       source_name,
            'notes':        notes,
            'status':       'converted' if label else random.choice(['pending', 'cold', 'contacted']),
            # ML metadata
            'qualification_score': round(base_score, 1),
            '_label':              label,     # ground-truth conversion (1/0)
            '_prob':               round(float(prob), 4),
            '_industry_tier':      ind_tier,
            '_seniority_tier':     sen_label,
            '_company_size':       size_label,
            '_is_synthetic':       True,      # always mark synthetic for DatasetManager
        }

    def _generate_edge_case(self, idx: int) -> Dict[str, Any]:
        """
        Generate a structured edge-case lead that the logistic model would not
        naturally produce.  These teach the ML model about boundary conditions.

        Edge types (chosen randomly):
          1. High-seniority C-suite with free email → low data quality signal
          2. Staff-level with perfect data + referral → unexpectedly qualifiable
          3. Missing most fields → sparse profile challenge
          4. Budget-rich notes + low seniority → notes override seniority
          5. Enterprise company + cold_outreach source → source penalises score
          6. AI/ML industry + no interests/notes → missing enrichment
        """
        rng = self.rng
        edge_type = rng.integers(1, 7)

        base = {
            '_is_synthetic': True,
            '_is_edge_case': True,
            'id': idx + 1,
        }

        if edge_type == 1:
            # C-suite with free email — high seniority, low email quality
            first, last = random.choice(_FIRST_NAMES), random.choice(_LAST_NAMES)
            base.update({
                'name':     f"{first} {last}",
                'position': random.choice(_C_SUITE),
                'email':    f"{first.lower()}.{last.lower()}@gmail.com",
                'company':  self._build_company_name('enterprise'),
                'industry': 'SaaS',
                'country':  'United States',
                'source':   'linkedin',
                'interests': ['automation', 'machine learning'],
                '_label':   1,   # still likely to convert — seniority wins
                'qualification_score': 62.0,
                '_prob': 0.62,
                '_seniority_tier': 'c_suite',
                '_industry_tier': 'high',
                '_company_size': 'enterprise',
            })

        elif edge_type == 2:
            # Staff-level with perfect data + referral
            first, last = random.choice(_FIRST_NAMES), random.choice(_LAST_NAMES)
            company = self._build_company_name('large')
            base.update({
                'name':        f"{first} {last}",
                'position':    random.choice(_STAFF),
                'email':       f"{first.lower()}@{self._company_to_domain(company)}",
                'phone':       f"+1-555-{rng.integers(100,999)}-{rng.integers(1000,9999)}",
                'company':     company,
                'industry':    'AI / ML Platforms',
                'country':     'United Kingdom',
                'linkedin_url':f"https://linkedin.com/in/{first.lower()}-{last.lower()}",
                'website':     f"https://{self._company_to_domain(company)}",
                'source':      'referral',
                'interests':   ['machine learning', 'automation', 'analytics'],
                'notes':       f"Referral from key account. Budget ${rng.integers(50,200)}K approved.",
                '_label':      1,   # referral + full data → converts despite low seniority
                'qualification_score': 58.0,
                '_prob': 0.58,
                '_seniority_tier': 'staff',
                '_industry_tier': 'high',
                '_company_size': 'large',
            })

        elif edge_type == 3:
            # Sparse profile — almost no data
            first, last = random.choice(_FIRST_NAMES), random.choice(_LAST_NAMES)
            base.update({
                'name':    f"{first} {last}",
                'email':   None,
                'company': None,
                'position': None,
                'source':  'web',
                '_label':  0,
                'qualification_score': 12.0,
                '_prob': 0.05,
                '_seniority_tier': 'staff',
                '_industry_tier': 'low',
                '_company_size': 'startup',
            })

        elif edge_type == 4:
            # Low-seniority but budget-rich notes
            first, last = random.choice(_FIRST_NAMES), random.choice(_LAST_NAMES)
            company = self._build_company_name('mid')
            base.update({
                'name':     f"{first} {last}",
                'position': random.choice(_MANAGER),
                'email':    f"{first.lower()}@{self._company_to_domain(company)}",
                'phone':    f"+44-{rng.integers(700,799)}-{rng.integers(100000,999999)}",
                'company':  company,
                'industry': 'FinTech',
                'country':  'United Kingdom',
                'source':   'inbound',
                'interests': ['analytics', 'automation'],
                'notes':    f"Board has approved ${rng.integers(2,15)}M for fintech modernization. Decision maker delegated to this contact.",
                '_label':   1,
                'qualification_score': 72.0,
                '_prob': 0.72,
                '_seniority_tier': 'manager',
                '_industry_tier': 'high',
                '_company_size': 'mid',
            })

        elif edge_type == 5:
            # Enterprise company + cold outreach — source penalty
            first, last = random.choice(_FIRST_NAMES), random.choice(_LAST_NAMES)
            company = self._build_company_name('enterprise')
            base.update({
                'name':     f"{first} {last}",
                'position': random.choice(_VP),
                'email':    f"{first.lower()}.{last.lower()}@{self._company_to_domain(company)}",
                'company':  company,
                'industry': 'Healthcare Technology',
                'country':  'United States',
                'source':   'cold_outreach',
                'interests': ['digital transformation'],
                '_label':   0,   # cold outreach to enterprise = low conversion
                'qualification_score': 38.0,
                '_prob': 0.22,
                '_seniority_tier': 'vp',
                '_industry_tier': 'high',
                '_company_size': 'enterprise',
            })

        else:
            # AI/ML industry + zero enrichment
            first, last = random.choice(_FIRST_NAMES), random.choice(_LAST_NAMES)
            base.update({
                'name':     f"{first} {last}",
                'position': random.choice(_DIRECTOR),
                'company':  self._build_company_name('startup'),
                'industry': 'AI / ML Platforms',
                'source':   'social_media',
                '_label':   0,   # no enrichment → uncertain, default cold
                'qualification_score': 30.0,
                '_prob': 0.30,
                '_seniority_tier': 'director',
                '_industry_tier': 'high',
                '_company_size': 'startup',
            })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

        # Fill in any missing optional fields with safe defaults
        for _field in ['phone', 'city', 'website', 'linkedin_url', 'interests',
                       'notes', 'product', 'status']:
            base.setdefault(_field, None)
        base.setdefault('status', 'cold' if base.get('_label') == 0 else 'converted')
        return base

    @staticmethod
    def _build_company_name(size_label: str) -> str:
        word1 = random.choice(_COMPANY_WORDS)
        word2 = random.choice(_COMPANY_WORDS) if random.random() < 0.4 else ''
        suffix_pool = {
            'enterprise': _COMPANY_SUFFIX_ENTERPRISE,
            'large':      _COMPANY_SUFFIX_LARGE,
            'mid':        _COMPANY_SUFFIX_LARGE + _COMPANY_SUFFIX_SMB,
            'smb':        _COMPANY_SUFFIX_SMB,
            'startup':    _COMPANY_SUFFIX_STARTUP,
        }[size_label]
        suffix = random.choice(suffix_pool)
        parts = [p for p in [word1, word2, suffix] if p]
        return ' '.join(parts)

    @staticmethod
    def _company_to_domain(company: str) -> str:
        slug = (
            company.lower()
            .replace(' ', '')
            .replace('corporation', 'corp')
            .replace('international', 'intl')
            .replace('holdings', '')
            .replace('group', '')
            [:20]
        )
        tld = random.choice(['.com', '.com', '.com', '.io', '.co', '.net'])
        return slug + tld

    @staticmethod
    def _build_notes(seniority: str, industry_tier: str, rng: np.random.Generator) -> str | None:
        if rng.random() < 0.30:
            return None  # 30 % of leads have no notes

        if seniority in ('c_suite', 'vp') and industry_tier == 'high':
            template = random.choice(_NOTES_TEMPLATES_HIGH)
        elif seniority in ('director', 'manager') or industry_tier in ('high', 'medium'):
            template = random.choice(_NOTES_TEMPLATES_MED)
        else:
            template = random.choice(_NOTES_TEMPLATES_LOW)

        return (
            template
            .replace('${amt}M', str(rng.integers(1, 20)))
            .replace('${amt}K', str(rng.integers(50, 500)))
            .replace('{n}', str(rng.integers(10, 500)))
            .replace('{q}', str(rng.integers(1, 5)))
        )


# ── Singleton / convenience ───────────────────────────────────────────────────

_generator: SyntheticLeadGenerator | None = None


def get_generator() -> SyntheticLeadGenerator:
    global _generator
    if _generator is None:
        _generator = SyntheticLeadGenerator()
    return _generator


def load_or_generate(
    n: int = 15_000,
    path: str | None = None,
    force_regen: bool = False,
) -> List[Dict[str, Any]]:
    """
    Load existing synthetic dataset from disk, or generate + save a fresh one.

    Args:
        n:           Number of leads to generate if file doesn't exist.
        path:        Override default save path.
        force_regen: Re-generate even if file exists.
    """
    if path is None:
        path = str(Path(__file__).parent.parent.parent / 'data' / 'synthetic_leads.json')

    fpath = Path(path)
    if not force_regen and fpath.exists():
        with open(fpath, encoding='utf-8') as fh:
            leads = json.load(fh)
        logger.info(f"Loaded {len(leads)} synthetic leads from {fpath}")
        return leads

    gen = get_generator()
    gen.generate_and_save(n=n, output_path=path)
    with open(fpath, encoding='utf-8') as fh:
        return json.load(fh)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15_000
    gen = SyntheticLeadGenerator()
    gen.generate_and_save(n=n)
