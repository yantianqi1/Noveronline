# Async Seed Upload And Chapter Continuity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把长篇小说上传改成异步分析流水线，并在 LLM 分析前增加章节切分与连续性摘要中间层。

**Architecture:** 后端把 `/api/project/seed/extract` 改成任务式入口，后台线程执行“提取文本 -> 章节切分 -> 连续性摘要 -> 种子分析 -> ontology”，并回写任务进度和项目状态；前端上传后改为轮询任务并展示阶段进度。

**Tech Stack:** Flask, Python dataclasses, background threads, Vue 3, Vite, pytest

---

### Task 1: Add Failing Backend Tests

**Files:**
- Modify: `backend/tests/test_offline_novel_pipeline.py`
- Create: `backend/tests/test_async_seed_pipeline.py`

**Step 1: Write the failing test**

```python
def test_seed_extract_returns_task_immediately():
    ...

def test_async_seed_pipeline_generates_chapter_outputs():
    ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_async_seed_pipeline.py -q`
Expected: FAIL because async upload pipeline and chapter outputs do not exist yet

### Task 2: Implement Backend Async Seed Pipeline

**Files:**
- Modify: `backend/app/api/project.py`
- Modify: `backend/app/models/project_types.py`
- Create: `backend/app/services/seed_extract_task_service.py`
- Create: `backend/app/services/novel_chapter_segmenter.py`
- Create: `backend/app/services/chapter_continuity_service.py`

**Step 1: Add task-driven upload flow**

- 上传接口立即返回 `project_id + task_id`
- 后台线程执行 seed 流水线

**Step 2: Add chapter segmentation**

- 优先按章标题切分
- 无标题时按叙事块切分

**Step 3: Add continuity summary**

- 为每章生成连续性字段
- 保存 `chapter_segments.json` 和 `chapter_continuity.json`

**Step 4: Update project/task status**

- 增加 `seed_processing` / `seed_completed`
- 任务消息体现当前阶段

**Step 5: Run tests**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_async_seed_pipeline.py backend/tests/test_offline_novel_pipeline.py -q`
Expected: PASS

### Task 3: Integrate Frontend Task Polling

**Files:**
- Modify: `frontend/src/api/project.js`
- Modify: `frontend/src/composables/useSeedUpload.js`
- Modify: `frontend/src/views/overview/SeedUploadPanel.vue`
- Modify: `frontend/src/views/OverviewView.vue`
- Modify: `frontend/src/App.vue`

**Step 1: Upload returns task**

- 上传成功后保存 `task_id`
- 轮询任务状态

**Step 2: Update progress UX**

- 区分“文件上传中”和“后台分析中”
- 展示阶段标签与总进度

**Step 3: Refresh project after completion**

- 任务完成后刷新项目列表
- 自动切到完成项目

**Step 4: Run build**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm run build`
Expected: PASS

### Task 4: Real End-To-End Validation

**Files:**
- Modify: none

**Step 1: Restart backend and frontend**

Run existing startup commands with current env

**Step 2: Upload real novel**

File: `/Volumes/Fanxiang S500Pro/小说项目/赘婿.txt`

**Step 3: Verify outputs**

- 任务最终完成
- `chapter_segments.json` 存在
- `chapter_continuity.json` 存在
- `seed_analysis.json` 存在

### Task 5: Full Verification

**Files:**
- Modify: none

**Step 1: Run backend tests**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_async_seed_pipeline.py backend/tests/test_offline_novel_pipeline.py backend/tests/test_worldline_engine.py backend/tests/test_worldline_agent_roster.py backend/tests/test_worldline_branch_comparison.py backend/tests/test_explicit_generation_modes.py -q`
Expected: PASS

**Step 2: Compile backend**

Run: `/tmp/mirofish_novel_venv/bin/python -m compileall /Users/项目/MiroFish-Novel/backend/app /Users/项目/MiroFish-Novel/backend/tests`
Expected: PASS

**Step 3: Build frontend**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm run build`
Expected: PASS
