from __future__ import annotations

import json
import re
import zipfile
from html import unescape
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (Nemo Codex Simple Indexer)"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
MappingMode = Literal["auto", "ordered-list", "integer-only", "filename-number"]


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read()


def strip_tags(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text or "", flags=re.I)
    text = re.sub(r"<.*?>", "", text, flags=re.S)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def natural_sort_key(name: str) -> list[tuple[int, Any]]:
    parts = re.split(r"(\d+(?:\.\d+)?)", name)
    key: list[tuple[int, Any]] = []
    for part in parts:
        if not part:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", part):
            key.append((0, float(part)))
        else:
            key.append((1, part.lower()))
    return key


def slugify_tag(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_series_id(url: str) -> int:
    match = re.search(r"\.(\d+)(?:/)?$", url.rstrip("/"))
    if not match:
        raise ValueError(f"Could not parse MangaKatana series id from URL: {url}")
    return int(match.group(1))


def extract_number_from_filename(filename: str) -> float | None:
    stem = Path(filename).stem
    match = re.search(r"(\d+(?:\.\d+)?)", stem)
    if not match:
        return None
    return float(match.group(1))


def parse_mangakatana_series(url: str) -> dict[str, Any]:
    html = fetch_text(url)

    title_match = re.search(r'<h1 class="heading">(.*?)</h1>', html, re.S)
    meta_description_match = re.search(
        r'<meta name="description" content="(.*?)"\s*/?>',
        html,
        re.S,
    )
    alt_match = re.search(r'<div class="alt_name">(.*?)</div>', html, re.S)
    authors_match = re.search(
        r'Author\(s\) / Artist\(s\):</div>\s*<div class="d-cell-small value authors">(.*?)</div>',
        html,
        re.S,
    )
    genres_match = re.search(r'<div class="genres">(.*?)</div>', html, re.S)
    status_match = re.search(
        r'<div class="d-cell-small label">Status:</div>\s*<div class="d-cell-small value status [^"]+">(.*?)</div>',
        html,
        re.S,
    )
    cover_match = re.search(
        r'<meta property="og:image" content="(.*?)"\s*/?>',
        html,
        re.S,
    )

    title = strip_tags(title_match.group(1) if title_match else "")
    description = strip_tags(
        meta_description_match.group(1) if meta_description_match else ""
    )
    description = re.sub(r"^Summary:\s*", "", description, flags=re.I)
    alt_titles = []
    if alt_match:
        alt_titles = [
            part.strip()
            for part in strip_tags(alt_match.group(1)).split(";")
            if part.strip()
        ]

    authors = []
    if authors_match:
        authors = [
            strip_tags(part)
            for part in re.findall(r">([^<]+)</a>", authors_match.group(1))
        ]

    genres = []
    if genres_match:
        genres = [
            strip_tags(part)
            for part in re.findall(r">([^<]+)</a>", genres_match.group(1))
        ]

    status = strip_tags(status_match.group(1) if status_match else "Ongoing").upper()
    cover_url = unescape(cover_match.group(1)) if cover_match else ""

    chapters: list[dict[str, Any]] = []
    for match in re.finditer(r'<tr[^>]+data-jump="([^"]+)".*?</tr>', html, re.S):
        row = match.group(0)
        link_match = re.search(
            r'href="([^"]+)"[^>]*>\s*(Chapter[^<]*)</a>',
            row,
            re.S | re.I,
        )
        if not link_match:
            continue

        chapter_url = link_match.group(1)
        chapter_name = strip_tags(link_match.group(2))
        number_match = re.search(r"/c(\d+(?:\.\d+)?)$", chapter_url)
        if not number_match:
            number_match = re.search(r"Chapter\s+(\d+(?:\.\d+)?)", chapter_name, re.I)
        if not number_match:
            continue

        chapters.append(
            {
                "number": float(number_match.group(1)),
                "number_text": number_match.group(1),
                "name": chapter_name,
                "url": chapter_url,
            }
        )

    chapters.sort(key=lambda item: item["number"])
    return {
        "title": title,
        "description": description,
        "alt_titles": alt_titles,
        "authors": authors,
        "genres": genres,
        "status": status,
        "cover_url": cover_url,
        "chapters": chapters,
    }


def choose_mapping_mode(
    file_names: list[str],
    remote_chapters: list[dict[str, Any]],
    mode: MappingMode,
) -> str:
    if mode != "auto":
        return mode
    if len(file_names) == len(remote_chapters):
        return "ordered-list"

    integer_only = [chapter for chapter in remote_chapters if chapter["number"].is_integer()]
    if len(file_names) == len(integer_only):
        return "integer-only"
    if all(extract_number_from_filename(name) is not None for name in file_names):
        return "filename-number"

    raise ValueError(
        "Could not determine chapter mapping automatically. "
        "Use mapping ordered-list, integer-only, or filename-number."
    )


def map_chapters(
    file_names: list[str],
    remote_chapters: list[dict[str, Any]],
    mode: MappingMode,
) -> list[dict[str, Any]]:
    selected_mode = choose_mapping_mode(file_names, remote_chapters, mode)

    if selected_mode == "ordered-list":
        if len(file_names) != len(remote_chapters):
            raise ValueError(
                f"ordered-list mapping requires matching counts, got {len(file_names)} files and "
                f"{len(remote_chapters)} remote chapters"
            )
        return [
            {
                "file": file_name,
                "number": chapter["number"],
                "name": chapter["name"],
                "url": chapter["url"],
            }
            for file_name, chapter in zip(file_names, remote_chapters)
        ]

    if selected_mode == "integer-only":
        integer_chapters = [
            chapter for chapter in remote_chapters if chapter["number"].is_integer()
        ]
        if len(file_names) != len(integer_chapters):
            raise ValueError(
                f"integer-only mapping requires matching counts, got {len(file_names)} files and "
                f"{len(integer_chapters)} integer-only remote chapters"
            )
        return [
            {
                "file": file_name,
                "number": int(chapter["number"]),
                "name": chapter["name"],
                "url": chapter["url"],
            }
            for file_name, chapter in zip(file_names, integer_chapters)
        ]

    if selected_mode == "filename-number":
        remote_by_number = {chapter["number"]: chapter for chapter in remote_chapters}
        mapped: list[dict[str, Any]] = []
        for file_name in file_names:
            chapter_number = extract_number_from_filename(file_name)
            if chapter_number is None:
                raise ValueError(f"Could not extract chapter number from filename: {file_name}")

            remote_match = remote_by_number.get(chapter_number)
            if remote_match:
                chapter_name = remote_match["name"]
                chapter_url = remote_match["url"]
            else:
                number_text = (
                    str(int(chapter_number))
                    if chapter_number.is_integer()
                    else str(chapter_number)
                )
                chapter_name = f"Chapter {number_text}"
                chapter_url = None

            mapped.append(
                {
                    "file": file_name,
                    "number": int(chapter_number) if chapter_number.is_integer() else chapter_number,
                    "name": chapter_name,
                    "url": chapter_url,
                }
            )
        return mapped

    raise ValueError(f"Unsupported mapping mode: {selected_mode}")


def build_payload(
    series_url: str,
    series_metadata: dict[str, Any],
    mapped_chapters: list[dict[str, Any]],
    cover_entry: str,
) -> dict[str, Any]:
    parsed_url = urlparse(series_url)
    path_only = parsed_url.path.rstrip("/")

    payload = {
        "id": parse_series_id(series_url),
        "title": series_metadata["title"],
        "title_alt": " ; ".join(series_metadata["alt_titles"]),
        "alt_titles": series_metadata["alt_titles"],
        "url": path_only,
        "public_url": series_url,
        "author": ", ".join(series_metadata["authors"]) if series_metadata["authors"] else "Unknown",
        "authors": series_metadata["authors"],
        "description": series_metadata["description"],
        "state": series_metadata["status"],
        "source": "MANGAKATANA",
        "tags": [
            {"key": slugify_tag(tag), "title": tag}
            for tag in series_metadata["genres"]
        ],
        "chapters": {},
        "cover_entry": cover_entry,
    }

    for chapter in mapped_chapters:
        chapter_key = Path(chapter["file"]).stem.replace(".", "_")
        chapter_payload = {
            "number": chapter["number"],
            "volume": 0,
            "name": chapter["name"],
            "file": chapter["file"],
        }
        if chapter.get("url"):
            chapter_payload["url"] = chapter["url"]
        payload["chapters"][chapter_key] = chapter_payload

    return payload


def _image_files(folder: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ],
        key=lambda path: natural_sort_key(path.name),
    )


def _chapter_image_folders(series_folder: Path) -> list[Path]:
    return sorted(
        [folder for folder in series_folder.iterdir() if folder.is_dir() and _image_files(folder)],
        key=lambda folder: natural_sort_key(folder.name),
    )


def pack_raw_images_to_cbz(
    series_folder: Path,
    overwrite: bool = False,
    single_chapter_name: str = "chapter-001.cbz",
) -> list[dict[str, Any]]:
    series_folder = series_folder.resolve()
    if not series_folder.exists() or not series_folder.is_dir():
        raise FileNotFoundError(f"Series folder not found: {series_folder}")

    chapter_folders = _chapter_image_folders(series_folder)
    packed: list[dict[str, Any]] = []

    if chapter_folders:
        for chapter_folder in chapter_folders:
            image_files = _image_files(chapter_folder)
            cbz_path = series_folder / f"{chapter_folder.name}.cbz"
            created = _write_cbz(cbz_path, image_files, overwrite=overwrite)
            packed.append(
                {
                    "source_folder": str(chapter_folder),
                    "file": cbz_path.name,
                    "image_count": len(image_files),
                    "created": created,
                }
            )
        return packed

    root_images = _image_files(series_folder)
    if root_images:
        cbz_path = series_folder / single_chapter_name
        created = _write_cbz(cbz_path, root_images, overwrite=overwrite)
        return [
            {
                "source_folder": str(series_folder),
                "file": cbz_path.name,
                "image_count": len(root_images),
                "created": created,
            }
        ]

    return []


def _write_cbz(cbz_path: Path, image_files: list[Path], overwrite: bool) -> bool:
    if cbz_path.exists() and not overwrite:
        return False
    cbz_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(cbz_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for image_file in image_files:
            archive.write(image_file, arcname=image_file.name)
    return True


def generate_codex_index(
    series_folder: Path,
    series_url: str,
    mapping: MappingMode = "auto",
    chapter_glob: str = "*.cbz",
    cover_entry: str = "cover.jpg",
    download_cover: bool = True,
    overwrite_cover: bool = False,
) -> dict[str, Any]:
    series_folder = series_folder.resolve()
    chapter_files = sorted(
        [path.name for path in series_folder.glob(chapter_glob)],
        key=natural_sort_key,
    )
    if not chapter_files:
        raise FileNotFoundError(f"No chapter files matched {chapter_glob!r} in {series_folder}")

    series_metadata = parse_mangakatana_series(series_url)
    mapped_chapters = map_chapters(chapter_files, series_metadata["chapters"], mapping)
    selected_mapping = choose_mapping_mode(chapter_files, series_metadata["chapters"], mapping)
    payload = build_payload(series_url, series_metadata, mapped_chapters, cover_entry)

    output_path = series_folder / "index.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    cover_written = False
    if download_cover and series_metadata["cover_url"]:
        cover_path = series_folder / cover_entry
        if overwrite_cover or not cover_path.exists():
            cover_path.write_bytes(fetch_bytes(series_metadata["cover_url"]))
            cover_written = True

    return {
        "index_path": str(output_path),
        "title": payload["title"],
        "chapter_count": len(mapped_chapters),
        "chapter_files": chapter_files,
        "mapping": selected_mapping,
        "cover_entry": cover_entry,
        "cover_written": cover_written,
    }


def build_simple_index(
    folder: str | Path,
    url: str,
    mapping: MappingMode = "auto",
    chapter_glob: str = "*.cbz",
    cover_entry: str = "cover.jpg",
    download_cover: bool = True,
    overwrite_cover: bool = False,
    overwrite_cbz: bool = False,
) -> dict[str, Any]:
    series_folder = Path(folder).expanduser().resolve()
    packed = pack_raw_images_to_cbz(series_folder, overwrite=overwrite_cbz)
    index_result = generate_codex_index(
        series_folder=series_folder,
        series_url=url,
        mapping=mapping,
        chapter_glob=chapter_glob,
        cover_entry=cover_entry,
        download_cover=download_cover,
        overwrite_cover=overwrite_cover,
    )
    return {
        "status": "success",
        "folder": str(series_folder),
        "packed": packed,
        **index_result,
    }
