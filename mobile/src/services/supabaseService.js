import { supabase } from '../config/supabase';

// ─── Users Sync ───────────────────────────────────────────────────────────────

export const supabaseUsers = {
  /** Get all synced users */
  getAll: () =>
    supabase.from('users_sync').select('*').order('created_at', { ascending: false }),

  /** Get a user by email */
  getByEmail: (email) =>
    supabase.from('users_sync').select('*').eq('email', email).single(),

  /** Upsert a user (called after Flask login/register) */
  upsert: (userData) =>
    supabase.from('users_sync').upsert(userData, { onConflict: 'email' }),
};

// ─── Leads Cache ──────────────────────────────────────────────────────────────

export const supabaseLeads = {
  /** Get paginated leads with optional filters */
  getLeads: async ({ page = 1, perPage = 20, status, country, industry, minScore, search, collectedBy } = {}) => {
    let query = supabase
      .from('leads_cache')
      .select('*', { count: 'exact' })
      .order('created_at', { ascending: false })
      .range((page - 1) * perPage, page * perPage - 1);

    // Always scope to the current user's leads
    if (collectedBy != null) query = query.eq('collected_by', collectedBy);

    if (status) query = query.eq('status', status);
    if (country) query = query.ilike('country', `%${country}%`);
    if (industry) query = query.ilike('industry', `%${industry}%`);
    if (minScore != null) query = query.gte('qualification_score', minScore);
    if (search) {
      query = query.or(
        `name.ilike.%${search}%,email.ilike.%${search}%,company.ilike.%${search}%`
      );
    }
    return query;
  },

  /** Get a single lead by flask_lead_id */
  getByFlaskId: (flaskId) =>
    supabase.from('leads_cache').select('*').eq('flask_lead_id', flaskId).single(),

  /** Upsert a lead from Flask */
  upsert: (leadData) =>
    supabase.from('leads_cache').upsert(leadData, { onConflict: 'flask_lead_id' }),

  /** Bulk upsert leads */
  bulkUpsert: (leads) =>
    supabase.from('leads_cache').upsert(leads, { onConflict: 'flask_lead_id' }),

  /** Update a lead's status/score locally */
  update: (id, data) =>
    supabase.from('leads_cache').update(data).eq('id', id),

  /** Subscribe to real-time lead changes */
  subscribe: (callback) => {
    const channel = supabase
      .channel('leads_cache_changes')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'leads_cache' },
        callback
      )
      .subscribe();
    return channel;
  },

  /** Unsubscribe from real-time */
  unsubscribe: (channel) => supabase.removeChannel(channel),
};

// ─── Sync Log ─────────────────────────────────────────────────────────────────

export const supabaseSyncLog = {
  getLogs: (limit = 50) =>
    supabase
      .from('sync_log')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(limit),

  addLog: (entry) => supabase.from('sync_log').insert(entry),
};

// ─── Stats derived from Supabase cache ───────────────────────────────────────

export const supabaseStats = {
  getLeadStats: async (collectedBy = null) => {
    let query = supabase.from('leads_cache').select('status, qualification_score');
    if (collectedBy != null) query = query.eq('collected_by', collectedBy);
    const { data, error } = await query;

    if (error || !data) return null;

    const total = data.length;
    const qualified = data.filter((l) => l.status === 'qualified').length;
    const contacted = data.filter((l) => l.status === 'contacted').length;
    const converted = data.filter((l) => l.status === 'converted').length;
    const pending = data.filter((l) => l.status === 'pending').length;
    const avgScore =
      total > 0
        ? data.reduce((sum, l) => sum + (l.qualification_score || 0), 0) / total
        : 0;

    return { total, qualified, contacted, converted, pending, avgScore };
  },
};
