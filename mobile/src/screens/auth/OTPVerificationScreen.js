import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { authAPI } from '../../services/api';
import { useTheme, COLORS } from '../../context/ThemeContext';
import { showError, showSuccess } from '../../utils/dialog';

const CODE_LENGTH = 6;
const RESEND_COOLDOWN = 60; // seconds

export default function OTPVerificationScreen({ navigation, route }) {
  const { email, maskedEmail } = route.params || {};
  const { theme } = useTheme();

  const [digits, setDigits]         = useState(Array(CODE_LENGTH).fill(''));
  const [loading, setLoading]       = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [countdown, setCountdown]   = useState(RESEND_COOLDOWN);
  const [error, setError]           = useState('');

  const inputRefs = useRef([]);
  const timerRef  = useRef(null);

  // Start countdown on mount
  useEffect(() => {
    startCountdown();
    return () => clearInterval(timerRef.current);
  }, []);

  const startCountdown = useCallback(() => {
    setCountdown(RESEND_COOLDOWN);
    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { clearInterval(timerRef.current); return 0; }
        return prev - 1;
      });
    }, 1000);
  }, []);

  const handleDigitChange = (text, index) => {
    // Accept only digits; handle paste of full code
    const clean = text.replace(/\D/g, '');
    if (clean.length > 1) {
      // Paste: spread across all boxes
      const spread = clean.slice(0, CODE_LENGTH).split('');
      const next = [...digits];
      spread.forEach((d, i) => { next[index + i < CODE_LENGTH ? index + i : CODE_LENGTH - 1] = d; });
      setDigits(next);
      const lastFilled = Math.min(index + spread.length - 1, CODE_LENGTH - 1);
      inputRefs.current[lastFilled]?.focus();
      if (index + spread.length >= CODE_LENGTH) {
        submitCode(next.join(''));
      }
      return;
    }

    const next = [...digits];
    next[index] = clean;
    setDigits(next);
    setError('');

    if (clean && index < CODE_LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }
    if (clean && index === CODE_LENGTH - 1) {
      submitCode([...next.slice(0, index), clean].join(''));
    }
  };

  const handleKeyPress = (e, index) => {
    if (e.nativeEvent.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const submitCode = async (code) => {
    if (code.length < CODE_LENGTH) return;
    setLoading(true);
    setError('');
    try {
      const resp = await authAPI.verifyEmail(email, code);
      const isPending = resp?.data?.status === 'pending_approval';
      showSuccess(
        isPending ? 'Email Verified' : 'Email Verified — Account Active',
        resp?.data?.message || (isPending
          ? 'Your email has been verified. Your account is now pending admin approval. You will be notified once activated.'
          : 'Your email has been verified. You can now sign in.'),
      );
      navigation.navigate('Login');
    } catch (err) {
      const msg = err?.response?.data?.message || err?.response?.data?.error || 'Verification failed.';
      setError(msg);
      // Clear digits so user can retype
      setDigits(Array(CODE_LENGTH).fill(''));
      inputRefs.current[0]?.focus();
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (countdown > 0 || resendLoading) return;
    setResendLoading(true);
    setError('');
    try {
      await authAPI.resendOtp(email);
      setDigits(Array(CODE_LENGTH).fill(''));
      inputRefs.current[0]?.focus();
      startCountdown();
      showSuccess('Code Sent', 'A new verification code has been sent to your email.');
    } catch (err) {
      const msg = err?.response?.data?.message || 'Could not resend code. Please try again.';
      showError('Error', msg);
    } finally {
      setResendLoading(false);
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
        {/* ── Header ── */}
        <View style={s.headerBg}>
          <View style={[s.blob, s.blob1]} />
          <View style={[s.blob, s.blob2]} />
          <View style={s.logoBox}>
            <Ionicons name="mail-open-outline" size={32} color="#fff" />
          </View>
          <Text style={s.title}>Verify Your Email</Text>
          <Text style={s.sub}>We sent a 6-digit code to</Text>
          <Text style={s.email}>{maskedEmail || email}</Text>
        </View>

        {/* ── Card ── */}
        <View style={s.card}>

          {/* OTP boxes */}
          <View style={s.boxRow}>
            {digits.map((d, i) => (
              <TextInput
                key={i}
                ref={ref => { inputRefs.current[i] = ref; }}
                style={[s.box, d ? s.boxFilled : null, error ? s.boxError : null]}
                value={d}
                onChangeText={t => handleDigitChange(t, i)}
                onKeyPress={e => handleKeyPress(e, i)}
                keyboardType="number-pad"
                maxLength={6}
                selectTextOnFocus
                textAlign="center"
                editable={!loading}
              />
            ))}
          </View>

          {/* Error message */}
          {!!error && (
            <View style={s.errorRow}>
              <Ionicons name="alert-circle-outline" size={14} color="#ef4444" />
              <Text style={s.errorTxt}>{error}</Text>
            </View>
          )}

          {/* Verify button */}
          <TouchableOpacity
            style={[s.btn, (loading || digits.join('').length < CODE_LENGTH) && { opacity: 0.6 }]}
            onPress={() => submitCode(digits.join(''))}
            disabled={loading || digits.join('').length < CODE_LENGTH}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <>
                  <Ionicons name="shield-checkmark-outline" size={18} color="#fff" />
                  <Text style={s.btnText}>Verify Email</Text>
                </>
            }
          </TouchableOpacity>

          {/* Resend */}
          <View style={s.resendRow}>
            <Text style={s.resendLabel}>Didn't receive a code?{'  '}</Text>
            {countdown > 0
              ? <Text style={s.resendCountdown}>Resend in {countdown}s</Text>
              : (
                <TouchableOpacity onPress={handleResend} disabled={resendLoading}>
                  {resendLoading
                    ? <ActivityIndicator size="small" color={COLORS.primary} />
                    : <Text style={s.resendLink}>Resend code</Text>
                  }
                </TouchableOpacity>
              )
            }
          </View>

          {/* Back to register */}
          <TouchableOpacity
            style={s.backBtn}
            onPress={() => navigation.goBack()}
          >
            <Ionicons name="arrow-back-outline" size={14} color={theme.textMuted} />
            <Text style={s.backTxt}>Change email address</Text>
          </TouchableOpacity>

        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = (theme) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  scroll: { flexGrow: 1, paddingBottom: 40 },

  /* ── Header ── */
  headerBg: {
    backgroundColor: COLORS.primary,
    paddingTop: Platform.OS === 'ios' ? 80 : 60,
    paddingBottom: 72,
    alignItems: 'center',
    overflow: 'hidden',
  },
  blob: { position: 'absolute', borderRadius: 9999 },
  blob1: { width: 260, height: 260, backgroundColor: 'rgba(255,255,255,0.07)', top: -80, right: -60 },
  blob2: { width: 180, height: 180, backgroundColor: 'rgba(139,92,246,0.35)', bottom: -70, left: -40 },
  logoBox: {
    width: 72, height: 72, borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.18)',
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 16,
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.35)',
    shadowColor: '#6366f1', shadowOpacity: 0.4, shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 }, elevation: 10,
  },
  title: { fontSize: 24, fontWeight: '800', color: '#fff', letterSpacing: 0.2 },
  sub:   { fontSize: 13, color: 'rgba(255,255,255,0.72)', marginTop: 8 },
  email: { fontSize: 14, fontWeight: '700', color: '#fff', marginTop: 2 },

  /* ── Card ── */
  card: {
    backgroundColor: theme.card,
    borderRadius: 28,
    marginHorizontal: 16,
    marginTop: -38,
    padding: 24,
    borderWidth: 1,
    borderColor: theme.cardBorder,
    shadowColor: '#000',
    shadowOpacity: 0.13,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },

  /* ── OTP boxes ── */
  boxRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginVertical: 24,
    gap: 8,
  },
  box: {
    flex: 1,
    height: 58,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: theme.inputBorder,
    backgroundColor: theme.input,
    fontSize: 24,
    fontWeight: '800',
    color: theme.text,
  },
  boxFilled: {
    borderColor: COLORS.primary,
    backgroundColor: `${COLORS.primary}12`,
  },
  boxError: {
    borderColor: '#ef4444',
  },

  /* ── Error ── */
  errorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 12,
    marginTop: -8,
  },
  errorTxt: { fontSize: 13, color: '#ef4444', flex: 1 },

  /* ── Button ── */
  btn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: COLORS.primary, borderRadius: 16, height: 56,
    shadowColor: COLORS.primary, shadowOpacity: 0.35,
    shadowRadius: 12, shadowOffset: { width: 0, height: 5 }, elevation: 6,
  },
  btnText: { color: '#fff', fontSize: 16, fontWeight: '800', letterSpacing: 0.3 },

  /* ── Resend ── */
  resendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 20,
  },
  resendLabel:     { fontSize: 13, color: theme.textSecondary },
  resendCountdown: { fontSize: 13, color: theme.textMuted, fontWeight: '600' },
  resendLink:      { fontSize: 13, color: COLORS.primary, fontWeight: '700' },

  /* ── Back ── */
  backBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    marginTop: 20,
  },
  backTxt: { fontSize: 13, color: theme.textMuted },
});
