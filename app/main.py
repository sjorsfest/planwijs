import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.auth import get_current_user
from app.database import dispose_engine, check_db_health
from app.logging_config import configure_logging
from app.routes import auth, users, events, methods, books, classes, subjects, lesplan, calendar

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await dispose_engine()


app = FastAPI(lifespan=lifespan)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(events.router)
app.include_router(methods.router, dependencies=[Depends(get_current_user)])
app.include_router(books.router, dependencies=[Depends(get_current_user)])
app.include_router(classes.router)
app.include_router(subjects.router, dependencies=[Depends(get_current_user)])
app.include_router(lesplan.router)
app.include_router(lesplan.preparation_todo_router)
app.include_router(calendar.router)

logger.info("Application started")



@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint that verifies database connectivity."""
    try:
        await check_db_health()
    except Exception:
        return {"status": "unhealthy", "database": "unreachable"}
    return {"status": "healthy", "database": "connected"}
