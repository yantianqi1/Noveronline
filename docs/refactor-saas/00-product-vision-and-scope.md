# 00. Product Vision and Scope

更新时间：`2026-07-13`

## 一句话定位

`MiroFish-Novel SaaS` 是面向长篇小说作者、工作室和 AI 写作团队的多智能体创作平台。它把小说文本、设定、大纲、角色卡和自由素材转换成可检索、可推演、可审计、可写作引用的故事世界数据，并通过 Agent 辅助作者完成分析、灵感推演、互动写作、正文生成和审校。

## 这次重构的产品目标

当前项目更像本地单人工作台。重构后的目标是公网 SaaS：

- 用户可以打开一个网站注册、登录、创建项目并开始写作。
- 每个用户看到自己的项目、素材、任务、LLM 配置和用量。
- 支持组织/团队，多人协作同一小说项目。
- 支持多人并发上传、分析、构图、推演和写作。
- 支持长任务恢复、重试、追踪和费用统计。
- 支持管理员运营、用户支持、限流、审计和安全隔离。
- 保留并增强当前所有旧功能，不因为 SaaS 化而砍掉 Agent 能力。

## 核心主链

目标系统仍以旧系统主链为基础：

```text
上传小说 / 设定 / 大纲 / 角色卡
  -> Seed Pipeline
  -> Ontology / Canon Tables / Story Graph
  -> Archives / Asset Library
  -> Worldline 推演
  -> Character Console 互动写作
  -> Writer Workbench 正文生成
  -> Manuscript / Review / World Data Update
```

重构不是换掉主链，而是把主链产品化、多人化、可部署化。

### 零起点写作与反向知识主链（规划契约）

新项目不应被强制先上传旧稿再开始写作。目标产品提供两条对等入口：

- `从一个想法开始` 让空项目直接进入 Writer，建立故事前提、book plan、章节/场景，再由用户手写或启动 Writer draft。该入口不要求 Seed，也不自动生成 canon 或 manuscript。
- `上传已有文本` 继续走 Upload -> Seed -> Assets / Graph -> Writer 主链，不为新入口削弱长文分析能力。

写作链同时需要反向回馈知识链：只从已持久化的 manuscript 检查点或显式采用的 draft 增量提取角色、关系、世界规则、地点、物件和剧情线索。所有提取结果先作为 `candidate + disabled` 保存，未经人工审阅不得进入 canon、manuscript 或 Writer 检索上下文。

完整产品、API、生命周期、UI 和分期设计见 [28. Zero-start Writer and Manuscript Asset Distillation](./28-zero-start-writer-and-manuscript-asset-distillation.md)。该方案当前是待实现目标，不代表现有产品已通过验收。

## 用户角色

### 个人作者

典型需求：

- 上传自己的长篇小说或设定。
- 让系统建立角色、关系、势力、伏笔和世界规则。
- 在世界线里测试剧情变量。
- 进入角色视角互动探索剧情。
- 在写作台里生成、续写、审校章节。

权限特点：

- 拥有自己的个人 workspace。
- 默认只能访问自己的项目和素材。
- 可以配置自己的 LLM 渠道，或使用平台提供的模型配额。

### 工作室作者

典型需求：

- 多个编辑、作者、设定专员共用同一系列小说项目。
- 分工维护角色卡、世界观、剧情线和章节稿件。
- 管理谁可以上传原文、谁可以采用世界线事件、谁可以发布定稿。

权限特点：

- 属于一个组织 tenant。
- 项目内有 owner、editor、writer、viewer 等角色。
- 需要操作审计和版本历史。

### 平台管理员

典型需求：

- 管理租户、用户、套餐、配额和模型渠道。
- 查看任务失败率、LLM 用量、成本和系统健康状态。
- 处理滥用、数据删除、封禁和用户支持。

权限特点：

- 管理控制台与作者工作台分离。
- 默认不能随意查看用户小说原文；敏感数据访问必须有审计。

### Agent / Worker

系统内部执行者：

- seed worker
- graph worker
- asset ingestion worker
- worldline worker
- writer worker
- reviewer worker
- search index worker

权限特点：

- 通过 service identity 访问数据。
- 每次任务必须携带 `tenant_id`、`project_id`、`run_id`。
- Worker 只能访问任务授权范围内的数据。

## 旧功能覆盖范围

### 必须覆盖的页面

| 旧页面 | 新位置 | 覆盖要求 |
|---|---|---|
| `/` 总览 | Project Dashboard | 项目列表、上传入口、seed 任务状态、最近项目、任务续传、失败重试 |
| `/story-graph` 故事图谱 | Story Graph Workspace | 图谱构建、图谱浏览、筛选、节点/边详情、证据、羁绊/支线生成 |
| `/assets` 资产库 | Asset Library | 统一资产、搜索、facets、详情、档案记忆、资产入库 Agent、重建索引 |
| `/worldline` 世界线 | Worldline Studio | 选择角色/档案、变量注入、prepare、自动演化、候选事件采用 |
| `/character-console` 角色控制 | Character Console | 选择 session/角色、第一人称互动、动作、对话、历史、记忆 |
| `/writer` 写作台 | Writer Workbench | 章节、场景、正文生成、续写、审校、手稿、工具 trace |
| `/guide` 帮助指南 | Guide / Onboarding | 工作流说明、空状态引导、模块依赖说明 |
| `/llm-facility` 设施面板 | LLM Facility | 渠道、模型、模块绑定、活动追踪、租户级配额 |

### 必须覆盖的后端能力

- 项目 CRUD、删除级联、项目目录迁移。
- TXT / MD / PDF 上传和解析。
- seed pipeline 长任务、分段、顺序精读、全局聚合、ontology、角色 Agent 档案。
- step trace、prompt/response trace、失败重试、断点续传。
- graph build 长任务、图谱快照、节点、边、证据。
- archive candidate / archive generation / archive memory review。
- asset CRUD、batch toggle、batch categorize、asset ingestion、style extraction。
- unified asset view、global search、facets、reindex。
- worldline prepare、session、runtime、agent roster、timeline、variable injection、auto-evolution、event adoption、agent actions/dialogues/memory。
- character console 对 worldline runtime 的读写。
- writer agent run、world update、chapter/scene/manuscript/preset/book plan/reviewer/dedup/one-click actions。
- LLM channels、models、module bindings、activity、concurrency。

## 新增 SaaS 范围

### 用户与租户

- 用户注册、登录、登出。
- 组织/团队 workspace。
- 项目成员与角色权限。
- 邀请成员。
- 租户级 LLM 配置和个人级覆盖。
- 租户级配额、限流和用量统计。

### 并发与隔离

- 多用户可以同时上传和分析不同小说。
- 同一项目可以有多个任务排队，但有明确互斥规则。
- 同一项目的写作、资产维护和图谱浏览可以并发。
- 数据隔离以 `tenant_id` 为第一约束，不依赖前端隐藏。
- 所有后台任务携带租户上下文。

### 运营与安全

- 审计日志。
- API 限流。
- 文件扫描和大小限制。
- 租户级数据导出和删除。
- LLM trace 脱敏视图。
- 管理员不能无审计地读取用户正文。

## 非目标

当前重构不做：

- 社交平台、舆情、Twitter、Reddit 或 sentiment-analysis 功能。
- 多世界分支重新成为主模型。
- 把所有 Agent 逻辑强制重写成 Go。
- 做纯营销落地页替代产品工作台。
- 用 mock 成功或伪数据掩盖未完成流程。

## 成功标准

### 产品成功标准

- 新用户注册后可以创建项目、上传小说并看到可理解的分析进度。
- seed 完成后，资产库、故事图谱、世界线和写作台都能消费同一套项目数据。
- 作者能在世界线里保存发展路径，并在写作台明确选择是否引用。
- 作者能在角色控制里完成互动记录，并转化为章节草稿。
- 写作台能从资产、图谱、worldline、角色互动和章节历史中检索上下文。

### 技术成功标准

- 任意业务表都包含或可追溯到 `tenant_id`。
- 后台任务可恢复、可重试、可取消、可追踪。
- 任务进度、Agent trace 和 LLM activity 不依赖单进程内存。
- 大文件和上传产物不进入 git，不存数据库大字段。
- Postgres RLS 或等价租户隔离策略通过测试验证。
- 单租户和多租户模式共用同一套代码路径。

### 迁移成功标准

- `18-legacy-coverage-matrix.md` 中每一项旧功能都有目标模块。
- 旧项目数据能导入新数据模型。
- 旧接口语义有兼容或明确替代。
- 旧页面功能不会在新 UI 中消失，只会重新组织。
