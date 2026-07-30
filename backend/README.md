# Legacy backend

This directory contains the retired FastAPI application used only as a source
for legacy-data import and compatibility work. It is not the current product
runtime and it has no supported frontend.

Active development belongs in:

- `apps/api` for the Go control plane
- `apps/web` for the Next.js application
- `apps/agent-runtime` for Python domain workers
- `apps/pi-agent-runtime` for the Writer Agent runtime
- `infra` for local and production infrastructure

Do not expose this service as a production application. When legacy behavior
must be inspected locally, install the dependencies and use the example
configuration in this directory:

```bash
cd backend
cp .env.example .env
uv sync --extra dev
APP_PORT=3888 uv run python run.py
```

See the root `README.md` for the supported SaaS startup path.
