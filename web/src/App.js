import React, { useState, useEffect, useRef, useCallback } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Layout, Spin, message, ConfigProvider, theme } from 'antd';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import './App.css';

import Dashboard from './pages/Dashboard';
import LeadsPage from './pages/LeadsPage';
import DataSources from './pages/DataSources';
import AIEngine from './pages/AIEngine';
import Settings from './pages/Settings';
import Login from './pages/Login';
import GoogleCallback from './pages/GoogleCallback';
import NotFound from './pages/NotFound';
import AdminPanel from './pages/AdminPanel';
import Analytics from './pages/Analytics';
import { ThemeContext } from './context/ThemeContext';

// Apply saved theme immediately (before React paint) to prevent flash
document.documentElement.setAttribute('data-theme', localStorage.getItem('theme') || 'dark');

const darkTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#6366f1',
    colorBgContainer: '#0f172a',
    colorBgElevated: '#1e293b',
    colorBorder: 'rgba(99,102,241,0.1)',
    colorText: '#e2e8f0',
    colorTextSecondary: '#94a3b8',
    borderRadius: 10,
    fontFamily: "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
  },
};

const lightTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: '#6366f1',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#f8fafc',
    colorBorder: 'rgba(99,102,241,0.2)',
    colorText: '#1e293b',
    colorTextSecondary: '#64748b',
    borderRadius: 10,
    fontFamily: "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
  },
};

const VALID_ROLES = ['user', 'manager', 'sub_admin', 'admin'];

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('authToken'));
  const [userRole, setUserRole] = useState(localStorage.getItem('userRole') || 'user');
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [isDark, setIsDark] = useState(localStorage.getItem('theme') !== 'light');
  const [notifCounts, setNotifCounts] = useState({ pendingUsers: 0, pendingLabels: 0 });
  const notifPollRef = useRef(null);

  const handleSetIsDark = (val) => {
    setIsDark(val);
    localStorage.setItem('theme', val ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', val ? 'dark' : 'light');
  };

  // Apply theme attribute on mount and whenever isDark changes
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  useEffect(() => {
    const token = localStorage.getItem('authToken');
    if (!token) {
      setIsAuthenticated(false);
      setLoading(false);
      return;
    }
    // Verify role from backend — don't trust localStorage alone
    fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:5000'}/api/v1/auth/profile`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(res => (res.ok ? res.json() : Promise.reject(res.status)))
      .then(data => {
        const role = data?.user?.role;
        // Always overwrite localStorage — never let a stale value persist.
        // If the backend returns an unrecognised role, treat it as 'user'.
        const resolvedRole = (role && VALID_ROLES.includes(role)) ? role : 'user';
        setUserRole(resolvedRole);
        localStorage.setItem('userRole', resolvedRole);
        // Persist fresh user object
        const existing = JSON.parse(localStorage.getItem('user') || '{}');
        localStorage.setItem('user', JSON.stringify({ ...existing, ...data.user }));
        setIsAuthenticated(true);
      })
      .catch(() => {
        // Token invalid — log out
        localStorage.removeItem('authToken');
        localStorage.removeItem('user');
        localStorage.removeItem('tokenExpiry');
        localStorage.removeItem('userRole');
        setIsAuthenticated(false);
      })
      .finally(() => setLoading(false));
  }, []);

  const fetchNotifCounts = useCallback(async (role) => {
    const token = localStorage.getItem('authToken');
    if (!token) return;
    const base = process.env.REACT_APP_API_URL || 'http://localhost:5000';
    const hdrs = { Authorization: `Bearer ${token}` };
    if (role !== 'admin' && role !== 'sub_admin') return;
    try {
      // ML label approvals are a system-admin-only queue — skip for sub_admin.
      // Pending *user* approvals are company-scoped server-side, so sub_admin gets those.
      const [labelsRes, usersRes] = await Promise.allSettled([
        role === 'admin'
          ? fetch(`${base}/api/v1/ai/feedback/pending`, { headers: hdrs }).then(r => r.json())
          : Promise.resolve(null),
        fetch(`${base}/api/v1/auth/admin/stats`, { headers: hdrs }).then(r => r.json()),
      ]);
      const labels = labelsRes.status === 'fulfilled' ? (labelsRes.value?.data?.length ?? labelsRes.value?.count ?? 0) : 0;
      const users  = usersRes.status === 'fulfilled' && usersRes.value ? (usersRes.value?.stats?.pending_users ?? 0) : 0;
      setNotifCounts({ pendingLabels: labels, pendingUsers: users });
    } catch {
      // non-fatal — counts stay at their last value
    }
  }, []);

  // Poll notification counts every 60 s while authenticated
  useEffect(() => {
    if (!isAuthenticated) return;
    const role = localStorage.getItem('userRole') || 'user';
    fetchNotifCounts(role);
    notifPollRef.current = setInterval(() => fetchNotifCounts(role), 60_000);
    return () => clearInterval(notifPollRef.current);
  }, [isAuthenticated, fetchNotifCounts]);

  const handleLoginSuccess = () => {
    setIsAuthenticated(true);
    setUserRole(localStorage.getItem('userRole') || 'user');
  };

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('user');
    localStorage.removeItem('tokenExpiry');
    localStorage.removeItem('userRole');
    setIsAuthenticated(false);
    setUserRole('user');
    message.success('Signed out');
  };

  const isAdmin    = userRole === 'admin';
  const isSubAdmin = userRole === 'sub_admin';
  const bgMain = isDark ? '#0a0e1a' : '#f4f6fb';

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: bgMain }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <ThemeContext.Provider value={{ isDark, setIsDark: handleSetIsDark }}>
      <ConfigProvider theme={isDark ? darkTheme : lightTheme}>
        <Router>
          {!isAuthenticated ? (
            <Routes>
              <Route path="/" element={<Login onLoginSuccess={handleLoginSuccess} />} />
              <Route path="/auth/google/callback" element={<GoogleCallback onLoginSuccess={handleLoginSuccess} />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          ) : (
            <Layout style={{ minHeight: '100vh', background: bgMain }}>
              <Sidebar collapsed={collapsed} userRole={userRole} notifCounts={notifCounts} />
              <Layout style={{ marginLeft: collapsed ? 80 : 240, transition: 'margin-left 0.2s' }}>
                <Header collapsed={collapsed} setCollapsed={setCollapsed} onLogout={handleLogout} />
                <Layout.Content style={{ background: bgMain, minHeight: 'calc(100vh - 56px)' }}>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/leads" element={<LeadsPage />} />
                    <Route path="/analytics" element={<Analytics />} />
                    <Route path="/auth/google/callback" element={<Navigate to="/" />} />
                    {isAdmin && <Route path="/sources" element={<DataSources />} />}
                    {/* sub_admin cannot access AI Engine — redirect to leads */}
                    <Route path="/ai-engine" element={isSubAdmin ? <Navigate to="/leads" replace /> : <AIEngine />} />
                    <Route path="/settings" element={<Settings userRole={userRole} />} />
                    {/* admin AND sub_admin can access admin panel (scoped by company for sub_admin) */}
                    {(isAdmin || isSubAdmin) && <Route path="/admin" element={<AdminPanel userRole={userRole} />} />}
                    <Route path="*" element={<NotFound />} />
                  </Routes>
                </Layout.Content>
              </Layout>
            </Layout>
          )}
        </Router>
      </ConfigProvider>
    </ThemeContext.Provider>
  );
}

export default App;
