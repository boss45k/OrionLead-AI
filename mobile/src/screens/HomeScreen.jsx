import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl, ActivityIndicator, Dimensions,
} from 'react-native';
import { LineChart, BarChart, PieChart } from 'react-native-chart-kit';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { leadsAPI, analyticsAPI } from '../services/api';

const { width: SCREEN_W } = Dimensions.get('window');
const CHART_W  = SCREEN_W - 48;
const PALETTE  = COLORS.chart; // 8-colour array from ThemeContext

const RANGES = [
  { label: '7d',  value: '7days'  },
  { label: '30d', value: '30days' },
  { label: '90d', value: '90days' },
];

const STATUS_COLORS = {
  hot: COLORS.green, warm: COLORS.amber, cold: '#3b82f6',
  qualified: COLORS.primary, contacted: COLORS.cyan,
  converted: COLORS.green, pending: '#64748b',
};

export default function HomeScreen({ navigation }) {
  const { theme, isDark } = useTheme();
  const { user } = useAuth();

  const [statsRaw,   setStatsRaw]   = useState(null);
  const [analytics,  setAnalytics]  = useState(null);
  const [recent,     setRecent]     = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error,      setError]      = useState(null);
  const [timeRange,  setTimeRange]  = useState('30days');

  // ── fetch ──────────────────────────────────────────────────────────────────
  const fetchData = useCallback(async (range = timeRange) => {
    try {
      setError(null);
      const [statsRes, leadsRes, analyticsRes] = await Promise.allSettled([
        leadsAPI.getStats(),
        leadsAPI.getLeads({ page: 1, per_page: 10 }),
        analyticsAPI.getAnalytics(range),
      ]);

      if (statsRes.status    === 'fulfilled') setStatsRaw(statsRes.value.data?.stats   || {});
      if (leadsRes.status    === 'fulfilled') setRecent(leadsRes.value.data?.leads      || []);
      if (analyticsRes.status === 'fulfilled') setAnalytics(analyticsRes.value.data?.data || null);

      if ([statsRes, leadsRes, analyticsRes].every(r => r.status === 'rejected')) {
        setError('Could not connect to server. Pull down to retry.');
      }
    } catch {
      setError('Unexpected error. Pull down to retry.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [timeRange]);

  useEffect(() => { fetchData(); }, []);

  const onRefresh = () => { setRefreshing(true); fetchData(); };
  const handleRangeChange = (r) => { setTimeRange(r); fetchData(r); };

  // ── derived values ─────────────────────────────────────────────────────────
  const st           = statsRaw || {};
  const totalLeads   = st.total_leads      ?? 0;
  const qualified    = st.qualified_leads  ?? 0;
  const newThisWeek  = st.new_this_week    ?? 0;

  const summary    = analytics?.summary || {};
  const funnel     = analytics?.funnel   || {};
  const contacted  = summary.contacted_leads  ?? funnel.contacted ?? 0;
  const converted  = summary.converted_leads  ?? funnel.converted ?? 0;
  const avgScore   = Math.round(summary.average_score ?? 0);

  const bySource   = analytics?.distribution?.by_source   || {};
  const byInterest = analytics?.distribution?.by_interest || {};
  const byCountry  = st.by_country    || analytics?.distribution?.by_country   || {};
  const byIndustry = st.by_industry   || analytics?.distribution?.by_industry  || {};
  const scoreDist  = st.by_score_range || analytics?.score_distribution || analytics?.distribution?.by_score_tier || {};
  const qualRate   = totalLeads > 0 ? ((qualified   / totalLeads) * 100).toFixed(1) : '0.0';
  const convRate   = totalLeads > 0 ? ((converted   / totalLeads) * 100).toFixed(1) : '0.0';

  const firstName  = user?.full_name?.split(' ')[0] || user?.email?.split('@')[0] || 'there';
  const s          = styles(theme, isDark);

  // ── chart config ───────────────────────────────────────────────────────────
  const baseChart = {
    backgroundGradientFrom: theme.card,
    backgroundGradientTo:   theme.card,
    color: (opacity = 1) => `rgba(99,102,241,${opacity})`,
    labelColor: () => theme.textMuted,
    strokeWidth: 2,
    decimalPlaces: 0,
    propsForBackgroundLines: { stroke: 'transparent' },
  };

  // ── loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <View style={[s.root, s.center]}>
        <ActivityIndicator size="large" color={COLORS.primary} />
        <Text style={s.loadingTxt}>Loading dashboard…</Text>
      </View>
    );
  }

  // ── sales funnel steps ─────────────────────────────────────────────────────
  const funnelSteps = [
    { label: 'Total',     value: totalLeads, color: COLORS.primary, pct: 100 },
    { label: 'Qualified', value: qualified,  color: COLORS.cyan,    pct: totalLeads > 0 ? Math.round((qualified  / totalLeads) * 100) : 0 },
    { label: 'Contacted', value: contacted,  color: COLORS.amber,   pct: totalLeads > 0 ? Math.round((contacted  / totalLeads) * 100) : 0 },
    { label: 'Converted', value: converted,  color: COLORS.green,   pct: totalLeads > 0 ? Math.round((converted  / totalLeads) * 100) : 0 },
  ];

  // ── line chart (lead activity) ─────────────────────────────────────────────
  const daily       = analytics?.daily_data || [];
  const step        = Math.ceil(daily.length / 8) || 1;
  const sampled     = daily.filter((_, i) => i % step === 0).slice(0, 8);

  // ── source bars ────────────────────────────────────────────────────────────
  const sourceEntries = Object.entries(bySource).slice(0, 6);
  const sourceMax     = Math.max(...sourceEntries.map(([, v]) => v), 1);

  // ── interest chart ────────────────────────────────────────────────────────
  const interestKeys = Object.keys(byInterest).slice(0, 5);

  // ── country pie ───────────────────────────────────────────────────────────
  const pieData = Object.entries(byCountry).slice(0, 5).map(([name, pop], i) => ({
    name:            name.length > 10 ? name.slice(0, 9) + '…' : name,
    population:      pop,
    color:           PALETTE[i % PALETTE.length],
    legendFontColor: theme.textSecondary,
    legendFontSize:  10,
  }));

  // ── industry chart ────────────────────────────────────────────────────────
  const industryKeys = Object.keys(byIndustry).slice(0, 5);

  // ── score distribution ────────────────────────────────────────────────────
  const scoreKeys = Object.keys(scoreDist).slice(0, 5);

  // ── status breakdown ──────────────────────────────────────────────────────
  const statusItems = [
    { label: 'Qualified', value: qualified, color: COLORS.cyan   },
    { label: 'Contacted', value: contacted,  color: COLORS.amber  },
    { label: 'Converted', value: converted,  color: COLORS.green  },
    { label: 'Pending',   value: Math.max(0, totalLeads - qualified - contacted - converted), color: '#64748b' },
  ];

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <ScrollView
      style={s.root}
      contentContainerStyle={s.scroll}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />
      }
    >
      {/* ── Header ─────────────────────────────────────────────────── */}
      <View style={s.header}>
        <View>
          <Text style={s.greeting}>Hello, {firstName}</Text>
          <Text style={s.date}>
            {new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
          </Text>
        </View>
        <View style={s.avatarCircle}>
          <Text style={s.avatarText}>{firstName[0].toUpperCase()}</Text>
        </View>
      </View>

      {/* ── Error banner ──────────────────────────────────────────── */}
      {error && (
        <View style={s.errorBanner}>
          <Ionicons name="cloud-offline-outline" size={15} color={COLORS.red} />
          <Text style={s.errorText}>{error}</Text>
        </View>
      )}

      {/* ── Time range selector ───────────────────────────────────── */}
      <View style={s.rangeRow}>
        {RANGES.map((r) => (
          <TouchableOpacity
            key={r.value}
            style={[s.rangeBtn, timeRange === r.value && s.rangeBtnActive]}
            onPress={() => handleRangeChange(r.value)}
          >
            <Text style={[s.rangeTxt, timeRange === r.value && s.rangeTxtActive]}>{r.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ── 6 KPI Cards ───────────────────────────────────────────── */}
      <View style={s.kpiGrid}>
        {[
          { label: 'Total Leads', value: totalLeads,   icon: 'people',           color: COLORS.primary, sub: `+${newThisWeek} this week`,   up: newThisWeek > 0   },
          { label: 'Qualified',   value: qualified,     icon: 'checkmark-circle', color: COLORS.cyan,    sub: `${qualRate}% of total`,        up: qualified > 0     },
          { label: 'Contacted',   value: contacted,     icon: 'mail',             color: COLORS.amber,   sub: contacted > 0 ? `${Math.round((contacted / (totalLeads || 1)) * 100)}% reach` : 'None yet', up: contacted > 0 },
          { label: 'Converted',   value: converted,     icon: 'rocket',           color: COLORS.green,   sub: `${convRate}% rate`,            up: converted > 0     },
          { label: 'Avg. Score',  value: avgScore,      icon: 'star',             color: COLORS.purple,  sub: avgScore > 70 ? 'High quality' : avgScore > 40 ? 'Moderate' : 'Needs work', up: avgScore > 50 },
          { label: 'This Week',   value: newThisWeek,   icon: 'trending-up',      color: COLORS.orange,  sub: newThisWeek > 0 ? 'New leads' : 'No new leads',    up: newThisWeek > 0 },
        ].map((item) => (
          <View key={item.label} style={[s.kpiCard, { borderLeftColor: item.color }]}>
            <View style={s.kpiTop}>
              <View style={{ flex: 1 }}>
                <Text style={s.kpiLabel}>{item.label}</Text>
                <Text style={s.kpiValue}>{item.value}</Text>
              </View>
              <View style={[s.kpiIcon, { backgroundColor: `${item.color}18` }]}>
                <Ionicons name={item.icon} size={18} color={item.color} />
              </View>
            </View>
            <View style={s.kpiSub}>
              <Ionicons
                name={item.up ? 'arrow-up' : 'arrow-down'}
                size={10}
                color={item.up ? COLORS.green : theme.textMuted}
              />
              <Text style={[s.kpiSubTxt, { color: item.up ? COLORS.green : theme.textMuted }]}>
                {item.sub}
              </Text>
            </View>
          </View>
        ))}
      </View>

      {/* ── Lead Activity Line Chart ───────────────────────────────── */}
      {sampled.length > 1 && (
        <View style={s.card}>
          <Text style={s.cardTitle}>
            <Ionicons name="trending-up" size={13} color={COLORS.primary} />  Lead Activity
          </Text>
          <View style={s.legendRow}>
            <View style={[s.legendDot, { backgroundColor: COLORS.primary }]} />
            <Text style={s.legendTxt}>New Leads</Text>
            <View style={[s.legendDot, { backgroundColor: COLORS.cyan, marginLeft: 12 }]} />
            <Text style={s.legendTxt}>Qualified</Text>
          </View>
          <LineChart
            data={{
              labels:   sampled.map(d => (d.date || '').slice(5)),
              datasets: [
                { data: sampled.map(d => d.leads     || 0), color: () => COLORS.primary, strokeWidth: 2 },
                { data: sampled.map(d => d.qualified || 0), color: () => COLORS.cyan,    strokeWidth: 2 },
              ],
            }}
            width={CHART_W}
            height={180}
            chartConfig={baseChart}
            bezier
            withInnerLines={false}
            withOuterLines={false}
            withDots={false}
            style={{ borderRadius: 10, marginTop: 4 }}
          />
        </View>
      )}

      {/* ── Sales Funnel ──────────────────────────────────────────── */}
      <View style={s.card}>
        <Text style={s.cardTitle}>
          <Ionicons name="funnel" size={13} color={COLORS.amber} />  Sales Funnel
        </Text>
        {funnelSteps.map((step, i) => (
          <View key={step.label} style={{ marginBottom: 12 }}>
            <View style={s.funnelRow}>
              <Text style={s.funnelLabel}>{step.label}</Text>
              <Text style={[s.funnelVal, { color: step.color }]}>
                {step.value}{' '}
                <Text style={s.funnelPct}>({step.pct}%)</Text>
              </Text>
            </View>
            <View style={s.progBg}>
              <View style={[s.progFill, { width: `${step.pct}%`, backgroundColor: step.color }]} />
            </View>
            {i < funnelSteps.length - 1 && (
              <Text style={[s.funnelArrow, { color: theme.textMuted }]}>▼</Text>
            )}
          </View>
        ))}
        <View style={s.divRow}>
          <Text style={s.divLabel}>Overall conversion</Text>
          <Text style={[s.divValue, { color: COLORS.green }]}>{convRate}%</Text>
        </View>
      </View>

      {/* ── By Source (horizontal bars) ───────────────────────────── */}
      {sourceEntries.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}>
            <Ionicons name="bar-chart" size={13} color={COLORS.cyan} />  By Source
          </Text>
          {sourceEntries.map(([name, val], i) => (
            <View key={name} style={{ marginBottom: 9 }}>
              <View style={s.funnelRow}>
                <Text style={[s.funnelLabel, { flex: 1 }]} numberOfLines={1}>
                  {name.replace(/_/g, ' ')}
                </Text>
                <Text style={[s.funnelVal, { color: PALETTE[i % PALETTE.length] }]}>{val}</Text>
              </View>
              <View style={s.progBg}>
                <View
                  style={[
                    s.progFill,
                    { width: `${Math.round((val / sourceMax) * 100)}%`, backgroundColor: PALETTE[i % PALETTE.length] },
                  ]}
                />
              </View>
            </View>
          ))}
        </View>
      )}

      {/* ── Top Interests Bar Chart ───────────────────────────────── */}
      {interestKeys.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}>
            <Ionicons name="bulb" size={13} color={COLORS.amber} />  Top Interests
          </Text>
          <BarChart
            data={{
              labels:   interestKeys.map(k => k.length > 8 ? k.slice(0, 7) + '…' : k),
              datasets: [{ data: interestKeys.map(k => byInterest[k] || 0) }],
            }}
            width={CHART_W}
            height={150}
            chartConfig={{ ...baseChart, color: (op = 1) => `rgba(245,158,11,${op})` }}
            showBarTops={false}
            fromZero
            style={{ borderRadius: 10, marginTop: 4 }}
          />
        </View>
      )}

      {/* ── By Country Pie ────────────────────────────────────────── */}
      {pieData.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}>
            <Ionicons name="globe" size={13} color={COLORS.primary} />  By Country
          </Text>
          <PieChart
            data={pieData}
            width={CHART_W}
            height={160}
            chartConfig={baseChart}
            accessor="population"
            backgroundColor="transparent"
            paddingLeft="10"
            center={[10, 0]}
          />
        </View>
      )}

      {/* ── By Industry Bar Chart ─────────────────────────────────── */}
      {industryKeys.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}>
            <Ionicons name="business" size={13} color={COLORS.purple} />  By Industry
          </Text>
          <BarChart
            data={{
              labels:   industryKeys.map(k => k.length > 8 ? k.slice(0, 7) + '…' : k),
              datasets: [{ data: industryKeys.map(k => byIndustry[k] || 0) }],
            }}
            width={CHART_W}
            height={150}
            chartConfig={{ ...baseChart, color: (op = 1) => `rgba(139,92,246,${op})` }}
            showBarTops={false}
            fromZero
            style={{ borderRadius: 10, marginTop: 4 }}
          />
        </View>
      )}

      {/* ── Score Distribution Bar Chart ──────────────────────────── */}
      {scoreKeys.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}>
            <Ionicons name="podium" size={13} color={COLORS.orange} />  Score Distribution
          </Text>
          <BarChart
            data={{
              labels:   scoreKeys,
              datasets: [{ data: scoreKeys.map(k => scoreDist[k] || 0) }],
            }}
            width={CHART_W}
            height={150}
            chartConfig={{ ...baseChart, color: (op = 1) => `rgba(249,115,22,${op})` }}
            showBarTops={false}
            fromZero
            style={{ borderRadius: 10, marginTop: 4 }}
          />
        </View>
      )}

      {/* ── Lead Status Breakdown ─────────────────────────────────── */}
      <View style={s.card}>
        <Text style={s.cardTitle}>
          <Ionicons name="pie-chart" size={13} color='#14b8a6' />  Status Breakdown
        </Text>
        {statusItems.map(item => (
          <View key={item.label} style={{ marginBottom: 10 }}>
            <View style={s.funnelRow}>
              <Text style={s.funnelLabel}>{item.label}</Text>
              <Text style={[s.funnelVal, { color: item.color }]}>
                {item.value}{' '}
                <Text style={s.funnelPct}>/ {totalLeads}</Text>
              </Text>
            </View>
            <View style={s.progBg}>
              <View
                style={[
                  s.progFill,
                  { width: `${totalLeads > 0 ? Math.round((item.value / totalLeads) * 100) : 0}%`, backgroundColor: item.color },
                ]}
              />
            </View>
          </View>
        ))}
        <View style={s.divRow}>
          <Text style={s.divLabel}>Qualification rate</Text>
          <Text style={[s.divValue, { color: COLORS.cyan }]}>{qualRate}%</Text>
        </View>
      </View>

      {/* ── Recent Leads (10) ──────────────────────────────────────── */}
      <View style={[s.card, { marginBottom: 32 }]}>
        <View style={s.sectionHeader}>
          <Text style={s.cardTitle}>
            <Ionicons name="people" size={13} color={COLORS.primary} />  Recent Leads
          </Text>
          <TouchableOpacity
            onPress={() => navigation.navigate('Leads')}
            style={s.seeAllBtn}
          >
            <Text style={s.seeAll}>See All</Text>
            <Ionicons name="chevron-forward" size={12} color={COLORS.primary} />
          </TouchableOpacity>
        </View>

        {recent.length === 0 ? (
          <Text style={s.emptyText}>No leads yet — collect some to get started.</Text>
        ) : (
          recent.map((lead, idx) => {
            const score  = Math.round(lead.qualification_score || 0);
            const scClr  = score >= 75 ? COLORS.green : score >= 45 ? COLORS.amber : COLORS.red;
            const stClr  = STATUS_COLORS[(lead.status || 'pending').toLowerCase()] || '#64748b';
            return (
              <TouchableOpacity
                key={lead.id}
                style={[s.leadRow, idx === recent.length - 1 && { borderBottomWidth: 0 }]}
                onPress={() =>
                  navigation.navigate('Leads', { screen: 'LeadDetail', params: { leadId: lead.id } })
                }
                activeOpacity={0.7}
              >
                <View style={s.leadAvatar}>
                  <Text style={s.leadAvatarTxt}>{(lead.name || '?')[0].toUpperCase()}</Text>
                </View>
                <View style={s.leadMeta}>
                  <Text style={s.leadName} numberOfLines={1}>{lead.name || '—'}</Text>
                  <Text style={s.leadSub} numberOfLines={1}>
                    {[lead.company, lead.industry || lead.email].filter(Boolean).join(' · ') || '—'}
                  </Text>
                </View>
                {/* Score + status dot */}
                <View style={{ alignItems: 'flex-end', gap: 5 }}>
                  <Text style={[s.scoreNum, { color: scClr }]}>{score}</Text>
                  <View style={[s.statusDot, { backgroundColor: stClr }]} />
                </View>
                <Ionicons name="chevron-forward" size={14} color={theme.textMuted} style={{ marginLeft: 4 }} />
              </TouchableOpacity>
            );
          })
        )}
      </View>
    </ScrollView>
  );
}

const styles = (theme, isDark) => StyleSheet.create({
  root:       { flex: 1, backgroundColor: theme.bg },
  scroll:     { padding: 16, paddingBottom: 40 },
  center:     { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  loadingTxt: { fontSize: 13, color: theme.textMuted },

  /* Header */
  header:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  greeting:    { fontSize: 22, fontWeight: '800', color: theme.text },
  date:        { fontSize: 11, color: theme.textMuted, marginTop: 2 },
  avatarCircle:{ width: 42, height: 42, borderRadius: 21, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center', shadowColor: COLORS.primary, shadowOpacity: 0.3, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  avatarText:  { color: '#fff', fontSize: 17, fontWeight: '800' },

  /* Error */
  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(239,68,68,0.08)', borderRadius: 12, padding: 12, marginBottom: 12, borderWidth: 1, borderColor: 'rgba(239,68,68,0.2)' },
  errorText:   { color: COLORS.red, fontSize: 13, flex: 1 },

  /* Time range */
  rangeRow:       { flexDirection: 'row', gap: 6, marginBottom: 14 },
  rangeBtn:       { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20, backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder },
  rangeBtnActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  rangeTxt:       { fontSize: 12, fontWeight: '700', color: theme.textMuted },
  rangeTxtActive: { color: '#fff' },

  /* 2-col KPI grid */
  kpiGrid:  { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 },
  kpiCard:  {
    width: (SCREEN_W - 42) / 2,
    backgroundColor: theme.card, borderRadius: 16, padding: 14,
    borderWidth: 1, borderColor: theme.cardBorder, borderLeftWidth: 3,
    shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2,
  },
  kpiTop:    { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 8 },
  kpiLabel:  { fontSize: 10, fontWeight: '700', color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 4 },
  kpiValue:  { fontSize: 28, fontWeight: '800', color: theme.text, lineHeight: 32 },
  kpiIcon:   { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center', marginLeft: 8 },
  kpiSub:    { flexDirection: 'row', alignItems: 'center', gap: 4 },
  kpiSubTxt: { fontSize: 11, fontWeight: '500' },

  /* Cards */
  card:      {
    backgroundColor: theme.card, borderRadius: 18, padding: 16, marginBottom: 14,
    borderWidth: 1, borderColor: theme.cardBorder,
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2,
  },
  cardTitle: { fontSize: 13, fontWeight: '700', color: theme.text, marginBottom: 12 },

  /* Line chart legend */
  legendRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendTxt: { fontSize: 11, color: theme.textSecondary, fontWeight: '500' },

  /* Funnel + progress */
  funnelRow:  { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 },
  funnelLabel:{ fontSize: 12, color: theme.textSecondary, fontWeight: '500', flex: 1 },
  funnelVal:  { fontSize: 12, fontWeight: '700' },
  funnelPct:  { fontWeight: '400', color: theme.textMuted },
  funnelArrow:{ textAlign: 'center', fontSize: 10, marginTop: 4, marginBottom: 2 },
  progBg:     { height: 8, backgroundColor: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)', borderRadius: 4, overflow: 'hidden' },
  progFill:   { height: '100%', borderRadius: 4 },

  /* Divider summary row */
  divRow:   { flexDirection: 'row', justifyContent: 'space-between', marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: theme.cardBorder },
  divLabel: { fontSize: 11, color: theme.textMuted },
  divValue: { fontSize: 14, fontWeight: '800' },

  /* Section header */
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  seeAllBtn:     { flexDirection: 'row', alignItems: 'center', gap: 2 },
  seeAll:        { fontSize: 12, fontWeight: '600', color: COLORS.primary },

  /* Lead rows */
  leadRow:      { flexDirection: 'row', alignItems: 'center', paddingVertical: 11, gap: 10, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  leadAvatar:   { width: 40, height: 40, borderRadius: 20, backgroundColor: `${COLORS.primary}15`, alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: `${COLORS.primary}25` },
  leadAvatarTxt:{ fontSize: 15, fontWeight: '700', color: COLORS.primary },
  leadMeta:     { flex: 1 },
  leadName:     { fontSize: 13, fontWeight: '600', color: theme.text },
  leadSub:      { fontSize: 11, color: theme.textMuted, marginTop: 2 },
  scoreNum:     { fontSize: 14, fontWeight: '800' },
  statusDot:    { width: 7, height: 7, borderRadius: 4 },
  emptyText:    { color: theme.textMuted, textAlign: 'center', paddingVertical: 20, fontSize: 13 },
});
