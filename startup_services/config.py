from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).expanduser()


def _split_command(command: str) -> list[str]:
    import shlex

    return shlex.split(command)


@dataclass(frozen=True)
class StartupServiceConfig:
    slug: str
    name: str
    command: tuple[str, ...]
    cwd: Path | None
    process_names: tuple[str, ...]
    visible_console: bool
    auto_start: bool
    stop_managed_on_shutdown: bool

    @property
    def executable(self) -> Path | None:
        if not self.command:
            return None
        return Path(self.command[0]).expanduser()


def _tailscale_config() -> StartupServiceConfig:
    command = os.getenv("TAILSCALE_COMMAND")
    if command:
        args = tuple(_split_command(command))
    else:
        exe = _env_path(
            "TAILSCALE_EXE",
            r"C:\Program Files\Tailscale\tailscale-ipn.exe",
        )
        args = (str(exe),)

    return StartupServiceConfig(
        slug="tailscale",
        name="Tailscale",
        command=args,
        cwd=Path(os.getenv("TAILSCALE_CWD", "")).expanduser() if os.getenv("TAILSCALE_CWD") else None,
        process_names=tuple(
            name.strip()
            for name in os.getenv("TAILSCALE_PROCESS_NAMES", "tailscale-ipn.exe,tailscaled.exe,tailscale.exe").split(",")
            if name.strip()
        ),
        visible_console=_env_flag("TAILSCALE_VISIBLE_CONSOLE", False),
        auto_start=_env_flag("NEMO_AUTOSTART_TAILSCALE", True),
        stop_managed_on_shutdown=_env_flag("NEMO_STOP_TAILSCALE_ON_SHUTDOWN", False),
    )


STARTUP_SERVICE_CONFIGS = (
    _tailscale_config(),
)


@lru_cache(maxsize=1)
def get_startup_service_map() -> dict[str, StartupServiceConfig]:
    return {service.slug: service for service in STARTUP_SERVICE_CONFIGS}
