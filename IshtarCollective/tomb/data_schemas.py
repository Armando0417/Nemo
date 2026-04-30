from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel


class GalleryTagLink(SQLModel, table=True):
    """
    ### Gallery–Tag Link (Bridge Table)
    **Author:** Sess  
    **Date:** Jan 09, 2026

    Association table enabling a **many-to-many relationship** between
    galleries and tags.

    This table does not store additional metadata — it exists purely
    to link galleries with their assigned tags.

    #### Fields:
    * **gallery_id** (int): Foreign key referencing `gallery.id`.
    * **tag_id** (int): Foreign key referencing `tag.id`.

    #### Notes:
    * Uses a **composite primary key** (`gallery_id`, `tag_id`)
      to prevent duplicate associations.
    """
    gallery_id: Optional[int] = Field(
        default=None,
        foreign_key="gallery.id",
        primary_key=True
    )
    tag_id: Optional[int] = Field(
        default=None,
        foreign_key="tag.id",
        primary_key=True
    )


class Tag(SQLModel, table=True):
    """
    ### Tag (Database Table)
    **Author:** Sess  
    **Date:** Jan 09, 2026

    Database schema representing a tag used for categorizing galleries.
    Tags may represent artists, characters, series, parodies, or
    general descriptors.

    #### Fields:
    * **id** (int): Unique database ID (Primary Key).
    * **name** (str): Display name of the tag (e.g., "Artoria Pendragon").
    * **category** (str): Classification of the tag  
      (e.g., "character", "artist", "series", "tag").

    #### Relationships:
    * **galleries**: All galleries associated with this tag
      (many-to-many).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    category: str = Field(index=True)

    # Many-to-Many Relationship back to Gallery
    galleries: List["Gallery"] = Relationship(
        back_populates="tags",
        link_model=GalleryTagLink
    )


class Gallery(SQLModel, table=True):
    """
    ### Gallery (Database Table)
    **Author:** Sess  
    **Date:** Jan 09, 2026

    Database schema representing a single gallery entry
    (e.g., a doujin, artbook, or image collection).

    Each gallery may contain multiple pages and be associated with
    any number of tags.

    #### Fields:
    * **id** (int): Unique database ID (Primary Key).
    * **media_id** (str): External or source identifier
      (e.g., scraped metadata ID).
    * **title** (str): Display title of the gallery.
    * **page_count** (int): Total number of pages/images.
    * **upload_date** (str): Original upload date of the gallery.
    * **path** (str): Physical storage path on disk (Tri-Hermes).

    #### Relationships:
    * **tags**: All tags associated with this gallery (many-to-many).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    media_id: str = Field(index=True, unique=True)
    title: str
    page_count: int
    upload_date: str
    path: str   
    is_completed: bool

    # Many-to-Many Relationship to Tag
    tags: List[Tag] = Relationship(
        back_populates="galleries",
        link_model=GalleryTagLink
    )
