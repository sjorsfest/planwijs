import unittest

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.lesplan import LesplanRequest, LessonPlan


class LesplanJsonbDefaultTests(unittest.TestCase):
    def test_lesplan_request_jsonb_default_compiles_without_double_quoting(self) -> None:
        ddl = str(CreateTable(LesplanRequest.__table__).compile(dialect=postgresql.dialect()))

        self.assertIn("selected_paragraph_ids JSONB DEFAULT '[]' NOT NULL", ddl)
        self.assertNotIn("'''[]''::jsonb'", ddl)

    def test_lesson_plan_jsonb_defaults_compile_without_double_quoting(self) -> None:
        ddl = str(CreateTable(LessonPlan.__table__).compile(dialect=postgresql.dialect()))

        self.assertIn("learning_objectives JSONB DEFAULT '[]' NOT NULL", ddl)
        self.assertIn("time_sections JSONB DEFAULT '[]' NOT NULL", ddl)
        self.assertIn("required_materials JSONB DEFAULT '[]' NOT NULL", ddl)
        self.assertIn("covered_paragraph_ids JSONB DEFAULT '[]' NOT NULL", ddl)
        self.assertNotIn("'''[]''::jsonb'", ddl)
