"""Shared agent setup for lesplan models."""

from __future__ import annotations

import os

from app.config import settings

MODEL_NAME = "openrouter:xiaomi/mimo-v2-pro"


def configure_env() -> None:
    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)
