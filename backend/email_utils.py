"""
Email utilities — SMTP-based sending with console fallback for dev.

Configure via environment variables:
  SMTP_HOST      (default: "" — triggers console-only mode)
  SMTP_PORT      (default: 587)
  SMTP_USER
  SMTP_PASSWORD
  SMTP_FROM      (default: noreply@resume-engine.local)
  FRONTEND_URL   (default: http://localhost)

For local development, use Mailtrap (smtp.mailtrap.io) or leave SMTP_HOST
empty to have emails printed to the server console instead.
"""

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST        = os.getenv("SMTP_HOST",        "")
SMTP_PORT        = int(os.getenv("SMTP_PORT",    "587"))
SMTP_USER        = os.getenv("SMTP_USER",        "")
SMTP_PASS        = os.getenv("SMTP_PASSWORD",    "")
SMTP_FROM        = os.getenv("SMTP_FROM",        "noreply@resume-engine.local")
SMTP_SKIP_VERIFY = os.getenv("SMTP_SKIP_VERIFY", "false").lower() == "true"
FRONTEND_URL     = os.getenv("FRONTEND_URL",     "http://localhost")


# ── Core sender ───────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, html_body: str) -> None:
    """
    Send an HTML email.  Falls back to console output when SMTP is not
    configured so development works without an email server.
    """
    if not SMTP_HOST or not SMTP_USER:
        _console_fallback(to, subject, html_body)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_FROM
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html"))

    # Use strict TLS in production; permissive only when SMTP_SKIP_VERIFY=true
    # (needed for Mailtrap sandbox and some self-signed SMTP servers)
    ctx = ssl.create_default_context()
    if SMTP_SKIP_VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            # Force AUTH PLAIN — CRAM-MD5 triggers lockout on Mailtrap sandbox
            if "auth" in server.esmtp_features:
                server.esmtp_features["auth"] = "PLAIN LOGIN"
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to], msg.as_string())
        print(f"📧 Email sent → {to} [{subject}]")
    except Exception as exc:
        print(f"⚠️  Email send failed to {to}: {exc}")
        _console_fallback(to, subject, html_body)


def _console_fallback(to: str, subject: str, body: str) -> None:
    sep = "─" * 60
    print(f"\n{sep}\n📧 EMAIL (console mode)\nTo:      {to}\nSubject: {subject}\n{sep}\n{body}\n{sep}\n")


# ── Email templates ───────────────────────────────────────────────────────────

def send_welcome_email(to: str, full_name: str, temp_password: str) -> None:
    """Sent when an Admin creates a new user account (US-006)."""
    send_email(
        to      = to,
        subject = "Welcome to Resume Engine — Your Account Details",
        html_body = f"""
<p>Hi <strong>{full_name}</strong>,</p>
<p>Your account has been created on <strong>Resume Engine</strong>.</p>
<table style="border-collapse:collapse;margin:16px 0">
  <tr><td style="padding:4px 12px 4px 0;color:#555">Email</td>
      <td><strong>{to}</strong></td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#555">Temporary Password</td>
      <td><code style="background:#f3f4f6;padding:2px 6px;border-radius:4px">{temp_password}</code></td></tr>
</table>
<p>Please log in at <a href="{FRONTEND_URL}">{FRONTEND_URL}</a> and
<strong>change your password immediately</strong>.</p>
<p style="color:#888;font-size:12px">If you did not expect this email, contact your system administrator.</p>
""",
    )


def send_password_reset_email(to: str, full_name: str, reset_token: str) -> None:
    """Sent for the self-service forgot-password flow (US-004)."""
    reset_url = f"{FRONTEND_URL}/reset-password?token={reset_token}"
    send_email(
        to      = to,
        subject = "Resume Engine — Password Reset Request",
        html_body = f"""
<p>Hi <strong>{full_name}</strong>,</p>
<p>A password reset was requested for your account.</p>
<p style="margin:20px 0">
  <a href="{reset_url}"
     style="background:#2563eb;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none">
    Reset My Password
  </a>
</p>
<p style="color:#555;font-size:13px">Or copy this link: <code>{reset_url}</code></p>
<p style="color:#888;font-size:12px">This link expires in <strong>1 hour</strong>.
If you did not request a password reset, you can safely ignore this email.</p>
""",
    )


def send_admin_reset_email(to: str, full_name: str, temp_password: str) -> None:
    """Sent when an Admin resets another user's password (US-010)."""
    send_email(
        to      = to,
        subject = "Resume Engine — Your Password Has Been Reset",
        html_body = f"""
<p>Hi <strong>{full_name}</strong>,</p>
<p>An administrator has reset your account password.</p>
<table style="border-collapse:collapse;margin:16px 0">
  <tr><td style="padding:4px 12px 4px 0;color:#555">New Temporary Password</td>
      <td><code style="background:#f3f4f6;padding:2px 6px;border-radius:4px">{temp_password}</code></td></tr>
</table>
<p>Please log in at <a href="{FRONTEND_URL}">{FRONTEND_URL}</a> and
<strong>change your password immediately</strong>.</p>
<p style="color:#888;font-size:12px">If you did not expect this change, contact your system administrator immediately.</p>
""",
    )
