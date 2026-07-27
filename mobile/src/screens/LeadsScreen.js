import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  View, Text, FlatList, TextInput, TouchableOpacity, StyleSheet,
  RefreshControl, ActivityIndicator, Modal, ScrollView,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { leadsAPI, collectAPI } from '../services/api';
import { triggerWebToMobile, syncSingleLead } from '../services/syncService';
import { useRealtimePatch } from '../hooks/useRealtime';
import LeadCard from '../components/LeadCard';
import { showError, showSuccess, showWarning, showConfirm } from '../utils/dialog';

// ── Fuzzy search helpers ──────────────────────────────────────────────────────
function levenshtein(a, b) {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = i;
    for (let j = 1; j <= b.length; j++) {
      const tmp = row[j - 1];
      row[j - 1] = prev;
      prev = a[i - 1] === b[j - 1] ? tmp : 1 + Math.min(tmp, prev, row[j]);
    }
    row[b.length] = prev;
  }
  return row[b.length];
}

function strSim(a, b) {
  const ml = Math.max(a.length, b.length);
  return ml === 0 ? 1 : 1 - levenshtein(a, b) / ml;
}

function scoreLead(lead, rawQuery) {
  const q = rawQuery.toLowerCase().trim();
  if (q.length < 2) return 0;
  const fields = [lead.name, lead.email, lead.company].map(f => (f || '').toLowerCase());
  let best = 0;
  const qWords = q.split(/\s+/).filter(w => w.length >= 2);
  for (const f of fields) {
    if (!f) continue;
    if (f === q) return 100;
    if (f.includes(q)) { best = Math.max(best, 85); continue; }
    if (qWords.every(w => f.includes(w))) { best = Math.max(best, 78); continue; }
    const clip = f.slice(0, Math.min(f.length, q.length + 5));
    const s1 = strSim(q, clip);
    if (s1 > 0.55) best = Math.max(best, Math.round(s1 * 76));
    const fWords = f.split(/[\s,@._\-+]+/).filter(w => w.length >= 2);
    for (const qw of qWords) {
      for (const fw of fWords) {
        const s = strSim(qw, fw);
        if (s > 0.62) best = Math.max(best, Math.round(s * 72));
      }
    }
    for (const fw of fWords) {
      if (fw.length < 2) continue;
      const s = strSim(q, fw);
      if (s > 0.62) best = Math.max(best, Math.round(s * 70));
    }
  }
  return best;
}

const STATUSES      = ['', 'hot', 'warm', 'cold', 'pending', 'qualified', 'contacted', 'converted'];
const INDUSTRIES    = ['', 'Technology', 'Healthcare', 'Finance', 'Education', 'Retail', 'Manufacturing', 'Real Estate', 'Marketing', 'Consulting', 'Other'];
const INTERESTS     = ['', 'AI', 'Machine Learning', 'Cloud', 'Automation', 'SaaS', 'B2B', 'Fintech', 'Digital Marketing', 'IoT'];
const SOURCES       = ['', 'manual', 'web', 'linkedin', 'apollo', 'hunter', 'csv', 'api'];
const QUALITY_TIERS = ['', 'high', 'medium', 'low'];
const COUNTRIES     = ['', 'United States', 'United Kingdom', 'Germany', 'France', 'UAE', 'Saudi Arabia', 'India', 'Canada', 'Australia', 'Japan', 'Brazil', 'Singapore', 'South Africa', 'Nigeria', 'Egypt', 'Indonesia', 'Turkey', 'Mexico', 'Netherlands', 'Sweden'];

const FILTER_TABS   = [
  { key: 'status',   label: 'Status'   },
  { key: 'industry', label: 'Industry' },
  { key: 'source',   label: 'Source'   },
  { key: 'interest', label: 'Interest' },
  { key: 'country',  label: 'Country'  },
  { key: 'quality',  label: 'Quality'  },
];

const PER_PAGE = 20;

export default function LeadsScreen({ navigation }) {
  const { theme } = useTheme();

  const [leads, setLeads]             = useState([]);
  const [total, setTotal]             = useState(0);
  const [page, setPage]               = useState(1);
  const [loading, setLoading]         = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing]   = useState(false);
  const [search, setSearch]           = useState('');

  // Filters
  const [filterStatus,   setFilterStatus]   = useState('');
  const [filterIndustry, setFilterIndustry] = useState('');
  const [filterSource,   setFilterSource]   = useState('');
  const [filterInterest, setFilterInterest] = useState('');
  const [filterCountry,  setFilterCountry]  = useState('');
  const [filterQuality,  setFilterQuality]  = useState('');
  const [showFilter, setShowFilter]         = useState(false);
  const [filterTab, setFilterTab]           = useState('status');

  // Add modal
  const [showAddModal, setAddModal] = useState(false);
  const [creating, setCreating]     = useState(false);

  // Batch select mode
  const [selectMode, setSelectMode]   = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [batchOp, setBatchOp]         = useState(null); // 'qualify' | 'enrich' | null

  const emptyLead = () => ({
    name: '', email: '', phone: '', company: '', position: '',
    industry: '', country: '', location: '', website: '', linkedin_url: '',
    source: 'manual', interest_level: '', notes: '',
  });
  const [newLead, setNewLead] = useState(emptyLead());
  const searchTimer         = useRef(null);
  const leadsIndexRef       = useRef([]);
  const leadsIndexLoadedRef = useRef(false);
  const [fuzzyResults, setFuzzyResults] = useState(null); // null = normal mode

  // Stable no-op — avoids re-subscribing Supabase channel on every keystroke
  // when the user is searching (search results come from the API, not realtime).
  const _noop = useCallback(() => {}, []);
  const { isConnected: realtimeConnected } = useRealtimePatch(
    search.trim() ? _noop : setLeads
  );

  const hasFilters = !!(filterStatus || filterIndustry || filterSource || filterInterest || filterCountry || filterQuality);

  const fetchLeads = useCallback(async (pg = 1, reset = false, silent = false) => {
    try {
      if (!silent) pg === 1 ? setLoading(true) : setLoadingMore(true);

      if (search.trim()) {
        const resp = await leadsAPI.searchLeads(search.trim(), PER_PAGE);
        const found = resp.data.leads || [];
        setLeads(found);
        setTotal(found.length);
        return;
      }

      const params = { page: pg, per_page: PER_PAGE };
      if (filterStatus)   params.status        = filterStatus;
      if (filterIndustry) params.industry      = filterIndustry;
      if (filterSource)   params.source        = filterSource;
      if (filterInterest) params.interest      = filterInterest;
      if (filterCountry)  params.country       = filterCountry;
      if (filterQuality)  params.quality_tier  = filterQuality;

      const resp    = await leadsAPI.getLeads(params);
      const fetched = resp.data.leads || [];
      setTotal(resp.data.total || 0);
      setLeads(reset || pg === 1 ? fetched : (prev) => [...prev, ...fetched]);
      setPage(pg);
    } catch {
      if (!silent) showError('Error', 'Failed to load leads');
    } finally {
      setLoading(false);
      setLoadingMore(false);
      setRefreshing(false);
    }
  }, [search, filterStatus, filterIndustry, filterSource, filterInterest, filterCountry, filterQuality]);

  useEffect(() => { fetchLeads(1, true); }, [filterStatus, filterIndustry, filterSource, filterInterest, filterCountry, filterQuality]);

  // Silently refetch page 1 whenever this tab regains focus — e.g. after a
  // collection run finishes on the AI Engine tab (the tab stays mounted, so
  // it wouldn't otherwise know new leads landed).
  useFocusEffect(
    useCallback(() => {
      fetchLeads(1, true, true);
    }, [fetchLeads])
  );

  // Load full lead objects into local index once on mount for fuzzy matching
  useEffect(() => {
    if (leadsIndexLoadedRef.current) return;
    leadsAPI.getLeads({ per_page: 300, page: 1 })
      .then(resp => { leadsIndexRef.current = resp.data.leads || []; })
      .catch(() => {})
      .finally(() => { leadsIndexLoadedRef.current = true; });
  }, []);

  // Fuzzy search: client-side Levenshtein scoring when index ready, backend fallback otherwise
  useEffect(() => {
    const q = search.trim();

    if (q.length < 2) {
      setFuzzyResults(null);
      clearTimeout(searchTimer.current);
      searchTimer.current = setTimeout(() => fetchLeads(1, true), 300);
      return () => clearTimeout(searchTimer.current);
    }

    if (leadsIndexLoadedRef.current && leadsIndexRef.current.length > 0) {
      const timer = setTimeout(() => {
        const hits = leadsIndexRef.current
          .map(l => ({ l, s: scoreLead(l, q) }))
          .filter(x => x.s >= 30)
          .sort((a, b) => b.s - a.s || (b.l.qualification_score || 0) - (a.l.qualification_score || 0))
          .slice(0, 20)
          .map(x => x.l);
        setFuzzyResults(hits);
      }, 90);
      return () => clearTimeout(timer);
    }

    // Index not ready yet — fall back to backend search
    setFuzzyResults(null);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => fetchLeads(1, true), 400);
    return () => clearTimeout(searchTimer.current);
  }, [search, fetchLeads]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchLeads(1, true);
    triggerWebToMobile({ silent: true }).catch(() => {});
  };

  const handleLoadMore = () => {
    if (loadingMore || leads.length >= total || search.trim() || fuzzyResults !== null) return;
    fetchLeads(page + 1);
  };

  const handleDelete = (leadId) => {
    showConfirm('Delete Lead', 'Are you sure? This cannot be undone.',
      async () => {
        try {
          await leadsAPI.deleteLead(leadId);
          setLeads((prev) => prev.filter((l) => l.id !== leadId));
          leadsIndexRef.current = leadsIndexRef.current.filter((l) => l.id !== leadId);
          setTotal((t) => t - 1);
        } catch {
          showError('Error', 'Failed to delete lead');
        }
      },
      undefined, 'Delete', 'Cancel', 'danger',
    );
  };

  const handleCreate = async () => {
    if (!newLead.name.trim()) { showWarning('Required', 'Name is required'); return; }
    try {
      setCreating(true);
      const resp    = await leadsAPI.createLead(newLead);
      const created = resp.data.lead;
      setLeads((prev) => [created, ...prev]);
      leadsIndexRef.current = [created, ...leadsIndexRef.current];
      setTotal((t) => t + 1);
      setAddModal(false);
      setNewLead(emptyLead());
      syncSingleLead(created.id).catch((err) =>
        console.warn('[LeadsScreen] syncSingleLead failed:', err?.message)
      );
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to create lead');
    } finally {
      setCreating(false);
    }
  };

  // ── Batch select helpers ───────────────────────────────────────────────────
  const enterSelectMode = (leadId) => {
    setSelectMode(true);
    setSelectedIds(new Set([leadId]));
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
  };

  const toggleSelected = (leadId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(leadId) ? next.delete(leadId) : next.add(leadId);
      return next;
    });
  };

  const selectAll = () => setSelectedIds(new Set(leads.map((l) => l.id)));

  const handleBatchQualify = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;
    setBatchOp('qualify');
    try {
      const resp = await leadsAPI.batchQualify(ids);
      const s    = resp.data?.stats || {};
      triggerWebToMobile({ silent: true }).catch(() => {});
      fetchLeads(1, true, true);
      exitSelectMode();
      showSuccess(
        'Qualification Complete',
        `Processed: ${s.total ?? ids.length}\n` +
        `Hot: ${s.hot ?? 0}  Warm: ${s.warm ?? 0}  Cold: ${s.cold ?? 0}`,
      );
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Batch qualification failed');
    } finally {
      setBatchOp(null);
    }
  };

  const handleBatchEnrich = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;
    setBatchOp('enrich');
    try {
      const resp    = await leadsAPI.enrichLeads(ids);
      const enriched = resp.data?.enriched ?? ids.length;
      triggerWebToMobile({ silent: true }).catch(() => {});
      fetchLeads(1, true, true);
      exitSelectMode();
      showSuccess('Enrichment Complete', `${enriched} lead${enriched !== 1 ? 's' : ''} enriched`);
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Batch enrichment failed');
    } finally {
      setBatchOp(null);
    }
  };

  const clearFilters = () => {
    setFilterStatus('');
    setFilterIndustry('');
    setFilterSource('');
    setFilterInterest('');
    setFilterCountry('');
    setFilterQuality('');
  };

  const s = useMemo(() => styles(theme), [theme]);

  // Stable ID-based handlers so renderItem deps don't change on every keystroke/filter
  const handleNavigate = useCallback((leadId) => {
    navigation.navigate('LeadDetail', { leadId });
  }, [navigation]);

  const renderItem = useCallback(({ item }) => {
    const isSelected = selectedIds.has(item.id);
    return (
      <TouchableOpacity
        activeOpacity={selectMode ? 0.7 : 1}
        onPress={selectMode ? () => toggleSelected(item.id) : undefined}
        onLongPress={!selectMode ? () => enterSelectMode(item.id) : undefined}
        style={{ position: 'relative' }}
      >
        <LeadCard
          lead={item}
          onPress={selectMode ? () => toggleSelected(item.id) : () => handleNavigate(item.id)}
          onDelete={selectMode ? undefined : () => handleDelete(item.id)}
        />
        {selectMode && (
          <View style={[s.selectOverlay, isSelected && s.selectOverlayActive]}>
            <View style={[s.checkbox, isSelected && s.checkboxActive]}>
              {isSelected && <Ionicons name="checkmark" size={13} color="#fff" />}
            </View>
          </View>
        )}
      </TouchableOpacity>
    );
  }, [selectedIds, selectMode, toggleSelected, enterSelectMode, handleNavigate, handleDelete, s]);

  const renderFooter = useCallback(() =>
    loadingMore ? <ActivityIndicator color={COLORS.primary} style={{ padding: 16 }} /> : null,
  [loadingMore]);

  const listExtraData = useMemo(() => ({ selectMode, selectedIds }), [selectMode, selectedIds]);

  const activeChips = [
    { val: filterStatus,   clear: () => setFilterStatus(''),   label: filterStatus   },
    { val: filterIndustry, clear: () => setFilterIndustry(''), label: filterIndustry },
    { val: filterSource,   clear: () => setFilterSource(''),   label: filterSource   },
    { val: filterInterest, clear: () => setFilterInterest(''), label: filterInterest },
    { val: filterCountry,  clear: () => setFilterCountry(''),  label: filterCountry  },
    { val: filterQuality,  clear: () => setFilterQuality(''),  label: `quality: ${filterQuality}` },
  ].filter((f) => f.val);

  const filterValues = {
    status:   filterStatus,
    industry: filterIndustry,
    source:   filterSource,
    interest: filterInterest,
    country:  filterCountry,
    quality:  filterQuality,
  };
  const filterSetters = {
    status:   setFilterStatus,
    industry: setFilterIndustry,
    source:   setFilterSource,
    interest: setFilterInterest,
    country:  setFilterCountry,
    quality:  setFilterQuality,
  };
  const filterOptions = {
    status:   STATUSES,
    industry: INDUSTRIES,
    source:   SOURCES,
    interest: INTERESTS,
    country:  COUNTRIES,
    quality:  QUALITY_TIERS,
  };
  const filterColors = {
    status:   COLORS.primary,
    industry: COLORS.cyan,
    source:   COLORS.green,
    interest: COLORS.amber,
    country:  COLORS.purple,
    quality:  COLORS.red,
  };
  const filterLabels = {
    status:   (v) => v ? v.charAt(0).toUpperCase() + v.slice(1) : 'All Statuses',
    industry: (v) => v || 'All Industries',
    source:   (v) => v || 'All Sources',
    interest: (v) => v || 'All Interests',
    country:  (v) => v || 'All Countries',
    quality:  (v) => v ? `${v.charAt(0).toUpperCase() + v.slice(1)} Quality` : 'All Quality Tiers',
  };

  return (
    <View style={s.root}>
      {/* Select mode header */}
      {selectMode ? (
        <View style={s.selectHeader}>
          <TouchableOpacity onPress={exitSelectMode} style={s.selectHeaderBtn}>
            <Ionicons name="close" size={20} color={theme.textSecondary} />
          </TouchableOpacity>
          <Text style={s.selectHeaderTitle}>
            {selectedIds.size} selected
          </Text>
          <TouchableOpacity onPress={selectAll} style={s.selectHeaderBtn}>
            <Text style={{ fontSize: 13, color: COLORS.primary, fontWeight: '700' }}>Page</Text>
          </TouchableOpacity>
        </View>
      ) : (
        /* Search + Filter Bar */
        <View style={s.searchRow}>
          <View style={s.searchBox}>
            <Ionicons name="search-outline" size={16} color={theme.textMuted} />
            <TextInput
              style={s.searchInput}
              value={search}
              onChangeText={setSearch}
              placeholder="Search leads..."
              placeholderTextColor={theme.textMuted}
            />
            {search.length > 0 && (
              <TouchableOpacity onPress={() => setSearch('')}>
                <Ionicons name="close-circle" size={16} color={theme.textMuted} />
              </TouchableOpacity>
            )}
          </View>
          <TouchableOpacity
            style={[s.iconBtn, hasFilters && { backgroundColor: COLORS.primary }]}
            onPress={() => setShowFilter(true)}
          >
            <Ionicons name="filter" size={18} color={hasFilters ? '#fff' : theme.textSecondary} />
          </TouchableOpacity>
          <TouchableOpacity style={[s.iconBtn, { backgroundColor: COLORS.primary }]} onPress={() => setAddModal(true)}>
            <Ionicons name="add" size={20} color="#fff" />
          </TouchableOpacity>
        </View>
      )}

      {/* Active filter chips */}
      {!selectMode && activeChips.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.activeFilters}>
          {activeChips.map((f) => (
            <TouchableOpacity key={f.label} style={s.activeChip} onPress={f.clear}>
              <Text style={s.activeChipTxt}>{f.label}</Text>
              <Ionicons name="close" size={11} color={COLORS.primary} />
            </TouchableOpacity>
          ))}
          <TouchableOpacity onPress={clearFilters}>
            <Text style={s.clearAll}>Clear all</Text>
          </TouchableOpacity>
        </ScrollView>
      )}

      {/* Fuzzy search indicator */}
      {fuzzyResults !== null && search.trim().length >= 2 && (
        <View style={{ paddingHorizontal: 14, paddingBottom: 4, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Ionicons name="flash-outline" size={12} color={COLORS.primary} />
          <Text style={{ fontSize: 11, color: COLORS.primary, fontWeight: '600' }}>
            {fuzzyResults.length} smart {fuzzyResults.length === 1 ? 'match' : 'matches'} for "{search.trim()}"
          </Text>
        </View>
      )}

      {/* List */}
      {loading ? (
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : (
        <FlatList
          data={fuzzyResults !== null ? fuzzyResults : leads}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          extraData={listExtraData}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={COLORS.primary} />}
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.3}
          ListFooterComponent={renderFooter}
          ListEmptyComponent={
            <View style={s.center}>
              <Ionicons name="people-outline" size={48} color={theme.textMuted} />
              <Text style={s.emptyText}>No leads found</Text>
            </View>
          }
          contentContainerStyle={{ padding: 12, paddingBottom: 100, flexGrow: 1 }}
          removeClippedSubviews={true}
          maxToRenderPerBatch={8}
          updateCellsBatchingPeriod={30}
          windowSize={7}
          initialNumToRender={10}
        />
      )}

      {/* Batch action bar */}
      {selectMode && (
        <View style={[s.batchBar, { backgroundColor: theme.card, borderTopColor: theme.cardBorder }]}>
          <TouchableOpacity
            style={[s.batchBtn, { backgroundColor: COLORS.primary }, (!selectedIds.size || batchOp) && s.batchBtnDisabled]}
            onPress={handleBatchQualify}
            disabled={!selectedIds.size || !!batchOp}
          >
            {batchOp === 'qualify' ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <><Ionicons name="flash" size={16} color="#fff" /><Text style={s.batchBtnText}>Qualify ({selectedIds.size})</Text></>
            )}
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.batchBtn, { backgroundColor: COLORS.cyan }, (!selectedIds.size || batchOp) && s.batchBtnDisabled]}
            onPress={handleBatchEnrich}
            disabled={!selectedIds.size || !!batchOp}
          >
            {batchOp === 'enrich' ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <><Ionicons name="sparkles" size={16} color="#fff" /><Text style={s.batchBtnText}>Enrich ({selectedIds.size})</Text></>
            )}
          </TouchableOpacity>
        </View>
      )}

      {/* ── Filter Modal ──────────────────────────────────────────────────── */}
      <Modal visible={showFilter} transparent animationType="slide" onRequestClose={() => setShowFilter(false)}>
        <TouchableOpacity style={s.modalOverlay} activeOpacity={1} onPress={() => setShowFilter(false)}>
          <View style={[s.filterSheet, { backgroundColor: theme.surface || theme.card }]}>
            <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: theme.textMuted, alignSelf: 'center', marginBottom: 16, opacity: 0.4 }} />
            <Text style={[s.filterTitle, { color: theme.text }]}>Filters</Text>

            {/* Filter category tabs — scrollable */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }} contentContainerStyle={{ gap: 4, paddingHorizontal: 2 }}>
              {FILTER_TABS.map(({ key, label }) => (
                <TouchableOpacity
                  key={key}
                  style={[s.filterTab, filterTab === key && s.filterTabActive]}
                  onPress={() => setFilterTab(key)}
                >
                  <Text style={[s.filterTabTxt, filterTab === key && { color: filterColors[key] ?? COLORS.primary }]}>{label}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            <ScrollView style={{ maxHeight: 280 }}>
              {filterOptions[filterTab]?.map((opt) => {
                const isActive = filterValues[filterTab] === opt;
                const color    = filterColors[filterTab] ?? COLORS.primary;
                const display  = filterLabels[filterTab]?.(opt) ?? opt;
                return (
                  <TouchableOpacity
                    key={opt || 'all'}
                    style={[s.filterOption, isActive && { backgroundColor: `${color}15` }]}
                    onPress={() => {
                      filterSetters[filterTab]?.(opt);
                      setShowFilter(false);
                    }}
                  >
                    <Text style={[s.filterOptionText, { color: isActive ? color : theme.text }]}>{display}</Text>
                    {isActive && <Ionicons name="checkmark" size={16} color={color} />}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>
        </TouchableOpacity>
      </Modal>

      {/* ── Add Lead Modal ─────────────────────────────────────────────────── */}
      <Modal visible={showAddModal} transparent animationType="slide" onRequestClose={() => setAddModal(false)}>
        <View style={s.modalOverlay}>
          <View style={[s.addSheet, { backgroundColor: theme.surface || theme.card }]}>
            <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: theme.textMuted, alignSelf: 'center', marginBottom: 16, opacity: 0.4 }} />
            <View style={s.modalHeader}>
              <Text style={[s.filterTitle, { color: theme.text }]}>Add New Lead</Text>
              <TouchableOpacity onPress={() => setAddModal(false)}>
                <Ionicons name="close" size={22} color={theme.textSecondary} />
              </TouchableOpacity>
            </View>
            <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
              {[
                { key: 'name',         label: 'Name *',         placeholder: 'John Doe',             type: 'default'       },
                { key: 'email',        label: 'Email',          placeholder: 'john@acme.com',        type: 'email-address' },
                { key: 'phone',        label: 'Phone',          placeholder: '+1 555 0100',          type: 'phone-pad'     },
                { key: 'company',      label: 'Company',        placeholder: 'Acme Corp',            type: 'default'       },
                { key: 'position',     label: 'Job Title',      placeholder: 'Sales Manager',        type: 'default'       },
                { key: 'industry',     label: 'Industry',       placeholder: 'Technology',           type: 'default'       },
                { key: 'country',      label: 'Country',        placeholder: 'United States',        type: 'default'       },
                { key: 'location',     label: 'City / Location',placeholder: 'New York, NY',         type: 'default'       },
                { key: 'website',      label: 'Website',        placeholder: 'https://acme.com',     type: 'url'           },
                { key: 'linkedin_url', label: 'LinkedIn URL',   placeholder: 'linkedin.com/in/john', type: 'url'           },
              ].map(({ key, label, placeholder, type }) => (
                <View key={key} style={{ marginBottom: 10 }}>
                  <Text style={[s.inputLabel, { color: theme.textSecondary }]}>{label}</Text>
                  <TextInput
                    style={[s.modalInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                    value={newLead[key]}
                    onChangeText={(v) => setNewLead((prev) => ({ ...prev, [key]: v }))}
                    placeholder={placeholder}
                    placeholderTextColor={theme.textMuted}
                    keyboardType={type}
                    autoCapitalize={type === 'email-address' || type === 'url' ? 'none' : 'words'}
                  />
                </View>
              ))}

              <Text style={[s.inputLabel, { color: theme.textSecondary }]}>Interest Level</Text>
              <View style={s.chipRow}>
                {['', 'hot', 'warm', 'cold'].map((lvl) => (
                  <TouchableOpacity
                    key={lvl || 'none'}
                    style={[s.chip, newLead.interest_level === lvl && { backgroundColor: COLORS.primary, borderColor: COLORS.primary }]}
                    onPress={() => setNewLead((p) => ({ ...p, interest_level: lvl }))}
                  >
                    <Text style={[s.chipTxt, newLead.interest_level === lvl && { color: '#fff' }]}>{lvl || 'None'}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={[s.inputLabel, { color: theme.textSecondary }]}>Notes</Text>
              <TextInput
                style={[s.modalInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder, height: 72, textAlignVertical: 'top', paddingTop: 10 }]}
                value={newLead.notes}
                onChangeText={(v) => setNewLead((p) => ({ ...p, notes: v }))}
                placeholder="Additional notes..."
                placeholderTextColor={theme.textMuted}
                multiline
              />

              <TouchableOpacity
                style={[s.createBtn, creating && { opacity: 0.7 }, { marginTop: 16 }]}
                onPress={handleCreate}
                disabled={creating}
              >
                {creating
                  ? <ActivityIndicator color="#fff" />
                  : <><Ionicons name="person-add-outline" size={17} color="#fff" /><Text style={s.createBtnText}>Create Lead</Text></>
                }
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = (theme) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 40, gap: 8 },

  /* Search bar */
  searchRow: { flexDirection: 'row', gap: 8, padding: 12, paddingBottom: 6 },
  searchBox: {
    flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: theme.input, borderRadius: 14, paddingHorizontal: 14,
    borderWidth: 1, borderColor: theme.inputBorder, height: 46,
  },
  searchInput: { flex: 1, color: theme.text, fontSize: 14 },
  iconBtn: {
    width: 46, height: 46, borderRadius: 14,
    backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder,
    alignItems: 'center', justifyContent: 'center',
  },
  countText: { fontSize: 12, color: theme.textMuted, paddingHorizontal: 14, paddingBottom: 6, fontWeight: '500' },
  emptyText: { color: theme.textMuted, marginTop: 10, fontSize: 14, fontWeight: '500' },

  /* Select mode header */
  selectHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: theme.card, borderBottomWidth: 1, borderBottomColor: theme.cardBorder,
  },
  selectHeaderBtn: { padding: 6 },
  selectHeaderTitle: { fontSize: 15, fontWeight: '700', color: theme.text },

  /* Select overlay on each card */
  selectOverlay: {
    position: 'absolute', top: 8, right: 8,
    width: 26, height: 26, borderRadius: 13,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.15)',
  },
  selectOverlayActive: { backgroundColor: COLORS.primary },
  checkbox: {
    width: 22, height: 22, borderRadius: 11,
    borderWidth: 2, borderColor: 'rgba(255,255,255,0.7)',
    alignItems: 'center', justifyContent: 'center',
  },
  checkboxActive: { borderColor: '#fff', backgroundColor: COLORS.primary },

  /* Batch action bar */
  batchBar: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    flexDirection: 'row', gap: 10, padding: 12, paddingBottom: 24,
    borderTopWidth: 1,
    shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 8, shadowOffset: { width: 0, height: -3 }, elevation: 6,
  },
  batchBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, height: 48, borderRadius: 14,
    shadowOpacity: 0.3, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 4,
  },
  batchBtnDisabled: { opacity: 0.4 },
  batchBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },

  /* Modals */
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'flex-end' },
  filterSheet:  { borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, paddingBottom: 40 },
  addSheet:     { borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, paddingBottom: 40, maxHeight: '88%' },
  filterTitle:  { fontSize: 17, fontWeight: '800', marginBottom: 16 },
  modalHeader:  { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  filterOption: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14, borderRadius: 12, marginBottom: 4 },
  filterOptionText: { fontSize: 15, fontWeight: '500' },

  /* Active filter chips */
  activeFilters: { paddingHorizontal: 12, paddingVertical: 6, gap: 8 },
  activeChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: `${COLORS.primary}15`, borderRadius: 20,
    paddingHorizontal: 11, paddingVertical: 5,
    borderWidth: 1, borderColor: `${COLORS.primary}30`,
  },
  activeChipTxt: { fontSize: 11, color: COLORS.primary, fontWeight: '700' },
  clearAll: { fontSize: 11, color: COLORS.red, paddingHorizontal: 8, paddingVertical: 5, fontWeight: '700' },

  /* Filter modal tabs */
  filterTab: {
    paddingHorizontal: 14, paddingVertical: 7, borderRadius: 9,
    backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder,
  },
  filterTabActive: { backgroundColor: theme.card, borderColor: theme.cardBorder },
  filterTabTxt: { fontSize: 11, fontWeight: '600', color: theme.textMuted },

  /* Add lead form */
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  chip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
    backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder,
  },
  chipTxt: { fontSize: 12, fontWeight: '600', color: theme.textMuted },

  inputLabel: { fontSize: 12, fontWeight: '600', marginBottom: 6, color: theme.textSecondary },
  modalInput: {
    height: 46, borderRadius: 12, paddingHorizontal: 14,
    fontSize: 14, borderWidth: 1,
  },
  createBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: COLORS.primary, borderRadius: 14, height: 52,
    shadowColor: COLORS.primary, shadowOpacity: 0.3,
    shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 5,
  },
  createBtnText: { color: '#fff', fontSize: 15, fontWeight: '800' },
});
