from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class Manga_Chapter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    series_id: Optional[int] = Field(default=None, foreign_key="manga_series.id")
    chapter_number: float = Field(index=True)
    title: Optional[str] = None
    page_count: int
    folder_path: str

    series: Optional["Manga_Series"] = Relationship(back_populates="chapters")


class Manga_Series(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    author: Optional[str] = None
    path: str = Field(unique=True, description="The physical folder path on disk")
    description: Optional[str] = None
    cover_image: str
    status: str = Field(default="Ongoing")

    chapters: List[Manga_Chapter] = Relationship(back_populates="series")
