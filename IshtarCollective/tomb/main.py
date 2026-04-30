import os
import re
from typing import Annotated, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlmodel import Session

from data_schemas import Gallery
from gallery_source import (
    clear_media_index_cache,
    get_source_root,
    iter_gallery_folders,
    resolve_gallery_path,
)
from librarian import Librarian

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

app = FastAPI(
    title="Codex Vault API",
    description="The digital archives for your manga collection.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cerejeira = Librarian(debug=True)
STATIC_PATH = str(get_source_root())


def natural_sort_key(value: str):
    """Sort strings containing numbers naturally: 1, 2, 10 instead of 1, 10, 2."""
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", value)]


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


@app.get("/", tags=["General"])
async def root():
    return {"message": "Welcome to the Codex Vault. The Librarian is on duty."}


@app.get("/system/populate", tags=["System"])
async def populate_tomb(base_path: str = STATIC_PATH):
    if not os.path.exists(base_path):
        raise HTTPException(status_code=404, detail="Storage path not found")

    clear_media_index_cache()
    archived_count = 0
    folders = [str(folder) for folder in iter_gallery_folders(base_path)]

    for folder in folders:
        try:
            result = cerejeira.archive_gallery_from_disk(folder)
            if result:
                archived_count += 1
        except Exception as exc:
            print(f"Error archiving {folder}: {exc}")
            continue

    return {
        "status": "Success",
        "message": f"Scanned {len(folders)} folders, archived {archived_count} new galleries.",
    }


@app.get("/report/galleries", tags=["Collection"])
async def get_galleries(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    results = cerejeira.search_galleries(limit=limit, offset=offset, sort="newest")
    return {
        "total": results["total"],
        "items": results["items"],
    }


@app.get("/view/gallery/{gallery_id}/pages", tags=["Reader"])
async def get_gallery_pages(gallery_id: int):
    with Session(cerejeira.engine) as session:
        gallery = session.get(Gallery, gallery_id)
        gallery_path = resolve_gallery_path(gallery) if gallery else None
        if not gallery or not gallery_path or not os.path.exists(gallery_path):
            raise HTTPException(status_code=404)

        valid_exts = (".jpg", ".jpeg", ".png", ".webp")
        raw_files = [file_name for file_name in os.listdir(gallery_path) if file_name.lower().endswith(valid_exts)]
        images = sorted(raw_files, key=natural_sort_key)

        return {
            "title": gallery.title,
            "pages": images,
        }


@app.get("/view/gallery/{gallery_id}/thumbnail", tags=["Reader"])
async def get_gallery_thumbnail(gallery_id: int):
    with Session(cerejeira.engine) as session:
        gallery = session.get(Gallery, gallery_id)
        gallery_path = resolve_gallery_path(gallery) if gallery else None
        if not gallery or not gallery_path or not os.path.exists(gallery_path):
            raise HTTPException(status_code=404, detail="Gallery not found on disk")

        valid_exts = (".jpg", ".jpeg", ".png", ".webp")
        images = sorted([file_name for file_name in os.listdir(gallery_path) if file_name.lower().endswith(valid_exts)])

        if not images:
            raise HTTPException(status_code=404, detail="No images found in folder")

        cover_path = os.path.join(gallery_path, images[0])
        ext = os.path.splitext(cover_path)[1].lower()
        media_type = f"image/{ext[1:]}" if ext != ".jpg" else "image/jpeg"

        return Response(content=open(cover_path, "rb").read(), media_type=media_type)


@app.get("/view/gallery/{gallery_id}/page/{filename}", tags=["Reader"])
async def serve_page_file(gallery_id: int, filename: str):
    with Session(cerejeira.engine) as session:
        gallery = session.get(Gallery, gallery_id)
        gallery_path = resolve_gallery_path(gallery) if gallery else None
        if not gallery or not gallery_path:
            raise HTTPException(status_code=404)

        file_path = os.path.join(gallery_path, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404)

        return FileResponse(file_path)


@app.get("/api/gallery/{gallery_id}", tags=["API"])
async def get_gallery_detail(gallery_id: int):
    with Session(cerejeira.engine) as session:
        gallery = session.get(Gallery, gallery_id)
        if not gallery:
            raise HTTPException(status_code=404, detail="Gallery not found")
        return _serialize_gallery_detail(gallery)


@app.get("/api/gallery/{gallery_id}/related", tags=["API"])
async def get_related_galleries(
    gallery_id: int,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
):
    results = cerejeira.get_related_galleries(gallery_id=gallery_id, limit=limit)
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


@app.get("/api/search", tags=["API"])
async def search_galleries(
    filters: Annotated[dict, Depends(build_gallery_filters)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: SearchSort = "relevance",
):
    results = cerejeira.search_galleries(
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
    )
    return {
        "total": results["total"],
        "query": filters["query"],
        "sort": results["sort"],
        "filters": filters["public_filters"],
        "items": results["items"],
    }


@app.get("/api/search/random", tags=["API"])
async def get_random_galleries(
    filters: Annotated[dict, Depends(build_gallery_filters)],
    count: Annotated[int, Query(ge=1, le=50)] = 1,
):
    results = cerejeira.pick_random_galleries(
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


@app.get("/api/search/facets", tags=["API"])
async def get_search_facets(
    filters: Annotated[dict, Depends(build_gallery_filters)],
    per_category_limit: Annotated[int, Query(ge=1, le=100)] = 12,
):
    results = cerejeira.get_facets(
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


@app.get("/api/tags", tags=["API"])
async def list_tags(
    filters: Annotated[dict, Depends(build_gallery_filters)],
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

    results = cerejeira.list_tags(
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


@app.get("/api/tags/by-category/{category}", tags=["API"])
async def list_tags_by_category(
    category: str,
    filters: Annotated[dict, Depends(build_gallery_filters)],
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

    results = cerejeira.list_tags(
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
