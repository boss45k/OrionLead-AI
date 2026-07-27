import React, { useEffect, useState, useContext, useCallback } from 'react';
import {
  Card, Row, Col, Spin, Table, Progress, Alert, Button,
  Tag, Select, Tooltip, message, Divider,
} from 'antd';
import { DatePicker } from 'antd';
import {
  DownloadOutlined, ReloadOutlined, MailOutlined, PhoneOutlined,
  GlobalOutlined, FilterOutlined, TrophyOutlined, TeamOutlined,
  ThunderboltOutlined, RiseOutlined,
} from '@ant-design/icons';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement,
  Title, Tooltip as ChartTooltip, Legend,
} from 'chart.js';
import { apiWithFallback } from '../services/api';
import { ThemeContext } from '../context/ThemeContext';
import dayjs from 'dayjs';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, ChartTooltip, Legend);

const { RangePicker } = DatePicker;

const C = {
  primary: '#6366f1', cyan: '#06b6d4', green: '#22c55e',
  amber: '#f59e0b', red: '#ef4444', muted: '#94a3b8',
};

const statusColor = (v) => ({
  hot: C.green, warm: C.amber, cold: '#3b82f6',
  converted: C.green, contacted: C.cyan, qualified: C.primary,
}[v] || '#94a3b8');

/* ─── KPI Card ─────────────────────────────────────────────── */
const KpiCard = ({ icon, label, value, sub, color, isDark }) => (
  <Card
    styles={{ body: { padding: '18px 20px' } }}
    style={{
      border: `1px solid ${isDark ? 'rgba(99,102,241,0.12)' : 'rgba(0,0,0,0.07)'}`,
      borderRadius: 12,
      background: isDark ? 'rgba(255,255,255,0.02)' : '#fff',
    }}
  >
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
      <div style={{
        width: 40, height: 40, borderRadius: 10,
        background: `${color}18`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 18, color }}>{icon}</span>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
          {label}
        </div>
        <div style={{
          fontSize: typeof value === 'string' && value.length > 12 ? 13 : 22,
          fontWeight: 800, color: 'var(--text-stat)', lineHeight: 1.2,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {value}
        </div>
        {sub && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>{sub}</div>
        )}
      </div>
    </div>
  </Card>
);

/* ─────────────────────────────────────────────────────────── */

const Analytics = () => {
  const { isDark } = useContext(ThemeContext);

  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const [scoreDist, setScoreDist]       = useState([]);
  const [sourcePerf, setSourcePerf]     = useState([]);
  const [statsTotal, setStatsTotal]     = useState(null);
  const [statsQual,  setStatsQual]      = useState(null);

  const [topLeads, setTopLeads]         = useState([]);
  const [topTotal, setTopTotal]         = useState(0);
  const [topPage, setTopPage]           = useState(1);
  const [topLoading, setTopLoading]     = useState(false);

  const [minScore, setMinScore]         = useState(undefined);
  const [sourceFilter, setSourceFilter] = useState(undefined);
  const [dateRange, setDateRange]       = useState(null);
  const [exporting, setExporting]       = useState(false);

  useEffect(() => { fetchCore(); }, []);
  useEffect(() => { fetchTopLeads(); }, [topPage, minScore, sourceFilter, dateRange]); // eslint-disable-line

  /* ── data fetching ─────────────────────────────────────── */

  const fetchCore = async () => {
    try {
      setLoading(true);
      setError(null);
      const [distRes, srcRes, statsRes] = await Promise.allSettled([
        apiWithFallback('/analytics/score-distribution', 'get'),
        apiWithFallback('/analytics/source-performance', 'get'),
        apiWithFallback('/leads/stats', 'get'),
      ]);
      if (distRes.status  === 'fulfilled') setScoreDist(distRes.value?.data?.data?.buckets   || []);
      if (srcRes.status   === 'fulfilled') setSourcePerf(srcRes.value?.data?.data?.sources   || []);
      if (statsRes.status === 'fulfilled') {
        const st = statsRes.value?.data?.stats || {};
        setStatsTotal(st.total_leads ?? null);
        setStatsQual(st.qualified_leads ?? null);
      }
      if (distRes.status === 'rejected' && srcRes.status === 'rejected')
        setError('Could not reach the server. Check your connection and try again.');
    } catch {
      setError('Failed to load analytics data.');
    } finally {
      setLoading(false);
    }
  };

  const buildLeadParams = useCallback((page, perPage) => {
    const params = { page, per_page: perPage, sort_by: 'qualification_score', sort_order: 'desc' };
    if (minScore !== undefined) params.min_score  = minScore;
    if (sourceFilter)           params.source     = sourceFilter;
    if (dateRange?.[0])         params.date_from  = dateRange[0].format('YYYY-MM-DD');
    if (dateRange?.[1])         params.date_to    = dateRange[1].format('YYYY-MM-DD');
    return params;
  }, [minScore, sourceFilter, dateRange]);

  const fetchTopLeads = useCallback(async () => {
    try {
      setTopLoading(true);
      const res = await apiWithFallback('/leads/', 'get', null, { params: buildLeadParams(topPage, 10) });
      setTopLeads(res?.data?.leads || []);
      setTopTotal(res?.data?.total || 0);
    } catch {
      setTopLeads([]);
      setTopTotal(0);
    } finally {
      setTopLoading(false);
    }
  }, [topPage, buildLeadParams]);

  const handleExportCSV = async () => {
    try {
      setExporting(true);
      const res   = await apiWithFallback('/leads/', 'get', null, { params: buildLeadParams(1, 100) });
      const leads = res?.data?.leads || [];
      if (!leads.length) { message.warning('No leads match the current filters.'); return; }
      const headers = ['Name', 'Email', 'Phone', 'Company', 'Position', 'Country', 'Industry', 'Score', 'Status', 'Source', 'Created'];
      const rows    = leads.map(l => [
        l.name || '', l.email || '', l.phone || '', l.company || '',
        l.position || '', l.country || '', l.industry || '',
        l.qualification_score ?? '', l.status || '', l.source || '',
        l.created_at ? new Date(l.created_at).toLocaleDateString() : '',
      ]);
      const csv  = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
      const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url;
      a.download = `leads_${dayjs().format('YYYY-MM-DD')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      message.success(`${leads.length} leads exported`);
    } catch {
      message.error('Export failed. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  /* ── derived KPIs ──────────────────────────────────────── */

  const totalLeads    = statsTotal ?? sourcePerf.reduce((s, r) => s + (r.total || 0), 0);
  const totalQual     = statsQual  ?? sourcePerf.reduce((s, r) => s + (r.qualified || 0), 0);
  const qualPct       = totalLeads > 0 ? Math.round((totalQual / totalLeads) * 100) : 0;
  const avgScore      = sourcePerf.length
    ? Math.round(sourcePerf.reduce((s, r) => s + (r.avg_score || 0), 0) / sourcePerf.length)
    : 0;
  const topSource     = [...sourcePerf].sort((a, b) => (b.qual_rate || 0) - (a.qual_rate || 0))[0]?.source || '—';

  /* ── theme helpers ─────────────────────────────────────── */

  const tickColor  = isDark ? '#94a3b8' : '#64748b';
  const gridColor  = isDark ? 'rgba(99,102,241,0.08)' : 'rgba(0,0,0,0.06)';
  const cardBorder = isDark ? 'rgba(99,102,241,0.12)' : 'rgba(0,0,0,0.07)';
  const filterBg   = isDark ? 'rgba(255,255,255,0.03)' : '#f8faff';
  const headerBg   = isDark ? 'rgba(255,255,255,0.02)' : '#f8faff';

  /* ── score distribution chart ──────────────────────────── */

  const distChartData = {
    labels: scoreDist.map(b => b.range),
    datasets: [{
      label: 'Leads',
      data: scoreDist.map(b => b.count),
      backgroundColor: scoreDist.map(b =>
        b.low >= 70 ? 'rgba(34,197,94,0.75)'  :
        b.low >= 40 ? 'rgba(245,158,11,0.75)' :
                      'rgba(99,102,241,0.65)'
      ),
      borderRadius: 6,
      borderSkipped: false,
    }],
  };

  const distChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: (ctx) => `  ${ctx.parsed.x} leads` } },
    },
    scales: {
      x: { ticks: { color: tickColor, font: { size: 11 } }, grid: { color: gridColor, drawBorder: false } },
      y: { ticks: { color: tickColor, font: { size: 11 } }, grid: { display: false } },
    },
  };

  /* ── source performance columns ────────────────────────── */

  const colHeader = (label, tip) => (
    <Tooltip title={tip} placement="top">
      <span style={{ whiteSpace: 'nowrap', cursor: tip ? 'help' : 'default', borderBottom: tip ? '1px dashed rgba(255,255,255,0.25)' : 'none' }}>
        {label}
      </span>
    </Tooltip>
  );

  const sourceColumns = [
    {
      title: colHeader('Source', 'Lead collection channel'),
      dataIndex: 'source', key: 'source', width: 160,
      render: (v) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: C.cyan, flexShrink: 0 }} />
          <span style={{ fontWeight: 600, color: 'var(--text-stat)', fontSize: 13 }}>{v}</span>
        </div>
      ),
    },
    {
      title: colHeader('Total', 'Total leads collected from this source'),
      dataIndex: 'total', key: 'total', width: 90, align: 'right',
      sorter: (a, b) => a.total - b.total,
      render: (v) => <span style={{ fontWeight: 700, color: 'var(--text-stat)' }}>{(v || 0).toLocaleString()}</span>,
    },
    {
      title: colHeader('Qualified', 'Leads with AI score ≥ 60'),
      dataIndex: 'qualified', key: 'qualified', width: 105, align: 'right',
      sorter: (a, b) => a.qualified - b.qualified,
      render: (v) => <span style={{ color: C.cyan, fontWeight: 600 }}>{(v || 0).toLocaleString()}</span>,
    },
    {
      title: colHeader('Qual Rate', 'Percentage of leads that are qualified (score ≥ 60)'),
      dataIndex: 'qual_rate', key: 'qual_rate', width: 160,
      sorter: (a, b) => a.qual_rate - b.qual_rate,
      defaultSortOrder: 'descend',
      render: (v) => {
        const color = v >= 60 ? C.green : v >= 30 ? C.amber : C.red;
        return (
          <div>
            <div style={{ marginBottom: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color }}>{v}%</span>
            </div>
            <Progress percent={v} size={['100%', 4]} strokeColor={color} showInfo={false} style={{ margin: 0 }} />
          </div>
        );
      },
    },
    {
      title: colHeader('Avg Score', 'Average AI qualification score (0–100)'),
      dataIndex: 'avg_score', key: 'avg_score', width: 110, align: 'center',
      sorter: (a, b) => a.avg_score - b.avg_score,
      render: (v) => {
        const color = v >= 70 ? C.green : v >= 40 ? C.amber : C.red;
        return (
          <Tag style={{
            background: `${color}18`, color, border: `1px solid ${color}30`,
            fontWeight: 700, fontSize: 12, minWidth: 40, textAlign: 'center', borderRadius: 6,
          }}>
            {v}
          </Tag>
        );
      },
    },
    {
      title: colHeader('Contacted', 'Leads that have been contacted'),
      dataIndex: 'contacted', key: 'contacted', width: 110, align: 'right',
      sorter: (a, b) => a.contacted - b.contacted,
      render: (v) => <span style={{ color: 'var(--text-secondary)' }}>{v ?? 0}</span>,
    },
    {
      title: colHeader('Converted', 'Leads successfully converted to customers'),
      dataIndex: 'converted', key: 'converted', width: 110, align: 'right',
      sorter: (a, b) => a.converted - b.converted,
      render: (v) => (
        <span style={{ color: v > 0 ? C.green : 'var(--text-muted)', fontWeight: v > 0 ? 700 : 400 }}>
          {v ?? 0}
        </span>
      ),
    },
  ];

  /* ── top leads columns ─────────────────────────────────── */

  const leadsColumns = [
    {
      title: 'Name', dataIndex: 'name', key: 'name', width: 170,
      render: (text, r) => (
        <div>
          <div style={{ fontWeight: 600, color: 'var(--text-stat)', fontSize: 13, lineHeight: 1.3 }}>
            {text || '—'}
          </div>
          {r.position && (
            <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 2 }}>{r.position}</div>
          )}
        </div>
      ),
    },
    {
      title: 'Company', dataIndex: 'company', key: 'company', width: 150,
      render: (v) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: 13, fontWeight: 500 }}>{v || '—'}</span>
      ),
    },
    {
      title: 'Country', dataIndex: 'country', key: 'country', width: 110,
      render: (v) => <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v || '—'}</span>,
    },
    {
      title: 'Industry', dataIndex: 'industry', key: 'industry', width: 130,
      render: (v) => v
        ? <Tag style={{ background: `${C.primary}12`, color: C.primary, border: 'none', fontSize: 11, borderRadius: 5 }}>{v}</Tag>
        : <span style={{ color: 'var(--text-muted)' }}>—</span>,
    },
    {
      title: 'Score', dataIndex: 'qualification_score', key: 'score', width: 90, align: 'center',
      render: (v) => {
        const s     = Math.round(v || 0);
        const color = s >= 70 ? C.green : s >= 40 ? C.amber : C.red;
        return (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
            <span style={{
              fontWeight: 800, fontSize: 15, color,
              background: `${color}15`, borderRadius: 6,
              padding: '2px 10px', display: 'inline-block',
            }}>
              {s}
            </span>
            <Progress
              percent={s} size={['52px', 3]}
              strokeColor={color} showInfo={false}
              style={{ margin: 0 }}
            />
          </div>
        );
      },
    },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 110,
      render: (v) => {
        const sk = (v || 'pending').toLowerCase();
        const c  = statusColor(sk);
        return (
          <Tag style={{
            background: `${c}15`, color: c,
            border: `1px solid ${c}30`,
            fontWeight: 600, fontSize: 11, borderRadius: 6,
          }}>
            <span style={{
              display: 'inline-block', width: 5, height: 5,
              borderRadius: '50%', background: c,
              marginRight: 5, verticalAlign: 'middle',
            }} />
            {sk.charAt(0).toUpperCase() + sk.slice(1)}
          </Tag>
        );
      },
    },
    {
      title: 'Contact', key: 'contact', width: 80, align: 'center',
      render: (_, r) => (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          {r.email        && <Tooltip title={r.email}><a href={`mailto:${r.email}`} style={{ color: C.cyan, fontSize: 14 }}><MailOutlined /></a></Tooltip>}
          {r.phone        && <Tooltip title={r.phone}><a href={`tel:${r.phone}`}   style={{ color: C.green, fontSize: 14 }}><PhoneOutlined /></a></Tooltip>}
          {r.linkedin_url && <Tooltip title="LinkedIn"><a href={r.linkedin_url} target="_blank" rel="noreferrer" style={{ color: '#0077b5', fontSize: 14 }}><GlobalOutlined /></a></Tooltip>}
          {!r.email && !r.phone && !r.linkedin_url && <span style={{ color: 'var(--text-muted)' }}>—</span>}
        </div>
      ),
    },
    {
      title: 'Source', dataIndex: 'source', key: 'source', width: 120,
      render: (v) => v
        ? <Tag style={{ background: isDark ? 'rgba(255,255,255,0.06)' : '#f1f5f9', color: 'var(--text-secondary)', border: 'none', fontSize: 11, borderRadius: 5 }}>{v}</Tag>
        : <span style={{ color: 'var(--text-muted)' }}>—</span>,
    },
    {
      title: 'Added', dataIndex: 'created_at', key: 'added', width: 95, align: 'right',
      render: (v) => (
        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
          {v ? new Date(v).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
        </span>
      ),
    },
  ];

  const uniqueSources    = [...new Set(sourcePerf.map(s => s.source))];
  const hasActiveFilters = minScore !== undefined || sourceFilter || dateRange;

  /* ── render ────────────────────────────────────────────── */

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 500 }}>
        <Spin size="large" tip="Loading analytics..." />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px 28px', maxWidth: 1400 }}>

      {error && (
        <Alert type="error" message={error} style={{ marginBottom: 20 }}
          action={<Button size="small" icon={<ReloadOutlined />} onClick={fetchCore}>Retry</Button>}
        />
      )}

      {/* ── Page header ──────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 800, color: 'var(--text-stat)' }}>
            Analytics & Reports
          </h1>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
            Score quality, source performance, and lead export
          </p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={fetchCore} style={{ borderRadius: 8 }}>
          Refresh
        </Button>
      </div>

      {/* ── KPI cards ────────────────────────────────────── */}
      <Row gutter={[14, 14]} style={{ marginBottom: 28 }}>
        <Col xs={12} sm={6}>
          <KpiCard icon={<TeamOutlined />}       label="Total Leads"    value={(totalLeads ?? topTotal).toLocaleString()} sub="in database"             color={C.primary} isDark={isDark} />
        </Col>
        <Col xs={12} sm={6}>
          <KpiCard icon={<TrophyOutlined />}     label="Qualified"      value={totalQual.toLocaleString()} sub={`${qualPct}% of total`} color={C.green}   isDark={isDark} />
        </Col>
        <Col xs={12} sm={6}>
          <KpiCard icon={<ThunderboltOutlined />} label="Avg Score"     value={avgScore}  sub="across all sources"                      color={C.amber}   isDark={isDark} />
        </Col>
        <Col xs={12} sm={6}>
          <KpiCard icon={<RiseOutlined />}        label="Top Source"    value={topSource} sub="highest qual rate"                       color={C.cyan}    isDark={isDark} />
        </Col>
      </Row>

      {/* ── Charts row ───────────────────────────────────── */}
      <Row gutter={[16, 16]} style={{ marginBottom: 28 }}>

        {/* Score Distribution */}
        <Col xs={24} lg={10}>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-stat)' }}>Score Distribution</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>Leads per AI score bracket</div>
          </div>
          <Card
            style={{ border: `1px solid ${cardBorder}`, borderRadius: 12 }}
            styles={{ body: { padding: '16px 20px 20px' } }}
          >
            <div style={{ display: 'flex', gap: 16, marginBottom: 14, flexWrap: 'wrap' }}>
              {[
                { label: 'Qualified', sub: '70–100', color: C.green },
                { label: 'Warm',      sub: '40–69',  color: C.amber },
                { label: 'Cold',      sub: '0–39',   color: C.primary },
              ].map(item => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 9, height: 9, borderRadius: 3, background: item.color, opacity: 0.85, display: 'inline-block' }} />
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    <strong style={{ color: item.color }}>{item.label}</strong> {item.sub}
                  </span>
                </div>
              ))}
            </div>
            <div style={{ height: 300 }}>
              {scoreDist.some(b => b.count > 0) ? (
                <Bar data={distChartData} options={distChartOptions} />
              ) : (
                <div style={{ textAlign: 'center', paddingTop: 110, color: 'var(--text-muted)', fontSize: 13 }}>
                  No scored leads yet
                </div>
              )}
            </div>
          </Card>
        </Col>

        {/* Source Performance */}
        <Col xs={24} lg={14}>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-stat)' }}>Source Performance</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>Quality breakdown by lead source — click headers to sort</div>
          </div>
          <Card
            style={{ border: `1px solid ${cardBorder}`, borderRadius: 12 }}
            styles={{ body: { padding: '0 0 8px' } }}
          >
            <Table
              columns={sourceColumns}
              dataSource={sourcePerf.map((s, i) => ({ ...s, key: i }))}
              pagination={false}
              size="small"
              scroll={{ x: 845, y: 320 }}
              locale={{
                emptyText: (
                  <div style={{ padding: '40px 0', color: 'var(--text-muted)', textAlign: 'center', fontSize: 13 }}>
                    No source data yet — collect some leads first
                  </div>
                ),
              }}
            />
          </Card>
        </Col>
      </Row>

      <Divider style={{ margin: '0 0 24px' }} />

      {/* ── Top Leads section header ──────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-stat)' }}>All Leads</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
            Sorted by qualification score — filter and export below
          </div>
        </div>
        <Button
          icon={<DownloadOutlined />}
          type="primary"
          loading={exporting}
          onClick={handleExportCSV}
          style={{ borderRadius: 8 }}
        >
          Export CSV{hasActiveFilters ? ' (filtered)' : ''}
        </Button>
      </div>

      {/* Filter bar */}
      <div style={{
        display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8,
        background: filterBg,
        border: `1px solid ${cardBorder}`,
        borderRadius: 10, padding: '10px 14px', marginBottom: 12,
      }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
          <FilterOutlined /> Filter
        </span>
        <Select
          placeholder="Min score"
          allowClear
          style={{ width: 160 }}
          value={minScore}
          onChange={(v) => { setMinScore(v); setTopPage(1); }}
          options={[
            { value: 0,  label: 'All scores' },
            { value: 70, label: 'Score ≥ 70  Qualified' },
            { value: 80, label: 'Score ≥ 80  High' },
            { value: 90, label: 'Score ≥ 90  Top' },
          ]}
        />
        <Select
          placeholder="All sources"
          allowClear
          style={{ width: 160 }}
          value={sourceFilter}
          onChange={(v) => { setSourceFilter(v || undefined); setTopPage(1); }}
          options={uniqueSources.map(s => ({ value: s, label: s }))}
        />
        <RangePicker
          value={dateRange}
          onChange={(val) => { setDateRange(val); setTopPage(1); }}
          placeholder={['From date', 'To date']}
          style={{ minWidth: 210 }}
        />
        {hasActiveFilters && (
          <Button
            size="small" type="text"
            style={{ color: C.primary, fontWeight: 600 }}
            onClick={() => { setMinScore(undefined); setSourceFilter(undefined); setDateRange(null); setTopPage(1); }}
          >
            Clear
          </Button>
        )}
      </div>

      {/* Top leads table */}
      <Card
        style={{ border: `1px solid ${cardBorder}`, borderRadius: 12 }}
        styles={{ body: { padding: 0 } }}
      >
        {topTotal > 0 && (
          <div style={{
            padding: '10px 16px 6px',
            background: headerBg,
            borderBottom: `1px solid ${cardBorder}`,
            borderRadius: '12px 12px 0 0',
            fontSize: 12, color: 'var(--text-muted)',
          }}>
            <strong style={{ color: 'var(--text-stat)' }}>{topTotal.toLocaleString()}</strong>
            {hasActiveFilters ? ' leads matching filters' : ' total leads'} · sorted by highest score
          </div>
        )}
        <Table
          columns={leadsColumns}
          dataSource={topLeads.map((l, i) => ({ ...l, key: l.id || i }))}
          loading={topLoading}
          pagination={{
            current: topPage,
            pageSize: 10,
            total: topTotal,
            onChange: (p) => setTopPage(p),
            showSizeChanger: false,
            showTotal: (t, range) => `${range[0]}–${range[1]} of ${t.toLocaleString()}`,
            style: { padding: '10px 16px' },
          }}
          size="small"
          scroll={{ x: 1060 }}
          locale={{
            emptyText: (
              <div style={{ padding: '48px 0', color: 'var(--text-muted)', textAlign: 'center', fontSize: 13 }}>
                {hasActiveFilters
                  ? 'No leads match the current filters — try adjusting or clearing them'
                  : 'No leads yet — collect some to see them here'}
              </div>
            ),
          }}
        />
      </Card>

    </div>
  );
};

export default Analytics;
