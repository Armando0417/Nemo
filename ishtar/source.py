from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ishtar.config import get_settings

METADATA_FILENAME = "metadata.json"
FAILED_PAGES_FILENAME = "failed_pages.json"


def get_source_root() -> Path:
    return get_settings().source_root


def is_recursive_scan_enabled() -> bool:
    return get_settings().recursive_scan


def iter_gallery_folders(base_path: str | Path | None = None) -> Iterable[Path]:
    root = Path(base_path) if base_path else get_source_root()
    if not root.exists():
        return []

    if is_recursive_scan_enabled():
        return (metadata_path.parent for metadata_path in root.rglob(METADATA_FILENAME))

    return (
        child
        for child in root.iterdir()
        if child.is_dir() and (child / METADATA_FILENAME).exists()
    )


def load_metadata(gallery_folder: str | Path) -> Optional[Dict[str, Any]]:
    metadata_path = Path(gallery_folder) / METADATA_FILENAME
    if not metadata_path.exists():
        return None

    with metadata_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_metadata(raw: Dict[str, Any], gallery_folder: str | Path) -> Dict[str, Any]:
    folder = Path(gallery_folder)

    def pick_first(*values: Any, default: str = "Unknown") -> str:
        for value in values:
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str) and value.strip():
                return value
        return default

    def pick_list(*values: Any) -> list[str]:
        for value in values:
            if isinstance(value, list):
                return [str(item) for item in value if str(item).strip()]
        return []

    return {
        "media_id": str(raw.get("media_id") or raw.get("id") or folder.name),
        "title": str(raw.get("title") or folder.name),
        "page_count": int(raw.get("page_count") or 0),
        "upload_date": str(raw.get("upload_date") or ""),
        "artist": pick_first(raw.get("artist"), raw.get("artists")),
        "series": pick_first(raw.get("series"), raw.get("parodies"), default="Original"),
        "group": pick_first(raw.get("group"), raw.get("groups")),
        "featured_characters": pick_list(raw.get("featured_characters"), raw.get("characters")),
        "tags": pick_list(raw.get("tags")),
        "path": str(folder),
        "is_completed": not (folder / FAILED_PAGES_FILENAME).exists(),
    }


@lru_cache(maxsize=1)
def build_media_index(base_path: str | None = None) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for folder in iter_gallery_folders(base_path):
        metadata = load_metadata(folder)
        if not metadata:
            continue

        media_id = str(metadata.get("media_id") or metadata.get("id") or folder.name)
        index[media_id] = str(folder)

    return index


def clear_media_index_cache() -> None:
    build_media_index.cache_clear()


def resolve_gallery_path(gallery: Any) -> Optional[str]:
    current_path = Path(gallery.path)
    if current_path.exists():
        return str(current_path)

    return build_media_index().get(str(gallery.media_id))
