import React, { useState, useEffect, useCallback, useContext } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Card, Tabs, Form, Input, Button, Checkbox, Switch, Table, message, Spin,
  Row, Col, Divider, Tag, Popconfirm, Select, InputNumber, Alert, Space, Tooltip,
} from 'antd';
import {
  DeleteOutlined, CopyOutlined, EyeOutlined, EyeInvisibleOutlined,
  PlusOutlined, CheckCircleOutlined, CloseCircleOutlined, WarningOutlined,
  BulbOutlined, MoonOutlined, ApiOutlined, SaveOutlined, LinkOutlined,
  ThunderboltOutlined, ExperimentOutlined, SendOutlined,
  GlobalOutlined, MailOutlined, RocketOutlined, CameraOutlined, UserOutlined,
} from '@ant-design/icons';
import { Avatar, Upload } from 'antd';
import { apiWithFallback, uploadProfilePhoto, deleteProfilePhoto } from '../services/api';
import { ThemeContext } from '../context/ThemeContext';

const Settings = ({ userRole }) => {
  const { isDark, setIsDark } = useContext(ThemeContext);
  const location = useLocation();
  const isAdmin   = userRole === 'admin';
  const isManager = userRole === 'manager';
  const [activeTab, setActiveTab] = useState(
    () => new URLSearchParams(location.search).get('tab') || 'profile'
  );
  const [loading, setLoading] = useState(false);
  const [settings, setSettings] = useState(null);
  const [notifForm] = Form.useForm();
  const [dataForm] = Form.useForm();
  const [dbForm] = Form.useForm();
  const [profileForm] = Form.useForm();
  const [apiKeys, setApiKeys] = useState([]);
  const [newKeyModal, setNewKeyModal] = useState(null);
  const [visibleKeys, setVisibleKeys] = useState({});
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState(null);

  // Profile photo state
  const [photoUrl, setPhotoUrl] = useState(null);
  const [photoUploading, setPhotoUploading] = useState(false);

  // Data cleanup state
  const [cleanupLoading, setCleanupLoading] = useState(false);

  // Integration keys state
  const [integrations, setIntegrations] = useState({});
  const [integrationsLoading, setIntegrationsLoading] = useState(false);
  const [integrationValues, setIntegrationValues] = useState({});
  const [visibleIntegrationKeys, setVisibleIntegrationKeys] = useState({});
  // per-key saving and testing state  { [envKey]: 'idle' | 'saving' | 'testing' | 'ok' | 'fail' }
  const [keyStatus, setKeyStatus] = useState({});

  // Personal API key state
  const [myApiKey, setMyApiKey] = useState(null);   // { has_key, masked }
  const [myApiKeyLoading, setMyApiKeyLoading] = useState(false);
  const [myApiKeyNew, setMyApiKeyNew] = useState(null);   // full key shown once
  const [myApiKeyRevoking, setMyApiKeyRevoking] = useState(false);
  const [bootstrapLoading, setBootstrapLoading] = useState(false);

  const fetchMyApiKey = useCallback(async () => {
    setMyApiKeyLoading(true);
    try {
      const res = await apiWithFallback('/settings/my-api-key', 'get');
      setMyApiKey(res?.data || null);
    } catch (e) {
      console.warn('My API key fetch failed:', e.message);
    } finally {
      setMyApiKeyLoading(false);
    }
  }, []);

  const handleGenerateMyApiKey = async () => {
    setMyApiKeyLoading(true);
    try {
      const res = await apiWithFallback('/settings/my-api-key/generate', 'post');
      setMyApiKeyNew(res?.data?.api_key || null);
      await fetchMyApiKey();
      message.success('API key generated — copy it now, it will not be shown again.');
    } catch (e) {
      message.error('Failed to generate API key: ' + (e?.response?.data?.message || e?.message || 'Unknown error'));
    } finally {
      setMyApiKeyLoading(false);
    }
  };

  const handleRevokeMyApiKey = async () => {
    setMyApiKeyRevoking(true);
    try {
      await apiWithFallback('/settings/my-api-key', 'delete');
      setMyApiKey(null);
      setMyApiKeyNew(null);
      message.success('API key revoked.');
    } catch (e) {
      message.error('Failed to revoke API key: ' + (e?.response?.data?.message || e?.message || 'Unknown error'));
    } finally {
      setMyApiKeyRevoking(false);
    }
  };

  const fetchIntegrations = useCallback(async () => {
    setIntegrationsLoading(true);
    try {
      const res = await apiWithFallback('/settings/integrations', 'get');
      const data = res?.data?.integrations || {};
      setIntegrations(data);
      // Pre-fill inputs with empty string (never show real keys)
      const vals = {};
      Object.keys(data).forEach(k => { vals[k] = ''; });
      setIntegrationValues(vals);
    } catch (e) {
      console.warn('Integrations fetch failed:', e.message);
    } finally {
      setIntegrationsLoading(false);
    }
  }, []);

  const handleSaveIntegration = async (envKey) => {
    const val = (integrationValues[envKey] || '').trim();
    if (!val) { message.info('Paste your API key first.'); return; }
    setKeyStatus(p => ({ ...p, [envKey]: 'saving' }));
    try {
      await apiWithFallback('/settings/integrations', 'post', { [envKey]: val });
      message.success(`${integrations[envKey]?.label || envKey} key saved.`);
      setIntegrationValues(p => ({ ...p, [envKey]: '' }));
      setKeyStatus(p => ({ ...p, [envKey]: 'ok' }));
      fetchIntegrations();
    } catch (e) {
      message.error('Save failed: ' + (e?.response?.data?.message || e?.message || 'Unknown'));
      setKeyStatus(p => ({ ...p, [envKey]: 'fail' }));
    }
  };

  const handleClearIntegration = async (envKey) => {
    setKeyStatus(p => ({ ...p, [envKey]: 'saving' }));
    try {
      await apiWithFallback('/settings/integrations', 'post', { [envKey]: '' });
      message.success(`${integrations[envKey]?.label || envKey} key removed.`);
      setKeyStatus(p => ({ ...p, [envKey]: 'idle' }));
      fetchIntegrations();
    } catch (e) {
      message.error('Remove failed: ' + (e?.response?.data?.message || e?.message || 'Unknown'));
      setKeyStatus(p => ({ ...p, [envKey]: 'idle' }));
    }
  };

  const handleTestIntegration = async (envKey) => {
    const val = (integrationValues[envKey] || '').trim();
    setKeyStatus(p => ({ ...p, [envKey]: 'testing' }));
    try {
      const res = await apiWithFallback('/settings/integrations/test', 'post',
        { key: envKey, ...(val ? { value: val } : {}) });
      const { valid, message: msg } = res?.data || {};
      if (valid) {
        message.success(`${integrations[envKey]?.label}: ${msg || 'Connected'}`);
        setKeyStatus(p => ({ ...p, [envKey]: 'ok' }));
      } else {
        message.warning(`${integrations[envKey]?.label}: ${msg || 'Invalid key'}`);
        setKeyStatus(p => ({ ...p, [envKey]: 'fail' }));
      }
    } catch (e) {
      message.error('Test failed: ' + (e?.response?.data?.message || e?.message || 'Unknown'));
      setKeyStatus(p => ({ ...p, [envKey]: 'fail' }));
    }
  };

  const fetchProfile = useCallback(async () => {
    try {
      const res = await apiWithFallback('/auth/profile', 'get');
      if (res?.data?.user) {
        const u = res.data.user;
        profileForm.setFieldsValue({
          full_name: u.full_name || u.name || '',
          email:     u.email || '',
          company:   u.company || '',
        });
        setPhotoUrl(u.profile_photo_url || null);
        // Keep localStorage in sync so Header picks it up
        const stored = JSON.parse(localStorage.getItem('user') || '{}');
        localStorage.setItem('user', JSON.stringify({ ...stored, profile_photo_url: u.profile_photo_url || null }));
      }
    } catch (err) {
      console.warn('Profile fetch failed:', err.message);
    }
  }, [profileForm]);

  const handlePhotoUpload = async (file) => {
    const allowed = ['image/jpeg', 'image/png', 'image/webp'];
    if (!allowed.includes(file.type)) {
      message.error('Only JPG, PNG, or WebP images are supported');
      return false;
    }
    const formData = new FormData();
    formData.append('photo', file);
    setPhotoUploading(true);
    try {
      const res = await uploadProfilePhoto(formData);
      const url = res.data?.profile_photo_url;
      setPhotoUrl(url);
      const stored = JSON.parse(localStorage.getItem('user') || '{}');
      localStorage.setItem('user', JSON.stringify({ ...stored, profile_photo_url: url }));
      message.success('Profile photo updated');
      window.dispatchEvent(new Event('profile-photo-updated'));
    } catch (err) {
      message.error(err?.response?.data?.message || 'Upload failed');
    } finally {
      setPhotoUploading(false);
    }
    return false; // prevent antd Upload default POST
  };

  const handleRemovePhoto = async () => {
    setPhotoUploading(true);
    try {
      await deleteProfilePhoto();
      setPhotoUrl(null);
      const stored = JSON.parse(localStorage.getItem('user') || '{}');
      localStorage.setItem('user', JSON.stringify({ ...stored, profile_photo_url: null }));
      message.success('Photo removed');
      window.dispatchEvent(new Event('profile-photo-updated'));
    } catch (err) {
      message.error('Failed to remove photo');
    } finally {
      setPhotoUploading(false);
    }
  };

  const fetchSettings = useCallback(async () => {
    try {
      setLoading(true);
      const response = await apiWithFallback('/settings', 'get');
      if (response?.data?.settings) {
        setSettings(response.data.settings);
        notifForm.setFieldsValue(response.data.settings);
        dataForm.setFieldsValue(response.data.settings);
        dbForm.setFieldsValue(response.data.settings);
        setApiKeys(response.data.api_keys || []);
      } else {
        setSettings({});
      }
    } catch (err) {
      console.warn('Settings fetch failed:', err.message);
      setSettings({});
    } finally {
      setLoading(false);
    }
  }, [notifForm, dataForm, dbForm]);

  useEffect(() => {
    fetchProfile();
    fetchSettings();
    fetchIntegrations();
    fetchMyApiKey();
  }, [fetchProfile, fetchSettings, fetchIntegrations, fetchMyApiKey]);

  const handleBootstrapAdmin = async () => {
    setBootstrapLoading(true);
    try {
      await apiWithFallback('/auth/admin/bootstrap', 'post');
      message.success('You are now the system admin! Please sign out and sign back in.');
    } catch (err) {
      const msg = err?.response?.data?.message || 'Could not claim admin access';
      message.error(msg);
    } finally {
      setBootstrapLoading(false);
    }
  };

  const handleSaveProfile = async (values) => {
    try {
      setLoading(true);
      const res = await apiWithFallback('/auth/profile', 'put', {
        full_name: values.full_name,
        company:   values.company,
      });
      if (res?.data?.user) {
        // Update cached user in localStorage
        const stored = JSON.parse(localStorage.getItem('user') || '{}');
        localStorage.setItem('user', JSON.stringify({ ...stored, ...res.data.user }));
      }
      message.success('Profile saved');
    } catch (error) {
      message.error('Failed to save profile');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSettings = async (values) => {
    try {
      setLoading(true);
      await apiWithFallback('/settings', 'post', values);
      setSettings(prev => ({ ...prev, ...values }));
      message.success('Settings saved');
    } catch (error) {
      message.error('Failed to save settings');
    } finally {
      setLoading(false);
    }
  };

  const generateApiKey = async () => {
    try {
      setLoading(true);
      const response = await apiWithFallback('/settings/api-keys/generate', 'post', { name: 'New API Key' });
      setNewKeyModal(response?.data?.api_key || null);
      message.success('API key generated');
      fetchSettings();
    } catch {
      message.error('Failed to generate API key');
    } finally {
      setLoading(false);
    }
  };

  const deleteApiKey = async (keyId) => {
    try {
      setLoading(true);
      await apiWithFallback(`/settings/api-keys/${keyId}`, 'delete');
      setApiKeys(apiKeys.filter(k => k.id !== keyId));
      message.success('API key deleted');
    } catch {
      message.error('Failed to delete API key');
    } finally {
      setLoading(false);
    }
  };

  const handleCleanup = async () => {
    setCleanupLoading(true);
    try {
      const res = await apiWithFallback('/leads/cleanup', 'post');
      const deleted = res?.data?.deleted_count ?? 0;
      const cutoff  = res?.data?.cutoff_date   || '';
      if (deleted === 0) {
        message.info(`No leads older than the retention cutoff (${cutoff}) were found.`);
      } else {
        message.success(`Deleted ${deleted} lead(s) older than ${cutoff}.`);
      }
    } catch (error) {
      const msg = error?.response?.data?.message || error?.message || 'Cleanup failed';
      message.error(msg);
    } finally {
      setCleanupLoading(false);
    }
  };

  const testDatabaseConnection = async (values) => {
    try {
      setTestingConnection(true);
      const response = await apiWithFallback('/settings/test-connection', 'post', {
        host: values.db_host, port: values.db_port,
        user: values.db_user, password: values.db_password, database: values.db_name,
      });
      const connected = response?.data?.connected ?? true;
      setConnectionStatus(connected);
      message.open({ type: connected ? 'success' : 'error', content: connected ? 'Database connected' : 'Connection failed' });
    } catch (error) {
      setConnectionStatus(false);
      message.error('Connection test error: ' + error.message);
    } finally {
      setTestingConnection(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    message.success('Copied to clipboard');
  };

  const handleClearAllLeads = async () => {
    try {
      setLoading(true);
      await apiWithFallback('/leads/clear', 'post');
      message.success('All leads cleared');
    } catch { message.error('Failed to clear leads'); }
    finally { setLoading(false); }
  };

  const handleResetSettings = async () => {
    try {
      setLoading(true);
      await apiWithFallback('/settings/reset', 'post');
      message.success('Settings reset to defaults');
      fetchSettings();
    } catch { message.error('Failed to reset settings'); }
    finally { setLoading(false); }
  };

  const apiKeyColumns = [
    { title: 'Name', dataIndex: 'name', key: 'name', render: (text) => <span style={{ fontWeight: 500 }}>{text}</span> },
    {
      title: 'Key', dataIndex: 'key', key: 'key',
      render: (text, record) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <code style={{ fontSize: 12, opacity: 0.7 }}>
            {text ? (visibleKeys[record.id] ? text : text.substring(0, 10) + '••••••••') : '(hidden for security)'}
          </code>
          {text && (
            <>
              <Button type="text" size="small" icon={visibleKeys[record.id] ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                onClick={() => setVisibleKeys(prev => ({ ...prev, [record.id]: !prev[record.id] }))} />
              <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => copyToClipboard(text)} />
            </>
          )}
        </div>
      ),
    },
    { title: 'Created', dataIndex: 'created', key: 'created', render: (text) => text ? new Date(text).toLocaleDateString() : '—' },
    { title: 'Last Used', dataIndex: 'last_used', key: 'last_used', render: (text) => text ? new Date(text).toLocaleDateString() : 'Never' },
    {
      title: 'Action', key: 'action',
      render: (_, record) => (
        <Popconfirm title="Delete this API key?" onConfirm={() => deleteApiKey(record.id)}>
          <Button type="text" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  if (loading && !settings) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 500 }}><Spin size="large" /></div>;
  }

  return (
    <div style={{ padding: '24px 28px' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ margin: '0 0 4px', fontSize: 26, fontWeight: 700 }}>Settings</h1>
        <p style={{ margin: 0, opacity: 0.5, fontSize: 13 }}>Manage your account, integrations, and preferences</p>
      </div>

      <Card styles={{ body: { padding: '8px 24px 24px' } }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          // ── Profile — all users ─────────────────────────────────────────────
          {
            key: 'profile', label: 'Profile',
            children: (
              <div>
                {/* ── Avatar ── */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 28,
                  padding: '20px 24px', background: isDark ? 'rgba(99,102,241,0.04)' : 'rgba(99,102,241,0.03)',
                  borderRadius: 14, border: `1px solid ${isDark ? 'rgba(99,102,241,0.10)' : 'rgba(99,102,241,0.08)'}` }}>
                  <div style={{ position: 'relative' }}>
                    <Avatar
                      size={72}
                      src={photoUrl || undefined}
                      icon={!photoUrl ? <UserOutlined /> : undefined}
                      style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)', fontSize: 28, fontWeight: 700 }}
                    />
                    {photoUploading && (
                      <div style={{ position: 'absolute', inset: 0, borderRadius: '50%',
                        background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Spin size="small" />
                      </div>
                    )}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: isDark ? '#e2e8f0' : '#1e293b' }}>
                      Profile Photo
                    </div>
                    <Space size={8}>
                      <Upload showUploadList={false} beforeUpload={handlePhotoUpload} accept="image/jpeg,image/png,image/webp">
                        <Button size="small" icon={<CameraOutlined />} loading={photoUploading}>
                          {photoUrl ? 'Change Photo' : 'Upload Photo'}
                        </Button>
                      </Upload>
                      {photoUrl && (
                        <Button size="small" danger onClick={handleRemovePhoto} loading={photoUploading}>
                          Remove
                        </Button>
                      )}
                    </Space>
                    <div style={{ color: isDark ? '#64748b' : '#94a3b8', fontSize: 11, marginTop: 6 }}>
                      JPG, PNG or WebP · max 5 MB · cropped to square
                    </div>
                  </div>
                </div>

                <Form form={profileForm} layout="vertical" onFinish={handleSaveProfile}>
                <Row gutter={[16, 16]}>
                  <Col xs={24} sm={12}>
                    <Form.Item label="Full Name" name="full_name" rules={[{ required: true, message: 'Please enter your name' }]}>
                      <Input placeholder="John Doe" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item label="Email" name="email">
                      <Input type="email" disabled />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={[16, 16]}>
                  <Col xs={24} sm={12}>
                    <Form.Item label="Company" name="company"><Input placeholder="Your Company" /></Form.Item>
                  </Col>
                </Row>
                <Form.Item><Button type="primary" htmlType="submit" loading={loading}>Save Profile</Button></Form.Item>
                </Form>
              </div>
            ),
          },
          // ── API Keys — admin/manager only ──────────────────────────────────
          ...(isAdmin || isManager ? [{
            key: 'api-keys', label: 'API Keys',
            children: (
              <div>
                <div style={{ marginBottom: 20 }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={generateApiKey} loading={loading}>Generate New API Key</Button>
                </div>
                {newKeyModal && (
                  <Alert type="warning" showIcon style={{ marginBottom: 20 }}
                    message="Save your API key — you won't see it again!"
                    description={
                      <div>
                        <code style={{ display: 'block', padding: 12, background: 'rgba(99,102,241,0.06)', borderRadius: 6, margin: '8px 0', wordBreak: 'break-all' }}>{newKeyModal.key}</code>
                        <Space>
                          <Button size="small" onClick={() => copyToClipboard(newKeyModal.key)}>Copy to Clipboard</Button>
                          <Button size="small" onClick={() => setNewKeyModal(null)}>Dismiss</Button>
                        </Space>
                      </div>
                    }
                  />
                )}
                <Table columns={apiKeyColumns} dataSource={apiKeys} rowKey="id" pagination={{ pageSize: 10 }} />
              </div>
            ),
          }] : []),
          {
            key: 'notifications', label: 'Notifications',
            children: (
              <Form form={notifForm} layout="vertical" onFinish={handleSaveSettings} initialValues={settings}>
                <Card title="Notification Preferences" type="inner">
                  <Form.Item label={null} name="notify_new_leads" valuePropName="checked"><Checkbox>Email me when new leads arrive</Checkbox></Form.Item>
                  <Form.Item label={null} name="notify_qualification" valuePropName="checked"><Checkbox>Notify when lead qualification completes</Checkbox></Form.Item>
                  <Form.Item label={null} name="notify_high_quality" valuePropName="checked"><Checkbox>Alert on high-quality leads (score &gt; 80)</Checkbox></Form.Item>
                  <Form.Item label={null} name="notify_system_errors" valuePropName="checked"><Checkbox>Notify about system errors</Checkbox></Form.Item>
                  <Form.Item label={null} name="notify_daily_digest" valuePropName="checked"><Checkbox>Send daily digest email</Checkbox></Form.Item>
                </Card>
                <Divider />
                <Card title="Notification Frequency" type="inner">
                  <Form.Item label="Digest Frequency" name="notify_frequency">
                    <Select style={{ maxWidth: 240 }} options={[{ value: 'daily', label: 'Daily' }, { value: 'weekly', label: 'Weekly' }, { value: 'monthly', label: 'Monthly' }]} />
                  </Form.Item>
                </Card>
                <Form.Item style={{ marginTop: 20 }}><Button type="primary" htmlType="submit" loading={loading}>Save Notification Settings</Button></Form.Item>
              </Form>
            ),
          },
          {
            key: 'data-collection', label: 'Data Collection',
            children: (
              <Form form={dataForm} layout="vertical" onFinish={handleSaveSettings} initialValues={settings}>
                <Card title="Automatic Data Collection" type="inner">
                  <Form.Item label={null} name="auto_collect_linkedin" valuePropName="checked"><Checkbox>Auto-collect from LinkedIn</Checkbox></Form.Item>
                  <Form.Item label={null} name="auto_collect_emails" valuePropName="checked"><Checkbox>Auto-collect email addresses</Checkbox></Form.Item>
                  <Form.Item label={null} name="auto_collect_company" valuePropName="checked"><Checkbox>Auto-collect company information</Checkbox></Form.Item>
                  <Form.Item label={null} name="auto_enrich_leads" valuePropName="checked"><Checkbox>Automatically enrich lead data</Checkbox></Form.Item>
                </Card>
                <Divider />
                <Card title="Data Retention" type="inner">
                  <Form.Item label="Keep lead data for (days)" name="data_retention_days"><InputNumber min={30} max={730} placeholder="90" style={{ width: 160 }} /></Form.Item>
                  <Form.Item label={null} name="auto_delete_old_data" valuePropName="checked"><Checkbox>Automatically delete old data</Checkbox></Form.Item>
                  <Divider style={{ margin: '12px 0' }} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <Popconfirm
                      title={`Delete leads older than ${settings?.data_retention_days || 90} days?`}
                      description="This action cannot be undone."
                      onConfirm={handleCleanup}
                      okText="Delete"
                      okButtonProps={{ danger: true }}
                      disabled={!settings?.auto_delete_old_data}
                    >
                      <Button danger loading={cleanupLoading} disabled={!settings?.auto_delete_old_data}>
                        Run Cleanup Now
                      </Button>
                    </Popconfirm>
                    {!settings?.auto_delete_old_data && (
                      <span style={{ color: '#94a3b8', fontSize: 12 }}>
                        Enable "Automatically delete old data" above to activate
                      </span>
                    )}
                  </div>
                </Card>
                <Form.Item style={{ marginTop: 20 }}><Button type="primary" htmlType="submit" loading={loading}>Save Data Collection Rules</Button></Form.Item>
              </Form>
            ),
          },
          // ── Database — admin only ───────────────────────────────────────────
          ...(isAdmin ? [{
            key: 'database', label: 'Database',
            children: (
              <Form form={dbForm} layout="vertical" initialValues={settings}>
                <Card title="Database Configuration" type="inner">
                  <Row gutter={[16, 16]}>
                    <Col xs={24} sm={12}><Form.Item label="Host" name="db_host"><Input placeholder="localhost" /></Form.Item></Col>
                    <Col xs={24} sm={12}><Form.Item label="Port" name="db_port"><InputNumber placeholder="3306" min={1} max={65535} style={{ width: '100%' }} /></Form.Item></Col>
                  </Row>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} sm={12}><Form.Item label="Username" name="db_user"><Input placeholder="root" /></Form.Item></Col>
                    <Col xs={24} sm={12}><Form.Item label="Password" name="db_password"><Input.Password placeholder="••••••••" /></Form.Item></Col>
                  </Row>
                  <Form.Item label="Database Name" name="db_name"><Input placeholder="ai_lead_collection" /></Form.Item>
                  <div style={{ marginTop: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
                    <Button type="primary" onClick={() => testDatabaseConnection(dbForm.getFieldsValue())} loading={testingConnection}>Test Connection</Button>
                    {connectionStatus !== null && (
                      <Tag icon={connectionStatus ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                        color={connectionStatus ? 'green' : 'red'}>
                        {connectionStatus ? 'Connected' : 'Failed'}
                      </Tag>
                    )}
                  </div>
                </Card>
                <div style={{ marginTop: 16 }}>
                  <Button type="primary" onClick={() => handleSaveSettings(dbForm.getFieldsValue())} loading={loading}>Save Database Settings</Button>
                </div>
              </Form>
            ),
          }] : []),
          {
            key: 'theme', label: 'Theme',
            children: (
              <div>
                <h3 style={{ marginBottom: 20, fontWeight: 600 }}>Appearance</h3>
                <Row gutter={[16, 16]} style={{ marginBottom: 32 }}>
                  {/* Dark mode preview */}
                  <Col xs={24} sm={12} md={8}>
                    <div
                      onClick={() => setIsDark(true)}
                      style={{
                        cursor: 'pointer',
                        borderRadius: 12,
                        overflow: 'hidden',
                        border: isDark ? '2px solid #6366f1' : '2px solid transparent',
                        boxShadow: isDark ? '0 0 0 3px rgba(99,102,241,0.25)' : 'none',
                        transition: 'all 0.2s',
                      }}
                    >
                      <div style={{ background: '#0a0e1a', padding: '16px 16px 12px' }}>
                        <div style={{ background: '#1e293b', borderRadius: 6, height: 8, width: '60%', marginBottom: 6 }} />
                        <div style={{ background: '#1e293b', borderRadius: 6, height: 6, width: '40%', marginBottom: 12 }} />
                        <div style={{ display: 'flex', gap: 6 }}>
                          <div style={{ background: '#6366f1', borderRadius: 4, height: 24, flex: 1 }} />
                          <div style={{ background: '#1e293b', borderRadius: 4, height: 24, flex: 2 }} />
                        </div>
                      </div>
                      <div style={{ background: '#0f172a', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <MoonOutlined style={{ color: '#6366f1' }} />
                        <span style={{ color: '#e2e8f0', fontWeight: 600, fontSize: 13 }}>Dark Mode</span>
                        {isDark && <Tag color="purple" style={{ marginLeft: 'auto', fontSize: 11 }}>Active</Tag>}
                      </div>
                    </div>
                  </Col>

                  {/* Light mode preview */}
                  <Col xs={24} sm={12} md={8}>
                    <div
                      onClick={() => setIsDark(false)}
                      style={{
                        cursor: 'pointer',
                        borderRadius: 12,
                        overflow: 'hidden',
                        border: !isDark ? '2px solid #6366f1' : '2px solid transparent',
                        boxShadow: !isDark ? '0 0 0 3px rgba(99,102,241,0.25)' : 'none',
                        transition: 'all 0.2s',
                      }}
                    >
                      <div style={{ background: '#f1f5f9', padding: '16px 16px 12px' }}>
                        <div style={{ background: '#e2e8f0', borderRadius: 6, height: 8, width: '60%', marginBottom: 6 }} />
                        <div style={{ background: '#e2e8f0', borderRadius: 6, height: 6, width: '40%', marginBottom: 12 }} />
                        <div style={{ display: 'flex', gap: 6 }}>
                          <div style={{ background: '#6366f1', borderRadius: 4, height: 24, flex: 1 }} />
                          <div style={{ background: '#e2e8f0', borderRadius: 4, height: 24, flex: 2 }} />
                        </div>
                      </div>
                      <div style={{ background: '#ffffff', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 8, borderTop: '1px solid #e2e8f0' }}>
                        <BulbOutlined style={{ color: '#6366f1' }} />
                        <span style={{ color: '#1e293b', fontWeight: 600, fontSize: 13 }}>Light Mode</span>
                        {!isDark && <Tag color="purple" style={{ marginLeft: 'auto', fontSize: 11 }}>Active</Tag>}
                      </div>
                    </div>
                  </Col>
                </Row>

                <Divider />

                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <span style={{ fontWeight: 500 }}>Dark Mode</span>
                  <Switch
                    checked={isDark}
                    checkedChildren={<MoonOutlined />}
                    unCheckedChildren={<BulbOutlined />}
                    onChange={(checked) => setIsDark(checked)}
                  />
                  <span style={{ opacity: 0.5, fontSize: 13 }}>Changes apply instantly — no page reload needed</span>
                </div>
              </div>
            ),
          },
          // ── Danger Zone — admin only ────────────────────────────────────────
          ...(isAdmin ? [{
            key: 'danger', label: <span style={{ color: '#ef4444' }}><WarningOutlined style={{ marginRight: 6 }} />Danger Zone</span>,
            children: (
              <div>
                <Alert
                  type="error"
                  showIcon
                  icon={<WarningOutlined />}
                  message="Irreversible Actions"
                  description="Every action on this page permanently destroys data. There is no undo. Read each warning carefully before confirming."
                  style={{ marginBottom: 24, borderRadius: 10 }}
                />

                {/* Clear All Leads */}
                <div style={{
                  border: '1px solid rgba(239,68,68,0.3)',
                  borderRadius: 12,
                  padding: '20px 24px',
                  marginBottom: 16,
                  background: 'rgba(239,68,68,0.04)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-stat)', marginBottom: 4 }}>
                        Clear All Leads
                      </div>
                      <div style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.6 }}>
                        Permanently deletes every lead in the database — scores, contacts, history, and all. This action affects all users and cannot be recovered.
                      </div>
                    </div>
                    <Popconfirm
                      title="Delete all leads?"
                      description="This cannot be undone. All lead data will be permanently destroyed."
                      onConfirm={handleClearAllLeads}
                      okText="Yes, delete everything"
                      okButtonProps={{ danger: true }}
                      cancelText="Cancel"
                      placement="topRight"
                    >
                      <Button danger loading={loading} style={{ flexShrink: 0 }}>
                        Clear All Leads
                      </Button>
                    </Popconfirm>
                  </div>
                </div>

                {/* Reset All Settings */}
                <div style={{
                  border: '1px solid rgba(239,68,68,0.3)',
                  borderRadius: 12,
                  padding: '20px 24px',
                  background: 'rgba(239,68,68,0.04)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-stat)', marginBottom: 4 }}>
                        Reset All Settings
                      </div>
                      <div style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.6 }}>
                        Resets every configuration value — API keys, notification preferences, data-collection rules, and database settings — back to factory defaults.
                      </div>
                    </div>
                    <Popconfirm
                      title="Reset all settings?"
                      description="All custom configuration will be lost and replaced with defaults."
                      onConfirm={handleResetSettings}
                      okText="Yes, reset everything"
                      okButtonProps={{ danger: true }}
                      cancelText="Cancel"
                      placement="topRight"
                    >
                      <Button danger loading={loading} style={{ flexShrink: 0 }}>
                        Reset All Settings
                      </Button>
                    </Popconfirm>
                  </div>
                </div>
              </div>
            ),
          }] : []),
          // ── Integrations — all users ───────────────────────────────────────
          {
            key: 'integrations',
            label: <span><ApiOutlined style={{ marginRight: 6 }} />Integrations</span>,
            children: (
              <Spin spinning={integrationsLoading}>
                <div>
                  {/* Summary bar */}
                  {Object.keys(integrations).length > 0 && (() => {
                    const total = Object.keys(integrations).length;
                    const active = Object.values(integrations).filter(v => v.configured).length;
                    return (
                      <Alert
                        style={{ marginBottom: 24, borderRadius: 10 }}
                        type={active >= 3 ? 'success' : active >= 1 ? 'info' : 'warning'}
                        showIcon
                        message={
                          <span>
                            <strong>{active} of {total}</strong> integrations active
                            {active === 0 && ' — add at least one lead source to start collecting'}
                          </span>
                        }
                        description={active >= 5 ? 'Great coverage! Your pipeline has multiple data sources.' :
                          active >= 2 ? 'Add more integrations to improve lead quality and volume.' :
                          'Recommended: Hunter.io + Apollo.io for best results on free plans.'}
                      />
                    );
                  })()}

                  {/* Categories */}
                  {[
                    { cat: 'lead_collection',   label: 'Lead Collection',     color: '#7c3aed', icon: <RocketOutlined /> },
                    { cat: 'enrichment',         label: 'Data Enrichment',     color: '#0e7490', icon: <ExperimentOutlined /> },
                    { cat: 'email_verification', label: 'Email Verification',  color: '#059669', icon: <MailOutlined /> },
                    { cat: 'ai',                 label: 'AI Providers',        color: '#d97706', icon: <ThunderboltOutlined /> },
                    { cat: 'social',             label: 'Social & Developer',  color: '#b45309', icon: <GlobalOutlined /> },
                  ].map(({ cat, label, color, icon }) => {
                    const keys = Object.entries(integrations).filter(([, v]) => v.category === cat);
                    if (!keys.length) return null;
                    return (
                      <div key={cat} style={{ marginBottom: 32 }}>
                        <Divider orientation="left" style={{ marginBottom: 16 }}>
                          <span style={{ color, fontWeight: 700, fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
                            {icon} {label}
                          </span>
                        </Divider>

                        <Row gutter={[16, 16]}>
                          {keys.map(([envKey, meta]) => {
                            const st = keyStatus[envKey] || 'idle';
                            const isBusy = st === 'saving' || st === 'testing';
                            const hasInput = !!(integrationValues[envKey] || '').trim();
                            const impactColor = meta.quality_impact === 'high' ? '#059669'
                              : meta.quality_impact === 'medium' ? '#d97706' : '#6366f1';

                            return (
                              <Col xs={24} lg={12} key={envKey}>
                                <div style={{
                                  padding: '16px 18px',
                                  background: 'var(--card-bg, rgba(255,255,255,0.03))',
                                  border: meta.configured
                                    ? '1.5px solid rgba(34,197,94,0.35)'
                                    : '1px solid var(--border-color, rgba(255,255,255,0.08))',
                                  borderRadius: 12,
                                  height: '100%',
                                  display: 'flex',
                                  flexDirection: 'column',
                                  gap: 10,
                                }}>
                                  {/* Header row */}
                                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                        <span style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-stat)' }}>
                                          {meta.label}
                                        </span>
                                        {meta.configured
                                          ? <Tag icon={<CheckCircleOutlined />} color="success" style={{ fontSize: 11 }}>Active</Tag>
                                          : <Tag icon={<CloseCircleOutlined />} color="default" style={{ fontSize: 11, opacity: 0.6 }}>Not set</Tag>}
                                        <Tooltip title={`Quality impact: ${meta.quality_impact}`}>
                                          <Tag color={impactColor} style={{ fontSize: 10, cursor: 'default' }}>
                                            {meta.quality_impact === 'high' ? '▲ High impact'
                                              : meta.quality_impact === 'medium' ? '● Medium impact'
                                              : '▼ Low impact'}
                                          </Tag>
                                        </Tooltip>
                                      </div>
                                      <div style={{ color: '#64748b', fontSize: 12, marginTop: 3 }}>{meta.description}</div>
                                    </div>
                                    <Tooltip title="View documentation">
                                      <a href={meta.docs} target="_blank" rel="noopener noreferrer" style={{ flexShrink: 0 }}>
                                        <LinkOutlined style={{ color: '#6366f1', fontSize: 15 }} />
                                      </a>
                                    </Tooltip>
                                  </div>

                                  {/* Free tier badge */}
                                  {meta.free_tier && (
                                    <div style={{ fontSize: 11, color: '#059669', fontWeight: 500 }}>
                                      Free tier: {meta.free_tier}
                                    </div>
                                  )}

                                  {/* Active key indicator */}
                                  {meta.configured && (
                                    <div style={{
                                      fontSize: 12, color: '#64748b',
                                      fontFamily: 'monospace', letterSpacing: 1,
                                    }}>
                                      Current: {meta.masked}
                                    </div>
                                  )}

                                  {/* Input */}
                                  <Input.Password
                                    placeholder={meta.configured ? 'Paste new key to replace…' : 'Paste API key here…'}
                                    value={integrationValues[envKey] || ''}
                                    onChange={e => setIntegrationValues(p => ({ ...p, [envKey]: e.target.value }))}
                                    visibilityToggle={{
                                      visible: !!visibleIntegrationKeys[envKey],
                                      onVisibleChange: v => setVisibleIntegrationKeys(p => ({ ...p, [envKey]: v })),
                                    }}
                                    onPressEnter={() => hasInput && handleSaveIntegration(envKey)}
                                    size="small"
                                  />

                                  {/* Action buttons */}
                                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                    <Button
                                      type="primary"
                                      size="small"
                                      icon={<SaveOutlined />}
                                      loading={st === 'saving'}
                                      disabled={!hasInput || isBusy}
                                      onClick={() => handleSaveIntegration(envKey)}
                                      style={{ background: '#6366f1', borderColor: '#6366f1', flex: 1 }}
                                    >
                                      Save
                                    </Button>
                                    <Button
                                      size="small"
                                      icon={<SendOutlined />}
                                      loading={st === 'testing'}
                                      disabled={(!hasInput && !meta.configured) || isBusy}
                                      onClick={() => handleTestIntegration(envKey)}
                                      style={{ flex: 1 }}
                                    >
                                      Test
                                    </Button>
                                    {meta.configured && (
                                      <Popconfirm
                                        title={`Remove ${meta.label} key?`}
                                        onConfirm={() => handleClearIntegration(envKey)}
                                        okText="Remove"
                                        okButtonProps={{ danger: true }}
                                        cancelText="Cancel"
                                      >
                                        <Button size="small" danger icon={<DeleteOutlined />} disabled={isBusy} />
                                      </Popconfirm>
                                    )}
                                  </div>
                                </div>
                              </Col>
                            );
                          })}
                        </Row>
                      </div>
                    );
                  })}

                  {/* ── Personal API Key ─────────────────────────────────────── */}
                  <Divider style={{ marginTop: 36 }} />
                  <div style={{ marginBottom: 4 }}>
                    <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-stat)' }}>
                      <ApiOutlined style={{ marginRight: 8, color: '#6366f1' }} />
                      Your Personal API Key
                    </span>
                    <div style={{ color: '#64748b', fontSize: 13, marginTop: 4 }}>
                      Use this key in the <code>X-API-Key</code> header to authenticate API requests without a session token.
                    </div>
                  </div>

                  <Spin spinning={myApiKeyLoading}>
                    <div style={{
                      padding: '16px 20px',
                      marginTop: 14,
                      background: 'var(--card-bg, rgba(255,255,255,0.03))',
                      border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
                      borderRadius: 10,
                    }}>
                      {myApiKeyNew ? (
                        <Alert
                          type="warning"
                          showIcon
                          style={{ marginBottom: 14 }}
                          message="Save your key now — it will not be shown again!"
                          description={
                            <div>
                              <code style={{
                                display: 'block', padding: 10,
                                background: 'rgba(99,102,241,0.08)',
                                borderRadius: 6, margin: '8px 0',
                                wordBreak: 'break-all', fontSize: 12,
                              }}>{myApiKeyNew}</code>
                              <Space>
                                <Button size="small" icon={<CopyOutlined />} onClick={() => copyToClipboard(myApiKeyNew)}>Copy</Button>
                                <Button size="small" onClick={() => setMyApiKeyNew(null)}>Dismiss</Button>
                              </Space>
                            </div>
                          }
                        />
                      ) : null}

                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                        {myApiKey?.has_key ? (
                          <Tag icon={<CheckCircleOutlined />} color="green" style={{ fontSize: 13, padding: '4px 10px' }}>
                            Active — {myApiKey.masked}
                          </Tag>
                        ) : (
                          <Tag icon={<CloseCircleOutlined />} color="default" style={{ fontSize: 13, padding: '4px 10px' }}>
                            No key configured
                          </Tag>
                        )}

                        <Button
                          type="primary"
                          icon={<PlusOutlined />}
                          loading={myApiKeyLoading}
                          onClick={handleGenerateMyApiKey}
                          style={{ background: '#6366f1', borderColor: '#6366f1' }}
                        >
                          {myApiKey?.has_key ? 'Regenerate Key' : 'Generate Key'}
                        </Button>

                        {myApiKey?.has_key && (
                          <Popconfirm
                            title="Revoke your API key?"
                            description="Any scripts using this key will stop working immediately."
                            onConfirm={handleRevokeMyApiKey}
                            okText="Revoke"
                            okButtonProps={{ danger: true }}
                            cancelText="Cancel"
                          >
                            <Button danger icon={<DeleteOutlined />} loading={myApiKeyRevoking}>
                              Revoke
                            </Button>
                          </Popconfirm>
                        )}
                      </div>
                    </div>
                  </Spin>
                </div>
              </Spin>
            ),
          },
        ]} />
      </Card>

      {/* First-Admin Recovery — only shown to non-admin users */}
      {!isAdmin && (
        <Card
          style={{
            marginTop: 20,
            background: 'rgba(249,115,22,0.04)',
            border: '1px solid rgba(249,115,22,0.2)',
            borderRadius: 16,
          }}
          bodyStyle={{ padding: '20px 24px' }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
            <div style={{
              width: 40, height: 40, borderRadius: 10, flexShrink: 0,
              background: 'rgba(249,115,22,0.12)', color: '#f97316',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18,
            }}>
              <WarningOutlined />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>
                System Administrator Setup
              </div>
              <div style={{ color: '#64748b', fontSize: 13, lineHeight: 1.6, marginBottom: 14 }}>
                If no administrator account exists yet, you can claim admin access for this account.
                This only works when there are zero admin accounts in the system — once claimed, subsequent attempts are blocked.
                After claiming, sign out and sign back in to activate your admin access.
              </div>
              <Button
                loading={bootstrapLoading}
                onClick={handleBootstrapAdmin}
                style={{
                  background: 'linear-gradient(135deg, #f97316, #fb923c)',
                  border: 'none', color: '#fff', fontWeight: 600, borderRadius: 8,
                }}
              >
                Claim Admin Access
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};

export default Settings;
