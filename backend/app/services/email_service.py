"""Delivery of sign-in codes: Resend HTTPS API, or the server log in development."""
from __future__ import annotations

import html
import logging
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import EmailFailedError, EmailNotConfiguredError

log = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"
SUBJECT = "Your TripAura sign-in code"


class Mailer(Protocol):
    def send_code(self, email: str, code: str, expires_minutes: int) -> None: ...


def code_message(code: str, expires_minutes: int) -> tuple[str, str]:
    """(plain text, HTML) bodies. The code is 6 digits; it is escaped anyway."""
    text = (f"Your TripAura sign-in code is {code}\n\n"
            f"It expires in {expires_minutes} minutes and can be used once.\n"
            "If you did not request it, you can ignore this email.\n")
    c = html.escape(code)
    body = (f'<p>Your TripAura sign-in code is:</p>'
            f'<p style="font-size:28px;font-weight:bold;letter-spacing:4px;font-family:monospace">{c}</p>'
            f'<p>It expires in {expires_minutes} minutes and can be used once.</p>'
            '<p style="color:#666">If you did not request it, you can ignore this email.</p>')
    return text, body


class ResendMailer:
    def __init__(self, api_key: str, sender: str, transport: httpx.BaseTransport | None = None,
                 timeout: float = 10.0):
        self._key = api_key
        self._from = sender
        self._transport = transport
        self._timeout = timeout

    def send_code(self, email: str, code: str, expires_minutes: int) -> None:
        text, body = code_message(code, expires_minutes)
        payload = {"from": self._from, "to": [email], "subject": SUBJECT, "text": text, "html": body}
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as http:
                r = http.post(RESEND_URL, json=payload, headers={"Authorization": f"Bearer {self._key}"})
        except httpx.HTTPError as exc:
            log.error("Resend request failed (%s)", exc.__class__.__name__)
            raise EmailFailedError("Could not send the sign-in email, please try again") from exc
        if r.status_code >= 300:
            log.error("Resend returned HTTP %s", r.status_code)   # body may echo the address; not logged
            raise EmailFailedError("Could not send the sign-in email, please try again")


class ConsoleMailer:
    """Development only: writes the code to the server log instead of sending it."""

    def send_code(self, email: str, code: str, expires_minutes: int) -> None:
        log.warning("DEV ONLY sign-in code for %s: %s", email, code)


def build_mailer(settings: Settings) -> Mailer:
    if settings.email_configured:
        return ResendMailer(settings.resend_api_key.strip(), settings.email_from)
    if settings.is_production:
        raise EmailNotConfiguredError("Email sign-in is not configured on this server")
    return ConsoleMailer()


def get_mailer() -> Mailer:
    """FastAPI dependency (overridden in tests)."""
    return build_mailer(get_settings())
