# 项目现状调查档案 — 索引

## 调查元信息

| 项目 | 值 |
|---|---|
| 调查日期 | 2026-07-31 |
| 当前 Git branch | `rewrite/web-clean-slate` |
| 当前 commit | `e995686`（docs: record prelaunch audit repair status） |
| 工作区状态 | 有 5 个未提交修改文件（pi-writer-activities.ts/test、writer-rail.tsx、writer-run.ts/test、tools/ui-preview/shots/），内容为「公开工具结果预览增强」，已并入本文档描述 |
| 仓库规模 | 1326 个 git 跟踪文件，约 50 万行（含历史文档）；Go API ~12 万行、Python 运行时 ~6.9 万行、Pi 运行时 ~1.8 万行、Web ~3.6 万行、Legacy backend ~8.9 万行 |

本目录是 2026-07-31 的静态审查快照；修复排序、实施边界和最终验证以 [13-fix-plan.md](13-fix-plan.md) 为准。

## 调查范围与方法

本次调查为**静态代码调查**，未修改任何业务代码、未运行会写数据库或调用付费模型的命令。方法：

1. 分层搜索（根目录 → 各 app 包清单 → 关键文件全文阅读）
2. 调用链追踪（定义 → 导出 → 注册 → 启用 → 真实调用）
3. 交叉验证（前后端事件名、数据库表、JSON Schema 契约三方对照）
4. 对每个工具追踪「定义 / 导出 / 注册 / 启用条件 / 底层服务 / 测试」

由于本环境无法并行派发多个 Subagent，调查由主 agent 按 Subagent 规划的分工顺序逐项完成：仓库地图 → Pi 核心链路 → 工具清点 → 前端通信 → 上下文 → 状态持久化 → 业务能力 → 测试与安全。所有结论均附文件路径与符号名；区分【已确认】【合理推断】【待确认】【疑似废弃】【未接通】。

## 文档清单

| 文件 | 内容 | 读者 |
|---|---|---|
| `00-README.md` | 本索引 | 所有人 |
| `01-executive-summary.md` | 非程序员摘要（≤4000 字） | 非程序员 |
| `02-repository-map.md` | 仓库地图：目录职责、启动/构建/测试入口 | 所有 AI |
| `03-system-architecture.md` | 系统架构 + Mermaid 图 | 架构读者 |
| `04-pi-agent-runtime.md` | **核心**：Pi 依赖、Session 创建、完整运行过程、生命周期事件、中断控制 | AI |
| `05-agent-tools-catalog.md` | **最重要**：全部 25 个 Agent 工具完整清单 + 逐工具档案 | AI |
| `06-prompts-context-skills.md` | System Prompt、上下文组装、Skill/RAG 现状 | AI |
| `07-frontend-agent-communication.md` | **核心**：前端 → Agent 通信时序、事件映射 | AI |
| `08-data-state-persistence.md` | **核心**：数据库模型、状态持久化、一致性风险 | AI |
| `09-feature-status-matrix.md` | 功能状态表 | 产品/PM |
| `10-security-observability-testing.md` | 安全、可观测性、测试 | 安全读者 |
| `11-known-issues-and-open-questions.md` | 问题、风险、待确认 | 维护者 |
| `12-ai-handoff.md` | **最终主档案**（1.5–3 万字），单文件交接 | 下一位 AI |
| `13-fix-plan.md` | 本次审查的严重度排序、修复方案、边界与验收 | 维护者/下一位 AI |

## 核心结论速览

- 项目是「长篇小说创作多智能体平台」SaaS 重构实现，**不是**舆情分析项目。
- Pi Agent（`@earendil-works/pi-agent-core@0.80.3`）在 `apps/pi-agent-runtime` 中被**直接使用**，三个执行器：Pi Writer（5 阶段流水线）、Pi Analysis（2 模块）、Pi Worldline Cast（1 模块）。
- 共 **25 个自定义 Agent 工具**（Writer 13 + Analysis 7 + Cast 5），**0 个 Pi 内置工具、0 个 MCP 工具、0 个 Extension、0 个 Skill、0 个子 Agent**。
- 调用链：Web（900ms 轮询）→ BFF → Go API → Temporal → Pi worker → LLM（OpenAI-compatible）。
- 成熟度高：Go 1073 个测试函数、Python 502 个、Web 124 个、Pi 18 个测试文件；31 个 DB migration；已有多轮上线前审计记录。

## 如何把本档案交给其他 AI

1. 打包：`tar -czf project-audit.tar.gz docs/project-audit/`
2. 或者直接发送这五个文件（12-ai-handoff.md、05-agent-tools-catalog.md、04-pi-agent-runtime.md、07-frontend-agent-communication.md、08-data-state-persistence.md），再按需补充其他文件。
3. 告诉接收 AI：先读 `12-ai-handoff.md`，需要细节时再查对应编号文档；所有结论以「【已确认】【合理推断】【待确认】」标记区分证据强度。

## 未完成调查项

- 未运行任何测试（静态调查）；live 行为结论来自代码路径与项目自带进度文档，未实机复验。
- 未逐字阅读 `apps/api/internal/httpapi/server.go`（1 万行，按 rg 定位关键 handler 阅读）。
- Legacy `backend/` 仅做了目录级调查（按 AGENTS.md 它是只读参考）。
- `tools/ui-preview/shots/` 为未提交的 UI 预览截图目录，未纳入分析。
