# V2bX SSH Manager

Windows desktop manager for a single V2bX VPS at a time.

## Features

- SSH password connection.
- Install/update V2bX using the upstream install script.
- Keep program installation separate from node deployment so logs are easier to interpret.
- Pull and edit `/etc/V2bX/config.json`.
- Deploy VLESS Reality and Shadowsocks nodes through the official `V2bX generate` prompt flow.
- Verify deployed node identities after scripted deployment to catch truncated multi-node configs.
- Add xray nodes without overwriting pulled nodes; updating requires selecting a row explicitly.
- Delete selected xray nodes from the local editing area.
- Built-in presets for VLESS Reality-style panel nodes and Shadowsocks.
- User templates saved beside the software in `data/templates.json`.
- Per-node `ApiHost`, `ApiKey`, `NodeID`, and `NodeType`.
- Backup before upload and restart.
- Roll back to the latest backup.
- View service status and recent logs.
- Optional firewall-open operation.

## Development

```powershell
.\run.bat
```

## Build

```powershell
.\build.bat
```

The executable is written to `..\..\outputs\V2bX-SSH-Manager.exe`.
