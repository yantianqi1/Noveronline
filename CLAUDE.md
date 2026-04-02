# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MiroFish-Novel is a multi-agent analysis platform for novel creation, plot prediction, relationship evolution, and parallel world simulation. Migrated from the upstream `MiroFish` project (GitHub: `https://github.com/666ghj/MiroFish`) but focused on novel-specific features, not general sentiment analysis.

Product domain: novel world-graph construction, character/faction/organization archive generation, relationship evolution analysis, parallel-world variable injection, plot trajectory simulation, writer workbench with multi-agent prose generation, and agent interaction.

## Commands

### Backend

```bash
cd backend
uv sync                    # Install Python dependencies
FLASK_PORT=3888 uv run python run.py   # Start Flask server on localhost:3888
```

如果 `uv` 不可用（如本机环境），用系统 Python 直接启动：

```bash
cd backend
FLASK_PORT=3888 python3 run.py
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
PYTHONPATH=$(pwd) pytest tests/test_worldline_engine.py tests/test_offline_novel_pipeline.py   # Key tests
PYTHONPATH=$(pwd) pytest tests/                                                                 # All tests
PYTHONPATH=$(pwd) pytest tests/test_some_file.py::test_function_name                            # Single test
```

## Architecture

### Backend (Python 3.11+ / Flask)

Four-layer structure under `backend/app/`:

- **`api/`** — Flask blueprints exposing REST endpoints. Key blueprints: `project.py` (project CRUD, novel seed upload), `novel.py` (story analysis, archive generation, chapter context, draft generation), `worldline_session.py` + `worldline_interaction.py` (world-line lifecycle), `writer_agent.py` (writer workbench: scenes, chapters, presets, streaming agent runs), `llm.py` (LLM facility panel), `archive.py` (archive library).
- **`services/`** — Business logic, organized into:
  - Core analysis: `novel_seed_analyzer.py` (offline character/organization/relationship extraction), `story_ontology_generator.py` (automatic ontology from novels), `narrative_entity_archivist.py` (character/faction archive generation)
  - World-line: `worldline_engine.py` (simulation engine with filesystem persistence), `worldline_runtime_service.py` (runtime operations)
  - Writer pipeline: `chapter_context_pack_builder.py` (Chapter Context Pack assembly), `archive_memory_review_service.py` (canon/candidate memory review), `writer_prompt_formatter.py` (prompt formatting from context + memory + style)
  - Draft agents (`services/agents/draft/`): Multi-agent prose generation pipeline — `orchestrator.py` coordinates `context_agent.py` → `memory_agent.py` → `style_agent.py` → `writer_agent.py` → `reviewer_agent.py`
  - Writer agent service (`services/writer_agent/`): Workbench persistence layer — `novel_db.py` (SQLite data layer for chapters/scenes/presets/sessions), `orchestrator.py` + `agent_loop.py` (agent decision loop with tool use), `chapter_service.py` / `scene_service.py` / `preset_service.py` (CRUD), `tools.py` + `tool_executors.py` (agent tool definitions and execution), `prompts.py` (prompt templates)
  - Other: `character_agent_service.py` (character dialogue), `plot_inspiration_engine.py` (plot inspiration), `llm_router.py` + `llm_module_registry.py` (LLM module binding/routing), `local_story_graph_builder.py` (local graph: `story_graph.json` + `story_graph.sqlite3`)
- **`models/`** — Data models and persistence: `project.py` (ProjectManager), `task.py` (TaskManager), `worldline.py` (session/branch data models).
- **`utils/`** — `llm_client.py` (OpenAI-compatible wrapper), `file_parser.py` (PDF/TXT/MD parsing), `llm_json.py` (JSON response normalization), `retry.py`.

### Frontend (Vue 3 + Vite)

Under `frontend/src/`:

- **`views/`** — Page components for Overview, Guide, Archive Library, Story Graph, World-line, Writer Workbench, Character Console, LLM Facility. The Writer Workbench (`WriterWorkbenchView.vue`) is the most complex view with project/chapter/POV selection, SSE streaming output, context inspector, and scene management. Sub-components in `views/writer/` handle scene list, scene editor, preset editor, and layout/state management.
- **`api/`** — Domain-specific API clients (`project.js`, `novel.js`, `worldline.js`, `archive.js`, `llm.js`, `writerAgent.js`) with base HTTP config in `http.js`. Writer agent client (`writerAgent.js`) handles SSE streaming for agent runs.
- **`composables/`** — Vue composables for shared state
- **`components/`** — Reusable UI components

Vite dev server proxies `/api` requests to the Flask backend at `http://127.0.0.1:5101`.

### Data Flow

**Main pipeline:** Upload novel text → file parsing → project creation → ontology generation + offline seed analysis → entity archive generation → world-line session with variable injection → branch evolution, character dialogue, agent actions → plot inspiration

**Writer pipeline:** Chapter Context Pack assembly (must_know / should_know / warnings / scene_candidates / writer_prompt_block) → memory review (canon/candidate/experiment tiers) → multi-agent draft generation (context → memory → style → writer → reviewer) via SSE streaming → scene management and compilation

### Key Distinction: Draft Agents vs Writer Agent Service

- **Draft agents** (`services/agents/draft/`) — The LLM reasoning pipeline: each agent handles one aspect of prose generation (context validation, memory preparation, style extraction, writing, reviewing). Coordinated by `orchestrator.py`.
- **Writer agent service** (`services/writer_agent/`) — The persistence and UX backend: manages chapters, scenes, presets, sessions via SQLite. Runs an agent loop with tool use for interactive writing assistance. Exposed via `/api/writer-agent` endpoints.

## Key Conventions

- **LLM configuration**: All LLM calls go through the "global facility panel" (`llm_facility.sqlite3`) for channel/model/module binding. Never use legacy single-group LLM environment variables.
- **Offline mode**: Pass `use_llm=false` explicitly; unbound modules raise errors rather than falling back to env vars.
- **Single world-line**: The project uses a single-world worldline model. Old multi-branch endpoints (`/branches`, `/comparison`) return `410`. All frontend/backend organized around `current_world`.
- **Memory tiers**: Long-term memory uses `canon / candidate / experiment` tiers. Default writing pipelines only inject active `canon`. Worldline auto-evolution outputs go to `candidate` for author review before promotion.
- **Graph construction** does not require `ZEP_API_KEY`; all core features run on the local graph.
- **Persistence**: Projects in `backend/uploads/projects/`. SQLite3 for LLM facility, archive library, and writer workbench data. World-line state on filesystem.
- **File uploads**: Max 100 MB. Supported formats: PDF, MD, TXT.
- **Restart after large changes**: Restart full project after code changes exceeding ~50 lines.
- **Domain language**: This is a novel analysis tool. Avoid importing social-media/sentiment-analysis semantics from the upstream MiroFish project. Adapt borrowed code to novel-domain terminology.

## Environment Variables

See `.env.example`. Key variables:
- `FLASK_PORT` (default 5101), `FLASK_HOST`, `FLASK_DEBUG`
- `LLM_REQUEST_TIMEOUT_SECONDS` (default 120)
- `ZEP_API_KEY` (only needed for online graph construction)
- `NARRATIVE_DEFAULT_BRANCH_COUNT` (default 3), `NARRATIVE_DEFAULT_TIMELINE_STEPS` (default 12)
