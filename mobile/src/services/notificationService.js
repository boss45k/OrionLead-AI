/**
 * Push notification service — SDK 54 compatible.
 *
 * Token flow:
 *   1. Check we're running in a real build (not Expo Go, where remote
 *      push notifications are unsupported since SDK 53).
 *   2. Request / verify notification permission.
 *   3. Create Android notification channel.
 *   4. Obtain an ExponentPushToken via Expo's push service (requires
 *      projectId from EAS — set in app.json extra.eas.projectId).
 *   5. Store token in SecureStore and register with the Flask backend.
 *
 * All failures are non-fatal — the app continues normally without notifications.
 */
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

const STORED_TOKEN_KEY = 'pushToken';

function isExpoGo() {
  // SDK 54: executionEnvironment is 'storeClient' in Expo Go, 'standalone' in builds
  const env = Constants.executionEnvironment;
  if (env) return env === 'storeClient';
  // Fallback for older SDK compat
  const ownership = Constants.appOwnership;
  return ownership === 'expo' || ownership === 'storeClient';
}

function getProjectId() {
  const id =
    Constants.expoConfig?.extra?.eas?.projectId ||
    Constants.easConfig?.projectId;
  if (!id || id === 'REPLACE_WITH_YOUR_EAS_PROJECT_ID') return null;
  return id;
}

/**
 * Request permission, get Expo push token, register with the backend.
 * Returns the token string, or null on any failure.
 *
 * @param {Function} registerFn  - mobileAPI.registerToken(token, platform)
 */
export async function registerForPushNotifications(registerFn) {
  try {
    if (isExpoGo()) {
      if (__DEV__) console.log('[notifications] Expo Go — push notifications require a development build, skipping');
      return null;
    }

    const Notifications = await import('expo-notifications').catch(() => null);
    const Device        = await import('expo-device').catch(() => null);

    if (!Notifications || !Device) {
      if (__DEV__) console.log('[notifications] expo-notifications / expo-device not available, skipping');
      return null;
    }

    if (!Device.isDevice) {
      if (__DEV__) console.log('[notifications] Simulator/emulator detected — skipping push registration');
      return null;
    }

    // Request permission
    const { status: existing } = await Notifications.getPermissionsAsync();
    let finalStatus = existing;
    if (existing !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== 'granted') {
      if (__DEV__) console.log('[notifications] Push permission denied');
      return null;
    }

    // Android: create a high-priority alert channel for heads-up (WhatsApp-style) pop-ups.
    // Use a distinct channelId so Android never serves a cached lower-importance channel.
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('orionlead_alerts', {
        name:             'OrionLead Alerts',
        description:      'Lead updates and AI scoring results',
        importance:       Notifications.AndroidImportance?.MAX ?? 5,
        vibrationPattern: [0, 250, 250, 250],
        lightColor:       '#6366f1',
        lockscreenVisibility: Notifications.AndroidNotificationVisibility?.PUBLIC,
        bypassDnd:        false,
        enableLights:     true,
        enableVibrate:    true,
        showBadge:        true,
        sound:            'default',
      });
    }

    // Get Expo push token — projectId required for SDK 47+
    const projectId = getProjectId();
    if (!projectId) {
      console.warn('[notifications] EAS projectId not set in app.json extra.eas.projectId — run "eas init" to link project');
      return null;
    }

    const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
    const token = tokenData?.data;
    if (!token) return null;

    await SecureStore.setItemAsync(STORED_TOKEN_KEY, token);

    const platform = Platform.OS === 'ios' ? 'ios' : 'android';
    await registerFn(token, platform);

    if (__DEV__) console.log('[notifications] Registered push token:', token.slice(0, 28) + '…');
    return token;

  } catch (err) {
    const msg = err?.message || String(err);
    if (msg.includes('Network request failed')) {
      console.warn('[notifications] Push token fetch failed — FCM requires an EAS build (eas build --platform android). Running via Expo Go or Metro only will not work.');
    } else {
      console.warn('[notifications] registerForPushNotifications failed (non-fatal):', msg);
    }
    return null;
  }
}

/**
 * Remove the stored push token from the backend on logout.
 *
 * @param {Function} unregisterFn  - mobileAPI.unregisterToken(token)
 */
export async function unregisterPushNotifications(unregisterFn) {
  try {
    const token = await SecureStore.getItemAsync(STORED_TOKEN_KEY);
    if (!token) return;
    await unregisterFn(token);
    await SecureStore.deleteItemAsync(STORED_TOKEN_KEY);
    if (__DEV__) console.log('[notifications] Push token unregistered');
  } catch (err) {
    console.warn('[notifications] unregisterPushNotifications failed (non-fatal):', err?.message);
  }
}
