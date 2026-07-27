import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Row, Col,
  message, Popconfirm, Switch, Typography, Alert,
} from 'antd';
import {
  UserAddOutlined, EditOutlined, DeleteOutlined, TeamOutlined,
  SafetyCertificateOutlined, ThunderboltOutlined, DatabaseOutlined,
  ReloadOutlined, CrownOutlined, ClockCircleOutlined, CheckCircleOutlined,
  ShopOutlined, NotificationOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import { apiWithFallback, broadcastNotification, listBroadcasts, deleteBroadcast } from '../services/api';

const { Title } = Typography;

const ROLE_COLORS = {
  admin:     '#6366f1',
  sub_admin: '#e879f9',
  manager:   '#f59e0b',
  user:      '#22c55e',
};
const ROLE_LABELS = {
  admin:     'Admin',
  sub_admin: 'Company Admin',
  manager:   'Manager',
  user:      'User',
};

const AdminPanel = ({ userRole }) => {
  const isSubAdmin = userRole === 'sub_admin';

  const [users, setUsers]               = useState([]);
  const [stats, setStats]               = useState({});
  const [companyName, setCompanyName]   = useState('');
  const [loading, setLoading]           = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingUser, setEditingUser]   = useState(null);
  const [pendingRoles, setPendingRoles] = useState({});
  const [approvingId, setApprovingId]   = useState(null);
  const [togglingId, setTogglingId]     = useState(null);
  const [broadcasts, setBroadcasts]           = useState([]);
  const [broadcastModal, setBroadcastModal]   = useState(false);
  const [sendingBroadcast, setSendingBroadcast] = useState(false);
  const [broadcastType, setBroadcastType]     = useState('info');
  const [broadcastTitle, setBroadcastTitle]   = useState('');
  const [broadcastDesc, setBroadcastDesc]     = useState('');
  const [form] = Form.useForm();

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiWithFallback('/auth/admin/users', 'get');
      setUsers(res.data.users || []);
      if (res.data.company_scope && res.data.company) {
        setCompanyName(res.data.company);
      }
    } catch {
      message.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await apiWithFallback('/auth/admin/stats', 'get');
      setStats(res.data.stats || {});
    } catch {
      message.warning('Could not load system stats');
    }
  }, []);

  const fetchBroadcasts = useCallback(async () => {
    if (isSubAdmin) return;
    try {
      const res = await listBroadcasts();
      setBroadcasts(res.data.broadcasts || []);
    } catch { /* silently ignore */ }
  }, [isSubAdmin]);

  useEffect(() => {
    fetchUsers();
    fetchStats();
    fetchBroadcasts();
  }, [fetchUsers, fetchStats, fetchBroadcasts]);

  const handleSendBroadcast = async () => {
    if (!broadcastTitle.trim()) { message.warning('Title is required'); return; }
    setSendingBroadcast(true);
    try {
      await broadcastNotification(broadcastTitle.trim(), broadcastDesc.trim(), broadcastType);
      message.success('Notification sent to all users');
      setBroadcastModal(false);
      setBroadcastTitle('');
      setBroadcastDesc('');
      setBroadcastType('info');
      fetchBroadcasts();
    } catch {
      message.error('Failed to send broadcast');
    } finally {
      setSendingBroadcast(false);
    }
  };

  const handleDeleteBroadcast = async (id) => {
    try {
      await deleteBroadcast(id);
      setBroadcasts(prev => prev.filter(b => b.id !== id));
      message.success('Broadcast dismissed for all users');
    } catch {
      message.error('Failed to remove broadcast');
    }
  };

  const handleCreateUser = () => {
    setEditingUser(null);
    form.resetFields();
    form.setFieldsValue({ role: 'user' });
    setModalVisible(true);
  };

  const handleEditUser = (user) => {
    setEditingUser(user);
    form.setFieldsValue({
      full_name: user.full_name,
      email:     user.email,
      company:   user.company,
      role:      user.role,
    });
    setModalVisible(true);
  };

  const handleDeleteUser = async (userId) => {
    try {
      await apiWithFallback(`/auth/admin/users/${userId}`, 'delete');
      message.success('User deleted');
      fetchUsers();
      fetchStats();
    } catch (err) {
      message.error(err?.response?.data?.message || 'Failed to delete user');
    }
  };

  const handleSubmit = async (values) => {
    try {
      if (editingUser) {
        const updateData = {
          full_name: values.full_name,
          company:   values.company,
          role:      values.role,
        };
        if (values.password) updateData.password = values.password;
        await apiWithFallback(`/auth/admin/users/${editingUser.id}`, 'put', updateData);
        message.success('User updated');
      } else {
        await apiWithFallback('/auth/admin/users', 'post', values);
        message.success('User created');
      }
      setModalVisible(false);
      fetchUsers();
      fetchStats();
    } catch (err) {
      message.error(err?.response?.data?.message || 'Operation failed');
    }
  };

  const handleToggleActive = async (user) => {
    const newState = !user.is_active;
    setUsers(prev => prev.map(u => u.id === user.id ? { ...u, is_active: newState } : u));
    setTogglingId(user.id);
    try {
      const res = await apiWithFallback(`/auth/admin/users/${user.id}`, 'put', { is_active: newState });
      const saved = res?.data?.user;
      if (saved) setUsers(prev => prev.map(u => u.id === user.id ? { ...u, ...saved } : u));
      message.success(`User ${newState ? 'activated' : 'deactivated'} successfully`);
      fetchStats();
    } catch (err) {
      setUsers(prev => prev.map(u => u.id === user.id ? { ...u, is_active: user.is_active } : u));
      message.error(err?.response?.data?.message || 'Failed to update user status');
    } finally {
      setTogglingId(null);
    }
  };

  const approveUser = async (userId) => {
    const role = pendingRoles[userId] || 'user';
    try {
      setApprovingId(userId);
      await apiWithFallback(`/auth/admin/users/${userId}`, 'put', { is_active: true, role });
      message.success('User approved and activated');
      fetchUsers();
      fetchStats();
    } catch (err) {
      message.error(err?.response?.data?.message || 'Failed to approve user');
    } finally {
      setApprovingId(null);
    }
  };

  // Base columns shared by both roles
  const baseColumns = [
    {
      title: 'User',
      key: 'user',
      render: (_, record) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {record.profile_photo_url ? (
            <img
              src={record.profile_photo_url}
              alt=""
              style={{ width: 36, height: 36, borderRadius: 10, objectFit: 'cover', flexShrink: 0 }}
            />
          ) : (
            <div style={{
              width: 36, height: 36, borderRadius: 10, flexShrink: 0,
              background: record.role === 'admin'
                ? 'linear-gradient(135deg, #6366f1, #8b5cf6)'
                : record.role === 'sub_admin'
                  ? 'linear-gradient(135deg, #a855f7, #e879f9)'
                  : 'linear-gradient(135deg, #334155, #475569)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 600, color: '#fff',
            }}>
              {(record.full_name || record.email || '?').charAt(0).toUpperCase()}
            </div>
          )}
          <div>
            <div style={{ color: 'var(--text-body)', fontWeight: 500, fontSize: 13 }}>
              {record.full_name || 'No Name'}
            </div>
            <div style={{ color: '#64748b', fontSize: 11 }}>{record.email}</div>
          </div>
        </div>
      ),
    },
    {
      title: 'Company',
      dataIndex: 'company',
      key: 'company',
      render: (v) => <span style={{ color: '#94a3b8' }}>{v || '—'}</span>,
    },
    {
      title: 'Role',
      dataIndex: 'role',
      key: 'role',
      render: (role) => (
        <Tag
          color={ROLE_COLORS[role] || '#64748b'}
          style={{ borderRadius: 6, fontWeight: 600 }}
        >
          {role === 'admin'     && <CrownOutlined style={{ marginRight: 4 }} />}
          {role === 'sub_admin' && <ShopOutlined  style={{ marginRight: 4 }} />}
          {ROLE_LABELS[role] || role}
        </Tag>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active, record) => (
        <Switch
          checked={active}
          loading={togglingId === record.id}
          onChange={() => handleToggleActive(record)}
          checkedChildren="Active"
          unCheckedChildren="Inactive"
          size="small"
        />
      ),
    },
  ];

  // sub_admin's table is already scoped to one company — the Company column would just
  // repeat the same value on every row, so drop it there. System admin keeps it, plus Edit + Delete.
  const columns = isSubAdmin ? baseColumns.filter(c => c.key !== 'company') : [
    ...baseColumns,
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button
            type="text" size="small"
            icon={<EditOutlined />}
            onClick={() => handleEditUser(record)}
            style={{ color: '#6366f1' }}
          />
          {record.role !== 'admin' && (
            <Popconfirm
              title="Delete this user?"
              onConfirm={() => handleDeleteUser(record.id)}
              okText="Delete"
              okButtonProps={{ danger: true }}
            >
              <Button type="text" size="small" icon={<DeleteOutlined />} style={{ color: '#ef4444' }} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const cardStyle = {
    background: 'rgba(15, 23, 42, 0.6)',
    border: '1px solid rgba(99,102,241,0.08)',
    borderRadius: 16,
  };

  const pendingUsers = users.filter(u => !u.is_active);
  const activeUsers  = users.filter(u =>  u.is_active);

  const allStatCards = [
    { title: 'Total Users',      value: stats.total_users     || 0, icon: <TeamOutlined />,              color: '#6366f1', subAdminOk: true  },
    { title: 'Active Users',     value: stats.active_users    || 0, icon: <SafetyCertificateOutlined />, color: '#22c55e', subAdminOk: true  },
    { title: 'Pending Approval', value: stats.pending_users   || 0, icon: <ClockCircleOutlined />,       color: '#f97316', subAdminOk: true  },
    { title: 'Admins',           value: stats.admin_count     || 0, icon: <CrownOutlined />,             color: '#f59e0b', subAdminOk: false },
    { title: 'Total Leads',      value: stats.total_leads     || 0, icon: <DatabaseOutlined />,          color: '#3b82f6', subAdminOk: true  },
    { title: 'Qualified Leads',  value: stats.qualified_leads || 0, icon: <ThunderboltOutlined />,       color: '#8b5cf6', subAdminOk: true  },
  ];
  const statCards = allStatCards.filter(s => !isSubAdmin || s.subAdminOk);

  return (
    <div style={{ padding: '24px 28px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <Title level={3} style={{ color: 'var(--text-stat)', margin: 0, fontWeight: 700 }}>
            {isSubAdmin ? (
              <>
                <ShopOutlined style={{ color: '#e879f9', marginRight: 10 }} />
                Company Admin
                {companyName && (
                  <span style={{
                    marginLeft: 12, fontSize: 16, fontWeight: 500,
                    color: '#e879f9', background: 'rgba(232,121,249,0.1)',
                    padding: '2px 12px', borderRadius: 20,
                  }}>
                    {companyName}
                  </span>
                )}
              </>
            ) : (
              <>
                <CrownOutlined style={{ color: '#f59e0b', marginRight: 10 }} />
                Admin Panel
              </>
            )}
          </Title>
          <p style={{ color: '#64748b', margin: '4px 0 0', fontSize: 13 }}>
            {isSubAdmin
              ? `Managing users within ${companyName || 'your company'}`
              : 'Manage users, roles, and system overview'
            }
          </p>
        </div>
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => { fetchUsers(); fetchStats(); }}
            style={{ borderColor: 'rgba(99,102,241,0.2)', color: '#94a3b8' }}
          >
            Refresh
          </Button>
          {!isSubAdmin && (
            <Button
              icon={<NotificationOutlined />}
              onClick={() => setBroadcastModal(true)}
              style={{ borderColor: 'rgba(99,102,241,0.3)', color: '#a78bfa' }}
            >
              Broadcast
            </Button>
          )}
          {!isSubAdmin && (
            <Button
              type="primary"
              icon={<UserAddOutlined />}
              onClick={handleCreateUser}
              style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', border: 'none', fontWeight: 600 }}
            >
              Add User
            </Button>
          )}
        </Space>
      </div>

      {/* Company scope notice */}
      {isSubAdmin && (
        <Alert
          type="info"
          showIcon
          icon={<ShopOutlined />}
          message={
            <span>
              You are managing users for <strong>{companyName || 'your company'}</strong> only.
              You can activate or deactivate users. Contact the system administrator for role changes or new accounts.
            </span>
          }
          style={{
            marginBottom: 20,
            background: 'rgba(232,121,249,0.06)',
            border: '1px solid rgba(232,121,249,0.2)',
            borderRadius: 12,
          }}
        />
      )}

      {/* Stats */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {statCards.map((s, i) => {
          const needsAttention = s.title === 'Pending Approval' && s.value > 0;
          return (
            <Col xs={24} sm={12} md={8} lg={isSubAdmin ? 8 : 4} xl={isSubAdmin ? 8 : 4} key={i} style={{ minWidth: 130 }}>
              <Card
                style={{
                  ...cardStyle,
                  ...(needsAttention ? { borderColor: 'rgba(249,115,22,0.45)' } : {}),
                }}
                styles={{ body: { padding: '16px 20px' } }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: 10,
                    background: `${s.color}15`, color: s.color,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 18,
                    animation: needsAttention ? 'pulse 1.8s ease-in-out infinite' : 'none',
                  }}>
                    {s.icon}
                  </div>
                  <div>
                    <div style={{ color: '#64748b', fontSize: 11, fontWeight: 500 }}>{s.title}</div>
                    <div style={{ color: needsAttention ? s.color : 'var(--text-stat)', fontSize: 22, fontWeight: 700 }}>{s.value}</div>
                  </div>
                </div>
              </Card>
            </Col>
          );
        })}
      </Row>

      {/* Active Broadcasts — system admin only */}
      {!isSubAdmin && broadcasts.length > 0 && (
        <Card
          title={
            <span style={{ color: '#a78bfa', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
              <NotificationOutlined />
              Active Broadcasts
              <span style={{ background: '#a78bfa20', color: '#a78bfa', borderRadius: 10, padding: '1px 8px', fontSize: 11, fontWeight: 700 }}>
                {broadcasts.length}
              </span>
            </span>
          }
          style={{ ...cardStyle, marginBottom: 20, borderColor: 'rgba(167,139,250,0.25)' }}
          styles={{ body: { padding: '8px 0' } }}
        >
          {broadcasts.map(b => {
            const typeColor = { info: '#3b82f6', success: '#22c55e', warning: '#f59e0b', error: '#ef4444' }[b.type] || '#3b82f6';
            return (
              <div key={b.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 20px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: typeColor, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: 'var(--text-body)', fontWeight: 600, fontSize: 13 }}>{b.title}</div>
                  {b.description && <div style={{ color: '#64748b', fontSize: 11, marginTop: 2 }}>{b.description}</div>}
                </div>
                <Tag color={typeColor} style={{ borderRadius: 6, fontWeight: 600, textTransform: 'capitalize', border: `1px solid ${typeColor}40` }}>
                  {b.type}
                </Tag>
                <Popconfirm title="Dismiss for all users?" onConfirm={() => handleDeleteBroadcast(b.id)} okText="Dismiss" okButtonProps={{ danger: true }}>
                  <Button type="text" size="small" icon={<CloseCircleOutlined />} style={{ color: '#ef4444' }} />
                </Popconfirm>
              </div>
            );
          })}
        </Card>
      )}

      {/* Pending Approval — system admin sees everyone; sub_admin sees their own company (server-scoped) */}
      {pendingUsers.length > 0 && (
        <Card
          title={
            <span style={{ color: '#f97316', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
              <ClockCircleOutlined />
              Pending Approval
              <span style={{
                background: '#f9731620', color: '#f97316',
                borderRadius: 10, padding: '1px 8px', fontSize: 11, fontWeight: 700,
              }}>
                {pendingUsers.length}
              </span>
            </span>
          }
          style={{ ...cardStyle, marginBottom: 20, borderColor: 'rgba(249,115,22,0.2)' }}
          styles={{ body: { padding: '8px 0' } }}
        >
          {pendingUsers.map(u => (
            <div key={u.id} style={{
              display: 'flex', alignItems: 'center', gap: 16,
              padding: '12px 20px',
              borderBottom: '1px solid rgba(255,255,255,0.04)',
            }}>
              {u.profile_photo_url ? (
                <img
                  src={u.profile_photo_url}
                  alt=""
                  style={{ width: 36, height: 36, borderRadius: 10, objectFit: 'cover', flexShrink: 0 }}
                />
              ) : (
                <div style={{
                  width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                  background: 'linear-gradient(135deg, #f97316, #fb923c)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 14, fontWeight: 700, color: '#fff',
                }}>
                  {(u.full_name || u.email || '?').charAt(0).toUpperCase()}
                </div>
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: 'var(--text-body)', fontWeight: 500, fontSize: 13 }}>
                  {u.full_name || 'No Name'}
                </div>
                <div style={{ color: '#64748b', fontSize: 11 }}>{u.email}</div>
                {u.company && <div style={{ color: '#475569', fontSize: 11 }}>{u.company}</div>}
              </div>
              {/* sub_admin can only activate — role changes are system-admin only */}
              {!isSubAdmin && (
                <Select
                  value={pendingRoles[u.id] || 'user'}
                  onChange={v => setPendingRoles(prev => ({ ...prev, [u.id]: v }))}
                  size="small"
                  style={{ width: 140 }}
                  popupMatchSelectWidth={false}
                >
                  <Select.Option value="user">User</Select.Option>
                  <Select.Option value="manager">Manager</Select.Option>
                  <Select.Option value="sub_admin">Company Admin</Select.Option>
                  <Select.Option value="admin">Admin</Select.Option>
                </Select>
              )}
              <Button
                type="primary" size="small"
                icon={<CheckCircleOutlined />}
                loading={approvingId === u.id}
                onClick={() => approveUser(u.id)}
                style={{ background: '#22c55e', borderColor: '#22c55e', fontWeight: 600 }}
              >
                Approve
              </Button>
              {/* Reject (delete) is system-admin only — sub_admin has no delete permission */}
              {!isSubAdmin && (
                <Popconfirm
                  title="Reject and delete this account?"
                  onConfirm={() => handleDeleteUser(u.id)}
                  okText="Reject"
                  okButtonProps={{ danger: true }}
                >
                  <Button type="text" size="small" icon={<DeleteOutlined />} style={{ color: '#ef4444' }} />
                </Popconfirm>
              )}
            </div>
          ))}
        </Card>
      )}

      {/* Users Table */}
      <Card
        title={
          <span style={{ color: 'var(--text-body)', fontWeight: 600 }}>
            {isSubAdmin ? `${companyName || 'Company'} Users` : 'User Management'}
          </span>
        }
        style={cardStyle}
        styles={{ body: { padding: 0 } }}
      >
        <Table
          dataSource={activeUsers}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          style={{ background: 'transparent' }}
        />
      </Card>

      {/* Broadcast Modal — system admin only */}
      {!isSubAdmin && (
        <Modal
          title={
            <span style={{ color: 'var(--text-stat)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
              <NotificationOutlined style={{ color: '#a78bfa' }} />
              Send Broadcast Notification
            </span>
          }
          open={broadcastModal}
          onCancel={() => { setBroadcastModal(false); setBroadcastTitle(''); setBroadcastDesc(''); setBroadcastType('info'); }}
          footer={null}
          styles={{ body: { paddingTop: 20 } }}
        >
          <div style={{ marginBottom: 14 }}>
            <div style={{ color: '#94a3b8', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Type</div>
            <Select value={broadcastType} onChange={setBroadcastType} style={{ width: '100%' }}>
              <Select.Option value="info">Info</Select.Option>
              <Select.Option value="success">Success</Select.Option>
              <Select.Option value="warning">Warning</Select.Option>
              <Select.Option value="error">Error</Select.Option>
            </Select>
          </div>
          <div style={{ marginBottom: 14 }}>
            <div style={{ color: '#94a3b8', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Title <span style={{ color: '#ef4444' }}>*</span></div>
            <Input
              value={broadcastTitle}
              onChange={e => setBroadcastTitle(e.target.value)}
              placeholder="e.g. Scheduled maintenance tonight at 10 PM"
              maxLength={120}
            />
          </div>
          <div style={{ marginBottom: 20 }}>
            <div style={{ color: '#94a3b8', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Message (optional)</div>
            <Input.TextArea
              value={broadcastDesc}
              onChange={e => setBroadcastDesc(e.target.value)}
              placeholder="Additional details visible in the notification panel..."
              rows={3}
              maxLength={300}
            />
          </div>
          <div style={{ textAlign: 'right' }}>
            <Space>
              <Button onClick={() => { setBroadcastModal(false); setBroadcastTitle(''); setBroadcastDesc(''); setBroadcastType('info'); }}>Cancel</Button>
              <Button
                type="primary"
                icon={<NotificationOutlined />}
                loading={sendingBroadcast}
                onClick={handleSendBroadcast}
                style={{ background: 'linear-gradient(135deg, #7c3aed, #a78bfa)', border: 'none', fontWeight: 600 }}
              >
                Send to All Users
              </Button>
            </Space>
          </div>
        </Modal>
      )}

      {/* Create/Edit Modal — system admin only */}
      {!isSubAdmin && (
        <Modal
          title={
            <span style={{ color: 'var(--text-stat)', fontWeight: 600 }}>
              {editingUser ? 'Edit User' : 'Create New User'}
            </span>
          }
          open={modalVisible}
          onCancel={() => setModalVisible(false)}
          footer={null}
          styles={{ body: { paddingTop: 20 } }}
        >
          <Form form={form} layout="vertical" onFinish={handleSubmit}>
            <Form.Item
              name="full_name"
              label="Full Name"
              rules={[{ required: true, message: 'Enter full name' }]}
            >
              <Input placeholder="John Doe" />
            </Form.Item>

            <Form.Item
              name="email"
              label="Email"
              rules={[
                { required: true, message: 'Enter email' },
                { type: 'email', message: 'Enter a valid email' },
              ]}
            >
              <Input placeholder="user@example.com" disabled={!!editingUser} />
            </Form.Item>

            <Form.Item
              name="password"
              label={editingUser ? 'New Password (leave empty to keep current)' : 'Password'}
              rules={editingUser ? [] : [{ required: true, min: 8, message: 'Min 8 characters' }]}
            >
              <Input.Password placeholder="Minimum 8 characters" />
            </Form.Item>

            {/* Company required when role is sub_admin */}
            <Form.Item shouldUpdate={(prev, curr) => prev.role !== curr.role} noStyle>
              {({ getFieldValue }) => (
                <Form.Item
                  name="company"
                  label="Company"
                  rules={
                    getFieldValue('role') === 'sub_admin'
                      ? [{ required: true, message: 'Company is required for Company Admin' }]
                      : []
                  }
                >
                  <Input placeholder="Company name" />
                </Form.Item>
              )}
            </Form.Item>

            <Form.Item name="role" label="Role" rules={[{ required: true }]}>
              <Select>
                <Select.Option value="user">User</Select.Option>
                <Select.Option value="manager">Manager</Select.Option>
                <Select.Option value="sub_admin">Company Admin</Select.Option>
                <Select.Option value="admin">Admin</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
              <Space>
                <Button onClick={() => setModalVisible(false)}>Cancel</Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', border: 'none', fontWeight: 600 }}
                >
                  {editingUser ? 'Update' : 'Create'}
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Modal>
      )}
    </div>
  );
};

export default AdminPanel;
