import logging

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.exceptions import AuthenticationError
from app.models.user import User

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise AuthenticationError("Invalid token")
    except JWTError:
        raise AuthenticationError("Invalid token")

    user = await session.get(User, user_id)
    if user is None:
        raise AuthenticationError("User not found")
    return user
