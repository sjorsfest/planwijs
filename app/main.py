import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import get_current_user
from app.config import settings
from app.database import check_db_health, dispose_engine
from app.logging_config import configure_logging
from app.middleware import RequestContextMiddleware, register_error_handlers
from app.routes import auth, books, calendar, classes, classrooms, lesplan, methods, subjects, users

configure_logging(debug=settings.debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await dispose_engine()


app = FastAPI(lifespan=lifespan)

# --- Middleware (outermost first) ---

# Request ID + timing (raw ASGI — safe for streaming / SSE)
app.add_middleware(RequestContextMiddleware)  # type: ignore[arg-type]

# CORS
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Error handlers ---
register_error_handlers(app)

# --- Routers ---
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(classrooms.router)
app.include_router(methods.router, dependencies=[Depends(get_current_user)])
app.include_router(books.router, dependencies=[Depends(get_current_user)])
app.include_router(classes.router)
app.include_router(subjects.router, dependencies=[Depends(get_current_user)])
app.include_router(lesplan.router)
app.include_router(lesplan.preparation_todo_router)
app.include_router(calendar.router)

logger.info("Application started", extra={"environment": settings.environment})


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint that verifies database connectivity."""
    try:
        await check_db_health()
    except Exception:
        return {"status": "unhealthy", "database": "unreachable"}
    return {"status": "healthy", "database": "connected"}
