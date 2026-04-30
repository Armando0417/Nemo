# import json
# import os
# from pathlib import Path
# from sqlmodel import Session, select
# from data_schemas import Manga_Series, Manga_Chapter
# from librarian import Librarian
# from reader import VaultReader

# class Indexer:
#     """
#     The Assistant Librarian.
#     Specializes in reading Kotatsu index.json files to populate the Vault.
#     """
#     def __init__(self, librarian: Librarian, library_path: str):
#         self.librarian = librarian
#         self.library_path = Path(library_path)

#     def run_scan(self, generate_thumbnails: bool = True):
#         print(f"--- Indexer: Synchronizing with Kotatsu Library at {self.library_path} ---")
        
#         if not self.library_path.exists():
#             print("Indexer Error: Library path not found.")
#             return {"status": "error", "message": "Library path not found"}

#         stats = {
#             "new_series": 0,
#             "new_chapters": 0,
#             "thumbnails_generated": 0
#         }

#         # 1. Walk through each folder in the library
#         for folder in self.library_path.iterdir():
#             if not folder.is_dir():
#                 continue

#             index_file = folder / "index.json"
#             if not index_file.exists():
#                 print(f"⚠️ Skipping {folder.name}: No index.json found.")
#                 continue

#             # 2. Parse the Kotatsu Metadata
#             with open(index_file, 'r', encoding='utf-8') as f:
#                 data = json.load(f)

#             series_title = data.get("title", folder.name)
#             series_path = str(folder.absolute())

#             with Session(self.librarian.engine) as session:
#                 # 3. Check if Series exists (by path)
#                 series = session.exec(
#                     select(Manga_Series).where(Manga_Series.path == series_path)
#                 ).first()

#                 if not series:
#                     print(f"➕ Archiving New Series: {series_title}")
#                     series = Manga_Series(
#                         title=series_title,
#                         path=series_path,
#                         author=data.get("author", "Unknown"),
#                         description=data.get("description", ""),
#                         status=data.get("state", "Ongoing"),
#                         cover_image="cover.jpg" # Kotatsu standard
#                     )
#                     session.add(series)
#                     session.commit()
#                     session.refresh(series)
#                     stats["new_series"] += 1

#                 # 4. Process Chapters from the JSON
#                 kotatsu_chapters = data.get("chapters", {})
#                 for ch_id, ch_info in kotatsu_chapters.items():
#                     filename = ch_info.get("file")
#                     if not filename:
#                         continue

#                     # Check if chapter already indexed for this series
#                     chapter = session.exec(
#                         select(Manga_Chapter).where(
#                             Manga_Chapter.folder_path == filename,
#                             Manga_Chapter.series_id == series.id
#                         )
#                     ).first()

#                     if not chapter:
#                         print(f"   📄 Adding Chapter {ch_info.get('number')}: {ch_info.get('name')}")
#                         new_chapter = Manga_Chapter(
#                             series_id=series.id,
#                             chapter_number=float(ch_info.get("number", 0)),
#                             title=ch_info.get("name"),
#                             page_count=0, # Will be calculated during thumbnail generation
#                             folder_path=filename 
#                         )
#                         session.add(new_chapter)
#                         session.commit()
#                         session.refresh(new_chapter)
#                         stats["new_chapters"] += 1
                        
#                         # Generate thumbnails for new chapters
#                         if generate_thumbnails:
#                             thumb_count = self._pregenerate_thumbnails(series, new_chapter)
#                             stats["thumbnails_generated"] += thumb_count
                            
#                             # Update page count
#                             new_chapter.page_count = thumb_count
#                             session.add(new_chapter)
#                             session.commit()
                
#                 session.commit()

#         print("--- Indexer: Vault is up to date! ---")
#         print(f"Stats: {stats['new_series']} new series, {stats['new_chapters']} new chapters, {stats['thumbnails_generated']} thumbnails generated")
#         return {"status": "success", "stats": stats}

#     def _pregenerate_thumbnails(self, series: Manga_Series, chapter: Manga_Chapter) -> int:
#         """
#         Pre-generate thumbnails for a chapter to avoid on-demand generation lag.
#         Returns the number of thumbnails generated.
#         """
#         print(f"      🖼️  Generating thumbnails for {chapter.title}...")
        
#         cbz_path = Path(series.path) / chapter.folder_path
#         if not cbz_path.exists():
#             print(f"      ⚠️  CBZ not found: {cbz_path}")
#             return 0
        
#         # Get list of all images in the chapter
#         image_list = VaultReader.get_image_list(cbz_path)
        
#         generated = 0
#         for img_name in image_list:
#             try:
#                 # This will generate and cache the thumbnail
#                 VaultReader.get_thumbnail_data(cbz_path, chapter.id, img_name)
#                 generated += 1
#             except Exception as e:
#                 print(f"      ❌ Failed to generate thumbnail for {img_name}: {e}")
        
#         print(f"      ✅ Generated {generated}/{len(image_list)} thumbnails")
#         return generated