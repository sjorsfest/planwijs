import unittest
from unittest.mock import patch

from app.agents.preparation_agent import (
    GeneratedPreparationTodo,
    GeneratedPreparationTodos,
    PreparationContext,
    _build_prompt,
    generate_preparation_todos,
)


class _FakeResult:
    def __init__(self, todos: list[GeneratedPreparationTodo]) -> None:
        self.output = GeneratedPreparationTodos(todos=todos)


class _FakeAgent:
    def __init__(self, *, result: _FakeResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def run(self, _prompt: str) -> _FakeResult:
        if self._error is not None:
            raise self._error
        if self._result is None:
            return _FakeResult([])
        return self._result


class PreparationAgentTests(unittest.IsolatedAsyncioTestCase):
    def _context(self) -> PreparationContext:
        return PreparationContext(
            lesson_number=2,
            title="De Griekse stadstaten",
            learning_objectives=["Leerlingen kunnen polis en acropolis uitleggen."],
            time_sections=[
                {
                    "start_min": 10,
                    "end_min": 30,
                    "activity": "Bronnencarousel",
                    "activity_type": "activity",
                    "description": "Leerlingen analyseren bronnen in tweetallen.",
                }
            ],
            required_materials=[
                "Historische kaart van het oude Griekenland",
                "Opdrachtblad tijdlijn-carousel met bronnen",
                "Flex-boek paragraaf 0 en 1",
            ],
            teacher_notes="Aandachtspunt: Check dat alle tweetallen actief bezig zijn.",
        )

    async def test_uses_fallback_when_model_returns_no_todos(self) -> None:
        fake_agent = _FakeAgent(result=_FakeResult([]))

        with patch("app.agents.preparation_agent._get_preparation_agent", return_value=fake_agent):
            todos = await generate_preparation_todos(self._context())

        self.assertGreaterEqual(len(todos), 1)
        self.assertTrue(any("opdrachtblad" in todo.title.lower() for todo in todos))

    def test_prompt_requires_todos_for_actionable_materials(self) -> None:
        prompt = _build_prompt(self._context())

        self.assertIn("Maak een concrete todo voor elk benoemd materiaal", prompt)
        self.assertIn("opdrachtblad, tijdlijn/carrousel, bronnen, afbeeldingen en kaarten", prompt)
        self.assertIn("Geef alleen een lege lijst als er echt geen voorbereiding nodig is", prompt)

    async def test_sanitizes_and_deduplicates_model_todos(self) -> None:
        fake_agent = _FakeAgent(
            result=_FakeResult(
                [
                    GeneratedPreparationTodo(
                        title="  Print opdrachtblad  ",
                        description="   ",
                        why="   ",
                    ),
                    GeneratedPreparationTodo(
                        title="print opdrachtblad",
                        description="duplicaat",
                        why="duplicaat",
                    ),
                ]
            )
        )

        with patch("app.agents.preparation_agent._get_preparation_agent", return_value=fake_agent):
            todos = await generate_preparation_todos(self._context())

        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0].title, "Print opdrachtblad")
        self.assertTrue(todos[0].description)
        self.assertTrue(todos[0].why)

    async def test_fallback_when_agent_raises_error(self) -> None:
        fake_agent = _FakeAgent(error=RuntimeError("model failure"))

        with (
            patch("app.agents.preparation_agent._get_preparation_agent", return_value=fake_agent),
            patch("app.agents.preparation_agent.logger.exception"),
        ):
            todos = await generate_preparation_todos(
                PreparationContext(
                    lesson_number=1,
                    title="Intro",
                    learning_objectives=["Kennismaken"],
                    time_sections=[
                        {
                            "start_min": 0,
                            "end_min": 10,
                            "activity": "Start",
                            "activity_type": "introduction",
                            "description": "Korte introductie",
                        }
                    ],
                    required_materials=["Flex-boek paragraaf 0 en 1"],
                    teacher_notes="",
                )
            )

        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0].title, "Controleer en verzamel benodigde materialen")


if __name__ == "__main__":
    unittest.main()
