import 'react-native-url-polyfill/auto';
import React, { useEffect, useRef } from 'react';
import { registerRootComponent } from 'expo';
import { NavigationContainer } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import { ActivityIndicator, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import Constants from 'expo-constants';

import { AuthProvider, useAuth } from './src/context/AuthContext';
import { ThemeProvider, useTheme } from './src/context/ThemeContext';
import AppNavigator from './src/navigation/AppNavigator';
import AuthNavigator from './src/navigation/AuthNavigator';
import { useNetworkSync } from './src/hooks/useRealtime';
import AppDialog from './src/components/AppDialog';

// expo-notifications native module logs SDK 53+ errors in Expo Go regardless
// of JS-level try/catch (it's a native-layer console.error). Skipping ALL
// notification JS calls in Expo Go prevents the JS-triggered warnings and
// keeps the console clean during development.
const IS_EXPO_GO = Constants.executionEnvironment === 'storeClient';

// Must run at module level in real builds — controls how foreground notifications
// appear. In Expo Go this is a no-op to avoid redundant SDK 53 warning output.
if (!IS_EXPO_GO) {
  try {
    const Notifications = require('expo-notifications');
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList:   true,
        shouldPlaySound:  true,
        shouldSetBadge:   true,
      }),
    });
  } catch {}
}

// Shared navigation ref — lets notification tap handlers navigate from outside components.
export const navigationRef = React.createRef();

function RootNavigator() {
  const { user, loading } = useAuth();
  const { theme, isDark } = useTheme();

  const pendingLeadRef = useRef(null);

  useNetworkSync();

  useEffect(() => {
    // Notification listeners are only wired in real builds (development / production).
    // In Expo Go, remote push is unsupported since SDK 53 — skip to avoid warnings.
    if (IS_EXPO_GO) return;

    let receivedSub, responseSub;
    try {
      const Notifications = require('expo-notifications');

      receivedSub = Notifications.addNotificationReceivedListener((notification) => {
        console.log('[Notifications] Foreground notification:', notification.request.identifier);
      });

      responseSub = Notifications.addNotificationResponseReceivedListener((response) => {
        const data = response.notification.request.content.data || {};
        if (data.lead_id && navigationRef.current?.isReady()) {
          navigationRef.current.navigate('Leads', {
            screen: 'LeadDetail',
            params: { leadId: Number(data.lead_id) },
          });
        }
      });

      // Cold-start: app was closed and user tapped a notification to open it
      Notifications.getLastNotificationResponseAsync().then((response) => {
        if (!response) return;
        const data = response.notification.request.content.data || {};
        if (data.lead_id) pendingLeadRef.current = Number(data.lead_id);
      }).catch(() => {});

    } catch {}

    return () => {
      try { receivedSub?.remove(); } catch {}
      try { responseSub?.remove(); } catch {}
    };
  }, []);

  const onNavigatorReady = () => {
    if (pendingLeadRef.current) {
      navigationRef.current?.navigate('Leads', {
        screen: 'LeadDetail',
        params: { leadId: pendingLeadRef.current },
      });
      pendingLeadRef.current = null;
    }
  };

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: theme.bg, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" color="#6366f1" />
        <StatusBar style={isDark ? 'light' : 'dark'} />
      </View>
    );
  }

  return (
    <>
      <StatusBar style={isDark ? 'light' : 'dark'} />
      <NavigationContainer ref={navigationRef} onReady={onNavigatorReady}>
        {user ? <AppNavigator /> : <AuthNavigator />}
      </NavigationContainer>
    </>
  );
}

function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <AuthProvider>
            <RootNavigator />
            <AppDialog />
          </AuthProvider>
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

registerRootComponent(App);
