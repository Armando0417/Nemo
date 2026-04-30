from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PriestessSettings:
    root_dir: Path
    env_file: Path
    service_name: str
    enabled: bool
    discord_webhook_url: str
    discord_username: str
    discord_mention: str
    relay_alerts_enabled: bool
    queue_max_size: int


@lru_cache(maxsize=1)
def get_settings() -> PriestessSettings:
    root_dir = Path(__file__).resolve().parent.parent
    env_file = Path(os.getenv("PRIESTESS_ENV_FILE", str(root_dir / "priestess" / "priestess.env"))).expanduser()
    _load_env_file(env_file)

    service_name = (
        os.getenv("PRIESTESS_SERVICE_NAME")
        or os.getenv("NEMO_ALERTS_SERVICE_NAME")
        or "Priestess"
    ).strip() or "Priestess"

    webhook_url = str(os.getenv("PRIESTESS_DISCORD_WEBHOOK_URL") or "").strip()

    return PriestessSettings(
        root_dir=root_dir,
        env_file=env_file,
        service_name=service_name,
        enabled=env_flag("PRIESTESS_ENABLED", True),
        discord_webhook_url=webhook_url,
        discord_username=str(os.getenv("PRIESTESS_DISCORD_USERNAME") or service_name).strip() or service_name,
        discord_mention=_normalize_discord_mention(os.getenv("PRIESTESS_DISCORD_MENTION") or ""),
        relay_alerts_enabled=env_flag("PRIESTESS_RELAY_ALERTS_ENABLED", True),
        queue_max_size=int(os.getenv("PRIESTESS_QUEUE_MAX_SIZE", "256")),
    )


def _normalize_discord_mention(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if value.startswith("<@&") and value.endswith(">"):
        return value
    if value.isdigit():
        return f"<@&{value}>"
    return value
