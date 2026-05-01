from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel

class Manga_Chapter(SQLModel, table=True):
    """
    ### Manga Chapter (Database Table)
    **Author:** Sess  
    **Date:** Jan 09, 2026

    Database schema representing an individual manga chapter linked to a series.

    #### Fields:
    * **id** (int): Unique database ID (Primary Key).
    * **series_id** (int): The ID of the Manga_Series this chapter belongs to.
    * **chapter_number** (float): The sequence number (supports 1.5, etc).
    * **title** (str): The specific name of the chapter.
    * **page_count** (int): Total number of images.
    * **folder_path** (str): Path to the image files.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Database linking
    series_id: Optional[int] = Field(default=None, foreign_key="manga_series.id")
    
    # Your Data Fields
    chapter_number: float = Field(index=True)
    title: Optional[str] = None
    page_count: int
    folder_path: str

    # Relationship back to the parent
    series: Optional["Manga_Series"] = Relationship(back_populates="chapters")


class Manga_Series(SQLModel, table=True):
    """
    ### Manga Series (Database Table)
    **Author:** Sess
    **Date:** Jan 09, 2026
    
    Database schema representing a complete manga series.
    
    #### Fields:
    * **id** (int): Unique database ID (Primary Key).
    * **title** (str): The title of the manga series.
    * **author** (str): The creator of the series.
    * **description** (str): A synopsis of the series.
    * **cover_image** (str): Path to the cover image.
    * **status** (str): "Ongoing", "Completed", etc.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Your Data Fields
    title: str = Field(index=True)
    author: Optional[str] = None
    path: str = Field(unique=True, description="The physical folder path on disk")
    description: Optional[str] = None
    cover_image: str
    status: str = Field(default="Ongoing")

    # Relationship to the children
    chapters: List[Manga_Chapter] = Relationship(back_populates="series")