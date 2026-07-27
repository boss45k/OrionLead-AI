import React, { useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import StatusBadge from './StatusBadge';

const TIER = (score) => {
  if (score >= 80) return { label: 'HIGH',   color: COLORS.green  };
  if (score >= 60) return { label: 'MED',    color: COLORS.amber  };
  if (score >= 35) return { label: 'LOW',    color: '#3b82f6'     };
  return               { label: 'NEW',    color: '#94a3b8'     };
};

const LeadCard = React.memo(function LeadCard({ lead, onPress, onDelete }) {
  const { theme } = useTheme();

  const score      = Math.round(lead.qualification_score || 0);
  const scoreColor = score >= 80 ? COLORS.green : score >= 60 ? COLORS.amber : score >= 35 ? '#3b82f6' : '#94a3b8';
  const tier       = TIER(score);
  const verified   = lead.data_points?.email_verified === true || lead.data_points?.email_verified === 'true';
  const hasPhone   = !!lead.phone;

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const s = useMemo(() => styles(theme), [theme]);

  return (
    <TouchableOpacity
      style={[s.card, { borderLeftColor: scoreColor }]}
      onPress={onPress}
      activeOpacity={0.72}
    >
      <View style={s.row}>
        {/* Avatar */}
        <View style={[s.avatar, { backgroundColor: `${scoreColor}14`, borderColor: `${scoreColor}28` }]}>
          <Text style={[s.avatarText, { color: scoreColor }]}>{(lead.name || '?')[0].toUpperCase()}</Text>
        </View>

        {/* Info */}
        <View style={s.info}>
          <Text style={s.name} numberOfLines={1}>{lead.name}</Text>
          <Text style={s.company} numberOfLines={1}>
            {lead.position ? `${lead.position} · ` : ''}{lead.company || lead.email || '—'}
          </Text>

          {/* Tags row */}
          <View style={s.tagRow}>
            {/* Quality tier pill */}
            <View style={[s.tierBadge, { backgroundColor: `${tier.color}15`, borderColor: `${tier.color}35` }]}>
              <Text style={[s.tierTxt, { color: tier.color }]}>{tier.label}</Text>
            </View>

            {lead.industry && (
              <View style={s.industryTag}>
                <Text style={s.industryTxt} numberOfLines={1}>{lead.industry}</Text>
              </View>
            )}

            {lead.country && (
              <Text style={s.country} numberOfLines={1}>{lead.country}</Text>
            )}
          </View>
        </View>

        {/* Right — score + status */}
        <View style={s.right}>
          <View style={[s.scoreCircle, { borderColor: scoreColor, backgroundColor: `${scoreColor}10` }]}>
            <Text style={[s.scoreNum, { color: scoreColor }]}>{score}</Text>
          </View>
          <StatusBadge status={lead.status} small />
        </View>
      </View>

      {/* Bottom row */}
      <View style={s.bottom}>
        {lead.email && (
          <View style={s.chip}>
            <Ionicons name="mail-outline" size={11} color={verified ? COLORS.green : theme.textMuted} />
            <Text style={[s.chipTxt, { maxWidth: 130 }]} numberOfLines={1}>{lead.email}</Text>
            {verified && <Ionicons name="checkmark-circle" size={10} color={COLORS.green} />}
          </View>
        )}
        {hasPhone && (
          <View style={s.chip}>
            <Ionicons name="call-outline" size={11} color={theme.textMuted} />
            <Text style={s.chipTxt} numberOfLines={1}>{lead.phone}</Text>
          </View>
        )}
        {!lead.email && !hasPhone && lead.source && (
          <View style={s.chip}>
            <Ionicons name="globe-outline" size={11} color={theme.textMuted} />
            <Text style={s.chipTxt}>{lead.source}</Text>
          </View>
        )}
        {lead.buying_intent === 'high' && (
          <View style={[s.chip, { backgroundColor: `${COLORS.green}12`, borderColor: `${COLORS.green}30` }]}>
            <Ionicons name="flame" size={11} color={COLORS.green} />
            <Text style={[s.chipTxt, { color: COLORS.green }]}>High intent</Text>
          </View>
        )}
        {onDelete && (
          <TouchableOpacity
            style={s.deleteBtn}
            onPress={(e) => { e.stopPropagation(); onDelete(); }}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="trash-outline" size={14} color={COLORS.red} />
          </TouchableOpacity>
        )}
      </View>
    </TouchableOpacity>
  );
});

export default LeadCard;

const styles = (theme) => StyleSheet.create({
  card: {
    backgroundColor: theme.card,
    borderRadius: 16,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: theme.cardBorder,
    borderLeftWidth: 4,           // overridden per-card with scoreColor
    shadowColor: '#000',
    shadowOpacity: 0.07,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  row:    { flexDirection: 'row', alignItems: 'flex-start' },
  avatar: {
    width: 44, height: 44, borderRadius: 22,
    alignItems: 'center', justifyContent: 'center', marginRight: 11,
    borderWidth: 1.5,
  },
  avatarText: { fontSize: 18, fontWeight: '800' },

  info:    { flex: 1 },
  name:    { fontSize: 15, fontWeight: '700', color: theme.text },
  company: { fontSize: 12, color: theme.textMuted, marginTop: 2 },

  tagRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 6, flexWrap: 'wrap' },

  tierBadge:   { borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2, borderWidth: 1 },
  tierTxt:     { fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },

  industryTag: { backgroundColor: `${COLORS.primary}12`, borderRadius: 20, paddingHorizontal: 8, paddingVertical: 2, borderWidth: 1, borderColor: `${COLORS.primary}20` },
  industryTxt: { fontSize: 10, color: COLORS.primary, fontWeight: '600' },

  country: { fontSize: 11, color: theme.textMuted },

  right:       { alignItems: 'center', gap: 7, marginLeft: 8 },
  scoreCircle: { width: 40, height: 40, borderRadius: 20, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  scoreNum:    { fontSize: 14, fontWeight: '900' },

  bottom:    { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, flexWrap: 'wrap' },
  chip:      { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: theme.input, borderRadius: 20, paddingHorizontal: 8, paddingVertical: 3, borderWidth: 1, borderColor: theme.inputBorder },
  chipTxt:   { fontSize: 10, color: theme.textMuted, fontWeight: '500' },
  deleteBtn: { marginLeft: 'auto', padding: 4 },
});
