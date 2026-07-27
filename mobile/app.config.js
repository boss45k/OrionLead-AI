/**
 * Dynamic Expo config — reads Supabase credentials from environment variables.
 *
 * USAGE (local dev):
 *   export EXPO_SUPABASE_URL="https://your-project.supabase.co"
 *   export EXPO_SUPABASE_ANON_KEY="your-publishable-anon-key"
 *   export EXPO_API_BASE_URL="http://192.168.x.x:5000"   # optional, defaults to localhost
 *   npx expo start
 *
 * USAGE (EAS production builds):
 *   eas secret:create --scope project --name EXPO_SUPABASE_URL   --value "..."
 *   eas secret:create --scope project --name EXPO_SUPABASE_ANON_KEY --value "..."
 *   eas build --platform all
 *
 * WHY app.config.js instead of app.json:
 *   app.json has no way to read process.env at build time.
 *   This file is the Expo-recommended way to inject secrets without
 *   hardcoding them in version-controlled files.
 *   When this file exists, Expo ignores the "extra" block in app.json.
 */

const base = require('./app.json').expo;

module.exports = () => ({
  expo: {
    ...base,
    plugins: [
      ...(base.plugins || []),
      'expo-asset',
      'expo-web-browser',
      '@react-native-google-signin/google-signin',
    ],
    extra: {
      eas:               base.extra?.eas,                    // preserve EAS projectId so eas init/build works
      SUPABASE_URL:      process.env.EXPO_SUPABASE_URL      || base.extra?.SUPABASE_URL,
      SUPABASE_ANON_KEY: process.env.EXPO_SUPABASE_ANON_KEY || base.extra?.SUPABASE_ANON_KEY,
      API_BASE_URL:      process.env.EXPO_API_BASE_URL       || base.extra?.API_BASE_URL || 'http://localhost:5000',
      GOOGLE_CLIENT_ID:          process.env.EXPO_GOOGLE_CLIENT_ID          || '656052458985-58o08p0oqh5flhqgpd82en5jo8qvvtbd.apps.googleusercontent.com',
      GOOGLE_ANDROID_CLIENT_ID:  process.env.EXPO_GOOGLE_ANDROID_CLIENT_ID  || null,
      GOOGLE_DESKTOP_CLIENT_ID:     process.env.EXPO_GOOGLE_DESKTOP_CLIENT_ID     || null,
      GOOGLE_DESKTOP_CLIENT_SECRET: process.env.EXPO_GOOGLE_DESKTOP_CLIENT_SECRET || null,
    },
  },
});
