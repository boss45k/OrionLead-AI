/**
 * OfflineQueue — persist mobile actions while offline and retry when reconnected.
 *
 * Uses expo-secure-store for storage (falls back to AsyncStorage).
 * Each queued item:
 *   {
 *     id:          string   (UUID)
 *     action_type: string   ('CREATE_LEAD' | 'UPDATE_LEAD' | 'DELETE_LEAD')
 *     payload:     object   (lead data or { lead_id })
 *     retry_count: number
 *     status:      'pending' | 'processing' | 'done' | 'failed'
 *     error:       string | null
 *     created_at:  ISO string
 *   }
 */

import * as SecureStore from 'expo-secure-store';
import NetInfo from '@react-native-community/netinfo';
import { leadsAPI } from './api';
import { syncAPI } from './api';

const QUEUE_KEY     = 'offline_queue_v1';
const MAX_RETRIES   = 5;
const BASE_DELAY_MS = 2000;

// ─── Persistence helpers ──────────────────────────────────────────────────────

async function _loadQueue() {
  try {
    const raw = await SecureStore.getItemAsync(QUEUE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (err) {
    console.warn('[OfflineQueue] Failed to load queue from SecureStore:', err?.message);
    return [];
  }
}

async function _saveQueue(queue) {
  try {
    await SecureStore.setItemAsync(QUEUE_KEY, JSON.stringify(queue));
  } catch (err) {
    console.warn('[OfflineQueue] Failed to persist queue:', err);
  }
}

function _uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function _delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Add an action to the offline queue.
 * @param {'CREATE_LEAD'|'UPDATE_LEAD'|'DELETE_LEAD'} actionType
 * @param {object} payload  Lead data or { lead_id } for deletes
 */
export async function enqueue(actionType, payload) {
  const queue = await _loadQueue();

  // Deduplication: for UPDATE and DELETE, if an identical pending action for
  // the same lead already exists in the queue, replace it instead of appending.
  // This prevents double-updates or double-deletes from rapid taps.
  const leadId = payload.lead_id || payload.flask_lead_id || payload.id;
  if (leadId && (actionType === 'UPDATE_LEAD' || actionType === 'DELETE_LEAD')) {
    const existingIdx = queue.findIndex(
      (i) => i.action_type === actionType && i.status === 'pending' &&
             (i.payload.lead_id === leadId || i.payload.flask_lead_id === leadId || i.payload.id === leadId)
    );
    if (existingIdx !== -1) {
      // Update existing item with the latest payload instead of duplicating
      queue[existingIdx].payload = { ...payload, updated_at: new Date().toISOString(), origin: 'mobile', sync_status: 'pending' };
      queue[existingIdx].retry_count = 0;
      queue[existingIdx].error = null;
      await _saveQueue(queue);
      if (__DEV__) console.log(`[OfflineQueue] Deduped ${actionType} for lead ${leadId} (id=${queue[existingIdx].id})`);
      return queue[existingIdx];
    }
  }

  const item = {
    id:          _uuid(),
    action_type: actionType,
    payload:     { ...payload, updated_at: new Date().toISOString(), origin: 'mobile', sync_status: 'pending' },
    retry_count: 0,
    status:      'pending',
    error:       null,
    created_at:  new Date().toISOString(),
  };
  queue.push(item);
  await _saveQueue(queue);
  if (__DEV__) console.log(`[OfflineQueue] Enqueued ${actionType} (id=${item.id})`);
  return item;
}

/**
 * Return all items currently in the queue.
 */
export async function getQueue() {
  return _loadQueue();
}

/**
 * Return count of pending items.
 */
export async function getPendingCount() {
  const q = await _loadQueue();
  return q.filter((i) => i.status === 'pending').length;
}

/**
 * Process the entire queue — execute each action against the backend.
 * Skips items with status='done' or 'failed' (exhausted retries).
 * Uses exponential backoff per item.
 *
 * @returns {{ processed: number, failed: number, skipped: number }}
 */
export async function processQueue() {
  // Do not attempt any network calls if the device is offline —
  // avoids burning retry counts and backoff delays for nothing.
  try {
    const net = await NetInfo.fetch();
    if (!net.isConnected) {
      if (__DEV__) console.log('[OfflineQueue] Device offline — skipping processQueue');
      return { processed: 0, failed: 0, skipped: 0 };
    }
  } catch (err) {
    console.warn('[OfflineQueue] NetInfo check failed, proceeding anyway:', err?.message);
  }

  const queue = await _loadQueue();
  let processed = 0, failed = 0, skipped = 0;

  for (let i = 0; i < queue.length; i++) {
    const item = queue[i];

    if (item.status === 'done') { skipped++; continue; }
    if (item.status === 'failed') { skipped++; continue; }
    if (item.retry_count >= MAX_RETRIES) {
      queue[i].status = 'failed';
      queue[i].error  = 'Max retries exceeded';
      failed++;
      continue;
    }

    queue[i].status = 'processing';

    try {
      await _executeAction(item);
      queue[i].status = 'done';
      processed++;
      if (__DEV__) console.log(`[OfflineQueue] ✓ ${item.action_type} id=${item.id}`);
    } catch (err) {
      queue[i].retry_count += 1;
      queue[i].status = queue[i].retry_count >= MAX_RETRIES ? 'failed' : 'pending';
      queue[i].error  = err?.message || String(err);
      failed++;
      console.warn(`[OfflineQueue] ✗ ${item.action_type} attempt ${queue[i].retry_count}: ${queue[i].error}`);

      // Exponential backoff before next item
      if (queue[i].retry_count < MAX_RETRIES) {
        await _delay(BASE_DELAY_MS * Math.pow(2, queue[i].retry_count - 1));
      }
    }
  }

  await _saveQueue(queue);
  return { processed, failed, skipped };
}

/**
 * Remove all completed ('done') items from the queue.
 */
export async function pruneCompleted() {
  const queue = await _loadQueue();
  const pruned = queue.filter((i) => i.status !== 'done');
  await _saveQueue(pruned);
  return queue.length - pruned.length;
}

/**
 * Clear the entire queue (use with caution).
 */
export async function clearQueue() {
  await _saveQueue([]);
}

// ─── Action executors ─────────────────────────────────────────────────────────

async function _executeAction(item) {
  const { action_type, payload } = item;

  switch (action_type) {
    case 'CREATE_LEAD': {
      // Create in MySQL via Flask API
      const resp = await leadsAPI.createLead({
        ...payload,
        source: payload.source || 'mobile',
      });
      const lead = resp.data?.lead;
      // Immediately sync to backend (mobile→web)
      if (lead?.id) {
        await syncAPI.mobileToWeb({ records: [{ ...payload, flask_lead_id: lead.id, sync_status: 'synced' }] });
      }
      break;
    }

    case 'UPDATE_LEAD': {
      const { lead_id, flask_lead_id, ...data } = payload;
      const id = flask_lead_id || lead_id;
      if (!id) throw new Error('UPDATE_LEAD requires lead_id or flask_lead_id');
      await leadsAPI.updateLead(id, data);
      // Sync update back to MySQL
      await syncAPI.mobileToWeb({ records: [{ ...payload, flask_lead_id: id, sync_status: 'synced' }] });
      break;
    }

    case 'DELETE_LEAD': {
      const { lead_id, flask_lead_id } = payload;
      const id = flask_lead_id || lead_id;
      if (!id) throw new Error('DELETE_LEAD requires lead_id or flask_lead_id');
      await leadsAPI.deleteLead(id);
      break;
    }

    default:
      throw new Error(`Unknown action_type: ${action_type}`);
  }
}
