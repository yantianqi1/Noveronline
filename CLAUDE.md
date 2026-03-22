# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MiroFish-Novel is a multi-agent analysis platform for novel creation, plot prediction, relationship evolution, and parallel world simulation. It was migrated from the upstream `MiroFish` project (GitHub: `https://github.com/666ghj/MiroFish`, local: `/Users/项目/MiroFish`) but focuses on novel-specific features, not general sentiment analysis.

The product domain is: novel world-graph construction, character/faction/organization archive generation, relationship evolution analysis, parallel-world variable injection, plot trajectory simulation, and agent interaction.

## Commands

### Backend

```bash
cd backend
uv sync                    # Install Python dependencies
uv run python run.py       # Start Flask server on localhost:5101
```

### Frontend

```bash
cd frontend
npm install                # Install Node dependencies
npm run dev                # Start Vite dev server on localhost:3891
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

- **`api/`** — Flask blueprints exposing REST endpoints. Key blueprints: `project.py` (project CRUD, novel seed upload), `novel.py` (story analysis, archive generation), `worldline_session.py` + `worldline_interaction.py` (world-line lifecycle), `llm.py` (LLM facility panel), `archive.py` (archive library).
- **`services/`** — Business logic. Key services:
  - `novel_seed_analyzer.py` — Offline character/organization/relationship extraction from novel text
  - `story_ontology_generator.py` — Automatic ontology generation from uploaded novels
  - `narrative_entity_archivist.py` — Character/faction archive generation
  - `worldline_engine.py` — World-line simulation engine with file-system persistence
  - `character_agent_service.py` — Character dialogue service
  - `plot_inspiration_engine.py` — Plot inspiration generation
  - `llm_router.py` + `llm_module_registry.py` — LLM module binding and routing
  - `local_story_graph_builder.py` — Local graph construction (`story_graph.json` + `story_graph.sqlite3`)
- **`models/`** — Data models and persistence: `project.py` (ProjectManager), `task.py` (TaskManager), `worldline.py` (session/branch data models).
- **`utils/`** — `llm_client.py` (OpenAI-compatible wrapper), `file_parser.py` (PDF/TXT/MD parsing), `llm_json.py` (JSON response normalization), `retry.py`.

### Frontend (Vue 3 + Vite)

Under `frontend/src/`:

- **`views/`** — Page components for Overview, Guide, Archive Library, Story Graph, World-line, Character Console, LLM Facility
- **`api/`** — Domain-specific API clients (`project.js`, `novel.js`, `worldline.js`, `archive.js`, `llm.js`) with base HTTP config in `http.js`
- **`composables/`** — Vue composables for shared state
- **`components/`** — Reusable UI components

Vite dev server proxies `/api` requests to the Flask backend at `http://127.0.0.1:5101`.

### Data Flow (Main Pipeline)

1. Upload novel text → file parsing → project creation
2. Automatic ontology generation + offline seed analysis (character/organization/relationship extraction)
3. Entity archive generation
4. Parallel world configuration generation
5. World-line session creation with variable injection
6. Branch evolution, character dialogue, agent actions
7. Plot inspiration generation

## Key Conventions

- **LLM configuration**: All LLM calls go through the "global facility panel" (`llm_facility.sqlite3`) for channel/model/module binding. Never use legacy single-group LLM environment variables.
- **Offline mode**: Pass `use_llm=false` explicitly; unbound modules raise errors rather than falling back to env vars.
- **Graph construction** does not require `ZEP_API_KEY`; novel parsing, archives, world-lines, character dialogue, and plot inspiration all run on the local graph.
- **Persistence**: Projects stored in `backend/uploads/projects/`. SQLite3 used for LLM facility and archive library. World-line state persisted to filesystem.
- **File uploads**: Max 100 MB. Supported formats: PDF, MD, TXT, Markdown.
- **Restart after large changes**: Restart the full project after code changes exceeding ~50 lines.
- **Domain language**: This is a novel analysis tool. Avoid importing social-media/sentiment-analysis semantics from the upstream MiroFish project. Adapt borrowed code to novel-domain terminology before merging.

## Environment Variables

See `.env.example`. Key variables:
- `FLASK_PORT` (default 5101), `FLASK_HOST`, `FLASK_DEBUG`
- `LLM_REQUEST_TIMEOUT_SECONDS` (default 120)
- `ZEP_API_KEY` (only needed for online graph construction)
- `NARRATIVE_DEFAULT_BRANCH_COUNT` (default 3), `NARRATIVE_DEFAULT_TIMELINE_STEPS` (default 12)
