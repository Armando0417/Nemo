from __future__ import annotations

import logging
import mimetypes
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse
from sqlmodel import Session

from ishtar.config import get_settings
from ishtar.schemas import Gallery
from ishtar.services.librarian import Librarian
from ishtar.source import (
    clear_media_index_cache,
    get_source_root,
    iter_gallery_folders,
    resolve_gallery_path,
)

logger = logging.getLogger("nemo.ishtar")

FilterMode = Literal["all", "any"]
SearchSort = Literal[
    "relevance",
    "newest",
    "oldest",
    "title_asc",
    "title_desc",
    "pages_asc",
    "pages_desc",
    "random",
]
TagSort = Literal["popular", "name"]

VALID_FILTER_CATEGORIES = {"artist", "series", "group", "character", "tag"}

settings = get_settings()
librarian = Librarian(db_path=str(settings.db_path), debug=settings.debug)

router = APIRouter()
api_router = APIRouter(prefix="/api/ishtar", tags=["Ishtar"])

FRONTEND_DIST_DIR = settings.frontend_dist_dir
FRONTEND_INDEX = FRONTEND_DIST_DIR / "index.html"
LIST_CACHE_CONTROL = "public, max-age=30"
DETAIL_CACHE_CONTROL = "public, max-age=300"
TAG_CACHE_CONTROL = "public, max-age=300"
IMAGE_CACHE_CONTROL = "public, max-age=86400"


def natural_sort_key(value: str):
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", value)]


@lru_cache(maxsize=4096)
def _list_gallery_images(gallery_path: str) -> tuple[str, ...]:
    valid_exts = (".jpg", ".jpeg", ".png", ".webp")
    raw_files = [file_name for file_name in os.listdir(gallery_path) if file_name.lower().endswith(valid_exts)]
    return tuple(sorted(raw_files, key=natural_sort_key))


def _group_tags(tags) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}

    for tag in sorted(tags, key=lambda item: (item.category, item.name.lower())):
        category = tag.category
        normalized_name = tag.name.casefold()
        seen.setdefault(category, set())
        if normalized_name in seen[category]:
            continue
        seen[category].add(normalized_name)
        grouped.setdefault(category, []).append(tag.name)

    return grouped


def _serialize_gallery_summary(gallery: Gallery) -> dict:
    return {
        "id": gallery.id,
        "media_id": gallery.media_id,
        "title": gallery.title,
        "page_count": gallery.page_count,
        "upload_date": gallery.upload_date,
        "is_completed": gallery.is_completed,
    }


def _serialize_gallery_detail(gallery: Gallery) -> dict:
    tags_grouped = _group_tags(gallery.tags)
    return {
        "id": gallery.id,
        "media_id": gallery.media_id,
        "title": gallery.title,
        "page_count": gallery.page_count,
        "upload_date": gallery.upload_date,
        "path": gallery.path,
        "is_completed": gallery.is_completed,
        "artists": tags_grouped.get("artist", []),
        "series": tags_grouped.get("series", []),
        "groups": tags_grouped.get("group", []),
        "characters": tags_grouped.get("character", []),
        "labels": tags_grouped.get("tag", []),
        "tags": tags_grouped,
    }


def _merge_scoped_terms(target: dict[str, list[str]], scoped_terms: Optional[list[str]], field_name: str):
    for term in scoped_terms or []:
        raw_term = term.strip()
        if not raw_term:
            continue
        if ":" not in raw_term:
            raise HTTPException(
                status_code=422,
                detail=f"Each '{field_name}' filter must use category:value syntax.",
            )

        category, name = raw_term.split(":", 1)
        normalized_category = category.strip().lower()
        normalized_name = name.strip()

        if normalized_category not in VALID_FILTER_CATEGORIES:
            allowed = ", ".join(sorted(VALID_FILTER_CATEGORIES))
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported filter category '{normalized_category}'. Allowed: {allowed}.",
            )
        if not normalized_name:
            raise HTTPException(
                status_code=422,
                detail=f"Scoped filter '{raw_term}' is missing a value.",
            )

        target[normalized_category].append(normalized_name)


def build_gallery_filters(
    q: str = "",
    completed: Optional[bool] = None,
    min_pages: Annotated[Optional[int], Query(ge=0)] = None,
    max_pages: Annotated[Optional[int], Query(ge=0)] = None,
    artists: Annotated[Optional[list[str]], Query()] = None,
    exclude_artists: Annotated[Optional[list[str]], Query()] = None,
    artist_mode: FilterMode = "any",
    series: Annotated[Optional[list[str]], Query()] = None,
    exclude_series: Annotated[Optional[list[str]], Query()] = None,
    series_mode: FilterMode = "any",
    groups: Annotated[Optional[list[str]], Query()] = None,
    exclude_groups: Annotated[Optional[list[str]], Query()] = None,
    group_mode: FilterMode = "any",
    characters: Annotated[Optional[list[str]], Query()] = None,
    exclude_characters: Annotated[Optional[list[str]], Query()] = None,
    character_mode: FilterMode = "all",
    tags: Annotated[Optional[list[str]], Query()] = None,
    exclude_tags: Annotated[Optional[list[str]], Query()] = None,
    tag_mode: FilterMode = "all",
    scoped_with: Annotated[
        Optional[list[str]],
        Query(alias="with", description="Category filters in category:value form."),
    ] = None,
    scoped_without: Annotated[
        Optional[list[str]],
        Query(alias="without", description="Excluded category filters in category:value form."),
    ] = None,
):
    if min_pages is not None and max_pages is not None and min_pages > max_pages:
        raise HTTPException(status_code=422, detail="'min_pages' cannot be greater than 'max_pages'.")

    include_filters = {
        "artist": list(artists or []),
        "series": list(series or []),
        "group": list(groups or []),
        "character": list(characters or []),
        "tag": list(tags or []),
    }
    exclude_filters = {
        "artist": list(exclude_artists or []),
        "series": list(exclude_series or []),
        "group": list(exclude_groups or []),
        "character": list(exclude_characters or []),
        "tag": list(exclude_tags or []),
    }

    _merge_scoped_terms(include_filters, scoped_with, "with")
    _merge_scoped_terms(exclude_filters, scoped_without, "without")

    filter_modes = {
        "artist": artist_mode,
        "series": series_mode,
        "group": group_mode,
        "character": character_mode,
        "tag": tag_mode,
    }

    return {
        "query": q,
        "completed": completed,
        "min_pages": min_pages,
        "max_pages": max_pages,
        "include_filters": include_filters,
        "exclude_filters": exclude_filters,
        "filter_modes": filter_modes,
        "public_filters": {
            "completed": completed,
            "min_pages": min_pages,
            "max_pages": max_pages,
            "include": include_filters,
            "exclude": exclude_filters,
            "modes": filter_modes,
        },
    }


@api_router.get("")
async def root() -> dict[str, str]:
    return {"message": "Welcome to The Tomb inside Nemo."}


@api_router.get("/system/populate")
async def populate_tomb(base_path: str = str(get_source_root())):
    if not os.path.exists(base_path):
        raise HTTPException(status_code=404, detail="Storage path not found")

    clear_media_index_cache()
    _list_gallery_images.cache_clear()
    archived_count = 0
    folders = [str(folder) for folder in iter_gallery_folders(base_path)]

    for folder in folders:
        try:
            result = librarian.archive_gallery_from_disk(folder)
            if result:
                archived_count += 1
        except Exception as exc:
            logger.exception("Error archiving Ishtar gallery %s: %s", folder, exc)
            continue

    return {
        "status": "Success",
        "message": f"Scanned {len(folders)} folders, archived {archived_count} new galleries.",
    }


@api_router.get("/report/galleries")
async def get_galleries(
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_total: bool = True,
):
    response.headers["Cache-Control"] = LIST_CACHE_CONTROL
    results = librarian.search_galleries(limit=limit, offset=offset, sort="newest", include_total=include_total)
    return {
        "total": results["total"],
        "items": results["items"],
    }


@api_router.get("/view/gallery/{gallery_id}/pages")
async def get_gallery_pages(gallery_id: int, response: Response):
    with Session(librarian.engine) as session:
        gallery = session.get(Gallery, gallery_id)
        gallery_path = resolve_gallery_path(gallery) if gallery else None
        if not gallery or not gallery_path or not os.path.exists(gallery_path):
            raise HTTPException(status_code=404)

        response.headers["Cache-Control"] = DETAIL_CACHE_CONTROL
        images = _list_gallery_images(gallery_path)

        return {
            "title": gallery.title,
            "pages": list(images),
        }


@api_router.get("/view/gallery/{gallery_id}/thumbnail")
async def get_gallery_thumbnail(gallery_id: int):
    with Session(librarian.engine) as session:
        gallery = session.get(Gallery, gallery_id)
        gallery_path = resolve_gallery_path(gallery) if gallery else None
        if not gallery or not gallery_path or not os.path.exists(gallery_path):
            raise HTTPException(status_code=404, detail="Gallery not found on disk")

        images = _list_gallery_images(gallery_path)
        if not images:
            raise HTTPException(status_code=404, detail="No images found in folder")

        cover_path = os.path.join(gallery_path, images[0])
        return FileResponse(cover_path, headers={"Cache-Control": IMAGE_CACHE_CONTROL})


@api_router.get("/view/gallery/{gallery_id}/page/{filename}")
async def serve_page_file(gallery_id: int, filename: str):
    with Session(librarian.engine) as session:
        gallery = session.get(Gallery, gallery_id)
        gallery_path = resolve_gallery_path(gallery) if gallery else None
        if not gallery or not gallery_path:
            raise HTTPException(status_code=404)

        file_path = os.path.join(gallery_path, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404)

        return FileResponse(file_path, headers={"Cache-Control": IMAGE_CACHE_CONTROL})


@api_router.get("/gallery/{gallery_id}")
async def get_gallery_detail(gallery_id: int, response: Response):
    with Session(librarian.engine) as session:
        gallery = session.get(Gallery, gallery_id)
        if not gallery:
            raise HTTPException(status_code=404, detail="Gallery not found")
        response.headers["Cache-Control"] = DETAIL_CACHE_CONTROL
        return _serialize_gallery_detail(gallery)


@api_router.get("/gallery/{gallery_id}/related")
async def get_related_galleries(
    gallery_id: int,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
):
    response.headers["Cache-Control"] = DETAIL_CACHE_CONTROL
    results = librarian.get_related_galleries(gallery_id=gallery_id, limit=limit)
    if not results:
        raise HTTPException(status_code=404, detail="Gallery not found")

    return {
        "gallery": _serialize_gallery_summary(results["gallery"]),
        "items": [
            {
                "shared_tag_count": item["shared_tag_count"],
                "gallery": _serialize_gallery_summary(item["gallery"]),
            }
            for item in results["items"]
        ],
    }


@api_router.get("/search")
async def search_galleries(
    filters: Annotated[dict, Depends(build_gallery_filters)],
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: SearchSort = "relevance",
    include_total: bool = True,
):
    response.headers["Cache-Control"] = LIST_CACHE_CONTROL
    results = librarian.search_galleries(
        query=filters["query"],
        include_filters=filters["include_filters"],
        exclude_filters=filters["exclude_filters"],
        filter_modes=filters["filter_modes"],
        completed=filters["completed"],
        min_pages=filters["min_pages"],
        max_pages=filters["max_pages"],
        limit=limit,
        offset=offset,
        sort=sort,
        include_total=include_total,
    )
    return {
        "total": results["total"],
        "query": filters["query"],
        "sort": results["sort"],
        "filters": filters["public_filters"],
        "items": results["items"],
    }


@api_router.get("/search/random")
async def get_random_galleries(
    filters: Annotated[dict, Depends(build_gallery_filters)],
    response: Response,
    count: Annotated[int, Query(ge=1, le=50)] = 1,
):
    response.headers["Cache-Control"] = LIST_CACHE_CONTROL
    results = librarian.pick_random_galleries(
        query=filters["query"],
        include_filters=filters["include_filters"],
        exclude_filters=filters["exclude_filters"],
        filter_modes=filters["filter_modes"],
        completed=filters["completed"],
        min_pages=filters["min_pages"],
        max_pages=filters["max_pages"],
        limit=count,
    )
    return {
        "total": results["total"],
        "count": len(results["items"]),
        "query": filters["query"],
        "filters": filters["public_filters"],
        "items": results["items"],
    }


@api_router.get("/search/facets")
async def get_search_facets(
    filters: Annotated[dict, Depends(build_gallery_filters)],
    response: Response,
    per_category_limit: Annotated[int, Query(ge=1, le=100)] = 12,
):
    response.headers["Cache-Control"] = TAG_CACHE_CONTROL
    results = librarian.get_facets(
        query=filters["query"],
        include_filters=filters["include_filters"],
        exclude_filters=filters["exclude_filters"],
        filter_modes=filters["filter_modes"],
        completed=filters["completed"],
        min_pages=filters["min_pages"],
        max_pages=filters["max_pages"],
        per_category_limit=per_category_limit,
    )
    return {
        "query": filters["query"],
        "filters": filters["public_filters"],
        "matching_galleries": results["matching_galleries"],
        "facets": results["facets"],
    }


@api_router.get("/tags")
async def list_tags(
    filters: Annotated[dict, Depends(build_gallery_filters)],
    response: Response,
    category: Optional[str] = None,
    name: str = "",
    min_count: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=250)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: TagSort = "popular",
):
    normalized_category = (category or "").strip().lower() or None
    if normalized_category and normalized_category not in VALID_FILTER_CATEGORIES:
        allowed = ", ".join(sorted(VALID_FILTER_CATEGORIES))
        raise HTTPException(status_code=422, detail=f"Unsupported category '{category}'. Allowed: {allowed}.")

    response.headers["Cache-Control"] = TAG_CACHE_CONTROL
    results = librarian.list_tags(
        category=normalized_category,
        query=name,
        title_query=filters["query"],
        min_count=min_count,
        limit=limit,
        offset=offset,
        sort=sort,
        include_filters=filters["include_filters"],
        exclude_filters=filters["exclude_filters"],
        filter_modes=filters["filter_modes"],
        completed=filters["completed"],
        min_pages=filters["min_pages"],
        max_pages=filters["max_pages"],
    )
    return {
        "category": normalized_category,
        "query": name,
        "gallery_scope": {
            "title_query": filters["query"],
            "filters": filters["public_filters"],
        },
        "matching_galleries": results["matching_galleries"],
        "total": results["total"],
        "items": results["items"],
    }


@api_router.get("/tags/by-category/{category}")
async def list_tags_by_category(
    category: str,
    filters: Annotated[dict, Depends(build_gallery_filters)],
    response: Response,
    name: str = "",
    min_count: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=250)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: TagSort = "popular",
):
    normalized_category = category.strip().lower()
    if normalized_category not in VALID_FILTER_CATEGORIES:
        allowed = ", ".join(sorted(VALID_FILTER_CATEGORIES))
        raise HTTPException(status_code=422, detail=f"Unsupported category '{category}'. Allowed: {allowed}.")

    response.headers["Cache-Control"] = TAG_CACHE_CONTROL
    results = librarian.list_tags(
        category=normalized_category,
        query=name,
        title_query=filters["query"],
        min_count=min_count,
        limit=limit,
        offset=offset,
        sort=sort,
        include_filters=filters["include_filters"],
        exclude_filters=filters["exclude_filters"],
        filter_modes=filters["filter_modes"],
        completed=filters["completed"],
        min_pages=filters["min_pages"],
        max_pages=filters["max_pages"],
    )
    return {
        "category": normalized_category,
        "query": name,
        "gallery_scope": {
            "title_query": filters["query"],
            "filters": filters["public_filters"],
        },
        "matching_galleries": results["matching_galleries"],
        "total": results["total"],
        "items": results["items"],
    }


def _frontend_response(path: str) -> Response:
    if not FRONTEND_INDEX.exists():
        return HTMLResponse(
            (
                "Ishtar frontend has not been built yet. "
                "Run `npm run build` in `IshtarCollective/gate` to generate `ishtar_frontend_dist`."
            ),
            status_code=503,
        )

    if path in {"", "/"}:
        return FileResponse(FRONTEND_INDEX)

    candidate = (FRONTEND_DIST_DIR / path).resolve()
    dist_root = FRONTEND_DIST_DIR.resolve()
    if dist_root not in {candidate, *candidate.parents}:
        raise HTTPException(status_code=404, detail="Not found")

    if candidate.exists() and candidate.is_file():
        media_type, _ = mimetypes.guess_type(candidate.name)
        return FileResponse(candidate, media_type=media_type)

    if Path(path).suffix:
        raise HTTPException(status_code=404, detail="Static asset not found")

    return FileResponse(FRONTEND_INDEX)


@router.get("/ishtar", include_in_schema=False)
async def ishtar_frontend_root() -> Response:
    return _frontend_response("")


@router.get("/ishtar/{path:path}", include_in_schema=False)
async def ishtar_frontend(path: str) -> Response:
    return _frontend_response(path)


router.include_router(api_router)
