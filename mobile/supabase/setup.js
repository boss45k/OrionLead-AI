/**
 * Supabase Database Setup Script
 * Run: node supabase/setup.js
 *
 * Creates all required tables, indexes, triggers, and RLS policies.
 * Requires: npm install @supabase/supabase-js
 */

const { createClient } = require('@supabase/supabase-js');

const SUPABASE_URL      = 'https://hlskwjpsycfdhjnillib.supabase.co';
// ⚠️  Use SERVICE ROLE key here (not anon/publishable key) — needed for DDL
// Get it from: Supabase Dashboard → Project Settings → API → service_role key
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY || 'PASTE_YOUR_SERVICE_ROLE_KEY_HERE';

if (SUPABASE_SERVICE_KEY === 'PASTE_YOUR_SERVICE_ROLE_KEY_HERE') {
  console.error('\n❌  Set SUPABASE_SERVICE_KEY env var or paste your service_role key in this file.');
  console.error('   Get it from: Supabase Dashboard → Project Settings → API → service_role\n');
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY, {
  auth: { persistSession: false },
});

const SQL_STEPS = [
  {
    name: 'Enable UUID extension',
    sql: `CREATE EXTENSION IF NOT EXISTS "uuid-ossp";`,
  },
  {
    name: 'Create users_sync table',
    sql: `
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
    `,
  },
  {
    name: 'Create leads_cache table',
    sql: `
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
    `,
  },
  {
    name: 'Create sync_log table',
    sql: `
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
    `,
  },
  {
    name: 'Create offline_queue table',
    sql: `
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
    `,
  },
  {
    name: 'Create indexes',
    sql: `
      CREATE INDEX IF NOT EXISTS idx_users_email     ON users_sync(email);
      CREATE INDEX IF NOT EXISTS idx_users_flask_id  ON users_sync(flask_user_id);
      CREATE INDEX IF NOT EXISTS idx_leads_status    ON leads_cache(status);
      CREATE INDEX IF NOT EXISTS idx_leads_sync      ON leads_cache(sync_status);
      CREATE INDEX IF NOT EXISTS idx_leads_origin    ON leads_cache(origin);
      CREATE INDEX IF NOT EXISTS idx_leads_country   ON leads_cache(country);
      CREATE INDEX IF NOT EXISTS idx_leads_flask_id  ON leads_cache(flask_lead_id);
      CREATE INDEX IF NOT EXISTS idx_leads_updated   ON leads_cache(updated_at);
      CREATE INDEX IF NOT EXISTS idx_sync_log        ON sync_log(created_at DESC);
      CREATE INDEX IF NOT EXISTS idx_queue_status    ON offline_queue(status);
    `,
  },
  {
    name: 'Create updated_at trigger function',
    sql: `
      CREATE OR REPLACE FUNCTION update_updated_at()
      RETURNS TRIGGER AS $$
      BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
      END;
      $$ LANGUAGE plpgsql;
    `,
  },
  {
    name: 'Attach updated_at triggers',
    sql: `
      DROP TRIGGER IF EXISTS trg_leads_updated_at ON leads_cache;
      DROP TRIGGER IF EXISTS trg_users_updated_at ON users_sync;
      CREATE TRIGGER trg_leads_updated_at
        BEFORE UPDATE ON leads_cache
        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
      CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users_sync
        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    `,
  },
  {
    name: 'Enable RLS',
    sql: `
      ALTER TABLE users_sync    ENABLE ROW LEVEL SECURITY;
      ALTER TABLE leads_cache   ENABLE ROW LEVEL SECURITY;
      ALTER TABLE sync_log      ENABLE ROW LEVEL SECURITY;
      ALTER TABLE offline_queue ENABLE ROW LEVEL SECURITY;
    `,
  },
  {
    name: 'Create RLS policies',
    sql: `
      DO $$ BEGIN
        -- users_sync
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='users_sync' AND policyname='auth_read_users') THEN
          CREATE POLICY auth_read_users ON users_sync FOR SELECT USING (auth.role() = 'authenticated');
        END IF;
        -- leads_cache
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='leads_cache' AND policyname='auth_read_leads') THEN
          CREATE POLICY auth_read_leads   ON leads_cache FOR SELECT USING (auth.role() = 'authenticated');
          CREATE POLICY auth_insert_leads ON leads_cache FOR INSERT WITH CHECK (auth.role() = 'authenticated');
          CREATE POLICY auth_update_leads ON leads_cache FOR UPDATE USING (auth.role() = 'authenticated');
          CREATE POLICY auth_delete_leads ON leads_cache FOR DELETE USING (auth.role() = 'authenticated');
        END IF;
        -- sync_log
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='sync_log' AND policyname='auth_read_sync_log') THEN
          CREATE POLICY auth_read_sync_log ON sync_log FOR SELECT USING (auth.role() = 'authenticated');
        END IF;
        -- offline_queue
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='offline_queue' AND policyname='auth_queue_all') THEN
          CREATE POLICY auth_queue_all ON offline_queue FOR ALL USING (auth.role() = 'authenticated');
        END IF;
      END $$;
    `,
  },
  {
    name: 'Enable real-time on leads_cache',
    sql: `ALTER PUBLICATION supabase_realtime ADD TABLE leads_cache;`,
    optional: true,   // may fail if already added — that's fine
  },
  {
    name: 'Enable real-time on users_sync',
    sql: `ALTER PUBLICATION supabase_realtime ADD TABLE users_sync;`,
    optional: true,
  },
];

async function runStep(step, index) {
  process.stdout.write(`  [${index + 1}/${SQL_STEPS.length}] ${step.name}... `);
  try {
    const { error } = await supabase.rpc('exec_sql', { query: step.sql }).single();
    // Supabase JS doesn't expose raw SQL — use the management API instead
    throw new Error('Use management API for DDL');
  } catch (_) {
    // Fallback: use Supabase REST SQL endpoint (requires service key)
  }
}

// ── Use Supabase Management API to run raw SQL ─────────────────────────────
const https = require('https');

function runSQL(sql) {
  return new Promise((resolve, reject) => {
    const projectRef = SUPABASE_URL.replace('https://', '').split('.')[0];
    const body = JSON.stringify({ query: sql });
    const options = {
      hostname: 'api.supabase.com',
      path:     `/v1/projects/${projectRef}/database/query`,
      method:   'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${SUPABASE_SERVICE_KEY}`,
        'Content-Length': Buffer.byteLength(body),
      },
    };
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode >= 400) reject(new Error(parsed.message || JSON.stringify(parsed)));
          else resolve(parsed);
        } catch {
          if (res.statusCode < 400) resolve({});
          else reject(new Error(data));
        }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function setup() {
  console.log('\n🚀  AI Lead Collection — Supabase Setup');
  console.log(`📡  Project: ${SUPABASE_URL}\n`);

  let passed = 0, failed = 0;

  for (let i = 0; i < SQL_STEPS.length; i++) {
    const step = SQL_STEPS[i];
    process.stdout.write(`  [${String(i + 1).padStart(2)}/${SQL_STEPS.length}] ${step.name}... `);
    try {
      await runSQL(step.sql.trim());
      console.log('✅');
      passed++;
    } catch (err) {
      if (step.optional) {
        console.log(`⚠️  skipped (${err.message.slice(0, 60)})`);
      } else {
        console.log(`❌  ${err.message.slice(0, 80)}`);
        failed++;
      }
    }
  }

  console.log(`\n${'─'.repeat(50)}`);
  console.log(`✅  ${passed} steps passed   ❌  ${failed} steps failed`);

  if (failed === 0) {
    console.log('\n🎉  Supabase is ready! Next steps:');
    console.log('   1. Copy your service_role key from Supabase Dashboard → Settings → API');
    console.log('   2. Add it to .env as SUPABASE_SERVICE_KEY=<key>');
    console.log('   3. Run the mobile app: cd mobile && npm install && npm start');
  } else {
    console.log('\n⚠️  Some steps failed. You can also run schema.sql manually:');
    console.log('   Supabase Dashboard → SQL Editor → paste supabase/schema.sql');
  }
}

setup().catch((err) => {
  console.error('\n💥  Fatal error:', err.message);
  process.exit(1);
});
