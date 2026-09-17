from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from taskrelaymcp.config import Principal, public_origin, secure_cookies
from taskrelaymcp.db import session_scope
from taskrelaymcp.models import BrowserSession, MCPKey, User

SESSION_COOKIE = "taskrelay_session"
SESSION_DAYS = 14


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(derived).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_hash = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.urlsafe_b64decode(raw_salt),
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=32,
        )
        return hmac.compare_digest(actual, base64.urlsafe_b64decode(raw_hash))
    except (ValueError, TypeError):
        return False


def new_session(db: Session, user: User) -> str:
    secret = secrets.token_urlsafe(32)
    db.add(
        BrowserSession(
            user_id=user.id,
            token_hash=hash_secret(secret),
            expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS),
        )
    )
    db.flush()
    return secret


def authenticate_mcp(db: Session, authorization: str | None) -> Principal | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    key = db.scalar(
        select(MCPKey).where(
            MCPKey.secret_hash == hash_secret(authorization.removeprefix("Bearer ")),
            MCPKey.revoked_at.is_(None),
        )
    )
    if not key or not key.user.active:
        return None
    return Principal(key.user.id, key.user.username, key.user.is_admin, "MCP", key.id, key.name)


def authenticate_session(db: Session, secret: str | None) -> Principal | None:
    if not secret:
        return None
    browser_session = db.scalar(
        select(BrowserSession).where(
            BrowserSession.token_hash == hash_secret(secret), BrowserSession.expires_at > datetime.now(UTC)
        )
    )
    if not browser_session or not browser_session.user.active:
        return None
    user = browser_session.user
    return Principal(user.id, user.username, user.is_admin, "WEB", cookie_authenticated=True)


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return False
    expected = public_origin()
    if expected:
        return origin.rstrip("/") == expected
    return not secure_cookies() and origin.rstrip("/") == str(request.base_url).rstrip("/")


def same_origin(request: Request) -> None:
    if not public_origin() and secure_cookies():
        raise HTTPException(503, "TASKRELAY_PUBLIC_ORIGIN is required when secure cookies are enabled")
    if not _same_origin(request):
        raise HTTPException(403, "Same-origin request required")


def current_user(
    request: Request, session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None
) -> Principal:
    with session_scope() as db:
        principal = authenticate_session(db, session_token)
    if not principal:
        raise HTTPException(401, "Authentication required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        same_origin(request)
    return principal


def ready_user(principal: Annotated[Principal, Depends(current_user)]) -> Principal:
    with session_scope() as db:
        if db.get(User, principal.user_id).must_change_password:
            raise HTTPException(403, "Password change required")
    return principal


def current_admin(principal: Annotated[Principal, Depends(ready_user)]) -> Principal:
    if not principal.is_admin:
        raise HTTPException(404, "Not Found")
    return principal


CurrentUser = Annotated[Principal, Depends(current_user)]
CurrentAdmin = Annotated[Principal, Depends(current_admin)]
ReadyUser = Annotated[Principal, Depends(ready_user)]
