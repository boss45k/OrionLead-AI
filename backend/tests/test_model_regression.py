"""
Model Regression Tests
======================
Smoke-tests that load the trained XGBoost model from disk and assert
expected score ranges for hand-crafted leads.

These tests:
  1. Protect against a corrupt or miscalibrated pickle silently degrading scores.
  2. Run after every retrain as a quality gate.
  3. Require NO database or Flask app context — pure ML layer tests.

Expected behaviour (approximate — ±15 pts tolerance):
  CEO at Salesforce with budget signals   → score >= 75  (clearly Hot)
  VP Engineering at enterprise SaaS       → score >= 60  (Warm or Hot)
  Staff intern, free email, no interests  → score <= 40  (Cold)
  Ghost lead (name only)                  → score <= 30
  Borderline: Manager with some signals   → score in [35, 80]
"""

import os
import sys
import pytest

# Make backend the root for imports
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

# Pre-set env vars so no DB/Flask config is needed
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY',   'test-regression')
os.environ.setdefault('JWT_SECRET_KEY', 'test-regression')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_model():
    """Load the trained XGBoost model. Skip test suite if no model exists."""
    from app.services.ml_model import XGBLeadScoringModel
    m = XGBLeadScoringModel()
    return m if m.is_trained else None


def _score(model, lead_data: dict) -> int:
    """Extract features and return an int score 0-100."""
    from app.services.ml_model import extract_features
    features = extract_features(lead_data)
    result = model.predict_with_explanation(features)
    return result['score']


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def model():
    m = _load_model()
    if m is None:
        pytest.skip("No trained model found at models/lead_scoring_sklearn.pkl — run train first")
    return m


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestModelRegression:

    def test_hot_lead_ceo_enterprise(self, model):
        """
        CEO at a major enterprise with budget signals and corporate email.
        Should score >= 75 (Hot territory).
        """
        lead = {
            'name':      'James Whitfield',
            'email':     'james.whitfield@salesforce.com',
            'company':   'Salesforce',
            'position':  'Chief Executive Officer',
            'industry':  'SaaS',
            'country':   'United States',
            'interests': ['digital transformation', 'automation', 'artificial intelligence'],
            'phone':     '+1-415-555-0100',
            'linkedin_url': 'https://linkedin.com/in/jwhitfield',
            'notes':     'Enterprise budget approved, looking for AI platform Q1',
            'source':    'referral',
        }
        score = _score(model, lead)
        assert score >= 75, (
            f"Hot lead (CEO/enterprise) scored {score} — expected >= 75. "
            "Model may be miscalibrated or pickle is corrupt."
        )

    def test_warm_lead_vp_engineering(self, model):
        """
        VP Engineering at a mid-size SaaS company.
        Should score >= 55 (at least Warm).
        """
        lead = {
            'name':      'Sarah Okafor',
            'email':     'sarah.okafor@techcorp.io',
            'company':   'TechCorp',
            'position':  'VP of Engineering',
            'industry':  'Software',
            'country':   'United Kingdom',
            'interests': ['devops', 'cloud computing', 'api integration'],
            'phone':     '+44-20-555-0200',
            'source':    'linkedin',
        }
        score = _score(model, lead)
        assert score >= 55, (
            f"Warm lead (VP Engineering) scored {score} — expected >= 55."
        )

    def test_cold_lead_intern_free_email(self, model):
        """
        Staff-level intern with a free email and no business interests.
        Should score <= 40 (Cold).
        """
        lead = {
            'name':      'Tom',
            'email':     'tom123@gmail.com',
            'company':   '',
            'position':  'Intern',
            'industry':  '',
            'country':   '',
            'interests': ['social media', 'design'],
            'source':    'website',
        }
        score = _score(model, lead)
        assert score <= 40, (
            f"Cold lead (intern/free email) scored {score} — expected <= 40."
        )

    def test_ghost_lead_name_only(self, model):
        """
        Ghost lead — name only, no email, no company, no phone.
        Should score <= 30.
        """
        lead = {
            'name':      'Anonymous',
            'email':     '',
            'company':   '',
            'position':  '',
            'industry':  '',
            'country':   '',
            'interests': [],
            'source':    'web_form',
        }
        score = _score(model, lead)
        assert score <= 30, (
            f"Ghost lead (name only) scored {score} — expected <= 30."
        )

    def test_borderline_manager(self, model):
        """
        Mid-level manager with partial data — score should be in a reasonable
        mid-range, not clamped at 0 or 100.
        """
        lead = {
            'name':      'Carlos Rivera',
            'email':     'carlos.rivera@acmecorp.com',
            'company':   'Acme Corp',
            'position':  'Sales Manager',
            'industry':  'Retail',
            'country':   'Mexico',
            'interests': ['crm', 'marketing automation'],
            'source':    'cold_outreach',
        }
        score = _score(model, lead)
        assert 25 <= score <= 85, (
            f"Borderline lead (Sales Manager) scored {score} — "
            "expected between 25 and 85 (not clamped)."
        )

    def test_score_is_integer_in_range(self, model):
        """Sanity check: score is always an int in [0, 100]."""
        lead = {
            'name': 'Test Lead', 'email': 'test@example.com',
            'company': 'Example Inc', 'position': 'Director',
            'industry': 'Technology', 'country': 'Germany',
            'interests': ['analytics'], 'source': 'partner',
        }
        score = _score(model, lead)
        assert isinstance(score, int), f"Score should be int, got {type(score)}"
        assert 0 <= score <= 100,      f"Score {score} is outside [0, 100]"

    def test_explanation_has_top_factors(self, model):
        """predict_with_explanation() must return top_factors list."""
        from app.services.ml_model import extract_features
        lead = {
            'name': 'Diana Chen', 'email': 'diana@startup.ai',
            'company': 'StartupAI', 'position': 'CTO',
            'industry': 'AI', 'country': 'Singapore',
            'interests': ['machine learning', 'mlops'],
            'source': 'referral',
        }
        features = extract_features(lead)
        result = model.predict_with_explanation(features)
        assert 'score' in result,       "predict_with_explanation missing 'score'"
        assert 'top_factors' in result, "predict_with_explanation missing 'top_factors'"
        assert isinstance(result['top_factors'], list), "top_factors must be a list"
        assert len(result['top_factors']) > 0, "top_factors should not be empty"
