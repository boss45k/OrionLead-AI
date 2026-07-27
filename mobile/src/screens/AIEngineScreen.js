import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, ActivityIndicator, FlatList, KeyboardAvoidingView,
  Platform, Keyboard, Animated,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { aiAPI, leadsAPI, collectAPI, interestAPI } from '../services/api';
import { triggerWebToMobile } from '../services/syncService';
import { showError, showSuccess, showWarning, showInfo, showDialog } from '../utils/dialog';

// ── Static data ────────────────────────────────────────────────────────────────
const COUNTRIES = [
  { code: 'US', name: 'United States' }, { code: 'UK', name: 'United Kingdom' },
  { code: 'DE', name: 'Germany' },       { code: 'FR', name: 'France' },
  { code: 'AE', name: 'UAE' },           { code: 'SA', name: 'Saudi Arabia' },
  { code: 'IN', name: 'India' },         { code: 'CA', name: 'Canada' },
  { code: 'AU', name: 'Australia' },     { code: 'JP', name: 'Japan' },
  { code: 'BR', name: 'Brazil' },        { code: 'EG', name: 'Egypt' },
  { code: 'NG', name: 'Nigeria' },       { code: 'ZA', name: 'South Africa' },
  { code: 'SG', name: 'Singapore' },     { code: 'KR', name: 'South Korea' },
  { code: 'MX', name: 'Mexico' },        { code: 'TR', name: 'Turkey' },
  { code: 'ID', name: 'Indonesia' },     { code: 'TH', name: 'Thailand' },
  { code: 'PH', name: 'Philippines' },   { code: 'MY', name: 'Malaysia' },
  { code: 'PK', name: 'Pakistan' },      { code: 'KE', name: 'Kenya' },
  { code: 'GH', name: 'Ghana' },         { code: 'MA', name: 'Morocco' },
  { code: 'CO', name: 'Colombia' },      { code: 'CL', name: 'Chile' },
  { code: 'AR', name: 'Argentina' },     { code: 'PL', name: 'Poland' },
  { code: 'NL', name: 'Netherlands' },   { code: 'SE', name: 'Sweden' },
  { code: 'CH', name: 'Switzerland' },   { code: 'IT', name: 'Italy' },
  { code: 'ES', name: 'Spain' },         { code: 'QA', name: 'Qatar' },
  { code: 'KW', name: 'Kuwait' },        { code: 'BH', name: 'Bahrain' },
  { code: 'OM', name: 'Oman' },          { code: 'JO', name: 'Jordan' },
  { code: 'LB', name: 'Lebanon' },       { code: 'NZ', name: 'New Zealand' },
  { code: 'IE', name: 'Ireland' },       { code: 'IL', name: 'Israel' },
  { code: 'RU', name: 'Russia' },        { code: 'UA', name: 'Ukraine' },
  { code: 'VN', name: 'Vietnam' },       { code: 'BD', name: 'Bangladesh' },
  { code: 'RO', name: 'Romania' },       { code: 'BE', name: 'Belgium' },
  { code: 'AT', name: 'Austria' },       { code: 'DK', name: 'Denmark' },
  { code: 'NO', name: 'Norway' },        { code: 'FI', name: 'Finland' },
  { code: 'PT', name: 'Portugal' },      { code: 'CZ', name: 'Czech Republic' },
  { code: 'HU', name: 'Hungary' },       { code: 'GR', name: 'Greece' },
  { code: 'IQ', name: 'Iraq' },          { code: 'DZ', name: 'Algeria' },
  { code: 'TZ', name: 'Tanzania' },      { code: 'ET', name: 'Ethiopia' },
];
const COUNTRY_NAME_MAP = Object.fromEntries(COUNTRIES.map((c) => [c.code, c.name]));

const SOCIAL_PLATFORMS = [
  { id: 'reddit',   label: 'Reddit',    icon: 'logo-reddit'   },
  { id: 'telegram', label: 'Telegram',  icon: 'paper-plane'   },
  { id: 'twitter',  label: 'Twitter/X', icon: 'logo-twitter'  },
  { id: 'facebook', label: 'Facebook',  icon: 'logo-facebook' },
  { id: 'linkedin', label: 'LinkedIn',  icon: 'logo-linkedin' },
];

const JOB_TITLES = ['CEO', 'CTO', 'CFO', 'COO', 'Founder', 'Co-Founder', 'VP Sales', 'VP Marketing', 'Marketing Director', 'Sales Manager', 'Product Manager', 'Head of Growth'];
const INDUSTRIES = ['Technology', 'SaaS', 'Finance', 'Healthcare', 'E-Commerce', 'Marketing', 'Manufacturing', 'Real Estate', 'Education', 'Consulting', 'Fintech', 'IoT', 'AI / ML'];
const MAX_PER_COUNTRY_OPTS = [5, 10, 20, 30, 50];
const MAX_PER_PLATFORM_OPTS = [5, 10, 20, 30];
const AUTO_LIMIT_OPTS = [25, 50, 75, 100];

const COLLECT_MODES = [
  { key: 'web',      label: 'Web',       icon: 'globe-outline'          },
  { key: 'social',   label: 'Social',    icon: 'share-social-outline'   },
  { key: 'auto',     label: 'Auto API',  icon: 'hardware-chip-outline'  },
  { key: 'interest', label: 'Interest',  icon: 'heart-outline'          },
];
const INTEREST_LIMIT_OPTS = [10, 20, 30, 50, 100];

const TABS = [
  { key: 'collect', label: 'Collect', icon: 'flash-outline' },
  { key: 'qualify', label: 'Qualify', icon: 'checkmark-circle-outline' },
  { key: 'chat',    label: 'AI Chat', icon: 'chatbubble-ellipses-outline' },
  { key: 'log',     label: 'Log',     icon: 'list-outline' },
];

// ── Chip component ─────────────────────────────────────────────────────────────
function Chip({ label, active, onPress, color = COLORS.primary, small }) {
  return (
    <TouchableOpacity
      style={[
        chipStyle.base,
        small && chipStyle.small,
        active ? { backgroundColor: color, borderColor: color } : {},
      ]}
      onPress={onPress}
      activeOpacity={0.75}
    >
      <Text style={[chipStyle.txt, small && chipStyle.smallTxt, active && chipStyle.activeTxt]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}
const chipStyle = StyleSheet.create({
  base:      { paddingHorizontal: 13, paddingVertical: 7, borderRadius: 20, borderWidth: 1, borderColor: 'rgba(148,163,184,0.4)', backgroundColor: 'transparent', margin: 3 },
  small:     { paddingHorizontal: 10, paddingVertical: 5 },
  txt:       { fontSize: 12, fontWeight: '600', color: '#6b7280' },
  smallTxt:  { fontSize: 11 },
  activeTxt: { color: '#fff' },
});

// ── Field label ────────────────────────────────────────────────────────────────
function FieldLabel({ text, theme }) {
  return <Text style={{ fontSize: 12, fontWeight: '700', color: theme.textMuted, marginBottom: 6, marginTop: 12 }}>{text}</Text>;
}

export default function AIEngineScreen() {
  const { theme } = useTheme();
  const { isAdmin, isManager } = useAuth();

  // ── shared ────────────────────────────────────────────────────────────────
  const [status, setStatus]       = useState(null);
  const [activeTab, setActiveTab] = useState('collect');
  const [collectMode, setCollectMode] = useState('web');

  // ── task polling (shared) ─────────────────────────────────────────────────
  const [running, setRunning]     = useState(false);
  const [taskId, setTaskId]       = useState(null);
  const [taskMode, setTaskMode]   = useState('web'); // which mode started the task
  const [progress, setProgress]   = useState(null);
  const [elapsed, setElapsed]     = useState(0);
  const pollRef = useRef(null);
  const elapsedRef = useRef(null);
  const fillAnim = useRef(new Animated.Value(0)).current;

  // ── pipeline / training ───────────────────────────────────────────────────
  const [training, setTraining]         = useState(false);
  const [syntheticN, setSyntheticN]     = useState(5000);
  const [trainResult, setTrainResult]   = useState(null);
  const [pipelineSummary, setPipeline]  = useState(null);
  const [loadingPipeline, setLoadingPipeline] = useState(false);

  // ── ML dashboard (manager + admin) ────────────────────────────────────────
  const [dashboardData, setDashboardData]       = useState(null);
  const [loadingDashboard, setLoadingDashboard] = useState(false);

  // ── web collection state ──────────────────────────────────────────────────
  const [webQuery, setWebQuery]           = useState('');
  const [webCountries, setWebCountries]   = useState(['US', 'UK']);
  const [webCity, setWebCity]             = useState('');
  const [webMaxPerCountry, setWebMax]     = useState(10);
  const [webCollType, setWebCollType]     = useState('companies');
  const [countrySearch, setCountrySearch] = useState('');

  // ── social collection state ───────────────────────────────────────────────
  const [socialQuery, setSocialQuery]         = useState('');
  const [socialPlatforms, setSocialPlatforms] = useState(['reddit', 'linkedin']);
  const [socialIndustry, setSocialIndustry]   = useState('');
  const [socialLocation, setSocialLocation]   = useState('');
  const [socialLocFocus, setSocialLocFocus]   = useState(false);
  const [socialMaxPer, setSocialMax]          = useState(10);
  const [socialCollType, setSocialCollType]   = useState('both');

  // ── auto collection state ─────────────────────────────────────────────────
  const [autoKeywords, setAutoKeywords]     = useState('');
  const [autoTitles, setAutoTitles]         = useState([]);
  const [autoLocations, setAutoLocations]   = useState([]);
  const [autoIndustries, setAutoIndustries] = useState([]);
  const [autoLimit, setAutoLimit]           = useState(25);

  // ── interest collection state ─────────────────────────────────────────────
  const [interestCategories, setInterestCategories] = useState([]);
  const [interestCategory, setInterestCategory]     = useState('');
  const [interestCountry, setInterestCountry]       = useState('');
  const [interestCountryFocus, setInterestCountryFocus] = useState(false);
  const [interestCity, setInterestCity]             = useState('');
  const [interestMaxLeads, setInterestMax]          = useState(30);
  const [loadingCategories, setLoadingCats]         = useState(false);

  // ── qualify tab ───────────────────────────────────────────────────────────
  const [pendingLeads, setPending]       = useState([]);
  const [loadingPending, setLoadingPending] = useState(false);
  const [pendingError, setPendingError]  = useState(null);
  const [qualifying, setQualifying]      = useState(false);
  const [qualifyResult, setQualifyResult] = useState(null);

  // ── chat tab ──────────────────────────────────────────────────────────────
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', text: "Hi! I'm your AI assistant. Ask me anything about your leads, pipeline, or sales strategy." }
  ]);
  const [chatInput, setChatInput]   = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatScrollRef = useRef(null);

  // ── log tab ───────────────────────────────────────────────────────────────
  const [activityLog, setActivityLog] = useState([]);
  const [logLoading, setLogLoading]   = useState(false);

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    aiAPI.getStatus().then((r) => setStatus(r.data)).catch(() => {});
    fetchActivityLog();
    fetchPipelineSummary();
    fetchInterestCategories();
  }, []);

  useEffect(() => {
    if (activeTab === 'qualify') fetchPendingLeads();
    if (activeTab === 'log')     fetchActivityLog();
  }, [activeTab]);

  // ── Polling ───────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!taskId || !running) return;
    let pollCount = 0;
    const MAX_POLLS = 180; // 6 min

    const getStatus = async (id, mode) => {
      if (mode === 'social')   return collectAPI.socialStatus(id);
      if (mode === 'auto')     return collectAPI.autoStatus(id);
      if (mode === 'interest') return interestAPI.status(id);
      return collectAPI.collectionStatus(id);
    };

    pollRef.current = setInterval(async () => {
      pollCount++;
      try {
        const r    = await getStatus(taskId, taskMode);
        const task = r.data?.data || r.data;
        setProgress(task);

        const done = task?.status === 'done' || task?.status === 'error' || pollCount >= MAX_POLLS;
        if (done) {
          clearInterval(pollRef.current);
          clearInterval(elapsedRef.current);
          setRunning(false);
          if (task?.status === 'done') {
            triggerWebToMobile({ silent: true }).catch(() => {});
            showSuccess('Collection Complete', `Saved ${task.saved || task.collected || 0} leads`);
          } else if (task?.status === 'error') {
            showError('Collection Failed', task.error || 'Unknown error');
          } else {
            showWarning('Timed Out', 'Collection is taking too long. Check the Log tab.');
          }
        }
      } catch (err) {
        console.warn('[AIEngine] Poll failed:', err?.message);
        clearInterval(pollRef.current);
        clearInterval(elapsedRef.current);
        setRunning(false);
        showError('Connection Lost', 'Lost contact with the server. Try again.');
      }
    }, 2000);

    return () => clearInterval(pollRef.current);
  }, [taskId, running, taskMode]);

  // ── Elapsed-time ticker (mirrors web's live "Xs" counter) ───────────────────
  useEffect(() => {
    if (!running) return;
    elapsedRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(elapsedRef.current);
  }, [running]);

  // ── Animate the progress fill instead of snapping to the new width ─────────
  useEffect(() => {
    Animated.timing(fillAnim, {
      toValue: progress?.percent || 0,
      duration: 400,
      useNativeDriver: false,
    }).start();
  }, [progress?.percent]);

  const fetchActivityLog = async () => {
    try {
      setLogLoading(true);
      const r = await aiAPI.getActivityLog();
      setActivityLog(r.data?.logs || r.data?.activities || []);
    } catch (err) {
      console.warn('[AIEngine] fetchActivityLog failed:', err?.message);
    } finally {
      setLogLoading(false);
    }
  };

  const fetchInterestCategories = async () => {
    try {
      setLoadingCats(true);
      const r = await interestAPI.getCategories();
      setInterestCategories(r.data?.categories || []);
    } catch (err) {
      console.warn('[AIEngine] fetchInterestCategories failed:', err?.message);
    } finally {
      setLoadingCats(false);
    }
  };

  const fetchPipelineSummary = async () => {
    try {
      setLoadingPipeline(true);
      const r = await aiAPI.getPipelineSummary();
      setPipeline(r.data);
    } catch (err) {
      // 403 = endpoint requires manager/admin role — silently skip
      if (err?.response?.status !== 403) {
        console.warn('[AIEngine] fetchPipelineSummary failed:', err?.message);
      }
    } finally {
      setLoadingPipeline(false);
    }
  };

  const fetchDashboard = async () => {
    try {
      setLoadingDashboard(true);
      const r = await collectAPI.getMLDashboard();
      setDashboardData(r.data);
    } catch (err) {
      console.warn('[AIEngine] fetchDashboard failed:', err?.message);
    } finally {
      setLoadingDashboard(false);
    }
  };

  const fetchPendingLeads = async () => {
    try {
      setLoadingPending(true);
      setPendingError(null);
      const resp = await leadsAPI.getLeads({ status: 'pending,low_quality', per_page: 50 });
      setPending(resp.data?.leads || []);
    } catch (err) {
      console.warn('[AIEngine] fetchPendingLeads failed:', err?.message);
      setPendingError(err?.response?.data?.message || err?.message || 'Failed to load leads');
      setPending([]);
    } finally {
      setLoadingPending(false);
    }
  };

  // ── Collection handlers ───────────────────────────────────────────────────
  const startTask = (taskIdVal, mode) => {
    setTaskId(taskIdVal);
    setTaskMode(mode);
    setProgress(null);
    setElapsed(0);
    fillAnim.setValue(0);
    setRunning(true);
  };

  const handleWebCollect = async () => {
    if (!webQuery.trim()) { showWarning('Required', 'Enter a search query'); return; }
    if (webCountries.length === 0) { showWarning('Required', 'Select at least one country'); return; }
    try {
      setRunning(true);
      const resp = await collectAPI.startCollection({
        query:           webQuery.trim(),
        countries:       webCountries,
        city:            webCity.trim() || undefined,
        max_per_country: webMaxPerCountry,
        collection_type: webCollType,
      });
      startTask(resp.data?.data?.task_id || resp.data?.task_id || resp.data?.id, 'web');
    } catch (err) {
      setRunning(false);
      showError('Error', err?.response?.data?.message || 'Failed to start web collection');
    }
  };

  const handleSocialCollect = async () => {
    if (!socialQuery.trim()) { showWarning('Required', 'Enter a search query'); return; }
    if (socialPlatforms.length === 0) { showWarning('Required', 'Select at least one platform'); return; }
    try {
      setRunning(true);
      const resp = await collectAPI.startSocial({
        query:            socialQuery.trim(),
        platforms:        socialPlatforms,
        industry:         socialIndustry.trim() || undefined,
        location:         socialLocation.trim() || undefined,
        max_per_platform: socialMaxPer,
        collect_type:     socialCollType,
      });
      startTask(resp.data?.data?.task_id || resp.data?.task_id || resp.data?.id, 'social');
    } catch (err) {
      setRunning(false);
      showError('Error', err?.response?.data?.message || 'Failed to start social collection');
    }
  };

  const handleAutoCollect = async () => {
    if (!autoKeywords.trim() && autoTitles.length === 0 && autoLocations.length === 0) {
      showWarning('Required', 'Enter keywords, or select job titles and locations');
      return;
    }
    try {
      setRunning(true);
      const resp = await collectAPI.startAuto({
        keywords:   autoKeywords.trim() || undefined,
        titles:     autoTitles.length   ? autoTitles     : undefined,
        locations:  autoLocations.length ? autoLocations  : undefined,
        industries: autoIndustries.length ? autoIndustries : undefined,
        limit:      autoLimit,
      });
      startTask(resp.data?.data?.task_id || resp.data?.task_id || resp.data?.id, 'auto');
    } catch (err) {
      setRunning(false);
      showError('Error', err?.response?.data?.message || 'Failed to start auto collection');
    }
  };

  const handleInterestCollect = async () => {
    if (!interestCategory) { showWarning('Required', 'Select a lead category'); return; }
    if (!interestCountry.trim()) { showWarning('Required', 'Enter a target country'); return; }
    try {
      setRunning(true);
      const resp = await interestAPI.start({
        category:  interestCategory,
        country:   interestCountry.trim(),
        city:      interestCity.trim() || undefined,
        max_leads: interestMaxLeads,
      });
      startTask(resp.data?.task_id || resp.data?.data?.task_id, 'interest');
    } catch (err) {
      setRunning(false);
      showError('Error', err?.response?.data?.message || 'Failed to start interest collection');
    }
  };

  const handleStop = () => {
    clearInterval(pollRef.current);
    clearInterval(elapsedRef.current);
    setRunning(false);
    setTaskId(null);
    setProgress(null);
    showInfo('Stopped', 'Collection stopped. Leads collected so far are saved.');
  };

  const handleTrainML = async () => {
    try {
      setTraining(true);
      setTrainResult(null);
      const resp = await aiAPI.retrain({ use_db: true, balance: 'auto', synthetic_n: syntheticN });
      const d = resp.data || {};
      setTrainResult(d);
      // Refresh status to show updated AUC
      aiAPI.getStatus().then((r) => setStatus(r.data)).catch(() => {});
    } catch (err) {
      showError('Training Error', err?.response?.data?.message || err?.message || 'ML training failed');
    } finally {
      setTraining(false);
    }
  };

  const handleQualifyPending = async () => {
    if (pendingLeads.length === 0) { showSuccess('All Clear', 'No pending leads to qualify.'); return; }
    const ids = pendingLeads.map((l) => l.id);
    try {
      setQualifying(true);
      setQualifyResult(null);
      const resp = await leadsAPI.batchQualify(ids);
      const s = resp.data?.stats || {};
      setQualifyResult(resp.data);
      triggerWebToMobile({ silent: true }).catch(() => {});
      fetchPendingLeads();
      showSuccess(
        'Qualification Complete',
        `Processed: ${s.total ?? ids.length}\n` +
        `Hot: ${s.hot ?? 0}  Warm: ${s.warm ?? 0}  Cold: ${s.cold ?? 0}  Unqualified: ${s.unqualified ?? 0}\n` +
        `Duration: ${s.duration_seconds ?? 0}s`,
      );
    } catch (err) {
      showError('Error', err?.response?.data?.message || err?.message || 'Batch qualification failed');
    } finally {
      setQualifying(false);
    }
  };

  const handleSendChat = async () => {
    const msg = chatInput.trim();
    if (!msg) return;
    Keyboard.dismiss();
    setChatInput('');
    // Snapshot current history before appending the new user message
    const historySnapshot = chatMessages.map((m) => ({ role: m.role, text: m.text }));
    setChatMessages((prev) => [...prev, { role: 'user', text: msg }]);
    setChatLoading(true);
    try {
      const resp  = await aiAPI.chat(msg, historySnapshot);
      const reply = resp.data?.response || resp.data?.message || 'No response';
      setChatMessages((prev) => [...prev, { role: 'assistant', text: reply }]);
    } catch (err) {
      const errMsg = err?.response?.data?.message || 'AI is unavailable right now. Try again.';
      setChatMessages((prev) => [...prev, { role: 'assistant', text: errMsg, error: true }]);
    } finally {
      setChatLoading(false);
      setTimeout(() => chatScrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  };

  // ── Helpers ───────────────────────────────────────────────────────────────
  const toggle = (arr, val) => arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val];
  const s = styles(theme);

  // ── Progress label based on mode ──────────────────────────────────────────
  // `stage_name` carries the live staged message (e.g. "Scoring with XGBoost…")
  // and is set on nearly every tick in demo mode — prefer it, falling back to
  // the older per-mode heuristics for real-mode ticks that don't set it.
  const progressLabel = () => {
    if (!progress) return 'Starting…';
    if (progress.stage_name) return progress.stage_name;
    if (taskMode === 'web')      return progress.current_country  ? `Scanning ${progress.current_country}…`  : 'Processing…';
    if (taskMode === 'social')   return progress.current_platform ? `Scanning ${progress.current_platform}…` : 'Processing…';
    if (taskMode === 'auto')     return progress.sources?.length  ? `Sources: ${progress.sources.join(', ')}` : 'Running pipeline…';
    if (taskMode === 'interest') return `Collecting ${interestCategory} leads…`;
    return 'Processing…';
  };
  const progressSub = () => {
    if (!progress) return '';
    let base = '';
    if (taskMode === 'web')      base = `${progress.saved || 0} saved · ${progress.completed_countries || 0}/${progress.total_countries || webCountries.length} countries`;
    else if (taskMode === 'social') {
      base = `${progress.saved || 0} saved · ${progress.completed_platforms || 0}/${progress.total_platforms || socialPlatforms.length} platforms`;
      if (progress.platform_leads && Object.keys(progress.platform_leads).length) {
        const perPlatform = Object.entries(progress.platform_leads)
          .filter(([, n]) => n > 0)
          .map(([plat, n]) => `${plat}: ${n}`)
          .join(' · ');
        if (perPlatform) base += `\n${perPlatform}`;
      }
    }
    else if (taskMode === 'auto')     base = `${progress.saved || 0} saved · ${progress.skipped || 0} skipped`;
    else if (taskMode === 'interest') base = `${progress.saved || 0} saved · ${progress.skipped || 0} skipped`;
    return elapsed > 0 ? `${base} · ${elapsed}s` : base;
  };

  const filteredCountries = countrySearch.trim()
    ? COUNTRIES.filter((c) =>
        c.name.toLowerCase().includes(countrySearch.toLowerCase()) ||
        c.code.toLowerCase().includes(countrySearch.toLowerCase())
      )
    : COUNTRIES;

  const locationSuggestions = (text) => {
    if (!text || text.length < 2) return [];
    const lower = text.toLowerCase();
    return COUNTRIES.filter(
      (c) => c.name.toLowerCase().includes(lower) || c.code.toLowerCase().includes(lower)
    ).slice(0, 6);
  };

  // Manager + admin get a read-only ML Dashboard tab, matching the web app
  const tabs = isManager
    ? [...TABS, { key: 'dashboard', label: 'ML Stats', icon: 'stats-chart-outline' }]
    : TABS;

  return (
    <View style={s.root}>
      {/* ── Main Tab Bar ─────────────────────────────────────────────────── */}
      <View style={s.tabs}>
        {tabs.map(({ key, label, icon }) => (
          <TouchableOpacity
            key={key}
            style={[s.tab, activeTab === key && s.tabActive]}
            onPress={() => setActiveTab(key)}
          >
            <Ionicons name={icon} size={15} color={activeTab === key ? '#fff' : theme.textMuted} />
            <Text style={[s.tabText, activeTab === key && s.tabTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ══════════════ COLLECT TAB ══════════════ */}
      {activeTab === 'collect' && (
        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">

          {/* AI Status */}
          {status && (
            <View style={s.statusCard}>
              <View style={[s.statusDot, { backgroundColor: status.status === 'idle' || status.status === 'ready' ? COLORS.green : COLORS.amber }]} />
              <Text style={s.statusText}>AI Engine: {status.status || 'Ready'}</Text>
              {status.model && <Text style={s.statusSub}>{status.model}</Text>}
            </View>
          )}

          {/* Pipeline Insights */}
          {pipelineSummary && (
            <View style={s.card}>
              <Text style={s.cardTitle}>
                <Ionicons name="analytics-outline" size={13} color={COLORS.cyan} /> Pipeline Insights
              </Text>
              {typeof (pipelineSummary.executive_summary || pipelineSummary.summary || pipelineSummary.message) === 'string' && (
                <Text style={s.insightText} numberOfLines={4}>
                  {pipelineSummary.executive_summary || pipelineSummary.summary || pipelineSummary.message}
                </Text>
              )}
              {Array.isArray(pipelineSummary.key_insights) &&
                pipelineSummary.key_insights.slice(0, 2).map((r, i) =>
                  typeof r === 'string' ? (
                    <View key={i} style={s.recRow}>
                      <Ionicons name="bulb-outline" size={12} color={COLORS.amber} style={{ marginTop: 2 }} />
                      <Text style={s.recText} numberOfLines={2}>{r}</Text>
                    </View>
                  ) : null
                )
              }
            </View>
          )}

          {/* ── Collect Mode Selector ──────────────────────────────── */}
          <View style={s.modeBar}>
            {COLLECT_MODES.map((m) => (
              <TouchableOpacity
                key={m.key}
                style={[s.modeBtn, collectMode === m.key && s.modeBtnActive]}
                onPress={() => { if (!running) setCollectMode(m.key); }}
              >
                <Ionicons name={m.icon} size={14} color={collectMode === m.key ? '#fff' : theme.textMuted} />
                <Text style={[s.modeTxt, collectMode === m.key && s.modeTxtActive]}>{m.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* ════════════════════════════ WEB MODE ════════════════════════════ */}
          {collectMode === 'web' && (
            <View style={s.card}>
              <Text style={s.sectionHeading}>
                <Ionicons name="globe" size={14} color={COLORS.primary} /> Web Data Collection
              </Text>
              <Text style={s.modeDesc}>Scrapes business directories and search engines by country. No API key needed.</Text>

              <FieldLabel text="Search Query *" theme={theme} />
              <TextInput
                style={[s.queryInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                value={webQuery}
                onChangeText={setWebQuery}
                placeholder='e.g. "software companies" or "digital marketing agency"'
                placeholderTextColor={theme.textMuted}
                multiline
                editable={!running}
              />

              <FieldLabel text="Collection Type" theme={theme} />
              <View style={s.chipRow}>
                {['companies', 'people'].map((t) => (
                  <Chip key={t} label={t.charAt(0).toUpperCase() + t.slice(1)} active={webCollType === t}
                    onPress={() => !running && setWebCollType(t)} />
                ))}
              </View>

              <FieldLabel text={`Target Countries (${webCountries.length} selected)`} theme={theme} />

              {/* Selected countries — removable pills */}
              {webCountries.length > 0 && (
                <View style={s.chipRow}>
                  {webCountries.map((code) => (
                    <TouchableOpacity
                      key={code}
                      style={[s.selectedPill, { backgroundColor: `${COLORS.primary}18`, borderColor: COLORS.primary }]}
                      onPress={() => !running && setWebCountries((p) => p.filter((c) => c !== code))}
                    >
                      <Text style={[s.selectedPillTxt, { color: COLORS.primary }]}>
                        {COUNTRY_NAME_MAP[code] || code}
                      </Text>
                      <Ionicons name="close-circle" size={14} color={COLORS.primary} />
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              {/* Country search */}
              <View style={[s.searchBox, { backgroundColor: theme.input, borderColor: theme.inputBorder }]}>
                <Ionicons name="search-outline" size={15} color={theme.textMuted} style={{ marginRight: 6 }} />
                <TextInput
                  style={{ flex: 1, color: theme.text, fontSize: 13, paddingVertical: 0 }}
                  value={countrySearch}
                  onChangeText={setCountrySearch}
                  placeholder="Search countries…"
                  placeholderTextColor={theme.textMuted}
                  editable={!running}
                />
                {countrySearch.length > 0 && (
                  <TouchableOpacity onPress={() => setCountrySearch('')}>
                    <Ionicons name="close-circle" size={15} color={theme.textMuted} />
                  </TouchableOpacity>
                )}
              </View>

              {/* Filtered country list */}
              <View style={s.chipRow}>
                {filteredCountries
                  .filter((c) => !webCountries.includes(c.code))
                  .map(({ code, name }) => (
                    <TouchableOpacity
                      key={code}
                      style={[s.countryChip, { backgroundColor: theme.input, borderColor: theme.inputBorder }]}
                      onPress={() => !running && setWebCountries((p) => [...p, code])}
                    >
                      <Text style={[s.countryChipTxt, { color: theme.text }]}>{name}</Text>
                    </TouchableOpacity>
                  ))
                }
              </View>
              {filteredCountries.filter((c) => !webCountries.includes(c.code)).length === 0 && countrySearch.length > 0 && (
                <Text style={[s.emptyHint, { color: theme.textMuted }]}>No countries match "{countrySearch}"</Text>
              )}

              <FieldLabel text="City (optional)" theme={theme} />
              <TextInput
                style={[s.fieldInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                value={webCity}
                onChangeText={setWebCity}
                placeholder="e.g. Dubai, London"
                placeholderTextColor={theme.textMuted}
                editable={!running}
              />

              <FieldLabel text={`Max leads per country: ${webMaxPerCountry}`} theme={theme} />
              <View style={s.chipRow}>
                {MAX_PER_COUNTRY_OPTS.map((n) => (
                  <Chip key={n} label={String(n)} active={webMaxPerCountry === n}
                    onPress={() => !running && setWebMax(n)} small />
                ))}
              </View>
            </View>
          )}

          {/* ════════════════════════════ SOCIAL MODE ════════════════════════════ */}
          {collectMode === 'social' && (
            <View style={s.card}>
              <Text style={s.sectionHeading}>
                <Ionicons name="share-social" size={14} color={COLORS.cyan} /> Social Media Collection
              </Text>
              <Text style={s.modeDesc}>Searches Reddit, LinkedIn, Telegram, Twitter/X and Facebook for leads matching your query.</Text>

              <FieldLabel text="Search Query *" theme={theme} />
              <TextInput
                style={[s.queryInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                value={socialQuery}
                onChangeText={setSocialQuery}
                placeholder='e.g. "SaaS founders" or "looking for CRM software"'
                placeholderTextColor={theme.textMuted}
                multiline
                editable={!running}
              />

              <FieldLabel text={`Platforms (${socialPlatforms.length} selected) *`} theme={theme} />
              <View style={s.chipRow}>
                {SOCIAL_PLATFORMS.map(({ id, label, icon }) => (
                  <TouchableOpacity
                    key={id}
                    style={[s.platformChip, socialPlatforms.includes(id) && s.platformChipActive]}
                    onPress={() => !running && setSocialPlatforms((p) => toggle(p, id))}
                  >
                    <Ionicons name={icon} size={14} color={socialPlatforms.includes(id) ? '#fff' : theme.textMuted} />
                    <Text style={[s.platformChipTxt, socialPlatforms.includes(id) && { color: '#fff' }]}>{label}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <FieldLabel text="Collect Type" theme={theme} />
              <View style={s.chipRow}>
                {['person', 'company', 'both'].map((t) => (
                  <Chip key={t} label={t.charAt(0).toUpperCase() + t.slice(1)} active={socialCollType === t}
                    onPress={() => !running && setSocialCollType(t)} color={COLORS.cyan} />
                ))}
              </View>

              <FieldLabel text="Industry (optional)" theme={theme} />
              <TextInput
                style={[s.fieldInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                value={socialIndustry}
                onChangeText={setSocialIndustry}
                placeholder="e.g. SaaS, Fintech, Healthcare"
                placeholderTextColor={theme.textMuted}
                editable={!running}
              />

              <FieldLabel text="Location (optional)" theme={theme} />
              <TextInput
                style={[s.fieldInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                value={socialLocation}
                onChangeText={(t) => { setSocialLocation(t); setSocialLocFocus(true); }}
                onFocus={() => setSocialLocFocus(true)}
                onBlur={() => setTimeout(() => setSocialLocFocus(false), 150)}
                placeholder="e.g. Dubai, New York, India"
                placeholderTextColor={theme.textMuted}
                editable={!running}
              />
              {socialLocFocus && locationSuggestions(socialLocation).length > 0 && (
                <View style={[s.suggestBox, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
                  {locationSuggestions(socialLocation).map((c) => (
                    <TouchableOpacity
                      key={c.code}
                      style={[s.suggestItem, { borderBottomColor: theme.cardBorder }]}
                      onPress={() => { setSocialLocation(c.name); setSocialLocFocus(false); }}
                    >
                      <Text style={[s.suggestCode, { color: COLORS.cyan }]}>{c.code}</Text>
                      <Text style={[s.suggestName, { color: theme.text }]}>{c.name}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              <FieldLabel text={`Max leads per platform: ${socialMaxPer}`} theme={theme} />
              <View style={s.chipRow}>
                {MAX_PER_PLATFORM_OPTS.map((n) => (
                  <Chip key={n} label={String(n)} active={socialMaxPer === n}
                    onPress={() => !running && setSocialMax(n)} small color={COLORS.cyan} />
                ))}
              </View>
            </View>
          )}

          {/* ════════════════════════════ AUTO API MODE ════════════════════════════ */}
          {collectMode === 'auto' && (
            <View style={s.card}>
              <Text style={s.sectionHeading}>
                <Ionicons name="hardware-chip" size={14} color={COLORS.purple} /> Auto API Pipeline
              </Text>
              <Text style={s.modeDesc}>Uses Apollo, Hunter.io, PDL and Clearbit to find and enrich leads. Requires API keys in settings.</Text>

              <FieldLabel text="Keywords (optional)" theme={theme} />
              <TextInput
                style={[s.queryInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                value={autoKeywords}
                onChangeText={setAutoKeywords}
                placeholder='e.g. "B2B SaaS growth hacking"'
                placeholderTextColor={theme.textMuted}
                multiline
                editable={!running}
              />

              <FieldLabel text={`Job Titles (${autoTitles.length} selected)`} theme={theme} />
              <View style={s.chipRow}>
                {JOB_TITLES.map((t) => (
                  <Chip key={t} label={t} active={autoTitles.includes(t)} small
                    onPress={() => !running && setAutoTitles((p) => toggle(p, t))} color={COLORS.purple} />
                ))}
              </View>

              <FieldLabel text={`Target Locations (${autoLocations.length} selected)`} theme={theme} />
              {autoLocations.length > 0 && (
                <View style={s.chipRow}>
                  {autoLocations.map((l) => (
                    <TouchableOpacity
                      key={l}
                      style={[s.selectedPill, { backgroundColor: `${COLORS.purple}18`, borderColor: COLORS.purple }]}
                      onPress={() => !running && setAutoLocations((p) => p.filter((x) => x !== l))}
                    >
                      <Text style={[s.selectedPillTxt, { color: COLORS.purple }]}>{l}</Text>
                      <Ionicons name="close-circle" size={14} color={COLORS.purple} />
                    </TouchableOpacity>
                  ))}
                </View>
              )}
              <View style={s.chipRow}>
                {COUNTRIES.filter((c) => !autoLocations.includes(c.name)).map(({ code, name }) => (
                  <TouchableOpacity
                    key={code}
                    style={[s.countryChip, { backgroundColor: theme.input, borderColor: theme.inputBorder }]}
                    onPress={() => !running && setAutoLocations((p) => [...p, name])}
                  >
                    <Text style={[s.countryChipTxt, { color: theme.text }]}>{name}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <FieldLabel text={`Industries (${autoIndustries.length} selected)`} theme={theme} />
              <View style={s.chipRow}>
                {INDUSTRIES.map((ind) => (
                  <Chip key={ind} label={ind} active={autoIndustries.includes(ind)} small
                    onPress={() => !running && setAutoIndustries((p) => toggle(p, ind))} color={COLORS.purple} />
                ))}
              </View>

              <FieldLabel text={`Lead Limit: ${autoLimit}`} theme={theme} />
              <View style={s.chipRow}>
                {AUTO_LIMIT_OPTS.map((n) => (
                  <Chip key={n} label={String(n)} active={autoLimit === n}
                    onPress={() => !running && setAutoLimit(n)} small color={COLORS.purple} />
                ))}
              </View>
            </View>
          )}

          {/* ════════════════════════════ INTEREST MODE ════════════════════════════ */}
          {collectMode === 'interest' && (
            <View style={s.card}>
              <Text style={s.sectionHeading}>
                <Ionicons name="heart" size={14} color={COLORS.red} /> Interest-Based Collection
              </Text>
              <Text style={s.modeDesc}>Collects leads actively looking for a specific product or service category in a target market.</Text>

              <FieldLabel text="Lead Category *" theme={theme} />
              {loadingCategories ? (
                <ActivityIndicator color={COLORS.primary} style={{ marginVertical: 8 }} />
              ) : interestCategories.length === 0 ? (
                <TouchableOpacity onPress={fetchInterestCategories} style={{ padding: 8 }}>
                  <Text style={{ color: COLORS.primary, fontSize: 13, fontWeight: '600' }}>Tap to load categories</Text>
                </TouchableOpacity>
              ) : (
                <View style={s.chipRow}>
                  {interestCategories.map((cat) => (
                    <Chip
                      key={cat.slug}
                      label={cat.name}
                      active={interestCategory === cat.slug}
                      onPress={() => !running && setInterestCategory(cat.slug)}
                      color={COLORS.red}
                      small
                    />
                  ))}
                </View>
              )}

              <FieldLabel text="Target Country *" theme={theme} />
              <TextInput
                style={[s.fieldInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                value={interestCountry}
                onChangeText={(t) => { setInterestCountry(t); setInterestCountryFocus(true); }}
                onFocus={() => setInterestCountryFocus(true)}
                onBlur={() => setTimeout(() => setInterestCountryFocus(false), 150)}
                placeholder="e.g. United States, Germany, UAE"
                placeholderTextColor={theme.textMuted}
                editable={!running}
              />
              {interestCountryFocus && locationSuggestions(interestCountry).length > 0 && (
                <View style={[s.suggestBox, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
                  {locationSuggestions(interestCountry).map((c) => (
                    <TouchableOpacity
                      key={c.code}
                      style={[s.suggestItem, { borderBottomColor: theme.cardBorder }]}
                      onPress={() => { setInterestCountry(c.name); setInterestCountryFocus(false); }}
                    >
                      <Text style={[s.suggestCode, { color: COLORS.primary }]}>{c.code}</Text>
                      <Text style={[s.suggestName, { color: theme.text }]}>{c.name}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              <FieldLabel text="City (optional)" theme={theme} />
              <TextInput
                style={[s.fieldInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                value={interestCity}
                onChangeText={setInterestCity}
                placeholder="e.g. New York, Berlin"
                placeholderTextColor={theme.textMuted}
                editable={!running}
              />

              <FieldLabel text={`Max Leads: ${interestMaxLeads}`} theme={theme} />
              <View style={s.chipRow}>
                {INTEREST_LIMIT_OPTS.map((n) => (
                  <Chip key={n} label={String(n)} active={interestMaxLeads === n}
                    onPress={() => !running && setInterestMax(n)} small color={COLORS.red} />
                ))}
              </View>
            </View>
          )}

          {/* ── Progress Card ──────────────────────────────────────────── */}
          {(running || progress) && (
            <View style={s.card}>
              <View style={s.sectionHeader}>
                <Text style={s.cardTitle}>Collection Progress{running ? ` · ${elapsed}s` : ''}</Text>
                {running && (
                  <TouchableOpacity onPress={handleStop}>
                    <Text style={{ fontSize: 13, color: COLORS.red, fontWeight: '700' }}>Stop</Text>
                  </TouchableOpacity>
                )}
              </View>
              <View style={s.progressRow}>
                <Text style={s.progressTxt} numberOfLines={1}>{progressLabel()}</Text>
                <Text style={[s.progressTxt, { color: COLORS.primary, fontWeight: '700' }]}>{progress?.percent || 0}%</Text>
              </View>
              <View style={s.progressBg}>
                <Animated.View
                  style={[
                    s.progressFill,
                    {
                      width: fillAnim.interpolate({
                        inputRange: [0, 100],
                        outputRange: ['0%', '100%'],
                        extrapolate: 'clamp',
                      }),
                    },
                  ]}
                />
              </View>
              <Text style={s.progressSub}>{progressSub()}</Text>
              {running && <ActivityIndicator color={COLORS.primary} style={{ marginTop: 8 }} />}
            </View>
          )}

          {/* ── Start Button ───────────────────────────────────────────── */}
          {!running && (
            <TouchableOpacity
              style={[s.startBtn, {
                backgroundColor:
                  collectMode === 'auto'     ? COLORS.purple :
                  collectMode === 'social'   ? COLORS.cyan   :
                  collectMode === 'interest' ? COLORS.red    :
                  COLORS.primary,
              }]}
              onPress={
                collectMode === 'web'      ? handleWebCollect      :
                collectMode === 'social'   ? handleSocialCollect   :
                collectMode === 'interest' ? handleInterestCollect :
                handleAutoCollect
              }
            >
              <Ionicons name="flash" size={18} color="#fff" />
              <Text style={s.startBtnText}>
                {collectMode === 'web'      ? 'Start Web Collection'    :
                 collectMode === 'social'   ? 'Start Social Collection' :
                 collectMode === 'interest' ? 'Start Interest Collect'  :
                 'Run Auto API Pipeline'}
              </Text>
            </TouchableOpacity>
          )}

          {/* ── ML Training (admin only) ────────────────────────────────── */}
          {isAdmin && (
            <View style={s.card}>
              <Text style={s.cardTitle}>ML Model Training</Text>

              {/* Current model AUC */}
              {status?.stats?.ml_model && (
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10, gap: 12 }}>
                  <View style={{ backgroundColor: COLORS.purple + '22', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 }}>
                    <Text style={{ color: COLORS.purple, fontWeight: '700', fontSize: 13 }}>
                      AUC {((status.stats.ml_model.auc || 0) * 100).toFixed(1)}%
                    </Text>
                  </View>
                  <View style={{ backgroundColor: COLORS.cyan + '22', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 }}>
                    <Text style={{ color: COLORS.cyan, fontWeight: '700', fontSize: 13 }}>
                      {(status.stats.ml_model.n_samples || 0).toLocaleString()} samples
                    </Text>
                  </View>
                </View>
              )}

              {/* Synthetic data size selector */}
              <Text style={[s.cardDesc, { marginBottom: 6 }]}>Blend synthetic leads for stronger training:</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
                {[
                  { n: 0,     label: 'DB Only' },
                  { n: 1000,  label: '+1K' },
                  { n: 5000,  label: '+5K' },
                  { n: 15000, label: '+15K' },
                ].map(({ n, label }) => (
                  <TouchableOpacity
                    key={n}
                    onPress={() => setSyntheticN(n)}
                    style={{
                      paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20,
                      backgroundColor: syntheticN === n ? COLORS.purple : COLORS.purple + '22',
                    }}
                  >
                    <Text style={{ color: syntheticN === n ? '#fff' : COLORS.purple, fontSize: 12, fontWeight: '600' }}>
                      {label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Train button */}
              <TouchableOpacity
                style={[s.trainBtn, training && { opacity: 0.6 }]}
                onPress={handleTrainML}
                disabled={training}
              >
                {training ? <ActivityIndicator color={COLORS.purple} size="small" /> : <Ionicons name="cog" size={18} color={COLORS.purple} />}
                <Text style={[s.trainBtnText, { color: COLORS.purple }]}>
                  {training ? 'Training…' : `Train ML Model${syntheticN > 0 ? ` (+${(syntheticN / 1000).toFixed(0)}K synth)` : ''}`}
                </Text>
              </TouchableOpacity>

              {/* Inline result after training */}
              {trainResult && (
                <View style={{ marginTop: 12, padding: 10, backgroundColor: (trainResult.retrained ? COLORS.green : COLORS.amber) + '18', borderRadius: 8 }}>
                  <Text style={{ color: trainResult.retrained ? COLORS.green : COLORS.amber, fontWeight: '700', fontSize: 13, marginBottom: 4 }}>
                    {trainResult.retrained ? 'Model Updated' : 'No improvement — kept old model'}
                  </Text>
                  {[
                    trainResult.new_model?.auc != null && `New AUC: ${(trainResult.new_model.auc * 100).toFixed(2)}%`,
                    trainResult.old_model?.auc != null && `Old AUC: ${(trainResult.old_model.auc * 100).toFixed(2)}%`,
                    trainResult.improvement?.auc_delta != null && `Delta: ${trainResult.improvement.auc_delta >= 0 ? '+' : ''}${(trainResult.improvement.auc_delta * 100).toFixed(2)}%`,
                    trainResult.new_model?.f1 != null && `F1: ${(trainResult.new_model.f1 * 100).toFixed(1)}%`,
                    trainResult.leads_used != null && `Samples: ${trainResult.leads_used.toLocaleString()}${trainResult.synthetic_used ? ` (${trainResult.synthetic_used.toLocaleString()} synthetic)` : ''}`,
                  ].filter(Boolean).map((line, i) => (
                    <Text key={i} style={{ color: theme.text, fontSize: 12, marginTop: 1 }}>{line}</Text>
                  ))}
                </View>
              )}
            </View>
          )}

        </ScrollView>
      )}

      {/* ══════════════ QUALIFY TAB ══════════════ */}
      {activeTab === 'qualify' && (
        <ScrollView contentContainerStyle={s.scroll}>
          <View style={s.card}>
            <View style={s.sectionHeader}>
              <Text style={s.cardTitle}>Pending Leads</Text>
              <TouchableOpacity onPress={fetchPendingLeads}>
                <Ionicons name="refresh" size={18} color={COLORS.primary} />
              </TouchableOpacity>
            </View>

            {loadingPending ? (
              <ActivityIndicator color={COLORS.primary} style={{ marginVertical: 16 }} />
            ) : pendingError ? (
              <View style={s.emptyBox}>
                <Ionicons name="alert-circle" size={40} color={COLORS.red} />
                <Text style={[s.emptyTxt, { color: COLORS.red }]}>Failed to load leads</Text>
                <Text style={[s.cardDesc, { textAlign: 'center', marginTop: 4 }]}>{pendingError}</Text>
                <TouchableOpacity style={[s.startBtn, { marginTop: 12, paddingHorizontal: 24, backgroundColor: COLORS.red }]} onPress={fetchPendingLeads}>
                  <Text style={s.startBtnText}>Retry</Text>
                </TouchableOpacity>
              </View>
            ) : pendingLeads.length === 0 ? (
              <View style={s.emptyBox}>
                <Ionicons name="checkmark-done-circle" size={40} color={COLORS.green} />
                <Text style={s.emptyTxt}>All leads are qualified!</Text>
              </View>
            ) : (
              <>
                <Text style={s.cardDesc}>{pendingLeads.length} lead{pendingLeads.length !== 1 ? 's' : ''} awaiting AI qualification</Text>
                {pendingLeads.slice(0, 5).map((l) => (
                  <View key={l.id} style={s.pendingRow}>
                    <View style={s.pendingAvatar}>
                      <Text style={s.pendingAvatarTxt}>{(l.name || '?')[0].toUpperCase()}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.pendingName} numberOfLines={1}>{l.name}</Text>
                      <Text style={s.pendingCompany} numberOfLines={1}>{l.company || l.email || '—'}</Text>
                    </View>
                  </View>
                ))}
                {pendingLeads.length > 5 && (
                  <Text style={s.moreText}>+{pendingLeads.length - 5} more</Text>
                )}
                <TouchableOpacity
                  style={[s.startBtn, { marginTop: 14, backgroundColor: COLORS.primary }, qualifying && { opacity: 0.6 }]}
                  onPress={handleQualifyPending}
                  disabled={qualifying}
                >
                  {qualifying
                    ? <ActivityIndicator color="#fff" />
                    : <><Ionicons name="flash" size={18} color="#fff" /><Text style={s.startBtnText}>Qualify All with AI</Text></>
                  }
                </TouchableOpacity>
              </>
            )}
          </View>

          {qualifyResult && (
            <View style={s.card}>
              <Text style={s.cardTitle}>Qualification Results</Text>
              {[
                { label: 'Total Processed', value: qualifyResult.stats?.total ?? qualifyResult.qualified_count, color: COLORS.primary },
                { label: 'Hot Leads',        value: qualifyResult.stats?.hot,        color: COLORS.green },
                { label: 'Warm Leads',       value: qualifyResult.stats?.warm,       color: COLORS.amber },
                { label: 'Cold Leads',       value: qualifyResult.stats?.cold,       color: COLORS.cyan },
                { label: 'Unqualified',      value: qualifyResult.stats?.unqualified, color: COLORS.textSecondary },
                { label: 'Duration',         value: qualifyResult.stats?.duration_seconds != null ? `${qualifyResult.stats.duration_seconds}s` : undefined },
              ].filter((r) => r.value != null).map(({ label, value, color }) => (
                <View key={label} style={s.resultRow}>
                  <Text style={s.resultLabel}>{label}</Text>
                  <Text style={[s.resultValue, color && { color }]}>{value}</Text>
                </View>
              ))}
            </View>
          )}
        </ScrollView>
      )}

      {/* ══════════════ AI CHAT TAB ══════════════ */}
      {activeTab === 'chat' && (
        <KeyboardAvoidingView
          style={{ flex: 1 }}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          keyboardVerticalOffset={120}
        >
          <FlatList
            ref={chatScrollRef}
            data={chatMessages}
            keyExtractor={(_, i) => String(i)}
            contentContainerStyle={s.chatList}
            onContentSizeChange={() => chatScrollRef.current?.scrollToEnd({ animated: true })}
            renderItem={({ item }) => (
              <View style={[
                s.bubble,
                item.role === 'user' ? s.bubbleUser : s.bubbleAI,
                item.error && { backgroundColor: `${COLORS.red}18` },
              ]}>
                {item.role === 'assistant' && (
                  <View style={s.aiAvatar}>
                    <Ionicons name="flash" size={10} color="#fff" />
                  </View>
                )}
                <Text style={[
                  s.bubbleText,
                  item.role === 'user' ? s.bubbleTextUser : s.bubbleTextAI,
                  item.error && { color: COLORS.red },
                ]}>
                  {item.text}
                </Text>
              </View>
            )}
            ListFooterComponent={chatLoading ? (
              <View style={[s.bubble, s.bubbleAI]}>
                <ActivityIndicator size="small" color={COLORS.primary} />
              </View>
            ) : null}
          />
          <View style={[s.chatInputRow, { backgroundColor: theme.card, borderTopColor: theme.cardBorder }]}>
            <TextInput
              style={[s.chatInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
              value={chatInput}
              onChangeText={setChatInput}
              placeholder="Ask about your leads, pipeline…"
              placeholderTextColor={theme.textMuted}
              multiline
              maxLength={500}
              onSubmitEditing={handleSendChat}
            />
            <TouchableOpacity
              style={[s.sendBtn, (!chatInput.trim() || chatLoading) && { opacity: 0.4 }]}
              onPress={handleSendChat}
              disabled={!chatInput.trim() || chatLoading}
            >
              <Ionicons name="send" size={18} color="#fff" />
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      )}

      {/* ══════════════ LOG TAB ══════════════ */}
      {activeTab === 'log' && (
        <ScrollView contentContainerStyle={s.scroll}>
          <View style={s.card}>
            <View style={s.sectionHeader}>
              <Text style={s.cardTitle}>Activity Log</Text>
              <TouchableOpacity onPress={fetchActivityLog}>
                <Ionicons name="refresh" size={18} color={COLORS.primary} />
              </TouchableOpacity>
            </View>
            {logLoading ? (
              <ActivityIndicator color={COLORS.primary} style={{ marginTop: 20 }} />
            ) : activityLog.length === 0 ? (
              <Text style={s.emptyTxt}>No activity yet.</Text>
            ) : (
              activityLog.slice(0, 50).map((entry, i) => {
                const isError  = entry.level === 'error' || entry.status === 'error';
                const mainText = entry.event || entry.message || (typeof entry === 'string' ? entry : null);
                const subText  = entry.details || entry.description || null;
                return (
                  <View key={i} style={s.logRow}>
                    <View style={[s.logDot, { backgroundColor: isError ? COLORS.red : COLORS.green }]} />
                    <View style={{ flex: 1 }}>
                      {mainText
                        ? <Text style={s.logMsg} numberOfLines={2}>{mainText}</Text>
                        : <Text style={[s.logMsg, { color: COLORS.red }]}>Malformed log entry</Text>
                      }
                      {subText && (
                        <Text style={[s.logTime, { color: theme.textSecondary, marginTop: 1 }]} numberOfLines={1}>{subText}</Text>
                      )}
                      {entry.timestamp && (
                        <Text style={s.logTime}>{new Date(entry.timestamp).toLocaleTimeString()}</Text>
                      )}
                    </View>
                  </View>
                );
              })
            )}
          </View>
        </ScrollView>
      )}

      {/* ══════════════ ML DASHBOARD TAB (manager + admin) ══════════════ */}
      {activeTab === 'dashboard' && isManager && (
        <ScrollView contentContainerStyle={s.scroll}>
          <View style={s.card}>
            <View style={s.sectionHeader}>
              <Text style={s.cardTitle}>ML Performance</Text>
              <TouchableOpacity onPress={fetchDashboard} disabled={loadingDashboard}>
                <Ionicons name="refresh" size={18} color={COLORS.primary} />
              </TouchableOpacity>
            </View>

            {loadingDashboard ? (
              <ActivityIndicator color={COLORS.primary} style={{ marginTop: 12 }} />
            ) : !dashboardData ? (
              <>
                <Text style={s.cardDesc}>Load current model metrics and dataset health.</Text>
                <TouchableOpacity style={s.trainBtn} onPress={fetchDashboard}>
                  <Ionicons name="cloud-download-outline" size={18} color={COLORS.primary} />
                  <Text style={[s.trainBtnText, { color: COLORS.primary }]}>Load Dashboard</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                  {[
                    { label: 'AUC',       val: dashboardData.current_model?.auc,       color: COLORS.green },
                    { label: 'Accuracy',  val: dashboardData.current_model?.accuracy,  color: COLORS.cyan },
                    { label: 'Precision', val: dashboardData.current_model?.precision, color: COLORS.amber },
                    { label: 'Recall',    val: dashboardData.current_model?.recall,    color: COLORS.purple },
                    { label: 'F1',        val: dashboardData.current_model?.f1,        color: COLORS.primary },
                  ].map(({ label, val, color }) => (
                    <View key={label} style={{ backgroundColor: color + '18', borderRadius: 10, paddingHorizontal: 11, paddingVertical: 7, minWidth: '30%' }}>
                      <Text style={{ color, fontWeight: '800', fontSize: 14 }}>
                        {val != null ? `${(val * 100).toFixed(1)}%` : '—'}
                      </Text>
                      <Text style={{ color: theme.textMuted, fontSize: 10, fontWeight: '600', marginTop: 1 }}>{label}</Text>
                    </View>
                  ))}
                </View>

                {dashboardData.current_model?.trained_at && (
                  <Text style={[s.cardDesc, { marginBottom: 12 }]}>
                    Trained {new Date(dashboardData.current_model.trained_at).toLocaleString()}
                    {dashboardData.current_model.n_samples != null ? ` · ${dashboardData.current_model.n_samples.toLocaleString()} samples` : ''}
                  </Text>
                )}

                {dashboardData.dataset_health && (
                  <View style={{ marginBottom: 4 }}>
                    <Text style={[s.cardTitle, { fontSize: 12 }]}>Dataset Health</Text>
                    <View style={s.sectionHeader}>
                      <Text style={s.cardDesc}>DB labeled</Text>
                      <Text style={s.cardDesc}>{dashboardData.dataset_health.db?.total_labeled ?? '—'}</Text>
                    </View>
                    <View style={s.sectionHeader}>
                      <Text style={s.cardDesc}>JSONL labeled</Text>
                      <Text style={s.cardDesc}>{dashboardData.dataset_health.jsonl?.labeled ?? '—'}</Text>
                    </View>
                  </View>
                )}

                {dashboardData.ml_llm_agreement && (
                  <View>
                    <Text style={[s.cardTitle, { fontSize: 12 }]}>ML / LLM Agreement</Text>
                    <Text style={s.cardDesc}>
                      {dashboardData.ml_llm_agreement.agreement_rate != null
                        ? `${(dashboardData.ml_llm_agreement.agreement_rate * 100).toFixed(1)}%`
                        : '—'}
                      {' '}({dashboardData.ml_llm_agreement.agreements ?? 0} / {dashboardData.ml_llm_agreement.total_comparisons ?? 0} comparisons)
                    </Text>
                  </View>
                )}
              </>
            )}
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const styles = (theme) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  scroll: { padding: 14, paddingBottom: 100 },

  // Main tabs — pill style
  tabs:          { flexDirection: 'row', backgroundColor: theme.card, borderBottomWidth: 1, borderBottomColor: theme.cardBorder, paddingHorizontal: 8, paddingVertical: 8, gap: 4 },
  tab:           { flex: 1, paddingVertical: 8, alignItems: 'center', gap: 3, borderRadius: 10 },
  tabActive:     { backgroundColor: COLORS.primary },
  tabText:       { fontSize: 10, fontWeight: '600', color: theme.textMuted },
  tabTextActive: { color: '#fff', fontWeight: '700' },

  // Status
  statusCard: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: `${COLORS.green}12`, borderRadius: 14, padding: 13, marginBottom: 12, borderWidth: 1, borderColor: `${COLORS.green}25` },
  statusDot:  { width: 10, height: 10, borderRadius: 5 },
  statusText: { fontSize: 13, fontWeight: '600', color: COLORS.green, flex: 1 },
  statusSub:  { fontSize: 11, color: theme.textMuted },

  // Cards
  card:          { backgroundColor: theme.card, borderRadius: 18, padding: 16, marginBottom: 14, borderWidth: 1, borderColor: theme.cardBorder, shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  cardTitle:     { fontSize: 13, fontWeight: '700', color: theme.text, marginBottom: 10 },
  cardDesc:      { fontSize: 12, color: theme.textMuted, marginBottom: 12, lineHeight: 18 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  sectionHeading:{ fontSize: 14, fontWeight: '800', color: theme.text, marginBottom: 4 },
  modeDesc:      { fontSize: 12, color: theme.textMuted, lineHeight: 17, marginBottom: 4 },

  insightText:   { fontSize: 13, color: theme.textSecondary, lineHeight: 20, marginBottom: 10 },
  recRow:        { flexDirection: 'row', gap: 6, marginBottom: 6, alignItems: 'flex-start' },
  recText:       { flex: 1, fontSize: 12, color: theme.textSecondary, lineHeight: 17 },

  // Collect mode selector
  modeBar:       { flexDirection: 'row', gap: 6, marginBottom: 12 },
  modeBtn:       { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 10, borderRadius: 14, backgroundColor: theme.card, borderWidth: 1, borderColor: theme.cardBorder },
  modeBtnActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary, shadowColor: COLORS.primary, shadowOpacity: 0.3, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  modeTxt:       { fontSize: 11, fontWeight: '700', color: theme.textMuted },
  modeTxtActive: { color: '#fff' },

  // Chips / inputs
  chipRow:      { flexDirection: 'row', flexWrap: 'wrap', marginBottom: 4 },
  selectedHint: { fontSize: 11, marginBottom: 6, marginTop: 2 },

  selectedPill: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: 20, borderWidth: 1.5, marginRight: 6, marginBottom: 6,
  },
  selectedPillTxt: { fontSize: 12, fontWeight: '700' },

  searchBox: {
    flexDirection: 'row', alignItems: 'center',
    borderWidth: 1, borderRadius: 12,
    paddingHorizontal: 10, paddingVertical: 8,
    marginBottom: 10, marginTop: 4,
  },

  countryChip: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: 20, borderWidth: 1,
    marginRight: 6, marginBottom: 6,
  },
  countryChipTxt: { fontSize: 12, fontWeight: '500' },

  emptyHint: { fontSize: 12, marginBottom: 8, fontStyle: 'italic' },

  suggestBox: {
    borderWidth: 1, borderRadius: 12,
    marginTop: -4, marginBottom: 8,
    overflow: 'hidden',
    shadowColor: '#000', shadowOpacity: 0.08,
    shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 4,
  },
  suggestItem: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 12, paddingVertical: 10,
    borderBottomWidth: 1,
  },
  suggestCode: { fontSize: 11, fontWeight: '800', width: 30 },
  suggestName: { fontSize: 13, fontWeight: '500' },

  queryInput: { borderWidth: 1, borderRadius: 14, padding: 13, fontSize: 14, minHeight: 64, textAlignVertical: 'top', marginBottom: 4 },
  fieldInput: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 13, paddingVertical: 11, fontSize: 14, marginBottom: 4 },

  // Platform chips (with icons)
  platformChip:       { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 13, paddingVertical: 8, borderRadius: 20, borderWidth: 1, borderColor: theme.inputBorder, backgroundColor: theme.input, margin: 3 },
  platformChipActive: { backgroundColor: COLORS.cyan, borderColor: COLORS.cyan },
  platformChipTxt:    { fontSize: 12, fontWeight: '600', color: theme.textMuted },

  // Progress
  progressRow:  { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  progressTxt:  { fontSize: 13, color: theme.textSecondary, fontWeight: '500', flex: 1 },
  progressBg:   { height: 9, backgroundColor: theme.input, borderRadius: 5, overflow: 'hidden', marginBottom: 6 },
  progressFill: { height: '100%', backgroundColor: COLORS.primary, borderRadius: 5 },
  progressSub:  { fontSize: 11, color: theme.textMuted, marginTop: 2 },

  // Buttons
  startBtn:     { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 16, height: 54, marginBottom: 14, shadowOpacity: 0.35, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 5 },
  startBtnText: { color: '#fff', fontSize: 15, fontWeight: '800' },
  trainBtn:     { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 11, borderRadius: 12, backgroundColor: `${COLORS.purple}15`, alignSelf: 'flex-start', borderWidth: 1, borderColor: `${COLORS.purple}25` },
  trainBtnText: { fontSize: 13, fontWeight: '700' },

  // Qualify tab
  emptyBox:        { alignItems: 'center', paddingVertical: 28, gap: 10 },
  emptyTxt:        { color: theme.textMuted, textAlign: 'center', paddingVertical: 20, fontSize: 13, fontWeight: '500' },
  pendingRow:      { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  pendingAvatar:   { width: 36, height: 36, borderRadius: 18, backgroundColor: `${COLORS.primary}15`, alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: `${COLORS.primary}25` },
  pendingAvatarTxt:{ fontSize: 14, fontWeight: '800', color: COLORS.primary },
  pendingName:     { fontSize: 13, fontWeight: '600', color: theme.text },
  pendingCompany:  { fontSize: 11, color: theme.textMuted, marginTop: 2 },
  moreText:        { fontSize: 12, color: theme.textMuted, marginTop: 10, textAlign: 'center', fontWeight: '500' },
  resultRow:       { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  resultLabel:     { fontSize: 13, color: theme.textMuted },
  resultValue:     { fontSize: 13, fontWeight: '700', color: theme.text },

  // Chat
  chatList:       { padding: 14, paddingBottom: 100, gap: 10 },
  bubble:         { maxWidth: '84%', borderRadius: 18, padding: 13 },
  bubbleUser:     { alignSelf: 'flex-end', backgroundColor: COLORS.primary, borderBottomRightRadius: 5 },
  bubbleAI:       { alignSelf: 'flex-start', backgroundColor: theme.card, borderWidth: 1, borderColor: theme.cardBorder, borderBottomLeftRadius: 5, flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  aiAvatar:       { width: 22, height: 22, borderRadius: 7, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center', marginTop: 1 },
  bubbleText:     { fontSize: 14, lineHeight: 21 },
  bubbleTextUser: { color: '#fff' },
  bubbleTextAI:   { color: theme.text, flex: 1 },
  chatInputRow:   { flexDirection: 'row', gap: 8, padding: 12, borderTopWidth: 1 },
  chatInput:      { flex: 1, borderRadius: 14, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 10, fontSize: 14, maxHeight: 80 },
  sendBtn:        { width: 46, height: 46, borderRadius: 14, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center', shadowColor: COLORS.primary, shadowOpacity: 0.3, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 3 },

  // Log
  logRow:  { flexDirection: 'row', gap: 10, paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  logDot:  { width: 8, height: 8, borderRadius: 4, marginTop: 5 },
  logMsg:  { fontSize: 13, color: theme.textSecondary, lineHeight: 19 },
  logTime: { fontSize: 10, color: theme.textMuted, marginTop: 3 },
});
