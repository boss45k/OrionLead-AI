-- ============================================================
-- AI Lead Collection System — Supabase Schema (v2)
-- Full two-way sync with MySQL backend
-- Run in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ────────────────────────────────────────────────────────────
-- 1. USERS SYNC TABLE
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users_sync (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_uuid     UUID UNIQUE,                     -- matches MySQL users.uuid
  flask_user_id INTEGER UNIQUE,                  -- matches MySQL users.id
  email         TEXT UNIQUE NOT NULL,
  full_name     TEXT,
  company       TEXT,
  role          TEXT DEFAULT 'user',
  is_active     BOOLEAN DEFAULT TRUE,

  -- Sync fields
  source        TEXT DEFAULT 'web',              -- 'web' | 'mobile'
  sync_status   TEXT DEFAULT 'synced',           -- 'pending' | 'synced' | 'failed'
  version       INTEGER DEFAULT 1,

  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  synced_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_sync_email    ON users_sync(email);
CREATE INDEX IF NOT EXISTS idx_users_sync_flask_id ON users_sync(flask_user_id);
CREATE INDEX IF NOT EXISTS idx_users_sync_uuid     ON users_sync(user_uuid);


-- ────────────────────────────────────────────────────────────
-- 2. LEADS CACHE TABLE  (primary mobile DB)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads_cache (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_uuid           UUID UNIQUE,               -- matches MySQL leads.uuid
  flask_lead_id       INTEGER UNIQUE,            -- matches MySQL leads.id (set after MySQL write)
  name                TEXT NOT NULL,
  email               TEXT,
  phone               TEXT,
  company             TEXT,
  position            TEXT,
  location            TEXT,
  country             TEXT,
  city                TEXT,
  industry            TEXT,
  website             TEXT,
  linkedin_url        TEXT,
  interests           JSONB DEFAULT '[]',
  product             TEXT,
  qualification_score FLOAT DEFAULT 0,
  status              TEXT DEFAULT 'pending',
  origin              TEXT DEFAULT 'mobile',     -- 'web' | 'mobile' — which DB created it
  source              TEXT,                      -- linkedin, web, manual, etc.
  notes               TEXT,

  -- Sync fields
  sync_status         TEXT DEFAULT 'pending',    -- 'pending' | 'synced' | 'failed'
  version             INTEGER DEFAULT 1,

  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW(),
  synced_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_leads_status     ON leads_cache(status);
CREATE INDEX IF NOT EXISTS idx_leads_sync_status ON leads_cache(sync_status);
CREATE INDEX IF NOT EXISTS idx_leads_origin     ON leads_cache(origin);
CREATE INDEX IF NOT EXISTS idx_leads_country    ON leads_cache(country);
CREATE INDEX IF NOT EXISTS idx_leads_industry   ON leads_cache(industry);
CREATE INDEX IF NOT EXISTS idx_leads_score      ON leads_cache(qualification_score);
CREATE INDEX IF NOT EXISTS idx_leads_flask_id   ON leads_cache(flask_lead_id);
CREATE INDEX IF NOT EXISTS idx_leads_uuid       ON leads_cache(lead_uuid);
CREATE INDEX IF NOT EXISTS idx_leads_updated    ON leads_cache(updated_at);


-- ────────────────────────────────────────────────────────────
-- 3. SYNC LOG TABLE
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_log (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operation    TEXT NOT NULL,   -- 'web_to_mobile' | 'mobile_to_web' | 'user_sync'
  direction    TEXT NOT NULL,   -- 'mysql_to_supabase' | 'supabase_to_mysql'
  records      INTEGER DEFAULT 0,
  status       TEXT DEFAULT 'success',  -- 'success' | 'partial' | 'failed'
  error_msg    TEXT,
  triggered_by TEXT,
  duration_ms  INTEGER,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_log_created ON sync_log(created_at DESC);


-- ────────────────────────────────────────────────────────────
-- 4. OFFLINE QUEUE TABLE  (mobile writes while offline)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS offline_queue (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  action_type  TEXT NOT NULL,      -- 'CREATE_LEAD' | 'UPDATE_LEAD' | 'DELETE_LEAD'
  payload      JSONB NOT NULL,
  retry_count  INTEGER DEFAULT 0,
  status       TEXT DEFAULT 'pending',  -- 'pending' | 'processing' | 'done' | 'failed'
  error_msg    TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_queue_status  ON offline_queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_created ON offline_queue(created_at);


-- ────────────────────────────────────────────────────────────
-- 5. AUTO updated_at TRIGGERS
-- ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_leads_updated_at    ON leads_cache;
DROP TRIGGER IF EXISTS trg_users_updated_at    ON users_sync;

CREATE TRIGGER trg_leads_updated_at
  BEFORE UPDATE ON leads_cache
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users_sync
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ────────────────────────────────────────────────────────────
-- 6. ROW LEVEL SECURITY
--
-- Strategy:
--   READ  → anon key allowed (mobile reads with anon key, no Supabase auth)
--   WRITE → service role only (backend writes via service key, bypasses RLS)
--
-- This avoids Supabase Auth rate limits on mobile while keeping writes secure.
-- ────────────────────────────────────────────────────────────

ALTER TABLE users_sync    ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads_cache   ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE offline_queue ENABLE ROW LEVEL SECURITY;

-- Drop old policies if re-running this script
DROP POLICY IF EXISTS "auth_read_users"    ON users_sync;
DROP POLICY IF EXISTS "auth_read_leads"    ON leads_cache;
DROP POLICY IF EXISTS "auth_insert_leads"  ON leads_cache;
DROP POLICY IF EXISTS "auth_update_leads"  ON leads_cache;
DROP POLICY IF EXISTS "auth_delete_leads"  ON leads_cache;
DROP POLICY IF EXISTS "auth_read_sync_log" ON sync_log;
DROP POLICY IF EXISTS "auth_queue_all"     ON offline_queue;

-- users_sync: anon can read (mobile looks up user by user_uuid/email)
--             writes handled by backend service role (bypasses RLS)
CREATE POLICY "anon_read_users"
  ON users_sync FOR SELECT
  USING (true);

-- leads_cache: anon can read and write (mobile creates leads offline)
--              backend service role handles bulk upserts from MySQL
CREATE POLICY "anon_read_leads"
  ON leads_cache FOR SELECT
  USING (true);

CREATE POLICY "anon_insert_leads"
  ON leads_cache FOR INSERT
  WITH CHECK (true);

CREATE POLICY "anon_update_leads"
  ON leads_cache FOR UPDATE
  USING (true);

CREATE POLICY "anon_delete_leads"
  ON leads_cache FOR DELETE
  USING (true);

-- sync_log: anon read-only
CREATE POLICY "anon_read_sync_log"
  ON sync_log FOR SELECT
  USING (true);

-- offline_queue: anon full access (mobile queues actions while offline)
CREATE POLICY "anon_queue_all"
  ON offline_queue FOR ALL
  USING (true);


-- ────────────────────────────────────────────────────────────
-- 7. EXPLICIT DATA API GRANTS
--
-- Required from May 30 (new projects) / October 30 (all projects).
-- Without these, PostgREST / supabase-js with the anon key returns
-- a "42501" permission error even when RLS policies allow access.
--
-- service_role bypasses both RLS and grants — backend is unaffected.
-- ────────────────────────────────────────────────────────────

-- leads_cache: mobile app reads, creates, and updates leads
GRANT SELECT, INSERT, UPDATE, DELETE ON public.leads_cache   TO anon;

-- users_sync: mobile app looks up users by uuid/email (read-only)
GRANT SELECT                          ON public.users_sync    TO anon;

-- sync_log: mobile app reads sync history (read-only)
GRANT SELECT                          ON public.sync_log      TO anon;

-- offline_queue: mobile queues actions while offline (full access)
GRANT SELECT, INSERT, UPDATE, DELETE  ON public.offline_queue TO anon;


-- ────────────────────────────────────────────────────────────
-- 8. REAL-TIME PUBLICATION
-- Enables Supabase real-time subscriptions in the mobile app
-- ────────────────────────────────────────────────────────────
-- Run after schema creation:
-- ALTER PUBLICATION supabase_realtime ADD TABLE leads_cache;
-- ALTER PUBLICATION supabase_realtime ADD TABLE users_sync;


-- ────────────────────────────────────────────────────────────
-- 8. WEBHOOK FUNCTION (Supabase Edge Function — optional)
-- Notifies Flask backend when mobile writes a new lead.
-- Deploy via: supabase functions deploy notify-backend
-- ────────────────────────────────────────────────────────────
-- See: mobile/supabase/functions/notify-backend/index.ts
