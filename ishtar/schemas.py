from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class GalleryTagLink(SQLModel, table=True):
    gallery_id: Optional[int] = Field(
        default=None,
        foreign_key="gallery.id",
        primary_key=True,
    )
    tag_id: Optional[int] = Field(
        default=None,
        foreign_key="tag.id",
        primary_key=True,
    )


class Tag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    category: str = Field(index=True)

    galleries: List["Gallery"] = Relationship(
        back_populates="tags",
        link_model=GalleryTagLink,
    )


class Gallery(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    media_id: str = Field(index=True, unique=True)
    title: str
    page_count: int
    upload_date: str
    path: str
    is_completed: bool

    tags: List[Tag] = Relationship(
        back_populates="galleries",
        link_model=GalleryTagLink,
    )
