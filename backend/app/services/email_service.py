"""
Email service — sends transactional emails via SMTP (Gmail by default).

Configuration (env vars, already present in .env):
    SMTP_SERVER   = smtp.gmail.com
    SMTP_PORT     = 587
    SMTP_USER     = your@gmail.com
    SMTP_PASSWORD = app-password

OTP helpers:
    generate_otp()          — returns a 6-digit string
    send_otp_email(...)     — sends the verification code email
"""

import os
import random
import string
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SMTP_SERVER    = os.getenv('SMTP_SERVER',   'smtp.gmail.com')
SMTP_PORT      = int(os.getenv('SMTP_PORT', 587))
SMTP_USER      = os.getenv('SMTP_USER',     '')
SMTP_PASSWORD  = os.getenv('SMTP_PASSWORD', '')
FROM_NAME      = os.getenv('EMAIL_FROM_NAME', 'OrionLead AI')
OTP_EXPIRY_MIN = int(os.getenv('OTP_EXPIRY_MINUTES', 10))
SMTP_TIMEOUT   = int(os.getenv('SMTP_TIMEOUT', 30))


def generate_otp(length: int = 6) -> str:
    """Return a cryptographically adequate random numeric OTP."""
    return ''.join(random.SystemRandom().choices(string.digits, k=length))


def _mask_email(email: str) -> str:
    """al***@gmail.com — show first 2 chars of local part, mask the rest."""
    try:
        local, domain = email.split('@', 1)
        visible = local[:2] if len(local) > 2 else local[0]
        return f"{visible}***@{domain}"
    except Exception:
        return email


def _do_send(msg_str: str, to_email: str) -> None:
    """Open an SMTP connection and deliver one message. Raises on failure."""
    import ssl as _ssl
    ctx = _ssl.create_default_context()
    if SMTP_PORT == 465:
        # Direct SSL — no STARTTLS negotiation
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=SMTP_TIMEOUT, context=ctx) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg_str)
    else:
        # STARTTLS (port 587)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg_str)


def _send(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Low-level SMTP send with one retry. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning('[EmailService] SMTP not configured — skipping send')
        return False
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f'{FROM_NAME} <{SMTP_USER}>'
    msg['To']      = to_email
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))
    msg_str = msg.as_string()
    for attempt in range(2):
        try:
            _do_send(msg_str, to_email)
            logger.info(f'[EmailService] Sent "{subject}" → {to_email}')
            return True
        except Exception as exc:
            if attempt == 0:
                logger.warning(f'[EmailService] Attempt 1 failed ({exc}), retrying…')
            else:
                logger.error(f'[EmailService] Failed to send to {to_email}: {exc}')
    return False


def send_new_lead_notification(to_email: str, lead_name: str, company: str,
                                score: float, source: str) -> bool:
    """Notify user that a new lead was saved."""
    score_int = int(score or 0)
    score_color = '#22c55e' if score_int >= 80 else '#f59e0b' if score_int >= 60 else '#94a3b8'
    html = f"""
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f0f4f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:40px 0;"><tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:28px 40px;text-align:center;">
    <h1 style="margin:0;color:#fff;font-size:20px;font-weight:800;">New Lead Captured</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.78);font-size:13px;">OrionLead AI</p>
  </td></tr>
  <tr><td style="padding:32px 40px;">
    <p style="margin:0 0 20px;color:#475569;font-size:14px;">A new lead has been added to your pipeline:</p>
    <div style="background:#f8fafc;border-radius:12px;padding:20px 24px;margin-bottom:20px;">
      <p style="margin:0 0 6px;color:#1e293b;font-size:16px;font-weight:700;">{lead_name}</p>
      <p style="margin:0 0 12px;color:#64748b;font-size:13px;">{company}</p>
      <div style="display:inline-block;background:{score_color}18;border-radius:8px;padding:4px 12px;">
        <span style="color:{score_color};font-weight:700;font-size:13px;">Score: {score_int}/100</span>
      </div>
      <p style="margin:10px 0 0;color:#94a3b8;font-size:12px;">Source: {source}</p>
    </div>
    <p style="margin:0;color:#94a3b8;font-size:12px;text-align:center;">You can manage this lead in the OrionLead AI app.</p>
  </td></tr>
  <tr><td style="padding:16px 40px;border-top:1px solid #f1f5f9;text-align:center;">
    <p style="margin:0;color:#cbd5e1;font-size:11px;">&copy; 2025 OrionLead AI · To unsubscribe, update notification settings in the app.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
    text = f"New lead: {lead_name} @ {company} — Score: {score_int}/100 (via {source})"
    return _send(to_email, f'New Lead: {lead_name} @ {company}', html, text)


def send_high_quality_alert(to_email: str, lead_name: str, company: str,
                             score: float, position: str) -> bool:
    """Alert user when a lead scores >= 80 (hot lead)."""
    score_int = int(score or 0)
    html = f"""
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f0f4f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:40px 0;"><tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#ef4444,#f97316);padding:28px 40px;text-align:center;">
    <p style="margin:0 0 8px;font-size:28px;">🔥</p>
    <h1 style="margin:0;color:#fff;font-size:20px;font-weight:800;">Hot Lead Alert</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.78);font-size:13px;">Score {score_int}/100 — Immediate action recommended</p>
  </td></tr>
  <tr><td style="padding:32px 40px;">
    <p style="margin:0 0 20px;color:#475569;font-size:14px;">A high-quality lead just entered your pipeline and is ready for outreach:</p>
    <div style="background:#fef2f2;border-left:4px solid #ef4444;border-radius:8px;padding:20px 24px;margin-bottom:20px;">
      <p style="margin:0 0 4px;color:#1e293b;font-size:16px;font-weight:700;">{lead_name}</p>
      {f'<p style="margin:0 0 8px;color:#64748b;font-size:13px;">{position}</p>' if position else ''}
      <p style="margin:0;color:#64748b;font-size:13px;">{company}</p>
    </div>
    <div style="text-align:center;margin-bottom:24px;">
      <div style="display:inline-block;background:#fef2f2;border-radius:12px;padding:12px 32px;">
        <span style="color:#ef4444;font-size:32px;font-weight:800;">{score_int}</span>
        <span style="color:#94a3b8;font-size:14px;">/100</span>
      </div>
    </div>
    <p style="margin:0;color:#94a3b8;font-size:12px;text-align:center;">Open the app to start outreach before this lead goes cold.</p>
  </td></tr>
  <tr><td style="padding:16px 40px;border-top:1px solid #f1f5f9;text-align:center;">
    <p style="margin:0;color:#cbd5e1;font-size:11px;">&copy; 2025 OrionLead AI · To unsubscribe, update notification settings in the app.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
    text = f"Hot Lead Alert: {lead_name} @ {company} scored {score_int}/100. Contact them now!"
    return _send(to_email, f'🔥 Hot Lead: {lead_name} @ {company} ({score_int}/100)', html, text)


def send_qualification_summary(to_email: str, processed: int, hot: int,
                                warm: int, cold: int, avg_score: float) -> bool:
    """Send a qualification run summary to the user."""
    avg = round(avg_score or 0, 1)
    html = f"""
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f0f4f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:40px 0;"><tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:28px 40px;text-align:center;">
    <h1 style="margin:0;color:#fff;font-size:20px;font-weight:800;">Qualification Complete</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.78);font-size:13px;">{processed} leads scored by AI</p>
  </td></tr>
  <tr><td style="padding:32px 40px;">
    <table width="100%" cellpadding="0" cellspacing="8">
      <tr>
        <td style="text-align:center;background:#fef2f218;border-radius:10px;padding:16px;">
          <p style="margin:0;color:#ef4444;font-size:24px;font-weight:800;">{hot}</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:12px;">Hot</p>
        </td>
        <td width="8"></td>
        <td style="text-align:center;background:#fef9ec;border-radius:10px;padding:16px;">
          <p style="margin:0;color:#f59e0b;font-size:24px;font-weight:800;">{warm}</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:12px;">Warm</p>
        </td>
        <td width="8"></td>
        <td style="text-align:center;background:#f8fafc;border-radius:10px;padding:16px;">
          <p style="margin:0;color:#94a3b8;font-size:24px;font-weight:800;">{cold}</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:12px;">Cold</p>
        </td>
        <td width="8"></td>
        <td style="text-align:center;background:#f0f9ff;border-radius:10px;padding:16px;">
          <p style="margin:0;color:#06b6d4;font-size:24px;font-weight:800;">{avg}</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:12px;">Avg Score</p>
        </td>
      </tr>
    </table>
  </td></tr>
  <tr><td style="padding:16px 40px;border-top:1px solid #f1f5f9;text-align:center;">
    <p style="margin:0;color:#cbd5e1;font-size:11px;">&copy; 2025 OrionLead AI · To unsubscribe, update notification settings in the app.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
    text = f"Qualification complete: {processed} leads — {hot} hot, {warm} warm, {cold} cold. Avg score: {avg}/100"
    return _send(to_email, f'Qualification Complete: {hot} hot leads found', html, text)


def send_otp_email(to_email: str, code: str, full_name: str = '') -> bool:
    """Send a 6-digit OTP verification email."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning('[EmailService] SMTP not configured — skipping OTP send')
        logger.info(f'[EmailService] DEV OTP for {to_email}: {code}')
        return False

    greeting = f'Hi {full_name.split()[0]},' if full_name else 'Hi,'
    html = f"""
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f0f4f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:40px 0;"><tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:36px 40px;text-align:center;">
    <h1 style="margin:0;color:#fff;font-size:22px;font-weight:800;">OrionLead AI</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.78);font-size:13px;">Email Verification</p>
  </td></tr>
  <tr><td style="padding:36px 40px;">
    <p style="margin:0 0 20px;color:#1e293b;font-size:15px;">{greeting}</p>
    <p style="margin:0 0 28px;color:#475569;font-size:14px;line-height:1.6;">
      Enter the code below to confirm your email. Expires in <strong>{OTP_EXPIRY_MIN} minutes</strong>.
    </p>
    <div style="text-align:center;margin:0 0 32px;">
      <div style="display:inline-block;background:#f8fafc;border:2px solid #e2e8f0;border-radius:14px;padding:20px 40px;">
        <span style="font-size:38px;font-weight:800;letter-spacing:12px;color:#6366f1;">{code}</span>
      </div>
    </div>
    <p style="margin:0;color:#94a3b8;font-size:12px;text-align:center;">If you didn't create an account, ignore this email.</p>
  </td></tr>
  <tr><td style="padding:20px 40px;border-top:1px solid #f1f5f9;text-align:center;">
    <p style="margin:0;color:#cbd5e1;font-size:11px;">&copy; 2025 OrionLead AI · Automated message, do not reply.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
    text = f"{greeting}\n\nYour OrionLead AI code: {code}\n\nExpires in {OTP_EXPIRY_MIN} minutes."
    return _send(to_email, f'{code} — Your OrionLead AI verification code', html, text)


def send_system_error_alert(to_email: str, path: str, method: str,
                             error_type: str, error_msg: str) -> bool:
    """Alert user when an unhandled server error occurs."""
    html = f"""
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f0f4f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:40px 0;"><tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#ef4444,#dc2626);padding:28px 40px;text-align:center;">
    <p style="margin:0 0 8px;font-size:28px;">&#9888;&#65039;</p>
    <h1 style="margin:0;color:#fff;font-size:20px;font-weight:800;">System Error</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.78);font-size:13px;">OrionLead AI &mdash; Error Alert</p>
  </td></tr>
  <tr><td style="padding:32px 40px;">
    <p style="margin:0 0 16px;color:#475569;font-size:14px;">An unexpected error occurred in your application:</p>
    <div style="background:#fef2f2;border-left:4px solid #ef4444;border-radius:8px;padding:16px 20px;margin-bottom:20px;font-family:monospace;font-size:12px;">
      <p style="margin:0 0 6px;color:#1e293b;"><strong>{method}</strong> {path}</p>
      <p style="margin:0 0 6px;color:#991b1b;font-weight:600;">{error_type}</p>
      <p style="margin:0;color:#64748b;word-break:break-word;">{error_msg}</p>
    </div>
    <p style="margin:0;color:#94a3b8;font-size:12px;text-align:center;">Check server logs for details. Disable this alert in Settings &rarr; Notifications.</p>
  </td></tr>
  <tr><td style="padding:16px 40px;border-top:1px solid #f1f5f9;text-align:center;">
    <p style="margin:0;color:#cbd5e1;font-size:11px;">&copy; 2025 OrionLead AI &middot; Automated error notification.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
    text = f"OrionLead AI Error: {method} {path} — {error_type}: {error_msg}"
    return _send(to_email, f'[OrionLead AI] System Error: {error_type}', html, text)


def send_daily_digest(to_email: str, total_leads: int, new_today: int,
                      hot_leads: int, avg_score: float) -> bool:
    """Send a daily summary of the user's lead pipeline."""
    from datetime import datetime as _dt
    date_str = _dt.now().strftime('%B %d, %Y')
    avg = round(avg_score or 0, 1)
    html = f"""
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f0f4f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:40px 0;"><tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:28px 40px;text-align:center;">
    <h1 style="margin:0;color:#fff;font-size:20px;font-weight:800;">Daily Digest</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.78);font-size:13px;">{date_str}</p>
  </td></tr>
  <tr><td style="padding:32px 40px;">
    <p style="margin:0 0 20px;color:#475569;font-size:14px;">Your lead pipeline summary:</p>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="text-align:center;background:#f8fafc;border-radius:10px;padding:16px 8px;">
          <p style="margin:0;color:#6366f1;font-size:28px;font-weight:800;">{total_leads}</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Total Leads</p>
        </td>
        <td width="8"></td>
        <td style="text-align:center;background:#f0fdf4;border-radius:10px;padding:16px 8px;">
          <p style="margin:0;color:#22c55e;font-size:28px;font-weight:800;">+{new_today}</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Added Today</p>
        </td>
        <td width="8"></td>
        <td style="text-align:center;background:#fef2f2;border-radius:10px;padding:16px 8px;">
          <p style="margin:0;color:#ef4444;font-size:28px;font-weight:800;">{hot_leads}</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Hot Leads</p>
        </td>
        <td width="8"></td>
        <td style="text-align:center;background:#fffbeb;border-radius:10px;padding:16px 8px;">
          <p style="margin:0;color:#f59e0b;font-size:28px;font-weight:800;">{avg}</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Avg Score</p>
        </td>
      </tr>
    </table>
  </td></tr>
  <tr><td style="padding:16px 40px;border-top:1px solid #f1f5f9;text-align:center;">
    <p style="margin:0;color:#cbd5e1;font-size:11px;">&copy; 2025 OrionLead AI &middot; Disable in Settings &rarr; Notifications.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
    text = f"Daily Digest ({date_str}): {total_leads} total, +{new_today} today, {hot_leads} hot, avg {avg}/100"
    return _send(to_email, f'OrionLead AI Daily Digest — {date_str}', html, text)
