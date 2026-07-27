/**
 * PipelineVisualizer
 * ==================
 * Shows all 10 collection pipeline stages with live stage highlighting.
 *
 * Props:
 *   currentStage  int     — which stage is active (1-10), or 0 for not started
 *   isDone        bool    — true when collection finished successfully
 *   strategy      object  — CollectionStrategy from AI Orchestrator
 *   qualityReport object  — quality_report from task status (post-run counts)
 */

import React from 'react';
import { Tag, Tooltip, Divider } from 'antd';
import {
  RobotOutlined,
  SearchOutlined,
  SwapOutlined,
  FilterOutlined,
  ApiOutlined,
  MailOutlined,
  SafetyCertificateOutlined,
  LineChartOutlined,
  BulbOutlined,
  DatabaseOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';

// ── Stage definitions ─────────────────────────────────────────────────────────

const STAGES = [
  {
    id: 1,
    name: 'AI Orchestrator',
    label: 'Gemini / Groq / Rules',
    desc: 'Analyzes query → intent, sources, DM titles, Google queries, rejection signals',
    icon: <RobotOutlined />,
    color: '#a78bfa',
  },
  {
    id: 2,
    name: 'Discovery',
    label: 'Apollo · Serper LinkedIn · Hunter · Google Places',
    desc: 'Collects raw candidates from AI-selected sources using strategy-guided queries',
    icon: <SearchOutlined />,
    color: '#06b6d4',
  },
  {
    id: 3,
    name: 'Normalization + Dedup',
    label: 'In-memory session dedup',
    desc: 'Standardize fields, extract domain, deduplicate by email + domain',
    icon: <SwapOutlined />,
    color: '#3b82f6',
  },
  {
    id: 4,
    name: 'Pre-filter + Strategy Check',
    label: 'No API cost',
    desc: 'CDN/tracker emails, URL-as-name, rejection signals from AI strategy → DROP',
    icon: <FilterOutlined />,
    color: '#f59e0b',
  },
  {
    id: 5,
    name: 'Enrichment',
    label: 'Conditional: pre-score ≥ 40',
    desc: 'Hunter email-finder, contact page scrape, lead_fallback strategies',
    icon: <ApiOutlined />,
    color: '#22c55e',
  },
  {
    id: 6,
    name: 'Verification',
    label: 'ZeroBounce SMTP',
    desc: 'valid → email_verified=True · invalid/spamtrap → email_verified=False',
    icon: <MailOutlined />,
    color: '#10b981',
  },
  {
    id: 7,
    name: 'Quality Gate',
    label: '0-100 scoring',
    desc: 'Email type, phone, company, name, non-B2B filter, source reliability → REJECT if < 30',
    icon: <SafetyCertificateOutlined />,
    color: '#f59e0b',
  },
  {
    id: 8,
    name: 'ML Qualification',
    label: 'XGBoost 34-feature model',
    desc: 'combined = quality×0.6 + ML×0.4 → DROP if combined < 12',
    icon: <LineChartOutlined />,
    color: '#fb923c',
  },
  {
    id: 9,
    name: 'Intelligence Check',
    label: 'Rule-based, in-memory',
    desc: 'Non-B2B org without named person · directory listing URL · no real name → DROP',
    icon: <BulbOutlined />,
    color: '#ef4444',
  },
  {
    id: 10,
    name: 'Save + Deep Intelligence',
    label: 'Gemini 8-step background analysis',
    desc: 'DB dedup → write lead → background Gemini analysis updates status: warm / hot / low_quality',
    icon: <DatabaseOutlined />,
    color: '#22c55e',
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

function getStatus(stageId, currentStage, isDone) {
  if (isDone && stageId <= 10) return 'done';
  if (!currentStage) return 'pending';
  if (stageId < currentStage) return 'done';
  if (stageId === currentStage) return 'active';
  return 'pending';
}

// ── Strategy output card ──────────────────────────────────────────────────────

function StrategyCard({ strategy }) {
  if (!strategy) return null;
  return (
    <div style={{
      background: 'rgba(167,139,250,0.06)',
      border: '1px solid rgba(167,139,250,0.2)',
      borderRadius: 8,
      padding: '12px 16px',
      marginBottom: 16,
    }}>
      <div style={{ color: '#a78bfa', fontSize: 10, fontWeight: 700, letterSpacing: 1, marginBottom: 10 }}>
        AI ORCHESTRATOR OUTPUT
      </div>

      {/* Intent + provider + confidence */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
        {strategy.intent && <Tag color="purple">intent: {strategy.intent}</Tag>}
        {strategy.persona && <Tag color="blue">persona: {strategy.persona}</Tag>}
        {strategy.provider && <Tag color="cyan">{strategy.provider}</Tag>}
        {strategy.confidence != null && (
          <Tag color={strategy.confidence >= 0.7 ? 'green' : 'orange'}>
            confidence: {Math.round(strategy.confidence * 100)}%
          </Tag>
        )}
      </div>

      {/* Sources */}
      {strategy.sources?.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <span style={{ color: '#64748b', fontSize: 11, marginRight: 6 }}>Sources:</span>
          {strategy.sources.map(s => (
            <Tag key={s} style={{ fontSize: 10, background: 'rgba(6,182,212,0.1)', border: '1px solid rgba(6,182,212,0.25)', color: '#7dd3fc' }}>
              {s}
            </Tag>
          ))}
        </div>
      )}

      {/* DM Titles */}
      {strategy.dm_titles?.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <span style={{ color: '#64748b', fontSize: 11, marginRight: 6 }}>DM Titles:</span>
          <span style={{ color: '#94a3b8', fontSize: 11 }}>
            {strategy.dm_titles.slice(0, 7).join(', ')}
            {strategy.dm_titles.length > 7 ? ' …' : ''}
          </span>
        </div>
      )}

      {/* Search queries */}
      {strategy.search_queries?.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <span style={{ color: '#64748b', fontSize: 11, marginRight: 6 }}>AI search queries:</span>
          <div style={{ marginTop: 4 }}>
            {strategy.search_queries.map((q, i) => (
              <div key={i} style={{ fontSize: 10, color: '#94a3b8', marginBottom: 3, paddingLeft: 8, borderLeft: '2px solid rgba(6,182,212,0.3)' }}>
                {q.length > 120 ? q.slice(0, 120) + '…' : q}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Rejection signals */}
      {strategy.rejection_signals?.length > 0 && (
        <div>
          <span style={{ color: '#64748b', fontSize: 11, marginRight: 6 }}>Rejection signals:</span>
          <span style={{ color: '#fca5a5', fontSize: 11 }}>
            {strategy.rejection_signals.join(', ')}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PipelineVisualizer({ currentStage, isDone, strategy, qualityReport }) {
  return (
    <div>
      <StrategyCard strategy={strategy} />

      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {STAGES.map((stage, idx) => {
          const status = getStatus(stage.id, currentStage, isDone);
          const isLast = idx === STAGES.length - 1;

          // Pull count annotations from quality report
          let countNote = null;
          if (qualityReport && status === 'done') {
            if (stage.id === 2) countNote = `${qualityReport.raw_candidates ?? 0} discovered`;
            if (stage.id === 3) countNote = `${qualityReport.duplicates ?? 0} dupes removed`;
            if (stage.id === 5) countNote = `${qualityReport.enriched_candidates ?? 0} enriched`;
            if (stage.id === 7) countNote = qualityReport.rejection_reasons
              ? `${Object.values(qualityReport.rejection_reasons).reduce((a, b) => a + b, 0)} rejected`
              : null;
            if (stage.id === 10) countNote = `${qualityReport.saved ?? 0} saved`;
          }

          return (
            <div key={stage.id} style={{ display: 'flex', alignItems: 'stretch' }}>
              {/* Connector column */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 36, flexShrink: 0 }}>
                {/* Stage circle */}
                <Tooltip title={stage.desc} placement="right">
                  <div style={{
                    width: 30,
                    height: 30,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 13,
                    flexShrink: 0,
                    cursor: 'default',
                    transition: 'all 0.35s',
                    background:
                      status === 'done'   ? 'rgba(34,197,94,0.12)' :
                      status === 'active' ? `rgba(${hexToRgb(stage.color)},0.15)` :
                                            'rgba(30,41,59,0.6)',
                    border: `2px solid ${
                      status === 'done'   ? '#22c55e' :
                      status === 'active' ? stage.color :
                                           '#334155'
                    }`,
                    color:
                      status === 'done'   ? '#22c55e' :
                      status === 'active' ? stage.color :
                                           '#475569',
                    boxShadow:
                      status === 'active'
                        ? `0 0 14px rgba(${hexToRgb(stage.color)},0.45)`
                        : 'none',
                  }}>
                    {status === 'done'
                      ? <CheckCircleOutlined style={{ fontSize: 13 }} />
                      : status === 'active'
                      ? <LoadingOutlined style={{ fontSize: 13 }} />
                      : stage.icon}
                  </div>
                </Tooltip>

                {/* Vertical connector line */}
                {!isLast && (
                  <div style={{
                    width: 2,
                    flex: 1,
                    minHeight: 14,
                    margin: '2px 0',
                    background: status === 'done' ? 'rgba(34,197,94,0.5)' : '#1e293b',
                    transition: 'background 0.35s',
                  }} />
                )}
              </div>

              {/* Content */}
              <div style={{
                flex: 1,
                paddingLeft: 12,
                paddingBottom: isLast ? 0 : 10,
                paddingTop: 4,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6, marginBottom: 2 }}>
                  <span style={{
                    fontSize: 12,
                    fontWeight: status === 'active' ? 700 : 500,
                    color:
                      status === 'done'   ? '#22c55e' :
                      status === 'active' ? stage.color :
                                           '#94a3b8',
                    transition: 'color 0.35s',
                  }}>
                    {stage.name}
                  </span>

                  {status === 'active' && (
                    <Tag color="processing" style={{ fontSize: 10, padding: '0 5px', lineHeight: '16px' }}>
                      Active
                    </Tag>
                  )}

                  {countNote && (
                    <span style={{ fontSize: 10, color: '#64748b' }}>{countNote}</span>
                  )}
                </div>

                {/* Label always visible */}
                <div style={{ fontSize: 10, color: '#475569', marginBottom: 2 }}>
                  {stage.label}
                </div>

                {/* Description only when active */}
                {status === 'active' && (
                  <div style={{ fontSize: 11, color: '#64748b', lineHeight: 1.45 }}>
                    {stage.desc}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {isDone && qualityReport && (
        <>
          <Divider style={{ borderColor: 'rgba(255,255,255,0.07)', margin: '14px 0 10px 0' }} />
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {[
              { label: 'Discovered', val: qualityReport.raw_candidates, color: '#94a3b8' },
              { label: 'Saved',      val: qualityReport.saved,          color: '#22c55e' },
              { label: 'Rejected',   val: qualityReport.rejected,        color: '#ef4444' },
              { label: 'Dupes',      val: qualityReport.duplicates,      color: '#f59e0b' },
              { label: 'Enriched',   val: qualityReport.enriched_candidates, color: '#06b6d4' },
            ].map(({ label, val, color }) => (
              <div key={label} style={{
                background: 'rgba(255,255,255,0.04)', borderRadius: 6,
                padding: '6px 12px', textAlign: 'center', minWidth: 70,
              }}>
                <div style={{ color: '#475569', fontSize: 10 }}>{label}</div>
                <div style={{ color, fontSize: 18, fontWeight: 700 }}>{val ?? '—'}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
