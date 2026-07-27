"""
Feedback Learning Loop
======================
Tracks lead outcomes and uses them to improve future scoring.

Components
----------
feedback_engine    : records outcome signals (converted, rejected, unqualified)
outcome_tracker    : aggregates outcomes into per-source and per-intent statistics
score_learning     : adjusts weight profiles based on observed conversion patterns
"""

from app.learning.feedback_engine  import FeedbackEngine, get_feedback_engine, record_outcome
from app.learning.outcome_tracker  import OutcomeTracker, get_outcome_tracker
from app.learning.score_learning   import ScoreLearner, get_score_learner

__all__ = [
    "FeedbackEngine",
    "get_feedback_engine",
    "record_outcome",
    "OutcomeTracker",
    "get_outcome_tracker",
    "ScoreLearner",
    "get_score_learner",
]
