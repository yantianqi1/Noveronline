# CLAUDE.md

This file guides Claude Code when working in this repository.

## Project Overview

MiroFish-Novel is a multi-agent novel analysis and writing platform. It turns uploaded novels, outlines, character cards, and free-form materials into structured story knowledge, then uses that knowledge for graph exploration, archive management, single-world simulation, and Writer Agent-assisted prose generation.

This repository was originally inspired by `MiroFish`, but this codebase is novel-domain specific. Do not bring back social-media, public-opinion, Twitter, Reddit, or sentiment-analysis abstractions unless explicitly requested.

## Commands

### Backend

```bash
cd backend
uv sync
APP_PORT=3888 uv run python run.py
```

If `uv` is unavailable:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .
APP_PORT=3888 .venv/bin/python run.py
```

FastAPI docs are available at `http://localhost:3888/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
npm run lint
npm run build
npm run test
```

The Vite dev server listens on `http://localhost:3999` and proxies `/api` to `http://127.0.0.1:3888`.

### Tests

```bash
cd backend
env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests
env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests/test_worldline_engine.py
```

Use explicit UTF-8 environment variables on machines where the repository path contains non-ASCII characters.

### Database Migrations

```bash
cd backend
uv run alembic upgrade head
uv run alembic revision -m "add_feature_table"
uv run alembic downgrade -1
```

Startup runs `alembic upgrade head` through the FastAPI lifespan. Never edit applied revisions; add a new revision.

## Architecture

### Backend

`backend/app/` is a layered FastAPI application:

- `api_fastapi/` — REST routers mounted under `/api`.
- `services/` — domain services for seed analysis, graph, archives, assets, worldline, and writer agent.
- `repositories/` — database access layer. Services should use repositories rather than raw SQL.
- `tables/` — SQLAlchemy table definitions with shared metadata.
- `schemas/` — Pydantic request and response schemas.
- `models/` — lightweight domain models and runtime managers.
- `middleware/` — API key auth and error handling.
- `backend/app/database.py` — engine creation and Alembic-backed initialization.
- `backend/app/dependencies.py` — FastAPI dependency providers.
- `backend/app/config.py` — Pydantic settings plus legacy compatibility config.
- `backend/app/main.py` — application factory, CORS, lifespan, `/health`, and router mounting.
- `utils/` — LLM client, JSON parsing, file parsing, logging, and retry utilities.

### Important Backend Subsystems

- **Seed pipeline**: upload, segmentation, sequential reading, aggregation, ontology generation, and character Agent profile generation.
- **Graph pipeline**: reading notes to story memory to `graph_*` unified DB tables.
- **Archive system**: candidate generation, narrative entity archives, and memory review tiers.
- **Asset library**: unified read model over assets, archives, threads, rules, relationships, projects, and manuscript blocks.
- **Worldline**: single-world simulation, prepared agent dossiers, runtime event tables, variable injection, auto-evolution, and SSE output.
- **Writer Agent**: retrieval planning, tool loop, prose writing, manuscript compilation, reviewer pass, dedup extraction, world-data update, and book-plan workflows.
- **LLM facility**: `llm_channels`, `llm_models`, `llm_module_bindings`, activity tracking, and module-level routing.

### Frontend

`frontend/src/` is a React 19 + TypeScript + Vite app:

- `pages/overview/` — project creation, seed upload, pipeline status, trace viewing.
- `pages/asset-library/` — unified assets, search, facets, details.
- `pages/story-graph/` — D3 story graph, build console, inspector, graph bond generation.
- `pages/worldline/` — worldline workbench, director panels, roster, timeline, variable controls.
- `pages/writer/` — Writer Workbench, book plan, chapters, scenes, manuscript, reviewer, continuation context.
- `pages/llm-facility/` — channel, model, and module-binding management.
- `components/` — shared business components and `ui/` primitives.
- `api/` — domain API clients and SSE helper.
- `stores/` — Zustand stores.
- `frontend/src/router.tsx` — React Router 7 route table. Legacy `/archive-library` redirects to `/assets`.

## Persistence Model

- Default DB: `backend/data/mirofish.db` via `DATABASE_URL`.
- Schema owner: Alembic revisions under `backend/alembic/versions/`.
- Runtime services should read and write through repositories.
- Legacy JSON artifacts in `backend/uploads/projects/` are being reduced; consult `docs/database/database-source-of-truth-matrix.md` before adding any JSON read path.
- Do not commit local databases, uploads, LLM traces, logs, or user manuscript content.

## LLM Rules

- All LLM calls route through the global LLM facility.
- Do not add legacy environment-variable model fallbacks.
- Missing module binding should be visible and explicit.
- Use module keys consistently, for example `writer_reviewer`, `writer_dedup_extractor`, and graph / archive generation modules.
- Prompt and response traces may include user content; treat them as sensitive runtime artifacts.

## Development Conventions

- Fix root causes rather than hiding failures.
- Avoid mock success paths, silent degradation, broad fallback behavior, and swallowed exceptions.
- Keep domain language novel-specific.
- Keep functions and files focused; split large responsibilities.
- Use parameterized DB operations and validate external input at boundaries.
- For backend tests, prefer a hard timeout around long-running commands.
- Check `git status --short` before editing because this repository often has active uncommitted work.

## Documentation Map

- `README.md` — public project overview, setup, commands, and contribution entry points.
- `AGENTS.md` — AI agent handoff, product facts, and stricter development constraints.
- `docs/CODEX_HANDOFF_GUIDE.md` — detailed Codex handoff notes.
- `docs/database/database-source-of-truth-matrix.md` — DB vs legacy source-of-truth matrix.
- `docs/fastapi-route-manifest.md` — route inventory.
- `docs/agent-data-schema-reference.md` — Agent data schemas and prompt references.

## Open Source Notes

The repository is licensed as `AGPL-3.0-only`. Contributions should follow `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SECURITY.md`.
