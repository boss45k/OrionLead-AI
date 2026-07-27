/**
 * CollectionReport
 * ================
 * Displays a per-run quality breakdown after any collection completes.
 * Renders inside the AI Engine page once a task status includes a quality_report.
 *
 * Props:
 *   report  — quality_report dict from the task status API
 *   onClose — callback to dismiss the panel
 */

import React from 'react';
import { Card, Row, Col, Tag, Tooltip, Progress, Divider } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  ThunderboltOutlined,
  MailOutlined,
  DatabaseOutlined,
  WarningOutlined,
  CloseOutlined,
} from '@ant-design/icons';

// ── Helpers ──────────────────────────────────────────────────────────────────

const REASON_LABELS = {
  cdn_tracker_email:          'CDN/tracker email',
  url_as_name:                'URL as name',
  page_title_as_name:         'Page title as name',
  no_contact_method:          'No contact method',
  username_only:              'Username only',
  invalid_email:              'Invalid email',
  low_quality_social:         'Low quality social',
  fake_or_generated_email:    'Generated email',
  weak_business_signal:       'Weak business signal',
  low_completeness:           'Low completeness',
  missing_company:            'Missing company',
  missing_name:               'Missing name',
  generic_unverified_email_only: 'Generic email only',
  no_anchor_data:             'No anchor data',
  below_min_score:            'Below threshold',
  duplicate_email:            'Duplicate email',
  duplicate_name_company:     'Duplicate lead',
  duplicate_domain:           'Duplicate domain',
  no_substance:               'No substance',
  slug_as_name:               'Slug as name',
  single_word_name:           'Single-word name',
  evaluation_error:           'Evaluation error',
};

function humanReason(key) {
  return REASON_LABELS[key] || key.replace(/_/g, ' ');
}

function pct(n, total) {
  if (!total) return 0;
  return Math.round((n / total) * 100);
}

// ── Stat tile ─────────────────────────────────────────────────────────────────

function StatTile({ icon, label, value, color, note }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.04)',
      borderRadius: 8,
      padding: '12px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      minWidth: 110,
      flex: 1,
    }}>
      <div style={{ color: '#64748b', fontSize: 11, display: 'flex', alignItems: 'center', gap: 6 }}>
        {icon}
        {label}
      </div>
      <div style={{ color, fontSize: 22, fontWeight: 700, lineHeight: 1 }}>
        {value ?? '—'}
      </div>
      {note && <div style={{ color: '#475569', fontSize: 10 }}>{note}</div>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function CollectionReport({ report, onClose }) {
  if (!report) return null;

  const raw         = report.raw_candidates        ?? 0;
  const enriched    = report.enriched_candidates    ?? 0;
  const saved       = report.saved                  ?? 0;
  const rejected    = report.rejected               ?? 0;
  const duplicates  = report.duplicates             ?? 0;
  const avgScore    = report.average_quality_score  ?? 0;
  const verified    = report.email_breakdown?.verified_personal ?? 0;
  const intentCount = report.intent_detected        ?? 0;
  const cacheHits   = report.cache_hits             ?? 0;

  const rejectionReasons = report.rejection_reasons || {};
  const topSources       = report.top_sources        || {};
  const apiCalls         = report.api_calls_made     || {};

  const topReasons = Object.entries(rejectionReasons)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);

  const topSourcesList = Object.entries(topSources)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  const saveRate = pct(saved, raw);

  return (
    <Card
      size="small"
      style={{
        background: 'rgba(15,23,42,0.85)',
        border: '1px solid rgba(6,182,212,0.25)',
        borderRadius: 10,
        marginTop: 16,
      }}
      styles={{ body: { padding: 16 } }}
      title={
        <span style={{ color: '#e2e8f0', fontSize: 13, fontWeight: 600 }}>
          <DatabaseOutlined style={{ marginRight: 8, color: '#06b6d4' }} />
          Collection Quality Report
        </span>
      }
      extra={
        onClose && (
          <CloseOutlined
            style={{ color: '#64748b', cursor: 'pointer' }}
            onClick={onClose}
          />
        )
      }
    >
      {/* ── Top stats ── */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        <StatTile
          icon={<DatabaseOutlined />}
          label="Discovered"
          value={raw}
          color="#94a3b8"
        />
        <StatTile
          icon={<ThunderboltOutlined />}
          label="Enriched"
          value={enriched}
          color="#06b6d4"
          note={cacheHits > 0 ? `${cacheHits} from cache` : null}
        />
        <StatTile
          icon={<CheckCircleOutlined />}
          label="Saved"
          value={saved}
          color="#22c55e"
          note={`${saveRate}% save rate`}
        />
        <StatTile
          icon={<CloseCircleOutlined />}
          label="Rejected"
          value={rejected}
          color="#ef4444"
        />
        <StatTile
          icon={<CopyOutlined />}
          label="Duplicates"
          value={duplicates}
          color="#f59e0b"
        />
        <StatTile
          icon={<MailOutlined />}
          label="Verified emails"
          value={verified}
          color="#a78bfa"
        />
        <StatTile
          icon={<ThunderboltOutlined />}
          label="Intent detected"
          value={intentCount}
          color="#fb923c"
        />
      </div>

      {/* ── Quality score bar ── */}
      {avgScore > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ color: '#94a3b8', fontSize: 11 }}>Avg quality score</span>
            <span style={{ color: '#e2e8f0', fontSize: 11, fontWeight: 600 }}>
              {avgScore}/100
            </span>
          </div>
          <Progress
            percent={avgScore}
            size="small"
            showInfo={false}
            strokeColor={avgScore >= 60 ? '#22c55e' : avgScore >= 40 ? '#f59e0b' : '#ef4444'}
            trailColor="rgba(255,255,255,0.08)"
          />
        </div>
      )}

      <Divider style={{ borderColor: 'rgba(255,255,255,0.07)', margin: '12px 0' }} />

      <Row gutter={16}>
        {/* ── Rejection reasons ── */}
        {topReasons.length > 0 && (
          <Col xs={24} sm={12}>
            <div style={{ color: '#64748b', fontSize: 11, marginBottom: 8, fontWeight: 600 }}>
              <WarningOutlined style={{ marginRight: 4, color: '#ef4444' }} />
              TOP REJECTION REASONS
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {topReasons.map(([reason, count]) => (
                <div key={reason} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{
                    flex: 1,
                    background: 'rgba(239,68,68,0.12)',
                    borderRadius: 4,
                    overflow: 'hidden',
                    height: 20,
                    position: 'relative',
                  }}>
                    <div style={{
                      position: 'absolute',
                      left: 0, top: 0, bottom: 0,
                      width: `${pct(count, rejected || 1)}%`,
                      background: 'rgba(239,68,68,0.3)',
                      borderRadius: 4,
                    }} />
                    <span style={{
                      position: 'absolute',
                      left: 8,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      fontSize: 10,
                      color: '#cbd5e1',
                      whiteSpace: 'nowrap',
                    }}>
                      {humanReason(reason)}
                    </span>
                  </div>
                  <Tag style={{
                    minWidth: 28,
                    textAlign: 'center',
                    background: 'rgba(239,68,68,0.15)',
                    border: 'none',
                    color: '#fca5a5',
                    fontSize: 10,
                  }}>
                    {count}
                  </Tag>
                </div>
              ))}
            </div>
          </Col>
        )}

        {/* ── Top sources ── */}
        {topSourcesList.length > 0 && (
          <Col xs={24} sm={12}>
            <div style={{ color: '#64748b', fontSize: 11, marginBottom: 8, fontWeight: 600 }}>
              <CheckCircleOutlined style={{ marginRight: 4, color: '#22c55e' }} />
              TOP SOURCES
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {topSourcesList.map(([src, count]) => (
                <div key={src} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{
                    flex: 1,
                    background: 'rgba(34,197,94,0.1)',
                    borderRadius: 4,
                    overflow: 'hidden',
                    height: 20,
                    position: 'relative',
                  }}>
                    <div style={{
                      position: 'absolute',
                      left: 0, top: 0, bottom: 0,
                      width: `${pct(count, saved || 1)}%`,
                      background: 'rgba(34,197,94,0.25)',
                      borderRadius: 4,
                    }} />
                    <span style={{
                      position: 'absolute',
                      left: 8,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      fontSize: 10,
                      color: '#cbd5e1',
                      whiteSpace: 'nowrap',
                    }}>
                      {src}
                    </span>
                  </div>
                  <Tag style={{
                    minWidth: 28,
                    textAlign: 'center',
                    background: 'rgba(34,197,94,0.15)',
                    border: 'none',
                    color: '#86efac',
                    fontSize: 10,
                  }}>
                    {count}
                  </Tag>
                </div>
              ))}
            </div>
          </Col>
        )}
      </Row>

      {/* ── API calls ── */}
      {Object.keys(apiCalls).length > 0 && (
        <>
          <Divider style={{ borderColor: 'rgba(255,255,255,0.07)', margin: '12px 0' }} />
          <div style={{ color: '#64748b', fontSize: 11, marginBottom: 6, fontWeight: 600 }}>
            API CALLS MADE
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {Object.entries(apiCalls).map(([api, count]) => (
              <Tooltip key={api} title={`${count} ${api} calls`}>
                <Tag style={{
                  background: 'rgba(6,182,212,0.1)',
                  border: '1px solid rgba(6,182,212,0.2)',
                  color: '#7dd3fc',
                  fontSize: 10,
                }}>
                  {api}: {count}
                </Tag>
              </Tooltip>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
