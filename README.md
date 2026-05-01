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
venv\Scripts\python.exe server.py
```

`server.py` defaults to port `80` through `NEMO_PORT`. On Windows, port 80 requires an Administrator terminal. If needed, use `NEMO_PORT=8080`.

Main URLs:
- `http://<server-ip>:8000/codex`
- `http://<server-ip>:8000/ishtar`
- `http://<server-ip>:8000/relay`
- `http://<server-ip>:8000/akashic`
- `http://<server-ip>:8000/htv`
- `http://<server-ip>:8000/voyager`
- `http://<server-ip>:8000/api/gates`
- `http://<server-ip>:8000/api/priestess`
- `http://<server-ip>:8000/api/dns`

See `ReadME` for the full local URL reference.

## Local Config

Copy example files before configuring secrets:

```powershell
Copy-Item TitanRelay\titanrelay.example.json TitanRelay\titanrelay.json
Copy-Item TitanRelay\relay.env.example TitanRelay\relay.env
Copy-Item priestess\priestess.env.example priestess\priestess.env
```

Set external library paths with environment variables when needed:
- `NEMO_PORT`: HTTP port, defaults to `80` when running `python server.py`.
- `NEMO_DNS_ENABLED`: starts Nemo's built-in DNS resolver, defaults to `true`.
- `NEMO_DNS_HOSTNAME`: defaults to `chaldeas.home`.
- `NEMO_DNS_RESOLVE_IP`: IP returned for `chaldeas.home`, e.g. your Tailscale IP.
- `NEMO_DNS_UPSTREAM`: upstream resolver for all other names, defaults to `1.1.1.1`.
- `CODEX_VAULT_LIBRARY_PATH`
- `TOMB_SOURCE_ROOT`
- `AKASHIC_JELLYFIN_EXE`, `AKASHIC_JELLYFIN_DATA`, `AKASHIC_JELLYFIN_CACHE`, `AKASHIC_JELLYFIN_LOGS`
- `HTV_JELLYFIN_EXE`, `HTV_JELLYFIN_DATA`, `HTV_JELLYFIN_CACHE`, `HTV_JELLYFIN_LOGS`
- `VOYAGER_JELLYFIN_EXE`, `VOYAGER_JELLYFIN_DATA`, `VOYAGER_JELLYFIN_CACHE`, `VOYAGER_JELLYFIN_LOGS`

## Archive Notes

This repository is meant to preserve the runnable Nemo application code and custom gate apps, not the homelab media payloads. A fresh clone can run the server after dependencies and local env files are recreated, but Codex/Ishtar/Jellyfin content still depends on your external library paths.

## chaldeas.home Setup

Configure each Jellyfin instance once:
- Akashic Records: Dashboard -> Settings -> Networking -> Base URL = `/akashic`
- H-TV: Dashboard -> Settings -> Networking -> Base URL = `/htv`
- Voyager Records: Dashboard -> Settings -> Networking -> Base URL = `/voyager`

Configure Tailscale Split DNS:
- Tailscale admin console -> DNS settings.
- Remove AdGuard as the global DNS override.
- Add Split DNS for `chaldeas.home` pointing to Armando-GP's Tailscale IP, for example `100.111.90.10`.
- Set `NEMO_DNS_RESOLVE_IP=100.111.90.10` before starting Nemo.

Nemo's DNS resolver is intentionally tiny: it answers only `chaldeas.home` and forwards every other DNS query to `NEMO_DNS_UPSTREAM`.
