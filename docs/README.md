# Documentation

本目录保存 MiroFish-Novel 的设计、迁移、接口和交接文档。

## 入口文档

- `CODEX_HANDOFF_GUIDE.md`：Codex / coding agent 接手指南。
- `agent-data-schema-reference.md`：Agent 数据结构、prompt 和参数参考。
- `fastapi-route-manifest.md`：FastAPI 路由清单。
- `database/database-source-of-truth-matrix.md`：统一数据库与 legacy JSON 真相源矩阵。
- `reference-projects-analysis.md`：参考项目分析。

## 设计与计划

- `plans/`：阶段性迁移、重构和修复计划。
- `superpowers/specs/`：功能规格文档。
- `examples/`：示例输出和演示材料。

## 维护约定

- 用户入口和快速开始更新 `../README.md`。
- AI 接手信息更新 `../AGENTS.md` 和 `../CLAUDE.md`。
- 数据真相源变化更新 `database/database-source-of-truth-matrix.md`。
- 新增公开 API 时同步更新 `fastapi-route-manifest.md`。
