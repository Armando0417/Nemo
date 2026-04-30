from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).expanduser()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class GateConfig:
    slug: str
    name: str
    subtitle: str
    jellyfin_exe: Path
    data_dir: Path
    cache_dir: Path
    log_dir: Path
    port: int

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


GATE_CONFIGS = (
    GateConfig(
        slug="akashic",
        name="Akashic Records",
        subtitle="The Eternal Media Archive",
        jellyfin_exe=_env_path(
            "AKASHIC_JELLYFIN_EXE",
            r"D:\Wandering_Sea\Den_Branch\Sarcophagus\AkashicRecords\engine\jellyfin.exe",
        ),
        data_dir=_env_path(
            "AKASHIC_JELLYFIN_DATA",
            r"D:\Wandering_Sea\Den_Branch\Sarcophagus\AkashicRecords\configurations\data",
        ),
        cache_dir=_env_path(
            "AKASHIC_JELLYFIN_CACHE",
            r"D:\Wandering_Sea\Den_Branch\Sarcophagus\AkashicRecords\configurations\cache",
        ),
        log_dir=_env_path(
            "AKASHIC_JELLYFIN_LOGS",
            r"D:\Wandering_Sea\Den_Branch\Sarcophagus\AkashicRecords\configurations\logs",
        ),
        port=_env_int("AKASHIC_JELLYFIN_PORT", 4004),
    ),
    GateConfig(
        slug="htv",
        name="H-TV",
        subtitle="The Hidden Channel",
        jellyfin_exe=_env_path(
            "HTV_JELLYFIN_EXE",
            r"E:\Wandering_Sea\Sarcophagus\HTV_Tomb\engine\jellyfin.exe",
        ),
        data_dir=_env_path(
            "HTV_JELLYFIN_DATA",
            r"E:\Wandering_Sea\Gates\HTV\data",
        ),
        cache_dir=_env_path(
            "HTV_JELLYFIN_CACHE",
            r"E:\Wandering_Sea\Gates\HTV\cache",
        ),
        log_dir=_env_path(
            "HTV_JELLYFIN_LOGS",
            r"E:\Wandering_Sea\Gates\HTV\logs",
        ),
        port=_env_int("HTV_JELLYFIN_PORT", 3434),
    ),
    GateConfig(
        slug="voyager",
        name="Voyager Records",
        subtitle="The Eternal Media Archive",
        jellyfin_exe=_env_path(
            "VOYAGER_JELLYFIN_EXE",
            r"D:\Wandering_Sea\Den_Branch\Sarcophagus\VoyagerRecords\engine\jellyfin.exe",
        ),
        data_dir=_env_path(
            "VOYAGER_JELLYFIN_DATA",
            r"D:\Wandering_Sea\Den_Branch\Sarcophagus\VoyagerRecords\configurations\data",
        ),
        cache_dir=_env_path(
            "VOYAGER_JELLYFIN_CACHE",
            r"D:\Wandering_Sea\Den_Branch\Sarcophagus\VoyagerRecords\configurations\cache",
        ),
        log_dir=_env_path(
            "VOYAGER_JELLYFIN_LOGS",
            r"D:\Wandering_Sea\Den_Branch\Sarcophagus\VoyagerRecords\configurations\logs",
        ),
        port=_env_int("VOYAGER_JELLYFIN_PORT", 1977),
    ),
)


@lru_cache(maxsize=1)
def get_gate_map() -> dict[str, GateConfig]:
    return {gate.slug: gate for gate in GATE_CONFIGS}
