from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path

DEFAULT_SOURCE_ROOT = Path(r"F:\Repository")


def env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no"}


@dataclass(frozen=True)
class IshtarSettings:
    root_dir: Path
    legacy_root: Path
    legacy_tomb_dir: Path
    frontend_project_dir: Path
    frontend_dist_dir: Path
    db_path: Path
    source_root: Path
    recursive_scan: bool
    debug: bool


@lru_cache(maxsize=1)
def get_settings() -> IshtarSettings:
    root_dir = Path(__file__).resolve().parent.parent
    legacy_root = root_dir / "IshtarCollective"
    legacy_tomb_dir = legacy_root / "tomb"
    frontend_project_dir = legacy_root / "gate"
    frontend_dist_dir = Path(
        os.getenv("ISHTAR_FRONTEND_DIST", str(root_dir / "ishtar_frontend_dist"))
    ).expanduser()
    db_path = Path(
        os.getenv("TOMB_DB_PATH", str(legacy_tomb_dir / "tomb.db"))
    ).expanduser()
    source_root = Path(
        os.getenv("TOMB_SOURCE_ROOT", str(DEFAULT_SOURCE_ROOT))
    ).expanduser()

    return IshtarSettings(
        root_dir=root_dir,
        legacy_root=legacy_root,
        legacy_tomb_dir=legacy_tomb_dir,
        frontend_project_dir=frontend_project_dir,
        frontend_dist_dir=frontend_dist_dir,
        db_path=db_path,
        source_root=source_root,
        recursive_scan=env_flag("TOMB_RECURSIVE_SCAN", True),
        debug=env_flag("TOMB_DEBUG", False),
    )
