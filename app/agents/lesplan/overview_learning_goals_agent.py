from __future__ import annotations

from typing import cast

from pydantic_ai import Agent

from ._agent_base import MODEL_NAME, configure_env
from .prompts import _OVERVIEW_LEARNING_GOALS_SYSTEM_PROMPT
from .types import GeneratedOverviewLearningGoals

_overview_learning_goals_agent: Agent[None, GeneratedOverviewLearningGoals] | None = None


def get_overview_learning_goals_agent() -> Agent[None, GeneratedOverviewLearningGoals]:
    global _overview_learning_goals_agent
    if _overview_learning_goals_agent is None:
        configure_env()
        _overview_learning_goals_agent = cast(
            Agent[None, GeneratedOverviewLearningGoals],
            Agent(
                MODEL_NAME,
                output_type=GeneratedOverviewLearningGoals,
                system_prompt=_OVERVIEW_LEARNING_GOALS_SYSTEM_PROMPT,
            ),
        )
    return _overview_learning_goals_agent
