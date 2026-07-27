import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl, ActivityIndicator, Modal, TextInput,
  FlatList, Switch, Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { adminAPI, leadsAPI, aiAPI } from '../services/api';
import { showError, showSuccess, showWarning, showConfirm } from '../utils/dialog';

const ROLES = ['user', 'manager', 'sub_admin', 'admin'];

const OUTCOME_COLORS = {
  hot:        COLORS.red,
  warm:       COLORS.amber,
  cold:       '#64748b',
  not_a_lead: '#888',
  converted:  COLORS.green,
};

export default function AdminScreen() {
  const { theme } = useTheme();
  const { isAdmin, isSubAdmin, isManager } = useAuth();

  // ── All hooks must run unconditionally (Rules of Hooks) ───────────────────
  const [activeTab, setActiveTab] = useState((isAdmin || isSubAdmin) ? 'users' : 'approvals');
  const [users, setUsers]         = useState([]);
  const [stats, setStats]         = useState(null);
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Create user modal
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating]     = useState(false);
  const [newUser, setNewUser]       = useState({ full_name: '', email: '', password: '', role: 'user', company: '' });

  // Edit user modal
  const [editUser, setEditUser]   = useState(null);
  const [updatingUser, setUpdating] = useState(false);

  // AI quality report
  const [qualityReport, setQualityReport] = useState(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [fetchError, setFetchError]       = useState(null);

  // Pending feedback approvals
  const [pendingFeedback, setPendingFeedback] = useState([]);
  const [loadingApprovals, setLoadingApprovals] = useState(false);
  const [actionId, setActionId]               = useState(null);

  const fetchPendingFeedback = useCallback(async (silent = false) => {
    if (!isManager) return; // approvals require manager or admin role on the backend
    try {
      if (!silent) setLoadingApprovals(true);
      const res = await aiAPI.getPendingFeedback();
      setPendingFeedback(res.data?.data || []);
    } catch (err) {
      console.warn('[Admin] fetchPendingFeedback failed:', err?.message);
    } finally {
      setLoadingApprovals(false);
    }
  }, [isManager]);

  const fetchAll = useCallback(async (silent = false) => {
    setFetchError(null);
    try {
      if (!silent) setLoading(true);
      const promises = [];
      if (isAdmin || isSubAdmin) {
        promises.push(adminAPI.listUsers().then(r => setUsers(r.data?.users || [])).catch(e => console.warn('[Admin] listUsers failed:', e?.message)));
      }
      if (isManager) {
        promises.push(fetchPendingFeedback(true));
      }
      if (isAdmin) {
        promises.push(adminAPI.getAdminStats().then(r => setStats(r.data?.stats || r.data)).catch(e => console.warn('[Admin] getAdminStats failed:', e?.message)));
      }
      await Promise.allSettled(promises);
    } catch (err) {
      console.error('[Admin] fetchAll unexpected error:', err?.message);
      setFetchError('An unexpected error occurred.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isAdmin, isSubAdmin, isManager, fetchPendingFeedback]);

  useEffect(() => { fetchAll(); }, []);

  useEffect(() => {
    if (activeTab === 'report' && !qualityReport) fetchQualityReport();
  }, [activeTab]);

  const fetchQualityReport = async () => {
    try {
      setLoadingReport(true);
      const r = await aiAPI.getQualityReport();
      setQualityReport(r.data?.report || r.data);
    } catch (err) {
      console.warn('[Admin] fetchQualityReport failed:', err?.message);
    } finally {
      setLoadingReport(false);
    }
  };

  const handleCreateUser = async () => {
    if (!newUser.full_name.trim() || !newUser.email.trim() || !newUser.password.trim()) {
      showWarning('Required', 'Name, email, and password are required');
      return;
    }
    if (newUser.password.length < 8) {
      showWarning('Weak password', 'Password must be at least 8 characters');
      return;
    }
    try {
      setCreating(true);
      await adminAPI.createUser(newUser);
      setShowCreate(false);
      setNewUser({ full_name: '', email: '', password: '', role: 'user', company: '' });
      fetchAll(true);
      showSuccess('Created', 'User created successfully');
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to create user');
    } finally {
      setCreating(false);
    }
  };

  const handleUpdateUser = async () => {
    if (!editUser) return;
    try {
      setUpdating(true);
      await adminAPI.updateUser(editUser.id, { full_name: editUser.full_name, role: editUser.role, company: editUser.company });
      setEditUser(null);
      fetchAll(true);
      showSuccess('Updated', 'User updated successfully');
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to update user');
    } finally {
      setUpdating(false);
    }
  };

  const handleToggleActive = async (u) => {
    const next = !u.is_active;
    try {
      await adminAPI.updateUser(u.id, { is_active: next });
      setUsers((prev) => prev.map((x) => x.id === u.id ? { ...x, is_active: next } : x));
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to update user status');
    }
  };

  const handleDeleteUser = (u) => {
    showConfirm(
      'Delete User',
      `Delete "${u.full_name || u.email}"? This cannot be undone.`,
      async () => {
        try {
          await adminAPI.deleteUser(u.id);
          setUsers((prev) => prev.filter((x) => x.id !== u.id));
        } catch (err) {
          showError('Error', err?.response?.data?.message || 'Failed to delete');
        }
      },
      undefined,
      'Delete',
      'Cancel',
      'danger',
    );
  };

  const handleApprove = async (item) => {
    setActionId(item.id);
    try {
      await aiAPI.approveFeedback(item.id);
      setPendingFeedback((prev) => prev.filter((x) => x.id !== item.id));
      showSuccess('Approved', `Label for "${item.lead_name || item.lead_email || 'lead'}" approved`);
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to approve');
    } finally {
      setActionId(null);
    }
  };

  const handleReject = (item) => {
    showConfirm(
      'Reject Label',
      `Reject "${(item.outcome || '').replace(/_/g, ' ')}" label for "${item.lead_name || item.lead_email || 'lead'}"?`,
      async () => {
        setActionId(item.id);
        try {
          await aiAPI.rejectFeedback(item.id);
          setPendingFeedback((prev) => prev.filter((x) => x.id !== item.id));
          showSuccess('Rejected', 'Label rejected and excluded from ML training');
        } catch (err) {
          showError('Error', err?.response?.data?.message || 'Failed to reject');
        } finally {
          setActionId(null);
        }
      },
      undefined,
      'Reject',
      'Cancel',
      'danger',
    );
  };

  const s = styles(theme);

  // ── Screen-level role guard (after all hooks) ─────────────────────────────
  if (!isManager && !isSubAdmin) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.bg, padding: 32 }}>
        <Ionicons name="lock-closed" size={48} color={theme.textMuted} />
        <Text style={{ fontSize: 18, fontWeight: '700', color: theme.text, marginTop: 16, marginBottom: 8 }}>
          Access Denied
        </Text>
        <Text style={{ fontSize: 14, color: theme.textMuted, textAlign: 'center', lineHeight: 20 }}>
          You need administrator, manager, or company admin privileges to view this screen.
        </Text>
      </View>
    );
  }

  // Build tab list based on role
  // sub_admin: users only; manager: approvals only; admin: full suite
  const tabs = [
    ...((isAdmin || isSubAdmin) ? [['users', 'Users', 'people']] : []),
    ...(isManager ? [['approvals', 'Approvals', 'checkmark-circle']] : []),
    ...(isAdmin ? [
      ['overview',  'Overview',  'bar-chart'],
      ['report',    'AI Report', 'flash'],
    ] : []),
  ];

  return (
    <View style={s.root}>
      {/* Tab Bar */}
      <View style={s.tabs}>
        {tabs.map(([key, label, icon]) => {
          const hasBadge = key === 'approvals' && pendingFeedback.length > 0;
          return (
            <TouchableOpacity key={key} style={[s.tab, activeTab === key && s.tabActive]} onPress={() => setActiveTab(key)}>
              <View style={{ position: 'relative' }}>
                <Ionicons name={`${icon}-outline`} size={16} color={activeTab === key ? '#fff' : theme.textMuted} />
                {hasBadge && (
                  <View style={s.tabBadge}>
                    <Text style={s.tabBadgeText}>{pendingFeedback.length > 9 ? '9+' : pendingFeedback.length}</Text>
                  </View>
                )}
              </View>
              <Text style={[s.tabText, activeTab === key && s.tabTextActive]}>{label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {loading && !refreshing ? (
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : fetchError ? (
        <View style={s.center}>
          <Ionicons name="cloud-offline-outline" size={48} color={theme.textMuted} />
          <Text style={[s.emptyTxt, { marginTop: 12 }]}>{fetchError}</Text>
          <TouchableOpacity style={[s.addBtn, { marginTop: 16 }]} onPress={() => fetchAll()}>
            <Text style={s.addBtnText}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <>
          {/* ── Users Tab (admin + sub_admin) ───────────────────────────── */}
          {activeTab === 'users' && (isAdmin || isSubAdmin) && (
            <View style={{ flex: 1 }}>
              <View style={s.listHeader}>
                <Text style={s.listTitle}>{users.length} user{users.length !== 1 ? 's' : ''}</Text>
                {isAdmin && (
                  <TouchableOpacity style={s.addBtn} onPress={() => setShowCreate(true)}>
                    <Ionicons name="add" size={18} color="#fff" />
                    <Text style={s.addBtnText}>New User</Text>
                  </TouchableOpacity>
                )}
              </View>
              <FlatList
                data={users}
                keyExtractor={(u) => String(u.id)}
                refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchAll(); }} tintColor={COLORS.primary} />}
                contentContainerStyle={{ padding: 12, paddingBottom: 100 }}
                renderItem={({ item: u }) => (
                  <View style={s.userCard}>
                    {u.profile_photo_url ? (
                      <Image source={{ uri: u.profile_photo_url }} style={s.userAvatarImg} />
                    ) : (
                      <View style={s.userAvatar}>
                        <Text style={s.userAvatarTxt}>{(u.full_name || u.email || '?')[0].toUpperCase()}</Text>
                      </View>
                    )}
                    <View style={s.userInfo}>
                      <Text style={s.userName}>{u.full_name || '—'}</Text>
                      <Text style={s.userEmail}>{u.email}</Text>
                      <View style={s.roleRow}>
                        <View style={[s.roleBadge, { backgroundColor: u.role === 'admin' ? `${COLORS.red}18` : `${COLORS.primary}18` }]}>
                          <Text style={[s.roleText, { color: u.role === 'admin' ? COLORS.red : COLORS.primary }]}>
                            {u.role?.toUpperCase()}
                          </Text>
                        </View>
                        {u.company && <Text style={s.userCompany}>{u.company}</Text>}
                      </View>
                    </View>
                    <View style={s.userActions}>
                      <Switch
                        value={u.is_active !== false}
                        onValueChange={() => handleToggleActive(u)}
                        trackColor={{ false: theme.inputBorder, true: `${COLORS.green}80` }}
                        thumbColor={u.is_active !== false ? COLORS.green : '#888'}
                        style={{ transform: [{ scaleX: 0.8 }, { scaleY: 0.8 }] }}
                      />
                      {isAdmin && (
                        <>
                          <TouchableOpacity style={s.iconAction} onPress={() => setEditUser({ ...u })}>
                            <Ionicons name="pencil-outline" size={16} color={COLORS.primary} />
                          </TouchableOpacity>
                          {u.role !== 'admin' && (
                            <TouchableOpacity style={s.iconAction} onPress={() => handleDeleteUser(u)}>
                              <Ionicons name="trash-outline" size={16} color={COLORS.red} />
                            </TouchableOpacity>
                          )}
                        </>
                      )}
                    </View>
                  </View>
                )}
              />
            </View>
          )}

          {/* ── Approvals Tab (manager + admin) ────────────────────────── */}
          {activeTab === 'approvals' && (
            loadingApprovals ? (
              <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
            ) : pendingFeedback.length === 0 ? (
              <View style={s.center}>
                <Ionicons name="checkmark-circle-outline" size={56} color={COLORS.green} />
                <Text style={[s.emptyTxt, { marginTop: 12, fontSize: 15, fontWeight: '600', color: theme.text }]}>
                  All caught up!
                </Text>
                <Text style={[s.emptyTxt, { marginTop: 4 }]}>No labels pending review.</Text>
                <TouchableOpacity
                  style={[s.addBtn, { marginTop: 16, backgroundColor: theme.input }]}
                  onPress={() => fetchPendingFeedback()}
                >
                  <Ionicons name="refresh" size={14} color={COLORS.primary} />
                  <Text style={[s.addBtnText, { color: COLORS.primary }]}>Refresh</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <FlatList
                data={pendingFeedback}
                keyExtractor={(item) => String(item.id)}
                refreshControl={
                  <RefreshControl
                    refreshing={refreshing}
                    onRefresh={() => { setRefreshing(true); fetchPendingFeedback().then(() => setRefreshing(false)); }}
                    tintColor={COLORS.primary}
                  />
                }
                contentContainerStyle={{ padding: 12, paddingBottom: 100 }}
                ListHeaderComponent={
                  <Text style={[s.listTitle, { marginBottom: 10 }]}>
                    {pendingFeedback.length} label{pendingFeedback.length !== 1 ? 's' : ''} awaiting review
                  </Text>
                }
                renderItem={({ item }) => {
                  const outcomeColor = OUTCOME_COLORS[item.outcome] || '#888';
                  const isActioning  = actionId === item.id;
                  return (
                    <View style={s.approvalCard}>
                      <View style={s.approvalInfo}>
                        <Text style={s.approvalLead} numberOfLines={1}>
                          {item.lead_name || item.lead_email || `Lead #${item.lead_id}`}
                        </Text>
                        {item.lead_company ? (
                          <Text style={s.approvalCompany} numberOfLines={1}>{item.lead_company}</Text>
                        ) : null}
                        <View style={s.approvalMeta}>
                          <View style={[s.outcomeBadge, { backgroundColor: `${outcomeColor}20` }]}>
                            <Text style={[s.outcomeBadgeText, { color: outcomeColor }]}>
                              {(item.outcome || '').replace(/_/g, ' ').toUpperCase()}
                            </Text>
                          </View>
                          {item.submitted_by_name ? (
                            <Text style={s.approvalSubmitter} numberOfLines={1}>
                              by {item.submitted_by_name}
                            </Text>
                          ) : null}
                        </View>
                      </View>
                      <View style={s.approvalActions}>
                        <TouchableOpacity
                          style={[s.approveBtn, isActioning && { opacity: 0.6 }]}
                          onPress={() => handleApprove(item)}
                          disabled={actionId !== null}
                        >
                          {isActioning ? (
                            <ActivityIndicator color="#fff" size="small" />
                          ) : (
                            <Ionicons name="checkmark" size={18} color="#fff" />
                          )}
                        </TouchableOpacity>
                        <TouchableOpacity
                          style={[s.rejectBtn, isActioning && { opacity: 0.6 }]}
                          onPress={() => handleReject(item)}
                          disabled={actionId !== null}
                        >
                          <Ionicons name="close" size={18} color="#fff" />
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                }}
              />
            )
          )}

          {/* ── Overview Tab (admin only) ───────────────────────────────── */}
          {activeTab === 'overview' && isAdmin && (
            <ScrollView
              contentContainerStyle={s.scroll}
              refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchAll(); }} tintColor={COLORS.primary} />}
            >
              {stats && (
                <>
                  <View style={s.statsGrid}>
                    {[
                      { label: 'Total Users',  value: stats.total_users     || users.length, color: COLORS.primary, icon: 'people' },
                      { label: 'Total Leads',  value: stats.total_leads     || 0, color: COLORS.cyan,   icon: 'person-add' },
                      { label: 'Qualified',    value: stats.qualified_leads || 0, color: COLORS.green,  icon: 'checkmark-circle' },
                      { label: 'Active Users', value: stats.active_users    || 0, color: COLORS.amber,  icon: 'trending-up' },
                    ].map(({ label, value, color, icon }) => (
                      <View key={label} style={[s.statCard, { borderTopColor: color }]}>
                        <Ionicons name={icon} size={18} color={color} style={{ marginBottom: 6 }} />
                        <Text style={[s.statValue, { color }]}>{value ?? '—'}</Text>
                        <Text style={s.statLabel}>{label}</Text>
                      </View>
                    ))}
                  </View>

                  {stats.users_by_role && (
                    <View style={s.card}>
                      <Text style={s.cardTitle}>Users by Role</Text>
                      {Object.entries(stats.users_by_role).map(([role, count]) => (
                        <View key={role} style={s.metaRow}>
                          <Text style={s.metaLabel}>{role.charAt(0).toUpperCase() + role.slice(1)}</Text>
                          <Text style={s.metaValue}>{count}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                </>
              )}
            </ScrollView>
          )}

          {/* ── AI Quality Report Tab (admin only) ────────────────────── */}
          {activeTab === 'report' && isAdmin && (
            <ScrollView contentContainerStyle={s.scroll}>
              {loadingReport ? (
                <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
              ) : qualityReport ? (
                <>
                  {qualityReport.provider_accuracy && (
                    <View style={s.card}>
                      <Text style={s.cardTitle}>Provider Accuracy</Text>
                      {Object.entries(qualityReport.provider_accuracy).map(([provider, metrics]) => (
                        <View key={provider} style={s.metaRow}>
                          <Text style={s.metaLabel}>{provider.toUpperCase()}</Text>
                          <Text style={s.metaValue}>
                            {metrics.accuracy != null ? `${Math.round(metrics.accuracy * 100)}%` : '—'}
                            {metrics.samples ? ` (${metrics.samples} samples)` : ''}
                          </Text>
                        </View>
                      ))}
                    </View>
                  )}
                  {qualityReport.dataset && (
                    <View style={s.card}>
                      <Text style={s.cardTitle}>Dataset Stats</Text>
                      {Object.entries(qualityReport.dataset).map(([k, v]) => (
                        <View key={k} style={s.metaRow}>
                          <Text style={s.metaLabel}>{k.replace(/_/g, ' ')}</Text>
                          <Text style={s.metaValue}>{String(v)}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                  {qualityReport.dynamic_weights && (
                    <View style={s.card}>
                      <Text style={s.cardTitle}>Dynamic Weights</Text>
                      {Object.entries(qualityReport.dynamic_weights).map(([k, v]) => (
                        <View key={k} style={s.metaRow}>
                          <Text style={s.metaLabel}>{k.toUpperCase()}</Text>
                          <Text style={s.metaValue}>{typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : String(v)}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                  <TouchableOpacity style={s.refreshReportBtn} onPress={() => { setQualityReport(null); fetchQualityReport(); }}>
                    <Ionicons name="refresh" size={16} color={COLORS.primary} />
                    <Text style={[s.addBtnText, { color: COLORS.primary }]}>Refresh Report</Text>
                  </TouchableOpacity>
                </>
              ) : (
                <View style={s.center}>
                  <Text style={s.emptyTxt}>No report available. Check AI Engine status.</Text>
                  <TouchableOpacity style={s.addBtn} onPress={fetchQualityReport}>
                    <Text style={s.addBtnText}>Generate Report</Text>
                  </TouchableOpacity>
                </View>
              )}
            </ScrollView>
          )}
        </>
      )}

      {/* Create User Modal */}
      <Modal visible={showCreate} transparent animationType="slide" onRequestClose={() => setShowCreate(false)}>
        <View style={s.modalOverlay}>
          <View style={[s.modalSheet, { backgroundColor: theme.card }]}>
            <View style={s.modalHeader}>
              <Text style={[s.modalTitle, { color: theme.text }]}>Create New User</Text>
              <TouchableOpacity onPress={() => setShowCreate(false)}>
                <Ionicons name="close" size={22} color={theme.textSecondary} />
              </TouchableOpacity>
            </View>
            <View style={s.modalDivider} />
            <ScrollView keyboardShouldPersistTaps="handled">
              {[
                { key: 'full_name', label: 'Full Name *', placeholder: 'John Doe',       type: 'default' },
                { key: 'email',     label: 'Email *',     placeholder: 'john@acme.com',   type: 'email-address' },
                { key: 'company',   label: 'Company',     placeholder: 'Acme Corp',       type: 'default' },
                { key: 'password',  label: 'Password *',  placeholder: 'Min. 8 chars',    type: 'default', secure: true },
              ].map(({ key, label, placeholder, type, secure }) => (
                <View key={key} style={{ marginBottom: 10 }}>
                  <Text style={[s.inputLabel, { color: theme.textSecondary }]}>{label}</Text>
                  <TextInput
                    style={[s.modalInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                    value={newUser[key]}
                    onChangeText={(v) => setNewUser((p) => ({ ...p, [key]: v }))}
                    placeholder={placeholder}
                    placeholderTextColor={theme.textMuted}
                    keyboardType={type}
                    secureTextEntry={!!secure}
                    autoCapitalize={type === 'email-address' ? 'none' : 'words'}
                  />
                </View>
              ))}
              <Text style={[s.inputLabel, { color: theme.textSecondary }]}>Role</Text>
              <View style={s.roleSelector}>
                {ROLES.map((r) => (
                  <TouchableOpacity
                    key={r}
                    style={[s.roleOption, newUser.role === r && { backgroundColor: COLORS.primary }]}
                    onPress={() => setNewUser((p) => ({ ...p, role: r }))}
                  >
                    <Text style={[s.roleOptionText, newUser.role === r && { color: '#fff' }]}>
                      {r.charAt(0).toUpperCase() + r.slice(1)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <View style={s.modalActions}>
                <TouchableOpacity style={s.cancelBtn} onPress={() => setShowCreate(false)} disabled={creating}>
                  <Text style={[s.cancelBtnText, { color: theme.textSecondary }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.addBtn, s.modalSubmitBtn, creating && { opacity: 0.7 }]}
                  onPress={handleCreateUser}
                  disabled={creating}
                >
                  {creating ? <ActivityIndicator color="#fff" size="small" /> : <Text style={s.addBtnText}>Create User</Text>}
                </TouchableOpacity>
              </View>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Edit User Modal */}
      <Modal visible={!!editUser} transparent animationType="slide" onRequestClose={() => setEditUser(null)}>
        {editUser && (
          <View style={s.modalOverlay}>
            <View style={[s.modalSheet, { backgroundColor: theme.card }]}>
              <View style={s.modalHeader}>
                <Text style={[s.modalTitle, { color: theme.text }]}>Edit User</Text>
                <TouchableOpacity onPress={() => setEditUser(null)}>
                  <Ionicons name="close" size={22} color={theme.textSecondary} />
                </TouchableOpacity>
              </View>
              <View style={s.modalDivider} />
              <ScrollView keyboardShouldPersistTaps="handled">
                {[
                  { key: 'full_name', label: 'Full Name', placeholder: 'John Doe',  type: 'default' },
                  { key: 'company',   label: 'Company',   placeholder: 'Acme Corp', type: 'default' },
                ].map(({ key, label, placeholder, type }) => (
                  <View key={key} style={{ marginBottom: 10 }}>
                    <Text style={[s.inputLabel, { color: theme.textSecondary }]}>{label}</Text>
                    <TextInput
                      style={[s.modalInput, { backgroundColor: theme.input, color: theme.text, borderColor: theme.inputBorder }]}
                      value={editUser[key] || ''}
                      onChangeText={(v) => setEditUser((p) => ({ ...p, [key]: v }))}
                      placeholder={placeholder}
                      placeholderTextColor={theme.textMuted}
                      keyboardType={type}
                    />
                  </View>
                ))}
                <Text style={[s.inputLabel, { color: theme.textSecondary }]}>Role</Text>
                <View style={s.roleSelector}>
                  {ROLES.map((r) => (
                    <TouchableOpacity
                      key={r}
                      style={[s.roleOption, editUser.role === r && { backgroundColor: COLORS.primary }]}
                      onPress={() => setEditUser((p) => ({ ...p, role: r }))}
                    >
                      <Text style={[s.roleOptionText, editUser.role === r && { color: '#fff' }]}>
                        {r.charAt(0).toUpperCase() + r.slice(1)}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <View style={s.modalActions}>
                  <TouchableOpacity style={s.cancelBtn} onPress={() => setEditUser(null)} disabled={updatingUser}>
                    <Text style={[s.cancelBtnText, { color: theme.textSecondary }]}>Cancel</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.addBtn, s.modalSubmitBtn, updatingUser && { opacity: 0.7 }]}
                    onPress={handleUpdateUser}
                    disabled={updatingUser}
                  >
                    {updatingUser ? <ActivityIndicator color="#fff" size="small" /> : <Text style={s.addBtnText}>Save Changes</Text>}
                  </TouchableOpacity>
                </View>
              </ScrollView>
            </View>
          </View>
        )}
      </Modal>
    </View>
  );
}

const styles = (theme) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  scroll: { padding: 14, paddingBottom: 100 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },

  tabs:          { flexDirection: 'row', backgroundColor: theme.card, borderBottomWidth: 1, borderBottomColor: theme.cardBorder, paddingHorizontal: 10, paddingVertical: 8, gap: 4 },
  tab:           { flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: 10, gap: 3 },
  tabActive:     { backgroundColor: COLORS.primary },
  tabText:       { fontSize: 11, fontWeight: '600', color: theme.textMuted },
  tabTextActive: { color: '#fff', fontWeight: '700' },
  tabBadge:      { position: 'absolute', top: -4, right: -6, minWidth: 14, height: 14, borderRadius: 7, backgroundColor: COLORS.red, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 2 },
  tabBadgeText:  { fontSize: 8, fontWeight: '800', color: '#fff' },

  listHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 12, paddingBottom: 4 },
  listTitle:  { fontSize: 13, color: theme.textMuted, fontWeight: '500' },
  addBtn:     { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: COLORS.primary, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 7 },
  addBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },

  userCard:     { flexDirection: 'row', alignItems: 'center', backgroundColor: theme.card, borderRadius: 14, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: theme.cardBorder, elevation: 1 },
  userAvatar:   { width: 44, height: 44, borderRadius: 22, backgroundColor: `${COLORS.primary}18`, alignItems: 'center', justifyContent: 'center', marginRight: 10 },
  userAvatarImg:{ width: 44, height: 44, borderRadius: 22, marginRight: 10 },
  userAvatarTxt:{ fontSize: 17, fontWeight: '800', color: COLORS.primary },
  userInfo:     { flex: 1 },
  userName:     { fontSize: 14, fontWeight: '700', color: theme.text },
  userEmail:    { fontSize: 12, color: theme.textMuted, marginTop: 1 },
  roleRow:      { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 },
  roleBadge:    { borderRadius: 20, paddingHorizontal: 8, paddingVertical: 2 },
  roleText:     { fontSize: 9, fontWeight: '700' },
  userCompany:  { fontSize: 11, color: theme.textMuted },
  userActions:  { gap: 6 },
  iconAction:   { width: 32, height: 32, borderRadius: 8, backgroundColor: theme.input, alignItems: 'center', justifyContent: 'center' },

  // Approval cards
  approvalCard:      { flexDirection: 'row', alignItems: 'center', backgroundColor: theme.card, borderRadius: 14, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: theme.cardBorder, elevation: 1 },
  approvalInfo:      { flex: 1, marginRight: 10 },
  approvalLead:      { fontSize: 14, fontWeight: '700', color: theme.text },
  approvalCompany:   { fontSize: 12, color: theme.textMuted, marginTop: 1 },
  approvalMeta:      { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4, flexWrap: 'wrap' },
  approvalSubmitter: { fontSize: 11, color: theme.textMuted, flexShrink: 1 },
  approvalActions:   { flexDirection: 'row', gap: 8 },
  outcomeBadge:      { borderRadius: 20, paddingHorizontal: 8, paddingVertical: 2 },
  outcomeBadgeText:  { fontSize: 9, fontWeight: '700' },
  approveBtn:        { width: 38, height: 38, borderRadius: 10, backgroundColor: COLORS.green, alignItems: 'center', justifyContent: 'center' },
  rejectBtn:         { width: 38, height: 38, borderRadius: 10, backgroundColor: COLORS.red,   alignItems: 'center', justifyContent: 'center' },

  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 },
  statCard:  { width: '47%', backgroundColor: theme.card, borderRadius: 14, padding: 14, borderTopWidth: 3, borderWidth: 1, borderColor: theme.cardBorder, elevation: 2 },
  statValue: { fontSize: 26, fontWeight: '800' },
  statLabel: { fontSize: 11, color: theme.textMuted, fontWeight: '600', marginTop: 2, textTransform: 'uppercase' },

  card:      { backgroundColor: theme.card, borderRadius: 16, padding: 16, marginBottom: 14, borderWidth: 1, borderColor: theme.cardBorder, elevation: 2 },
  cardTitle: { fontSize: 13, fontWeight: '700', color: theme.text, marginBottom: 10 },
  metaRow:   { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  metaLabel: { fontSize: 13, color: theme.textMuted },
  metaValue: { fontSize: 13, color: theme.text, fontWeight: '500' },

  reportText: { fontSize: 13, color: theme.textSecondary, lineHeight: 21 },
  recRow:     { flexDirection: 'row', gap: 8, marginBottom: 8, alignItems: 'flex-start' },
  recText:    { flex: 1, fontSize: 13, color: theme.textSecondary, lineHeight: 19 },
  refreshReportBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, justifyContent: 'center', padding: 12 },
  emptyTxt:   { color: theme.textMuted, textAlign: 'center', marginBottom: 4 },

  // Modals
  modalOverlay:   { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'flex-end' },
  modalSheet:     { borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: 20, paddingBottom: 40, maxHeight: '88%' },
  modalHeader:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  modalTitle:     { fontSize: 17, fontWeight: '700' },
  modalDivider:   { height: 1, backgroundColor: theme.cardBorder, marginVertical: 14 },
  inputLabel:     { fontSize: 12, fontWeight: '600', marginBottom: 5 },
  modalInput:     { height: 48, borderRadius: 12, paddingHorizontal: 14, fontSize: 14, borderWidth: 1 },
  roleSelector:   { flexDirection: 'row', gap: 8, marginBottom: 4 },
  roleOption:     { flex: 1, paddingVertical: 9, borderRadius: 10, backgroundColor: theme.input, alignItems: 'center', borderWidth: 1, borderColor: theme.inputBorder },
  roleOptionText: { fontSize: 13, fontWeight: '600', color: theme.textSecondary },
  modalActions:   { flexDirection: 'row', gap: 10, marginTop: 20 },
  cancelBtn:      { flex: 1, height: 48, borderRadius: 12, borderWidth: 1.5, borderColor: theme.inputBorder, alignItems: 'center', justifyContent: 'center' },
  cancelBtnText:  { fontSize: 14, fontWeight: '700' },
  modalSubmitBtn: { flex: 1.6, height: 48, borderRadius: 12, justifyContent: 'center' },
});
