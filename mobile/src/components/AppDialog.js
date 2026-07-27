/**
 * AppDialog — modern animated modal dialog.
 * Mount once in App.js: <AppDialog />
 * Trigger imperatively via showError / showSuccess / showConfirm / showDialog.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { COLORS } from '../context/ThemeContext';
import { _registerDialog } from '../utils/dialog';

const TYPE_META = {
  success: { icon: '✓', color: COLORS.green,   bg: '#dcfce7', darkBg: '#052e16' },
  error:   { icon: '✕', color: COLORS.red,     bg: '#fee2e2', darkBg: '#2d0a0a' },
  warning: { icon: '!', color: COLORS.amber,   bg: '#fef9c3', darkBg: '#2d1f00' },
  info:    { icon: 'i', color: COLORS.primary, bg: '#ede9fe', darkBg: '#160d3a' },
  confirm: { icon: '?', color: COLORS.amber,   bg: '#fef9c3', darkBg: '#2d1f00' },
};

const INITIAL = { title: '', message: '', type: 'info', buttons: [{ text: 'OK' }] };

export default function AppDialog() {
  const { theme, isDark } = useTheme();
  const [visible, setVisible]   = useState(false);
  const [dialog,  setDialog]    = useState(INITIAL);

  const opacity = useRef(new Animated.Value(0)).current;
  const scale   = useRef(new Animated.Value(0.88)).current;

  useEffect(() => {
    _registerDialog((d) => {
      setDialog(d);
      setVisible(true);
    });
    return () => _registerDialog(null);
  }, []);

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.timing(opacity, { toValue: 1, duration: 180, useNativeDriver: true }),
        Animated.spring(scale,   { toValue: 1, useNativeDriver: true, bounciness: 6 }),
      ]).start();
    }
  }, [visible]);

  const dismiss = (btn) => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 0, duration: 140, useNativeDriver: true }),
      Animated.timing(scale,   { toValue: 0.88, duration: 140, useNativeDriver: true }),
    ]).start(() => {
      setVisible(false);
      opacity.setValue(0);
      scale.setValue(0.88);
      btn?.onPress?.();
    });
  };

  const meta    = TYPE_META[dialog.type] || TYPE_META.info;
  const iconBg  = isDark ? meta.darkBg : meta.bg;
  const isMulti = dialog.buttons?.length > 1;

  return (
    <Modal visible={visible} transparent animationType="none" statusBarTranslucent onRequestClose={() => dismiss(dialog.buttons[0])}>
      <Pressable style={s.backdrop} onPress={() => dismiss(dialog.buttons[0])}>
        <Animated.View style={[s.card, { backgroundColor: theme.card, borderColor: theme.cardBorder, opacity, transform: [{ scale }] }]}>

          {/* Icon badge */}
          <View style={[s.iconWrap, { backgroundColor: iconBg }]}>
            <Text style={[s.iconText, { color: meta.color }]}>{meta.icon}</Text>
          </View>

          {/* Title */}
          <Text style={[s.title, { color: theme.text }]}>{dialog.title}</Text>

          {/* Message */}
          {!!dialog.message && (
            <Text style={[s.message, { color: theme.textSecondary }]}>{dialog.message}</Text>
          )}

          {/* Buttons */}
          <View style={[s.btnRow, isMulti && s.btnRowMulti]}>
            {dialog.buttons?.map((btn, i) => {
              const isCancel  = btn.style === 'cancel';
              const isDanger  = btn.style === 'danger';
              const isPrimary = !isCancel;

              const bgColor = isCancel  ? theme.surface
                            : isDanger  ? COLORS.red
                            : meta.color;
              const txtColor = isCancel ? theme.textSecondary : '#fff';

              return (
                <TouchableOpacity
                  key={i}
                  style={[s.btn, isMulti && s.btnFlex, { backgroundColor: bgColor }]}
                  activeOpacity={0.8}
                  onPress={() => dismiss(btn)}
                >
                  <Text style={[s.btnTxt, { color: txtColor }]}>{btn.text}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

        </Animated.View>
      </Pressable>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 28,
  },
  card: {
    width: '100%',
    maxWidth: 360,
    borderRadius: 24,
    borderWidth: 1,
    padding: 28,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.25,
    shadowOffset: { width: 0, height: 8 },
    shadowRadius: 24,
    elevation: 16,
  },
  iconWrap: {
    width: 60,
    height: 60,
    borderRadius: 30,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 18,
  },
  iconText: {
    fontSize: 26,
    fontWeight: '800',
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 8,
    letterSpacing: 0.2,
  },
  message: {
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
    marginBottom: 24,
  },
  btnRow: {
    width: '100%',
    gap: 10,
  },
  btnRowMulti: {
    flexDirection: 'row',
  },
  btn: {
    flex: 0,
    width: '100%',
    paddingVertical: 13,
    borderRadius: 14,
    alignItems: 'center',
  },
  btnFlex: {
    flex: 1,
    width: undefined,
  },
  btnTxt: {
    fontSize: 15,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
});
