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
APP_PORT=3888 uv run python run.py     # Start FastAPI server on localhost:3888
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
npm run dev -- --port 3999 # Start Vite dev server on localhost:3999
npm run build              # Production build (also used as frontend validation)
```

### Tests

```bash
cd backend
PYTHONPATH=$(pwd) pytest tests/                                    # All tests
PYTHONPATH=$(pwd) pytest tests/test_worldline_engine.py            # Single file
PYTHONPATH=$(pwd) pytest tests/test_some_file.py::test_func_name   # Single test
```

## Architecture

### Backend (Python 3.11+ / Flask)

Four-layer structure under `backend/app/`:

- **`api/`** — Flask blueprints (REST endpoints). Key: `project.py`, `writer_agent.py`, `worldline_session.py`, `worldline_prepare.py`, `archive.py`, `llm.py`, `novel.py`, `assets.py`, `unified_assets.py`.
- **`services/`** — Business logic. Major subsystems described below.
- **`models/`** — Data models: `project.py` (ProjectManager), `task.py` (TaskManager with cancellation), `worldline.py` (session/branch models). Project status lifecycle: CREATED → SEED_PROCESSING → ONTOLOGY_GENERATED → GRAPH_BUILDING → GRAPH_COMPLETED (or FAILED).
- **`utils/`** — `llm_client.py` (OpenAI-compatible wrapper with JSON retry + step trace), `file_parser.py`, `llm_json.py` (5-level JSON fallback), `logger.py`.
- **`config.py`** — Central config from `.env`. Database filenames: `llm_facility.sqlite3`, `archive_library.sqlite3`.

### Key Backend Subsystems

**Seed Pipeline (4-stage)**:
Upload → `smart_novel_segmenter` → `sequential_reader` (LLM sequential reading with arc/volume summaries) → `seed_analysis_aggregator` + `story_ontology_generator` → `character_agent_profile_generator`. Progress tracked via `SeedTaskProgressTracker`. Frontend chapter mapping in `seedPipelineChapters.js` must stay in sync with `seed_pipeline_chapters.py`.

**Graph Building**:
`reading_notes_graph_adapter` → `story_memory_builder` → `graph_builder` (concurrent) → `local_story_graph_storage` (JSON + SQLite). Nodes carry `importance_tier`, edges carry `weight`.

**Archive System**:
`archive_candidate_builder` → `narrative_entity_archivist` (LLM, template sections by tier) → `archive_library_service` (SQLite). Memory review: canon/candidate/experiment tiers.

**Worldline Engine**:
`worldline_engine` (filesystem persistence, single-world model) → `worldline_prepare_service` (session setup) → `worldline_agent_registry` (agent roster) → `character_agent_service` (dialogue/action) → auto-evolution with SSE.

**Writer Agent Service** (`services/writer_agent/`):
`novel_db.py` (SQLite: chapters/scenes/presets/sessions/manuscripts/outline_versions + entity association tables) → `retrieval_planner.py` (lightweight LLM pre-pass that drafts a `<retrieval_plan>` of tools to call before writing, injected into the orchestrator user message) → `orchestrator.py` + `agent_loop.py` (agent decision loop with tools) → modular `prompts/` subpackage (5 writer modules + reviewer module, assembled per task) → `tools.py` + `tool_executors.py` (write_prose, compile_manuscript, query_entity, manage_entity, manage_thread, manage_world_rule, manage_relationship, etc.) → `manuscript_service.py` + `manuscript_context_builder.py`. Task types: `write_scene`, `continue`, `outline`. World data update endpoint (`/api/writer-agent/world-update`) runs agent loop to incrementally update entities/threads/rules after prose is committed. Entity association tables (`thread_entity_links`, `rule_entity_links`) link plot threads and world rules to entities; `query_entity` returns enriched context including associated threads and applicable rules. Outline versioning: `outline_versions` table stores snapshots on save with optional labels; supports preview and restore.

**Asset Library** (`services/assets/`):
`assets_service.py` (per-project asset CRUD on `assets_library.sqlite3`) + `style_extractor` (extracts writing-style assets from uploaded references). New unified layer: `unified_asset_view.py` aggregates 6 read-only data silos (assets, archives, threads, rules, relationships, projects) into a single asset DTO; `global_search_indexer.py` mirrors all searchable entries into `backend/uploads/system/global_search.sqlite3` with an FTS5 trigram virtual table for cross-silo search; `ingestion_agent/` is an LLM agent that ingests free-form material into structured assets. Exposed via `api/unified_assets.py` (facets, detail, global FTS search).

**Agent Memory** (`services/agents/memory/`):
Episodic (short-term, limit=6) + Long-term (canon/candidate, limit=6). Promotable types: goal, preference, promise, relationship, strategy.

**Agent Registry** (`services/agents/registry/`):
`agent_schema_registry.py` (BASE_AGENT_SCHEMA + character/organization/relationship extensions), `agent_template_registry.py` (tier-based sections: protagonist/major=8, supporting=5, minor=3).

### Frontend (Vue 3 + Vite)

Under `frontend/src/`:

- **`views/`** — Pages: Overview (seed upload + processing), Writer Workbench, Worldline Workbench, Archive Library, Story Graph, Character Console, LLM Facility.
- **`views/writer/`** — Writer sub-components: SceneEditor, ManuscriptDrawer, ManuscriptReadingPane, ManuscriptTocPanel, ContinuationContextPanel.
- **`views/overview/`** — Seed processing UI: InlineWorkflowStream, PipelineVisualization, step trace viewer.
- **`views/story-graph/`** — D3.js force-directed graph with type filtering, graduated highlighting, node inspector with async archive loading. Toolbar-based layout (no sidebar).
- **`api/`** — Domain API clients (project, novel, worldline, archive, llm, writerAgent). SSE client in `sse.js`.
- **`composables/`** — Shared state composables (seed upload, project catalog, LLM activity, layout state).

Vite dev server proxies `/api` to Flask backend at `http://127.0.0.1:3888`.

## Key Conventions

- **LLM configuration**: All LLM calls route through the "global facility panel" (`llm_facility.sqlite3`). Never use legacy single-group LLM env vars. Unbound modules raise errors — no env var fallback.
- **Single world-line**: Single-world model only. Old multi-branch endpoints return `410`.
- **Memory tiers**: `canon` (confirmed) / `candidate` (pending review) / `experiment`. Writing pipelines only inject active `canon`. Worldline auto-evolution outputs go to `candidate`.
- **Persistence**: Projects in `backend/uploads/projects/`. SQLite3 for LLM facility, archive library, task storage, chapter metadata, writer workbench. Worldline state on filesystem.
- **File uploads**: Max 100 MB. Formats: PDF, MD, TXT.
- **Domain language**: Novel analysis terminology. Not social-media/sentiment-analysis.

## Reference Documentation

- [Agent Data Schema Reference](./docs/agent-data-schema-reference.md) — All agent data structures, LLM prompts, and parameter configurations.
- [Outline Versioning Design](./docs/superpowers/specs/2026-04-05-outline-versioning-design.md) — Outline snapshot and version history feature spec.

## Environment Variables

See `.env.example`:
- `APP_PORT` (default 3888), `APP_HOST`, `APP_DEBUG`
- `LLM_REQUEST_TIMEOUT_SECONDS` (default 120)
- `ZEP_API_KEY` (optional, only for online graph construction)
- `NARRATIVE_DEFAULT_BRANCH_COUNT` (default 3), `NARRATIVE_DEFAULT_TIMELINE_STEPS` (default 12)
