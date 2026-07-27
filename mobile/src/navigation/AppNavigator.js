import React, { useState, useEffect } from 'react';
import { Platform } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createStackNavigator } from '@react-navigation/stack';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme, COLORS } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { adminAPI, aiAPI } from '../services/api';

import HomeScreen        from '../screens/DashboardScreen';
import LeadsScreen       from '../screens/LeadsScreen';
import LeadDetailScreen  from '../screens/LeadDetailScreen';
import AIEngineScreen    from '../screens/AIEngineScreen';
import AnalyticsScreen   from '../screens/AnalyticsScreen';
import SettingsScreen    from '../screens/SettingsScreen';
import AdminScreen       from '../screens/AdminScreen';
import ProfileScreen     from '../screens/ProfileScreen';
import DataSourcesScreen from '../screens/DataSourcesScreen';

const Tab           = createBottomTabNavigator();
const LeadsStack    = createStackNavigator();
const SettingsStack = createStackNavigator();

function LeadsStackNavigator() {
  const { theme } = useTheme();
  return (
    <LeadsStack.Navigator
      screenOptions={{
        headerStyle:         { backgroundColor: theme.card },
        headerTintColor:     theme.text,
        headerTitleStyle:    { fontWeight: '700', fontSize: 17 },
        headerShadowVisible: false,
        headerBackTitleVisible: false,
      }}
    >
      <LeadsStack.Screen name="LeadsList"  component={LeadsScreen}      options={{ title: 'Leads' }} />
      <LeadsStack.Screen name="LeadDetail" component={LeadDetailScreen} options={{ title: 'Lead Detail' }} />
    </LeadsStack.Navigator>
  );
}

function SettingsStackNavigator() {
  const { theme } = useTheme();
  return (
    <SettingsStack.Navigator
      screenOptions={{
        headerStyle:         { backgroundColor: theme.card },
        headerTintColor:     theme.text,
        headerTitleStyle:    { fontWeight: '700', fontSize: 17 },
        headerShadowVisible: false,
        headerBackTitleVisible: false,
      }}
    >
      <SettingsStack.Screen name="Profile"  component={ProfileScreen}  options={{ title: 'Profile' }} />
      <SettingsStack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Settings' }} />
    </SettingsStack.Navigator>
  );
}

const ICONS = {
  Dashboard: ['home',      'home-outline'],
  Leads:     ['people',    'people-outline'],
  AI:        ['flash',     'flash-outline'],
  Analytics: ['bar-chart', 'bar-chart-outline'],
  Sources:   ['layers',    'layers-outline'],
  Admin:     ['shield',    'shield-outline'],
  Account:   ['person',    'person-outline'],
};

export default function AppNavigator() {
  const { theme } = useTheme();
  const { isAdmin, isSubAdmin, isManager } = useAuth();
  const insets = useSafeAreaInsets();
  const [pendingCount, setPendingCount] = useState(null);

  // Admin and manager both fetch pending label-approval counts; only admin also counts pending users
  useEffect(() => {
    if (!isManager) { setPendingCount(null); return; }
    const fetchPending = async () => {
      try {
        let count = 0;
        const feedbackRes = await aiAPI.getPendingFeedback();
        count += feedbackRes.data?.count || 0;
        if (isAdmin) {
          const usersRes = await adminAPI.listUsers();
          count += (usersRes.data?.users || []).filter(u => !u.is_active).length;
        }
        setPendingCount(count > 0 ? count : null);
      } catch {}
    };
    fetchPending();
    const interval = setInterval(fetchPending, 30000);
    return () => clearInterval(interval);
  }, [isAdmin, isManager]);

  const bottomInset = insets.bottom;
  const tabBarHeight = Platform.OS === 'ios' ? 82 : 56 + bottomInset;
  const tabBarPaddingBottom = Platform.OS === 'ios' ? 24 : 8 + bottomInset;

  const tabScreenOptions = ({ route }) => ({
    tabBarIcon: ({ focused, color, size }) => {
      const [active, inactive] = ICONS[route.name] || ['ellipse', 'ellipse-outline'];
      return <Ionicons name={focused ? active : inactive} size={size} color={color} />;
    },
    tabBarActiveTintColor:   COLORS.primary,
    tabBarInactiveTintColor: theme.textMuted,
    tabBarStyle: {
      backgroundColor: theme.tabBar,
      borderTopColor:  theme.tabBorder,
      borderTopWidth:  1,
      paddingBottom:   tabBarPaddingBottom,
      paddingTop:      6,
      height:          tabBarHeight,
      shadowColor:     '#000',
      shadowOpacity:   0.1,
      shadowRadius:    12,
      shadowOffset:    { width: 0, height: -3 },
      elevation:       12,
    },
    tabBarLabelStyle: { fontSize: 11, fontWeight: '600', marginTop: 2 },
    headerStyle:         { backgroundColor: theme.card },
    headerTintColor:     theme.text,
    headerTitleStyle:    { fontWeight: '700', fontSize: 17 },
    headerShadowVisible: false,
  });

  return (
    <Tab.Navigator screenOptions={tabScreenOptions}>
      <Tab.Screen name="Dashboard" component={HomeScreen}             options={{ title: 'Dashboard' }} />
      <Tab.Screen name="Leads"     component={LeadsStackNavigator}    options={{ title: 'Leads', headerShown: false }} />
      {/* sub_admin has no AI Engine access — backend blocks it at route level */}
      {!isSubAdmin && (
        <Tab.Screen name="AI" component={AIEngineScreen} options={{ title: 'AI Engine', headerTitle: 'AI Engine' }} />
      )}
      <Tab.Screen name="Analytics" component={AnalyticsScreen}        options={{ title: 'Analytics' }} />
      {isAdmin && (
        <Tab.Screen name="Sources" component={DataSourcesScreen}      options={{ title: 'Sources', headerTitle: 'Data Sources' }} />
      )}
      {(isManager || isSubAdmin) && (
        <Tab.Screen
          name="Admin"
          component={AdminScreen}
          options={{ title: isSubAdmin ? 'Team' : isAdmin ? 'Admin' : 'Approvals', tabBarBadge: pendingCount ?? undefined }}
        />
      )}
      <Tab.Screen name="Account"   component={SettingsStackNavigator} options={{ title: 'Account', headerShown: false }} />
    </Tab.Navigator>
  );
}
