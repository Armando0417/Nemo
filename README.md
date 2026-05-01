# Nemo

Nemo is the host FastAPI application for the local gates/modules in this workspace.

Included in this repository:
- Nemo server entrypoint: `server.py`
- FastAPI routers: `routers/`
- Integrated backend modules: `codex/`, `ishtar/`, `relay/`, `gates/`, `priestess/`, `startup_services/`
- Custom app source trees: `CodexVault/`, `IshtarCollective/`, `TitanRelay/`
- Built frontend assets served directly by Nemo: `codex_frontend_dist/`, `ishtar_frontend_dist/`, `TitanRelay/web/`
- Example config files such as `*.env.example` and `TitanRelay/titanrelay.example.json`

Intentionally excluded:
- Media libraries served from external drives.
- Relay transferred payloads under `TitanRelay/device-handoff/`.
- Python virtual environments, `node_modules`, caches, and build scratch folders.
- Live secrets/config such as `*.env`, `TitanRelay/relay.env`, `priestess/priestess.env`, and `TitanRelay/titanrelay.json`.
- Jellyfin binaries/data/cache/log directories. Nemo only keeps the management code that can point at external Jellyfin installs.

## Run

Create a Python environment and install the server dependencies:

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start Nemo:

```powershell
venv\Scripts\python.exe -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Main URLs:
- `http://<server-ip>:8000/codex`
- `http://<server-ip>:8000/ishtar`
- `http://<server-ip>:8000/relay`
- `http://<server-ip>:8000/api/gates`
- `http://<server-ip>:8000/api/priestess`

See `ReadME` for the full local URL reference.

## Local Config

Copy example files before configuring secrets:

```powershell
Copy-Item TitanRelay\titanrelay.example.json TitanRelay\titanrelay.json
Copy-Item TitanRelay\relay.env.example TitanRelay\relay.env
Copy-Item priestess\priestess.env.example priestess\priestess.env
```

Set external library paths with environment variables when needed:
- `CODEX_VAULT_LIBRARY_PATH`
- `TOMB_SOURCE_ROOT`
- `AKASHIC_JELLYFIN_EXE`, `AKASHIC_JELLYFIN_DATA`, `AKASHIC_JELLYFIN_CACHE`, `AKASHIC_JELLYFIN_LOGS`
- `HTV_JELLYFIN_EXE`, `HTV_JELLYFIN_DATA`, `HTV_JELLYFIN_CACHE`, `HTV_JELLYFIN_LOGS`
- `VOYAGER_JELLYFIN_EXE`, `VOYAGER_JELLYFIN_DATA`, `VOYAGER_JELLYFIN_CACHE`, `VOYAGER_JELLYFIN_LOGS`

## Archive Notes

This repository is meant to preserve the runnable Nemo application code and custom gate apps, not the homelab media payloads. A fresh clone can run the server after dependencies and local env files are recreated, but Codex/Ishtar/Jellyfin content still depends on your external library paths.
