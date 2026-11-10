"""Email one-time-code sign-in and server-side sessions.

- Codes: 6 random digits (secrets), stored only as HMAC-SHA256(SECRET_KEY, email:code), valid for
  10 minutes, at most 5 verify attempts, single use; a new request replaces earlier unused codes.
- Sessions: 32-byte random token in an HttpOnly cookie; the database stores its SHA-256, a CSRF token,
  the user and an absolute expiry (SESSION_DAYS).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import InvalidCodeError
from app.core.timeutil import as_utc, utc_now
from app.db.models import AuthSession, IdempotencyRecord, LoginCode, Trip, User

CODE_TTL_SECONDS = 600
CODE_MAX_ATTEMPTS = 5
SESSION_COOKIE = "ta_session"
INVALID_CODE_MESSAGE = "The code is wrong or has expired. Request a new code and try again."

# Pragmatic address syntax check (RFC 5321 lengths, dot-atom local part, LDH domain labels).
_EMAIL = re.compile(
    r"^(?=.{3,254}$)(?=[^@]{1,64}@)[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")


def normalise_email(value: str) -> str:
    v = value.strip().lower()
    if not _EMAIL.match(v):
        raise ValueError("Enter a valid email address")
    return v


def code_hash(settings: Settings, email: str, code: str) -> str:
    return hmac.new(settings.signing_key, f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_code(db: Session, settings: Settings, email: str) -> str:
    """Create a fresh code for `email` (replacing earlier unused ones) and return it in clear text."""
    t = utc_now()
    db.execute(delete(LoginCode).where(LoginCode.email == email))
    db.execute(delete(LoginCode).where(LoginCode.expires_at < t - dt.timedelta(days=1)))
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(LoginCode(email=email, code_hash=code_hash(settings, email, code), created_at=t,
                     expires_at=t + dt.timedelta(seconds=CODE_TTL_SECONDS)))
    db.commit()
    return code


def check_code(db: Session, settings: Settings, email: str, code: str) -> None:
    """Consume the code or raise InvalidCodeError (same message for wrong, expired, used, exhausted)."""
    row = db.scalars(select(LoginCode).where(LoginCode.email == email, LoginCode.used_at.is_(None))
                     .order_by(LoginCode.id.desc()).limit(1)).first()
    if row is None or as_utc(row.expires_at) <= utc_now() or row.attempts >= CODE_MAX_ATTEMPTS:
        raise InvalidCodeError(INVALID_CODE_MESSAGE)
    # Conditional updates keep the attempt limit and single use exact under concurrent requests.
    counted = db.execute(update(LoginCode).where(LoginCode.id == row.id, LoginCode.used_at.is_(None),
                                                 LoginCode.attempts < CODE_MAX_ATTEMPTS)
                         .values(attempts=LoginCode.attempts + 1)).rowcount
    db.commit()
    if not counted or not hmac.compare_digest(row.code_hash, code_hash(settings, email, code)):
        raise InvalidCodeError(INVALID_CODE_MESSAGE)
    used = db.execute(update(LoginCode).where(LoginCode.id == row.id, LoginCode.used_at.is_(None))
                      .values(used_at=utc_now())).rowcount
    db.commit()
    if not used:
        raise InvalidCodeError(INVALID_CODE_MESSAGE)


def upsert_user(db: Session, settings: Settings, email: str) -> User:
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(email=email)
        db.add(user)
    user.role = "admin" if email in settings.admin_email_set else "user"
    user.last_login_at = utc_now()
    db.commit()
    return user


@dataclass
class NewSession:
    token: str
    record: AuthSession


def create_session(db: Session, settings: Settings, user: User) -> NewSession:
    t = utc_now()
    db.execute(delete(AuthSession).where(AuthSession.expires_at < t))   # housekeeping
    token = secrets.token_urlsafe(32)
    rec = AuthSession(token_hash=token_hash(token), csrf_token=secrets.token_urlsafe(32), user_id=user.id,
                      created_at=t, expires_at=t + dt.timedelta(days=settings.session_days))
    db.add(rec)
    db.commit()
    return NewSession(token=token, record=rec)


def load_session(db: Session, token: str | None) -> tuple[AuthSession, User] | None:
    """The live session and its user, or None. Expired sessions are deleted."""
    if not token or len(token) > 200:
        return None
    rec = db.scalars(select(AuthSession).where(AuthSession.token_hash == token_hash(token))).first()
    if rec is None:
        return None
    if as_utc(rec.expires_at) <= utc_now():
        db.delete(rec)
        db.commit()
        return None
    user = db.get(User, rec.user_id)
    return (rec, user) if user is not None else None


def delete_session(db: Session, rec: AuthSession) -> None:
    db.delete(rec)
    db.commit()


def delete_account(db: Session, user_id: int) -> None:
    """Remove everything stored for a user, in one transaction."""
    email = db.scalars(select(User.email).where(User.id == user_id)).first()
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    db.execute(delete(Trip).where(Trip.user_id == user_id))
    db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id))
    if email:
        db.execute(delete(LoginCode).where(LoginCode.email == email))
    db.execute(delete(User).where(User.id == user_id))
    db.commit()


def set_session_cookie(response, settings: Settings, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_days * 86400, path="/",
                        httponly=True, secure=settings.cookie_secure_effective, samesite=settings.cookie_samesite)


def clear_session_cookie(response, settings: Settings) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=settings.cookie_secure_effective,
                           samesite=settings.cookie_samesite)

