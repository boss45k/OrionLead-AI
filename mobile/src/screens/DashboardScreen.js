import React, { useState, useEffect, useCallback } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { setDashboardRefresher, clearDashboardRefresher } from '../utils/dashboardRefresh';
import {
  View, Text, ScrollView, StyleSheet, RefreshControl,
  TouchableOpacity, Dimensions, ActivityIndicator,
} from 'react-native';
import { LineChart, BarChart } from 'react-native-chart-kit';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { leadsAPI, analyticsAPI, syncAPI } from '../services/api';
import { triggerWebToMobile } from '../services/syncService';
import KPICard from '../components/KPICard';
import StatusBadge from '../components/StatusBadge';

const { width: SCREEN_W } = Dimensions.get('window');
const CHART_W = SCREEN_W - 48;

export default function DashboardScreen({ navigation }) {
  const { theme, isDark } = useTheme();
  const { user } = useAuth();

  const [stats, setStats]           = useState(null);
  const [analytics, setAnalytics]   = useState(null);
  const [recentLeads, setRecent]    = useState([]);
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [timeRange, setTimeRange]   = useState('30days');
  const [dashError, setDashError]   = useState(null);
  const [syncStatus, setSyncStatus] = useState(null);
  const [retrying, setRetrying]     = useState(false);
  const [syncing, setSyncing]       = useState(false);

  const fetchAll = useCallback(async (silent = false) => {
    setDashError(null);
    try {
      if (!silent) setRefreshing(true);
      const [statsRes, leadsRes, analyticsRes] = await Promise.allSettled([
        leadsAPI.getStats(),
        leadsAPI.getLeads({ page: 1, per_page: 10 }),
        analyticsAPI.getAnalytics(timeRange),
      ]);

      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value.data.stats);
      } else {
        console.warn('[Dashboard] getStats failed:', statsRes.reason?.message);
      }
      if (leadsRes.status === 'fulfilled') {
        setRecent(leadsRes.value.data.leads || []);
      } else {
        console.warn('[Dashboard] getLeads failed:', leadsRes.reason?.message);
      }
      if (analyticsRes.status === 'fulfilled') {
        setAnalytics(analyticsRes.value.data?.data);
      } else {
        console.warn('[Dashboard] getAnalytics failed:', analyticsRes.reason?.message);
      }

      // If all three failed, surface an error so the screen isn't blank
      if (
        statsRes.status === 'rejected' &&
        leadsRes.status === 'rejected' &&
        analyticsRes.status === 'rejected'
      ) {
        setDashError('Could not connect to the server. Check your connection.');
      }

      // Sync leads to Supabase in background
      triggerWebToMobile({ silent: true }).catch((err) => {
        console.warn('[Dashboard] triggerWebToMobile failed:', err?.message);
      });
    } catch (err) {
      console.error('[Dashboard] fetchAll unexpected error:', err?.message);
      setDashError('An unexpected error occurred. Please retry.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [timeRange]);

  useEffect(() => { fetchAll(false); }, [timeRange]);

  // Register this screen's refresher so LeadDetail (and any other screen)
  // can trigger an immediate silent refresh without the user switching tabs.
  useEffect(() => {
    setDashboardRefresher(() => fetchAll(true));
    return () => clearDashboardRefresher();
  }, [fetchAll]);

  // Also refresh silently whenever the tab gains focus (e.g. user switches tabs).
  useFocusEffect(
    useCallback(() => {
      fetchAll(true);
    }, [fetchAll])
  );

  // Sync status — non-blocking, never prevents dashboard from loading
  const refreshSyncStatus = useCallback(() => {
    syncAPI.getSyncStatus()
      .then((res) => setSyncStatus(res.data))
      .catch(() => {});
  }, []);

  useEffect(() => { refreshSyncStatus(); }, []);

  const handleRetrySync = useCallback(async () => {
    try {
      setRetrying(true);
      await syncAPI.retryFailed();
      refreshSyncStatus();
    } catch {
      // non-fatal
    } finally {
      setRetrying(false);
    }
  }, [refreshSyncStatus]);

  const handleSync = useCallback(async () => {
    if (syncing) return;
    setSyncing(true);
    try {
      await triggerWebToMobile({ silent: false });
      refreshSyncStatus();
    } catch {
      // non-fatal
    } finally {
      setSyncing(false);
    }
  }, [syncing, refreshSyncStatus]);

  const s = styles(theme, isDark);
  const chartConfig = {
    backgroundGradientFrom: theme.card,
    backgroundGradientTo: theme.card,
    color: (opacity = 1) => `rgba(99, 102, 241, ${opacity})`,
    labelColor: () => theme.textMuted,
    strokeWidth: 2,
    propsForDots: { r: '3', strokeWidth: '1', stroke: COLORS.primary },
    decimalPlaces: 0,
  };

  if (loading) {
    return (
      <View style={[s.root, s.center]}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (dashError) {
    return (
      <View style={[s.root, s.center]}>
        <Ionicons name="cloud-offline-outline" size={48} color={theme.textMuted} />
        <Text style={[s.empty, { marginTop: 12, marginBottom: 20 }]}>{dashError}</Text>
        <TouchableOpacity
          style={{ backgroundColor: COLORS.primary, paddingHorizontal: 28, paddingVertical: 12, borderRadius: 14, flexDirection: 'row', alignItems: 'center', gap: 6 }}
          onPress={() => { setLoading(true); fetchAll(false); }}
        >
          <Ionicons name="refresh" size={15} color="#fff" />
          <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const st = stats || {};
  const totalLeads      = st.total_leads || 0;
  const qualifiedLeads  = st.qualified_leads || 0;
  const contactedLeads  = st.contacted_leads || 0;
  const convertedLeads  = st.converted_leads || 0;
  const newThisWeek     = st.new_this_week || 0;
  const avgScore        = st.avg_score ? Math.round(st.avg_score) : 0;
  const qualRate        = st.qualification_rate ? st.qualification_rate.toFixed(1) : '0.0';
  const conversionRate  = st.conversion_rate ? st.conversion_rate.toFixed(1) : '0.0';

  const dailyData  = analytics?.daily_data || [];
  const chartLabels = dailyData
    .filter((_, i) => i % Math.ceil(dailyData.length / 6) === 0)
    .map((d) => (d.date || '').slice(5));
  const chartDataPoints = dailyData
    .filter((_, i) => i % Math.ceil(dailyData.length / 6) === 0)
    .map((d) => d.leads || 0);

  const RANGES = ['7days', '30days', '90days'];

  return (
    <ScrollView
      style={s.root}
      contentContainerStyle={s.scroll}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => fetchAll(false)} tintColor={COLORS.primary} />}
    >
      {/* Header */}
      <View style={s.headerRow}>
        <View>
          <Text style={s.greeting}>Good {greeting()}, {user?.full_name?.split(' ')[0] || 'there'} 👋</Text>
          <Text style={s.date}>{new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</Text>
        </View>
        <TouchableOpacity style={s.refreshBtn} onPress={() => fetchAll(false)}>
          <Ionicons name="refresh-outline" size={20} color={COLORS.primary} />
        </TouchableOpacity>
      </View>

      {/* Sync status banner — shown only when there is something actionable */}
      {syncStatus && (() => {
        const h = syncStatus.overall_health;
        if (h === 'ok') return false;
        if (h === 'unconfigured') return true;
        if (h === 'error') return syncStatus.failed_count > 0;
        if (h === 'stale') return syncStatus.pending_count > 0;
        return false;
      })() && (
        <View style={[
          s.syncBanner,
          syncStatus.overall_health === 'error'        ? s.syncError :
          syncStatus.overall_health === 'unconfigured' ? s.syncInfo  :
                                                         s.syncWarn,
        ]}>
          <Ionicons
            name={
              syncStatus.overall_health === 'error'        ? 'warning'           :
              syncStatus.overall_health === 'unconfigured' ? 'information-circle' :
                                                             'time-outline'
            }
            size={15}
            color={
              syncStatus.overall_health === 'error'        ? '#ef4444' :
              syncStatus.overall_health === 'unconfigured' ? '#6366f1' :
                                                             '#f59e0b'
            }
            style={{ marginRight: 6 }}
          />
          <Text style={[s.syncBannerText, {
            color: syncStatus.overall_health === 'error'        ? '#ef4444' :
                   syncStatus.overall_health === 'unconfigured' ? '#6366f1' :
                                                                  '#f59e0b',
            flex: 1,
          }]}>
            {syncStatus.overall_health === 'unconfigured'
              ? 'Sync not configured'
              : syncStatus.overall_health === 'error'
              ? `${syncStatus.failed_count} lead(s) failed to sync`
              : `${syncStatus.pending_count} lead(s) pending sync`}
          </Text>

          {syncStatus.overall_health === 'error' && (
            <TouchableOpacity
              onPress={handleRetrySync}
              disabled={retrying}
              style={s.syncRetryBtn}
            >
              {retrying
                ? <ActivityIndicator size="small" color="#ef4444" />
                : <Text style={s.syncRetryTxt}>Retry</Text>
              }
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* KPI Cards */}
      <View style={s.kpiGrid}>
        <KPICard title="Total Leads"  value={totalLeads}     icon="people"          color={COLORS.primary} sub={`+${newThisWeek} this week`} />
        <KPICard title="Qualified"    value={qualifiedLeads} icon="checkmark-circle" color={COLORS.cyan}    sub={`${qualRate}% of total`} />
        <KPICard title="Converted"    value={convertedLeads} icon="rocket"           color={COLORS.green}   sub={`${conversionRate}% rate`} />
        <KPICard title="Avg. Score"   value={avgScore}       icon="star"             color={COLORS.purple}  sub={avgScore > 70 ? 'High quality' : 'Keep going'} />
      </View>

      {/* Time Range Selector */}
      <View style={s.rangeRow}>
        {RANGES.map((r) => (
          <TouchableOpacity
            key={r}
            style={[s.rangeBtn, timeRange === r && s.rangeBtnActive]}
            onPress={() => setTimeRange(r)}
          >
            <Text style={[s.rangeTxt, timeRange === r && s.rangeTxtActive]}>
              {r === '7days' ? '7d' : r === '30days' ? '30d' : '90d'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Lead Activity Chart */}
      {chartLabels.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardTitle}>
            <Ionicons name="trending-up" size={14} color={COLORS.primary} /> Lead Activity
          </Text>
          <LineChart
            data={{ labels: chartLabels, datasets: [{ data: chartDataPoints.length ? chartDataPoints : [0] }] }}
            width={CHART_W}
            height={180}
            chartConfig={chartConfig}
            bezier
            style={{ borderRadius: 12, marginTop: 8 }}
            withInnerLines={false}
            withOuterLines={false}
          />
        </View>
      )}

      {/* Sales Funnel */}
      <View style={s.card}>
        <Text style={s.cardTitle}>
          <Ionicons name="funnel" size={14} color={COLORS.amber} /> Sales Funnel
        </Text>
        {[
          { label: 'Total',     value: totalLeads,     color: COLORS.primary },
          { label: 'Qualified', value: qualifiedLeads, color: COLORS.cyan },
          { label: 'Contacted', value: contactedLeads, color: COLORS.amber },
        ].map((step) => {
          const pct = totalLeads > 0 ? (step.value / totalLeads) * 100 : 0;
          return (
            <View key={step.label} style={s.funnelRow}>
              <View style={s.funnelLabelRow}>
                <Text style={s.funnelLabel}>{step.label}</Text>
                <Text style={[s.funnelValue, { color: step.color }]}>
                  {step.value} ({pct.toFixed(0)}%)
                </Text>
              </View>
              <View style={s.funnelBg}>
                <View style={[s.funnelFill, { width: `${pct}%`, backgroundColor: step.color }]} />
              </View>
            </View>
          );
        })}
      </View>

      {/* Quick Actions */}
      <View style={s.card}>
        <Text style={s.cardTitle}>
          <Ionicons name="flash" size={14} color={COLORS.amber} /> Quick Actions
        </Text>
        <View style={s.quickRow}>
          {[
            { icon: 'flash',      label: 'AI Collect', color: COLORS.primary, tab: 'AI'        },
            { icon: 'people',     label: 'All Leads',  color: COLORS.cyan,    tab: 'Leads'     },
            { icon: 'bar-chart',  label: 'Analytics',  color: COLORS.amber,   tab: 'Analytics' },
            { icon: 'sync',       label: 'Sync',       color: COLORS.green,   action: 'sync'   },
          ].map((a) => (
            <TouchableOpacity
              key={a.label}
              style={s.quickBtn}
              disabled={a.action === 'sync' && syncing}
              onPress={() => a.action === 'sync' ? handleSync() : navigation.navigate(a.tab)}
            >
              <View style={[s.quickIcon, { backgroundColor: `${a.color}18`, borderColor: `${a.color}22` }]}>
                {a.action === 'sync' && syncing
                  ? <ActivityIndicator size="small" color={a.color} />
                  : <Ionicons name={a.icon} size={22} color={a.color} />
                }
              </View>
              <Text style={s.quickLabel}>{a.action === 'sync' && syncing ? 'Syncing…' : a.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Recent Leads */}
      <View style={s.card}>
        <View style={s.sectionHeader}>
          <Text style={s.cardTitle}>
            <Ionicons name="people" size={14} color={COLORS.primary} /> Recent Leads
          </Text>
          <TouchableOpacity onPress={() => navigation.navigate('Leads')}>
            <Text style={s.viewAll}>View All</Text>
          </TouchableOpacity>
        </View>
        {recentLeads.length === 0 ? (
          <Text style={s.empty}>No leads yet — collect some to get started.</Text>
        ) : (
          recentLeads.slice(0, 5).map((lead) => (
            <TouchableOpacity
              key={lead.id}
              style={s.leadRow}
              onPress={() => navigation.navigate('Leads', { screen: 'LeadDetail', params: { leadId: lead.id } })}
            >
              <View style={s.leadAvatar}>
                <Text style={s.leadAvatarText}>{(lead.name || '?')[0].toUpperCase()}</Text>
              </View>
              <View style={s.leadInfo}>
                <Text style={s.leadName} numberOfLines={1}>{lead.name}</Text>
                <Text style={s.leadCompany} numberOfLines={1}>{lead.company || lead.email || '—'}</Text>
              </View>
              <View style={s.leadRight}>
                <StatusBadge status={lead.status} />
                <Text style={[s.score, { color: scoreColor(lead.qualification_score) }]}>
                  {Math.round(lead.qualification_score || 0)}
                </Text>
              </View>
            </TouchableOpacity>
          ))
        )}
      </View>

    </ScrollView>
  );
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'morning';
  if (h < 18) return 'afternoon';
  return 'evening';
}

function scoreColor(score) {
  if (!score) return COLORS.pending;
  if (score >= 80) return COLORS.green;
  if (score >= 60) return COLORS.amber;
  return COLORS.red;
}

const styles = (theme, isDark) => StyleSheet.create({
  root:    { flex: 1, backgroundColor: theme.bg },
  scroll:  { padding: 16, paddingBottom: 100 },
  center:  { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },

  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 },
  greeting:  { fontSize: 22, fontWeight: '800', color: theme.text, letterSpacing: 0.2 },
  date:      { fontSize: 12, color: theme.textMuted, marginTop: 3 },
  refreshBtn:{
    padding: 9, backgroundColor: `${COLORS.primary}18`,
    borderRadius: 13, borderWidth: 1, borderColor: `${COLORS.primary}25`,
  },

  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 },

  syncBanner:     { flexDirection: 'row', alignItems: 'center', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 9, marginBottom: 12, borderWidth: 1 },
  syncError:      { backgroundColor: 'rgba(239,68,68,0.08)', borderColor: 'rgba(239,68,68,0.2)' },
  syncWarn:       { backgroundColor: 'rgba(245,158,11,0.08)', borderColor: 'rgba(245,158,11,0.2)' },
  syncInfo:       { backgroundColor: 'rgba(99,102,241,0.08)', borderColor: 'rgba(99,102,241,0.2)' },
  syncBannerText: { fontSize: 12, fontWeight: '600' },
  syncRetryBtn:   { marginLeft: 10, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: 'rgba(239,68,68,0.4)', minWidth: 44, alignItems: 'center' },
  syncRetryTxt:   { fontSize: 11, fontWeight: '700', color: '#ef4444' },

  rangeRow:       { flexDirection: 'row', gap: 6, marginBottom: 16 },
  rangeBtn:       { paddingHorizontal: 16, paddingVertical: 7, borderRadius: 20, backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder },
  rangeBtnActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  rangeTxt:       { fontSize: 12, fontWeight: '700', color: theme.textMuted },
  rangeTxtActive: { color: '#fff' },

  card: {
    backgroundColor: theme.card, borderRadius: 18,
    padding: 16, marginBottom: 14,
    borderWidth: 1, borderColor: theme.cardBorder,
    shadowColor: '#000', shadowOpacity: 0.05,
    shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 2,
  },
  cardTitle: { fontSize: 13, fontWeight: '700', color: theme.text, marginBottom: 12 },

  quickRow:   { flexDirection: 'row', justifyContent: 'space-between' },
  quickBtn:   { alignItems: 'center', flex: 1 },
  quickIcon:  {
    width: 52, height: 52, borderRadius: 16,
    alignItems: 'center', justifyContent: 'center', marginBottom: 7,
    borderWidth: 1,
  },
  quickLabel: { fontSize: 11, fontWeight: '600', color: theme.textSecondary },

  funnelRow: { marginBottom: 12 },
  funnelLabelRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 },
  funnelLabel: { fontSize: 12, color: theme.textSecondary, fontWeight: '500' },
  funnelValue: { fontSize: 12, fontWeight: '700' },
  funnelBg:   { height: 8, backgroundColor: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)', borderRadius: 4, overflow: 'hidden' },
  funnelFill: { height: '100%', borderRadius: 4 },

  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  viewAll:       { fontSize: 12, color: COLORS.primary, fontWeight: '700' },
  empty:         { color: theme.textMuted, fontSize: 13, textAlign: 'center', paddingVertical: 24 },

  leadRow:       { flexDirection: 'row', alignItems: 'center', paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  leadAvatar:    { width: 40, height: 40, borderRadius: 20, backgroundColor: `${COLORS.primary}18`, alignItems: 'center', justifyContent: 'center', marginRight: 11, borderWidth: 1.5, borderColor: `${COLORS.primary}25` },
  leadAvatarText:{ fontSize: 16, fontWeight: '700', color: COLORS.primary },
  leadInfo:      { flex: 1 },
  leadName:      { fontSize: 14, fontWeight: '600', color: theme.text },
  leadCompany:   { fontSize: 12, color: theme.textMuted, marginTop: 2 },
  leadRight:     { alignItems: 'flex-end', gap: 4 },
  score:         { fontSize: 13, fontWeight: '800', marginTop: 2 },
});
