import { useEffect, useState, useCallback, useContext } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Row, Col, Card, Statistic, Table, Spin, Tag, Progress,
  Button, Select, Tooltip, Divider, Badge, Alert, message,
} from 'antd';
import {
  ArrowUpOutlined, ArrowDownOutlined, ReloadOutlined, GlobalOutlined,
  TeamOutlined, ThunderboltOutlined, CheckCircleOutlined,
  PhoneOutlined, MailOutlined, RocketOutlined, BulbOutlined,
  FunnelPlotOutlined, LineChartOutlined, BarChartOutlined,
  PlusOutlined, ExportOutlined, UserOutlined, StarOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { Bar, Line, Doughnut } from 'react-chartjs-2';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement,
  LineElement, BarElement, ArcElement, Title, Tooltip as ChartTooltip,
  Legend, Filler,
} from 'chart.js';
import { apiWithFallback } from '../services/api';
import { ThemeContext } from '../context/ThemeContext';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Title, ChartTooltip, Legend, Filler,
);

const COLORS = {
  primary: '#6366f1', cyan: '#06b6d4', green: '#22c55e',
  amber: '#f59e0b', red: '#ef4444', purple: '#8b5cf6',
  orange: '#f97316', teal: '#14b8a6', pink: '#ec4899',
};

const PALETTE = [
  '#6366f1', '#06b6d4', '#22c55e', '#f59e0b',
  '#ef4444', '#8b5cf6', '#14b8a6', '#f97316',
];

const STATUS_CFG = {
  hot:       { color: '#22c55e', bg: 'rgba(34,197,94,0.12)' },
  warm:      { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  cold:      { color: '#3b82f6', bg: 'rgba(59,130,246,0.12)' },
  qualified: { color: '#6366f1', bg: 'rgba(99,102,241,0.12)' },
  contacted: { color: '#06b6d4', bg: 'rgba(6,182,212,0.12)' },
  converted: { color: '#22c55e', bg: 'rgba(34,197,94,0.12)' },
  pending:   { color: '#94a3b8', bg: 'rgba(148,163,184,0.12)' },
};

const Dashboard = () => {
  const { isDark } = useContext(ThemeContext);
  const navigate = useNavigate();

  const userRole         = localStorage.getItem('userRole') || 'user';
  const isAdmin          = userRole === 'admin';
  const isManagerOrAdmin = isAdmin || userRole === 'manager';
  const isMobileUser     = (() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}').source === 'mobile'; }
    catch { return false; }
  })();

  const [stats, setStats]             = useState(null);
  const [recentLeads, setRecentLeads] = useState([]);
  const [loading, setLoading]         = useState(true);
  const [refreshing, setRefreshing]   = useState(false);
  const [error, setError]             = useState(null);
  const [countryData, setCountryData] = useState({});
  const [industryData, setIndustryData] = useState({});
  const [scoreDistData, setScoreDistData] = useState({});
  const [analyticsData, setAnalyticsData] = useState(null);
  const [timeRange, setTimeRange]     = useState('30days');
  const [syncStatus, setSyncStatus]   = useState(null);
  const [syncing, setSyncing]         = useState(false);
  // Persist dismiss across sessions so it doesn't reappear on every page load
  const [syncDismissed, setSyncDismissed] = useState(
    () => localStorage.getItem('syncBannerDismissed') || null
  );

  /* ── fetch ──────────────────────────────────────────────────── */
  const fetchDashboardData = useCallback(async (range = timeRange, silent = false) => {
    try {
      if (!silent) setRefreshing(true);
      setError(null);
      const [statsRes, leadsRes, analyticsRes] = await Promise.allSettled([
        apiWithFallback('/leads/stats', 'get'),
        apiWithFallback('/leads/', 'get', null, { params: { page: 1, per_page: 10, sort_by: 'created_at', sort_order: 'desc' } }),
        apiWithFallback('/analytics', 'get', null, { params: { range } }),
      ]);

      const allFailed = [statsRes, leadsRes, analyticsRes].every(r => r.status === 'rejected');
      if (allFailed) {
        setError('Failed to load dashboard data. Check your connection.');
      }

      if (statsRes.status === 'fulfilled') {
        const s = statsRes.value.data.stats || {};
        setStats({
          totalLeads:      s.total_leads      ?? 0,
          qualifiedLeads:  s.qualified_leads  ?? 0,
          newLeadsThisWeek: s.new_this_week   ?? 0,
          accuracy:        s.conversion_rate  ?? 0,
        });
        if (s.by_country)     setCountryData(s.by_country);
        if (s.by_industry)    setIndustryData(s.by_industry);
        if (s.by_score_range) setScoreDistData(s.by_score_range);
      }

      if (leadsRes.status === 'fulfilled') {
        const leads = leadsRes.value.data.leads;
        setRecentLeads(Array.isArray(leads) ? leads.slice(0, 10) : []);
      }

      if (analyticsRes.status === 'fulfilled') {
        const data = analyticsRes.value.data?.data;
        if (data) setAnalyticsData(data);
      }
    } catch {
      /* errors surfaced by individual results */
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [timeRange]);

  useEffect(() => { fetchDashboardData(timeRange, false); }, []);   // eslint-disable-line

  // Sync status — only relevant for mobile-registered accounts
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!isMobileUser) return;
    apiWithFallback('/sync/status', 'get')
      .then((res) => {
        setSyncStatus(res.data);
        // If the health improved to ok, clear any saved dismissal
        if (res.data?.overall_health === 'ok') {
          localStorage.removeItem('syncBannerDismissed');
          setSyncDismissed(null);
        }
      })
      .catch(() => {});
  }, [isMobileUser]);

  const handleSyncDismiss = () => {
    const health = syncStatus?.overall_health;
    setSyncDismissed(health);
    localStorage.setItem('syncBannerDismissed', health);
  };

  const handleSyncNow = async () => {
    setSyncing(true);
    const isRetry = syncStatus?.overall_health === 'error' && syncStatus?.failed_count > 0;
    try {
      await apiWithFallback(isRetry ? '/sync/retry-failed' : '/sync/web-to-mobile', 'post');
      message.success(isRetry ? 'Retrying failed leads…' : 'Sync triggered — leads are being pushed to mobile');
      setTimeout(async () => {
        try {
          const res = await apiWithFallback('/sync/status', 'get');
          setSyncStatus(res.data);
          if (res.data?.overall_health === 'ok') {
            setSyncDismissed(null);
            localStorage.removeItem('syncBannerDismissed');
          }
        } catch {}
        setSyncing(false);
      }, 2500);
    } catch {
      message.error('Sync failed — Supabase may not be configured or reachable');
      setSyncing(false);
    }
  };

  const showSyncBanner = isMobileUser && syncStatus && (() => {
    const h = syncStatus.overall_health;
    if (h === 'ok' || h === syncDismissed) return false;
    if (h === 'unconfigured') return true;
    if (h === 'error')  return syncStatus.failed_count  > 0;
    if (h === 'stale')  return syncStatus.pending_count > 0;
    return false;
  })();

  const handleRangeChange = (val) => {
    setTimeRange(val);
    fetchDashboardData(val, true);
  };

  /* ── chart helpers ──────────────────────────────────────────── */
  const tickColor  = isDark ? '#475569' : '#94a3b8';
  const gridColor  = isDark ? 'rgba(99,102,241,0.05)' : 'rgba(0,0,0,0.05)';
  const cardBorder = isDark ? 'rgba(99,102,241,0.1)' : 'rgba(0,0,0,0.06)';

  const baseOpts = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: {
        ticks: { color: tickColor, font: { size: 11 } },
        grid: { color: gridColor, drawBorder: false },
      },
      x: {
        ticks: { color: tickColor, font: { size: 11 } },
        grid: { display: false },
      },
    },
  };

  /* ── derived numbers ────────────────────────────────────────── */
  if (loading && !stats) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 500 }}>
        <Spin size="large" />
      </div>
    );
  }

  const s          = stats || { totalLeads: 0, qualifiedLeads: 0, newLeadsThisWeek: 0, accuracy: 0 };
  const summary    = analyticsData?.summary || {};
  const funnel     = analyticsData?.funnel  || {};
  const bySource   = analyticsData?.distribution?.by_source  || {};
  const byInterest = analyticsData?.distribution?.by_interest || {};

  const contacted  = summary.contacted_leads  ?? funnel.contacted ?? 0;
  const converted  = summary.converted_leads  ?? funnel.converted ?? 0;
  const avgScore   = summary.average_score    ?? 0;
  const qualRate   = s.totalLeads > 0 ? ((s.qualifiedLeads / s.totalLeads) * 100).toFixed(1) : '0.0';
  const weekGrowth = s.totalLeads > 0 ? ((s.newLeadsThisWeek / s.totalLeads) * 100).toFixed(1) : '0.0';

  const funnelSteps = [
    { label: 'Total',     value: s.totalLeads,     color: COLORS.primary, pct: 100 },
    { label: 'Qualified', value: s.qualifiedLeads,  color: COLORS.cyan,    pct: s.totalLeads > 0 ? Math.round((s.qualifiedLeads / s.totalLeads) * 100) : 0 },
    { label: 'Contacted', value: contacted,         color: COLORS.amber,   pct: s.totalLeads > 0 ? Math.round((contacted / s.totalLeads) * 100) : 0 },
    { label: 'Converted', value: converted,         color: COLORS.green,   pct: s.totalLeads > 0 ? Math.round((converted / s.totalLeads) * 100) : 0 },
  ];

  /* ── table columns ──────────────────────────────────────────── */
  const columns = [
    {
      title: 'Name', dataIndex: 'name', key: 'name', width: 150,
      render: (text, r) => (
        <div>
          <div style={{ fontWeight: 600, color: 'var(--text-stat)', fontSize: 13 }}>{text}</div>
          {r.position && <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>{r.position}</div>}
        </div>
      ),
    },
    {
      title: 'Company', dataIndex: 'company', key: 'company', width: 130,
      render: (v) => <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v || '—'}</span>,
    },
    {
      title: 'Industry', dataIndex: 'industry', key: 'industry', width: 120,
      render: (v) => v
        ? <Tag style={{ fontSize: 11, background: 'rgba(99,102,241,0.1)', color: COLORS.primary, border: 'none' }}>{v}</Tag>
        : <span style={{ color: 'var(--text-muted)' }}>—</span>,
    },
    {
      title: 'Contact', key: 'contact', width: 130,
      render: (_, r) => (
        <div style={{ display: 'flex', gap: 8 }}>
          {r.email && (
            <Tooltip title={r.email}>
              <a href={`mailto:${r.email}`} style={{ color: COLORS.cyan }}>
                <MailOutlined style={{ fontSize: 14 }} />
              </a>
            </Tooltip>
          )}
          {r.phone && (
            <Tooltip title={r.phone}>
              <a href={`tel:${r.phone}`} style={{ color: COLORS.green }}>
                <PhoneOutlined style={{ fontSize: 14 }} />
              </a>
            </Tooltip>
          )}
          {r.linkedin_url && (
            <Tooltip title="LinkedIn">
              <a href={r.linkedin_url} target="_blank" rel="noreferrer" style={{ color: '#0077b5' }}>
                <GlobalOutlined style={{ fontSize: 14 }} />
              </a>
            </Tooltip>
          )}
          {!r.email && !r.phone && !r.linkedin_url && (
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
          )}
        </div>
      ),
    },
    {
      title: 'Country', key: 'country', width: 90,
      render: (_, r) => <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{r.country || r.location || '—'}</span>,
    },
    {
      title: 'Score', dataIndex: 'qualification_score', key: 'score', width: 72,
      render: (score) => {
        const sc = score || 0;
        return (
          <Progress
            type="circle" percent={sc} size={34}
            strokeColor={sc > 75 ? COLORS.green : sc > 45 ? COLORS.amber : COLORS.red}
            format={(p) => <span style={{ fontSize: 9, fontWeight: 700 }}>{p}</span>}
          />
        );
      },
    },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 95,
      render: (status) => {
        const sk = (status || 'pending').toLowerCase();
        const c  = STATUS_CFG[sk] || STATUS_CFG.pending;
        return (
          <Tag style={{ background: c.bg, color: c.color, border: 'none', fontWeight: 600, fontSize: 11 }}>
            <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: c.color, marginRight: 5, verticalAlign: 'middle' }} />
            {sk.toUpperCase()}
          </Tag>
        );
      },
    },
    {
      title: 'Source', dataIndex: 'source', key: 'source', width: 100,
      render: (v) => v
        ? <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{v}</span>
        : <span style={{ color: 'var(--text-muted)' }}>—</span>,
    },
  ];

  /* ── render ─────────────────────────────────────────────────── */
  const cardStyle = { border: `1px solid ${cardBorder}` };

  return (
    <div style={{ padding: '24px 28px' }}>

      {error && (
        <Alert
          type="error"
          message={error}
          style={{ marginBottom: 16 }}
          action={
            <Button size="small" icon={<ReloadOutlined />} onClick={() => fetchDashboardData(timeRange, false)}>
              Retry
            </Button>
          }
        />
      )}

      {/* Sync status banner — only shown when there are leads to action */}
      {showSyncBanner && (
        <Alert
          type={syncStatus.overall_health === 'error' ? 'error' : syncStatus.overall_health === 'unconfigured' ? 'info' : 'warning'}
          showIcon
          closable
          onClose={handleSyncDismiss}
          style={{ marginBottom: 16 }}
          message={
            syncStatus.overall_health === 'unconfigured'
              ? 'Supabase sync not configured — mobile app will not receive updates'
              : syncStatus.overall_health === 'error'
              ? `Sync error — ${syncStatus.failed_count} lead(s) failed to sync`
              : `Sync is stale — ${syncStatus.pending_count} lead(s) pending`
          }
          description={
            syncStatus.last_sync_at
              ? `Last sync: ${new Date(syncStatus.last_sync_at).toLocaleString()} · Status: ${syncStatus.last_sync_status}`
              : 'No sync has run yet'
          }
          action={
            syncStatus.overall_health !== 'unconfigured' && (
              <Button
                size="small"
                icon={<SyncOutlined spin={syncing} />}
                loading={syncing}
                onClick={handleSyncNow}
                style={{ marginLeft: 8 }}
              >
                Sync Now
              </Button>
            )
          }
        />
      )}

      {/* ── Header ─────────────────────────────────────────────── */}
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ margin: '0 0 3px', fontSize: 24, fontWeight: 700 }}>Dashboard</h1>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
            {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <Select
            value={timeRange}
            onChange={handleRangeChange}
            size="middle"
            style={{ width: 110 }}
            options={[
              { value: '7days',  label: 'Last 7d' },
              { value: '30days', label: 'Last 30d' },
              { value: '90days', label: 'Last 90d' },
            ]}
          />
          {isAdmin && (
            <Button icon={<PlusOutlined />} type="primary" onClick={() => navigate('/leads')}>
              Add Lead
            </Button>
          )}
          {isManagerOrAdmin && (
            <Button icon={<ThunderboltOutlined />} onClick={() => navigate('/ai-engine')}>
              AI Engine
            </Button>
          )}
          <Button icon={<ReloadOutlined spin={refreshing} />} onClick={() => fetchDashboardData(timeRange, false)} loading={refreshing}>
            Refresh
          </Button>
        </div>
      </div>

      {/* ── KPI Cards (6) ──────────────────────────────────────── */}
      <Row gutter={[14, 14]} style={{ marginBottom: 22 }}>
        {[
          {
            title: 'Total Leads', value: s.totalLeads, icon: <TeamOutlined />,
            color: COLORS.primary, sub: `+${s.newLeadsThisWeek} this week`, up: s.newLeadsThisWeek > 0,
          },
          {
            title: 'Qualified', value: s.qualifiedLeads, icon: <CheckCircleOutlined />,
            color: COLORS.cyan, sub: `${qualRate}% of total`, up: s.qualifiedLeads > 0,
          },
          {
            title: 'Contacted', value: contacted, icon: <MailOutlined />,
            color: COLORS.amber, sub: contacted > 0 ? `${Math.round((contacted / s.totalLeads || 0) * 100)}% reach rate` : 'None yet', up: contacted > 0,
          },
          {
            title: 'Converted', value: converted, icon: <RocketOutlined />,
            color: COLORS.green, sub: converted > 0 ? `${Math.round((converted / (contacted || 1)) * 100)}% close rate` : 'None yet', up: converted > 0,
          },
          {
            title: 'Avg. Score', value: avgScore, suffix: '', icon: <StarOutlined />,
            color: COLORS.purple, sub: avgScore > 70 ? 'High quality' : avgScore > 40 ? 'Moderate' : 'Needs work', up: avgScore > 50,
          },
          {
            title: 'This Week', value: s.newLeadsThisWeek, icon: <ArrowUpOutlined />,
            color: COLORS.orange, sub: s.newLeadsThisWeek > 0 ? `+${weekGrowth}% of total` : 'No new leads', up: s.newLeadsThisWeek > 0,
          },
        ].map((item, i) => (
          <Col xs={24} sm={12} xl={4} key={i}>
            <Card styles={{ body: { padding: '18px 20px' } }} style={{ ...cardStyle, borderLeft: `3px solid ${item.color}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ color: 'var(--text-muted)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.8, fontWeight: 600, marginBottom: 6 }}>
                    {item.title}
                  </div>
                  <Statistic
                    value={item.value}
                    suffix={item.suffix}
                    valueStyle={{ color: 'var(--text-stat)', fontSize: 26, fontWeight: 700, lineHeight: 1.1 }}
                  />
                </div>
                <div style={{
                  width: 36, height: 36, borderRadius: 10,
                  background: `${item.color}18`, display: 'flex',
                  alignItems: 'center', justifyContent: 'center',
                  color: item.color, fontSize: 16, flexShrink: 0,
                }}>{item.icon}</div>
              </div>
              <div style={{ color: item.up ? COLORS.green : 'var(--text-muted)', fontSize: 11, marginTop: 8, fontWeight: 500 }}>
                {item.up ? <ArrowUpOutlined /> : <ArrowDownOutlined />} {item.sub}
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* ── Activity Chart + Sales Funnel ──────────────────────── */}
      <Row gutter={[14, 14]} style={{ marginBottom: 22 }}>
        <Col xs={24} lg={15}>
          <Card
            style={cardStyle}
            title={
              <span style={{ color: 'var(--text-h)', fontSize: 13, fontWeight: 600 }}>
                <LineChartOutlined style={{ color: COLORS.primary, marginRight: 8 }} />
                Lead Activity
              </span>
            }
            styles={{ body: { padding: '12px 20px 16px' } }}
          >
            <div style={{ height: 260 }}>
              <Line
                data={{
                  labels: (analyticsData?.daily_data || []).map(d => d.date?.slice(5) || ''),
                  datasets: [
                    {
                      label: 'New Leads',
                      data: (analyticsData?.daily_data || []).map(d => d.leads || 0),
                      borderColor: COLORS.primary,
                      backgroundColor: 'rgba(99,102,241,0.07)',
                      tension: 0.4, fill: true, pointRadius: 2,
                      pointBackgroundColor: COLORS.primary, borderWidth: 2,
                    },
                    {
                      label: 'Qualified',
                      data: (analyticsData?.daily_data || []).map(d => d.qualified || 0),
                      borderColor: COLORS.cyan,
                      backgroundColor: 'rgba(6,182,212,0.06)',
                      tension: 0.4, fill: true, pointRadius: 2,
                      pointBackgroundColor: COLORS.cyan, borderWidth: 2,
                      borderDash: [4, 3],
                    },
                  ],
                }}
                options={{
                  ...baseOpts,
                  plugins: {
                    legend: {
                      display: true,
                      position: 'top',
                      labels: { color: tickColor, font: { size: 11 }, boxWidth: 12, padding: 16 },
                    },
                  },
                }}
              />
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={9}>
          <Card
            style={{ ...cardStyle, height: '100%' }}
            title={
              <span style={{ color: 'var(--text-h)', fontSize: 13, fontWeight: 600 }}>
                <FunnelPlotOutlined style={{ color: COLORS.amber, marginRight: 8 }} />
                Sales Funnel
              </span>
            }
            styles={{ body: { padding: '16px 24px' } }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {funnelSteps.map((step, i) => (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 500 }}>{step.label}</span>
                    <span style={{ fontSize: 12, color: step.color, fontWeight: 700 }}>
                      {step.value.toLocaleString()} <span style={{ opacity: 0.7, fontWeight: 400 }}>({step.pct}%)</span>
                    </span>
                  </div>
                  <div style={{ height: 8, borderRadius: 4, background: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', width: `${step.pct}%`,
                      background: `linear-gradient(90deg, ${step.color}cc, ${step.color})`,
                      borderRadius: 4, transition: 'width 0.6s ease',
                    }} />
                  </div>
                  {i < funnelSteps.length - 1 && (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 10, marginTop: 2 }}>▼</div>
                  )}
                </div>
              ))}
            </div>
            <Divider style={{ margin: '16px 0 10px' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Overall conversion</span>
              <span style={{ fontSize: 13, color: COLORS.green, fontWeight: 700 }}>
                {s.totalLeads > 0 ? ((converted / s.totalLeads) * 100).toFixed(1) : 0}%
              </span>
            </div>
          </Card>
        </Col>
      </Row>

      {/* ── Source + Interest + Country ────────────────────────── */}
      <Row gutter={[14, 14]} style={{ marginBottom: 22 }}>
        <Col xs={24} md={8}>
          <Card
            style={cardStyle}
            title={
              <span style={{ color: 'var(--text-h)', fontSize: 13, fontWeight: 600 }}>
                <BarChartOutlined style={{ color: COLORS.cyan, marginRight: 8 }} />
                By Source
              </span>
            }
            styles={{ body: { padding: '12px 16px 16px' } }}
          >
            <div style={{ height: 220 }}>
              {Object.keys(bySource).length > 0 ? (
                <Bar
                  data={{
                    labels: Object.keys(bySource).slice(0, 8).map(k => k.replace(/_/g, ' ')),
                    datasets: [{
                      data: Object.values(bySource).slice(0, 8),
                      backgroundColor: PALETTE,
                      borderRadius: 6, barThickness: 18,
                    }],
                  }}
                  options={{ ...baseOpts, indexAxis: 'y' }}
                />
              ) : (
                <div style={{ textAlign: 'center', paddingTop: 60, color: 'var(--text-muted)', fontSize: 13 }}>No source data</div>
              )}
            </div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card
            style={cardStyle}
            title={
              <span style={{ color: 'var(--text-h)', fontSize: 13, fontWeight: 600 }}>
                <BulbOutlined style={{ color: COLORS.amber, marginRight: 8 }} />
                Top Interests
              </span>
            }
            styles={{ body: { padding: '12px 16px 16px' } }}
          >
            <div style={{ height: 220 }}>
              {Object.keys(byInterest).length > 0 ? (
                <Bar
                  data={{
                    labels: Object.keys(byInterest).slice(0, 7).map(k => k.length > 14 ? k.slice(0, 13) + '…' : k),
                    datasets: [{
                      data: Object.values(byInterest).slice(0, 7),
                      backgroundColor: COLORS.amber + 'cc',
                      borderRadius: 6, barThickness: 18,
                    }],
                  }}
                  options={baseOpts}
                />
              ) : (
                <div style={{ textAlign: 'center', paddingTop: 60, color: 'var(--text-muted)', fontSize: 13 }}>No interest data</div>
              )}
            </div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card
            style={cardStyle}
            title={
              <span style={{ color: 'var(--text-h)', fontSize: 13, fontWeight: 600 }}>
                <GlobalOutlined style={{ color: COLORS.primary, marginRight: 8 }} />
                By Country
              </span>
            }
            styles={{ body: { padding: '12px 16px 16px' } }}
          >
            <div style={{ height: 220 }}>
              {Object.keys(countryData).length > 0 ? (
                <Doughnut
                  data={{
                    labels: Object.keys(countryData).slice(0, 7),
                    datasets: [{
                      data: Object.values(countryData).slice(0, 7),
                      backgroundColor: PALETTE,
                      borderColor: isDark ? '#0f172a' : '#ffffff',
                      borderWidth: 3,
                    }],
                  }}
                  options={{
                    responsive: true, maintainAspectRatio: false,
                    cutout: '62%',
                    plugins: {
                      legend: { position: 'right', labels: { color: tickColor, font: { size: 10 }, padding: 8, boxWidth: 10 } },
                    },
                  }}
                />
              ) : (
                <div style={{ textAlign: 'center', paddingTop: 60, color: 'var(--text-muted)', fontSize: 13 }}>No country data</div>
              )}
            </div>
          </Card>
        </Col>
      </Row>

      {/* ── Industry + Score Distribution + Status ─────────────── */}
      <Row gutter={[14, 14]} style={{ marginBottom: 22 }}>
        <Col xs={24} lg={11}>
          <Card
            style={cardStyle}
            title={
              <span style={{ color: 'var(--text-h)', fontSize: 13, fontWeight: 600 }}>
                <BarChartOutlined style={{ color: COLORS.purple, marginRight: 8 }} />
                By Industry
              </span>
            }
            styles={{ body: { padding: '12px 20px 16px' } }}
          >
            <div style={{ height: 230 }}>
              {Object.keys(industryData).length > 0 ? (
                <Bar
                  data={{
                    labels: Object.keys(industryData).slice(0, 10).map(k => k.replace(/_/g, ' ')),
                    datasets: [{
                      data: Object.values(industryData).slice(0, 10),
                      backgroundColor: COLORS.purple + 'bb',
                      borderRadius: 6, barThickness: 22,
                    }],
                  }}
                  options={{ ...baseOpts, indexAxis: 'y' }}
                />
              ) : (
                <div style={{ textAlign: 'center', paddingTop: 80, color: 'var(--text-muted)', fontSize: 13 }}>No industry data</div>
              )}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={7}>
          <Card
            style={cardStyle}
            title={
              <span style={{ color: 'var(--text-h)', fontSize: 13, fontWeight: 600 }}>
                <ThunderboltOutlined style={{ color: COLORS.amber, marginRight: 8 }} />
                Score Distribution
              </span>
            }
            styles={{ body: { padding: '12px 16px 16px' } }}
          >
            <div style={{ height: 230 }}>
              {Object.keys(scoreDistData).length > 0 ? (
                <Bar
                  data={{
                    labels: Object.keys(scoreDistData),
                    datasets: [{
                      label: 'Leads',
                      data: Object.values(scoreDistData),
                      backgroundColor: [
                        'rgba(239,68,68,0.75)',
                        'rgba(245,158,11,0.75)',
                        'rgba(99,102,241,0.75)',
                        'rgba(6,182,212,0.75)',
                        'rgba(34,197,94,0.75)',
                      ],
                      borderRadius: 6,
                      barThickness: 28,
                    }],
                  }}
                  options={{
                    ...baseOpts,
                    plugins: {
                      legend: { display: false },
                      tooltip: {
                        callbacks: {
                          label: (ctx) => ` ${ctx.parsed.y} leads`,
                        },
                      },
                    },
                  }}
                />
              ) : (
                <div style={{ textAlign: 'center', paddingTop: 80, color: 'var(--text-muted)', fontSize: 13 }}>No scored leads yet</div>
              )}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={6}>
          <Card
            style={{ ...cardStyle, height: '100%' }}
            title={
              <span style={{ color: 'var(--text-h)', fontSize: 13, fontWeight: 600 }}>
                <UserOutlined style={{ color: COLORS.teal, marginRight: 8 }} />
                Lead Status Breakdown
              </span>
            }
            styles={{ body: { padding: '12px 20px 16px' } }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 8 }}>
              {[
                { label: 'Qualified',  value: s.qualifiedLeads, color: COLORS.cyan },
                { label: 'Contacted',  value: contacted,         color: COLORS.amber },
                { label: 'Converted',  value: converted,         color: COLORS.green },
                { label: 'Pending',    value: Math.max(0, s.totalLeads - s.qualifiedLeads - contacted - converted), color: '#64748b' },
              ].map((item, i) => (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 500 }}>{item.label}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: item.color }}>
                      {item.value} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>/ {s.totalLeads}</span>
                    </span>
                  </div>
                  <Progress
                    percent={s.totalLeads > 0 ? Math.round((item.value / s.totalLeads) * 100) : 0}
                    strokeColor={item.color}
                    showInfo={false}
                    size={['100%', 7]}
                    style={{ margin: 0 }}
                  />
                </div>
              ))}
            </div>
            <Divider style={{ margin: '14px 0 10px' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Qualification rate</span>
              <span style={{ fontSize: 13, color: COLORS.cyan, fontWeight: 700 }}>{qualRate}%</span>
            </div>
          </Card>
        </Col>
      </Row>

      {/* ── Recent Leads ───────────────────────────────────────── */}
      <Row>
        <Col span={24}>
          <Card
            style={cardStyle}
            title={
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-h)', fontSize: 13, fontWeight: 600 }}>
                  <TeamOutlined style={{ color: COLORS.primary, marginRight: 8 }} />
                  Recent Leads
                  <Badge count={recentLeads.length} style={{ marginLeft: 8, background: COLORS.primary }} />
                </span>
                <Button size="small" icon={<ExportOutlined />} onClick={() => navigate('/leads')}>
                  View All
                </Button>
              </div>
            }
            styles={{ body: { padding: '4px 8px 12px' } }}
          >
            <Table
              columns={columns}
              dataSource={recentLeads.map((lead, i) => ({ ...lead, key: lead.id || i }))}
              pagination={false}
              size="small"
              scroll={{ x: 900 }}
              locale={{ emptyText: <div style={{ padding: '30px 0', color: 'var(--text-muted)' }}>No leads yet — collect some to get started</div> }}
            />
          </Card>
        </Col>
      </Row>

    </div>
  );
};

export default Dashboard;
