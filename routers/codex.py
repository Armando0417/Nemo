from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlmodel import Session, func, select

from codex.config import get_settings
from codex.schemas import Manga_Chapter, Manga_Series
from codex.services.librarian import Librarian
from codex.services.reader import VaultReader
from codex.services.scanner import Indexer
from codex.services.simple_indexer import MappingMode, build_simple_index

logger = logging.getLogger("nemo.codex")

settings = get_settings()
VaultReader.configure(settings.cache_dir)

librarian = Librarian(db_path=str(settings.db_path), debug=settings.debug)
indexer = Indexer(librarian, str(settings.library_root))

IMAGE_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}
LIST_CACHE_HEADERS = {"Cache-Control": "public, max-age=30"}
FRONTEND_DIST_DIR = settings.frontend_dist_dir
FRONTEND_INDEX = FRONTEND_DIST_DIR / "index.html"
SELECTIVE_INDEX_PAGE = settings.selective_index_html

router = APIRouter()
api_router = APIRouter(prefix="/api/codex", tags=["Codex"])


def normalize_path(path_value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path_value)))


def preferred_series_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None

    stored_path = Path(path_value)
    preferred_path = settings.library_root / stored_path.name if stored_path.name else settings.library_root

    if preferred_path.exists():
        return preferred_path
    if stored_path.exists():
        return stored_path
    return preferred_path


def resolve_series_base_path(series: Manga_Series) -> Path:
    resolved_path = preferred_series_path(series.path)
    if resolved_path is None:
        raise HTTPException(status_code=404, detail="Series path not configured")
    return resolved_path


def migrate_series_paths() -> None:
    if not settings.library_root.exists():
        logger.warning("Codex library root does not exist: %s", settings.library_root)
        return

    with Session(librarian.engine) as session:
        all_series = list(session.exec(select(Manga_Series).order_by(Manga_Series.id)))
        reserved_paths = {
            normalize_path(series.path): series.id for series in all_series if series.path
        }
        updated_count = 0

        for series in all_series:
            preferred_path = preferred_series_path(series.path)
            if preferred_path is None or not preferred_path.exists():
                continue

            current_norm = normalize_path(series.path)
            preferred_norm = normalize_path(preferred_path)
            if current_norm == preferred_norm:
                continue

            existing_series_id = reserved_paths.get(preferred_norm)
            if existing_series_id and existing_series_id != series.id:
                logger.warning(
                    "Skipping Codex path migration for %s because %s is already assigned.",
                    series.title,
                    preferred_path,
                )
                continue

            reserved_paths.pop(current_norm, None)
            reserved_paths[preferred_norm] = series.id
            series.path = str(preferred_path)
            session.add(series)
            updated_count += 1

        if updated_count:
            session.commit()
            logger.info("Migrated %s Codex series paths to %s.", updated_count, settings.library_root)


migrate_series_paths()


def warm_adjacent_pages_after_response(full_path: Path, chapter_id: int, page_name: str) -> None:
    image_list = VaultReader.get_image_list(full_path)
    if image_list:
        VaultReader.warm_adjacent_pages(full_path, chapter_id, image_list, page_name)


class SelectiveIndexRequest(BaseModel):
    keep_series_ids: list[int] = []


class SimpleIndexRequest(BaseModel):
    folder: str
    url: str
    mapping: MappingMode = "auto"
    chapter_glob: str = "*.cbz"
    cover_entry: str = "cover.jpg"
    download_cover: bool = True
    overwrite_cover: bool = False
    overwrite_cbz: bool = False
    run_scan: bool = True


@api_router.get("")
def root() -> dict[str, str]:
    return {"message": "Welcome to the Codex section inside Nemo."}


@api_router.get("/report/all_manga", response_model=list[Manga_Series])
def get_all_manga() -> list[Manga_Series]:
    return librarian.get_all_series()


@api_router.get("/report/series/{series_id}", response_model=Manga_Series)
def get_series_details(series_id: int) -> Manga_Series:
    with Session(librarian.engine) as session:
        series = session.get(Manga_Series, series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Manga series not found")
        return series


@api_router.get("/report/homepage")
def get_homepage_data() -> dict[str, list[dict[str, object]]]:
    with Session(librarian.engine) as session:
        statement = (
            select(Manga_Series, func.count(Manga_Chapter.id).label("chapter_count"))
            .outerjoin(Manga_Chapter)
            .group_by(Manga_Series.id)
        )
        results = session.exec(statement).all()

    homepage_list = []
    for series, count in results:
        homepage_list.append(
            {
                "id": series.id,
                "title": series.title,
                "path": series.path,
                "author": series.author,
                "status": series.status,
                "cover_image": series.cover_image,
                "chapterCount": count,
            }
        )

    return {"mangaList": homepage_list}


@api_router.get("/report/chapters", response_model=list[Manga_Chapter])
def get_chapters_for(series_id: int) -> list[Manga_Chapter]:
    return librarian.get_chapters_for(series_id)


@api_router.post("/archive/manga", response_model=Manga_Series)
def add_manga_series(series: Manga_Series) -> Manga_Series:
    try:
        return librarian.add_new_series(series)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.post("/archive/chapter", response_model=Manga_Chapter)
def add_manga_chapter(chapter: Manga_Chapter) -> Manga_Chapter:
    try:
        return librarian.add_new_chapter_to_series(chapter)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.get("/index")
def index_manga() -> dict[str, object]:
    return indexer.run_scan()


@api_router.post("/admin/simple-index")
def simple_index(payload: SimpleIndexRequest) -> dict[str, object]:
    try:
        result = build_simple_index(
            folder=payload.folder,
            url=payload.url,
            mapping=payload.mapping,
            chapter_glob=payload.chapter_glob,
            cover_entry=payload.cover_entry,
            download_cover=payload.download_cover,
            overwrite_cover=payload.overwrite_cover,
            overwrite_cbz=payload.overwrite_cbz,
        )
        if payload.run_scan:
            result["scan_result"] = indexer.run_scan_for_paths([payload.folder])
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.get("/admin/selective-index", response_class=HTMLResponse)
def selective_index_page() -> HTMLResponse:
    if not SELECTIVE_INDEX_PAGE.exists():
        raise HTTPException(status_code=404, detail="Selective index page not found")
    return HTMLResponse(SELECTIVE_INDEX_PAGE.read_text(encoding="utf-8"))


@api_router.get("/admin/selective-index/data")
def selective_index_data() -> dict[str, list[dict[str, object]]]:
    with Session(librarian.engine) as session:
        statement = (
            select(Manga_Series, func.count(Manga_Chapter.id).label("chapter_count"))
            .outerjoin(Manga_Chapter)
            .group_by(Manga_Series.id)
            .order_by(Manga_Series.title)
        )
        results = session.exec(statement).all()

    series_rows = []
    for series, count in results:
        series_rows.append(
            {
                "id": series.id,
                "title": series.title,
                "author": series.author,
                "status": series.status,
                "path": series.path,
                "chapterCount": count,
            }
        )

    return {"series": series_rows}


@api_router.post("/admin/selective-index/run")
def selective_index_run(payload: SelectiveIndexRequest) -> dict[str, object]:
    keep_ids = set(payload.keep_series_ids or [])

    with Session(librarian.engine) as session:
        all_series = list(session.exec(select(Manga_Series).order_by(Manga_Series.title)))
        rebuild_targets = [series for series in all_series if series.id not in keep_ids]

        rebuild_paths: list[str] = []
        removed_titles: list[str] = []

        for series in rebuild_targets:
            rebuild_paths.append(str(resolve_series_base_path(series)))
            removed_titles.append(series.title)

            chapters = list(
                session.exec(select(Manga_Chapter).where(Manga_Chapter.series_id == series.id))
            )
            for chapter in chapters:
                session.delete(chapter)

            session.delete(series)

        session.commit()

    unique_rebuild_paths = list(dict.fromkeys(rebuild_paths))
    scan_result = (
        indexer.run_scan_for_paths(unique_rebuild_paths)
        if unique_rebuild_paths
        else {
            "status": "success",
            "stats": {
                "new_series": 0,
                "new_chapters": 0,
                "updated_series": 0,
                "updated_chapters": 0,
                "thumbnails_generated": 0,
            },
        }
    )

    return {
        "status": "success",
        "kept_series_count": len(all_series) - len(removed_titles),
        "deleted_series_count": len(removed_titles),
        "reindexed_folder_count": len(unique_rebuild_paths),
        "deleted_titles": removed_titles,
        "scan_result": scan_result,
    }


@api_router.get("/view/chapter/{chapter_id}/pages")
def get_pages(chapter_id: int, background_tasks: BackgroundTasks, response: Response) -> list[str]:
    started_at = time.perf_counter()
    with Session(librarian.engine) as session:
        chapter = session.get(Manga_Chapter, chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")

        series = session.get(Manga_Series, chapter.series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Series for this chapter not found")

        full_path = resolve_series_base_path(series) / chapter.folder_path
        image_list = VaultReader.get_image_list(full_path)
        response.headers.update(LIST_CACHE_HEADERS)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        if elapsed_ms > 500:
            logger.info(
                "Codex page list loaded slowly: chapter=%s pages=%s elapsed=%.1fms path=%s.",
                chapter_id,
                len(image_list),
                elapsed_ms,
                full_path,
            )
        if settings.background_warming and image_list:
            background_tasks.add_task(
                VaultReader.warm_chapter_assets,
                full_path,
                chapter.id,
                image_list,
            )
        return image_list


@api_router.get("/view/chapter/{chapter_id}/page/{page_name}")
def get_page(chapter_id: int, page_name: str, background_tasks: BackgroundTasks) -> Response:
    started_at = time.perf_counter()
    with Session(librarian.engine) as session:
        chapter = session.get(Manga_Chapter, chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")

        series = session.get(Manga_Series, chapter.series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Series not found")

        full_path = resolve_series_base_path(series) / chapter.folder_path
        if settings.background_warming:
            background_tasks.add_task(
                warm_adjacent_pages_after_response,
                full_path,
                chapter.id,
                page_name,
            )
        page_file = VaultReader.ensure_page_cached(full_path, chapter_id, page_name)
        if page_file is None:
            raise HTTPException(status_code=404, detail="Page not found")

        media_type = VaultReader.get_page_media_type(page_name)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        if elapsed_ms > 500:
            logger.info(
                "Codex page served slowly: chapter=%s page=%s elapsed=%.1fms cached_file=%s.",
                chapter_id,
                page_name,
                elapsed_ms,
                page_file,
            )
        return FileResponse(page_file, media_type=media_type, headers=IMAGE_CACHE_HEADERS)


@api_router.get("/view/series/cover/{series_id}")
def get_cover(series_id: int) -> Response:
    with Session(librarian.engine) as session:
        series = session.get(Manga_Series, series_id)
        if not series or not series.path:
            raise HTTPException(status_code=404, detail="Series not in database")

        base_path = resolve_series_base_path(series)
        valid_extensions = [".png", ".jpg", ".jpeg", ".webp"]
        target_file = None

        for ext in valid_extensions:
            potential_path = base_path / f"cover{ext}"
            if potential_path.exists():
                target_file = potential_path
                break

        if not target_file and series.cover_image:
            potential_path = base_path / series.cover_image
            if potential_path.exists():
                target_file = potential_path

        if not target_file:
            raise HTTPException(status_code=404, detail="Cover file not found on disk")

        suffix = target_file.suffix.lower()
        media_type = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
        return FileResponse(target_file, media_type=media_type, headers=IMAGE_CACHE_HEADERS)


@api_router.get("/view/chapter/{chapter_id}/page/{page_name}/thumb")
def get_page_thumbnail(chapter_id: int, page_name: str) -> Response:
    with Session(librarian.engine) as session:
        chapter = session.get(Manga_Chapter, chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")

        series = session.get(Manga_Series, chapter.series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Series not found")

        full_path = resolve_series_base_path(series) / chapter.folder_path
        thumb_file = VaultReader.ensure_thumbnail_cached(full_path, chapter_id, page_name)
        if thumb_file is None:
            raise HTTPException(status_code=404, detail="Page not found")

        return FileResponse(
            thumb_file,
            media_type=VaultReader.get_page_media_type(thumb_file.name),
            headers=IMAGE_CACHE_HEADERS,
        )


@api_router.post("/admin/generate-thumbnails/{series_id}")
def generate_thumbnails_for_series(series_id: int) -> dict[str, object]:
    with Session(librarian.engine) as session:
        series = session.get(Manga_Series, series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Series not found")

    chapters = librarian.get_chapters_for(series_id)
    total_generated = 0
    for chapter in chapters:
        cbz_path = resolve_series_base_path(series) / chapter.folder_path
        image_list = VaultReader.get_image_list(cbz_path)

        for image_name in image_list:
            VaultReader.get_thumbnail_data(cbz_path, chapter.id, image_name)
            total_generated += 1

    return {
        "status": "success",
        "series": series.title,
        "chapters": len(chapters),
        "thumbnails_generated": total_generated,
    }


def _frontend_response(path: str) -> Response:
    if not FRONTEND_INDEX.exists():
        return HTMLResponse(
            (
                "Codex frontend has not been built yet. "
                "Run `npm run build` in `CodexVault/CodexVault` to generate `codex_frontend_dist`."
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


@router.get("/codex", include_in_schema=False)
def codex_frontend_root() -> Response:
	return _frontend_response("")


@router.get("/codex/{path:path}", include_in_schema=False)
def codex_frontend(path: str) -> Response:
	return _frontend_response(path)


router.include_router(api_router)
