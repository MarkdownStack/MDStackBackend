"""Transactional email via the Mailgun HTTP API — moved from app/email.py.

Only two emails exist right now — "verify your address" (registration) and
"reset your password" (forgot-password) — kept as their own module (rather
than inlined into service.py) so a future email has somewhere obvious to
live alongside them.

Config now comes from Settings (app/core/config.py) instead of a raw
os.getenv() call at import time — same defaults, same best-effort
"unconfigured -> skip and log a warning, never raise" contract.
"""

import logging

import httpx

from ...core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


def _verification_email_html(to_email: str, verify_link: str) -> str:
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;color:#2b2b2b;">
      <h1 style="font-size:20px;margin:0 0 16px;color:#111;">Confirm your email</h1>
      <p style="font-size:14px;line-height:1.6;margin:0 0 24px;color:#555;">
        Welcome to MarkdownStack! Confirm <strong>{to_email}</strong> to activate
        your account. This link expires in 24 hours.
      </p>
      <p style="margin:0 0 24px;">
        <a href="{verify_link}"
           style="display:inline-block;background:#d8a657;color:#1a1408;padding:12px 22px;
                  border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">
          Verify email address
        </a>
      </p>
      <p style="font-size:12px;line-height:1.5;color:#999;margin:0;">
        Or paste this link into your browser:<br>
        <a href="{verify_link}" style="color:#999;">{verify_link}</a>
      </p>
      <p style="font-size:12px;line-height:1.5;color:#999;margin:24px 0 0;">
        Didn't sign up for MarkdownStack? You can safely ignore this email.
      </p>
    </div>
    """


def _password_reset_email_html(to_email: str, reset_link: str) -> str:
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;color:#2b2b2b;">
      <h1 style="font-size:20px;margin:0 0 16px;color:#111;">Reset your password</h1>
      <p style="font-size:14px;line-height:1.6;margin:0 0 24px;color:#555;">
        We got a request to reset the password for <strong>{to_email}</strong>.
        This link expires in 1 hour. If you didn't ask for this, you can
        safely ignore this email — your password won't change.
      </p>
      <p style="margin:0 0 24px;">
        <a href="{reset_link}"
           style="display:inline-block;background:#d8a657;color:#1a1408;padding:12px 22px;
                  border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">
          Reset password
        </a>
      </p>
      <p style="font-size:12px;line-height:1.5;color:#999;margin:0;">
        Or paste this link into your browser:<br>
        <a href="{reset_link}" style="color:#999;">{reset_link}</a>
      </p>
    </div>
    """


async def send_verification_email(to_email: str, token: str) -> bool:
    """Send the "verify your email" link for `to_email` via Mailgun.

    Returns True/False on whether the send succeeded rather than raising —
    registration should still succeed even if Mailgun is unreachable or
    unconfigured (the user can always hit "resend" once it's fixed), so the
    caller treats this as best-effort and just logs failures here instead
    of surfacing a 500 for something the user didn't directly cause.
    """
    if not settings.mailgun_api_key or not settings.mailgun_uri or not settings.mailgun_from_addr:
        logger.warning(
            "MAILGUN_API_KEY/MAILGUN_URI/MAILGUN_FROM_ADDR not configured — skipping verification email to %s",
            to_email,
        )
        return False

    verify_link = f"{settings.frontend_base_url}/verify-email?token={token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.mailgun_uri,
                auth=("api", settings.mailgun_api_key),
                data={
                    "from": settings.mailgun_from_email,
                    "to": to_email,
                    "subject": "Verify your MarkdownStack email",
                    "html": _verification_email_html(to_email, verify_link),
                    "text": f"Confirm your MarkdownStack account: {verify_link}",
                },
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError:
        logger.exception("Mailgun send failed for verification email to %s", to_email)
        return False


async def send_password_reset_email(to_email: str, token: str) -> bool:
    """Send the "reset your password" link for `to_email` via Mailgun.

    Same best-effort contract as send_verification_email — returns
    True/False, never raises, so a Mailgun outage doesn't turn "forgot
    password" into a 500 for something the user didn't cause.
    """
    if not settings.mailgun_api_key or not settings.mailgun_uri or not settings.mailgun_from_addr:
        logger.warning(
            "MAILGUN_API_KEY/MAILGUN_URI/MAILGUN_FROM_ADDR not configured — skipping password reset email to %s",
            to_email,
        )
        return False

    reset_link = f"{settings.frontend_base_url}/reset-password?token={token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.mailgun_uri,
                auth=("api", settings.mailgun_api_key),
                data={
                    "from": settings.mailgun_from_email,
                    "to": to_email,
                    "subject": "Reset your MarkdownStack password",
                    "html": _password_reset_email_html(to_email, reset_link),
                    "text": f"Reset your MarkdownStack password: {reset_link}",
                },
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError:
        logger.exception("Mailgun send failed for password reset email to %s", to_email)
        return False
