import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, ActivityIndicator, Linking, Modal,
} from 'react-native';
let Clipboard = null;
try { Clipboard = require('expo-clipboard'); } catch {}
import { Ionicons } from '@expo/vector-icons';
import { useTheme, COLORS } from '../context/ThemeContext';
import { leadsAPI, aiAPI } from '../services/api';
import { syncSingleLead } from '../services/syncService';
import { refreshDashboard } from '../utils/dashboardRefresh';
import { showError, showSuccess, showInfo, showConfirm } from '../utils/dialog';
import StatusBadge from '../components/StatusBadge';

// ── ML Training Label Bar ─────────────────────────────────────────────────────
const OUTCOME_CONFIG = [
  { outcome: 'converted',   label: 'Converted',  detail: 'Deal closed',   icon: 'trophy-outline',        solid: '#16a34a' },
  { outcome: 'contacted',   label: 'Replied',    detail: 'Got a reply',   icon: 'mail-outline',           solid: '#2563eb' },
  { outcome: 'cold',        label: 'No Reply',   detail: 'Went silent',   icon: 'time-outline',           solid: '#64748b' },
  { outcome: 'unqualified', label: 'Not a Fit',  detail: 'Wrong target',  icon: 'close-circle-outline',   solid: '#dc2626' },
];

function QuickLabelBar({ lead, onLabeled }) {
  const { theme } = useTheme();
  const [saving, setSaving]         = useState(null);
  const [saved, setSaved]           = useState(lead?.outcome || null);
  const [approvalStatus, setStatus] = useState(lead?.approval_status || null);

  const submit = async (outcome) => {
    if (saving) return;
    setSaving(outcome);
    try {
      const res = await aiAPI.submitFeedback(lead.id, outcome);
      const status = res?.data?.approval_status || 'approved';
      setSaved(outcome);
      setStatus(status);
      if (onLabeled) onLabeled(lead.id, outcome, status);
    } catch {
      // non-fatal
    } finally {
      setSaving(null);
    }
  };

  const savedCfg   = OUTCOME_CONFIG.find((c) => c.outcome === saved);
  const isPending  = approvalStatus === 'pending';
  const isRejected = approvalStatus === 'rejected';

  const StatusChip = () => {
    if (isRejected) return (
      <View style={[qlStyles.chip, { backgroundColor: 'rgba(220,38,38,0.1)', borderColor: 'rgba(220,38,38,0.4)' }]}>
        <Ionicons name="close-circle-outline" size={11} color="#dc2626" />
        <Text style={[qlStyles.chipTxt, { color: '#dc2626' }]}>Rejected — re-label</Text>
      </View>
    );
    if (isPending) return (
      <View style={[qlStyles.chip, { backgroundColor: 'rgba(234,179,8,0.1)', borderColor: 'rgba(234,179,8,0.4)' }]}>
        <Ionicons name="time-outline" size={11} color="#ca8a04" />
        <Text style={[qlStyles.chipTxt, { color: '#ca8a04' }]}>Pending review</Text>
      </View>
    );
    if (savedCfg) return (
      <View style={[qlStyles.chip, { backgroundColor: `${savedCfg.solid}18`, borderColor: `${savedCfg.solid}40` }]}>
        <Ionicons name={savedCfg.icon} size={11} color={savedCfg.solid} />
        <Text style={[qlStyles.chipTxt, { color: savedCfg.solid }]}>{savedCfg.label}</Text>
      </View>
    );
    return (
      <View style={[qlStyles.chip, { borderStyle: 'dashed' }]}>
        <Text style={[qlStyles.chipTxt, { color: theme.textMuted }]}>Unlabeled</Text>
      </View>
    );
  };

  return (
    <View style={[qlStyles.wrap, { backgroundColor: theme.card, borderColor: theme.cardBorder }]}>
      <View style={qlStyles.header}>
        <View style={qlStyles.titleRow}>
          <Ionicons name="school-outline" size={14} color={COLORS.purple} />
          <Text style={[qlStyles.title, { color: theme.text }]}>Train ML — Label this lead</Text>
        </View>
        <StatusChip />
      </View>
      <View style={qlStyles.grid}>
        {OUTCOME_CONFIG.map(({ outcome, label, detail, icon, solid }) => {
          const isActive  = saved === outcome && !isPending && !isRejected;
          const isLoading = saving === outcome;
          return (
            <TouchableOpacity
              key={outcome}
              style={[
                qlStyles.btn,
                { borderColor: isActive ? solid : theme.inputBorder, backgroundColor: isActive ? solid : theme.input },
              ]}
              onPress={() => submit(outcome)}
              disabled={!!saving}
              activeOpacity={0.75}
            >
              {isLoading
                ? <ActivityIndicator size="small" color={isActive ? '#fff' : solid} />
                : <Ionicons name={icon} size={20} color={isActive ? '#fff' : solid} />
              }
              <Text style={[qlStyles.btnLabel, { color: isActive ? '#fff' : theme.text }]}>{label}</Text>
              <Text style={[qlStyles.btnDetail, { color: isActive ? 'rgba(255,255,255,0.75)' : theme.textMuted }]}>{detail}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const qlStyles = StyleSheet.create({
  wrap:      { borderRadius: 18, padding: 14, marginBottom: 14, borderWidth: 1, shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  header:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  titleRow:  { flexDirection: 'row', alignItems: 'center', gap: 6 },
  title:     { fontSize: 13, fontWeight: '700' },
  chip:      { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 9, paddingVertical: 3, borderRadius: 20, borderWidth: 1, borderColor: 'rgba(148,163,184,0.4)' },
  chipTxt:   { fontSize: 11, fontWeight: '600' },
  grid:      { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  btn:       { width: '47.5%', alignItems: 'center', paddingVertical: 14, borderRadius: 14, borderWidth: 1.5, gap: 4 },
  btnLabel:  { fontSize: 13, fontWeight: '700' },
  btnDetail: { fontSize: 10, fontWeight: '400' },
});

// ─────────────────────────────────────────────────────────────────────────────

const STATUS_GROUPS = [
  { label: 'AI Score',  items: [
    { key: 'hot',         color: '#e53935' },
    { key: 'warm',        color: '#fb8c00' },
    { key: 'cold',        color: '#039be5' },
    { key: 'unqualified', color: '#757575' },
  ]},
  { label: 'Workflow', items: [
    { key: 'pending',   color: '#7b1fa2' },
    { key: 'contacted', color: '#00897b' },
    { key: 'converted', color: '#43a047' },
  ]},
];

export default function LeadDetailScreen({ route, navigation }) {
  const { leadId } = route.params;
  const { theme } = useTheme();

  const [lead, setLead]             = useState(null);
  const [loading, setLoading]       = useState(true);
  const [editing, setEditing]       = useState(false);
  const [saving, setSaving]         = useState(false);
  const [qualifying, setQualify]    = useState(false);
  const [form, setForm]             = useState({});

  // AI actions
  const [analyzing, setAnalyzing]     = useState(false);
  const [enriching, setEnriching]     = useState(false);
  const [genEmail, setGenEmail]       = useState(false);
  const [aiModal, setAiModal]         = useState(null); // { title, content }

  const fetchLead = useCallback(async () => {
    try {
      const resp = await leadsAPI.getLead(leadId);
      const l = resp.data.lead;
      setLead(l);
      setForm({
        name: l.name || '', email: l.email || '', phone: l.phone || '',
        company: l.company || '', position: l.position || '',
        country: l.country || '', city: l.city || '',
        industry: l.industry || '', website: l.website || '',
        linkedin_url: l.linkedin_url || '', notes: l.notes || '',
        status: l.status || 'pending',
      });
    } catch {
      showError('Error', 'Failed to load lead');
      navigation.goBack();
    } finally {
      setLoading(false);
    }
  }, [leadId]);

  useEffect(() => { fetchLead(); }, []);

  // ── Unsaved-changes guard (iOS header chevron + Android hardware back) ────
  // navigation.addListener('beforeRemove') fires for ALL back gestures on both
  // platforms — header back button, swipe-back (iOS), hardware back (Android).
  useEffect(() => {
    const unsub = navigation.addListener('beforeRemove', (e) => {
      if (!editing) return; // nothing unsaved — let navigation proceed
      e.preventDefault();  // block the back action
      showConfirm(
        'Unsaved Changes',
        'You have unsaved changes. Discard them and go back?',
        () => {
          setEditing(false);
          navigation.dispatch(e.data.action);
        },
        undefined,
        'Discard',
        'Keep Editing',
        'danger',
      );
    });
    return unsub;
  }, [navigation, editing]);

  const handleSave = async () => {
    try {
      setSaving(true);
      const resp = await leadsAPI.updateLead(leadId, form);
      setLead(resp.data.lead);
      setEditing(false);
      syncSingleLead(leadId).catch(() => {});
      refreshDashboard();
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleQualify = async () => {
    try {
      setQualify(true);
      const resp = await leadsAPI.qualifyLead(leadId, true);
      const updated = {
        ...lead,
        qualification_score: resp.data.score,
        status: resp.data.category || lead.status,
      };
      setLead(updated);
      setForm((f) => ({ ...f, status: updated.status }));
      syncSingleLead(leadId).catch(() => {});
      refreshDashboard();
      const recs = (resp.data.recommendations || []).slice(0, 2).join('\n');
      showSuccess(
        'AI Qualification Complete',
        `Score: ${resp.data.score}/100\nCategory: ${resp.data.category?.toUpperCase()}\nConfidence: ${Math.round((resp.data.confidence || 0) * 100)}%${recs ? '\n\n' + recs : ''}`,
      );
    } catch (err) {
      showError('Error', err?.response?.data?.message || err?.message || 'Qualification failed');
    } finally {
      setQualify(false);
    }
  };

  const handleAnalyze = async () => {
    try {
      setAnalyzing(true);
      const resp = await aiAPI.analyzeLead(leadId);
      const d = resp.data;
      const a = d.analysis || {};
      const lines = [];
      if (a.company_analysis)          lines.push(`Company\n${a.company_analysis}`);
      if (a.decision_maker_assessment) lines.push(`Decision Maker\n${a.decision_maker_assessment}`);
      if (a.pain_points?.length)       lines.push(`Pain Points\n• ${a.pain_points.join('\n• ')}`);
      if (a.buying_signals?.length)    lines.push(`Buying Signals\n• ${a.buying_signals.join('\n• ')}`);
      if (a.risk_factors?.length)      lines.push(`Risk Factors\n• ${a.risk_factors.join('\n• ')}`);
      if (a.recommended_approach)      lines.push(`Recommended Approach\n${a.recommended_approach}`);
      if (a.talking_points?.length)    lines.push(`Talking Points\n• ${a.talking_points.join('\n• ')}`);
      const meta = [
        a.estimated_deal_size && `Deal Size: ${a.estimated_deal_size}`,
        a.sales_cycle_estimate && `Sales Cycle: ${a.sales_cycle_estimate}`,
        a.priority && `Priority: ${a.priority}`,
      ].filter(Boolean).join('   ');
      if (meta) lines.push(meta);
      if (d.ai_provider) lines.push(`\nPowered by: ${d.ai_provider}`);
      setAiModal({ title: `Analysis: ${lead.name || lead.company}`, content: lines.join('\n\n') || JSON.stringify(d, null, 2) });
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'AI analysis failed');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleGenerateEmail = async () => {
    try {
      setGenEmail(true);
      const resp = await aiAPI.generateEmail(leadId, { email_type: 'cold_outreach', tone: 'professional' });
      const d = resp.data;
      const e = d.email || d;
      const lines = [];
      if (e.subject) lines.push(`Subject: ${e.subject}`);
      if (e.body)    lines.push(e.body);
      else if (e.content) lines.push(e.content);
      if (e.call_to_action)        lines.push(`CTA: ${e.call_to_action}`);
      if (e.personalization_notes) lines.push(`Notes: ${e.personalization_notes}`);
      if (d.ai_provider) lines.push(`\nPowered by: ${d.ai_provider}`);
      setAiModal({ title: `Email Draft: ${lead.name || lead.company}`, content: lines.join('\n\n') || JSON.stringify(d, null, 2) });
    } catch (err) {
      showError('Error', err?.response?.data?.message || 'Email generation failed');
    } finally {
      setGenEmail(false);
    }
  };

  const handleEnrich = async () => {
    showConfirm(
      'Enrich Lead',
      'Use AI to enrich this lead with additional data (website, industry, social)?',
      async () => {
        try {
          setEnriching(true);
          await aiAPI.enrichLead(leadId);
          await fetchLead();
          showSuccess('Enriched', 'Lead data has been enriched successfully');
          syncSingleLead(leadId).catch(() => {});
          refreshDashboard();
        } catch (err) {
          showError('Error', err?.response?.data?.message || 'Enrichment failed');
        } finally {
          setEnriching(false);
        }
      },
    );
  };

  const handleStatusChange = async (newStatus) => {
    try {
      await leadsAPI.updateLead(leadId, { status: newStatus });
      setLead((prev) => ({ ...prev, status: newStatus }));
      setForm((f) => ({ ...f, status: newStatus }));
      syncSingleLead(leadId).catch(() => {});
      refreshDashboard();
    } catch {
      showError('Error', 'Failed to update status');
    }
  };

  const s = styles(theme);

  if (loading) {
    return <View style={[s.root, s.center]}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }
  if (!lead) return null;

  const score = Math.round(lead.qualification_score || 0);
  const scoreColor = score >= 80 ? COLORS.green : score >= 60 ? COLORS.amber : COLORS.red;

  return (
    <View style={{ flex: 1 }}>
      <ScrollView style={s.root} contentContainerStyle={s.scroll}>

        {/* Hero Card */}
        <View style={s.heroCard}>
          <View style={s.avatarRow}>
            <View style={s.avatar}>
              <Text style={s.avatarText}>{(lead.name || '?')[0].toUpperCase()}</Text>
            </View>
            <View style={s.heroInfo}>
              <Text style={s.heroName}>{lead.name}</Text>
              <Text style={s.heroSub}>
                {lead.position || ''}{lead.position && lead.company ? ' · ' : ''}{lead.company || ''}
              </Text>
            </View>
            <View style={s.scoreCircle}>
              <Text style={[s.scoreNum, { color: scoreColor }]}>{score}</Text>
              <Text style={s.scoreLabel}>score</Text>
            </View>
          </View>

          {/* Status Groups */}
          <View style={{ marginTop: 12 }}>
            {STATUS_GROUPS.map((group) => (
              <View key={group.label} style={{ marginBottom: 6 }}>
                <Text style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 4, fontWeight: '600', letterSpacing: 0.5 }}>
                  {group.label.toUpperCase()}
                </Text>
                <View style={s.statusRow}>
                  {group.items.map(({ key, color }) => {
                    const active = form.status === key;
                    return (
                      <TouchableOpacity
                        key={key}
                        style={[s.statusBtn, active && { backgroundColor: color, borderColor: color }]}
                        onPress={() => handleStatusChange(key)}
                      >
                        <Text style={[s.statusBtnText, active && { color: '#fff' }]}>
                          {key.charAt(0).toUpperCase() + key.slice(1)}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            ))}
          </View>

          {/* Quick Contact + AI Actions */}
          <View style={s.actionRow}>
            {lead.email && (
              <TouchableOpacity style={s.actionBtn} onPress={() => Linking.openURL(`mailto:${lead.email}`)}>
                <Ionicons name="mail" size={16} color={COLORS.cyan} />
                <Text style={[s.actionTxt, { color: COLORS.cyan }]}>Email</Text>
              </TouchableOpacity>
            )}
            {lead.phone && (
              <TouchableOpacity style={s.actionBtn} onPress={() => Linking.openURL(`tel:${lead.phone}`)}>
                <Ionicons name="call" size={16} color={COLORS.green} />
                <Text style={[s.actionTxt, { color: COLORS.green }]}>Call</Text>
              </TouchableOpacity>
            )}
            {lead.linkedin_url && (
              <TouchableOpacity style={s.actionBtn} onPress={() => Linking.openURL(lead.linkedin_url)}>
                <Ionicons name="logo-linkedin" size={16} color="#0077b5" />
                <Text style={[s.actionTxt, { color: '#0077b5' }]}>LinkedIn</Text>
              </TouchableOpacity>
            )}
            {lead.website && (
              <TouchableOpacity style={s.actionBtn} onPress={() => Linking.openURL(lead.website.startsWith('http') ? lead.website : `https://${lead.website}`)}>
                <Ionicons name="globe" size={16} color={COLORS.purple} />
                <Text style={[s.actionTxt, { color: COLORS.purple }]}>Website</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* ML Training Label Bar */}
        <QuickLabelBar
          lead={lead}
          onLabeled={(leadId, outcome) => setLead((prev) => ({ ...prev, outcome }))}
        />

        {/* AI Tools Card */}
        <View style={s.card}>
          <Text style={s.sectionTitle}>AI Tools</Text>
          <View style={s.aiToolsGrid}>
            {[
              {
                icon: 'flash',        color: COLORS.primary,
                label: 'Qualify',     desc: 'Score & categorize',
                loading: qualifying,  onPress: handleQualify,
              },
              {
                icon: 'analytics',    color: COLORS.cyan,
                label: 'Analyze',     desc: 'Deep lead insights',
                loading: analyzing,   onPress: handleAnalyze,
              },
              {
                icon: 'mail-unread',  color: COLORS.amber,
                label: 'Write Email', desc: 'Cold outreach draft',
                loading: genEmail,    onPress: handleGenerateEmail,
              },
              {
                icon: 'sparkles',     color: COLORS.green,
                label: 'Enrich',      desc: 'Fill missing data',
                loading: enriching,   onPress: handleEnrich,
              },
            ].map(({ icon, color, label, desc, loading: busy, onPress }) => (
              <TouchableOpacity
                key={label}
                style={[s.aiTool, { borderColor: `${color}30`, backgroundColor: `${color}08` }]}
                onPress={onPress}
                disabled={busy}
                activeOpacity={0.75}
              >
                <View style={[s.aiToolIcon, { backgroundColor: `${color}20` }]}>
                  {busy
                    ? <ActivityIndicator size="small" color={color} />
                    : <Ionicons name={icon} size={22} color={color} />
                  }
                </View>
                <Text style={[s.aiToolLabel, { color: theme.text }]}>{label}</Text>
                <Text style={[s.aiToolDesc, { color: theme.textMuted }]}>{desc}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Contact Info */}
        <View style={s.card}>
          <View style={s.sectionHeader}>
            <Text style={s.sectionTitle}>Contact Info</Text>
            <TouchableOpacity onPress={() => editing ? handleSave() : setEditing(true)} disabled={saving}>
              {saving
                ? <ActivityIndicator size="small" color={COLORS.primary} />
                : <Text style={s.editBtn}>{editing ? 'Save' : 'Edit'}</Text>
              }
            </TouchableOpacity>
          </View>

          {editing && (
            <TouchableOpacity
              style={s.cancelEdit}
              onPress={() => {
                // Reset form to last saved lead data and exit edit mode
                setForm({
                  name: lead.name || '', email: lead.email || '', phone: lead.phone || '',
                  company: lead.company || '', position: lead.position || '',
                  country: lead.country || '', city: lead.city || '',
                  industry: lead.industry || '', website: lead.website || '',
                  linkedin_url: lead.linkedin_url || '', notes: lead.notes || '',
                  status: lead.status || 'pending',
                });
                setEditing(false);
              }}
            >
              <Text style={s.cancelEditText}>Cancel</Text>
            </TouchableOpacity>
          )}

          {[
            { icon: 'person-outline',   label: 'Name',     field: 'name',     type: 'default' },
            { icon: 'business-outline', label: 'Company',  field: 'company',  type: 'default' },
            { icon: 'briefcase-outline',label: 'Position', field: 'position', type: 'default' },
            { icon: 'mail-outline',     label: 'Email',    field: 'email',    type: 'email-address' },
            { icon: 'call-outline',     label: 'Phone',    field: 'phone',    type: 'phone-pad' },
            { icon: 'globe-outline',    label: 'Website',  field: 'website',  type: 'url' },
            { icon: 'location-outline', label: 'Country',  field: 'country',  type: 'default' },
            { icon: 'map-outline',      label: 'City',     field: 'city',     type: 'default' },
            { icon: 'business-outline', label: 'Industry', field: 'industry', type: 'default' },
          ].map(({ icon, label, field, type }) => (
            <View key={field} style={s.infoRow}>
              <Ionicons name={icon} size={15} color={theme.textMuted} style={s.infoIcon} />
              <View style={s.infoContent}>
                <Text style={s.infoLabel}>{label}</Text>
                {editing ? (
                  <TextInput
                    style={[s.infoInput, { color: theme.text, borderColor: theme.inputBorder }]}
                    value={form[field]}
                    onChangeText={(v) => setForm((f) => ({ ...f, [field]: v }))}
                    keyboardType={type}
                    autoCapitalize={type === 'email-address' || type === 'url' ? 'none' : 'sentences'}
                    placeholderTextColor={theme.textMuted}
                    placeholder={`Enter ${label.toLowerCase()}`}
                  />
                ) : (
                  <Text style={s.infoValue}>{lead[field] || '—'}</Text>
                )}
              </View>
            </View>
          ))}
        </View>

        {/* Notes */}
        <View style={s.card}>
          <Text style={s.sectionTitle}>Notes</Text>
          {editing ? (
            <TextInput
              style={[s.notesInput, { color: theme.text, borderColor: theme.inputBorder, backgroundColor: theme.input }]}
              value={form.notes}
              onChangeText={(v) => setForm((f) => ({ ...f, notes: v }))}
              multiline
              numberOfLines={5}
              placeholder="Add notes..."
              placeholderTextColor={theme.textMuted}
            />
          ) : (
            <Text style={s.notesText}>{lead.notes || 'No notes yet.'}</Text>
          )}
        </View>

        {/* Interests */}
        {Array.isArray(lead.interests) && lead.interests.length > 0 && (
          <View style={s.card}>
            <Text style={s.sectionTitle}>Interests</Text>
            <View style={s.tagsRow}>
              {lead.interests.map((tag, i) => (
                <View key={i} style={s.tag}>
                  <Text style={s.tagText}>{tag}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Meta */}
        <View style={[s.card, { marginBottom: 32 }]}>
          <Text style={s.sectionTitle}>Details</Text>
          {[
            { label: 'Source',    value: lead.source || '—' },
            { label: 'Lead Type', value: lead.lead_type || '—' },
            { label: 'Origin',    value: lead.origin || '—' },
            { label: 'Created',   value: lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '—' },
            { label: 'Updated',   value: lead.updated_at ? new Date(lead.updated_at).toLocaleDateString() : '—' },
          ].map(({ label, value }) => (
            <View key={label} style={s.metaRow}>
              <Text style={s.metaLabel}>{label}</Text>
              <Text style={s.metaValue}>{value}</Text>
            </View>
          ))}
        </View>

      </ScrollView>

      {/* AI Result Modal */}
      <Modal
        visible={!!aiModal}
        transparent
        animationType="slide"
        onRequestClose={() => setAiModal(null)}
      >
        <View style={s.modalOverlay}>
          <View style={[s.modalSheet, { backgroundColor: theme.surface || theme.card }]}>
            <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: theme.textMuted, alignSelf: 'center', marginBottom: 16, opacity: 0.4 }} />
            <View style={s.modalHeader}>
              <Text style={[s.modalTitle, { color: theme.text }]} numberOfLines={2}>{aiModal?.title}</Text>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TouchableOpacity
                  onPress={() => {
                    if (Clipboard) {
                      Clipboard.setStringAsync(aiModal?.content || '');
                      showSuccess('Copied', 'Content copied to clipboard');
                    } else {
                      showInfo('Unavailable', 'Clipboard not supported in Expo Go');
                    }
                  }}
                  style={[s.modalClose, { backgroundColor: `${COLORS.primary}15` }]}
                >
                  <Ionicons name="copy-outline" size={15} color={COLORS.primary} />
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setAiModal(null)} style={s.modalClose}>
                  <Ionicons name="close" size={16} color={theme.textSecondary} />
                </TouchableOpacity>
              </View>
            </View>
            <ScrollView showsVerticalScrollIndicator={false}>
              {(aiModal?.content || '').split('\n\n').map((block, i) => {
                const lines = block.split('\n');
                const isHeader = lines.length > 1 && lines[0] && !lines[0].startsWith('•') && !lines[0].startsWith('Powered');
                return (
                  <View key={i} style={{ marginBottom: 14 }}>
                    {isHeader ? (
                      <>
                        <Text style={[s.modalSectionTitle, { color: COLORS.primary }]}>{lines[0]}</Text>
                        {lines.slice(1).map((l, j) => (
                          <Text key={j} style={[s.modalContent, { color: theme.textSecondary }]}>{l}</Text>
                        ))}
                      </>
                    ) : (
                      <Text style={[s.modalContent, { color: block.startsWith('Powered') ? theme.textMuted : theme.textSecondary, fontStyle: block.startsWith('Powered') ? 'italic' : 'normal' }]}>{block}</Text>
                    )}
                  </View>
                );
              })}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = (theme) => StyleSheet.create({
  root:   { flex: 1, backgroundColor: theme.bg },
  scroll: { padding: 16 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },

  heroCard: {
    backgroundColor: theme.card, borderRadius: 22,
    padding: 20, marginBottom: 14,
    borderWidth: 1, borderColor: theme.cardBorder,
    shadowColor: COLORS.primary, shadowOpacity: 0.1,
    shadowRadius: 16, shadowOffset: { width: 0, height: 6 }, elevation: 4,
  },
  avatarRow:  { flexDirection: 'row', alignItems: 'center' },
  avatar:     { width: 56, height: 56, borderRadius: 28, backgroundColor: `${COLORS.primary}18`, alignItems: 'center', justifyContent: 'center', marginRight: 14, borderWidth: 2, borderColor: `${COLORS.primary}30` },
  avatarText: { fontSize: 24, fontWeight: '800', color: COLORS.primary },
  heroInfo:   { flex: 1 },
  heroName:   { fontSize: 19, fontWeight: '800', color: theme.text, letterSpacing: 0.1 },
  heroSub:    { fontSize: 13, color: theme.textMuted, marginTop: 3 },
  scoreCircle:{ alignItems: 'center', paddingLeft: 4 },
  scoreNum:   { fontSize: 26, fontWeight: '900' },
  scoreLabel: { fontSize: 10, color: theme.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },

  statusRow:    { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  statusBtn:    { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20, backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder },
  statusBtnText:{ fontSize: 12, fontWeight: '600', color: theme.textSecondary },

  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 14 },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 13, paddingVertical: 8, borderRadius: 12, backgroundColor: theme.input, borderWidth: 1, borderColor: theme.inputBorder },
  actionTxt: { fontSize: 12, fontWeight: '600' },

  card: {
    backgroundColor: theme.card, borderRadius: 18, padding: 16, marginBottom: 14,
    borderWidth: 1, borderColor: theme.cardBorder,
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2,
  },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  sectionTitle:  { fontSize: 14, fontWeight: '700', color: theme.text },
  editBtn:       { fontSize: 14, fontWeight: '700', color: COLORS.primary },
  cancelEdit:    { marginBottom: 10 },
  cancelEditText:{ fontSize: 13, color: COLORS.red, fontWeight: '600' },

  // AI Tools grid
  aiToolsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 4 },
  aiTool: {
    width: '47%', alignItems: 'center',
    paddingVertical: 18, paddingHorizontal: 10, borderRadius: 16,
    borderWidth: 1.5, gap: 8,
  },
  aiToolIcon:  { width: 48, height: 48, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  aiToolLabel: { fontSize: 13, fontWeight: '700', textAlign: 'center' },
  aiToolDesc:  { fontSize: 11, textAlign: 'center', lineHeight: 15, color: theme.textMuted },

  infoRow:     { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 13 },
  infoIcon:    { marginTop: 3, marginRight: 10, width: 18 },
  infoContent: { flex: 1 },
  infoLabel:   { fontSize: 11, fontWeight: '700', color: theme.textMuted, marginBottom: 2, textTransform: 'uppercase', letterSpacing: 0.4 },
  infoValue:   { fontSize: 14, color: theme.text, fontWeight: '500' },
  infoInput:   { fontSize: 14, borderBottomWidth: 1, paddingVertical: 3, paddingHorizontal: 0 },

  notesInput: { borderWidth: 1, borderRadius: 12, padding: 12, fontSize: 14, textAlignVertical: 'top', minHeight: 90, marginTop: 8 },
  notesText:  { fontSize: 14, color: theme.textSecondary, lineHeight: 22 },

  tagsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  tag:     { backgroundColor: `${COLORS.primary}15`, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: `${COLORS.primary}25` },
  tagText: { fontSize: 12, color: COLORS.primary, fontWeight: '600' },

  metaRow:   { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: theme.cardBorder },
  metaLabel: { fontSize: 13, color: theme.textMuted },
  metaValue: { fontSize: 13, color: theme.text, fontWeight: '500' },

  // Modal
  modalOverlay:      { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  modalSheet:        { borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: 20, paddingBottom: 44, maxHeight: '84%' },
  modalHeader:       { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18, gap: 10 },
  modalClose:        { padding: 3, backgroundColor: theme.input, borderRadius: 20, width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  modalTitle:        { fontSize: 16, fontWeight: '800', flex: 1, color: theme.text },
  modalSectionTitle: { fontSize: 12, fontWeight: '700', letterSpacing: 0.5, marginBottom: 5, textTransform: 'uppercase' },
  modalContent:      { fontSize: 13, lineHeight: 20 },
});
