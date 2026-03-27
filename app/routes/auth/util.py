import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from jose import jwt

from app.config import settings

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
    payload = json.dumps(
        {"redirect_uri": redirect_uri, "exp": int(time.time()) + STATE_TTL_SECONDS},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    sig = hmac.new(settings.oauth_state_secret.encode(), payload, hashlib.sha256).digest()
    return f"{_b64url_encode(payload)}.{_b64url_encode(sig)}"


def _decode_state(state: str) -> str:
    try:
        encoded_payload, encoded_sig = state.split(".", 1)
        payload_bytes = _b64url_decode(encoded_payload)
        sig_bytes = _b64url_decode(encoded_sig)
    except Exception as exc:
        raise ValueError("invalid_state") from exc

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


def _build_redirect_url(base_uri: str, params: dict[str, str]) -> str:
    parsed = urlparse(base_uri)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update(params)
    return urlunparse(parsed._replace(query=urlencode(current)))
