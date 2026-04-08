import logging
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.database import get_session
from app.exceptions import ValidationError
from app.models import User

from .util import _build_redirect_url, _create_access_token, _decode_state, _encode_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/google/start")
async def login_with_google(redirect_uri: str = Query(..., min_length=1)):
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        logger.warning("Invalid redirect_uri in /google/start: %s", redirect_uri)
        raise ValidationError("Invalid redirect_uri")

    logger.info("Starting Google OAuth flow, redirect_uri=%s", redirect_uri)
    state = _encode_state(redirect_uri)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}")


@router.get("/google/callback")
async def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    if state is None:
        logger.warning("OAuth callback received without state parameter")
        raise ValidationError("Missing state")

    try:
        redirect_uri = _decode_state(state)
    except ValueError as exc:
        logger.warning("OAuth state validation failed: %s", exc)
        raise ValidationError(str(exc))

    if error:
        logger.warning("OAuth provider returned error: %s", error)
        return RedirectResponse(_build_redirect_url(redirect_uri, {"error": error}))
    if not code:
        logger.warning("OAuth callback missing code parameter")
        return RedirectResponse(_build_redirect_url(redirect_uri, {"error": "missing_code"}))

    logger.debug("Exchanging OAuth code for token")
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
            logger.error("Token exchange failed: status=%s", token_resp.status_code)
            return RedirectResponse(_build_redirect_url(redirect_uri, {"error": "token_exchange_failed"}))

        logger.debug("Fetching Google user profile")
        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_resp.json()['access_token']}"},
        )
        if user_resp.is_error:
            logger.error("User profile fetch failed: status=%s", user_resp.status_code)
            return RedirectResponse(_build_redirect_url(redirect_uri, {"error": "profile_fetch_failed"}))

    info = user_resp.json()
    google_id: str = info["id"]
    email: str = info["email"]
    name: str = info.get("name", email)

    result = await session.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if not user:
        logger.info("Creating new user: email=%s", email)
        user = User(name=name, email=email, google_id=google_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        logger.info("Existing user logged in: id=%s email=%s", user.id, email)

    token = _create_access_token(str(user.id), email=user.email, name=user.name)
    logger.debug("Issued access token for user id=%s", user.id)
    return RedirectResponse(_build_redirect_url(redirect_uri, {"access_token": token}))
