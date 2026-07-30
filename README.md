# MiroFish-Novel

MiroFish-Novel 是一个面向长篇小说创作的多智能体分析与写作平台。它把小说、设定、大纲、角色卡和自由素材转化为可检索的故事知识，通过单世界 Worldline 和 Writer Agent 帮助作者完成推演、创作、审校与手稿管理。

> 当前活跃产品是 `apps/* + infra/*` 的 SaaS 实现。根目录旧 `frontend/` 已退役并删除；`apps/web` 是唯一前端代码和 Web 构建上下文。`backend/` 仅作 Legacy import/兼容参考，不是产品运行时。

## 核心产品链

```text
上传小说 -> Seed Pipeline -> Story Graph / Assets -> Worldline / Character -> Writer Agent -> Manuscript
```

- **Seed Pipeline**：解析 TXT / Markdown / PDF，执行分段精读、全局聚合、ontology 和角色档案生成。
- **Story Graph / Assets**：管理角色、组织、关系、事件、伏笔、世界规则和写作素材。
- **Single-world Worldline**：围绕唯一 `current_world` 执行变量注入、剧情推演和角色互动。
- **Writer Agent**：以连续 Agent thread 作为主交互，流式呈现工具活动与候选正文，并在 artifact workspace 中管理稿件、章节、审校和规划。
- **LLM Facility**：统一管理渠道、模型、模块绑定、配额、用量与隐私边界。

## 技术架构

| 责任 | 技术 / 目录 |
|---|---|
| Web 产品 | Next.js 15 + React 19 + TypeScript，`apps/web` |
| Control Plane | Go HTTP/RBAC/workflow admission/read side，`apps/api` |
| 领域 Agent Runtime | Python + Temporal，`apps/agent-runtime` |
| Writer Agent Runtime | TypeScript + Pi Agent + Temporal，`apps/pi-agent-runtime` |
| 数据与基础设施 | Postgres + Redis + Temporal + MinIO，`infra` |

## 快速启动

需要 Git、Docker Desktop 或 Docker Engine，以及 Docker Compose v2。首次启动会构建
Web、API 和 Agent Runtime 镜像，并初始化本地 Postgres、Redis、Temporal 与 MinIO。

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml up -d --build
```

- Web：`http://localhost:3999`
- API：`http://localhost:3888`
- Readiness：`http://localhost:3888/readyz`

停止服务：

```bash
docker compose -f infra/docker-compose.yml down
```

LLM 模块未绑定时必须显式失败。不要用环境变量单渠道 fallback、mock 成功或伪数据绕过 LLM Facility。

## 开发与验证

```bash
# Go control plane
cd apps/api
go test ./...

# Next Web
cd apps/web
npm test
npm run typecheck
npm run build

# Python Agent Runtime
cd apps/agent-runtime
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests -q

# Pi Writer Runtime
cd apps/pi-agent-runtime
npm test
npm run typecheck
npm run build
```

会写入数据库、对象存储或队列的 live/E2E 测试必须使用独立测试栈：

```bash
infra/scripts/run-live-test-stack.sh -- <command>
```

需要 API/Web 时使用 `--app`。禁止把任何 `*_LIVE_DATABASE_URL` 指向主 `mirofish` 数据库。

## 目录责任

```text
apps/
  api/               Go control plane
  web/               唯一 Next.js 前端
  agent-runtime/     Seed / Graph / Asset / Worldline workers
  pi-agent-runtime/  Pi Writer Agent runtime
infra/               Postgres / Redis / Temporal / MinIO / deployment
docs/refactor-saas/  SaaS 范围、契约和当前进度
tasks/               活动任务板
backend/             Legacy import / compatibility reference only
```

本机缓存、参考仓库、测试数据库、上传物和生成素材不属于发行内容，均由
`.gitignore` 排除。公开仓库不依赖任何未声明的 Git submodule。

`docs/plans/` 和 `docs/superpowers/` 是历史设计记录。其中指向旧 `frontend/`、Vue/Vite 或旧 Writer 长页的命令不是当前开发入口。

## 开发约束

- 候选 draft/canon 更改不能自动采用，必须是用户动作或明确策略。
- 所有 SaaS 数据路径必须携带 tenant/project/run 上下文并经过 RBAC/RLS。
- 不记录或渲染 API Key、凭证、系统 prompt、provider body、用户小说原文或私有 trace。
- 不恢复多分支 Worldline、旧 LLM 环境变量 fallback、旧蓝色前端或表单堆叠式 Writer 长页。
- 工作区可能存在并行未提交改动；编辑前先运行 `git status --short`，不覆盖他人改动。

## 真相源

1. `docs/refactor-saas/DEVELOPMENT_PLAN.md`：范围、阶段和最终完成定义。
2. `docs/refactor-saas/24-current-development-progress.md`：唯一当前进度、关键路径和验证新鲜度入口。
3. `tasks/refactor-saas-parallel-board.md`：活动任务、依赖与 next gate。
4. 当前 worktree、schema 和本轮测试输出：冲突时的最终事实。

## 贡献与许可

提交前请阅读 `CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md` 和
`SUPPORT.md`。Pull request 会运行 Go、Python、Next.js、Pi Runtime 与共享契约检查。
不要提交 API Key、用户小说原文、私有数据库、上传产物或 LLM trace。

本项目使用 `AGPL-3.0-only` 许可，详见 `LICENSE`。

本项目部分能力源自 [MiroFish](https://github.com/666ghj/MiroFish)，并自
2026 年 3 月起针对长篇小说创作和 SaaS 架构进行了实质性重构。来源与修改声明见
`NOTICE`。
