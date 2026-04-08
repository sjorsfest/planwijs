from contextlib import asynccontextmanager
import unittest
from unittest.mock import patch

from sqlalchemy.exc import InterfaceError, OperationalError

from app.database import run_read_with_retry


class RunReadWithRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_once_on_closed_connection(self) -> None:
        sessions = ["first", "second"]
        call_order: list[str] = []
        index = 0

        @asynccontextmanager
        async def fake_get_session_context():
            nonlocal index
            session = sessions[index]
            index += 1
            yield session

        async def operation(session: str) -> str:
            call_order.append(session)
            if len(call_order) == 1:
                raise InterfaceError("SELECT 1", {}, Exception("connection is closed"))
            return "ok"

        with patch("app.database.get_session_context", fake_get_session_context):
            result = await run_read_with_retry(operation)  # type: ignore[arg-type]

        self.assertEqual(result, "ok")
        self.assertEqual(call_order, ["first", "second"])

    async def test_does_not_retry_non_retryable_error(self) -> None:
        call_count = 0

        @asynccontextmanager
        async def fake_get_session_context():
            yield "only"

        async def operation(session: str) -> str:
            nonlocal call_count
            call_count += 1
            raise OperationalError("SELECT 1", {}, Exception("syntax error at or near SELECT"))

        with patch("app.database.get_session_context", fake_get_session_context):
            with self.assertRaises(OperationalError):
                await run_read_with_retry(operation)  # type: ignore[arg-type]

        self.assertEqual(call_count, 1)
