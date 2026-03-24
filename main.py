import logging

from fastapi import FastAPI

from app.logging_config import configure_logging
from app.routes import auth, users, events

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(events.router)

logger.info("Application started")
