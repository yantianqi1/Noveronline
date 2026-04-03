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

- **`api/`** — Flask blueprints exposing REST endpoints. Key blueprints:
  - `project.py` (project CRUD, novel seed upload, task cancellation, step trace API)
  - `project_graph.py` (project graph query: `GET /<project_id>/graph`)
  - `novel.py` (story analysis, archive generation, chapter context, draft generation)
  - `novel_graph_defaults.py` (default graph entity types and entity type resolution helpers)
  - `worldline_session.py` + `worldline_interaction.py` (world-line lifecycle)
  - `worldline_auto_evolution.py` + `worldline_auto_evolution_sse.py` (auto-evolution task + SSE streaming)
  - `worldline_events.py` (event adopt/edit/query via WorldlineEventService)
  - `worldline_prepare.py` (session preparation + agent detail endpoints)
  - `worldline_support.py` (shared worldline dependencies: engine proxy, initialization, helpers)
  - `writer_agent.py` (writer workbench: scenes, chapters, presets, streaming agent runs)
  - `llm.py` (LLM facility panel)
  - `archive.py` (archive library)

- **`services/`** — Business logic, organized into:
  - **Seed pipeline (4-stage)**: `seed_extract_runner.py` (orchestrator), `seed_extract_task_service.py` (task service layer), `smart_novel_segmenter.py` (token-budget segmentation), `sequential_reader.py` (LLM sequential reading with running context), `reading_notes_manager.py` (3-tier notes: core_facts / relationship_graph / plot_state with arc/volume summaries), `character_agent_profile_generator.py` (concurrent profile generation for important characters), `seed_task_progress.py` (structured progress tracking with timeline events), `seed_pipeline_chapters.py` (4-chapter definitions: text_prep / deep_reading / integration / agent_build), `seed_task_callbacks.py` (task lifecycle callbacks), `seed_stage_settings.py` (stage configuration), `seed_stage_fallback_support.py` (fallback handling), `seed_llm_retry.py` / `seed_llm_normalizer_utils.py` / `seed_llm_payload_normalizer.py` (LLM output normalization and retry), `seed_line_protocol.py` (seed data protocol), `seed_analysis_aggregator.py` (aggregates seed analyses), `novel_seed_analyzer.py` (seed content analysis), `novel_chapter_segmenter.py` (chapter segmentation)
  - **Core analysis**: `story_ontology_generator.py` (automatic ontology from novels), `story_ontology_line_protocol.py` / `story_ontology_protocol_prompts.py` (ontology protocol and prompts), `narrative_entity_archivist.py` (character/faction archive generation), `entity_resolution_service.py` (entity disambiguation with line protocol and prompts), `organization_candidate_filter.py` (organization candidate filtering)
  - **Contextual block analysis**: `analysis_block_builder.py`, `contextual_block_analyzer.py`, `contextual_block_line_protocol.py`, `contextual_block_protocol_prompts.py` — block-level content analysis pipeline
  - **Local block facts**: `local_block_fact_extractor.py`, `local_block_fact_line_protocol.py`, `local_block_fact_prompts.py`, `local_block_fact_protocol_prompts.py`, `local_block_fact_support.py` — fact extraction from text blocks
  - **Chapter cards**: `chapter_card_generator.py`, `chapter_card_fallback_builder.py`, `chapter_card_line_protocol.py`, `chapter_card_protocol_prompts.py`, `chapter_meta_service.py`, `chapter_meta_storage.py` — structured chapter documentation with metadata persistence
  - **Continuity & consistency**: `chapter_continuity_service.py` (chapter continuity checking), `continuity_consistency_auditor.py` (plot consistency auditing), `canon_history_retriever.py` (canonical history retrieval)
  - **Step tracing**: `step_trace_context.py` (contextvars-based trace context), `step_trace_writer.py` (trace bundle file I/O) — captures LLM prompts/responses per step for UI inspection
  - **Graph building**: `graph_builder.py` (story graph construction orchestrator), `graph_builder_types.py` (graph type definitions), `graph_builder_worker.py` (concurrent graph building), `local_story_graph_builder.py` (local graph: `story_graph.json` + `story_graph.sqlite3`), `local_story_graph_models.py` (GraphNode, GraphEdge, GraphSnapshot data models), `local_story_graph_storage.py` (SQLite persistence), `local_story_graph_support.py` (helper utilities), `reading_notes_graph_adapter.py` (bridges reading notes to graph format), `story_memory_builder.py` (builds story memory blocks including relationship ledger), `story_context_source_builder.py` (context source assembly)
  - **Archive system**: `archive_candidate_builder.py` (builds archive candidates from seed/graph), `archive_library_service.py` (global archive library CRUD with SQLite), `archive_library_storage.py` (archive library persistence), `archive_memory_review_service.py` (canon/candidate memory review)
  - **World-line**: `worldline_engine.py` (simulation engine with filesystem persistence), `worldline_runtime_service.py` (runtime operations), `worldline_runtime_storage.py` (runtime state storage), `worldline_engine_factory.py` (engine creation factory), `worldline_single_world.py` (single-world model with branch constants), `worldline_branch_service.py` / `worldline_branch_support.py` / `worldline_branch_comparison.py` (branch lifecycle and comparison), `worldline_event_service.py` (event management), `worldline_prepare_service.py` / `worldline_prepare_storage.py` (session preparation), `worldline_source_loader.py` (source data loading), `worldline_auto_action_service.py` (auto-action execution), `worldline_auto_evolution_support.py` / `worldline_auto_evolution_task_service.py` (auto-evolution orchestration)
  - **Anchor points & timeline**: `anchor_point_builder.py`, `anchor_point_line_protocol.py`, `anchor_point_prompts.py`, `anchor_point_protocol_prompts.py` (worldline anchor point generation), `skeleton_timeline_builder.py` (skeleton timeline construction), `sentence_atlas_builder.py` (sentence atlas building)
  - **Writer pipeline**: `chapter_context_pack_builder.py` (Chapter Context Pack assembly), `chapter_context_ranker.py` (context relevance ranking), `writer_prompt_formatter.py` (prompt formatting from context + memory + style), `prompt_budget_manager.py` (token budget management for prompts)
  - **Draft agents** (`services/agents/draft/`): Multi-agent prose generation pipeline — `orchestrator.py` coordinates `context_agent.py` → `memory_agent.py` → `style_agent.py` → `writer_agent.py` → `reviewer_agent.py`, with `orchestration_support.py` and `review_support.py`
  - **Agent memory system** (`services/agents/memory/`): `agent_memory_service.py` (persistent agent memory orchestration with episodic/long-term stores, dialogue recording, memory promotion), `agent_memory_stores.py` (EpisodicMemoryStore + LongTermMemoryStore), `agent_memory_writer_summary.py` (writer memory summary builder), `episodic_store.py` (short-term episodic memory), `long_term_store.py` (long-term canonical memory), `store_support.py` (memory store helpers). Supports memory promotion types: goal/preference/promise/relationship/strategy. Limits: SESSION_LIMIT=6, LONG_TERM_LIMIT=6.
  - **Agent registry** (`services/agents/registry/`): `agent_schema_registry.py` (standardized agent field definitions with BASE_AGENT_SCHEMA and extensions for character/organization/relationship), `agent_template_registry.py` (template registry with tier-based sections: protagonist/major get 8 sections, supporting get 5, minor get 3)
  - **Worldline agents** (`services/agents/worldline/`): `character_agent_service.py` (character dialogue agent), `worldline_agent_registry.py` (worldline agent registry)
  - **Writer agent service** (`services/writer_agent/`): Workbench persistence layer — `novel_db.py` (SQLite data layer for chapters/scenes/presets/sessions), `orchestrator.py` + `agent_loop.py` (agent decision loop with tool use), `chapter_service.py` / `scene_service.py` / `preset_service.py` (CRUD), `tools.py` + `tool_executors.py` (agent tool definitions and execution), `prompts.py` (prompt templates)
  - **LLM infrastructure**: `llm_router.py` + `llm_module_registry.py` (LLM module binding/routing), `llm_activity_tracker.py` (LLM API activity tracking), `llm_concurrency_service.py` (concurrent LLM call management), `llm_settings_service.py` (settings management), `llm_storage.py` (persistent LLM facility database)
  - **Other**: `character_agent_service.py` (character dialogue), `plot_inspiration_engine.py` (plot inspiration), `influence_propagation.py` (influence spread modeling with importance tier weights), `genre_plugin.py` (genre-specific customization), `parallel_world_config_generator.py` (parallel world configuration), `world_state_store.py` (persistent world state), `text_processor.py` (text preprocessing), `memory_subject_utils.py` (memory subject normalization), `zep_entity_reader.py` / `zep_entity_reader_processing.py` / `zep_entity_reader_types.py` (Zep graph integration)

- **`models/`** — Data models and persistence: `project.py` (ProjectManager), `project_types.py` (ProjectStatus enum: CREATED/SEED_PROCESSING/ONTOLOGY_GENERATED/GRAPH_BUILDING/GRAPH_COMPLETED/FAILED), `task.py` (TaskManager with cancellation support), `task_storage.py` (task run state SQLite persistence with indexes), `worldline.py` (session/branch data models).

- **`utils/`** — `llm_client.py` (OpenAI-compatible wrapper with 3-attempt JSON retry and step trace capture), `file_parser.py` (PDF/TXT/MD parsing), `llm_json.py` (5-level JSON parsing fallback), `llm_transient.py` (transient error detection: retryable status codes 408/429/500/502/503/504), `task_file_logger.py` (per-task file logging), `logger.py` (unified logging with file rotation and UTF-8 console support), `upstream_error_formatter.py` (HTML error formatting for upstream service errors), `retry.py`.

- **`config.py`** — Central configuration loading from `.env`, defines Config class with database filenames (`llm_facility.sqlite3`, `archive_library.sqlite3`), upload/chunk settings.

### Frontend (Vue 3 + Vite)

Under `frontend/src/`:

- **`views/`** — Page components for Overview, Guide, Archive Library, Story Graph, World-line, Writer Workbench, Character Console, LLM Facility.
  - The Overview page (`OverviewView.vue`) has two layout modes: idle (command grid + recent projects + upload/analysis panels) and processing (hero + 2-column grid with workflow stream + sticky focus card sidebar). Sub-components: `OverviewHeroPanel.vue`, `OverviewNextActionsPanel.vue`, `OverviewRecentProjects.vue`, `OverviewTaskFocusCard.vue`, `SeedAnalysisPanel.vue`, `SeedUploadFormFields.vue`.
  - The Writer Workbench (`WriterWorkbenchView.vue`) is the most complex view with project/chapter/POV selection, SSE streaming output, context inspector, and scene management. Sub-components in `views/writer/` handle scene list, scene editor, preset editor, and layout/state management.
  - The Character Console has sub-components: `SessionCommandPanel`, `WorldlineAgentRoster`, `AgentHistoryPanel`, `AgentDetailPanel`, `AgentDialoguePanel`, `InteractionLogPanel`, with `agentDetailPresentation.js` for agent data formatting.
  - The LLM Facility view has sub-components: `LlmChannelPanel.vue`, `LlmModuleBindingsPanel.vue`, `llmModuleBindingDrafts.js`.

- **`views/overview/`** — Seed processing UI: `InlineWorkflowStream.vue` (orchestrator), `InlineStreamSummaryBar.vue` (per-chapter progress), `InlineStreamChatContent.vue` (expandable chapter→step hierarchy), `SeedDrawerStepItem.vue` + `SeedDrawerStepDetail.vue` (step trace viewer with full prompt/response), `SeedDrawerChapterCard.vue` + `SeedDrawerSummaryBar.vue` (chapter-level progress cards), `PipelineVisualization.vue` (6-stage rail with sliding window), `seedPipelineChapters.js` (chapter definitions synced with backend), `seedUploadTaskView.js` (stage progress interpolation and timeline normalization), `seedProjectId.js` (project ID state), `overviewWorkbenchState.js` (overview workbench state management). Task detail components: `SeedTaskLlmCard`, `SeedTaskTimeline`, `SeedTaskLogPanel`, `SeedTaskStageCard`.

- **`views/story-graph/`** — D3.js-based story graph visualization: `storyGraphRenderer.js` (D3 force simulation with zoom/pan), `storyGraphRendererElements.js` (SVG node/edge creation, graduated selection highlighting with neighbor strength-based opacity/size/glow), `storyGraphRenderModel.js` (data normalization, edge pair/curve calculation, neighbor strength map computation), `storyGraphViewModel.js` (type filtering, degree-based label visibility), `graphBuildTaskPoller.js` (build task polling), `AgentTemplateConfigurator.vue` (archive template tier configuration), `archiveTemplateLabels.js` (template label utilities).

- **`views/shared/`** — Shared view state/layout utilities: `worldlineSelectorState.js`, `archiveLibraryLayout.js`, `archiveLibraryPickerLayout.js`, `worldlineWorkbenchLayout.js`.

- **`api/`** — Domain-specific API clients (`project.js`, `novel.js`, `worldline.js`, `archive.js`, `llm.js`, `writerAgent.js`) with base HTTP config in `http.js` and `apiBase.js`. SSE streaming client in `sse.js`. Writer agent client (`writerAgent.js`) handles SSE streaming for agent runs.

- **`composables/`** — Vue composables for shared state: `useSeedUpload.js` (task polling at 1200ms), `seedUploadTaskState.js` (state normalization), `useSeedDrawerCollapse.js` (auto-collapse state machine for step/chapter items), `useProjectCatalog.js` (project list state), `useLlmActivity.js` (LLM activity monitoring), `useWorldlineWorkbenchLayout.js` (worldline layout state), `useArchiveLibraryLayout.js` (archive library layout state).

- **`components/`** — Reusable UI components: `StoryGraphPanel.vue` (main graph canvas with D3 renderer, type filtering, legend), `StoryGraphInspector.vue` (node/edge detail panel with async archive loading and collapsible sections), `InspectorSection.vue` (collapsible card for archive data display), `archiveDetailSections.js` (archive section formatting helper), `ArchiveLibraryPicker.vue` / `ArchiveLibraryDetailCard.vue` / `ArchiveLibraryGridItem.vue` (archive library browsing UI), `AgentProgressPanel.vue` (background task progress), `LlmActivityIndicator.vue` (LLM call status indicator).

- **`utils/`** — `chineseDisplay.js` (Chinese text display utilities).

Vite dev server proxies `/api` requests to the Flask backend at `http://127.0.0.1:3888`.

### Seed Pipeline (4-Stage Architecture)

The seed extraction pipeline uses a 4-stage LLM-driven sequential reading model:

1. **Text Preparation** (`extract_text` → `smart_segmentation`): Parse uploaded files, segment chapters into reading segments respecting token budgets (default 50k tokens/segment)
2. **Sequential Deep Reading** (`sequential_reading`): LLM reads segments sequentially maintaining running context. Produces per-segment reading notes (characters, organizations, relationships, world rules, plot threads). Generates arc summaries every 5 segments and volume summaries for long novels.
3. **Global Integration** (`global_integration` → `ontology`): Aggregates reading notes into `seed_analysis.json`, generates story ontology (entity types, edge types, story focus dimensions)
4. **Character Agent Profiles** (`agent_profiles`): Generates structured agent profiles for important characters (>= 2 segment appearances) with personality, speech patterns, relationships, capabilities, knowledge boundaries, motivations

The pipeline tracks progress via `SeedTaskProgressTracker` which emits structured timeline events with step-level trace capture. Each step's LLM prompts and responses are recorded in trace bundles on disk (`task_traces/<task_id>/steps/<step_id>.json`) and viewable in the frontend.

Frontend chapter mapping is defined in `frontend/src/views/overview/seedPipelineChapters.js` (must stay in sync with `backend/app/services/seed_pipeline_chapters.py`). Four UI chapters: 文本准备 / 深度阅读 / 全局整合 / 角色构建.

### Graph Building Pipeline

After seed analysis, the graph building pipeline constructs a local story graph:

1. **Reading notes adaptation** (`reading_notes_graph_adapter.py`): Bridges seed pipeline output (reading notes) into graph-compatible format
2. **Story memory construction** (`story_memory_builder.py`): Builds story memory blocks including relationship ledger tracking relationship evolution across narrative blocks
3. **Graph construction** (`graph_builder.py` → `graph_builder_worker.py` → `local_story_graph_builder.py`): Concurrent entity extraction and edge building. Edge types: ALLIED_WITH, CONFLICTS_WITH, PARTICIPATES_IN, LOCATED_IN, POSSESSES, OBEYS_RULE, etc.
4. **Persistence** (`local_story_graph_storage.py`): Dual persistence to `story_graph.json` + `story_graph.sqlite3`

Graph nodes carry `importance_tier` (protagonist/major/supporting/minor), aliases, and evidence refs. Edges carry `weight` (occurrence count) reflecting relationship depth.

### Archive System

Archives are structured entity profiles generated from graph data:

1. **Candidate building** (`archive_candidate_builder.py`): Extracts candidates from seed analysis or graph entities
2. **Entity archiving** (`narrative_entity_archivist.py`): Generates `NarrativeEntityArchive` with template-based sections varying by importance tier and agent kind (character/organization/relationship)
3. **Archive library** (`archive_library_service.py`): Global archive persistence with search, filtering, and reindexing via SQLite
4. **Memory review** (`archive_memory_review_service.py`): Canon/candidate/experiment memory tier management with adopt/reject workflow

Template sections by tier: protagonist/major get identity/motivation/tension/relationship/behavior/state/risk/private (8 sections); supporting get identity/motivation/tension/relationship/state (5 sections); minor get identity/state/summary (3 sections).

### Data Flow

**Seed pipeline:** Upload novel text → file parsing → smart segmentation → sequential LLM reading with running notes → global integration (seed_analysis.json) → ontology generation → character agent profile generation

**Graph pipeline:** Seed analysis → reading notes adaptation → story memory building → concurrent graph construction → local graph persistence (JSON + SQLite) → archive candidate building → entity archiving → archive library indexing

**Post-seed:** Entity archive generation → world-line session preparation → anchor point building → skeleton timeline → auto-evolution with SSE streaming → event management → character dialogue → plot inspiration

**Writer pipeline:** Chapter Context Pack assembly (must_know / should_know / warnings / scene_candidates / writer_prompt_block) → memory review (canon/candidate/experiment tiers) → multi-agent draft generation (context → memory → style → writer → reviewer) via SSE streaming → scene management and compilation

### Key Distinction: Draft Agents vs Writer Agent Service

- **Draft agents** (`services/agents/draft/`) — The LLM reasoning pipeline: each agent handles one aspect of prose generation (context validation, memory preparation, style extraction, writing, reviewing). Coordinated by `orchestrator.py` with `orchestration_support.py` and `review_support.py`.
- **Writer agent service** (`services/writer_agent/`) — The persistence and UX backend: manages chapters, scenes, presets, sessions via SQLite. Runs an agent loop with tool use for interactive writing assistance. Exposed via `/api/writer-agent` endpoints.
- **Agent memory system** (`services/agents/memory/`) — Persistent memory for agents: episodic (short-term dialogue) and long-term (promoted canonical memories). Memory types: goal, preference, promise, relationship, strategy.

### Story Graph Visualization

The frontend story graph uses D3.js v7 force-directed layout:

- **Force simulation**: charge=-400, collide=50, center gravity with x/y forces
- **Node rendering**: Circles colored by entity type (10 types: character/organization/faction/group/artifact/knowledgeitem/plotevent/location/rulesystem/unknown). Node labels truncated to 8 chars, visibility controlled by degree-based highlighting (top 18 nodes by connection count).
- **Edge rendering**: Curved paths for multi-edge pairs, self-loop arcs, edge labels with background rects
- **Selection highlighting**: Clicking a node triggers graduated neighbor highlighting — neighbor nodes scale (10-16px radius) and glow proportional to relationship weight (summed edge weights, normalized to [0,1]). Non-adjacent nodes dim to 0.2 opacity, non-adjacent edges to 0.15. Selected node gets pink (#E91E63) stroke + glow.
- **Node inspector**: Async archive loading — clicking a node fetches archive data from the library API, displays identity/motivation/tension/relationship/behavior/state/risk/private sections in collapsible cards. Falls back to summary when no archive exists.
- **Type filtering**: Toggle entity types on/off. Default visible: character, organization, faction, group.

## Key Conventions

- **LLM configuration**: All LLM calls go through the "global facility panel" (`llm_facility.sqlite3`) for channel/model/module binding. Never use legacy single-group LLM environment variables. LLM activity tracking, concurrency management, and settings are centralized in dedicated services.
- **Offline mode**: Pass `use_llm=false` explicitly; unbound modules raise errors rather than falling back to env vars.
- **Single world-line**: The project uses a single-world worldline model. Old multi-branch endpoints (`/branches`, `/comparison`) return `410`. All frontend/backend organized around `current_world`.
- **Memory tiers**: Long-term memory uses `canon / candidate / experiment` tiers. Default writing pipelines only inject active `canon`. Worldline auto-evolution outputs go to `candidate` for author review before promotion.
- **Agent memory**: Agent memory uses episodic (short-term, SESSION_LIMIT=6) and long-term (canonical, LONG_TERM_LIMIT=6) stores with memory promotion for goal/preference/promise/relationship/strategy types.
- **Graph construction** does not require `ZEP_API_KEY`; all core features run on the local graph. Edges carry `weight` (occurrence count) used for visualization intensity.
- **Persistence**: Projects in `backend/uploads/projects/`. SQLite3 for LLM facility, archive library, task storage, chapter metadata, and writer workbench data. World-line state on filesystem.
- **File uploads**: Max 100 MB. Supported formats: PDF, MD, TXT.
- **Restart after large changes**: Restart full project after code changes exceeding ~50 lines.
- **Domain language**: This is a novel analysis tool. Avoid importing social-media/sentiment-analysis semantics from the upstream MiroFish project. Adapt borrowed code to novel-domain terminology.
- **Project status lifecycle**: CREATED → SEED_PROCESSING → ONTOLOGY_GENERATED → GRAPH_BUILDING → GRAPH_COMPLETED (or FAILED at any stage).

## Environment Variables

See `.env.example`. Key variables:
- `FLASK_PORT` (default 3888), `FLASK_HOST`, `FLASK_DEBUG`
- `LLM_REQUEST_TIMEOUT_SECONDS` (default 120)
- `ZEP_API_KEY` (only needed for online graph construction)
- `NARRATIVE_DEFAULT_BRANCH_COUNT` (default 3), `NARRATIVE_DEFAULT_TIMELINE_STEPS` (default 12)
