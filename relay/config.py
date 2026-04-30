from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
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
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError:
        return default


def _load_json_config(path: Path) -> dict:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@dataclass(frozen=True)
class RelaySettings:
    root_dir: Path
    legacy_root: Path
    web_root: Path
    config_path: Path
    env_file: Path
    runtime_dir: Path
    project_name: str
    copyparty_base_url: str
    copyparty_password: str
    copyparty_username: str
    copyparty_users: str
    inbox_root: str
    dump_root: str
    copyparty_auto_start: bool
    copyparty_launch_command: str
    copyparty_launch_cwd: Path
    copyparty_startup_timeout: float
    copyparty_status_timeout: float


@lru_cache(maxsize=1)
def get_settings() -> RelaySettings:
    root_dir = Path(__file__).resolve().parent.parent
    legacy_root = root_dir / "TitanRelay"
    env_file = Path(os.getenv("RELAY_ENV_FILE", str(legacy_root / "relay.env"))).expanduser()
    _load_env_file(env_file)

    config_path = Path(
        os.getenv("RELAY_CONFIG_PATH", str(legacy_root / "titanrelay.json"))
    ).expanduser()
    raw_config = _load_json_config(config_path)
    copyparty_config = raw_config.get("copyparty") or {}
    mailbox_config = raw_config.get("mailboxes") or {}

    project_name = str(
        os.getenv("RELAY_PROJECT_NAME")
        or raw_config.get("projectName")
        or "Relay"
    ).strip() or "Relay"
    copyparty_base_url = str(
        os.getenv("RELAY_COPYPARTY_BASE_URL")
        or copyparty_config.get("baseUrl")
        or "http://127.0.0.1:3923"
    ).rstrip("/")
    copyparty_password = str(
        os.getenv("RELAY_COPYPARTY_PASSWORD")
        or copyparty_config.get("password")
        or ""
    )
    copyparty_username = str(os.getenv("RELAY_COPYPARTY_USERNAME") or "relay").strip() or "relay"
    copyparty_users = str(os.getenv("RELAY_COPYPARTY_USERS") or "").strip()
    if not copyparty_users and copyparty_password:
        copyparty_users = f"{copyparty_username}:{copyparty_password}"

    copyparty_launch_command = str(
        os.getenv("RELAY_COPYPARTY_LAUNCH_COMMAND") or ""
    ).strip()

    return RelaySettings(
        root_dir=root_dir,
        legacy_root=legacy_root,
        web_root=legacy_root / "web",
        config_path=config_path,
        env_file=env_file,
        runtime_dir=Path(
            os.getenv("RELAY_RUNTIME_DIR", str(legacy_root / "relay_runtime"))
        ).expanduser(),
        project_name=project_name,
        copyparty_base_url=copyparty_base_url,
        copyparty_password=copyparty_password,
        copyparty_username=copyparty_username,
        copyparty_users=copyparty_users,
        inbox_root=str(
            os.getenv("RELAY_INBOX_ROOT")
            or mailbox_config.get("inboxRoot")
            or "/device-handoff"
        ),
        dump_root=str(
            os.getenv("RELAY_DUMP_ROOT")
            or mailbox_config.get("dumpRoot")
            or "/device-handoff-dump"
        ),
        copyparty_auto_start=env_flag(
            "RELAY_COPYPARTY_AUTO_START",
            bool(copyparty_launch_command),
        ),
        copyparty_launch_command=copyparty_launch_command,
        copyparty_launch_cwd=Path(
            os.getenv("RELAY_COPYPARTY_LAUNCH_CWD", str(legacy_root))
        ).expanduser(),
        copyparty_startup_timeout=env_float("RELAY_COPYPARTY_STARTUP_TIMEOUT", 20.0),
        copyparty_status_timeout=env_float("RELAY_COPYPARTY_STATUS_TIMEOUT", 3.0),
    )
