#!/usr/bin/env python3
"""
Initial ML model training script.

Usage (from backend/):
    python scripts/train_initial_model.py [--n N] [--force-regen]

Workflow:
  1. Load (or generate) N synthetic B2B leads
  2. Extract 30 features per lead
  3. Train XGBoost with Optuna (10 trials)
  4. Isotonic probability calibration on 20% hold-out
  5. Evaluate: AUC-ROC, Accuracy, Precision, Recall, F1
  6. Save model to backend/models/lead_scoring_sklearn.pkl
  7. Print full evaluation report + SHAP top features

Target: hold-out AUC > 0.80
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# ── Bootstrap: add backend/ to sys.path so app imports work ──────────────────
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('train')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Train XGBoost lead scoring model')
    p.add_argument('--n',          type=int,  default=15_000,
                   help='Number of synthetic leads to generate (default 15000)')
    p.add_argument('--force-regen', action='store_true',
                   help='Re-generate synthetic data even if cached file exists')
    p.add_argument('--use-db',     action='store_true',
                   help='Build dataset from DB leads + outcomes via DatasetManager '
                        '(enables versioning, balancing, and real-label priority)')
    p.add_argument('--balance',    choices=['auto', 'smote', 'weighted', 'none'],
                   default='auto',
                   help='Class balancing method when --use-db is active (default: auto)')
    return p.parse_args()


def main() -> None:
    args = parse_args()

    dataset_version = None   # filled when --use-db is used

    if args.use_db:
        # ── 1a. Load dataset from DB via DatasetManager (versioned) ──────────
        logger.info("Building versioned training dataset from DB (DatasetManager)…")
        t0 = time.perf_counter()

        from app import create_app
        app = create_app()
        with app.app_context():
            from app.services.dataset_manager import get_dataset_manager
            from app.models.models import db

            manager = get_dataset_manager()
            result  = manager.build_training_dataset(
                balance_method=args.balance,
            )
            leads = result.leads
            dataset_version = result.version

            # Persist DatasetVersion record so metrics can be written back later
            db.session.add(dataset_version)
            db.session.commit()
            logger.info(f"DatasetVersion saved: {dataset_version.version_tag}")

        logger.info(
            f"DB dataset ready in {time.perf_counter() - t0:.1f}s  "
            f"n={result.stats['n_total']} "
            f"pos={result.stats['positive_rate']:.1%} "
            f"balance={result.stats['balance_method']}"
        )
    else:
        # ── 1b. Original path: pure synthetic data ────────────────────────────
        logger.info(f"Loading synthetic leads (n={args.n:,}, force_regen={args.force_regen})…")
        t0 = time.perf_counter()

        synth_path = _BACKEND / 'data' / 'synthetic_leads.json'
        synth_path.parent.mkdir(parents=True, exist_ok=True)

        if args.force_regen or not synth_path.exists():
            from app.services.data_generator import get_generator
            gen   = get_generator()
            leads = gen.generate(n=args.n)
            with open(synth_path, 'w') as fh:
                json.dump(leads, fh)
            logger.info(f"Generated {len(leads):,} synthetic leads → {synth_path}")
        else:
            with open(synth_path) as fh:
                leads = json.load(fh)
            logger.info(f"Loaded {len(leads):,} synthetic leads from {synth_path}")

    logger.info(f"Data ready in {time.perf_counter() - t0:.1f}s")

    # ── 2. Verify labels ──────────────────────────────────────────────────────
    n_pos = sum(1 for l in leads if l.get('_label') == 1)
    n_neg = sum(1 for l in leads if l.get('_label') == 0)
    logger.info(f"Label distribution: pos={n_pos:,} ({n_pos/len(leads)*100:.1f}%)  "
                f"neg={n_neg:,} ({n_neg/len(leads)*100:.1f}%)")

    # ── 3. Feature extraction sanity check ───────────────────────────────────
    from app.services.ml_model import extract_features, N_FEATURES, FEATURE_NAMES
    sample = leads[:5]
    for i, lead in enumerate(sample):
        feat = extract_features(lead)
        assert feat.shape == (1, N_FEATURES), \
            f"Feature shape mismatch on sample {i}: {feat.shape}"
    logger.info(f"Feature extraction OK — {N_FEATURES} features per lead")

    # ── 4. Train ──────────────────────────────────────────────────────────────
    from app.services.ml_model import XGBLeadScoringModel
    model = XGBLeadScoringModel()

    logger.info("Starting XGBoost training with Optuna hyperparameter tuning…")
    t1 = time.perf_counter()
    success = model.train_from_leads(leads)
    elapsed = time.perf_counter() - t1

    if not success:
        logger.error("Training FAILED — see logs above")
        sys.exit(1)

    logger.info(f"Training completed in {elapsed:.1f}s")

    # ── 5. Evaluation report ──────────────────────────────────────────────────
    stats = model.training_stats
    print()
    print("=" * 60)
    print("  XGBoost Lead Scoring Model — Training Report")
    print("=" * 60)
    print(f"  Model version   : {stats.get('model_version', '?')}")
    print(f"  Feature count   : {stats.get('n_features', '?')}")
    print(f"  Total samples   : {stats.get('n_samples', '?'):,}")
    print(f"    Synthetic     : {stats.get('n_synthetic', '?'):,}")
    print(f"    Real          : {stats.get('n_real', '?'):,}")
    print(f"  Positive rate   : {stats.get('positive_rate', '?')}%")
    print(f"  Best CV AUC     : {stats.get('best_cv_auc', '?'):.4f}")
    print(f"  Hold-out AUC    : {stats.get('hold_out_auc', '?'):.4f}")
    print(f"  Hold-out Acc    : {stats.get('hold_out_accuracy', '?'):.4f}")
    print()

    # Optuna best params
    best = stats.get('best_params', {})
    if best:
        print("  Best Optuna hyperparameters:")
        for k, v in best.items():
            if k not in ('use_label_encoder', 'eval_metric', 'random_state',
                         'n_jobs', 'scale_pos_weight'):
                print(f"    {k:25s}: {v}")
    print()

    # ── 6. SHAP top-feature report ────────────────────────────────────────────
    logger.info("Computing SHAP feature importance on 500-sample subset…")
    try:
        import numpy as np
        import shap

        subset = leads[:500]
        X = np.vstack([extract_features(l) for l in subset])
        inner = getattr(model.model, 'estimator', model.model)
        explainer = shap.TreeExplainer(inner)
        shap_vals = explainer.shap_values(X)
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[1]
        mean_abs = np.abs(shap_vals).mean(axis=0)
        ranked = sorted(
            zip(FEATURE_NAMES, mean_abs.tolist()),
            key=lambda x: x[1], reverse=True,
        )

        print("  SHAP feature importance (top 15):")
        for rank, (name, importance) in enumerate(ranked[:15], 1):
            bar = '█' * int(importance * 80 / ranked[0][1])
            print(f"  {rank:2}. {name:30s} {importance:.4f}  {bar}")
        print()
    except Exception as exc:
        logger.warning(f"SHAP report skipped: {exc}")

    # ── 7. Write metrics back to DatasetVersion record (if --use-db) ─────────
    if dataset_version is not None:
        try:
            from app import create_app
            app = create_app()
            with app.app_context():
                from app.models.models import db, DatasetVersion

                dv = DatasetVersion.query.filter_by(
                    version_tag=dataset_version.version_tag
                ).first()
                if dv:
                    dv.train_auc       = stats.get('hold_out_auc')
                    dv.train_accuracy  = stats.get('hold_out_accuracy')
                    dv.train_precision = stats.get('hold_out_precision')
                    dv.train_recall    = stats.get('hold_out_recall')
                    dv.train_f1        = stats.get('hold_out_f1')
                    dv.cv_auc_mean     = stats.get('best_cv_auc')
                    dv.cv_auc_std      = stats.get('cv_auc_std')
                    dv.is_active       = True

                    # Mark all previous versions as inactive
                    DatasetVersion.query.filter(
                        DatasetVersion.id != dv.id
                    ).update({'is_active': False})

                    db.session.commit()
                    logger.info(f"DatasetVersion {dv.version_tag} metrics saved to DB")
        except Exception as exc:
            logger.warning(f"Could not write metrics to DatasetVersion: {exc}")

    # ── 8. Pass / fail ────────────────────────────────────────────────────────
    auc = stats.get('hold_out_auc', 0.0)
    target = 0.80
    if auc >= target:
        print(f"  RESULT: PASS  (AUC {auc:.4f} >= {target})")
    else:
        print(f"  RESULT: WARN  (AUC {auc:.4f} < {target} — consider more data or tuning)")
    print("=" * 60)

    model_path = _BACKEND / 'models' / 'lead_scoring_sklearn.pkl'
    print(f"\n  Model saved -> {model_path}")


if __name__ == '__main__':
    main()
