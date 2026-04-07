"""Optional SMTP: email itinerary after booking."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from backend.config import settings

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool((settings.smtp_host or "").strip() and (settings.smtp_from or "").strip())


def _send_sync(to_address: str, subject: str, body: str) -> str:
    """
    Send a plain-text email. Returns an empty string on success, or a short error message.
    """
    host = (settings.smtp_host or "").strip()
    from_addr = (settings.smtp_from or "").strip()
    if not host or not from_addr:
        return "SMTP is not configured."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_address.strip()
    msg.set_content(body)

    user = (settings.smtp_user or "").strip()
    password = settings.smtp_password or ""

    try:
        if settings.smtp_ssl:
            with smtplib.SMTP_SSL(host, settings.smtp_port, timeout=45) as server:
                if user:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, settings.smtp_port, timeout=45) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if user:
                    server.login(user, password)
                server.send_message(msg)
    except OSError as e:
        logger.warning("SMTP send failed: %s", e)
        return str(e) or "SMTP connection failed."
    except smtplib.SMTPException as e:
        logger.warning("SMTP send failed: %s", e)
        return str(e) or "SMTP error."

    return ""


async def send_itinerary_email(to_address: str, subject: str, body: str) -> str:
    """Async wrapper; returns empty string on success, else an error message."""
    return await asyncio.to_thread(_send_sync, to_address, subject, body)
