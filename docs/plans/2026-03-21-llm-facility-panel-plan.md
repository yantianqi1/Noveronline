# LLM Facility Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为项目增加 SQLite 驱动的 LLM 设施面板，支持管理 OpenAI 兼容渠道、同步模型列表，并把业务模块绑定到明确的“渠道 + 模型”组合。

**Architecture:** 后端新增 SQLite 存储层、设施服务层和统一 LLM 路由器；已有业务服务通过模块键解析客户端；前端新增设施面板页面，统一管理渠道、模型缓存和模块绑定。

**Tech Stack:** Flask, sqlite3, OpenAI Python SDK, Vue 3, Vite, pytest, node:test

---

### Task 1: Add Failing Backend Tests For LLM Facilities

**Files:**
- Create: `backend/tests/test_llm_facility_api.py`
- Modify: `backend/tests/test_explicit_generation_modes.py`

**Step 1: Write the failing tests**

```python
def test_llm_facility_supports_channel_sync_and_module_binding():
    ...

def test_story_ontology_requires_module_binding_when_llm_enabled():
    ...
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_llm_facility_api.py backend/tests/test_explicit_generation_modes.py -q`
Expected: FAIL because `/api/llm/*` endpoints and module-based routing do not exist yet

### Task 2: Implement SQLite LLM Facility Backend

**Files:**
- Create: `backend/app/services/llm_module_registry.py`
- Create: `backend/app/services/llm_storage.py`
- Create: `backend/app/services/llm_settings_service.py`
- Create: `backend/app/services/llm_router.py`
- Create: `backend/app/api/llm.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/__init__.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/utils/llm_client.py`

**Step 1: Add SQLite schema and CRUD helpers**

- Create database path under runtime uploads directory
- Implement channel/model/binding tables
- Add snapshot reads and write helpers

**Step 2: Add facility service and model sync**

- Create channel CRUD methods
- Sync models via OpenAI-compatible `models.list`
- Mask API keys in snapshot responses

**Step 3: Add unified router**

- Resolve `module_key -> channel + model`
- Build `LLMClient`
- Expose helpers to get bound model name for UI/progress

**Step 4: Add Flask API**

- Register `/api/llm`
- Add settings snapshot, channel CRUD, sync-models, module-binding endpoints

**Step 5: Run backend tests**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_llm_facility_api.py backend/tests/test_explicit_generation_modes.py -q`
Expected: PASS

### Task 3: Switch Existing LLM Services To Module Routing

**Files:**
- Modify: `backend/app/services/story_ontology_generator.py`
- Modify: `backend/app/services/local_block_fact_extractor.py`
- Modify: `backend/app/services/contextual_block_analyzer.py`
- Modify: `backend/app/services/narrative_entity_archivist.py`
- Modify: `backend/app/services/parallel_world_config_generator.py`
- Modify: `backend/app/services/seed_task_progress.py`

**Step 1: Route each business service through module keys**

- `story_ontology`
- `local_block_facts`
- `contextual_block_analysis`
- `narrative_archives`
- `parallel_world_config`

**Step 2: Remove env-based LLM selection**

- Stop reading `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME`
- Keep explicit failure behavior when `use_llm=True` and module binding missing

**Step 3: Update progress display**

- Seed task progress shows stage-specific model names when available

**Step 4: Run targeted backend tests**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_story_memory_pipeline.py backend/tests/test_async_seed_pipeline.py backend/tests/test_offline_novel_pipeline.py backend/tests/test_explicit_generation_modes.py backend/tests/test_llm_facility_api.py -q`
Expected: PASS

### Task 4: Add Frontend Facility Panel

**Files:**
- Create: `frontend/src/api/llm.js`
- Create: `frontend/src/views/LlmFacilityView.vue`
- Create: `frontend/tests/llm-facility-api.test.mjs`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/App.vue`

**Step 1: Add frontend API layer**

- Fetch settings snapshot
- Create/update/delete channels
- Sync models
- Save module bindings

**Step 2: Build facility panel**

- Render channels and cached models
- Support editing channel config
- Support module bindings

**Step 3: Add one frontend test for API path/state helpers**

- Verify request payload shaping or route helper behavior

**Step 4: Run frontend verification**

Run: `cd /Users/项目/MiroFish-Novel/frontend && node --test tests/llm-facility-api.test.mjs`
Expected: PASS

### Task 5: Run Final Verification

**Files:**
- Modify: none

**Step 1: Run backend test suite for touched areas**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_llm_client.py backend/tests/test_llm_facility_api.py backend/tests/test_explicit_generation_modes.py backend/tests/test_story_memory_pipeline.py backend/tests/test_async_seed_pipeline.py backend/tests/test_offline_novel_pipeline.py -q`
Expected: PASS

**Step 2: Compile backend**

Run: `/tmp/mirofish_novel_venv/bin/python -m compileall /Users/项目/MiroFish-Novel/backend/app /Users/项目/MiroFish-Novel/backend/tests`
Expected: PASS

**Step 3: Run frontend test**

Run: `cd /Users/项目/MiroFish-Novel/frontend && node --test tests/llm-facility-api.test.mjs`
Expected: PASS

**Step 4: Build frontend**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm run build`
Expected: PASS
