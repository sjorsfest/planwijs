import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.database import get_session
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
STATE_TTL_SECONDS = 600


def _create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _encode_state(redirect_uri: str) -> str:
    payload = json.dumps({"redirect_uri": redirect_uri, "exp": int(time.time()) + STATE_TTL_SECONDS}, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(settings.oauth_state_secret.encode(), payload, hashlib.sha256).digest()
    return f"{_b64url_encode(payload)}.{_b64url_encode(sig)}"


def _decode_state(state: str) -> str:
    try:
        encoded_payload, encoded_sig = state.split(".", 1)
        payload_bytes = _b64url_decode(encoded_payload)
        sig_bytes = _b64url_decode(encoded_sig)
    except Exception:
        raise ValueError("invalid_state")

    expected_sig = hmac.new(settings.oauth_state_secret.encode(), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(sig_bytes, expected_sig):
        raise ValueError("invalid_state")

    payload = json.loads(payload_bytes.decode())
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("state_expired")

    redirect_uri = payload.get("redirect_uri", "")
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid_redirect_uri")

    return redirect_uri


def _build_redirect_url(base_uri: str, params: dict) -> str:
    parsed = urlparse(base_uri)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update(params)
    return urlunparse(parsed._replace(query=urlencode(current)))


@router.get("/google/start")
async def login_with_google(redirect_uri: str = Query(..., min_length=1)):
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")

    state = _encode_state(redirect_uri)
    params = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/auth?{params}")


@router.get("/google/callback")
async def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    if state is None:
        raise HTTPException(status_code=400, detail="Missing state")

    try:
        redirect_uri = _decode_state(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if error:
        return RedirectResponse(_build_redirect_url(redirect_uri, {"error": error}))
    if not code:
        return RedirectResponse(_build_redirect_url(redirect_uri, {"error": "missing_code"}))

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.is_error:
            return RedirectResponse(_build_redirect_url(redirect_uri, {"error": "token_exchange_failed"}))

        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_resp.json()['access_token']}"},
        )
        if user_resp.is_error:
            return RedirectResponse(_build_redirect_url(redirect_uri, {"error": "profile_fetch_failed"}))

    info = user_resp.json()
    google_id: str = info["id"]
    email: str = info["email"]
    name: str = info.get("name", email)

    result = await session.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(name=name, email=email, google_id=google_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = _create_access_token(str(user.id))
    return RedirectResponse(_build_redirect_url(redirect_uri, {"access_token": token}))
