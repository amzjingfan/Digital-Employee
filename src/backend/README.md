# Backend

FastAPI backend for Joukir's StaffDeck application.

## Install and run

Run commands from the repository root. Install the locked backend dependencies with:

```bash
uv sync --project src/backend --locked --extra dev
```

Start the complete single-port development application with the wrapper for the
current platform:

```bash
# macOS, Linux, or WSL
src/scripts/dev_up.sh --detach
```

```powershell
# Windows PowerShell
.\src\scripts\dev_up.ps1 --detach
```

For backend-only debugging, point the settings loader at the ignored backend
configuration and start the API directly:

```bash
ULTRARAG_DOTENV=src/backend/.env src/backend/.venv/bin/python -m uvicorn \
  --app-dir backend app.main:app --host 127.0.0.1 --port 8000
```

```powershell
$env:ULTRARAG_DOTENV = "src/backend/.env"
src\backend\.venv\Scripts\python.exe -m uvicorn `
  --app-dir backend app.main:app --host 127.0.0.1 --port 8000
```

The repository does not provide `.env.example`. Obtain `src/backend/.env` through the
approved secure deployment handoff, or supply the required settings through the
process environment. Do not commit deployment configuration or secrets.

PostgreSQL is authoritative for the current restored development environment and
for production schema work. Apply reviewed schema changes from `src/backend/migrations/`
and preserve the configured tenant RLS and least-privilege roles. SQLite remains a
local default for isolated demos and tests that explicitly use it; it does not
represent the restored PostgreSQL/Casdoor environment.

Use `http://127.0.0.1:8000/api/health` for the backend-only health check. The main
application deliberately disables Swagger, ReDoc, and the OpenAPI schema, so
`/docs`, `/redoc`, and `/openapi.json` are unavailable.

`CORS_ORIGINS` controls the allowed frontend origins. The lifecycle wrappers supply
the local single-port origins by default; set the variable explicitly when another
trusted frontend origin is required.

## Agent process sandbox

Commands exposed by the Harness are always executed through an OS process
sandbox. Anthropic's Sandbox Runtime is the preferred backend because it uses
the native primitive on macOS, Linux, and Windows. Release builds bundle the
SRT package and a matching Node binary, so end users do not need Node or a
global npm installation. Source deployments prepare the same reviewed runtime
once from the repository root:

```bash
python3 src/packaging/fetch_sandbox_runtime.py src/packaging/sandbox_runtime
```

The bootstrap uses the committed dependency lock and `npm ci`, verifies the
downloaded Node archive, and applies StaffDeck's reviewed unrestricted-network
compatibility patch. The repository-local runtime takes precedence over a
global `srt` installation. Unreviewed global installations are ignored unless
development explicitly sets `STAFFDECK_ALLOW_GLOBAL_SRT=true`; normal
`src/scripts/dev_up.sh` startup prepares the reviewed local runtime automatically.

When `srt` is unavailable, Linux deployments may use the existing Bubblewrap
backend (`bwrap`). There is no unsandboxed fallback: the `exec_command`
capability is reported as unavailable until one of these backends is installed.
The sandbox keeps the current TaskFrame workspace as the only writable area.
The tenant administrator selects unrestricted network access (the default), a
domain allowlist, or complete network denial in Runtime Settings. Policies are
enforced by SRT and fail closed when the selected backend cannot represent one.

On Windows, SRT also needs its one-time elevated setup so it can create the
dedicated `srt-sandbox` account and egress filter:

```powershell
srt windows-install
```

The macOS backend uses Seatbelt and works on both Intel (`x86_64`) and Apple
Silicon (`arm64`) builds. The packaging scripts bundle the matching Node
binary for the build architecture and sign it with the rest of the app.

## General Skill Code Runtime

通用技能生成的 Python/Bash runner 不直接依赖系统 Python。运行时按以下顺序选择环境：

1. `GENERAL_SKILL_RUNTIME_PYTHON` 指定的 Python；
2. `GENERAL_SKILL_RUNTIME_VENV` 指定虚拟环境中的 Python；
3. `src/backend/.venv/bin/python`；
4. 自动创建 `src/backend/.runtime_venv`。

`GENERAL_SKILL_RUNTIME_PACKAGES` 默认安装/校验 `requests,httpx`，用于通用 API
访问。需要文档解析或数据处理时可以扩展为：

```bash
GENERAL_SKILL_RUNTIME_PACKAGES="requests,httpx,beautifulsoup4,lxml,pypdf,python-docx,pandas,numpy,python-dateutil"
```

如果部署环境禁止自动安装依赖，设置：

```bash
GENERAL_SKILL_RUNTIME_AUTO_INSTALL="false"
GENERAL_SKILL_RUNTIME_PYTHON="/path/to/prepared/venv/bin/python"
```

## Demo Seed

Startup seeds:

- `tenant_demo`
- refund skill `after_sales_refund`
- exchange skill `after_sales_exchange`
- mock HTTP tool `order.query`

Set `DEMO_MODEL_API_KEY` before first startup if you want a default model config to be created automatically.
