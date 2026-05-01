from pathlib import Path
from fastapi import FastAPI, HTTPException
from sqlmodel import Session, func, select
from librarian import Librarian
from data_schemas import Manga_Series, Manga_Chapter
from scanner import Indexer
from typing import List
from fastapi import Response
from reader import VaultReader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import os


DEFAULT_LIBRARY_PATH = Path(r"D:\Wandering_Sea\T7_Branch\Sarcophagus\CV_Tomb")


def env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}

BACKEND_HOST = os.getenv("CODEX_VAULT_BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("CODEX_VAULT_BACKEND_PORT", "6220"))
FRONTEND_PORT = int(os.getenv("CODEX_VAULT_FRONTEND_PORT", "6221"))
DB_PATH = os.getenv("CODEX_VAULT_DB_PATH", "codex_vault.db")
LIBRARY_ROOT = Path(os.getenv("CODEX_VAULT_LIBRARY_PATH", str(DEFAULT_LIBRARY_PATH))).expanduser()
LIBRARY_PATH = str(LIBRARY_ROOT)
DEBUG_MODE = env_flag("CODEX_VAULT_DEBUG", True)
DEFAULT_FRONTEND_ORIGINS = [
    f"http://localhost:{FRONTEND_PORT}",
    f"http://127.0.0.1:{FRONTEND_PORT}",
]
EXTRA_FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CODEX_VAULT_FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]
FRONTEND_ORIGIN_REGEX = os.getenv(
    "CODEX_VAULT_FRONTEND_ORIGIN_REGEX",
    rf"^https?://[^/]+:{FRONTEND_PORT}$"
)
IMAGE_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}

app = FastAPI(
    title="Codex Vault API",
    description="The digital archives for your manga collection.",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*DEFAULT_FRONTEND_ORIGINS, *EXTRA_FRONTEND_ORIGINS],
    allow_origin_regex=FRONTEND_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)


def normalize_path(path_value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path_value)))


def preferred_series_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None

    stored_path = Path(path_value)
    preferred_path = LIBRARY_ROOT / stored_path.name if stored_path.name else LIBRARY_ROOT

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


cerejeira = Librarian(db_name=DB_PATH, debug=DEBUG_MODE)
assistant = Indexer(cerejeira, LIBRARY_PATH)
SELECTIVE_INDEX_PAGE = Path(__file__).with_name("selective_index.html")


def migrate_series_paths() -> None:
    if not LIBRARY_ROOT.exists():
        print(f"WARNING: Library root does not exist: {LIBRARY_ROOT}")
        return

    with Session(cerejeira.engine) as session:
        all_series = list(session.exec(select(Manga_Series).order_by(Manga_Series.id)))
        reserved_paths = {
            normalize_path(series.path): series.id
            for series in all_series
            if series.path
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
                print(
                    f"WARNING: Skipping path migration for '{series.title}' "
                    f"because {preferred_path} is already assigned."
                )
                continue

            print(f"Migrating '{series.title}' path to {preferred_path}")
            reserved_paths.pop(current_norm, None)
            reserved_paths[preferred_norm] = series.id
            series.path = str(preferred_path)
            session.add(series)
            updated_count += 1

        if updated_count:
            session.commit()
            print(f"Migrated {updated_count} series paths to {LIBRARY_ROOT}")


migrate_series_paths()


class SelectiveIndexRequest(BaseModel):
    keep_series_ids: List[int] = []


@app.get("/", tags=["General"])
async def root():
    """Welcome message for the Codex Vault."""
    return {"message": "Welcome to the Codex Vault. The Librarian is on duty."}


@app.get("/report/all_manga", response_model=List[Manga_Series], tags=["Collection"])
async def get_all_manga():
    """Ask the Librarian to list every manga on the shelves."""
    return cerejeira.get_all_series()

@app.get("/report/series/{series_id}", response_model=Manga_Series, tags=["Collection"])
async def get_series_details(series_id: int):
    """Ask the Librarian for the details of a specific manga series."""
    with Session(cerejeira.engine) as session:
        series = session.get(Manga_Series, series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Manga series not found")
        return series


@app.get("/report/homepage", tags=["Collection"])
async def get_homepage_data():
    """
    Returns a summary of all manga series including chapter counts 
    specifically formatted for the frontend dashboard.
    """
    with Session(cerejeira.engine) as session:
        # We query the Series and a count of their related Chapters
        # Using a join is much faster than fetching everything and filtering in Python
        statement = (
            select(Manga_Series, func.count(Manga_Chapter.id).label("chapter_count"))
            .outerjoin(Manga_Chapter)
            .group_by(Manga_Series.id)
        )
        results = session.exec(statement).all()

        homepage_list = []
        for series, count in results:
            homepage_list.append({
                "id": series.id,
                "title": series.title,
                "path": series.path,
                "author": series.author,
                "status": series.status,
                "cover_image": series.cover_image,
                "chapterCount": count
            })
            
        return {"mangaList": homepage_list}


@app.get("/report/chapters", response_model=List[Manga_Chapter], tags=["Collection"])
async def get_chapters_for(series_id: int):
    """Ask the Librarian to list every manga on the shelves."""
    return cerejeira.get_chapters_for(series_id)




@app.post("/archive/manga", response_model=Manga_Series, tags=["Collection"])
async def add_manga_series(series: Manga_Series):
    """Hand a new manga series to the Librarian for archiving."""
    try:
        return cerejeira.add_new_series(series)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/archive/chapter", response_model=Manga_Chapter, tags=["Collection"])
async def add_manga_chapter(chapter: Manga_Chapter):
    """Hand a new manga chapter to the Librarian for archiving."""
    try:
        return cerejeira.add_new_chapter_to_series(chapter)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/index", tags=["Indexing"])
async def index_manga():
    """Ask the Librarian to scan the manga library for new manga."""
    return assistant.run_scan()


@app.get("/admin/selective-index", response_class=HTMLResponse, tags=["Admin"])
async def selective_index_page():
    """Small admin page for selective rebuilds."""
    if not SELECTIVE_INDEX_PAGE.exists():
        raise HTTPException(status_code=404, detail="Selective index page not found")
    return HTMLResponse(SELECTIVE_INDEX_PAGE.read_text(encoding="utf-8"))


@app.get("/admin/selective-index/data", tags=["Admin"])
async def selective_index_data():
    """List all indexed manga so the selective rebuild page can render a table."""
    with Session(cerejeira.engine) as session:
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


@app.post("/admin/selective-index/run", tags=["Admin"])
async def selective_index_run(payload: SelectiveIndexRequest):
    """
    Keep the checked series untouched, delete the unchecked rows, then re-scan only those
    unchecked folders so metadata/thumbnails rebuild without touching the rest of the library.
    """
    keep_ids = set(payload.keep_series_ids or [])

    with Session(cerejeira.engine) as session:
        all_series = list(session.exec(select(Manga_Series).order_by(Manga_Series.title)))
        rebuild_targets = [series for series in all_series if series.id not in keep_ids]

        rebuild_paths = []
        removed_titles = []

        for series in rebuild_targets:
            rebuild_paths.append(str(resolve_series_base_path(series)))
            removed_titles.append(series.title)

            chapters = list(
                session.exec(
                    select(Manga_Chapter).where(Manga_Chapter.series_id == series.id)
                )
            )
            for chapter in chapters:
                session.delete(chapter)

            session.delete(series)

        session.commit()

    unique_rebuild_paths = list(dict.fromkeys(rebuild_paths))
    scan_result = (
        assistant.run_scan_for_paths(unique_rebuild_paths)
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



@app.get("/view/chapter/{chapter_id}/pages", tags=["Reader"])
async def get_pages(chapter_id: int):
    """Lists all images in a chapter."""
    with Session(cerejeira.engine) as session:
        chapter = session.get(Manga_Chapter, chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        
        series = session.get(Manga_Series, chapter.series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Series for this chapter not found")
        
        # Combine paths safely using Pathlib
        full_path = resolve_series_base_path(series) / chapter.folder_path
        
        return VaultReader.get_image_list(full_path)

@app.get("/view/chapter/{chapter_id}/page/{page_name}", tags=["Reader"])
async def get_page(chapter_id: int, page_name: str):
    with Session(cerejeira.engine) as session:
        chapter = session.get(Manga_Chapter, chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
            
        series = session.get(Manga_Series, chapter.series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Series not found")
            
        full_path = resolve_series_base_path(series) / chapter.folder_path
        
        # Pass ALL THREE arguments: path, id, and name
        image_bytes = VaultReader.get_page_data(full_path, chapter_id, page_name)
        
        if image_bytes is None:
            raise HTTPException(status_code=404, detail="Page not found")

        ext = page_name.split('.')[-1].lower()
        media_type = f"image/{ext}" if ext != 'jpg' else "image/jpeg"
        
        return Response(content=image_bytes, media_type=media_type, headers=IMAGE_CACHE_HEADERS)
    
    
    
    
    
@app.get("/view/series/cover/{series_id}", tags=["Reader"])
async def get_cover(series_id: int):
    with Session(cerejeira.engine) as session:
        series = session.get(Manga_Series, series_id)
        if not series or not series.path:
            raise HTTPException(status_code=404, detail="Series not in Database")

        # 1. Construct the base path
        base_path = resolve_series_base_path(series)
        
        # 2. Try to find the file (Checking both extensions)
        valid_extensions = [".png", ".jpg", ".jpeg", ".webp"]
        target_file = None
        
        for ext in valid_extensions:
            # We check for 'cover.png', 'cover.jpg', etc.
            potential_path = base_path / f"cover{ext}"
            if potential_path.exists():
                target_file = potential_path
                break
        
        # 3. If still not found, check if the DB has a specific filename stored
        if not target_file and series.cover_image:
            potential_path = base_path / series.cover_image
            if potential_path.exists():
                target_file = potential_path

        # 4. Final check & Debugging
        if not target_file:
            print(f"DEBUG: Librarian searched in {base_path} but found no cover files.")
            raise HTTPException(status_code=404, detail="Cover file not found on disk")

        # 5. Serve the file
        content = target_file.read_bytes()
        # Determine media type by extension
        media_type = "image/png" if target_file.suffix.lower() == ".png" else "image/jpeg"
        
        return Response(content=content, media_type=media_type)
    
@app.get("/view/chapter/{chapter_id}/page/{page_name}/thumb", tags=["Reader"])
async def get_page_thumbnail(chapter_id: int, page_name: str):
    """Get an optimized thumbnail of a page for preview grids."""
    with Session(cerejeira.engine) as session:
        chapter = session.get(Manga_Chapter, chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
            
        series = session.get(Manga_Series, chapter.series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Series not found")
            
        full_path = resolve_series_base_path(series) / chapter.folder_path
        
        # Get thumbnail version
        thumb_bytes = VaultReader.get_thumbnail_data(full_path, chapter_id, page_name)
        
        if thumb_bytes is None:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Thumbnails are always JPEG
        return Response(content=thumb_bytes, media_type="image/jpeg", headers=IMAGE_CACHE_HEADERS)


@app.post("/admin/generate-thumbnails/{series_id}", tags=["Admin"])
async def generate_thumbnails_for_series(series_id: int):
    """Pre-generate all thumbnails for a series to speed up browsing."""
    with Session(cerejeira.engine) as session:
        series = session.get(Manga_Series, series_id)
        if not series:
            raise HTTPException(404)
        
        chapters = cerejeira.get_chapters_for(series_id)
        
        total_generated = 0
        for chapter in chapters:
            cbz_path = resolve_series_base_path(series) / chapter.folder_path
            image_list = VaultReader.get_image_list(cbz_path)
            
            for img_name in image_list:
                VaultReader.get_thumbnail_data(cbz_path, chapter.id, img_name)
                total_generated += 1
        
        return {
            "status": "success", 
            "series": series.title,
            "chapters": len(chapters),
            "thumbnails_generated": total_generated
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)
