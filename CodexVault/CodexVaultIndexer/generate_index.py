import argparse
import json
import re
import subprocess
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (CodexVaultIndexer)"


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


def resolve_folder_path(path_text: str) -> Path:
    folder = Path(path_text).expanduser()
    if folder.exists() and folder.is_dir():
        return folder

    drive_match = re.match(r"^([A-Za-z]):[\\/](.*)$", path_text)
    if not drive_match:
        return folder

    drive_name = drive_match.group(1)
    relative_part = drive_match.group(2).replace("\\", "/")

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-PSDrive -Name '{drive_name}' -PSProvider FileSystem).Root",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return folder

    drive_root = result.stdout.replace("\x00", "").strip()
    if not drive_root:
        return folder

    candidate = Path(drive_root) / Path(relative_part)
    return candidate


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
        r'<meta name="description" content="(.*?)"\s*/?>', html, re.S
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
        r'<meta property="og:image" content="(.*?)"\s*/?>', html, re.S
    )

    title = strip_tags(title_match.group(1) if title_match else "")
    description = strip_tags(
        meta_description_match.group(1) if meta_description_match else ""
    )
    description = re.sub(r"^Summary:\s*", "", description, flags=re.I)
    alt_titles = []
    if alt_match:
        alt_titles = [part.strip() for part in strip_tags(alt_match.group(1)).split(";") if part.strip()]

    authors = []
    if authors_match:
        authors = [strip_tags(part) for part in re.findall(r">([^<]+)</a>", authors_match.group(1))]

    genres = []
    if genres_match:
        genres = [strip_tags(part) for part in re.findall(r">([^<]+)</a>", genres_match.group(1))]

    status = strip_tags(status_match.group(1) if status_match else "Ongoing").upper()
    cover_url = unescape(cover_match.group(1)) if cover_match else ""

    chapters: list[dict[str, Any]] = []
    for match in re.finditer(r'<tr[^>]+data-jump="([^"]+)".*?</tr>', html, re.S):
        row = match.group(0)
        link_match = re.search(
            r'href="([^"]+)"[^>]*>\s*(Chapter[^<]*)</a>', row, re.S | re.I
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
    file_names: list[str], remote_chapters: list[dict[str, Any]], mode: str
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
        "Use --mapping ordered-list, integer-only, or filename-number."
    )


def map_chapters(
    file_names: list[str], remote_chapters: list[dict[str, Any]], mode: str
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
                number_text = str(int(chapter_number)) if chapter_number.is_integer() else str(chapter_number)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Codex Vault index.json from a MangaKatana series page."
    )
    parser.add_argument("folder", help="Local manga folder containing .cbz files")
    parser.add_argument("url", help="MangaKatana series URL")
    parser.add_argument(
        "--mapping",
        choices=["auto", "ordered-list", "integer-only", "filename-number"],
        default="auto",
        help="How to map local files to MangaKatana chapter rows",
    )
    parser.add_argument(
        "--chapter-glob",
        default="*.cbz",
        help="Glob pattern for chapter archives inside the folder",
    )
    parser.add_argument(
        "--cover-entry",
        default="cover.jpg",
        help="Filename to reference as the local cover image in index.json",
    )
    parser.add_argument(
        "--download-cover",
        action="store_true",
        help="Download the MangaKatana cover into the manga folder if available",
    )
    parser.add_argument(
        "--overwrite-cover",
        action="store_true",
        help="Overwrite the local cover file when downloading",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    folder = resolve_folder_path(args.folder)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")

    chapter_files = sorted(
        [path.name for path in folder.glob(args.chapter_glob)],
        key=natural_sort_key,
    )
    if not chapter_files:
        raise FileNotFoundError(
            f"No chapter files matched {args.chapter_glob!r} in {folder}"
        )

    series_metadata = parse_mangakatana_series(args.url)
    mapped_chapters = map_chapters(chapter_files, series_metadata["chapters"], args.mapping)
    payload = build_payload(args.url, series_metadata, mapped_chapters, args.cover_entry)

    output_path = folder / "index.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.download_cover and series_metadata["cover_url"]:
        cover_path = folder / args.cover_entry
        if args.overwrite_cover or not cover_path.exists():
            cover_path.write_bytes(fetch_bytes(series_metadata["cover_url"]))

    print(f"Wrote {output_path}")
    print(f"Mapped {len(mapped_chapters)} chapter files using mode: {choose_mapping_mode(chapter_files, series_metadata['chapters'], args.mapping)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Network error: {exc}")
        raise SystemExit(1)
    except Exception as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
