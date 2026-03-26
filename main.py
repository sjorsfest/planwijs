import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import dispose_engine
from app.logging_config import configure_logging
from app.routes import auth, users, events, methods, books, classes, subjects, lesplan

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
app.include_router(methods.router)
app.include_router(books.router)
app.include_router(classes.router)
app.include_router(subjects.router)
app.include_router(lesplan.router)

logger.info("Application started")
