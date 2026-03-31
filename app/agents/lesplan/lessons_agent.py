from __future__ import annotations

from typing import cast

from pydantic_ai import Agent

from ._agent_base import MODEL_NAME, configure_env
from .prompts import _LESSONS_SYSTEM_PROMPT
from .types import GeneratedLessons

_lessons_agent: Agent[None, GeneratedLessons] | None = None


def get_lessons_agent() -> Agent[None, GeneratedLessons]:
    global _lessons_agent
    if _lessons_agent is None:
        configure_env()
        _lessons_agent = cast(
            Agent[None, GeneratedLessons],
            Agent(
                MODEL_NAME,
                output_type=GeneratedLessons,
                system_prompt=_LESSONS_SYSTEM_PROMPT,
            ),
        )
    return _lessons_agent
