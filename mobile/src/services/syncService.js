/**
 * SyncService (mobile) — two-way sync between Supabase and MySQL backend.
 *
 * Web → Mobile  (web_to_mobile):
 *   Backend pushes MySQL leads → Supabase, mobile reads via real-time.
 *
 * Mobile → Web  (mobile_to_web):
 *   Mobile writes to Supabase first, then calls backend POST /sync/mobile-to-web.
 *   Backend writes to MySQL. Loop prevention: origin + sync_status flags.
 *
 * Offline:
 *   When offline, actions are queued via offlineQueue.js.
 *   When online, queue is flushed automatically.
 *
 * Conflict resolution: last-write-wins (updated_at) — handled by backend.
 */

import { leadsAPI, syncAPI } from './api';
import { supabaseLeads, supabaseSyncLog } from './supabaseService';
import { enqueue, processQueue, getPendingCount } from './offlineQueue';

const TAG = '[SyncService]';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function _now() {
  return new Date().toISOString();
}

function _toSupabaseRow(lead, origin = 'web') {
  return {
    flask_lead_id:       lead.id,
    lead_uuid:           lead.uuid,
    name:                lead.name,
    email:               lead.email,
    phone:               lead.phone,
    company:             lead.company,
    position:            lead.position,
    location:            lead.location,
    country:             lead.country,
    city:                lead.city,
    industry:            lead.industry,
    website:             lead.website,
    linkedin_url:        lead.linkedin_url,
    interests:           lead.interests || [],
    product:             lead.product,
    qualification_score: lead.qualification_score || 0,
    status:              lead.status || 'pending',
    origin,
    source:              lead.source,
    notes:               lead.notes,
    collected_by:        lead.collected_by ?? null,
    version:             lead.version || 1,
    sync_status:         'synced',         // already in MySQL — mark synced
    updated_at:          lead.updated_at || _now(),
    synced_at:           _now(),
  };
}

// ─── Web → Mobile (MySQL → Supabase) ─────────────────────────────────────────

/**
 * Trigger the backend to push pending MySQL leads → Supabase.
 * Usually called on app foreground / dashboard open.
 */
export async function triggerWebToMobile({ leadIds, since, silent = false } = {}) {
  try {
    const resp = await syncAPI.webToMobile({ lead_ids: leadIds, since });
    const result = resp.data;
    if (!silent) {
      if (__DEV__) console.log(TAG, 'web→mobile:', result);
    }
    return { success: true, ...result };
  } catch (err) {
    console.warn(TAG, 'web→mobile failed:', err?.message);
    return { success: false, error: err?.message };
  }
}

/**
 * Fetch latest leads from Flask and push into Supabase cache.
 * Fallback when the backend-initiated push is unavailable.
 */
export async function syncLeadsToSupabase({ page = 1, perPage = 50, silent = false } = {}) {
  try {
    const resp  = await leadsAPI.getLeads({ page, per_page: perPage });
    const leads = resp.data?.leads || [];
    if (leads.length === 0) return { success: true, synced: 0 };

    const rows = leads.map((l) => _toSupabaseRow(l, 'web'));
    const { error } = await supabaseLeads.bulkUpsert(rows);
    if (error) throw error;

    if (!silent) {
      await supabaseSyncLog.addLog({
        operation:  'web_to_mobile',
        direction:  'mysql_to_supabase',
        records:    rows.length,
        status:     'success',
        triggered_by: 'mobile_app',
      });
    }
    return { success: true, synced: rows.length };
  } catch (err) {
    console.warn(TAG, 'syncLeadsToSupabase failed:', err?.message);
    return { success: false, error: err?.message };
  }
}

// ─── Mobile → Web (Supabase → MySQL) ─────────────────────────────────────────

/**
 * Write a lead created/updated on mobile → Supabase first, then notify backend.
 * Backend will write to MySQL and mark sync_status='synced'.
 *
 * Loop prevention:
 *   • We set origin='mobile' and sync_status='pending' in Supabase.
 *   • Backend reads pending records, writes to MySQL, then patches sync_status='synced'.
 *   • Next web→mobile run skips records where origin='mobile' AND sync_status='synced'.
 *
 * @param {object} leadData   Full lead payload (include lead_uuid if available)
 * @param {boolean} isOnline  If false, action is queued for later
 */
export async function pushLeadToBackend(leadData, isOnline = true) {
  const record = {
    ...leadData,
    origin:      'mobile',
    sync_status: 'pending',
    updated_at:  _now(),
  };

  if (!isOnline) {
    const actionType = leadData.flask_lead_id ? 'UPDATE_LEAD' : 'CREATE_LEAD';
    await enqueue(actionType, record);
    if (__DEV__) console.log(TAG, `Queued ${actionType} for offline retry`);
    return { success: true, queued: true };
  }

  try {
    // 1. Write to Supabase (mobile DB)
    const { error: sbErr } = await supabaseLeads.upsert({
      ...record,
      lead_uuid: leadData.uuid || leadData.lead_uuid,
    });
    if (sbErr) throw sbErr;

    // 2. Notify backend to write to MySQL (mobile→web)
    const resp = await syncAPI.mobileToWeb({ records: [record] });
    const result = resp.data;

    if (__DEV__) console.log(TAG, 'mobile→web:', result);
    return { success: true, queued: false, ...result };
  } catch (err) {
    console.warn(TAG, 'pushLeadToBackend failed — queuing:', err?.message);
    // Fall back to offline queue
    const actionType = leadData.flask_lead_id ? 'UPDATE_LEAD' : 'CREATE_LEAD';
    await enqueue(actionType, record);
    return { success: false, queued: true, error: err?.message };
  }
}

/**
 * Push a lead deletion to the backend.
 */
export async function deleteLeadFromBackend(flaskLeadId, isOnline = true) {
  if (!isOnline) {
    await enqueue('DELETE_LEAD', { flask_lead_id: flaskLeadId });
    return { success: true, queued: true };
  }
  try {
    await leadsAPI.deleteLead(flaskLeadId);
    return { success: true };
  } catch (err) {
    await enqueue('DELETE_LEAD', { flask_lead_id: flaskLeadId });
    return { success: false, queued: true, error: err?.message };
  }
}

// ─── Single-lead sync (after qualify / status change) ────────────────────────

/**
 * Re-fetch a single lead from Flask and push into Supabase.
 */
export async function syncSingleLead(flaskLeadId) {
  try {
    const resp = await leadsAPI.getLead(flaskLeadId);
    const l = resp.data?.lead;
    if (!l) return { success: false };
    const { error } = await supabaseLeads.upsert(_toSupabaseRow(l, 'web'));
    return { success: !error, error: error?.message };
  } catch (err) {
    console.warn(TAG, 'syncSingleLead failed:', err?.message);
    return { success: false };
  }
}

// ─── User sync ────────────────────────────────────────────────────────────────

/**
 * After Flask login, tell the backend to sync this user → Supabase users_sync.
 * The backend uses the service key (bypasses RLS), so this is the only safe
 * path for writing to users_sync.  The mobile anon key has SELECT-only access.
 *
 * Same email  →  same user_uuid  across MySQL and Supabase (guaranteed by backend).
 */
export async function syncUserAfterLogin(user) {
  try {
    // Backend call: POST /api/v1/sync/user  — uses service key, bypasses RLS
    await syncAPI.syncCurrentUser();
    return { success: true };
  } catch (err) {
    console.warn(TAG, 'syncUserAfterLogin failed:', err?.message);
    return { success: false, error: err?.message };
  }
}

// ─── Offline queue flusher ────────────────────────────────────────────────────

/**
 * Call this when the app regains connectivity.
 * Processes any queued offline actions.
 */
export async function flushOfflineQueue() {
  const pending = await getPendingCount();
  if (pending === 0) return { processed: 0, failed: 0, skipped: 0 };
  if (__DEV__) console.log(TAG, `Flushing offline queue (${pending} pending)...`);
  const result = await processQueue();
  if (__DEV__) console.log(TAG, 'Queue flush result:', result);
  return result;
}
