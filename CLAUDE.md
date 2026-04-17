# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MiroFish-Novel is a multi-agent novel analysis and writing platform. Users upload novel text, the system extracts structured knowledge (characters, relationships, world rules, plot threads), builds a story graph, generates entity archives, and provides a worldline simulation engine and multi-agent writing workbench.

Product domain: novel world-graph construction, character/faction/organization archive generation, relationship evolution analysis, worldline variable injection, plot trajectory simulation, writer workbench with multi-agent prose generation, and agent interaction.

Migrated from the upstream `MiroFish` project (GitHub: `https://github.com/666ghj/MiroFish`). This is a novel-specific platform — avoid social-media/sentiment-analysis semantics from the upstream project.

## Commands

### Backend

```bash
cd backend
uv sync                                # Install Python dependencies
APP_PORT=3888 uv run python run.py     # Start FastAPI server (uvicorn) on localhost:3888
```

If `uv` is unavailable:

```bash
cd backend
APP_PORT=3888 python3 run.py
```

### Frontend

```bash
cd frontend
npm install                # Install Node dependencies
npm run dev                # Start Vite dev server on localhost:3999 (strictPort)
npm run build              # Production build: `tsc -b && vite build`
npm run lint               # Type-check only: `tsc --noEmit`
npm run test               # Vitest run
```

### Tests

```bash
cd backend
PYTHONPATH=$(pwd) pytest tests/                                    # All tests
PYTHONPATH=$(pwd) pytest tests/test_worldline_engine.py            # Single file
PYTHONPATH=$(pwd) pytest tests/test_some_file.py::test_func_name   # Single test
```

### Database migrations (Alembic)

Schema lifecycle is owned by alembic revisions under `backend/alembic/versions/`. Production/dev runtime auto-runs `alembic upgrade head` on FastAPI startup (`app.main._lifespan`). Tests bypass this via the `_unified_db_bootstrap` conftest fixture.

```bash
cd backend
uv run alembic upgrade head                     # Apply all pending migrations
uv run alembic revision -m "add_foo_table"      # Create a new revision
uv run alembic downgrade -1                     # Roll back one revision
```

## Architecture

### Backend (Python 3.11+ / FastAPI / SQLAlchemy 2.0 / Alembic)

Layered structure under `backend/app/`:

- **`api_fastapi/`** — FastAPI routers (REST endpoints). Mounted at `/api` prefix. Modules: `project.py`, `novel.py`, `llm.py`, `archive.py`, `assets.py`, `unified_assets.py`, `worldline.py`, `writer_agent.py`, plus shared `common.py` / `graph_defaults.py`. (The old `api/` Flask blueprint package is retired — do not add new routes there.)
- **`services/`** — Business logic. Major subsystems described below.
- **`repositories/`** — Thin SQLAlchemy Core/ORM repositories over the unified DB, one per domain (`archive_repo`, `asset_repo`, `chapter_repo`, `entity_repo`, `graph_repo`, `llm_repo`, `manuscript_repo`, `narrative_repo`, `outline_repo`, `preset_repo`, `project_artifact_repo`, `relationship_repo`, `scene_repo`, `search_repo`, `task_repo`, `thread_repo`, `world_rule_repo`, `worldline_prepare_repo`, `worldline_runtime_repo`, `worldline_session_repo`, `book_plan_repo`, `event_repo`, `meta_repo`). Plus `search_backends/` (pluggable: `like_search`, `sqlite_search`, `postgres_search`).
- **`tables/`** — SQLAlchemy table definitions grouped by domain: `archive.py`, `assets.py`, `fts.py`, `graph.py`, `llm.py`, `novel.py`, `search.py`, `task.py`, `worldline.py`. A single shared `metadata` is exported from `tables/__init__.py`.
- **`schemas/`** — Pydantic request/response schemas per domain (`assets_schemas`, `llm_schemas`, `novel_schemas`, `project_schemas`, `unified_assets_schemas`, `worldline_schemas`, `writer_agent_schemas`).
- **`models/`** — Lightweight domain dataclasses: `project.py` (ProjectManager), `task.py` (TaskManager with cancellation), `worldline.py` (session/branch models), `project_types.py`. Project status lifecycle: CREATED → SEED_PROCESSING → ONTOLOGY_GENERATED → GRAPH_BUILDING → GRAPH_COMPLETED (or FAILED).
- **`middleware/`** — `auth.py` (`ApiKeyAuthMiddleware`), `error_handler.py` (exception handlers).
- **`database.py`** — `create_engine_from_settings`, `get_engine`, `init_db(use_alembic=True|False)`. SQLite default, Postgres-ready via `DATABASE_URL`.
- **`dependencies.py`** — FastAPI dependency providers (settings, engine, repositories).
- **`utils/`** — `llm_client.py` (OpenAI-compatible wrapper with JSON retry + step trace), `file_parser.py`, `llm_json.py` (5-level JSON fallback), `logger.py`.
- **`config.py`** — Pydantic `Settings` + legacy `Config` class, central config from `.env`. Unified DB URL via `DATABASE_URL` (default `sqlite:///./data/mirofish.db`).
- **`main.py`** — FastAPI app factory (`create_app`), CORS + private-network CORS, api-key auth middleware, alembic-driven lifespan, `/health` endpoint, mounts `api_router`.
- **`alembic/`** — Alembic env + `versions/` migration revisions. `alembic.ini` at `backend/` root.

### Unified Database

Single SQLite/Postgres DB (default `backend/data/mirofish.db`) owns almost all persistent state. The legacy multi-file split (`llm_facility.sqlite3`, `archive_library.sqlite3`, `assets_library.sqlite3`, `novel.sqlite3`, per-project JSON artifacts, worldline filesystem state) has been migrated into this DB via phases C–H. Runtime services read/write through repositories only. See `docs/database/database-source-of-truth-matrix.md` for the authoritative per-domain source-of-truth map (still tracks residual legacy read paths).

Key tables include:
- `llm_channels` / `llm_models` / `llm_module_bindings` / `writer_presets_global`
- `assets` / `asset_links` (unified asset store, including `manuscript_block` rows)
- `archive_library` / `archive_sources` / `archive_agent_memory` / `archive_agent_memory_events`
- `entities` / `entity_aliases` / `entity_labels` / `relationships` / `plot_threads` / `world_rule_evidence` / `thread_entity_links` / `rule_entity_links`
- `chapter_content` / `chapter_meta` / `scenes` / `outline_versions` / `book_plans`
- `graph_meta` / `graph_nodes` / `graph_node_labels` / `graph_aliases` / `graph_edges` / `graph_evidence`
- `prepare_runs` / `prepared_agent_dossiers` / `prepare_event_log` / `worldline_sessions` / `worldline_runtime_*`
- `project_artifacts` (DB mirror for legacy project JSON payloads; see Phase G)
- `task_runs`
- FTS virtual tables in `tables/fts.py` + `tables/search.py`

### Key Backend Subsystems

**Seed Pipeline (4-stage)**:
Upload → `smart_novel_segmenter` → `sequential_reader` (LLM sequential reading with arc/volume summaries) → `seed_analysis_aggregator` + `story_ontology_generator` → `character_agent_profile_generator`. Progress tracked via `SeedTaskProgressTracker`. Frontend chapter mapping in `pages/overview/seed-pipeline-chapters.ts` must stay in sync with `seed_pipeline_chapters.py`.

**Graph Building**:
`reading_notes_graph_adapter` → `story_memory_builder` → `graph_builder` (concurrent) → `local_story_graph_builder` (writes to unified `graph_*` tables via `GraphRepository`). Nodes carry `importance_tier`, edges carry `weight`.

**Archive System**:
`archive_candidate_builder` → `narrative_entity_archivist` (LLM, template sections by tier) → `archive_library_service` (unified DB `archive_library` table). Memory review: canon/candidate/experiment tiers.

**Worldline Engine**:
`worldline_engine` (fileless DB persistence via `WorldStateStore`) → `worldline_prepare_service` (session setup, rows in `prepare_runs`/`prepared_agent_dossiers`) → `worldline_agent_registry` (agent roster) → `character_agent_service` (dialogue/action) → auto-evolution with SSE. All session/branch state lives in `worldline_sessions` / `worldline_runtime_*` tables. Single-world model; old multi-branch endpoints return `410`.

**Writer Agent Service** (`services/writer_agent/`):
Flat module layout (not a `prompts/` subpackage — prompts live in `prompts.py`):
- `retrieval_planner.py` — lightweight LLM pre-pass that drafts a `<retrieval_plan>` of tools to call before writing, injected into the orchestrator user message.
- `orchestrator.py` + `agent_loop.py` — agent decision loop with tools.
- `prompts.py` — single-file home for writer/reviewer prompts (previously modular, now consolidated).
- `tools.py` + `tool_executors.py` — `write_prose`, `compile_manuscript`, `query_entity`, `manage_entity`, `manage_thread`, `manage_world_rule`, `manage_relationship`, etc.
- `manuscript_service.py` + `manuscript_context_builder.py` — manuscript CRUD via `ManuscriptRepository`; stores blocks in the unified `assets` table with `asset_type='manuscript_block'`.
- `chapter_service.py`, `scene_service.py`, `preset_service.py`, `book_plan_service.py`, `book_run_orchestrator.py`, `post_processor.py`, `writer.py`.

Task types: `write_scene`, `continue`, `outline`. World data update endpoint (`/api/writer-agent/world-update`) runs the agent loop to incrementally update entities/threads/rules after prose is committed. Entity association tables (`thread_entity_links`, `rule_entity_links`) link plot threads and world rules to entities; `query_entity` returns enriched context including associated threads and applicable rules. Outline versioning: `outline_versions` table stores snapshots on save with optional labels; supports preview and restore.

**Asset Library** (`services/assets/`):
`assets_service.py` operates on the unified `assets` table via `AssetRepository`. `style_extractor/` extracts writing-style assets from uploaded references. Unified layer: `unified_asset_view.py` aggregates read-only data silos (assets, archives, threads, rules, relationships, projects) into a single asset DTO; `global_search_indexer.py` populates the unified-DB FTS tables (`tables/fts.py` + `tables/search.py`) for cross-silo search, with pluggable backends under `repositories/search_backends/` (`like_search`, `sqlite_search`, `postgres_search`); `ingestion_agent/` is an LLM agent that ingests free-form material into structured assets. Exposed via `api_fastapi/unified_assets.py` (facets, detail, global FTS search). `manuscript_adapter.py` maps manuscript blocks into the asset view.

**Agent Memory** (`services/agents/memory/`):
Episodic (short-term, limit=6) + Long-term (canon/candidate, limit=6). Promotable types: goal, preference, promise, relationship, strategy. Stores under `agent_memory_stores.py`, `episodic_store.py`, `long_term_store.py`.

**Agent Registry** (`services/agents/registry/`):
`agent_schema_registry.py` (BASE_AGENT_SCHEMA + character/organization/relationship extensions), `agent_template_registry.py` (tier-based sections: protagonist/major=8, supporting=5, minor=3).

**Agent Worldline** (`services/agents/worldline/`):
`worldline_agent_registry.py`, `character_agent_service.py`.

### Frontend (React 19 + TypeScript + Vite 6)

Under `frontend/src/`:

- **`pages/`** — Route entry points, one subfolder per page with `page.tsx` plus supporting view-models/panels:
  - `overview/` — seed upload + pipeline processing UI (`inline-workflow-stream`, `pipeline-visualization`, `seed-step-trace-panel`, `seed-task-timeline`, chapter map at `seed-pipeline-chapters.ts`).
  - `writer/` — Writer Workbench: `book-plan-panel`, `continuation-context-panel`, `forbidden-lexicon-panel`, `manuscript-drawer`, `manuscript-prose-view`, `manuscript-reading-pane`, `manuscript-toc-panel`/`manuscript-toc-sidebar`, `outline-view`, `preset-editor`.
  - `worldline/` — Worldline Workbench: `control-panel`, `director/`, `timeline`, `selection-panel`, `variable-lock-panel`, `simulation-roster`, `auto-task-panel`, `inspiration-panel`.
  - `story-graph/` — D3.js force-directed graph, `graph-build-console`, `world-overview-dashboard`, agent/archive template configurator, inspector.
  - `asset-library/` — Unified asset library page.
  - `character-console/`, `llm-facility/`, `guide/`.
- **`components/`** — Shared components: `archive-detail-view`, `archive-library-picker`, `archive-memory-panel`, `agent-progress-panel`, `agent-trace-panel`, `llm-activity-indicator`, `story-graph-inspector`, `story-graph-panel`, plus `ui/` (shadcn/ui primitives).
- **`api/`** — Domain API clients (`archive.ts`, `assets.ts`, `http.ts`, `llm.ts`, `novel.ts`, `project.ts`, `sse.ts`, `worldline.ts`, `writer-agent.ts`). SSE client in `sse.ts`.
- **`stores/`** — Zustand stores (`layout-store.ts`, `seed-upload-store.ts`).
- **`hooks/`**, **`lib/`**, **`types/`** — Shared hooks, utilities, and TS types.
- **`router.tsx`** — React Router 7 routes (lazy-loaded pages). Legacy `/archive-library` redirects to `/assets`.

Vite dev server proxies `/api` to FastAPI backend at `http://127.0.0.1:3888`. Port 3999 is `strictPort`. Tailwind CSS 4 via `@tailwindcss/vite`. Data layer: TanStack Query 5. UI primitives: Base UI + Radix + shadcn/ui. Forms: React Hook Form + Zod.

## Key Conventions

- **LLM configuration**: All LLM calls route through the "global facility panel" (now the `llm_channels` / `llm_models` / `llm_module_bindings` tables in the unified DB). Never use legacy single-group LLM env vars. Unbound modules raise errors — no env var fallback. The `llm_facility.sqlite3` / `archive_library.sqlite3` / `assets_library.sqlite3` names in `config.py` are legacy filename constants retained for compatibility; runtime services read from the unified DB.
- **Single world-line**: Single-world model only. Old multi-branch endpoints return `410`.
- **Memory tiers**: `canon` (confirmed) / `candidate` (pending review) / `experiment`. Writing pipelines only inject active `canon`. Worldline auto-evolution outputs go to `candidate`.
- **Persistence**: Unified SQLite DB at `backend/data/mirofish.db` (path from `DATABASE_URL`). Legacy per-project JSON artifacts in `backend/uploads/projects/` are being phased out; `project_artifacts` table mirrors them. Seed/graph/novel runtime reads have been switched to `project_artifacts` (Phase G G-2). Some reading paths (`story_memory.json`, `chapter_segments.json`, `chapter_continuity.json`, `narrative_archives.json`, `parallel_world_config.json`) still survive — consult the truth matrix before adding new JSON reads.
- **Schema lifecycle**: Only change schema via new alembic revisions under `backend/alembic/versions/`. Never edit applied revisions.
- **Repositories over raw SQL**: Services must call repositories in `app/repositories/`, not raw SQL. `get_engine()` in `app/database.py` is the shared engine.
- **File uploads**: Max 100 MB. Formats: PDF, MD, TXT.
- **Domain language**: Novel analysis terminology. Not social-media/sentiment-analysis.

## Reference Documentation

- [Agent Data Schema Reference](./docs/agent-data-schema-reference.md) — All agent data structures, LLM prompts, and parameter configurations.
- [Database Source-of-Truth Matrix](./docs/database/database-source-of-truth-matrix.md) — Per-domain DB vs legacy JSON status (updated per migration phase).
- [Database Unification Migration Plan](./docs/plans/2026-04-14-database-unification-migration-plan.md) — Master plan for phases C–H.
- [Remaining Phases Implementation Guide](./docs/plans/2026-04-17-remaining-phases-implementation-guide.md) — Detailed implementation guide for Phase D4/D11/E/F/G/H.
- [Outline Versioning Design](./docs/superpowers/specs/2026-04-05-outline-versioning-design.md) — Outline snapshot and version history feature spec.
- [FastAPI Route Manifest](./docs/fastapi-route-manifest.md) — Current REST endpoints.

## Environment Variables

See `.env.example`:
- `APP_PORT` (default 3888), `APP_HOST` (default 0.0.0.0), `APP_DEBUG` (default true — enables uvicorn reload)
- `DATABASE_URL` (default `sqlite:///./data/mirofish.db`)
- `LLM_REQUEST_TIMEOUT_SECONDS` (default 120)
- `ZEP_API_KEY` (optional, only for online graph construction)
- `NARRATIVE_DEFAULT_BRANCH_COUNT` (default 3), `NARRATIVE_DEFAULT_TIMELINE_STEPS` (default 12)
- `ADMIN_SECRET` (optional, for API key auth middleware)
