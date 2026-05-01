'''
# Librarian

**Author:** Sess
**Date:** Jan 09, 2026

This Librarian file defines the Librarian class, which is responsible for managing the database. 

I named it Librarian instead of something like `database manager` or `database` since it's 
easier for me to remember what it's doing and what purpose it has. Plus helps me frame the methods
in a more specific way. 

'''

from typing import List, Optional
from sqlmodel import Session, select, SQLModel, create_engine
from data_schemas import Manga_Series, Manga_Chapter

class Librarian:
    """
    ### Librarian
    **Author:** Sess
    **Date:** Jan 09, 2026
    
    The Librarian manages the Codex Vault collections.
    She handles adding new books to shelves, finding them,
    and organizing chapters.
    """

    class _Library:
        """
        A 'Private' internal class to handle the physical infrastructure.
        """
        def __init__(self, db_url: str, echo: bool):
            self.engine = create_engine(db_url, echo=echo)

        def build_shelves(self):
            """Creates the tables if they don't exist."""
            print("--- Librarian is preparing the shelves (Creating Tables) ---")
            SQLModel.metadata.create_all(self.engine)
            print("--- Database construction complete! ---")





    def __init__(self, db_name: str = "codex_vault.db", debug: bool = True):
        sqlite_url = f"sqlite:///{db_name}"
        # Initialize the private internal library
        self._library = self._Library(sqlite_url, echo=debug)
        
        # Build shelves immediately on hire
        self._library.build_shelves()
        
        # Keep a reference to the engine for the Librarian's use
        self.engine = self._library.engine

    def add_new_series(self, series_data: Manga_Series):
        """Archives a new Manga_Series into the vault."""
        with Session(self.engine) as session:
            session.add(series_data)
            session.commit()
            session.refresh(series_data)
            print(f"Librarian: Successfully archived '{series_data.title}' (ID: {series_data.id})")
            return series_data

    def get_all_series(self) -> List[Manga_Series]:
        """Lists every manga currently on the shelves."""
        with Session(self.engine) as session:
            statement = select(Manga_Series)
            results = session.exec(statement)
            return list(results)

    def get_chapters_for(self, series_id:int) -> List[Manga_Chapter]:
        """Lists every manga currently on the shelves for a specific series."""
        with Session(self.engine) as session:
            statement = (
                select(Manga_Chapter)
                .where(Manga_Chapter.series_id == series_id)
                .order_by(Manga_Chapter.chapter_number, Manga_Chapter.id)
            )
            results = session.exec(statement)
            return list(results)
    
    def add_new_chapter_to_series(self, chapter_data: Manga_Chapter):
        """Archives a new Manga_Chapter into the vault."""
        with Session(self.engine) as session:
            session.add(chapter_data)
            session.commit()
            session.refresh(chapter_data)
            print(f"Librarian: Successfully archived '{chapter_data.title}' (ID: {chapter_data.id})")
            return chapter_data



if __name__ == "__main__":

    librarian = Librarian(debug=True)
        
        
        
        
