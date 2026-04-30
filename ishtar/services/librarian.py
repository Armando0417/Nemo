from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import Float, Integer, text
from sqlmodel import Session, SQLModel, create_engine, func, select

from ishtar.schemas import Gallery, GalleryTagLink, Tag
from ishtar.source import load_metadata, normalize_metadata

VALID_TAG_CATEGORIES = ("artist", "series", "group", "character", "tag")
DEFAULT_FILTER_MODES = {
    "artist": "any",
    "series": "any",
    "group": "any",
    "character": "all",
    "tag": "all",
}


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
        self._ensure_query_support()

    def _ensure_query_support(self) -> None:
        statements = [
            "CREATE INDEX IF NOT EXISTS ix_gallery_is_completed ON gallery (is_completed)",
            "CREATE INDEX IF NOT EXISTS ix_gallery_page_count ON gallery (page_count)",
            "CREATE INDEX IF NOT EXISTS ix_gallery_upload_date ON gallery (upload_date)",
            "CREATE INDEX IF NOT EXISTS ix_gallery_lower_title ON gallery (lower(title))",
            "CREATE INDEX IF NOT EXISTS ix_gallerytaglink_tag_gallery ON gallerytaglink (tag_id, gallery_id)",
            "CREATE INDEX IF NOT EXISTS ix_gallerytaglink_gallery_tag ON gallerytaglink (gallery_id, tag_id)",
            "CREATE INDEX IF NOT EXISTS ix_tag_category_lower_name ON tag (category, lower(name))",
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS gallery_fts
            USING fts5(title, content='gallery', content_rowid='id')
            """,
            """
            CREATE TRIGGER IF NOT EXISTS gallery_ai AFTER INSERT ON gallery BEGIN
                INSERT INTO gallery_fts(rowid, title) VALUES (new.id, new.title);
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS gallery_ad AFTER DELETE ON gallery BEGIN
                INSERT INTO gallery_fts(gallery_fts, rowid, title)
                VALUES ('delete', old.id, old.title);
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS gallery_au AFTER UPDATE ON gallery BEGIN
                INSERT INTO gallery_fts(gallery_fts, rowid, title)
                VALUES ('delete', old.id, old.title);
                INSERT INTO gallery_fts(rowid, title) VALUES (new.id, new.title);
            END
            """,
        ]

        with self.engine.begin() as conn:
            for statement in statements:
                conn.exec_driver_sql(statement)
            gallery_count = conn.exec_driver_sql("SELECT COUNT(*) FROM gallery").scalar_one()
            if gallery_count:
                fts_count = conn.exec_driver_sql("SELECT COUNT(*) FROM gallery_fts").scalar_one()
                if fts_count != gallery_count:
                    conn.exec_driver_sql("INSERT INTO gallery_fts(gallery_fts) VALUES ('rebuild')")

    def _get_or_create_tag(self, session: Session, name: str, category: str) -> Tag:
        cleaned_name = (name or "").strip()
        cleaned_category = (category or "").strip().lower()
        statement = select(Tag).where(
            func.lower(Tag.name) == cleaned_name.lower(),
            Tag.category == cleaned_category,
        )
        tag = session.exec(statement).first()
        if not tag:
            tag = Tag(name=cleaned_name, category=cleaned_category)
            session.add(tag)
        return tag

    def archive_gallery_from_disk(self, gallery_folder: str) -> Gallery | None:
        meta = load_metadata(gallery_folder)
        if not meta:
            return None

        normalized = normalize_metadata(meta, gallery_folder)

        with Session(self.engine) as session:
            existing = session.exec(
                select(Gallery).where(Gallery.media_id == normalized["media_id"])
            ).first()
            if existing:
                existing.title = normalized["title"]
                existing.page_count = normalized["page_count"]
                existing.upload_date = normalized["upload_date"]
                existing.path = normalized["path"]
                existing.is_completed = normalized["is_completed"]
                existing.tags = self._build_tags(session, normalized)
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing

            new_gallery = Gallery(
                media_id=normalized["media_id"],
                title=normalized["title"],
                page_count=normalized["page_count"],
                upload_date=normalized["upload_date"],
                path=normalized["path"],
                is_completed=normalized["is_completed"],
            )

            new_gallery.tags = self._build_tags(session, normalized)
            session.add(new_gallery)
            session.commit()
            session.refresh(new_gallery)
            return new_gallery

    def _build_tags(self, session: Session, normalized: dict) -> list[Tag]:
        tags_to_link = []
        tags_to_link.append(self._get_or_create_tag(session, normalized["artist"], "artist"))
        tags_to_link.append(self._get_or_create_tag(session, normalized["series"], "series"))
        tags_to_link.append(self._get_or_create_tag(session, normalized["group"], "group"))

        for char in normalized.get("featured_characters", []):
            tags_to_link.append(self._get_or_create_tag(session, char, "character"))

        for tag_name in normalized.get("tags", []):
            tags_to_link.append(self._get_or_create_tag(session, tag_name, "tag"))

        return tags_to_link

    def _clean_values(self, values: Optional[Sequence[str]]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for value in values or []:
            normalized = str(value).strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(normalized)

        return cleaned

    def _normalize_filter_map(self, values: Optional[Dict[str, Sequence[str]]]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {category: [] for category in VALID_TAG_CATEGORIES}
        for category, raw_values in (values or {}).items():
            if category not in VALID_TAG_CATEGORIES:
                continue
            normalized[category] = self._clean_values(raw_values)
        return normalized

    def _normalize_modes(self, values: Optional[Dict[str, str]]) -> dict[str, str]:
        normalized = dict(DEFAULT_FILTER_MODES)
        for category, mode in (values or {}).items():
            if category not in VALID_TAG_CATEGORIES:
                continue
            normalized[category] = "any" if str(mode).lower() == "any" else "all"
        return normalized

    def _build_fts_match_query(self, query: str) -> Optional[str]:
        tokens = re.findall(r"\w+", (query or "").lower())
        if not tokens:
            return None
        return " AND ".join(f"{token}*" for token in tokens[:12])

    def _apply_title_search(self, statement, query: str):
        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return statement, None

        match_query = self._build_fts_match_query(cleaned_query)
        if not match_query:
            return statement.where(func.lower(Gallery.title).like(f"%{cleaned_query.lower()}%")), None

        fts_matches = (
            text(
                "SELECT rowid, bm25(gallery_fts) AS rank "
                "FROM gallery_fts WHERE gallery_fts MATCH :match_query"
            )
            .bindparams(match_query=match_query)
            .columns(rowid=Integer, rank=Float)
            .subquery()
        )
        return statement.join(fts_matches, fts_matches.c.rowid == Gallery.id), fts_matches.c.rank

    def _apply_category_filter(self, statement, category: str, values: Sequence[str], mode: str):
        cleaned_values = self._clean_values(values)
        if not cleaned_values:
            return statement

        lookup_values = [value.lower() for value in cleaned_values]
        matches = (
            select(GalleryTagLink.gallery_id)
            .join(Tag, Tag.id == GalleryTagLink.tag_id)
            .where(
                Tag.category == category,
                func.lower(Tag.name).in_(lookup_values),
            )
            .group_by(GalleryTagLink.gallery_id)
        )

        if mode == "all":
            matches = matches.having(
                func.count(func.distinct(func.lower(Tag.name))) >= len(lookup_values)
            )

        return statement.where(Gallery.id.in_(matches))

    def _apply_category_exclusion(self, statement, category: str, values: Sequence[str]):
        cleaned_values = self._clean_values(values)
        if not cleaned_values:
            return statement

        lookup_values = [value.lower() for value in cleaned_values]
        excluded = (
            select(GalleryTagLink.gallery_id)
            .join(Tag, Tag.id == GalleryTagLink.tag_id)
            .where(
                Tag.category == category,
                func.lower(Tag.name).in_(lookup_values),
            )
        )
        return statement.where(~Gallery.id.in_(excluded))

    def _build_gallery_query(
        self,
        query: str = "",
        include_filters: Optional[Dict[str, Sequence[str]]] = None,
        exclude_filters: Optional[Dict[str, Sequence[str]]] = None,
        filter_modes: Optional[Dict[str, str]] = None,
        completed: Optional[bool] = None,
        min_pages: Optional[int] = None,
        max_pages: Optional[int] = None,
    ):
        statement = select(Gallery)
        statement, rank_column = self._apply_title_search(statement, query)

        normalized_includes = self._normalize_filter_map(include_filters)
        normalized_excludes = self._normalize_filter_map(exclude_filters)
        normalized_modes = self._normalize_modes(filter_modes)

        if completed is not None:
            statement = statement.where(Gallery.is_completed == completed)
        if min_pages is not None:
            statement = statement.where(Gallery.page_count >= min_pages)
        if max_pages is not None:
            statement = statement.where(Gallery.page_count <= max_pages)

        for category in VALID_TAG_CATEGORIES:
            statement = self._apply_category_filter(
                statement,
                category,
                normalized_includes[category],
                normalized_modes[category],
            )
            statement = self._apply_category_exclusion(
                statement,
                category,
                normalized_excludes[category],
            )

        return statement, rank_column

    def _apply_sort(self, statement, sort: str, rank_column):
        normalized_sort = (sort or "newest").lower()

        if normalized_sort == "relevance" and rank_column is not None:
            return statement.order_by(rank_column.asc(), Gallery.id.desc())
        if normalized_sort == "oldest":
            return statement.order_by(Gallery.id.asc())
        if normalized_sort == "title_asc":
            return statement.order_by(Gallery.title.asc(), Gallery.id.asc())
        if normalized_sort == "title_desc":
            return statement.order_by(Gallery.title.desc(), Gallery.id.desc())
        if normalized_sort == "pages_asc":
            return statement.order_by(Gallery.page_count.asc(), Gallery.id.asc())
        if normalized_sort == "pages_desc":
            return statement.order_by(Gallery.page_count.desc(), Gallery.id.desc())
        if normalized_sort == "random":
            return statement.order_by(func.random())
        return statement.order_by(Gallery.id.desc())

    def _count_rows(self, session: Session, statement) -> int:
        return session.exec(
            select(func.count()).select_from(statement.order_by(None).subquery())
        ).one()

    def search_galleries(
        self,
        query: str = "",
        include_filters: Optional[Dict[str, Sequence[str]]] = None,
        exclude_filters: Optional[Dict[str, Sequence[str]]] = None,
        filter_modes: Optional[Dict[str, str]] = None,
        completed: Optional[bool] = None,
        min_pages: Optional[int] = None,
        max_pages: Optional[int] = None,
        limit: int = 20,
        offset: int = 0,
        sort: str = "relevance",
        include_total: bool = True,
    ) -> dict[str, Any]:
        with Session(self.engine) as session:
            statement, rank_column = self._build_gallery_query(
                query=query,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                filter_modes=filter_modes,
                completed=completed,
                min_pages=min_pages,
                max_pages=max_pages,
            )
            resolved_sort = sort if not (sort == "relevance" and rank_column is None) else "newest"
            total = self._count_rows(session, statement) if include_total else None
            results = session.exec(
                self._apply_sort(statement, resolved_sort, rank_column)
                .offset(offset)
                .limit(limit)
            ).all()
            return {
                "total": total,
                "items": results,
                "sort": resolved_sort,
            }

    def pick_random_galleries(
        self,
        query: str = "",
        include_filters: Optional[Dict[str, Sequence[str]]] = None,
        exclude_filters: Optional[Dict[str, Sequence[str]]] = None,
        filter_modes: Optional[Dict[str, str]] = None,
        completed: Optional[bool] = None,
        min_pages: Optional[int] = None,
        max_pages: Optional[int] = None,
        limit: int = 1,
    ) -> dict[str, Any]:
        with Session(self.engine) as session:
            statement, _ = self._build_gallery_query(
                query=query,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                filter_modes=filter_modes,
                completed=completed,
                min_pages=min_pages,
                max_pages=max_pages,
            )
            total = self._count_rows(session, statement)
            results = session.exec(statement.order_by(func.random()).limit(limit)).all()
            return {
                "total": total,
                "items": results,
            }

    def list_tags(
        self,
        category: Optional[str] = None,
        query: str = "",
        title_query: str = "",
        min_count: int = 1,
        limit: int = 50,
        offset: int = 0,
        sort: str = "popular",
        include_filters: Optional[Dict[str, Sequence[str]]] = None,
        exclude_filters: Optional[Dict[str, Sequence[str]]] = None,
        filter_modes: Optional[Dict[str, str]] = None,
        completed: Optional[bool] = None,
        min_pages: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> dict[str, Any]:
        with Session(self.engine) as session:
            gallery_query, _ = self._build_gallery_query(
                query=title_query,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                filter_modes=filter_modes,
                completed=completed,
                min_pages=min_pages,
                max_pages=max_pages,
            )
            matching_galleries = self._count_rows(session, gallery_query)
            gallery_scope = gallery_query.order_by(None).subquery()
            display_name = func.min(Tag.name).label("name")
            gallery_count = func.count(func.distinct(GalleryTagLink.gallery_id)).label("gallery_count")

            statement = (
                select(
                    Tag.category.label("category"),
                    display_name,
                    gallery_count,
                )
                .join(GalleryTagLink, GalleryTagLink.tag_id == Tag.id)
                .where(GalleryTagLink.gallery_id.in_(select(gallery_scope.c.id)))
                .group_by(Tag.category, func.lower(Tag.name))
            )

            normalized_category = (category or "").strip().lower()
            if normalized_category:
                statement = statement.where(Tag.category == normalized_category)

            cleaned_query = (query or "").strip().lower()
            if cleaned_query:
                statement = statement.where(func.lower(Tag.name).like(f"%{cleaned_query}%"))

            if min_count > 1:
                statement = statement.having(gallery_count >= min_count)

            total = self._count_rows(session, statement)

            if (sort or "").lower() == "name":
                statement = statement.order_by(Tag.category.asc(), display_name.asc())
            else:
                statement = statement.order_by(gallery_count.desc(), display_name.asc())

            rows = session.exec(statement.offset(offset).limit(limit)).all()
            items = [
                {
                    "category": row.category,
                    "name": row.name,
                    "gallery_count": row.gallery_count,
                }
                for row in rows
            ]
            return {
                "total": total,
                "matching_galleries": matching_galleries,
                "items": items,
            }

    def get_facets(
        self,
        include_filters: Optional[Dict[str, Sequence[str]]] = None,
        exclude_filters: Optional[Dict[str, Sequence[str]]] = None,
        filter_modes: Optional[Dict[str, str]] = None,
        query: str = "",
        completed: Optional[bool] = None,
        min_pages: Optional[int] = None,
        max_pages: Optional[int] = None,
        per_category_limit: int = 12,
    ) -> dict[str, Any]:
        with Session(self.engine) as session:
            gallery_query, _ = self._build_gallery_query(
                query=query,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                filter_modes=filter_modes,
                completed=completed,
                min_pages=min_pages,
                max_pages=max_pages,
            )
            matching_galleries = self._count_rows(session, gallery_query)
            gallery_scope = gallery_query.order_by(None).subquery()
            display_name = func.min(Tag.name).label("name")
            gallery_count = func.count(func.distinct(GalleryTagLink.gallery_id)).label("gallery_count")

            statement = (
                select(
                    Tag.category.label("category"),
                    display_name,
                    gallery_count,
                )
                .join(GalleryTagLink, GalleryTagLink.tag_id == Tag.id)
                .where(GalleryTagLink.gallery_id.in_(select(gallery_scope.c.id)))
                .group_by(Tag.category, func.lower(Tag.name))
                .order_by(Tag.category.asc(), gallery_count.desc(), display_name.asc())
            )

            rows = session.exec(statement).all()
            facets: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                bucket = facets[row.category]
                if len(bucket) >= per_category_limit:
                    continue
                bucket.append(
                    {
                        "name": row.name,
                        "gallery_count": row.gallery_count,
                    }
                )

            return {
                "matching_galleries": matching_galleries,
                "facets": dict(facets),
            }

    def get_related_galleries(self, gallery_id: int, limit: int = 12) -> Optional[dict[str, Any]]:
        with Session(self.engine) as session:
            target_gallery = session.get(Gallery, gallery_id)
            if not target_gallery:
                return None

            target_tags = (
                select(
                    Tag.category.label("category"),
                    func.lower(Tag.name).label("normalized_name"),
                )
                .join(GalleryTagLink, GalleryTagLink.tag_id == Tag.id)
                .where(GalleryTagLink.gallery_id == gallery_id)
                .group_by(Tag.category, func.lower(Tag.name))
                .subquery()
            )

            shared_tag_count = func.count().label("shared_tag_count")
            statement = (
                select(Gallery, shared_tag_count)
                .join(GalleryTagLink, GalleryTagLink.gallery_id == Gallery.id)
                .join(Tag, Tag.id == GalleryTagLink.tag_id)
                .join(
                    target_tags,
                    (target_tags.c.category == Tag.category)
                    & (target_tags.c.normalized_name == func.lower(Tag.name)),
                )
                .where(Gallery.id != gallery_id)
                .group_by(
                    Gallery.id,
                    Gallery.media_id,
                    Gallery.title,
                    Gallery.page_count,
                    Gallery.upload_date,
                    Gallery.path,
                    Gallery.is_completed,
                )
                .order_by(shared_tag_count.desc(), Gallery.page_count.desc(), Gallery.id.desc())
                .limit(limit)
            )

            rows = session.exec(statement).all()
            return {
                "gallery": target_gallery,
                "items": [
                    {
                        "shared_tag_count": shared_count,
                        "gallery": gallery,
                    }
                    for gallery, shared_count in rows
                ],
            }
