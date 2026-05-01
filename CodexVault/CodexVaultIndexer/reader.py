import os
import zipfile
from pathlib import Path
from typing import List, Optional
from PIL import Image
import io

class VaultReader:
    """
    The VaultReader is responsible for opening the physical 
    archived files (.cbz) and extracting the pages.
    """
    
    CACHE_DIR = Path("./vault_cache")
    THUMB_CACHE_DIR = Path("./vault_cache/thumbnails")
    MAX_CACHE_FILES = 100
    MAX_THUMB_CACHE_FILES = 2000
    THUMB_WIDTH = 400  # Max width for thumbnails
    THUMB_QUALITY = 85  # JPEG quality (1-100)
    
    @classmethod
    def _setup_cache_dirs(cls):
        """Ensure cache directories exist."""
        cls.CACHE_DIR.mkdir(exist_ok=True)
        cls.THUMB_CACHE_DIR.mkdir(exist_ok=True)
    
    @staticmethod
    def get_image_list(cbz_path: Path) -> List[str]:
        """Returns a sorted list of all image filenames inside the CBZ."""
        if not cbz_path.exists():
            return []
            
        with zipfile.ZipFile(cbz_path, 'r') as archive:
            images = [
                f for f in archive.namelist() 
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
            ]
            images.sort() 
            return images
        
        
    @classmethod
    def _enforce_cache_limit(cls):
        """Ensures the cache doesn't exceed MAX_CACHE_FILES."""
        # Get all files in the cache directory recursively (excluding thumbnails)
        all_files = [
            f for f in cls.CACHE_DIR.rglob('*') 
            if f.is_file() and not str(f).startswith(str(cls.THUMB_CACHE_DIR))
        ]
        
        if len(all_files) >= cls.MAX_CACHE_FILES:
            # Sort files by last access time (atime) - oldest first
            all_files.sort(key=lambda x: x.stat().st_atime)
            
            # Delete the oldest ones until we are under the limit
            to_delete = len(all_files) - cls.MAX_CACHE_FILES + 1
            for i in range(to_delete):
                print(f"Librarian: Evicting old cache file: {all_files[i].name}")
                all_files[i].unlink()
                
                
    @classmethod
    def get_page_data(cls, cbz_path: Path, chapter_id: int, page_name: str):    
        """Get full-resolution page data."""
        cls._setup_cache_dirs()
        
        cache_folder = cls.CACHE_DIR / str(chapter_id)
        cache_file = cache_folder / page_name

        if cache_file.exists():
            # Update the access time so it doesn't get deleted soon
            os.utime(cache_file, None) 
            return cache_file.read_bytes()

        # Before adding a new one, check the limit
        cls._enforce_cache_limit()

        if not cbz_path.exists():
            return None

        try:
            with zipfile.ZipFile(cbz_path, 'r') as archive:
                image_bytes = archive.read(page_name)
                cache_folder.mkdir(parents=True, exist_ok=True)
                cache_file.write_bytes(image_bytes)
                return image_bytes
        except Exception as e:
            print(f"Error reading page: {e}")
            return None
    
    
    @classmethod
    def get_thumbnail_data(cls, cbz_path: Path, chapter_id: int, page_name: str):
        """
        Get thumbnail version of a page.
        Creates and caches a smaller version optimized for previews.
        """
        cls._setup_cache_dirs()
        
        # Check if thumbnail already exists in cache
        thumb_cache_folder = cls.THUMB_CACHE_DIR / str(chapter_id)
        thumb_cache_file = thumb_cache_folder / f"{page_name}.thumb.jpg"
        
        if thumb_cache_file.exists():
            os.utime(thumb_cache_file, None)  # Update access time
            return thumb_cache_file.read_bytes()
        
        # Get the full-resolution image first
        full_image_bytes = cls.get_page_data(cbz_path, chapter_id, page_name)
        if not full_image_bytes:
            return None
        
        try:
            # Open image with PIL
            img = Image.open(io.BytesIO(full_image_bytes))
            
            # Convert to RGB if necessary (for PNG with transparency, etc.)
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = rgb_img
            
            # Calculate new size maintaining aspect ratio
            original_width, original_height = img.size
            if original_width > cls.THUMB_WIDTH:
                ratio = cls.THUMB_WIDTH / original_width
                new_height = int(original_height * ratio)
                img = img.resize((cls.THUMB_WIDTH, new_height), Image.Resampling.LANCZOS)
            
            # Save as optimized JPEG
            thumb_cache_folder.mkdir(parents=True, exist_ok=True)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=cls.THUMB_QUALITY, optimize=True)
            thumb_bytes = buffer.getvalue()
            
            # Cache the thumbnail
            thumb_cache_file.write_bytes(thumb_bytes)
            
            print(f"Generated thumbnail: {page_name} ({len(full_image_bytes)} -> {len(thumb_bytes)} bytes)")
            
            return thumb_bytes
            
        except Exception as e:
            print(f"Error generating thumbnail: {e}")
            # Fallback to full image if thumbnail generation fails
            return full_image_bytes