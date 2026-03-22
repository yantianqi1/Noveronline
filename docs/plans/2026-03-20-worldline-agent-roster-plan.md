# Worldline Agent Roster Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为世界线补上统一的 agent 名册与关系 agent 交互主链。

**Architecture:** 在后端新增一个派生式 `worldline_agent_registry` 服务，从 branch 状态动态生成 agent 卡片；API 通过 `agent_id` 解析到角色、组织或关系；前端在角色控制台新增名册面板并支持点选交互。

**Tech Stack:** Flask, Python dataclasses, Vue 3, Vite, pytest

---

### Task 1: Add Failing API Tests

**Files:**
- Create: `backend/tests/test_worldline_agent_roster.py`

**Step 1: Write the failing test**

```python
def test_worldline_agent_roster_lists_character_org_and_relation_agents():
    ...

def test_relation_agent_supports_dialogue_and_action():
    ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_worldline_agent_roster.py -q`
Expected: FAIL because roster API and relation-agent support do not exist yet

### Task 2: Implement Derived Agent Registry

**Files:**
- Create: `backend/app/services/worldline_agent_registry.py`
- Modify: `backend/app/api/worldline_support.py`
- Modify: `backend/app/api/worldline_interaction.py`
- Modify: `backend/app/services/worldline_branch_service.py`

**Step 1: Implement registry models/helpers**

- Add stable `agent_id` generation
- Add branch roster derivation for character / organization / relationship
- Add agent lookup by `agent_id` or display name

**Step 2: Add API endpoint**

- `GET /api/worldline/session/<session_id>/agents`

**Step 3: Extend dialogue/action**

- `agent-dialogue` resolves `agent_id`
- `agent-action` resolves `agent_id`
- relation action updates relation state during step

**Step 4: Run tests**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_worldline_agent_roster.py -q`
Expected: PASS

### Task 3: Add Frontend Agent Roster Panel

**Files:**
- Create: `frontend/src/views/character-console/WorldlineAgentRoster.vue`
- Modify: `frontend/src/api/worldline.js`
- Modify: `frontend/src/views/CharacterConsoleView.vue`

**Step 1: Add frontend API wrapper**

- Add `getWorldlineAgents(sessionId, branchId?)`

**Step 2: Build roster component**

- Fetch roster
- Group by `agent_kind`
- Emit selected agent

**Step 3: Integrate into control panel**

- Clicking roster card fills chat target and action target

**Step 4: Run build**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm run build`
Expected: PASS

### Task 4: Run Full Verification

**Files:**
- Modify: none

**Step 1: Run backend test suite for touched areas**

Run: `PYTHONPATH=/Users/项目/MiroFish-Novel/backend /tmp/mirofish_novel_venv/bin/pytest backend/tests/test_worldline_engine.py backend/tests/test_offline_novel_pipeline.py backend/tests/test_explicit_generation_modes.py backend/tests/test_worldline_agent_roster.py -q`
Expected: PASS

**Step 2: Compile backend**

Run: `/tmp/mirofish_novel_venv/bin/python -m compileall /Users/项目/MiroFish-Novel/backend/app /Users/项目/MiroFish-Novel/backend/tests`
Expected: PASS

**Step 3: Build frontend**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm run build`
Expected: PASS

