# Deployment on Windows

The Windows desktop is the primary host. Two modes are supported. Use **native**
mode for discovery and development; move to Docker only after connectivity, MCP
integration, and the discovery mapping are stable.

## Prerequisites

- Python 3.11+ (3.12 recommended). [`uv`](https://docs.astral.sh/uv/) is
  recommended for fast installs, but `pip` works.
- Network reachability from the Windows desktop to Qdrant/PostgreSQL on the
  Synology (test with `Test-NetConnection synology.local -Port 6333`).

## Native mode

```powershell
# From the repository root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

Copy-Item .env.example .env
Copy-Item config\schema_mapping.example.yaml config\schema_mapping.yaml
# Edit both from your discovery report.

# Read-only discovery
python scripts\inspect_qdrant.py
python scripts\inspect_postgres.py

# Verify read-only + smoke test
python scripts\verify_read_only.py
python scripts\smoke_test.py --query "asset tagging implementation risks"

# Run the REST API (http://127.0.0.1:8765/docs)
python -m synology_rag.api
```

The MCP server is normally launched by the AI client (see
[`mcp-tools.md`](mcp-tools.md)); to run it manually:

```powershell
python -m synology_rag.mcp.server
```

### One-command installer

`scripts/install-windows.ps1` wraps venv creation, dependency install,
configuration validation, and service actions:

```powershell
# Set up the environment
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Action install

# Validate configuration (fails closed on problems)
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Action validate

# Run in the foreground
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Action run

# Tail logs / remove the venv
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Action logs
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Action uninstall
```

Administrator rights are only needed if you later register a Windows service or a
firewall rule. For a long-running background service, wrap the run command with
[NSSM](https://nssm.cc/) or Task Scheduler pointing at
`.venv\Scripts\python.exe -m synology_rag.api`.

## Docker mode

Use after native validation. The container reaches the Synology over the LAN, so
set `QDRANT_URL`/`POSTGRES_HOST` to the Synology address (not `localhost`).

```powershell
# Build and run; the port is published to 127.0.0.1 only.
docker compose up --build
```

Key points baked into `docker-compose.yml`:
- Publishes `127.0.0.1:8765:8765` (not exposed to the LAN/internet).
- Sets `BIND_HOST=0.0.0.0` + `ALLOW_NON_LOCAL_BIND=true` (safe because the host
  binding is localhost-only).
- Mounts `config/schema_mapping.yaml` read-only.
- If the Synology hostname is not resolvable inside the container, add an
  `extra_hosts` entry.

Secrets are injected from `.env` at runtime and never baked into the image.

## Configuration reference

See [`.env.example`](../.env.example) and
[`config/schema_mapping.example.yaml`](../config/schema_mapping.example.yaml).
Startup fails closed on missing/invalid configuration, so a clean start confirms
your settings are coherent.

## Health & logs

- Liveness: `GET http://127.0.0.1:8765/health/live`
- Readiness: `GET http://127.0.0.1:8765/health/ready`
- Logs are structured JSON on stderr. Redirect to a file for a Windows service,
  e.g. `... 2> logs\api.log`.
