# Remove Prompt Budget Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 删除本地 prompt 裁剪逻辑，让第一阶段和剧情块分析阶段发送完整上下文。

**Architecture:** 保留 `PromptBudgetManager` 作为稳定接口，只替换其内部实现为无预算拼接器。这样调用方无需改动构造方式，行为变化集中在一个文件和一组测试里。

**Tech Stack:** Python 3.11, pytest

---

### Task 1: 锁定新行为

**Files:**
- Modify: `backend/tests/test_prompt_budget.py`

**Step 1: Write the failing test**

把现有“应裁剪”测试改成“超长输入也应完整保留”。

**Step 2: Run test to verify it fails**

Run: `env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 /Users/项目/MiroFish-Novel/.venv/bin/python -m pytest backend/tests/test_prompt_budget.py -q`

**Step 3: Write minimal implementation**

把 `PromptBudgetManager.build_prompt()` 改为仅拼接非空 sections。

**Step 4: Run test to verify it passes**

Run: 同上

### Task 2: 清理预算逻辑

**Files:**
- Modify: `backend/app/services/prompt_budget_manager.py`

**Step 1: Remove unused budget constants**

删除段落优先级、字符限制、截断提示和相关辅助函数。

**Step 2: Keep stable API**

保留 `PromptBudgetManager` 类名和 `build_prompt()` 方法签名。

**Step 3: Run targeted tests**

Run: `env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 /Users/项目/MiroFish-Novel/.venv/bin/python -m pytest backend/tests/test_prompt_budget.py backend/tests/test_seed_block_retry.py backend/tests/test_story_memory_pipeline.py backend/tests/test_skeleton_timeline.py backend/tests/test_async_seed_pipeline.py backend/tests/test_llm_client.py -q`
