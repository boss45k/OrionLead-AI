"""
DatasetManager — Production Data Strategy for ML Retraining
============================================================

Responsibilities:
  1. Collect training records from Lead + LeadOutcome tables
  2. Apply a 3-tier labeling priority:
       Tier 1: business_outcome  (converted / rejected)      confidence 1.0
       Tier 2: user_feedback     (contacted / unqualified)   confidence 0.8
       Tier 3: ai_prediction     (hot / warm / cold)         confidence 0.6
  3. Balance the dataset to reduce cold-lead bias
  4. Merge in synthetic data when real leads < MIN_REAL_LEADS
  5. Version every training snapshot (SHA-256 hash + DB record)

Public API:
    manager = DatasetManager()
    result  = manager.build_training_dataset()
    # result.leads     → list of lead dicts with _label + _label_source
    # result.version   → DatasetVersion ORM object (not yet committed)
    # result.stats     → dict summary for logging/API response
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

MIN_REAL_LEADS      = 50      # below this, synthetic data is blended in
TARGET_POSITIVE_RATE = 0.40   # desired fraction of positive class in training set
DATASETS_DIR        = Path(__file__).resolve().parent.parent.parent / 'data' / 'datasets'
SYNTHETIC_CACHE     = Path(__file__).resolve().parent.parent.parent / 'data' / 'synthetic_leads.json'

# Label → binary mapping
_POSITIVE_OUTCOMES = frozenset({'converted', 'contacted', 'hot'})
_NEGATIVE_OUTCOMES = frozenset({'rejected', 'unqualified', 'cold'})

# Label source → confidence
_SOURCE_CONFIDENCE = {
    'business_outcome': 1.0,
    'user_feedback':    0.8,
    'ai_prediction':    0.6,
}


# ─── Result container ─────────────────────────────────────────────────────────

@dataclass
class DatasetBuildResult:
    leads:   List[Dict[str, Any]]
    version: Any                          # DatasetVersion ORM (not yet committed)
    stats:   Dict[str, Any] = field(default_factory=dict)


# ─── DatasetManager ───────────────────────────────────────────────────────────

class DatasetManager:
    """
    Assembles, balances, and versions the ML training dataset.

    Designed to run inside a Flask app context (uses SQLAlchemy + ORM models).
    All DB access is read-only here — the caller is responsible for committing
    the DatasetVersion record after training completes.
    """

    def __init__(self, app_context_required: bool = True):
        self._require_ctx = app_context_required

    # ── Public API ────────────────────────────────────────────────────────────

    def build_training_dataset(
        self,
        *,
        min_label_confidence: float = 0.0,
        include_soft_labels: bool = False,
        balance_method: str = 'auto',   # 'smote' | 'weighted' | 'none' | 'auto'
        max_synthetic_ratio: float = 0.6,
        force_synthetic_n: Optional[int] = None,
    ) -> DatasetBuildResult:
        """
        Assemble a training-ready dataset.

        Parameters
        ----------
        min_label_confidence:
            Exclude labels below this confidence threshold.
        include_soft_labels:
            If True, 'warm' leads (binary_label=None) are treated as positives.
        balance_method:
            How to address class imbalance.
            'auto' → tries SMOTE, falls back to 'weighted'.
        max_synthetic_ratio:
            At most this fraction of the final dataset will be synthetic rows.
        force_synthetic_n:
            Override: generate exactly this many synthetic leads regardless.

        Returns
        -------
        DatasetBuildResult with leads, a (uncommitted) DatasetVersion, and stats.
        """
        # 1. Load real labeled leads from DB
        real_leads = self._load_real_labeled_leads(
            min_confidence=min_label_confidence,
            include_soft=include_soft_labels,
        )
        n_real = len(real_leads)
        logger.info(f"[DatasetManager] Real labeled leads: {n_real}")

        # 2. Determine if synthetic data is needed
        pos_real = sum(1 for l in real_leads if l.get('_label') == 1)
        neg_real = n_real - pos_real
        real_pos_rate = pos_real / n_real if n_real else 0.0

        synthetic_leads: List[Dict[str, Any]] = []
        if n_real < MIN_REAL_LEADS or real_pos_rate < 0.20:
            n_synth = self._compute_synthetic_needed(
                n_real, pos_real, neg_real,
                max_ratio=max_synthetic_ratio,
                force_n=force_synthetic_n,
            )
            synthetic_leads = self._load_synthetic_leads(n_synth)
            logger.info(f"[DatasetManager] Added {len(synthetic_leads)} synthetic leads")

        all_leads = real_leads + synthetic_leads

        # 3. Balance dataset
        resolved_balance = self._resolve_balance_method(balance_method, all_leads)
        all_leads = self._balance_dataset(all_leads, resolved_balance)

        # 4. Compute stats & hash
        n_total  = len(all_leads)
        n_pos    = sum(1 for l in all_leads if l.get('_label') == 1)
        n_neg    = n_total - n_pos
        pos_rate = n_pos / n_total if n_total else 0.0

        label_sources = self._count_label_sources(all_leads)
        data_hash     = self._hash_dataset(all_leads)
        version_tag   = f"v{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # 5. Persist snapshot to disk
        DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_path = DATASETS_DIR / f"{version_tag}.json"
        with open(snapshot_path, 'w') as fh:
            json.dump(all_leads, fh)
        rel_path = str(snapshot_path.relative_to(
            Path(__file__).resolve().parent.parent.parent
        ))

        # 6. Build DatasetVersion ORM object (caller commits it)
        from app.models.models import DatasetVersion
        version = DatasetVersion(
            version_tag    = version_tag,
            data_hash      = data_hash,
            n_total        = n_total,
            n_real         = n_real,
            n_synthetic    = len(synthetic_leads),
            n_positive     = n_pos,
            n_negative     = n_neg,
            positive_rate  = pos_rate,
            label_sources  = label_sources,
            balance_method = resolved_balance,
            snapshot_path  = rel_path,
        )

        stats = {
            'version_tag':   version_tag,
            'n_total':       n_total,
            'n_real':        n_real,
            'n_synthetic':   len(synthetic_leads),
            'n_positive':    n_pos,
            'n_negative':    n_neg,
            'positive_rate': round(pos_rate, 4),
            'balance_method':resolved_balance,
            'label_sources': label_sources,
            'snapshot_path': rel_path,
            'data_hash':     data_hash,
        }
        logger.info(
            f"[DatasetManager] Dataset built — {n_total} leads "
            f"({n_pos} pos / {n_neg} neg = {pos_rate:.1%}) "
            f"balance={resolved_balance} hash={data_hash[:8]}"
        )
        return DatasetBuildResult(leads=all_leads, version=version, stats=stats)

    def record_outcome(
        self,
        lead_id: int,
        outcome: str,
        label_source: str,
        *,
        ml_score: Optional[float] = None,
        rule_score: Optional[float] = None,
        llm_score: Optional[float] = None,
        scoring_method: Optional[str] = None,
        feedback_notes: Optional[str] = None,
        recorded_by: Optional[int] = None,
    ) -> Any:
        """
        Upsert a LeadOutcome for a lead.

        If an outcome already exists for this lead, it is REPLACED only if
        the new label_source has equal or higher confidence than the existing one.

        Returns the LeadOutcome ORM object (not yet committed).
        """
        from app.models.models import LeadOutcome, db

        allowed_outcomes = {
            'converted', 'contacted', 'rejected', 'unqualified',
            'cold', 'warm', 'hot',
        }
        if outcome not in allowed_outcomes:
            raise ValueError(f"Unknown outcome '{outcome}'. Must be one of {allowed_outcomes}")
        if label_source not in _SOURCE_CONFIDENCE:
            raise ValueError(f"Unknown label_source '{label_source}'")

        binary = LeadOutcome.derive_binary(outcome)
        confidence = _SOURCE_CONFIDENCE[label_source]

        existing = LeadOutcome.query.filter_by(lead_id=lead_id).first()
        if existing:
            existing_confidence = _SOURCE_CONFIDENCE.get(existing.label_source, 0.0)
            if confidence < existing_confidence:
                logger.debug(
                    f"[DatasetManager] Keeping existing outcome for lead {lead_id} "
                    f"({existing.label_source} > {label_source})"
                )
                return existing
            # Upgrade the existing record
            existing.outcome          = outcome
            existing.label_source     = label_source
            existing.label_confidence = confidence
            existing.binary_label     = binary
            existing.ml_score_at_time   = ml_score
            existing.rule_score_at_time = rule_score
            existing.llm_score_at_time  = llm_score
            existing.scoring_method     = scoring_method
            existing.feedback_notes     = feedback_notes
            existing.recorded_by        = recorded_by
            existing.updated_at         = datetime.now(timezone.utc)
            return existing

        outcome_obj = LeadOutcome(
            lead_id           = lead_id,
            outcome           = outcome,
            label_source      = label_source,
            label_confidence  = confidence,
            binary_label      = binary,
            ml_score_at_time  = ml_score,
            rule_score_at_time= rule_score,
            llm_score_at_time = llm_score,
            scoring_method    = scoring_method,
            feedback_notes    = feedback_notes,
            recorded_by       = recorded_by,
        )
        db.session.add(outcome_obj)
        return outcome_obj

    def get_dataset_stats(self) -> Dict[str, Any]:
        """Return a summary of current labeled data for the dashboard."""
        from app.models.models import LeadOutcome, DatasetVersion, Lead

        try:
            total_leads    = Lead.query.count()
            total_outcomes = LeadOutcome.query.count()
            pos_count      = LeadOutcome.query.filter_by(binary_label=1).count()
            neg_count      = LeadOutcome.query.filter_by(binary_label=0).count()
            soft_count     = LeadOutcome.query.filter_by(binary_label=None).count()

            by_source: Dict[str, int] = {}
            for src in _SOURCE_CONFIDENCE:
                by_source[src] = LeadOutcome.query.filter_by(label_source=src).count()

            by_outcome: Dict[str, int] = {}
            for out in ('converted', 'contacted', 'rejected', 'unqualified', 'cold', 'warm', 'hot'):
                by_outcome[out] = LeadOutcome.query.filter_by(outcome=out).count()

            latest_version = (DatasetVersion.query
                              .order_by(DatasetVersion.created_at.desc())
                              .first())

            return {
                'total_leads':            total_leads,
                'labeled_leads':          total_outcomes,
                'unlabeled_leads':        total_leads - total_outcomes,
                'positive_labels':        pos_count,
                'negative_labels':        neg_count,
                'soft_labels':            soft_count,
                'label_sources':          by_source,
                'outcome_distribution':   by_outcome,
                'ready_for_training':     total_outcomes >= 30,
                'recommended_retrain':    total_outcomes >= 50,
                'latest_dataset_version': latest_version.to_dict() if latest_version else None,
            }
        except Exception as exc:
            logger.error(f"[DatasetManager] get_dataset_stats error: {exc}")
            return {'error': str(exc)}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_real_labeled_leads(
        self,
        min_confidence: float,
        include_soft: bool,
    ) -> List[Dict[str, Any]]:
        """
        Join leads + lead_outcomes; apply 3-tier labeling priority.

        Only leads with a LeadOutcome row and binary_label set (or soft-included)
        are returned.  Each dict gets:
            _label         : int (0 or 1)
            _label_source  : str
            _label_confidence : float
            _is_synthetic  : False
        """
        from app.models.models import Lead, LeadOutcome

        try:
            rows = (
                Lead.query
                .join(LeadOutcome, Lead.id == LeadOutcome.lead_id)
                .add_columns(
                    LeadOutcome.outcome,
                    LeadOutcome.label_source,
                    LeadOutcome.label_confidence,
                    LeadOutcome.binary_label,
                    LeadOutcome.ml_score_at_time,
                    LeadOutcome.rule_score_at_time,
                    LeadOutcome.llm_score_at_time,
                )
                .filter(
                    LeadOutcome.label_confidence >= min_confidence,
                    LeadOutcome.approval_status == 'approved',
                    ~Lead.email_type.like('generated%'),
                )
                .all()
            )
        except Exception as exc:
            logger.warning(f"[DatasetManager] DB query failed: {exc} — returning empty")
            return []

        results = []
        for row in rows:
            lead, outcome, src, conf, binary, ml_s, rule_s, llm_s = row

            if binary is None:
                if not include_soft:
                    continue
                binary = 1   # treat 'warm' as soft positive

            lead_dict = {
                'id':                lead.id,
                'name':              lead.name or '',
                'email':             lead.email or '',
                'phone':             lead.phone or '',
                'company':           lead.company or '',
                'position':          lead.position or '',
                'industry':          lead.industry or '',
                'country':           lead.country or '',
                'city':              lead.city or '',
                'website':           lead.website or '',
                'linkedin_url':      lead.linkedin_url or '',
                'interests':         lead.interests or [],
                'notes':             lead.notes or '',
                'source':            lead.source or '',
                'qualification_score': lead.qualification_score or 0.0,
                'completeness_score':  lead.completeness_score or 0.0,
                'email_type':        lead.email_type or '',
                # Training metadata
                '_label':            binary,
                '_label_source':     src,
                '_label_confidence': conf,
                '_outcome':          outcome,
                '_ml_score':         ml_s,
                '_rule_score':       rule_s,
                '_llm_score':        llm_s,
                '_is_synthetic':     False,
            }
            results.append(lead_dict)

        return results

    def _load_synthetic_leads(self, n: int) -> List[Dict[str, Any]]:
        """
        Load (or generate) synthetic leads, mark them _is_synthetic=True,
        and return exactly n of them (or all if fewer available).
        """
        if n <= 0:
            return []

        leads: List[Dict[str, Any]] = []

        if SYNTHETIC_CACHE.exists():
            try:
                with open(SYNTHETIC_CACHE) as fh:
                    leads = json.load(fh)
                logger.debug(f"[DatasetManager] Loaded {len(leads)} synthetic leads from cache")
            except Exception as exc:
                logger.warning(f"[DatasetManager] Failed to load synthetic cache: {exc}")

        if len(leads) < n:
            try:
                from app.services.data_generator import get_generator
                gen   = get_generator()
                leads = gen.generate(n=max(n, 5_000))
                SYNTHETIC_CACHE.parent.mkdir(parents=True, exist_ok=True)
                with open(SYNTHETIC_CACHE, 'w') as fh:
                    json.dump(leads, fh)
                logger.info(f"[DatasetManager] Generated {len(leads)} synthetic leads")
            except Exception as exc:
                logger.error(f"[DatasetManager] Synthetic generation failed: {exc}")
                return []

        # Shuffle to avoid ordering bias, then take n
        np.random.shuffle(leads)
        selected = leads[:n]

        # Tag each as synthetic and ensure _label/_label_source are set
        for lead in selected:
            lead['_is_synthetic']   = True
            lead['_label_source']   = 'synthetic'
            lead['_label_confidence'] = 0.5
            if '_label' not in lead:
                score = lead.get('qualification_score', 50)
                lead['_label'] = 1 if score >= 60 else 0

        return selected

    def _compute_synthetic_needed(
        self,
        n_real: int,
        pos_real: int,
        neg_real: int,
        max_ratio: float,
        force_n: Optional[int],
    ) -> int:
        """Compute how many synthetic leads to blend in."""
        if force_n is not None:
            return force_n

        if n_real == 0:
            return 2_000

        # How many synthetic positives do we need to reach TARGET_POSITIVE_RATE?
        # target = (pos_real + synth_pos) / (n_real + n_synth)
        # Assume synthetic generator produces ~35% positives
        synth_pos_rate = 0.35
        target = TARGET_POSITIVE_RATE

        # Solve for n_synth:  (pos_real + n_synth*0.35) / (n_real + n_synth) = target
        # → n_synth = (target*n_real - pos_real) / (synth_pos_rate - target)
        denom = synth_pos_rate - target
        if denom <= 0:
            n_synth = max(0, MIN_REAL_LEADS - n_real)
        else:
            n_synth = int((target * n_real - pos_real) / denom)
            n_synth = max(n_synth, 0)

        # Respect max_ratio cap
        max_synth = int(n_real * max_ratio / (1 - max_ratio))
        n_synth = min(n_synth, max_synth)

        # Always add at least some synthetic data if we're below MIN_REAL_LEADS
        if n_real < MIN_REAL_LEADS:
            n_synth = max(n_synth, MIN_REAL_LEADS * 10)

        return n_synth

    def _resolve_balance_method(
        self,
        method: str,
        leads: List[Dict[str, Any]],
    ) -> str:
        """Resolve 'auto' to a concrete method based on data characteristics."""
        if method != 'auto':
            return method

        n_pos = sum(1 for l in leads if l.get('_label') == 1)
        n_neg = len(leads) - n_pos
        if n_pos == 0 or n_neg == 0:
            return 'none'

        ratio = min(n_pos, n_neg) / max(n_pos, n_neg)
        if ratio >= 0.40:
            return 'none'    # already balanced enough

        try:
            import importlib
            importlib.import_module('imblearn')
            return 'smote'
        except ImportError:
            return 'weighted'

    def _balance_dataset(
        self,
        leads: List[Dict[str, Any]],
        method: str,
    ) -> List[Dict[str, Any]]:
        """
        Balance positive / negative classes.

        'smote'    — SMOTE on feature vectors (requires imbalanced-learn)
        'weighted' — Return leads as-is; XGBoost scale_pos_weight handles it
        'none'     — No balancing

        Note: SMOTE generates NEW synthetic feature rows without lead-level metadata.
        These rows are marked _is_synthetic=True and _label_source='smote'.
        """
        if method == 'none' or method == 'weighted':
            return leads

        if method != 'smote':
            logger.warning(f"[DatasetManager] Unknown balance method '{method}', using 'none'")
            return leads

        try:
            from imblearn.over_sampling import SMOTE
            from app.services.ml_model import extract_features, N_FEATURES

            X_rows, y_rows, meta_rows = [], [], []
            for lead in leads:
                lbl = lead.get('_label')
                if lbl is None:
                    continue
                feat = extract_features(lead).flatten()
                X_rows.append(feat)
                y_rows.append(int(lbl))
                meta_rows.append(lead)

            if not X_rows:
                return leads

            X = np.array(X_rows, dtype=np.float32)
            y = np.array(y_rows, dtype=np.int32)

            n_pos = int(y.sum())
            n_neg = len(y) - n_pos
            if n_pos < 2 or n_neg < 2:
                logger.warning("[DatasetManager] Too few samples for SMOTE, skipping")
                return leads

            # Target: minority class gets upsampled to 40% of dataset
            n_min  = min(n_pos, n_neg)
            n_maj  = max(n_pos, n_neg)
            target = int(n_maj * (TARGET_POSITIVE_RATE / (1 - TARGET_POSITIVE_RATE)))
            target = max(target, n_min)

            k_neighbors = min(5, n_min - 1)
            if k_neighbors < 1:
                return leads

            smote = SMOTE(
                sampling_strategy={1: target} if n_pos < n_neg else {0: target},
                k_neighbors=k_neighbors,
                random_state=42,
            )
            X_res, y_res = smote.fit_resample(X, y)

            # Reconstruct lead list: original leads first, then SMOTE-generated rows
            n_original = len(leads)
            result_leads = list(leads)  # copy originals

            for i in range(n_original, len(X_res)):
                label = int(y_res[i])
                synth_lead = {
                    '_label':           label,
                    '_label_source':    'smote',
                    '_label_confidence': 0.5,
                    '_is_synthetic':    True,
                    # Store features back as a special key (used by train pipeline)
                    '_smote_features':  X_res[i].tolist(),
                }
                result_leads.append(synth_lead)

            n_added = len(result_leads) - n_original
            logger.info(f"[DatasetManager] SMOTE added {n_added} synthetic samples")
            return result_leads

        except ImportError:
            logger.warning("[DatasetManager] imbalanced-learn not installed, skipping SMOTE")
            return leads
        except Exception as exc:
            logger.error(f"[DatasetManager] SMOTE failed: {exc}, using original data")
            return leads

    def _count_label_sources(self, leads: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for lead in leads:
            src = lead.get('_label_source', 'unknown')
            counts[src] = counts.get(src, 0) + 1
        return counts

    def _hash_dataset(self, leads: List[Dict[str, Any]]) -> str:
        """SHA-256 of sorted lead IDs + labels — fast, stable identity check."""
        items = sorted(
            (str(l.get('id', l.get('_label_source', ''))), str(l.get('_label', '')))
            for l in leads
        )
        raw = json.dumps(items, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()


# ─── Module-level singleton ───────────────────────────────────────────────────

_manager: Optional[DatasetManager] = None


def get_dataset_manager() -> DatasetManager:
    global _manager
    if _manager is None:
        _manager = DatasetManager()
    return _manager
