import React, { useContext } from 'react';
import { Layout, Menu, Badge } from 'antd';
import {
  DashboardOutlined,
  TeamOutlined,
  SettingOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
  CrownOutlined,
  BarChartOutlined,
  ShopOutlined,
} from '@ant-design/icons';
import { Link, useLocation } from 'react-router-dom';
import { ThemeContext } from '../context/ThemeContext';

const Sidebar = ({ collapsed, userRole, notifCounts = {} }) => {
  const location = useLocation();
  const { isDark } = useContext(ThemeContext);
  const isAdmin    = userRole === 'admin';
  const isSubAdmin = userRole === 'sub_admin';
  const isAdminOrManager = userRole === 'admin' || userRole === 'manager';
  const pendingLabels = notifCounts.pendingLabels || 0;
  const pendingUsers  = notifCounts.pendingUsers  || 0;


  const pathToKey = {
    '/': '1',
    '/sources': '2',
    '/leads': '3',
    '/ai-engine': '4',
    '/analytics': '5',
    '/settings': '6',
    '/admin': '7',
  };

  const aiEngineLabel = (
    <Link to="/ai-engine">
      <Badge count={isAdminOrManager ? pendingLabels : 0} size="small" offset={[6, 0]}
        style={{ backgroundColor: '#f59e0b' }}>
        AI Engine
      </Badge>
    </Link>
  );

  const adminLabel = (
    <Link to="/admin">
      <Badge count={pendingUsers} size="small" offset={[6, 0]}
        style={{ backgroundColor: '#ef4444' }}>
        Admin Panel
      </Badge>
    </Link>
  );

  const companyAdminLabel = (
    <Link to="/admin">
      <Badge count={pendingUsers} size="small" offset={[6, 0]}
        style={{ backgroundColor: '#ef4444' }}>
        Company Admin
      </Badge>
    </Link>
  );

  const items = [
    { key: '1', icon: <DashboardOutlined />, label: <Link to="/">Dashboard</Link> },
    { key: '3', icon: <TeamOutlined />, label: <Link to="/leads">Leads</Link> },
    { key: '5', icon: <BarChartOutlined />, label: <Link to="/analytics">Analytics</Link> },
    { key: '6', icon: <SettingOutlined />, label: <Link to="/settings">Settings</Link> },
  ];

  // sub_admin has no AI Engine access — skip it from the sidebar entirely
  if (!isSubAdmin) {
    items.splice(3, 0,
      { key: '4', icon: <ThunderboltOutlined />, label: aiEngineLabel },
    );
  }

  if (isAdmin) {
    items.splice(1, 0,
      { key: '2', icon: <DatabaseOutlined />, label: <Link to="/sources">Data Sources</Link> },
    );
    items.push(
      { type: 'divider' },
      { key: '7', icon: <CrownOutlined style={{ color: '#f59e0b' }} />, label: adminLabel },
    );
  } else if (isSubAdmin) {
    items.push(
      { type: 'divider' },
      { key: '7', icon: <ShopOutlined style={{ color: '#e879f9' }} />, label: companyAdminLabel },
    );
  }

  // Theme-dependent tokens
  const siderBg      = isDark ? 'linear-gradient(180deg, #111827 0%, #0f172a 100%)' : 'linear-gradient(180deg, #fefeff 0%, #f8faff 100%)';
  const siderBorder  = isDark ? '1px solid rgba(99,102,241,0.06)' : '1px solid #e2e8f0';
  const brandBorder  = isDark ? '1px solid rgba(99,102,241,0.06)' : '1px solid #f1f5f9';
  const brandTitle   = isDark ? '#f1f5f9' : '#1e293b';
  const brandSub     = '#6366f1';
  const statusBg     = isDark ? 'rgba(99,102,241,0.06)' : 'rgba(99,102,241,0.05)';
  const statusBorder = isDark ? '1px solid rgba(99,102,241,0.08)' : '1px solid rgba(99,102,241,0.12)';
  const statusText   = isDark ? '#94a3b8' : '#64748b';
  const statusSub    = isDark ? '#475569' : '#94a3b8';

  return (
    <Layout.Sider
      theme={isDark ? 'dark' : 'light'}
      collapsible
      collapsed={collapsed}
      breakpoint="lg"
      collapsedWidth={80}
      width={240}
      trigger={null}
      style={{
        position: 'fixed',
        left: 0,
        top: 0,
        bottom: 0,
        zIndex: 100,
        background: siderBg,
        borderRight: siderBorder,
        transition: 'background 0.3s, border-color 0.3s',
      }}
    >
      {/* Brand */}
      <div style={{
        padding: collapsed ? '20px 12px' : '24px 20px',
        textAlign: collapsed ? 'center' : 'left',
        borderBottom: brandBorder,
        marginBottom: 8,
        transition: 'border-color 0.3s',
      }}>
        {collapsed ? (
          <div style={{
            width: 42, height: 42, borderRadius: 13,
            background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 60%, #a78bfa 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto',
            boxShadow: '0 4px 14px rgba(99,102,241,0.35)',
          }}>
            <svg width="22" height="22" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
              <line x1="20" y1="13" x2="12" y2="27" stroke="white" strokeWidth="2.2" strokeOpacity="0.55" strokeLinecap="round"/>
              <line x1="20" y1="13" x2="28" y2="27" stroke="white" strokeWidth="2.2" strokeOpacity="0.55" strokeLinecap="round"/>
              <line x1="13" y1="30" x2="27" y2="30" stroke="white" strokeWidth="2.2" strokeOpacity="0.55" strokeLinecap="round"/>
              <circle cx="20" cy="9.5" r="4.5" fill="white"/>
              <circle cx="11" cy="30" r="4" fill="white" fillOpacity="0.9"/>
              <circle cx="29" cy="30" r="4" fill="white" fillOpacity="0.9"/>
            </svg>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 11,
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 60%, #a78bfa 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 12px rgba(99,102,241,0.35)',
              flexShrink: 0,
            }}>
              <svg width="20" height="20" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                <line x1="20" y1="13" x2="12" y2="27" stroke="white" strokeWidth="2.2" strokeOpacity="0.55" strokeLinecap="round"/>
                <line x1="20" y1="13" x2="28" y2="27" stroke="white" strokeWidth="2.2" strokeOpacity="0.55" strokeLinecap="round"/>
                <line x1="13" y1="30" x2="27" y2="30" stroke="white" strokeWidth="2.2" strokeOpacity="0.55" strokeLinecap="round"/>
                <circle cx="20" cy="9.5" r="4.5" fill="white"/>
                <circle cx="11" cy="30" r="4" fill="white" fillOpacity="0.9"/>
                <circle cx="29" cy="30" r="4" fill="white" fillOpacity="0.9"/>
              </svg>
            </div>
            <div>
              <div style={{ color: brandTitle, fontSize: 16, fontWeight: 800, lineHeight: 1.2, letterSpacing: '-0.02em', transition: 'color 0.3s' }}>OrionLead AI</div>
              <div style={{ color: brandSub, fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1.5 }}>Lead Intelligence</div>
            </div>
          </div>
        )}
      </div>

      <Menu
        theme={isDark ? 'dark' : 'light'}
        mode="inline"
        selectedKeys={[pathToKey[location.pathname] || '1']}
        items={items}
        style={{ background: 'transparent', border: 'none', padding: '4px 0' }}
      />

      {/* Bottom Status */}
      {!collapsed && (
        <div style={{
          position: 'absolute', bottom: 16, left: 16, right: 16,
          background: statusBg, padding: '12px 14px',
          borderRadius: 12, border: statusBorder,
          transition: 'background 0.3s, border-color 0.3s',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: '#22c55e', boxShadow: '0 0 8px rgba(34,197,94,0.6)',
            }} />
            <span style={{ color: statusText, fontSize: 11, fontWeight: 600, transition: 'color 0.3s' }}>System Online</span>
          </div>
          <div style={{ color: statusSub, fontSize: 10, transition: 'color 0.3s' }}>
            {isAdmin ? 'Admin Access' : isSubAdmin ? 'Company Admin' : userRole === 'manager' ? 'Manager Access' : 'AI Engine Active'}
          </div>
        </div>
      )}
    </Layout.Sider>
  );
};

export default Sidebar;
