import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator, Modal,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle, Line, Path, G } from 'react-native-svg';
import { GoogleSignin, statusCodes } from '@react-native-google-signin/google-signin';
import { useAuth } from '../../context/AuthContext';
import { useTheme, COLORS } from '../../context/ThemeContext';
import { showError, showWarning, showInfo, showSuccess } from '../../utils/dialog';
import { getServerUrl, setServerUrl, testServerUrl } from '../../services/api';

// Web client ID — GoogleSignin uses this to request an idToken verifiable by the backend.
// The Android OAuth client (SHA-1 registered) handles Play Services auth silently.
const GOOGLE_WEB_CLIENT_ID = '656052458985-58o08p0oqh5flhqgpd82en5jo8qvvtbd.apps.googleusercontent.com';

export default function LoginScreen({ navigation }) {
  const { login, googleLogin } = useAuth();
  const { theme } = useTheme();

  const [email, setEmail]         = useState('');
  const [password, setPassword]   = useState('');
  const [showPass, setShowPass]   = useState(false);
  const [loading, setLoading]     = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  const [serverModalVisible, setServerModalVisible] = useState(false);
  const [serverUrlInput, setServerUrlInput] = useState('');
  const [testingServer, setTestingServer]   = useState(false);

  useEffect(() => {
    GoogleSignin.configure({ webClientId: GOOGLE_WEB_CLIENT_ID });
  }, []);

  const openServerSettings = () => {
    setServerUrlInput(getServerUrl());
    setServerModalVisible(true);
  };

  const handleTestServer = async () => {
    const url = serverUrlInput.trim();
    if (!url) {
      showWarning('Missing URL', 'Enter a server address first, e.g. http://192.168.1.10:5000');
      return;
    }
    setTestingServer(true);
    try {
      await testServerUrl(url);
      showSuccess('Connected', 'Successfully reached the server.');
    } catch (err) {
      showError('Cannot Connect', 'Could not reach that address. Double-check the IP, port, and that the backend is running.');
    } finally {
      setTestingServer(false);
    }
  };

  const handleSaveServer = async () => {
    const url = serverUrlInput.trim();
    if (!url) {
      showWarning('Missing URL', 'Enter a server address first, e.g. http://192.168.1.10:5000');
      return;
    }
    await setServerUrl(url);
    setServerModalVisible(false);
    showSuccess('Saved', 'The app will now use this server address.');
  };

  const handleLogin = async () => {
    const trimmedEmail = email.trim().toLowerCase();
    const trimmedPass  = password.trim();

    if (!trimmedEmail || !trimmedPass) {
      showWarning('Missing Fields', 'Please enter your email and password.');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      showWarning('Invalid Email', 'Please enter a valid email address.');
      return;
    }
    if (trimmedPass.length < 6) {
      showWarning('Invalid Password', 'Password must be at least 6 characters.');
      return;
    }

    try {
      setLoading(true);
      await login(trimmedEmail, password);
    } catch (err) {
      // Backend message takes priority over Axios generic message
      const backendMsg = err?.response?.data?.message || err?.response?.data?.error;
      const msg = backendMsg || err?.message || 'Login failed. Please try again.';

      const isCredErr    = msg.toLowerCase().includes('invalid credentials');
      const isPending    = msg.toLowerCase().includes('pending');
      const isDisabled   = msg.toLowerCase().includes('deactivated');
      const isUnverified = msg.toLowerCase().includes('verify your email');
      const isNetwork    = !err.response;

      if (isUnverified) {
        navigation.navigate('OTPVerification', { email: trimmedEmail, maskedEmail: null });
        return;
      }

      const title = isNetwork  ? 'No Connection'
                  : isCredErr  ? 'Incorrect Email or Password'
                  : isDisabled ? 'Account Disabled'
                  : isPending  ? 'Account Pending Approval'
                  : 'Login Failed';

      const body = isNetwork ? 'Cannot reach the server. Check your connection and try again.'
                 : isCredErr ? 'The email or password you entered is incorrect. Please try again.'
                 : msg;

      showError(title, body);
    } finally {
      setLoading(false);
    }
  };

  const handleGooglePress = async () => {
    setGoogleLoading(true);
    try {
      await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
      // Clear any cached Google session so the account picker always appears,
      // letting the user choose a different account after signing out.
      try { await GoogleSignin.signOut(); } catch (_) {}
      const result = await GoogleSignin.signIn();
      // v13+ returns { data: { idToken } }, earlier versions return { idToken } directly
      const idToken = result?.data?.idToken ?? result?.idToken;
      if (!idToken) throw new Error('No ID token received from Google.');
      await googleLogin(idToken);
    } catch (err) {
      if (err.code === statusCodes.SIGN_IN_CANCELLED) {
        // user closed the dialog — no alert needed
      } else if (err.code === statusCodes.IN_PROGRESS) {
        showInfo('Please wait', 'Sign-in is already in progress.');
      } else if (err.code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) {
        showError('Unavailable', 'Google Play Services is not available on this device.');
      } else {
        const msg = err?.response?.data?.message || err?.message || 'Google sign-in failed.';
        showError('Sign-In Failed', msg);
      }
    } finally {
      setGoogleLoading(false);
    }
  };

  const s = styles(theme);

  return (
    <KeyboardAvoidingView
      style={s.root}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <StatusBar style="light" />
      <ScrollView
        contentContainerStyle={s.scroll}
        keyboardShouldPersistTaps="handled"
        bounces={false}
      >
        {/* ── Decorative Header ─────────────────────────────────────── */}
        <View style={s.headerBg}>
          <View style={[s.blob, s.blob1]} />
          <View style={[s.blob, s.blob2]} />
          <View style={[s.blob, s.blob3]} />
          <View style={s.logoBox}>
            <Svg width={34} height={34} viewBox="0 0 40 40">
              <Line x1="20" y1="13" x2="12" y2="27" stroke="white" strokeWidth="2" strokeOpacity="0.55" strokeLinecap="round"/>
              <Line x1="20" y1="13" x2="28" y2="27" stroke="white" strokeWidth="2" strokeOpacity="0.55" strokeLinecap="round"/>
              <Line x1="13" y1="30" x2="27" y2="30" stroke="white" strokeWidth="2" strokeOpacity="0.55" strokeLinecap="round"/>
              <Circle cx="20" cy="9.5" r="4.5" fill="white"/>
              <Circle cx="11" cy="30" r="4" fill="white" fillOpacity="0.9"/>
              <Circle cx="29" cy="30" r="4" fill="white" fillOpacity="0.9"/>
            </Svg>
          </View>
          <Text style={s.appName}>OrionLead AI</Text>
          <Text style={s.headerSub}>Sign in to your account</Text>
        </View>

        {/* ── Form Card ─────────────────────────────────────────────── */}
        <View style={s.card}>

          <Text style={s.label}>Email address</Text>
          <View style={s.inputRow}>
            <Ionicons name="mail-outline" size={18} color={theme.textMuted} style={s.inputIcon} />
            <TextInput
              style={s.input}
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              placeholderTextColor={theme.textMuted}
              keyboardType="email-address"
              autoCapitalize="none"
              autoComplete="email"
            />
          </View>

          <Text style={[s.label, { marginTop: 16 }]}>Password</Text>
          <View style={s.inputRow}>
            <Ionicons name="lock-closed-outline" size={18} color={theme.textMuted} style={s.inputIcon} />
            <TextInput
              style={[s.input, { flex: 1 }]}
              value={password}
              onChangeText={setPassword}
              placeholder="••••••••"
              placeholderTextColor={theme.textMuted}
              secureTextEntry={!showPass}
              autoComplete="password"
            />
            <TouchableOpacity onPress={() => setShowPass(!showPass)} style={s.eyeBtn}>
              <Ionicons
                name={showPass ? 'eye-off-outline' : 'eye-outline'}
                size={18}
                color={theme.textMuted}
              />
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={s.forgotBtn}
            onPress={() => showInfo('Reset Password', 'Contact your admin to reset your password, or use the web app.')}
          >
            <Text style={s.forgotTxt}>Forgot password?</Text>
          </TouchableOpacity>

          {/* Sign In button */}
          <TouchableOpacity
            style={[s.btn, loading && { opacity: 0.75 }]}
            onPress={handleLogin}
            disabled={loading || googleLoading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <>
                  <Ionicons name="log-in-outline" size={18} color="#fff" />
                  <Text style={s.btnText}>Sign In</Text>
                </>
            }
          </TouchableOpacity>

          {/* Divider */}
          <View style={s.dividerRow}>
            <View style={s.dividerLine} />
            <Text style={s.dividerTxt}>or continue with</Text>
            <View style={s.dividerLine} />
          </View>

          {/* Google Sign-In button */}
          <TouchableOpacity
            style={[s.googleBtn, googleLoading && { opacity: 0.7 }]}
            onPress={handleGooglePress}
            disabled={googleLoading || loading}
            activeOpacity={0.85}
          >
            {googleLoading ? (
              <ActivityIndicator color={theme.text} size="small" />
            ) : (
              <>
                {/* Google "G" logo */}
                <Svg width={20} height={20} viewBox="0 0 48 48">
                  <G>
                    <Path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                    <Path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                    <Path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                    <Path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                    <Path fill="none" d="M0 0h48v48H0z"/>
                  </G>
                </Svg>
                <Text style={[s.googleTxt, { color: theme.text }]}>Continue with Google</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Register link */}
          <TouchableOpacity
            style={s.linkBtn}
            onPress={() => navigation.navigate('Register')}
          >
            <Text style={s.linkText}>
              Don't have an account?{'  '}
              <Text style={s.linkAccent}>Create one</Text>
            </Text>
          </TouchableOpacity>

          {/* Server settings link — lets this build point at any backend */}
          <TouchableOpacity style={s.serverBtn} onPress={openServerSettings}>
            <Ionicons name="server-outline" size={13} color={theme.textMuted} />
            <Text style={s.serverBtnText}>Server Settings</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>

      {/* Server Settings modal */}
      <Modal
        visible={serverModalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setServerModalVisible(false)}
      >
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <Text style={s.modalTitle}>Server Settings</Text>
            <Text style={s.modalSubtitle}>
              Point this app at any backend — e.g. your own computer's address
              (find it with ipconfig / ifconfig).
            </Text>

            <TextInput
              style={s.modalInput}
              value={serverUrlInput}
              onChangeText={setServerUrlInput}
              placeholder="http://192.168.1.10:5000"
              placeholderTextColor={theme.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
            />

            <View style={s.modalBtnRow}>
              <TouchableOpacity
                style={[s.modalBtn, s.modalBtnSecondary]}
                onPress={handleTestServer}
                disabled={testingServer}
              >
                {testingServer
                  ? <ActivityIndicator color={COLORS.primary} size="small" />
                  : <Text style={s.modalBtnSecondaryText}>Test Connection</Text>}
              </TouchableOpacity>
              <TouchableOpacity style={[s.modalBtn, s.modalBtnPrimary]} onPress={handleSaveServer}>
                <Text style={s.modalBtnPrimaryText}>Save</Text>
              </TouchableOpacity>
            </View>

            <TouchableOpacity style={s.modalCancel} onPress={() => setServerModalVisible(false)}>
              <Text style={s.modalCancelText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const styles = (theme) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  scroll: { flexGrow: 1, paddingBottom: 32 },

  /* ── Header ── */
  headerBg: {
    backgroundColor: COLORS.primary,
    paddingTop: Platform.OS === 'ios' ? 80 : 60,
    paddingBottom: 70,
    alignItems: 'center',
    overflow: 'hidden',
  },
  blob: { position: 'absolute', borderRadius: 9999 },
  blob1: { width: 300, height: 300, backgroundColor: 'rgba(255,255,255,0.07)', top: -90, right: -70 },
  blob2: { width: 200, height: 200, backgroundColor: 'rgba(139,92,246,0.35)', bottom: -80, left: -50 },
  blob3: { width: 130, height: 130, backgroundColor: 'rgba(255,255,255,0.05)', top: 50, left: -25 },
  logoBox: {
    width: 68, height: 68, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.18)',
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 16,
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.35)',
    shadowColor: '#6366f1', shadowOpacity: 0.45, shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 }, elevation: 12,
  },
  appName:   { fontSize: 26, fontWeight: '800', color: '#fff', letterSpacing: 0.2 },
  headerSub: { fontSize: 14, color: 'rgba(255,255,255,0.72)', marginTop: 6 },

  /* ── Card ── */
  card: {
    backgroundColor: theme.card,
    borderRadius: 28,
    marginHorizontal: 16,
    marginTop: -36,
    padding: 24,
    borderWidth: 1,
    borderColor: theme.cardBorder,
    shadowColor: '#000',
    shadowOpacity: 0.14,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },

  /* ── Form ── */
  label: { fontSize: 13, fontWeight: '600', color: theme.textSecondary, marginBottom: 8 },
  inputRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: theme.input,
    borderRadius: 14, borderWidth: 1, borderColor: theme.inputBorder,
    paddingHorizontal: 14,
  },
  inputIcon: { marginRight: 10 },
  input:     { flex: 1, height: 52, color: theme.text, fontSize: 15 },
  eyeBtn:    { padding: 6 },

  /* ── Sign In button ── */
  btn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    marginTop: 24, backgroundColor: COLORS.primary, borderRadius: 16, height: 56,
    shadowColor: COLORS.primary, shadowOpacity: 0.38,
    shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 6,
  },
  btnText: { color: '#fff', fontSize: 16, fontWeight: '800', letterSpacing: 0.3 },

  /* ── Forgot ── */
  forgotBtn: { alignSelf: 'flex-end', marginTop: 8, marginBottom: 4 },
  forgotTxt: { fontSize: 13, color: COLORS.primary, fontWeight: '600' },

  /* ── Divider ── */
  dividerRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginVertical: 20 },
  dividerLine:{ flex: 1, height: 1, backgroundColor: theme.cardBorder },
  dividerTxt: { fontSize: 12, color: theme.textMuted, fontWeight: '500' },

  /* ── Google button ── */
  googleBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
    height: 56, borderRadius: 16,
    backgroundColor: theme.input,
    borderWidth: 1.5, borderColor: theme.inputBorder,
    marginBottom: 20,
  },
  googleTxt: { fontSize: 15, fontWeight: '700' },

  /* ── Register link ── */
  linkBtn:    { alignItems: 'center' },
  linkText:   { fontSize: 14, color: theme.textSecondary },
  linkAccent: { color: COLORS.primary, fontWeight: '700' },

  /* ── Server settings link ── */
  serverBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    marginTop: 18,
  },
  serverBtnText: { fontSize: 12, color: theme.textMuted, fontWeight: '600' },

  /* ── Server settings modal ── */
  modalOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center', alignItems: 'center', padding: 24,
  },
  modalCard: {
    width: '100%', maxWidth: 400,
    backgroundColor: theme.card, borderRadius: 20, padding: 22,
    borderWidth: 1, borderColor: theme.cardBorder,
  },
  modalTitle:    { fontSize: 18, fontWeight: '800', color: theme.text, marginBottom: 6 },
  modalSubtitle: { fontSize: 13, color: theme.textSecondary, marginBottom: 16, lineHeight: 18 },
  modalInput: {
    height: 50, borderRadius: 12, borderWidth: 1, borderColor: theme.inputBorder,
    backgroundColor: theme.input, color: theme.text, paddingHorizontal: 14, fontSize: 14,
  },
  modalBtnRow: { flexDirection: 'row', gap: 10, marginTop: 16 },
  modalBtn: {
    flex: 1, height: 46, borderRadius: 12,
    alignItems: 'center', justifyContent: 'center',
  },
  modalBtnSecondary:     { backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder },
  modalBtnSecondaryText: { color: COLORS.primary, fontWeight: '700', fontSize: 13 },
  modalBtnPrimary:       { backgroundColor: COLORS.primary },
  modalBtnPrimaryText:   { color: '#fff', fontWeight: '700', fontSize: 13 },
  modalCancel:     { alignItems: 'center', marginTop: 14 },
  modalCancelText: { color: theme.textMuted, fontSize: 13, fontWeight: '600' },
});
