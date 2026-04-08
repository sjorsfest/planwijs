from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
import logging
from typing import TypeVar

from sqlalchemy.exc import DBAPIError, InterfaceError as SAInterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, text

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    future=True,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_recycle=settings.database_pool_recycle,
)
SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()


async def create_db_and_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


T = TypeVar("T")
ReadOperation = Callable[[AsyncSession], Awaitable[T]]

_RETRYABLE_CONNECTION_MESSAGES = (
    "connection is closed",
    "connection was closed",
    "closed the connection unexpectedly",
    "terminating connection",
)


def _is_retryable_disconnect_error(exc: Exception) -> bool:
    if isinstance(exc, DBAPIError) and exc.connection_invalidated:
        return True

    for candidate in _iter_exception_chain(exc):
        message = str(candidate).lower()
        if any(text in message for text in _RETRYABLE_CONNECTION_MESSAGES):
            return True
        if isinstance(candidate, (SAInterfaceError, OperationalError)) and "connection" in message:
            return True
    return False


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    queue: list[BaseException] = [exc]
    while queue:
        current = queue.pop(0)
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)
        yield current

        original = getattr(current, "orig", None)
        if isinstance(original, BaseException):
            queue.append(original)

        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            queue.append(cause)

        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException):
            queue.append(context)


async def run_read_with_retry(operation: ReadOperation[T]) -> T:
    try:
        async with get_session_context() as session:
            return await operation(session)
    except Exception as exc:
        if not _is_retryable_disconnect_error(exc):
            raise
        logger.warning("Retrying read operation after transient database disconnect")

    async with get_session_context() as session:
        return await operation(session)


async def check_db_health() -> bool:
    """Check database connectivity. Returns True if healthy."""
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
        return True
