"""
Advanced Intent Engine
======================
Infers semantic buying intent from lead signals without requiring
explicit user input.  Outputs:
  - buying_stage:   "awareness" | "consideration" | "decision" | "unknown"
  - urgency:        "high" | "medium" | "low"
  - commercial_intent: 0.0-1.0

Usage
-----
    from app.intent import SemanticIntentEngine, get_intent_engine

    engine = get_intent_engine()
    result = engine.infer(lead)
"""

from app.intent.semantic_intent import SemanticIntentEngine, get_intent_engine, infer_intent

__all__ = ["SemanticIntentEngine", "get_intent_engine", "infer_intent"]
