import React, { useContext, useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Layout, Button, Dropdown, Avatar, Space, Tooltip, Popover, Badge, Modal } from 'antd';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  LogoutOutlined,
  UserOutlined,
  BellOutlined,
  SunOutlined,
  MoonOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  CheckOutlined,
  SearchOutlined,
  HomeOutlined,
  TeamOutlined,
  BarChartOutlined,
  RobotOutlined,
  DatabaseOutlined,
  SettingOutlined,
  FireOutlined,
  BulbOutlined,
  MinusCircleOutlined,
  PlusCircleOutlined,
  ThunderboltOutlined,
  LineChartOutlined,
  ToolOutlined,
  ApiOutlined,
  HistoryOutlined,
  FunnelPlotOutlined,
  ExportOutlined,
  TagOutlined,
  SafetyOutlined,
  AimOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { ThemeContext } from '../context/ThemeContext';
import { useNotifications } from '../hooks/useNotifications';

/* ── Search catalogue ────────────────────────────────────────── */
// group colours
const GROUP_COLOR = {
  Pages:      '#6366f1',
  'AI Engine':'#8b5cf6',
  Leads:      '#f59e0b',
  Settings:   '#0ea5e9',
  Admin:      '#ef4444',
  Actions:    '#22c55e',
};

const SEARCH_ITEMS = [
  // ── Pages ──────────────────────────────────────────────────────────
  { id:'dashboard',      group:'Pages',     label:'Dashboard',             description:'KPIs, recent activity and pipeline overview',          Icon:HomeOutlined,         path:'/',           keywords:['home','overview','stats','kpi','summary','pipeline'] },
  { id:'leads',          group:'Pages',     label:'All Leads',             description:'View, filter and manage every lead',                   Icon:TeamOutlined,         path:'/leads',      keywords:['contacts','prospects','crm','list','leads'] },
  { id:'analytics',      group:'Pages',     label:'Analytics',             description:'Charts, conversion rate, activity timeline',           Icon:BarChartOutlined,     path:'/analytics',  keywords:['charts','reports','metrics','data','graphs','conversion','funnel'] },
  { id:'ai-engine',      group:'Pages',     label:'AI Engine',             description:'Collect leads, run AI scoring, train the ML model',    Icon:RobotOutlined,        path:'/ai-engine',  keywords:['collect','score','ml','gemini','ai','machine learning','qualify'], noSubAdmin:true },
  { id:'sources',        group:'Pages',     label:'Data Sources',          description:'Configure collection sources and integrations',        Icon:DatabaseOutlined,     path:'/sources',    keywords:['sources','integration','linkedin','github','google','apollo'], adminOnly:true },
  { id:'admin',          group:'Pages',     label:'Admin Panel',           description:'Manage users, roles and system settings',              Icon:SettingOutlined,      path:'/admin',      keywords:['users','permissions','roles','system','admin','management'], adminOnly:true },
  { id:'settings',       group:'Pages',     label:'Settings',              description:'Account, profile, API keys and notifications',         Icon:SettingOutlined,      path:'/settings',   keywords:['profile','password','account','preferences','configuration'] },

  // ── AI Engine tabs ─────────────────────────────────────────────────
  { id:'ai-chat',        group:'AI Engine', label:'AI Copilot Chat',       description:'Talk to the AI to collect leads by query',            Icon:RobotOutlined,        path:'/ai-engine',  tab:'chat',      keywords:['chat','ask','collect','query','gemini','ai copilot','conversation'], noSubAdmin:true },
  { id:'ai-collect',     group:'AI Engine', label:'Collect Leads (AI)',    description:'Start an AI-powered lead collection run',             Icon:ThunderboltOutlined,  path:'/ai-engine',  tab:'chat',      keywords:['collect','gather','find leads','run','start','harvest'], noSubAdmin:true },
  { id:'ai-summary',     group:'AI Engine', label:'Pipeline Summary',      description:'View last collection run statistics and results',     Icon:LineChartOutlined,    path:'/ai-engine',  tab:'summary',   keywords:['summary','results','pipeline','last run','collection stats'], noSubAdmin:true },
  { id:'ai-dashboard',   group:'AI Engine', label:'ML Dashboard',          description:'Model accuracy, AUC, precision and recall metrics',   Icon:BarChartOutlined,     path:'/ai-engine',  tab:'dashboard', keywords:['ml','model','accuracy','auc','metrics','performance','machine learning'], noSubAdmin:true },
  { id:'ai-retrain',     group:'AI Engine', label:'Retrain ML Model',      description:'Train the model on labelled lead data',               Icon:ToolOutlined,         path:'/ai-engine',  tab:'retrain',   keywords:['train','retrain','model','fit','improve','xgboost','ml training'], noSubAdmin:true },
  { id:'ai-explain',     group:'AI Engine', label:'Explain Prediction',    description:'See why a lead received its AI score',                Icon:AimOutlined,          path:'/ai-engine',  tab:'explain',   keywords:['explain','explainer','shap','why','prediction','score reason','interpretation'], noSubAdmin:true },
  { id:'ai-interest',    group:'AI Engine', label:'Interest-Based Collect',description:'Collect leads by industry or interest category',      Icon:TagOutlined,          path:'/ai-engine',  tab:'interest',  keywords:['interest','industry','category','niche','topic','sector'], noSubAdmin:true },
  { id:'ai-approvals',   group:'AI Engine', label:'Label Approvals',       description:'Review and approve outcome labels for ML training',   Icon:SafetyOutlined,       path:'/ai-engine',  tab:'approvals', keywords:['approvals','labels','review','approve','reject','training data'], adminOnly:true },

  // ── Lead filters ───────────────────────────────────────────────────
  { id:'hot-leads',      group:'Leads',     label:'Hot Leads',             description:'Leads scored Hot — highest priority',                 Icon:FireOutlined,         path:'/leads',      interest:'Hot',       keywords:['hot','fire','priority','best','top','qualified','high score'] },
  { id:'warm-leads',     group:'Leads',     label:'Warm Leads',            description:'Leads scored Warm — medium potential',                Icon:BulbOutlined,         path:'/leads',      interest:'Warm',      keywords:['warm','medium','potential','moderate'] },
  { id:'cold-leads',     group:'Leads',     label:'Cold Leads',            description:'Leads scored Cold — low priority',                    Icon:MinusCircleOutlined,  path:'/leads',      interest:'Cold',      keywords:['cold','low','unqualified','weak'] },
  { id:'status-new',     group:'Leads',     label:'New Leads',             description:'Leads with New status — not yet contacted',           Icon:PlusCircleOutlined,   path:'/leads',      status:'New',         keywords:['new','fresh','untouched','recent','status new'] },
  { id:'status-contact', group:'Leads',     label:'Contacted Leads',       description:'Leads that have been reached out to',                 Icon:TeamOutlined,         path:'/leads',      status:'Contacted',   keywords:['contacted','reached','outreach','status contacted'] },
  { id:'status-qualif',  group:'Leads',     label:'Qualified Leads',       description:'Leads that passed qualification criteria',            Icon:CheckCircleOutlined,  path:'/leads',      status:'Qualified',   keywords:['qualified','passed','approved','status qualified'] },
  { id:'status-convert', group:'Leads',     label:'Converted Leads',       description:'Successfully converted — deals won',                  Icon:CheckCircleOutlined,  path:'/leads',      status:'Converted',   keywords:['converted','won','closed','success','deal'] },
  { id:'status-reject',  group:'Leads',     label:'Rejected Leads',        description:'Leads that were disqualified',                        Icon:CloseCircleOutlined,  path:'/leads',      status:'Rejected',    keywords:['rejected','disqualified','lost','declined','not a fit'] },

  // ── Settings tabs ──────────────────────────────────────────────────
  { id:'set-profile',    group:'Settings',  label:'Profile Settings',      description:'Update name, email, avatar and password',             Icon:UserOutlined,         path:'/settings',   tab:'profile',        keywords:['profile','name','avatar','photo','password','change password','account'] },
  { id:'set-apikeys',    group:'Settings',  label:'API Keys',              description:'Generate and manage your API access tokens',          Icon:ApiOutlined,          path:'/settings',   tab:'api-keys',       keywords:['api key','token','access key','api','key','generate','secret'] },
  { id:'set-notif',      group:'Settings',  label:'Notification Settings', description:'Configure email and push notification preferences',   Icon:BellOutlined,         path:'/settings',   tab:'notifications',  keywords:['notifications','alerts','email alerts','push','notify','preferences'] },
  { id:'set-database',   group:'Settings',  label:'Database Settings',     description:'Supabase connection and database configuration',      Icon:DatabaseOutlined,     path:'/settings',   tab:'database',       keywords:['database','supabase','connection','db','storage','backup'], adminOnly:true },

  // ── Quick actions ──────────────────────────────────────────────────
  { id:'act-export',     group:'Actions',   label:'Export Leads to CSV',   description:'Download all leads as a professional Excel-ready CSV', Icon:ExportOutlined,       path:'/leads',      action:'export',      keywords:['export','download','csv','excel','spreadsheet','file'] },
  { id:'act-add-lead',   group:'Actions',   label:'Add New Lead',          description:'Manually create a new lead in the system',            Icon:PlusCircleOutlined,   path:'/leads',      action:'add',         keywords:['add','create','new lead','manual','insert'] },
  { id:'act-qualify',    group:'Actions',   label:'Qualify All Leads',     description:'Run AI scoring on all unscored leads',                Icon:AimOutlined,          path:'/ai-engine',  tab:'chat',           keywords:['qualify','score','ai score','batch','qualify all','run ai'], noSubAdmin:true },
  { id:'act-sync',       group:'Actions',   label:'Sync to Mobile',        description:'Push latest leads to the mobile app via Supabase',    Icon:ThunderboltOutlined,  path:'/ai-engine',  tab:'summary',        keywords:['sync','mobile','supabase','push','real-time','update'], noSubAdmin:true },

  // ── Admin-only ─────────────────────────────────────────────────────
  { id:'adm-users',      group:'Admin',     label:'User Management',       description:'Activate, deactivate and manage user accounts',       Icon:UserOutlined,         path:'/admin',      keywords:['users','accounts','activate','deactivate','manage','roles'], adminOnly:true },
  { id:'adm-audit',      group:'Admin',     label:'Activity Audit Log',    description:'System-wide activity log and event history',          Icon:HistoryOutlined,      path:'/admin',      keywords:['audit','log','history','activity','events','tracking'], adminOnly:true },
  { id:'adm-sources',    group:'Admin',     label:'Manage Data Sources',   description:'Enable, configure and test collection integrations',  Icon:FunnelPlotOutlined,   path:'/sources',    keywords:['sources','linkedin','apollo','github','hunter','configure','enable'], adminOnly:true },
];

/* ── Edit-distance (Levenshtein) ─────────────────────────────── */
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

// Similarity 0–1 between two strings (Levenshtein-based)
function strSim(a, b) {
  const ml = Math.max(a.length, b.length);
  return ml === 0 ? 1 : 1 - levenshtein(a, b) / ml;
}

/* ── Fuzzy lead scorer (used on local index) ─────────────────── */
function scoreLead(lead, rawQuery) {
  const q = rawQuery.toLowerCase().trim();
  if (q.length < 2) return 0;
  const fields = [lead.name, lead.email, lead.company].map(f => (f || '').toLowerCase());
  let best = 0;
  const qWords = q.split(/\s+/).filter(w => w.length >= 2);

  for (const f of fields) {
    if (!f) continue;
    if (f === q)         { return 100; }
    if (f.includes(q))  { best = Math.max(best, 85); continue; }
    if (qWords.length > 1 && qWords.every(w => f.includes(w))) { best = Math.max(best, 78); continue; }

    // Full-string Levenshtein (compare against prefix of same length)
    const clip = f.slice(0, Math.min(f.length, q.length + 5));
    const s1 = strSim(q, clip);
    if (s1 > 0.55) best = Math.max(best, Math.round(s1 * 76));

    // Word-level: each query word vs each field word
    const fWords = f.split(/[\s,@._\-+]+/).filter(w => w.length >= 2);
    for (const qw of qWords) {
      for (const fw of fWords) {
        const s = strSim(qw, fw);
        if (s > 0.62) best = Math.max(best, Math.round(s * 72));
      }
    }
    // Also entire query vs each field word (catches single-name searches)
    for (const fw of fWords) {
      if (fw.length < 2) continue;
      const s = strSim(q, fw);
      if (s > 0.62) best = Math.max(best, Math.round(s * 70));
    }
  }
  return best;
}

/* ── Fuzzy scoring (navigation items) ───────────────────────── */
function scoreMatch(item, q) {
  if (!q) return 1;
  const label = item.label.toLowerCase();
  const desc  = item.description.toLowerCase();
  const kws   = item.keywords || [];

  if (label === q)               return 100;
  if (label.startsWith(q))       return 88;
  if (kws.includes(q))           return 82;

  const qWords = q.split(/\s+/).filter(w => w.length > 1);
  if (qWords.length > 1 && qWords.every(w => label.includes(w) || kws.some(k => k.includes(w)))) return 76;

  if (label.includes(q))                              return 70;
  if (kws.some(k => k === q))                         return 65;
  if (label.split(' ').some(w => w.startsWith(q)))   return 55;
  if (kws.some(k => k.startsWith(q)))                return 50;
  if (desc.includes(q))                               return 42;
  if (kws.some(k => k.includes(q)))                  return 35;
  if (qWords.some(w => w.length > 2 && (label.includes(w) || kws.some(k => k.includes(w))))) return 25;

  // Levenshtein fallback — catches typos like "dashbord" → "Dashboard"
  const labelWords = label.split(/\s+/);
  const kwWords    = kws.flatMap(k => k.split(/\s+/));
  for (const qw of [...qWords, q]) {
    if (qw.length < 3) continue;
    for (const lw of [...labelWords, ...kwWords]) {
      if (lw.length < 3) continue;
      if (strSim(qw, lw) > 0.68) return 22;
    }
  }
  return 0;
}

const RECENT_KEY = 'orionlead_search_recent';
function getRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); }
  catch { return []; }
}
function saveRecent(id) {
  const prev = getRecent().filter(x => x !== id);
  localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...prev].slice(0, 5)));
}

/* ── SmartSearch ─────────────────────────────────────────────── */
const SmartSearch = ({ isDark, userRole }) => {
  const [open, setOpen]           = useState(false);
  const [query, setQuery]         = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const navigate  = useNavigate();
  const inputRef  = useRef(null);
  const listRef   = useRef(null);
  const isAdmin   = userRole === 'admin';
  const isMgr     = userRole === 'manager';

  // Ctrl+K / Cmd+K shortcut
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); setOpen(o => !o); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 80);
      setQuery('');
      setActiveIdx(0);
    }
  }, [open]);

  const isSubAdmin = userRole === 'sub_admin';

  const baseItems = useMemo(() =>
    SEARCH_ITEMS.filter(i => {
      if (i.adminOnly && !isAdmin) return false;
      if (i.managerOk && !isAdmin && !isMgr) return false;
      if (i.noSubAdmin && isSubAdmin) return false;
      return true;
    }),
    [isAdmin, isMgr, isSubAdmin]
  );

  // ── Leads index (loaded once, fuzzy-searched client-side) ──────────────
  const leadsIndexRef  = useRef([]);
  const leadsLoadedRef = useRef(false);
  const [leadResults, setLeadResults] = useState([]);

  useEffect(() => {
    if (!open || leadsLoadedRef.current) return;
    const token = localStorage.getItem('authToken');
    if (!token) return;
    const base = process.env.REACT_APP_API_URL || 'http://localhost:5000';
    fetch(`${base}/api/v1/leads/?per_page=300`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        leadsIndexRef.current = (data.leads || []).map(l => ({
          id:      l.id,
          name:    (l.name    || '').trim(),
          email:   (l.email   || '').trim(),
          company: (l.company || '').trim(),
          score:   Math.round(l.qualification_score || 0),
        }));
      })
      .catch(() => {})
      .finally(() => {
        leadsLoadedRef.current = true; // never retry — avoids auth-error loops
      });
  }, [open]);

  // Debounced fuzzy matching against local index
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setLeadResults([]); return; }
    const timer = setTimeout(() => {
      const hits = leadsIndexRef.current
        .map(l => ({ l, s: scoreLead(l, q) }))
        .filter(x => x.s >= 30)
        .sort((a, b) => b.s - a.s || b.l.score - a.l.score)
        .slice(0, 5)
        .map(x => x.l);
      setLeadResults(hits);
    }, 90);
    return () => clearTimeout(timer);
  }, [query]);

  // ── Navigation results (instant, memoized) ─────────────────────────────
  const navResults = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      const recent = getRecent();
      const recentItems = recent
        .map(id => baseItems.find(i => i.id === id))
        .filter(Boolean)
        .map(i => ({ ...i, _recent: true }));
      const suggestions = baseItems
        .filter(i => i.group === 'Pages' && !recent.includes(i.id))
        .slice(0, 6);
      return [...recentItems, ...suggestions];
    }
    return baseItems
      .map(i => ({ item: i, score: scoreMatch(i, q) }))
      .filter(x => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .map(x => x.item);
  }, [query, baseItems]);

  // ── Combined results: fuzzy leads first, then nav items ────────────────
  const results = useMemo(() => {
    const q = query.trim();
    if (!q) return navResults;

    const leadItems = leadResults.map(l => ({
      id:          `lead_${l.id}`,
      group:       'Leads',
      label:       l.name || l.email || 'Unknown Lead',
      description: [l.company, l.score >= 1 ? `Score ${l.score}` : null].filter(Boolean).join(' · '),
      Icon:        TeamOutlined,
      path:        '/leads',
      leadSearch:  l.name || l.email || '',
      _leadScore:  l.score,
      keywords:    [],
    }));

    // "Search all" fallback always at bottom of Leads group
    const searchAll = {
      id:          '__lead-search__',
      group:       'Leads',
      label:       `Search all leads for "${q}"`,
      description: 'Browse every matching lead on the Leads page',
      Icon:        SearchOutlined,
      path:        '/leads',
      leadSearch:  q,
      keywords:    [],
    };

    return [...leadItems, searchAll, ...navResults];
  }, [query, navResults, leadResults]);

  // Keep active item visible when navigating with keys
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${activeIdx}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIdx]);

  const handleSelect = useCallback((item) => {
    setOpen(false);
    if (item.id !== '__lead-search__') saveRecent(item.id);
    const params = new URLSearchParams();
    if (item.tab)        params.set('tab',      item.tab);
    if (item.interest)   params.set('interest', item.interest);
    if (item.status)     params.set('status',   item.status);
    if (item.action)     params.set('action',   item.action);
    if (item.leadSearch) params.set('q',        item.leadSearch);
    const qs = params.toString();
    navigate(item.path + (qs ? `?${qs}` : ''));
  }, [navigate]);

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter' && results[activeIdx]) handleSelect(results[activeIdx]);
    else if (e.key === 'Escape') setOpen(false);
  };

  const modalBg      = isDark ? '#0c1220'  : '#ffffff';
  const inputBg      = isDark ? '#141c2e'  : '#f8fafc';
  const borderCol    = isDark ? 'rgba(99,102,241,0.22)' : 'rgba(99,102,241,0.18)';
  const dividerCol   = isDark ? 'rgba(99,102,241,0.10)' : 'rgba(99,102,241,0.08)';
  const textPrimary  = isDark ? '#e2e8f0'  : '#0f172a';
  const textSec      = isDark ? '#94a3b8'  : '#64748b';
  const activeBg     = isDark ? 'rgba(99,102,241,0.14)' : 'rgba(99,102,241,0.08)';
  const iconActiveBg = isDark ? 'rgba(99,102,241,0.22)' : 'rgba(99,102,241,0.14)';
  const iconIdleBg   = isDark ? 'rgba(255,255,255,0.05)': 'rgba(0,0,0,0.04)';
  const kbdBg        = isDark ? 'rgba(255,255,255,0.06)': 'rgba(0,0,0,0.05)';

  // Group consecutive items
  const leadScoreColor = (s) => s >= 80 ? '#22c55e' : s >= 50 ? '#f59e0b' : '#94a3b8';

  const renderItems = () => {
    if (results.length === 0) return (
      <div style={{ padding: '36px 24px', textAlign: 'center', color: textSec, fontSize: 13 }}>
        No results for <strong style={{ color: textPrimary }}>"{query}"</strong>
      </div>
    );

    const q = query.trim().toLowerCase();
    const showGroups = !!q;
    let lastGroup = null;
    let flatIdx = 0;

    return results.map((item) => {
      const idx = flatIdx++;
      const isActive   = idx === activeIdx;
      const grpColor   = GROUP_COLOR[item.group] || '#6366f1';
      const groupChanged = item.group !== lastGroup;
      const showHeader = showGroups && groupChanged && item.id !== '__lead-search__';
      lastGroup = item.group;

      const isLeadItem   = item._leadScore !== undefined;
      const isSearchAll  = item.id === '__lead-search__';
      const scoreCol     = isLeadItem ? leadScoreColor(item._leadScore) : grpColor;

      return (
        <React.Fragment key={item.id}>
          {showHeader && (
            <div style={{
              padding: '6px 18px 3px',
              fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.8,
              color: grpColor, opacity: 0.8,
              borderTop: `1px solid ${dividerCol}`,
            }}>
              {item.group}
            </div>
          )}
          {!showGroups && item._recent && idx === 0 && (
            <div style={{ padding: '6px 18px 3px', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.8, color: textSec }}>
              Recent
            </div>
          )}
          {!showGroups && !item._recent && (results.find(r => r._recent) ? results.filter(r => r._recent).length : 0) === idx && (
            <div style={{ padding: '6px 18px 3px', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.8, color: textSec, borderTop: `1px solid ${dividerCol}` }}>
              Suggestions
            </div>
          )}
          <div
            data-idx={idx}
            onClick={() => handleSelect(item)}
            onMouseEnter={() => setActiveIdx(idx)}
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '9px 18px', cursor: 'pointer',
              background: isActive ? activeBg : 'transparent',
              opacity: isSearchAll ? 0.72 : 1,
              transition: 'background 0.08s',
            }}
          >
            <div style={{
              width: 32, height: 32, borderRadius: 8, flexShrink: 0,
              background: isLeadItem
                ? `${leadScoreColor(item._leadScore)}18`
                : isActive ? iconActiveBg : iconIdleBg,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'background 0.08s',
            }}>
              <item.Icon style={{ fontSize: 14, color: isActive ? scoreCol : isLeadItem ? leadScoreColor(item._leadScore) : textSec }} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: textPrimary, fontSize: 13, fontWeight: isActive ? 600 : isLeadItem ? 500 : 400, lineHeight: 1.3 }}>
                {item.label}
              </div>
              <div style={{ color: textSec, fontSize: 11, marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.description}
              </div>
            </div>
            {/* Score badge for fuzzy-matched leads */}
            {isLeadItem && item._leadScore >= 1 && (
              <span style={{
                fontSize: 11, fontWeight: 700,
                color: leadScoreColor(item._leadScore),
                background: `${leadScoreColor(item._leadScore)}18`,
                border: `1px solid ${leadScoreColor(item._leadScore)}40`,
                borderRadius: 6, padding: '2px 7px', flexShrink: 0,
              }}>
                {item._leadScore}
              </span>
            )}
            {item._recent && (
              <HistoryOutlined style={{ fontSize: 11, color: textSec, flexShrink: 0, opacity: 0.6 }} />
            )}
            {isActive && (
              <kbd style={{
                fontSize: 10, color: scoreCol,
                background: `${scoreCol}18`, border: `1px solid ${scoreCol}40`,
                borderRadius: 4, padding: '2px 6px', fontFamily: 'inherit', flexShrink: 0,
              }}>↵</kbd>
            )}
          </div>
        </React.Fragment>
      );
    });
  };

  return (
    <>
      <Tooltip title="Search (Ctrl+K)">
        <Button
          type="text"
          icon={<SearchOutlined />}
          onClick={() => setOpen(true)}
          style={{ color: isDark ? '#94a3b8' : '#64748b', width: 36, height: 36, fontSize: 16 }}
        />
      </Tooltip>

      <Modal
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        closable={false}
        width={580}
        centered
        styles={{
          content: {
            padding: 0,
            borderRadius: 16,
            background: modalBg,
            border: `1px solid ${borderCol}`,
            boxShadow: isDark
              ? '0 32px 96px rgba(0,0,0,0.7), 0 4px 24px rgba(99,102,241,0.18)'
              : '0 24px 80px rgba(0,0,0,0.14), 0 4px 24px rgba(99,102,241,0.12)',
            overflow: 'hidden',
          },
          mask: { backdropFilter: 'blur(6px)', background: 'rgba(0,0,0,0.45)' },
        }}
      >
        {/* Input row */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '14px 18px',
          background: inputBg,
          borderBottom: `1px solid ${dividerCol}`,
        }}>
          <SearchOutlined style={{ color: '#6366f1', fontSize: 18, flexShrink: 0 }} />
          <input
            ref={inputRef}
            value={query}
            onChange={e => { setQuery(e.target.value); setActiveIdx(0); }}
            onKeyDown={handleKeyDown}
            placeholder="Search pages, leads, AI features, settings…"
            style={{
              flex: 1, border: 'none', outline: 'none',
              background: 'transparent', color: textPrimary,
              fontSize: 15, fontFamily: 'inherit',
            }}
          />
          {query && (
            <button
              onClick={() => { setQuery(''); setActiveIdx(0); inputRef.current?.focus(); }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: textSec, fontSize: 16, lineHeight: 1, padding: 0 }}
            >×</button>
          )}
          <kbd style={{
            fontSize: 10, color: textSec, background: kbdBg,
            border: `1px solid ${dividerCol}`, borderRadius: 4, padding: '2px 6px', fontFamily: 'inherit', flexShrink: 0,
          }}>ESC</kbd>
        </div>

        {/* Results list */}
        <div ref={listRef} style={{ maxHeight: 400, overflowY: 'auto', padding: '4px 0' }}>
          {renderItems()}
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '7px 18px', borderTop: `1px solid ${dividerCol}`,
        }}>
          <div style={{ display: 'flex', gap: 14 }}>
            {[['↑↓', 'navigate'], ['↵', 'open'], ['ESC', 'close']].map(([key, label]) => (
              <span key={key} style={{ color: textSec, fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                <kbd style={{ fontSize: 10, background: kbdBg, border: `1px solid ${dividerCol}`, borderRadius: 3, padding: '1px 5px', fontFamily: 'inherit', color: textSec }}>{key}</kbd>
                {label}
              </span>
            ))}
          </div>
          <span style={{ color: textSec, fontSize: 10, opacity: 0.6 }}>
            {results.length} result{results.length !== 1 ? 's' : ''}
          </span>
        </div>
      </Modal>
    </>
  );
};

/* ── helpers ────────────────────────────────────────────────── */
function timeAgo(date) {
  if (!date) return null;
  const diff = Date.now() - new Date(date).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const TYPE_CFG = {
  success: { color: '#22c55e', bg: 'rgba(34,197,94,0.12)',   Icon: CheckCircleOutlined },
  warning: { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)',  Icon: ExclamationCircleOutlined },
  error:   { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',   Icon: CloseCircleOutlined },
  info:    { color: '#6366f1', bg: 'rgba(99,102,241,0.12)',  Icon: InfoCircleOutlined },
};

/* ── NotificationsPanel ─────────────────────────────────────── */
const NotificationsPanel = ({ notifications, readIds, markRead, markAllRead, isDark, lastFetch, onRefresh }) => {
  const panelBg     = isDark ? '#1e293b'  : '#ffffff';
  const headBg      = isDark ? '#111827'  : '#fafbff';
  const borderColor = isDark ? 'rgba(99,102,241,0.08)' : 'rgba(99,102,241,0.08)';
  const textHead    = isDark ? '#f1f5f9'  : '#0f172a';
  const textSub     = isDark ? '#94a3b8'  : '#64748b';
  const textMuted   = isDark ? '#64748b'  : '#94a3b8';
  const hoverBg     = isDark ? 'rgba(99,102,241,0.06)' : 'rgba(99,102,241,0.04)';
  const unreadBg    = isDark ? 'rgba(99,102,241,0.08)' : 'rgba(99,102,241,0.05)';

  const unread    = notifications.filter(n => !readIds.has(n.id));
  const hasUnread = unread.length > 0;
  const fetchAgo  = lastFetch ? timeAgo(lastFetch) : null;

  return (
    <div style={{ width: 380, borderRadius: 16, overflow: 'hidden', background: panelBg }}>

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 18px',
        background: headBg,
        borderBottom: `1px solid ${borderColor}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ color: textHead, fontWeight: 700, fontSize: 15 }}>Notifications</span>
          {hasUnread && (
            <span style={{
              background: 'linear-gradient(135deg,#6366f1,#8b5cf6)',
              color: '#fff', fontSize: 11, fontWeight: 700,
              padding: '1px 8px', borderRadius: 20, lineHeight: '18px',
            }}>
              {unread.length} new
            </span>
          )}
        </div>
        {hasUnread && (
          <Button
            type="text"
            size="small"
            icon={<CheckOutlined />}
            onClick={() => markAllRead(notifications)}
            style={{ color: '#6366f1', fontSize: 12, height: 28, padding: '0 10px' }}
          >
            Mark all read
          </Button>
        )}
      </div>

      {/* List */}
      <div style={{ maxHeight: 400, overflowY: 'auto' }}>
        {notifications.length === 0 ? (
          <div style={{ padding: '48px 24px', textAlign: 'center' }}>
            <div style={{
              width: 48, height: 48, borderRadius: 14,
              background: isDark ? 'rgba(99,102,241,0.08)' : 'rgba(99,102,241,0.06)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 12px',
            }}>
              <BellOutlined style={{ fontSize: 22, color: '#6366f1' }} />
            </div>
            <div style={{ color: textHead, fontWeight: 600, fontSize: 14, marginBottom: 4 }}>All caught up</div>
            <div style={{ color: textMuted, fontSize: 12 }}>No notifications right now</div>
          </div>
        ) : (
          notifications.map((n, i) => {
            const isRead = readIds.has(n.id);
            const cfg    = TYPE_CFG[n.type] || TYPE_CFG.info;
            const ago    = n.timeAgo || timeAgo(n.time);
            return (
              <div
                key={n.id}
                onClick={() => markRead(n.id)}
                style={{
                  display: 'flex', gap: 12, padding: '13px 18px',
                  cursor: 'pointer',
                  background: isRead ? 'transparent' : unreadBg,
                  borderBottom: i < notifications.length - 1 ? `1px solid ${borderColor}` : 'none',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e  => { if (isRead) e.currentTarget.style.background = hoverBg; }}
                onMouseLeave={e  => { e.currentTarget.style.background = isRead ? 'transparent' : unreadBg; }}
              >
                {/* Type icon */}
                <div style={{
                  width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                  background: cfg.bg,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <cfg.Icon style={{ color: cfg.color, fontSize: 16 }} />
                </div>

                {/* Text */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    color: textHead, fontSize: 13,
                    fontWeight: isRead ? 400 : 600,
                    lineHeight: 1.4, marginBottom: 3,
                  }}>
                    {n.title}
                  </div>
                  <div style={{ color: textSub, fontSize: 12, lineHeight: 1.4 }}>
                    {n.description}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 5, flexWrap: 'wrap' }}>
                    <span style={{
                      fontSize: 10, fontWeight: 600, textTransform: 'uppercase',
                      letterSpacing: 0.5, color: cfg.color,
                    }}>
                      {n.category}
                    </span>
                    {ago && (
                      <>
                        <span style={{ color: borderColor }}>·</span>
                        <span style={{ fontSize: 11, color: textMuted }}>{ago}</span>
                      </>
                    )}
                    {n.email_sent && (
                      <>
                        <span style={{ color: borderColor }}>·</span>
                        <span style={{
                          fontSize: 10, fontWeight: 600,
                          color: '#22c55e',
                          background: 'rgba(34,197,94,0.10)',
                          padding: '1px 6px', borderRadius: 4,
                        }}>
                          ✉ email sent
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* Unread dot */}
                {!isRead && (
                  <div style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: '#6366f1', flexShrink: 0, marginTop: 6,
                  }} />
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer — last-refresh timestamp + manual refresh */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 18px',
        background: headBg,
        borderTop: `1px solid ${borderColor}`,
      }}>
        <span style={{ color: textMuted, fontSize: 11 }}>
          {fetchAgo ? `Updated ${fetchAgo}` : 'Loading…'}
        </span>
        <Button
          type="text"
          size="small"
          onClick={onRefresh}
          style={{ color: '#6366f1', fontSize: 11, height: 22, padding: '0 6px' }}
        >
          Refresh
        </Button>
      </div>
    </div>
  );
};

/* ── Header ─────────────────────────────────────────────────── */
const Header = ({ collapsed, setCollapsed, onLogout }) => {
  const { isDark, setIsDark } = useContext(ThemeContext);
  const { notifications, readIds, unreadCount, lastFetch, markRead, markAllRead, refresh } = useNotifications();
  const [notifOpen, setNotifOpen] = useState(false);
  const [photoUrl, setPhotoUrl] = useState(
    () => JSON.parse(localStorage.getItem('user') || '{}').profile_photo_url || null
  );
  const user     = JSON.parse(localStorage.getItem('user') || '{}');
  const userRole = localStorage.getItem('userRole') || 'user';

  // Refresh avatar when Settings page uploads a new photo
  React.useEffect(() => {
    const handler = () => setPhotoUrl(
      JSON.parse(localStorage.getItem('user') || '{}').profile_photo_url || null
    );
    window.addEventListener('profile-photo-updated', handler);
    return () => window.removeEventListener('profile-photo-updated', handler);
  }, []);
  const navigate = useNavigate();

  const roleLabels  = { admin: 'Administrator', sub_admin: 'Company Admin', manager: 'Manager', user: 'User' };
  const roleColors  = { admin: '#f59e0b', sub_admin: '#e879f9', manager: '#6366f1', user: '#22c55e' };

  const userMenu = [
    { key: 'profile', label: 'Profile', icon: <UserOutlined />, onClick: () => navigate('/settings') },
    { type: 'divider' },
    { key: 'logout', label: 'Sign Out', icon: <LogoutOutlined />, onClick: onLogout, danger: true },
  ];

  const textPrimary    = isDark ? '#e2e8f0' : '#1e293b';
  const textSecondary  = isDark ? '#94a3b8' : '#64748b';
  const userPillBg     = isDark ? 'rgba(99,102,241,0.04)' : 'rgba(99,102,241,0.05)';
  const userPillBorder = isDark ? '1px solid rgba(99,102,241,0.08)' : '1px solid #e9ecf2';
  const popoverBg      = isDark ? '#1e293b' : '#ffffff';
  const popoverBorder  = isDark ? 'rgba(99,102,241,0.10)' : 'rgba(99,102,241,0.10)';

  return (
    <Layout.Header style={{
      background: 'var(--bg-header)',
      backdropFilter: 'blur(12px)',
      padding: '0 28px',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      borderBottom: '1px solid var(--border-subtle)',
      transition: 'background 0.3s',
      height: 56,
      lineHeight: '56px',
    }}>
      <Button
        type="text"
        icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        onClick={() => setCollapsed(!collapsed)}
        style={{ fontSize: 16, color: textSecondary, width: 36, height: 36 }}
      />

      <Space size={8}>
        {/* Smart search */}
        <SmartSearch isDark={isDark} userRole={userRole} />

        {/* Theme toggle */}
        <Tooltip title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}>
          <Button
            type="text"
            icon={isDark ? <SunOutlined /> : <MoonOutlined />}
            onClick={() => setIsDark(!isDark)}
            style={{
              color: isDark ? '#f59e0b' : '#6366f1',
              width: 36, height: 36, fontSize: 16,
              transition: 'color 0.25s',
            }}
          />
        </Tooltip>

        {/* Notifications */}
        <Popover
          open={notifOpen}
          onOpenChange={setNotifOpen}
          trigger="click"
          placement="bottomRight"
          arrow={false}
          content={
            <NotificationsPanel
              notifications={notifications}
              readIds={readIds}
              markRead={markRead}
              markAllRead={markAllRead}
              isDark={isDark}
              lastFetch={lastFetch}
              onRefresh={refresh}
            />
          }
          styles={{
            root: { padding: 0 },
            body: {
              padding: 0,
              borderRadius: 16,
              background: popoverBg,
              border: `1px solid ${popoverBorder}`,
              boxShadow: isDark
                ? '0 20px 60px rgba(0,0,0,0.5)'
                : '0 16px 48px rgba(0,0,0,0.12), 0 4px 16px rgba(99,102,241,0.08)',
              overflow: 'hidden',
            },
          }}
        >
          <Tooltip title="Notifications" open={notifOpen ? false : undefined}>
            <Badge
              count={unreadCount}
              size="small"
              offset={[-2, 2]}
              styles={{ indicator: { boxShadow: 'none', background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' } }}
            >
              <Button
                type="text"
                icon={<BellOutlined />}
                style={{
                  color: notifOpen ? '#6366f1' : textSecondary,
                  width: 36, height: 36,
                  background: notifOpen
                    ? (isDark ? 'rgba(99,102,241,0.10)' : 'rgba(99,102,241,0.07)')
                    : 'transparent',
                  transition: 'all 0.2s',
                }}
              />
            </Badge>
          </Tooltip>
        </Popover>

        {/* User menu */}
        <Dropdown menu={{ items: userMenu }} trigger={['click']}>
          <div style={{
            display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 10,
            padding: '4px 12px 4px 4px', borderRadius: 12,
            background: userPillBg, border: userPillBorder,
            transition: 'all 0.2s',
          }}>
            <Avatar
              size={32}
              src={photoUrl || undefined}
              style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', fontSize: 13, fontWeight: 600 }}
            >
              {!photoUrl && (user.full_name || user.email || 'A').charAt(0).toUpperCase()}
            </Avatar>
            <div style={{ lineHeight: 1.3 }}>
              <div style={{ color: textPrimary, fontSize: 13, fontWeight: 500 }}>
                {user.full_name || user.email || 'Admin'}
              </div>
              <div style={{ color: roleColors[userRole] || textSecondary, fontSize: 10, fontWeight: 600 }}>
                {roleLabels[userRole] || 'User'}
              </div>
            </div>
          </div>
        </Dropdown>
      </Space>
    </Layout.Header>
  );
};

export default Header;
