# 17. Migration Roadmap

更新时间：`2026-07-03`

## 迁移策略

迁移路线改为 **Writer-first Pi Agent vertical slice**。

不要一次性推倒重写所有功能，也不要先把完整 SaaS 底座搭完才验证核心创作价值。最优顺序是：

1. 冻结文档、契约和基线。
2. 先打通用户写作台和后端 Pi Writer Agent。
3. 把资产库、故事图谱、worldline、角色控制分批接入 writer tools。
4. 再用 SaaS 基座承接已经跑通的 Writer vertical slice。
5. 迁移 seed/assets/graph/worldline/character 等领域能力。
6. 最后完成 legacy import、旧架构清理和生产硬化。

开发总纲以 `DEVELOPMENT_PLAN.md` 为准。本文件是路线摘要。

## Phase 0：文档、契约和基线冻结

目标：

- 以 `DEVELOPMENT_PLAN.md` 作为开发入口。
- 以 `18-legacy-coverage-matrix.md` 作为旧功能覆盖基线。
- 确认当前未提交改动处理策略。
- 冻结第一阶段 Writer/Pi/API/event/tool/LLM 契约。

产出：

- 覆盖矩阵通过负责人确认。
- `tasks/refactor-saas-parallel-board.md` 与 Writer-first 顺序一致。
- 不再把“从零开发 Writer Agent loop”作为首选方案。

验收：

- `/goal` 可以只读 `DEVELOPMENT_PLAN.md` 并知道完整阶段顺序。
- 第一阶段所有详细文档引用清楚。

## Phase 1：Writer-first Pi Agent 最小闭环

实现：

- 写作台 writer run 入口。
- writer run API。
- Pi Writer Runtime Node/TS worker。
- LLM Facility adapter。
- 最小 writer tools。
- token stream / tool events。
- draft revision 保存。
- draft adoption 到 manuscript。

详细设计：

- `21-pi-writer-agent-runtime.md`
- `11-writer-workbench.md`
- `12-llm-facility.md`
- `13-agent-runtime.md`
- `14-data-model.md`
- `15-api-contracts.md`

验收：

- LLM 未绑定时显式失败。
- 绑定模型后写作台可生成真实 draft。
- 前端可看到 token stream、tool calls、trace 和最终 draft。
- 用户可采用 draft 到 manuscript。
- 不使用 mock 正文、假成功或旧式环境变量 LLM fallback。

## Phase 2：写作台工具接入知识层

实现：

- 资产检索 tool。
- 角色档案 tool。
- 世界规则 tool。
- 图谱邻居 tool。
- worldline saved path tool。
- rewrite / outline proposal tools。

详细设计：

- `08-asset-library.md`
- `07-story-graph.md`
- `09-worldline.md`
- `11-writer-workbench.md`
- `13-agent-runtime.md`
- `21-pi-writer-agent-runtime.md`

验收：

- Writer 能显式引用资产、图谱节点、worldline path。
- simulation/candidate 不会自动变 canon。
- 工具结果在写作台右侧可审阅。

## Phase 3：SaaS 基座承接 Writer vertical slice

创建：

```text
apps/web
apps/api
apps/pi-agent-runtime
apps/agent-runtime
packages/shared-contracts
infra/docker-compose
```

实现：

- Next.js app shell。
- Go API health 和 project/writer 最小 API。
- Postgres。
- Redis。
- Temporal。
- MinIO。
- Pi writer workflow。
- Python worker hello workflow。

详细设计：

- `01-target-architecture.md`
- `02-tech-stack.md`
- `03-multi-tenant-saas.md`
- `14-data-model.md`
- `15-api-contracts.md`
- `16-deployment-and-ops.md`

验收：

- 登录后进入项目页。
- Go 启动 writer workflow。
- Pi Worker 执行 writer run。
- 前端看到 workflow event。
- Python worker 仍可作为 seed/graph/worldline 承接点。

## Phase 4：LLM Facility、Trace、Usage、权限硬化

实现：

- tenant channels。
- models sync。
- module bindings。
- llm activity。
- usage events。
- distributed concurrency。
- trace privacy。
- tool permission checks。

迁移：

- 旧 `llm_channels` / `llm_models` / `llm_module_bindings` 导入 tenant scope。
- Pi Writer Runtime 只通过 LLM Facility adapter 获取模型和 key。

验收：

- 缺绑定显式失败。
- writer/seed/worldline 模块能调用绑定模型。
- activity/usage 可按 tenant/project/run/module 查询。
- API Key 和完整小说原文不出现在日志。

## Phase 5：Seed / Assets / Graph 结构化迁移

实现：

- upload。
- object storage。
- SeedPipelineWorkflow。
- Python seed activities。
- seed progress UI。
- structured canon writes。
- assets CRUD/search/facets。
- archive entity/memory candidate review。
- asset ingestion / style extraction workflow。
- graph build workflow。
- story_graph tables。
- React Flow UI。
- inspector。
- compose mode。

迁移：

- 复用旧 seed services。
- `project_artifacts` 导入新表或 object artifacts。
- 旧 assets 和 archive rows 导入。
- classification map 导入。
- 旧 `graph_*` 导入 snapshot。

验收：

- 上传 TXT/MD/PDF 分析成功。
- old seed 功能全部覆盖。
- seed 结果可被 Writer tools 检索。
- 旧 unified-assets 能力覆盖。
- 入库 Agent 可用。
- Writer `query_assets` 读取新资产库。
- 构建图谱。
- 大图可读。
- 羁绊/支线生成。
- Writer `query_graph_neighbors` 读取图谱。

## Phase 6：Worldline / Character Console 创作链闭环

实现：

- prepare workflow。
- session/runtime tables。
- event adoption。
- saved paths。
- worldline UI。
- Writer saved path reference。
- Character Console interaction sessions。
- first-person mode。
- turn stream。
- convert to chapter workflow。
- interaction draft 接入 Writer。
- reviewer。
- dedup。
- book plans。
- one-click actions。
- forbidden lexicon。
- outline versions。
- manuscript export。

迁移：

- 旧 `worldline_sessions` / agent logs 导入。
- 旧 `chapter_content` / `scenes` / `assets manuscript_block` 导入。

验收：

- 单世界推演完整。
- 保存路径给 Writer 引用。
- 不恢复旧多分支主模型。
- 角色互动记录可保存。
- 可转为章节草稿。
- 转写草稿能进入写作台。
- 旧 writer-agent API 语义覆盖。
- 写作台可实际生成、审校、采用和导出正文。

## Phase 7：Legacy import、覆盖矩阵验证和旧架构清理

清理：

- 旧 FastAPI public routes。
- 旧 `project_artifacts` runtime fallback。
- 旧多分支接口。
- 旧本地文件真相源。

保留：

- legacy importer。
- migration reports。
- export tools。

验收：

- 旧 SQLite/project artifacts 可生成 import report。
- selected import 有成功、失败和 rollback report。
- 未完成导入不会被标记为成功。
- 覆盖矩阵剩余项都有 owner/wave 或明确 deprecated-with-reason。
- 不恢复旧 FastAPI public routes 或旧本地文件真相源。

## Phase 8：Ops / Billing / Security / Production hardening

实现：

- usage。
- quota。
- billing hooks。
- monitoring。
- backup。
- audit review。
- rate limit。
- cost control。

验收：

- 可公网部署。
- 可限制成本。
- 可定位故障。
- logs 不含敏感原文/API Key。

## 迁移原则

- `DEVELOPMENT_PLAN.md` 是执行入口。
- 每个 phase 都必须可运行或明确 blocked。
- 不破坏旧数据导入。
- 不把未完成模块伪装完成。
- 每迁移一个模块，更新覆盖矩阵。
- 前端页面先做新结构，再接真实 API，不放假数据。
- Pi Writer Runtime 只替代 writer agent loop，不自动吞掉所有 Python 领域逻辑。

## 验收清单

- 22 个主文档覆盖所有模块和 Writer-first Pi 路线。
- 每个旧 endpoint group 有新 API。
- 每个旧页面有新页面。
- 每个旧表有迁移目的地。
- 每个旧 LLM module 有新绑定。
- 每个长任务进入 workflow 或有明确兼容过渡。
- 写作台优先跑通 Pi Agent 真实闭环。
