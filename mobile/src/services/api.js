import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

// ─── Base URL ─────────────────────────────────────────────────────────────────
// In dev mode, derives the backend IP from Expo's Metro bundler host so the
// app keeps working even when the PC's WiFi IP changes — no manual update needed.
// In production, falls back to the app.json extra.API_BASE_URL value.
const _resolveBaseUrl = () => {
  // 1. Explicit override always wins (useful for USB/ADB or custom setups)
  const configured = Constants.expoConfig?.extra?.API_BASE_URL;

  // 2. In development, extract the host that Expo Go is already talking to
  //    (Metro bundler runs on the same machine as the Flask backend)
  if (__DEV__) {
    const hostUri =
      Constants.expoConfig?.hostUri ||                    // SDK 45+ Expo Go
      Constants.manifest2?.extra?.expoGo?.debuggerHost;  // SDK 50+ new manifest

    if (hostUri) {
      const host = hostUri.split(':')[0]; // strip the Metro port (8081)
      // Only auto-derive backend URL when host is a real LAN IP (e.g. 192.168.x.x).
      // Tunnel/ngrok hosts (abc.ngrok.io, exp.direct, etc.) must NOT be used
      // because they only forward the Metro port, not Flask port 5000.
      const isLanIp = host && /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(host);
      if (isLanIp) {
        return `http://${host}:5000`;
      }
    }
    // Tunnel mode or explicit override — use configured value if it points
    // somewhere other than localhost.
    if (configured && !configured.includes('127.0.0.1') && !configured.includes('localhost')) {
      return configured;
    }
  }

  return configured ?? 'http://127.0.0.1:5000';
};

export const API_BASE_URL = _resolveBaseUrl();

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ─── Runtime server URL override ──────────────────────────────────────────────
// Lets a user point an already-installed build at any backend (e.g. their own
// computer) without a rebuild — useful when the build-time API_BASE_URL only
// reaches the developer's network. Persisted in SecureStore so it survives
// app restarts; takes effect immediately once set.
const SERVER_URL_KEY = 'customServerUrl';

function _normalizeUrl(url) {
  return url.trim().replace(/\/+$/, '');
}

/** Reads any saved override and applies it to the shared axios instance.
 *  Call once at app startup, before any screen makes a request. */
export async function initApiBaseUrl() {
  try {
    const saved = await SecureStore.getItemAsync(SERVER_URL_KEY);
    if (saved) {
      api.defaults.baseURL = `${_normalizeUrl(saved)}/api/v1`;
    }
  } catch (err) {
    console.warn('[api] Failed to read saved server URL:', err?.message);
  }
}

/** Current effective server URL (without the /api/v1 suffix), for display in Settings. */
export function getServerUrl() {
  return api.defaults.baseURL.replace(/\/api\/v1\/?$/, '');
}

/** Persists and immediately applies a new server URL. */
export async function setServerUrl(url) {
  const clean = _normalizeUrl(url);
  await SecureStore.setItemAsync(SERVER_URL_KEY, clean);
  api.defaults.baseURL = `${clean}/api/v1`;
}

/** Clears the override, reverting to the build-time default. */
export async function resetServerUrl() {
  await SecureStore.deleteItemAsync(SERVER_URL_KEY);
  api.defaults.baseURL = `${API_BASE_URL}/api/v1`;
}

/** One-off reachability check against an arbitrary URL — does not touch the shared instance. */
export async function testServerUrl(url) {
  const clean = _normalizeUrl(url);
  const resp = await axios.get(`${clean}/api/v1/health`, { timeout: 8000 });
  return resp.data;
}

// ─── Unauthorized handler ─────────────────────────────────────────────────────
// AuthContext calls setUnauthorizedHandler(logout) on mount so that when the
// 401 interceptor fires it can trigger a full context logout, not just clear
// SecureStore. This avoids a circular import (api ← AuthContext ← api).
let _onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  _onUnauthorized = fn;
}

// ─── Attach JWT token to every request ───────────────────────────────────────
api.interceptors.request.use(async (config) => {
  try {
    const token = await SecureStore.getItemAsync('authToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch (err) {
    console.warn('[api] SecureStore read failed, sending request without token:', err?.message);
  }
  return config;
});

// ─── Handle 401 — silent token refresh then retry, or logout ─────────────────
// Auth endpoints (login, logout, register, google, refresh) are excluded from
// the refresh-and-retry loop to prevent infinite recursion.
const AUTH_ENDPOINT_RE = /\/auth\/(login|logout|register|google|refresh)$/;

// Single in-flight refresh promise shared across concurrent 401s so we only
// hit /auth/refresh once even if multiple requests expire simultaneously.
let _refreshPromise = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status;
    const url    = error.config?.url || '';
    const isRetry = error.config?._isRetry;

    if (status === 401 && !AUTH_ENDPOINT_RE.test(url) && !isRetry) {
      try {
        // Coalesce concurrent 401s into one refresh call
        if (!_refreshPromise) {
          _refreshPromise = authAPI.refreshToken()
            .finally(() => { _refreshPromise = null; });
        }
        const refreshRes = await _refreshPromise;
        const newToken = refreshRes?.data?.token;

        if (newToken) {
          await SecureStore.setItemAsync('authToken', newToken);
          // Retry original request with new token, marked so we don't loop
          const retryConfig = {
            ...error.config,
            _isRetry: true,
            headers: { ...error.config.headers, Authorization: `Bearer ${newToken}` },
          };
          return api(retryConfig);
        }
      } catch (refreshErr) {
        console.warn('[api] Silent token refresh failed:', refreshErr?.message);
      }

      // Refresh failed — clear credentials and trigger logout
      try {
        await SecureStore.deleteItemAsync('authToken');
        await SecureStore.deleteItemAsync('authUser');
      } catch (err) {
        console.warn('[api] SecureStore delete failed during 401 cleanup:', err?.message);
      }
      if (typeof _onUnauthorized === 'function') {
        _onUnauthorized();
      }
    }

    // For auth-endpoint 401s (bad password, etc.) just reject normally
    return Promise.reject(error);
  }
);

// ─── Auth ─────────────────────────────────────────────────────────────────────
export const authAPI = {
  login: (email, password) => api.post('/auth/login', { email, password }),
  register: (data) => api.post('/auth/register', data),
  googleAuth: (credential) => api.post('/auth/google', { credential }),
  verifyEmail: (email, code) => api.post('/auth/verify-email', { email, code }),
  resendOtp: (email) => api.post('/auth/resend-otp', { email }),
  refreshToken: () => api.post('/auth/refresh'),
  getProfile: () => api.get('/auth/profile'),
  logout: () => api.post('/auth/logout'),
  changePassword: (currentPassword, newPassword) =>
    api.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword }),
};

// ─── Leads ────────────────────────────────────────────────────────────────────
export const leadsAPI = {
  getLeads: (params = {}) => api.get('/leads/', { params }),
  getLead: (id) => api.get(`/leads/${id}`),
  createLead: (data) => api.post('/leads/', data),
  updateLead: (id, data) => api.put(`/leads/${id}`, data),
  deleteLead: (id) => api.delete(`/leads/${id}`),
  searchLeads: (query, limit = 20) => api.get('/leads/search', { params: { query, limit } }),
  getStats: () => api.get('/leads/stats'),
  qualifyLead: (id, force = false) => api.post(`/leads/${id}/qualify`, { force_requalify: force, return_explanation: true }),
  batchQualify: (lead_ids) => api.post('/leads/batch-qualify', { lead_ids }),
  enrichLeads: (lead_ids) => api.post('/leads/enrich', { lead_ids }),
};

// ─── Analytics ────────────────────────────────────────────────────────────────
export const analyticsAPI = {
  getAnalytics: (range = '30days') => api.get('/analytics', { params: { range } }),
  getSummary: () => api.get('/analytics/summary'),
  getMetrics: () => api.get('/analytics/metrics'),
  getDaily: (days = 30) => api.get('/analytics/daily', { params: { days } }),
};

// ─── AI Engine ────────────────────────────────────────────────────────────────
export const aiAPI = {
  getStatus:        () => api.get('/ai/stats'),
  startCollection:  (data) => api.post('/ai/collect-leads', data),
  getTaskProgress:  (taskId) => api.get(`/ai/collect-leads/status/${taskId}`),
  getActivityLog:   () => api.get('/ai/logs'),
  trainML:          (body = {})   => api.post('/ai/train-ml', body),
  retrain:          (body = {})   => api.post('/ai/retrain', body),
  chat:             (message, history = []) => api.post('/ai/chat', { message, history }),
  analyzeLead:      (id) => api.post(`/ai/analyze-lead/${id}`),
  generateEmail:    (id, data = {}) => api.post(`/ai/generate-email/${id}`, data),
  enrichLead:       (id) => api.post(`/ai/enrich/${id}`),
  submitFeedback:     (lead_id, outcome) => api.post('/ai/feedback', { lead_id, outcome, label_source: 'user_feedback' }),
  getPipelineSummary: () => api.get('/ai/pipeline-summary'),
  getQualityReport:   () => api.get('/ai/quality-report'),
  getPendingFeedback: () => api.get('/ai/feedback/pending'),
  approveFeedback:    (id, note = '') => api.post(`/ai/feedback/${id}/approve`, { note }),
  rejectFeedback:     (id, note = '') => api.post(`/ai/feedback/${id}/reject`,  { note }),
};

// ─── Settings ─────────────────────────────────────────────────────────────────
export const settingsAPI = {
  getSettings: () => api.get('/settings'),
  saveSettings: (data) => api.post('/settings', data),
  testConnection: () => api.get('/health'),    // health check — verifies the backend API is reachable
};

// ─── Sync ─────────────────────────────────────────────────────────────────────
export const syncAPI = {
  // User sync
  syncCurrentUser: () => api.post('/sync/user'),
  syncAllUsers:    () => api.post('/sync/users/all'),

  // Web → Mobile: push MySQL leads → Supabase
  webToMobile: (data = {}) => api.post('/sync/web-to-mobile', data),

  // Mobile → Web: push Supabase records → MySQL
  mobileToWeb: (data = {}) => api.post('/sync/mobile-to-web', data),

  // Polling fallback (admin): pull pending Supabase records → MySQL
  poll: (limit = 200) => api.post('/sync/poll', { limit }),

  // Status + audit log
  getSyncStatus: () => api.get('/sync/status'),
  getSyncLogs:   (limit = 50) => api.get('/sync/logs', { params: { limit } }),
  retryFailed:   () => api.post('/sync/retry-failed'),
};

// ─── Profile ──────────────────────────────────────────────────────────────────
export const profileAPI = {
  update:      (data)     => api.put('/auth/profile', data),
  uploadPhoto: (formData) => api.put('/auth/profile/photo', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30000,
  }),
  deletePhoto: ()         => api.delete('/auth/profile/photo'),
};

// ─── Data Sources ─────────────────────────────────────────────────────────────
export const sourcesAPI = {
  getAll:    ()           => api.get('/sources'),
  getOne:    (id)         => api.get(`/sources/${id}`),
  create:    (data)       => api.post('/sources', data),
  update:    (id, data)   => api.put(`/sources/${id}`, data),
  remove:    (id)         => api.delete(`/sources/${id}`),
  sync:      (id)         => api.post(`/sources/${id}/sync`),
  getStats:  ()           => api.get('/sources/stats'),
  uploadCSV: (formData)   => api.post('/sources/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  }),
};

// ─── AI Collect extras ────────────────────────────────────────────────────────
export const collectAPI = {
  startSocial:       (data)   => api.post('/ai/collect-social', data),
  socialStatus:      (taskId) => api.get(`/ai/collect-social/status/${taskId}`),
  startAuto:         (data)   => api.post('/ai/collect/auto', data),
  autoStatus:        (taskId) => api.get(`/ai/collect/auto/status/${taskId}`),
  autoSources:       ()       => api.get('/ai/collect/auto/sources'),
  batchEnrich:       (data)   => api.post('/ai/enrich/batch', data),
  explainLead:       (id)     => api.get(`/ai/explain/${id}`),
  getMLDashboard:    ()       => api.get('/ai/dashboard'),
  getModelVersions:  ()       => api.get('/ai/model-versions'),
  restoreVersion:    (ver)    => api.post(`/ai/model-versions/${ver}/restore`),
  startCollection:   (data)   => api.post('/ai/collect-leads', data),
  collectionStatus:  (taskId) => api.get(`/ai/collect-leads/status/${taskId}`),
};

// ─── API Keys ─────────────────────────────────────────────────────────────────
export const apiKeysAPI = {
  // Team workspace keys — returned inside GET /settings response
  list:       ()       => api.get('/settings').then((r) => ({ data: { api_keys: r.data?.api_keys || [] } })),
  create:     (data)   => api.post('/settings/api-keys/generate', data),
  remove:     (id)     => api.delete(`/settings/api-keys/${id}`),
  // Personal user key — stored on the user row
  getPersonal:()       => api.get('/settings/my-api-key'),
  regenerate: ()       => api.post('/settings/my-api-key/generate'),
  revoke:     ()       => api.delete('/settings/my-api-key'),
};

// ─── Integrations ─────────────────────────────────────────────────────────────
export const integrationsAPI = {
  getAll:  ()              => api.get('/settings/integrations'),
  save:    (data)          => api.post('/settings/integrations', data),
  test:    (key, value)    => api.post('/settings/integrations/test', { key, ...(value ? { value } : {}) }),
};

// ─── Admin ────────────────────────────────────────────────────────────────────
export const adminAPI = {
  listUsers: () => api.get('/auth/admin/users'),
  createUser: (data) => api.post('/auth/admin/users', data),
  updateUser: (id, data) => api.put(`/auth/admin/users/${id}`, data),
  deleteUser: (id) => api.delete(`/auth/admin/users/${id}`),
  getAdminStats: () => api.get('/auth/admin/stats'),
};

// ─── Mobile (push notification token management) ──────────────────────────────
export const mobileAPI = {
  registerToken:    (token, platform = 'android', app_version = null) =>
    api.post('/mobile/register-token', { token, platform, app_version }),
  unregisterToken:  (token) =>
    api.delete('/mobile/unregister-token', { data: { token } }),
  testNotification: (title, body) =>
    api.post('/debug/test-notification', { title, body }),
};

// ─── Interest-based collection ────────────────────────────────────────────────
export const interestAPI = {
  getCategories: () => api.get('/ai/lead-categories'),
  start: (data) =>
    api.post('/ai/collect-by-interest', data),
  status: (taskId) =>
    api.get(`/ai/collect-by-interest/status/${taskId}`),
};

export default api;
