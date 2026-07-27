import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import * as SecureStore from 'expo-secure-store';
import { authAPI, mobileAPI, setUnauthorizedHandler, initApiBaseUrl } from '../services/api';
import { syncUserAfterLogin } from '../services/syncService';
import { registerForPushNotifications, unregisterPushNotifications } from '../services/notificationService';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]     = useState(null);
  const [token, setToken]   = useState(null);
  const [loading, setLoading] = useState(true);

  // ── Register 401 → logout handler with the Axios interceptor ─────────────
  // Must be set before any API call, so we do it synchronously on first render.
  // The ref-based logout is used to avoid a stale-closure in the interceptor.
  const logoutRef = React.useRef(null);

  // ── Restore session on app launch ──────────────────────────────────────────
  useEffect(() => {
    // Wire the Axios 401 interceptor to call our logout so UI resets immediately
    setUnauthorizedHandler(() => {
      if (logoutRef.current) logoutRef.current();
    });

    (async () => {
      try {
        await initApiBaseUrl();
        const storedToken = await SecureStore.getItemAsync('authToken');
        const storedUser  = await SecureStore.getItemAsync('authUser');
        if (storedToken && storedUser) {
          // Optimistically restore so screens render immediately
          setToken(storedToken);
          setUser(JSON.parse(storedUser));
          // Re-register push token — token may have changed after a fresh install
          registerForPushNotifications(mobileAPI.registerToken).catch(() => {});
          // Verify token + refresh role from backend in background
          try {
            const resp    = await authAPI.getProfile();
            const fresh   = resp.data?.user;
            if (fresh) {
              await SecureStore.setItemAsync('authUser', JSON.stringify(fresh));
              setUser(fresh);
            }
          } catch (verifyErr) {
            // 401 is handled by the interceptor above; log other errors
            if (verifyErr?.response?.status !== 401) {
              console.warn('[AuthContext] Profile refresh failed (network?):', verifyErr?.message);
            }
            // Keep cached user on network errors
          }
        }
      } catch (err) {
        console.error('[AuthContext] Session restore failed:', err?.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // ── Login via Flask backend ────────────────────────────────────────────────
  const login = useCallback(async (email, password) => {
    const resp = await authAPI.login(email, password);
    const { token: jwt, user: userData } = resp.data;

    await SecureStore.setItemAsync('authToken', jwt);
    await SecureStore.setItemAsync('authUser', JSON.stringify(userData));
    setToken(jwt);
    setUser(userData);

    // Sync user to Supabase users_sync in background
    syncUserAfterLogin(userData).catch(() => {});

    // Register FCM push token — fire-and-forget, never blocks login
    registerForPushNotifications(mobileAPI.registerToken).catch(() => {});

    return userData;
  }, []);

  // ── Register via Flask backend ─────────────────────────────────────────────
  // Flask creates the user with is_active=False (pending admin approval).
  // Do NOT auto-login — the account is inactive and login would return 401.
  const register = useCallback(async (data) => {
    const resp = await authAPI.register(data);
    return resp.data;
  }, []);

  // ── Google sign-in ──────────────────────────────────────────────────────────
  const googleLogin = useCallback(async (credential) => {
    const resp = await authAPI.googleAuth(credential);
    const { token: jwt, user: userData } = resp.data;

    await SecureStore.setItemAsync('authToken', jwt);
    await SecureStore.setItemAsync('authUser', JSON.stringify(userData));
    setToken(jwt);
    setUser(userData);
    syncUserAfterLogin(userData).catch(() => {});
    registerForPushNotifications(mobileAPI.registerToken).catch(() => {});
    return userData;
  }, []);

  // ── Logout ──────────────────────────────────────────────────────────────────
  const logout = useCallback(async () => {
    // Unregister push token before clearing credentials — fire-and-forget
    unregisterPushNotifications(mobileAPI.unregisterToken).catch(() => {});

    try { await authAPI.logout(); } catch (err) {
      console.warn('[AuthContext] Logout API call failed (ignored):', err?.message);
    }
    try {
      await SecureStore.deleteItemAsync('authToken');
      await SecureStore.deleteItemAsync('authUser');
    } catch (err) {
      console.warn('[AuthContext] SecureStore delete failed during logout:', err?.message);
    }
    setToken(null);
    setUser(null);
  }, []);

  // ── Refresh profile ─────────────────────────────────────────────────────────
  const refreshProfile = useCallback(async () => {
    try {
      const resp    = await authAPI.getProfile();
      const updated = resp.data.user;
      await SecureStore.setItemAsync('authUser', JSON.stringify(updated));
      setUser(updated);
      return updated;
    } catch (err) {
      console.warn('[AuthContext] refreshProfile failed:', err?.message);
    }
  }, []);

  // Keep logoutRef current so the interceptor always calls the latest logout
  useEffect(() => { logoutRef.current = logout; }, [logout]);

  const isAdmin    = user?.role === 'admin';
  const isSubAdmin = user?.role === 'sub_admin';
  const isManager  = user?.role === 'admin' || user?.role === 'manager';

  return (
    <AuthContext.Provider
      value={{ user, token, loading, isAdmin, isSubAdmin, isManager, login, register, googleLogin, logout, refreshProfile }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
