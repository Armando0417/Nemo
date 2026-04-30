from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path

DEFAULT_LIBRARY_PATH = Path(r"D:\Wandering_Sea\T7_Branch\Sarcophagus\CV_Tomb")


def env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CodexSettings:
    root_dir: Path
    legacy_root: Path
    legacy_indexer_dir: Path
    frontend_project_dir: Path
    frontend_dist_dir: Path
    data_dir: Path
    db_path: Path
    cache_dir: Path
    library_root: Path
    debug: bool
    background_warming: bool
    selective_index_html: Path


@lru_cache(maxsize=1)
def get_settings() -> CodexSettings:
    root_dir = Path(__file__).resolve().parent.parent
    legacy_root = root_dir / "CodexVault"
    legacy_indexer_dir = legacy_root / "CodexVaultIndexer"
    frontend_project_dir = legacy_root / "CodexVault"
    frontend_dist_dir = Path(
        os.getenv("CODEX_VAULT_FRONTEND_DIST", str(root_dir / "codex_frontend_dist"))
    ).expanduser()
    data_dir = Path(
        os.getenv("CODEX_VAULT_DATA_DIR", str(legacy_indexer_dir))
    ).expanduser()
    db_path = Path(
        os.getenv("CODEX_VAULT_DB_PATH", str(data_dir / "codex_vault.db"))
    ).expanduser()
    cache_dir = Path(
        os.getenv("CODEX_VAULT_CACHE_DIR", str(data_dir / "vault_cache"))
    ).expanduser()
    library_root = Path(
        os.getenv("CODEX_VAULT_LIBRARY_PATH", str(DEFAULT_LIBRARY_PATH))
    ).expanduser()
    selective_index_html = Path(
        os.getenv(
            "CODEX_VAULT_SELECTIVE_INDEX_HTML",
            str(root_dir / "codex" / "templates" / "selective_index.html"),
        )
    ).expanduser()

    return CodexSettings(
        root_dir=root_dir,
        legacy_root=legacy_root,
        legacy_indexer_dir=legacy_indexer_dir,
        frontend_project_dir=frontend_project_dir,
        frontend_dist_dir=frontend_dist_dir,
        data_dir=data_dir,
        db_path=db_path,
        cache_dir=cache_dir,
        library_root=library_root,
        debug=env_flag("CODEX_VAULT_DEBUG", False),
        background_warming=env_flag("CODEX_VAULT_BACKGROUND_WARMING", False),
        selective_index_html=selective_index_html,
    )
