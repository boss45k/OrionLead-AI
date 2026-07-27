import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, Switch, ActivityIndicator, Image, ActionSheetIOS, Platform, Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { settingsAPI, syncAPI, profileAPI, apiKeysAPI, integrationsAPI, mobileAPI } from '../services/api';
import { showError, showSuccess, showWarning, showInfo, showConfirm, showDialog } from '../utils/dialog';
import { supabase } from '../config/supabase';
import { supabaseSyncLog } from '../services/supabaseService';
import { triggerWebToMobile, syncUserAfterLogin } from '../services/syncService';
// Lazy-load ImagePicker so a missing native module doesn't crash the whole screen
let _ImagePicker = null;
const getImagePicker = () => {
  if (_ImagePicker) return _ImagePicker;
  try {
    _ImagePicker = require('expo-image-picker');
    return _ImagePicker;
  } catch (e) {
    return null;
  }
};

const TABS = [
  { key: 'profile',       label: 'Profile'      },
  { key: 'notifications', label: 'Notifications' },
  { key: 'integrations',  label: 'Integrations' },
  { key: 'sync',          label: 'Sync'         },
  { key: 'apikeys',       label: 'API Keys'     },
  { key: 'app',           label: 'App'          },
];

const NOTIF_FIELDS = [
  { key: 'notify_new_leads',     label: 'Email me when new leads arrive'           },
  { key: 'notify_qualification', label: 'Notify when lead qualification completes' },
  { key: 'notify_high_quality',  label: 'Alert on high-quality leads (score > 80)' },
  { key: 'notify_system_errors', label: 'Notify about system errors'              },
  { key: 'notify_daily_digest',  label: 'Send daily digest email'                 },
];

export default function SettingsScreen({ route }) {
  const { theme, isDark, toggleTheme } = useTheme();
  const { user, logout, refreshProfile, isAdmin } = useAuth();

  const [activeTab, setActiveTab] = useState(route?.params?.initialTab || 'profile');

  // ── Profile state ─────────────────────────────────────────────────────────
  const [fullName,       setFullName]       = useState(user?.full_name || '');
  const [company,        setCompany]        = useState(user?.company || '');
  const [saving,         setSaving]         = useState(false);
  const [testing,        setTesting]        = useState(false);
  const [connStatus,     setConnStatus]     = useState(null);
  const [photoUrl,       setPhotoUrl]       = useState(user?.profile_photo_url || null);
  const [photoUploading, setPhotoUploading] = useState(false);
  const [showPhotoSheet, setShowPhotoSheet] = useState(false);

  // ── Notifications state ───────────────────────────────────────────────────
  const [notifSettings,  setNotifSettings]  = useState({});
  const [notifLoading,   setNotifLoading]   = useState(false);
  const [savingNotif,    setSavingNotif]     = useState(false);
  const [testingPush,    setTestingPush]     = useState(false);

  // ── Integrations state ────────────────────────────────────────────────────
  const [integrations,      setIntegrations]      = useState({});
  const [integrationsLoading, setIntegrationsLoad] = useState(false);
  const [inputValues,       setInputValues]       = useState({});
  const [keyOps,            setKeyOps]            = useState({});  // { [envKey]: 'saving'|'testing'|'ok'|'fail'|undefined }

  // ── Sync state ────────────────────────────────────────────────────────────
  const [syncStatus, setSyncStatus] = useState(null);
  const [syncing,    setSyncing]    = useState(false);
  const [syncLogs,   setSyncLogs]   = useState([]);

  // ── API Keys state ────────────────────────────────────────────────────────
  const [apiKeys,     setApiKeys]     = useState([]);
  const [keysLoading, setKeysLoading] = useState(false);
  const [newKeyName,  setNewKeyName]  = useState('');
  const [creatingKey, setCreatingKey] = useState(false);
  const [personalKey, setPersonalKey] = useState(null);

  // ── Load on tab switch ────────────────────────────────────────────────────
  useEffect(() => {
    if (activeTab === 'sync')          loadSyncData();
    if (activeTab === 'apikeys')       loadApiKeys();
    if (activeTab === 'integrations')  loadIntegrations();
    if (activeTab === 'notifications') loadNotifSettings();
  }, [activeTab]);

  // ── Notifications ─────────────────────────────────────────────────────────
  const loadNotifSettings = async () => {
    setNotifLoading(true);
    try {
      const res = await settingsAPI.getSettings();
      const s   = res.data?.settings || {};
      setNotifSettings({
        notify_new_leads:     !!s.notify_new_leads,
        notify_qualification: !!s.notify_qualification,
        notify_high_quality:  !!s.notify_high_quality,
        notify_system_errors: !!s.notify_system_errors,
        notify_daily_digest:  !!s.notify_daily_digest,
      });
    } catch (err) {
      console.warn('[Settings] loadNotifSettings failed:', err?.message);
    } finally {
      setNotifLoading(false);
    }
  };

  const handleSaveNotif = async () => {
    setSavingNotif(true);
    try {
      await settingsAPI.saveSettings(notifSettings);
      showSuccess('Saved', 'Notification preferences updated');
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to save notification settings');
    } finally {
      setSavingNotif(false);
    }
  };

  const handleTestPush = async () => {
    setTestingPush(true);
    try {
      const res  = await mobileAPI.testNotification('OrionLead Test', 'Push notifications are working!');
      const sent = res.data?.sent ?? 0;
      if (sent > 0) {
        showSuccess('Sent', `Notification sent to ${sent} device(s). Check your lock screen.`);
      } else {
        showError('No Devices', 'No registered device found. Open the app on your phone and log in first.');
      }
    } catch (err) {
      showError('Error', err?.response?.data?.error || err?.response?.data?.message || 'Failed to send test notification');
    } finally {
      setTestingPush(false);
    }
  };

  // ── Integrations ──────────────────────────────────────────────────────────
  const loadIntegrations = async () => {
    setIntegrationsLoad(true);
    try {
      const res  = await integrationsAPI.getAll();
      const data = res.data?.integrations || {};
      setIntegrations(data);
      const vals = {};
      Object.keys(data).forEach((k) => { vals[k] = ''; });
      setInputValues(vals);
    } catch (err) {
      console.warn('[Settings] loadIntegrations failed:', err?.message);
    } finally {
      setIntegrationsLoad(false);
    }
  };

  const handleSaveIntegration = async (envKey) => {
    const val = (inputValues[envKey] || '').trim();
    if (!val) { showWarning('Paste Key', 'Enter your API key first.'); return; }
    setKeyOps((p) => ({ ...p, [envKey]: 'saving' }));
    try {
      await integrationsAPI.save({ [envKey]: val });
      setInputValues((p) => ({ ...p, [envKey]: '' }));
      setKeyOps((p) => ({ ...p, [envKey]: 'ok' }));
      loadIntegrations();
      showSuccess('Saved', `${integrations[envKey]?.label || envKey} key saved.`);
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to save key');
      setKeyOps((p) => ({ ...p, [envKey]: 'fail' }));
    }
  };

  const handleTestIntegration = async (envKey) => {
    const val = (inputValues[envKey] || '').trim();
    setKeyOps((p) => ({ ...p, [envKey]: 'testing' }));
    try {
      const res = await integrationsAPI.test(envKey, val || undefined);
      const { valid, message: msg } = res.data || {};
      setKeyOps((p) => ({ ...p, [envKey]: valid ? 'ok' : 'fail' }));
      showDialog({
        title: valid ? 'Connected' : 'Invalid Key',
        message: `${integrations[envKey]?.label}: ${msg || (valid ? 'Connected successfully' : 'Invalid key')}`,
        type: valid ? 'success' : 'error',
      });
    } catch (err) {
      setKeyOps((p) => ({ ...p, [envKey]: 'fail' }));
      showError('Test Failed', err?.response?.data?.message || 'Connection test failed');
    }
  };

  const handleClearIntegration = (envKey) => {
    showConfirm(
      `Remove ${integrations[envKey]?.label || envKey}?`,
      'The key will be deleted from your environment.',
      async () => {
        setKeyOps((p) => ({ ...p, [envKey]: 'saving' }));
        try {
          await integrationsAPI.save({ [envKey]: '' });
          setKeyOps((p) => ({ ...p, [envKey]: undefined }));
          loadIntegrations();
        } catch (err) {
          showError('Error', err?.response?.data?.message || 'Failed to remove key');
          setKeyOps((p) => ({ ...p, [envKey]: undefined }));
        }
      },
      undefined, 'Remove', 'Cancel', 'danger',
    );
  };

  // ── API Keys ──────────────────────────────────────────────────────────────
  const loadApiKeys = async () => {
    setKeysLoading(true);
    try {
      const [keysRes, personalRes] = await Promise.allSettled([
        apiKeysAPI.list(),
        apiKeysAPI.getPersonal(),
      ]);
      if (keysRes.status === 'fulfilled')     setApiKeys(keysRes.value.data?.api_keys || []);
      if (personalRes.status === 'fulfilled') setPersonalKey(personalRes.value.data || null);
    } catch (err) {
      console.warn('[Settings] loadApiKeys failed:', err?.message);
    } finally {
      setKeysLoading(false);
    }
  };

  const handleCreateKey = async () => {
    if (!newKeyName.trim()) { showWarning('Required', 'Key name is required'); return; }
    setCreatingKey(true);
    try {
      await apiKeysAPI.create({ name: newKeyName.trim() });
      setNewKeyName('');
      loadApiKeys();
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to create key');
    } finally {
      setCreatingKey(false);
    }
  };

  const handleDeleteKey = (key) => {
    showConfirm(
      'Revoke Key',
      `Revoke "${key.name}"? Any integrations using it will stop working.`,
      async () => {
        try {
          await apiKeysAPI.remove(key.id);
          setApiKeys((prev) => prev.filter((k) => k.id !== key.id));
        } catch (err) {
          showError('Error', err?.response?.data?.message || 'Failed to revoke key');
        }
      },
      undefined, 'Revoke', 'Cancel', 'danger',
    );
  };

  const handleRegeneratePersonal = () => {
    showConfirm(
      'Regenerate Key',
      'Your current personal API key will be invalidated. Continue?',
      async () => {
        try {
          const res    = await apiKeysAPI.regenerate();
          const newKey = res.data?.api_key;
          showInfo('Key Generated — Save It Now', newKey || '(key not returned)');
          const freshRes = await apiKeysAPI.getPersonal();
          setPersonalKey(freshRes.data || null);
        } catch (err) {
          showError('Error', err?.response?.data?.message || 'Failed to regenerate');
        }
      },
      undefined, 'Regenerate', 'Cancel', 'danger',
    );
  };

  // ── Sync ──────────────────────────────────────────────────────────────────
  const loadSyncData = async () => {
    try {
      const [statusRes, logsRes] = await Promise.allSettled([
        syncAPI.getSyncStatus(),
        supabaseSyncLog.getLogs(10),
      ]);
      if (statusRes.status === 'fulfilled') setSyncStatus(statusRes.value.data);
      if (logsRes.status === 'fulfilled')   setSyncLogs(logsRes.value.data || []);
    } catch (err) {
      console.warn('[Settings] loadSyncData unexpected error:', err?.message);
    }
  };

  const handleSyncLeads = async () => {
    setSyncing(true);
    try {
      const result = await triggerWebToMobile();
      showSuccess('Sync Complete', `${result.synced ?? 0} leads synced to Supabase`);
      loadSyncData();
    } catch (err) {
      showError('Sync Failed', err?.response?.data?.message || 'Could not sync leads.');
    } finally {
      setSyncing(false);
    }
  };

  const handleSyncUser = async () => {
    setSyncing(true);
    try {
      await syncUserAfterLogin(user);
      showSuccess('Sync Complete', 'User synced to Supabase');
    } catch (err) {
      showError('Sync Failed', err?.response?.data?.message || 'Could not sync user.');
    } finally {
      setSyncing(false);
    }
  };

  // ── Profile ───────────────────────────────────────────────────────────────
  const handlePickPhoto = () => {
    if (!getImagePicker()) {
      showWarning('Not Available', 'Image picker module not found. Restart the app or rebuild.');
      return;
    }
    if (Platform.OS === 'ios') {
      const options = photoUrl
        ? ['Take Photo', 'Choose from Library', 'Remove Photo', 'Cancel']
        : ['Take Photo', 'Choose from Library', 'Cancel'];
      ActionSheetIOS.showActionSheetWithOptions(
        { options, destructiveButtonIndex: photoUrl ? 2 : undefined, cancelButtonIndex: options.length - 1 },
        (idx) => _handlePhotoAction(idx),
      );
    } else {
      setShowPhotoSheet(true);
    }
  };

  const _handlePhotoAction = async (idx) => {
    const cancelIdx = photoUrl ? 3 : 2;
    if (idx === cancelIdx) return;

    // Remove photo
    if (idx === 2 && photoUrl) {
      try {
        setPhotoUploading(true);
        await profileAPI.deletePhoto();
        setPhotoUrl(null);
        refreshProfile().catch(() => {});
        showSuccess('Removed', 'Profile photo removed');
      } catch (err) {
        showError('Error', 'Failed to remove photo');
      } finally {
        setPhotoUploading(false);
      }
      return;
    }

    try {
      // Request permissions
      const IP = getImagePicker();
      if (!IP) {
        showWarning('Not Available', 'Image picker not available. Please restart the app.');
        return;
      }

      if (idx === 0) {
        const { status } = await IP.requestCameraPermissionsAsync();
        if (status !== 'granted') {
          showWarning('Permission denied', 'Camera access is required to take a photo.');
          return;
        }
      } else {
        const { status } = await IP.requestMediaLibraryPermissionsAsync();
        if (status !== 'granted') {
          showWarning('Permission denied', 'Photo library access is required.');
          return;
        }
      }

      // Launch picker
      const pickerOptions = {
        mediaTypes: IP.MediaTypeOptions ? IP.MediaTypeOptions.Images : ['images'],
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.85,
      };

      const result = idx === 0
        ? await IP.launchCameraAsync(pickerOptions)
        : await IP.launchImageLibraryAsync(pickerOptions);

      if (!result || result.canceled) return;

      const asset = result.assets?.[0];
      if (!asset?.uri) return;

      const formData = new FormData();
      formData.append('photo', {
        uri: asset.uri,
        type: asset.mimeType || 'image/jpeg',
        name: 'photo.jpg',
      });

      setPhotoUploading(true);
      const res = await profileAPI.uploadPhoto(formData);
      const newUrl = res.data?.profile_photo_url || asset.uri;
      setPhotoUrl(newUrl);
      refreshProfile().catch(() => {});
      showSuccess('Updated', 'Profile photo saved');
    } catch (err) {
      const msg = err?.response?.data?.message || err?.message || 'Something went wrong';
      showError('Failed', msg);
    } finally {
      setPhotoUploading(false);
    }
  };

  const handleSaveProfile = async () => {
    if (!fullName.trim()) { showWarning('Required', 'Full name is required'); return; }
    setSaving(true);
    try {
      await profileAPI.update({ full_name: fullName.trim(), company: company.trim() });
      await refreshProfile();
      showSuccess('Saved', 'Profile updated successfully');
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setConnStatus(null);
    try {
      // Test both Flask backend and Supabase in parallel
      const [backendResult, supabaseResult] = await Promise.allSettled([
        settingsAPI.testConnection(),
        supabase.from('leads_cache').select('count', { count: 'exact', head: true }),
      ]);

      const backendOk  = backendResult.status === 'fulfilled';
      const supabaseOk = supabaseResult.status === 'fulfilled' && !supabaseResult.value?.error;

      if (backendOk && supabaseOk) {
        setConnStatus({ ok: true, message: 'Backend (Flask) + Supabase both connected' });
      } else if (backendOk && !supabaseOk) {
        setConnStatus({ ok: false, message: 'Backend OK — Supabase connection failed. Check SUPABASE_URL / SUPABASE_ANON_KEY in app.json.' });
      } else if (!backendOk && supabaseOk) {
        setConnStatus({ ok: false, message: 'Supabase OK — Backend API unreachable. Is the Flask server running?' });
      } else {
        setConnStatus({ ok: false, message: 'Both connections failed. Check your network and server.' });
      }
    } catch (err) {
      setConnStatus({ ok: false, message: err?.message || 'Connection test failed' });
    } finally {
      setTesting(false);
    }
  };

  const handleLogout = () => {
    showConfirm('Sign Out', 'Are you sure you want to sign out?', logout, undefined, 'Sign Out', 'Cancel', 'danger');
  };

  const s = styles(theme);

  // ── Category grouping for integrations ────────────────────────────────────
  const CATEGORY_META = {
    lead_collection:   { label: 'Lead Collection',    color: COLORS.primary },
    enrichment:        { label: 'Data Enrichment',    color: COLORS.cyan    },
    web_search:        { label: 'Web Search',         color: '#f97316'      },
    email_verification:{ label: 'Email Verification', color: COLORS.green   },
    ai:                { label: 'AI Providers',       color: COLORS.amber   },
    social:            { label: 'Social & Developer', color: COLORS.purple  },
  };

  const integrationsByCategory = Object.entries(integrations).reduce((acc, [key, meta]) => {
    const cat = meta.category || 'other';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push([key, meta]);
    return acc;
  }, {});

  return (
    <View style={s.root}>
      {/* Scrollable Tabs */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={s.tabsScroll}
        contentContainerStyle={s.tabsContent}
      >
        {TABS.map(({ key, label }) => (
          <TouchableOpacity
            key={key}
            style={[s.tab, activeTab === key && s.tabActive]}
            onPress={() => setActiveTab(key)}
          >
            <Text style={[s.tabText, activeTab === key && s.tabTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <ScrollView contentContainerStyle={s.scroll}>

        {/* ══ PROFILE TAB ══ */}
        {activeTab === 'profile' && (
          <>
            <View style={s.avatarSection}>
              <TouchableOpacity onPress={handlePickPhoto} style={s.avatarWrap} disabled={photoUploading}>
                {photoUrl ? (
                  <Image source={{ uri: photoUrl }} style={s.avatarImg} />
                ) : (
                  <View style={s.avatar}>
                    <Text style={s.avatarText}>{(user?.full_name || user?.email || 'U')[0].toUpperCase()}</Text>
                  </View>
                )}
                <View style={s.avatarEditBadge}>
                  {photoUploading
                    ? <ActivityIndicator size={10} color="#fff" />
                    : <Ionicons name="camera" size={10} color="#fff" />}
                </View>
              </TouchableOpacity>
              <View>
                <Text style={s.userName}>{user?.full_name || 'User'}</Text>
                <Text style={s.userEmail}>{user?.email}</Text>
                <View style={s.roleBadge}>
                  <Text style={s.roleText}>{user?.role?.toUpperCase() || 'USER'}</Text>
                </View>
              </View>
            </View>

            <View style={s.card}>
              <Text style={s.cardTitle}>Edit Profile</Text>
              {[
                { label: 'Full Name', value: fullName, set: setFullName, icon: 'person-outline'   },
                { label: 'Company',   value: company,  set: setCompany,  icon: 'business-outline' },
              ].map(({ label, value, set, icon }) => (
                <View key={label} style={{ marginBottom: 12 }}>
                  <Text style={s.inputLabel}>{label}</Text>
                  <View style={s.inputRow}>
                    <Ionicons name={icon} size={16} color={theme.textMuted} style={{ marginRight: 8 }} />
                    <TextInput style={s.input} value={value} onChangeText={set} placeholderTextColor={theme.textMuted} />
                  </View>
                </View>
              ))}
              <TouchableOpacity style={[s.saveBtn, saving && { opacity: 0.7 }]} onPress={handleSaveProfile} disabled={saving}>
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveBtnText}>Save Changes</Text>}
              </TouchableOpacity>
            </View>

            <View style={s.card}>
              <Text style={s.cardTitle}>Backend Connection</Text>
              <TouchableOpacity style={[s.outlineBtn, testing && { opacity: 0.7 }]} onPress={handleTestConnection} disabled={testing}>
                {testing ? <ActivityIndicator size="small" color={COLORS.primary} /> : <Ionicons name="wifi" size={16} color={COLORS.primary} />}
                <Text style={[s.outlineBtnText, { color: COLORS.primary }]}>Test Connection</Text>
              </TouchableOpacity>
              {connStatus && (
                <View style={[s.connResult, { backgroundColor: connStatus.ok ? `${COLORS.green}18` : `${COLORS.red}18` }]}>
                  <Ionicons name={connStatus.ok ? 'checkmark-circle' : 'close-circle'} size={16} color={connStatus.ok ? COLORS.green : COLORS.red} />
                  <Text style={[s.connMsg, { color: connStatus.ok ? COLORS.green : COLORS.red }]}>{connStatus.message}</Text>
                </View>
              )}
            </View>

            <TouchableOpacity style={s.logoutBtn} onPress={handleLogout}>
              <Ionicons name="log-out-outline" size={18} color={COLORS.red} />
              <Text style={s.logoutText}>Sign Out</Text>
            </TouchableOpacity>
          </>
        )}

        {/* ══ NOTIFICATIONS TAB ══ */}
        {activeTab === 'notifications' && (
          <>
            {notifLoading ? (
              <ActivityIndicator color={COLORS.primary} style={{ marginTop: 40 }} />
            ) : (
              <View style={s.card}>
                <Text style={s.cardTitle}>Email Preferences</Text>
                <Text style={[s.cardDesc, { color: theme.textMuted }]}>Control which events trigger email notifications.</Text>
                {NOTIF_FIELDS.map(({ key, label }) => (
                  <View key={key} style={s.settingRow}>
                    <Text style={[s.settingLabel, { flex: 1, fontSize: 13 }]}>{label}</Text>
                    <Switch
                      value={!!notifSettings[key]}
                      onValueChange={(v) => setNotifSettings((p) => ({ ...p, [key]: v }))}
                      trackColor={{ false: theme.inputBorder, true: COLORS.primary }}
                      thumbColor="#fff"
                    />
                  </View>
                ))}
                <TouchableOpacity style={[s.saveBtn, { marginTop: 14 }, savingNotif && { opacity: 0.7 }]} onPress={handleSaveNotif} disabled={savingNotif}>
                  {savingNotif ? <ActivityIndicator color="#fff" /> : <Text style={s.saveBtnText}>Save Preferences</Text>}
                </TouchableOpacity>
              </View>
            )}

            {/* Push notification test */}
            <View style={[s.card, { marginTop: 12 }]}>
              <Text style={s.cardTitle}>Push Notifications</Text>
              <Text style={[s.cardDesc, { color: theme.textMuted }]}>
                Send a test notification to this device to verify delivery is working.
              </Text>
              <TouchableOpacity
                style={[s.saveBtn, { marginTop: 14, backgroundColor: COLORS.cyan }, testingPush && { opacity: 0.7 }]}
                onPress={handleTestPush}
                disabled={testingPush}
              >
                {testingPush
                  ? <ActivityIndicator color="#fff" />
                  : (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Ionicons name="notifications-outline" size={16} color="#fff" />
                      <Text style={s.saveBtnText}>Send Test Notification</Text>
                    </View>
                  )
                }
              </TouchableOpacity>
            </View>
          </>
        )}

        {/* ══ INTEGRATIONS TAB ══ */}
        {activeTab === 'integrations' && (
          <>
            {integrationsLoading ? (
              <ActivityIndicator color={COLORS.primary} style={{ marginTop: 40 }} />
            ) : Object.keys(integrations).length === 0 ? (
              <View style={s.emptyBox}>
                <Ionicons name="link-outline" size={44} color={theme.textMuted} />
                <Text style={[s.emptyTxt, { color: theme.textMuted }]}>No integrations found</Text>
              </View>
            ) : (
              <>
                {/* Summary */}
                {(() => {
                  const total  = Object.keys(integrations).length;
                  const active = Object.values(integrations).filter((v) => v.configured).length;
                  const color  = active >= 3 ? COLORS.green : active >= 1 ? COLORS.amber : COLORS.red;
                  return (
                    <View style={[s.summaryBanner, { backgroundColor: `${color}12`, borderColor: `${color}30` }]}>
                      <Ionicons name={active >= 3 ? 'checkmark-circle' : 'alert-circle'} size={18} color={color} />
                      <Text style={[s.summaryBannerText, { color }]}>{active} of {total} integrations active</Text>
                    </View>
                  );
                })()}

                {/* Categories */}
                {Object.entries(CATEGORY_META).map(([cat, catMeta]) => {
                  const entries = integrationsByCategory[cat];
                  if (!entries?.length) return null;
                  return (
                    <View key={cat}>
                      <View style={s.catHeader}>
                        <View style={[s.catDot, { backgroundColor: catMeta.color }]} />
                        <Text style={[s.catLabel, { color: catMeta.color }]}>{catMeta.label}</Text>
                      </View>
                      {entries.map(([envKey, meta]) => {
                        const op     = keyOps[envKey];
                        const isBusy = op === 'saving' || op === 'testing';
                        const hasVal = !!(inputValues[envKey] || '').trim();
                        return (
                          <View key={envKey} style={[s.integCard, meta.configured && s.integCardActive]}>
                            {/* Header */}
                            <View style={s.integHeader}>
                              <View style={{ flex: 1 }}>
                                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                  <Text style={s.integName}>{meta.label}</Text>
                                  <View style={[s.statusBadge, { backgroundColor: meta.configured ? `${COLORS.green}18` : `${theme.inputBorder}50` }]}>
                                    <View style={[s.statusDot, { backgroundColor: meta.configured ? COLORS.green : theme.textMuted }]} />
                                    <Text style={[s.statusTxt, { color: meta.configured ? COLORS.green : theme.textMuted }]}>
                                      {meta.configured ? 'Active' : 'Not set'}
                                    </Text>
                                  </View>
                                </View>
                                <Text style={s.integDesc} numberOfLines={2}>{meta.description}</Text>
                                {meta.free_tier ? <Text style={s.integFree}>{meta.free_tier}</Text> : null}
                                {meta.configured && meta.masked ? (
                                  <Text style={s.integMasked}>Current: {meta.masked}</Text>
                                ) : null}
                              </View>
                            </View>

                            {/* Input */}
                            <TextInput
                              style={[s.integInput, { backgroundColor: theme.input, borderColor: theme.inputBorder, color: theme.text }]}
                              value={inputValues[envKey] || ''}
                              onChangeText={(v) => setInputValues((p) => ({ ...p, [envKey]: v }))}
                              placeholder={meta.configured ? 'Paste new key to replace…' : 'Paste API key here…'}
                              placeholderTextColor={theme.textMuted}
                              secureTextEntry
                              autoCapitalize="none"
                              editable={!isBusy}
                            />

                            {/* Actions */}
                            <View style={s.integActions}>
                              <TouchableOpacity
                                style={[s.integBtn, { backgroundColor: COLORS.primary, flex: 1 }, (!hasVal || isBusy) && { opacity: 0.4 }]}
                                onPress={() => handleSaveIntegration(envKey)}
                                disabled={!hasVal || isBusy}
                              >
                                {op === 'saving'
                                  ? <ActivityIndicator size="small" color="#fff" />
                                  : <><Ionicons name="save-outline" size={13} color="#fff" /><Text style={s.integBtnText}>Save</Text></>
                                }
                              </TouchableOpacity>
                              <TouchableOpacity
                                style={[s.integBtn, { backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder, flex: 1 }, ((!hasVal && !meta.configured) || isBusy) && { opacity: 0.4 }]}
                                onPress={() => handleTestIntegration(envKey)}
                                disabled={(!hasVal && !meta.configured) || isBusy}
                              >
                                {op === 'testing'
                                  ? <ActivityIndicator size="small" color={COLORS.primary} />
                                  : <><Ionicons name="send-outline" size={13} color={COLORS.primary} /><Text style={[s.integBtnText, { color: COLORS.primary }]}>Test</Text></>
                                }
                              </TouchableOpacity>
                              {meta.configured && (
                                <TouchableOpacity
                                  style={[s.integBtn, { backgroundColor: `${COLORS.red}12`, borderWidth: 1, borderColor: `${COLORS.red}25` }, isBusy && { opacity: 0.4 }]}
                                  onPress={() => handleClearIntegration(envKey)}
                                  disabled={isBusy}
                                >
                                  <Ionicons name="trash-outline" size={14} color={COLORS.red} />
                                </TouchableOpacity>
                              )}
                            </View>
                          </View>
                        );
                      })}
                    </View>
                  );
                })}
              </>
            )}
          </>
        )}

        {/* ══ SYNC TAB ══ */}
        {activeTab === 'sync' && (
          <>
            {syncStatus && (
              <View style={s.card}>
                <Text style={s.cardTitle}>Sync Status</Text>
                <View style={s.syncStatRow}>
                  <Ionicons
                    name={syncStatus.supabase_configured ? 'cloud-done' : 'cloud-offline'}
                    size={20}
                    color={syncStatus.supabase_configured ? COLORS.green : COLORS.red}
                  />
                  <Text style={[s.syncStatTxt, { color: syncStatus.supabase_configured ? COLORS.green : COLORS.red }]}>
                    Supabase {syncStatus.supabase_configured ? 'Connected' : 'Not Configured'}
                  </Text>
                </View>
                {[
                  { label: 'Flask Users', value: syncStatus.flask_users },
                  { label: 'Flask Leads', value: syncStatus.flask_leads },
                ].map(({ label, value }) => (
                  <View key={label} style={s.metaRow}>
                    <Text style={s.metaLabel}>{label}</Text>
                    <Text style={s.metaValue}>{value}</Text>
                  </View>
                ))}
              </View>
            )}
            <View style={s.card}>
              <Text style={s.cardTitle}>Manual Sync</Text>
              <TouchableOpacity style={[s.syncBtn, syncing && { opacity: 0.6 }]} onPress={handleSyncLeads} disabled={syncing}>
                {syncing ? <ActivityIndicator color="#fff" /> : <Ionicons name="sync" size={16} color="#fff" />}
                <Text style={s.syncBtnText}>Sync Leads → Supabase</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.syncBtn, { backgroundColor: COLORS.cyan, marginTop: 8 }, syncing && { opacity: 0.6 }]} onPress={handleSyncUser} disabled={syncing}>
                {syncing ? <ActivityIndicator color="#fff" /> : <Ionicons name="person" size={16} color="#fff" />}
                <Text style={s.syncBtnText}>Sync My User → Supabase</Text>
              </TouchableOpacity>
            </View>
            {syncLogs.length > 0 && (
              <View style={s.card}>
                <Text style={s.cardTitle}>Recent Sync Activity</Text>
                {syncLogs.map((log, i) => (
                  <View key={i} style={s.logRow}>
                    <Ionicons
                      name={log.status === 'success' ? 'checkmark-circle' : 'alert-circle'}
                      size={14}
                      color={log.status === 'success' ? COLORS.green : COLORS.red}
                    />
                    <View style={{ flex: 1 }}>
                      <Text style={s.logTxt}>{log.operation} · {log.records} records</Text>
                      <Text style={s.logTime}>{log.created_at ? new Date(log.created_at).toLocaleString() : ''}</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}
          </>
        )}

        {/* ══ API KEYS TAB ══ */}
        {activeTab === 'apikeys' && (
          <>
            <View style={s.card}>
              <Text style={s.cardTitle}>Personal API Key</Text>
              {personalKey?.has_key ? (
                <>
                  <View style={[s.keyBox, { backgroundColor: theme.input, borderColor: theme.inputBorder }]}>
                    <Text style={[s.keyText, { color: theme.text }]} numberOfLines={1}>{personalKey.masked || '••••••••••••••••'}</Text>
                  </View>
                  <Text style={[s.metaLabel, { marginTop: 6 }]}>Key is active — regenerate to get a new one</Text>
                </>
              ) : (
                <Text style={s.metaLabel}>No personal key generated yet.</Text>
              )}
              <TouchableOpacity style={[s.outlineBtn, { marginTop: 10 }]} onPress={handleRegeneratePersonal}>
                <Ionicons name="refresh" size={15} color={COLORS.amber} />
                <Text style={[s.outlineBtnText, { color: COLORS.amber }]}>Regenerate</Text>
              </TouchableOpacity>
            </View>
            <View style={s.card}>
              <Text style={s.cardTitle}>Team API Keys</Text>
              <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: COLORS.amber + '15', borderRadius: 8, padding: 10, marginBottom: 12 }}>
                <Ionicons name="time-outline" size={15} color={COLORS.amber} style={{ marginTop: 1 }} />
                <Text style={{ flex: 1, fontSize: 12, color: COLORS.amber, lineHeight: 18 }}>
                  Team keys are reserved for future webhook integrations (Zapier, Make.com, landing pages). Use your Personal API Key above for current API access.
                </Text>
              </View>
              <View style={[s.inputRow, { marginBottom: 10 }]}>
                <Ionicons name="key-outline" size={16} color={theme.textMuted} style={{ marginRight: 8 }} />
                <TextInput
                  style={s.input}
                  value={newKeyName}
                  onChangeText={setNewKeyName}
                  placeholder="Key name (e.g. Zapier Integration)"
                  placeholderTextColor={theme.textMuted}
                />
              </View>
              <TouchableOpacity style={[s.saveBtn, creatingKey && { opacity: 0.6 }]} onPress={handleCreateKey} disabled={creatingKey}>
                {creatingKey ? <ActivityIndicator color="#fff" /> : <Text style={s.saveBtnText}>Create Key</Text>}
              </TouchableOpacity>
              {keysLoading ? (
                <ActivityIndicator color={COLORS.primary} style={{ marginTop: 16 }} />
              ) : apiKeys.length === 0 ? (
                <Text style={[s.metaLabel, { marginTop: 12, textAlign: 'center' }]}>No API keys yet.</Text>
              ) : (
                apiKeys.map((key) => (
                  <View key={key.id} style={[s.metaRow, { alignItems: 'flex-start' }]}>
                    <View style={{ flex: 1 }}>
                      <Text style={[s.metaValue, { fontSize: 14 }]}>{key.name}</Text>
                      <Text style={s.metaLabel}>{key.key ? key.key.slice(0, 18) + '…' : '••••••••••'}</Text>
                    </View>
                    <TouchableOpacity onPress={() => handleDeleteKey(key)}>
                      <Ionicons name="trash-outline" size={17} color={COLORS.red} />
                    </TouchableOpacity>
                  </View>
                ))
              )}
            </View>
          </>
        )}

        {/* ══ APP TAB ══ */}
        {activeTab === 'app' && (
          <>
            <View style={s.card}>
              <Text style={s.cardTitle}>Appearance</Text>
              <View style={s.settingRow}>
                <View style={s.settingLeft}>
                  <Ionicons name={isDark ? 'moon' : 'sunny'} size={18} color={isDark ? COLORS.purple : COLORS.amber} />
                  <Text style={s.settingLabel}>Dark Mode</Text>
                </View>
                <Switch
                  value={isDark}
                  onValueChange={toggleTheme}
                  trackColor={{ false: theme.inputBorder, true: COLORS.primary }}
                  thumbColor="#fff"
                />
              </View>
            </View>
            <View style={s.card}>
              <Text style={s.cardTitle}>About</Text>
              {[
                { label: 'Version',  value: '1.0.0'                   },
                { label: 'Backend',  value: 'Flask API'               },
                { label: 'Database', value: 'Supabase + PostgreSQL'   },
                { label: 'AI Engine',value: 'Gemini 2.5 Flash'        },
              ].map(({ label, value }) => (
                <View key={label} style={s.metaRow}>
                  <Text style={s.metaLabel}>{label}</Text>
                  <Text style={s.metaValue}>{value}</Text>
                </View>
              ))}
            </View>
          </>
        )}

      </ScrollView>

      {/* ── Photo Action Sheet (Android) ── */}
      <Modal
        visible={showPhotoSheet}
        transparent
        animationType="slide"
        onRequestClose={() => setShowPhotoSheet(false)}
      >
        <TouchableOpacity
          style={s.sheetOverlay}
          activeOpacity={1}
          onPress={() => setShowPhotoSheet(false)}
        >
          <View style={[s.sheet, { backgroundColor: theme.card }]}>
            {/* Handle bar */}
            <View style={s.sheetHandle} />

            {/* Title */}
            <Text style={[s.sheetTitle, { color: theme.text }]}>Profile Photo</Text>
            <Text style={[s.sheetSubtitle, { color: theme.textMuted }]}>Choose how to update your photo</Text>

            <View style={[s.sheetDivider, { backgroundColor: theme.cardBorder }]} />

            {/* Options */}
            {[
              { idx: 0, icon: 'camera',        label: 'Take Photo',           color: COLORS.primary },
              { idx: 1, icon: 'images',         label: 'Choose from Library',  color: COLORS.cyan    },
            ].map(({ idx, icon, label, color }) => (
              <TouchableOpacity
                key={idx}
                style={s.sheetOption}
                onPress={() => { setShowPhotoSheet(false); setTimeout(() => _handlePhotoAction(idx), 200); }}
                activeOpacity={0.7}
              >
                <View style={[s.sheetIconWrap, { backgroundColor: `${color}15` }]}>
                  <Ionicons name={icon} size={20} color={color} />
                </View>
                <Text style={[s.sheetOptionText, { color: theme.text }]}>{label}</Text>
                <Ionicons name="chevron-forward" size={16} color={theme.textMuted} />
              </TouchableOpacity>
            ))}

            {photoUrl && (
              <TouchableOpacity
                style={s.sheetOption}
                onPress={() => { setShowPhotoSheet(false); setTimeout(() => _handlePhotoAction(2), 200); }}
                activeOpacity={0.7}
              >
                <View style={[s.sheetIconWrap, { backgroundColor: `${COLORS.red}15` }]}>
                  <Ionicons name="trash" size={20} color={COLORS.red} />
                </View>
                <Text style={[s.sheetOptionText, { color: COLORS.red }]}>Remove Photo</Text>
                <Ionicons name="chevron-forward" size={16} color={COLORS.red} />
              </TouchableOpacity>
            )}

            {/* Cancel button */}
            <TouchableOpacity
              style={[s.sheetCancel, { backgroundColor: theme.input, borderColor: theme.inputBorder }]}
              onPress={() => setShowPhotoSheet(false)}
              activeOpacity={0.7}
            >
              <Text style={[s.sheetCancelText, { color: theme.textSecondary }]}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = (theme) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  scroll: { padding: 16, paddingBottom: 100 },

  /* ── Scrollable Tabs ── */
  tabsScroll:   { backgroundColor: theme.card, borderBottomWidth: 1, borderBottomColor: theme.cardBorder, flexGrow: 0 },
  tabsContent:  { paddingHorizontal: 10, paddingVertical: 8, gap: 4 },
  tab:          { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 10 },
  tabActive:    { backgroundColor: COLORS.primary },
  tabText:      { fontSize: 12, fontWeight: '600', color: theme.textMuted },
  tabTextActive:{ color: '#fff', fontWeight: '700' },

  /* ── Avatar ── */
  avatarSection: { flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: 16, padding: 4 },
  avatarWrap: { position: 'relative' },
  avatar: {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: COLORS.primary,
    alignItems: 'center', justifyContent: 'center',
    shadowColor: COLORS.primary, shadowOpacity: 0.35,
    shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 5,
  },
  avatarImg: {
    width: 64, height: 64, borderRadius: 32,
    shadowColor: '#000', shadowOpacity: 0.2,
    shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 5,
  },
  avatarEditBadge: {
    position: 'absolute', bottom: 0, right: 0,
    width: 20, height: 20, borderRadius: 10,
    backgroundColor: COLORS.primary,
    alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: '#fff',
  },
  avatarText: { fontSize: 26, fontWeight: '800', color: '#fff' },
  userName:   { fontSize: 17, fontWeight: '800', color: theme.text },
  userEmail:  { fontSize: 12, color: theme.textMuted, marginTop: 3 },
  roleBadge:  { backgroundColor: `${COLORS.primary}18`, borderRadius: 20, paddingHorizontal: 11, paddingVertical: 3, alignSelf: 'flex-start', marginTop: 6, borderWidth: 1, borderColor: `${COLORS.primary}28` },
  roleText:   { fontSize: 10, fontWeight: '700', color: COLORS.primary },

  /* ── Card ── */
  card: {
    backgroundColor: theme.card, borderRadius: 18,
    padding: 16, marginBottom: 14,
    borderWidth: 1, borderColor: theme.cardBorder,
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2,
  },
  cardTitle: { fontSize: 14, fontWeight: '700', color: theme.text, marginBottom: 14 },
  cardDesc:  { fontSize: 12, lineHeight: 18, marginBottom: 10 },

  /* ── Inputs ── */
  inputLabel: { fontSize: 12, fontWeight: '600', color: theme.textSecondary, marginBottom: 6 },
  inputRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: theme.input, borderRadius: 14,
    borderWidth: 1, borderColor: theme.inputBorder,
    paddingHorizontal: 14, height: 48,
  },
  input: { flex: 1, color: theme.text, fontSize: 14 },

  /* ── Buttons ── */
  saveBtn: {
    backgroundColor: COLORS.primary, borderRadius: 14,
    height: 48, alignItems: 'center', justifyContent: 'center', marginTop: 6,
    shadowColor: COLORS.primary, shadowOpacity: 0.3,
    shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 4,
  },
  saveBtnText: { color: '#fff', fontSize: 14, fontWeight: '800' },

  outlineBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    borderWidth: 1, borderColor: COLORS.primary,
    borderRadius: 12, paddingHorizontal: 16, paddingVertical: 10,
    alignSelf: 'flex-start',
  },
  outlineBtnText: { fontSize: 13, fontWeight: '700' },
  connResult: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, padding: 12, borderRadius: 12 },
  connMsg:    { fontSize: 13, fontWeight: '500', flex: 1 },

  logoutBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
    backgroundColor: 'rgba(239,68,68,0.08)', borderRadius: 16,
    paddingVertical: 14, marginTop: 4,
    borderWidth: 1, borderColor: 'rgba(239,68,68,0.18)',
  },
  logoutText: { fontSize: 15, fontWeight: '700', color: COLORS.red },

  /* ── Notifications ── */
  settingRow:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  settingLeft:  { flexDirection: 'row', alignItems: 'center', gap: 10 },
  settingLabel: { fontSize: 15, color: theme.text, fontWeight: '500' },

  /* ── Integrations ── */
  summaryBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    borderWidth: 1, borderRadius: 14, padding: 14, marginBottom: 16,
  },
  summaryBannerText: { fontSize: 13, fontWeight: '600' },
  catHeader:  { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8, marginTop: 8 },
  catDot:     { width: 8, height: 8, borderRadius: 4 },
  catLabel:   { fontSize: 12, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 },

  integCard: {
    backgroundColor: theme.card, borderRadius: 16,
    padding: 14, marginBottom: 10,
    borderWidth: 1, borderColor: theme.cardBorder,
  },
  integCardActive: { borderColor: 'rgba(34,197,94,0.35)' },
  integHeader: { flexDirection: 'row', marginBottom: 10 },
  integName:   { fontSize: 14, fontWeight: '700', color: theme.text },
  integDesc:   { fontSize: 12, color: theme.textMuted, marginTop: 3, lineHeight: 17 },
  integFree:   { fontSize: 11, color: COLORS.green, fontWeight: '600', marginTop: 4 },
  integMasked: { fontSize: 11, color: theme.textMuted, fontFamily: 'monospace', marginTop: 4, letterSpacing: 1 },

  statusBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, borderRadius: 20, paddingHorizontal: 7, paddingVertical: 2 },
  statusDot:   { width: 5, height: 5, borderRadius: 3 },
  statusTxt:   { fontSize: 10, fontWeight: '700' },

  integInput: {
    borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9,
    fontSize: 13, marginBottom: 10,
  },
  integActions: { flexDirection: 'row', gap: 8 },
  integBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 5, paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10,
  },
  integBtnText: { fontSize: 12, fontWeight: '700', color: '#fff' },

  emptyBox: { alignItems: 'center', paddingTop: 60, gap: 8 },
  emptyTxt:  { fontSize: 15, fontWeight: '600', marginTop: 8 },

  /* ── Sync ── */
  syncStatRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 },
  syncStatTxt: { fontSize: 14, fontWeight: '600' },
  syncBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: COLORS.primary, borderRadius: 14, height: 46,
  },
  syncBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },

  logRow:  { flexDirection: 'row', gap: 8, alignItems: 'flex-start', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  logTxt:  { fontSize: 12, color: theme.textSecondary },
  logTime: { fontSize: 11, color: theme.textMuted, marginTop: 2 },

  /* ── Meta rows ── */
  metaRow:   { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  metaLabel: { fontSize: 13, color: theme.textMuted },
  metaValue: { fontSize: 13, color: theme.text, fontWeight: '500' },

  keyBox:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 11 },
  keyText: { flex: 1, fontSize: 13, fontFamily: 'monospace', marginRight: 8 },

  /* ── Photo Action Sheet ── */
  sheetOverlay:    { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  sheet:           { borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 36 },
  sheetHandle:     { width: 40, height: 4, borderRadius: 2, backgroundColor: 'rgba(150,150,150,0.35)', alignSelf: 'center', marginBottom: 18 },
  sheetTitle:      { fontSize: 17, fontWeight: '800', textAlign: 'center', marginBottom: 4 },
  sheetSubtitle:   { fontSize: 13, textAlign: 'center', marginBottom: 16 },
  sheetDivider:    { height: 1, marginBottom: 8 },
  sheetOption:     { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 4, gap: 14 },
  sheetIconWrap:   { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  sheetOptionText: { flex: 1, fontSize: 15, fontWeight: '600' },
  sheetCancel:     { marginTop: 10, height: 52, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  sheetCancelText: { fontSize: 15, fontWeight: '700' },
});
