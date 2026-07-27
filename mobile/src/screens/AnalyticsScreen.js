import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  ActivityIndicator, RefreshControl, Dimensions, Share,
} from 'react-native';
import { LineChart, PieChart } from 'react-native-chart-kit';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { analyticsAPI, leadsAPI } from '../services/api';
import { showInfo } from '../utils/dialog';
import StatusBadge from '../components/StatusBadge';

const { width: SCREEN_W } = Dimensions.get('window');
const CHART_W = SCREEN_W - 48;

const RANGES = [
  { label: '7d',  value: '7days'  },
  { label: '30d', value: '30days' },
  { label: '90d', value: '90days' },
  { label: 'All', value: 'all'    },
];

const SCORE_FILTERS = [
  { label: 'All',  value: undefined },
  { label: '70+',  value: 70 },
  { label: '80+',  value: 80 },
  { label: '90+',  value: 90 },
];

const statusColor = (v) => ({
  hot: COLORS.green, warm: COLORS.amber, cold: '#3b82f6',
  converted: COLORS.green, contacted: COLORS.cyan, qualified: COLORS.primary,
}[v] || '#94a3b8');

const CATEGORY_PALETTE = ['#6366f1', '#06b6d4', '#22c55e', '#f59e0b', '#ef4444', '#a855f7'];
const categoryColor = (i) => COLORS.chart?.[i % (COLORS.chart?.length || 6)] || CATEGORY_PALETTE[i % CATEGORY_PALETTE.length];

// Ranked horizontal bar row — full label always readable (no chart-axis truncation).
function RankedBarRow({ label, value, total, color, theme, isDark }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <View style={{ marginBottom: 10 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 }}>
        <Text style={{ fontSize: 12, color: theme.textSecondary, fontWeight: '500', flex: 1, marginRight: 8 }} numberOfLines={1}>{label}</Text>
        <Text style={{ fontSize: 12, fontWeight: '700', color }}>{value} ({pct}%)</Text>
      </View>
      <View style={{ height: 8, backgroundColor: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)', borderRadius: 4, overflow: 'hidden' }}>
        <View style={{ height: '100%', borderRadius: 4, width: `${Math.max(pct, 3)}%`, backgroundColor: color }} />
      </View>
    </View>
  );
}

// ── Mini progress bar ──────────────────────────────────────────────────────────
function MiniBar({ pct, color }) {
  return (
    <View style={{ height: 5, backgroundColor: 'rgba(148,163,184,0.2)', borderRadius: 3, overflow: 'hidden', marginTop: 3 }}>
      <View style={{ height: '100%', width: `${Math.min(pct, 100)}%`, backgroundColor: color, borderRadius: 3 }} />
    </View>
  );
}

export default function AnalyticsScreen() {
  const { theme, isDark } = useTheme();

  const [analytics, setAnalytics]     = useState(null);
  const [srcPerf, setSrcPerf]         = useState([]);
  const [loading, setLoading]         = useState(true);
  const [refreshing, setRefreshing]   = useState(false);
  const [timeRange, setTimeRange]     = useState('30days');
  const [fetchError, setFetchError]   = useState(null);

  // Top leads
  const [topLeads, setTopLeads]       = useState([]);
  const [topTotal, setTopTotal]       = useState(0);
  const [topPage, setTopPage]         = useState(1);
  const [topLoading, setTopLoading]   = useState(false);
  const [minScore, setMinScore]       = useState(undefined);
  const [srcFilter, setSrcFilter]     = useState(undefined);
  const [exporting, setExporting]     = useState(false);

  const fetchData = useCallback(async () => {
    setFetchError(null);
    try {
      const [analyticsRes, srcPerfRes] = await Promise.allSettled([
        analyticsAPI.getAnalytics(timeRange),
        analyticsAPI.getSourcePerformance?.() ?? Promise.reject('no endpoint'),
      ]);
      if (analyticsRes.status === 'fulfilled') {
        setAnalytics(analyticsRes.value.data?.data ?? null);
      }
      if (srcPerfRes.status === 'fulfilled') {
        setSrcPerf(srcPerfRes.value?.data?.data?.sources || []);
      } else if (analyticsRes.status === 'fulfilled') {
        setSrcPerf(analyticsRes.value.data?.data?.source_performance || []);
      }
    } catch (err) {
      setFetchError(err?.response?.data?.message || err?.message || 'Failed to load analytics');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [timeRange]);

  const fetchTopLeads = useCallback(async (page = 1) => {
    try {
      setTopLoading(true);
      const params = { page, per_page: 10, sort_by: 'qualification_score', sort_order: 'desc' };
      if (minScore !== undefined) params.min_score = minScore;
      if (srcFilter)              params.source    = srcFilter;
      const res = await leadsAPI.getLeads(params);
      const leads = res.data?.leads || [];
      const total = res.data?.total || 0;
      setTopLeads(page === 1 ? leads : (prev) => [...prev, ...leads]);
      setTopTotal(total);
      setTopPage(page);
    } catch {
      // non-fatal
    } finally {
      setTopLoading(false);
    }
  }, [minScore, srcFilter]);

  useEffect(() => { fetchData(); }, [timeRange]);
  useEffect(() => { fetchTopLeads(1); }, [minScore, srcFilter, fetchTopLeads]);

  // Silently refresh whenever this tab regains focus — e.g. after a collection
  // run finishes on the AI Engine tab (the tab stays mounted, so it wouldn't
  // otherwise pick up the new numbers).
  useFocusEffect(
    useCallback(() => {
      fetchData();
      fetchTopLeads(1);
    }, [fetchData, fetchTopLeads])
  );

  const handleExport = async () => {
    try {
      setExporting(true);
      const params = { page: 1, per_page: 100, sort_by: 'qualification_score', sort_order: 'desc' };
      if (minScore !== undefined) params.min_score = minScore;
      if (srcFilter)              params.source    = srcFilter;
      const res   = await leadsAPI.getLeads(params);
      const leads = res.data?.leads || [];
      if (!leads.length) { showInfo('No leads', 'No leads match the current filters'); return; }

      const header = 'Name,Email,Phone,Company,Position,Country,Industry,Score,Status,Source,Created';
      const rows   = leads.map((l) => [
        l.name, l.email, l.phone, l.company, l.position,
        l.country, l.industry, l.qualification_score, l.status, l.source,
        l.created_at ? new Date(l.created_at).toLocaleDateString() : '',
      ].map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
      const csv = [header, ...rows].join('\n');
      await Share.share({ message: csv, title: 'Leads Export' });
    } catch {
      // user cancelled share or error
    } finally {
      setExporting(false);
    }
  };

  const s = styles(theme, isDark);
  const chartConfig = {
    backgroundGradientFrom: theme.card,
    backgroundGradientTo:   theme.card,
    color: (opacity = 1) => `rgba(99,102,241,${opacity})`,
    labelColor: () => theme.textMuted,
    strokeWidth: 2,
    decimalPlaces: 0,
    propsForBackgroundLines: { stroke: 'transparent' },
  };

  if (loading) {
    return <View style={[s.root, s.center]}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  if (fetchError) {
    return (
      <View style={[s.root, s.center]}>
        <Ionicons name="cloud-offline-outline" size={48} color={theme.textMuted} />
        <Text style={s.errorText}>{fetchError}</Text>
        <TouchableOpacity style={s.retryBtn} onPress={() => { setLoading(true); fetchData(); }}>
          <Ionicons name="refresh" size={15} color="#fff" />
          <Text style={s.retryBtnText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const summary    = analytics?.summary || {};
  const daily      = analytics?.daily_data || [];
  const bySource   = analytics?.distribution?.by_source || {};
  const byInterest = analytics?.distribution?.by_interest || {};
  const byCountry  = analytics?.distribution?.by_country || {};
  const byIndustry = analytics?.distribution?.by_industry || {};
  const funnel     = analytics?.funnel || {};
  const byStatus   = analytics?.distribution?.by_status || {};
  const scoreDist  = analytics?.distribution?.by_score_tier || analytics?.score_distribution || {};

  const totalLeads = summary.total_leads     || 0;
  const qualified  = summary.qualified_leads || 0;
  const contacted  = summary.contacted_leads || 0;
  const converted  = funnel.converted || summary.converted_leads || 0;
  const avgScore   = Math.round(summary.average_score || 0);
  const qualRate   = totalLeads > 0 ? ((qualified / totalLeads) * 100).toFixed(1) : '0.0';
  const convRate   = totalLeads > 0 ? ((converted / totalLeads) * 100).toFixed(1) : '0.0';

  const KPI_CARDS = [
    { label: 'Total Leads', value: totalLeads, icon: 'people',           color: COLORS.primary, sub: 'all time' },
    { label: 'Qualified',   value: qualified,  icon: 'checkmark-circle', color: COLORS.cyan,    sub: `${qualRate}% of total` },
    { label: 'Contacted',   value: contacted,  icon: 'mail',             color: COLORS.amber,   sub: 'reached out' },
    { label: 'Converted',   value: converted,  icon: 'rocket',           color: '#22c55e',      sub: `${convRate}% rate` },
    { label: 'Avg Score',   value: avgScore,   icon: 'star',             color: '#8b5cf6',      sub: avgScore >= 70 ? 'High quality' : 'Keep scoring' },
    { label: 'Conv. Rate',  value: `${convRate}%`, icon: 'trending-up',  color: '#f97316',      sub: 'of all leads' },
  ];

  const sampleStep   = Math.ceil(daily.length / 8) || 1;
  const sampledDaily = daily.filter((_, i) => i % sampleStep === 0);
  const lineData = {
    labels: sampledDaily.map((d) => (d.date || '').slice(5)),
    datasets: [
      { data: sampledDaily.map((d) => d.leads || 0),     color: () => COLORS.primary, strokeWidth: 2 },
      { data: sampledDaily.map((d) => d.qualified || 0), color: () => COLORS.cyan,    strokeWidth: 2 },
    ],
    legend: ['New Leads', 'Qualified'],
  };

  // Ranked by count (not insertion order) so the biggest categories always
  // win the top-6 slots, and zero-count entries never render a dead row.
  const topKeysByValue = (obj, n = 6) =>
    Object.keys(obj)
      .filter((k) => (obj[k] || 0) > 0)
      .sort((a, b) => (obj[b] || 0) - (obj[a] || 0))
      .slice(0, n);

  const sourceKeys   = topKeysByValue(bySource);
  const industryKeys = topKeysByValue(byIndustry);
  const interestKeys = topKeysByValue(byInterest);
  const scoreKeys    = Object.keys(scoreDist).sort();
  const statusKeys   = Object.keys(byStatus).filter((k) => byStatus[k] > 0).slice(0, 5);

  const countryEntries = Object.entries(byCountry).slice(0, 5);
  const pieData = countryEntries.map(([name, population], i) => ({
    name: name.length > 10 ? name.slice(0, 9) + '…' : name,
    population,
    color: COLORS.chart?.[i % (COLORS.chart?.length || 6)] || ['#6366f1','#06b6d4','#22c55e','#f59e0b','#ef4444'][i % 5],
    legendFontColor: theme.textSecondary,
    legendFontSize: 11,
  }));

  // Source filter options derived from source performance data
  const srcOptions = [...new Set(srcPerf.map((s) => s.source).filter(Boolean))];

  const hasMoreLeads = topLeads.length < topTotal;

  return (
    <ScrollView
      style={s.root}
      contentContainerStyle={s.scroll}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); fetchTopLeads(1); }} tintColor={COLORS.primary} />
      }
    >
      {/* ── Time Range ──────────────────────────────────────── */}
      <View style={s.rangeRow}>
        {RANGES.map((r) => (
          <TouchableOpacity
            key={r.value}
            style={[s.rangeBtn, timeRange === r.value && s.rangeBtnActive]}
            onPress={() => setTimeRange(r.value)}
          >
            <Text style={[s.rangeTxt, timeRange === r.value && s.rangeTxtActive]}>{r.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ── KPI Grid ────────────────────────────────────────── */}
      <View style={s.kpiGrid}>
        {KPI_CARDS.map((item) => (
          <View key={item.label} style={[s.kpiCard, { borderLeftColor: item.color }]}>
            <View style={s.kpiTop}>
              <View style={{ flex: 1 }}>
                <Text style={s.kpiLabel}>{item.label}</Text>
                <Text style={[s.kpiVal, { color: item.color }]}>{item.value}</Text>
              </View>
              <View style={[s.kpiIcon, { backgroundColor: `${item.color}15` }]}>
                <Ionicons name={item.icon} size={17} color={item.color} />
              </View>
            </View>
            <Text style={s.kpiSub}>{item.sub}</Text>
          </View>
        ))}
      </View>

      {/* ── Lead Activity ─────────────────────────────────── */}
      {sampledDaily.length > 1 && (
        <View style={s.card}>
          <Text style={s.cardTitle}><Ionicons name="trending-up" size={13} color={COLORS.primary} /> Lead Activity</Text>
          <LineChart data={lineData} width={CHART_W} height={180} chartConfig={chartConfig}
            bezier style={{ borderRadius: 10, marginTop: 4 }} withInnerLines={false} withOuterLines={false} withDots={false} />
        </View>
      )}

      {/* ── Conversion Funnel ─────────────────────────────── */}
      <View style={s.card}>
        <Text style={s.cardTitle}><Ionicons name="funnel" size={13} color={COLORS.amber} /> Conversion Funnel</Text>
        {[
          { label: 'Total',     value: funnel.total     || totalLeads || 0, color: COLORS.primary },
          { label: 'Qualified', value: funnel.qualified || qualified   || 0, color: COLORS.cyan },
          { label: 'Contacted', value: funnel.contacted || contacted   || 0, color: COLORS.amber },
          { label: 'Converted', value: funnel.converted || converted   || 0, color: COLORS.green },
        ].map((step) => {
          const tot = funnel.total || totalLeads || 1;
          const pct = Math.round((step.value / tot) * 100);
          return (
            <View key={step.label} style={{ marginBottom: 10 }}>
              <View style={s.funnelLabelRow}>
                <Text style={s.funnelLabel}>{step.label}</Text>
                <Text style={[s.funnelValue, { color: step.color }]}>{step.value.toLocaleString()} ({pct}%)</Text>
              </View>
              <View style={s.funnelBg}>
                <View style={[s.funnelFill, { width: `${pct}%`, backgroundColor: step.color }]} />
              </View>
            </View>
          );
        })}
        <View style={s.convRow}>
          <Text style={s.convLabel}>Overall Conversion</Text>
          <Text style={[s.convValue, { color: COLORS.green }]}>{convRate}%</Text>
        </View>
      </View>

      {/* ── Score Distribution ─────────────────────────────── */}
      {scoreKeys.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}><Ionicons name="podium" size={13} color={COLORS.purple} /> Score Distribution</Text>
          <View style={s.legendRow}>
            {[
              { label: 'Qualified', sub: '70–100', color: COLORS.green  },
              { label: 'Warm',      sub: '40–69',  color: COLORS.amber  },
              { label: 'Cold',      sub: '0–39',   color: COLORS.primary },
            ].map((l) => (
              <View key={l.label} style={s.legendItem}>
                <View style={[s.legendDot, { backgroundColor: l.color }]} />
                <Text style={s.legendTxt}><Text style={{ color: l.color, fontWeight: '700' }}>{l.label}</Text> {l.sub}</Text>
              </View>
            ))}
          </View>
          {scoreKeys.map((tier) => {
            const val = scoreDist[tier] || 0;
            const tot = Object.values(scoreDist).reduce((a, b) => a + b, 0) || 1;
            const pct = Math.round((val / tot) * 100);
            const clr = tier.includes('80') || tier === 'high'   ? COLORS.green
                      : tier.includes('60') || tier === 'medium' ? COLORS.cyan
                      : tier.includes('40')                       ? COLORS.amber
                      : COLORS.primary;
            return (
              <View key={tier} style={{ marginBottom: 10 }}>
                <View style={s.funnelLabelRow}>
                  <Text style={s.funnelLabel}>{tier}</Text>
                  <Text style={[s.funnelValue, { color: clr }]}>{val} ({pct}%)</Text>
                </View>
                <View style={s.funnelBg}>
                  <View style={[s.funnelFill, { width: `${pct}%`, backgroundColor: clr }]} />
                </View>
              </View>
            );
          })}
        </View>
      )}

      {/* ── Status Breakdown ───────────────────────────────── */}
      {statusKeys.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}><Ionicons name="pie-chart" size={13} color={COLORS.purple} /> Status Breakdown</Text>
          {statusKeys.map((key) => {
            const val = byStatus[key] || 0;
            const tot = Object.values(byStatus).reduce((a, b) => a + b, 0) || 1;
            const pct = Math.round((val / tot) * 100);
            const clr = statusColor(key);
            return (
              <View key={key} style={{ marginBottom: 8 }}>
                <View style={s.funnelLabelRow}>
                  <Text style={s.funnelLabel}>{key.charAt(0).toUpperCase() + key.slice(1)}</Text>
                  <Text style={[s.funnelValue, { color: clr }]}>{val} ({pct}%)</Text>
                </View>
                <View style={s.funnelBg}>
                  <View style={[s.funnelFill, { width: `${pct}%`, backgroundColor: clr }]} />
                </View>
              </View>
            );
          })}
        </View>
      )}

      {/* ── By Industry ────────────────────────────────────── */}
      <View style={s.card}>
        <Text style={s.cardTitle}><Ionicons name="business" size={13} color={COLORS.purple} /> By Industry</Text>
        {industryKeys.length > 0 ? (
          industryKeys.map((k, i) => (
            <RankedBarRow key={k} label={k} value={byIndustry[k] || 0}
              total={Object.values(byIndustry).reduce((a, b) => a + b, 0)}
              color={categoryColor(i)} theme={theme} isDark={isDark} />
          ))
        ) : (
          <Text style={s.emptyTxt}>No industry data yet — collect some leads first.</Text>
        )}
      </View>

      {/* ── By Source ──────────────────────────────────────── */}
      <View style={s.card}>
        <Text style={s.cardTitle}><Ionicons name="bar-chart" size={13} color={COLORS.cyan} /> By Source</Text>
        {sourceKeys.length > 0 ? (
          sourceKeys.map((k, i) => (
            <RankedBarRow key={k} label={k.replace(/_/g, ' ')} value={bySource[k] || 0}
              total={Object.values(bySource).reduce((a, b) => a + b, 0)}
              color={categoryColor(i)} theme={theme} isDark={isDark} />
          ))
        ) : (
          <Text style={s.emptyTxt}>No source data yet — collect some leads first.</Text>
        )}
      </View>

      {/* ── Top Interests ──────────────────────────────────── */}
      <View style={s.card}>
        <Text style={s.cardTitle}><Ionicons name="bulb" size={13} color={COLORS.amber} /> Top Interests</Text>
        {interestKeys.length > 0 ? (
          interestKeys.map((k, i) => (
            <RankedBarRow key={k} label={k} value={byInterest[k] || 0}
              total={Object.values(byInterest).reduce((a, b) => a + b, 0)}
              color={categoryColor(i)} theme={theme} isDark={isDark} />
          ))
        ) : (
          <Text style={s.emptyTxt}>No interest data yet — collect some leads first.</Text>
        )}
      </View>

      {/* ── By Country ─────────────────────────────────────── */}
      {pieData.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}><Ionicons name="globe" size={13} color={COLORS.primary} /> By Country</Text>
          <PieChart data={pieData} width={CHART_W} height={160} chartConfig={chartConfig}
            accessor="population" backgroundColor="transparent" paddingLeft="10" center={[10, 0]} />
        </View>
      )}

      {/* ── Source Performance Table (web-matching) ──────── */}
      {srcPerf.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}><Ionicons name="stats-chart" size={13} color={COLORS.green} /> Source Performance</Text>
          <Text style={s.cardSub}>Sorted by qualification rate — higher is better</Text>

          {/* Header */}
          <View style={[s.tRow, { borderBottomWidth: 1.5, borderBottomColor: theme.cardBorder }]}>
            <Text style={[s.tCell, s.tHead, { flex: 2, textAlign: 'left' }]}>Source</Text>
            <Text style={[s.tCell, s.tHead]}>Total</Text>
            <Text style={[s.tCell, s.tHead]}>Qual.</Text>
            <Text style={[s.tCell, s.tHead, { flex: 1.5 }]}>Qual %</Text>
            <Text style={[s.tCell, s.tHead]}>Score</Text>
          </View>

          {[...srcPerf].sort((a, b) => (b.qual_rate || 0) - (a.qual_rate || 0)).slice(0, 10).map((row, i) => {
            const qRate  = row.qual_rate ?? (row.total > 0 ? Math.round((row.qualified / row.total) * 100) : 0);
            const qColor = qRate >= 60 ? COLORS.green : qRate >= 30 ? COLORS.amber : COLORS.red;
            const score  = row.avg_score != null ? Math.round(row.avg_score) : null;
            const sColor = score != null ? (score >= 70 ? COLORS.green : score >= 40 ? COLORS.amber : COLORS.red) : theme.textMuted;
            return (
              <View key={i} style={[s.tRow, i % 2 === 1 && s.tRowAlt]}>
                <Text style={[s.tCell, { flex: 2, textAlign: 'left', fontWeight: '600', color: theme.text }]} numberOfLines={1}>
                  {row.source || row.name || '—'}
                </Text>
                <Text style={s.tCell}>{(row.total ?? row.leads ?? 0).toLocaleString()}</Text>
                <Text style={[s.tCell, { color: COLORS.cyan }]}>{row.qualified ?? '—'}</Text>
                <View style={[s.tCell, { flex: 1.5 }]}>
                  <Text style={{ fontSize: 11, fontWeight: '700', color: qColor, textAlign: 'center' }}>{qRate}%</Text>
                  <MiniBar pct={qRate} color={qColor} />
                </View>
                <View style={[s.tCell, { alignItems: 'center' }]}>
                  {score != null ? (
                    <View style={{ backgroundColor: `${sColor}18`, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                      <Text style={{ fontSize: 11, fontWeight: '700', color: sColor }}>{score}</Text>
                    </View>
                  ) : <Text style={s.tCell}>—</Text>}
                </View>
              </View>
            );
          })}

          {/* Contacted / Converted sub-row if available */}
          {srcPerf.some((r) => r.contacted != null || r.converted != null) && (
            <View style={{ marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: theme.cardBorder }}>
              <Text style={[s.cardSub, { marginBottom: 8 }]}>Outreach summary</Text>
              <View style={[s.tRow, { borderBottomWidth: 1.5, borderBottomColor: theme.cardBorder }]}>
                <Text style={[s.tCell, s.tHead, { flex: 2, textAlign: 'left' }]}>Source</Text>
                <Text style={[s.tCell, s.tHead]}>Contacted</Text>
                <Text style={[s.tCell, s.tHead]}>Converted</Text>
              </View>
              {srcPerf.filter((r) => r.contacted != null || r.converted != null).slice(0, 8).map((row, i) => (
                <View key={i} style={[s.tRow, i % 2 === 1 && s.tRowAlt]}>
                  <Text style={[s.tCell, { flex: 2, textAlign: 'left', fontWeight: '600', color: theme.text }]} numberOfLines={1}>
                    {row.source || '—'}
                  </Text>
                  <Text style={[s.tCell, { color: COLORS.amber }]}>{row.contacted ?? '—'}</Text>
                  <Text style={[s.tCell, { color: (row.converted || 0) > 0 ? COLORS.green : theme.textMuted, fontWeight: (row.converted || 0) > 0 ? '700' : '400' }]}>
                    {row.converted ?? '—'}
                  </Text>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* ══ Top Leads by Score ═══════════════════════════════ */}
      <View style={[s.card, { marginBottom: 32 }]}>
        {/* Section header */}
        <View style={s.sectionHeader}>
          <View>
            <Text style={s.cardTitle}><Ionicons name="trophy" size={13} color={COLORS.amber} /> Top Leads by Score</Text>
            <Text style={s.cardSub}>{topTotal > 0 ? `${topTotal.toLocaleString()} leads` : 'Sorted by highest score first'}</Text>
          </View>
          <TouchableOpacity
            style={[s.exportBtn, exporting && { opacity: 0.5 }]}
            onPress={handleExport}
            disabled={exporting}
          >
            {exporting
              ? <ActivityIndicator size="small" color={COLORS.primary} />
              : <><Ionicons name="download-outline" size={14} color={COLORS.primary} /><Text style={s.exportTxt}>Export</Text></>
            }
          </TouchableOpacity>
        </View>

        {/* Score filter */}
        <View style={s.filterRow}>
          <Ionicons name="filter-outline" size={13} color={theme.textMuted} style={{ marginRight: 4 }} />
          {SCORE_FILTERS.map((f) => (
            <TouchableOpacity
              key={String(f.value)}
              style={[s.filterChip, minScore === f.value && s.filterChipActive]}
              onPress={() => setMinScore(f.value)}
            >
              <Text style={[s.filterChipTxt, minScore === f.value && s.filterChipTxtActive]}>{f.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Source filter */}
        {srcOptions.length > 0 && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TouchableOpacity
                style={[s.filterChip, srcFilter === undefined && s.filterChipActive]}
                onPress={() => setSrcFilter(undefined)}
              >
                <Text style={[s.filterChipTxt, srcFilter === undefined && s.filterChipTxtActive]}>All sources</Text>
              </TouchableOpacity>
              {srcOptions.slice(0, 8).map((src) => (
                <TouchableOpacity
                  key={src}
                  style={[s.filterChip, srcFilter === src && s.filterChipActive]}
                  onPress={() => setSrcFilter(src === srcFilter ? undefined : src)}
                >
                  <Text style={[s.filterChipTxt, srcFilter === src && s.filterChipTxtActive]}>{src}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
        )}

        {/* Leads list */}
        {topLoading && topLeads.length === 0 ? (
          <ActivityIndicator color={COLORS.primary} style={{ marginVertical: 20 }} />
        ) : topLeads.length === 0 ? (
          <View style={{ alignItems: 'center', paddingVertical: 28 }}>
            <Ionicons name="people-outline" size={36} color={theme.textMuted} />
            <Text style={{ color: theme.textMuted, marginTop: 8, fontSize: 13 }}>
              {minScore !== undefined || srcFilter ? 'No leads match the current filters' : 'No leads yet'}
            </Text>
            {(minScore !== undefined || srcFilter) && (
              <TouchableOpacity onPress={() => { setMinScore(undefined); setSrcFilter(undefined); }} style={{ marginTop: 8 }}>
                <Text style={{ color: COLORS.primary, fontSize: 13, fontWeight: '600' }}>Clear filters</Text>
              </TouchableOpacity>
            )}
          </View>
        ) : (
          topLeads.map((lead, i) => {
            const score = Math.round(lead.qualification_score || 0);
            const scoreColor = score >= 80 ? COLORS.green : score >= 60 ? COLORS.amber : score >= 35 ? '#3b82f6' : '#94a3b8';
            const sk = (lead.status || 'pending').toLowerCase();
            const stColor = statusColor(sk);
            return (
              <View key={lead.id || i} style={[s.leadRow, i % 2 === 1 && s.leadRowAlt]}>
                {/* Avatar */}
                <View style={[s.leadAvatar, { backgroundColor: `${scoreColor}14` }]}>
                  <Text style={[s.leadAvatarTxt, { color: scoreColor }]}>{(lead.name || '?')[0].toUpperCase()}</Text>
                </View>

                {/* Info */}
                <View style={{ flex: 1 }}>
                  <Text style={s.leadName} numberOfLines={1}>{lead.name}</Text>
                  <Text style={s.leadSub} numberOfLines={1}>
                    {lead.position ? `${lead.position} · ` : ''}{lead.company || lead.email || '—'}
                  </Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 }}>
                    {lead.country && <Text style={s.leadMeta}>{lead.country}</Text>}
                    {lead.source  && <Text style={s.leadMeta}>{lead.source}</Text>}
                  </View>
                </View>

                {/* Score + Status */}
                <View style={{ alignItems: 'center', gap: 5 }}>
                  <View style={[s.scoreCircle, { borderColor: scoreColor }]}>
                    <Text style={[s.scoreNum, { color: scoreColor }]}>{score}</Text>
                  </View>
                  <View style={{ backgroundColor: `${stColor}18`, borderRadius: 6, paddingHorizontal: 5, paddingVertical: 2 }}>
                    <Text style={{ fontSize: 9, fontWeight: '700', color: stColor }}>{sk.toUpperCase()}</Text>
                  </View>
                </View>
              </View>
            );
          })
        )}

        {/* Load more */}
        {hasMoreLeads && (
          <TouchableOpacity
            style={[s.loadMoreBtn, topLoading && { opacity: 0.5 }]}
            onPress={() => fetchTopLeads(topPage + 1)}
            disabled={topLoading}
          >
            {topLoading
              ? <ActivityIndicator size="small" color={COLORS.primary} />
              : <Text style={s.loadMoreTxt}>Load more ({topTotal - topLeads.length} remaining)</Text>
            }
          </TouchableOpacity>
        )}
      </View>

    </ScrollView>
  );
}

const styles = (theme, isDark) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  scroll: { padding: 16, paddingBottom: 100 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24, gap: 12 },
  errorText:    { fontSize: 14, textAlign: 'center', color: theme.textMuted, lineHeight: 20, marginBottom: 16 },
  retryBtn:     { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, paddingHorizontal: 28, paddingVertical: 12, borderRadius: 14 },
  retryBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },

  rangeRow:       { flexDirection: 'row', gap: 6, marginBottom: 16 },
  rangeBtn:       { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20, backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder },
  rangeBtnActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  rangeTxt:       { fontSize: 12, fontWeight: '700', color: theme.textMuted },
  rangeTxtActive: { color: '#fff' },

  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 },
  kpiCard: {
    width: (SCREEN_W - 42) / 2,
    backgroundColor: theme.card, borderRadius: 16, padding: 14,
    borderWidth: 1, borderColor: theme.cardBorder, borderLeftWidth: 4,
    shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2,
  },
  kpiTop:  { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 6 },
  kpiLabel:{ fontSize: 10, fontWeight: '700', color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 3 },
  kpiVal:  { fontSize: 26, fontWeight: '800', lineHeight: 30 },
  kpiIcon: { width: 34, height: 34, borderRadius: 10, alignItems: 'center', justifyContent: 'center', marginLeft: 8 },
  kpiSub:  { fontSize: 10, color: theme.textMuted, fontWeight: '500' },

  card: {
    backgroundColor: theme.card, borderRadius: 18, padding: 16, marginBottom: 14,
    borderWidth: 1, borderColor: theme.cardBorder,
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2,
  },
  cardTitle:     { fontSize: 13, fontWeight: '700', color: theme.text, marginBottom: 4 },
  cardSub:       { fontSize: 11, color: theme.textMuted, marginBottom: 10 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 },

  legendRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 12 },
  legendItem:{ flexDirection: 'row', alignItems: 'center', gap: 5 },
  legendDot: { width: 8, height: 8, borderRadius: 2, opacity: 0.85 },
  legendTxt: { fontSize: 11, color: theme.textMuted },

  funnelLabelRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 },
  funnelLabel:    { fontSize: 12, color: theme.textSecondary, fontWeight: '500' },
  funnelValue:    { fontSize: 12, fontWeight: '700' },
  funnelBg:       { height: 8, backgroundColor: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)', borderRadius: 4, overflow: 'hidden' },
  funnelFill:     { height: '100%', borderRadius: 4 },
  convRow:        { flexDirection: 'row', justifyContent: 'space-between', marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: theme.cardBorder },
  convLabel:      { fontSize: 12, color: theme.textMuted, fontWeight: '500' },
  convValue:      { fontSize: 16, fontWeight: '800' },

  // Source performance table
  tRow:    { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: `${theme.cardBorder}80` },
  tRowAlt: { backgroundColor: isDark ? 'rgba(255,255,255,0.025)' : 'rgba(0,0,0,0.02)' },
  tCell:   { flex: 1, fontSize: 12, color: theme.textSecondary, textAlign: 'center' },
  tHead:   { fontSize: 10, fontWeight: '700', color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.3 },

  // Export button
  exportBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 10, borderWidth: 1, borderColor: `${COLORS.primary}40`, backgroundColor: `${COLORS.primary}10` },
  exportTxt: { fontSize: 12, fontWeight: '700', color: COLORS.primary },

  // Filters
  filterRow:         { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10, flexWrap: 'wrap' },
  filterChip:        { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20, backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder },
  filterChipActive:  { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  filterChipTxt:     { fontSize: 11, fontWeight: '600', color: theme.textMuted },
  filterChipTxtActive:{ color: '#fff' },

  // Lead rows
  leadRow:      { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: `${theme.cardBorder}60` },
  leadRowAlt:   { backgroundColor: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.015)' },
  leadAvatar:   { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  leadAvatarTxt:{ fontSize: 15, fontWeight: '800' },
  leadName:     { fontSize: 13, fontWeight: '700', color: theme.text },
  leadSub:      { fontSize: 11, color: theme.textMuted, marginTop: 1 },
  leadMeta:     { fontSize: 10, color: theme.textMuted },
  scoreCircle:  { width: 36, height: 36, borderRadius: 18, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  scoreNum:     { fontSize: 12, fontWeight: '900' },

  loadMoreBtn:  { alignItems: 'center', paddingVertical: 12, marginTop: 6, borderTopWidth: 1, borderTopColor: theme.cardBorder },
  loadMoreTxt:  { fontSize: 13, fontWeight: '600', color: COLORS.primary },
});
