from __future__ import annotations

import argparse
import json

from codex.services.simple_indexer import build_simple_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pack raw Codex chapter image folders into CBZ files and generate index.json from MangaKatana."
    )
    parser.add_argument("folder", help="Series folder containing raw image folders or CBZ files")
    parser.add_argument("url", help="MangaKatana series URL")
    parser.add_argument(
        "--mapping",
        choices=["auto", "ordered-list", "integer-only", "filename-number"],
        default="auto",
        help="How to map local CBZ files to MangaKatana chapters",
    )
    parser.add_argument(
        "--chapter-glob",
        default="*.cbz",
        help="Glob pattern for chapter archives inside the series folder",
    )
    parser.add_argument(
        "--cover-entry",
        default="cover.jpg",
        help="Filename to reference as the local cover image in index.json",
    )
    parser.add_argument(
        "--no-cover",
        action="store_true",
        help="Do not download the MangaKatana cover",
    )
    parser.add_argument(
        "--overwrite-cover",
        action="store_true",
        help="Overwrite the local cover file when downloading",
    )
    parser.add_argument(
        "--overwrite-cbz",
        action="store_true",
        help="Overwrite existing CBZ files generated from raw image folders",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_simple_index(
        folder=args.folder,
        url=args.url,
        mapping=args.mapping,
        chapter_glob=args.chapter_glob,
        cover_entry=args.cover_entry,
        download_cover=not args.no_cover,
        overwrite_cover=args.overwrite_cover,
        overwrite_cbz=args.overwrite_cbz,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
