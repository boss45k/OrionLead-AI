import React from 'react';
import { Button } from 'antd';
import { useNavigate } from 'react-router-dom';
import { HomeOutlined, ArrowLeftOutlined } from '@ant-design/icons';

const NotFound = () => {
  const navigate = useNavigate();

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '80vh',
      padding: '40px 24px',
      textAlign: 'center',
    }}>
      {/* Decorative number */}
      <div style={{
        fontSize: 120,
        fontWeight: 800,
        lineHeight: 1,
        background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        backgroundClip: 'text',
        marginBottom: 8,
        letterSpacing: -4,
      }}>
        404
      </div>

      <h2 style={{
        fontSize: 22,
        fontWeight: 700,
        color: 'var(--text-stat)',
        margin: '0 0 12px',
      }}>
        Page Not Found
      </h2>

      <p style={{
        color: 'var(--text-muted)',
        fontSize: 14,
        maxWidth: 360,
        margin: '0 0 32px',
        lineHeight: 1.6,
      }}>
        The page you're looking for doesn't exist or you don't have permission to access it.
      </p>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
        <Button
          type="primary"
          icon={<HomeOutlined />}
          size="large"
          onClick={() => navigate('/')}
          style={{
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            border: 'none',
            fontWeight: 600,
            borderRadius: 10,
          }}
        >
          Back to Dashboard
        </Button>
        <Button
          icon={<ArrowLeftOutlined />}
          size="large"
          onClick={() => navigate(-1)}
          style={{ borderRadius: 10 }}
        >
          Go Back
        </Button>
      </div>
    </div>
  );
};

export default NotFound;
