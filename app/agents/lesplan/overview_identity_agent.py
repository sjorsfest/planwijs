from __future__ import annotations

from typing import cast

from pydantic_ai import Agent

from ._agent_base import MODEL_NAME, configure_env
from .prompts import _OVERVIEW_IDENTITY_SYSTEM_PROMPT
from .types import GeneratedOverviewIdentity

_overview_identity_agent: Agent[None, GeneratedOverviewIdentity] | None = None


def get_overview_identity_agent() -> Agent[None, GeneratedOverviewIdentity]:
    global _overview_identity_agent
    if _overview_identity_agent is None:
        configure_env()
        _overview_identity_agent = cast(
            Agent[None, GeneratedOverviewIdentity],
            Agent(
                MODEL_NAME,
                output_type=GeneratedOverviewIdentity,
                system_prompt=_OVERVIEW_IDENTITY_SYSTEM_PROMPT,
            ),
        )
    return _overview_identity_agent
