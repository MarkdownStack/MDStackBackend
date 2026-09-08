"""Transactional email via the Mailgun HTTP API.

Only one email exists right now — the "verify your address" link sent on
registration (see routers/auth.py) — but this is kept as its own module
(rather than inlined in the router) so a password-reset email or similar
later on has somewhere obvious to live alongside it.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY", "")
# The full "…/v3/<domain>/messages" endpoint, not just a domain — this repo's
# actual Mailgun setup hands out the whole URI directly rather than a bare
# domain, so this module posts straight to it instead of assembling one from
# an API-base + domain pair.
MAILGUN_URI = os.getenv("MAILGUN_URI", "")
MAILGUN_FROM_ADDR = os.getenv("MAILGUN_FROM_ADDR", "")
MAILGUN_FROM_EMAIL = f"MarkdownStack <{MAILGUN_FROM_ADDR}>" if MAILGUN_FROM_ADDR else ""

# Used to build the link embedded in the email — must point at wherever the
# frontend is actually served (not the backend), since /verify-email is a
# frontend route that then calls the backend API itself.
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")


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


async def send_verification_email(to_email: str, token: str) -> bool:
    """Send the "verify your email" link for `to_email` via Mailgun.

    Returns True/False on whether the send succeeded rather than raising —
    registration should still succeed even if Mailgun is unreachable or
    unconfigured (the user can always hit "resend" once it's fixed), so the
    router treats this as best-effort and just logs failures here instead
    of surfacing a 500 for something the user didn't directly cause.
    """
    if not MAILGUN_API_KEY or not MAILGUN_URI or not MAILGUN_FROM_ADDR:
        logger.warning(
            "MAILGUN_API_KEY/MAILGUN_URI/MAILGUN_FROM_ADDR not configured — skipping verification email to %s",
            to_email,
        )
        return False

    verify_link = f"{FRONTEND_BASE_URL}/verify-email?token={token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                MAILGUN_URI,
                auth=("api", MAILGUN_API_KEY),
                data={
                    "from": MAILGUN_FROM_EMAIL,
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
