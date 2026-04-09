import unittest

from app.routes.lesplan.util import _normalize_overview_payload


class LesplanOverviewNormalizationTests(unittest.TestCase):
    def test_normalizes_legacy_overview_shape(self) -> None:
        legacy_payload = {
            "title": "Middeleeuwen",
            "learning_goals": ["Doel 1", "Doel 2"],
            "key_knowledge": ["Kennis 1", "Kennis 2"],
            "recommended_approach": "Aanpak",
            "learning_progression": "Leerlijn",
            "lesson_outline": [
                {
                    "lesson_number": 1,
                    "subject_focus": "Start",
                    "description": "Intro",
                    "builds_on": "Voorkennis",
                },
                {
                    "lesson_number": 2,
                    "subject_focus": "Verdieping",
                    "description": "Vervolg",
                    "builds_on": "Bouwt voort op les 1.",
                },
            ],
            "didactic_approach": "Didactiek",
        }

        normalized = _normalize_overview_payload(
            legacy_payload,
            num_lessons=2,
            paragraph_count=3,
        )

        self.assertEqual(normalized["series_summary"], "Leerlijn")
        self.assertTrue(normalized["series_themes"])
        self.assertEqual(len(normalized["lesson_outline"]), 2)
        for item in normalized["lesson_outline"]:
            self.assertGreaterEqual(len(item["concept_tags"]), 2)
            self.assertIn("paragraph_indices", item)
            self.assertTrue(item.get("teaching_approach_hint"))

        covered = {idx for item in normalized["lesson_outline"] for idx in item["paragraph_indices"]}
        self.assertEqual(covered, {0, 1, 2})
        self.assertEqual(len(normalized["goal_coverage"]), 2)
        self.assertEqual(len(normalized["knowledge_coverage"]), 2)
        self.assertNotIn("approval_readiness", normalized)

    def test_rewrites_generic_teaching_hints_to_varied_workforms(self) -> None:
        payload = {
            "title": "Interbellum",
            "learning_goals": ["Doel 1"],
            "key_knowledge": ["Kennis 1"],
            "lesson_outline": [
                {
                    "lesson_number": 1,
                    "subject_focus": "Tijdvak en begrippen",
                    "description": "Plaats gebeurtenissen op een tijdlijn.",
                    "teaching_approach_hint": (
                        "Korte activering, daarna gerichte uitleg over tijdvak en begrippen, "
                        "gevolgd door begeleide verwerking en een afsluitende check op begrip."
                    ),
                },
                {
                    "lesson_number": 2,
                    "subject_focus": "Fascisme en communisme vergelijken",
                    "description": "Vergelijk overeenkomsten en verschillen.",
                    "teaching_approach_hint": (
                        "Korte activering, daarna gerichte uitleg over fascisme en communisme, "
                        "gevolgd door begeleide verwerking en een afsluitende check op begrip."
                    ),
                },
                {
                    "lesson_number": 3,
                    "subject_focus": "Welvaart en crisis in de Verenigde Staten",
                    "description": "Onderzoek oorzaken en gevolgen van de crisis.",
                    "teaching_approach_hint": (
                        "Korte activering, daarna gerichte uitleg over welvaart en crisis in de VS, "
                        "gevolgd door begeleide verwerking en een afsluitende check op begrip."
                    ),
                },
            ],
            "recommended_approach": "Aanpak",
            "learning_progression": "Leerlijn",
            "didactic_approach": "Didactiek",
        }

        normalized = _normalize_overview_payload(payload, num_lessons=3, paragraph_count=3)
        hints = [item["teaching_approach_hint"] for item in normalized["lesson_outline"]]
        self.assertEqual(len(hints), 3)
        self.assertTrue(all(hint and hint.strip() for hint in hints))
        self.assertTrue(all(not hint.lower().startswith("korte activering, daarna gerichte uitleg over") for hint in hints))
        self.assertGreater(len(set(hints)), 1)
