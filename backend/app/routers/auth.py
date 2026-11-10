"""Email one-time-code sign-in.

request-code always answers 202 for a well-formed address (whether or not an account exists);
accounts are created on the first successful verify.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ratelimit import enforce
from app.db.database import get_db
from app.db.models import User
from app.routers.deps import Auth, require_auth
from app.services import auth_service as svc
from app.services.email_service import Mailer, get_mailer

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class EmailBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return svc.normalise_email(v)


class VerifyBody(EmailBody):
    code: str = Field(pattern=r"^[0-9]{6}$")


class UserOut(BaseModel):
    id: int
    email: str
    role: str


class CodeSent(BaseModel):
    sent: bool
    expires_in: int


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


def _session_out(user: User, csrf_token: str) -> SessionOut:
    return SessionOut(user=UserOut(id=user.id, email=user.email, role=user.role), csrf_token=csrf_token)


def _signed_out() -> Response:
    """204 that also clears the session cookie in the browser."""
    response = Response(status_code=204)
    svc.clear_session_cookie(response, get_settings())
    return response


@router.post("/request-code", status_code=202, response_model=CodeSent)
def request_code(body: EmailBody, db: Session = Depends(get_db), mailer: Mailer = Depends(get_mailer)) -> CodeSent:
    enforce("auth_email", body.email, "Too many codes requested for this address, please wait")
    code = svc.issue_code(db, get_settings(), body.email)
    mailer.send_code(body.email, code, svc.CODE_TTL_SECONDS // 60)
    return CodeSent(sent=True, expires_in=svc.CODE_TTL_SECONDS)


@router.post("/verify", response_model=SessionOut)
def verify(body: VerifyBody, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    s = get_settings()
    svc.check_code(db, s, body.email, body.code)
    user = svc.upsert_user(db, s, body.email)
    new = svc.create_session(db, s, user)
    svc.set_session_cookie(response, s, new.token)
    log.info("User %s signed in (%s)", user.id, user.role)
    return _session_out(user, new.record.csrf_token)


@router.get("/me", response_model=SessionOut)
def me(auth: Auth = Depends(require_auth)) -> SessionOut:
    return _session_out(auth.user, auth.session.csrf_token)


@router.post("/logout", status_code=204)
def logout(auth: Auth = Depends(require_auth), db: Session = Depends(get_db)) -> Response:
    svc.delete_session(db, auth.session)
    return _signed_out()


@router.delete("/account", status_code=204)
def delete_account(auth: Auth = Depends(require_auth), db: Session = Depends(get_db)) -> Response:
    """Permanently delete the caller's account: user row, sessions, trips and idempotency records."""
    user_id = auth.user.id
    svc.delete_account(db, user_id)
    log.info("User %s deleted their account", user_id)
    return _signed_out()
