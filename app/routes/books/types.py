from pydantic import BaseModel


class ParagraphResponse(BaseModel):
    id: str
    index: int
    title: str
    synopsis: str | None


class ChapterResponse(BaseModel):
    id: str
    index: int
    title: str
    paragraphs: list[ParagraphResponse]


class BookDetailResponse(BaseModel):
    id: str
    slug: str
    title: str
    subject_id: str | None
    subject_slug: str | None
    subject_name: str | None
    subject_category: str | None
    method_id: str | None
    edition: str | None
    school_years: list
    levels: list
    cover_url: str | None
    url: str
    chapters: list[ChapterResponse]
