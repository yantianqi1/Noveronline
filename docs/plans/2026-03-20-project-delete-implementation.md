# Project Delete Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为总览页的项目档案簿增加真实删除能力，删除后同步更新前端列表和当前种子分析状态。

**Architecture:** 后端新增按 `project_id` 删除项目目录的 API，前端在项目档案簿中为每个项目提供删除按钮，并在删除成功后刷新列表、清理当前选中项目相关状态。实现保持最小范围，不引入“清空全部项目”等更高风险操作。

**Tech Stack:** Flask, Vue 3, Vite, Node test runner, pytest

---

### Task 1: 后端删除接口

**Files:**
- Modify: `backend/app/api/project.py`
- Test: `backend/tests/test_project_delete_api.py`

**Step 1: Write the failing test**

写一个接口测试，先创建项目，再调用删除接口，并断言：
- 返回 `success: true`
- 项目目录被删除
- 之后再查询该项目返回 `404`

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH='/Users/项目/MiroFish-Novel/.venv/lib/python3.11/site-packages' /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest tests/test_project_delete_api.py`

**Step 3: Write minimal implementation**

在 `project.py` 中新增删除路由，复用 `ProjectManager.delete_project`，对不存在项目返回 `404`。

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH='/Users/项目/MiroFish-Novel/.venv/lib/python3.11/site-packages' /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest tests/test_project_delete_api.py`

### Task 2: 前端删除入口

**Files:**
- Modify: `frontend/src/api/project.js`
- Modify: `frontend/src/api/http.js`
- Modify: `frontend/src/views/OverviewView.vue`
- Test: `frontend/tests/project-api.test.mjs`

**Step 1: Write the failing test**

写一个前端 API 层测试，断言存在 `deleteProject(projectId)`，且构造的路径是 `/api/project/<id>`。

**Step 2: Run test to verify it fails**

Run: `/opt/homebrew/Cellar/node/25.8.0/bin/node --test frontend/tests/project-api.test.mjs`

**Step 3: Write minimal implementation**

新增 `del` 请求封装与 `deleteProject` API；在总览页列表项添加删除按钮和删除中状态。

**Step 4: Run test to verify it passes**

Run: `/opt/homebrew/Cellar/node/25.8.0/bin/node --test frontend/tests/project-api.test.mjs frontend/tests/api-base.test.mjs frontend/tests/vite-config.test.mjs`

### Task 3: 删除后的状态同步与页面验证

**Files:**
- Modify: `frontend/src/views/OverviewView.vue`

**Step 1: Write the failing behavior check**

用页面自动化或手工路径验证：删除当前选中项目后，列表刷新，`seedProjectId` 和 `seedResult` 被清空。

**Step 2: Implement minimal state sync**

删除成功后：
- 从本地列表移除对应项目
- 若删除的是当前 `seedProjectId`，清空 `seedProjectId`、`seedResult`、`seedError`
- 若列表仍有项目，自动切到最新项目

**Step 3: Run verification**

Run:
- `PYTHONPATH='/Users/项目/MiroFish-Novel/.venv/lib/python3.11/site-packages' /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest tests/test_project_delete_api.py tests/test_cors.py`
- `/opt/homebrew/Cellar/node/25.8.0/bin/node --test frontend/tests/*.test.mjs`
- 用 Playwright 打开 `http://127.0.0.1:5174`，执行上传后的项目删除操作，确认列表和状态同步更新
