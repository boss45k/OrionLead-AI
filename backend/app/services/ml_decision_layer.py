"""
ML Decision Layer — Intelligent Routing + Quality Evaluation + Dataset Logging

Replaces the fixed-weight parallel execution with data-driven routing decisions.

Architecture:
  ┌─────────────────────────────────────────────┐
  │             MLDecisionLayer                 │
  │                                             │
  │  1. route()        → pick providers         │
  │  2. score()        → dynamic weights        │
  │  3. evaluate()     → response quality gate  │
  │  4. log()          → JSONL training dataset │
  │  5. feedback()     → label past predictions │
  └─────────────────────────────────────────────┘

Routing Tiers (decided at call time):
  TIER_1_ML_ONLY    completeness >= 0.80 AND ml_conf >= 0.75  → Agent + ML only
  TIER_2_ML_GROQ    completeness >= 0.50 AND ml_conf >= 0.55  → Agent + ML + Groq
  TIER_3_FULL       completeness >= 0.30 OR  ml_conf <  0.55  → Agent + ML + Gemini
  TIER_4_LLM_HEAVY  completeness <  0.30                      → LLM primary, agent backup

Dataset file: backend/data/training_dataset.jsonl
Provider stats: backend/data/provider_stats.json
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.services.ml_model import N_FEATURES

logger = logging.getLogger(__name__)


def _audit_log(
    decision_type: str,
    result: Any,
    lead_id: Optional[int] = None,
    user_id: Optional[int] = None,
    extra: Optional[dict] = None,
) -> None:
    """
    Emit a structured audit log entry consumed by any log aggregator.

    Fields written to `extra` (queryable in Datadog / CloudWatch / Loki):
        event          str  — always 'ml_decision'
        decision_type  str  — 'spam_check' | 'duplicate_check' | 'quality_tier'
                               | 'feedback_submit' | 'spam_blocked'
        lead_id        int  — the lead being processed (None for unit calls)
        user_id        int  — the user who triggered the action (None if automated)
        result         any  — the key outcome value (tier name, bool, score)
        ts             str  — UTC ISO timestamp
    """
    payload: Dict[str, Any] = {
        'event':         'ml_decision',
        'decision_type': decision_type,
        'lead_id':       lead_id,
        'user_id':       user_id,
        'result':        result,
        'ts':            datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    logger.info(f"[{decision_type}] result={result} lead={lead_id}", extra=payload)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).parent.parent.parent / 'data'
_DATA_DIR.mkdir(parents=True, exist_ok=True)

DATASET_PATH      = _DATA_DIR / 'training_dataset.jsonl'
PROVIDER_STATS    = _DATA_DIR / 'provider_stats.json'
QUALITY_LOG_PATH  = _DATA_DIR / 'quality_log.jsonl'

# ---------------------------------------------------------------------------
# Routing tier constants
# ---------------------------------------------------------------------------
TIER_1_ML_ONLY   = 'ml_only'
TIER_2_ML_GROQ   = 'ml_groq'
TIER_3_FULL      = 'full_stack'
TIER_4_LLM_HEAVY = 'llm_heavy'

# Minimum ML confidence to trust the model exclusively.
# Raised to 0.82: model trained on ~71 samples isn't reliable enough to skip LLM at 75%.
ML_ONLY_CONF_THRESHOLD  = 0.82
ML_ASSIST_CONF_THRESHOLD = 0.55

# Data completeness thresholds (0–1)
COMPLETENESS_HIGH  = 0.80
COMPLETENESS_MED   = 0.50
COMPLETENESS_LOW   = 0.30

# ── Shared classification thresholds (single source of truth) ───────────────
# Import these wherever score→category conversion is needed instead of
# hard-coding magic numbers.
SCORE_HOT       = 80   # score >= 80  → Hot
SCORE_WARM      = 60   # score >= 60  → Warm
SCORE_COLD      = 0    # score <  60  → Cold

# ── Circuit-breaker constants ────────────────────────────────────────────────
_CB_FAILURE_THRESHOLD = 5    # consecutive quality failures before disable
_CB_COOLDOWN_SECS     = 300  # 5-minute cooldown

# ── Dataset size cap ─────────────────────────────────────────────────────────
_DATASET_MAX_ROWS    = 10_000
_DATASET_TRIM_EVERY  = 100   # check row count every N appends

# Free email providers for feature extraction
_FREE_EMAIL_PROVIDERS = frozenset([
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'icloud.com', 'live.com', 'aol.com', 'protonmail.com',
    'mail.com', 'yandex.com', 'me.com', 'gmx.com',
])

_KEY_FIELDS = [
    'name', 'email', 'phone', 'company', 'position',
    'linkedin_url', 'website', 'industry', 'country', 'interests',
]


# ============================================================================
# 1. PROVIDER ACCURACY TRACKER
# ============================================================================

class ProviderTracker:
    """
    Tracks per-provider prediction accuracy using a sliding window.

    When a lead is marked 'converted', the ground-truth label is 1 (positive).
    When marked 'unqualified' or 'cold', label is 0.

    For each provider we track the rolling Mean Absolute Error (MAE)
    against ground truth over the last 200 labeled samples.
    This feeds dynamic weight computation.
    """

    _WINDOW = 200

    def __init__(self):
        self._lock = threading.Lock()
        # provider → deque of (predicted_score 0-100, ground_truth 0-100)
        self._history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self._WINDOW))
        # Circuit-breaker state (not persisted — resets on restart)
        self._consecutive_failures: Dict[str, int] = defaultdict(int)
        self._disabled_until: Dict[str, float] = {}   # provider → monotonic timestamp
        self._load()

    # ------------------------------------------------------------------
    def record(self, provider: str, predicted: float, ground_truth: float):
        """Record one prediction + its eventual ground-truth label."""
        with self._lock:
            self._history[provider].append((predicted, ground_truth))
        self._save()

    def mae(self, provider: str) -> Optional[float]:
        """Mean absolute error for a provider (None if < 5 samples)."""
        with self._lock:
            h = list(self._history.get(provider, []))
        if len(h) < 5:
            return None
        errors = [abs(p - g) for p, g in h]
        return float(np.mean(errors))

    def sample_count(self, provider: str) -> int:
        with self._lock:
            return len(self._history.get(provider, []))

    def provider_weights(self, available_providers: List[str]) -> Dict[str, float]:
        """
        Compute normalized weights inversely proportional to MAE.
        Providers with no history get base weight 1.0.
        Providers with MAE get weight = 1 / (1 + MAE/50) — higher error → lower weight.
        """
        raw: Dict[str, float] = {}
        for p in available_providers:
            m = self.mae(p)
            raw[p] = 1.0 / (1.0 + (m / 50.0)) if m is not None else 1.0

        total = sum(raw.values()) or 1.0
        return {p: v / total for p, v in raw.items()}

    # ------------------------------------------------------------------
    # Circuit-breaker methods
    # ------------------------------------------------------------------

    def record_quality_failure(self, provider: str) -> bool:
        """
        Increment consecutive-failure counter.
        Returns True if provider was just tripped (first time it crosses threshold).
        """
        with self._lock:
            self._consecutive_failures[provider] += 1
            count = self._consecutive_failures[provider]
            if count >= _CB_FAILURE_THRESHOLD:
                deadline = time.monotonic() + _CB_COOLDOWN_SECS
                self._disabled_until[provider] = deadline
                logger.warning(
                    f"[CircuitBreaker] {provider} disabled for {_CB_COOLDOWN_SECS}s "
                    f"after {count} consecutive quality failures"
                )
                return True
        return False

    def record_quality_success(self, provider: str) -> None:
        """Reset failure counter and re-enable provider on a successful response."""
        with self._lock:
            self._consecutive_failures[provider] = 0
            self._disabled_until.pop(provider, None)

    def is_disabled(self, provider: str) -> bool:
        """True if the provider is in circuit-breaker cooldown."""
        deadline = self._disabled_until.get(provider)
        if deadline is None:
            return False
        if time.monotonic() >= deadline:
            # Cooldown expired — re-enable
            with self._lock:
                self._disabled_until.pop(provider, None)
                self._consecutive_failures[provider] = 0
            logger.info(f"[CircuitBreaker] {provider} re-enabled after cooldown")
            return False
        return True

    # ------------------------------------------------------------------
    def _path(self) -> Path:
        return PROVIDER_STATS

    def _save(self):
        try:
            data = {p: list(h) for p, h in self._history.items()}
            path = self._path()
            tmp = path.with_suffix('.tmp')
            with open(tmp, 'w') as f:
                json.dump(data, f)
            os.replace(tmp, path)
        except Exception as e:
            logger.warning(f"ProviderTracker save failed: {e}")

    def _load(self):
        try:
            if self._path().exists():
                with open(self._path()) as f:
                    data = json.load(f)
                for p, entries in data.items():
                    self._history[p] = deque(entries, maxlen=self._WINDOW)
        except Exception as e:
            logger.warning(f"ProviderTracker load failed: {e}")


# ============================================================================
# 2. FEEDBACK ACCURACY TRACKER
# ============================================================================

_FEEDBACK_ACCURACY_PATH = _DATA_DIR / 'feedback_accuracy.json'

# Map outcome → ground-truth score (0–100) for MAE computation
_OUTCOME_GT_SCORE = {
    'converted':    100.0,
    'contacted':     75.0,
    'hot':           90.0,
    'warm':          60.0,
    'cold':          20.0,
    'rejected':      10.0,
    'unqualified':   15.0,
}

# Map outcome → hard binary for precision/recall
_OUTCOME_BINARY = {
    'converted':   1, 'contacted': 1, 'hot': 1,
    'cold':        0, 'rejected':  0, 'unqualified': 0,
    'warm':        None,  # soft — excluded from binary metrics
}


class FeedbackAccuracyTracker:
    """
    Tracks how well each scoring component (ML, rules, LLM) predicts real outcomes,
    broken down by label_source and lead source channel.

    Stores two sliding windows per dimension:
      - (predicted_score, ground_truth_score) → MAE
      - (predicted_binary, ground_truth_binary) → accuracy / precision / recall

    Persisted to feedback_accuracy.json.  Thread-safe via a single RLock.
    """

    _WINDOW = 500

    def __init__(self):
        self._lock = threading.RLock()
        # Keyed by (dimension, key) e.g. ('label_source', 'user_feedback')
        # or ('lead_source', 'linkedin') or ('provider', 'ml')
        self._score_history:  Dict[str, deque] = defaultdict(lambda: deque(maxlen=self._WINDOW))
        self._binary_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self._WINDOW))
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def record(
        self,
        outcome: str,
        *,
        ml_score:    Optional[float] = None,
        rule_score:  Optional[float] = None,
        llm_score:   Optional[float] = None,
        label_source: str = 'user_feedback',
        lead_source:  str = 'unknown',
    ) -> None:
        """
        Record one labeled outcome and the scores that were predicted for it.

        Parameters
        ----------
        outcome:      The real outcome (converted / contacted / cold / etc.)
        ml_score:     The ML model's score at prediction time (0–100)
        rule_score:   The rule-engine score at prediction time (0–100)
        llm_score:    The LLM score at prediction time (0–100)
        label_source: Source of the outcome label (business_outcome / user_feedback / ai_prediction)
        lead_source:  The original lead acquisition channel (linkedin / web / etc.)
        """
        gt_score  = _OUTCOME_GT_SCORE.get(outcome)
        gt_binary = _OUTCOME_BINARY.get(outcome)

        if gt_score is None:
            return  # unknown outcome — skip

        with self._lock:
            # Record per provider
            for provider, score in [('ml', ml_score), ('rule', rule_score), ('llm', llm_score)]:
                if score is not None:
                    key = f'provider:{provider}'
                    self._score_history[key].append((score, gt_score))
                    if gt_binary is not None:
                        predicted_binary = 1 if score >= 60 else 0
                        self._binary_history[key].append((predicted_binary, gt_binary))

            # Record per label_source
            src_key = f'label_source:{label_source}'
            # Use the best available score for label_source tracking
            best_score = ml_score or rule_score or llm_score
            if best_score is not None:
                self._score_history[src_key].append((best_score, gt_score))
                if gt_binary is not None:
                    self._binary_history[src_key].append((1 if best_score >= 60 else 0, gt_binary))

            # Record per lead acquisition channel
            ch_key = f'lead_source:{lead_source.lower()}'
            if best_score is not None:
                self._score_history[ch_key].append((best_score, gt_score))
                if gt_binary is not None:
                    self._binary_history[ch_key].append((1 if best_score >= 60 else 0, gt_binary))

        self._save()

    def accuracy_report(self) -> Dict[str, Any]:
        """
        Return a structured report for the /api/v1/ai/feedback-accuracy endpoint.

        Shape:
          {
            "by_provider":     {"ml": {...}, "rule": {...}, "llm": {...}},
            "by_label_source": {"user_feedback": {...}, ...},
            "by_lead_source":  {"linkedin": {...}, ...},
            "total_feedback":  int,
          }
        """
        with self._lock:
            report: Dict[str, Any] = {
                'by_provider':     {},
                'by_label_source': {},
                'by_lead_source':  {},
                'total_feedback':  0,
            }
            total = 0
            for key in list(self._score_history.keys()):
                dim, name = key.split(':', 1)
                stats = self._compute_stats(key)
                total += stats.get('n', 0)
                bucket = {
                    'provider':        'by_provider',
                    'label_source':    'by_label_source',
                    'lead_source':     'by_lead_source',
                }.get(dim, 'other')
                report[bucket][name] = stats
            report['total_feedback'] = total
        return report

    def model_vs_reality(self, lead_id: int) -> Optional[Dict[str, Any]]:
        """
        Return the prediction-vs-outcome comparison for a specific lead.
        Reads directly from the JSONL dataset file for the per-lead record.
        """
        try:
            if not DATASET_PATH.exists():
                return None
            with open(DATASET_PATH) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get('lead_id') == lead_id and rec.get('label') is not None:
                            ml  = rec.get('ml_score')
                            rule = rec.get('rule_score')
                            llm  = rec.get('llm_score')
                            gt   = _OUTCOME_GT_SCORE.get(rec.get('label_outcome', ''), rec['label'] * 100)
                            return {
                                'lead_id':       lead_id,
                                'ml_predicted':  ml,
                                'rule_predicted':rule,
                                'llm_predicted': llm,
                                'ground_truth':  gt,
                                'outcome':       rec.get('label_outcome'),
                                'ml_error':      round(abs(ml - gt), 1) if ml is not None else None,
                                'rule_error':    round(abs(rule - gt), 1) if rule is not None else None,
                                'llm_error':     round(abs(llm - gt), 1) if llm is not None else None,
                            }
                    except (json.JSONDecodeError, KeyError):
                        pass
        except Exception as exc:
            logger.warning(f"FeedbackAccuracyTracker.model_vs_reality: {exc}")
        return None

    # ── Internals ─────────────────────────────────────────────────────────────

    def _compute_stats(self, key: str) -> Dict[str, Any]:
        scores  = list(self._score_history.get(key, []))
        binaries = list(self._binary_history.get(key, []))
        n = len(scores)
        if n == 0:
            return {'n': 0, 'mae': None, 'accuracy': None, 'precision': None, 'recall': None}

        mae = float(np.mean([abs(p - g) for p, g in scores]))

        # Binary metrics
        acc = prec = rec = None
        if binaries:
            nb  = len(binaries)
            tp  = sum(1 for p, g in binaries if p == 1 and g == 1)
            tn  = sum(1 for p, g in binaries if p == 0 and g == 0)
            fp  = sum(1 for p, g in binaries if p == 1 and g == 0)
            fn  = sum(1 for p, g in binaries if p == 0 and g == 1)
            acc  = round((tp + tn) / nb, 3) if nb else None
            prec = round(tp / (tp + fp), 3) if (tp + fp) > 0 else None
            rec  = round(tp / (tp + fn), 3) if (tp + fn) > 0 else None

        return {
            'n':         n,
            'mae':       round(mae, 2),
            'accuracy':  acc,
            'precision': prec,
            'recall':    rec,
        }

    def _save(self):
        try:
            data = {
                'score_history':  {k: list(v) for k, v in self._score_history.items()},
                'binary_history': {k: list(v) for k, v in self._binary_history.items()},
            }
            tmp = _FEEDBACK_ACCURACY_PATH.with_suffix('.tmp')
            with open(tmp, 'w') as fh:
                json.dump(data, fh)
            tmp.replace(_FEEDBACK_ACCURACY_PATH)
        except Exception as exc:
            logger.warning(f"FeedbackAccuracyTracker._save: {exc}")

    def _load(self):
        try:
            if _FEEDBACK_ACCURACY_PATH.exists():
                with open(_FEEDBACK_ACCURACY_PATH) as fh:
                    data = json.load(fh)
                for k, v in data.get('score_history', {}).items():
                    self._score_history[k] = deque(v, maxlen=self._WINDOW)
                for k, v in data.get('binary_history', {}).items():
                    self._binary_history[k] = deque(v, maxlen=self._WINDOW)
        except Exception as exc:
            logger.warning(f"FeedbackAccuracyTracker._load: {exc}")


# ============================================================================
# 3. RESPONSE QUALITY EVALUATOR
# ============================================================================

class ResponseQualityEvaluator:
    """
    Gate for LLM responses before they enter the scoring pipeline.

    Checks:
      - Valid JSON structure with required keys
      - Score in [0, 100]
      - Non-empty reasoning (at least 20 chars)
      - Category / score coherence (e.g. score=90 but category='Cold' → penalty)
      - Deviation from rule-based agent score (flags outliers, does NOT reject)

    Returns a quality dict: {quality_score: 0-1, issues: [...], usable: bool}
    """

    REQUIRED_KEYS = {'score', 'category'}

    # Category → expected score band
    _CATEGORY_BANDS = {
        'hot':  (70, 100),
        'warm': (40, 85),
        'cold': (0, 65),
    }

    def evaluate(
        self,
        response: Dict[str, Any],
        agent_score: Optional[float] = None,
        provider: str = 'unknown',
    ) -> Dict[str, Any]:
        issues: List[str] = []
        deductions = 0.0

        # 1. Required keys present
        missing = self.REQUIRED_KEYS - set(response.keys())
        if missing:
            issues.append(f"missing_keys:{missing}")
            deductions += 0.5

        # 2. Score in valid range
        score = response.get('score')
        if score is None:
            issues.append('score_missing')
            deductions += 0.3
        elif not isinstance(score, (int, float)) or not (0 <= score <= 100):
            issues.append(f'score_out_of_range:{score}')
            deductions += 0.3

        # 3. Reasoning non-trivial
        reasoning = response.get('reason') or response.get('reasoning') or ''
        if len(str(reasoning)) < 20:
            issues.append('reasoning_too_short')
            deductions += 0.15

        # 4. Category / score coherence
        category = str(response.get('category', '')).lower()
        if score is not None and category in self._CATEGORY_BANDS:
            lo, hi = self._CATEGORY_BANDS[category]
            if not (lo <= score <= hi):
                issues.append(f'category_score_incoherent:{category}@{score}')
                deductions += 0.2

        # 5. Outlier vs rule-based agent (soft flag only)
        if agent_score is not None and score is not None:
            deviation = abs(float(score) - float(agent_score))
            if deviation > 40:
                issues.append(f'outlier_vs_agent:delta={deviation:.0f}')
                deductions += 0.1   # soft — LLM may just know more

        quality_score = max(0.0, 1.0 - deductions)
        usable = quality_score >= 0.4 and 'score_missing' not in issues

        result = {
            'quality_score': round(quality_score, 3),
            'usable': usable,
            'issues': issues,
            'provider': provider,
            'ts': datetime.now(timezone.utc).isoformat(),
        }

        if issues:
            logger.debug(f"Quality eval [{provider}]: {issues} → score={quality_score:.2f}")

        # Log to quality file for auditing
        self._log(result, response)
        return result

    def _log(self, result: Dict, response: Dict):
        try:
            entry = {**result, 'raw_score': response.get('score'),
                     'raw_category': response.get('category')}
            with open(QUALITY_LOG_PATH, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception:
            pass


# ============================================================================
# 3. DATASET LOGGER
# ============================================================================

class DatasetLogger:
    """
    Appends prediction records to a JSONL file for continuous training.

    Record schema:
      lead_id          int
      ts               ISO timestamp
      features         list[float]  — N_FEATURES values from extract_features()
      data_completeness float
      route_tier       str
      provider_scores  {provider: score}
      final_score      int
      ml_confidence    float | null
      label            null (filled in by label_lead())

    label_lead(lead_id, outcome):
      Scans the file and fills label=1 (converted) or label=0 (cold/unqualified)
      for all records matching lead_id.
      Uses atomic write (tempfile + os.replace) to prevent corruption.
    """

    _lock = threading.Lock()
    _write_count = 0  # class-level write counter for trim scheduling

    def log(
        self,
        lead_id: Optional[int],
        features: np.ndarray,
        data_completeness: float,
        route_tier: str,
        provider_scores: Dict[str, float],
        final_score: int,
        ml_confidence: Optional[float],
        prompt_version: Optional[str] = None,
    ) -> None:
        # Extract individual provider scores for fast analysis without parsing provider_scores dict
        _llm_score = (
            provider_scores.get('gemini') or provider_scores.get('groq') or None
        )
        record = {
            'lead_id':          lead_id,
            'ts':               datetime.now(timezone.utc).isoformat(),
            'features':         features[0].tolist() if features is not None else [],
            'data_completeness': round(data_completeness, 3),
            'route_tier':       route_tier,
            'provider_scores':  {k: round(v, 2) for k, v in provider_scores.items()},
            'ml_score':         round(provider_scores['ml'], 2) if 'ml' in provider_scores else None,
            'llm_score':        round(_llm_score, 2) if _llm_score is not None else None,
            'agent_score':      round(provider_scores['agent'], 2) if 'agent' in provider_scores else None,
            'final_score':      final_score,
            'ml_confidence':    round(ml_confidence, 4) if ml_confidence is not None else None,
            'prompt_version':   prompt_version,
            'label':            None,
        }
        with self._lock:
            try:
                with open(DATASET_PATH, 'a') as f:
                    f.write(json.dumps(record) + '\n')
                DatasetLogger._write_count += 1
                if DatasetLogger._write_count % _DATASET_TRIM_EVERY == 0:
                    self._trim_to_max()
            except Exception as e:
                logger.warning(f"DatasetLogger.log failed: {e}")

    def _trim_to_max(self) -> None:
        """
        Keep the dataset under _DATASET_MAX_ROWS.
        Labeled rows are preserved preferentially; oldest unlabeled rows are dropped.
        Must be called under self._lock.
        """
        try:
            if not DATASET_PATH.exists():
                return
            raw_lines = [l for l in DATASET_PATH.read_text().splitlines() if l.strip()]
            if len(raw_lines) <= _DATASET_MAX_ROWS:
                return

            records = []
            for line in raw_lines:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

            labeled   = [r for r in records if r.get('label') is not None]
            unlabeled = [r for r in records if r.get('label') is None]

            # Always keep all labeled; fill remaining quota with newest unlabeled
            keep = labeled[-_DATASET_MAX_ROWS:]
            remaining = _DATASET_MAX_ROWS - len(keep)
            if remaining > 0:
                keep.extend(unlabeled[-remaining:])

            keep.sort(key=lambda r: r.get('ts', ''))

            self._atomic_write(DATASET_PATH, '\n'.join(json.dumps(r) for r in keep) + '\n')
            logger.info(f"[DatasetLogger] trimmed to {len(keep)} rows (was {len(records)})")
        except Exception as e:
            logger.warning(f"DatasetLogger._trim_to_max failed: {e}")

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Write content atomically using tempfile + os.replace."""
        tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                f.write(content)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def label_lead(self, lead_id: int, outcome: str) -> int:
        """
        Set label for all records with this lead_id.
          outcome='converted'                → label = 1
          outcome in ('cold','unqualified')  → label = 0
          outcome='contacted'                → label = 0.7 (soft positive)
        Returns count of records updated.
        """
        label_map = {
            'converted':   1.0,
            'contacted':   0.7,
            'cold':        0.0,
            'unqualified': 0.0,
            'pending':     None,
        }
        label = label_map.get(outcome)
        if label is None:
            return 0

        updated = 0
        with self._lock:
            try:
                if not DATASET_PATH.exists():
                    return 0
                lines = DATASET_PATH.read_text().splitlines()
                new_lines = []
                for line in lines:
                    try:
                        rec = json.loads(line)
                        if rec.get('lead_id') == lead_id and rec.get('label') is None:
                            rec['label'] = label
                            rec['labeled_at'] = datetime.now(timezone.utc).isoformat()
                            rec['label_outcome'] = outcome
                            updated += 1
                        new_lines.append(json.dumps(rec))
                    except json.JSONDecodeError:
                        new_lines.append(line)
                # Atomic write — prevents corruption if process is killed mid-write
                self._atomic_write(DATASET_PATH, '\n'.join(new_lines) + '\n')
            except Exception as e:
                logger.warning(f"DatasetLogger.label_lead failed: {e}")
        return updated

    def load_labeled(self) -> List[Dict[str, Any]]:
        """Return all records that have a numeric label (for retraining)."""
        records = []
        try:
            if not DATASET_PATH.exists():
                return []
            with open(DATASET_PATH) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if isinstance(rec.get('label'), (int, float)) and rec['label'] is not None:
                            records.append(rec)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            logger.warning(f"DatasetLogger.load_labeled failed: {e}")
        return records

    def dataset_stats(self) -> Dict[str, Any]:
        total = labeled = positives = 0
        try:
            if DATASET_PATH.exists():
                for line in DATASET_PATH.read_text().splitlines():
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                        total += 1
                        if rec.get('label') is not None:
                            labeled += 1
                            if rec['label'] >= 0.5:
                                positives += 1
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
        return {
            'total': total,
            'labeled': labeled,
            'positives': positives,
            'negatives': labeled - positives,
            'unlabeled': total - labeled,
        }


# ============================================================================
# 4. DATA COMPLETENESS (standalone helper)
# ============================================================================

def compute_completeness(lead_data: Dict[str, Any]) -> float:
    """Return fraction of key fields that are filled (0.0–1.0)."""
    filled = sum(
        1 for f in _KEY_FIELDS
        if lead_data.get(f) not in (None, '', [], {})
    )
    return filled / len(_KEY_FIELDS)


# ============================================================================
# 5. SPAM DETECTOR
# ============================================================================

class SpamDetector:
    """
    Detect spam, bot, and disposable-email submissions before scoring.

    Checks:
      1. Disposable / temporary email domain
      2. Role-based email prefix (admin@, info@, noreply@, ...)
      3. Gibberish name (almost no vowels, too short)
      4. Ghost lead — no contact information at all
      5. Repeated/keyboard-walk characters in email prefix

    Returns {is_spam, spam_score 0-1, issues, score_penalty 0-40}
    """

    _DISPOSABLE: frozenset = frozenset([
        'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'throwaway.email',
        'yopmail.com', '10minutemail.com', 'trashmail.com', 'maildrop.cc',
        'sharklasers.com', 'grr.la', 'guerrillamail.info', 'guerrillamail.biz',
        'guerrillamail.de', 'guerrillamail.net', 'guerrillamail.org',
        'spam4.me', 'spamgourmet.com', 'fakeinbox.com', 'mailnull.com',
        'dispostable.com', 'mailexpire.com', 'throwam.com', 'filzmail.com',
        'noref.in', 'pookmail.com', 'discardmail.com', 'spamherelots.com',
        'sogetthis.com', 'spikio.com', 'getnada.com', 'mailsac.com',
        'tempinbox.com', 'jetable.fr.nf', 'trashmail.at', 'trashmail.io',
        'trashmail.me', 'trashmail.xyz', 'trashmail.net', 'trashmail.org',
        'getairmail.com', 'spamfree24.org', 'mytrashmail.com',
    ])

    _ROLE_PREFIXES: frozenset = frozenset([
        'admin', 'info', 'contact', 'support', 'noreply', 'no-reply',
        'hello', 'sales', 'marketing', 'hr', 'careers', 'jobs', 'office',
        'mail', 'email', 'webmaster', 'postmaster', 'feedback', 'help',
        'team', 'service', 'bot', 'do-not-reply', 'donotreply', 'billing',
        'accounting', 'legal', 'security', 'privacy', 'abuse', 'spam',
    ])

    _VOWELS: frozenset = frozenset('aeiouy')
    _RE_NON_ALPHA = re.compile(r'[^a-zA-Z]')

    def check(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        # spam_override=True skips role-based and ghost-lead checks so that
        # legitimate role emails (e.g. admin@enterprise.com) are not blocked.
        spam_override = bool(lead_data.get('spam_override', False))
        issues: List[str] = []
        score = 0.0

        email = str(lead_data.get('email', '')).lower().strip()
        name  = str(lead_data.get('name',  '')).strip()

        # 1. Disposable domain
        if '@' in email:
            domain = email.split('@', 1)[1]
            if domain in self._DISPOSABLE:
                issues.append('disposable_email_domain')
                score += 0.6

        # 2. Role-based email prefix (skipped when spam_override is set)
        if not spam_override and '@' in email:
            prefix = email.split('@', 1)[0].split('+')[0]  # strip sub-address
            if prefix in self._ROLE_PREFIXES:
                issues.append('role_based_email')
                score += 0.3

        # 3. Gibberish name — no vowels, too short, or missing
        if name:
            letters = self._RE_NON_ALPHA.sub('', name)
            if len(letters) >= 4:
                vowel_ratio = sum(1 for c in letters.lower() if c in self._VOWELS) / len(letters)
                if vowel_ratio < 0.10:
                    issues.append('gibberish_name_no_vowels')
                    score += 0.4
            if len(name.split()) == 1 and len(name) < 3:
                issues.append('name_too_short')
                score += 0.2
        else:
            issues.append('name_missing')
            score += 0.1

        # 4. Ghost lead — absolutely no contact info (skipped when spam_override is set)
        if not spam_override:
            has_any = any(lead_data.get(f) for f in ['email', 'phone', 'company', 'linkedin_url'])
            if not has_any:
                issues.append('no_contact_info')
                score += 0.5

        # 5. Repeated / keyboard-walk chars in email prefix
        if '@' in email:
            pfx = email.split('@', 1)[0]
            if len(pfx) >= 5 and len(set(pfx)) <= 2:
                issues.append('repeated_chars_in_email')
                score += 0.4

        score = min(score, 1.0)
        is_spam = score >= 0.5

        if is_spam:
            _audit_log(
                decision_type='spam_check',
                result=True,
                extra={'spam_score': round(score, 2), 'issues': issues},
            )

        return {
            'is_spam':       is_spam,
            'spam_score':    round(score, 2),
            'issues':        issues,
            'score_penalty': min(int(round(score * 40)), 40),
        }


# ============================================================================
# 6. DUPLICATE DETECTOR
# ============================================================================

class DuplicateDetector:
    """
    DB-backed exact-match duplicate detection.

    Replaces the previous JSON file (data/seen_contacts.json) with the
    SeenContact SQLAlchemy model — safe under concurrent Gunicorn workers,
    indexed for O(1) lookups, and race-condition-safe via unique constraint
    + IntegrityError handling.

    Public interface is identical to the old JSON-backed version:
        result = detector.check(lead_data)   # {'is_exact_duplicate': bool, ...}
        detector.register(lead_data)          # insert if new, silently skip if exists
    """

    _RE_NON_DIGIT = re.compile(r'\D')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Query SeenContact for this email / phone.
        Each field is checked independently via its own indexed column.
        Falls back to 'not duplicate' on any DB error so scoring continues.
        """
        email = self._norm_email(lead_data.get('email'))
        phone = self._norm_phone(lead_data.get('phone'))

        email_dup = False
        phone_dup = False

        try:
            from flask import has_app_context
            if not has_app_context():
                return {'is_exact_duplicate': False, 'duplicate_fields': []}
            from app.models.models import SeenContact, db
            if email:
                email_dup = (
                    db.session.query(SeenContact)
                    .filter(SeenContact.normalized_email == email)
                    .first() is not None
                )
            if phone:
                phone_dup = (
                    db.session.query(SeenContact)
                    .filter(SeenContact.normalized_phone == phone)
                    .first() is not None
                )
        except Exception as exc:
            logger.warning(f"DuplicateDetector.check DB error (non-fatal): {exc}")

        dup_fields: List[str] = []
        if email_dup:
            dup_fields.append('email')
        if phone_dup:
            dup_fields.append('phone')

        is_dup = email_dup or phone_dup
        if is_dup:
            _audit_log(
                decision_type='duplicate_check',
                result=True,
                extra={'duplicate_fields': dup_fields},
            )

        return {
            'is_exact_duplicate': is_dup,
            'duplicate_fields':   dup_fields,
        }

    def register(self, lead_data: Dict[str, Any]) -> None:
        """
        Insert normalised email / phone into SeenContact.
        Silently skips if the exact (email, phone) pair already exists
        (IntegrityError on the composite unique constraint).
        Falls back gracefully on any other DB error.
        """
        email = self._norm_email(lead_data.get('email'))
        phone = self._norm_phone(lead_data.get('phone'))

        if not email and not phone:
            return

        try:
            from flask import has_app_context
            if not has_app_context():
                return
            from app.models.models import SeenContact, db
            from sqlalchemy.exc import IntegrityError

            row = SeenContact(
                normalized_email=email or None,
                normalized_phone=phone or None,
            )
            db.session.add(row)
            db.session.commit()
            logger.debug(
                f"DuplicateDetector: registered email={email!r} phone={phone!r}"
            )
        except Exception as exc:
            # IntegrityError → exact pair already exists; any other error → log and move on
            from sqlalchemy.exc import IntegrityError
            if isinstance(exc, IntegrityError):
                logger.debug(
                    f"DuplicateDetector: contact already registered "
                    f"(email={email!r} phone={phone!r}) — skipping"
                )
            else:
                logger.warning(
                    f"DuplicateDetector.register DB error (non-fatal): {exc}"
                )
            try:
                from app.models.models import db
                db.session.rollback()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Normalisation helpers (unchanged from JSON version)
    # ------------------------------------------------------------------

    @staticmethod
    def _norm_email(v: Any) -> str:
        return str(v).lower().strip() if v else ''

    def _norm_phone(self, v: Any) -> str:
        return self._RE_NON_DIGIT.sub('', str(v)) if v else ''


# ============================================================================
# 6b. LEAD QUALITY MEMORY
# ============================================================================

_LEAD_MEMORY_PATH = _DATA_DIR / 'lead_quality_memory.json'
_LEAD_MEMORY_MAX  = 2_000   # cap stored leads to keep file small


class LeadQualityMemory:
    """
    Stores feature vectors + outcomes of past leads.
    At scoring time, finds the K nearest historical leads and returns
    a memory_signal (±adjustment 0–10 points) based on their real outcomes.

    Similarity metric: cosine similarity on the 30–35-feature vector.
    """

    _K       = 5    # neighbours to consult
    _THRESH  = 0.75  # minimum cosine similarity to count as "similar"

    def __init__(self):
        self._lock = threading.RLock()
        # List of {'features': [...], 'outcome': str, 'binary': 0|1|None, 'ts': str}
        self._records: List[Dict[str, Any]] = []
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def record(self, features: np.ndarray, outcome: str, binary: Optional[int]) -> None:
        """Store a labeled lead's feature vector for future similarity queries."""
        with self._lock:
            self._records.append({
                'features': features[0].tolist(),
                'outcome':  outcome,
                'binary':   binary,
                'ts':       datetime.now(timezone.utc).isoformat(),
            })
            if len(self._records) > _LEAD_MEMORY_MAX:
                # Keep newest records; evict oldest
                self._records = self._records[-_LEAD_MEMORY_MAX:]
        self._save()

    def memory_signal(self, features: np.ndarray) -> Dict[str, Any]:
        """
        Find K most similar historical leads and return an adjustment signal.

        Returns:
          {
            'adjustment':   int    — score delta (-10 to +10) to add to final score
            'n_similar':    int    — number of neighbours found above threshold
            'avg_binary':   float  — mean binary outcome of neighbours (0.0–1.0)
            'confidence':   float  — how confident the signal is (0–1)
          }
        """
        with self._lock:
            records = list(self._records)

        if not records:
            return {'adjustment': 0, 'n_similar': 0, 'avg_binary': None, 'confidence': 0.0}

        query = features[0]
        q_norm = np.linalg.norm(query)
        if q_norm < 1e-8:
            return {'adjustment': 0, 'n_similar': 0, 'avg_binary': None, 'confidence': 0.0}

        similarities = []
        for rec in records:
            if rec.get('binary') is None:
                continue  # skip soft-label leads
            vec = np.array(rec['features'], dtype=np.float32)
            v_norm = np.linalg.norm(vec)
            if v_norm < 1e-8:
                continue
            cos_sim = float(np.dot(query, vec) / (q_norm * v_norm))
            if cos_sim >= self._THRESH:
                similarities.append((cos_sim, rec['binary']))

        if not similarities:
            return {'adjustment': 0, 'n_similar': 0, 'avg_binary': None, 'confidence': 0.0}

        # Top-K most similar
        top_k = sorted(similarities, key=lambda x: x[0], reverse=True)[:self._K]
        n = len(top_k)
        avg_bin   = float(np.mean([b for _, b in top_k]))
        avg_sim   = float(np.mean([s for s, _ in top_k]))
        confidence = round(avg_sim * (n / self._K), 3)

        # Adjustment: positive outcome history → +points, negative → -points
        # Scale: avg_bin=1.0 → +10, avg_bin=0.0 → -10, 0.5 → 0 (neutral)
        adjustment = int(round((avg_bin - 0.5) * 20 * confidence))
        adjustment = max(-10, min(10, adjustment))

        return {
            'adjustment': adjustment,
            'n_similar':  n,
            'avg_binary': round(avg_bin, 3),
            'confidence': confidence,
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self):
        try:
            tmp = _LEAD_MEMORY_PATH.with_suffix('.tmp')
            with open(tmp, 'w') as fh:
                json.dump(self._records, fh)
            tmp.replace(_LEAD_MEMORY_PATH)
        except Exception as exc:
            logger.warning(f"LeadQualityMemory._save: {exc}")

    def _load(self):
        try:
            if _LEAD_MEMORY_PATH.exists():
                with open(_LEAD_MEMORY_PATH) as fh:
                    self._records = json.load(fh)
        except Exception as exc:
            logger.warning(f"LeadQualityMemory._load: {exc}")


# ============================================================================
# 7. LEAD QUALITY CLASSIFIER
# ============================================================================

class LeadQualityClassifier:
    """
    Assign an actionable quality tier to a lead.

    Tiers (by adjusted score):
      spam       —  blocked before scoring
      premium    ≥ 80   Immediate personal outreach
      qualified  ≥ 60   Schedule discovery call within 24 h
      marginal   ≥ 40   Add to nurture sequence
      low        ≥ 20   Manual review
      junk        < 20   Discard
    """

    _TIERS = [
        (SCORE_HOT,  'premium',   'Immediate personal outreach — high conversion probability'),
        (SCORE_WARM, 'qualified', 'Schedule discovery call within 24 hours'),
        (40,         'marginal',  'Add to nurture sequence — monitor for engagement'),
        (20,         'low',       'Manual review — low conversion probability'),
        (0,          'junk',      'Discard — insufficient data or quality signals'),
    ]

    def classify(
        self,
        final_score: int,
        spam_result: Optional[Dict[str, Any]] = None,
        completeness: float = 1.0,
        duplicate_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        modifiers: List[str] = []

        # Spam overrides everything
        if spam_result and spam_result.get('is_spam'):
            return {
                'tier':           'spam',
                'action':         'Block — spam or bot submission detected',
                'modifiers':      spam_result.get('issues', []),
                'adjusted_score': 0,
            }

        # Duplicate warning (does not block, just annotates)
        if duplicate_result and duplicate_result.get('is_exact_duplicate'):
            modifiers.append('duplicate:' + ','.join(duplicate_result.get('duplicate_fields', [])))

        # Completeness-based score adjustment
        adjusted = final_score
        if completeness < 0.30:
            adjusted = int(adjusted * 0.85)
            modifiers.append('low_completeness_penalty')
        elif completeness < 0.50:
            adjusted = int(adjusted * 0.92)
            modifiers.append('medium_completeness_penalty')

        adjusted = max(0, min(100, adjusted))

        for threshold, tier, action in self._TIERS:
            if adjusted >= threshold:
                _audit_log(
                    decision_type='quality_tier',
                    result=tier,
                    extra={'adjusted_score': adjusted, 'modifiers': modifiers},
                )
                return {
                    'tier':           tier,
                    'action':         action,
                    'modifiers':      modifiers,
                    'adjusted_score': adjusted,
                }

        _audit_log(
            decision_type='quality_tier',
            result='junk',
            extra={'adjusted_score': adjusted, 'modifiers': modifiers},
        )
        return {
            'tier':           'junk',
            'action':         'Discard — insufficient data or quality signals',
            'modifiers':      modifiers,
            'adjusted_score': adjusted,
        }


# ============================================================================
# 8. ML DECISION LAYER — main orchestrator
# ============================================================================

class MLDecisionLayer:
    """
    Central brain for intelligent provider routing and score combination.

    Usage (in ai.py):
        decision = get_decision_layer()
        tier, result = decision.qualify(lead_data, lead_id=lead.id)
    """

    def __init__(self):
        self.tracker          = ProviderTracker()
        self.feedback_tracker = FeedbackAccuracyTracker()
        self.evaluator        = ResponseQualityEvaluator()
        self.dataset          = DatasetLogger()
        self.spam             = SpamDetector()
        self.dedup            = DuplicateDetector()
        self.classifier       = LeadQualityClassifier()
        self.lead_memory      = LeadQualityMemory()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def qualify(
        self,
        lead_data: Dict[str, Any],
        lead_id: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Main entry point. Returns (tier_name, qualification_result).

        Execution order (best-tier design):
          1. Run rule-based agent + ML first — zero API cost, always fast.
          2. Feed all signals into _decide_best_tier → picks the optimal tier.
          3. Only call LLM if the tier warrants it.
        """
        t0 = time.monotonic()

        completeness = compute_completeness(lead_data)
        features, ml_score, ml_confidence = self._get_ml_signal(lead_data)

        # ── Pre-checks: spam + duplicate ─────────────────────────────────
        spam_result = self.spam.check(lead_data)
        dup_result  = self.dedup.check(lead_data)

        if spam_result['is_spam']:
            _audit_log(
                decision_type='spam_blocked',
                result='blocked',
                lead_id=lead_id,
                extra={
                    'spam_score': spam_result['spam_score'],
                    'issues':     spam_result['issues'],
                },
            )
            quality_class = self.classifier.classify(
                0, spam_result=spam_result,
                completeness=completeness, duplicate_result=dup_result,
            )
            return TIER_4_LLM_HEAVY, {
                'score': 0,
                'category': 'Cold',
                'confidence': 0.99,
                'ai_provider': 'SpamDetector',
                'routing_tier': 'spam_blocked',
                'data_completeness': round(completeness, 2),
                'spam': spam_result,
                'duplicate': dup_result,
                'quality': quality_class,
                'scoring_breakdown': {'spam': spam_result},
                'latency_ms': round((time.monotonic() - t0) * 1000),
            }

        if dup_result['is_exact_duplicate']:
            logger.info(
                f"[DuplicateDetector] lead={lead_id} is a duplicate "
                f"(fields={dup_result['duplicate_fields']})"
            )
        else:
            # ── FAISS semantic near-duplicate check (only for non-exact-dups) ─
            try:
                from app.services.advanced_ai import get_faiss_dedup, get_embedder, generate_lead_embedding
                _embedder = get_embedder()
                _faiss    = get_faiss_dedup()
                if _embedder is not None and _faiss is not None and _faiss.index is not None:
                    _emb = generate_lead_embedding(lead_data, _embedder)
                    if _emb is not None:
                        _similar = _faiss.find_duplicates(_emb, threshold=0.85)
                        if _similar:
                            dup_result['near_duplicate_ids'] = _similar
                            dup_result['duplicate_type']     = 'semantic'
                            logger.info(
                                f"[FAISSDedup] lead={lead_id} is a semantic near-duplicate "
                                f"of lead(s) {_similar}"
                            )
            except Exception as _faiss_err:
                logger.debug(f"FAISS semantic dedup error (non-fatal): {_faiss_err}")

        # --- Layer 1: Rules (free, instant) + Layer 2: ML ----------------
        provider_scores: Dict[str, float] = {}
        breakdown: Dict[str, Any] = {}

        agent_score = self._run_agent(lead_data, breakdown)
        if agent_score is not None:
            provider_scores['agent'] = agent_score

        if ml_score is not None:
            provider_scores['ml'] = float(ml_score)
            breakdown['ml'] = {
                'score':      ml_score,
                'confidence': ml_confidence,
                'features':   features[0].tolist() if features is not None else [],
            }

        # --- Best-Tier Decision (all signals available now) ---------------
        tier = self._decide_best_tier(completeness, ml_confidence, ml_score, agent_score)
        logger.info(
            f"[Best Tier] lead={lead_id} → {tier} | "
            f"completeness={completeness:.2f} ml_conf={ml_confidence} "
            f"agent={agent_score} ml={ml_score}"
        )

        # --- Layer 3: LLM (only when tier calls for it) -------------------
        llm_result = None
        if tier in (TIER_2_ML_GROQ, TIER_3_FULL, TIER_4_LLM_HEAVY):
            llm_result = self._run_llm(
                lead_data,
                breakdown,
                provider_scores,
                agent_score,
                # TIER_2 and TIER_3 both use Groq-first: Groq (70B) is fast and smart.
                # Gemini is reserved as fallback. TIER_4 (very sparse data) still prefers
                # Gemini's deeper reasoning as primary with Groq as safety net.
                prefer_fast=(tier in (TIER_2_ML_GROQ, TIER_3_FULL)),
            )

        # --- Dynamic weight combination ----------------------------------
        final_score = self._combine(provider_scores, tier, ml_confidence)

        # --- Lead Quality Memory signal ----------------------------------
        memory_signal = {'adjustment': 0, 'n_similar': 0, 'avg_binary': None, 'confidence': 0.0}
        if features is not None:
            try:
                memory_signal = self.lead_memory.memory_signal(features)
                if memory_signal['adjustment'] != 0:
                    adjusted_by_memory = min(100, max(0, final_score + memory_signal['adjustment']))
                    logger.info(
                        f"[LeadMemory] lead={lead_id} signal={memory_signal['adjustment']:+d} "
                        f"({final_score}→{adjusted_by_memory}) n_similar={memory_signal['n_similar']}"
                    )
                    final_score = adjusted_by_memory
            except Exception as _mem_err:
                logger.debug(f"[LeadMemory] non-fatal error: {_mem_err}")

        # --- Build response ----------------------------------------------
        category = 'Hot' if final_score >= SCORE_HOT else 'Warm' if final_score >= SCORE_WARM else 'Cold'
        layer_count = len(provider_scores)
        confidence = min(0.95, 0.45 + layer_count * 0.18)

        # Quality classification (tier + recommended action)
        quality_class = self.classifier.classify(
            final_score,
            spam_result=spam_result,
            completeness=completeness,
            duplicate_result=dup_result,
        )

        response: Dict[str, Any] = {}
        if llm_result:
            response.update(llm_result)

        response.update({
            'score':             final_score,
            'category':          category,
            'confidence':        round(confidence, 2),
            'ai_provider':       ' + '.join(provider_scores.keys()),
            'routing_tier':      tier,
            'data_completeness': round(completeness, 2),
            'scoring_breakdown': breakdown,
            'latency_ms':        round((time.monotonic() - t0) * 1000),
            'spam':              spam_result,
            'duplicate':         dup_result,
            'quality':           quality_class,
            'memory_signal':     memory_signal,
        })

        # Register contact info for future duplicate checks (only if not duplicate)
        if not dup_result['is_exact_duplicate']:
            self.dedup.register(lead_data)

        # --- Log to training dataset -------------------------------------
        try:
            self.dataset.log(
                lead_id=lead_id,
                features=features if features is not None else np.zeros((1, N_FEATURES)),
                data_completeness=completeness,
                route_tier=tier,
                provider_scores=provider_scores,
                final_score=final_score,
                ml_confidence=ml_confidence,
                prompt_version=llm_result.get('prompt_version') if llm_result else None,
            )
        except Exception as _log_err:
            logger.warning(f"[ProductionSafety] DatasetLogger failed (non-fatal): {_log_err}")

        return tier, response

    def qualify_safe(
        self,
        lead_data: Dict[str, Any],
        lead_id: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Production-safe wrapper around qualify().
        Catches ALL exceptions and returns a rule-based fallback score
        so the API never returns 500 due to ML/AI failures.
        """
        try:
            return self.qualify(lead_data, lead_id=lead_id)
        except Exception as exc:
            logger.error(
                f"[ProductionSafety] qualify() raised unexpectedly: {exc}",
                exc_info=True,
            )
            _audit_log(
                decision_type='qualify_exception',
                result='fallback',
                lead_id=lead_id,
                extra={'error': str(exc)},
            )
            # Emergency rule-based fallback
            try:
                from app.services.qualification_agent import QualificationAgent
                agent  = QualificationAgent()
                result = agent.qualify_lead(lead_data)
                score  = result.score
                cat    = result.category
            except Exception:
                score = 30
                cat   = 'Cold'

            return TIER_4_LLM_HEAVY, {
                'score':             score,
                'category':          cat,
                'confidence':        0.30,
                'ai_provider':       'FallbackAgent',
                'routing_tier':      'fallback',
                'data_completeness': 0.0,
                'scoring_breakdown': {'fallback': True, 'error': str(exc)},
                'latency_ms':        0,
                'spam':              {'is_spam': False, 'spam_score': 0.0, 'issues': []},
                'duplicate':         {'is_exact_duplicate': False, 'duplicate_fields': []},
                'quality':           {'tier': 'low', 'action': 'Manual review recommended',
                                      'modifiers': ['fallback_mode'], 'adjusted_score': score},
                'memory_signal':     {'adjustment': 0, 'n_similar': 0, 'avg_binary': None, 'confidence': 0.0},
            }

    def on_lead_status_change(
        self,
        lead_id:      int,
        new_status:   str,
        *,
        label_source: str = 'user_feedback',
        feedback_notes: Optional[str] = None,
        recorded_by:  Optional[int] = None,
    ) -> int:
        """
        Call this whenever a lead's outcome is known.

        Steps:
          1. Label the JSONL training dataset record (backward compat)
          2. Persist a LeadOutcome row in the DB via DatasetManager (Task 1)
          3. Update ProviderTracker MAE (for dynamic weight computation)
          4. Update FeedbackAccuracyTracker (per-source / per-channel accuracy)

        Returns the number of JSONL records that were labeled.
        """
        # ── 1. JSONL labeling (existing behaviour, kept for backward compat) ──
        count = self.dataset.label_lead(lead_id, new_status)

        # ── 2. DB persistence via DatasetManager ──────────────────────────────
        ml_score = rule_score = llm_score = scoring_method = lead_source = None
        try:
            # Read the JSONL record to get scores at prediction time
            if DATASET_PATH.exists():
                with open(DATASET_PATH) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            if rec.get('lead_id') == lead_id:
                                ps = rec.get('provider_scores', {})
                                ml_score      = ps.get('ml')
                                rule_score    = ps.get('agent')
                                llm_score     = ps.get('gemini') or ps.get('groq')
                                scoring_method = rec.get('route_tier')
                                break
                        except json.JSONDecodeError:
                            pass
        except Exception as exc:
            logger.debug(f"on_lead_status_change: could not read JSONL scores: {exc}")

        try:
            from flask import current_app
            with current_app.app_context():
                from app.models.models import db, Lead
                from app.services.dataset_manager import get_dataset_manager

                lead = db.session.get(Lead, lead_id)
                if lead:
                    lead_source = lead.source or 'unknown'
                    manager = get_dataset_manager()
                    manager.record_outcome(
                        lead_id        = lead_id,
                        outcome        = new_status,
                        label_source   = label_source,
                        ml_score       = ml_score,
                        rule_score     = rule_score,
                        llm_score      = llm_score,
                        scoring_method = scoring_method,
                        feedback_notes = feedback_notes,
                        recorded_by    = recorded_by,
                    )
                    db.session.commit()
        except RuntimeError:
            # No Flask app context (unit tests / CLI) — skip DB write
            pass
        except Exception as exc:
            logger.warning(f"on_lead_status_change: DB persist failed: {exc}")

        # ── 3. ProviderTracker MAE update ─────────────────────────────────────
        ground_truth = _OUTCOME_GT_SCORE.get(new_status, 20.0)
        self._update_provider_accuracy(lead_id, ground_truth)

        # ── 4. FeedbackAccuracyTracker ────────────────────────────────────────
        self.feedback_tracker.record(
            outcome      = new_status,
            ml_score     = ml_score,
            rule_score   = rule_score,
            llm_score    = llm_score,
            label_source = label_source,
            lead_source  = lead_source or 'unknown',
        )

        # ── 5. LeadQualityMemory — store feature vector + outcome ─────────────
        try:
            if DATASET_PATH.exists():
                with open(DATASET_PATH) as _fh:
                    for _line in _fh:
                        _line = _line.strip()
                        if not _line:
                            continue
                        try:
                            _rec = json.loads(_line)
                            if _rec.get('lead_id') == lead_id:
                                _feats = _rec.get('features')
                                if _feats and len(_feats) > 0:
                                    _feat_arr = np.array([_feats], dtype=np.float32)
                                    _binary = _OUTCOME_BINARY.get(new_status)
                                    self.lead_memory.record(_feat_arr, new_status, _binary)
                                break
                        except (json.JSONDecodeError, Exception):
                            pass
        except Exception as _mem_err:
            logger.debug(f"LeadQualityMemory record failed (non-fatal): {_mem_err}")

        if count > 0:
            logger.info(
                f"[Feedback] lead={lead_id} outcome={new_status} "
                f"src={label_source} jsonl_labeled={count}"
            )
        return count

    def should_auto_retrain(self, min_new_labeled: int = 20) -> bool:
        """True if enough new labeled samples have accumulated since last train."""
        stats = self.dataset.dataset_stats()
        return stats['positives'] >= 5 and stats['negatives'] >= 5 \
            and stats['labeled'] >= min_new_labeled

    def quality_report(self) -> Dict[str, Any]:
        """Return provider accuracy + dataset stats for the /ai/quality-report endpoint."""
        providers = ['agent', 'ml', 'gemini', 'groq']
        accuracy = {}
        for p in providers:
            mae = self.tracker.mae(p)
            n   = self.tracker.sample_count(p)
            accuracy[p] = {
                'mae':      round(mae, 2) if mae is not None else None,
                'samples':  n,
                'accuracy': round(max(0, 1 - (mae / 100)), 3) if mae is not None else None,
            }
        return {
            'provider_accuracy': accuracy,
            'dataset':           self.dataset.dataset_stats(),
            'dynamic_weights':   self.tracker.provider_weights(['agent', 'ml', 'gemini', 'groq']),
            'feedback_accuracy': self.feedback_tracker.accuracy_report(),
        }

    # ------------------------------------------------------------------
    # INTERNAL: ROUTING
    # ------------------------------------------------------------------

    def _decide_best_tier(
        self,
        completeness: float,
        ml_confidence: Optional[float],
        ml_score: Optional[int],
        agent_score: Optional[float],
    ) -> str:
        """
        Select the most efficient tier that produces the highest-quality result.

        5 signals evaluated in priority order:

          1. Data completeness  — sparse data forces LLM-heavy inference
          2. ML uncertainty + disagreement  — confused ML + rule conflict → Gemini needed
          3. Borderline zone (50–75)  — ambiguous leads must never skip LLM
          4. ML/rule agreement gap  — large gap → LLM arbitration required
          5. ML historical reliability (ProviderTracker MAE)  — earned trust unlocks TIER_1

        Tier map:
          TIER_1 (ml_only)    → ML + rules fully agree, high confidence, proven reliable
          TIER_2 (ml_groq)    → Moderate confidence, no conflict, fast Groq check sufficient
          TIER_3 (full_stack) → Borderline / disagreement / uncertain — Gemini brain
          TIER_4 (llm_heavy)  → Sparse data or very confused ML — LLM must lead
        """
        # ── Signal 1: Sparse data → LLM must infer missing context ──────────
        if completeness < COMPLETENESS_LOW:
            return TIER_4_LLM_HEAVY

        # ── Pre-compute agreement / score signals ────────────────────────────
        _ml = float(ml_score) if ml_score is not None else None
        _ag = float(agent_score) if agent_score is not None else None

        agreement_gap = abs(_ml - _ag) if (_ml is not None and _ag is not None) else 0.0

        if _ml is not None and _ag is not None:
            combined = 0.55 * _ml + 0.45 * _ag   # ML slightly outweighs rules
        elif _ml is not None:
            combined = _ml
        elif _ag is not None:
            combined = _ag
        else:
            combined = 50.0

        # Large gap: ML and rules fundamentally disagree → LLM must arbitrate
        high_disagreement = agreement_gap > 25

        # Borderline zone: a lead scoring 50–75 is genuinely uncertain — never skip LLM
        is_borderline = 50.0 <= combined <= 75.0

        # ── Signal 2: Very uncertain ML + high disagreement → needs deep reasoning
        if (
            ml_confidence is not None and ml_confidence < 0.40
            and high_disagreement
        ):
            return TIER_3_FULL if completeness >= COMPLETENESS_MED else TIER_4_LLM_HEAVY

        # ── Signal 3: Borderline or high disagreement → always use Gemini brain
        if is_borderline or high_disagreement:
            return TIER_3_FULL

        # ── Signal 4: Check ML track record from ProviderTracker ────────────
        ml_mae = self.tracker.mae('ml')
        # Reliable = MAE < 15 (accurate), OR no history yet (benefit of doubt for new system)
        ml_reliable = ml_mae is None or ml_mae < 15.0

        # ── Signal 5: TIER_1 — ML alone sufficient ──────────────────────────
        # Requires all of: high completeness, high ML confidence, no conflict,
        #                  not borderline (already checked), and proven ML accuracy
        if (
            completeness >= COMPLETENESS_HIGH
            and ml_confidence is not None
            and ml_confidence >= ML_ONLY_CONF_THRESHOLD
            and ml_reliable
        ):
            return TIER_1_ML_ONLY

        # ── Signal 6: TIER_2 — Groq speed-check sufficient ──────────────────
        # Medium completeness, moderate ML confidence, no major conflict
        if (
            completeness >= COMPLETENESS_MED
            and ml_confidence is not None
            and ml_confidence >= ML_ASSIST_CONF_THRESHOLD
        ):
            return TIER_2_ML_GROQ

        # ── Default: TIER_3 — Gemini brain + ML + rules ─────────────────────
        return TIER_3_FULL

    # ------------------------------------------------------------------
    # INTERNAL: LAYER RUNNERS
    # ------------------------------------------------------------------

    @staticmethod
    def _run_agent(
        lead_data: Dict[str, Any],
        breakdown: Dict[str, Any],
    ) -> Optional[float]:
        try:
            from app.services.qualification_agent import QualificationAgent
            agent = QualificationAgent()
            result = agent.qualify_lead(lead_data)
            breakdown['rule_based'] = {
                'score':      result.score,
                'category':   result.category,
                'confidence': result.confidence,
            }
            return float(result.score)
        except Exception as e:
            logger.warning(f"Agent layer error: {e}")
            return None

    @staticmethod
    def _get_ml_signal(
        lead_data: Dict[str, Any],
    ) -> Tuple[Optional[np.ndarray], Optional[int], Optional[float]]:
        """
        Returns (features, score, confidence).
        Production-safe: any failure returns (None, None, None) so the pipeline
        falls through to rule-based + LLM tiers without raising.
        Enforces a 5-second timeout via threading.
        """
        # Fast pre-check — skip thread overhead entirely when no model is loaded.
        # This avoids burning 5 s per call while the system awaits retraining.
        from app.services.advanced_ai import get_ml_model, extract_features, is_ml_model_ready
        if not is_ml_model_ready():
            return None, None, None

        _result: List[Any] = [None, None, None]
        _exc:    List[Any] = [None]

        def _run():
            try:
                model = get_ml_model()
                if model is None or model.model is None:
                    return
                features = extract_features(lead_data)
                if features is None or features.shape[1] == 0:
                    return
                prob = model.model.predict_proba(features)[0][1]
                score = int(round(prob * 100))
                _result[0] = features
                _result[1] = score
                _result[2] = round(float(prob), 4)
            except Exception as e:
                _exc[0] = e

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=5.0)

        if t.is_alive():
            logger.warning("[ProductionSafety] ML signal timed out — falling back to rules+LLM")
            _audit_log('ml_timeout', 'timeout', extra={'timeout_secs': 5})
            return None, None, None

        if _exc[0]:
            logger.warning(f"[ProductionSafety] ML signal error (non-fatal): {_exc[0]}")
            return None, None, None

        return tuple(_result)

    def _run_llm(
        self,
        lead_data: Dict[str, Any],
        breakdown: Dict[str, Any],
        provider_scores: Dict[str, float],
        agent_score: Optional[float],
        prefer_fast: bool = False,
        timeout_secs: float = 20.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Call LLM layer with quality gate + secondary-provider retry.

        Production-safe:
          - Enforces timeout_secs (default 20s) via threading
          - Any LLM failure returns None; pipeline continues with rules + ML
          - Both providers failing is logged as a structured audit event

        Routing:
          prefer_fast=True  (TIER_2) → Groq-first, Gemini as rescue
          prefer_fast=False (TIER_3/4) → Gemini brain, Groq safety fallback
        """
        _llm_result: List[Any] = [None]

        def _run():
            _llm_result[0] = self._run_llm_inner(
                lead_data, breakdown, provider_scores, agent_score, prefer_fast
            )

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=timeout_secs)

        if t.is_alive():
            logger.warning(
                f"[ProductionSafety] LLM timed out after {timeout_secs}s "
                f"(prefer_fast={prefer_fast}) — relying on ML + rules"
            )
            _audit_log('llm_timeout', 'timeout', extra={'timeout_secs': timeout_secs,
                                                         'prefer_fast': prefer_fast})
            return None

        return _llm_result[0]

    def _run_llm_inner(
        self,
        lead_data: Dict[str, Any],
        breakdown: Dict[str, Any],
        provider_scores: Dict[str, float],
        agent_score: Optional[float],
        prefer_fast: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Inner LLM execution (called inside a thread by _run_llm)."""
        try:
            from app.services.gemini_service import get_ai_service
            ai_svc = get_ai_service()

            # ── Circuit-breaker: skip disabled primary provider ───────────────
            _use_fast = prefer_fast
            primary_key = 'groq' if prefer_fast else 'gemini'
            if self.tracker.is_disabled(primary_key):
                logger.info(
                    f"[CircuitBreaker] {primary_key} is disabled — skipping to secondary"
                )
                _use_fast = not prefer_fast

            llm_result = ai_svc.qualify_lead(lead_data, prefer_fast=_use_fast)
            # Use normalized short key so it matches _TIER_PRIORS + tracker keys
            provider_key = llm_result.get('provider_key') or ai_svc.provider_key
            provider_name = llm_result.get('ai_provider', provider_key)

            # ── Ollama local-LLM fallback when no cloud API keys are configured ─
            if provider_key == 'rules':
                try:
                    from app.services.advanced_ai import qualify_with_ollama
                    _ollama_res = qualify_with_ollama(lead_data)
                    if _ollama_res:
                        _ollama_res.setdefault('provider_key', 'ollama')
                        llm_result    = _ollama_res
                        provider_key  = 'ollama'
                        provider_name = _ollama_res.get('ai_provider', 'Ollama')
                        logger.info("[MLRouter] Ollama local-LLM used (no cloud API keys)")
                except Exception as _ol_err:
                    logger.debug(f"[Ollama] fallback skipped: {_ol_err}")

            quality = self.evaluator.evaluate(
                llm_result,
                agent_score=agent_score,
                provider=provider_key,
            )

            if quality['usable']:
                self.tracker.record_quality_success(provider_key)
                provider_scores[provider_key] = float(llm_result.get('score', 50))
                breakdown['llm'] = {**llm_result, 'quality': quality}
                return llm_result

            # ── Quality gate failed: trip circuit breaker + try secondary ─────
            self.tracker.record_quality_failure(provider_key)
            logger.warning(
                f"LLM [{provider_name}] failed quality gate "
                f"(q={quality['quality_score']:.2f}, issues={quality['issues']}) "
                f"— trying secondary provider"
            )
            breakdown['llm_rejected_primary'] = {
                'provider': provider_key, 'quality': quality,
                'raw_score': llm_result.get('score'),
            }

            secondary_key = 'gemini' if prefer_fast else 'groq'
            if self.tracker.is_disabled(secondary_key):
                logger.warning(f"[CircuitBreaker] secondary {secondary_key} also disabled — relying on ML + rules")
                return None

            llm_result2 = ai_svc.qualify_lead(lead_data, prefer_fast=not prefer_fast)

            provider_key2 = llm_result2.get('provider_key') or ai_svc.provider_key
            provider_name2 = llm_result2.get('ai_provider', provider_key2)

            quality2 = self.evaluator.evaluate(
                llm_result2,
                agent_score=agent_score,
                provider=provider_key2,
            )

            if quality2['usable']:
                self.tracker.record_quality_success(provider_key2)
                logger.info(f"Secondary provider [{provider_name2}] passed quality gate")
                provider_scores[provider_key2] = float(llm_result2.get('score', 50))
                breakdown['llm'] = {**llm_result2, 'quality': quality2, 'used_secondary': True}
                return llm_result2

            # Both providers failed quality
            self.tracker.record_quality_failure(provider_key2)
            logger.warning("Both LLM providers failed quality gate — relying on ML + rules")
            breakdown['llm_rejected_secondary'] = {
                'provider': provider_key2, 'quality': quality2,
                'raw_score': llm_result2.get('score'),
            }
            return None

        except Exception as e:
            logger.error(f"LLM layer error: {e}")
            return None

    # ------------------------------------------------------------------
    # INTERNAL: DYNAMIC SCORE COMBINATION
    # ------------------------------------------------------------------

    def _combine(
        self,
        provider_scores: Dict[str, float],
        tier: str,
        ml_confidence: Optional[float],
    ) -> int:
        """
        Confidence-driven hybrid scoring:

        Step 1 — base from tracker MAE history OR tier priors (cold-start).
        Step 2 — confidence reshape:
            ml_conf >= 0.85  → ML gets 55% cap (LLM still has influence)
            ml_conf >= 0.70  → ML gets 45% cap
            ml_conf <  0.40  → LLM/rules get 75% combined weight
        Step 3 — historical accuracy penalty/bonus per provider.
        Step 4 — agent floor: final score cannot be more than 20 pts below the
                 rule-based agent score.  Prevents ML from crashing scores when
                 LLM times out and ML is the only non-rules signal present.
        """
        if not provider_scores:
            return 50

        if len(provider_scores) == 1:
            return int(round(list(provider_scores.values())[0]))

        # ── Step 1: Base weights (history or prior) ───────────────────────────
        dyn_weights = self.tracker.provider_weights(list(provider_scores.keys()))
        tier_priors = _TIER_PRIORS.get(tier, {})

        blended: Dict[str, float] = {}
        for p in provider_scores:
            n = self.tracker.sample_count(p)
            blended[p] = dyn_weights[p] if n >= 5 else tier_priors.get(p, 1.0 / len(provider_scores))

        # ── Step 2: Confidence-driven reshape ─────────────────────────────────
        if ml_confidence is not None and 'ml' in blended:
            llm_keys = [k for k in provider_scores if k in ('gemini', 'groq')]

            if ml_confidence >= 0.85:
                # High ML confidence — cap ML at 55% so LLM still has meaningful influence.
                ml_target = 0.55
                remaining = 1.0 - ml_target
                total_non_ml = sum(v for k, v in blended.items() if k != 'ml') or 1.0
                for k in blended:
                    if k != 'ml':
                        blended[k] = (blended[k] / total_non_ml) * remaining
                blended['ml'] = ml_target

            elif ml_confidence >= 0.70:
                # Moderately high — cap at 45% so LLM has meaningful influence
                ml_target = 0.45
                remaining = 1.0 - ml_target
                total_non_ml = sum(v for k, v in blended.items() if k != 'ml') or 1.0
                for k in blended:
                    if k != 'ml':
                        blended[k] = (blended[k] / total_non_ml) * remaining
                blended['ml'] = ml_target

            elif ml_confidence < 0.40 and llm_keys:
                # Uncertain ML — let LLM/rules lead (75% combined to non-ML)
                ml_target = 0.25
                remaining = 1.0 - ml_target
                total_non_ml = sum(v for k, v in blended.items() if k != 'ml') or 1.0
                for k in blended:
                    if k != 'ml':
                        blended[k] = (blended[k] / total_non_ml) * remaining
                blended['ml'] = ml_target

        # ── Step 3: Historical accuracy adjustment per provider ───────────────
        ml_mae = self.tracker.mae('ml')
        if ml_mae is not None and 'ml' in blended:
            if ml_mae < 10.0:
                # Highly accurate ML (MAE < 10) — reward it with a +10% weight bonus
                blended['ml'] = min(blended['ml'] + 0.10, 0.90)
            elif ml_mae < 20.0:
                # Moderate accuracy — small bonus
                blended['ml'] = min(blended['ml'] + 0.05, 0.85)
            else:
                # Poor accuracy — penalise up to -10%
                penalty = min(0.10, (ml_mae - 20.0) / 300.0)
                blended['ml'] = max(0.05, blended['ml'] - penalty)

        # Apply same accuracy-based adjustment for LLM providers
        for _llm_key in ('gemini', 'groq'):
            if _llm_key not in blended:
                continue
            _llm_mae = self.tracker.mae(_llm_key)
            if _llm_mae is not None and _llm_mae > 25.0:
                _penalty = min(0.08, (_llm_mae - 25.0) / 375.0)
                blended[_llm_key] = max(0.05, blended[_llm_key] - _penalty)

        # ── Final normalize + weighted sum ────────────────────────────────────
        total = sum(blended.values()) or 1.0
        weights = {p: w / total for p, w in blended.items()}

        final = sum(weights[p] * provider_scores[p] for p in provider_scores)

        # ── Step 4: Agent floor — ML cannot nuke a solid rule-based score ────
        # When LLM times out and only ML + agent are present, an under-trained
        # ML model can produce scores like 0-15 for leads the rules correctly
        # score at 40+.  Cap the downside: never more than 20 pts below agent.
        agent_score = provider_scores.get('agent')
        if agent_score is not None and 'gemini' not in provider_scores and 'groq' not in provider_scores:
            floor = max(0.0, agent_score - 20.0)
            final = max(final, floor)

        return min(max(int(round(final)), 0), 100)

    def _update_provider_accuracy(self, lead_id: int, ground_truth: float):
        """
        Look up the logged prediction for this lead_id and record
        per-provider accuracy in the tracker.
        """
        try:
            if not DATASET_PATH.exists():
                return
            with open(DATASET_PATH) as f:
                for line in reversed(f.readlines()):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get('lead_id') == lead_id:
                            for provider, score in rec.get('provider_scores', {}).items():
                                self.tracker.record(provider, score, ground_truth)
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            logger.warning(f"_update_provider_accuracy failed: {e}")


# ---------------------------------------------------------------------------
# Tier-based static weight priors (cold-start fallback)
# ---------------------------------------------------------------------------
# Keys must match AIService.provider_key ('gemini' | 'groq') and ProviderTracker keys
_TIER_PRIORS: Dict[str, Dict[str, float]] = {
    # TIER_1: ML already passed high-confidence threshold — it leads decisively.
    TIER_1_ML_ONLY:   {'agent': 0.20, 'ml': 0.80},
    # TIER_2: Groq adds context but ML signal is already good — balanced 45/40/15.
    TIER_2_ML_GROQ:   {'agent': 0.15, 'ml': 0.45, 'groq': 0.40},
    # TIER_3: Gemini leads on borderline/complex leads; ML is supporting evidence.
    TIER_3_FULL:      {'agent': 0.10, 'ml': 0.25, 'gemini': 0.65},
    # TIER_4: Data is sparse — LLM must infer; rules act as sanity floor.
    TIER_4_LLM_HEAVY: {'agent': 0.15, 'gemini': 0.85},
}


# ============================================================================
# 6. MODULE-LEVEL SINGLETON
# ============================================================================

_decision_layer: Optional[MLDecisionLayer] = None
_dl_lock = threading.Lock()


def get_decision_layer() -> MLDecisionLayer:
    """Thread-safe singleton accessor."""
    global _decision_layer
    if _decision_layer is None:
        with _dl_lock:
            if _decision_layer is None:
                _decision_layer = MLDecisionLayer()
    return _decision_layer


# ============================================================================
# 7. AUTO-RETRAIN HELPER (called from the API endpoint)
# ============================================================================

def auto_retrain_if_ready(min_new_labeled: int = 20) -> Dict[str, Any]:
    """
    Check if enough new labeled data exists, then retrain the ML model.
    Safe to call on every qualification (will no-op most of the time).
    Returns a status dict.
    """
    dl = get_decision_layer()
    if not dl.should_auto_retrain(min_new_labeled):
        stats = dl.dataset.dataset_stats()
        return {'retrained': False, 'reason': 'insufficient_labeled_data', 'stats': stats}

    try:
        from app.services.advanced_ai import get_ml_model, extract_features
        from app.models.models import Lead

        model = get_ml_model()
        if model is None:
            return {'retrained': False, 'reason': 'ml_model_not_available'}

        # Build training set from BOTH db leads AND dataset-logged leads
        labeled_records = dl.dataset.load_labeled()
        leads_as_dicts: List[Dict[str, Any]] = []

        for rec in labeled_records:
            # Reconstruct a pseudo-lead dict from logged features + label
            label = rec['label']
            pseudo_score = int(label * 100)
            leads_as_dicts.append({
                '_features_override': rec['features'],
                'qualification_score': pseudo_score,
                'label': label,
            })

        # Also pull real leads from DB
        try:
            db_leads = Lead.query.filter(
                Lead.qualification_score.isnot(None),
                Lead.qualification_score > 0,
            ).all()
            for l in db_leads:
                leads_as_dicts.append({
                    'name':                l.name,
                    'email':               l.email,
                    'phone':               l.phone,
                    'company':             l.company,
                    'position':            l.position,
                    'linkedin_url':        l.linkedin_url,
                    'website':             l.website,
                    'industry':            l.industry,
                    'country':             l.country,
                    'interests':           l.interests,
                    'source':              l.source,
                    'qualification_score': l.qualification_score,
                })
        except Exception as db_err:
            logger.warning(f"DB lead fetch during retrain: {db_err}")

        success = model.train_from_leads(leads_as_dicts)
        return {
            'retrained':    success,
            'reason':       'auto_trigger',
            'dataset_rows': len(leads_as_dicts),
            'stats':        dl.dataset.dataset_stats(),
        }
    except Exception as e:
        logger.error(f"auto_retrain_if_ready error: {e}", exc_info=True)
        return {'retrained': False, 'reason': str(e)}
