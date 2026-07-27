import React, { useState, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { useTheme, COLORS } from '../../context/ThemeContext';
import { showError, showSuccess, showWarning } from '../../utils/dialog';

function getPasswordStrength(pw) {
  if (!pw) return { level: 0, label: '', color: 'transparent' };
  let score = 0;
  if (pw.length >= 8)            score++;
  if (pw.length >= 12)           score++;
  if (/[A-Z]/.test(pw))         score++;
  if (/[0-9]/.test(pw))         score++;
  if (/[^A-Za-z0-9]/.test(pw))  score++;
  if (score <= 1) return { level: 1, label: 'Weak',   color: '#ef4444' };
  if (score === 2) return { level: 2, label: 'Fair',   color: '#f97316' };
  if (score === 3) return { level: 3, label: 'Good',   color: '#eab308' };
  return             { level: 4, label: 'Strong', color: '#22c55e' };
}

export default function RegisterScreen({ navigation }) {
  const { register } = useAuth();
  const { theme } = useTheme();

  const [fullName, setFullName] = useState('');
  const [email, setEmail]       = useState('');
  const [company, setCompany]   = useState('');
  const [password, setPassword]       = useState('');
  const [confirmPass, setConfirmPass] = useState('');
  const [showPass, setShowPass]       = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading]         = useState(false);
  const scrollRef = useRef(null);

  const handleRegister = async () => {
    const trimmedEmail = email.trim().toLowerCase();
    if (!fullName.trim() || !trimmedEmail || !password.trim()) {
      showWarning('Missing fields', 'Full name, email, and password are required.');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      showWarning('Invalid Email', 'Please enter a valid email address.');
      return;
    }
    if (password.length < 8) {
      showWarning('Weak password', 'Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPass) {
      showWarning('Passwords do not match', 'Please make sure both passwords are the same.');
      return;
    }
    try {
      setLoading(true);
      const result = await register({
        full_name: fullName.trim(),
        email: trimmedEmail,
        company: company.trim() || undefined,
        password,
        source: 'mobile',
      });

      if (result?.status === 'verify_email') {
        navigation.replace('OTPVerification', {
          email:       trimmedEmail,
          maskedEmail: result.email,
        });
      } else {
        showSuccess(
          'Account Created',
          'Your account is pending admin approval. You will be notified once activated.',
        );
        navigation.navigate('Login');
      }
    } catch (err) {
      if (!err.response) {
        showError('No Connection', 'Cannot reach the server. Check your connection and try again.');
        return;
      }
      let msg = err?.response?.data?.message || err?.message || 'Registration failed. Please try again.';
      if (err.response?.status === 429) {
        msg = 'Too many sign-up attempts. Please wait a few minutes and try again.';
      } else if (msg.toLowerCase().includes('already')) {
        msg = 'This email is already registered. Please sign in instead.';
      }
      showError('Registration Failed', msg);
    } finally {
      setLoading(false);
    }
  };

  const s = styles(theme);

  return (
    <KeyboardAvoidingView
      style={s.root}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 20}
    >
      <StatusBar style="light" />
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={s.scroll}
        keyboardShouldPersistTaps="handled"
        bounces={false}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Decorative Header ─────────────────────────────────────── */}
        <View style={s.headerBg}>
          <View style={[s.blob, s.blob1]} />
          <View style={[s.blob, s.blob2]} />
          <View style={[s.blob, s.blob3]} />
          <View style={s.logoBox}>
            <Ionicons name="person-add" size={32} color="#fff" />
          </View>
          <Text style={s.appName}>Create Account</Text>
          <Text style={s.headerSub}>Start collecting leads with AI</Text>
        </View>

        {/* ── Form Card ─────────────────────────────────────────────── */}
        <View style={s.card}>

          {[
            { label: 'Full Name *',  value: fullName, set: setFullName, icon: 'person-outline',   placeholder: 'John Doe',            type: 'default' },
            { label: 'Email *',      value: email,    set: setEmail,    icon: 'mail-outline',      placeholder: 'you@example.com',     type: 'email-address' },
            { label: 'Company',      value: company,  set: setCompany,  icon: 'business-outline',  placeholder: 'Acme Corp (optional)', type: 'default' },
          ].map(({ label, value, set, icon, placeholder, type }) => (
            <View key={label} style={{ marginBottom: 16 }}>
              <Text style={s.label}>{label}</Text>
              <View style={s.inputRow}>
                <Ionicons name={icon} size={18} color={theme.textMuted} style={s.inputIcon} />
                <TextInput
                  style={s.input}
                  value={value}
                  onChangeText={set}
                  placeholder={placeholder}
                  placeholderTextColor={theme.textMuted}
                  keyboardType={type}
                  autoCapitalize={type === 'email-address' ? 'none' : 'words'}
                />
              </View>
            </View>
          ))}

          <Text style={s.label}>Password *</Text>
          <View style={s.inputRow}>
            <Ionicons name="lock-closed-outline" size={18} color={theme.textMuted} style={s.inputIcon} />
            <TextInput
              style={[s.input, { flex: 1 }]}
              value={password}
              onChangeText={setPassword}
              placeholder="Min. 8 characters"
              placeholderTextColor={theme.textMuted}
              secureTextEntry={!showPass}
            />
            <TouchableOpacity onPress={() => setShowPass(!showPass)} style={s.eyeBtn}>
              <Ionicons name={showPass ? 'eye-off-outline' : 'eye-outline'} size={18} color={theme.textMuted} />
            </TouchableOpacity>
          </View>

          {/* ── Password strength meter ── */}
          {password.length > 0 && (() => {
            const { level, label, color } = getPasswordStrength(password);
            return (
              <View style={s.strengthWrap}>
                <View style={s.strengthBars}>
                  {[1,2,3,4].map(i => (
                    <View
                      key={i}
                      style={[s.strengthBar, { backgroundColor: i <= level ? color : theme.inputBorder }]}
                    />
                  ))}
                </View>
                <Text style={[s.strengthLabel, { color }]}>{label}</Text>
              </View>
            );
          })()}

          <Text style={[s.label, { marginTop: 14 }]}>Confirm Password *</Text>
          <View style={[s.inputRow, confirmPass && confirmPass !== password && { borderColor: '#ef4444' }]}>
            <Ionicons name="lock-closed-outline" size={18} color={theme.textMuted} style={s.inputIcon} />
            <TextInput
              style={[s.input, { flex: 1 }]}
              value={confirmPass}
              onChangeText={setConfirmPass}
              placeholder="Re-enter your password"
              placeholderTextColor={theme.textMuted}
              secureTextEntry={!showConfirm}
              onFocus={() => {
                setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 150);
              }}
            />
            <TouchableOpacity onPress={() => setShowConfirm(!showConfirm)} style={s.eyeBtn}>
              <Ionicons name={showConfirm ? 'eye-off-outline' : 'eye-outline'} size={18} color={theme.textMuted} />
            </TouchableOpacity>
          </View>
          {confirmPass.length > 0 && confirmPass !== password && (
            <Text style={{ color: '#ef4444', fontSize: 12, marginTop: 4, marginLeft: 2 }}>
              Passwords do not match
            </Text>
          )}

          <TouchableOpacity
            style={[s.btn, loading && { opacity: 0.75 }]}
            onPress={handleRegister}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <>
                  <Ionicons name="checkmark-circle-outline" size={18} color="#fff" />
                  <Text style={s.btnText}>Create Account</Text>
                </>
            }
          </TouchableOpacity>

          <View style={s.dividerRow}>
            <View style={s.dividerLine} />
            <Text style={s.dividerTxt}>or</Text>
            <View style={s.dividerLine} />
          </View>

          <TouchableOpacity style={s.linkBtn} onPress={() => navigation.goBack()}>
            <Text style={s.linkText}>
              Already have an account?{'  '}
              <Text style={s.linkAccent}>Sign in</Text>
            </Text>
          </TouchableOpacity>

        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = (theme) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  scroll: { flexGrow: 1, paddingBottom: 64 },

  /* ── Header ── */
  headerBg: {
    backgroundColor: COLORS.purple,
    paddingTop: Platform.OS === 'ios' ? 70 : 50,
    paddingBottom: 70,
    alignItems: 'center',
    overflow: 'hidden',
  },
  blob: { position: 'absolute', borderRadius: 9999 },
  blob1: { width: 280, height: 280, backgroundColor: 'rgba(255,255,255,0.07)', top: -80, right: -60 },
  blob2: { width: 200, height: 200, backgroundColor: 'rgba(99,102,241,0.4)', bottom: -80, left: -50 },
  blob3: { width: 130, height: 130, backgroundColor: 'rgba(255,255,255,0.05)', top: 40, left: -20 },
  logoBox: {
    width: 76, height: 76, borderRadius: 24,
    backgroundColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 18,
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.28)',
    shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 }, elevation: 10,
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

  /* ── Button ── */
  btn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    marginTop: 24, backgroundColor: COLORS.purple, borderRadius: 16, height: 56,
    shadowColor: COLORS.purple, shadowOpacity: 0.38,
    shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 6,
  },
  btnText: { color: '#fff', fontSize: 16, fontWeight: '800', letterSpacing: 0.3 },

  /* ── Divider ── */
  dividerRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginVertical: 20 },
  dividerLine:{ flex: 1, height: 1, backgroundColor: theme.cardBorder },
  dividerTxt: { fontSize: 12, color: theme.textMuted, fontWeight: '500' },

  /* ── Password strength ── */
  strengthWrap: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8,
  },
  strengthBars: { flexDirection: 'row', gap: 4, flex: 1 },
  strengthBar: {
    flex: 1, height: 4, borderRadius: 4,
  },
  strengthLabel: { fontSize: 11, fontWeight: '700', minWidth: 40, textAlign: 'right' },

  /* ── Link ── */
  linkBtn:    { alignItems: 'center' },
  linkText:   { fontSize: 14, color: theme.textSecondary },
  linkAccent: { color: COLORS.purple, fontWeight: '700' },
});
