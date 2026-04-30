from __future__ import annotations

from typing import List

from sqlmodel import SQLModel, Session, create_engine, select

from codex.schemas import Manga_Chapter, Manga_Series


class Librarian:
    class _Library:
        def __init__(self, db_url: str, echo: bool):
            self.engine = create_engine(db_url, echo=echo)

        def build_shelves(self) -> None:
            SQLModel.metadata.create_all(self.engine)

    def __init__(self, db_path: str, debug: bool = False):
        sqlite_url = f"sqlite:///{db_path}"
        self._library = self._Library(sqlite_url, echo=debug)
        self._library.build_shelves()
        self.engine = self._library.engine

    def add_new_series(self, series_data: Manga_Series) -> Manga_Series:
        with Session(self.engine) as session:
            session.add(series_data)
            session.commit()
            session.refresh(series_data)
            return series_data

    def get_all_series(self) -> List[Manga_Series]:
        with Session(self.engine) as session:
            return list(session.exec(select(Manga_Series)))

    def get_chapters_for(self, series_id: int) -> List[Manga_Chapter]:
        with Session(self.engine) as session:
            statement = (
                select(Manga_Chapter)
                .where(Manga_Chapter.series_id == series_id)
                .order_by(Manga_Chapter.chapter_number, Manga_Chapter.id)
            )
            return list(session.exec(statement))

    def add_new_chapter_to_series(self, chapter_data: Manga_Chapter) -> Manga_Chapter:
        with Session(self.engine) as session:
            session.add(chapter_data)
            session.commit()
            session.refresh(chapter_data)
            return chapter_data
