from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel


class CalendarItemType(str, Enum):
    LESSON = "lesson"
    PREPARATION_TODO = "preparation_todo"


class CalendarLessonItem(BaseModel):
    type: CalendarItemType = CalendarItemType.LESSON
    id: str
    title: str
    planned_date: date
    lesson_number: int
    learning_objectives: list[str]
    lesplan_id: str
    lesplan_title: str
    created_at: datetime


class CalendarTodoItem(BaseModel):
    type: CalendarItemType = CalendarItemType.PREPARATION_TODO
    id: str
    title: str
    description: str
    due_date: date
    status: str
    lesson_id: str
    lesson_title: str
    lesplan_id: str
    lesplan_title: str
    created_at: datetime


class CalendarResponse(BaseModel):
    start_date: date
    end_date: date
    items: list[CalendarLessonItem | CalendarTodoItem]
