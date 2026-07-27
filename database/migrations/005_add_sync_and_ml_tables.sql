-- Migration 005: Add sync fields, ML/outcome tables, and new system tables
-- Brings the schema up to date with app/models/models.py as of May 2026.
-- Applied after: 004_add_lead_type.sql
--
-- Compatible with MySQL 5.7+ and MySQL 8.x.
-- Each ALTER TABLE is wrapped in a stored procedure that checks
-- information_schema first, so the script is safe to re-run.
--
-- Sections:
--   1. users        — uuid, api_key, source, sync_status, version
--   2. leads        — uuid, origin, completeness_score, email_type,
--                     spam_override, interest/buying-intent fields,
--                     sync_status, version, last_synced_at
--   3. data_sources — api_key_masked, enabled, sync_frequency, records_count,
--                     performance, last_error, updated_at; rename last_crawled→last_sync
--   4. seen_contacts        (new)
--   5. sync_logs            (new)
--   6. lead_outcomes        (new)
--   7. dataset_versions     (new)
--   8. user_settings        (new)
--   9. admin_api_keys       (new)

USE ai_lead_db;

-- ─────────────────────────────────────────────────────────────────────────────
-- Helper: add a column only if it doesn't exist yet
-- ─────────────────────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS _add_col;
DELIMITER $$
CREATE PROCEDURE _add_col(
    IN p_table  VARCHAR(64),
    IN p_col    VARCHAR(64),
    IN p_defn   TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = p_table
          AND COLUMN_NAME  = p_col
    ) THEN
        SET @sql = CONCAT('ALTER TABLE `', p_table, '` ADD COLUMN `', p_col, '` ', p_defn);
        PREPARE s FROM @sql;
        EXECUTE s;
        DEALLOCATE PREPARE s;
    END IF;
END $$
DELIMITER ;

-- Helper: create an index only if it doesn't exist yet
DROP PROCEDURE IF EXISTS _add_idx;
DELIMITER $$
CREATE PROCEDURE _add_idx(
    IN p_table  VARCHAR(64),
    IN p_index  VARCHAR(64),
    IN p_cols   VARCHAR(255),
    IN p_unique TINYINT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = p_table
          AND INDEX_NAME   = p_index
    ) THEN
        IF p_unique THEN
            SET @sql = CONCAT('CREATE UNIQUE INDEX `', p_index, '` ON `', p_table, '` (', p_cols, ')');
        ELSE
            SET @sql = CONCAT('CREATE INDEX `', p_index, '` ON `', p_table, '` (', p_cols, ')');
        END IF;
        PREPARE s FROM @sql;
        EXECUTE s;
        DEALLOCATE PREPARE s;
    END IF;
END $$
DELIMITER ;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. users — uuid, api_key, source, sync_status, version
-- ─────────────────────────────────────────────────────────────────────────────
CALL _add_col('users', 'uuid',        'VARCHAR(36) NULL AFTER `id`');
CALL _add_col('users', 'api_key',     'VARCHAR(64) NULL AFTER `is_active`');
CALL _add_col('users', 'source',      "VARCHAR(20) NOT NULL DEFAULT 'web' AFTER `api_key`");
CALL _add_col('users', 'sync_status', "VARCHAR(20) NOT NULL DEFAULT 'pending' AFTER `source`");
CALL _add_col('users', 'version',     'INT NOT NULL DEFAULT 1 AFTER `sync_status`');

-- Backfill uuid for pre-existing rows then enforce NOT NULL
UPDATE users SET uuid = UUID() WHERE uuid IS NULL;
ALTER TABLE users MODIFY COLUMN uuid VARCHAR(36) NOT NULL;

CALL _add_idx('users', 'idx_users_uuid',    'uuid',    1);
CALL _add_idx('users', 'idx_users_api_key', 'api_key', 1);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. leads
-- ─────────────────────────────────────────────────────────────────────────────
CALL _add_col('leads', 'uuid',               'VARCHAR(36) NULL AFTER `id`');
CALL _add_col('leads', 'completeness_score', 'FLOAT NOT NULL DEFAULT 0.0 AFTER `qualification_score`');
CALL _add_col('leads', 'email_type',         'VARCHAR(30) NULL AFTER `completeness_score`');
CALL _add_col('leads', 'origin',             "VARCHAR(20) NOT NULL DEFAULT 'web' AFTER `lead_type`");
CALL _add_col('leads', 'spam_override',      'TINYINT(1) NOT NULL DEFAULT 0 AFTER `notes`');
-- Buying-intent fields (category-based collection engine)
CALL _add_col('leads', 'interest_category',  'VARCHAR(100) NULL AFTER `spam_override`');
CALL _add_col('leads', 'product_interest',   'VARCHAR(500) NULL AFTER `interest_category`');
CALL _add_col('leads', 'buying_intent',      'VARCHAR(20)  NULL AFTER `product_interest`');
CALL _add_col('leads', 'intent_confidence',  'FLOAT        NULL AFTER `buying_intent`');
CALL _add_col('leads', 'intent_source',      'VARCHAR(100) NULL AFTER `intent_confidence`');
CALL _add_col('leads', 'intent_reason',      'VARCHAR(500) NULL AFTER `intent_source`');
-- Sync fields
CALL _add_col('leads', 'sync_status',        "VARCHAR(20) NOT NULL DEFAULT 'pending' AFTER `intent_reason`");
CALL _add_col('leads', 'version',            'INT NOT NULL DEFAULT 1 AFTER `sync_status`');
CALL _add_col('leads', 'last_synced_at',     'DATETIME NULL AFTER `version`');

UPDATE leads SET uuid = UUID() WHERE uuid IS NULL;
ALTER TABLE leads MODIFY COLUMN uuid VARCHAR(36) NOT NULL;

CALL _add_idx('leads', 'idx_leads_uuid',               'uuid',              1);
CALL _add_idx('leads', 'idx_leads_interest_category',  'interest_category', 0);
CALL _add_idx('leads', 'idx_leads_buying_intent',      'buying_intent',     0);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. data_sources
-- ─────────────────────────────────────────────────────────────────────────────
CALL _add_col('data_sources', 'api_key_masked', 'VARCHAR(255) NULL AFTER `url`');
CALL _add_col('data_sources', 'enabled',        'TINYINT(1) NOT NULL DEFAULT 1 AFTER `api_key_masked`');
CALL _add_col('data_sources', 'sync_frequency', "VARCHAR(20) NOT NULL DEFAULT 'manual' AFTER `enabled`");
CALL _add_col('data_sources', 'records_count',  'INT NOT NULL DEFAULT 0 AFTER `sync_frequency`');
CALL _add_col('data_sources', 'performance',    'FLOAT NOT NULL DEFAULT 0.0 AFTER `records_count`');
CALL _add_col('data_sources', 'last_error',     'TEXT NULL AFTER `performance`');
CALL _add_col('data_sources', 'updated_at',     'DATETIME NULL ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`');

-- Rename last_crawled → last_sync
DROP PROCEDURE IF EXISTS _m005_rename_last_crawled;
DELIMITER $$
CREATE PROCEDURE _m005_rename_last_crawled()
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = 'data_sources'
          AND COLUMN_NAME  = 'last_crawled'
    ) THEN
        ALTER TABLE data_sources CHANGE COLUMN last_crawled last_sync DATETIME NULL;
    END IF;
    -- Ensure last_sync exists even if last_crawled was never present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = 'data_sources'
          AND COLUMN_NAME  = 'last_sync'
    ) THEN
        ALTER TABLE data_sources ADD COLUMN last_sync DATETIME NULL AFTER `enabled`;
    END IF;
END $$
DELIMITER ;
CALL _m005_rename_last_crawled();
DROP PROCEDURE IF EXISTS _m005_rename_last_crawled;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. seen_contacts  (new)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS seen_contacts (
    id               INT PRIMARY KEY AUTO_INCREMENT,
    normalized_email VARCHAR(255) NULL,
    normalized_phone VARCHAR(50)  NULL,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_seen_contact_email_phone (normalized_email, normalized_phone),
    INDEX idx_seen_contacts_email (normalized_email),
    INDEX idx_seen_contacts_phone (normalized_phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. sync_logs  (new)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_logs (
    id           INT PRIMARY KEY AUTO_INCREMENT,
    operation    VARCHAR(50)  NOT NULL,
    direction    VARCHAR(30)  NOT NULL,
    records      INT          NOT NULL DEFAULT 0,
    status       VARCHAR(20)  NOT NULL DEFAULT 'success',
    error_msg    TEXT         NULL,
    triggered_by VARCHAR(120) NULL,
    duration_ms  INT          NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sync_logs_operation  (operation),
    INDEX idx_sync_logs_status     (status),
    INDEX idx_sync_logs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. lead_outcomes  (new)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lead_outcomes (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    lead_id             INT         NOT NULL,
    outcome             VARCHAR(30) NOT NULL,
    label_source        VARCHAR(30) NOT NULL,
    label_confidence    FLOAT       NOT NULL DEFAULT 1.0,
    binary_label        INT         NULL,
    ml_score_at_time    FLOAT       NULL,
    rule_score_at_time  FLOAT       NULL,
    llm_score_at_time   FLOAT       NULL,
    scoring_method      VARCHAR(30) NULL,
    feedback_notes      TEXT        NULL,
    recorded_by         INT         NULL,
    recorded_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_lead_outcome_lead_id (lead_id),
    CONSTRAINT fk_lead_outcomes_lead FOREIGN KEY (lead_id)     REFERENCES leads(id) ON DELETE CASCADE,
    CONSTRAINT fk_lead_outcomes_user FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_lead_outcomes_lead_id     (lead_id),
    INDEX idx_lead_outcomes_binary      (binary_label),
    INDEX idx_lead_outcomes_recorded_at (recorded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. dataset_versions  (new)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dataset_versions (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    version_tag     VARCHAR(50)  NOT NULL,
    data_hash       VARCHAR(64)  NOT NULL,
    n_total         INT          NOT NULL,
    n_real          INT          NOT NULL,
    n_synthetic     INT          NOT NULL,
    n_positive      INT          NOT NULL,
    n_negative      INT          NOT NULL,
    positive_rate   FLOAT        NOT NULL,
    label_sources   JSON         NULL,
    balance_method  VARCHAR(30)  NULL,
    snapshot_path   VARCHAR(500) NULL,
    train_auc       FLOAT        NULL,
    train_accuracy  FLOAT        NULL,
    train_precision FLOAT        NULL,
    train_recall    FLOAT        NULL,
    train_f1        FLOAT        NULL,
    cv_auc_mean     FLOAT        NULL,
    cv_auc_std      FLOAT        NULL,
    is_active       TINYINT(1)   NOT NULL DEFAULT 0,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY idx_dataset_versions_tag (version_tag),
    INDEX idx_dataset_versions_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─────────────────────────────────────────────────────────────────────────────
-- 8. user_settings  (new)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
    id         INT PRIMARY KEY AUTO_INCREMENT,
    user_id    INT          NOT NULL,
    `key`      VARCHAR(100) NOT NULL,
    value      TEXT         NULL,
    updated_at DATETIME     NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_setting (user_id, `key`),
    CONSTRAINT fk_user_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_settings_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─────────────────────────────────────────────────────────────────────────────
-- 9. admin_api_keys  (new)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_api_keys (
    id           INT PRIMARY KEY AUTO_INCREMENT,
    name         VARCHAR(255) NOT NULL,
    `key`        VARCHAR(80)  NOT NULL,
    key_masked   VARCHAR(30)  NOT NULL,
    created_by   INT          NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at DATETIME     NULL,
    UNIQUE KEY idx_admin_api_keys_key (`key`),
    CONSTRAINT fk_admin_api_keys_user FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_admin_api_keys_created_by (created_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─────────────────────────────────────────────────────────────────────────────
-- Cleanup helpers
-- ─────────────────────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS _add_col;
DROP PROCEDURE IF EXISTS _add_idx;
