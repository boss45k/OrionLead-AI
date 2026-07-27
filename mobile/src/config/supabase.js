import 'react-native-url-polyfill/auto';
import { createClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

// ─── Supabase credentials ────────────────────────────────────────────────────
// Credentials are injected via app.json → "extra" block (local dev)
// or EAS Secrets (production builds).
//
// HOW TO CONFIGURE:
//   Local dev  : set SUPABASE_URL and SUPABASE_ANON_KEY in mobile/app.json extra{}
//                OR create mobile/app.config.js reading from process.env
//   EAS build  : eas secret:create --scope project --name SUPABASE_URL --value "..."
//
// NOTE: Only the anon (publishable) key belongs here.
//       The service_role key must NEVER be used in mobile code.
//
// ⚠️  No hardcoded fallback values — if config is missing the error below
//     gives an actionable message instead of silently using the wrong project.

const _url  = Constants.expoConfig?.extra?.SUPABASE_URL;
const _key  = Constants.expoConfig?.extra?.SUPABASE_ANON_KEY;

if (!_url || _url.includes('__') || _url === '') {
  throw new Error(
    '[Supabase] SUPABASE_URL is not configured.\n' +
    'Set it in mobile/app.json → expo.extra.SUPABASE_URL\n' +
    'or via EAS Secrets for production builds.\n' +
    'See mobile/.env.example for the required format.'
  );
}

if (!_key || _key.includes('__') || _key === '') {
  throw new Error(
    '[Supabase] SUPABASE_ANON_KEY is not configured.\n' +
    'Set it in mobile/app.json → expo.extra.SUPABASE_ANON_KEY\n' +
    'or via EAS Secrets for production builds.\n' +
    'See mobile/.env.example for the required format.'
  );
}

export const SUPABASE_URL      = _url;
export const SUPABASE_ANON_KEY = _key;

// ─── SecureStore adapter for Supabase session persistence ────────────────────
const ExpoSecureStoreAdapter = {
  getItem:    (key)        => SecureStore.getItemAsync(key),
  setItem:    (key, value) => SecureStore.setItemAsync(key, value),
  removeItem: (key)        => SecureStore.deleteItemAsync(key),
};

// ─── Supabase client ──────────────────────────────────────────────────────────
export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: ExpoSecureStoreAdapter,
    autoRefreshToken:  true,
    persistSession:    true,
    detectSessionInUrl: false,
  },
});
