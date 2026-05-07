from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from pathlib import Path
import subprocess
import threading
from typing import Any

from startup_services.config import StartupServiceConfig, get_startup_service_map

logger = logging.getLogger("nemo.startup")


@dataclass
class StartupServiceStatus:
    slug: str
    name: str
    state: str
    running: bool
    managed: bool
    pid: int | None
    managed_pid: int | None
    executable_exists: bool
    visible_console: bool
    auto_start: bool
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StartupServiceManager:
    def __init__(self):
        self._services = get_startup_service_map()
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen] = {}

    def list_statuses(self) -> list[dict[str, Any]]:
        return [self.check_service(slug) for slug in self._services]

    def start_auto_services(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for slug, service in self._services.items():
            if not service.auto_start:
                logger.info("Startup service %s is configured but auto-start is disabled.", slug)
                continue
            try:
                logger.info("Auto-starting startup service %s.", slug)
                results.append(self.start_service(slug))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to auto-start startup service %s.", slug)
                results.append(
                    {
                        "slug": slug,
                        "name": service.name,
                        "action": "start_failed",
                        "detail": str(exc),
                    }
                )
        return results

    def check_service(self, slug: str) -> dict[str, Any]:
        service = self._require_service(slug)
        managed_process = self._get_live_process(service.slug)
        discovered_pid = self._find_process_pid(service.process_names)
        pid = discovered_pid or (managed_process.pid if managed_process else None)
        executable = service.executable
        executable_exists = executable.exists() if executable is not None else False

        state = "running" if pid is not None else "stopped"
        detail = None
        if executable is None or not service.command:
            state = "not_configured"
            detail = "No command is configured."
        elif not executable_exists:
            state = "missing_executable"
            detail = f"Executable not found: {executable}"

        return StartupServiceStatus(
            slug=service.slug,
            name=service.name,
            state=state,
            running=pid is not None,
            managed=managed_process is not None,
            pid=pid,
            managed_pid=managed_process.pid if managed_process else None,
            executable_exists=executable_exists,
            visible_console=service.visible_console,
            auto_start=service.auto_start,
            detail=detail,
        ).to_dict()

    def start_service(self, slug: str) -> dict[str, Any]:
        service = self._require_service(slug)
        status = self.check_service(service.slug)
        if status["running"]:
            logger.info("Startup service %s is already running on pid %s.", service.slug, status.get("pid"))
            status["action"] = "already_running"
            return status
        if status["state"] in {"missing_executable", "not_configured"}:
            logger.error("Startup service %s cannot start: %s", service.slug, status.get("detail"))
            raise FileNotFoundError(status["detail"] or f"{service.name} is not configured.")

        with self._lock:
            existing = self._get_live_process(service.slug)
            if existing is None:
                self._processes[service.slug] = self._spawn_service(service)

        status = self.check_service(service.slug)
        logger.info("Startup service %s started with pid %s.", service.slug, status.get("pid"))
        status["action"] = "started"
        return status

    def stop_service(self, slug: str) -> dict[str, Any]:
        service = self._require_service(slug)
        logger.info("Stopping startup service %s.", service.slug)
        stopped_pids: list[int] = []
        managed_process = self._get_live_process(service.slug)
        if managed_process is not None:
            self._kill_pid(managed_process.pid)
            stopped_pids.append(managed_process.pid)
            self._processes.pop(service.slug, None)

        status = self.check_service(service.slug)
        status["action"] = "stopped" if stopped_pids else "not_managed"
        status["stopped_pids"] = stopped_pids
        logger.info("Startup service %s stop result: %s.", service.slug, status["action"])
        return status

    def shutdown_managed(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for slug, process in list(self._processes.items()):
            service = self._services.get(slug)
            if service is None or not service.stop_managed_on_shutdown:
                continue
            try:
                logger.info("Stopping managed startup service %s on Nemo shutdown.", slug)
                self._kill_pid(process.pid)
                self._processes.pop(slug, None)
                results.append({"slug": slug, "action": "stopped", "pid": process.pid})
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to stop startup service %s during shutdown.", slug)
                results.append({"slug": slug, "action": "shutdown_error", "detail": str(exc)})
        return results

    def _require_service(self, slug: str) -> StartupServiceConfig:
        normalized = slug.strip().lower()
        service = self._services.get(normalized)
        if service is None:
            supported = ", ".join(sorted(self._services))
            raise KeyError(f"Unknown startup service '{slug}'. Supported services: {supported}.")
        return service

    def _get_live_process(self, slug: str) -> subprocess.Popen | None:
        process = self._processes.get(slug)
        if process is None:
            return None
        if process.poll() is not None:
            self._processes.pop(slug, None)
            return None
        return process

    def _spawn_service(self, service: StartupServiceConfig) -> subprocess.Popen:
        creationflags = 0
        startupinfo = None
        if service.visible_console:
            creationflags |= getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        else:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

        cwd = str(service.cwd) if service.cwd and service.cwd.exists() else None
        logger.info(
            "Launching startup service %s executable=%s cwd=%s visible_console=%s.",
            service.slug,
            service.command[0] if service.command else "not-configured",
            cwd or "<default>",
            service.visible_console,
        )
        return subprocess.Popen(
            list(service.command),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=None if service.visible_console else subprocess.DEVNULL,
            stderr=None if service.visible_console else subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

    def _find_process_pid(self, process_names: tuple[str, ...]) -> int | None:
        if not process_names:
            return None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        for process_name in process_names:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            for line in result.stdout.splitlines():
                cleaned = line.strip()
                if not cleaned or cleaned.upper().startswith("INFO:"):
                    continue
                columns = [part.strip('"') for part in cleaned.split('","')]
                if len(columns) < 2:
                    continue
                try:
                    return int(columns[1])
                except ValueError:
                    continue
        return None

    def _kill_pid(self, pid: int) -> None:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )


_MANAGER: StartupServiceManager | None = None


def get_startup_service_manager() -> StartupServiceManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = StartupServiceManager()
    return _MANAGER
