import React, { useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  Modal, Linking, Platform, TextInput, ActivityIndicator, Image,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { authAPI, profileAPI } from '../services/api';
import { showError, showSuccess, showWarning, showInfo, showConfirm } from '../utils/dialog';

const APP_VERSION = '1.0.0';
const SUPPORT_EMAIL = 'support@orionlead.ai';

export default function ProfileScreen({ navigation }) {
  const { theme, isDark, toggleTheme } = useTheme();
  const { user, logout, isAdmin, isManager, refreshProfile } = useAuth();
  const s = styles(theme, isDark);

  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [appearanceVisible, setAppearanceVisible] = useState(false);
  const [aboutVisible, setAboutVisible]           = useState(false);
  const [helpVisible, setHelpVisible]             = useState(false);
  const [securityVisible, setSecurityVisible]     = useState(false);

  // Change-password form state
  const [currentPass, setCurrentPass] = useState('');
  const [newPass,     setNewPass]     = useState('');
  const [confirmPass, setConfirmPass] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew,     setShowNew]     = useState(false);
  const [showConfirmPass, setShowConfirmPass] = useState(false);
  const [changingPass, setChangingPass] = useState(false);

  const roleMeta = {
    admin:   { label: 'Administrator', color: COLORS.amber },
    manager: { label: 'Manager',       color: COLORS.primary },
    user:    { label: 'User',          color: COLORS.green },
  };
  const role = roleMeta[user?.role] || roleMeta.user;

  const handlePhotoTap = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      showWarning('Permission Required', 'Please allow photo library access to change your profile picture.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.7,
    });
    if (result.canceled) return;
    try {
      setUploadingPhoto(true);
      const asset = result.assets[0];
      const form = new FormData();
      form.append('photo', { uri: asset.uri, name: 'photo.jpg', type: 'image/jpeg' });
      await profileAPI.uploadPhoto(form);
      await refreshProfile();
    } catch (err) {
      showError('Upload Failed', err?.response?.data?.message || 'Could not upload photo.');
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handleLogout = () => {
    showConfirm('Sign Out', 'Are you sure you want to sign out?', logout, undefined, 'Sign Out', 'Cancel', 'danger');
  };

  const handleItem = (item) => {
    if (item.action === 'appearance') { setAppearanceVisible(true); return; }
    if (item.action === 'about')      { setAboutVisible(true);      return; }
    if (item.action === 'help')       { setHelpVisible(true);       return; }
    if (item.action === 'security')   { setSecurityVisible(true);   return; }
    if (item.tab)                     { navigation.navigate(item.tab, item.params || {}); }
  };

  const handleChangePassword = async () => {
    if (!currentPass || !newPass || !confirmPass) {
      showWarning('Required', 'Please fill in all password fields.'); return;
    }
    if (newPass.length < 8) {
      showWarning('Weak Password', 'New password must be at least 8 characters.'); return;
    }
    if (newPass !== confirmPass) {
      showWarning('Mismatch', 'New password and confirmation do not match.'); return;
    }
    try {
      setChangingPass(true);
      await authAPI.changePassword(currentPass, newPass);
      setCurrentPass(''); setNewPass(''); setConfirmPass('');
      setSecurityVisible(false);
      showSuccess('Password Changed', 'Your password has been updated successfully.');
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to change password.');
    } finally {
      setChangingPass(false);
    }
  };

  const MENU_ITEMS = [
    {
      section: 'Account',
      items: [
        { icon: 'person-outline',           label: 'Edit Profile',  tab: 'Settings', params: { initialTab: 'profile'  }, tint: COLORS.primary },
        { icon: 'sync-outline',             label: 'Sync Settings', tab: 'Settings', params: { initialTab: 'sync'     }, tint: COLORS.cyan },
        { icon: 'shield-checkmark-outline', label: 'Security',      action: 'security', tint: COLORS.green },
      ],
    },
    {
      section: 'App',
      items: [
        { icon: 'moon-outline',             label: 'Appearance',    action: 'appearance', tint: COLORS.purple },
        { icon: 'help-circle-outline',      label: 'Help & Support',action: 'help',       tint: COLORS.amber },
        { icon: 'information-circle-outline',label: 'About',        action: 'about',      tint: COLORS.textMuted || '#64748b' },
      ],
    },
  ];

  return (
    <ScrollView style={s.root} contentContainerStyle={s.scroll}>

      {/* ── Profile Card ─────────────────────────────────────────── */}
      <View style={s.profileCard}>
        <TouchableOpacity onPress={handlePhotoTap} activeOpacity={0.8} style={s.avatarRing}>
          {user?.profile_photo_url ? (
            <Image source={{ uri: user.profile_photo_url }} style={s.avatar} />
          ) : (
            <View style={[s.avatar, { backgroundColor: role.color }]}>
              <Text style={s.avatarText}>
                {(user?.full_name || user?.email || 'U')[0].toUpperCase()}
              </Text>
            </View>
          )}
          {uploadingPhoto && (
            <View style={s.avatarOverlay}>
              <ActivityIndicator color="#fff" />
            </View>
          )}
          <View style={s.cameraChip}>
            <Ionicons name="camera" size={11} color="#fff" />
          </View>
        </TouchableOpacity>
        <Text style={s.name}>{user?.full_name || 'User'}</Text>
        <Text style={s.email}>{user?.email || '—'}</Text>
        {user?.company ? <Text style={s.company}>{user.company}</Text> : null}
        <View style={[s.roleBadge, { backgroundColor: `${role.color}18`, borderColor: `${role.color}30` }]}>
          <View style={[s.roleDot, { backgroundColor: role.color }]} />
          <Text style={[s.roleText, { color: role.color }]}>{role.label}</Text>
        </View>
      </View>

      {/* ── Stats Row ────────────────────────────────────────────── */}
      <View style={s.statsRow}>
        {[
          { label: 'Role',   value: user?.role || 'user' },
          { label: 'Access', value: isAdmin ? 'Full' : isManager ? 'Manager' : 'Basic' },
          { label: 'Status', value: 'Active' },
        ].map((st, idx) => (
          <View key={st.label} style={[s.statCell, idx < 2 && { borderRightWidth: 1, borderRightColor: theme.cardBorder }]}>
            <Text style={s.statVal}>{st.value}</Text>
            <Text style={s.statLbl}>{st.label}</Text>
          </View>
        ))}
      </View>

      {/* ── Menu Sections ────────────────────────────────────────── */}
      {MENU_ITEMS.map((section) => (
        <View key={section.section} style={s.section}>
          <Text style={s.sectionTitle}>{section.section}</Text>
          <View style={s.sectionCard}>
            {section.items.map((item, idx) => (
              <TouchableOpacity
                key={item.label}
                style={[s.menuRow, idx < section.items.length - 1 && s.menuRowBorder]}
                onPress={() => handleItem(item)}
                activeOpacity={0.6}
              >
                <View style={[s.menuIcon, { backgroundColor: `${item.tint}15` }]}>
                  <Ionicons name={item.icon} size={18} color={item.tint} />
                </View>
                <Text style={s.menuLabel}>{item.label}</Text>
                {item.action === 'appearance' && (
                  <View style={[s.themeChip, { backgroundColor: `${COLORS.purple}15` }]}>
                    <Text style={[s.themeChipText, { color: COLORS.purple }]}>
                      {isDark ? 'Dark' : 'Light'}
                    </Text>
                  </View>
                )}
                <View style={s.chevronBox}>
                  <Ionicons name="chevron-forward" size={14} color={theme.textMuted} />
                </View>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ))}

      {/* ── Sign Out ─────────────────────────────────────────────── */}
      <TouchableOpacity style={s.logoutBtn} onPress={handleLogout} activeOpacity={0.8}>
        <Ionicons name="log-out-outline" size={18} color={COLORS.red} />
        <Text style={s.logoutText}>Sign Out</Text>
      </TouchableOpacity>

      <Text style={s.version}>OrionLead AI · v{APP_VERSION}</Text>

      {/* ════════════════════════════════════════════════════════════
          SECURITY MODAL
      ════════════════════════════════════════════════════════════ */}
      <Modal visible={securityVisible} transparent animationType="slide" onRequestClose={() => setSecurityVisible(false)}>
        <View style={s.overlay}>
          <View style={[s.sheet, { backgroundColor: theme.card }]}>
            <View style={s.sheetHandle} />
            <Text style={[s.sheetTitle, { color: theme.text }]}>Security</Text>
            <Text style={[s.sheetSub, { color: theme.textMuted }]}>Change your account password</Text>

            {[
              { label: 'Current Password', value: currentPass, set: setCurrentPass, show: showCurrent, toggle: () => setShowCurrent(v => !v) },
              { label: 'New Password',     value: newPass,     set: setNewPass,     show: showNew,     toggle: () => setShowNew(v => !v) },
              { label: 'Confirm New Password', value: confirmPass, set: setConfirmPass, show: showConfirmPass, toggle: () => setShowConfirmPass(v => !v) },
            ].map(({ label, value, set, show, toggle }) => (
              <View key={label} style={{ marginBottom: 12 }}>
                <Text style={[s.secLabel, { color: theme.textMuted }]}>{label}</Text>
                <View style={[s.secInputRow, { backgroundColor: theme.input, borderColor: theme.inputBorder }]}>
                  <Ionicons name="lock-closed-outline" size={16} color={theme.textMuted} style={{ marginRight: 8 }} />
                  <TextInput
                    style={[s.secInput, { color: theme.text }]}
                    value={value}
                    onChangeText={set}
                    secureTextEntry={!show}
                    placeholder="••••••••"
                    placeholderTextColor={theme.textMuted}
                    autoCapitalize="none"
                  />
                  <TouchableOpacity onPress={toggle} style={{ padding: 4 }}>
                    <Ionicons name={show ? 'eye-off-outline' : 'eye-outline'} size={16} color={theme.textMuted} />
                  </TouchableOpacity>
                </View>
              </View>
            ))}

            {newPass.length > 0 && (
              <View style={[s.strengthRow, { backgroundColor: theme.input, borderColor: theme.inputBorder }]}>
                {[
                  { check: newPass.length >= 8,          label: '8+ chars'     },
                  { check: /[A-Z]/.test(newPass),        label: 'Uppercase'    },
                  { check: /[0-9]/.test(newPass),        label: 'Number'       },
                  { check: /[^A-Za-z0-9]/.test(newPass), label: 'Special char' },
                ].map(({ check, label }) => (
                  <View key={label} style={s.strengthItem}>
                    <Ionicons name={check ? 'checkmark-circle' : 'ellipse-outline'} size={13} color={check ? COLORS.green : theme.textMuted} />
                    <Text style={[s.strengthTxt, { color: check ? COLORS.green : theme.textMuted }]}>{label}</Text>
                  </View>
                ))}
              </View>
            )}

            <TouchableOpacity
              style={[s.sheetSaveBtn, changingPass && { opacity: 0.7 }]}
              onPress={handleChangePassword}
              disabled={changingPass}
            >
              {changingPass
                ? <ActivityIndicator color="#fff" />
                : <><Ionicons name="shield-checkmark-outline" size={16} color="#fff" /><Text style={s.sheetSaveBtnTxt}>Update Password</Text></>
              }
            </TouchableOpacity>

            <TouchableOpacity style={[s.sheetClose, { backgroundColor: theme.input }]} onPress={() => {
              setSecurityVisible(false);
              setCurrentPass(''); setNewPass(''); setConfirmPass('');
            }}>
              <Text style={[s.sheetCloseTxt, { color: theme.text }]}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* ════════════════════════════════════════════════════════════
          APPEARANCE MODAL
      ════════════════════════════════════════════════════════════ */}
      <Modal visible={appearanceVisible} transparent animationType="slide" onRequestClose={() => setAppearanceVisible(false)}>
        <View style={s.overlay}>
          <View style={[s.sheet, { backgroundColor: theme.card }]}>
            <View style={s.sheetHandle} />
            <Text style={[s.sheetTitle, { color: theme.text }]}>Appearance</Text>
            <Text style={[s.sheetSub, { color: theme.textMuted }]}>Choose your preferred theme</Text>

            {[
              { label: 'Light Mode',  value: false, icon: 'sunny-outline',  desc: 'White background, dark text' },
              { label: 'Dark Mode',   value: true,  icon: 'moon-outline',   desc: 'Dark background, light text' },
            ].map(({ label, value, icon, desc }) => {
              const active = isDark === value;
              return (
                <TouchableOpacity
                  key={label}
                  style={[s.themeOption, active && { borderColor: COLORS.purple, backgroundColor: `${COLORS.purple}10` }]}
                  onPress={() => { if (!active) toggleTheme(); }}
                  activeOpacity={0.7}
                >
                  <View style={[s.themeIconBox, { backgroundColor: active ? `${COLORS.purple}20` : theme.input }]}>
                    <Ionicons name={icon} size={22} color={active ? COLORS.purple : theme.textMuted} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[s.themeOptionLabel, { color: active ? COLORS.purple : theme.text }]}>{label}</Text>
                    <Text style={[s.themeOptionDesc, { color: theme.textMuted }]}>{desc}</Text>
                  </View>
                  {active && <Ionicons name="checkmark-circle" size={22} color={COLORS.purple} />}
                </TouchableOpacity>
              );
            })}

            <TouchableOpacity style={[s.sheetClose, { backgroundColor: theme.input }]} onPress={() => setAppearanceVisible(false)}>
              <Text style={[s.sheetCloseTxt, { color: theme.text }]}>Done</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* ════════════════════════════════════════════════════════════
          ABOUT MODAL
      ════════════════════════════════════════════════════════════ */}
      <Modal visible={aboutVisible} transparent animationType="slide" onRequestClose={() => setAboutVisible(false)}>
        <View style={s.overlay}>
          <View style={[s.sheet, { backgroundColor: theme.card }]}>
            <View style={s.sheetHandle} />
            <Text style={[s.sheetTitle, { color: theme.text }]}>About OrionLead AI</Text>

            <View style={[s.aboutLogoBox, { backgroundColor: `${COLORS.primary}15` }]}>
              <Ionicons name="flash" size={40} color={COLORS.primary} />
            </View>

            {[
              { label: 'App Name',    value: 'OrionLead AI' },
              { label: 'Version',     value: `v${APP_VERSION}` },
              { label: 'Platform',    value: Platform.OS === 'ios' ? 'iOS' : 'Android' },
              { label: 'Developer',   value: 'Ali Jradeh' },
              { label: 'University',  value: 'Islamic University of Lebanon' },
              { label: 'Supervisor',  value: 'Dr. Mohammad Alawwan' },
            ].map(({ label, value }) => (
              <View key={label} style={[s.aboutRow, { borderBottomColor: theme.cardBorder }]}>
                <Text style={[s.aboutLabel, { color: theme.textMuted }]}>{label}</Text>
                <Text style={[s.aboutValue, { color: theme.text }]}>{value}</Text>
              </View>
            ))}

            <Text style={[s.aboutDesc, { color: theme.textSecondary }]}>
              AI-powered B2B lead generation and qualification platform. Collects, enriches, and scores leads using a 4-layer AI cascade.
            </Text>

            <TouchableOpacity style={[s.sheetClose, { backgroundColor: theme.input }]} onPress={() => setAboutVisible(false)}>
              <Text style={[s.sheetCloseTxt, { color: theme.text }]}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* ════════════════════════════════════════════════════════════
          HELP & SUPPORT MODAL
      ════════════════════════════════════════════════════════════ */}
      <Modal visible={helpVisible} transparent animationType="slide" onRequestClose={() => setHelpVisible(false)}>
        <View style={s.overlay}>
          <View style={[s.sheet, { backgroundColor: theme.card }]}>
            <View style={s.sheetHandle} />
            <Text style={[s.sheetTitle, { color: theme.text }]}>Help & Support</Text>
            <Text style={[s.sheetSub, { color: theme.textMuted }]}>How can we help you?</Text>

            {[
              {
                icon: 'mail-outline',
                label: 'Email Support',
                desc: SUPPORT_EMAIL,
                color: COLORS.primary,
                onPress: () => Linking.openURL(`mailto:${SUPPORT_EMAIL}?subject=OrionLead AI Support`),
              },
              {
                icon: 'chatbubble-outline',
                label: 'Report a Bug',
                desc: 'Send us details about the issue',
                color: COLORS.amber,
                onPress: () => Linking.openURL(`mailto:${SUPPORT_EMAIL}?subject=Bug Report - OrionLead AI v${APP_VERSION}`),
              },
              {
                icon: 'document-text-outline',
                label: 'Documentation',
                desc: 'View guides and API reference',
                color: COLORS.cyan,
                onPress: () => showInfo('Documentation', 'Documentation is available in the web dashboard under Help → Docs.'),
              },
              {
                icon: 'refresh-circle-outline',
                label: 'Clear App Cache',
                desc: 'Reset local data and reload',
                color: COLORS.red,
                onPress: () => showConfirm(
                  'Clear Cache',
                  'This will clear locally cached data. Your account and leads data will not be affected.',
                  () => showSuccess('Done', 'Cache cleared.'),
                  undefined, 'Clear', 'Cancel', 'danger',
                ),
              },
            ].map(({ icon, label, desc, color, onPress }) => (
              <TouchableOpacity key={label} style={[s.helpRow, { borderBottomColor: theme.cardBorder }]} onPress={onPress} activeOpacity={0.7}>
                <View style={[s.helpIcon, { backgroundColor: `${color}15` }]}>
                  <Ionicons name={icon} size={20} color={color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[s.helpLabel, { color: theme.text }]}>{label}</Text>
                  <Text style={[s.helpDesc, { color: theme.textMuted }]}>{desc}</Text>
                </View>
                <Ionicons name="chevron-forward" size={14} color={theme.textMuted} />
              </TouchableOpacity>
            ))}

            <View style={[s.faqBox, { backgroundColor: theme.input }]}>
              <Text style={[s.faqTitle, { color: theme.text }]}>Quick FAQ</Text>
              {[
                { q: 'How do I qualify a lead?', a: 'Open the lead and tap "Re-qualify with AI".' },
                { q: 'Why is my data not syncing?', a: 'Check Settings → Sync tab, then tap "Sync Now".' },
                { q: 'How do I change my password?', a: 'Go to Settings → Security tab.' },
              ].map(({ q, a }) => (
                <View key={q} style={s.faqItem}>
                  <Text style={[s.faqQ, { color: theme.text }]}>{q}</Text>
                  <Text style={[s.faqA, { color: theme.textMuted }]}>{a}</Text>
                </View>
              ))}
            </View>

            <TouchableOpacity style={[s.sheetClose, { backgroundColor: theme.input }]} onPress={() => setHelpVisible(false)}>
              <Text style={[s.sheetCloseTxt, { color: theme.text }]}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

    </ScrollView>
  );
}

const styles = (theme, isDark) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  scroll: { padding: 16, paddingBottom: 40 },

  /* Profile Card */
  profileCard: {
    backgroundColor: theme.card, borderRadius: 22, padding: 28,
    alignItems: 'center', marginBottom: 12,
    borderWidth: 1, borderColor: theme.cardBorder,
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 }, elevation: 3,
  },
  avatarRing: {
    padding: 4, borderRadius: 44, borderWidth: 2,
    borderColor: `${COLORS.primary}50`, marginBottom: 16,
    shadowColor: COLORS.primary, shadowOpacity: 0.25,
    shadowRadius: 10, shadowOffset: { width: 0, height: 3 }, elevation: 4,
  },
  avatar:     { width: 76, height: 76, borderRadius: 38, alignItems: 'center', justifyContent: 'center' },
  avatarText:    { fontSize: 32, fontWeight: '800', color: '#fff' },
  avatarOverlay: { ...StyleSheet.absoluteFillObject, borderRadius: 38, backgroundColor: 'rgba(0,0,0,0.45)', alignItems: 'center', justifyContent: 'center' },
  cameraChip:    { position: 'absolute', bottom: -2, right: -2, width: 24, height: 24, borderRadius: 12, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: '#fff' },
  name:       { fontSize: 21, fontWeight: '800', color: theme.text, marginBottom: 4, letterSpacing: 0.1 },
  email:      { fontSize: 13, color: theme.textMuted, marginBottom: 4 },
  company:    { fontSize: 13, color: theme.textSecondary, marginBottom: 8 },
  roleBadge:  { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 5, borderRadius: 20, borderWidth: 1, marginTop: 6 },
  roleDot:    { width: 6, height: 6, borderRadius: 3 },
  roleText:   { fontSize: 12, fontWeight: '700' },

  /* Stats */
  statsRow: {
    flexDirection: 'row', backgroundColor: theme.card, borderRadius: 18,
    marginBottom: 16, borderWidth: 1, borderColor: theme.cardBorder, overflow: 'hidden',
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2,
  },
  statCell: { flex: 1, alignItems: 'center', paddingVertical: 16 },
  statVal:  { fontSize: 14, fontWeight: '800', color: theme.text, textTransform: 'capitalize' },
  statLbl:  { fontSize: 11, color: theme.textMuted, marginTop: 3, fontWeight: '600' },

  /* Menu */
  section:      { marginBottom: 16 },
  sectionTitle: { fontSize: 11, fontWeight: '700', color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8, marginLeft: 4 },
  sectionCard:  { backgroundColor: theme.card, borderRadius: 18, overflow: 'hidden', borderWidth: 1, borderColor: theme.cardBorder, shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  menuRow:      { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 16, gap: 13 },
  menuRowBorder:{ borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  menuIcon:     { width: 36, height: 36, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  menuLabel:    { flex: 1, fontSize: 15, color: theme.text, fontWeight: '500' },
  chevronBox:   { width: 26, height: 26, borderRadius: 8, backgroundColor: theme.input, alignItems: 'center', justifyContent: 'center' },
  themeChip:    { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 20, marginRight: 6 },
  themeChipText:{ fontSize: 11, fontWeight: '700' },

  /* Sign Out */
  logoutBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: isDark ? 'rgba(239,68,68,0.08)' : 'rgba(239,68,68,0.06)',
    borderWidth: 1, borderColor: 'rgba(239,68,68,0.2)',
    borderRadius: 16, paddingVertical: 15, marginBottom: 20,
  },
  logoutText: { color: COLORS.red, fontSize: 15, fontWeight: '700' },
  version:    { textAlign: 'center', fontSize: 12, color: theme.textMuted, marginBottom: 8 },

  /* Shared sheet */
  overlay:       { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  sheet:         { borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: 24, paddingBottom: 40 },
  sheetHandle:   { width: 40, height: 4, borderRadius: 2, backgroundColor: '#ccc', alignSelf: 'center', marginBottom: 20 },
  sheetTitle:    { fontSize: 18, fontWeight: '800', marginBottom: 4 },
  sheetSub:      { fontSize: 13, marginBottom: 20 },
  sheetClose:    { marginTop: 20, borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  sheetCloseTxt: { fontSize: 15, fontWeight: '700' },

  /* Appearance */
  themeOption: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    borderWidth: 1.5, borderColor: 'transparent',
    borderRadius: 16, padding: 14, marginBottom: 10,
  },
  themeIconBox:      { width: 44, height: 44, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  themeOptionLabel:  { fontSize: 15, fontWeight: '700' },
  themeOptionDesc:   { fontSize: 12, marginTop: 2 },

  /* About */
  aboutLogoBox: { width: 80, height: 80, borderRadius: 24, alignSelf: 'center', alignItems: 'center', justifyContent: 'center', marginBottom: 20 },
  aboutRow:     { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1 },
  aboutLabel:   { fontSize: 13 },
  aboutValue:   { fontSize: 13, fontWeight: '600' },
  aboutDesc:    { fontSize: 13, lineHeight: 20, marginTop: 16, textAlign: 'center' },

  /* Security */
  secLabel:     { fontSize: 12, fontWeight: '600', marginBottom: 6 },
  secInputRow:  { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: 14, paddingHorizontal: 12, height: 50 },
  secInput:     { flex: 1, fontSize: 15 },
  strengthRow:  { flexDirection: 'row', flexWrap: 'wrap', gap: 8, borderWidth: 1, borderRadius: 12, padding: 10, marginBottom: 4 },
  strengthItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  strengthTxt:  { fontSize: 11, fontWeight: '600' },
  sheetSaveBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary, borderRadius: 14, height: 50, marginTop: 16 },
  sheetSaveBtnTxt: { color: '#fff', fontSize: 15, fontWeight: '800' },

  /* Help */
  helpRow:  { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14, borderBottomWidth: 1 },
  helpIcon: { width: 42, height: 42, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  helpLabel:{ fontSize: 14, fontWeight: '700' },
  helpDesc: { fontSize: 12, marginTop: 2 },
  faqBox:   { borderRadius: 14, padding: 14, marginTop: 16 },
  faqTitle: { fontSize: 13, fontWeight: '700', marginBottom: 10 },
  faqItem:  { marginBottom: 10 },
  faqQ:     { fontSize: 13, fontWeight: '600' },
  faqA:     { fontSize: 12, marginTop: 3, lineHeight: 18 },
});
