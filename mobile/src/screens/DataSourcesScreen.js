import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  Switch, ActivityIndicator, Modal, TextInput, RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { sourcesAPI } from '../services/api';
import { showError, showWarning, showConfirm } from '../utils/dialog';

function timeAgo(iso) {
  if (!iso) return null;
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)    return 'just now';
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const isSystem = (r) => !!(r.config?.system);

const TYPE_META = {
  API:      { icon: 'globe-outline',    color: '#06b6d4' },
  CSV:      { icon: 'document-outline', color: '#8b5cf6' },
  Database: { icon: 'server-outline',   color: '#f59e0b' },
  Web:      { icon: 'search-outline',   color: '#22c55e' },
};
const TYPES     = Object.keys(TYPE_META);
const FREQ_OPTS = ['manual', 'hourly', 'daily', 'weekly'];

const emptyForm = () => ({
  name: '', type: 'API', description: '', sync_frequency: 'manual',
  api_url: '', api_key: '', db_query: '', search_query: '',
});

function StatusBadge({ status, enabled }) {
  if (!enabled) {
    return (
      <View style={[sbSt.badge, { backgroundColor: '#94a3b820' }]}>
        <Ionicons name="time-outline" size={10} color="#94a3b8" />
        <Text style={[sbSt.txt, { color: '#94a3b8' }]}>Disabled</Text>
      </View>
    );
  }
  if (status === 'error') {
    return (
      <View style={[sbSt.badge, { backgroundColor: `${COLORS.red}18` }]}>
        <Ionicons name="warning-outline" size={10} color={COLORS.red} />
        <Text style={[sbSt.txt, { color: COLORS.red }]}>Error</Text>
      </View>
    );
  }
  if (status === 'active') {
    return (
      <View style={[sbSt.badge, { backgroundColor: `${COLORS.green}18` }]}>
        <Ionicons name="checkmark-circle-outline" size={10} color={COLORS.green} />
        <Text style={[sbSt.txt, { color: COLORS.green }]}>Active</Text>
      </View>
    );
  }
  if (status === 'inactive') {
    return (
      <View style={[sbSt.badge, { backgroundColor: '#f59e0b18' }]}>
        <Ionicons name="warning-outline" size={10} color="#f59e0b" />
        <Text style={[sbSt.txt, { color: '#f59e0b' }]}>No API Key</Text>
      </View>
    );
  }
  return (
    <View style={[sbSt.badge, { backgroundColor: '#94a3b820' }]}>
      <Ionicons name="time-outline" size={10} color="#94a3b8" />
      <Text style={[sbSt.txt, { color: '#94a3b8' }]}>Idle</Text>
    </View>
  );
}

const sbSt = StyleSheet.create({
  badge: { flexDirection: 'row', alignItems: 'center', gap: 4, borderRadius: 20, paddingHorizontal: 8, paddingVertical: 3 },
  txt:   { fontSize: 10, fontWeight: '700' },
});

export default function DataSourcesScreen() {
  const { theme } = useTheme();
  const s = styles(theme);

  const [sources, setSources]     = useState([]);
  const [stats, setStats]         = useState(null);
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefresh]  = useState(false);
  const [syncing, setSyncing]     = useState({});
  const [toggling, setToggling]   = useState({});
  const [syncResult, setSyncResult] = useState(null);

  const [showAdd, setShowAdd]   = useState(false);
  const [editSrc, setEditSrc]   = useState(null);
  const [cfgSrc, setCfgSrc]     = useState(null);
  const [saving, setSaving]     = useState(false);
  const [form, setForm]         = useState(emptyForm());
  const [cfgForm, setCfgForm]   = useState({
    max_leads: '40', keywords: '', locations: '', titles: '', industries: '',
  });

  const fetchData = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const [srcRes, statRes] = await Promise.allSettled([
        sourcesAPI.getAll(),
        sourcesAPI.getStats(),
      ]);
      if (srcRes.status === 'fulfilled') {
        const raw = srcRes.value.data;
        setSources(Array.isArray(raw) ? raw : (raw?.sources || raw?.data || []));
      }
      if (statRes.status === 'fulfilled') {
        const raw = statRes.value.data;
        setStats(raw?.stats || raw);
      }
    } catch (err) {
      console.warn('[Sources] fetch failed:', err?.message);
    } finally {
      setLoading(false);
      setRefresh(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, []);

  // ── Toggle ────────────────────────────────────────────────────────────────
  const handleToggle = async (src) => {
    const newEnabled = !(src.enabled ?? src.is_active);
    setSources((p) => p.map((x) => x.id === src.id ? { ...x, enabled: newEnabled, is_active: newEnabled } : x));
    setToggling((p) => ({ ...p, [src.id]: true }));
    try {
      await sourcesAPI.update(src.id, { enabled: newEnabled });
    } catch (err) {
      setSources((p) => p.map((x) => x.id === src.id ? { ...x, enabled: !newEnabled, is_active: !newEnabled } : x));
      showError('Error', err?.response?.data?.message || 'Failed to update source');
    } finally {
      setToggling((p) => ({ ...p, [src.id]: false }));
    }
  };

  // ── Sync ──────────────────────────────────────────────────────────────────
  const handleSync = async (src) => {
    setSyncing((p) => ({ ...p, [src.id]: true }));
    setSyncResult(null);
    try {
      const res = await sourcesAPI.sync(src.id);
      const d   = res.data?.data || {};
      const msg = res.data?.message || `Synced ${d.synced_records || 0} new leads`;
      setSyncResult({ sourceId: src.id, success: true, message: msg, data: d });
      fetchData(true);
    } catch (err) {
      setSyncResult({ sourceId: src.id, success: false, message: err?.response?.data?.message || 'Sync failed' });
      fetchData(true);
    } finally {
      setSyncing((p) => ({ ...p, [src.id]: false }));
    }
  };

  // ── Delete ────────────────────────────────────────────────────────────────
  const handleDelete = (src) => {
    showConfirm(
      'Delete Source',
      `Delete "${src.name}"? This cannot be undone.`,
      async () => {
        try {
          await sourcesAPI.remove(src.id);
          setSources((p) => p.filter((x) => x.id !== src.id));
          if (syncResult?.sourceId === src.id) setSyncResult(null);
        } catch (err) {
          showError('Error', err?.response?.data?.message || 'Failed to delete');
        }
      },
      undefined, 'Delete', 'Cancel', 'danger',
    );
  };

  // ── Create custom source ──────────────────────────────────────────────────
  const buildConfig = (f) => {
    if (f.type === 'API')      return { url: f.api_url, api_key: f.api_key };
    if (f.type === 'Database') return { query: f.db_query };
    if (f.type === 'Web')      return { search_query: f.search_query };
    return {};
  };

  const handleCreate = async () => {
    if (!form.name.trim()) { showWarning('Required', 'Source name is required'); return; }
    setSaving(true);
    try {
      await sourcesAPI.create({
        name: form.name.trim(),
        type: form.type,
        description: form.description.trim(),
        sync_frequency: form.sync_frequency,
        enabled: true,
        config: buildConfig(form),
      });
      setShowAdd(false);
      setForm(emptyForm());
      fetchData(true);
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to create source');
    } finally {
      setSaving(false);
    }
  };

  // ── Update custom source ──────────────────────────────────────────────────
  const handleUpdate = async () => {
    if (!editSrc) return;
    setSaving(true);
    try {
      await sourcesAPI.update(editSrc.id, {
        name: editSrc.name,
        description: editSrc.description,
        sync_frequency: editSrc.sync_frequency,
        config: editSrc.config || {},
      });
      setEditSrc(null);
      fetchData(true);
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to update source');
    } finally {
      setSaving(false);
    }
  };

  // ── Configure system source ───────────────────────────────────────────────
  const openConfigure = (src) => {
    const sc = src.config?.sync_config || {};
    setCfgSrc(src);
    setCfgForm({
      max_leads:  String(sc.max_leads  || (src.config?.action === 'enrich' ? 50 : 40)),
      keywords:   sc.keywords   || '',
      locations:  (sc.locations  || []).join(', '),
      titles:     (sc.titles     || []).join(', '),
      industries: (sc.industries || []).join(', '),
    });
  };

  const handleConfigure = async () => {
    if (!cfgSrc) return;
    setSaving(true);
    const sync_config = { max_leads: Number(cfgForm.max_leads) || 40 };
    if (cfgForm.keywords)   sync_config.keywords   = cfgForm.keywords.trim();
    if (cfgForm.locations)  sync_config.locations  = cfgForm.locations.split(',').map((x) => x.trim()).filter(Boolean);
    if (cfgForm.titles)     sync_config.titles     = cfgForm.titles.split(',').map((x) => x.trim()).filter(Boolean);
    if (cfgForm.industries) sync_config.industries = cfgForm.industries.split(',').map((x) => x.trim()).filter(Boolean);
    try {
      await sourcesAPI.update(cfgSrc.id, { sync_config });
      setCfgSrc(null);
      fetchData(true);
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to save parameters');
    } finally {
      setSaving(false);
    }
  };

  const setF = (key, val) => setForm((p) => ({ ...p, [key]: val }));

  // ── Derived stats ─────────────────────────────────────────────────────────
  const systemSources = sources.filter(isSystem);
  const userSources   = sources.filter((x) => !isSystem(x));
  const apiKeysSet    = systemSources.filter((x) => x.status === 'active').length;
  const totalRecords  = stats?.total_records  || 0;
  const avgPerf       = Math.round(stats?.average_performance || 0);
  const lastSync      = timeAgo(stats?.last_sync);

  // ── Source card ───────────────────────────────────────────────────────────
  const SourceCard = ({ src }) => {
    const meta    = TYPE_META[src.type] || TYPE_META.Web;
    const sys     = isSystem(src);
    const enabled = !!(src.enabled ?? src.is_active);
    const perf    = src.performance ?? 0;
    const records = (src.records ?? src.records_count ?? 0);
    const ago     = timeAgo(src.last_sync);

    return (
      <View style={s.sourceCard}>
        <View style={s.srcHeader}>
          <View style={[s.srcIconWrap, { backgroundColor: `${meta.color}18` }]}>
            <Ionicons name={meta.icon} size={17} color={meta.color} />
            {sys && (
              <View style={s.starBadge}>
                <Ionicons name="star" size={9} color="#6366f1" />
              </View>
            )}
          </View>
          <View style={s.srcInfo}>
            <Text style={s.srcName} numberOfLines={1}>{src.name}</Text>
            <Text style={s.srcType} numberOfLines={1}>{src.type} · {src.sync_frequency || 'manual'}</Text>
          </View>
          <Switch
            value={enabled}
            onValueChange={() => handleToggle(src)}
            disabled={!!toggling[src.id]}
            trackColor={{ false: theme.inputBorder, true: `${COLORS.green}80` }}
            thumbColor={enabled ? COLORS.green : '#888'}
            style={{ transform: [{ scaleX: 0.85 }, { scaleY: 0.85 }] }}
          />
        </View>

        <View style={s.srcMeta}>
          <StatusBadge status={src.status} enabled={enabled} />
          <Text style={s.srcRecords}>{records.toLocaleString()} records</Text>
          {ago && <Text style={s.srcSync}>{ago}</Text>}
        </View>

        {src.last_error && src.status === 'error' && (
          <View style={s.errorRow}>
            <Ionicons name="warning-outline" size={12} color={COLORS.red} />
            <Text style={s.errorTxt} numberOfLines={2}>{src.last_error}</Text>
          </View>
        )}

        {perf > 0 && (
          <View style={s.perfRow}>
            <Text style={s.perfLbl}>Perf</Text>
            <View style={s.perfBg}>
              <View style={[s.perfFill, {
                width: `${Math.min(perf, 100)}%`,
                backgroundColor: perf >= 80 ? COLORS.green : perf >= 50 ? '#f59e0b' : COLORS.red,
              }]} />
            </View>
            <Text style={s.perfPct}>{Math.round(perf)}%</Text>
          </View>
        )}

        <View style={s.srcActions}>
          <TouchableOpacity
            style={[s.actionBtn, { backgroundColor: `${COLORS.cyan}15`, borderColor: `${COLORS.cyan}30` }]}
            onPress={() => handleSync(src)}
            disabled={!!syncing[src.id] || !enabled}
          >
            {syncing[src.id]
              ? <ActivityIndicator size="small" color={COLORS.cyan} />
              : <Ionicons name="sync" size={13} color={enabled ? COLORS.cyan : '#94a3b8'} />
            }
            <Text style={[s.actionTxt, { color: enabled ? COLORS.cyan : '#94a3b8' }]}>Sync</Text>
          </TouchableOpacity>

          {sys ? (
            <TouchableOpacity
              style={[s.actionBtn, { backgroundColor: `${COLORS.primary}15`, borderColor: `${COLORS.primary}30` }]}
              onPress={() => openConfigure(src)}
            >
              <Ionicons name="settings-outline" size={13} color={COLORS.primary} />
              <Text style={[s.actionTxt, { color: COLORS.primary }]}>Configure</Text>
            </TouchableOpacity>
          ) : (
            <>
              <TouchableOpacity
                style={[s.actionBtn, { backgroundColor: '#f59e0b15', borderColor: '#f59e0b30' }]}
                onPress={() => setEditSrc({ ...src, config: src.config || {} })}
              >
                <Ionicons name="pencil-outline" size={13} color="#f59e0b" />
                <Text style={[s.actionTxt, { color: '#f59e0b' }]}>Edit</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.actionBtn, { backgroundColor: `${COLORS.red}12`, borderColor: `${COLORS.red}25` }]}
                onPress={() => handleDelete(src)}
              >
                <Ionicons name="trash-outline" size={13} color={COLORS.red} />
                <Text style={[s.actionTxt, { color: COLORS.red }]}>Delete</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      </View>
    );
  };

  const isWebSrc = ['web_public', 'social_media'].includes(cfgSrc?.config?.system_key);
  const isEnrich = cfgSrc?.config?.action === 'enrich';
  const isApollo = cfgSrc?.config?.system_key === 'apollo';

  if (loading && sources.length === 0) {
    return <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  return (
    <View style={s.root}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 100 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => { setRefresh(true); fetchData(); }}
            tintColor={COLORS.primary}
          />
        }
      >
        {/* ── KPI Cards ─────────────────────────────────────────────────── */}
        <View style={s.kpiGrid}>
          {[
            { title: 'Built-in', value: systemSources.length, sub: `${apiKeysSet} API keys set`, icon: 'star-outline', color: COLORS.primary },
            { title: 'Total Records', value: totalRecords.toLocaleString(), sub: 'all sources', icon: 'people-outline', color: COLORS.green },
            { title: 'Avg Perf', value: `${avgPerf}%`, bar: avgPerf, icon: 'flash-outline', color: '#f59e0b' },
            { title: 'Last Sync', value: lastSync || '—', sub: 'most recent', icon: 'time-outline', color: COLORS.cyan },
          ].map(({ title, value, sub, icon, color, bar }) => (
            <View key={title} style={[s.kpiCard, { borderLeftColor: color }]}>
              <View style={s.kpiTop}>
                <View style={{ flex: 1 }}>
                  <Text style={s.kpiTitle}>{title}</Text>
                  <Text style={[s.kpiVal, { color }]}>{value}</Text>
                </View>
                <Ionicons name={icon} size={20} color={color} style={{ opacity: 0.6 }} />
              </View>
              {bar != null ? (
                <View style={s.kpiBar}>
                  <View style={[s.kpiBarFill, {
                    width: `${Math.min(bar, 100)}%`,
                    backgroundColor: bar >= 70 ? COLORS.green : '#f59e0b',
                  }]} />
                </View>
              ) : (
                <Text style={s.kpiSub}>{sub}</Text>
              )}
            </View>
          ))}
        </View>

        {/* ── Sync result banner ─────────────────────────────────────────── */}
        {syncResult && (
          <View style={[
            s.banner,
            { backgroundColor: syncResult.success ? `${COLORS.green}15` : `${COLORS.red}15`,
              borderColor:      syncResult.success ? `${COLORS.green}40` : `${COLORS.red}40` },
          ]}>
            <Ionicons
              name={syncResult.success ? 'checkmark-circle-outline' : 'alert-circle-outline'}
              size={16}
              color={syncResult.success ? COLORS.green : COLORS.red}
            />
            <Text style={[s.bannerTxt, { color: syncResult.success ? COLORS.green : COLORS.red, flex: 1 }]}>
              {syncResult.message}
              {syncResult.success && syncResult.data?.synced_records != null &&
                ` · ${syncResult.data.synced_records} new leads`}
            </Text>
            <TouchableOpacity onPress={() => setSyncResult(null)}>
              <Ionicons name="close" size={16} color={syncResult.success ? COLORS.green : COLORS.red} />
            </TouchableOpacity>
          </View>
        )}

        {/* ── Built-in Integrations ──────────────────────────────────────── */}
        <View style={s.sectionHeader}>
          <Ionicons name="star-outline" size={15} color={COLORS.primary} />
          <Text style={s.sectionTitle}>Built-in Integrations</Text>
          <View style={[s.sectionBadge, { backgroundColor: `${COLORS.primary}15` }]}>
            <Text style={[s.sectionBadgeTxt, { color: COLORS.primary }]}>{systemSources.length}</Text>
          </View>
        </View>

        {systemSources.length === 0 ? (
          <View style={s.emptySection}>
            <Ionicons name="star-outline" size={32} color={theme.textMuted} />
            <Text style={s.emptyTxt}>Built-in integrations loading…</Text>
          </View>
        ) : (
          <View style={s.sourceList}>
            {systemSources.map((src) => <SourceCard key={src.id} src={src} />)}
          </View>
        )}

        {/* ── Custom Sources ─────────────────────────────────────────────── */}
        <View style={[s.sectionHeader, { marginTop: 8 }]}>
          <Ionicons name="server-outline" size={15} color={COLORS.cyan} />
          <Text style={s.sectionTitle}>Custom Sources</Text>
          <View style={[s.sectionBadge, { backgroundColor: `${COLORS.cyan}15` }]}>
            <Text style={[s.sectionBadgeTxt, { color: COLORS.cyan }]}>{userSources.length}</Text>
          </View>
        </View>

        {userSources.length === 0 ? (
          <View style={s.emptySection}>
            <Ionicons name="server-outline" size={32} color={theme.textMuted} />
            <Text style={s.emptyTxt}>No custom sources yet</Text>
            <Text style={s.emptyHint}>Add an API endpoint, CSV file, or external database</Text>
            <TouchableOpacity style={s.emptyBtn} onPress={() => { setForm(emptyForm()); setShowAdd(true); }}>
              <Ionicons name="add" size={14} color="#fff" />
              <Text style={s.emptyBtnTxt}>Add Source</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={s.sourceList}>
            {userSources.map((src) => <SourceCard key={src.id} src={src} />)}
          </View>
        )}
      </ScrollView>

      {/* FAB */}
      <TouchableOpacity style={s.fab} onPress={() => { setForm(emptyForm()); setShowAdd(true); }} activeOpacity={0.85}>
        <Ionicons name="add" size={26} color="#fff" />
      </TouchableOpacity>

      {/* ── Add Source Modal ──────────────────────────────────────────────── */}
      <Modal visible={showAdd} transparent animationType="slide" onRequestClose={() => setShowAdd(false)}>
        <View style={s.overlay}>
          <View style={[s.sheet, { backgroundColor: theme.card }]}>
            <View style={s.modalHeader}>
              <Text style={[s.modalTitle, { color: theme.text }]}>Add Custom Source</Text>
              <TouchableOpacity onPress={() => setShowAdd(false)}>
                <Ionicons name="close" size={22} color={theme.textSecondary} />
              </TouchableOpacity>
            </View>
            <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
              <FieldInput label="Source Name *" value={form.name} onChange={(v) => setF('name', v)} placeholder="My API Source" theme={theme} />
              <FieldInput label="Description"   value={form.description} onChange={(v) => setF('description', v)} placeholder="Optional description" theme={theme} />

              <Text style={[s.fieldLabel, { color: theme.textSecondary }]}>Type</Text>
              <View style={s.chipRow}>
                {TYPES.map((t) => {
                  const meta = TYPE_META[t];
                  return (
                    <TouchableOpacity
                      key={t}
                      style={[s.chip, form.type === t && { backgroundColor: meta.color, borderColor: meta.color }]}
                      onPress={() => setF('type', t)}
                    >
                      <Ionicons name={meta.icon} size={12} color={form.type === t ? '#fff' : theme.textMuted} />
                      <Text style={[s.chipTxt, form.type === t && { color: '#fff' }]}>{t}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <Text style={[s.fieldLabel, { color: theme.textSecondary }]}>Sync Frequency</Text>
              <View style={s.chipRow}>
                {FREQ_OPTS.map((f) => (
                  <TouchableOpacity
                    key={f}
                    style={[s.chip, form.sync_frequency === f && { backgroundColor: COLORS.primary, borderColor: COLORS.primary }]}
                    onPress={() => setF('sync_frequency', f)}
                  >
                    <Text style={[s.chipTxt, form.sync_frequency === f && { color: '#fff' }]}>{f}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {form.type === 'API' && (
                <>
                  <FieldInput label="API URL"  value={form.api_url}  onChange={(v) => setF('api_url', v)}  placeholder="https://api.example.com/leads" theme={theme} />
                  <FieldInput label="API Key"  value={form.api_key}  onChange={(v) => setF('api_key', v)}  placeholder="sk-..." theme={theme} secure />
                </>
              )}
              {form.type === 'Database' && (
                <FieldInput label="SQL Query" value={form.db_query} onChange={(v) => setF('db_query', v)} placeholder="SELECT name, email FROM contacts" theme={theme} multiline />
              )}
              {form.type === 'Web' && (
                <View style={[s.infoBanner, { backgroundColor: `${COLORS.primary}12`, borderColor: `${COLORS.primary}25` }]}>
                  <Ionicons name="information-circle-outline" size={15} color={COLORS.primary} />
                  <Text style={[s.infoBannerTxt, { color: COLORS.primary }]}>
                    Web sources use the AI Collect engine. Use the Collect button on the Leads page to run a targeted collection.
                  </Text>
                </View>
              )}
              {form.type === 'CSV' && (
                <View style={[s.infoBanner, { backgroundColor: '#8b5cf612', borderColor: '#8b5cf630' }]}>
                  <Ionicons name="cloud-upload-outline" size={15} color="#8b5cf6" />
                  <Text style={[s.infoBannerTxt, { color: '#8b5cf6' }]}>
                    Create the source first, then use the web app to upload your CSV file.
                  </Text>
                </View>
              )}

              <TouchableOpacity style={[s.saveBtn, saving && { opacity: 0.6 }]} onPress={handleCreate} disabled={saving}>
                {saving
                  ? <ActivityIndicator color="#fff" />
                  : <><Ionicons name="add-circle-outline" size={18} color="#fff" /><Text style={s.saveBtnTxt}>Create Source</Text></>
                }
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* ── Edit Modal (custom sources) ───────────────────────────────────── */}
      <Modal visible={!!editSrc} transparent animationType="slide" onRequestClose={() => setEditSrc(null)}>
        {editSrc && (
          <View style={s.overlay}>
            <View style={[s.sheet, { backgroundColor: theme.card }]}>
              <View style={s.modalHeader}>
                <Text style={[s.modalTitle, { color: theme.text }]}>Edit — {editSrc.name}</Text>
                <TouchableOpacity onPress={() => setEditSrc(null)}>
                  <Ionicons name="close" size={22} color={theme.textSecondary} />
                </TouchableOpacity>
              </View>
              <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                <FieldInput label="Name"        value={editSrc.name}           onChange={(v) => setEditSrc((p) => ({ ...p, name: v }))}        theme={theme} />
                <FieldInput label="Description" value={editSrc.description||''} onChange={(v) => setEditSrc((p) => ({ ...p, description: v }))} theme={theme} />

                <Text style={[s.fieldLabel, { color: theme.textSecondary }]}>Sync Frequency</Text>
                <View style={s.chipRow}>
                  {FREQ_OPTS.map((f) => (
                    <TouchableOpacity
                      key={f}
                      style={[s.chip, editSrc.sync_frequency === f && { backgroundColor: COLORS.primary, borderColor: COLORS.primary }]}
                      onPress={() => setEditSrc((p) => ({ ...p, sync_frequency: f }))}
                    >
                      <Text style={[s.chipTxt, editSrc.sync_frequency === f && { color: '#fff' }]}>{f}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <TouchableOpacity
                  style={[s.saveBtn, { backgroundColor: '#f59e0b' }, saving && { opacity: 0.6 }]}
                  onPress={handleUpdate}
                  disabled={saving}
                >
                  {saving
                    ? <ActivityIndicator color="#fff" />
                    : <><Ionicons name="checkmark-outline" size={18} color="#fff" /><Text style={s.saveBtnTxt}>Save Changes</Text></>
                  }
                </TouchableOpacity>
              </ScrollView>
            </View>
          </View>
        )}
      </Modal>

      {/* ── Configure Modal (system sources) ─────────────────────────────── */}
      <Modal visible={!!cfgSrc} transparent animationType="slide" onRequestClose={() => setCfgSrc(null)}>
        {cfgSrc && (
          <View style={s.overlay}>
            <View style={[s.sheet, { backgroundColor: theme.card }]}>
              <View style={s.modalHeader}>
                <Text style={[s.modalTitle, { color: theme.text }]}>Configure — {cfgSrc.name}</Text>
                <TouchableOpacity onPress={() => setCfgSrc(null)}>
                  <Ionicons name="close" size={22} color={theme.textSecondary} />
                </TouchableOpacity>
              </View>
              <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                {cfgSrc.status === 'inactive' && (
                  <View style={[s.infoBanner, { backgroundColor: '#f59e0b12', borderColor: '#f59e0b30', marginBottom: 4 }]}>
                    <Ionicons name="lock-closed-outline" size={15} color="#f59e0b" />
                    <Text style={[s.infoBannerTxt, { color: '#f59e0b' }]}>
                      API key not configured — contact your administrator to activate this source.
                    </Text>
                  </View>
                )}

                {isWebSrc ? (
                  <View style={[s.infoBanner, { backgroundColor: `${COLORS.primary}12`, borderColor: `${COLORS.primary}25` }]}>
                    <Ionicons name="information-circle-outline" size={15} color={COLORS.primary} />
                    <Text style={[s.infoBannerTxt, { color: COLORS.primary }]}>
                      Use the Collect button on the Leads page. Search parameters (keywords, location) are set per-search.
                    </Text>
                  </View>
                ) : (
                  <>
                    <FieldInput
                      label="Max leads per sync"
                      value={cfgForm.max_leads}
                      onChange={(v) => setCfgForm((p) => ({ ...p, max_leads: v }))}
                      placeholder="40"
                      theme={theme}
                    />
                    {!isEnrich && (
                      <>
                        <FieldInput
                          label="Keywords"
                          value={cfgForm.keywords}
                          onChange={(v) => setCfgForm((p) => ({ ...p, keywords: v }))}
                          placeholder="SaaS startup founder"
                          theme={theme}
                        />
                        <FieldInput
                          label="Locations (comma-separated)"
                          value={cfgForm.locations}
                          onChange={(v) => setCfgForm((p) => ({ ...p, locations: v }))}
                          placeholder="New York, London, Berlin"
                          theme={theme}
                        />
                      </>
                    )}
                    {isApollo && (
                      <>
                        <FieldInput
                          label="Job Titles (comma-separated)"
                          value={cfgForm.titles}
                          onChange={(v) => setCfgForm((p) => ({ ...p, titles: v }))}
                          placeholder="CEO, Founder, CTO"
                          theme={theme}
                        />
                        <FieldInput
                          label="Industries (comma-separated)"
                          value={cfgForm.industries}
                          onChange={(v) => setCfgForm((p) => ({ ...p, industries: v }))}
                          placeholder="SaaS, FinTech, Healthcare"
                          theme={theme}
                        />
                      </>
                    )}
                    <TouchableOpacity
                      style={[s.saveBtn, saving && { opacity: 0.6 }]}
                      onPress={handleConfigure}
                      disabled={saving}
                    >
                      {saving
                        ? <ActivityIndicator color="#fff" />
                        : <><Ionicons name="checkmark-outline" size={18} color="#fff" /><Text style={s.saveBtnTxt}>Save Parameters</Text></>
                      }
                    </TouchableOpacity>
                  </>
                )}
              </ScrollView>
            </View>
          </View>
        )}
      </Modal>
    </View>
  );
}

function FieldInput({ label, value, onChange, placeholder, theme, secure, multiline }) {
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={{ fontSize: 12, fontWeight: '600', color: theme.textSecondary, marginBottom: 5 }}>{label}</Text>
      <TextInput
        style={{
          backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder,
          borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10,
          color: theme.text, fontSize: 14,
          minHeight: multiline ? 72 : 44,
          textAlignVertical: multiline ? 'top' : 'center',
        }}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={theme.textMuted}
        secureTextEntry={!!secure}
        autoCapitalize="none"
        multiline={!!multiline}
      />
    </View>
  );
}

const styles = (theme) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  kpiGrid:    { flexDirection: 'row', flexWrap: 'wrap', padding: 12, gap: 10 },
  kpiCard:    {
    width: '47.5%', backgroundColor: theme.card,
    borderRadius: 12, padding: 14,
    borderWidth: 1, borderColor: theme.cardBorder, borderLeftWidth: 3,
  },
  kpiTop:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 },
  kpiTitle:   { fontSize: 10, fontWeight: '600', color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 3 },
  kpiVal:     { fontSize: 20, fontWeight: '800', lineHeight: 24 },
  kpiSub:     { fontSize: 10, color: theme.textMuted },
  kpiBar:     { height: 5, backgroundColor: theme.input, borderRadius: 3, overflow: 'hidden' },
  kpiBarFill: { height: '100%', borderRadius: 3 },

  banner:    {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    marginHorizontal: 12, marginBottom: 10,
    padding: 12, borderRadius: 10, borderWidth: 1,
  },
  bannerTxt: { fontSize: 12, fontWeight: '500', lineHeight: 16 },

  sectionHeader:   { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingTop: 10, paddingBottom: 6 },
  sectionTitle:    { fontSize: 14, fontWeight: '700', color: theme.text, flex: 1 },
  sectionBadge:    { borderRadius: 20, paddingHorizontal: 8, paddingVertical: 2 },
  sectionBadgeTxt: { fontSize: 11, fontWeight: '700' },

  sourceList: { paddingHorizontal: 12, gap: 10 },

  sourceCard: {
    backgroundColor: theme.card, borderRadius: 16,
    padding: 14, borderWidth: 1, borderColor: theme.cardBorder, elevation: 2,
  },
  srcHeader:   { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
  srcIconWrap: { width: 38, height: 38, borderRadius: 11, alignItems: 'center', justifyContent: 'center', position: 'relative' },
  starBadge:   {
    position: 'absolute', top: -3, right: -3,
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: '#6366f118', alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: '#6366f135',
  },
  srcInfo:    { flex: 1 },
  srcName:    { fontSize: 14, fontWeight: '700', color: theme.text },
  srcType:    { fontSize: 11, color: theme.textMuted, marginTop: 2 },

  srcMeta:    { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  srcRecords: { fontSize: 11, color: theme.textMuted, flex: 1 },
  srcSync:    { fontSize: 11, color: theme.textMuted },

  errorRow:   { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginBottom: 8 },
  errorTxt:   { flex: 1, fontSize: 11, color: COLORS.red, lineHeight: 15 },

  perfRow:    { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  perfLbl:    { fontSize: 11, color: theme.textMuted, width: 30 },
  perfBg:     { flex: 1, height: 5, backgroundColor: theme.input, borderRadius: 3, overflow: 'hidden' },
  perfFill:   { height: '100%', borderRadius: 3 },
  perfPct:    { fontSize: 11, color: theme.textMuted, width: 30, textAlign: 'right' },

  srcActions: { flexDirection: 'row', gap: 8 },
  actionBtn:  { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 8, borderRadius: 10, borderWidth: 1 },
  actionTxt:  { fontSize: 12, fontWeight: '600' },

  emptySection: { alignItems: 'center', paddingVertical: 32, gap: 6 },
  emptyTxt:     { fontSize: 14, fontWeight: '700', color: theme.text, marginTop: 4 },
  emptyHint:    { fontSize: 12, color: theme.textMuted, textAlign: 'center', paddingHorizontal: 24 },
  emptyBtn:     { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, borderRadius: 20, paddingHorizontal: 16, paddingVertical: 8, marginTop: 6 },
  emptyBtnTxt:  { color: '#fff', fontSize: 13, fontWeight: '600' },

  fab: {
    position: 'absolute', bottom: 24, right: 20,
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: COLORS.primary,
    alignItems: 'center', justifyContent: 'center',
    elevation: 8, shadowColor: COLORS.primary, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.4, shadowRadius: 8,
  },

  overlay:     { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'flex-end' },
  sheet:       { borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 20, paddingBottom: 40, maxHeight: '90%' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  modalTitle:  { fontSize: 17, fontWeight: '700', flex: 1, marginRight: 10 },

  fieldLabel: { fontSize: 12, fontWeight: '600', marginBottom: 6, marginTop: 4 },
  chipRow:    { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 12, paddingVertical: 7,
    borderRadius: 20, backgroundColor: theme.input,
    borderWidth: 1, borderColor: theme.inputBorder,
  },
  chipTxt: { fontSize: 12, fontWeight: '600', color: theme.textMuted },

  infoBanner:    { flexDirection: 'row', gap: 8, alignItems: 'flex-start', padding: 12, borderRadius: 10, borderWidth: 1, marginBottom: 12 },
  infoBannerTxt: { flex: 1, fontSize: 12, lineHeight: 17 },

  saveBtn:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary, borderRadius: 14, height: 50, marginTop: 4 },
  saveBtnTxt: { color: '#fff', fontSize: 15, fontWeight: '700' },
});
