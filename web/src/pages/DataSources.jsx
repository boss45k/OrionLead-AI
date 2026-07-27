import { useState, useEffect, useCallback } from 'react';
import {
  Card, Button, Table, Modal, Form, Input, Select, message,
  Space, Tag, Row, Col, Progress, Popconfirm, Spin, Switch, Alert,
  Tooltip, Upload, Divider, Typography, InputNumber,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, SyncOutlined, ReloadOutlined,
  EditOutlined, CloudUploadOutlined, ApiOutlined, DatabaseOutlined,
  GlobalOutlined, FileTextOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, ClockCircleOutlined, ThunderboltOutlined,
  InfoCircleOutlined, LockOutlined, SettingOutlined, RocketOutlined,
  StarOutlined, WarningOutlined,
} from '@ant-design/icons';
import { apiWithFallback } from '../services/api';
import axios from 'axios';

const { Text } = Typography;

const TYPE_META = {
  API:      { icon: <ApiOutlined />,      color: '#06b6d4', label: 'API',      bg: 'rgba(6,182,212,0.1)' },
  CSV:      { icon: <FileTextOutlined />, color: '#8b5cf6', label: 'CSV',      bg: 'rgba(139,92,246,0.1)' },
  Database: { icon: <DatabaseOutlined />, color: '#f59e0b', label: 'Database', bg: 'rgba(245,158,11,0.1)' },
  Web:      { icon: <GlobalOutlined />,   color: '#22c55e', label: 'Web',      bg: 'rgba(34,197,94,0.1)' },
};

const FREQ_OPTIONS = [
  { label: 'Manual only', value: 'manual' },
  { label: 'Every hour',  value: 'hourly' },
  { label: 'Daily',       value: 'daily' },
  { label: 'Weekly',      value: 'weekly' },
];

function timeAgo(iso) {
  if (!iso) return null;
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)    return 'just now';
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function StatusBadge({ status, enabled, lastError }) {
  if (!enabled) {
    return <Tag icon={<ClockCircleOutlined />} color="default" style={{ border: 'none' }}>Disabled</Tag>;
  }
  if (status === 'error') {
    return (
      <Tooltip title={lastError || 'Last sync failed'}>
        <Tag icon={<ExclamationCircleOutlined />} color="error" style={{ border: 'none' }}>Error</Tag>
      </Tooltip>
    );
  }
  if (status === 'active') {
    return <Tag icon={<CheckCircleOutlined />} color="success" style={{ border: 'none' }}>Active</Tag>;
  }
  if (status === 'inactive') {
    return (
      <Tooltip title="API key not configured">
        <Tag icon={<WarningOutlined />} color="warning" style={{ border: 'none' }}>No API Key</Tag>
      </Tooltip>
    );
  }
  return <Tag icon={<ClockCircleOutlined />} color="default" style={{ border: 'none' }}>Idle</Tag>;
}

function ActionBadge({ action }) {
  if (action === 'enrich') {
    return (
      <Tag
        icon={<ThunderboltOutlined />}
        style={{ background: 'rgba(245,158,11,0.12)', color: '#f59e0b', border: 'none', fontSize: 10 }}
      >
        Enrichment
      </Tag>
    );
  }
  return (
    <Tag
      icon={<RocketOutlined />}
      style={{ background: 'rgba(34,197,94,0.12)', color: '#22c55e', border: 'none', fontSize: 10 }}
    >
      Collection
    </Tag>
  );
}

const isSystem = (r) => !!(r.config?.system);

const DataSources = () => {
  const [sources, setSources]                   = useState([]);
  const [stats, setStats]                       = useState({});
  const [loading, setLoading]                   = useState(true);
  const [fetchError, setFetchError]             = useState(null);
  const [addModalVisible, setAddModalVisible]   = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [cfgModalVisible, setCfgModalVisible]   = useState(false);
  const [editingSource, setEditingSource]       = useState(null);
  const [syncingId, setSyncingId]               = useState(null);
  const [syncResult, setSyncResult]             = useState(null);
  const [togglingId, setTogglingId]             = useState(null);
  const [deletingId, setDeletingId]             = useState(null);
  const [addType, setAddType]                   = useState('API');
  const [editType, setEditType]                 = useState('API');
  const [csvUploading, setCsvUploading]         = useState(false);
  const [addForm]  = Form.useForm();
  const [editForm] = Form.useForm();
  const [cfgForm]  = Form.useForm();

  const fetchSources = useCallback(async () => {
    try {
      setLoading(true);
      setFetchError(null);
      const res = await apiWithFallback('/sources', 'get');
      const list = res.data?.data || [];
      setSources(Array.isArray(list) ? list : []);
      setStats(res.data?.stats || {});
    } catch {
      setFetchError('Failed to load data sources. Check your connection.');
      setSources([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSources(); }, [fetchSources]);

  // ── Add (user-defined sources only) ─────────────────────────────────────────
  const handleAdd = async (values) => {
    try {
      setLoading(true);
      const payload = {
        name:           values.name,
        type:           values.type,
        url:            values.url || '',
        api_key:        values.api_key || '',
        sync_frequency: values.sync_frequency || 'manual',
        enabled:        true,
        config:         values.type === 'Database'
          ? { query: values.db_query || 'SELECT * FROM leads LIMIT 1000' }
          : {},
      };
      await apiWithFallback('/sources', 'post', payload);
      message.success('Data source added successfully');
      addForm.resetFields();
      setAddModalVisible(false);
      setAddType('API');
      fetchSources();
    } catch (err) {
      message.error('Failed to add source: ' + (err?.response?.data?.message || err?.message || 'Unknown'));
    } finally {
      setLoading(false);
    }
  };

  // ── Edit (user-defined sources only) ─────────────────────────────────────────
  const openEdit = (source) => {
    setEditingSource(source);
    setEditType(source.type);
    editForm.setFieldsValue({
      name:           source.name,
      type:           source.type,
      url:            source.url,
      sync_frequency: source.sync_frequency,
      db_query:       source.config?.query || '',
    });
    setEditModalVisible(true);
  };

  const handleEdit = async (values) => {
    try {
      setLoading(true);
      const payload = {
        name:           values.name,
        type:           values.type,
        url:            values.url || '',
        sync_frequency: values.sync_frequency || 'manual',
        config:         values.type === 'Database'
          ? { ...(editingSource?.config || {}), query: values.db_query || 'SELECT * FROM leads LIMIT 1000' }
          : (editingSource?.config || {}),
      };
      if (values.api_key) payload.api_key = values.api_key;
      await apiWithFallback(`/sources/${editingSource.id}`, 'put', payload);
      message.success('Source updated');
      setEditModalVisible(false);
      setEditingSource(null);
      fetchSources();
    } catch (err) {
      message.error('Failed to update: ' + (err?.response?.data?.message || err?.message || 'Unknown'));
    } finally {
      setLoading(false);
    }
  };

  // ── Configure sync params (built-in sources) ─────────────────────────────────
  const openConfigure = (source) => {
    setEditingSource(source);
    const sc = source.config?.sync_config || {};
    const action = source.config?.action || 'collect';
    cfgForm.setFieldsValue({
      max_leads: sc.max_leads || (action === 'enrich' ? 50 : 40),
      keywords:  sc.keywords  || '',
      locations: (sc.locations || []).join(', '),
      titles:    (sc.titles    || []).join(', '),
      industries:(sc.industries|| []).join(', '),
    });
    setCfgModalVisible(true);
  };

  const handleConfigure = async (values) => {
    try {
      setLoading(true);
      const sync_config = {
        max_leads: values.max_leads || 40,
      };
      if (values.keywords)   sync_config.keywords   = values.keywords.trim();
      if (values.locations)  sync_config.locations  = values.locations.split(',').map(s => s.trim()).filter(Boolean);
      if (values.titles)     sync_config.titles     = values.titles.split(',').map(s => s.trim()).filter(Boolean);
      if (values.industries) sync_config.industries = values.industries.split(',').map(s => s.trim()).filter(Boolean);

      await apiWithFallback(`/sources/${editingSource.id}`, 'put', { sync_config });
      message.success('Sync parameters saved');
      setCfgModalVisible(false);
      setEditingSource(null);
      fetchSources();
    } catch (err) {
      message.error('Failed to save: ' + (err?.response?.data?.message || err?.message || 'Unknown'));
    } finally {
      setLoading(false);
    }
  };

  // ── Toggle ───────────────────────────────────────────────────────────────────
  const handleToggle = async (source) => {
    const newEnabled = !source.enabled;
    // Optimistic update — flip enabled immediately so status badge reacts
    setSources(prev => prev.map(s =>
      s.id === source.id ? { ...s, enabled: newEnabled } : s
    ));
    try {
      setTogglingId(source.id);
      await apiWithFallback(`/sources/${source.id}`, 'put', { enabled: newEnabled });
    } catch {
      // Revert on failure
      setSources(prev => prev.map(s =>
        s.id === source.id ? { ...s, enabled: source.enabled } : s
      ));
      message.error('Failed to toggle source');
    } finally {
      setTogglingId(null);
    }
  };

  // ── Sync ─────────────────────────────────────────────────────────────────────
  const handleSync = async (source) => {
    try {
      setSyncingId(source.id);
      setSyncResult(null);
      const res = await apiWithFallback(`/sources/${source.id}/sync`, 'post');
      const d   = res.data?.data || {};
      const msg = res.data?.message || `Synced ${d.synced_records || 0} new leads`;
      setSyncResult({ sourceId: source.id, success: true, message: msg, data: d });
      message.success(msg);
      fetchSources();
    } catch (err) {
      const errMsg = err?.response?.data?.message || err?.message || 'Sync failed';
      setSyncResult({ sourceId: source.id, success: false, message: errMsg });
      message.error(errMsg);
      fetchSources();
    } finally {
      setSyncingId(null);
    }
  };

  // ── Delete (user-defined only) ───────────────────────────────────────────────
  const handleDelete = async (sourceId) => {
    try {
      setDeletingId(sourceId);
      await apiWithFallback(`/sources/${sourceId}`, 'delete');
      setSources(prev => prev.filter(s => s.id !== sourceId));
      message.success('Source deleted');
      if (syncResult?.sourceId === sourceId) setSyncResult(null);
    } catch (err) {
      message.error('Failed to delete: ' + (err?.response?.data?.message || err?.message || 'Unknown'));
    } finally {
      setDeletingId(null);
    }
  };

  // ── CSV Upload ────────────────────────────────────────────────────────────────
  const handleCsvUpload = async (file, sourceId) => {
    try {
      setCsvUploading(true);
      const token = localStorage.getItem('authToken') || '';
      const formData = new FormData();
      formData.append('file', file);
      if (sourceId) formData.append('source_id', sourceId);
      const baseUrl = (process.env.REACT_APP_API_URL || 'http://localhost:5000') + '/api/v1';
      const res = await axios.post(`${baseUrl}/sources/upload`, formData, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
      });
      const d = res.data?.data || {};
      message.success(`CSV uploaded — ${d.row_count || 0} rows ready to sync`);
      fetchSources();
    } catch (err) {
      message.error('Upload failed: ' + (err?.response?.data?.message || err?.message || 'Unknown'));
    } finally {
      setCsvUploading(false);
    }
  };

  // ── Table columns ─────────────────────────────────────────────────────────────
  const columns = [
    {
      title: 'Source',
      key: 'source',
      width: 240,
      render: (_, r) => {
        const meta = TYPE_META[r.type] || TYPE_META.API;
        const sys  = isSystem(r);
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 9,
              background: meta.bg,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: meta.color, fontSize: 17, flexShrink: 0,
              border: sys ? `1px solid ${meta.color}33` : 'none',
            }}>
              {meta.icon}
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontWeight: 600, color: 'var(--text-stat)', fontSize: 13 }}>{r.name}</span>
                {sys && (
                  <Tooltip title="Built-in integration">
                    <StarOutlined style={{ fontSize: 11, color: '#6366f1' }} />
                  </Tooltip>
                )}
              </div>
              {r.description
                ? <div style={{ fontSize: 11, color: '#64748b', marginTop: 1, maxWidth: 180 }} className="truncate">{r.description}</div>
                : <Tag style={{ background: meta.bg, color: meta.color, border: 'none', fontSize: 10, marginTop: 2 }}>{meta.label}</Tag>
              }
            </div>
          </div>
        );
      },
    },
    {
      title: 'Type',
      key: 'action_type',
      width: 110,
      render: (_, r) => {
        const sys = isSystem(r);
        if (sys && r.action) return <ActionBadge action={r.action} />;
        const meta = TYPE_META[r.type] || TYPE_META.API;
        return (
          <Tag style={{ background: meta.bg, color: meta.color, border: 'none', fontSize: 10 }}>
            {meta.label}
          </Tag>
        );
      },
    },
    {
      title: 'Records',
      dataIndex: 'records',
      key: 'records',
      width: 85,
      align: 'center',
      render: (v) => (
        <span style={{ fontWeight: 700, color: 'var(--text-stat)', fontSize: 13 }}>
          {(v || 0).toLocaleString()}
        </span>
      ),
    },
    {
      title: 'Performance',
      dataIndex: 'performance',
      key: 'performance',
      width: 120,
      render: (p) => {
        const pct = Math.round(p || 0);
        const color = pct >= 80 ? '#22c55e' : pct >= 50 ? '#f59e0b' : '#ef4444';
        return (
          <div>
            <Progress percent={pct} size="small" strokeColor={color} showInfo={false} style={{ marginBottom: 2 }} />
            <span style={{ fontSize: 11, color }}>{pct}%</span>
          </div>
        );
      },
    },
    {
      title: 'Last Sync',
      dataIndex: 'last_sync',
      key: 'last_sync',
      width: 100,
      render: (ts) => {
        const ago = timeAgo(ts);
        return ago
          ? <Tooltip title={ts}><span style={{ color: '#64748b', fontSize: 12 }}>{ago}</span></Tooltip>
          : <span style={{ color: '#475569', fontSize: 12 }}>Never</span>;
      },
    },
    {
      title: 'Status',
      key: 'status',
      width: 115,
      render: (_, r) => <StatusBadge status={r.status} enabled={r.enabled} lastError={r.last_error} />,
    },
    {
      title: 'On',
      key: 'enabled',
      width: 55,
      align: 'center',
      render: (_, r) => (
        <Switch
          checked={r.enabled}
          loading={togglingId === r.id}
          onChange={() => handleToggle(r)}
          size="small"
        />
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 130,
      render: (_, r) => {
        const sys = isSystem(r);
        return (
          <Space size={4}>
            <Tooltip title="Sync now">
              <Button
                type="text" size="small"
                icon={<SyncOutlined spin={syncingId === r.id} />}
                loading={syncingId === r.id}
                disabled={!r.enabled || !!syncingId}
                onClick={() => handleSync(r)}
                style={{ color: '#06b6d4' }}
              />
            </Tooltip>

            {/* Built-in: Configure params | User-defined: Edit */}
            {sys ? (
              <Tooltip title="Configure sync parameters">
                <Button
                  type="text" size="small"
                  icon={<SettingOutlined />}
                  onClick={() => openConfigure(r)}
                  style={{ color: '#6366f1' }}
                />
              </Tooltip>
            ) : (
              <>
                {r.type === 'CSV' && (
                  <Tooltip title="Upload CSV">
                    <Button
                      type="text" size="small"
                      icon={<CloudUploadOutlined />}
                      loading={csvUploading}
                      onClick={() => {
                        const input = document.createElement('input');
                        input.type = 'file'; input.accept = '.csv';
                        input.onchange = (e) => { const f = e.target.files[0]; if (f) handleCsvUpload(f, r.id); };
                        input.click();
                      }}
                      style={{ color: '#8b5cf6' }}
                    />
                  </Tooltip>
                )}
                <Tooltip title="Edit">
                  <Button
                    type="text" size="small"
                    icon={<EditOutlined />}
                    onClick={() => openEdit(r)}
                    style={{ color: '#f59e0b' }}
                  />
                </Tooltip>
                <Popconfirm
                  title="Delete this source?"
                  description="This cannot be undone."
                  onConfirm={() => handleDelete(r.id)}
                  okText="Delete" okButtonProps={{ danger: true }}
                >
                  <Button
                    type="text" size="small"
                    icon={<DeleteOutlined />}
                    loading={deletingId === r.id}
                    danger
                  />
                </Popconfirm>
              </>
            )}
          </Space>
        );
      },
    },
  ];

  // ── Shared form fields (user-defined add/edit) ────────────────────────────────
  const TypeFields = ({ type, onTypeChange }) => (
    <>
      <Form.Item label="Source Name" name="name" rules={[{ required: true, message: 'Required' }]}>
        <Input placeholder="e.g., HubSpot API, Leads Export" />
      </Form.Item>
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item label="Source Type" name="type" rules={[{ required: true }]}>
            <Select
              options={Object.entries(TYPE_META).map(([v, m]) => ({
                label: <Space><span style={{ color: m.color }}>{m.icon}</span>{m.label}</Space>,
                value: v,
              }))}
              onChange={onTypeChange}
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="Sync Schedule" name="sync_frequency" initialValue="manual">
            <Select options={FREQ_OPTIONS} />
          </Form.Item>
        </Col>
      </Row>

      {type === 'API' && (
        <>
          <Form.Item label="API Endpoint URL" name="url" rules={[{ required: true, message: 'Required' }, { type: 'url', message: 'Enter a valid URL' }]}>
            <Input placeholder="https://api.example.com/v1/leads" />
          </Form.Item>
          <Form.Item label={<span>API Key <Text type="secondary" style={{ fontSize: 11 }}>(stored masked)</Text></span>} name="api_key">
            <Input.Password placeholder="sk-..." />
          </Form.Item>
        </>
      )}

      {type === 'CSV' && (
        <Form.Item label="CSV File Path (or upload below)" name="url">
          <Input placeholder="/uploads/leads.csv  — or leave blank and upload" />
        </Form.Item>
      )}

      {type === 'Database' && (
        <>
          <Form.Item label="Connection String" name="url" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="postgresql://user:pass@host:5432/dbname" />
          </Form.Item>
          <Form.Item label="SQL Query" name="db_query" initialValue="SELECT * FROM leads LIMIT 1000">
            <Input.TextArea rows={3} placeholder="SELECT name, email, company FROM contacts LIMIT 500" />
          </Form.Item>
        </>
      )}

      {type === 'Web' && (
        <Alert type="info" showIcon icon={<InfoCircleOutlined />}
          message="Web sources use the AI Collect engine"
          description="Run web collection from the Leads page → Collect from Web. Web sources are tracked here for record-keeping."
          style={{ marginTop: 4 }}
        />
      )}
    </>
  );

  // ── Configure modal content (built-in sources) ────────────────────────────────
  const isEnrich = editingSource?.config?.action === 'enrich';
  const isWebSource = ['web_public', 'social_media'].includes(editingSource?.config?.system_key);

  // ── Summary stats ─────────────────────────────────────────────────────────────
  const systemSources = sources.filter(isSystem);
  const userSources   = sources.filter(s => !isSystem(s));
  const activeCt      = stats.active_sources || 0;
  const totalRecords  = stats.total_records  || 0;
  const avgPerf       = Math.round(stats.average_performance || 0);
  const lastSync      = timeAgo(stats.last_sync);
  const apiKeysSet    = systemSources.filter(s => s.status === 'active').length;

  if (loading && sources.length === 0) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 500 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px 28px' }}>
      {fetchError && (
        <Alert type="error" message={fetchError} style={{ marginBottom: 16 }}
          action={<Button size="small" icon={<ReloadOutlined />} onClick={fetchSources}>Retry</Button>}
        />
      )}

      {/* Header */}
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ margin: '0 0 4px', fontSize: 26, fontWeight: 700 }}>Data Sources</h1>
          <p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>
            {systemSources.length} built-in integrations · {userSources.length} custom sources · {activeCt} active
          </p>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchSources} loading={loading}>Refresh</Button>
          <Button
            type="primary" icon={<PlusOutlined />}
            onClick={() => { setAddModalVisible(true); setAddType('API'); addForm.resetFields(); addForm.setFieldsValue({ type: 'API', sync_frequency: 'manual' }); }}
            style={{ background: 'linear-gradient(135deg,#06b6d4,#6366f1)', border: 'none' }}
          >
            Add Custom Source
          </Button>
        </Space>
      </div>

      {/* Stats cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {[
          {
            title: 'Built-in Integrations',
            value: systemSources.length,
            suffix: `${apiKeysSet} API keys configured`,
            color: '#6366f1', icon: <StarOutlined />,
          },
          {
            title: 'Total Leads Tracked',
            value: totalRecords.toLocaleString(),
            suffix: 'across all sources',
            color: '#22c55e', icon: <CheckCircleOutlined />,
          },
          {
            title: 'Avg Sync Performance',
            value: `${avgPerf}%`,
            suffix: <Progress percent={avgPerf} size="small" strokeColor={avgPerf >= 70 ? '#22c55e' : '#f59e0b'} showInfo={false} style={{ width: 100, marginTop: 4 }} />,
            color: '#f59e0b', icon: <ThunderboltOutlined />,
          },
          {
            title: 'Last Sync',
            value: lastSync || '—',
            suffix: 'most recent activity',
            color: '#06b6d4', icon: <ClockCircleOutlined />,
          },
        ].map((item, i) => (
          <Col xs={24} sm={12} lg={6} key={i}>
            <Card styles={{ body: { padding: '18px 20px' } }} style={{ borderLeft: `3px solid ${item.color}`, borderRadius: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={{ color: '#64748b', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.8, fontWeight: 600, marginBottom: 6 }}>{item.title}</div>
                  <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-stat)', lineHeight: 1.1 }}>{item.value}</div>
                  <div style={{ color: '#64748b', fontSize: 12, marginTop: 6 }}>{item.suffix}</div>
                </div>
                <div style={{ fontSize: 22, color: item.color, opacity: 0.6 }}>{item.icon}</div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* Sync result banner */}
      {syncResult && (
        <Alert
          type={syncResult.success ? 'success' : 'error'}
          message={syncResult.message}
          description={syncResult.success && syncResult.data && (
            <span>
              {syncResult.data.synced_records} new leads
              {syncResult.data.duration_seconds != null && ` · ${syncResult.data.duration_seconds}s`}
              {syncResult.data.total_records != null && ` · ${syncResult.data.total_records} total records`}
            </span>
          )}
          showIcon closable onClose={() => setSyncResult(null)}
          style={{ marginBottom: 16, borderRadius: 8 }}
        />
      )}

      {/* Built-in integrations section */}
      <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
        <StarOutlined style={{ color: '#6366f1' }} />
        <span style={{ fontWeight: 600, fontSize: 14 }}>Built-in Integrations</span>
        <Tag style={{ background: 'rgba(99,102,241,0.1)', color: '#6366f1', border: 'none' }}>
          {systemSources.length} sources
        </Tag>
      </div>

      <Card styles={{ body: { padding: 0 } }} style={{ borderRadius: 10, marginBottom: 24 }}>
        <Table
          columns={columns}
          dataSource={systemSources.map((s, i) => ({ ...s, key: s.id ?? `sys-${i}` }))}
          loading={loading}
          pagination={false}
          scroll={{ x: 900 }}
          size="middle"
          locale={{ emptyText: (
            <div style={{ padding: '32px 0', textAlign: 'center', color: '#64748b' }}>
              <StarOutlined style={{ fontSize: 28, marginBottom: 8, opacity: 0.4 }} />
              <div>Built-in integrations loading…</div>
            </div>
          )}}
        />
      </Card>

      {/* Custom sources section */}
      <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
        <DatabaseOutlined style={{ color: '#06b6d4' }} />
        <span style={{ fontWeight: 600, fontSize: 14 }}>Custom Sources</span>
        <Tag style={{ background: 'rgba(6,182,212,0.1)', color: '#06b6d4', border: 'none' }}>
          {userSources.length} sources
        </Tag>
      </div>

      <Card styles={{ body: { padding: 0 } }} style={{ borderRadius: 10 }}>
        <Table
          columns={columns}
          dataSource={userSources.map((s, i) => ({ ...s, key: s.id ?? `usr-${i}` }))}
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (t) => `${t} sources` }}
          scroll={{ x: 900 }}
          size="middle"
          locale={{ emptyText: (
            <div style={{ padding: '40px 0', textAlign: 'center', color: '#64748b' }}>
              <DatabaseOutlined style={{ fontSize: 36, marginBottom: 12, opacity: 0.4 }} />
              <div style={{ fontWeight: 600 }}>No custom sources yet</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Add an API endpoint, CSV file, or external database</div>
              <Button
                type="primary" icon={<PlusOutlined />} style={{ marginTop: 12 }}
                onClick={() => { setAddModalVisible(true); addForm.setFieldsValue({ type: 'API', sync_frequency: 'manual' }); }}
              >
                Add Source
              </Button>
            </div>
          )}}
        />
      </Card>

      {/* ── Add Source Modal ── */}
      <Modal
        title={<div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><PlusOutlined style={{ color: '#06b6d4', fontSize: 18 }} /><span>Add Custom Source</span></div>}
        open={addModalVisible}
        onCancel={() => { setAddModalVisible(false); addForm.resetFields(); }}
        footer={null} width={580}
      >
        <Divider style={{ margin: '12px 0 20px' }} />
        <Form form={addForm} layout="vertical" onFinish={handleAdd} initialValues={{ type: 'API', sync_frequency: 'manual' }}>
          <TypeFields type={addType} onTypeChange={setAddType} />
          {addType === 'CSV' && (
            <Form.Item label="Upload CSV file">
              <Upload.Dragger accept=".csv" multiple={false} showUploadList={false}
                customRequest={({ file, onSuccess }) => { handleCsvUpload(file, null); onSuccess('ok'); }}
                style={{ borderRadius: 8 }}
              >
                <p className="ant-upload-drag-icon"><CloudUploadOutlined style={{ color: '#06b6d4', fontSize: 28 }} /></p>
                <p style={{ margin: 0, fontWeight: 500 }}>Drop CSV here or click to browse</p>
                <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 12 }}>Columns: name, email, phone, company, position, location, industry, website, linkedin_url</p>
              </Upload.Dragger>
            </Form.Item>
          )}
          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}
              style={{ background: 'linear-gradient(135deg,#06b6d4,#6366f1)', border: 'none', borderRadius: 8, fontWeight: 600 }}>
              Add Source
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Edit Modal (user-defined) ── */}
      <Modal
        title={<div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><EditOutlined style={{ color: '#f59e0b', fontSize: 18 }} /><span>Edit — {editingSource?.name}</span></div>}
        open={editModalVisible}
        onCancel={() => { setEditModalVisible(false); setEditingSource(null); editForm.resetFields(); }}
        footer={null} width={580}
      >
        <Divider style={{ margin: '12px 0 20px' }} />
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <TypeFields type={editType} onTypeChange={setEditType} />
          {editingSource?.api_key && (
            <Form.Item label={<span>New API Key <Text type="secondary" style={{ fontSize: 11 }}>current: {editingSource.api_key}</Text></span>} name="api_key">
              <Input.Password placeholder="Leave blank to keep existing key" />
            </Form.Item>
          )}
          {editType === 'CSV' && (
            <Form.Item label="Replace CSV file">
              <Button icon={<CloudUploadOutlined />} loading={csvUploading}
                onClick={() => {
                  const input = document.createElement('input');
                  input.type = 'file'; input.accept = '.csv';
                  input.onchange = (e) => { const f = e.target.files[0]; if (f) handleCsvUpload(f, editingSource?.id); };
                  input.click();
                }}>
                Upload new CSV
              </Button>
            </Form.Item>
          )}
          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}
              style={{ background: 'linear-gradient(135deg,#f59e0b,#ef4444)', border: 'none', borderRadius: 8, fontWeight: 600 }}>
              Save Changes
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Configure Modal (built-in sources) ── */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <SettingOutlined style={{ color: '#6366f1', fontSize: 18 }} />
            <span>Configure — {editingSource?.name}</span>
          </div>
        }
        open={cfgModalVisible}
        onCancel={() => { setCfgModalVisible(false); setEditingSource(null); cfgForm.resetFields(); }}
        footer={null} width={520}
      >
        <Divider style={{ margin: '12px 0 16px' }} />

        {editingSource?.description && (
          <Alert
            type="info" showIcon
            message={editingSource.description}
            style={{ marginBottom: 16, borderRadius: 8 }}
          />
        )}

        {editingSource?.status === 'inactive' && (
          <Alert
            type="warning" showIcon icon={<LockOutlined />}
            message={`API key not configured — contact your system administrator to activate ${editingSource?.name}`}
            style={{ marginBottom: 16, borderRadius: 8 }}
          />
        )}

        {isWebSource ? (
          <Alert
            type="info" showIcon icon={<InfoCircleOutlined />}
            message="Use the Leads page Collect button"
            description="This source requires search parameters (keywords, location) that are set per-search. Go to the Leads page and use the Collect from Web button to run a targeted collection."
            style={{ borderRadius: 8 }}
          />
        ) : (
          <Form form={cfgForm} layout="vertical" onFinish={handleConfigure}>
            <Form.Item label="Max leads per sync" name="max_leads">
              <InputNumber min={1} max={200} style={{ width: '100%' }} />
            </Form.Item>

            {!isEnrich && (
              <>
                <Form.Item label="Keywords" name="keywords" extra="Search terms (e.g. 'SaaS startup', 'developer Berlin')">
                  <Input placeholder="e.g. SaaS startup founder" />
                </Form.Item>
                <Form.Item label="Locations" name="locations" extra="Comma-separated (e.g. 'New York, London, Berlin')">
                  <Input placeholder="New York, London" />
                </Form.Item>
              </>
            )}

            {editingSource?.config?.system_key === 'apollo' && (
              <>
                <Form.Item label="Job Titles" name="titles" extra="Comma-separated (e.g. 'CEO, Founder, VP Sales')">
                  <Input placeholder="CEO, Founder, CTO" />
                </Form.Item>
                <Form.Item label="Industries" name="industries" extra="Comma-separated">
                  <Input placeholder="SaaS, FinTech, Healthcare" />
                </Form.Item>
              </>
            )}

            <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
              <Button type="primary" htmlType="submit" block size="large" loading={loading}
                style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)', border: 'none', borderRadius: 8, fontWeight: 600 }}>
                Save Parameters
              </Button>
            </Form.Item>
          </Form>
        )}
      </Modal>
    </div>
  );
};

export default DataSources;
