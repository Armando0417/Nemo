import json
import os
from pathlib import Path
from sqlmodel import Session, select
from data_schemas import Manga_Series, Manga_Chapter
from librarian import Librarian
from reader import VaultReader

class Indexer:
    """
    The Assistant Librarian.
    Specializes in reading Kotatsu index.json files to populate the Vault.
    """
    def __init__(self, librarian: Librarian, library_path: str):
        self.librarian = librarian
        self.library_path = Path(library_path)

    def _new_stats(self):
        stats = {
            "new_series": 0,
            "new_chapters": 0,
            "updated_series": 0,
            "updated_chapters": 0,
            "thumbnails_generated": 0
        }
        return stats

    def _log_stats(self, stats):
        print("--- Indexer: Vault is up to date! ---")
        print(
            "Stats: "
            f"{stats['new_series']} new series, "
            f"{stats['updated_series']} updated series, "
            f"{stats['new_chapters']} new chapters, "
            f"{stats['updated_chapters']} updated chapters, "
            f"{stats['thumbnails_generated']} thumbnails generated"
        )

    def run_scan(self, generate_thumbnails: bool = True):
        print(f"--- Indexer: Synchronizing with Kotatsu Library at {self.library_path} ---")
        
        if not self.library_path.exists():
            print("Indexer Error: Library path not found.")
            return {"status": "error", "message": "Library path not found"}

        target_folders = [
            folder
            for folder in self.library_path.iterdir()
            if folder.is_dir()
        ]
        return self._run_scan_for_folders(target_folders, generate_thumbnails)

    def run_scan_for_paths(self, folder_paths: list[str], generate_thumbnails: bool = True):
        target_folders = []
        for raw_path in folder_paths:
            folder = Path(raw_path)
            if folder.exists() and folder.is_dir():
                target_folders.append(folder)
            else:
                print(f"⚠️ Skipping missing folder: {raw_path}")

        print(f"--- Indexer: Selective synchronization for {len(target_folders)} folders ---")
        return self._run_scan_for_folders(target_folders, generate_thumbnails)

    def _run_scan_for_folders(self, folders: list[Path], generate_thumbnails: bool):
        stats = self._new_stats()

        # 1. Walk through each folder in the library
        for folder in folders:
            index_file = folder / "index.json"
            if not index_file.exists():
                print(f"⚠️ Skipping {folder.name}: No index.json found.")
                continue

            # 2. Parse the Kotatsu Metadata
            with open(index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            series_title = data.get("title", folder.name)
            series_path = str(folder.absolute())
            cover_entry = data.get("cover_entry", "cover.jpg")

            with Session(self.librarian.engine) as session:
                # 3. Check if Series exists (by path)
                series = session.exec(
                    select(Manga_Series).where(Manga_Series.path == series_path)
                ).first()

                if not series:
                    print(f"➕ Archiving New Series: {series_title}")
                    series = Manga_Series(
                        title=series_title,
                        path=series_path,
                        author=data.get("author", "Unknown"),
                        description=data.get("description", ""),
                        status=data.get("state", "Ongoing"),
                        cover_image=cover_entry
                    )
                    session.add(series)
                    session.commit()
                    session.refresh(series)
                    stats["new_series"] += 1
                else:
                    series_updated = False
                    next_author = data.get("author", "Unknown")
                    next_description = data.get("description", "")
                    next_status = data.get("state", "Ongoing")

                    if series.title != series_title:
                        series.title = series_title
                        series_updated = True
                    if series.author != next_author:
                        series.author = next_author
                        series_updated = True
                    if series.description != next_description:
                        series.description = next_description
                        series_updated = True
                    if series.status != next_status:
                        series.status = next_status
                        series_updated = True
                    if series.cover_image != cover_entry:
                        series.cover_image = cover_entry
                        series_updated = True

                    if series_updated:
                        print(f"🔄 Updating Series Metadata: {series_title}")
                        session.add(series)
                        session.commit()
                        session.refresh(series)
                        stats["updated_series"] += 1

                # 4. Process Chapters from the JSON
                kotatsu_chapters = data.get("chapters", {})
                for ch_id, ch_info in kotatsu_chapters.items():
                    filename = ch_info.get("file")
                    if not filename:
                        continue

                    # Check if chapter already indexed for this series
                    chapter = session.exec(
                        select(Manga_Chapter).where(
                            Manga_Chapter.folder_path == filename,
                            Manga_Chapter.series_id == series.id
                        )
                    ).first()

                    if not chapter:
                        print(f"   📄 Adding Chapter {ch_info.get('number')}: {ch_info.get('name')}")
                        new_chapter = Manga_Chapter(
                            series_id=series.id,
                            chapter_number=float(ch_info.get("number", 0)),
                            title=ch_info.get("name"),
                            page_count=0, # Will be calculated during thumbnail generation
                            folder_path=filename 
                        )
                        session.add(new_chapter)
                        session.commit()
                        session.refresh(new_chapter)
                        stats["new_chapters"] += 1
                        
                        # Generate thumbnails for new chapters
                        if generate_thumbnails:
                            thumb_count = self._pregenerate_thumbnails(series, new_chapter)
                            stats["thumbnails_generated"] += thumb_count
                            
                            # Update page count
                            new_chapter.page_count = thumb_count
                            session.add(new_chapter)
                            session.commit()
                    else:
                        chapter_updated = False
                        next_number = float(ch_info.get("number", 0))
                        next_title = ch_info.get("name")

                        if chapter.chapter_number != next_number:
                            chapter.chapter_number = next_number
                            chapter_updated = True
                        if chapter.title != next_title:
                            chapter.title = next_title
                            chapter_updated = True

                        if chapter_updated:
                            print(f"   🔄 Updating Chapter {next_number}: {next_title}")
                            session.add(chapter)
                            session.commit()
                            stats["updated_chapters"] += 1
                
                session.commit()

        self._log_stats(stats)
        return {"status": "success", "stats": stats}

    def _pregenerate_thumbnails(self, series: Manga_Series, chapter: Manga_Chapter) -> int:
        """
        Pre-generate thumbnails for a chapter to avoid on-demand generation lag.
        Returns the number of thumbnails generated.
        """
        print(f"      🖼️  Generating thumbnails for {chapter.title}...")
        
        cbz_path = Path(series.path) / chapter.folder_path
        if not cbz_path.exists():
            print(f"      ⚠️  CBZ not found: {cbz_path}")
            return 0
        
        # Get list of all images in the chapter
        image_list = VaultReader.get_image_list(cbz_path)
        
        generated = 0
        for img_name in image_list:
            try:
                # This will generate and cache the thumbnail
                VaultReader.get_thumbnail_data(cbz_path, chapter.id, img_name)
                generated += 1
            except Exception as e:
                print(f"      ❌ Failed to generate thumbnail for {img_name}: {e}")
        
        print(f"      ✅ Generated {generated}/{len(image_list)} thumbnails")
        return generated
