# 12-Subagent-并行执行协议

## 1. 目标

本文件定义本轮重构如何安全地使用 `subagent` 并行执行。目标不是追求同时开工最多，而是在不破坏边界的前提下最大化并行。

---

## 2. 并行前提

只有在以下基线完成后，才允许进入大规模并行：

- `06` 功能覆盖矩阵冻结
- `07` 接口与页面清单冻结
- `08` 字段映射冻结
- `10` 隐性语义矩阵冻结
- OpenAPI / error code / event schema 冻结
- monorepo 与基础 infra 初始化完成

---

## 3. 并行切分原则

每个 subagent 必须同时满足以下条件：

- 有独占写目录
- 有独占测试责任
- 有明确输入 contract
- 有明确下游依赖
- 不允许跨模块随手改 shared schema

公共定义只能由 `contracts owner` 修改。

---

## 4. 推荐并行车道

| Lane | 责任范围 | 独占写边界 | 前置依赖 |
|---|---|---|---|
| A | contracts | `packages/contracts/**`、`apps/api/openapi*` | 无 |
| B | infra + migration | `infra/**`、`migrations/**`、`apps/api/src/bootstrap/**` | A |
| C | project + seed-analysis | `apps/api/src/modules/project/**`、`seed_analysis/**` | A、B |
| D | graph | `apps/api/src/modules/graph/**`、`apps/web/src/features/story-graph/**` | A、B、C |
| E | archive-library | `apps/api/src/modules/archive_library/**` | A、B、C、D(read-only contract) |
| F | llm-facility | `apps/api/src/modules/llm_facility/**`、`apps/web/src/features/llm-facility/**` | A、B |
| G | worldline | `apps/api/src/modules/worldline/**`、`apps/web/src/features/worldline/**`、`character-console/**` | A、B、D、E、F |
| H | writer | `apps/api/src/modules/writer/**`、`apps/web/src/features/writer/**` | A、B、E、F、G |
| I | web shell | `apps/web/src/app/**`、`shared/**`、`pages/overview`、`guide` | A |

---

## 5. 强约束

### 5.1 不允许的行为

- worldline agent 修改 writer contract
- writer agent 修改 worldline projection 结构
- graph agent 修改 archive memory schema
- 前端 agent 绕过 generated client 直接手写新 DTO
- 任何 agent 在未更新 `contracts` 的情况下私改公共错误模型

### 5.2 允许的行为

- 本模块内部重构
- 在 contracts owner 批准后消费新 schema
- 在自己模块内补测试、补文档、补适配层

---

## 6. 集成节奏

并行不是所有 lane 同时到底，而是分 3 波：

1. 波次一：`A + B + I`
2. 波次二：`C + D + E + F`
3. 波次三：`G + H`

每波结束都必须进行一次：

- contract diff 检查
- migration dry-run
- integration smoke test

---

## 7. Definition of Done

每个 lane 完成时必须交付：

- 模块代码
- 模块测试
- 模块 README / ADR / runbook
- 对应 `06/07/09/10` 勾选更新
- 不破坏其他 lane 的 contract

未更新矩阵与测试，不算完成。
