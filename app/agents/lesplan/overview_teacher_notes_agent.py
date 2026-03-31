from __future__ import annotations

from typing import cast

from pydantic_ai import Agent

from ._agent_base import MODEL_NAME, configure_env
from .prompts import _OVERVIEW_NOTES_SYSTEM_PROMPT
from .types import GeneratedOverviewTeacherNotes

_overview_teacher_notes_agent: Agent[None, GeneratedOverviewTeacherNotes] | None = None


def get_overview_teacher_notes_agent() -> Agent[None, GeneratedOverviewTeacherNotes]:
    global _overview_teacher_notes_agent
    if _overview_teacher_notes_agent is None:
        configure_env()
        _overview_teacher_notes_agent = cast(
            Agent[None, GeneratedOverviewTeacherNotes],
            Agent(
                MODEL_NAME,
                output_type=GeneratedOverviewTeacherNotes,
                system_prompt=_OVERVIEW_NOTES_SYSTEM_PROMPT,
            ),
        )
    return _overview_teacher_notes_agent
