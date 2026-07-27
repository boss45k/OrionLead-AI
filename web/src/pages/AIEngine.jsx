import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Card, Button, Row, Col, Statistic, Table, Space, message, Spin,
  Tag, Progress, Modal, Form, Slider, Input, Select, Alert, Badge,
  Tabs, Typography, List, Empty, Divider, Tooltip, AutoComplete,
} from 'antd';
import {
  PlayCircleOutlined, StopOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined,
  RocketOutlined, RobotOutlined, SendOutlined, ThunderboltOutlined, BulbOutlined, ApiOutlined,
  LineChartOutlined, ToolOutlined, AimOutlined, RollbackOutlined,
  DatabaseOutlined, ArrowUpOutlined, ArrowDownOutlined, EyeOutlined,
  GlobalOutlined, LinkedinOutlined,
} from '@ant-design/icons';
import { apiWithFallback, extractApiError } from '../services/api';
import PipelineVisualizer from '../components/PipelineVisualizer';


const { Text, Paragraph } = Typography;

const DEFAULT_STATS = {
  accuracy: 0,
  throughput: 0,
  avg_response_time: 0,
  total_qualified: 0,
  running: false,
  ai_provider: 'Not connected',
};

const AIEngine = () => {
  const location = useLocation();
  const [activeTab, setActiveTab] = useState(() => new URLSearchParams(location.search).get('tab') || 'chat');
  const [isRunning, setIsRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [aiStats, setAiStats] = useState(null);
  const [logs, setLogs] = useState([]);
  const [settingsModalVisible, setSettingsModalVisible] = useState(false);
  const [runProgress, setRunProgress] = useState(0);
  const [isRunningBatch, setIsRunningBatch] = useState(false);
  const [settingsForm] = Form.useForm();
  const [supportedCountries, setSupportedCountries] = useState([]);

  // AI Chat state
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  // AI Pipeline Summary state
  const [pipelineSummary, setPipelineSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  // AI health state — start as loading so first render shows "Checking…" not "Status unknown"
  const [aiHealth, setAIHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);

  // Batch result
  const [batchResult, setBatchResult] = useState(null);

  // ML Dashboard state
  const [dashboardData, setDashboardData] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);

  // Persisted AI settings
  const [aiSettings, setAiSettings] = useState({ confidence_threshold: 75, batch_size: 100, max_workers: 4 });

  // Retrain & Rollback state
  const [retrainLoading, setRetrainLoading] = useState(false);
  const [retrainResult, setRetrainResult] = useState(null);
  const [modelVersions, setModelVersions] = useState([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [rollbackLoading, setRollbackLoading] = useState(false);

  // Lead Explainer state
  const [explainLeadId, setExplainLeadId] = useState('');
  const [explainResult, setExplainResult] = useState(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainSearch, setExplainSearch] = useState('');
  const [explainOptions, setExplainOptions] = useState([]);
  const [explainSearching, setExplainSearching] = useState(false);

  // Approval queue state
  const [userRole] = useState(() => localStorage.getItem('userRole') || 'user');
  const [pendingLabels, setPendingLabels] = useState([]);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [approveLoadingId, setApproveLoadingId] = useState(null);
  const [rejectModal, setRejectModal] = useState({ visible: false, id: null, note: '' });
  const [leadDetailModal, setLeadDetailModal] = useState({ visible: false, lead: null, loading: false });

  // Interest-Based Collection state
  const [interestCategories, setInterestCategories] = useState([]);
  const [interestForm] = Form.useForm();
  const [isInterestCollecting, setIsInterestCollecting] = useState(false);
  const [interestResult, setInterestResult] = useState(null);
  const [interestProgress, setInterestProgress] = useState(0);
  const [interestProgressText, setInterestProgressText] = useState('');
  const interestPollRef = useRef(null);

  const metrics = aiStats || DEFAULT_STATS;
  const isAdminOrManager = userRole === 'admin' || userRole === 'manager';

  useEffect(() => {
    const loadInitialData = async () => {
      try {
        setLoadingInitial(true);
        const role = localStorage.getItem('userRole') || 'user';
        const tasks = [
          fetchAIStats(), fetchLogs(), fetchSupportedCountries(),
          fetchInterestCategories(),
        ];
        if (role === 'admin' || role === 'manager') {
          tasks.push(fetchAISettings());
        }
        if (role === 'admin' || role === 'manager') {
          tasks.push(fetchPendingLabels());
        }
        await Promise.all(tasks);
      } finally {
        setLoadingInitial(false);
        // Always run health check — runs after page is visible, never blocks render
        fetchAIHealth();
      }
    };
    loadInitialData();
  }, []);

  // Auto-refresh logs every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (!isRunningBatch) fetchLogs();
    }, 5000);
    return () => clearInterval(interval);
  }, [isRunningBatch]);

  // Auto-refresh stats every 15 seconds so the total leads card stays in sync
  // with collections that happen on the Leads page
  useEffect(() => {
    const interval = setInterval(() => {
      if (!isRunningBatch && !isInterestCollecting) fetchAIStats();
    }, 15000);
    return () => clearInterval(interval);
  }, [isRunningBatch, isInterestCollecting]);

  // Clean up interest poll on unmount
  useEffect(() => {
    return () => {
      if (interestPollRef.current) clearInterval(interestPollRef.current);
    };
  }, []);

  const fetchAIStats = async () => {
    try {
      const response = await apiWithFallback('/ai/stats', 'get');
      if (response.data.stats) {
        setAiStats(response.data.stats);
        setIsRunning(response.data.stats.running ?? false);
      }
    } catch {
      // stats remain null – UI shows default zeros
    }
  };

  const fetchLogs = async () => {
    try {
      const response = await apiWithFallback('/ai/logs', 'get');
      if (response.data.logs) setLogs(response.data.logs);
    } catch {
      // logs remain empty
    }
  };

  const handleStartEngine = async () => {
    try {
      setLoading(true);
      await apiWithFallback('/ai/start', 'post', {});
      setIsRunning(true);
      message.success('AI Engine started successfully');
      fetchAIStats();
    } catch (error) {
      message.error('Failed to start AI Engine: ' + (error?.response?.data?.message || error?.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const handleStopEngine = async () => {
    try {
      setLoading(true);
      await apiWithFallback('/ai/stop', 'post', {});
      setIsRunning(false);
      message.success('AI Engine stopped');
      fetchAIStats();
    } catch (error) {
      message.error('Failed to stop AI Engine: ' + (error?.response?.data?.message || error?.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const handleRestartEngine = async () => {
    try {
      setLoading(true);
      await apiWithFallback('/ai/restart', 'post', {});
      message.success('AI Engine restarting...');
      setIsRunning(true);
      fetchAIStats();
    } catch (error) {
      message.error('Failed to restart AI Engine: ' + (error?.response?.data?.message || error?.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const handleQualifyNow = async () => {
    try {
      setIsRunningBatch(true);
      setRunProgress(10);
      setBatchResult(null);

      // Dispatch — returns 202 immediately
      const dispatch = await apiWithFallback(
        '/ai/qualify-batch', 'post',
        { limit: 200 },
        { timeout: 15000 }
      );
      const taskId = dispatch.data?.task_id;
      if (!taskId) throw new Error('No task_id returned from server');
      setRunProgress(20);

      // Poll until done
      let result = null;
      let attempts = 0;
      const maxAttempts = 120; // 120 × 3s = 6 min ceiling
      while (attempts < maxAttempts) {
        await new Promise(r => setTimeout(r, 3000));
        attempts++;
        const poll = await apiWithFallback(`/ai/task-status/${taskId}`, 'get', null, { timeout: 10000 });
        const { status, result: taskResult, error: taskError } = poll.data || {};
        if (status === 'SUCCESS') {
          result = taskResult || {};
          break;
        }
        if (status === 'FAILURE') {
          throw new Error(taskError || 'Batch qualification failed');
        }
        // PENDING / STARTED / RETRY — keep waiting, advance progress bar
        setRunProgress(Math.min(20 + attempts * 0.6, 88));
      }
      if (!result) throw new Error('Batch qualification timed out');

      setBatchResult(result);
      setRunProgress(100);
      message.success(
        `Qualified ${result.processed || 0} leads: ${result.hot || 0} hot, ${result.warm || 0} warm, ${result.cold || 0} cold`
      );
      setTimeout(() => {
        setRunProgress(0);
        fetchAIStats();
        fetchLogs();
        setIsRunningBatch(false);
      }, 1000);
    } catch (error) {
      message.error('Batch qualification error: ' + (error?.response?.data?.message || error?.message || 'Unknown error'));
      setRunProgress(0);
      setIsRunningBatch(false);
    }
  };

  const handleSaveSettings = async (values) => {
    try {
      setLoading(true);
      const res = await apiWithFallback('/ai/settings', 'post', values || {});
      const saved = res?.data?.data || values;
      setAiSettings(prev => ({ ...prev, ...saved }));
      message.success('Settings saved successfully');
      setSettingsModalVisible(false);
      settingsForm.resetFields();
    } catch (error) {
      message.error('Failed to save settings: ' + (error?.response?.data?.message || error?.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const fetchAIHealth = async () => {
    setHealthLoading(true);
    try {
      const response = await apiWithFallback('/ai/health', 'get');
      const data = response.data || {};
      setAIHealth({ ai_status: 'offline', ...data });
    } catch {
      setAIHealth({ ai_status: 'offline', model: null });
    } finally {
      setHealthLoading(false);
    }
  };

  const fetchAISettings = async () => {
    try {
      const res = await apiWithFallback('/ai/settings', 'get');
      const s = res?.data?.settings || {};
      if (s && typeof s === 'object') setAiSettings(prev => ({ ...prev, ...s }));
    } catch {
      // keep defaults on failure
    }
  };

  const handleOpenSettings = async () => {
    await fetchAISettings();
    settingsForm.setFieldsValue({
      confidence_threshold: aiSettings.confidence_threshold,
      batch_size:           aiSettings.batch_size,
      max_workers:          aiSettings.max_workers,
    });
    setSettingsModalVisible(true);
  };

  const handleChatSend = async () => {
    const msg = chatInput.trim();
    if (!msg || chatLoading) return;
    setChatMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setChatInput('');
    setChatLoading(true);
    try {
      const response = await apiWithFallback('/ai/chat', 'post', { message: msg });
      const aiResponse = response.data?.response || 'No response from AI.';
      setChatMessages((prev) => [...prev, { role: 'ai', content: aiResponse, provider: response.data?.ai_provider }]);
    } catch {
      setChatMessages((prev) => [...prev, { role: 'ai', content: 'Error: Could not reach AI service.' }]);
    } finally {
      setChatLoading(false);
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  };

  const handlePipelineSummary = async () => {
    setSummaryLoading(true);
    setPipelineSummary(null);
    try {
      const response = await apiWithFallback('/ai/pipeline-summary', 'get');
      setPipelineSummary(response.data?.summary || null);
    } catch {
      message.error('Failed to generate pipeline summary');
    } finally {
      setSummaryLoading(false);
    }
  };

  const fetchSupportedCountries = async () => {
    try {
      const response = await apiWithFallback('/ai/supported-countries', 'get');
      if (response.data.countries) setSupportedCountries(response.data.countries);
    } catch {
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
        { code: 'KR', name: 'South Korea' },
        { code: 'MX', name: 'Mexico' },
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

  const handleInterestCollect = async (values) => {
    // Clear any existing poll
    if (interestPollRef.current) {
      clearInterval(interestPollRef.current);
      interestPollRef.current = null;
    }

    setIsInterestCollecting(true);
    setInterestResult(null);
    setInterestProgress(0);
    setInterestProgressText('Starting collection...');

    const payload = {
      category:  values.interest_category,
      country:   values.interest_country,
      city:      values.interest_city || undefined,
      max_leads: values.interest_max_leads || 30,
      sources:   values.interest_sources?.length ? values.interest_sources : undefined,
    };

    let taskId = null;
    try {
      const startRes = await apiWithFallback('/ai/collect-by-interest', 'post', payload, { timeout: 20000 });
      taskId = startRes.data?.task_id || startRes.data?.data?.task_id;
    } catch (err) {
      const msg = err?.response?.data?.message || 'Failed to start collection';
      message.error(msg);
      setInterestResult({ status: 'error', message: msg });
      setIsInterestCollecting(false);
      return;
    }

    if (!taskId) {
      message.error('No task ID returned — collection may have failed to start');
      setIsInterestCollecting(false);
      return;
    }

    // Poll every 2 seconds — max 8 minutes
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

        setInterestProgress(pct);
        setInterestProgressText(msg);

        const isDone  = task.status === 'done'  || pct >= 100;
        const isError = task.status === 'error';

        if (isDone || isError || pollCount >= maxPolls) {
          clearInterval(interestPollRef.current);
          interestPollRef.current = null;
          setIsInterestCollecting(false);
          setInterestProgress(100);

          if (isError) {
            const errMsg = task.error || 'Interest collection failed';
            message.error(errMsg);
            setInterestResult({ status: 'error', message: errMsg });
          } else {
            const saved = task.saved || 0;
            if (saved > 0) {
              message.success(`Saved ${saved} leads for ${values.interest_category}`);
            } else {
              message.warning('Collection complete — no leads met quality requirements');
            }
            setInterestResult({
              status:         'success',
              collected:      task.raw_candidates || 0,
              saved,
              rejected:       task.rejected   || 0,
              duplicates:     task.duplicates  || 0,
              quality_report: task.quality_report || null,
            });
            // Refresh stats so total_leads card reflects newly collected leads
            fetchAIStats();
          }
        }
      } catch (pollErr) {
        // Transient network error — keep polling unless max reached
        if (pollCount >= maxPolls) {
          clearInterval(interestPollRef.current);
          interestPollRef.current = null;
          setIsInterestCollecting(false);
          message.error('Collection status check timed out');
          setInterestResult({ status: 'error', message: 'Status check timed out' });
        }
      }
    }, 2000);
  };

  // ── New handlers ─────────────────────────────────────────────────────────

  const fetchDashboard = async () => {
    setDashboardLoading(true);
    try {
      const res = await apiWithFallback('/ai/dashboard', 'get');
      setDashboardData(res.data);
    } catch {
      message.error('Failed to load dashboard data');
    } finally {
      setDashboardLoading(false);
    }
  };

  const fetchModelVersions = async () => {
    setVersionsLoading(true);
    try {
      const res = await apiWithFallback('/ai/model-versions', 'get');
      setModelVersions(res.data.versions || []);
    } catch {
      message.error('Failed to load model versions');
    } finally {
      setVersionsLoading(false);
    }
  };

  const handleRetrain = async () => {
    setRetrainLoading(true);
    setRetrainResult(null);
    try {
      const res = await apiWithFallback('/ai/retrain', 'post', { use_db: true, balance: 'auto' });
      setRetrainResult(res.data);
      message.success('Retraining complete!');
      fetchModelVersions();
    } catch (e) {
      message.error(e?.response?.data?.message || 'Retrain failed');
    } finally {
      setRetrainLoading(false);
    }
  };

  const handleRollback = async (filename) => {
    setRollbackLoading(true);
    try {
      await apiWithFallback('/ai/rollback', 'post', { filename });
      message.success(`Rolled back to: ${filename}`);
      fetchModelVersions();
    } catch {
      message.error('Rollback failed');
    } finally {
      setRollbackLoading(false);
    }
  };

  const fetchPendingLabels = async () => {
    setPendingLoading(true);
    try {
      const res = await apiWithFallback('/ai/feedback/pending', 'get');
      setPendingLabels(res.data?.data || []);
    } catch (e) {
      message.error(extractApiError(e, 'Failed to load pending labels'));
    } finally {
      setPendingLoading(false);
    }
  };

  const handleApproveFeedback = async (id) => {
    setApproveLoadingId(id);
    try {
      await apiWithFallback(`/ai/feedback/${id}/approve`, 'post', {});
      message.success('Label approved — added to ML training set');
      setPendingLabels((prev) => prev.filter((l) => l.id !== id));
    } catch (e) {
      message.error(extractApiError(e, 'Approval failed'));
    } finally {
      setApproveLoadingId(null);
    }
  };

  const handleRejectFeedback = async () => {
    const { id, note } = rejectModal;
    setRejectModal((prev) => ({ ...prev, visible: false }));
    try {
      await apiWithFallback(`/ai/feedback/${id}/reject`, 'post', { note: note || undefined });
      message.success('Label rejected');
      setPendingLabels((prev) => prev.filter((l) => l.id !== id));
    } catch (e) {
      message.error(extractApiError(e, 'Rejection failed'));
    }
  };

  const handleViewLeadDetail = async (leadId) => {
    setLeadDetailModal({ visible: true, lead: null, loading: true });
    try {
      const res = await apiWithFallback(`/leads/${leadId}`, 'get');
      setLeadDetailModal({ visible: true, lead: res?.data?.lead || res?.data || null, loading: false });
    } catch {
      message.error('Could not load lead details');
      setLeadDetailModal({ visible: false, lead: null, loading: false });
    }
  };

  const handleExplainSearch = async (val) => {
    setExplainSearch(val);
    if (!val || val.length < 2) { setExplainOptions([]); return; }
    setExplainSearching(true);
    try {
      const res = await apiWithFallback(`/leads/?search=${encodeURIComponent(val)}&limit=10`, 'get');
      const leads = res.data?.leads || res.data?.data || [];
      setExplainOptions(leads.map((l) => ({
        value: String(l.id),
        label: <span><strong>#{l.id}</strong> — {l.name || '(no name)'}{l.company ? ` @ ${l.company}` : ''}</span>,
      })));
    } catch {
      setExplainOptions([]);
    } finally {
      setExplainSearching(false);
    }
  };

  const handleExplain = async () => {
    if (!explainLeadId) { message.warning('Search and select a lead first'); return; }
    setExplainLoading(true);
    setExplainResult(null);
    try {
      const res = await apiWithFallback(`/ai/explain/${explainLeadId}`, 'get');
      setExplainResult(res.data);
    } catch (e) {
      message.error(e?.response?.data?.message || 'Explanation failed');
    } finally {
      setExplainLoading(false);
    }
  };

  const logColumns = [
    {
      title: 'Time',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 140,
      render: (text) => <span style={{ fontSize: 12 }}>{new Date(text).toLocaleTimeString()}</span>,
    },
    {
      title: 'Event',
      dataIndex: 'event',
      key: 'event',
      render: (text) => <span style={{ fontWeight: 500 }}>{text}</span>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status) => (
        <Tag
          icon={
            status === 'success' ? <CheckCircleOutlined /> :
            status === 'error'   ? <CloseCircleOutlined /> :
                                   <ExclamationCircleOutlined />
          }
          color={status === 'success' ? 'green' : status === 'error' ? 'red' : 'orange'}
        >
          {status?.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Details',
      dataIndex: 'details',
      key: 'details',
      render: (text) => <span style={{ fontSize: 12, color: '#64748b' }}>{text}</span>,
    },
  ];

  const OUTCOME_TAG = {
    converted: { color: 'green',   label: 'Converted' },
    replied:   { color: 'blue',    label: 'Replied'   },
    no_reply:  { color: 'default', label: 'No Reply'  },
    not_a_fit: { color: 'red',     label: 'Not a Fit' },
  };

  const tabItems = [
    // ── Approval Queue tab (admin + manager) ────────────────────────────────
    ...((userRole === 'admin' || userRole === 'manager') ? [{
      key: 'approvals',
      label: (
        <span>
          <CheckCircleOutlined style={{ marginRight: 6 }} />
          Label Approvals
          {pendingLabels.length > 0 && (
            <Badge count={pendingLabels.length} size="small" style={{ marginLeft: 6, backgroundColor: '#f59e0b' }} />
          )}
        </span>
      ),
      children: (
        <div style={{ padding: '12px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <p style={{ color: '#64748b', fontSize: 12, margin: 0 }}>
              User-submitted outcome labels awaiting review. Approved labels enter ML training; rejected labels are excluded.
            </p>
            <Button icon={<ReloadOutlined />} onClick={fetchPendingLabels} loading={pendingLoading} size="small">
              Refresh
            </Button>
          </div>

          {pendingLabels.length === 0 && !pendingLoading && (
            <Empty
              description={<span style={{ color: '#666' }}>No pending labels — all caught up!</span>}
            />
          )}

          {(pendingLabels.length > 0 || pendingLoading) && (
            <Table
              size="small"
              loading={pendingLoading}
              dataSource={pendingLabels.map((l) => ({ ...l, key: l.id }))}
              pagination={{ pageSize: 10, showSizeChanger: false }}
              columns={[
                {
                  title: 'Lead',
                  key: 'lead',
                  render: (_, r) => (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Tooltip title="View lead details">
                          <Button
                            type="text"
                            size="small"
                            icon={<EyeOutlined style={{ fontSize: 15, color: '#6366f1' }} />}
                            onClick={() => handleViewLeadDetail(r.lead_id)}
                            style={{ padding: '2px 4px', flexShrink: 0 }}
                          />
                        </Tooltip>
                        <div>
                          <div style={{ color: 'var(--text-stat)', fontWeight: 500, fontSize: 13 }}>{r.lead_name || '—'}</div>
                          <div style={{ color: '#64748b', fontSize: 11 }}>{r.lead_company || ''}</div>
                        </div>
                      </div>
                      <Button
                        type="primary"
                        icon={<CheckCircleOutlined />}
                        loading={approveLoadingId === r.id}
                        disabled={approveLoadingId !== null && approveLoadingId !== r.id}
                        onClick={() => handleApproveFeedback(r.id)}
                        style={{
                          background: 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)',
                          borderColor: '#14532d',
                          boxShadow: '0 2px 8px rgba(22,163,74,0.4), inset 0 1px 0 rgba(255,255,255,0.12)',
                          fontWeight: 700,
                          fontSize: 12,
                          letterSpacing: '0.04em',
                          height: 34,
                          borderRadius: 8,
                          flexShrink: 0,
                        }}
                      >
                        Approve
                      </Button>
                    </div>
                  ),
                },
                {
                  title: 'Outcome',
                  dataIndex: 'outcome',
                  key: 'outcome',
                  width: 120,
                  render: (v) => {
                    const cfg = OUTCOME_TAG[v] || { color: 'default', label: v };
                    return <Tag color={cfg.color}>{cfg.label}</Tag>;
                  },
                },
                {
                  title: 'Submitted By',
                  dataIndex: 'submitted_by_name',
                  key: 'submitted_by_name',
                  width: 130,
                  render: (v) => <span style={{ color: '#94a3b8', fontSize: 12 }}>{v || '—'}</span>,
                },
                {
                  title: 'When',
                  dataIndex: 'recorded_at',
                  key: 'recorded_at',
                  width: 140,
                  render: (v) => (
                    <span style={{ color: '#64748b', fontSize: 11 }}>
                      {v ? new Date(v).toLocaleString() : '—'}
                    </span>
                  ),
                },
                {
                  title: '',
                  key: 'actions',
                  width: 80,
                  render: (_, r) => (
                    <Button
                      size="small"
                      danger
                      type="text"
                      icon={<CloseCircleOutlined />}
                      onClick={() => setRejectModal({ visible: true, id: r.id, note: '' })}
                      style={{ fontSize: 11 }}
                    >
                      Reject
                    </Button>
                  ),
                },
              ]}
              style={{ color: 'var(--text-stat)' }}
            />
          )}
        </div>
      ),
    }] : []),
    {
      key: 'chat',
      label: <span><RobotOutlined style={{ marginRight: 6 }} />AI Assistant</span>,
      children: (
        <div>
          <div style={{ maxHeight: 400, overflowY: 'auto', padding: '12px 0', minHeight: 200 }}>
            {chatMessages.length === 0 && (
              <Empty
                image={<RobotOutlined style={{ fontSize: 48, color: '#333' }} />}
                description={<span style={{ color: '#666' }}>Ask the AI anything about your leads, pipeline, or sales strategy.</span>}
                style={{ padding: '40px 0' }}
              />
            )}
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  marginBottom: 12,
                }}
              >
                <div
                  style={{
                    maxWidth: '75%',
                    padding: '10px 14px',
                    borderRadius: 12,
                    background: msg.role === 'user' ? '#6366f1' : 'var(--bg-elevated)',
                    color: msg.role === 'user' ? '#ffffff' : 'var(--text-body)',
                    fontSize: 13,
                    lineHeight: 1.5,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {msg.role === 'ai' && (
                    <div style={{ fontSize: 10, color: '#06b6d4', marginBottom: 4, fontWeight: 600 }}>
                      <RobotOutlined /> {msg.provider || 'AI'}
                    </div>
                  )}
                  {msg.content}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 12 }}>
                <div style={{ padding: '10px 14px', borderRadius: 12, background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                  <Spin size="small" /> Thinking...
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <Input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onPressEnter={handleChatSend}
              placeholder="Ask about your leads... e.g. 'Which leads should I focus on this week?'"
              style={{ background: 'var(--bg-elevated)', borderColor: 'rgba(99,102,241,0.15)', color: 'var(--text-stat)' }}
              disabled={chatLoading}
            />
            <Button type="primary" icon={<SendOutlined />} onClick={handleChatSend} loading={chatLoading}>
              Send
            </Button>
          </div>
          <div style={{ marginTop: 8 }}>
            <Space wrap size={[4, 4]}>
              {['Which leads are highest priority?', 'Summarize my pipeline health', 'What industries have the best leads?', 'Suggest next steps for hot leads'].map((q) => (
                <Tag
                  key={q}
                  style={{ cursor: 'pointer', background: 'var(--bg-elevated)', borderColor: 'rgba(99,102,241,0.15)', color: '#64748b' }}
                  onClick={() => setChatInput(q)}
                >
                  {q}
                </Tag>
              ))}
            </Space>
          </div>
        </div>
      ),
    },
    {
      key: 'summary',
      label: <span><BulbOutlined style={{ marginRight: 6 }} />Pipeline Insights</span>,
      children: (
        <div style={{ padding: '12px 0' }}>
          <Button
            type="primary"
            icon={<BulbOutlined />}
            onClick={handlePipelineSummary}
            loading={summaryLoading}
            style={{ marginBottom: 16 }}
          >
            {summaryLoading ? 'AI is analyzing...' : 'Generate AI Pipeline Summary'}
          </Button>
          {pipelineSummary && (
            <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: 20 }}>
              <div style={{ marginBottom: 16 }}>
                <Tag
                  color={
                    pipelineSummary.pipeline_health === 'Excellent' ? 'green' :
                    pipelineSummary.pipeline_health === 'Good'      ? 'blue'  :
                    pipelineSummary.pipeline_health === 'Fair'      ? 'orange': 'red'
                  }
                  style={{ fontSize: 14, padding: '4px 12px' }}
                >
                  Pipeline Health: {pipelineSummary.pipeline_health}
                </Tag>
              </div>
              <Paragraph style={{ color: 'var(--text-stat)', fontSize: 14, lineHeight: 1.6 }}>
                {pipelineSummary.executive_summary}
              </Paragraph>
              <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
                <Col xs={24} md={8}>
                  <h4 style={{ color: '#06b6d4', margin: '0 0 8px 0' }}>Key Insights</h4>
                  <List
                    size="small"
                    dataSource={pipelineSummary.key_insights || []}
                    renderItem={(item) => (
                      <List.Item style={{ color: 'var(--text-body)', borderColor: 'var(--border-subtle)', padding: '6px 0' }}>
                        {item}
                      </List.Item>
                    )}
                  />
                </Col>
                <Col xs={24} md={8}>
                  <h4 style={{ color: '#22c55e', margin: '0 0 8px 0' }}>Recommendations</h4>
                  <List
                    size="small"
                    dataSource={pipelineSummary.recommendations || []}
                    renderItem={(item) => (
                      <List.Item style={{ color: 'var(--text-body)', borderColor: 'var(--border-subtle)', padding: '6px 0' }}>
                        {item}
                      </List.Item>
                    )}
                  />
                </Col>
                <Col xs={24} md={8}>
                  <h4 style={{ color: '#f59e0b', margin: '0 0 8px 0' }}>Immediate Actions</h4>
                  <List
                    size="small"
                    dataSource={pipelineSummary.immediate_actions || []}
                    renderItem={(item) => (
                      <List.Item style={{ color: 'var(--text-body)', borderColor: 'var(--border-subtle)', padding: '6px 0' }}>
                        {item}
                      </List.Item>
                    )}
                  />
                  {pipelineSummary.focus_countries?.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <Text style={{ color: '#64748b', fontSize: 11 }}>Focus Countries: </Text>
                      {pipelineSummary.focus_countries.map((c) => (
                        <Tag key={c} color="cyan" style={{ marginTop: 4 }}>{c}</Tag>
                      ))}
                    </div>
                  )}
                </Col>
              </Row>
            </div>
          )}
          {!pipelineSummary && !summaryLoading && (
            <Empty description={<span style={{ color: '#666' }}>Click the button above to generate an AI-powered analysis of your lead pipeline</span>} />
          )}
        </div>
      ),
    },
    // ── ML Dashboard tab (manager + admin only) ───────────────────────────────
    ...((userRole === 'manager' || userRole === 'admin') ? [{
      key: 'dashboard',
      label: <span><LineChartOutlined style={{ marginRight: 6 }} />ML Dashboard</span>,
      children: (
        <div style={{ padding: '12px 0' }}>
          <Button
            type="primary" icon={<LineChartOutlined />}
            onClick={fetchDashboard} loading={dashboardLoading}
            style={{ marginBottom: 16 }}
          >
            Load Dashboard
          </Button>

          {dashboardData && (
            <>
              {/* Current model metrics */}
              <div style={{ marginBottom: 20 }}>
                <h4 style={{ color: '#06b6d4', margin: '0 0 12px 0' }}>Current Model</h4>
                <Row gutter={[12, 12]}>
                  {[
                    { label: 'AUC',       val: dashboardData.current_model?.auc,       color: '#22c55e' },
                    { label: 'Accuracy',  val: dashboardData.current_model?.accuracy,  color: '#06b6d4' },
                    { label: 'Precision', val: dashboardData.current_model?.precision, color: '#f59e0b' },
                    { label: 'Recall',    val: dashboardData.current_model?.recall,    color: '#a78bfa' },
                    { label: 'F1',        val: dashboardData.current_model?.f1,        color: '#fb923c' },
                  ].map(({ label, val, color }) => (
                    <Col xs={12} sm={4} key={label}>
                      <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                        <div style={{ color: '#64748b', fontSize: 11, marginBottom: 4 }}>{label}</div>
                        <div style={{ color, fontSize: 20, fontWeight: 700 }}>
                          {val != null ? (val * 100).toFixed(1) + '%' : '—'}
                        </div>
                      </div>
                    </Col>
                  ))}
                  <Col xs={12} sm={4}>
                    <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                      <div style={{ color: '#64748b', fontSize: 11, marginBottom: 4 }}>Samples</div>
                      <div style={{ color: 'var(--text-stat)', fontSize: 20, fontWeight: 700 }}>
                        {dashboardData.current_model?.n_samples?.toLocaleString() ?? '—'}
                      </div>
                    </div>
                  </Col>
                </Row>
                {dashboardData.current_model?.trained_at && (
                  <div style={{ color: '#64748b', fontSize: 11, marginTop: 8 }}>
                    Trained: {new Date(dashboardData.current_model.trained_at).toLocaleString()} &nbsp;|&nbsp;
                    Version: {dashboardData.current_model.model_version || '—'}
                  </div>
                )}
              </div>

              {/* Conversion by tier */}
              <div style={{ marginBottom: 20 }}>
                <h4 style={{ color: '#06b6d4', margin: '0 0 12px 0' }}>Conversion Rate by Tier</h4>
                <Row gutter={[12, 12]}>
                  {['hot', 'warm', 'cold'].map((tier) => {
                    const d = dashboardData.conversion_by_tier?.[tier] || {};
                    const pct = d.conversion_rate != null ? (d.conversion_rate * 100).toFixed(1) + '%' : '—';
                    const tierColor = tier === 'hot' ? '#ef4444' : tier === 'warm' ? '#f59e0b' : '#64748b';
                    return (
                      <Col xs={24} sm={8} key={tier}>
                        <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: '14px 18px' }}>
                          <Tag color={tier === 'hot' ? 'red' : tier === 'warm' ? 'orange' : 'default'} style={{ marginBottom: 8, textTransform: 'uppercase' }}>{tier}</Tag>
                          <div style={{ color: tierColor, fontSize: 24, fontWeight: 700 }}>{pct}</div>
                          <div style={{ color: '#64748b', fontSize: 11 }}>{d.converted ?? 0} / {d.total ?? 0} converted</div>
                        </div>
                      </Col>
                    );
                  })}
                </Row>
              </div>

              {/* ML vs LLM agreement + dataset health */}
              <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
                <Col xs={24} sm={12}>
                  <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: '14px 18px' }}>
                    <h4 style={{ color: '#06b6d4', margin: '0 0 10px 0', fontSize: 13 }}>ML vs LLM Agreement</h4>
                    <div style={{ color: '#22c55e', fontSize: 28, fontWeight: 700 }}>
                      {dashboardData.ml_llm_agreement?.agreement_rate != null
                        ? (dashboardData.ml_llm_agreement.agreement_rate * 100).toFixed(1) + '%'
                        : '—'}
                    </div>
                    <div style={{ color: '#64748b', fontSize: 11 }}>
                      {dashboardData.ml_llm_agreement?.agreements ?? 0} / {dashboardData.ml_llm_agreement?.total_comparisons ?? 0} comparisons
                    </div>
                  </div>
                </Col>
                <Col xs={24} sm={12}>
                  <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: '14px 18px' }}>
                    <h4 style={{ color: '#06b6d4', margin: '0 0 10px 0', fontSize: 13 }}>Dataset Health</h4>
                    <div style={{ color: '#64748b', fontSize: 12 }}>
                      <div>DB labeled: <b style={{ color: 'var(--text-stat)' }}>{dashboardData.dataset_health?.db?.total_labeled ?? '—'}</b></div>
                      <div>JSONL labeled: <b style={{ color: 'var(--text-stat)' }}>{dashboardData.dataset_health?.jsonl?.labeled ?? '—'}</b></div>
                      <div>Positive rate: <b style={{ color: '#22c55e' }}>
                        {dashboardData.dataset_health?.db?.positive_rate != null
                          ? (dashboardData.dataset_health.db.positive_rate * 100).toFixed(1) + '%'
                          : '—'}
                      </b></div>
                    </div>
                  </div>
                </Col>
              </Row>

              {/* Metrics history */}
              {dashboardData.model_metrics_history?.length > 0 && (
                <div>
                  <h4 style={{ color: '#06b6d4', margin: '0 0 12px 0' }}>
                    Training History (last {dashboardData.model_metrics_history.length} runs)
                  </h4>
                  <Table
                    size="small"
                    dataSource={[...dashboardData.model_metrics_history].reverse().map((r, i) => ({ ...r, key: i }))}
                    pagination={{ pageSize: 5 }}
                    columns={[
                      { title: 'Date', dataIndex: 'ts', key: 'ts', width: 160,
                        render: (v) => v ? new Date(v).toLocaleString() : '—' },
                      { title: 'AUC',  dataIndex: 'auc',      key: 'auc',      width: 80,
                        render: (v) => v != null ? <Tag color="green">{(v*100).toFixed(1)}%</Tag> : '—' },
                      { title: 'Acc',  dataIndex: 'accuracy', key: 'accuracy', width: 80,
                        render: (v) => v != null ? (v*100).toFixed(1)+'%' : '—' },
                      { title: 'P',    dataIndex: 'precision',key: 'precision',width: 70,
                        render: (v) => v != null ? (v*100).toFixed(1)+'%' : '—' },
                      { title: 'R',    dataIndex: 'recall',   key: 'recall',   width: 70,
                        render: (v) => v != null ? (v*100).toFixed(1)+'%' : '—' },
                      { title: 'F1',   dataIndex: 'f1',       key: 'f1',       width: 70,
                        render: (v) => v != null ? (v*100).toFixed(1)+'%' : '—' },
                      { title: 'N',    dataIndex: 'n_samples',key: 'n_samples',width: 80,
                        render: (v) => v?.toLocaleString() ?? '—' },
                    ]}
                    style={{ color: 'var(--text-stat)' }}
                  />
                </div>
              )}
            </>
          )}
          {!dashboardData && !dashboardLoading && (
            <Empty description={<span style={{ color: '#666' }}>Click Load Dashboard to see ML performance metrics</span>} />
          )}
        </div>
      ),
    }] : []),
    // ── Retrain & Rollback tab (admin only) ───────────────────────────────────
    ...(userRole === 'admin' ? [{
      key: 'retrain',
      label: <span><ToolOutlined style={{ marginRight: 6 }} />Retrain / Rollback</span>,
      children: (
        <div style={{ padding: '12px 0' }}>
          <Row gutter={[16, 16]}>
            {/* Retrain panel */}
            <Col xs={24} md={12}>
              <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: 20 }}>
                <h4 style={{ color: '#06b6d4', margin: '0 0 12px 0' }}>Retrain ML Model</h4>
                <p style={{ color: '#64748b', fontSize: 12, marginBottom: 16 }}>
                  Trains a new XGBoost model on all labeled leads (DB + JSONL). Old vs new AUC compared — new model only replaces current if it improves.
                </p>
                <Button
                  type="primary" icon={<DatabaseOutlined />}
                  onClick={handleRetrain} loading={retrainLoading}
                  style={{ width: '100%', marginBottom: 12 }}
                >
                  {retrainLoading ? 'Training...' : 'Retrain Now'}
                </Button>

                {retrainResult && (
                  <div style={{ marginTop: 12 }}>
                    <Alert
                      type={retrainResult.retrained ? 'success' : 'warning'}
                      message={retrainResult.retrained ? 'Model updated' : 'Training ran but model not replaced'}
                      description={
                        <div style={{ fontSize: 12, marginTop: 4 }}>
                          {retrainResult.new_model && <>
                            <div>New AUC: <b style={{ color: '#22c55e' }}>{retrainResult.new_model.auc != null ? (retrainResult.new_model.auc*100).toFixed(2)+'%' : '—'}</b></div>
                            <div>Old AUC: <b style={{ color: '#64748b' }}>{retrainResult.old_model?.auc != null ? (retrainResult.old_model.auc*100).toFixed(2)+'%' : '—'}</b></div>
                            {retrainResult.improvement?.auc_delta != null && (
                              <div>
                                Delta:{' '}
                                <b style={{ color: retrainResult.improvement.auc_delta >= 0 ? '#22c55e' : '#ef4444' }}>
                                  {retrainResult.improvement.auc_delta >= 0
                                    ? <ArrowUpOutlined />
                                    : <ArrowDownOutlined />}
                                  {' '}{(retrainResult.improvement.auc_delta*100).toFixed(2)}%
                                </b>
                              </div>
                            )}
                            <div>New F1: {retrainResult.new_model.f1 != null ? (retrainResult.new_model.f1*100).toFixed(1)+'%' : '—'}</div>
                            <div>Samples: {retrainResult.leads_used}</div>
                          </>}
                        </div>
                      }
                      showIcon
                    />
                  </div>
                )}
              </div>
            </Col>

            {/* Rollback panel */}
            <Col xs={24} md={12}>
              <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: 20 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h4 style={{ color: '#06b6d4', margin: 0 }}>Model Versions</h4>
                  <Button size="small" icon={<ReloadOutlined />} onClick={fetchModelVersions} loading={versionsLoading}>
                    Refresh
                  </Button>
                </div>
                {modelVersions.length === 0 && !versionsLoading && (
                  <Empty description={<span style={{ color: '#666', fontSize: 12 }}>No archived versions yet. Train the model to create archives.</span>} />
                )}
                {modelVersions.map((v) => (
                  <div
                    key={v.filename}
                    style={{ background: 'rgba(15,23,42,0.5)', borderRadius: 6, padding: '10px 14px', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  >
                    <div>
                      <div style={{ color: 'var(--text-stat)', fontSize: 12, fontWeight: 500 }}>
                        {v.trained_at ? new Date(v.trained_at).toLocaleString() : v.filename}
                      </div>
                      <Space size={4} style={{ marginTop: 4 }}>
                        {v.auc   != null && <Tag color="green"  style={{ fontSize: 10 }}>AUC {(v.auc*100).toFixed(1)}%</Tag>}
                        {v.f1    != null && <Tag color="blue"   style={{ fontSize: 10 }}>F1 {(v.f1*100).toFixed(1)}%</Tag>}
                        {v.n_samples != null && <Tag style={{ fontSize: 10 }}>n={v.n_samples}</Tag>}
                      </Space>
                    </div>
                    <Button
                      size="small" icon={<RollbackOutlined />}
                      onClick={() => handleRollback(v.filename)}
                      loading={rollbackLoading}
                    >
                      Restore
                    </Button>
                  </div>
                ))}
              </div>
            </Col>
          </Row>
        </div>
      ),
    }] : []),
    // ── Lead Explainer tab ───────────────────────────────────────────────────
    {
      key: 'explain',
      label: <span><AimOutlined style={{ marginRight: 6 }} />Lead Explainer</span>,
      children: (
        <div style={{ padding: '12px 0' }}>
          <p style={{ color: '#64748b', fontSize: 12, marginBottom: 12 }}>
            Enter a Lead ID to get a SHAP-powered explanation of why the ML model scored that lead, plus an AI-written plain-English summary.
          </p>
          <Space style={{ marginBottom: 20 }}>
            <AutoComplete
              options={explainOptions}
              onSearch={handleExplainSearch}
              onSelect={(val) => { setExplainLeadId(val); setExplainSearch(val); }}
              value={explainSearch}
              onChange={setExplainSearch}
              notFoundContent={explainSearching ? <Spin size="small" /> : 'No leads found'}
              style={{ width: 280 }}
            >
              <Input
                placeholder="Search lead by name or company…"
                style={{ background: 'var(--bg-elevated)', borderColor: 'rgba(99,102,241,0.2)', color: 'var(--text-stat)' }}
              />
            </AutoComplete>
            <Button type="primary" icon={<AimOutlined />} onClick={handleExplain} loading={explainLoading} disabled={!explainLeadId}>
              Explain
            </Button>
          </Space>

          {explainResult && (
            <>
              {/* Header */}
              <div style={{ marginBottom: 16 }}>
                <Tag color="blue" style={{ fontSize: 13, padding: '4px 12px' }}>
                  {explainResult.name} @ {explainResult.company}
                </Tag>
                {explainResult.ml_score != null && (
                  <Tag
                    color={explainResult.ml_score >= 80 ? 'red' : explainResult.ml_score >= 60 ? 'orange' : 'default'}
                    style={{ fontSize: 13, padding: '4px 12px' }}
                  >
                    ML Score: {explainResult.ml_score}/100
                  </Tag>
                )}
              </div>

              {/* LLM explanation */}
              {explainResult.llm_explanation && (
                <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: 16, marginBottom: 16 }}>
                  <div style={{ color: '#06b6d4', fontSize: 11, fontWeight: 600, marginBottom: 6 }}>
                    <RobotOutlined /> AI EXPLANATION
                  </div>
                  <p style={{ color: 'var(--text-stat)', fontSize: 13, lineHeight: 1.6, margin: 0 }}>
                    {explainResult.llm_explanation}
                  </p>
                </div>
              )}

              {/* SHAP factors */}
              {explainResult.shap_factors?.length > 0 && (
                <div>
                  <h4 style={{ color: '#06b6d4', margin: '0 0 12px 0', fontSize: 13 }}>Top Scoring Factors (SHAP)</h4>
                  {explainResult.shap_factors.map((f, i) => (
                    <div
                      key={i}
                      style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: '12px 16px', marginBottom: 8, borderLeft: `3px solid ${f.direction === 'positive' ? '#22c55e' : '#ef4444'}` }}
                    >
                      <Row align="middle" justify="space-between">
                        <Col>
                          <Space>
                            {f.direction === 'positive'
                              ? <ArrowUpOutlined style={{ color: '#22c55e' }} />
                              : <ArrowDownOutlined style={{ color: '#ef4444' }} />}
                            <span style={{ color: 'var(--text-stat)', fontWeight: 500, fontSize: 13 }}>
                              {f.feature.replace(/_/g, ' ')}
                            </span>
                          </Space>
                          <div style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>{f.description}</div>
                        </Col>
                        <Col>
                          <Tag color={f.direction === 'positive' ? 'green' : 'red'} style={{ fontWeight: 600 }}>
                            {f.impact > 0 ? '+' : ''}{f.impact.toFixed(3)}
                          </Tag>
                        </Col>
                      </Row>
                    </div>
                  ))}
                </div>
              )}

              {/* No SHAP available */}
              {(!explainResult.shap_factors || explainResult.shap_factors.length === 0) && (
                <Alert
                  type="info"
                  message="SHAP not available"
                  description="Run model retraining to enable detailed SHAP feature explanations."
                  showIcon
                />
              )}
            </>
          )}

          {!explainResult && !explainLoading && (
            <Empty description={<span style={{ color: '#666' }}>Enter a Lead ID above to get an AI-powered explanation</span>} />
          )}
        </div>
      ),
    },

    // ── Interest-Based Collection tab ─────────────────────────────────────────
    {
      key: 'interest',
      label: <span><AimOutlined style={{ marginRight: 6 }} />Interest-Based Collection</span>,
      children: (
        <div style={{ padding: '16px 0' }}>
          <p style={{ color: '#64748b', fontSize: 12, margin: '0 0 20px 0' }}>
            Collect leads who show buying intent for a specific product or service category.
            Queries are auto-generated from category keywords and filtered by quality score.
          </p>

          <Form
            form={interestForm}
            layout="vertical"
            onFinish={handleInterestCollect}
            initialValues={{ interest_max_leads: 30, interest_sources: ['web', 'directories', 'news'] }}
          >
            <Row gutter={[16, 0]}>
              {/* Category */}
              <Col xs={24} md={8}>
                <Form.Item
                  label={<span style={{ color: '#94a3b8' }}>Product / Service Category</span>}
                  name="interest_category"
                  rules={[{ required: true, message: 'Select a category' }]}
                >
                  <Select
                    showSearch
                    placeholder="e.g. Laptops, Real Estate, Software"
                    filterOption={(input, opt) =>
                      opt.label.toLowerCase().includes(input.toLowerCase())
                    }
                    options={interestCategories.map((c) => ({ label: c.name, value: c.slug }))}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              </Col>

              {/* Country */}
              <Col xs={24} md={5}>
                <Form.Item
                  label={<span style={{ color: '#94a3b8' }}>Country</span>}
                  name="interest_country"
                  rules={[{ required: true, message: 'Enter a country' }]}
                >
                  <Select
                    showSearch
                    placeholder="e.g. Lebanon"
                    filterOption={(input, opt) =>
                      opt.label.toLowerCase().includes(input.toLowerCase())
                    }
                    options={supportedCountries.map((c) => ({ label: c.name, value: c.name }))}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              </Col>

              {/* City */}
              <Col xs={24} md={4}>
                <Form.Item
                  label={<span style={{ color: '#94a3b8' }}>City (optional)</span>}
                  name="interest_city"
                >
                  <Input
                    placeholder="e.g. Beirut"
                    style={{ background: 'rgba(99,102,241,0.06)', borderColor: 'rgba(99,102,241,0.15)', color: 'var(--text-stat)' }}
                  />
                </Form.Item>
              </Col>

              {/* Max leads */}
              <Col xs={24} md={4}>
                <Form.Item
                  label={<span style={{ color: '#94a3b8' }}>Max Leads</span>}
                  name="interest_max_leads"
                >
                  <Select options={[
                    { label: '10',  value: 10  },
                    { label: '20',  value: 20  },
                    { label: '30',  value: 30  },
                    { label: '50',  value: 50  },
                    { label: '100', value: 100 },
                  ]} style={{ width: '100%' }} />
                </Form.Item>
              </Col>

              {/* Sources */}
              <Col xs={24} md={3} style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 24 }}>
                <Form.Item style={{ width: '100%', marginBottom: 0 }}>
                  <Button
                    type="primary"
                    htmlType="submit"
                    icon={<AimOutlined />}
                    loading={isInterestCollecting}
                    size="large"
                    style={{ width: '100%', background: '#7c3aed', borderColor: '#7c3aed' }}
                  >
                    {isInterestCollecting ? 'Collecting...' : 'Collect'}
                  </Button>
                </Form.Item>
              </Col>
            </Row>

            {/* Source selector */}
            <Form.Item
              label={<span style={{ color: '#94a3b8' }}>Data Sources</span>}
              name="interest_sources"
            >
              <Select
                mode="multiple"
                placeholder="Select sources (default: web + directories + news)"
                options={[
                  { label: 'Web',          value: 'web'         },
                  { label: 'Directories',  value: 'directories' },
                  { label: 'News',         value: 'news'        },
                  { label: 'Social Media', value: 'social'      },
                  { label: 'GitHub',       value: 'github'      },
                ]}
                style={{ maxWidth: 600 }}
              />
            </Form.Item>
          </Form>

          {/* Progress */}
          {isInterestCollecting && (
            <div style={{ marginTop: 16, padding: '14px 18px', background: 'var(--bg-elevated)', borderRadius: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
                <Spin size="small" style={{ marginRight: 10 }} />
                <span style={{ color: '#94a3b8', fontSize: 13 }}>
                  {interestProgressText || 'Collecting...'}
                </span>
              </div>
              <Progress
                percent={interestProgress}
                strokeColor={{ '0%': '#7c3aed', '100%': '#06b6d4' }}
                trailColor="rgba(99,102,241,0.12)"
                showInfo={false}
                size="small"
              />
            </div>
          )}

          {interestResult && !isInterestCollecting && (
            <div style={{ marginTop: 20 }}>
              {/* Summary bar */}
              <Alert
                type={
                  interestResult.status === 'error' ? 'error'
                  : interestResult.saved > 0 ? 'success'
                  : 'warning'
                }
                showIcon
                closable
                onClose={() => setInterestResult(null)}
                message={
                  interestResult.status === 'error'
                    ? `Collection failed: ${interestResult.message}`
                    : `Collected ${interestResult.collected ?? 0} candidates — saved ${interestResult.saved ?? 0}, rejected ${interestResult.rejected ?? 0}`
                }
                style={{ marginBottom: 16 }}
              />

              {/* Quality report */}
              {interestResult.quality_report && (
                <div style={{ background: 'var(--bg-elevated)', borderRadius: 8, padding: 16 }}>
                  <h4 style={{ color: '#06b6d4', margin: '0 0 12px 0', fontSize: 13 }}>Quality Report</h4>
                  <Row gutter={[12, 12]}>
                    {[
                      { label: 'Queries Run',    val: interestResult.quality_report.queries_run,           color: '#94a3b8' },
                      { label: 'Candidates',     val: interestResult.quality_report.raw_candidates,        color: '#94a3b8' },
                      { label: 'Saved',          val: interestResult.quality_report.saved,                 color: '#22c55e' },
                      { label: 'Rejected',       val: interestResult.quality_report.rejected,              color: '#ef4444' },
                      { label: 'Duplicates',     val: interestResult.quality_report.duplicates,            color: '#f59e0b' },
                      { label: 'Avg Score',      val: interestResult.quality_report.average_quality_score, color: '#06b6d4' },
                    ].map(({ label, val, color }) => (
                      <Col xs={12} sm={4} key={label}>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ color: '#64748b', fontSize: 11 }}>{label}</div>
                          <div style={{ color, fontSize: 20, fontWeight: 700 }}>{val ?? '—'}</div>
                        </div>
                      </Col>
                    ))}
                  </Row>

                  {/* Intent breakdown */}
                  {interestResult.quality_report.intent_breakdown && (
                    <div style={{ marginTop: 16 }}>
                      <div style={{ color: '#64748b', fontSize: 11, marginBottom: 8 }}>Buying Intent Breakdown</div>
                      <Space wrap>
                        {Object.entries(interestResult.quality_report.intent_breakdown).map(([level, count]) => (
                          <Tag
                            key={level}
                            color={level === 'high' ? 'red' : level === 'medium' ? 'orange' : level === 'low' ? 'blue' : 'default'}
                            style={{ fontSize: 12, padding: '2px 10px' }}
                          >
                            {level}: {count}
                          </Tag>
                        ))}
                      </Space>
                    </div>
                  )}

                  {/* Rejection reasons */}
                  {interestResult.quality_report.rejection_reasons &&
                    Object.keys(interestResult.quality_report.rejection_reasons).length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ color: '#64748b', fontSize: 11, marginBottom: 6 }}>Rejection Reasons</div>
                      <Space wrap>
                        {Object.entries(interestResult.quality_report.rejection_reasons).map(([reason, count]) => (
                          <Tag key={reason} color="volcano" style={{ fontSize: 11 }}>
                            {reason}: {count}
                          </Tag>
                        ))}
                      </Space>
                    </div>
                  )}

                  <div style={{ marginTop: 12, color: '#475569', fontSize: 11 }}>
                    Duration: {interestResult.quality_report.duration_seconds}s
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ),
    },
  ];

  if (loadingInitial) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 500 }}>
        <Spin size="large" tip="Loading AI Engine..." />
      </div>
    );
  }

  const _hs = healthLoading ? 'checking' : (aiHealth?.ai_status ?? 'unknown');
  const healthColor  = _hs === 'healthy'      ? '#22c55e'
                     : _hs === 'no_key'       ? '#f59e0b'
                     : _hs === 'rate_limited' ? '#f59e0b'
                     : _hs === 'quota_exceeded'? '#f59e0b'
                     : _hs === 'unauthorized' ? '#f59e0b'
                     : (_hs === 'checking' || _hs === 'unknown') ? '#94a3b8'
                     : '#ff6b6b';
  const healthBg     = _hs === 'healthy'      ? 'linear-gradient(135deg, #0a2e14 0%, #0f3d1a 100%)'
                     : (_hs === 'no_key' || _hs === 'rate_limited' || _hs === 'quota_exceeded' || _hs === 'unauthorized')
                       ? 'linear-gradient(135deg, #2e2a0a 0%, #3d350f 100%)'
                     : (_hs === 'checking' || _hs === 'unknown') ? 'linear-gradient(135deg, #1a1f2e 0%, #1e2438 100%)'
                     : 'linear-gradient(135deg, #3d1a0f 0%, #2e140a 100%)';
  const healthBorder = _hs === 'healthy'      ? '#1b5e20'
                     : (_hs === 'no_key' || _hs === 'rate_limited' || _hs === 'quota_exceeded' || _hs === 'unauthorized')
                       ? '#5d4a0f'
                     : (_hs === 'checking' || _hs === 'unknown') ? '#2d3748'
                     : '#5d1a0f';

  return (
    <div style={{ padding: 20 }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, margin: '0 0 6px 0', color: 'var(--text-stat)' }}>
          AI Engine
        </h1>
        <p style={{ color: '#64748b', fontSize: 13, margin: 0 }}>
          {isAdminOrManager
            ? 'Real-time lead qualification with live metrics and control'
            : 'Chat with AI, collect leads by interest, and explain lead scores'}
        </p>
      </div>

      {/* Quick-start banner for regular users */}
      {!isAdminOrManager && (
        <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
          {[
            { icon: <RobotOutlined style={{ fontSize: 22, color: '#6366f1' }} />, title: 'AI Assistant', desc: 'Ask anything about your leads or get sales advice', tab: 'chat' },
            { icon: <AimOutlined   style={{ fontSize: 22, color: '#7c3aed' }} />, title: 'Collect by Interest', desc: 'Find leads who want to buy a specific product', tab: 'interest' },
            { icon: <BulbOutlined  style={{ fontSize: 22, color: '#06b6d4' }} />, title: 'Pipeline Insights', desc: 'Get an AI summary of your lead pipeline health', tab: 'summary' },
            { icon: <ApiOutlined   style={{ fontSize: 22, color: '#22c55e' }} />, title: 'Lead Explainer', desc: 'Understand why any lead was scored the way it was', tab: 'explain' },
          ].map(({ icon, title, desc }) => (
            <Col xs={24} sm={12} md={6} key={title}>
              <div style={{
                background: 'var(--bg-card)', borderRadius: 12, padding: '14px 16px',
                border: '1px solid var(--border-card)',
                display: 'flex', alignItems: 'flex-start', gap: 12,
              }}>
                <div style={{ marginTop: 2 }}>{icon}</div>
                <div>
                  <div style={{ color: 'var(--text-stat)', fontWeight: 600, fontSize: 13, marginBottom: 3 }}>{title}</div>
                  <div style={{ color: '#64748b', fontSize: 11, lineHeight: 1.45 }}>{desc}</div>
                </div>
              </div>
            </Col>
          ))}
        </Row>
      )}


      {/* AI Status Banner */}
      <Card
        style={{ marginBottom: 16, background: healthBg, borderColor: healthBorder }}
        styles={{ body: { padding: '12px 20px' } }}
      >
        <Row align="middle" justify="space-between">
          <Col>
            <Space>
              <ApiOutlined style={{ color: healthColor, fontSize: 18 }} />
              <Text style={{ color: 'var(--text-stat)', fontWeight: 600 }}>
                {isAdminOrManager ? (
                  <>
                    {aiHealth?.provider || 'AI Engine'}:{' '}
                    {_hs === 'checking'       ? 'Checking…'
                    : _hs === 'unknown'       ? 'Status unknown'
                    : _hs === 'healthy'       ? 'Connected'
                    : _hs === 'no_key'        ? 'No API key — using rule-based scoring'
                    : _hs === 'rate_limited'  ? 'Rate limited — falling back to cached results'
                    : _hs === 'quota_exceeded'? 'Quota exceeded — rule-based scoring active'
                    : _hs === 'unauthorized'  ? 'Invalid API key — using rule-based scoring'
                    : _hs === 'offline'       ? 'Offline — using rule-based scoring'
                    : 'Unavailable — using rule-based scoring'}
                  </>
                ) : (
                  _hs === 'healthy'
                    ? 'AI is ready — your leads are being analyzed in real time'
                    : _hs === 'checking' || _hs === 'unknown'
                    ? 'Checking AI status…'
                    : 'AI scoring active — results may use rule-based fallback'
                )}
              </Text>
              {isAdminOrManager && _hs === 'checking' && <Spin size="small" style={{ marginLeft: 4 }} />}
              {isAdminOrManager && aiHealth?.model      && <Tag color="blue">{aiHealth.model}</Tag>}
              {isAdminOrManager && aiHealth?.latency_ms && <Tag color="cyan">{aiHealth.latency_ms}ms</Tag>}
              {isAdminOrManager && _hs !== 'healthy' && _hs !== 'checking' && _hs !== 'unknown' && (
                <Tag color="orange">Fallback active</Tag>
              )}
            </Space>
          </Col>
          {isAdminOrManager && (
            <Col>
              <Button size="small" icon={<ReloadOutlined />} onClick={fetchAIHealth}>Refresh</Button>
            </Col>
          )}
        </Row>
      </Card>

      {/* Engine Status Card — admin / manager only */}
      {isAdminOrManager && <Card
        style={{ marginBottom: 24, background: 'var(--bg-card)', borderColor: 'var(--border-card)' }}
        styles={{ body: { padding: 24 } }}
      >
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={12}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div
                style={{
                  width: 24, height: 24, borderRadius: '50%',
                  background: isRunning ? '#22c55e' : '#d9d9d9',
                  animation: isRunning ? 'pulse 1.5s infinite' : 'none',
                  boxShadow: isRunning ? '0 0 20px rgba(26,222,128,0.6)' : 'none',
                }}
              />
              <div>
                <p style={{ margin: 0, fontWeight: 600, fontSize: 16, color: 'var(--text-stat)' }}>
                  Engine Status:{' '}
                  <span style={{ color: isRunning ? '#22c55e' : '#64748b' }}>
                    {isRunning ? 'Running' : 'Stopped'}
                  </span>
                </p>
                <p style={{ margin: '4px 0 0 0', color: '#64748b', fontSize: 12 }}>
                  {isRunning ? 'Processing qualified leads' : 'Engine is idle'}
                </p>
              </div>
            </div>
          </Col>
          <Col xs={24} sm={12} style={{ textAlign: 'right' }}>
            {userRole === 'admin' && (
              <Space>
                <Button
                  type={isRunning ? 'default' : 'primary'}
                  icon={<PlayCircleOutlined />}
                  onClick={handleStartEngine}
                  loading={loading}
                  disabled={isRunning}
                >
                  Start
                </Button>
                <Button
                  type="primary" danger
                  icon={<StopOutlined />}
                  onClick={handleStopEngine}
                  loading={loading}
                  disabled={!isRunning}
                >
                  Stop
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={handleRestartEngine}
                  loading={loading}
                >
                  Restart
                </Button>
              </Space>
            )}
          </Col>
        </Row>
      </Card>}

      {/* Key Metrics */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: 20 } }} style={{ background: 'rgba(15,23,42,0.6)' }}>
            <Statistic
              title="Total Leads"
              value={metrics.total_leads || 0}
              valueStyle={{ color: 'var(--text-stat)', fontSize: 28, fontWeight: 700 }}
            />
            <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(239,68,68,0.12)', borderRadius: 6, padding: '2px 8px', fontSize: 11, color: '#ef4444', fontWeight: 600 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} />
                {metrics.hot || 0} Hot
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(245,158,11,0.12)', borderRadius: 6, padding: '2px 8px', fontSize: 11, color: '#f59e0b', fontWeight: 600 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
                {metrics.warm || 0} Warm
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(59,130,246,0.12)', borderRadius: 6, padding: '2px 8px', fontSize: 11, color: '#3b82f6', fontWeight: 600 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#3b82f6', display: 'inline-block' }} />
                {metrics.cold || 0} Cold
              </span>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: 20 } }} style={{ background: 'rgba(15,23,42,0.6)' }}>
            <div style={{ color: '#64748b', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Average Score</div>
            {metrics.average_score > 0 ? (
              <>
                <div style={{ fontSize: 28, fontWeight: 700, color: metrics.average_score >= 70 ? '#22c55e' : metrics.average_score >= 50 ? '#f59e0b' : '#ef4444', marginBottom: 8 }}>
                  {metrics.average_score}<span style={{ fontSize: 14, color: '#64748b', fontWeight: 400 }}> / 100</span>
                </div>
                <Progress
                  percent={Math.round(metrics.average_score)}
                  strokeColor={metrics.average_score >= 70 ? '#22c55e' : metrics.average_score >= 50 ? '#f59e0b' : '#ef4444'}
                  trailColor="rgba(99,102,241,0.12)"
                  size="small"
                  showInfo={false}
                />
              </>
            ) : (
              <>
                <div style={{ fontSize: 22, fontWeight: 700, color: '#475569', marginBottom: 6 }}>Not scored</div>
                <div style={{ fontSize: 11, color: '#6366f1', cursor: 'pointer' }} onClick={handleQualifyNow}>
                  → Run AI Qualification to score
                </div>
              </>
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: 20 } }} style={{ background: 'rgba(15,23,42,0.6)' }}>
            <div style={{ color: '#64748b', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Data Completeness</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: metrics.data_completeness >= 70 ? '#22c55e' : metrics.data_completeness >= 40 ? '#f59e0b' : 'var(--text-stat)', marginBottom: 8 }}>
              {metrics.data_completeness || 0}<span style={{ fontSize: 14, color: '#64748b', fontWeight: 400 }}>%</span>
            </div>
            <div style={{ fontSize: 11, color: '#64748b' }}>
              {metrics.with_email || 0} with email &nbsp;·&nbsp; {metrics.with_phone || 0} with phone
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: 20 } }} style={{ background: 'rgba(15,23,42,0.6)' }}>
            <div style={{ color: '#64748b', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>AI Provider</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: (_hs === 'healthy' || metrics.ai_available) ? '#22c55e' : '#94a3b8', marginBottom: 8, lineHeight: 1.2 }}>
              {aiHealth?.provider || metrics.ai_provider || 'Gemini AI'}
            </div>
            <Badge
              status={_hs === 'healthy' || metrics.ai_available ? 'success' : _hs === 'checking' || _hs === 'unknown' ? 'default' : 'warning'}
              text={
                <span style={{ color: '#64748b', fontSize: 11 }}>
                  {_hs === 'healthy' || metrics.ai_available
                    ? `Connected${aiHealth?.model ? ` · ${aiHealth.model}` : ''}`
                    : _hs === 'checking' ? 'Checking…'
                    : _hs === 'unknown'  ? 'Status unknown'
                    : _hs === 'offline'  ? 'Offline — rule-based active'
                    : 'Rule-based scoring active'}
                </span>
              }
            />
          </Card>
        </Col>
      </Row>

      {/* Batch Qualification */}
      <Card style={{ marginBottom: 24, background: 'rgba(15,23,42,0.6)' }} styles={{ body: { padding: 20 } }}>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} md={12}>
            <Space direction="vertical" size={2}>
              <h3 style={{ margin: 0, color: 'var(--text-stat)', fontSize: 14, fontWeight: 600 }}>
                <ThunderboltOutlined style={{ color: '#f59e0b', marginRight: 8 }} />
                AI Batch Qualification
              </h3>
              <p style={{ margin: 0, color: '#64748b', fontSize: 12 }}>
                Score all leads using {metrics.ai_provider || 'Gemini AI'}. Each lead gets AI reasoning, strengths, and next actions.
              </p>
            </Space>
          </Col>
          <Col xs={24} md={12} style={{ textAlign: 'right' }}>
            <Button
              type="primary"
              icon={<RocketOutlined />}
              onClick={handleQualifyNow}
              loading={isRunningBatch}
              size="large"
            >
              {isRunningBatch ? 'Qualifying with AI...' : 'Run AI Qualification'}
            </Button>
          </Col>
        </Row>
        {isRunningBatch && (
          <div style={{ marginTop: 16 }}>
            <Progress percent={Math.round(runProgress)} status="active" strokeColor={{ '0%': '#f59e0b', '100%': '#22c55e' }} />
            <p style={{ margin: '8px 0 0 0', color: '#64748b', fontSize: 12 }}>
              Scoring all leads with AI... {Math.round(runProgress)}%
            </p>
          </div>
        )}
        {batchResult && !isRunningBatch && (
          <div style={{ marginTop: 16, padding: 12, background: 'var(--bg-elevated)', borderRadius: 8 }}>
            <Row gutter={16}>
              <Col span={4}><Statistic title="Processed" value={batchResult.processed || 0} valueStyle={{ color: 'var(--text-stat)', fontSize: 18 }} /></Col>
              <Col span={4}><Statistic title="Hot"       value={batchResult.hot || 0}       valueStyle={{ color: '#ef4444',           fontSize: 18 }} /></Col>
              <Col span={4}><Statistic title="Warm"      value={batchResult.warm || 0}      valueStyle={{ color: '#f59e0b',           fontSize: 18 }} /></Col>
              <Col span={4}><Statistic title="Cold"      value={batchResult.cold || 0}      valueStyle={{ color: '#3b82f6',           fontSize: 18 }} /></Col>
              <Col span={4}><Statistic title="Avg Score" value={batchResult.average_score || 0} valueStyle={{ color: '#22c55e',       fontSize: 18 }} /></Col>
              <Col span={4}><Statistic title="Model"     value={batchResult.ai_provider || 'Gemini'} valueStyle={{ color: '#06b6d4', fontSize: 14 }} /></Col>
            </Row>
          </div>
        )}
      </Card>

      {/* ── 10-Stage Pipeline Overview ──────────────────────────────────────── */}
      <Card
        style={{ marginBottom: 24, background: 'rgba(15,23,42,0.6)', borderColor: 'var(--border-card)' }}
        styles={{ body: { padding: 20 } }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <RocketOutlined style={{ fontSize: 18, color: '#a78bfa' }} />
          <div>
            <h3 style={{ margin: 0, color: 'var(--text-stat)', fontSize: 14, fontWeight: 600 }}>
              10-Stage Collection Pipeline
            </h3>
            <p style={{ margin: 0, color: '#64748b', fontSize: 11 }}>
              Every lead candidate passes through all stages before being saved
            </p>
          </div>
        </div>
        <PipelineVisualizer currentStage={0} isDone={false} strategy={null} qualityReport={null} />
      </Card>


      {/* AI Intelligence Tabs */}
      <Card
        style={{ marginBottom: 24, background: 'rgba(15,23,42,0.6)' }}
        styles={{ body: { padding: '0 20px 20px 20px' } }}
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab} style={{ color: 'var(--text-stat)' }} items={tabItems} />
      </Card>

      {/* AI Settings — admin / manager only */}
      {isAdminOrManager && (
        <Card style={{ marginBottom: 24, background: 'rgba(15,23,42,0.6)' }} styles={{ body: { padding: 20 } }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ margin: 0, color: 'var(--text-stat)', fontSize: 14, fontWeight: 600 }}>AI Model Settings</h3>
            {userRole === 'admin'
              ? <Button type="primary" onClick={handleOpenSettings}>Configure</Button>
              : <span style={{ fontSize: 11, color: '#64748b' }}>View only</span>
            }
          </div>
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12}>
              <label style={{ color: '#64748b', fontSize: 12 }}>
                Confidence Threshold — <strong style={{ color: 'var(--text-stat)' }}>{aiSettings.confidence_threshold}%</strong>
              </label>
              <Slider value={aiSettings.confidence_threshold} disabled marks={{ 0: '0%', 50: '50%', 100: '100%' }} style={{ marginTop: 8 }} />
            </Col>
            <Col xs={24} sm={12}>
              <label style={{ color: '#64748b', fontSize: 12 }}>
                Batch Size — <strong style={{ color: 'var(--text-stat)' }}>{aiSettings.batch_size} leads</strong>
              </label>
              <Input value={aiSettings.batch_size} disabled style={{ marginTop: 8 }} />
            </Col>
            <Col xs={24} sm={12}>
              <label style={{ color: '#64748b', fontSize: 12 }}>
                Max Workers — <strong style={{ color: 'var(--text-stat)' }}>{aiSettings.max_workers} threads</strong>
              </label>
              <Input value={aiSettings.max_workers} disabled style={{ marginTop: 8 }} />
            </Col>
          </Row>
        </Card>
      )}

      {/* Live Logs */}
      <Card style={{ background: 'rgba(15,23,42,0.6)' }} styles={{ body: { padding: 20 } }}>
        <h3 style={{ margin: '0 0 16px 0', color: 'var(--text-stat)', fontSize: 14, fontWeight: 600 }}>Live Activity Log</h3>
        <Table
          columns={logColumns}
          dataSource={logs.map((log, i) => ({ ...log, key: i }))}
          pagination={false}
          style={{ color: 'var(--text-stat)' }}
          size="small"
          scroll={{ x: 800 }}
          locale={{ emptyText: <div style={{ padding: '20px 0', color: '#475569' }}>No activity logged yet</div> }}
        />
      </Card>

      {/* Reject Label Modal */}
      <Modal
        title="Reject Label"
        open={rejectModal.visible}
        onCancel={() => setRejectModal({ visible: false, id: null, note: '' })}
        onOk={handleRejectFeedback}
        okText="Reject"
        okButtonProps={{ danger: true }}
      >
        <p style={{ marginBottom: 12, color: '#64748b', fontSize: 13 }}>
          Optionally explain why this label is being rejected. The user will not see this note.
        </p>
        <Input.TextArea
          rows={3}
          placeholder="e.g. Lead was already marked converted by another team member"
          value={rejectModal.note}
          onChange={(e) => setRejectModal((prev) => ({ ...prev, note: e.target.value }))}
        />
      </Modal>

      {/* Lead Detail Modal */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <EyeOutlined style={{ color: '#6366f1' }} />
            <span>Lead Details</span>
          </div>
        }
        open={leadDetailModal.visible}
        onCancel={() => setLeadDetailModal({ visible: false, lead: null, loading: false })}
        footer={null}
        width={520}
      >
        {leadDetailModal.loading && (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin size="large" />
          </div>
        )}
        {!leadDetailModal.loading && leadDetailModal.lead && (() => {
          const l = leadDetailModal.lead;
          const score = l.qualification_score ?? 0;
          const scoreColor = score >= 70 ? '#16a34a' : score >= 40 ? '#d97706' : '#dc2626';
          const Field = ({ label, value }) => value ? (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: '#64748b', marginBottom: 2 }}>{label}</div>
              <div style={{ fontSize: 13, color: 'var(--text-stat, #0f172a)', fontWeight: 500 }}>{value}</div>
            </div>
          ) : null;
          return (
            <div>
              {/* Score banner */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 14,
                padding: '12px 16px', borderRadius: 10, marginBottom: 18,
                background: `${scoreColor}12`, border: `1px solid ${scoreColor}30`,
              }}>
                <div style={{
                  width: 52, height: 52, borderRadius: '50%', flexShrink: 0,
                  border: `3px solid ${scoreColor}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 16, fontWeight: 800, color: scoreColor,
                }}>
                  {Math.round(score)}
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-stat, #0f172a)' }}>{l.name}</div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>{l.position || ''}{l.position && l.company ? ' · ' : ''}{l.company || ''}</div>
                </div>
                {l.status && (
                  <Tag style={{ marginLeft: 'auto', flexShrink: 0 }}
                    color={l.status === 'qualified' ? 'green' : l.status === 'pending' ? 'orange' : 'default'}>
                    {l.status}
                  </Tag>
                )}
              </div>

              <Divider style={{ margin: '0 0 14px 0', borderColor: 'rgba(99,102,241,0.15)' }} />

              {/* Contact */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 20px' }}>
                <Field label="Email" value={l.email} />
                <Field label="Phone" value={l.phone} />
                <Field label="Location" value={[l.city, l.country].filter(Boolean).join(', ') || l.location} />
                <Field label="Industry" value={l.industry} />
                <Field label="Source" value={l.source} />
                <Field label="Lead Type" value={l.lead_type} />
              </div>

              {(l.website || l.linkedin_url) && (
                <>
                  <Divider style={{ margin: '10px 0 14px 0', borderColor: 'rgba(99,102,241,0.15)' }} />
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    {l.website && (
                      <a href={l.website} target="_blank" rel="noreferrer"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#6366f1' }}>
                        <GlobalOutlined /> {l.website}
                      </a>
                    )}
                    {l.linkedin_url && (
                      <a href={l.linkedin_url} target="_blank" rel="noreferrer"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#0077b5' }}>
                        <LinkedinOutlined /> LinkedIn
                      </a>
                    )}
                  </div>
                </>
              )}

              {l.notes && (
                <>
                  <Divider style={{ margin: '14px 0', borderColor: 'rgba(99,102,241,0.15)' }} />
                  <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Notes</div>
                  <div style={{ fontSize: 12, color: 'var(--text-stat, #374151)', lineHeight: 1.6 }}>{l.notes}</div>
                </>
              )}
            </div>
          );
        })()}
      </Modal>

      {/* Settings Modal */}
      <Modal
        title="AI Model Settings"
        open={settingsModalVisible}
        onCancel={() => setSettingsModalVisible(false)}
        onOk={() => settingsForm.submit()}
        width={600}
      >
        <Form form={settingsForm} layout="vertical" onFinish={handleSaveSettings}>
          <Form.Item label="Confidence Threshold" name="confidence_threshold" initialValue={75} rules={[{ required: true }]}>
            <Slider min={0} max={100} marks={{ 0: '0%', 50: '50%', 100: '100%' }} />
          </Form.Item>
          <Form.Item
            label="Batch Size" name="batch_size" initialValue={100}
            rules={[{ required: true, message: 'Please enter batch size' }, { pattern: /^[0-9]+$/, message: 'Must be a number' }]}
          >
            <Input type="number" placeholder="100" min={1} max={1000} />
          </Form.Item>
          <Form.Item
            label="Max Workers" name="max_workers" initialValue={4}
            rules={[{ required: true, message: 'Please enter max workers' }, { pattern: /^[0-9]+$/, message: 'Must be a number' }]}
          >
            <Input type="number" placeholder="4" min={1} max={16} />
          </Form.Item>
        </Form>
      </Modal>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
};

export default AIEngine;
