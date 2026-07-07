# 23. A4 Story Graph Runner Fix Handoff

更新时间：`2026-07-07`

## 目的

本文记录 `A4-fix Story Graph Runner Worker` 对 reviewer blocking issues 的修复结果、TDD RED/GREEN 证据、验证命令和后续接手提示词。

## Provenance / 使用边界

本文是来自单独 A4 worker 的历史/外部 handoff note，用于保留上下文和后续复核线索。它不是 Wave 0 governance 工作产出的产品完成证据，也不能单独证明 Story Graph runner 已经 product-complete。

本文件未记录可核验的精确 commit SHA；commit/provenance 在本文件中未记录。后续 agent 在采用本文结论前，必须对照当前 git diff/commit history、实际 `apps/**` 产品代码变更和重新运行的测试输出进行验证。若无法把本文描述对应到明确代码 diff/commit 和新鲜验证结果，应把它视为待复核交接材料，而不是已完成事实。

工作只发生在：

`/Users/yantianqi/Documents/Noveronline-saas-mainline`

不要修改主工作区：

`/Users/yantianqi/Documents/Noveronline`

## Status

外部 A4 worker 报告已修复 A4 reviewer 对 Story Graph Runner 的 blocking issues；该状态需要后续 agent 用实际 git diff/commit 和新鲜测试结果复核后，才可作为 product-complete 证据引用。

目标分支：`codex/saas-mainline`

涉及文件：

- `apps/agent-runtime/mirofish_agents/temporal/graph.py`
- `apps/agent-runtime/tests/test_story_graph_workflow.py`

## RED Observed

先扩展失败测试后运行：

```bash
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_story_graph_workflow.py -q -k 'graph_bond or story_graph'
```

观察到 5 个预期失败，覆盖：

- `PostgresWorkflowRunStatusWriter` 仍硬编码 `workflow_type = 'story_graph_build'`，无法更新 admitted bond workflow row。
- `graph_bond_generation_activity` 对 runner 返回 `status: failed` 仍标记 completed。
- `graph_bond_generation_activity` 未严格要求 admitted bond context：`workflow_type`、`project_id`、`module_key`。
- LLM provider 输出中 safe-looking 字段包含 selected node ids、focus text、API-key-like value、prompt marker 时仍可能进入候选资产路径。
- candidate writer 直接写入时，safe-looking `tags` / `payload` value 仍可能进入 `assets.tags_jsonb` / `assets.payload_jsonb`。

## What Changed

- `PostgresWorkflowRunStatusWriter` 更新 `workflow_runs` 时改为使用 `context.workflow_type` 参数，不再硬编码 `story_graph_build`。
- Bond generation failed status 会更新 admitted `story_graph_bond_generation` workflow row；失败路径也能标记 failed。
- `graph_bond_generation_activity` 现在 fail closed 要求：
  - `context.workflow_type == story_graph_bond_generation`
  - `context.project_id` 非空
  - `context.module_key == graph_bond_generator`
- `graph_bond_generation_activity` 现在检查 runner result：
  - 只有 `status == completed` 才写 completed event/status。
  - `status == failed` 或非 completed 时，使用 runner public error code/message 写 failed event/status。
  - 不把 failed runner result 的 `candidate_batch_id` 等字段公开到 failed result。
- candidate sanitization 增加 value-level scrub/validation：
  - required public `title` / `summary` 中命中 sensitive value 时，LLM runner 以 `SCHEMA_VALIDATION_FAILED` fail closed，不调用 candidate writer。
  - optional `tags` / `payload` value 中命中 sensitive marker 时，保守移除该 value 或字段。
  - 检测 node id、focus text、`sk-`、credential/API key marker、prompt/snippet/raw text marker 等。
- DB candidate writer 路径也复用 graph bond candidate normalization/sanitization，避免绕过 LLM runner 的直接写入泄露。

## Verification

已运行并通过：

```bash
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_story_graph_workflow.py -q -k 'graph_bond or story_graph'
cd apps/agent-runtime && .venv/bin/python -m pytest tests -q -k 'graph'
cd apps/api && go test ./internal/storygraph ./internal/httpapi -run 'StoryGraph|Graph|Bond' -count=1
cd apps/web && npm run test -- --test-name-pattern='Story Graph|graph'
git diff --check
```

结果摘要：

- agent-runtime focused Story Graph tests：`18 passed`
- agent-runtime graph selection：`19 passed, 211 deselected`
- Go StoryGraph/Graph/Bond tests：`ok` for `internal/storygraph` and `internal/httpapi`
- Web Story Graph/graph tests：`35 pass`
- `git diff --check`：exit 0

## Remaining Risks

- 当前修复是 focused unit/integration-like 覆盖，尚未跑真实 Postgres + Temporal + provider live E2E。
- value-level scrub 是保守启发式规则；后续如果 graph bond provider 输出 schema 扩展，需要同步补测试，确保 safe-looking field 不成为新泄露路径。
- 若其他 worker 改动 `AgentContext`、workflow admission 或 LLM Facility error schema，需要复测本文件中的验证命令。

## Suggested Next Checks

后续 worker 如果继续 Story Graph runner，可优先检查：

1. 用真实 Postgres admission row 验证 `story_graph_bond_generation` failed/completed status update。
2. 用 Temporal worker 触发 `graph_bond_generation_activity`，验证 failed runner 不产生 completed event。
3. 补 live provider fake-server E2E，覆盖 unsafe JSON output 被 fail closed，safe JSON output 可写 candidate assets。
4. 审查公开 API result 和 `workflow_events.payload_jsonb`，确保没有 selected node ids、focus text、prompt、snippets 或 credentials。

## 新对话启动提示词

可复制下面这段作为新 worker 开场：

```text
你是 Story Graph Runner Follow-up Worker。只在 /Users/yantianqi/Documents/Noveronline-saas-mainline 工作，不要修改 /Users/yantianqi/Documents/Noveronline。分支 codex/saas-mainline。你不是唯一 worker，不要回滚他人改动。

先读：
- AGENTS.md
- docs/refactor-saas/23-a4-story-graph-runner-fix-handoff.md
- docs/refactor-saas/07-story-graph.md
- docs/refactor-saas/13-agent-runtime.md
- apps/agent-runtime/mirofish_agents/temporal/graph.py
- apps/agent-runtime/tests/test_story_graph_workflow.py

目标：继续验证并加固 Story Graph bond generation runner，重点检查真实 admitted workflow row、Temporal activity failed/completed event/status、一切公开 result / workflow event / assets candidate payload 的敏感信息清洗。必须使用 TDD：先写或扩展失败测试并确认 RED，再最小实现，再 GREEN。

硬约束：
- 不新增 mock success、静默 fallback、吞错或伪数据路径。
- 不泄露 API key、credential_ref、prompt、source/raw text、snippets、selected node ids、focus text。
- bond generation 必须只更新 workflow_type = story_graph_bond_generation 的 admitted row。
- runner 返回 failed 或非 completed 时必须 fail closed，写 failed event/status，不写 completed。
- 只改与 Story Graph runner 直接相关的文件；不要碰 Seed、Writer、Worldline、Character Console 的业务实现，除非验证明确要求且先说明原因。

建议验证：
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_story_graph_workflow.py -q -k 'graph_bond or story_graph'
cd apps/agent-runtime && .venv/bin/python -m pytest tests -q -k 'graph'
cd apps/api && go test ./internal/storygraph ./internal/httpapi -run 'StoryGraph|Graph|Bond' -count=1
cd apps/web && npm run test -- --test-name-pattern='Story Graph|graph'
git diff --check

完成后交接：Status / Files Changed / RED observed / What Changed / Verification / Remaining Risks。
```
