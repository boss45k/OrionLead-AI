/**
 * Quick table creator — runs via Supabase Management API.
 * Usage:  node supabase/create-tables.js <service_role_key>
 *
 * Get service_role key from:
 *   Supabase Dashboard → Project Settings → API → service_role (secret)
 */

const https = require('https');

const PROJECT_REF  = 'hlskwjpsycfdhjnillib';
const SERVICE_KEY  = process.argv[2];

if (!SERVICE_KEY) {
  console.error('\nUsage: node supabase/create-tables.js <your_service_role_key>\n');
  console.error('Get it from: https://supabase.com/dashboard/project/' + PROJECT_REF + '/settings/api\n');
  process.exit(1);
}

const TABLES_SQL = `
-- ══════════════════════════════════════════════════════
-- AI Lead Collection — Database Schema
-- ══════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. users_sync
CREATE TABLE IF NOT EXISTS users_sync (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_uuid     UUID UNIQUE,
  flask_user_id INTEGER UNIQUE,
  email         TEXT UNIQUE NOT NULL,
  full_name     TEXT,
  company       TEXT,
  role          TEXT DEFAULT 'user',
  is_active     BOOLEAN DEFAULT TRUE,
  source        TEXT DEFAULT 'web',
  sync_status   TEXT DEFAULT 'synced',
  version       INTEGER DEFAULT 1,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  synced_at     TIMESTAMPTZ DEFAULT NOW()
);

-- 2. leads_cache
CREATE TABLE IF NOT EXISTS leads_cache (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_uuid           UUID UNIQUE,
  flask_lead_id       INTEGER UNIQUE,
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
  origin              TEXT DEFAULT 'mobile',
  source              TEXT,
  notes               TEXT,
  sync_status         TEXT DEFAULT 'pending',
  version             INTEGER DEFAULT 1,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW(),
  synced_at           TIMESTAMPTZ
);

-- 3. sync_log
CREATE TABLE IF NOT EXISTS sync_log (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operation    TEXT NOT NULL,
  direction    TEXT NOT NULL,
  records      INTEGER DEFAULT 0,
  status       TEXT DEFAULT 'success',
  error_msg    TEXT,
  triggered_by TEXT,
  duration_ms  INTEGER,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 4. offline_queue
CREATE TABLE IF NOT EXISTS offline_queue (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  action_type  TEXT NOT NULL,
  payload      JSONB NOT NULL,
  retry_count  INTEGER DEFAULT 0,
  status       TEXT DEFAULT 'pending',
  error_msg    TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);

-- 5. Indexes
CREATE INDEX IF NOT EXISTS idx_users_email      ON users_sync(email);
CREATE INDEX IF NOT EXISTS idx_users_flask_id   ON users_sync(flask_user_id);
CREATE INDEX IF NOT EXISTS idx_leads_status     ON leads_cache(status);
CREATE INDEX IF NOT EXISTS idx_leads_sync       ON leads_cache(sync_status);
CREATE INDEX IF NOT EXISTS idx_leads_origin     ON leads_cache(origin);
CREATE INDEX IF NOT EXISTS idx_leads_country    ON leads_cache(country);
CREATE INDEX IF NOT EXISTS idx_leads_flask_id   ON leads_cache(flask_lead_id);
CREATE INDEX IF NOT EXISTS idx_leads_updated    ON leads_cache(updated_at);
CREATE INDEX IF NOT EXISTS idx_sync_log_created ON sync_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_queue_status     ON offline_queue(status);

-- 6. updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS \$\$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
\$\$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_leads_updated_at ON leads_cache;
DROP TRIGGER IF EXISTS trg_users_updated_at ON users_sync;
CREATE TRIGGER trg_leads_updated_at BEFORE UPDATE ON leads_cache FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users_sync  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- 7. RLS
ALTER TABLE users_sync    ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads_cache   ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE offline_queue ENABLE ROW LEVEL SECURITY;

-- policies (safe to re-run)
DO \$do\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='users_sync' AND policyname='anon_read_users') THEN
    CREATE POLICY anon_read_users ON users_sync FOR SELECT USING (true);
  END IF;
  -- Backend (service key) handles all writes to users_sync via sync_users_to_supabase().
  -- This INSERT policy is a safety net only; real writes bypass RLS via service key.
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='users_sync' AND policyname='anon_insert_users') THEN
    CREATE POLICY anon_insert_users ON users_sync FOR INSERT WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='users_sync' AND policyname='anon_update_users') THEN
    CREATE POLICY anon_update_users ON users_sync FOR UPDATE USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='leads_cache' AND policyname='anon_all_leads') THEN
    CREATE POLICY anon_all_leads ON leads_cache FOR ALL USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='sync_log'    AND policyname='anon_read_log') THEN
    CREATE POLICY anon_read_log ON sync_log FOR SELECT USING (true);
    CREATE POLICY anon_insert_log ON sync_log FOR INSERT WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='offline_queue' AND policyname='anon_queue') THEN
    CREATE POLICY anon_queue ON offline_queue FOR ALL USING (true) WITH CHECK (true);
  END IF;
END
\$do\$;

-- 8. Real-time
ALTER PUBLICATION supabase_realtime ADD TABLE leads_cache;
ALTER PUBLICATION supabase_realtime ADD TABLE users_sync;
`;

function runSQL(sql) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ query: sql });
    const req = https.request({
      hostname: 'api.supabase.com',
      path:     `/v1/projects/${PROJECT_REF}/database/query`,
      method:   'POST',
      headers:  {
        'Content-Type':   'application/json',
        'Authorization':  `Bearer ${SERVICE_KEY}`,
        'Content-Length': Buffer.byteLength(body),
      },
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(data) }); }
        catch { resolve({ status: res.statusCode, body: data }); }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

(async () => {
  console.log('\n🚀  Creating Supabase tables for AI Lead Collection...');
  console.log(`📡  Project: https://${PROJECT_REF}.supabase.co\n`);

  const result = await runSQL(TABLES_SQL);

  if (result.status === 200 || result.status === 201) {
    console.log('✅  All tables created successfully!\n');
    console.log('Next steps:');
    console.log('  1. cd mobile && npm install && npm start');
    console.log('  2. Add SUPABASE_SERVICE_KEY to .env for backend sync\n');
  } else {
    console.log('❌  Error:', JSON.stringify(result.body, null, 2));
    console.log('\nAlternative: paste supabase/schema.sql into Supabase SQL Editor:');
    console.log(`  https://supabase.com/dashboard/project/${PROJECT_REF}/sql\n`);
  }
})();
