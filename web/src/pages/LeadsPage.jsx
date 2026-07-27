import React, { useState, useEffect, useRef, useContext } from 'react';
import { useLocation } from 'react-router-dom';
import { ThemeContext } from '../context/ThemeContext';
import {
  Card,
  Table,
  Button,
  Input,
  Modal,
  Form,
  Space,
  Tag,
  Popconfirm,
  message,
  Row,
  Col,
  Select,
  Tooltip,
  Progress,
  Drawer,
  Divider,
  Alert,
  Skeleton,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  DownloadOutlined,
  MailOutlined,
  ClearOutlined,
  EyeOutlined,
  SearchOutlined,
  ReloadOutlined,
  RobotOutlined,
  CopyOutlined,
  CloudDownloadOutlined,
  GlobalOutlined,
  TeamOutlined,
  FilterOutlined,
  ThunderboltOutlined,
  AimOutlined,
  EnvironmentOutlined,
  RocketOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  FireOutlined,
  UpOutlined,
  DownOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  TrophyOutlined,
} from '@ant-design/icons';
import { apiWithFallback } from '../services/api';

// ── Quick Label Bar ────────────────────────────────────────────────────────────
const OUTCOME_CONFIG = [
  { outcome: 'converted',   label: 'Converted',  detail: 'Deal closed',  solid: '#16a34a', light: 'rgba(22,163,74,0.1)',    border: 'rgba(22,163,74,0.4)',    Icon: TrophyOutlined      },
  { outcome: 'contacted',   label: 'Replied',    detail: 'Got a reply',  solid: '#2563eb', light: 'rgba(37,99,235,0.1)',    border: 'rgba(37,99,235,0.4)',    Icon: MailOutlined        },
  { outcome: 'cold',        label: 'No Reply',   detail: 'Went silent',  solid: '#64748b', light: 'rgba(100,116,139,0.1)', border: 'rgba(100,116,139,0.4)', Icon: ClockCircleOutlined },
  { outcome: 'unqualified', label: 'Not a Fit',  detail: 'Wrong target', solid: '#dc2626', light: 'rgba(220,38,38,0.1)',   border: 'rgba(220,38,38,0.4)',   Icon: CloseCircleOutlined },
];

const QuickLabelBar = ({ lead, onLabeled }) => {
  const { isDark } = useContext(ThemeContext);
  const [saving, setSaving]               = useState(null);
  const [saved, setSaved]                 = useState(lead?.outcome || null);
  const [approvalStatus, setApprovalStatus] = useState(lead?.approval_status || null);
  const [hovered, setHovered]             = useState(null);

  const submit = async (outcome) => {
    if (saving) return;
    setSaving(outcome);
    try {
      const res = await apiWithFallback('/ai/feedback', 'post', {
        lead_id:      lead.id,
        outcome:      outcome,
        label_source: 'user_feedback',
      });
      const status = res?.data?.approval_status || 'approved';
      setSaved(outcome);
      setApprovalStatus(status);
      if (onLabeled) onLabeled(lead.id, outcome, status);
    } catch {
      // non-fatal
    } finally {
      setSaving(null);
    }
  };

  const savedCfg   = OUTCOME_CONFIG.find(c => c.outcome === saved);
  const dividerClr = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)';
  const mutedClr   = isDark ? '#475569' : '#9ca3af';
  const isPending  = approvalStatus === 'pending';
  const isRejected = approvalStatus === 'rejected';

  // Header badge
  const renderBadge = () => {
    if (isRejected) return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '3px 10px', borderRadius: 999,
        background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.4)',
        color: '#dc2626', fontSize: 11, fontWeight: 600,
      }}>
        <CloseCircleOutlined style={{ fontSize: 10 }} /> Rejected — re-label
      </span>
    );
    if (isPending) return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '3px 10px', borderRadius: 999,
        background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.4)',
        color: '#d97706', fontSize: 11, fontWeight: 600,
      }}>
        <ClockCircleOutlined style={{ fontSize: 10 }} /> Pending approval
      </span>
    );
    if (savedCfg) return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '3px 10px', borderRadius: 999,
        background: savedCfg.light, border: `1px solid ${savedCfg.border}`,
        color: savedCfg.solid, fontSize: 11, fontWeight: 600,
      }}>
        <savedCfg.Icon style={{ fontSize: 10 }} /> {savedCfg.label}
      </span>
    );
    return (
      <span style={{
        fontSize: 11, color: mutedClr, padding: '3px 10px', borderRadius: 999,
        border: `1px dashed ${isDark ? '#334155' : '#d1d5db'}`,
      }}>Unlabeled</span>
    );
  };

  return (
    <div style={{
      borderRadius: 12,
      border: `1px solid ${isDark ? 'rgba(255,255,255,0.09)' : 'rgba(0,0,0,0.09)'}`,
      background: isDark ? 'rgba(255,255,255,0.03)' : '#fff',
      boxShadow: isDark ? 'none' : '0 1px 6px rgba(0,0,0,0.06)',
      overflow: 'hidden', marginBottom: 24,
    }}>

      {/* ── Header ── */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 16px',
        borderBottom: `1px solid ${dividerClr}`,
        background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.015)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <RobotOutlined style={{ color: '#6366f1', fontSize: 13 }} />
          <span style={{
            fontSize: 11, fontWeight: 700, letterSpacing: '0.07em',
            textTransform: 'uppercase', color: isDark ? '#cbd5e1' : '#374151',
          }}>Lead Outcome</span>
        </div>
        {renderBadge()}
      </div>

      {/* ── Outcome buttons ── */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 8, padding: '12px 14px',
      }}>
        {OUTCOME_CONFIG.map(({ outcome, label, detail, solid, light, border, Icon }) => {
          const isActive  = saved === outcome && !isPending && !isRejected;
          const isHov     = hovered === outcome && !saving;
          const isLoading = saving === outcome;

          const bg  = isActive ? solid : isHov ? light : 'transparent';
          const bdr = isActive ? solid : isHov ? border : (isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)');
          const clr = isActive ? '#fff' : isHov ? solid : (isDark ? '#64748b' : '#6b7280');

          return (
            <button
              key={outcome}
              onClick={() => submit(outcome)}
              onMouseEnter={() => setHovered(outcome)}
              onMouseLeave={() => setHovered(null)}
              disabled={!!saving}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                gap: 5, padding: '11px 6px', borderRadius: 9,
                border: `1.5px solid ${bdr}`,
                background: bg, color: clr,
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving && !isLoading ? 0.35 : 1,
                transition: 'background 0.14s, border-color 0.14s, color 0.14s, opacity 0.14s',
              }}
            >
              <span style={{ fontSize: 17, lineHeight: 1 }}>
                {isLoading ? <SyncOutlined spin style={{ fontSize: 16 }} /> : <Icon />}
              </span>
              <span style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.3 }}>{label}</span>
              <span style={{ fontSize: 10, opacity: 0.65, lineHeight: 1.2, fontWeight: 400 }}>{detail}</span>
            </button>
          );
        })}
      </div>

      {/* ── Status strip ── */}
      {saved && (
        <div style={{
          padding: '8px 16px',
          borderTop: `1px solid ${dividerClr}`,
          display: 'flex', alignItems: 'center', gap: 8,
          background: isPending
            ? (isDark ? 'rgba(245,158,11,0.08)' : 'rgba(245,158,11,0.06)')
            : isRejected
            ? (isDark ? 'rgba(220,38,38,0.08)' : 'rgba(220,38,38,0.06)')
            : (savedCfg ? (isDark ? `${savedCfg.solid}18` : savedCfg.light) : 'transparent'),
        }}>
          {isPending ? (
            <>
              <ClockCircleOutlined style={{ color: '#d97706', fontSize: 13 }} />
              <span style={{ fontSize: 12, color: '#d97706', fontWeight: 500 }}>
                Awaiting manager approval
              </span>
              <span style={{ fontSize: 11, color: mutedClr, marginLeft: 'auto' }}>
                Will train AI once approved
              </span>
            </>
          ) : isRejected ? (
            <>
              <CloseCircleOutlined style={{ color: '#dc2626', fontSize: 13 }} />
              <span style={{ fontSize: 12, color: '#dc2626', fontWeight: 500 }}>
                Label rejected by manager
              </span>
              <span style={{ fontSize: 11, color: mutedClr, marginLeft: 'auto' }}>
                Pick a different outcome
              </span>
            </>
          ) : (
            <>
              <CheckCircleOutlined style={{ color: savedCfg?.solid, fontSize: 13 }} />
              <span style={{ fontSize: 12, color: savedCfg?.solid, fontWeight: 500 }}>
                Approved — trains AI model
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
};

const LeadsPage = () => {
  const { isDark } = useContext(ThemeContext);
  const location = useLocation();
  const [leads, setLeads] = useState([]);
  const [totalLeads, setTotalLeads] = useState(0);  // Total from API
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterInterest, setFilterInterest] = useState('');
  const [filterLocation, setFilterLocation] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [filterCountry, setFilterCountry] = useState('');
  const [filterIndustry, setFilterIndustry] = useState('');
  const [filterQualityTier, setFilterQualityTier] = useState('');
  const [filterVerifiedEmail, setFilterVerifiedEmail] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);  // Default 5 per page for better pagination
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const searchDebounceRef = useRef(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [addModalVisible, setAddModalVisible] = useState(false);
  const [selectedLead, setSelectedLead] = useState(null);
  const [addForm] = Form.useForm();

  // AI feature state
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [aiAnalysisLoading, setAiAnalysisLoading] = useState(false);
  const [aiEmail, setAiEmail] = useState(null);
  const [aiEmailLoading, setAiEmailLoading] = useState(false);
  const [aiEmailType, setAiEmailType] = useState('cold_outreach');
  const [aiEmailTone, setAiEmailTone] = useState('professional');
  const [collectLoading, setCollectLoading] = useState(false);
  const [collectModalVisible, setCollectModalVisible] = useState(false);
  const [collectProgress, setCollectProgress] = useState(0);
  const [collectProgressText, setCollectProgressText] = useState('');
  const [collectElapsed, setCollectElapsed] = useState(0);
  const collectElapsedRef = useRef(null);

  // Batch AI qualification state
  const [loadingLeadId, setLoadingLeadId] = useState(null);    // per-row ML re-score spinner
  const [loadingAILeadId, setLoadingAILeadId] = useState(null); // per-row Groq/Gemini spinner
  const [lastCollectionResult, setLastCollectionResult] = useState(null);
  const [supportedCountries, setSupportedCountries] = useState([]);
  const [collectionType, setCollectionType] = useState('companies');
  const [collectForm] = Form.useForm();

  // Auto collect state
  const [autoCollectVisible, setAutoCollectVisible] = useState(false);
  const [autoCollectSources, setAutoCollectSources] = useState({});
  const [autoCollectLoading, setAutoCollectLoading] = useState(false);
  const [autoCollectProgress, setAutoCollectProgress] = useState(0);
  const [autoCollectElapsed, setAutoCollectElapsed] = useState(0);
  const [autoCollectResult, setAutoCollectResult] = useState(null);
  const [autoCollectForm] = Form.useForm();
  const autoCollectElapsedRef = useRef(null);
  const autoCollectNudgeRef = useRef(null);
  const [autoShowInterest, setAutoShowInterest] = useState(false);

  // Interest-based collection state
  const [interestModalVisible, setInterestModalVisible] = useState(false);
  const [interestCategories, setInterestCategories] = useState([]);
  const [interestForm] = Form.useForm();
  const [isInterestCollecting, setIsInterestCollecting] = useState(false);
  const [interestResult, setInterestResult] = useState(null);
  const [interestProgress, setInterestProgress] = useState(0);
  const [interestElapsed, setInterestElapsed] = useState(0);
  const [interestProgressText, setInterestProgressText] = useState('');
  const interestElapsedRef = useRef(null);
  const interestNudgeRef = useRef(null);
  const interestPollRef = useRef(null);
  const [filterBuyingIntent, setFilterBuyingIntent] = useState('');

  // Lead assignment state
  const [assignLoading, setAssignLoading] = useState(false);
  const currentUserId   = JSON.parse(localStorage.getItem('user') || '{}').id;
  const currentUserRole = localStorage.getItem('userRole') || 'user';

  // Social media collection state
  const [socialModalVisible, setSocialModalVisible] = useState(false);
  const [socialLoading, setSocialLoading] = useState(false);
  const [socialProgress, setSocialProgress] = useState(0);
  const [socialProgressText, setSocialProgressText] = useState('');
  const [socialResult, setSocialResult] = useState(null);
  const [socialForm] = Form.useForm();
  const [socialPlatformResults, setSocialPlatformResults] = useState([]); // per-platform live status

  // Apply URL params injected by the smart search (e.g. /leads?q=X&interest=Hot)
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const q        = params.get('q');
    const interest = params.get('interest');
    const status   = params.get('status');
    if (q)        setSearchText(q);
    if (interest) setFilterInterest(interest);
    if (status)   setFilterStatus(status);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounce search input — wait 400ms after last keystroke before fetching
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => {
      setDebouncedSearch(searchText);
      setCurrentPage(1);
    }, 400);
    return () => clearTimeout(searchDebounceRef.current);
  }, [searchText]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchLeads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, pageSize, debouncedSearch, filterStatus, filterInterest, filterLocation, filterSource, filterCountry, filterIndustry, filterQualityTier, filterVerifiedEmail, filterBuyingIntent]);

  useEffect(() => {
    fetchSupportedCountries();
    fetchInterestCategories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchSupportedCountries = async () => {
    try {
      const response = await apiWithFallback('/ai/supported-countries', 'get');
      if (response.data.countries) {
        setSupportedCountries(response.data.countries);
      }
    } catch (error) {
      setSupportedCountries([
        { code: 'US', name: 'United States' },
        { code: 'UK', name: 'United Kingdom' },
        { code: 'DE', name: 'Germany' },
        { code: 'FR', name: 'France' },
        { code: 'AE', name: 'United Arab Emirates' },
        { code: 'SA', name: 'Saudi Arabia' },
        { code: 'IN', name: 'India' },
        { code: 'CA', name: 'Canada' },
        { code: 'AU', name: 'Australia' },
        { code: 'JP', name: 'Japan' },
        { code: 'BR', name: 'Brazil' },
        { code: 'EG', name: 'Egypt' },
        { code: 'NG', name: 'Nigeria' },
        { code: 'ZA', name: 'South Africa' },
        { code: 'SG', name: 'Singapore' },
      ]);
    }
  };

  const fetchInterestCategories = async () => {
    try {
      const response = await apiWithFallback('/ai/lead-categories', 'get');
      if (response.data.categories) setInterestCategories(response.data.categories);
    } catch {
      setInterestCategories([]);
    }
  };

  const fetchLeads = async () => {
    try {
      setLoading(true);
      
      // Check if authenticated
      const token = localStorage.getItem('authToken');
      if (!token) {
        setLeads([]);
        return;
      }

      // Fetch from real API — all filterable fields passed server-side
      const response = await apiWithFallback('/leads/', 'get', null, {
        params: {
          page: currentPage,
          per_page: pageSize,
          ...(filterStatus      && { status:       filterStatus }),
          ...(filterSource      && { source:       filterSource }),
          ...(filterLocation    && { location:     filterLocation }),
          ...(filterInterest    && { interest:     filterInterest }),
          ...(filterCountry     && { country:      filterCountry }),
          ...(filterIndustry    && { industry:     filterIndustry }),
          ...(filterQualityTier && { quality_tier: filterQualityTier }),
          ...(filterVerifiedEmail  && { verified_email:  true }),
          ...(filterBuyingIntent  && { buying_intent:   filterBuyingIntent }),
          ...(debouncedSearch.trim() && { search: debouncedSearch.trim() }),
        }
      });

      let allLeads = [];
      let apiTotal = 0;

      if (response.data && response.data.leads && Array.isArray(response.data.leads)) {
        allLeads = response.data.leads;
        apiTotal = response.data.total || allLeads.length;
      } else if (response.data && Array.isArray(response.data)) {
        allLeads = response.data;
        apiTotal = allLeads.length;
      } else {
        throw new Error('Invalid API response format');
      }
      
      // Normalize: map qualification_score to score (no inflating — show real 0 as 0)
      allLeads = allLeads.map(lead => ({
        ...lead,
        score: lead.qualification_score != null ? Math.round(lead.qualification_score) : 0,
        status: lead.status || 'cold',
        company: lead.company || 'N/A',
      }));
      
      // All filtering is now server-side — just use the results directly
      setLeads(allLeads);
      setTotalLeads(apiTotal);
    } catch (error) {
      if (error.response?.status === 401) {
        message.error('Session expired. Please log in again.');
        localStorage.removeItem('authToken');
        localStorage.removeItem('tokenExpiry');
      } else {
        message.error('Failed to load leads: ' + (error.message || 'Unknown error'));
      }
      setLeads([]);
    } finally {
      setLoading(false);
    }
  };

  const [exporting, setExporting] = useState(false);

  const handleExportCSV = async () => {
    const msgKey = 'csv-export';
    setExporting(true);

    // CSV cell helpers ─────────────────────────────────────────────────────
    // Always-text (strings, URLs, etc.)
    const qt = (v) => v == null || v === '' ? '""' : `"${String(v).replace(/"/g, '""')}"`;
    // Numeric — leave unquoted so Excel sorts/sums correctly
    const qn = (v) => { if (v == null || v === '') return ''; const n = Number(v); return isNaN(n) ? qt(v) : String(n); };
    // Phone — Excel formula trick: ="digits" prevents 1.42E+10 scientific notation
    const qPhone = (v) => {
      if (!v) return '""';
      const formula = `="${v}"`;
      return '"' + formula.replace(/"/g, '""') + '"';
    };
    // Date as DD-Mon-YYYY text — prevents Excel date auto-conversion and ########
    const qDate = (v) => {
      if (!v) return '""';
      const d = new Date(v);
      if (isNaN(d.getTime())) return '""';
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      return qt(`${d.getDate()}-${months[d.getMonth()]}-${d.getFullYear()}`);
    };

    const HEADERS = [
      'Name', 'Email', 'Phone', 'Company', 'Position', 'Website',
      'Country', 'Location', 'Industry', 'Company Size',
      'Interest Level', 'Score', 'Quality Tier',
      'Status', 'Source', 'Email Verified', 'Created Date',
    ];

    // toRow returns a ready-to-join CSV line (each cell already formatted)
    const toRow = (l) => [
      qt(l.name),
      qt(l.email),
      qPhone(l.phone),
      qt(l.company),
      qt(l.position),
      qt(l.website),
      qt(l.country),
      qt(l.location),
      qt(l.industry),
      qt(l.company_size),
      qt(l.interest_level),
      qn(l.qualification_score != null ? l.qualification_score : ''),
      qt(l.quality_tier),
      qt(l.status),
      qt(l.source),
      qt(l.email_verified ? 'Yes' : 'No'),
      qDate(l.created_at),
    ].join(',');

    const buildFilters = () => [
      filterStatus   && `Status=${filterStatus}`,
      filterInterest && `Interest=${filterInterest}`,
      filterCountry  && `Country=${filterCountry}`,
      filterIndustry && `Industry=${filterIndustry}`,
      filterSource   && `Source=${filterSource}`,
      searchText     && `Search="${searchText}"`,
    ].filter(Boolean);

    try {
      // ── 1. Try backend export endpoint ──────────────────────────
      message.loading({ content: 'Connecting to export service…', key: msgKey, duration: 0 });
      let backendOk = false;
      try {
        const token   = localStorage.getItem('authToken');
        const apiBase = (process.env.REACT_APP_API_URL || 'http://localhost:5000') + '/api/v1';
        const qs      = new URLSearchParams();
        if (filterStatus)   qs.set('status',   filterStatus);
        if (filterInterest) qs.set('interest',  filterInterest);
        if (searchText)     qs.set('search',    searchText);
        if (filterCountry)  qs.set('country',   filterCountry);
        if (filterIndustry) qs.set('industry',  filterIndustry);
        if (filterLocation) qs.set('location',  filterLocation);
        if (filterSource)   qs.set('source',    filterSource);

        const resp = await fetch(`${apiBase}/leads/export?${qs}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (resp.ok) {
          const blob = await resp.blob();
          const date = new Date().toISOString().split('T')[0];
          const filters = buildFilters();
          const link = document.createElement('a');
          link.href = URL.createObjectURL(blob);
          link.download = `OrionLead_Export_${filters.length ? 'filtered' : 'all'}_${date}.csv`;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(link.href);
          message.success({ content: 'Export complete — check your downloads.', key: msgKey, duration: 4 });
          backendOk = true;
        }
      } catch { /* fall through */ }
      if (backendOk) return;

      // ── 2. Client-side paginated export ─────────────────────────
      const collected = [];
      let page = 1;
      const PER_PAGE = 100;
      const knownTotal = totalLeads || 0;

      const filters = buildFilters();
      const filterParams = {
        sort_by: 'created_at', sort_order: 'desc',
        ...(filterStatus   && { status:   filterStatus }),
        ...(filterInterest && { interest: filterInterest }),
        ...(searchText     && { search:   searchText }),
        ...(filterCountry  && { country:  filterCountry }),
        ...(filterIndustry && { industry: filterIndustry }),
        ...(filterLocation && { location: filterLocation }),
        ...(filterSource   && { source:   filterSource }),
      };

      while (true) {
        const pct = knownTotal > 0
          ? Math.min(Math.round((collected.length / knownTotal) * 92), 92)
          : null;

        message.loading({
          content: pct != null
            ? `Exporting leads… ${pct}%  (${collected.length} / ${knownTotal})`
            : `Fetching page ${page}… (${collected.length} leads so far)`,
          key: msgKey, duration: 0,
        });

        const res = await apiWithFallback('/leads/', 'get', null, {
          params: { page, per_page: PER_PAGE, ...filterParams },
        });
        const batch = res?.data?.leads || [];
        collected.push(...batch);
        if (batch.length < PER_PAGE || page >= 20) break;
        page++;
      }

      if (!collected.length) {
        message.warning({ content: 'No leads match the current filters.', key: msgKey, duration: 3 });
        return;
      }

      message.loading({ content: `Building file… (${collected.length} leads)`, key: msgKey, duration: 0 });

      // Professional CSV: clean header row + data rows only.
      // No metadata rows — they break Excel's table recognition.
      // Context lives in the filename instead.
      const csvContent = [
        HEADERS.map(h => `"${h}"`).join(','),   // header row
        ...collected.map(toRow),                // data rows (toRow returns ready CSV line)
      ].join('\r\n');

      const blob = new Blob(['﻿' + csvContent], { type: 'text/csv;charset=utf-8;' });

      const dateStr = new Date().toISOString().split('T')[0];
      const nameParts = [
        'OrionLead_Export',
        filters.length ? 'filtered' : `${collected.length}leads`,
        dateStr,
      ];
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = nameParts.join('_') + '.csv';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);

      message.success({
        content: `${collected.length} lead${collected.length !== 1 ? 's' : ''} exported successfully`,
        key: msgKey, duration: 4,
      });
    } catch {
      message.error({ content: 'Export failed — please try again.', key: msgKey, duration: 3 });
    } finally {
      setExporting(false);   // always runs — even after early return from backend path
    }
  };

  const handleContact = (lead, type) => {
    if (type === 'email') {
      window.location.href = `mailto:${lead.email}`;
    } else if (type === 'phone') {
      window.location.href = `tel:${lead.phone}`;
    }
  };

  const handleDeleteLead = async (id) => {
    try {
      setLoading(true);
      await apiWithFallback(`/leads/${id}`, 'delete');
      message.success('✓ Lead deleted');
      fetchLeads();
    } catch (error) {
      message.error('Failed to delete lead: ' + (error?.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const handleClearAllLeads = async () => {
    try {
      setLoading(true);
      const resp = await apiWithFallback('/leads/all', 'delete');
      message.success(`${resp?.data?.deleted_count ?? 'All'} leads deleted — database is clean`);
      fetchLeads();
    } catch (error) {
      message.error('Failed to clear leads: ' + (error?.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const [addLeadLoading, setAddLeadLoading] = useState(false);

  const handleAddLead = async (values) => {
    setAddLeadLoading(true);
    try {
      await apiWithFallback('/leads/', 'post', {
        name:      values.name,
        email:     values.email     || undefined,
        phone:     values.phone     || undefined,
        company:   values.company,
        position:  values.position  || undefined,
        lead_type: values.lead_type || 'person',
        interests: values.interests ? (Array.isArray(values.interests) ? values.interests : [values.interests]) : [],
        product:   values.product   || undefined,
        location:  values.location  || undefined,
        country:   values.country   || undefined,
        city:      values.city      || undefined,
        industry:  values.industry  || undefined,
        website:   values.website   || undefined,
        linkedin_url: values.linkedin_url || undefined,
        source:    'manual',
      });
      message.success('Lead added successfully');
      addForm.resetFields();
      setAddModalVisible(false);
      fetchLeads();
    } catch (error) {
      const resp = error?.response?.data;
      const detail = resp?.reasons?.join(' · ') || resp?.message || error?.message || 'Unknown error';
      message.error('Could not save lead: ' + detail, 6);
    } finally {
      setAddLeadLoading(false);
    }
  };

  const handleShowDetail = (lead) => {
    setSelectedLead(lead);
    setDetailModalVisible(true);
  };

  const handleInterestCollect = async (values) => {
    // Clear any leftover poll/timers from previous run
    if (interestPollRef.current)  { clearInterval(interestPollRef.current);  interestPollRef.current  = null; }
    if (interestNudgeRef.current) { clearInterval(interestNudgeRef.current); interestNudgeRef.current = null; }
    if (interestElapsedRef.current) { clearInterval(interestElapsedRef.current); interestElapsedRef.current = null; }

    setIsInterestCollecting(true);
    setInterestResult(null);
    setInterestProgress(0);
    setInterestElapsed(0);
    setInterestProgressText('🔍 Starting collection…');

    // Elapsed-time ticker (purely cosmetic — shows how long collection is taking)
    const _t0 = Date.now();
    interestElapsedRef.current = setInterval(() => {
      setInterestElapsed(Math.round((Date.now() - _t0) / 1000));
    }, 1000);

    const _stopAll = () => {
      clearInterval(interestElapsedRef.current);
      clearInterval(interestNudgeRef.current);
      clearInterval(interestPollRef.current);
      interestElapsedRef.current = null;
      interestNudgeRef.current   = null;
      interestPollRef.current    = null;
    };

    // Step 1: start collection — returns task_id in <1s
    let taskId = null;
    try {
      const payload = {
        category:  values.interest_category,
        country:   values.interest_country,
        city:      values.interest_city || undefined,
        max_leads: values.interest_max_leads || 30,
        sources:   values.interest_sources?.length ? values.interest_sources : undefined,
      };
      const startRes = await apiWithFallback('/ai/collect-by-interest', 'post', payload, { timeout: 20000 });
      taskId = startRes.data?.task_id || startRes.data?.data?.task_id;
    } catch (err) {
      _stopAll();
      setIsInterestCollecting(false);
      const msg = err?.response?.data?.message || 'Failed to start collection';
      message.error(msg);
      setInterestResult({ status: 'error', message: msg });
      return;
    }

    if (!taskId) {
      _stopAll();
      setIsInterestCollecting(false);
      message.error('No task ID returned — collection could not start');
      setInterestResult({ status: 'error', message: 'No task ID returned' });
      return;
    }

    // Step 2: poll backend every 2s for real progress — max 8 min
    let pollCount = 0;
    const maxPolls = 240;

    interestPollRef.current = setInterval(async () => {
      pollCount++;
      try {
        const statusRes = await apiWithFallback(
          `/ai/collect-by-interest/status/${taskId}`, 'get', null, { timeout: 5000 }
        );
        const task = statusRes.data?.data || {};
        const pct  = task.percent || 0;
        const msg  = task.stage_name || '';

        // Real backend progress overrides the nudge
        setInterestProgress(pct);
        if (msg) setInterestProgressText(msg);

        const isDone  = task.status === 'done'  || pct >= 100;
        const isError = task.status === 'error';

        if (isDone || isError || pollCount >= maxPolls) {
          _stopAll();
          setIsInterestCollecting(false);
          setInterestProgress(100);

          if (isError) {
            const errMsg = task.error || 'Interest collection failed';
            message.error(errMsg);
            setInterestResult({ status: 'error', message: errMsg });
            setInterestProgressText('');
          } else {
            const saved = task.saved || 0;
            const elapsed = Math.round((Date.now() - _t0) / 1000);
            setInterestProgressText(
              saved > 0 ? `✅ Done — ${saved} leads saved in ${elapsed}s` : `✅ Done — 0 new leads in ${elapsed}s`
            );
            setInterestResult({
              status:         'success',
              collected:      task.raw_candidates || 0,
              saved,
              rejected:       task.rejected   || 0,
              duplicates:     task.duplicates  || 0,
              quality_report: task.quality_report || null,
            });
            if (saved > 0) {
              message.success(`Saved ${saved} leads for ${values.interest_category}`);
              setCurrentPage(1);
              fetchLeads();
            } else {
              message.warning('Collection complete — no leads met quality requirements');
            }
          }
        }
      } catch {
        if (pollCount >= maxPolls) {
          _stopAll();
          setIsInterestCollecting(false);
          message.error('Collection status check timed out');
          setInterestResult({ status: 'error', message: 'Status check timed out' });
        }
      }
    }, 2000);
  };

  const handleClearFilters = () => {
    setSearchText('');
    setDebouncedSearch('');
    setFilterStatus('');
    setFilterInterest('');
    setFilterLocation('');
    setFilterSource('');
    setFilterCountry('');
    setFilterIndustry('');
    setFilterQualityTier('');
    setFilterVerifiedEmail(false);
    setFilterBuyingIntent('');
    setCurrentPage(1);
  };

  // ── Quality helpers ─────────────────────────────────────────────────────────
  const getQualityTierStyle = (tier) => {
    const t = (tier || '').toLowerCase();
    if (t === 'high_quality') return { bg: 'rgba(34,197,94,0.15)', color: '#4ade80', label: '★ High' };
    if (t === 'qualified')    return { bg: 'rgba(99,102,241,0.15)', color: '#818cf8', label: '✓ Validated' };
    if (t === 'pending')      return { bg: 'rgba(251,191,36,0.15)', color: '#fbbf24', label: '◷ Pending' };
    if (t === 'low_quality')  return { bg: 'rgba(239,68,68,0.12)',  color: '#f87171', label: '↓ Low' };
    if (t === 'rejected')     return { bg: 'rgba(100,116,139,0.15)', color: '#94a3b8', label: '✕ Rejected' };
    return { bg: 'rgba(100,116,139,0.10)', color: '#64748b', label: tier || '–' };
  };

  // Derive quality tier from score — must match backend thresholds exactly.
  const getTierFromScore = (score) => {
    const s = score || 0;
    if (s >= 80) return 'high_quality';
    if (s >= 35) return 'qualified';   // backend qualified_threshold = 35
    if (s >= 20) return 'pending';     // backend pending_threshold   = 20
    if (s >= 8)  return 'low_quality'; // backend low_quality_threshold = 8
    if (s > 0)   return 'rejected';
    return '';
  };

  const getEmailTypeStyle = (emailType) => {
    const t = (emailType || '').toLowerCase();
    if (t === 'personal_business' || t === 'personal') return { color: '#4ade80', label: 'Personal' };
    if (t === 'company')   return { color: '#60a5fa', label: 'Company' };
    if (t === 'generic')   return { color: '#fbbf24', label: 'Generic' };
    if (t === 'free')      return { color: '#a78bfa', label: 'Free' };
    if (t === 'generated_personal' || t === 'generated_generic' || t === 'generated')
      return { color: '#ef4444', label: 'Generated' };
    return { color: '#64748b', label: emailType || '–' };
  };

  const handleCollectFromWeb = async (values) => {
    const startTime = Date.now();
    // Warm-up: smoothly fill 0→10% while the initial POST is in-flight
    let warmupPct = 0;
    const warmupInterval = setInterval(() => {
      warmupPct = Math.min(warmupPct + 1.5, 10);
      setCollectProgress(warmupPct);
    }, 400);

    // Elapsed-time ticker
    if (collectElapsedRef.current) clearInterval(collectElapsedRef.current);
    collectElapsedRef.current = setInterval(() => {
      setCollectElapsed(Math.round((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      setCollectLoading(true);
      setCollectProgress(0);
      setCollectElapsed(0);
      setCollectProgressText('🔍 Starting web collection...');
      setLastCollectionResult(null);

      // Start async collection — returns task_id immediately
      const response = await apiWithFallback('/ai/collect-leads', 'post', {
        query: values.query,
        countries: values.countries,
        city: values.city || '',
        max_per_country: values.max_per_country || 10,
        collection_type: values.collection_type || 'companies',
      }, { timeout: 30000 });

      clearInterval(warmupInterval);

      const taskId = response.data?.data?.task_id;
      if (!taskId) {
        // Fallback if no task_id (shouldn't happen)
        clearInterval(collectElapsedRef.current);
        setCollectProgress(100);
        message.success(response.data.message || 'Collection started');
        setTimeout(() => { setCollectProgress(0); setCollectElapsed(0); setCollectLoading(false); setCollectModalVisible(false); fetchLeads(); }, 2000);
        return;
      }

      // Sequential setTimeout polling — each poll waits for the previous to
      // finish before scheduling the next, so pollCount never races ahead.
      const deadlineMs = 7 * 60 * 1000; // 7-minute hard limit (AI planning + scraping + per-lead pipeline can take 4-6 min)
      let pollStopped = false;

      const stopPolling = () => { pollStopped = true; };

      const poll = async () => {
        if (pollStopped) return;
        if (Date.now() - startTime > deadlineMs) {
          stopPolling();
          clearInterval(collectElapsedRef.current);
          setCollectProgress(100);
          message.info('Collection is still processing in the background — leads will appear shortly');
          await fetchLeads();
          setTimeout(() => { setCollectProgress(0); setCollectElapsed(0); setCollectProgressText(''); setCollectLoading(false); setCollectModalVisible(false); }, 2000);
          return;
        }

        try {
          const statusRes = await apiWithFallback(`/ai/collect-leads/status/${taskId}`, 'get', null, { timeout: 8000 });
          const task = statusRes.data?.data || {};
          const pct = task.percent || 0;
          const saved = task.saved || 0;
          const collected = task.total_collected || 0;
          const currentCountry = task.current_country || task.current_platform || '';
          const byCountry = task.by_country || {};

          // Always trust server value; no nudge beyond server's real percent
          setCollectProgress(Math.max(pct, 5));

          const elapsed = Math.round((Date.now() - startTime) / 1000);
          if (pct >= 85 && currentCountry === 'saving') {
            setCollectProgressText(`💾 Saving ${collected} leads... · ${elapsed}s`);
          } else if (currentCountry && currentCountry !== 'saving') {
            const doneCount = task.completed_countries || 0;
            const total = task.total_countries || 0;
            const byTags = Object.entries(byCountry).map(([c, n]) => `${c}:${n}`).join(' ');
            setCollectProgressText(
              `🌐 ${currentCountry.toUpperCase()} · ${doneCount}/${total} countries${byTags ? ' · ' + byTags : ''} · ${elapsed}s`
            );
          } else if (collected > 0) {
            setCollectProgressText(`📊 ${collected} leads found (${pct}%) · ${elapsed}s`);
          } else {
            setCollectProgressText(`🔍 Scanning web sources... · ${elapsed}s`);
          }

          if (task.status === 'done' || task.status === 'error' || pct >= 100) {
            stopPolling();
            clearInterval(collectElapsedRef.current);
            setCollectProgress(100);

            if (task.status === 'error') {
              message.error('Web collection encountered an error');
              setCollectProgressText('');
              setLastCollectionResult({ status: 'error', message: 'Collection failed' });
            } else {
              const duration = Math.round((Date.now() - startTime) / 1000);
              const rejReasons = task.rejection_reasons || {};
              const rejEntries = Object.entries(rejReasons).sort((a, b) => b[1] - a[1]);
              const topReason  = rejEntries[0];
              const dupes = task.duplicates || task.quality_report?.duplicates || 0;

              let resultMsg;
              if (saved === 0 && collected > 0) {
                if (dupes >= collected) {
                  resultMsg = `Collected ${collected} leads — all already in database (duplicates)`;
                } else if (topReason) {
                  resultMsg = `Collected ${collected} leads, saved 0 — top rejection: ${topReason[0].replace(/_/g, ' ')} ×${topReason[1]}`;
                } else {
                  resultMsg = `Collected ${collected} leads, saved 0 — rejected by intelligence gate`;
                }
                setCollectProgressText(`⚠️ 0 leads saved · ${duration}s`);
              } else {
                resultMsg = `Collected ${collected} leads, saved ${saved} new · ${duration}s`;
                setCollectProgressText(`✅ Done — ${saved} new leads saved in ${duration}s`);
                message.success(resultMsg);
              }
              setLastCollectionResult({ status: 'success', message: resultMsg, data: task });
              setCurrentPage(1);
              setSearchText('');
              setFilterStatus('');
              setFilterSource('');
              try {
                const refreshRes = await apiWithFallback('/leads/', 'get', null, { params: { page: 1, per_page: pageSize } });
                if (refreshRes.data?.leads) {
                  setLeads(refreshRes.data.leads.map(lead => ({
                    ...lead,
                    score: lead.qualification_score != null ? Math.round(lead.qualification_score) : 0,
                    status: lead.status || 'cold',
                    company: lead.company || 'N/A',
                  })));
                  setTotalLeads(refreshRes.data.total || refreshRes.data.leads.length);
                }
              } catch (refreshErr) { console.error('Failed to refresh leads:', refreshErr); }
            }
            setTimeout(() => { setCollectProgress(0); setCollectElapsed(0); setCollectProgressText(''); setCollectLoading(false); setCollectModalVisible(false); }, 2500);
            return; // done — no next poll
          }
        } catch {
          // Poll request failed — wait longer before retrying
          if (!pollStopped) setTimeout(poll, 3000);
          return;
        }

        // Schedule next poll only after this one fully resolved
        if (!pollStopped) setTimeout(poll, 1500);
      };

      setTimeout(poll, 1500);

    } catch (error) {
      clearInterval(warmupInterval);
      clearInterval(collectElapsedRef.current);
      setCollectProgress(0);
      setCollectElapsed(0);
      setCollectLoading(false);
      const errMsg = error?.response?.data?.message || error?.message || 'Unknown error';
      message.error('Collection failed: ' + errMsg);
      setLastCollectionResult({ status: 'error', message: errMsg });
    }
  };

  const handleCollectFromSocial = async (values) => {
    const platformEmojis = { reddit: '🔴', telegram: '✈️', twitter: '🐦', facebook: '📘', linkedin: '💼' };
    const chosenPlatforms = values.platforms || [];

    try {
      setSocialLoading(true);
      setSocialProgress(0);
      setSocialProgressText('Starting collection...');
      setSocialResult(null);
      // Init per-platform status rows as pending
      setSocialPlatformResults(chosenPlatforms.map(p => ({ platform: p, status: 'pending', leads: 0 })));

      const response = await apiWithFallback('/ai/collect-social', 'post', {
        query: values.query,
        platforms: chosenPlatforms,
        industry: values.industry || '',
        max_per_platform: values.max_per_platform || 10,
        collect_type: values.collect_type || 'both',
        location: values.location || '',
      }, { timeout: 30000 });

      const data = response.data.data || {};
      const taskId = data.task_id;

      if (!taskId) {
        // Fallback: no task_id (shouldn't happen, but handle gracefully)
        setSocialProgress(100);
        setSocialProgressText('Done!');
        const resultMsg = response.data.message || 'Collection started';
        setSocialResult({ status: 'success', message: resultMsg, data });
        message.success(resultMsg);
        setCurrentPage(1);
        setTimeout(async () => {
          setSocialProgress(0); setSocialProgressText(''); setSocialLoading(false);
          setSocialModalVisible(false);
          try {
            const refreshRes = await apiWithFallback('/leads/', 'get', null, {
              params: { page: 1, per_page: pageSize }
            });
            if (refreshRes.data?.leads) {
              setLeads(refreshRes.data.leads.map(lead => ({
                ...lead,
                score: lead.qualification_score != null ? Math.round(lead.qualification_score) : 0,
                status: lead.status || 'cold',
                company: lead.company || 'N/A',
              })));
              setTotalLeads(refreshRes.data.total || refreshRes.data.leads.length);
            }
          } catch (e) { console.error('Refresh failed:', e); }
        }, 2000);
        return;
      }

      // Poll for real progress — 1s intervals, 6 min max
      let pollCount = 0;
      const maxPolls = 360;
      let lastActivePlatform = '';

      const refreshLeads = async () => {
        try {
          const refreshRes = await apiWithFallback('/leads/', 'get', null, { params: { page: 1, per_page: pageSize } });
          if (refreshRes.data?.leads) {
            setLeads(refreshRes.data.leads.map(lead => ({
              ...lead,
              score: lead.qualification_score != null ? Math.round(lead.qualification_score) : 0,
              status: lead.status || 'cold',
              company: lead.company || 'N/A',
            })));
            setTotalLeads(refreshRes.data.total || refreshRes.data.leads.length);
          }
        } catch (e) { console.error('Refresh failed:', e); }
      };

      const pollInterval = setInterval(async () => {
        pollCount++;
        try {
          const statusRes = await apiWithFallback(`/ai/collect-social/status/${taskId}`, 'get', null, { timeout: 5000 });
          const task = statusRes.data?.data || {};
          const pct = task.percent || 0;
          const platform = task.current_platform || '';
          const saved = task.saved || 0;
          const collected = task.total_collected || 0;
          const completedCount = task.completed_platforms || 0;

          setSocialProgress(pct);

          // Per-platform lead counts from backend (demo sends this as live dict)
          const platformLeads = task.platform_leads || {};
          const totalPlatforms = task.total_platforms || chosenPlatforms.length;
          const isScoring = platform === 'scoring';
          const isSaving  = platform === 'saving';

          // Update per-platform status + live lead counts
          setSocialPlatformResults(prev => prev.map((r, i) => {
            const liveCount = platformLeads[r.platform] ?? r.leads;
            if (i < completedCount) return { ...r, status: 'done', leads: liveCount };
            if (r.platform === platform && !isScoring && !isSaving)
              return { ...r, status: 'active', leads: liveCount };
            return { ...r, leads: liveCount };
          }));
          if (platform && platform !== lastActivePlatform && !isScoring && !isSaving)
            lastActivePlatform = platform;

          const totalFound = Object.values(platformLeads).reduce((a, b) => a + b, 0);
          if (isSaving) {
            setSocialProgressText(`💾 Saving ${totalFound} leads to database...`);
          } else if (isScoring) {
            setSocialProgressText(`🤖 Scoring ${totalFound} leads with XGBoost...`);
          } else if (platform) {
            const emoji = platformEmojis[platform] || '🔍';
            const platformCount = platformLeads[platform] || 0;
            setSocialProgressText(`${emoji} ${platform.charAt(0).toUpperCase() + platform.slice(1)}: ${platformCount} leads found (${completedCount}/${totalPlatforms} done)`);
          } else if (pct > 0) {
            setSocialProgressText(`Connecting to social platforms...`);
          }

          if (task.status === 'done' || task.status === 'error' || pct >= 100) {
            clearInterval(pollInterval);
            setSocialProgress(100);
            // Mark all platforms done, preserve final lead counts
            const finalPlatformLeads = task.platform_leads || {};
            setSocialPlatformResults(prev => prev.map(r => ({
              ...r,
              status: task.status === 'error' ? 'error' : 'done',
              leads: finalPlatformLeads[r.platform] ?? r.leads,
            })));

            if (task.status === 'error') {
              setSocialProgressText('Collection failed');
              message.error('Social collection encountered an error');
              setSocialResult({ status: 'error', message: 'Collection failed' });
            } else {
              const socialDupes = task.duplicates || 0;
              let msg, progressMsg;
              if (saved === 0 && collected > 0) {
                if (socialDupes >= collected) {
                  msg = `No new leads — all ${collected} already in database`;
                  progressMsg = `⚠️ 0 saved (all duplicates)`;
                  message.info(msg);
                } else if (socialDupes > 0) {
                  msg = `Collected ${collected}, saved 0 (${socialDupes} duplicates, ${collected - socialDupes} rejected)`;
                  progressMsg = `⚠️ 0 saved (${socialDupes} duplicates)`;
                  message.warning(msg);
                } else {
                  msg = `Collected ${collected} leads, saved 0 new`;
                  progressMsg = `⚠️ 0 saved (rejected by intelligence gate)`;
                  message.warning(msg);
                }
              } else {
                msg = `Collected ${collected} leads, saved ${saved} new`;
                progressMsg = `✅ ${msg}`;
                message.success(msg);
              }
              setSocialProgressText(progressMsg);
              setSocialResult({ status: 'success', message: msg, data: task });
              setCurrentPage(1); setSearchText(''); setFilterStatus(''); setFilterSource('');
              await refreshLeads();
            }

            setTimeout(() => {
              setSocialProgress(0); setSocialProgressText(''); setSocialLoading(false);
              setSocialPlatformResults([]);
              setSocialModalVisible(false);
            }, 2500);
          }
        } catch {
          // Status endpoint failed — keep polling silently
        }

        if (pollCount >= maxPolls) {
          clearInterval(pollInterval);
          setSocialProgress(100);
          setSocialProgressText('✅ Collection completed');
          message.success('Social collection finished');
          setCurrentPage(1);
          await refreshLeads();
          setTimeout(() => {
            setSocialProgress(0); setSocialProgressText(''); setSocialLoading(false);
            setSocialPlatformResults([]);
            setSocialModalVisible(false);
          }, 2000);
        }
      }, 1000);

    } catch (error) {
      setSocialProgress(0);
      setSocialProgressText('');
      setSocialLoading(false);
      const errMsg = error?.response?.data?.message || error?.message || 'Unknown error';
      message.error('Social collection failed: ' + errMsg);
      setSocialResult({ status: 'error', message: errMsg });
    }
  };

  const openAutoCollect = async () => {
    setAutoCollectResult(null);
    setAutoCollectProgress(0);
    setAutoCollectVisible(true);
    try {
      const res = await apiWithFallback('/ai/collect/auto/sources', 'get');
      setAutoCollectSources(res.data || {});
    } catch (_) {}
  };

  const handleAutoCollect = async (values) => {
    setAutoCollectLoading(true);
    setAutoCollectResult(null);
    setAutoCollectProgress(0);
    setAutoCollectElapsed(0);

    const _t0 = Date.now();
    autoCollectElapsedRef.current = setInterval(() => {
      setAutoCollectElapsed(Math.round((Date.now() - _t0) / 1000));
    }, 1000);

    const _stopTimers = () => {
      clearInterval(autoCollectElapsedRef.current);
      clearInterval(autoCollectNudgeRef.current);
    };

    try {
      const payload = {
        keywords:                  values.keywords   || '',
        titles:                    values.titles     || [],
        locations:                 values.locations  || [],
        industries:                values.industries || [],
        domains:                   values.domains ? values.domains.split(',').map(d => d.trim()).filter(Boolean) : [],
        limit:                     values.limit  || 25,
        interest_product_category: values.interest_product_category || '',
        interest_target_industry:  values.interest_target_industry  || '',
        interest_buying_intent:    values.interest_buying_intent    || '',
        interest_country:          values.interest_country          || '',
        interest_city:             values.interest_city             || '',
      };
      const res = await apiWithFallback('/ai/collect/auto', 'post', payload);
      const taskId = res.data?.task_id;
      message.loading({ content: 'Pipeline running: Apollo → Hunter → PDL → AI…', key: 'autoCollect', duration: 0 });

      // Nudge progress +1% every 2s so bar always moves while running
      autoCollectNudgeRef.current = setInterval(() => {
        setAutoCollectProgress(prev => (prev < 82 ? prev + 1 : prev));
      }, 2000);

      let _pollErrors = 0;
      const poll = async () => {
        try {
          const st = await apiWithFallback(`/ai/collect/auto/status/${taskId}`, 'get');
          _pollErrors = 0; // reset on successful response
          const { status, percent = 0, saved = 0, collected = 0, sources = [], message: srvMsg } = st.data || {};
          setAutoCollectProgress(prev => Math.max(prev, percent));
          if (status === 'done') {
            _stopTimers();
            message.destroy('autoCollect');
            setAutoCollectResult({ saved, collected, sources });
            setAutoCollectLoading(false);
            if (saved === 0) message.warning(srvMsg || 'Pipeline complete — no leads met quality requirements');
            await fetchLeads();
          } else if (status === 'error') {
            _stopTimers();
            message.destroy('autoCollect');
            message.error('Auto-collect pipeline failed: ' + (srvMsg || 'check server logs'));
            setAutoCollectLoading(false);
            await fetchLeads();
          } else {
            setTimeout(poll, 2000);
          }
        } catch (_) {
          _pollErrors++;
          if (_pollErrors >= 3) {
            _stopTimers();
            message.destroy('autoCollect');
            message.warning('Lost connection to server — pipeline may still be running. Check leads table in a moment.');
            setAutoCollectLoading(false);
            await fetchLeads();
          } else {
            setTimeout(poll, 3000); // retry after a longer wait
          }
        }
      };
      setTimeout(poll, 3000);
    } catch (error) {
      _stopTimers();
      message.destroy('autoCollect');
      message.error('Auto-collect failed: ' + (error?.response?.data?.message || error?.message || 'Unknown'));
      setAutoCollectLoading(false);
    }
  };

  // eslint-disable-next-line no-unused-vars
  const handleEnrichWithClearbit = async () => {
    try {
      setLoading(true);
      message.loading('Enriching leads with Clearbit data from real sources...');
      
      const response = await apiWithFallback('/leads/enrich', 'post', {
        lead_ids: leads.slice(0, 5).map(l => l.id)  // Enrich first 5 (free tier limit)
      });
      
      if (response.data.enriched > 0) {
        message.success(`✓ Enriched ${response.data.enriched} leads with real company data (Industry, Tech Stack, Location)`);
        fetchLeads();
      } else if (response.data.status === 'unconfigured') {
        message.warning('Clearbit not configured. Please set CLEARBIT_API_KEY');
      } else {
        message.info('No leads enriched (check Clearbit API configuration)');
      }
    } catch (error) {
      if (error.message?.includes('unconfigured') || error.message?.includes('400')) {
        message.warning('Clearbit API key not configured. Check CLEARBIT_SETUP.md for instructions');
      } else {
        message.error('Failed to enrich leads: ' + (error?.message || 'Unknown error'));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleAssignLead = async (leadId, userId) => {
    setAssignLoading(true);
    try {
      const res = await apiWithFallback(`/leads/${leadId}/assign`, 'patch', { user_id: userId });
      const { assigned_to, assigned_to_name } = res.data;
      setLeads(prev => prev.map(l =>
        l.id === leadId ? { ...l, assigned_to, assigned_to_name } : l
      ));
      setSelectedLead(prev => prev?.id === leadId ? { ...prev, assigned_to, assigned_to_name } : prev);
      message.success(userId ? `Lead claimed by ${assigned_to_name || 'you'}` : 'Lead unassigned');
    } catch (err) {
      message.error(err?.response?.data?.message || 'Assignment failed');
    } finally {
      setAssignLoading(false);
    }
  };

  const handleRefreshSingleLeadWithAI = async (lead) => {
    setLoadingAILeadId(lead.id);
    const prevScore = lead.score ?? lead.qualification_score ?? 0;
    message.loading({ content: `Queuing AI score for ${lead.name || 'lead'}…`, key: `ai_${lead.id}`, duration: 0 });
    try {
      // Dispatch — returns 202 + task_id immediately
      const dispatch = await apiWithFallback(`/ai/refresh-lead/${lead.id}`, 'post', {}, { timeout: 10000 });
      const taskId = dispatch.data?.task_id;
      if (!taskId) throw new Error('No task_id returned');

      message.loading({ content: `AI scoring ${lead.name || 'lead'}…`, key: `ai_${lead.id}`, duration: 0 });

      // Poll until done (max 60 × 3s = 3 min)
      let d = null;
      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 3000));
        const poll = await apiWithFallback(`/ai/task-status/${taskId}`, 'get', null, { timeout: 8000 });
        const { status, result, error: taskError } = poll.data || {};
        if (status === 'SUCCESS') { d = result || {}; break; }
        if (status === 'FAILURE') throw new Error(taskError || 'AI scoring failed');
      }
      if (!d) throw new Error('AI scoring timed out');

      const score = d.new_score ?? d.score;
      const cat   = (d.category || '').toLowerCase();
      const provider = d.ai_provider || 'AI';
      const changeStr = score != null && Math.round(score) !== Math.round(prevScore)
        ? ` (was ${Math.round(prevScore)})`
        : ' (score unchanged)';
      message.success({ content: `${lead.name || 'Lead'} → ${cat.toUpperCase()} ${Math.round(score ?? 0)}%${changeStr} via ${provider}`, key: `ai_${lead.id}`, duration: 4 });
      if (score != null) {
        setLeads(prev => prev.map(l =>
          l.id === lead.id
            ? { ...l, score: Math.round(score), qualification_score: score, status: cat || l.status }
            : l
        ));
      }
      fetchLeads();
    } catch (error) {
      message.error({ content: 'Groq/Gemini score failed: ' + (error?.response?.data?.message || error?.message || 'Unknown error'), key: `ai_${lead.id}` });
    } finally {
      setLoadingAILeadId(null);
    }
  };

  const handleMLQualifySingleLead = async (lead) => {
    setLoadingLeadId(lead.id);
    const prevScore = lead.score ?? lead.qualification_score ?? 0;
    message.loading({ content: `ML scoring ${lead.name || 'lead'}…`, key: `ml_${lead.id}`, duration: 0 });
    try {
      const res = await apiWithFallback(`/ai/qualify/${lead.id}`, 'post', { fast: true });
      const d = res.data || {};
      const score = d.score ?? d.qualification_score;
      const cat = (d.category || '').toLowerCase();
      const changeStr = score != null && Math.round(score) !== Math.round(prevScore)
        ? ` (was ${Math.round(prevScore)})`
        : ' (score unchanged)';
      message.success({ content: `ML: ${lead.name || 'Lead'} → ${cat.toUpperCase()} ${Math.round(score ?? 0)}%${changeStr}`, key: `ml_${lead.id}`, duration: 4 });
      if (score != null) {
        setLeads(prev => prev.map(l =>
          l.id === lead.id
            ? { ...l, score: Math.round(score), qualification_score: score, status: cat || l.status }
            : l
        ));
      }
      fetchLeads();
    } catch (error) {
      message.error({ content: 'ML score failed: ' + (error?.response?.data?.message || error?.message || 'Unknown error'), key: `ml_${lead.id}` });
    } finally {
      setLoadingLeadId(null);
    }
  };

  const handleAIAnalyze = async (lead) => {
    setAiAnalysis(null);
    setAiAnalysisLoading(true);
    try {
      const response = await apiWithFallback(`/ai/analyze-lead/${lead.id}`, 'post', {});
      setAiAnalysis(response.data);
      message.success(`AI analysis complete for ${lead.name}`);
      // Refresh lead details so status/tier reflect the latest DB values
      try {
        const refreshed = await apiWithFallback(`/leads/${lead.id}`, 'get');
        const freshLead = refreshed.data?.lead || refreshed.data;
        if (freshLead) {
          setSelectedLead({
            ...freshLead,
            score: freshLead.qualification_score != null ? Math.round(freshLead.qualification_score) : 0,
          });
        }
      } catch (_) { /* non-fatal */ }
    } catch (error) {
      message.error('AI analysis failed: ' + (error?.message || 'Unknown error'));
    } finally {
      setAiAnalysisLoading(false);
    }
  };

  const handleAIGenerateEmail = async (lead) => {
    setAiEmail(null);
    setAiEmailLoading(true);
    try {
      const response = await apiWithFallback(`/ai/generate-email/${lead.id}`, 'post', {
        email_type: aiEmailType,
        tone: aiEmailTone,
      });
      setAiEmail(response.data);
      message.success('AI email generated!');
    } catch (error) {
      message.error('Email generation failed: ' + (error?.message || 'Unknown error'));
    } finally {
      setAiEmailLoading(false);
    }
  };

  const handleCopyEmail = () => {
    if (aiEmail?.email) {
      const text = `Subject: ${aiEmail.email.subject}\n\n${aiEmail.email.body}`;
      navigator.clipboard.writeText(text);
      message.success('Email copied to clipboard');
    }
  };

  const getStatusColor = (status) => {
    const s = status ? status.toLowerCase() : 'cold';
    const map = {
      // AI category labels
      hot:             { bg: 'rgba(34,197,94,0.12)',   color: '#22c55e' },
      warm:            { bg: 'rgba(245,158,11,0.12)',   color: '#f59e0b' },
      cold:            { bg: 'rgba(100,116,139,0.12)',  color: '#64748b' },
      // Validator / system statuses
      qualified:       { bg: 'rgba(34,197,94,0.12)',   color: '#22c55e' },
      pending:         { bg: 'rgba(245,158,11,0.12)',   color: '#f59e0b' },
      low_quality:     { bg: 'rgba(239,68,68,0.10)',    color: '#ef4444' },
      rejected:        { bg: 'rgba(239,68,68,0.14)',    color: '#dc2626' },
      // 4-tier collection policy statuses
      validated:       { bg: 'rgba(34,197,94,0.15)',   color: '#16a34a' },
      semi_validated:  { bg: 'rgba(6,182,212,0.13)',   color: '#0891b2' },
      unvalidated:     { bg: 'rgba(100,116,139,0.10)', color: '#64748b' },
      needs_review:    { bg: 'rgba(245,158,11,0.13)',  color: '#d97706' },
    };
    return map[s] || { bg: 'rgba(100,116,139,0.10)', color: '#64748b' };
  };

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      width: 120,
      render: (text) => <span style={{ fontWeight: 500, color: 'var(--text-stat)' }}>{text}</span>,
    },
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
      width: 150,
      render: (text) => <span style={{ color: '#94a3b8', fontSize: '12px' }}>{text}</span>,
    },
    {
      title: 'Company',
      dataIndex: 'company',
      key: 'company',
      width: 120,
      render: (text) => <span style={{ color: '#94a3b8' }}>{text}</span>,
    },
    {
      title: 'Interest',
      dataIndex: 'interests',
      key: 'interests',
      width: 160,
      render: (interests) => {
        if (!Array.isArray(interests) || interests.length === 0) {
          return <span style={{ color: isDark ? '#334155' : '#cbd5e1', fontSize: '11px' }}>No interest</span>;
        }
        const _P = {
          'AI Tools':          '#6366f1',
          'Cloud Solutions':   '#0ea5e9',
          'CRM Software':      '#f59e0b',
          'Data Analytics':    '#10b981',
          'Digital Marketing': '#f97316',
          'Cybersecurity':     '#ef4444',
          'Machine Learning':  '#8b5cf6',
          'IoT':               '#14b8a6',
          'Blockchain':        '#a855f7',
          'Fintech':           '#3b82f6',
          'E-commerce':        '#ec4899',
          'Real Estate':       '#78716c',
          'DevOps':            '#0891b2',
          'Automation':        '#65a30d',
          'SaaS':              '#6366f1',
        };
        const matchLower = filterInterest ? filterInterest.toLowerCase() : '';
        const visible = interests.slice(0, 2);
        const overflow = interests.length - visible.length;
        return (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}>
            {visible.map((interest, idx) => {
              const isMatch = matchLower && interest.toLowerCase().includes(matchLower);
              const clr = _P[interest] || '#6366f1';
              const dimmed = matchLower && !isMatch;
              return (
                <span key={idx} style={{
                  display: 'inline-flex', alignItems: 'center',
                  fontSize: 10, fontWeight: isMatch ? 700 : 500,
                  padding: '3px 8px', borderRadius: 12,
                  background: isMatch
                    ? `${clr}28`
                    : dimmed
                    ? (isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)')
                    : `${clr}18`,
                  border: `1.5px solid ${isMatch ? `${clr}aa` : dimmed ? (isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)') : `${clr}55`}`,
                  color: isMatch ? clr : dimmed ? (isDark ? '#475569' : '#94a3b8') : clr,
                  opacity: dimmed ? 0.5 : 1,
                  boxShadow: isMatch ? `0 0 0 2px ${clr}22` : 'none',
                  whiteSpace: 'nowrap',
                  transition: 'all 0.15s',
                }}>{interest}</span>
              );
            })}
            {overflow > 0 && (
              <span style={{
                fontSize: 9, fontWeight: 600, padding: '2px 5px', borderRadius: 8,
                background: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)',
                color: isDark ? '#64748b' : '#94a3b8',
              }}>+{overflow}</span>
            )}
          </div>
        );
      },
    },
    {
      title: 'Location',
      dataIndex: 'location',
      key: 'location',
      width: 120,
      render: (loc, record) => (
        <span style={{ color: '#94a3b8', fontSize: '12px' }}>
          {record.country ? `${record.city || ''} ${record.country}`.trim() : loc || '–'}
        </span>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'lead_type',
      key: 'lead_type',
      width: 90,
      filters: [
        { text: 'Company', value: 'company' },
        { text: 'Person', value: 'person' },
      ],
      onFilter: (value, record) => (record.lead_type || '') === value,
      render: (type) => {
        if (!type) return <span style={{ color: '#475569', fontSize: '12px' }}>–</span>;
        const isCompany = type === 'company';
        return (
          <Tag style={{
            background: isCompany ? 'rgba(99,102,241,0.12)' : 'rgba(34,197,94,0.12)',
            color: isCompany ? '#818cf8' : '#4ade80',
            border: 'none', fontWeight: 600, fontSize: 11,
          }}>
            {isCompany ? '🏢 Company' : '👤 Person'}
          </Tag>
        );
      },
    },
    {
      title: 'Industry',
      dataIndex: 'industry',
      key: 'industry',
      width: 110,
      render: (industry) => (
        <span style={{ color: '#94a3b8', fontSize: '12px' }}>
          {industry ? industry.replace('_', ' ') : '–'}
        </span>
      ),
    },
    {
      title: 'Quality',
      key: 'quality',
      width: 110,
      render: (_, record) => {
        const dp = record.data_points || {};
        // Score-derived tier is always current; fall back to stored quality_tier for
        // leads that have no qualification_score yet (e.g. manually created).
        const tier = getTierFromScore(record.score) || dp.quality_tier || '';
        const emailType = record.email_type || dp.email_type || '';
        const emailVerified = dp.email_verified || false;
        const emailConf = dp.email_confidence != null ? Math.round(dp.email_confidence * 100) : null;
        const srcRel = dp.source_reliability_score != null ? Math.round(dp.source_reliability_score) : null;
        const tierStyle = getQualityTierStyle(tier);
        const emailStyle = getEmailTypeStyle(emailType);

        const tooltipContent = (
          <div style={{ fontSize: 12, minWidth: 160 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Quality Details</div>
            {tier && <div>Tier: <span style={{ color: tierStyle.color }}>{tier}</span></div>}
            {emailType && <div>Email type: <span style={{ color: emailStyle.color }}>{emailType}</span></div>}
            <div>Email verified: <span style={{ color: emailVerified ? '#4ade80' : '#f87171' }}>{emailVerified ? 'Yes' : 'No'}</span></div>
            {emailConf != null && <div>Email confidence: {emailConf}%</div>}
            {srcRel != null && <div>Source reliability: {srcRel}/100</div>}
          </div>
        );

        return (
          <Tooltip title={tooltipContent} placement="left">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              {tier ? (
                <Tag style={{ background: tierStyle.bg, color: tierStyle.color, border: 'none', fontWeight: 600, fontSize: 10, margin: 0 }}>
                  {tierStyle.label}
                </Tag>
              ) : null}
              {emailType ? (
                <span style={{ fontSize: 10, color: emailStyle.color }}>
                  {emailStyle.label}
                  {emailVerified && <span style={{ color: '#4ade80', marginLeft: 3 }}>✓</span>}
                </span>
              ) : null}
            </div>
          </Tooltip>
        );
      },
    },
    {
      title: 'Score',
      dataIndex: 'score',
      key: 'score',
      width: 80,
      sorter: (a, b) => a.score - b.score,
      render: (score, record) => {
        const hasEmail = !!record.email;
        const hasPhone = !!record.phone;
        const dp = record.data_points || {};
        const emailVerified = dp.email_verified || false;
        const missing = [];
        if (!hasEmail) missing.push('email');
        if (!hasPhone) missing.push('phone');
        if (!record.position) missing.push('position');
        if (!record.industry) missing.push('industry');
        const tooltipContent = (
          <div style={{ fontSize: 12 }}>
            <div style={{ marginBottom: 4, fontWeight: 600 }}>Score: {score}/100</div>
            {hasEmail && <div style={{ color: emailVerified ? '#22c55e' : '#fbbf24' }}>{emailVerified ? '✓' : '~'} Email{emailVerified ? ' (verified)' : ' (unverified)'}</div>}
            {hasPhone && <div style={{ color: '#22c55e' }}>✓ Phone</div>}
            {missing.length > 0 && (
              <div style={{ color: '#f87171', marginTop: 4 }}>Missing: {missing.join(', ')}</div>
            )}
          </div>
        );
        return (
          <Tooltip title={tooltipContent} placement="left">
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
              <Progress
                percent={score}
                type="circle"
                width={34}
                strokeColor={score >= 80 ? '#22c55e' : score >= 60 ? '#818cf8' : score >= 35 ? '#f59e0b' : '#ef4444'}
              />
              <div style={{ display: 'flex', gap: 3 }}>
                <span style={{ fontSize: 10, color: hasEmail ? (emailVerified ? '#22c55e' : '#fbbf24') : '#475569' }} title={hasEmail ? (emailVerified ? 'Verified email' : 'Unverified email') : 'No email'}>✉</span>
                <span style={{ fontSize: 10, color: hasPhone ? '#22c55e' : '#475569' }} title={hasPhone ? 'Has phone' : 'No phone'}>☎</span>
              </div>
            </div>
          </Tooltip>
        );
      },
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status) => {
        const statusLower = (status || 'cold').toLowerCase();
        const colors = getStatusColor(status);
        const icon = statusLower === 'hot' ? '🔥' : statusLower === 'warm' ? '☀' : statusLower === 'cold' ? '❄' : null;
        const label = statusLower === 'low_quality' ? 'LOW' : statusLower.toUpperCase();
        return (
          <Tag style={{ background: colors.bg, color: colors.color, border: 'none', fontWeight: 700, fontSize: 11, letterSpacing: '0.4px' }}>
            {icon
              ? <>{icon} {label}</>
              : <><span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: colors.color, marginRight: 6, verticalAlign: 'middle' }} />{label}</>
            }
          </Tag>
        );
      },
    },
    {
      title: 'Actions',
      key: 'action',
      width: 210,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="View Details">
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              style={{ color: '#6366f1' }}
              onClick={() => { setAiAnalysis(null); setAiEmail(null); handleShowDetail(record); }}
            />
          </Tooltip>
          <Tooltip title="AI Deep Analysis">
            <Button
              type="text"
              size="small"
              icon={<RobotOutlined />}
              style={{ color: '#22c55e' }}
              onClick={() => { setAiAnalysis(null); setAiEmail(null); handleShowDetail(record); handleAIAnalyze(record); }}
            />
          </Tooltip>
          <Tooltip title="ML Re-score (fast, no API)">
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              style={{ color: '#f59e0b' }}
              onClick={() => handleMLQualifySingleLead(record)}
              loading={loadingLeadId === record.id}
            />
          </Tooltip>
          <Tooltip title="Groq/Gemini deep AI score">
            <Button
              type="text"
              size="small"
              icon={<ThunderboltOutlined />}
              style={{ color: '#a855f7' }}
              onClick={() => handleRefreshSingleLeadWithAI(record)}
              loading={loadingAILeadId === record.id}
            />
          </Tooltip>
          <Popconfirm title="Delete this lead?" onConfirm={() => handleDeleteLead(record.id)}>
            <Button type="text" size="small" icon={<DeleteOutlined />} danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const filteredLeads = leads; // Do NOT slice - API already returns paginated data

  return (
    <div style={{ padding: '20px' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>

        {/* Title row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700, color: isDark ? '#f1f5f9' : '#0f172a' }}>Leads Management</h1>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setAddModalVisible(true)}
            size="large"
            style={{ background: '#7c3aed', borderColor: '#7c3aed', fontWeight: 600, borderRadius: 10 }}
          >
            Add Lead
          </Button>
        </div>

        {/* Action bar */}
        <div style={{
          display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 10,
          background: isDark ? '#0f172a' : '#f8fafc',
          border: `1px solid ${isDark ? 'rgba(99,102,241,0.12)' : '#e2e8f0'}`,
          borderRadius: 14, padding: '12px 18px',
        }}>

          {/* ── Collect ── */}
          <div>
            <div style={{
              fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1.4,
              color: isDark ? '#475569' : '#94a3b8', marginBottom: 8,
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <span style={{ display: 'inline-block', width: 16, height: 1.5, borderRadius: 2, background: isDark ? '#1e293b' : '#e2e8f0' }} />
              Collect
              <span style={{ display: 'inline-block', width: 16, height: 1.5, borderRadius: 2, background: isDark ? '#1e293b' : '#e2e8f0' }} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {[
                { icon: <RocketOutlined />, label: 'Auto',     sub: 'AI pipeline', color: '#7c3aed', filled: true,  onClick: openAutoCollect,                       tip: 'Automated pipeline: Hunter → PDL → AI enrichment' },
                { icon: <GlobalOutlined />, label: 'Web',      sub: 'Web scrape',  color: '#0891b2', filled: false, onClick: () => setCollectModalVisible(true),   tip: 'Scrape leads from public web pages and directories' },
                { icon: <TeamOutlined />,   label: 'Social',   sub: 'Networks',    color: '#059669', filled: false, onClick: () => setSocialModalVisible(true),    tip: 'Find leads from public social media groups' },
                { icon: <AimOutlined />,    label: 'Interest', sub: 'By category', color: '#d97706', filled: false, onClick: () => { setInterestModalVisible(true); setInterestResult(null); }, tip: 'Collect leads by product/service interest category' },
              ].map(({ icon, label, sub, color, filled, onClick, tip }) => (
                <Tooltip key={label} title={tip} placement="bottom">
                  <button
                    onClick={onClick}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                      width: 88, height: 44,
                      border: `1.5px solid ${color}`,
                      borderRadius: 10,
                      background: filled
                        ? `linear-gradient(135deg, ${color}, ${color}cc)`
                        : (isDark ? 'rgba(255,255,255,0.03)' : '#fff'),
                      boxShadow: filled ? `0 4px 14px ${color}44` : 'none',
                      cursor: 'pointer',
                      outline: 'none',
                      transition: 'opacity 0.15s',
                      flexShrink: 0,
                    }}
                    onMouseEnter={e => { e.currentTarget.style.opacity = '0.85'; }}
                    onMouseLeave={e => { e.currentTarget.style.opacity = '1'; }}
                  >
                    <span style={{ fontSize: 14, lineHeight: 1, display: 'flex', color: filled ? '#fff' : color }}>
                      {icon}
                    </span>
                    <div style={{ textAlign: 'left' }}>
                      <div style={{ fontSize: 12, fontWeight: 700, lineHeight: 1.3, whiteSpace: 'nowrap', color: filled ? '#fff' : (isDark ? '#e2e8f0' : '#1e293b') }}>
                        {label}
                      </div>
                      <div style={{ fontSize: 10, fontWeight: 500, lineHeight: 1.2, whiteSpace: 'nowrap', color: filled ? 'rgba(255,255,255,0.72)' : color }}>
                        {sub}
                      </div>
                    </div>
                  </button>
                </Tooltip>
              ))}
            </div>
          </div>

          {/* ── Danger (admin only) ── */}
          {localStorage.getItem('userRole') === 'admin' && (
            <>
              <Divider type="vertical" style={{ height: 48, margin: '0 4px', borderColor: isDark ? 'rgba(99,102,241,0.18)' : '#e2e8f0' }} />
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#ef4444', marginBottom: 6 }}>Admin</div>
                <Popconfirm
                  title="Delete ALL leads?"
                  description="This will permanently remove every lead from the database. You cannot undo this."
                  onConfirm={handleClearAllLeads}
                  okText="Yes, Delete All"
                  okType="danger"
                  cancelText="Cancel"
                >
                  <Button danger icon={<DeleteOutlined />} loading={loading} style={{ background: 'transparent', borderRadius: 8 }}>
                    Clear All
                  </Button>
                </Popconfirm>
              </div>
            </>
          )}
        </div>
      </div>


      {/* Filters */}
      <Card 
        style={{ marginBottom: '24px', borderRadius: '12px' }} 
        bodyStyle={{ padding: '16px 20px' }}
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <FilterOutlined style={{ color: '#6366f1' }} />
            <span style={{ fontSize: '14px', fontWeight: 600 }}>Filter & Search</span>
            <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 400, marginLeft: '8px' }}>
              {(searchText || filterStatus || filterInterest || filterLocation || filterSource || filterCountry || filterIndustry || filterQualityTier || filterVerifiedEmail)
                ? 'Filters active' : 'No filters applied'}
            </span>
          </div>
        }
        extra={
          <Space>
            <Button size="small" icon={<DownloadOutlined />} onClick={handleExportCSV} loading={exporting}>
              Export CSV
            </Button>
            <Button size="small" icon={<ClearOutlined />} onClick={handleClearFilters}>
              Clear All
            </Button>
          </Space>
        }
      >
        <Row gutter={[12, 12]}>
          <Col xs={24} sm={12} md={8}>
            <Input
              placeholder="Search by name, email, company..."
              prefix={<SearchOutlined style={{ color: '#64748b' }} />}
              value={searchText}
              onChange={(e) => {
                setSearchText(e.target.value);
                setCurrentPage(1);
              }}
              allowClear
              style={{ borderRadius: '8px' }}
            />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              placeholder="Status"
              value={filterStatus || undefined}
              onChange={(value) => {
                setFilterStatus(value || '');
                setCurrentPage(1);
              }}
              allowClear
              options={[
                { label: '🔥 Hot', value: 'hot' },
                { label: '🟡 Warm', value: 'warm' },
                { label: '🔵 Cold', value: 'cold' },
              ]}
              style={{ width: '100%', borderRadius: '8px' }}
            />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              placeholder="Industry"
              value={filterIndustry || undefined}
              onChange={(value) => {
                setFilterIndustry(value || '');
                setCurrentPage(1);
              }}
              allowClear
              showSearch
              options={[
                { label: 'Technology', value: 'technology' },
                { label: 'Healthcare', value: 'healthcare' },
                { label: 'Finance', value: 'finance' },
                { label: 'Manufacturing', value: 'manufacturing' },
                { label: 'Retail', value: 'retail' },
                { label: 'Real Estate', value: 'real_estate' },
                { label: 'Education', value: 'education' },
                { label: 'Consulting', value: 'consulting' },
                { label: 'Marketing', value: 'marketing' },
                { label: 'Logistics', value: 'logistics' },
                { label: 'Food & Beverage', value: 'food_beverage' },
                { label: 'Energy', value: 'energy' },
                { label: 'Automotive', value: 'automotive' },
                { label: 'Telecom', value: 'telecom' },
                { label: 'AI/ML', value: 'AI/ML' },
                { label: 'SaaS', value: 'SaaS' },
                { label: 'E-commerce', value: 'E-commerce' },
              ]}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              placeholder="Country"
              value={filterCountry || undefined}
              onChange={(value) => {
                setFilterCountry(value || '');
                setCurrentPage(1);
              }}
              showSearch
              allowClear
              options={supportedCountries.map(c => ({
                label: c.name,
                value: c.name,
              }))}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              placeholder="Interest"
              value={filterInterest || undefined}
              onChange={(value) => {
                setFilterInterest(value || '');
                setCurrentPage(1);
              }}
              allowClear
              showSearch
              options={[
                { label: 'AI Tools',          value: 'AI Tools' },
                { label: 'Cloud Solutions',   value: 'Cloud Solutions' },
                { label: 'CRM Software',      value: 'CRM Software' },
                { label: 'Data Analytics',    value: 'Data Analytics' },
                { label: 'Digital Marketing', value: 'Digital Marketing' },
                { label: 'Cybersecurity',     value: 'Cybersecurity' },
                { label: 'Machine Learning',  value: 'Machine Learning' },
                { label: 'IoT',               value: 'IoT' },
                { label: 'Blockchain',        value: 'Blockchain' },
                { label: 'Fintech',           value: 'Fintech' },
                { label: 'E-commerce',        value: 'E-commerce' },
                { label: 'Real Estate',       value: 'Real Estate' },
                { label: 'DevOps',            value: 'DevOps' },
                { label: 'Automation',        value: 'Automation' },
                { label: 'SaaS',              value: 'SaaS' },
              ]}
              style={{ width: '100%' }}
            />
          </Col>
        </Row>
        <Row gutter={[12, 12]} style={{ marginTop: '12px' }}>
          <Col xs={24} sm={12} md={6}>
            <Input
              placeholder="Filter by location (e.g. Dubai, London)"
              prefix={<AimOutlined style={{ color: '#64748b' }} />}
              value={filterLocation}
              onChange={(e) => {
                setFilterLocation(e.target.value);
                setCurrentPage(1);
              }}
              allowClear
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Select
              placeholder="Source"
              value={filterSource || undefined}
              onChange={(value) => {
                setFilterSource(value || '');
                setCurrentPage(1);
              }}
              allowClear
              options={[
                { label: '🌐 Web Public', value: 'web_public' },
                { label: '🔵 Hunter.io', value: 'hunter' },
                { label: '🟣 PDL', value: 'pdl' },
                { label: '🟤 Clearbit', value: 'clearbit' },
                { label: '🟢 Apollo', value: 'apollo' },
                { label: '🟠 Reddit', value: 'reddit' },
                { label: '🔵 Telegram', value: 'telegram' },
                { label: '🐦 Twitter', value: 'twitter' },
                { label: '📘 Facebook', value: 'facebook' },
                { label: '💼 LinkedIn', value: 'linkedin' },
                { label: '✏️ Manual', value: 'manual' },
              ]}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              placeholder="Quality Tier"
              value={filterQualityTier || undefined}
              onChange={(value) => {
                setFilterQualityTier(value || '');
                setCurrentPage(1);
              }}
              allowClear
              options={[
                { label: '★ High Quality', value: 'high_quality' },
                { label: '✓ Validated',    value: 'qualified' },
                { label: '◷ Pending',      value: 'pending' },
                { label: '↓ Low Quality',  value: 'low_quality' },
              ]}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              placeholder="Verified Email"
              value={filterVerifiedEmail ? 'verified' : undefined}
              onChange={(value) => {
                setFilterVerifiedEmail(value === 'verified');
                setCurrentPage(1);
              }}
              allowClear
              options={[
                { label: '✓ Verified Email Only', value: 'verified' },
              ]}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              placeholder="Buying Intent"
              value={filterBuyingIntent || undefined}
              onChange={(value) => {
                setFilterBuyingIntent(value || '');
                setCurrentPage(1);
              }}
              allowClear
              options={[
                { label: '🔥 High Intent',   value: 'high' },
                { label: '🟡 Medium Intent', value: 'medium' },
                { label: '🔵 Low Intent',    value: 'low' },
                { label: '⬜ No Intent',     value: 'none' },
              ]}
              style={{ width: '100%' }}
            />
          </Col>
        </Row>
      </Card>

      {/* Active Filter Summary Bar */}
      {(filterInterest || filterStatus || filterCountry || filterIndustry || filterSource || filterLocation || filterQualityTier || filterBuyingIntent || filterVerifiedEmail || debouncedSearch) && (
        <div style={{
          display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6,
          marginBottom: 12, padding: '8px 14px',
          background: isDark ? 'rgba(99,102,241,0.06)' : 'rgba(99,102,241,0.04)',
          border: `1px solid ${isDark ? 'rgba(99,102,241,0.18)' : 'rgba(99,102,241,0.15)'}`,
          borderRadius: 10,
        }}>
          <span style={{ fontSize: 11, color: '#6366f1', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', marginRight: 4 }}>
            <FilterOutlined style={{ marginRight: 4 }} />Filtered by
          </span>
          {debouncedSearch && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)', color: '#6366f1', cursor: 'pointer' }}
              onClick={() => { setSearchText(''); setDebouncedSearch(''); }}>
              Search: "{debouncedSearch}" ×
            </span>
          )}
          {filterInterest && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.4)', color: '#6366f1', fontWeight: 600, cursor: 'pointer' }}
              onClick={() => setFilterInterest('')}>
              Interest: {filterInterest} ×
            </span>
          )}
          {filterStatus && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#6366f1', cursor: 'pointer' }}
              onClick={() => setFilterStatus('')}>
              Status: {filterStatus} ×
            </span>
          )}
          {filterCountry && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#6366f1', cursor: 'pointer' }}
              onClick={() => setFilterCountry('')}>
              Country: {filterCountry} ×
            </span>
          )}
          {filterIndustry && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#6366f1', cursor: 'pointer' }}
              onClick={() => setFilterIndustry('')}>
              Industry: {filterIndustry} ×
            </span>
          )}
          {filterSource && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#6366f1', cursor: 'pointer' }}
              onClick={() => setFilterSource('')}>
              Source: {filterSource} ×
            </span>
          )}
          {filterLocation && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#6366f1', cursor: 'pointer' }}
              onClick={() => setFilterLocation('')}>
              Location: {filterLocation} ×
            </span>
          )}
          {filterBuyingIntent && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#6366f1', cursor: 'pointer' }}
              onClick={() => setFilterBuyingIntent('')}>
              Intent: {filterBuyingIntent} ×
            </span>
          )}
          {filterQualityTier && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#6366f1', cursor: 'pointer' }}
              onClick={() => setFilterQualityTier('')}>
              Tier: {filterQualityTier} ×
            </span>
          )}
          {filterVerifiedEmail && (
            <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 10, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#6366f1', cursor: 'pointer' }}
              onClick={() => setFilterVerifiedEmail(false)}>
              Verified Email only ×
            </span>
          )}
          <span style={{ marginLeft: 'auto', fontSize: 11, color: '#94a3b8', cursor: 'pointer' }}
            onClick={handleClearFilters}>
            Clear all
          </span>
        </div>
      )}

      {/* Leads Table */}
      <Card bodyStyle={{ padding: '16px' }}>
        {loading && leads.length === 0 ? (
          <div style={{ padding: '8px 0' }}>
            {[...Array(8)].map((_, i) => (
              <div key={i} style={{ display: 'flex', gap: 16, alignItems: 'center', padding: '12px 0', borderBottom: i < 7 ? '1px solid rgba(0,0,0,0.06)' : 'none' }}>
                <Skeleton.Avatar active size={32} shape="circle" style={{ flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <Skeleton active title={{ width: '35%' }} paragraph={{ rows: 1, width: '55%' }} style={{ margin: 0 }} />
                </div>
                <Skeleton.Button active size="small" style={{ width: 60 }} />
                <Skeleton.Button active size="small" style={{ width: 50 }} />
              </div>
            ))}
          </div>
        ) : (
        <Table
          columns={columns}
          dataSource={filteredLeads.map((lead, i) => ({ ...lead, key: lead.id || i }))}
          loading={loading && leads.length > 0}
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            total: totalLeads,
            onChange: (page, size) => {
              setCurrentPage(page);
              setPageSize(size);
            },
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} leads`,
            style: { color: 'var(--text-stat)' },
          }}
          style={{ color: 'var(--text-stat)' }}
          scroll={{ x: 1200 }}
          size="small"
        />
        )}
      </Card>

      {/* Lead Detail Modal */}
      <Drawer
        title="Lead Details"
        placement="right"
        onClose={() => { setDetailModalVisible(false); setAiAnalysis(null); setAiEmail(null); }}
        open={detailModalVisible}
        width={600}
      >
        {selectedLead && (
          <div>
            {/* ── Assignment banner ── */}
            {(() => {
              const assignedToMe = selectedLead.assigned_to === currentUserId;
              const assignedToOther = selectedLead.assigned_to && !assignedToMe;
              const canManage = currentUserRole === 'admin' || currentUserRole === 'manager';
              return (
                <div style={{ marginBottom: 16 }}>
                  {assignedToOther && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 8, borderRadius: 8 }}
                      message={
                        <span>
                          <b>{selectedLead.assigned_to_name || 'A teammate'}</b> is handling this lead
                        </span>
                      }
                      description="Labeling it will overwrite their outcome. Coordinate before acting."
                    />
                  )}
                  {assignedToMe && (
                    <Alert
                      type="success"
                      showIcon
                      style={{ marginBottom: 8, borderRadius: 8 }}
                      message="You have claimed this lead"
                      action={
                        <Button size="small" danger loading={assignLoading}
                          onClick={() => handleAssignLead(selectedLead.id, null)}>
                          Release
                        </Button>
                      }
                    />
                  )}
                  {!selectedLead.assigned_to && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <Button size="small" type="primary" ghost loading={assignLoading}
                        icon={<AimOutlined />}
                        onClick={() => handleAssignLead(selectedLead.id, currentUserId)}>
                        Claim this lead
                      </Button>
                      <span style={{ fontSize: 11, color: '#64748b' }}>
                        Lets your team know you're handling it
                      </span>
                    </div>
                  )}
                  {assignedToOther && canManage && (
                    <Button size="small" danger ghost loading={assignLoading} style={{ marginTop: 6 }}
                      onClick={() => handleAssignLead(selectedLead.id, null)}>
                      Unassign (admin override)
                    </Button>
                  )}
                </div>
              );
            })()}

            {/* ── Quick Label Bar ── trains ML with one click */}
            <QuickLabelBar
              key={selectedLead?.id}
              lead={selectedLead}
              onLabeled={(leadId, outcome) => {
                setLeads(prev => prev.map(l =>
                  l.id === leadId ? { ...l, outcome } : l
                ));
                setSelectedLead(prev => prev?.id === leadId ? { ...prev, outcome } : prev);
              }}
            />

            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ color: 'var(--text-stat)', marginBottom: '16px' }}>Contact Information</h3>
              <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Name</p>
                <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500, fontSize: '16px' }}>{selectedLead.name}</p>
              </div>
              <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Email</p>
                <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.email}</p>
              </div>
              <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Phone</p>
                <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.phone}</p>
              </div>
            </div>

            <Divider style={{ borderColor: 'rgba(99,102,241,0.15)' }} />

            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ color: 'var(--text-stat)', marginBottom: '16px' }}>Company Details</h3>
              <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Company</p>
                <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.company}</p>
              </div>
              <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Role</p>
                <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.role || 'N/A'}</p>
              </div>
              <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Location</p>
                <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.location || 'N/A'}</p>
              </div>
              {selectedLead.country && (
                <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Country</p>
                  <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.country}</p>
                </div>
              )}
              {selectedLead.city && (
                <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>City</p>
                  <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.city}</p>
                </div>
              )}
              {selectedLead.lead_type && (
                <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Lead Type</p>
                  <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>
                    {selectedLead.lead_type === 'company' ? '🏢 Company' : '👤 Person'}
                  </p>
                </div>
              )}
              {selectedLead.industry && (
                <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Industry</p>
                  <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.industry.replace('_', ' ')}</p>
                </div>
              )}
              {selectedLead.website && (
                <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Website</p>
                  <a href={selectedLead.website} target="_blank" rel="noopener noreferrer"
                     style={{ color: '#06b6d4', fontWeight: 500 }}>{selectedLead.website}</a>
                </div>
              )}
              {selectedLead.linkedin_url && (
                <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>LinkedIn</p>
                  <a href={selectedLead.linkedin_url} target="_blank" rel="noopener noreferrer"
                     style={{ color: '#06b6d4', fontWeight: 500 }}>{selectedLead.linkedin_url}</a>
                </div>
              )}
              {selectedLead.product && (
                <div style={{ background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Product Interest</p>
                  <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.product}</p>
                </div>
              )}
            </div>

            {/* Interest / Buying Intent section — only shown for interest-collected leads */}
            {(selectedLead.interest_category || selectedLead.buying_intent) && (
              <>
                <Divider style={{ borderColor: 'rgba(99,102,241,0.15)' }} />
                <div style={{ marginBottom: '20px' }}>
                  <h3 style={{ color: 'var(--text-stat)', marginBottom: '16px' }}>
                    <AimOutlined style={{ color: '#d97706', marginRight: 8 }} />Buying Intent
                  </h3>
                  {selectedLead.interest_category && (
                    <div style={{ background: 'rgba(217,119,6,0.08)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                      <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Interest Category</p>
                      <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.interest_category}</p>
                    </div>
                  )}
                  {selectedLead.product_interest && (
                    <div style={{ background: 'rgba(217,119,6,0.08)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                      <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Product Interest</p>
                      <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 500 }}>{selectedLead.product_interest}</p>
                    </div>
                  )}
                  {selectedLead.buying_intent && (
                    <div style={{ background: 'rgba(217,119,6,0.08)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                      <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Buying Intent</p>
                      <Tag color={
                        selectedLead.buying_intent === 'high'   ? 'green' :
                        selectedLead.buying_intent === 'medium' ? 'blue'  :
                        selectedLead.buying_intent === 'low'    ? 'orange': 'default'
                      } style={{ fontWeight: 600, fontSize: 13 }}>
                        {selectedLead.buying_intent?.toUpperCase()}
                        {selectedLead.intent_confidence != null &&
                          ` — ${Math.round(selectedLead.intent_confidence * 100)}% confidence`}
                      </Tag>
                    </div>
                  )}
                  {selectedLead.intent_reason && (
                    <div style={{ background: 'rgba(217,119,6,0.08)', padding: '16px', borderRadius: '8px', marginBottom: '12px' }}>
                      <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Intent Signals</p>
                      <p style={{ margin: 0, color: 'var(--text-stat)', fontSize: 13, lineHeight: 1.5 }}>{selectedLead.intent_reason}</p>
                    </div>
                  )}
                </div>
              </>
            )}

            <Divider style={{ borderColor: 'rgba(99,102,241,0.15)' }} />

            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ color: 'var(--text-stat)', marginBottom: '16px' }}>Qualification &amp; Validation</h3>

              {/* Score + Validation Level row */}
              <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                <div style={{ flex: 1, background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Score</p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Progress type="circle" percent={selectedLead.score} size={44}
                      strokeColor={selectedLead.score > 80 ? '#22c55e' : selectedLead.score > 50 ? '#f59e0b' : '#ef4444'} />
                    <div>
                      <p style={{ margin: 0, color: 'var(--text-stat)', fontWeight: 600, fontSize: '15px' }}>{selectedLead.score}%</p>
                      <p style={{ margin: 0, color: '#64748b', fontSize: '11px' }}>Intelligence Score</p>
                    </div>
                  </div>
                </div>
                <div style={{ flex: 1, background: 'rgba(99,102,241,0.06)', padding: '16px', borderRadius: '8px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#64748b', fontSize: '12px' }}>Validation Level</p>
                  <Tag style={{ background: getStatusColor(selectedLead.status).bg, color: getStatusColor(selectedLead.status).color, border: 'none', fontWeight: 700, fontSize: 12, padding: '2px 10px' }}>
                    {(selectedLead.status || 'unknown').replace('_', ' ').toUpperCase()}
                  </Tag>
                  <p style={{ margin: '6px 0 0 0', color: '#64748b', fontSize: '11px' }}>
                    {selectedLead.status === 'validated'      ? 'Verified email + domain + strong confidence'  :
                     selectedLead.status === 'semi_validated' ? 'Partial verification — may lack email/domain' :
                     selectedLead.status === 'unvalidated'    ? 'Raw discovery — not yet enriched'             :
                     selectedLead.status === 'needs_review'   ? 'Flagged — requires manual review'             : 'Status unknown'}
                  </p>
                </div>
              </div>

              {/* Email + Domain verified row */}
              {(() => {
                const dp = selectedLead.data_points || {};
                const intel = dp.intelligence_score || {};
                const bd = intel.confidence_breakdown || {};
                const emailVerified = dp.email_verified || false;
                const hasEmail = !!selectedLead.email;
                const hasWebsite = !!selectedLead.website;
                const hasBusinessEmail = hasEmail && !['gmail.com','yahoo.com','hotmail.com','outlook.com'].some(d => (selectedLead.email||'').endsWith(d));
                const isDecisionMaker = !!selectedLead.position && /ceo|founder|co.?founder|cto|cmo|cfo|coo|vp|svp|evp|president|managing\s+director|owner|director|head\s+of/i.test(selectedLead.position);
                const srcRel = Math.round(bd.source || dp.source_reliability_score || 0);
                const hasBD = Object.keys(bd).length > 0;
                return (
                  <>
                    <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                      <div style={{ flex: 1, background: 'rgba(99,102,241,0.06)', padding: '14px', borderRadius: '8px' }}>
                        <p style={{ margin: '0 0 6px 0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: 0.5 }}>Email</p>
                        {!hasEmail
                          ? <span style={{ color: '#ef4444', fontSize: 13 }}>✗ No email</span>
                          : emailVerified
                            ? <span style={{ color: '#22c55e', fontSize: 13 }}>✓ Verified</span>
                            : hasBusinessEmail
                              ? <span style={{ color: '#f59e0b', fontSize: 13 }}>~ Business (unverified)</span>
                              : <span style={{ color: '#94a3b8', fontSize: 13 }}>~ Generic email</span>
                        }
                        {hasEmail && <p style={{ margin: '4px 0 0 0', color: '#64748b', fontSize: '11px' }}>{selectedLead.email}</p>}
                      </div>
                      <div style={{ flex: 1, background: 'rgba(99,102,241,0.06)', padding: '14px', borderRadius: '8px' }}>
                        <p style={{ margin: '0 0 6px 0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: 0.5 }}>Domain</p>
                        {hasWebsite
                          ? <span style={{ color: '#22c55e', fontSize: 13 }}>✓ Website present</span>
                          : <span style={{ color: '#ef4444', fontSize: 13 }}>✗ No website</span>
                        }
                        {hasWebsite && <p style={{ margin: '4px 0 0 0', color: '#64748b', fontSize: '11px', wordBreak: 'break-all' }}>{selectedLead.website}</p>}
                      </div>
                    </div>

                    {/* Decision Maker + Source */}
                    <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                      <div style={{ flex: 1, background: 'rgba(99,102,241,0.06)', padding: '14px', borderRadius: '8px' }}>
                        <p style={{ margin: '0 0 6px 0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: 0.5 }}>Decision Maker</p>
                        {isDecisionMaker
                          ? <span style={{ color: '#22c55e', fontSize: 13 }}>✓ {selectedLead.position}</span>
                          : selectedLead.position
                            ? <span style={{ color: '#94a3b8', fontSize: 13 }}>~ {selectedLead.position}</span>
                            : <span style={{ color: '#64748b', fontSize: 13 }}>– Not detected</span>
                        }
                      </div>
                      <div style={{ flex: 1, background: 'rgba(99,102,241,0.06)', padding: '14px', borderRadius: '8px' }}>
                        <p style={{ margin: '0 0 6px 0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: 0.5 }}>Source</p>
                        <span style={{ color: 'var(--text-stat)', fontSize: 13 }}>{selectedLead.source || '–'}</span>
                        {srcRel > 0 && <span style={{ marginLeft: 6, color: srcRel >= 70 ? '#22c55e' : srcRel >= 45 ? '#f59e0b' : '#94a3b8', fontSize: 12 }}>({srcRel}%)</span>}
                      </div>
                    </div>

                    {/* Confidence Breakdown bars — only shown when intelligence pipeline ran */}
                    {hasBD && (
                      <div style={{ background: 'rgba(99,102,241,0.06)', padding: '14px', borderRadius: '8px', marginBottom: 12 }}>
                        <p style={{ margin: '0 0 10px 0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: 0.5 }}>Confidence Breakdown</p>
                        {[
                          { label: 'Identity',    key: 'identity', color: '#818cf8' },
                          { label: 'Company Fit', key: 'company',  color: '#06b6d4' },
                          { label: 'Email',       key: 'email',    color: '#22c55e' },
                          { label: 'Source',      key: 'source',   color: '#f59e0b' },
                          { label: 'Intent',      key: 'intent',   color: '#a855f7' },
                        ].map(({ label, key, color }) => {
                          const val = Math.round(bd[key] || 0);
                          return (
                            <div key={key} style={{ marginBottom: 8 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                                <span style={{ color: '#94a3b8', fontSize: 11 }}>{label}</span>
                                <span style={{ color, fontSize: 11, fontWeight: 600 }}>{val}%</span>
                              </div>
                              <Progress
                                percent={val}
                                size="small"
                                strokeColor={color}
                                trailColor={isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'}
                                showInfo={false}
                              />
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </>
                );
              })()}
            </div>

            <Space style={{ width: '100%', marginTop: '20px' }} direction="vertical">
              <Space style={{ width: '100%' }}>
                <Button type="primary" icon={<RobotOutlined />} onClick={() => handleAIAnalyze(selectedLead)} loading={aiAnalysisLoading}>
                  AI Deep Analysis
                </Button>
                <Button icon={<MailOutlined />} onClick={() => handleAIGenerateEmail(selectedLead)} loading={aiEmailLoading}>
                  AI Generate Email
                </Button>
              </Space>

              {/* AI Analysis Results */}
              {aiAnalysisLoading && (
                <div style={{ padding: 16, background: 'rgba(15,23,42,0.8)', borderRadius: 8, textAlign: 'center' }}>
                  <span style={{ color: '#22c55e' }}><RobotOutlined /> AI is analyzing this lead...</span>
                </div>
              )}
              {aiAnalysis?.analysis && (
                <div style={{ background: 'rgba(15,23,42,0.8)', borderRadius: 8, padding: 16 }}>
                  <h4 style={{ color: '#22c55e', margin: '0 0 12px 0' }}><RobotOutlined /> AI Analysis <Tag color="cyan">{aiAnalysis.ai_provider}</Tag></h4>
                  
                  <div style={{ marginBottom: 12 }}>
                    <p style={{ color: '#64748b', fontSize: 11, margin: 0 }}>Company Analysis</p>
                    <p style={{ color: 'var(--text-stat)', fontSize: 13, margin: '4px 0 0 0' }}>{aiAnalysis.analysis.company_analysis}</p>
                  </div>
                  
                  <div style={{ marginBottom: 12 }}>
                    <p style={{ color: '#64748b', fontSize: 11, margin: 0 }}>Decision Maker</p>
                    <p style={{ color: 'var(--text-stat)', fontSize: 13, margin: '4px 0 0 0' }}>{aiAnalysis.analysis.decision_maker_assessment}</p>
                  </div>

                  {[
                    { label: 'Pain Points',    items: aiAnalysis.analysis.pain_points    || [], color: 'volcano' },
                    { label: 'Buying Signals', items: aiAnalysis.analysis.buying_signals || [], color: 'green'   },
                    { label: 'Talking Points', items: aiAnalysis.analysis.talking_points || [], color: 'blue'    },
                    { label: 'Risk Factors',   items: aiAnalysis.analysis.risk_factors   || [], color: 'red'     },
                  ].map(({ label, items, color }) => (
                    <div key={label} style={{ marginBottom: 10 }}>
                      <p style={{ color: '#64748b', fontSize: 11, margin: '0 0 4px 0' }}>{label}</p>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {items.map((item, i) => (
                          <Tag key={i} color={color} style={{ whiteSpace: 'normal', lineHeight: '1.4', marginBottom: 2 }}>{item}</Tag>
                        ))}
                      </div>
                    </div>
                  ))}

                  <div style={{ marginTop: 12, padding: '8px 12px', background: 'rgba(15,23,42,0.6)', borderRadius: 6 }}>
                    <p style={{ color: '#64748b', fontSize: 11, margin: 0 }}>Recommended Approach</p>
                    <p style={{ color: '#06b6d4', fontSize: 13, margin: '4px 0 0 0' }}>{aiAnalysis.analysis.recommended_approach}</p>
                  </div>

                  <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    <Tag color="purple">Deal: {aiAnalysis.analysis.estimated_deal_size}</Tag>
                    <Tag color="orange">Cycle: {aiAnalysis.analysis.sales_cycle_estimate}</Tag>
                    <Tag color={aiAnalysis.analysis.priority === 'High' ? 'red' : 'default'}>Priority: {aiAnalysis.analysis.priority}</Tag>
                  </div>
                </div>
              )}

              {/* AI Email Generation */}
              {!aiEmail && !aiEmailLoading && (
                <div style={{ background: 'rgba(15,23,42,0.8)', borderRadius: 8, padding: 12 }}>
                  <Row gutter={12}>
                    <Col span={12}>
                      <p style={{ color: '#64748b', fontSize: 11, margin: '0 0 4px 0' }}>Email Type</p>
                      <Select
                        value={aiEmailType}
                        onChange={setAiEmailType}
                        style={{ width: '100%' }}
                        size="small"
                        options={[
                          { label: 'Cold Outreach', value: 'cold_outreach' },
                          { label: 'Follow Up', value: 'follow_up' },
                          { label: 'Meeting Request', value: 'meeting_request' },
                          { label: 'Value Proposition', value: 'value_proposition' },
                        ]}
                      />
                    </Col>
                    <Col span={12}>
                      <p style={{ color: '#64748b', fontSize: 11, margin: '0 0 4px 0' }}>Tone</p>
                      <Select
                        value={aiEmailTone}
                        onChange={setAiEmailTone}
                        style={{ width: '100%' }}
                        size="small"
                        options={[
                          { label: 'Professional', value: 'professional' },
                          { label: 'Friendly', value: 'friendly' },
                          { label: 'Urgent', value: 'urgent' },
                          { label: 'Consultative', value: 'consultative' },
                        ]}
                      />
                    </Col>
                  </Row>
                </div>
              )}

              {aiEmailLoading && (
                <div style={{ padding: 16, background: 'rgba(15,23,42,0.8)', borderRadius: 8, textAlign: 'center' }}>
                  <span style={{ color: '#06b6d4' }}><MailOutlined /> AI is writing the email...</span>
                </div>
              )}

              {aiEmail?.email && (
                <div style={{ background: 'rgba(15,23,42,0.8)', borderRadius: 8, padding: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <h4 style={{ color: '#06b6d4', margin: 0 }}><MailOutlined /> AI Generated Email <Tag color="cyan">{aiEmail.ai_provider}</Tag></h4>
                    <Button size="small" icon={<CopyOutlined />} onClick={handleCopyEmail}>Copy</Button>
                  </div>
                  <div style={{ background: 'rgba(15,23,42,0.6)', borderRadius: 6, padding: 12 }}>
                    <p style={{ color: '#f59e0b', fontWeight: 600, margin: '0 0 8px 0' }}>Subject: {aiEmail.email.subject}</p>
                    <p style={{ color: 'var(--text-stat)', fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', margin: 0 }}>{aiEmail.email.body}</p>
                  </div>
                  {aiEmail.email.personalization_notes && (
                    <p style={{ color: '#64748b', fontSize: 11, margin: '8px 0 0 0', fontStyle: 'italic' }}>
                      ✨ {aiEmail.email.personalization_notes}
                    </p>
                  )}
                </div>
              )}

              <Space style={{ width: '100%' }}>
                <Button type="primary" block onClick={() => handleContact(selectedLead, 'email')}>
                  Send Email
                </Button>
                <Button block onClick={() => handleContact(selectedLead, 'phone')}>
                  Call
                </Button>
              </Space>
            </Space>
          </div>
        )}
      </Drawer>

      {/* Add Lead Modal */}
      <Modal
        title="Add New Lead"
        open={addModalVisible}
        onCancel={() => {
          setAddModalVisible(false);
          addForm.resetFields();
        }}
        footer={null}
        width={600}
      >
        <Form
          form={addForm}
          layout="vertical"
          onFinish={handleAddLead}
        >
          <Form.Item name="lead_type" initialValue="person" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 10 }}>
              {[{ value: 'person', icon: '👤', label: 'Person' }, { value: 'company', icon: '🏢', label: 'Company' }].map(opt => (
                <label key={opt.value} style={{ flex: 1, cursor: 'pointer' }}>
                  <input type="radio" name="lead_type_radio" value={opt.value} style={{ display: 'none' }}
                    defaultChecked={opt.value === 'person'}
                    onChange={() => addForm.setFieldValue('lead_type', opt.value)} />
                  <Form.Item noStyle shouldUpdate={(prev, cur) => prev.lead_type !== cur.lead_type}>
                    {({ getFieldValue }) => {
                      const active = getFieldValue('lead_type') === opt.value;
                      return (
                        <div onClick={() => addForm.setFieldValue('lead_type', opt.value)} style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                          padding: '10px 0', borderRadius: 10,
                          border: `2px solid ${active ? (opt.value === 'company' ? '#818cf8' : '#4ade80') : (isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0')}`,
                          background: active ? (opt.value === 'company' ? 'rgba(99,102,241,0.1)' : 'rgba(34,197,94,0.08)') : 'transparent',
                          color: active ? (opt.value === 'company' ? '#818cf8' : '#22c55e') : (isDark ? '#64748b' : '#94a3b8'),
                          fontWeight: active ? 700 : 500, fontSize: 14, cursor: 'pointer',
                          transition: 'all 0.15s',
                        }}>
                          <span style={{ fontSize: 18 }}>{opt.icon}</span>{opt.label}
                        </div>
                      );
                    }}
                  </Form.Item>
                </label>
              ))}
            </div>
          </Form.Item>

          <Form.Item label="Name" name="name" rules={[{ required: true, message: 'Please enter name' }]}>
            <Input placeholder="John Doe" />
          </Form.Item>
          <Form.Item label="Email" name="email" rules={[{ required: true, type: 'email', message: 'Please enter valid email' }]}>
            <Input placeholder="john@company.com" />
          </Form.Item>
          <Form.Item label="Phone" name="phone">
            <Input placeholder="+1-555-0000" />
          </Form.Item>
          <Row gutter={12}>
            <Col xs={24} sm={12}>
              <Form.Item label="Company" name="company" rules={[{ required: true, message: 'Please enter company' }]}>
                <Input placeholder="Company Name" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label="Position / Role" name="position">
                <Input placeholder="e.g. CEO, VP Sales, CTO" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col xs={24} sm={12}>
              <Form.Item label="Interest" name="interests">
                <Select
                  mode="multiple"
                  placeholder="Select interests"
                  maxTagCount={2}
                  options={[
                    { label: 'AI Tools',          value: 'AI Tools' },
                    { label: 'Cloud Solutions',   value: 'Cloud Solutions' },
                    { label: 'CRM Software',      value: 'CRM Software' },
                    { label: 'Data Analytics',    value: 'Data Analytics' },
                    { label: 'Digital Marketing', value: 'Digital Marketing' },
                    { label: 'Cybersecurity',     value: 'Cybersecurity' },
                    { label: 'Machine Learning',  value: 'Machine Learning' },
                    { label: 'IoT',               value: 'IoT' },
                    { label: 'Blockchain',        value: 'Blockchain' },
                    { label: 'Fintech',           value: 'Fintech' },
                    { label: 'E-commerce',        value: 'E-commerce' },
                    { label: 'DevOps',            value: 'DevOps' },
                    { label: 'SaaS',              value: 'SaaS' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label="Product / Service" name="product">
                <Input placeholder="e.g. CRM Software, Cloud Analytics" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col xs={24} sm={12}>
              <Form.Item label="Country" name="country">
                <Input placeholder="e.g. United States, Germany, UAE" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label="City" name="city">
                <Input placeholder="e.g. Dubai, New York" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col xs={24} sm={12}>
              <Form.Item label="LinkedIn URL" name="linkedin_url">
                <Input placeholder="https://linkedin.com/in/username" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label="Website" name="website">
                <Input placeholder="https://company.com" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="Industry" name="industry">
            <Select
              placeholder="Select industry"
              allowClear
              showSearch
              options={[
                { label: 'Software / SaaS',      value: 'Software / SaaS' },
                { label: 'Finance & Fintech',     value: 'Finance & Fintech' },
                { label: 'Healthcare & MedTech',  value: 'Healthcare & MedTech' },
                { label: 'Marketing & Agencies',  value: 'Marketing & Agencies' },
                { label: 'E-commerce & Retail',   value: 'E-commerce & Retail' },
                { label: 'Real Estate',           value: 'Real Estate' },
                { label: 'Education & EdTech',    value: 'Education & EdTech' },
                { label: 'Manufacturing',         value: 'Manufacturing' },
                { label: 'Technology',            value: 'Technology' },
                { label: 'Consulting',            value: 'Consulting' },
                { label: 'Logistics',             value: 'Logistics' },
                { label: 'Energy',                value: 'Energy' },
                { label: 'Telecom',               value: 'Telecom' },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={addLeadLoading}>
              Add Lead
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* Collect from Web Modal */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <GlobalOutlined style={{ fontSize: '22px', color: '#06b6d4' }} />
            <div>
              <span style={{ fontSize: '16px', fontWeight: 600 }}>Collect Leads from Web</span>
              <p style={{ margin: 0, color: '#64748b', fontSize: '12px', fontWeight: 400 }}>
                Extract real business data from public websites across 37+ countries
              </p>
            </div>
          </div>
        }
        open={collectModalVisible}
        onCancel={() => {
          if (!collectLoading) {
            setCollectModalVisible(false);
            collectForm.resetFields();
            setLastCollectionResult(null);
            setCollectProgress(0);
          }
        }}
        footer={null}
        width={750}
      >
        {/* Quick Presets */}
        <div style={{ marginBottom: '20px' }}>
          <p style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '8px', fontWeight: 500 }}>QUICK PRESETS</p>
          <Space wrap size={[8, 8]}>
            {[
              { label: 'Tech Companies USA', q: 'technology companies', c: ['US'], type: 'companies' },
              { label: 'Marketing Agencies UK', q: 'marketing agencies', c: ['UK'], type: 'companies' },
              { label: 'SaaS Startups Global', q: 'SaaS startup company', c: ['US', 'UK', 'DE'], type: 'companies' },
              { label: 'CTOs & Founders', q: 'CTO founder startup', c: ['US'], type: 'people' },
              { label: 'Real Estate UAE', q: 'real estate companies', c: ['AE'], type: 'companies' },
              { label: 'AI Companies India', q: 'artificial intelligence companies', c: ['IN'], type: 'companies' },
            ].map((preset) => (
              <Tag
                key={preset.label}
                style={{
                  cursor: 'pointer', padding: '4px 12px', borderRadius: '16px',
                  background: 'rgba(6,182,212,0.08)', border: '1px solid rgba(6,182,212,0.2)',
                  color: '#06b6d4', fontSize: '12px',
                }}
                onClick={() => {
                  collectForm.setFieldsValue({
                    query: preset.q,
                    countries: preset.c,
                    collection_type: preset.type,
                  });
                  setCollectionType(preset.type);
                }}
              >
                <ThunderboltOutlined style={{ marginRight: '4px' }} />
                {preset.label}
              </Tag>
            ))}
          </Space>
        </div>

        <Divider style={{ margin: '12px 0 20px' }} />

        <Form
          form={collectForm}
          layout="vertical"
          onFinish={handleCollectFromWeb}
          initialValues={{ max_per_country: 10, collection_type: 'companies' }}
        >
          <Row gutter={[16, 0]}>
            <Col xs={24} md={12}>
              <Form.Item
                label={<span style={{ fontWeight: 500 }}>Collection Type</span>}
                name="collection_type"
              >
                <Select
                  onChange={(val) => setCollectionType(val)}
                  options={[
                    { label: '🏢 Companies & Businesses', value: 'companies' },
                    { label: '👤 People / Contacts', value: 'people' },
                  ]}
                  size="large"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                label={<span style={{ fontWeight: 500 }}>Search Query</span>}
                name="query"
                rules={[{ required: true, message: 'Enter what to search for' }]}
              >
                <Input
                  prefix={<SearchOutlined />}
                  placeholder={collectionType === 'people'
                    ? 'e.g. marketing manager, CTO, sales director'
                    : 'e.g. technology companies, marketing agencies'
                  }
                  size="large"
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={[16, 0]}>
            <Col xs={24} md={12}>
              <Form.Item
                label={<span style={{ fontWeight: 500 }}>Target Countries</span>}
                name="countries"
                rules={[{ required: true, message: 'Select at least one country' }]}
              >
                <Select
                  mode="multiple"
                  placeholder="Select countries (37+ supported)"
                  maxTagCount={3}
                  showSearch
                  options={supportedCountries.map((c) => ({
                    label: `${c.name} (${c.code})`,
                    value: c.code,
                  }))}
                  style={{ width: '100%' }}
                  size="large"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label={<span style={{ fontWeight: 500 }}>City (optional)</span>} name="city">
                <Input placeholder="e.g. Dubai, London" size="large" />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label={<span style={{ fontWeight: 500 }}>Max per Country</span>} name="max_per_country">
                <Select
                  size="large"
                  options={[
                    { label: '5 leads', value: 5 },
                    { label: '10 leads', value: 10 },
                    { label: '20 leads', value: 20 },
                    { label: '30 leads', value: 30 },
                    { label: '50 leads', value: 50 },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          {lastCollectionResult && (
            <Alert
              message={lastCollectionResult.message}
              description={(() => {
                const d = lastCollectionResult.data || {};
                const rej = d.rejection_reasons || {};
                const entries = Object.entries(rej).sort((a, b) => b[1] - a[1]);
                if (lastCollectionResult.status !== 'success' || d.saved !== 0 || entries.length === 0) return null;
                return (
                  <div style={{ marginTop: 6 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 12 }}>
                      Why leads were rejected:
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {entries.map(([reason, count]) => (
                        <span key={reason} style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          background: 'rgba(0,0,0,0.06)', borderRadius: 4,
                          padding: '2px 8px', fontSize: 11, fontFamily: 'monospace',
                        }}>
                          {reason.replace(/_/g, ' ')}
                          <span style={{ fontWeight: 700, color: '#d97706' }}>×{count}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })()}
              type={lastCollectionResult.data?.saved === 0 && lastCollectionResult.status === 'success' ? 'warning' : lastCollectionResult.status === 'success' ? 'success' : 'error'}
              showIcon
              closable
              onClose={() => setLastCollectionResult(null)}
              style={{ marginBottom: '16px', borderRadius: '8px' }}
            />
          )}

          {collectLoading && (
            <div style={{
              marginBottom: 16,
              padding: '14px 18px',
              background: isDark ? 'rgba(99,102,241,0.08)' : '#f8faff',
              border: `1px solid ${isDark ? 'rgba(99,102,241,0.2)' : '#e0e7ff'}`,
              borderRadius: 12,
            }}>
              {/* Header row */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 8, height: 8, borderRadius: '50%',
                    background: collectProgress >= 100 ? '#22c55e' : '#6366f1',
                    boxShadow: collectProgress < 100 ? '0 0 0 3px rgba(99,102,241,0.2)' : 'none',
                    animation: collectProgress < 100 ? 'pulse 1.5s infinite' : 'none',
                  }} />
                  <span style={{ fontWeight: 600, fontSize: 13, color: isDark ? '#e2e8f0' : '#1e293b' }}>
                    {collectProgress >= 100 ? 'Collection complete' : 'Collecting leads…'}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  {collectElapsed > 0 && (
                    <span style={{ fontSize: 11, color: '#94a3b8' }}>{collectElapsed}s</span>
                  )}
                  <span style={{
                    fontSize: 13, fontWeight: 700,
                    color: collectProgress >= 100 ? '#22c55e' : '#6366f1',
                  }}>
                    {Math.round(collectProgress)}%
                  </span>
                </div>
              </div>

              {/* Progress bar */}
              <Progress
                percent={Math.round(collectProgress)}
                status={collectProgress >= 100 ? 'success' : 'active'}
                strokeColor={collectProgress >= 100
                  ? '#22c55e'
                  : { '0%': '#6366f1', '100%': '#06b6d4' }}
                trailColor={isDark ? 'rgba(255,255,255,0.06)' : '#e2e8f0'}
                strokeWidth={8}
                showInfo={false}
                style={{ margin: 0 }}
              />

              {/* Status text */}
              <div style={{ marginTop: 8, fontSize: 12, color: '#64748b', display: 'flex', alignItems: 'center', gap: 6 }}>
                <GlobalOutlined style={{ fontSize: 11 }} />
                <span>{collectProgressText || 'Scanning web sources…'}</span>
              </div>
            </div>
          )}

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              icon={<CloudDownloadOutlined />}
              loading={collectLoading}
              size="large"
              style={{ 
                background: 'linear-gradient(135deg, #06b6d4, #6366f1)', 
                border: 'none', height: '48px', fontSize: '15px', fontWeight: 600,
                borderRadius: '10px',
              }}
            >
              {collectionType === 'people' ? 'Collect People' : 'Collect Companies'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* Collect from Social Media Modal */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <TeamOutlined style={{ fontSize: '22px', color: '#059669' }} />
            <div>
              <span style={{ fontSize: '16px', fontWeight: 600 }}>Collect Leads from Social Media</span>
              <p style={{ margin: 0, color: '#64748b', fontSize: '12px', fontWeight: 400 }}>
                Extract real leads from public groups, channels, profiles & company pages
              </p>
            </div>
          </div>
        }
        open={socialModalVisible}
        onCancel={() => {
          if (!socialLoading) {
            setSocialModalVisible(false);
            socialForm.resetFields();
            setSocialResult(null);
            setSocialProgress(0);
            setSocialProgressText('');
            setSocialPlatformResults([]);
          }
        }}
        footer={null}
        width={750}
      >
        {/* Quick Presets */}
        <div style={{ marginBottom: '20px' }}>
          <p style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '8px', fontWeight: 500 }}>QUICK PRESETS</p>
          <Space wrap size={[8, 8]}>
            {[
              { label: 'SaaS Founders', q: 'SaaS startup founder', pl: ['reddit', 'linkedin', 'twitter'], ind: 'startups' },
              { label: 'AI Companies', q: 'artificial intelligence company', pl: ['linkedin', 'twitter'], ind: 'ai' },
              { label: 'Marketing Pros', q: 'marketing agency digital', pl: ['reddit', 'facebook', 'linkedin'], ind: 'marketing' },
              { label: 'Tech Communities', q: 'technology software developer', pl: ['reddit', 'telegram'], ind: 'technology' },
              { label: 'E-commerce Sellers', q: 'ecommerce online store', pl: ['reddit', 'facebook'], ind: 'ecommerce' },
            ].map((preset) => (
              <Tag
                key={preset.label}
                style={{
                  cursor: 'pointer', padding: '4px 12px', borderRadius: '16px',
                  background: 'rgba(5,150,105,0.08)', border: '1px solid rgba(5,150,105,0.2)',
                  color: '#059669', fontSize: '12px',
                }}
                onClick={() => {
                  socialForm.setFieldsValue({
                    query: preset.q,
                    platforms: preset.pl,
                    industry: preset.ind,
                  });
                }}
              >
                <ThunderboltOutlined style={{ marginRight: '4px' }} />
                {preset.label}
              </Tag>
            ))}
          </Space>
        </div>

        <Divider style={{ margin: '12px 0 20px' }} />

        <Form
          form={socialForm}
          layout="vertical"
          onFinish={handleCollectFromSocial}
          initialValues={{ max_per_platform: 10, platforms: ['reddit'], collect_type: 'both' }}
        >
          <Form.Item
            label={<span style={{ fontWeight: 500 }}>Select Platforms</span>}
            name="platforms"
            rules={[{ required: true, message: 'Select at least one platform' }]}
          >
            <Select
              mode="multiple"
              placeholder="Choose platforms to collect from"
              maxTagCount={5}
              size="large"
              options={[
                { label: '🟠 Reddit — Subreddits & Communities', value: 'reddit' },
                { label: '💼 LinkedIn — Companies & Professionals', value: 'linkedin' },
                { label: '🔵 Telegram — Public Channels & Groups', value: 'telegram' },
                { label: '🐦 Twitter / X — Profiles & Bios', value: 'twitter' },
                { label: '📘 Facebook — Pages & Groups', value: 'facebook' },
              ]}
            />
          </Form.Item>

          <Row gutter={[16, 0]}>
            <Col xs={24} md={12}>
              <Form.Item
                label={<span style={{ fontWeight: 500 }}>Search Topic</span>}
                name="query"
                rules={[{ required: true, message: 'Enter a search topic' }]}
              >
                <Input
                  prefix={<SearchOutlined />}
                  placeholder="e.g. SaaS startups, AI tools, marketing agencies"
                  size="large"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label={<span style={{ fontWeight: 500 }}>Industry</span>} name="industry">
                <Select
                  allowClear
                  placeholder="Select industry"
                  size="large"
                  options={[
                    { label: 'Technology', value: 'technology' },
                    { label: 'Marketing', value: 'marketing' },
                    { label: 'Finance / Fintech', value: 'finance' },
                    { label: 'E-commerce', value: 'ecommerce' },
                    { label: 'SaaS / Startups', value: 'startups' },
                    { label: 'AI / Machine Learning', value: 'ai' },
                    { label: 'Sales / B2B', value: 'sales' },
                    { label: 'Design', value: 'design' },
                    { label: 'Real Estate', value: 'realestate' },
                    { label: 'Healthcare', value: 'health' },
                    { label: 'Consulting', value: 'consulting' },
                    { label: 'Education', value: 'education' },
                    { label: 'Logistics', value: 'logistics' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label={<span style={{ fontWeight: 500 }}>Max per Platform</span>} name="max_per_platform">
                <Select
                  size="large"
                  options={[
                    { label: '5 leads', value: 5 },
                    { label: '10 leads', value: 10 },
                    { label: '15 leads', value: 15 },
                    { label: '20 leads', value: 20 },
                    { label: '30 leads', value: 30 },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={[16, 0]}>
            <Col xs={24} md={12}>
              <Form.Item label={<span style={{ fontWeight: 500 }}>Collect Type</span>} name="collect_type">
                <Select
                  size="large"
                  placeholder="Companies & People"
                  options={[
                    { label: '🏢 Companies & 👤 People', value: 'both' },
                    { label: '🏢 Companies Only', value: 'company' },
                    { label: '👤 People Only', value: 'person' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label={<span style={{ fontWeight: 500 }}>Location Filter</span>} name="location">
                <Select
                  showSearch
                  allowClear
                  size="large"
                  placeholder="Any country (optional)"
                  suffixIcon={<EnvironmentOutlined />}
                  filterOption={(input, option) =>
                    (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                  }
                  options={[
                    // Middle East & North Africa
                    { label: '🇱🇧 Lebanon', value: 'Lebanon' },
                    { label: '🇦🇪 United Arab Emirates', value: 'United Arab Emirates' },
                    { label: '🇸🇦 Saudi Arabia', value: 'Saudi Arabia' },
                    { label: '🇪🇬 Egypt', value: 'Egypt' },
                    { label: '🇯🇴 Jordan', value: 'Jordan' },
                    { label: '🇰🇼 Kuwait', value: 'Kuwait' },
                    { label: '🇶🇦 Qatar', value: 'Qatar' },
                    { label: '🇧🇭 Bahrain', value: 'Bahrain' },
                    { label: '🇴🇲 Oman', value: 'Oman' },
                    { label: '🇮🇶 Iraq', value: 'Iraq' },
                    { label: '🇹🇷 Turkey', value: 'Turkey' },
                    { label: '🇮🇱 Israel', value: 'Israel' },
                    { label: '🇲🇦 Morocco', value: 'Morocco' },
                    { label: '🇹🇳 Tunisia', value: 'Tunisia' },
                    // Europe
                    { label: '🇬🇧 United Kingdom', value: 'United Kingdom' },
                    { label: '🇩🇪 Germany', value: 'Germany' },
                    { label: '🇫🇷 France', value: 'France' },
                    { label: '🇳🇱 Netherlands', value: 'Netherlands' },
                    { label: '🇪🇸 Spain', value: 'Spain' },
                    { label: '🇮🇹 Italy', value: 'Italy' },
                    { label: '🇸🇪 Sweden', value: 'Sweden' },
                    { label: '🇨🇭 Switzerland', value: 'Switzerland' },
                    { label: '🇵🇱 Poland', value: 'Poland' },
                    // Americas
                    { label: '🇺🇸 United States', value: 'United States' },
                    { label: '🇨🇦 Canada', value: 'Canada' },
                    { label: '🇧🇷 Brazil', value: 'Brazil' },
                    { label: '🇲🇽 Mexico', value: 'Mexico' },
                    { label: '🇦🇷 Argentina', value: 'Argentina' },
                    // Asia Pacific
                    { label: '🇮🇳 India', value: 'India' },
                    { label: '🇦🇺 Australia', value: 'Australia' },
                    { label: '🇸🇬 Singapore', value: 'Singapore' },
                    { label: '🇯🇵 Japan', value: 'Japan' },
                    { label: '🇰🇷 South Korea', value: 'South Korea' },
                    { label: '🇨🇳 China', value: 'China' },
                    { label: '🇵🇰 Pakistan', value: 'Pakistan' },
                    { label: '🇮🇩 Indonesia', value: 'Indonesia' },
                    // Africa
                    { label: '🇳🇬 Nigeria', value: 'Nigeria' },
                    { label: '🇿🇦 South Africa', value: 'South Africa' },
                    { label: '🇰🇪 Kenya', value: 'Kenya' },
                    { label: '🇬🇭 Ghana', value: 'Ghana' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          {socialResult && (
            <Alert
              message={socialResult.message}
              type={socialResult.status === 'success' ? 'success' : 'error'}
              showIcon
              closable
              onClose={() => setSocialResult(null)}
              style={{ marginBottom: '16px', borderRadius: '8px' }}
            />
          )}

          {socialLoading && (
            <div style={{ marginBottom: '16px', padding: '16px', background: 'rgba(5,150,105,0.05)', borderRadius: '8px', border: '1px solid rgba(5,150,105,0.12)' }}>
              {/* Overall progress bar */}
              <Progress
                percent={Math.round(socialProgress)}
                status={socialProgress >= 100 ? 'success' : 'active'}
                strokeColor={{ from: '#059669', to: '#10b981' }}
                style={{ marginBottom: '8px' }}
              />
              <p style={{ color: '#64748b', fontSize: '12px', marginBottom: '10px' }}>
                <ThunderboltOutlined style={{ marginRight: '6px', color: '#059669' }} />
                {socialProgressText || 'Searching social media platforms...'}
              </p>

              {/* Per-platform status list */}
              {socialPlatformResults.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {socialPlatformResults.map(({ platform, status, leads: pLeads }) => {
                    const emoji = { reddit: '🔴', telegram: '✈️', twitter: '🐦', facebook: '📘', linkedin: '💼' }[platform] || '🔍';
                    const statusStyle = {
                      done:    { bg: 'rgba(5,150,105,0.12)',  color: '#059669', icon: '✓' },
                      active:  { bg: 'rgba(234,179,8,0.12)',  color: '#b45309', icon: '⟳' },
                      pending: { bg: 'rgba(100,116,139,0.08)', color: '#94a3b8', icon: '—' },
                      error:   { bg: 'rgba(239,68,68,0.10)',  color: '#dc2626', icon: '✗' },
                    }[status] || { bg: 'rgba(100,116,139,0.08)', color: '#94a3b8', icon: '—' };
                    return (
                      <span key={platform} style={{
                        display: 'inline-flex', alignItems: 'center', gap: '4px',
                        padding: '2px 10px', borderRadius: '12px',
                        background: statusStyle.bg, color: statusStyle.color,
                        fontSize: '11px', fontWeight: 500,
                        border: `1px solid ${statusStyle.color}22`,
                      }}>
                        <span>{emoji}</span>
                        <span style={{ textTransform: 'capitalize' }}>{platform}</span>
                        <span style={{ opacity: 0.8 }}>{statusStyle.icon}</span>
                        {pLeads > 0 && <span>({pLeads})</span>}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              icon={<TeamOutlined />}
              loading={socialLoading}
              size="large"
              style={{ 
                background: 'linear-gradient(135deg, #059669, #10b981)', 
                border: 'none', height: '48px', fontSize: '15px', fontWeight: 600,
                borderRadius: '10px',
              }}
            >
              Collect from Social Media
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Interest-Based Collection Modal ───────────────────────────── */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <AimOutlined style={{ fontSize: 22, color: '#d97706' }} />
            <div>
              <span style={{ fontSize: 16, fontWeight: 600 }}>Interest-Based Collection</span>
              <p style={{ margin: 0, color: '#64748b', fontSize: 12, fontWeight: 400 }}>
                Collect leads actively looking for a product or service category
              </p>
            </div>
          </div>
        }
        open={interestModalVisible}
        onCancel={() => {
          if (!isInterestCollecting) {
            setInterestModalVisible(false);
            interestForm.resetFields();
            setInterestResult(null);
          }
        }}
        footer={null}
        width={680}
      >
        <Form
          form={interestForm}
          layout="vertical"
          onFinish={handleInterestCollect}
          initialValues={{ interest_max_leads: 30, interest_sources: ['web', 'directories', 'news'] }}
        >
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item
                label="Product / Service Category"
                name="interest_category"
                rules={[{ required: true, message: 'Select a category' }]}
              >
                <Select
                  placeholder="e.g. Laptops, Real Estate, Cars…"
                  showSearch
                  optionFilterProp="label"
                  options={interestCategories.map(c => ({ label: c.name, value: c.slug }))}
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item
                label="Country"
                name="interest_country"
                rules={[{ required: true, message: 'Enter a country' }]}
              >
                <Select
                  placeholder="e.g. Lebanon, United States…"
                  showSearch
                  optionFilterProp="label"
                  options={supportedCountries.map(c => ({ label: c.name, value: c.name }))}
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item label="City (optional)" name="interest_city">
                <Input placeholder="e.g. Beirut, Dubai" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label={`Max Leads`} name="interest_max_leads">
                <Select
                  options={[10, 20, 30, 50, 75, 100].map(n => ({ label: `${n} leads`, value: n }))}
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="Collect From" name="interest_sources">
            <Select
              mode="multiple"
              placeholder="Select sources"
              options={[
                { label: '🌐 Web & Directories', value: 'web' },
                { label: '📋 Business Directories', value: 'directories' },
                { label: '📰 News & Press', value: 'news' },
                { label: '💬 Social Media', value: 'social' },
                { label: '🐙 GitHub', value: 'github' },
              ]}
              style={{ width: '100%' }}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              icon={<AimOutlined />}
              disabled={isInterestCollecting}
              size="large"
              style={{
                background: 'linear-gradient(135deg, #d97706, #f59e0b)',
                border: 'none', height: 48, fontSize: 15, fontWeight: 600, borderRadius: 10,
              }}
            >
              Collect by Interest
            </Button>
          </Form.Item>
        </Form>

        {/* ── Progress bar ── */}
        {isInterestCollecting && (
          <div style={{ marginTop: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 12, color: '#94a3b8' }}>{interestProgressText}</span>
              <span style={{ fontSize: 12, color: '#64748b' }}>⏱ {interestElapsed}s</span>
            </div>
            <Progress
              percent={interestProgress}
              status="active"
              strokeColor={{ from: '#d97706', to: '#f59e0b' }}
              showInfo={false}
            />
          </div>
        )}

        {/* ── Result summary (after collection) ── */}
        {interestResult && !isInterestCollecting && (
          <div style={{ marginTop: 20 }}>
            {interestResult.status === 'error' ? (
              <Alert type="error" message={interestResult.message} showIcon />
            ) : (
              <Alert
                type={interestResult.saved > 0 ? 'success' : 'warning'}
                showIcon
                message={interestProgressText}
                description={
                  `Scanned ${interestResult.collected ?? 0} candidates — ` +
                  `saved ${interestResult.saved ?? 0}, ` +
                  `rejected ${interestResult.rejected ?? 0}, ` +
                  `duplicates ${interestResult.duplicates ?? 0}` +
                  (interestResult.quality_report?.average_quality_score > 0
                    ? ` · avg score ${interestResult.quality_report.average_quality_score}%`
                    : '')
                }
              />
            )}
          </div>
        )}
      </Modal>

      {/* ── Auto Collect Modal ─────────────────────────────────────────── */}
      <Modal
        title={<span><RocketOutlined style={{ color: '#7c3aed', marginRight: 8 }} />Auto Collect — Automated Lead Pipeline</span>}
        open={autoCollectVisible}
        onCancel={() => { if (!autoCollectLoading) { setAutoCollectVisible(false); autoCollectForm.resetFields(); setAutoCollectResult(null); setAutoCollectProgress(0); setAutoCollectElapsed(0); }}}
        footer={null}
        width={680}
      >
        {/* Source status badges */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
          {Object.entries(autoCollectSources).map(([key, src]) => (
            <Tag
              key={key}
              icon={src.configured ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
              color={src.configured ? 'green' : 'default'}
              style={{ padding: '4px 10px', fontSize: 13 }}
              title={src.description}
            >
              {src.label}
            </Tag>
          ))}
        </div>

        {/* Quick-fill presets */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 6, fontWeight: 500 }}>Quick presets:</div>
          <Space wrap size={[6, 6]}>
            {[
              { label: 'SaaS Founders', keywords: 'SaaS founder', titles: ['CEO', 'Founder', 'Co-Founder'], industries: ['Technology', 'SaaS'] },
              { label: 'AI Startups', keywords: 'AI startup machine learning', titles: ['CTO', 'VP Engineering', 'Head of AI'], industries: ['Artificial Intelligence', 'Technology'] },
              { label: 'Sales Leaders', keywords: 'B2B sales revenue', titles: ['VP Sales', 'Head of Sales', 'Chief Revenue Officer'], industries: ['Technology', 'SaaS'] },
              { label: 'FinTech', keywords: 'fintech payments banking', titles: ['CEO', 'CFO', 'Head of Finance'], industries: ['FinTech', 'Financial Services'] },
              { label: 'Growth / Marketing', keywords: 'growth hacking digital marketing', titles: ['CMO', 'VP Marketing', 'Head of Growth'], industries: ['Technology', 'Marketing'] },
              { label: 'HealthTech', keywords: 'healthtech medical digital health', titles: ['CEO', 'CMO', 'Head of Product'], industries: ['Healthcare', 'BioTech'] },
              { label: 'E-commerce', keywords: 'ecommerce retail D2C', titles: ['CEO', 'Head of E-commerce', 'VP Product'], industries: ['E-commerce', 'Retail'] },
              { label: 'DevTools / APIs', keywords: 'developer tools API infrastructure', titles: ['CTO', 'Head of Platform', 'Developer Advocate'], industries: ['Technology', 'Developer Tools'] },
            ].map(preset => (
              <Tag
                key={preset.label}
                color="purple"
                style={{ cursor: 'pointer', userSelect: 'none', padding: '2px 10px' }}
                onClick={() => autoCollectForm.setFieldsValue({
                  keywords:   preset.keywords,
                  titles:     preset.titles,
                  industries: preset.industries,
                })}
              >
                {preset.label}
              </Tag>
            ))}
          </Space>
        </div>

        <Form form={autoCollectForm} layout="vertical" onFinish={handleAutoCollect}>
          <Form.Item label="Keywords / Search Terms" name="keywords">
            <Input placeholder='e.g. "SaaS founder" or "AI startup"' allowClear />
          </Form.Item>
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item label="Job Titles" name="titles">
                <Select mode="tags" placeholder="CEO, CTO, VP Sales…" tokenSeparators={[',']} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="Locations" name="locations">
                <Select
                  mode="tags"
                  placeholder="United States, United Kingdom…"
                  tokenSeparators={[',']}
                  showSearch
                  filterOption={(input, option) =>
                    (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                  }
                  options={[
                    { label: '🌎 Americas', options: [
                      { label: 'United States', value: 'United States' },
                      { label: 'Canada', value: 'Canada' },
                      { label: 'Brazil', value: 'Brazil' },
                      { label: 'Mexico', value: 'Mexico' },
                      { label: 'Argentina', value: 'Argentina' },
                    ]},
                    { label: '🌍 Europe', options: [
                      { label: 'United Kingdom', value: 'United Kingdom' },
                      { label: 'Germany', value: 'Germany' },
                      { label: 'France', value: 'France' },
                      { label: 'Netherlands', value: 'Netherlands' },
                      { label: 'Sweden', value: 'Sweden' },
                      { label: 'Spain', value: 'Spain' },
                      { label: 'Switzerland', value: 'Switzerland' },
                      { label: 'Denmark', value: 'Denmark' },
                      { label: 'Norway', value: 'Norway' },
                      { label: 'Finland', value: 'Finland' },
                      { label: 'Poland', value: 'Poland' },
                      { label: 'Italy', value: 'Italy' },
                      { label: 'Belgium', value: 'Belgium' },
                      { label: 'Portugal', value: 'Portugal' },
                    ]},
                    { label: '🌏 Asia-Pacific', options: [
                      { label: 'Australia', value: 'Australia' },
                      { label: 'India', value: 'India' },
                      { label: 'Singapore', value: 'Singapore' },
                      { label: 'Japan', value: 'Japan' },
                      { label: 'South Korea', value: 'South Korea' },
                      { label: 'Hong Kong', value: 'Hong Kong' },
                      { label: 'New Zealand', value: 'New Zealand' },
                      { label: 'Indonesia', value: 'Indonesia' },
                      { label: 'Philippines', value: 'Philippines' },
                    ]},
                    { label: '🌍 Middle East & Africa', options: [
                      { label: 'United Arab Emirates', value: 'United Arab Emirates' },
                      { label: 'Israel', value: 'Israel' },
                      { label: 'Saudi Arabia', value: 'Saudi Arabia' },
                      { label: 'South Africa', value: 'South Africa' },
                      { label: 'Egypt', value: 'Egypt' },
                      { label: 'Nigeria', value: 'Nigeria' },
                    ]},
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item label="Industries" name="industries">
                <Select mode="tags" placeholder="SaaS, FinTech, Healthcare…" tokenSeparators={[',']} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="Max Leads" name="limit" initialValue={25}>
                <Select options={[10,25,50,75,100].map(n => ({ label: `${n} leads`, value: n }))} />
              </Form.Item>
            </Col>
          </Row>

          {/* Optional Interest Targeting Section */}
          <div style={{ marginBottom: 16 }}>
            <div
              style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 8 }}
              onClick={() => setAutoShowInterest(prev => !prev)}
            >
              <FireOutlined style={{ color: '#f59e0b' }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: '#f59e0b' }}>Interest Targeting</span>
              <Tag color="orange" style={{ fontSize: 11 }}>Optional</Tag>
              <span style={{ fontSize: 11, color: '#94a3b8', flex: 1 }}>
                Improves query quality and decision-maker targeting
              </span>
              {autoShowInterest ? <UpOutlined style={{ fontSize: 11, color: '#94a3b8' }} /> : <DownOutlined style={{ fontSize: 11, color: '#94a3b8' }} />}
            </div>
            {autoShowInterest && (
              <div style={{ padding: '12px 16px', background: isDark ? 'rgba(245,158,11,0.06)' : '#fffbeb', borderRadius: 8, border: '1px solid rgba(245,158,11,0.2)' }}>
                <Row gutter={12}>
                  <Col xs={24} md={12}>
                    <Form.Item label="Product / Service Category" name="interest_product_category" style={{ marginBottom: 12 }}>
                      <Input placeholder="e.g. CRM software, payroll tools, HR platform" allowClear />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item label="Target Industry" name="interest_target_industry" style={{ marginBottom: 12 }}>
                      <Select allowClear placeholder="SaaS, FinTech, E-commerce…" options={[
                        { label: 'SaaS / Software', value: 'SaaS' },
                        { label: 'FinTech', value: 'FinTech' },
                        { label: 'E-commerce', value: 'E-commerce' },
                        { label: 'Healthcare', value: 'Healthcare' },
                        { label: 'Marketing / AdTech', value: 'Marketing' },
                        { label: 'Developer Tools', value: 'Developer Tools' },
                        { label: 'HR / Recruiting', value: 'HR' },
                        { label: 'Real Estate', value: 'Real Estate' },
                        { label: 'Logistics', value: 'Logistics' },
                        { label: 'EdTech', value: 'EdTech' },
                      ]} />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={12}>
                  <Col xs={24} md={12}>
                    <Form.Item label="Buying Intent" name="interest_buying_intent" style={{ marginBottom: 12 }}>
                      <Select allowClear placeholder="Any intent level" options={[
                        { label: '🔥 High — actively evaluating', value: 'high' },
                        { label: '⚡ Medium — researching', value: 'medium' },
                        { label: '🌱 Low — awareness stage', value: 'low' },
                      ]} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item label="Target Country" name="interest_country" style={{ marginBottom: 12 }}>
                      <Input placeholder="e.g. United States, Nigeria" allowClear />
                    </Form.Item>
                  </Col>
                </Row>
              </div>
            )}
          </div>

          {autoCollectLoading && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: '#64748b' }}>Apollo → Hunter → PDL → AI enrichment → Saving…</span>
                <span style={{ fontSize: 12, color: '#64748b' }}>⏱ {autoCollectElapsed}s</span>
              </div>
              <Progress percent={autoCollectProgress} status="active" strokeColor="#7c3aed" />
            </div>
          )}

          {autoCollectResult && (
            <Alert
              type="success"
              style={{ marginBottom: 16 }}
              message={`Done — ${autoCollectResult.saved} leads saved (${autoCollectResult.collected} found) · ⏱ ${autoCollectElapsed}s`}
              description={autoCollectResult.sources?.length ? `Sources: ${autoCollectResult.sources.join(', ')}` : undefined}
              showIcon
            />
          )}

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={autoCollectLoading}
              icon={<RocketOutlined />}
              block
              style={{ background: '#7c3aed', borderColor: '#7c3aed', height: 42 }}
            >
              {autoCollectLoading ? 'Running Pipeline…' : 'Start Auto Collect'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default LeadsPage;
