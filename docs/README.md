# Documentation

本目录保存 MiroFish-Novel 的设计、迁移、接口和历史记录。

## 入口文档

- `refactor-saas/DEVELOPMENT_PLAN.md`：SaaS 重构范围、阶段顺序和最终完成定义。
- `refactor-saas/24-current-development-progress.md`：唯一当前 SaaS 进度和 next-step 入口。
- `../AGENTS.md`：coding agent 仓库边界和接手规则。
- `agent-data-schema-reference.md`：Agent 数据结构、prompt 和参数参考。
- `fastapi-route-manifest.md`：FastAPI 路由清单。
- `database/database-source-of-truth-matrix.md`：统一数据库与 legacy JSON 真相源矩阵。
- `reference-projects-analysis.md`：参考项目分析。

## 设计与计划

- `plans/`：历史阶段的迁移、重构和修复设计记录；不表示当前进度、优先级或下一步。
- `superpowers/specs/`：历史功能规格文档。
- `examples/`：示例输出和演示材料。

`plans/` 和 `superpowers/` 中指向根目录旧 `frontend/`、Vue/Vite 或旧 Writer 长页的路径只是历史记录，不得作为当前实现、构建或视觉验收依据。

## 维护约定

- 用户入口和快速开始更新 `../README.md`。
- AI 接手信息更新 `../AGENTS.md` 和 `../CLAUDE.md`。
- 数据真相源变化更新 `database/database-source-of-truth-matrix.md`。
- 新增公开 API 时同步更新 `fastapi-route-manifest.md`。
- 当前 SaaS 进度只能更新 `refactor-saas/24-current-development-progress.md`；不要新增 handoff、live progress 或第二份进度总表。
