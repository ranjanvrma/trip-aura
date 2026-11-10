from __future__ import annotations

import hmac
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import CsrfError, NotAuthenticatedError, RateLimitedError
from app.core.ratelimit import limiter
from app.core.security import UNSAFE_METHODS
from app.db.database import get_db
from app.db.models import AuthSession, User
from app.nlp.registry import get_semantic
from app.services.auth_service import SESSION_COOKIE, load_session
from app.services.itinerary_service import ItineraryService
from app.services.providers import get_providers


@lru_cache
def _service(mode: str, key_present: bool) -> ItineraryService:
    return ItineraryService(get_providers(), get_settings(), semantic=get_semantic())


def get_itinerary_service() -> ItineraryService:
    s = get_settings()
    return _service(s.data_mode.value, s.google_configured)


# ---------------------------------------------------------------------------- auth
@dataclass
class Auth:
    user: User
    session: AuthSession

    @property
    def is_admin(self) -> bool:
        return self.user.role == "admin"


def optional_auth(request: Request, db: Session = Depends(get_db)) -> Auth | None:
    found = load_session(db, request.cookies.get(SESSION_COOKIE))
    return Auth(user=found[1], session=found[0]) if found else None


def require_auth(request: Request, auth: Auth | None = Depends(optional_auth)) -> Auth:
    """A valid session; unsafe methods must also echo its CSRF token in X-CSRF-Token."""
    if auth is None:
        raise NotAuthenticatedError("Sign in to continue")
    if request.method.upper() in UNSAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not hmac.compare_digest(sent.encode(), auth.session.csrf_token.encode()):
            raise CsrfError("Missing or invalid CSRF token")
    return auth


def generation_limit(auth: Auth = Depends(require_auth)) -> Auth:
    """Trip generation (create / preview / regenerate): 6 per minute per user."""
    if get_settings().rate_limit_enabled:
        wait = limiter.hit("generate", f"user:{auth.user.id}")
        if wait:
            raise RateLimitedError(wait, "Too many trips generated in a short time, please wait a moment")
    return auth
