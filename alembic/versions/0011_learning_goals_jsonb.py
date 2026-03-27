"""store lesplan_overview.learning_goals as JSONB array

Revision ID: 0011_learning_goals_jsonb
Revises: 0010_learning_progression
Create Date: 2026-03-26 23:20:00.000000

"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_learning_goals_jsonb"
down_revision: Union[str, Sequence[str], None] = "0010_learning_progression"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_list(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text:
            normalized.append(text)
    return normalized


def _parse_learning_goals(raw: Any) -> list[str]:
    if raw is None:
        return []

    if isinstance(raw, list):
        return _normalize_list(raw)

    if isinstance(raw, (tuple, set)):
        return _normalize_list(list(raw))

    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="ignore")
    else:
        text = str(raw)

    stripped = text.strip()
    if not stripped:
        return []

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        return _normalize_list(parsed)
    if isinstance(parsed, str):
        parsed_str = parsed.strip()
        return [parsed_str] if parsed_str else []

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        line = line.strip()
        if line:
            cleaned_lines.append(line)

    if len(cleaned_lines) > 1:
        return cleaned_lines
    if cleaned_lines:
        return [cleaned_lines[0]]
    return []


def upgrade() -> None:
    op.add_column(
        "lesplan_overview",
        sa.Column("learning_goals_tmp", postgresql.JSONB(), nullable=False, server_default="[]"),
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, learning_goals FROM lesplan_overview")).mappings().all()
    for row in rows:
        goals = _parse_learning_goals(row["learning_goals"])
        bind.execute(
            sa.text(
                "UPDATE lesplan_overview "
                "SET learning_goals_tmp = CAST(:learning_goals AS jsonb) "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "learning_goals": json.dumps(goals, ensure_ascii=False),
            },
        )

    op.drop_column("lesplan_overview", "learning_goals")
    op.alter_column(
        "lesplan_overview",
        "learning_goals_tmp",
        new_column_name="learning_goals",
        existing_type=postgresql.JSONB(),
        nullable=False,
        server_default="[]",
    )


def downgrade() -> None:
    op.add_column(
        "lesplan_overview",
        sa.Column(
            "learning_goals_text",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, learning_goals FROM lesplan_overview")).mappings().all()
    for row in rows:
        goals = _parse_learning_goals(row["learning_goals"])
        bind.execute(
            sa.text(
                "UPDATE lesplan_overview "
                "SET learning_goals_text = :learning_goals "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "learning_goals": "\n".join(goals),
            },
        )

    op.drop_column("lesplan_overview", "learning_goals")
    op.alter_column(
        "lesplan_overview",
        "learning_goals_text",
        new_column_name="learning_goals",
        existing_type=sqlmodel.sql.sqltypes.AutoString(),
        nullable=False,
        server_default="",
    )
