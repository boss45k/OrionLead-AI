import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { COLORS } from '../context/ThemeContext';

const CONFIG = {
  hot:       { color: COLORS.green,   bg: `${COLORS.green}18`,   border: `${COLORS.green}30`   },
  warm:      { color: COLORS.amber,   bg: `${COLORS.amber}18`,   border: `${COLORS.amber}30`   },
  cold:      { color: '#3b82f6',      bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.25)' },
  qualified: { color: COLORS.primary, bg: `${COLORS.primary}18`, border: `${COLORS.primary}30` },
  contacted: { color: COLORS.cyan,    bg: `${COLORS.cyan}18`,    border: `${COLORS.cyan}30`    },
  converted: { color: COLORS.green,   bg: `${COLORS.green}18`,   border: `${COLORS.green}30`   },
  pending:   { color: '#94a3b8',      bg: 'rgba(148,163,184,0.12)', border: 'rgba(148,163,184,0.25)' },
};

export default function StatusBadge({ status, small = false }) {
  const key = (status || 'pending').toLowerCase();
  const cfg = CONFIG[key] || CONFIG.pending;

  return (
    <View style={[
      styles.badge,
      { backgroundColor: cfg.bg, borderColor: cfg.border },
      small && styles.small,
    ]}>
      <View style={[styles.dot, { backgroundColor: cfg.color }]} />
      <Text style={[styles.text, { color: cfg.color }, small && styles.textSmall]}>
        {key.toUpperCase()}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 9, paddingVertical: 4,
    borderRadius: 20, borderWidth: 1,
  },
  small:     { paddingHorizontal: 7, paddingVertical: 3 },
  dot:       { width: 5, height: 5, borderRadius: 3 },
  text:      { fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },
  textSmall: { fontSize: 9 },
});
