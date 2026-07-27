import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';

export default function KPICard({ title, value, icon, color, sub }) {
  const { theme } = useTheme();
  const s = styles(theme, color);
  return (
    <View style={s.card}>
      <View style={s.topRow}>
        <View style={s.iconBox}>
          <Ionicons name={icon} size={20} color={color} />
        </View>
        <Text style={s.value}>{value ?? '—'}</Text>
      </View>
      <Text style={s.title}>{title}</Text>
      {sub && <Text style={s.sub}>{sub}</Text>}
    </View>
  );
}

const styles = (theme, color) => StyleSheet.create({
  card: {
    width: '47%',
    backgroundColor: theme.card,
    borderRadius: 18,
    padding: 16,
    borderWidth: 1,
    borderColor: theme.cardBorder,
    shadowColor: color,
    shadowOpacity: 0.14,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
  topRow:  { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 },
  iconBox: {
    width: 42, height: 42, borderRadius: 13,
    backgroundColor: `${color}18`,
    alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: `${color}22`,
  },
  value: { fontSize: 28, fontWeight: '800', color: theme.text, lineHeight: 34, alignSelf: 'flex-end' },
  title: { fontSize: 11, fontWeight: '700', color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.7 },
  sub:   { fontSize: 11, color: theme.textMuted, marginTop: 3, fontWeight: '500' },
});
