import unittest

from app.agents.lesplan_agent import (
    GeneratedOverviewSequence,
    LesplanContext,
    LessonOutlineItem,
    _normalize_learning_goals_for_context,
)


class LearningGoalsQualityTests(unittest.TestCase):
    def _context(self) -> LesplanContext:
        return LesplanContext(
            book_title="Boek",
            book_subject="Geschiedenis",
            method_name="Methode",
            paragraphs=[
                {"index": 0, "title": "Paragraaf 1", "synopsis": "A"},
                {"index": 1, "title": "Paragraaf 2", "synopsis": "B"},
            ],
            level="vmbo-t",
            school_year="leerjaar_1",
            class_size=24,
            difficulty="Groen",
            num_lessons=2,
            lesson_duration_minutes=50,
        )

    def _sequence(self) -> GeneratedOverviewSequence:
        return GeneratedOverviewSequence(
            key_knowledge=["Atheense democratie", "Bestuursvormen"],
            lesson_outline=[
                LessonOutlineItem(
                    lesson_number=1,
                    subject_focus="Bestuursvormen in Griekenland",
                    description="Introductie op vormen van bestuur.",
                    teaching_approach_hint="Korte uitleg gevolgd door een koppelopdracht.",
                    builds_on="Start van de reeks.",
                    concept_tags=["monarchie", "democratie"],
                    lesson_intention="Leerlingen herkennen basisbegrippen.",
                    end_understanding="Leerlingen kunnen de vier vormen onderscheiden.",
                    sequence_rationale="Fundament voor verdieping.",
                    builds_on_lessons=[],
                    paragraph_indices=[0],
                ),
                LessonOutlineItem(
                    lesson_number=2,
                    subject_focus="Atheense democratie in de praktijk",
                    description="Toepassen van kernbegrippen op Athene.",
                    teaching_approach_hint="Bronanalyse met klassikale nabespreking.",
                    builds_on="Bouwt voort op les 1.",
                    concept_tags=["athene", "burgerschap"],
                    lesson_intention="Leerlingen koppelen begrippen aan casussen.",
                    end_understanding="Leerlingen leggen besluitvorming in Athene uit.",
                    sequence_rationale="Verdieping en toepassing.",
                    builds_on_lessons=[1],
                    paragraph_indices=[1],
                ),
            ],
        )

    def test_rewrites_vague_goal_to_observable_goal(self) -> None:
        normalized = _normalize_learning_goals_for_context(
            ["Leerlingen begrijpen democratie."],
            ctx=self._context(),
            sequence=self._sequence(),
        )

        self.assertEqual(len(normalized), 1)
        self.assertTrue(normalized[0].startswith("Leerlingen kunnen "))
        self.assertIn("zichtbaar in", normalized[0].lower())
        self.assertNotIn("begrijpen", normalized[0].lower())

    def test_keeps_already_concrete_goal(self) -> None:
        goal = (
            "Leerlingen kunnen monarchie, aristocratie, democratie en tirannie koppelen aan de juiste definitie, "
            "zichtbaar in een korte koppelopdracht."
        )
        normalized = _normalize_learning_goals_for_context(
            [goal],
            ctx=self._context(),
            sequence=self._sequence(),
        )

        self.assertEqual(normalized, [goal])


if __name__ == "__main__":
    unittest.main()
