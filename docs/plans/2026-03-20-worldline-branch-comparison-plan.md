# Worldline Branch Comparison Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为世界线工作台补上平行世界分支对比能力。

**Architecture:** 后端新增 `worldline_branch_comparison` 服务，从已有 session/branch 状态派生对比摘要，并通过 comparison API 暴露；前端新增对比分支卡片面板，在不改动现有时间轴主链的前提下展示多分支差异。

**Tech Stack:** Flask, Python dataclasses, Vue 3, Vite, pytest

---

### Task 1: Add Failing Backend Tests

**Files:**
- Modify: `backend/tests/test_worldline_engine.py`

**Step 1: Write the failing test**

```python
def test_branch_comparison_returns_latest_event_and_pending_items():
    ...

def test_branch_comparison_can_filter_branch_ids():
    ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_worldline_engine.py -q`
Expected: FAIL because comparison service and API support do not exist yet

### Task 2: Implement Branch Comparison Service

**Files:**
- Create: `backend/app/services/worldline_branch_comparison.py`
- Modify: `backend/app/services/worldline_engine.py`
- Modify: `backend/app/api/worldline_session.py`

**Step 1: Implement summary helpers**

- 按 branch 派生最新事件、关键角色状态、关键组织状态
- 汇总关系变化与 pending 摘要
- 输出 session 级 comparison axes

**Step 2: Extend engine**

- 新增 comparison 查询方法
- 支持 `branch_ids` 过滤

**Step 3: Add API endpoint**

- `GET /api/worldline/session/<session_id>/comparison`

**Step 4: Run tests**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_worldline_engine.py -q`
Expected: PASS

### Task 3: Add Frontend Comparison Panel

**Files:**
- Create: `frontend/src/views/worldline/WorldlineBranchComparison.vue`
- Modify: `frontend/src/api/worldline.js`
- Modify: `frontend/src/views/WorldlineWorkbenchView.vue`

**Step 1: Add frontend API wrapper**

- Add `getWorldlineComparison(sessionId, branchIds?)`

**Step 2: Build comparison component**

- 展示分支卡片
- 渲染最新事件、关键状态、关系变化、待处理事项
- 空状态可读

**Step 3: Integrate into workbench**

- 会话创建后自动加载 comparison
- 分支刷新、推进、变量注入后同步刷新 comparison

**Step 4: Run build**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm run build`
Expected: PASS

### Task 4: Run Full Verification

**Files:**
- Modify: none

**Step 1: Run backend tests**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_worldline_engine.py backend/tests/test_worldline_agent_roster.py backend/tests/test_offline_novel_pipeline.py backend/tests/test_explicit_generation_modes.py -q`
Expected: PASS

**Step 2: Compile backend**

Run: `/tmp/mirofish_novel_venv/bin/python -m compileall /Users/项目/MiroFish-Novel/backend/app /Users/项目/MiroFish-Novel/backend/tests`
Expected: PASS

**Step 3: Build frontend**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm run build`
Expected: PASS
