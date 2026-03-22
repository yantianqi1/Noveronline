# Global LLM Config Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 清理仓库中的 legacy LLM env 配置入口，确保所有 LLM 模块只依赖全局设施绑定，显式离线模式除外。

**Architecture:** 不改当前模块绑定架构，只补强约束。通过测试锁定“禁止 legacy env”，再删除示例配置、文档和测试残留，最后跑回归验证。

**Tech Stack:** Flask, Vue 3, pytest, node:test

---

### Task 1: Add Failing Regression Tests

**Files:**
- Create: `backend/tests/test_legacy_llm_config_cleanup.py`
- Modify: `backend/tests/test_async_seed_pipeline.py`
- Modify: `backend/tests/test_offline_novel_pipeline.py`
- Modify: `backend/tests/test_seed_continuity_artifacts.py`

**Step 1: Write the failing tests**

- Add a scan test that fails if runtime code references `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME`
- Remove obsolete test setup that mutates `Config.LLM_API_KEY`

**Step 2: Run tests to verify they fail**

Run: `cd /Users/项目/MiroFish-Novel/backend && ./.venv/bin/pytest tests/test_legacy_llm_config_cleanup.py tests/test_async_seed_pipeline.py tests/test_offline_novel_pipeline.py tests/test_seed_continuity_artifacts.py -q`

### Task 2: Remove Legacy Config Entrypoints

**Files:**
- Modify: `.env`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/CODEX_HANDOFF_GUIDE.md`

**Step 1: Remove old `LLM_*` env examples**

- Delete `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME`
- Keep runtime / Zep / narrative defaults only

**Step 2: Rewrite docs**

- State that LLM modules must be configured in the global facility panel
- Keep explicit offline mode wording

### Task 3: Verify End-to-End Expectations

**Files:**
- Modify: none

**Step 1: Run targeted backend tests**

Run: `cd /Users/项目/MiroFish-Novel/backend && ./.venv/bin/pytest tests/test_legacy_llm_config_cleanup.py tests/test_explicit_generation_modes.py tests/test_async_seed_pipeline.py tests/test_offline_novel_pipeline.py tests/test_seed_continuity_artifacts.py tests/test_llm_facility_api.py -q`

**Step 2: Run frontend verification**

Run: `cd /Users/项目/MiroFish-Novel/frontend && node --test tests/*.test.mjs`

**Step 3: Build frontend**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm run build`
