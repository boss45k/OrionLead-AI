import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Spin, message } from 'antd';
import { apiWithFallback } from '../services/api';

const GOOGLE_REDIRECT_URI = window.location.origin + '/auth/google/callback';

const GoogleCallback = ({ onLoginSuccess }) => {
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const exchanged = useRef(false);

  useEffect(() => {
    if (exchanged.current) return;
    exchanged.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const errorParam = params.get('error');

    if (errorParam) {
      setError('Google sign-in was cancelled');
      message.error('Google sign-in was cancelled');
      setTimeout(() => navigate('/'), 2000);
      return;
    }

    if (!code) {
      setError('No authorization code received');
      message.error('No authorization code received');
      setTimeout(() => navigate('/'), 2000);
      return;
    }

    // Exchange the code with our backend
    apiWithFallback('/auth/google', 'post', { code, redirect_uri: GOOGLE_REDIRECT_URI })
      .then((res) => {
        const { token, user, expires_in } = res.data;
        localStorage.setItem('authToken', token);
        localStorage.setItem('tokenExpiry', (Date.now() + (expires_in || 86400) * 1000).toString());
        localStorage.setItem('user', JSON.stringify(user));
        localStorage.setItem('userRole', user.role || 'user');
        message.success(`Welcome${user.full_name ? ', ' + user.full_name : ''}!`);
        onLoginSuccess();
      })
      .catch((err) => {
        const msg = err?.response?.data?.message || 'Google sign-in failed';
        setError(msg);
        message.error(msg);
        setTimeout(() => navigate('/'), 3000);
      });
  }, [navigate, onLoginSuccess]);

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
      minHeight: '100vh', background: '#0a0e1a', color: '#e2e8f0',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* background orbs */}
      <div style={{
        position: 'absolute', top: '-20%', left: '-10%', width: 500, height: 500,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(99,102,241,0.08) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', bottom: '-15%', right: '-5%', width: 400, height: 400,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(139,92,246,0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <div style={{
        position: 'relative', zIndex: 1, textAlign: 'center',
        background: 'rgba(15,23,42,0.85)', backdropFilter: 'blur(20px)',
        border: '1px solid rgba(99,102,241,0.12)', borderRadius: 20,
        padding: '40px 48px', minWidth: 320,
      }}>
        {error ? (
          <>
            <div style={{
              width: 56, height: 56, borderRadius: '50%', margin: '0 auto 20px',
              background: 'rgba(239,68,68,0.12)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
                  stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <p style={{ fontSize: 15, fontWeight: 600, color: '#f87171', margin: '0 0 8px' }}>{error}</p>
            <p style={{ color: '#475569', fontSize: 13, margin: 0 }}>Redirecting to login...</p>
          </>
        ) : (
          <>
            <div style={{ position: 'relative', width: 48, height: 48, margin: '0 auto 20px' }}>
              <Spin size="large" />
            </div>
            <p style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0', margin: '0 0 6px' }}>
              Signing in with Google
            </p>
            <p style={{ color: '#475569', fontSize: 13, margin: 0 }}>Verifying your account...</p>
          </>
        )}
      </div>
    </div>
  );
};

export default GoogleCallback;
