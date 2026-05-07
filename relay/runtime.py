from __future__ import annotations

import os
import logging
from pathlib import Path
import shlex
import subprocess
import threading
import time
from typing import Any

from relay.config import RelaySettings
from relay.service import CopypartyClient

logger = logging.getLogger("nemo.copyparty")


class CopypartyRuntimeManager:
    def __init__(self, settings: RelaySettings):
        self.settings = settings
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._last_reachable: bool | None = None

    def status(self, client: CopypartyClient) -> dict[str, Any]:
        reachable, detail, status_code = client.probe(timeout=self.settings.copyparty_status_timeout)
        process = self._get_live_process()
        if reachable != self._last_reachable:
            if reachable:
                logger.info("Copyparty is reachable at %s.", client.base_url)
            else:
                logger.warning("Copyparty is not reachable at %s: %s", client.base_url, detail or "unknown error")
            self._last_reachable = reachable
        return {
            "reachable": reachable,
            "detail": detail,
            "statusCode": status_code,
            "baseUrl": client.base_url,
            "managed": process is not None,
            "managedPid": process.pid if process is not None else None,
            "autoStart": self.settings.copyparty_auto_start,
            "launchConfigured": bool(self.settings.copyparty_launch_command),
        }

    def ensure_running(self, client: CopypartyClient, start_if_needed: bool | None = None) -> dict[str, Any]:
        status = self.status(client)
        if status["reachable"]:
            return status

        should_start = self.settings.copyparty_auto_start if start_if_needed is None else start_if_needed
        if not should_start:
            logger.info("Copyparty auto-start skipped because it is disabled.")
            return status

        if not self.settings.copyparty_launch_command:
            logger.warning("Copyparty is unreachable and no launch command is configured.")
            status["detail"] = (
                status["detail"]
                or "Copyparty is not reachable and RELAY_COPYPARTY_LAUNCH_COMMAND is not configured."
            )
            return status

        with self._lock:
            status = self.status(client)
            if status["reachable"]:
                return status

            process = self._get_live_process()
            if process is None:
                process = self._spawn_process()
                logger.info("Copyparty spawned with pid %s.", process.pid)

        deadline = time.time() + self.settings.copyparty_startup_timeout
        while time.time() < deadline:
            status = self.status(client)
            if status["reachable"]:
                return status
            if process.poll() is not None:
                logger.error("Copyparty exited with code %s before becoming reachable.", process.returncode)
                status["detail"] = (
                    f"Copyparty launch process exited with code {process.returncode} before becoming reachable."
                )
                return status
            time.sleep(0.5)

        status = self.status(client)
        if not status["reachable"]:
            logger.error("Timed out waiting for Copyparty at %s.", client.base_url)
            status["detail"] = (
                status["detail"]
                or f"Timed out waiting for Copyparty at {client.base_url}."
            )
        return status

    def _spawn_process(self) -> subprocess.Popen:
        command = shlex.split(self.settings.copyparty_launch_command, posix=False)
        if not command:
            raise RuntimeError("RELAY_COPYPARTY_LAUNCH_COMMAND did not produce an executable command.")

        runtime_dir = self.settings.runtime_dir
        appdata_dir = runtime_dir / "appdata"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        appdata_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["APPDATA"] = str(appdata_dir)
        env.setdefault("RELAY_COPYPARTY_BASE_URL", self.settings.copyparty_base_url)
        env.setdefault("RELAY_COPYPARTY_USERNAME", self.settings.copyparty_username)
        env.setdefault("RELAY_COPYPARTY_PASSWORD", self.settings.copyparty_password)
        env.setdefault("RELAY_COPYPARTY_USERS", self.settings.copyparty_users)
        env.setdefault("RELAY_INBOX_ROOT", self.settings.inbox_root)
        env.setdefault("RELAY_DUMP_ROOT", self.settings.dump_root)

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        logger.info(
            "Launching Copyparty executable=%s cwd=%s runtime=%s.",
            command[0],
            self.settings.copyparty_launch_cwd,
            runtime_dir,
        )
        process = subprocess.Popen(
            command,
            cwd=str(self.settings.copyparty_launch_cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self._process = process
        return process

    def _get_live_process(self) -> subprocess.Popen | None:
        process = self._process
        if process is None:
            return None
        if process.poll() is not None:
            logger.warning("Managed Copyparty process exited with code %s.", process.returncode)
            self._process = None
            return None
        return process
