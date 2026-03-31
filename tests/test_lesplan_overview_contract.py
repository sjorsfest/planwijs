import unittest

from app.agents.lesplan_agent import (
    ApprovalReadiness,
    GeneratedLesplanOverview,
    GoalCoverageItem,
    KnowledgeCoverageItem,
    LesplanContext,
    LessonOutlineItem,
    _normalize_lesson_outline_for_context,
    _validate_overview_for_context,
)


class LesplanOverviewContractTests(unittest.TestCase):
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
            class_size=25,
            difficulty="Groen",
            num_lessons=2,
            lesson_duration_minutes=50,
        )

    def _valid_overview(self) -> GeneratedLesplanOverview:
        return GeneratedLesplanOverview(
            title="Vroege Middeleeuwen",
            series_summary="Deze reeks behandelt de machtsverschuivingen in de vroege middeleeuwen.",
            series_themes=["macht", "kerk", "samenleving"],
            learning_goals=[
                "Leerlingen kunnen de sociale orde uitleggen.",
                "Leerlingen kunnen de rol van de kerk duiden.",
            ],
            key_knowledge=["feodalisme", "kerstening"],
            recommended_approach="Concreet en stap-voor-stap met veel herhaling.",
            learning_progression="Van basisbegrippen naar vergelijking en toepassing.",
            lesson_outline=[
                LessonOutlineItem(
                    lesson_number=1,
                    subject_focus="Basis van de samenleving",
                    description="Introductie van kernbegrippen.",
                    teaching_approach_hint="Korte activering, gerichte uitleg en begeleide oefening met checkvragen.",
                    builds_on="Voorkennis uit de basisschool.",
                    concept_tags=["feodalisme", "standen"],
                    lesson_intention="Leerlingen maken kennis met de sociale orde.",
                    end_understanding="Leerlingen begrijpen de basisstructuur.",
                    sequence_rationale="Eerste fundament voor latere verdieping.",
                    builds_on_lessons=[],
                    paragraph_indices=[0],
                ),
                LessonOutlineItem(
                    lesson_number=2,
                    subject_focus="Kerk en macht",
                    description="De invloed van de kerk op bestuur en dagelijks leven.",
                    teaching_approach_hint="Start met herhaling, daarna bronanalyse in duo's en klassikale terugkoppeling.",
                    builds_on="Bouwt voort op les 1.",
                    concept_tags=["kerk", "kerstening"],
                    lesson_intention="Leerlingen koppelen religie aan machtsvorming.",
                    end_understanding="Leerlingen duiden de rol van de kerk.",
                    sequence_rationale="Verdieping op eerder geleerd maatschappelijk kader.",
                    builds_on_lessons=[1],
                    paragraph_indices=[1],
                ),
            ],
            goal_coverage=[
                GoalCoverageItem(
                    goal="Leerlingen kunnen de sociale orde uitleggen.",
                    lesson_numbers=[1],
                    rationale="Les 1 behandelt de orde expliciet.",
                ),
                GoalCoverageItem(
                    goal="Leerlingen kunnen de rol van de kerk duiden.",
                    lesson_numbers=[2],
                    rationale="Les 2 focust op kerkelijke invloed.",
                ),
            ],
            knowledge_coverage=[
                KnowledgeCoverageItem(
                    knowledge="feodalisme",
                    lesson_numbers=[1],
                    rationale="Wordt in les 1 geïntroduceerd.",
                ),
                KnowledgeCoverageItem(
                    knowledge="kerstening",
                    lesson_numbers=[2],
                    rationale="Wordt in les 2 uitgewerkt.",
                ),
            ],
            approval_readiness=ApprovalReadiness(
                ready_for_approval=True,
                rationale="Doelen en opbouw zijn voldoende uitgewerkt.",
                checklist=["Doelen gecontroleerd", "Opbouw gecontroleerd"],
                open_questions=[],
            ),
            didactic_approach="Activering, instructie, verwerking en reflectie.",
        )

    def test_valid_overview_passes_contract_validation(self) -> None:
        _validate_overview_for_context(self._valid_overview(), self._context())

    def test_missing_paragraph_coverage_fails_validation(self) -> None:
        overview = self._valid_overview()
        overview.lesson_outline[1].paragraph_indices = []

        with self.assertRaises(ValueError):
            _validate_overview_for_context(overview, self._context())

    def test_non_contiguous_lessons_fail_validation(self) -> None:
        overview = self._valid_overview()
        overview.lesson_outline[1].lesson_number = 3

        with self.assertRaises(ValueError):
            _validate_overview_for_context(overview, self._context())

    def test_missing_teaching_hint_fails_validation(self) -> None:
        overview = self._valid_overview()
        overview.lesson_outline[0].teaching_approach_hint = ""

        with self.assertRaises(ValueError):
            _validate_overview_for_context(overview, self._context())

    def test_placeholder_lesson_text_is_enriched_during_normalization(self) -> None:
        ctx = self._context()
        normalized = _normalize_lesson_outline_for_context(
            [
                LessonOutlineItem(
                    lesson_number=1,
                    subject_focus="Les 1",
                    description="In deze les staat les 1 centraal.",
                    lesson_intention="In deze les staat les 1 centraal.",
                    end_understanding="In deze les staat les 1 centraal.",
                    sequence_rationale="Start van de reeks.",
                    concept_tags=["feodalisme", "standen"],
                    paragraph_indices=[0],
                ),
                LessonOutlineItem(
                    lesson_number=2,
                    subject_focus="Les 2",
                    description="In deze les staat les 2 centraal.",
                    lesson_intention="In deze les staat les 2 centraal.",
                    end_understanding="In deze les staat les 2 centraal.",
                    sequence_rationale="Bouwt voort op les 1.",
                    concept_tags=["kerk", "kerstening"],
                    builds_on_lessons=[1],
                    paragraph_indices=[1],
                ),
            ],
            ctx,
            ["feodalisme", "kerstening"],
        )

        self.assertEqual(len(normalized), 2)
        for lesson in normalized:
            self.assertNotRegex(lesson.subject_focus.lower(), r"^les\s*\d+$")
            self.assertNotIn("in deze les staat", lesson.description.lower())
            self.assertNotEqual(lesson.lesson_intention.strip(), lesson.description.strip())
            self.assertNotEqual(lesson.end_understanding.strip(), lesson.description.strip())
