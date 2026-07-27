from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event as _sa_event
import uuid as _uuid


def _now():
    return datetime.now(timezone.utc)

db = SQLAlchemy()


def _gen_uuid():
    return str(_uuid.uuid4())


class User(db.Model):
    """User model for authentication"""
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    uuid          = db.Column(db.String(36), unique=True, nullable=False, default=_gen_uuid, index=True)
    email         = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name     = db.Column(db.String(255))
    company       = db.Column(db.String(255))
    role          = db.Column(db.String(50), default='user')
    is_active     = db.Column(db.Boolean, default=True)
    approved_at   = db.Column(db.DateTime, nullable=True)  # set once, first time an admin/sub_admin activates the account
    api_key       = db.Column(db.String(64), unique=True, nullable=True, index=True)

    # ── Email verification ────────────────────────────────────────────────────
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    otp_code       = db.Column(db.String(10),  nullable=True)
    otp_expires_at = db.Column(db.DateTime,    nullable=True)
    otp_attempts   = db.Column(db.Integer,     default=0, nullable=False)

    # ── Profile photo ────────────────────────────────────────────────────────
    profile_photo = db.Column(db.String(255), nullable=True)

    # ── Sync fields ──────────────────────────────────────────────────────────
    source        = db.Column(db.String(20), default='web')       # 'web' | 'mobile'
    sync_status   = db.Column(db.String(20), default='pending')   # 'pending' | 'synced' | 'failed'
    version       = db.Column(db.Integer, default=1, nullable=False)

    created_at    = db.Column(db.DateTime, default=_now)
    updated_at    = db.Column(db.DateTime, default=_now, onupdate=_now)

    def __repr__(self):
        return f'<User {self.email}>'

    def bump_version(self):
        """Increment optimistic-lock version on every write."""
        self.version = (self.version or 0) + 1
        self.updated_at = _now()


class Lead(db.Model):
    """Lead model for storing collected leads"""
    __tablename__ = 'leads'

    id                  = db.Column(db.Integer, primary_key=True)
    uuid                = db.Column(db.String(36), unique=True, nullable=False, default=_gen_uuid, index=True)
    name                = db.Column(db.String(255), nullable=False)
    email               = db.Column(db.String(120), nullable=True, index=True)
    phone               = db.Column(db.String(20), nullable=True)
    company             = db.Column(db.String(255), nullable=True)
    position            = db.Column(db.String(255), nullable=True)
    location            = db.Column(db.String(255), nullable=True, index=True)
    country             = db.Column(db.String(100), nullable=True, index=True)
    city                = db.Column(db.String(255), nullable=True)
    industry            = db.Column(db.String(255), nullable=True, index=True)
    website             = db.Column(db.String(500), nullable=True)
    linkedin_url        = db.Column(db.String(500), nullable=True)
    interests           = db.Column(db.JSON, nullable=True)
    product             = db.Column(db.String(255), nullable=True)
    qualification_score = db.Column(db.Float, default=0.0)
    completeness_score  = db.Column(db.Float, default=0.0)             # 0–100 field-completeness score
    email_type          = db.Column(db.String(30), nullable=True)      # 'personal'|'company'|'generic'|'free'|'generated_personal'|'generated_generic'
    status              = db.Column(db.String(50), default='pending')
    source              = db.Column(db.String(100), nullable=True)
    origin              = db.Column(db.String(20), default='web')      # 'web' | 'mobile'  — which DB created it
    lead_type           = db.Column(db.String(50), nullable=True)
    data_points         = db.Column(db.JSON, nullable=True)
    notes               = db.Column(db.Text, nullable=True)
    spam_override       = db.Column(db.Boolean, default=False, nullable=False)

    # ── Interest / buying-intent fields (category-based collection) ───────────
    interest_category   = db.Column(db.String(100), nullable=True, index=True)  # e.g. 'Laptops'
    product_interest    = db.Column(db.String(500), nullable=True)               # matched keywords
    buying_intent       = db.Column(db.String(20),  nullable=True)               # high/medium/low/none
    intent_confidence   = db.Column(db.Float,        nullable=True)              # 0.0–1.0
    intent_source       = db.Column(db.String(100),  nullable=True)              # which query/source
    intent_reason       = db.Column(db.String(500),  nullable=True)              # human-readable why

    # ── Ownership ─────────────────────────────────────────────────────────────
    collected_by  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    assigned_to   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    # ── Sync fields ──────────────────────────────────────────────────────────
    sync_status   = db.Column(db.String(20), default='pending')    # 'pending' | 'synced' | 'failed'
    version       = db.Column(db.Integer, default=1, nullable=False)
    last_synced_at= db.Column(db.DateTime, nullable=True)

    created_at    = db.Column(db.DateTime, default=_now, index=True)
    updated_at    = db.Column(db.DateTime, default=_now, onupdate=_now)

    def __repr__(self):
        return f'<Lead {self.name}>'

    def bump_version(self):
        self.version = (self.version or 0) + 1
        self.updated_at = _now()

    def mark_synced(self):
        self.sync_status = 'synced'
        self.last_synced_at = _now()

    def mark_pending(self):
        self.sync_status = 'pending'


@_sa_event.listens_for(Lead, 'before_insert')
def _stamp_collected_by(mapper, connection, target):
    """Auto-stamp collected_by from the current request's user_id."""
    if target.collected_by is None:
        try:
            from flask import g as _g
            uid = getattr(_g, 'user_id', None)
            if uid:
                target.collected_by = uid
        except RuntimeError:
            pass  # No request context (migrations, tests, CLI)


class LeadActivity(db.Model):
    """Track activities and interactions with leads"""
    __tablename__ = 'lead_activities'

    id            = db.Column(db.Integer, primary_key=True)
    lead_id       = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=False)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    activity_type = db.Column(db.String(100), nullable=False)
    notes         = db.Column(db.Text, nullable=True)
    created_at    = db.Column(db.DateTime, default=_now)

    def __repr__(self):
        return f'<LeadActivity {self.activity_type}>'


class DataSource(db.Model):
    """
    Persistent data source — API endpoint, CSV file, or external database.
    Real sync results are stored here; nothing is mocked.
    """
    __tablename__ = 'data_sources'

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), unique=True, nullable=False)
    # source_type: 'API' | 'CSV' | 'Database' | 'Web'
    source_type     = db.Column('type', db.String(50), nullable=False, default='API')
    url             = db.Column(db.String(500), nullable=True)      # endpoint / file path / connection string
    api_key_masked  = db.Column(db.String(255), nullable=True)      # stored masked: sk_***_XXXX
    enabled         = db.Column(db.Boolean, default=True, nullable=False)
    sync_frequency  = db.Column(db.String(20), default='manual')    # 'manual'|'hourly'|'daily'|'weekly'
    records_count   = db.Column(db.Integer, default=0)              # total leads ever imported from this source
    last_sync       = db.Column(db.DateTime, nullable=True)         # when last successful sync ran
    performance     = db.Column(db.Float, default=0.0)             # 0-100 success rate of last sync
    status          = db.Column(db.String(50), default='active')    # 'active'|'error'|'disabled'
    last_error      = db.Column(db.Text, nullable=True)             # last sync error message
    # Extra config stored as JSON: file_path, query, headers, field_map, etc.
    config          = db.Column(db.JSON, nullable=True)
    created_at      = db.Column(db.DateTime, default=_now)
    updated_at      = db.Column(db.DateTime, default=_now, onupdate=_now)

    def to_dict(self):
        return {
            'id':             self.id,
            'name':           self.name,
            'type':           self.source_type,
            'url':            self.url or '',
            'api_key':        self.api_key_masked or '',
            'enabled':        self.enabled,
            'sync_frequency': self.sync_frequency,
            'records':        self.records_count,
            'last_sync':      self.last_sync.isoformat() if self.last_sync else None,
            'performance':    self.performance,
            'status':         self.status,
            'last_error':     self.last_error,
            'config':         self.config or {},
            'created_at':     self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<DataSource {self.name}>'


class ClassificationCategory(db.Model):
    """Classification categories for interests"""
    __tablename__ = 'classification_categories'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    keywords    = db.Column(db.JSON, nullable=True)
    created_at  = db.Column(db.DateTime, default=_now)

    def __repr__(self):
        return f'<ClassificationCategory {self.name}>'


class SeenContact(db.Model):
    """
    Tracks normalised contact info from every lead that passes spam/dup checks.
    Used by DuplicateDetector to flag re-submissions.

    Replaces: backend/data/seen_contacts.json
    Safe under concurrent workers — duplicate inserts are caught via the
    unique constraint and silently rolled back.
    """
    __tablename__ = 'seen_contacts'

    id               = db.Column(db.Integer, primary_key=True)
    normalized_email = db.Column(db.String(255), nullable=True, index=True)
    normalized_phone = db.Column(db.String(50),  nullable=True, index=True)
    created_at       = db.Column(db.DateTime, default=_now)

    __table_args__ = (
        db.UniqueConstraint(
            'normalized_email', 'normalized_phone',
            name='uq_seen_contact_email_phone',
        ),
    )

    def __repr__(self):
        return f'<SeenContact email={self.normalized_email} phone={self.normalized_phone}>'


class SyncLog(db.Model):
    """Log every sync operation for auditing and debugging."""
    __tablename__ = 'sync_logs'

    id           = db.Column(db.Integer, primary_key=True)
    operation    = db.Column(db.String(50), nullable=False)   # 'web_to_mobile' | 'mobile_to_web' | 'user_sync'
    direction    = db.Column(db.String(30), nullable=False)   # 'mysql_to_supabase' | 'supabase_to_mysql'
    records      = db.Column(db.Integer, default=0)
    status       = db.Column(db.String(20), default='success')  # 'success' | 'partial' | 'failed'
    error_msg    = db.Column(db.Text, nullable=True)
    triggered_by = db.Column(db.String(120), nullable=True)   # user email or 'webhook'
    duration_ms  = db.Column(db.Integer, nullable=True)
    created_at   = db.Column(db.DateTime, default=_now)

    def __repr__(self):
        return f'<SyncLog {self.operation} {self.status}>'


# ─────────────────────────────────────────────────────────────────────────────
# ML / Data-Strategy models
# ─────────────────────────────────────────────────────────────────────────────

class LeadOutcome(db.Model):
    """
    Ground-truth outcome label for a lead — the real signal used to retrain ML.

    Label priority (highest confidence wins):
        business_outcome  (converted / rejected)        confidence ≈ 1.0
        user_feedback     (contacted / unqualified)     confidence ≈ 0.8
        ai_prediction     (hot / warm / cold)           confidence ≈ 0.6

    Binary ML label:
        converted, contacted → 1  (positive)
        rejected, unqualified, cold → 0  (negative)
        warm → 0.5 (soft label — excluded from hard binary training by default)

    Outcome values:
        'converted'    — lead became a customer
        'contacted'    — lead was reached and responded positively
        'rejected'     — lead explicitly declined / bad fit
        'unqualified'  — sales team marked as not a fit
        'cold'         — no response after outreach (AI-predicted cold)
        'warm'         — responded but not yet converted (AI-predicted warm)
        'hot'          — strong buying signals (AI-predicted hot)
    """
    __tablename__ = 'lead_outcomes'

    id                 = db.Column(db.Integer, primary_key=True)
    lead_id            = db.Column(db.Integer, db.ForeignKey('leads.id', ondelete='CASCADE'),
                                   nullable=False, index=True)

    # Ground truth
    outcome            = db.Column(db.String(30), nullable=False)
    # Source of this label
    label_source       = db.Column(db.String(30), nullable=False)
    # 0.0–1.0: how confident we are this label is correct
    label_confidence   = db.Column(db.Float, default=1.0, nullable=False)
    # Derived hard binary for training: 1=positive, 0=negative, None=soft/excluded
    binary_label       = db.Column(db.Integer, nullable=True, index=True)

    # Snapshot of AI scores at time of scoring (for model performance tracking)
    ml_score_at_time   = db.Column(db.Float, nullable=True)
    rule_score_at_time = db.Column(db.Float, nullable=True)
    llm_score_at_time  = db.Column(db.Float, nullable=True)
    scoring_method     = db.Column(db.String(30), nullable=True)

    # Free-text reason from user (optional)
    feedback_notes     = db.Column(db.Text, nullable=True)
    # User who recorded this outcome (nullable = automated/AI)
    recorded_by        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    recorded_at        = db.Column(db.DateTime, default=_now, index=True)
    updated_at         = db.Column(db.DateTime, default=_now, onupdate=_now)

    # ── Approval workflow ─────────────────────────────────────────────────────
    # pending  → submitted by user, awaiting manager review
    # approved → manager confirmed label; counts toward ML training
    # rejected → manager rejected label; excluded from training
    approval_status    = db.Column(db.String(20), nullable=False, default='approved', index=True)
    approved_by        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at        = db.Column(db.DateTime, nullable=True)
    approval_note      = db.Column(db.Text, nullable=True)

    # Only one outcome per lead (latest wins via upsert logic in service layer)
    __table_args__ = (
        db.UniqueConstraint('lead_id', name='uq_lead_outcome_lead_id'),
    )

    # ── Helpers ───────────────────────────────────────────────────────────────
    _POSITIVE_OUTCOMES = frozenset({'converted', 'contacted', 'hot'})
    _NEGATIVE_OUTCOMES = frozenset({'rejected', 'unqualified', 'cold'})

    @classmethod
    def derive_binary(cls, outcome: str) -> int | None:
        """Return 1, 0, or None (soft label, excluded from hard training)."""
        if outcome in cls._POSITIVE_OUTCOMES:
            return 1
        if outcome in cls._NEGATIVE_OUTCOMES:
            return 0
        return None   # 'warm' — soft label

    def to_dict(self) -> dict:
        return {
            'id':                self.id,
            'lead_id':           self.lead_id,
            'outcome':           self.outcome,
            'label_source':      self.label_source,
            'label_confidence':  self.label_confidence,
            'binary_label':      self.binary_label,
            'ml_score_at_time':  self.ml_score_at_time,
            'rule_score_at_time':self.rule_score_at_time,
            'llm_score_at_time': self.llm_score_at_time,
            'scoring_method':    self.scoring_method,
            'feedback_notes':    self.feedback_notes,
            'approval_status':   self.approval_status,
            'approved_by':       self.approved_by,
            'approved_at':       self.approved_at.isoformat() if self.approved_at else None,
            'approval_note':     self.approval_note,
            'recorded_at':       self.recorded_at.isoformat() if self.recorded_at else None,
        }

    def __repr__(self):
        return f'<LeadOutcome lead={self.lead_id} outcome={self.outcome} src={self.label_source}>'


class DatasetVersion(db.Model):
    """
    Immutable snapshot of a training dataset.

    Every time the ML model is retrained a new DatasetVersion is created.
    The snapshot JSON is stored on disk; this record stores its metadata
    and the training metrics achieved with it.

    Versioning allows:
      - Full audit trail of what data trained each model
      - Rollback: load an old snapshot and retrain
      - Comparison: old vs new model metrics side by side
    """
    __tablename__ = 'dataset_versions'

    id               = db.Column(db.Integer, primary_key=True)
    version_tag      = db.Column(db.String(50), unique=True, nullable=False, index=True)
    # SHA-256 of the feature matrix — used to detect identical re-runs
    data_hash        = db.Column(db.String(64), nullable=False)

    # Composition
    n_total          = db.Column(db.Integer, nullable=False)
    n_real           = db.Column(db.Integer, nullable=False)
    n_synthetic      = db.Column(db.Integer, nullable=False)
    n_positive       = db.Column(db.Integer, nullable=False)
    n_negative       = db.Column(db.Integer, nullable=False)
    positive_rate    = db.Column(db.Float, nullable=False)

    # Label-source breakdown (JSON: {"business_outcome": N, "user_feedback": N, "ai_prediction": N})
    label_sources    = db.Column(db.JSON, nullable=True)

    # Balancing method applied
    balance_method   = db.Column(db.String(30), nullable=True)  # 'smote'|'weighted'|'none'

    # File path of the on-disk snapshot (relative to backend/)
    snapshot_path    = db.Column(db.String(500), nullable=True)

    # Training metrics (populated after training completes)
    train_auc        = db.Column(db.Float, nullable=True)
    train_accuracy   = db.Column(db.Float, nullable=True)
    train_precision  = db.Column(db.Float, nullable=True)
    train_recall     = db.Column(db.Float, nullable=True)
    train_f1         = db.Column(db.Float, nullable=True)
    cv_auc_mean      = db.Column(db.Float, nullable=True)
    cv_auc_std       = db.Column(db.Float, nullable=True)

    # Whether this version's model is currently live
    is_active        = db.Column(db.Boolean, default=False, nullable=False)

    created_at       = db.Column(db.DateTime, default=_now, index=True)

    def to_dict(self) -> dict:
        return {
            'id':            self.id,
            'version_tag':   self.version_tag,
            'data_hash':     self.data_hash,
            'n_total':       self.n_total,
            'n_real':        self.n_real,
            'n_synthetic':   self.n_synthetic,
            'n_positive':    self.n_positive,
            'n_negative':    self.n_negative,
            'positive_rate': round(self.positive_rate, 4),
            'label_sources': self.label_sources or {},
            'balance_method':self.balance_method,
            'snapshot_path': self.snapshot_path,
            'metrics': {
                'auc':       self.train_auc,
                'accuracy':  self.train_accuracy,
                'precision': self.train_precision,
                'recall':    self.train_recall,
                'f1':        self.train_f1,
                'cv_auc_mean': self.cv_auc_mean,
                'cv_auc_std':  self.cv_auc_std,
            },
            'is_active':     self.is_active,
            'created_at':    self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<DatasetVersion {self.version_tag} n={self.n_total} pos={self.positive_rate:.0%}>'


class UserSetting(db.Model):
    """Per-user key-value settings store (notifications, data-collection prefs, etc.)"""
    __tablename__ = 'user_settings'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    key        = db.Column(db.String(100), nullable=False)
    value      = db.Column(db.Text, nullable=True)   # JSON-serialised value
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'key', name='uq_user_setting'),
    )

    def __repr__(self):
        return f'<UserSetting user={self.user_id} key={self.key}>'


class AdminApiKey(db.Model):
    """System-level API keys generated by admins/managers for external integrations."""
    __tablename__ = 'admin_api_keys'

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(255), nullable=False)
    key          = db.Column(db.String(80), unique=True, nullable=False, index=True)
    key_masked   = db.Column(db.String(30), nullable=False)   # first 10 chars + ••••••••
    created_by   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at   = db.Column(db.DateTime, default=_now)
    last_used_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self, reveal_key=False):
        return {
            'id':           self.id,
            'name':         self.name,
            'key':          self.key if reveal_key else None,
            'key_masked':   self.key_masked,
            'created':      self.created_at.isoformat() if self.created_at else None,
            'last_used':    self.last_used_at.isoformat() if self.last_used_at else None,
        }

    def __repr__(self):
        return f'<AdminApiKey {self.name}>'


class DeviceToken(db.Model):
    """FCM device tokens for push notifications — one row per device per user."""
    __tablename__ = 'device_tokens'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    token       = db.Column(db.String(512), nullable=False, unique=True)
    platform    = db.Column(db.String(20), nullable=False, default='android')  # 'android' | 'ios' | 'web'
    app_version = db.Column(db.String(20), nullable=True)
    created_at  = db.Column(db.DateTime, default=_now)
    updated_at  = db.Column(db.DateTime, default=_now, onupdate=_now)

    user = db.relationship(
        'User',
        backref=db.backref('device_tokens', lazy='dynamic', passive_deletes=True),
    )

    def __repr__(self):
        return f'<DeviceToken user={self.user_id} platform={self.platform}>'
