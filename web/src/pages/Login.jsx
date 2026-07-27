import { useState, useContext, useEffect, useRef, useCallback } from 'react';
import { Card, Form, Input, Button, message, Divider, Alert } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, BankOutlined, ExclamationCircleFilled } from '@ant-design/icons';
import api from '../services/api';
import { ThemeContext } from '../context/ThemeContext';

const OTP_LENGTH  = 6;
const RESEND_SECS = 60;

// Inject keyframes once
if (typeof document !== 'undefined' && !document.getElementById('_shake_kf')) {
  const s = document.createElement('style');
  s.id = '_shake_kf';
  s.textContent = `
    @keyframes _shake {
      0%,100%{transform:translateX(0)}
      15%{transform:translateX(-6px)}
      30%{transform:translateX(6px)}
      45%{transform:translateX(-5px)}
      60%{transform:translateX(5px)}
      75%{transform:translateX(-3px)}
      90%{transform:translateX(3px)}
    }
    ._shake { animation: _shake 0.42s cubic-bezier(.36,.07,.19,.97) both; }

    @keyframes _bgGrad {
      0%,100% { background-position: 0% 50%; }
      50%     { background-position: 100% 50%; }
    }
    @keyframes _cardIn {
      from { opacity:0; transform:translateY(24px) scale(0.97); }
      to   { opacity:1; transform:translateY(0) scale(1); }
    }
    @keyframes _logoGlow {
      0%,100% { box-shadow: 0 8px 32px rgba(99,102,241,0.35), 0 2px 8px rgba(99,102,241,0.2); }
      50%     { box-shadow: 0 8px 52px rgba(99,102,241,0.65), 0 0 0 8px rgba(99,102,241,0.09); }
    }
    ._card-in  { animation: _cardIn 0.52s cubic-bezier(0.16,1,0.3,1) both; }
    ._logo-glow { animation: _logoGlow 3.2s ease-in-out infinite; }
    ._focus-ring .ant-input-affix-wrapper { transition: box-shadow 0.2s ease, border-color 0.2s ease !important; }
    ._focus-ring .ant-input-affix-wrapper:focus-within,
    ._focus-ring .ant-input-affix-wrapper-focused { box-shadow: 0 0 0 3px rgba(99,102,241,0.2) !important; border-color: #6366f1 !important; }
    @keyframes _btnGlow {
      0%,100% { box-shadow: 0 0 10px 2px rgba(99,102,241,0.45), 0 0 24px 4px rgba(139,92,246,0.25), 0 4px 14px rgba(99,102,241,0.35); }
      50%     { box-shadow: 0 0 18px 5px rgba(99,102,241,0.70), 0 0 40px 8px rgba(139,92,246,0.40), 0 6px 20px rgba(99,102,241,0.55); }
    }
    @keyframes _btnShimmer {
      0%   { transform: translateX(-120%) skewX(-20deg); }
      100% { transform: translateX(320%)  skewX(-20deg); }
    }
    ._btn-anim {
      position: relative !important;
      overflow: hidden !important;
      animation: _btnGlow 2.4s ease-in-out infinite !important;
      transition: transform 0.18s ease !important;
    }
    ._btn-anim::before {
      content: '';
      position: absolute;
      top: -10%; left: 0;
      width: 38%; height: 120%;
      background: linear-gradient(105deg, transparent 20%, rgba(255,255,255,0.32) 50%, transparent 80%);
      animation: _btnShimmer 2.2s ease-in-out infinite;
      pointer-events: none;
    }
    ._btn-anim:not([disabled]):hover {
      transform: translateY(-2px) scale(1.015) !important;
      animation: none !important;
      box-shadow: 0 0 26px 8px rgba(99,102,241,0.75), 0 0 52px 12px rgba(139,92,246,0.45), 0 8px 24px rgba(99,102,241,0.6) !important;
    }
    ._btn-anim:not([disabled]):hover::before { animation: none !important; opacity: 0; }
    ._btn-anim:not([disabled]):active { transform: translateY(0px) scale(0.99) !important; }
    @keyframes _starTwinkle {
      0%,100% { opacity:0.3; transform:scale(1); }
      50%     { opacity:1;   transform:scale(1.8); }
    }
    @keyframes _starDrift {
      0%   { transform:translateY(0px) scale(1); opacity:0.7; }
      100% { transform:translateY(-110px) scale(0.4); opacity:0; }
    }
    @keyframes _oCW65  {0%{transform:rotate(0deg)    translateX(65px)  rotate(0deg)}   100%{transform:rotate(360deg)   translateX(65px)  rotate(-360deg)}}
    @keyframes _oCW130 {0%{transform:rotate(0deg)    translateX(130px) rotate(0deg)}   100%{transform:rotate(360deg)   translateX(130px) rotate(-360deg)}}
    @keyframes _oCW230 {0%{transform:rotate(0deg)    translateX(230px) rotate(0deg)}   100%{transform:rotate(360deg)   translateX(230px) rotate(-360deg)}}
    @keyframes _oCW360 {0%{transform:rotate(0deg)    translateX(360px) rotate(0deg)}   100%{transform:rotate(360deg)   translateX(360px) rotate(-360deg)}}
    @keyframes _oCW510 {0%{transform:rotate(0deg)    translateX(510px) rotate(0deg)}   100%{transform:rotate(360deg)   translateX(510px) rotate(-360deg)}}
    @keyframes _oCCW230{0%{transform:rotate(0deg)    translateX(230px) rotate(0deg)}   100%{transform:rotate(-360deg)  translateX(230px) rotate(360deg)}}
    @keyframes _oCCW360{0%{transform:rotate(0deg)    translateX(360px) rotate(0deg)}   100%{transform:rotate(-360deg)  translateX(360px) rotate(360deg)}}
    @keyframes _oCCW510{0%{transform:rotate(0deg)    translateX(510px) rotate(0deg)}   100%{transform:rotate(-360deg)  translateX(510px) rotate(360deg)}}

    @keyframes _formSlideInRight {
      from { opacity:0; transform:translateX(32px) scale(0.98); }
      to   { opacity:1; transform:translateX(0)    scale(1); }
    }
    @keyframes _formSlideInLeft {
      from { opacity:0; transform:translateX(-32px) scale(0.98); }
      to   { opacity:1; transform:translateX(0)     scale(1); }
    }
    @keyframes _fieldFloat {
      from { opacity:0; transform:translateY(14px); }
      to   { opacity:1; transform:translateY(0); }
    }
    @keyframes _cardBorderPulse {
      0%,100% { box-shadow: 0 0 0 0px rgba(99,102,241,0); }
      50%     { box-shadow: 0 0 0 6px rgba(99,102,241,0.07), 0 0 50px rgba(99,102,241,0.04); }
    }
    @keyframes _tabBounce {
      0%   { transform:scaleX(0.8) scaleY(0.9); }
      60%  { transform:scaleX(1.04) scaleY(1.02); }
      100% { transform:scaleX(1) scaleY(1); }
    }
    ._slide-in-right { animation: _formSlideInRight 0.38s cubic-bezier(0.16,1,0.3,1) both; }
    ._slide-in-left  { animation: _formSlideInLeft  0.38s cubic-bezier(0.16,1,0.3,1) both; }
    ._field-f1 { animation: _fieldFloat 0.32s ease 0.04s both; }
    ._field-f2 { animation: _fieldFloat 0.32s ease 0.10s both; }
    ._field-f3 { animation: _fieldFloat 0.32s ease 0.16s both; }
    ._field-f4 { animation: _fieldFloat 0.32s ease 0.22s both; }
    ._field-f5 { animation: _fieldFloat 0.32s ease 0.28s both; }
    ._field-f6 { animation: _fieldFloat 0.32s ease 0.34s both; }
    ._card-border-pulse { animation: _cardBorderPulse 5s ease-in-out infinite; }
    ._tab-bounce { animation: _tabBounce 0.35s cubic-bezier(0.34,1.56,0.64,1) both; }
  `;
  document.head.appendChild(s);
}

const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';

function getPasswordStrength(pw) {
  if (!pw) return null;
  let score = 0;
  if (pw.length >= 8)           score++;
  if (pw.length >= 12)          score++;
  if (/[A-Z]/.test(pw))        score++;
  if (/[0-9]/.test(pw))        score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (score <= 1) return { level: 1, label: 'Weak',   color: '#ef4444' };
  if (score === 2) return { level: 2, label: 'Fair',   color: '#f97316' };
  if (score === 3) return { level: 3, label: 'Good',   color: '#eab308' };
  return             { level: 4, label: 'Strong', color: '#22c55e' };
}

const Login = ({ onLoginSuccess }) => {
  const { isDark } = useContext(ThemeContext);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState('login');
  const [pendingMessage, setPendingMessage] = useState('');
  const [loginForm] = Form.useForm();
  const [signupForm] = Form.useForm();
  const signupPassword = Form.useWatch('password', signupForm);
  const [loginError, setLoginError] = useState('');
  const [shaking, setShaking] = useState(false);
  const [googleHover, setGoogleHover] = useState(false);
  const [googleActive, setGoogleActive] = useState(false);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const [formKey, setFormKey] = useState(0);
  const [slideDir, setSlideDir] = useState('right');
  const cardRef = useRef(null);

  const handleCardMouseMove = useCallback((e) => {
    const card = cardRef.current;
    if (!card) return;
    const rect = card.getBoundingClientRect();
    const dx = (e.clientX - (rect.left + rect.width  / 2)) / (rect.width  / 2);
    const dy = (e.clientY - (rect.top  + rect.height / 2)) / (rect.height / 2);
    setTilt({ x: dy * -5, y: dx * 5 });
  }, []);

  const handleCardMouseLeave = useCallback(() => setTilt({ x: 0, y: 0 }), []);

  // ── OTP verification state ────────────────────────────────────────────────
  const [otpEmail, setOtpEmail]             = useState('');
  const [otpMasked, setOtpMasked]           = useState('');
  const [otpDigits, setOtpDigits]           = useState(Array(OTP_LENGTH).fill(''));
  const [otpLoading, setOtpLoading]         = useState(false);
  const [otpError, setOtpError]             = useState('');
  const [otpCountdown, setOtpCountdown]     = useState(RESEND_SECS);
  const [resendLoading, setResendLoading]   = useState(false);
  const otpRefs   = useRef([]);
  const timerRef  = useRef(null);

  const startCountdown = useCallback(() => {
    setOtpCountdown(RESEND_SECS);
    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setOtpCountdown(prev => {
        if (prev <= 1) { clearInterval(timerRef.current); return 0; }
        return prev - 1;
      });
    }, 1000);
  }, []);

  useEffect(() => {
    if (mode === 'verify_email') startCountdown();
    return () => clearInterval(timerRef.current);
  }, [mode, startCountdown]);

  const enterVerifyMode = (email, masked) => {
    setOtpEmail(email);
    setOtpMasked(masked || email);
    setOtpDigits(Array(OTP_LENGTH).fill(''));
    setOtpError('');
    setMode('verify_email');
  };

  const handleOtpChange = (val, idx) => {
    const clean = val.replace(/\D/g, '');
    // Paste of full code
    if (clean.length > 1) {
      const spread = clean.slice(0, OTP_LENGTH).split('');
      const next = Array(OTP_LENGTH).fill('');
      spread.forEach((d, i) => { if (idx + i < OTP_LENGTH) next[idx + i] = d; });
      setOtpDigits(next);
      const lastIdx = Math.min(idx + spread.length - 1, OTP_LENGTH - 1);
      otpRefs.current[lastIdx]?.focus();
      if (idx + spread.length >= OTP_LENGTH) submitOtp(next.join(''));
      return;
    }
    const next = [...otpDigits];
    next[idx] = clean;
    setOtpDigits(next);
    setOtpError('');
    if (clean && idx < OTP_LENGTH - 1) otpRefs.current[idx + 1]?.focus();
    if (clean && idx === OTP_LENGTH - 1) submitOtp([...next.slice(0, idx), clean].join(''));
  };

  const handleOtpKeyDown = (e, idx) => {
    if (e.key === 'Backspace' && !otpDigits[idx] && idx > 0) {
      otpRefs.current[idx - 1]?.focus();
    }
  };

  const submitOtp = async (code) => {
    if (code.length < OTP_LENGTH || otpLoading) return;
    setOtpLoading(true);
    setOtpError('');
    try {
      const resp = await api.post('/auth/verify-email', { email: otpEmail, code });
      if (resp.data?.status === 'pending_approval') {
        setPendingMessage(resp.data?.message || 'Email verified. Your account is awaiting admin approval.');
        setMode('pending');
      } else {
        message.success(resp.data?.message || 'Email verified! You can now sign in.');
        setMode('login');
      }
    } catch (err) {
      const msg = err?.response?.data?.message || err?.response?.data?.error || 'Verification failed.';
      setOtpError(msg);
      setOtpDigits(Array(OTP_LENGTH).fill(''));
      setTimeout(() => otpRefs.current[0]?.focus(), 50);
    } finally {
      setOtpLoading(false);
    }
  };

  const handleResendOtp = async () => {
    if (otpCountdown > 0 || resendLoading) return;
    setResendLoading(true);
    setOtpError('');
    try {
      await api.post('/auth/resend-otp', { email: otpEmail });
      setOtpDigits(Array(OTP_LENGTH).fill(''));
      startCountdown();
      message.success('A new code has been sent to your email.');
    } catch (err) {
      const msg = err?.response?.data?.message || 'Could not resend code. Please try again.';
      message.error(msg);
    } finally {
      setResendLoading(false);
    }
  };

  const triggerShake = () => {
    setShaking(true);
    setTimeout(() => setShaking(false), 450);
  };


  const handleGoogleSignIn = () => {
    if (!GOOGLE_CLIENT_ID) {
      message.info('Google Sign-In is not configured');
      return;
    }
    // Use standard OAuth redirect flow — avoids FedCM status check entirely.
    const redirectUri = window.location.origin + '/auth/google/callback';
    const params = new URLSearchParams({
      client_id:     GOOGLE_CLIENT_ID,
      redirect_uri:  redirectUri,
      response_type: 'code',
      scope:         'openid email profile',
      access_type:   'offline',
      prompt:        'select_account',
    });
    window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
  };

  const handleLogin = async (values) => {
    setLoginError('');
    setLoading(true);
    try {
      const response = await api.post('/auth/login', { email: values.email, password: values.password });
      const { token, user, expires_in, is_first_login } = response.data;
      localStorage.setItem('authToken', token);
      localStorage.setItem('tokenExpiry', (Date.now() + (expires_in || 86400) * 1000).toString());
      localStorage.setItem('user', JSON.stringify(user));
      localStorage.setItem('userRole', user.role || 'user');
      message.success(
        is_first_login
          ? `Welcome to OrionLead AI, ${user.full_name?.split(' ')[0] || 'there'} — let's find your first leads.`
          : 'Welcome back!'
      );
      onLoginSuccess();
    } catch (error) {
      triggerShake();
      const status = error.response?.status;
      const msg    = (error.response?.data?.message || '').toLowerCase();

      if (status === 401) {
        const isPending    = msg.includes('pending');
        const isDisabled   = msg.includes('deactivated');
        const isUnverified = msg.includes('verify your email');

        if (isUnverified) {
          enterVerifyMode(values.email.trim().toLowerCase(), null);
        } else if (isDisabled) {
          setLoginError('Your account has been deactivated. Please contact your administrator.');
        } else if (isPending) {
          setLoginError(error.response?.data?.message || 'Your account is pending admin approval. Please contact your administrator.');
        } else {
          loginForm.setFields([
            { name: 'email',    errors: [''] },
            { name: 'password', errors: ['Invalid email or password'] },
          ]);
        }
      } else if (status === 403) {
        setLoginError('Access denied. You do not have permission to sign in.');
      } else if (status === 429) {
        setLoginError('Too many attempts. Please wait a moment and try again.');
      } else if (!error.response) {
        setLoginError('Cannot reach the server. Check your connection and try again.');
      } else {
        setLoginError(error.response?.data?.message || 'Sign-in failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const [signupError, setSignupError] = useState('');

  const handleSignup = async (values) => {
    setSignupError('');
    setLoading(true);
    try {
      const resp = await api.post('/auth/register', {
        email: values.email,
        password: values.password,
        full_name: values.full_name,
        company: values.company || undefined,
      });
      signupForm.resetFields();
      if (resp.data?.status === 'verify_email') {
        enterVerifyMode(values.email.trim().toLowerCase(), resp.data.email);
      } else {
        setPendingMessage(resp.data?.message || "Your account has been created, but we could not deliver the verification email. An administrator will review and activate your account — you'll be able to sign in once approved.");
        setMode('pending');
      }
    } catch (error) {
      const raw = error?.response?.data?.message || error?.response?.data?.error || '';
      const status = error?.response?.status;
      let msg = raw || 'Registration failed. Please try again.';
      if (!error.response) {
        msg = 'Cannot reach the server. Check your connection and try again.';
      } else if (status === 429) {
        msg = 'Too many sign-up attempts. Please wait a moment and try again.';
      } else if (raw.toLowerCase().includes('already')) {
        msg = 'This email is already registered. Please sign in instead.';
      }
      setSignupError(msg);
    } finally {
      setLoading(false);
    }
  };

  // ── Theme-aware tokens ──────────────────────────────────────────
  const bgPage     = isDark
    ? 'linear-gradient(-45deg,#0a0e1a,#0f172a,#12102a,#091620)'
    : 'linear-gradient(-45deg,#f0f4f8,#edf0ff,#f4f0ff,#eef6ff)';
  const orb1Color  = isDark ? 'rgba(99,102,241,0.08)' : 'rgba(99,102,241,0.14)';
  const orb2Color  = isDark ? 'rgba(139,92,246,0.06)' : 'rgba(139,92,246,0.10)';
  const cardBg     = isDark ? 'rgba(15,23,42,0.85)' : 'rgba(255,255,255,0.95)';
  const cardBorder = isDark ? '1px solid rgba(99,102,241,0.08)' : '1px solid #e2e8f0';
  const tabBg      = isDark ? 'rgba(15,23,42,0.6)'   : '#f1f5f9';
  const tabBorder  = isDark ? '1px solid rgba(99,102,241,0.08)' : '1px solid #e2e8f0';
  const tabInactive = isDark ? '#64748b' : '#64748b';
  const titleColor  = isDark ? '#f1f5f9' : '#1e293b';
  const subtitleColor = isDark ? '#64748b' : '#64748b';
  const footerColor   = isDark ? '#475569' : '#94a3b8';
  const dividerColor  = isDark ? 'rgba(99,102,241,0.12)' : '#e2e8f0';
  const dividerTextColor = isDark ? '#475569' : '#94a3b8';
  const iconColor     = isDark ? '#64748b' : '#94a3b8';

  const inputStyle = {
    background: isDark ? 'rgba(15,23,42,0.6)' : '#ffffff',
    border: isDark ? '1px solid rgba(99,102,241,0.15)' : '1px solid #e2e8f0',
    borderRadius: 10,
    color: isDark ? '#e2e8f0' : '#1e293b',
    height: 44,
  };

  const googleBtnStyle = {
    width: '100%',
    height: 48,
    borderRadius: 12,
    fontSize: 14,
    fontWeight: 600,
    letterSpacing: '0.01em',
    cursor: 'pointer',
    border: 'none',
    outline: 'none',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    position: 'relative',
    overflow: 'hidden',
    transition: 'transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease',
    transform: googleActive ? 'scale(0.975)' : googleHover ? 'scale(1.012)' : 'scale(1)',
    ...(isDark ? {
      background: googleHover
        ? 'rgba(30,41,59,0.95)'
        : 'rgba(15,23,42,0.7)',
      boxShadow: googleHover
        ? '0 0 0 1px rgba(99,102,241,0.4), 0 4px 20px rgba(99,102,241,0.15)'
        : '0 0 0 1px rgba(99,102,241,0.12)',
      color: '#e2e8f0',
    } : {
      background: googleHover ? '#f8faff' : '#ffffff',
      boxShadow: googleHover
        ? '0 0 0 1.5px rgba(99,102,241,0.35), 0 4px 16px rgba(99,102,241,0.10)'
        : '0 0 0 1px #e2e8f0, 0 1px 4px rgba(0,0,0,0.06)',
      color: '#1e293b',
    }),
  };

  // r=orbit radius, s=dot size, odur=orbit period, dl=orbit delay, tdur=twinkle dur, tdl=twinkle delay
  const starData = [
    {r:65,  s:9,  odur:'4.5s', dl:'0s',     tdur:'2.8s', tdl:'0s'},
    {r:65,  s:7,  odur:'4.5s', dl:'1.5s',   tdur:'3.3s', tdl:'0.8s'},
    {r:65,  s:8,  odur:'4.5s', dl:'3.0s',   tdur:'2.5s', tdl:'1.4s'},
    {r:130, s:10, odur:'9s',   dl:'0s',     tdur:'3.6s', tdl:'0.3s'},
    {r:130, s:8,  odur:'9s',   dl:'2.25s',  tdur:'2.9s', tdl:'1.5s'},
    {r:130, s:11, odur:'9s',   dl:'4.5s',   tdur:'4.1s', tdl:'0.7s'},
    {r:130, s:7,  odur:'9s',   dl:'6.75s',  tdur:'3.2s', tdl:'2.0s'},
    {r:230, s:12, odur:'18s',  dl:'0s',     tdur:'4.2s', tdl:'0.5s'},
    {r:230, s:9,  odur:'18s',  dl:'3.6s',   tdur:'2.7s', tdl:'1.2s'},
    {r:230, s:10, odur:'18s',  dl:'7.2s',   tdur:'3.8s', tdl:'0s'},
    {r:230, s:8,  odur:'18s',  dl:'10.8s',  tdur:'3.0s', tdl:'1.8s', ccw:true},
    {r:230, s:11, odur:'18s',  dl:'14.4s',  tdur:'4.4s', tdl:'0.9s'},
    {r:360, s:14, odur:'30s',  dl:'0s',     tdur:'3.5s', tdl:'0.4s'},
    {r:360, s:10, odur:'30s',  dl:'5.0s',   tdur:'2.8s', tdl:'2.1s'},
    {r:360, s:12, odur:'30s',  dl:'10.0s',  tdur:'4.0s', tdl:'0.6s'},
    {r:360, s:8,  odur:'30s',  dl:'15.0s',  tdur:'3.3s', tdl:'1.3s', ccw:true},
    {r:360, s:13, odur:'30s',  dl:'20.0s',  tdur:'2.6s', tdl:'0.2s'},
    {r:360, s:9,  odur:'30s',  dl:'25.0s',  tdur:'4.5s', tdl:'1.7s'},
    {r:510, s:16, odur:'50s',  dl:'0s',     tdur:'3.9s', tdl:'0.8s'},
    {r:510, s:11, odur:'50s',  dl:'8.33s',  tdur:'2.5s', tdl:'0s'},
    {r:510, s:13, odur:'50s',  dl:'16.67s', tdur:'4.2s', tdl:'1.6s'},
    {r:510, s:9,  odur:'50s',  dl:'25.0s',  tdur:'3.1s', tdl:'2.4s', ccw:true},
    {r:510, s:15, odur:'50s',  dl:'33.33s', tdur:'2.8s', tdl:'0.5s'},
    {r:510, s:10, odur:'50s',  dl:'41.67s', tdur:'4.6s', tdl:'1.1s'},
  ];
  const starC = isDark ? 'rgba(190,200,255,' : 'rgba(109,40,217,';

  const oColors = isDark
    ? ['#a78bfa','#67e8f9','#f9a8d4','#86efac','#fde68a','#c4b5fd','#7dd3fc','#fbcfe8']
    : ['#7c3aed','#0284c7','#db2777','#047857','#b45309','#6d28d9','#0369a1','#be185d'];
  // r=orbit radius, s=dot size, ci=color index, dur=period, dl=delay, ccw=counter-clockwise
  const orbitItems = [
    {r:65,  s:8,  ci:5, dur:'3.5s',  dl:'0s'},
    {r:65,  s:7,  ci:3, dur:'3.5s',  dl:'1.75s'},
    {r:130, s:11, ci:0, dur:'7s',    dl:'0s'},
    {r:130, s:9,  ci:1, dur:'7s',    dl:'2.33s'},
    {r:130, s:10, ci:4, dur:'7s',    dl:'4.67s'},
    {r:230, s:13, ci:2, dur:'14s',   dl:'0s'},
    {r:230, s:11, ci:6, dur:'14s',   dl:'3.5s'},
    {r:230, s:12, ci:7, dur:'14s',   dl:'7s'},
    {r:230, s:9,  ci:3, dur:'14s',   dl:'10.5s', ccw:true},
    {r:360, s:16, ci:4, dur:'26s',   dl:'0s'},
    {r:360, s:12, ci:0, dur:'26s',   dl:'6.5s',  ccw:true},
    {r:360, s:14, ci:1, dur:'26s',   dl:'13s'},
    {r:360, s:10, ci:5, dur:'26s',   dl:'19.5s'},
    {r:510, s:18, ci:6, dur:'44s',   dl:'0s'},
    {r:510, s:13, ci:2, dur:'44s',   dl:'11s',   ccw:true},
    {r:510, s:15, ci:7, dur:'44s',   dl:'22s'},
    {r:510, s:11, ci:4, dur:'44s',   dl:'33s'},
  ];
  const orbitRingR = [65, 130, 230, 360, 510];
  const ringColor = isDark ? 'rgba(148,163,184,0.18)' : 'rgba(109,40,217,0.14)';

  return (
    <div className="_focus-ring" style={{
      display: 'flex', justifyContent: 'center', alignItems: 'center',
      minHeight: '100vh', background: bgPage,
      backgroundSize: '400% 400%',
      animation: '_bgGrad 16s ease infinite',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Background orbs */}
      <div style={{
        position: 'absolute', top: '-20%', left: '-10%', width: 500, height: 500,
        borderRadius: '50%',
        background: `radial-gradient(circle, ${orb1Color} 0%, transparent 70%)`,
        pointerEvents: 'none', transition: 'background 0.3s',
      }} />
      <div style={{
        position: 'absolute', bottom: '-15%', right: '-5%', width: 400, height: 400,
        borderRadius: '50%',
        background: `radial-gradient(circle, ${orb2Color} 0%, transparent 70%)`,
        pointerEvents: 'none', transition: 'background 0.3s',
      }} />

      {/* Orbital system — center at 50%/50% */}
      {/* Orbit ring trails */}
      {orbitRingR.map((r, i) => (
        <div key={`ring-${i}`} style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          width: r * 2, height: r * 2,
          borderRadius: '50%',
          border: `1.5px solid ${ringColor}`,
          pointerEvents: 'none',
        }} />
      ))}

      {/* Stars — each orbits on its ring via rotate(N)translateX(r)rotate(-N) */}
      {starData.map((st, i) => (
        <div key={`star-${i}`} style={{
          position: 'absolute', top: '50%', left: '50%',
          width: st.s, height: st.s,
          marginTop: -st.s / 2, marginLeft: -st.s / 2,
          borderRadius: '50%',
          background: `radial-gradient(circle, #fff 0%, ${starC}1.0) 25%, ${starC}0.5) 60%, transparent 100%)`,
          boxShadow: `0 0 ${st.s}px ${starC}0.9), 0 0 ${st.s * 3}px ${starC}0.5)`,
          animation: `_o${st.ccw ? 'CCW' : 'CW'}${st.r} ${st.odur} linear ${st.dl} infinite, _starTwinkle ${st.tdur} ease-in-out ${st.tdl} infinite`,
          pointerEvents: 'none',
        }} />
      ))}

      {/* Orbiting colored dots */}
      {orbitItems.map((o, i) => (
        <div key={`orb-${i}`} style={{
          position: 'absolute', top: '50%', left: '50%',
          width: o.s, height: o.s,
          marginTop: -o.s / 2, marginLeft: -o.s / 2,
          borderRadius: '50%',
          background: `radial-gradient(circle, #fff 0%, ${oColors[o.ci]} 35%, ${oColors[o.ci]}88 65%, transparent 100%)`,
          boxShadow: `0 0 ${o.s * 2}px ${oColors[o.ci]}, 0 0 ${o.s * 5}px ${oColors[o.ci]}bb`,
          animation: `_o${o.ccw ? 'CCW' : 'CW'}${o.r} ${o.dur} linear ${o.dl} infinite`,
          pointerEvents: 'none',
        }} />
      ))}

      <div
        ref={cardRef}
        className="_card-in"
        onMouseMove={handleCardMouseMove}
        onMouseLeave={handleCardMouseLeave}
        style={{
          width: 420, position: 'relative', zIndex: 1,
          transform: `perspective(1200px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg) translateZ(0)`,
          transition: tilt.x === 0 && tilt.y === 0
            ? 'transform 0.6s cubic-bezier(0.16,1,0.3,1)'
            : 'transform 0.1s linear',
          transformStyle: 'preserve-3d',
          willChange: 'transform',
        }}
      >
        {/* Brand */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div className="_logo-glow" style={{
            width: 64, height: 64, borderRadius: 20, margin: '0 auto 16px',
            background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 60%, #a78bfa 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="34" height="34" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
              <line x1="20" y1="13" x2="12" y2="27" stroke="white" strokeWidth="2" strokeOpacity="0.55" strokeLinecap="round"/>
              <line x1="20" y1="13" x2="28" y2="27" stroke="white" strokeWidth="2" strokeOpacity="0.55" strokeLinecap="round"/>
              <line x1="13" y1="30" x2="27" y2="30" stroke="white" strokeWidth="2" strokeOpacity="0.55" strokeLinecap="round"/>
              <circle cx="20" cy="9.5" r="4.5" fill="white"/>
              <circle cx="11" cy="30" r="4" fill="white" fillOpacity="0.9"/>
              <circle cx="29" cy="30" r="4" fill="white" fillOpacity="0.9"/>
            </svg>
          </div>
          <h1 style={{ fontSize: 30, fontWeight: 800, color: titleColor, margin: '0 0 5px', letterSpacing: '-0.03em', transition: 'color 0.3s' }}>OrionLead AI</h1>
          <p style={{ color: subtitleColor, fontSize: 13, margin: 0, fontWeight: 500, letterSpacing: '0.02em' }}>Intelligent Lead Platform</p>
        </div>

        <Card
          className="_card-border-pulse"
          style={{
            background: cardBg,
            border: cardBorder,
            borderRadius: 20,
            backdropFilter: 'blur(20px)',
            boxShadow: isDark
              ? '0 24px 80px rgba(0,0,0,0.45), 0 8px 32px rgba(99,102,241,0.08)'
              : '0 8px 40px rgba(0,0,0,0.10), 0 2px 8px rgba(0,0,0,0.06)',
            transition: 'background 0.3s, border-color 0.3s, box-shadow 0.3s',
          }}
          styles={{ body: { padding: '28px 32px' } }}
        >
          {/* Pending approval screen */}
          {mode === 'pending' && (
            <div style={{ textAlign: 'center', padding: '12px 0 20px' }}>
              <div style={{
                width: 64, height: 64, borderRadius: '50%', margin: '0 auto 16px',
                background: 'rgba(99,102,241,0.12)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28,
              }}>⏳</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: titleColor, marginBottom: 8 }}>
                Account Pending Approval
              </div>
              <div style={{ color: subtitleColor, fontSize: 13, lineHeight: 1.6, marginBottom: 20 }}>
                {pendingMessage || "Your account has been created, but we could not deliver the verification email. An administrator will review and activate your account — you'll be able to sign in once approved."}
              </div>
              <button
                onClick={() => setMode('login')}
                style={{
                  width: '100%', padding: '12px 0', border: 'none', cursor: 'pointer',
                  borderRadius: 12, fontSize: 14, fontWeight: 600,
                  background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', color: '#fff',
                }}
              >
                Back to Sign In
              </button>
            </div>
          )}

          {/* Email OTP verification screen */}
          {mode === 'verify_email' && (
            <div style={{ padding: '4px 0 8px' }}>
              <div style={{ textAlign: 'center', marginBottom: 24 }}>
                <div style={{
                  width: 60, height: 60, borderRadius: '50%', margin: '0 auto 14px',
                  background: 'rgba(99,102,241,0.12)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26,
                }}>✉️</div>
                <div style={{ fontSize: 17, fontWeight: 700, color: titleColor, marginBottom: 6 }}>
                  Verify your email
                </div>
                <div style={{ color: subtitleColor, fontSize: 13, lineHeight: 1.6 }}>
                  We sent a 6-digit code to<br />
                  <strong style={{ color: titleColor }}>{otpMasked || otpEmail}</strong>
                </div>
              </div>

              {/* 6 digit boxes */}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 16 }}>
                {otpDigits.map((d, i) => (
                  <input
                    key={i}
                    ref={el => { otpRefs.current[i] = el; }}
                    value={d}
                    onChange={e => handleOtpChange(e.target.value, i)}
                    onKeyDown={e => handleOtpKeyDown(e, i)}
                    maxLength={6}
                    style={{
                      width: 46, height: 56, textAlign: 'center',
                      fontSize: 24, fontWeight: 800,
                      borderRadius: 12,
                      border: otpError
                        ? '2px solid #ef4444'
                        : d ? '2px solid #6366f1' : `2px solid ${isDark ? 'rgba(99,102,241,0.2)' : '#e2e8f0'}`,
                      background: d
                        ? isDark ? 'rgba(99,102,241,0.12)' : 'rgba(99,102,241,0.06)'
                        : isDark ? 'rgba(15,23,42,0.6)' : '#fff',
                      color: titleColor,
                      outline: 'none',
                      transition: 'border-color 0.2s',
                    }}
                    disabled={otpLoading}
                  />
                ))}
              </div>

              {otpError && (
                <div style={{
                  color: '#ef4444', fontSize: 13, textAlign: 'center',
                  marginBottom: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                }}>
                  <ExclamationCircleFilled style={{ fontSize: 13 }} />
                  {otpError}
                </div>
              )}

              <Button
                type="primary"
                block
                loading={otpLoading}
                disabled={otpDigits.join('').length < OTP_LENGTH}
                onClick={() => submitOtp(otpDigits.join(''))}
                style={{
                  height: 46, fontSize: 15, fontWeight: 600,
                  background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                  border: 'none', borderRadius: 12, marginBottom: 16,
                }}
              >
                Verify Email
              </Button>

              <div style={{ textAlign: 'center', fontSize: 13, color: subtitleColor, marginBottom: 12 }}>
                Didn't receive a code?{' '}
                {otpCountdown > 0
                  ? <span style={{ color: subtitleColor }}>Resend in {otpCountdown}s</span>
                  : (
                    <button
                      onClick={handleResendOtp}
                      disabled={resendLoading}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        color: '#6366f1', fontWeight: 600, fontSize: 13, padding: 0,
                      }}
                    >
                      {resendLoading ? 'Sending…' : 'Resend code'}
                    </button>
                  )
                }
              </div>

              <div style={{ textAlign: 'center' }}>
                <button
                  onClick={() => setMode('signup')}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: subtitleColor, fontSize: 12, padding: 0,
                  }}
                >
                  ← Change email address
                </button>
              </div>
            </div>
          )}

          {/* Tab switcher — only show on login/signup modes */}
          {mode !== 'pending' && mode !== 'verify_email' && (
          <div style={{
            display: 'flex', marginBottom: 24, borderRadius: 12,
            background: tabBg, padding: 4, border: tabBorder,
            transition: 'background 0.3s, border-color 0.3s',
          }}>
            {['login', 'signup'].map((m) => (
              <button
                key={m}
                onClick={() => {
                  if (m !== mode) {
                    setSlideDir(m === 'signup' ? 'right' : 'left');
                    setFormKey(k => k + 1);
                    setMode(m);
                  }
                }}
                style={{
                  flex: 1, padding: '10px 0', border: 'none', cursor: 'pointer',
                  borderRadius: 10, fontSize: 14, fontWeight: 600,
                  transition: 'all 0.25s cubic-bezier(0.34,1.56,0.64,1)',
                  background: mode === m ? 'linear-gradient(135deg, #6366f1, #8b5cf6)' : 'transparent',
                  color: mode === m ? '#fff' : tabInactive,
                  boxShadow: mode === m ? '0 4px 14px rgba(99,102,241,0.45)' : 'none',
                  transform: mode === m ? 'scale(1.03)' : 'scale(1)',
                  letterSpacing: mode === m ? '0.01em' : '0',
                }}
              >
                {m === 'login' ? 'Sign In' : 'Create Account'}
              </button>
            ))}
          </div>
          )}

          {/* LOGIN FORM */}
          {mode === 'login' && (
            <div
              key={`login-${formKey}`}
              className={shaking ? '_shake' : slideDir === 'left' ? '_slide-in-left' : '_slide-in-right'}
            >
              {loginError && (
                <Alert
                  type="error"
                  message={loginError}
                  showIcon
                  icon={<ExclamationCircleFilled />}
                  style={{
                    marginBottom: 16, borderRadius: 10, fontSize: 13,
                    background: isDark ? 'rgba(239,68,68,0.10)' : '#fff1f0',
                    border: isDark ? '1px solid rgba(239,68,68,0.25)' : '1px solid #ffa39e',
                    color: isDark ? '#fca5a5' : '#cf1322',
                  }}
                  closable
                  onClose={() => setLoginError('')}
                />
              )}
              <Form
                form={loginForm}
                onFinish={handleLogin}
                layout="vertical"
                size="large"
                requiredMark={false}
                onValuesChange={() => {
                  setLoginError('');
                  loginForm.setFields([
                    { name: 'email',    errors: [] },
                    { name: 'password', errors: [] },
                  ]);
                }}
              >
                <Form.Item
                  name="email"
                  className="_field-f1"
                  style={{ marginBottom: 16 }}
                  rules={[
                    { required: true, message: 'Email is required' },
                    { type: 'email',   message: 'Enter a valid email address' },
                  ]}
                >
                  <Input
                    prefix={<MailOutlined style={{ color: iconColor }} />}
                    placeholder="Email address"
                    autoComplete="email"
                    style={inputStyle}
                  />
                </Form.Item>
                <Form.Item
                  name="password"
                  className="_field-f2"
                  style={{ marginBottom: 20 }}
                  rules={[{ required: true, message: 'Password is required' }]}
                >
                  <Input.Password
                    prefix={<LockOutlined style={{ color: iconColor }} />}
                    placeholder="Password"
                    autoComplete="current-password"
                    style={inputStyle}
                  />
                </Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  loading={loading}
                  className="_btn-anim _field-f3"
                  style={{
                    height: 46, fontSize: 15, fontWeight: 600,
                    background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                    border: 'none', borderRadius: 12,
                  }}
                >
                  Sign In
                </Button>
              </Form>
            </div>
          )}

          {/* SIGNUP FORM */}
          {mode === 'signup' && (
            <div key={`signup-${formKey}`} className={slideDir === 'right' ? '_slide-in-right' : '_slide-in-left'}>
            <Form form={signupForm} onFinish={handleSignup} layout="vertical" size="large" requiredMark={false}
              onValuesChange={() => setSignupError('')}>
              {signupError && (
                <Alert
                  type="error"
                  message={signupError}
                  showIcon
                  icon={<ExclamationCircleFilled />}
                  style={{
                    marginBottom: 16, borderRadius: 10, fontSize: 13,
                    background: isDark ? 'rgba(239,68,68,0.10)' : '#fff1f0',
                    border: isDark ? '1px solid rgba(239,68,68,0.25)' : '1px solid #ffa39e',
                    color: isDark ? '#fca5a5' : '#cf1322',
                  }}
                  closable
                  onClose={() => setSignupError('')}
                />
              )}
              <Form.Item name="full_name"
                className="_field-f1"
                rules={[{ required: true, min: 2, message: 'Full name (min 2 characters)' }]}
                style={{ marginBottom: 14 }}>
                <Input prefix={<UserOutlined style={{ color: iconColor }} />}
                  placeholder="Full name" autoComplete="name" style={inputStyle} />
              </Form.Item>
              <Form.Item name="email"
                className="_field-f2"
                rules={[{ required: true, type: 'email', message: 'Enter a valid email' }]}
                style={{ marginBottom: 14 }}>
                <Input prefix={<MailOutlined style={{ color: iconColor }} />}
                  placeholder="Email address" autoComplete="email" style={inputStyle} />
              </Form.Item>
              <Form.Item name="password"
                className="_field-f3"
                rules={[{ required: true, min: 8, message: 'Password (min 8 characters)' }]}
                style={{ marginBottom: signupPassword ? 6 : 14 }}>
                <Input.Password prefix={<LockOutlined style={{ color: iconColor }} />}
                  placeholder="Password" autoComplete="new-password" style={inputStyle} />
              </Form.Item>
              {(() => {
                const s = getPasswordStrength(signupPassword);
                if (!s) return null;
                return (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                    <div style={{ display: 'flex', gap: 4, flex: 1 }}>
                      {[1,2,3,4].map(i => (
                        <div key={i} style={{
                          flex: 1, height: 4, borderRadius: 4,
                          backgroundColor: i <= s.level ? s.color : (isDark ? '#374151' : '#e5e7eb'),
                          transition: 'background-color 0.2s',
                        }} />
                      ))}
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: s.color, minWidth: 38, textAlign: 'right' }}>
                      {s.label}
                    </span>
                  </div>
                );
              })()}
              <Form.Item name="confirm" dependencies={['password']}
                className="_field-f4"
                rules={[
                  { required: true, message: 'Confirm your password' },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue('password') === value) return Promise.resolve();
                      return Promise.reject(new Error('Passwords do not match'));
                    },
                  }),
                ]}
                style={{ marginBottom: 14 }}>
                <Input.Password prefix={<LockOutlined style={{ color: iconColor }} />}
                  placeholder="Confirm password" autoComplete="new-password" style={inputStyle} />
              </Form.Item>
              <Form.Item name="company" className="_field-f5" style={{ marginBottom: 20 }}>
                <Input prefix={<BankOutlined style={{ color: iconColor }} />}
                  placeholder="Company (optional)" autoComplete="organization" style={inputStyle} />
              </Form.Item>
              <Button type="primary" htmlType="submit" block loading={loading}
                className="_btn-anim _field-f6"
                style={{
                  height: 46, fontSize: 15, fontWeight: 600,
                  background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                  border: 'none', borderRadius: 12,
                }}>
                Create Account
              </Button>
            </Form>
            </div>
          )}

          {mode !== 'pending' && mode !== 'verify_email' && <Divider style={{ borderColor: dividerColor, margin: '20px 0', color: dividerTextColor, fontSize: 12 }}>
            or continue with
          </Divider>}

          {mode !== 'pending' && mode !== 'verify_email' && (
            <button
              onClick={handleGoogleSignIn}
              onMouseEnter={() => setGoogleHover(true)}
              onMouseLeave={() => { setGoogleHover(false); setGoogleActive(false); }}
              onMouseDown={() => setGoogleActive(true)}
              onMouseUp={() => setGoogleActive(false)}
              style={googleBtnStyle}
            >
              {/* shimmer sweep on hover */}
              <span style={{
                position: 'absolute', inset: 0, borderRadius: 12,
                background: 'linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.07) 50%, transparent 60%)',
                backgroundSize: '200% 100%',
                backgroundPosition: googleHover ? '0% 0%' : '200% 0%',
                transition: 'background-position 0.5s ease',
                pointerEvents: 'none',
              }} />
              <svg width="18" height="18" viewBox="0 0 48 48" style={{ flexShrink: 0, position: 'relative', zIndex: 1 }}>
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
              </svg>
              <span style={{ position: 'relative', zIndex: 1 }}>Continue with Google</span>
            </button>
          )}

          <div style={{ textAlign: 'center', marginTop: 20 }}>
            <span style={{ color: footerColor, fontSize: 12 }}>
              Secure AI-powered lead management
            </span>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default Login;
