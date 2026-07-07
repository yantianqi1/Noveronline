# 02. Tech Stack

更新时间：`2026-06-27`

## 推荐技术栈

| 层 | 推荐 |
|---|---|
| Web App | Next.js App Router + React + TypeScript |
| UI | Tailwind CSS + shadcn/ui + Radix primitives + lucide-react |
| 图谱 UI | React Flow / @xyflow/react |
| 富文本 / 稿件编辑 | Tiptap / ProseMirror |
| Control Plane | Go |
| Go HTTP | chi 或 Gin，优先 chi + 标准库风格 |
| Go DB | pgx + sqlc 或 Ent |
| Workflow | Temporal |
| Writer Agent Runtime | Node.js 22.19+ + `@earendil-works/pi-agent-core` + `@earendil-works/pi-ai` |
| Python Agent Runtime | Python 3.12+ |
| Python Agent API | Temporal Python worker，必要时内部 FastAPI |
| Database | PostgreSQL 16+ |
| Tenant Isolation | PostgreSQL Row Level Security |
| Vector Search | pgvector |
| Cache / Rate Limit | Redis |
| Object Storage | S3 / Cloudflare R2 / MinIO |
| Auth | Auth.js / Clerk / 自建 OIDC，按商业策略选择 |
| Observability | OpenTelemetry + Prometheus + Grafana + Loki/Sentry |
| Packaging | Docker / Docker Compose 起步，Kubernetes 可选 |

## 为什么是 Go + Pi Writer + Python Hybrid

### Go 适合控制面

Go 负责：

- 公网 HTTP API。
- 多租户中间件。
- 鉴权和权限。
- 高并发任务提交。
- SSE / WebSocket。
- 配额、计费、审计。
- 数据库事务和一致性边界。

优势：

- 并发模型直接。
- 单 binary 部署简单。
- 内存占用低。
- 标准库 HTTP 能力成熟。
- 在服务端 API、流式推送、后台协调方面稳定。

### Python 适合 Agent Runtime

Python 负责：

- 长文本解析和分析。
- LLM prompt 编排。
- JSON 修复、schema 验证、retry。
- seed pipeline。
- story graph semantic build。
- worldline agent / director。
- writer orchestrator / composer / reviewer。

优势：

- 当前项目已有大量 Python 领域逻辑。
- LLM / NLP / data processing 生态更顺手。
- Prompt 和 Agent 迭代速度高。
- 保留旧能力风险最低。

### Temporal 是连接层

Temporal 让 Go 和 Python 都可以成为 workflow/activity worker：

- Go 启动 workflow、查询 workflow、取消 workflow。
- Python 执行 LLM-heavy activity。
- 长任务状态由 Temporal 和业务 task 表共同记录。
- Worker 崩溃不会丢失任务状态。

## 为什么不是全 Go

全 Go 可以得到更统一的部署，但对这个项目不是最佳效果：

- 需要重写 seed、graph、worldline、writer 的核心 Agent 能力。
- Prompt iteration 和 LLM JSON 处理会更笨重。
- 当前 Python 测试、服务和领域模型积累无法复用。
- AI 生态中很多工具链优先支持 Python。

结论：Go 应进入后端核心，但不应该吞掉 Agent 层。

## 为什么不是保留当前 Vite + FastAPI

当前栈适合本地单人开发，不适合作为最终 SaaS 基座：

- Vite SPA 需要额外处理 auth、server routing、metadata、用户门户和组织路由。
- FastAPI 作为公网控制面可以工作，但在多租户、计费、实时推送、高并发文件和任务控制上不如 Go 控制面清晰。
- 当前 FastAPI 同时承担公网 API 和 Agent 执行，职责混在一起。
- 长任务大量依赖 task 表和内存 async task，生产恢复能力不足。

保留 FastAPI 的合理方式：迁移期内部 adapter 或局部 worker endpoint。

## 前端选型

### Next.js

职责：

- SaaS app shell。
- Auth-aware routing。
- Tenant/project nested routes。
- Server Components 加载低敏基础数据。
- Client Components 承载复杂交互工作台。

路由建议：

```text
/(marketing)
/(auth)/login
/(app)/[tenantSlug]/projects
/(app)/[tenantSlug]/projects/[projectId]/overview
/(app)/[tenantSlug]/projects/[projectId]/graph
/(app)/[tenantSlug]/projects/[projectId]/assets
/(app)/[tenantSlug]/projects/[projectId]/worldline
/(app)/[tenantSlug]/projects/[projectId]/character-console
/(app)/[tenantSlug]/projects/[projectId]/writer
/(app)/[tenantSlug]/settings/llm
```

### UI System

推荐：

- Tailwind tokens。
- shadcn/ui 作为基础组件生成方式。
- Radix primitives 做 accessibility。
- lucide-react 做图标。
- 少量自研高密度组件：Command Bar、Inspector、Trace Drawer、Timeline、Asset Card、Graph Sidebar。

禁止：

- 大面积营销式 hero 侵入工作台。
- emoji 做结构性图标。
- 一页塞满解释性文本。
- 卡片套卡片。
- 单一紫蓝/深蓝/米色主题失控。

### React Flow

用于故事图谱重做：

- 节点/边声明式数据。
- Minimap、controls、viewport、selection。
- 自定义节点和边。
- 支持节点分组、折叠、局部展开。

D3 可以继续用于布局计算或统计图，但不再直接承担全部图谱交互 UI。

### Tiptap

用于写作台正文编辑：

- 场景正文。
- 章节稿。
- 审校批注。
- span rewrite。
- diff / suggestion mark。

第一阶段可以保留 textarea + prose view，但目标写作台应升级到 Tiptap。

## 后端选型

### Go HTTP

推荐 `chi`：

- 接近标准库。
- 中间件简单。
- 路由可读。
- OpenAPI 生成容易接入。

如果团队更熟 Gin，也可用 Gin，但文档中默认按 chi 风格描述。

### Go DB

两条可选路线：

#### sqlc + pgx

优点：

- SQL 可控。
- 类型安全。
- 性能好。
- RLS / CTE / Postgres 特性不受 ORM 限制。

缺点：

- schema 演化时 SQL 文件较多。
- 复杂对象组装需要手写。

#### Ent

优点：

- schema 声明式。
- migration、关系、隐私策略有框架支持。
- 适合快速建模。

缺点：

- 对复杂 SQL 和 RLS 的控制需要更谨慎。
- 大量 JSONB / 搜索 / 向量场景可能仍需手写 SQL。

推荐：核心多租户业务使用 `sqlc + pgx`，如果团队喜欢 schema-first，可在非复杂域使用 Ent。不要同时在同一领域混用。

### Python Worker

推荐：

- 保留当前 FastAPI 服务逻辑中的领域代码，逐步提取为 `mirofish_agents` package。
- Temporal activities 调用这些 service。
- LLM client、schema、prompt、trace writer 统一放 agent runtime。
- 旧 API 层逐步下线。

### Pi Writer Runtime

推荐：

- 第一阶段 Writer Agent loop 使用 `earendil-works/pi` SDK。
- 新增 Node/TypeScript worker，例如 `apps/pi-agent-runtime`。
- Pi 只负责 writer 的通用 agent loop、tool calling 和 event stream。
- LLM key、模块绑定、trace、权限、draft/manuscript persistence 仍由 MiroFish 控制。
- 不使用 `pi-coding-agent` CLI 作为产品后端。

## 数据层

### PostgreSQL

必须使用：

- transaction。
- foreign key / unique constraint。
- JSONB。
- RLS。
- partial index。
- full text search。
- pgvector。

SQLite 只保留本地 demo 或测试，不作为 SaaS 运行数据库。

### pgvector

用于：

- asset semantic search。
- archive memory recall。
- scene / chapter context retrieval。
- worldline event retrieval。
- writer dedup / style retrieval 的补充索引。

向量表不要替代主业务表。它是检索索引，不是真相源。

### Redis

用于：

- rate limit。
- request id / stream fanout 辅助。
- session cache。
- feature flag cache。

不用于：

- 长期任务真相源。
- manuscript 正文真相源。
- Agent memory 真相源。

## 工作流层

### Temporal

每个长流程都应是 workflow：

- seed pipeline。
- graph build。
- asset ingestion。
- style extraction。
- worldline prepare。
- worldline auto-evolution。
- character interaction to chapter。
- writer run。
- reviewer run。

Workflow 负责状态机，Activity 负责实际工作。

### Task 表仍然保留

Temporal 不直接替代业务 task read model。需要保留 `task_runs` 或新 `workflow_runs`：

- 方便前端统一查询。
- 方便权限过滤。
- 方便 dashboard 展示。
- 方便跨 workflow 类型搜索。

Temporal 是执行真相源，业务 task 表是产品读模型和审计入口。

## Auth 选型

### 可选 1：Auth.js

适合：

- 想自主管理 auth。
- 需要 Next.js 深度集成。
- 预算敏感。

需要自建：

- 组织。
- 邀请。
- RBAC。
- session hardening。

### 可选 2：Clerk

适合：

- 快速上线 SaaS。
- 内置组织、邀请、session 管理。
- 接受商业服务依赖。

仍需自建：

- 项目级权限。
- 租户数据隔离。
- 用量和计费。

### 推荐

如果以最快产品化为目标，用 Clerk。
如果以完全自控和开源部署为目标，用 Auth.js + 自建组织表。

文档后续默认不绑定供应商，只要求 Go API 接收可信 auth claims 并映射到内部 `users` / `tenants` / `memberships`。

## 参考资料

- Next.js App Router: https://nextjs.org/docs/app
- Go `net/http`: https://pkg.go.dev/net/http
- Temporal Go SDK: https://docs.temporal.io/develop/go
- Temporal Python SDK: https://docs.temporal.io/develop/python
- PostgreSQL Row Security Policies: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- pgvector: https://github.com/pgvector/pgvector
- React Flow: https://reactflow.dev/
- Tiptap: https://tiptap.dev/docs
