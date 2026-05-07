from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path
from typing import List
from functools import lru_cache
import shutil
import time
import zipfile

from PIL import Image

logger = logging.getLogger("nemo.codex.reader")


def natural_sort_key(value: str):
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", value)]


@lru_cache(maxsize=4096)
def _read_image_list(cbz_path_value: str) -> tuple[str, ...]:
    cbz_path = Path(cbz_path_value)
    if not cbz_path.exists():
        return ()

    with zipfile.ZipFile(cbz_path, "r") as archive:
        images = [
            entry
            for entry in archive.namelist()
            if entry.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        ]
        images.sort(key=natural_sort_key)
        return tuple(images)


class VaultReader:
    CACHE_DIR = Path("./vault_cache")
    THUMB_CACHE_DIR = CACHE_DIR / "thumbnails"
    MAX_CACHE_FILES = 1000
    THUMB_WIDTH = 400
    THUMB_QUALITY = 85
    CACHE_ENFORCE_INTERVAL_SECONDS = 60.0
    _last_cache_enforcement = 0.0

    @classmethod
    def configure(cls, cache_dir: Path) -> None:
        cls.CACHE_DIR = Path(cache_dir)
        cls.THUMB_CACHE_DIR = cls.CACHE_DIR / "thumbnails"

    @classmethod
    def _setup_cache_dirs(cls) -> None:
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cls.THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_image_list(cbz_path: Path) -> List[str]:
        return list(_read_image_list(str(cbz_path.resolve())))

    @classmethod
    def _enforce_cache_limit(cls) -> None:
        now = time.time()
        if now - cls._last_cache_enforcement < cls.CACHE_ENFORCE_INTERVAL_SECONDS:
            return

        cls._last_cache_enforcement = now
        all_files = [
            file_path
            for file_path in cls.CACHE_DIR.rglob("*")
            if file_path.is_file() and cls.THUMB_CACHE_DIR not in file_path.parents
        ]

        if len(all_files) < cls.MAX_CACHE_FILES:
            return

        all_files.sort(key=lambda file_path: file_path.stat().st_atime)
        to_delete = len(all_files) - cls.MAX_CACHE_FILES + 1
        for file_path in all_files[:to_delete]:
            file_path.unlink(missing_ok=True)

    @classmethod
    def get_page_media_type(cls, page_name: str) -> str:
        suffix = Path(page_name).suffix.lower()
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(suffix, "application/octet-stream")

    @classmethod
    def ensure_page_cached(cls, cbz_path: Path, chapter_id: int, page_name: str) -> Path | None:
        cls._setup_cache_dirs()

        cache_file = cls.CACHE_DIR / str(chapter_id) / Path(page_name)

        if cache_file.exists():
            os.utime(cache_file, None)
            return cache_file

        cls._enforce_cache_limit()

        if not cbz_path.exists():
            return None

        try:
            started_at = time.perf_counter()
            with zipfile.ZipFile(cbz_path, "r") as archive:
                with archive.open(page_name, "r") as source:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    with cache_file.open("wb") as target:
                        shutil.copyfileobj(source, target, length=1024 * 256)
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                if elapsed_ms > 500:
                    logger.info(
                        "Extracted Codex page slowly: chapter=%s page=%s elapsed=%.1fms.",
                        chapter_id,
                        page_name,
                        elapsed_ms,
                    )
                return cache_file
        except Exception as exc:
            logger.exception("Error reading Codex page %s from %s: %s", page_name, cbz_path, exc)
            return None

    @classmethod
    def get_page_data(cls, cbz_path: Path, chapter_id: int, page_name: str) -> bytes | None:
        cache_file = cls.ensure_page_cached(cbz_path, chapter_id, page_name)
        if cache_file is None:
            return None
        return cache_file.read_bytes()

    @classmethod
    def ensure_thumbnail_cached(cls, cbz_path: Path, chapter_id: int, page_name: str) -> Path | None:
        cls._setup_cache_dirs()

        thumb_cache_file = cls.THUMB_CACHE_DIR / str(chapter_id) / f"{page_name}.thumb.jpg"

        if thumb_cache_file.exists():
            os.utime(thumb_cache_file, None)
            return thumb_cache_file

        page_file = cls.ensure_page_cached(cbz_path, chapter_id, page_name)
        if page_file is None:
            return None

        try:
            with Image.open(page_file) as img:
                if img.mode in ("RGBA", "LA", "P"):
                    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    rgb_img.paste(
                        img,
                        mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None,
                    )
                    img = rgb_img

                original_width, original_height = img.size
                if original_width > cls.THUMB_WIDTH:
                    ratio = cls.THUMB_WIDTH / original_width
                    new_height = int(original_height * ratio)
                    img = img.resize((cls.THUMB_WIDTH, new_height), Image.Resampling.LANCZOS)

                thumb_cache_file.parent.mkdir(parents=True, exist_ok=True)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=cls.THUMB_QUALITY, optimize=True)
                thumb_cache_file.write_bytes(buffer.getvalue())
                return thumb_cache_file
        except Exception as exc:
            logger.exception("Error generating Codex thumbnail %s from %s: %s", page_name, cbz_path, exc)
            return page_file

    @classmethod
    def get_thumbnail_data(cls, cbz_path: Path, chapter_id: int, page_name: str) -> bytes | None:
        thumb_cache_file = cls.ensure_thumbnail_cached(cbz_path, chapter_id, page_name)
        if thumb_cache_file is None:
            return None
        return thumb_cache_file.read_bytes()

    @classmethod
    def warm_chapter_assets(
        cls,
        cbz_path: Path,
        chapter_id: int,
        image_names: list[str],
        page_limit: int = 4,
        thumb_limit: int = 8,
    ) -> None:
        for image_name in image_names[:page_limit]:
            try:
                cls.ensure_page_cached(cbz_path, chapter_id, image_name)
            except Exception:
                continue

        for image_name in image_names[:thumb_limit]:
            try:
                cls.ensure_thumbnail_cached(cbz_path, chapter_id, image_name)
            except Exception:
                continue

    @classmethod
    def warm_adjacent_pages(
        cls,
        cbz_path: Path,
        chapter_id: int,
        image_names: list[str],
        page_name: str,
        forward_page_count: int = 2,
        thumb_count: int = 4,
    ) -> None:
        try:
            current_index = image_names.index(page_name)
        except ValueError:
            return

        neighbor_names = image_names[current_index + 1 : current_index + 1 + forward_page_count]
        thumb_names = image_names[current_index + 1 : current_index + 1 + thumb_count]

        for image_name in neighbor_names:
            try:
                cls.ensure_page_cached(cbz_path, chapter_id, image_name)
            except Exception:
                continue

        for image_name in thumb_names:
            try:
                cls.ensure_thumbnail_cached(cbz_path, chapter_id, image_name)
            except Exception:
                continue
