# TitanRelay

TitanRelay is a standalone mailbox app that uses Copyparty as the storage and post-office layer.

Each device gets an inbox and a dump folder:

- `/device-handoff/pit`
- `/device-handoff/ipad`
- `/device-handoff/s23`
- `/device-handoff/laptop`
- `/device-handoff-dump/pit`
- `/device-handoff-dump/ipad`
- `/device-handoff-dump/s23`
- `/device-handoff-dump/laptop`

The browser talks to TitanRelay, and TitanRelay talks to Copyparty. That removes the old same-origin requirement and keeps the Copyparty password out of the frontend.

## Files

- `titanrelay_server.py`: standalone Python server and Copyparty proxy
- `titanrelay.json`: active runtime config
- `titanrelay.example.json`: clean config template
- `start-titanrelay.ps1`: launch script
- `initialize-mailboxes.ps1`: creates the inbox and dump folders in Copyparty
- `web/`: frontend, PWA assets, and device pages

## Run

1. Edit `titanrelay.json` if the Copyparty URL, password, roots, or device list need to change.
2. Run `.\initialize-mailboxes.ps1` once.
3. Run `.\start-titanrelay.ps1`.
4. Open `http://127.0.0.1:8732/`.

## Notes

- TitanRelay defaults to `http://127.0.0.1:3923` because that matched the existing project.
- The included config keeps the existing Copyparty password from the original frontend setup.
- If you want remote devices to install the app as a real PWA, serve TitanRelay over `https://` or through a secure local reverse proxy. On plain LAN `http://`, the app still works in a browser, but installability and service workers depend on secure-context rules.
- Inbox entries are moved into the matching dump folder when the user clicks `Download + Dump`.
- Folder uploads preserve relative paths. Android-style leaked picker roots are stripped so uploads do not recreate `/storage/emulated/0/...`.
