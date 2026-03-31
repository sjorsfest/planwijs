from __future__ import annotations

from typing import cast

from pydantic_ai import Agent

from ._agent_base import MODEL_NAME, configure_env
from .prompts import _OVERVIEW_SEQUENCE_SYSTEM_PROMPT
from .types import GeneratedOverviewSequence

_overview_sequence_agent: Agent[None, GeneratedOverviewSequence] | None = None


def get_overview_sequence_agent() -> Agent[None, GeneratedOverviewSequence]:
    global _overview_sequence_agent
    if _overview_sequence_agent is None:
        configure_env()
        _overview_sequence_agent = cast(
            Agent[None, GeneratedOverviewSequence],
            Agent(
                MODEL_NAME,
                output_type=GeneratedOverviewSequence,
                system_prompt=_OVERVIEW_SEQUENCE_SYSTEM_PROMPT,
            ),
        )
    return _overview_sequence_agent
