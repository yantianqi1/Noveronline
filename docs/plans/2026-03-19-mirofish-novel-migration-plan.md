# MiroFish-Novel Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a clean novel-focused repository that migrates the strongest reusable engine pieces from MiroFish and exposes the first useful backend APIs for story analysis.

**Architecture:** Backend-first migration. Preserve file parsing, project persistence, graph construction, entity reading, and LLM wrappers. Replace old social-media semantics with novel-specific ontology, entity archives, and parallel-world configuration.

**Tech Stack:** Flask, OpenAI-compatible LLM, Zep, file-system persistence, Python 3.11+

---

### Task 1: Repository Bootstrap

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `backend/pyproject.toml`
- Create: `backend/run.py`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`

**Steps:**
1. Create the new repository root and initialize git.
2. Add the environment template and root README.
3. Add backend package metadata and run entry.
4. Verify file paths and imports are coherent.

### Task 2: Migrate Reusable Foundation Modules

**Files:**
- Copy: `backend/app/utils/file_parser.py`
- Copy: `backend/app/utils/llm_client.py`
- Copy: `backend/app/utils/logger.py`
- Copy: `backend/app/utils/retry.py`
- Copy: `backend/app/utils/zep_paging.py`
- Copy: `backend/app/models/project.py`
- Copy: `backend/app/models/task.py`
- Copy: `backend/app/services/text_processor.py`
- Copy: `backend/app/services/graph_builder.py`
- Copy: `backend/app/services/zep_entity_reader.py`
- Copy: `backend/app/services/zep_tools.py`

**Steps:**
1. Copy only the reusable backend foundation modules.
2. Keep imports aligned with the new repo layout.
3. Patch obvious naming mismatches where needed.

### Task 3: Replace Domain Semantics

**Files:**
- Create: `backend/app/services/story_ontology_generator.py`
- Create: `backend/app/services/narrative_entity_archivist.py`
- Create: `backend/app/services/parallel_world_config_generator.py`
- Modify: `backend/app/models/project.py`

**Steps:**
1. Create a novel-specific ontology generator.
2. Create a narrative archive generator for characters, factions, and organizations.
3. Create a parallel-world configuration generator.
4. Add `analysis_goal` compatibility on the project model.

### Task 4: Expose New APIs

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/project.py`
- Create: `backend/app/api/novel.py`

**Steps:**
1. Add project upload and ontology generation API.
2. Add graph build API and task query API.
3. Add archive generation API.
4. Add parallel-world config API.

### Task 5: Codex Handoff Docs

**Files:**
- Create: `docs/CODEX_HANDOFF_GUIDE.md`
- Create: `docs/plans/2026-03-19-mirofish-novel-design.md`
- Create: `docs/plans/2026-03-19-mirofish-novel-migration-plan.md`

**Steps:**
1. Describe the new strategic direction.
2. Describe what was migrated vs. intentionally left behind.
3. Define the next execution priorities for Codex.

### Task 6: Next Migration Queue

**Files:**
- Future modify: `backend/app/services/*`
- Future create: `frontend/*`

**Steps:**
1. Bring in worldline simulation state storage.
2. Design agent action schema for narrative evolution.
3. Build the front-end author workbench.
4. Rebuild report generation for plot-development insight.
