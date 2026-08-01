# 仓库地图

## 1. 顶层目录

```
MiroFish-Novel/
├── apps/                      # SaaS 活跃代码（真相源）
│   ├── api/                   # Go control plane（HTTP/RBAC/workflow admission/read side）
│   ├── web/                   # 唯一 Next.js 前端
│   ├── agent-runtime/         # Python 领域 worker（Seed/Graph/Worldline/Reviewer/Planning/Legacy import）
│   └── pi-agent-runtime/      # Pi Writer Agent Runtime（TS + Pi Agent + Temporal）
├── packages/
│   └── shared-contracts/      # Go → Pi → Web 的 JSON Schema 契约（冻结）
├── infra/                     # Docker Compose、Postgres migrations、部署脚本
├── docs/                      # 设计文档；refactor-saas/ 是 SaaS 进度真相源
├── tasks/                     # 活动任务板
├── backend/                   # ⚠️ Legacy FastAPI（仅迁移/兼容参考，不是产品运行时）
├── tools/                     # 内部工具（ui-preview 等）
├── .github/                   # CI
├── AGENTS.md / CLAUDE.md      # Agent 接手说明（本调查的主要输入之一）
└── 首页-手机端/               # 未参与 SaaS 的遗留目录（未调查）
```

## 2. 各 app 职责

### apps/api（Go 1.24，约 12 万行）
- `cmd/api/`：入口（main.go、readiness.go）
- `internal/httpapi/`：HTTP 路由与 handler。`server.go` 约 1 万行，含中央路由、认证、CSRF、限流、SSE。
- `internal/workflows/`：Temporal 客户端、workflow admission、事件读写（writer.go、writer_admission.go、writer_events.go、analysis_*.go、seed_*.go、story_graph_*.go、worldline 相关）。
- `internal/llm/`：LLM Facility（registry.go 33 个模块、bindings.go、catalog.go、resolver.go、quota、telemetry、provider_executor.go）。
- 其他：auth、authrecovery、collaboration、assets、assetcatalog、assetdistillation、characterconsole、manuscriptexport、manuscriptworkspace、writerworkspace、writerplanning、worldline、sourcefiles、projectoverview、projectreadiness、projectadmin、storygraph、traces、observability、platformratelimit、registration、testschema。

### apps/web（Next.js 15.5 + React 19，约 3.6 万行）
- `app/`：页面（login、recovery、invitations、projects/[projectId]/* 工作台、workspace 书架）+ BFF 路由（`app/api/...`）。
- `lib/api/`：浏览器端 API 客户端（writer-client.ts、writer-run.ts、asset-client.ts、worldline-client.ts、graph-client.ts、character-console-client.ts、llm-client.ts 等）。
- `lib/server/`：服务端 BFF 代理（api-proxy.ts、project-proxy.ts、client-proof.ts）。
- `app/projects/[projectId]/`：7 个工作台（overview、assets、characters、graph、worldline、writer、settings）+ workbench 导航。
- writer 目录是 Agent 交互核心：writer-workspace.tsx（主画布+布局）、writer-rail.tsx（常驻协作者 dock）、use-writer-run.ts（轮询 hook）。

### apps/pi-agent-runtime（TS，约 1.8 万行）—— 本次调查核心
- `src/contracts/`：Writer/Analysis/WorldlineCast 的 run 契约 + worker spec。
- `src/runtime/`：三个 Pi Agent 执行器（pi-writer-agent.ts、pi-analysis-agent.ts、pi-worldline-cast-agent.ts）+ Postgres 依赖实现（postgres-pi-writer-deps.ts 等）+ recall-fusion.ts（RRF 融合）+ object-store.ts。
- `src/activities/`：Temporal 活动（pi-writer-activities.ts 2256 行，含 13 工具的全部执行调度、5 阶段编排、事件记录）。
- `src/workflows/`：Temporal workflow（pi-writer-workflow.ts、pi-analysis-workflow.ts、pi-worldline-goal-start-workflow.ts）。
- `src/llm/`：pi-ai-compose.ts（单次 complete 路径）、model-capabilities.ts、quota/（Postgres 配额存储）。
- `src/tools/`：工具权限门控（permissions.ts、analysis-permissions.ts、worldline-cast-permissions.ts）。
- 三个 worker 入口：worker.ts（writer）、analysis-worker.ts、worldline-cast-worker.ts。

### apps/agent-runtime（Python + Temporal，约 6.9 万行）
- `mirofish_agents/temporal/`：worker.py（按 task queue 注册 workflow）、seed.py、worldline.py、worldline_prepare.py、worldline_auto_evolution.py、character.py、writer_review.py、writer_planning.py、graph.py、assets.py、legacy_import_*.py、manuscript_asset_distillation.py。
- `mirofish_agents/seed/`：sequential_reader.py（JSON Chat LLM 客户端 + LLM Facility 绑定解析）、global_aggregator.py、pdf_ocr.py、quota_chat_client.py。
- `mirofish_agents/llm_quota/`、`llm/model_capabilities.py`。
- `mirofish_agents/legacy_import/`：Legacy 数据迁移。

### packages/shared-contracts（约 380 行）
- `schemas/`：writer-workflow-input.schema.json、writer-runtime-event.schema.json、writer-public-event.schema.json、writer-tool-request.schema.json（Draft 2020-12 JSON Schema，冻结三端契约）。
- 有 Go/Python/TS 序列化器测试防漂移。

## 3. 启动 / 构建 / 测试入口

| 入口 | 命令 |
|---|---|
| 本地全栈 | `docker compose -f infra/docker-compose.yml up -d --build`（Web :3999、API :3888、Temporal UI :8233） |
| Go 测试 | `cd apps/api && go test ./...` |
| Web 测试/类型/构建 | `cd apps/web && npm test && npm run typecheck && npm run build` |
| Pi 测试/类型/构建 | `cd apps/pi-agent-runtime && npm test && npm run typecheck && npm run build` |
| Python 测试 | `cd apps/agent-runtime && env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests -q` |
| live 测试 | `infra/scripts/run-live-test-stack.sh -- <command>`（隔离 `mirofish_test_*` 栈） |
| Pi writer worker | `cd apps/pi-agent-runtime && npm run worker` |
| Pi analysis worker | `npm run analysis-worker` |
| Pi cast worker | `npm run worldline-cast-worker` |

## 4. 基础设施（infra）

- `docker-compose.yml`：postgres(pgvector:pg16, :54329)、redis(:63799)、temporal(+ui)、minio(:9000/9001)、schema-init(31 migrations)、api、web、8 个 Python worker、3 个 Pi worker、legacy-import-worker、monitoring。
- `postgres/migrations/0001~0031`：全部 schema。
- `scripts/`：bootstrap、健康检查、live-test 栈、备份恢复。
- 部署：`compose.production.yml`、`compose.staging.yml`、`compose.remote-images.yml`、`deployment/`。

## 5. 数据库入口

- 主库：Postgres 16 + pgvector，`infra/postgres/migrations/`（31 个 revision）。
- 表数约 110+（详见 08 文档）；核心表：projects、chapters、scenes、manuscript_blocks、writer_runs、writer_drafts、writer_threads、assets、entities、story_graph_*、worldline_*、workflow_runs、workflow_events、llm_*、resource_locks、agent_traces。

## 6. 重要配置文件

- `AGENTS.md`：Agent 接手规则（前端必须连真实后端等硬约束）。
- `docs/refactor-saas/DEVELOPMENT_PLAN.md`：SaaS 范围与 DoD。
- `docs/refactor-saas/24-current-development-progress.md`：唯一当前进度。
- `tasks/refactor-saas-parallel-board.md`：活动任务板。
- `infra/.env.example`：环境变量模板（真实 `.env` git-ignored，本调查未读取其中秘密）。
- `apps/pi-agent-runtime/package.json`：Pi 依赖锁定（`@earendil-works/pi-agent-core@0.80.3`、`pi-ai@0.80.3`）。
