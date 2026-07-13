# 作者登录后工作流贯通审计

审计日期：`2026-07-12`

## 文档定位

本文记录“单个小说作者登录网站后，能否从空项目自然完成创作主链”的时点审计结果，重点检查真实运行条件、跨页面 handoff 和作者体验。

本文不是新的进度真相源，不替代：

1. `DEVELOPMENT_PLAN.md`：范围与最终完成定义。
2. `24-current-development-progress.md`：唯一当前进度入口。
3. `tasks/refactor-saas-parallel-board.md`：活动目标与 next gate。
4. 当前 worktree、schema、运行中 Compose 和本轮测试：冲突时的最终事实。

本文发现与当前进度文档冲突时，应先修复产品或重新取得证据，再校准进度文档；不得用本文直接机械改写任务状态。

## 审计结论

当前项目具备较完整的领域能力、健康的本地 Compose 和大量隔离 live/browser 证据，但普通作者的自然点击路径尚未完全贯通。

当前可定性为：

- 可进入开发内测。
- 在人工补齐配额并知道内部跳转方式时，可以分段试用主要能力。
- 不能对外宣称“作者登录后可自然、流畅地从上传小说走到审校与导出”。
- Real Legacy cutover 仍是 MAIN-100 的独立授权 gate，但不是新作者主链断点的原因。

## 目标作者工作流

预期的正常流程为：

```text
登录 / 注册
  -> 个人工作区与首个项目
  -> LLM Facility 就绪检查
  -> 上传 TXT / MD / PDF
  -> Seed Pipeline
  -> Assets
  -> Story Graph
  -> single-current-world Worldline
  -> Character Console
  -> Pi Writer
  -> Reviewer
  -> 作者显式 adoption
  -> Manuscript
  -> TXT 导出
```

返回用户登录后当前会进入第一个有效项目的 Overview，而不是恢复上次停留页面。主导航顺序为 Overview、Assets、Story Graph、Worldline、Character Console、Writer，LLM Facility 位于项目设置中。

## 当前运行证据

审计时的只读运行证据：

| 范围 | 当前事实 |
|---|---|
| Compose | API、Web、Postgres、Redis、Temporal、MinIO、Pi Runtime 和领域 workers healthy |
| Readiness | `GET /readyz` 返回 `200`，Postgres/schema、Redis、Temporal pollers、object storage 均 ready |
| Auth | `/login`、`/signup` 可访问；未登录项目路由重定向 `/login`；未登录 API 返回 `401`；development auth endpoint 返回 `404` |
| Schema | migration ledger 共 `16` 条，最新为 `0016_workspace_membership_scope_backfill` |
| 主库账号 | `1 user / 1 workspace / 1 project / 2 active sessions` |
| 主库创作数据 | `source_files / workflow_runs / assets / worldline_sessions / character_sessions / writer_runs / manuscript_blocks` 均为 `0` |
| LLM 配置 | `1` 个启用 external HTTPS channel、`50` 个模型、`26` 个项目级 module bindings |
| LLM 配额 | `llm_quota_policies = 0`、`llm_quota_reservations = 0` |
| LLM 活动 | 主库 `llm_activity = 0`；当前真实项目没有 Provider 调用记录 |
| Embedding | `asset_search_embedding` 未绑定，当前 Provider 没有 embedding model |
| OCR | Seed worker 已配置 Tesseract，安装 `chi_sim`、`eng`、`osd` |
| Worktree | 分支 `codex/saas-mainline`；大量未提交改动，尚非可复现 release baseline |

本轮代码验证：

- Go API：`go test -count=1 ./...` passed。
- Web：`194 passed, 8 skipped`；typecheck passed。
- Pi Runtime：`71 passed, 4 skipped`。
- Python 关键 Seed/Graph/Worldline/Planning/Review：`265 passed`。
- `git diff --check` passed。

上述结果证明当前代码和服务没有明显基础回归，但不等价于同一真实作者、同一项目、当前 external Provider 的连续产品旅程通过。

## 问题清单

### AWF-001：当前项目缺少 LLM 配额策略

严重级别：`blocker`

当前主库已有 `26` 个项目级模块绑定，但 `llm_quota_policies = 0`。Go 与 Python Provider admission 在找不到适用策略时都会 fail closed 为 `LLM_QUOTA_POLICY_UNAVAILABLE`。

影响：

- Seed 可以完成上传、解析等前置步骤，但首次语义 LLM 阶段无法完成。
- Graph、Worldline、Character、Writer、Reviewer 等真实 Provider 调用无法完成。
- Provider health 通过只能证明 transport/channel/credential 可用，不能替代 quota reservation、usage、activity 和 trace 成功链。

代码证据：

- `apps/api/internal/llm/quota_policy.go`：`Reserve` 在无 policy 时显式失败。
- `apps/agent-runtime/mirofish_agents/llm_quota/postgres.py`：Python worker 在无 policy 时显式失败。
- `apps/web/components/llm-facility-shell.tsx`：UI 明确提示“尚未配置配额策略，生产调用将关闭失败”。
- 各 live fixture 会主动插入 `llm_quota_policies`，因此隔离 E2E 通过不能证明当前主项目已配置。

关闭条件：

- 新项目存在明确、可审计的适用 quota policy，或作者完成可发现的首次配额设置。
- 使用当前项目执行至少一次真实 quota reserve/finalize，产生 usage、`llm_activity` 和 private trace。
- 无 policy 时在上传或启动 workflow 前给出可操作的 LLM Facility 跳转，不允许任务运行到中途后只显示通用失败。

### AWF-002：注册和 Overview 缺少 LLM onboarding / preflight

严重级别：`high`

注册事务只创建 user、credential、session、personal tenant、membership、首项目和 project membership，不创建 channel、module binding 或 quota policy。当前数据库也没有 platform module defaults。

注册成功后页面直接进入 Overview，Overview 默认主动作是“上传并开始分析”，没有先检查以下条件：

- 所需 Seed 模块是否已绑定。
- credential 是否可解密。
- external opt-in 是否满足。
- quota policy 是否适用。
- Provider 是否具备目标能力。

失败后 Overview 丢弃具体错误原因，只显示“操作未完成，请检查输入或稍后重试”，作者无法判断应前往 LLM Facility。

关闭条件：

- 新账号首次进入项目时显示创作就绪检查。
- 未完成 LLM 配置时，Overview 主动作改为“完成模型与预算设置”，并链接到准确模块/配额页面。
- 错误面向作者说明“发生了什么、影响是什么、如何恢复”，不暴露 credential、prompt、Provider body 或内部堆栈。
- 注册浏览器测试必须覆盖“空租户 -> 完成 LLM 设置 -> 首次 workflow 成功”，不能只验证 cookie 和 Overview redirect。

### AWF-003：Worldline preparation 未自然传递到 Character Console

严重级别：`high`

Worldline 准备角色后仅提供“刷新准备状态与角色”，没有进入 Character Console 的 CTA，也没有把 `anchor_session_id`、`prepare_id` 或 saved path 带入下一页面。

Character Console 只有在 URL query 已包含 `prepare_id` 时才加载 prepared agents；普通侧栏点击进入 Character 后，POV agent 为空。当前角色准备记录输入已改为 hidden，但页面没有 preparation 列表或恢复选择器，因此不能从 UI 自行找回上下文。

现有 Worldline/Character browser live 测试通过 `page.goto(...?anchor_session_id=...&prepare_id=...)` 手工构造目标 URL，未证明普通用户可以点击完成 handoff。

关闭条件：

- Worldline preparation ready 后显示“进入角色控制”主动作。
- 跳转携带 typed、owner-validated 的 session/preparation/saved-path 引用。
- Character Console 可列出并恢复当前项目的可用 preparation，不依赖用户填写或知道内部 ID。
- Browser E2E 必须从 Worldline 页面点击进入 Character，不允许用手工拼 query 替代产品导航。

### AWF-004：Character 转稿后未进入 Writer

严重级别：`high`

Character 的“转章节草稿”会创建 Writer run，但成功后仍停留在 Character 页面，仅显示“章节候选草稿任务已提交”。结果 run id 保存为 `runtime_run_id`，Writer 页面只识别 `runId`，页面没有“在写作台查看”链接。

现有 browser live 测试从 Character URL 读取 `runtime_run_id` 后直接调用 API 轮询 Writer run，未通过 Writer UI 完成查看、恢复和 adoption。

关闭条件：

- 创建 Writer run 后提供“在写作台查看”CTA，目标为 Writer 的公开 workspace route，并携带正确 `runId`。
- Writer 能从 handoff 打开对应 run、恢复 stream/events、展示 candidate draft。
- E2E 必须点击进入 Writer，完成显式 adoption、review、manuscript 和 export；API 轮询只能作为辅助断言，不能替代 UI 旅程。

### AWF-005：无 embedding 能力时仍展示 vector / hybrid 搜索

严重级别：`medium`

Assets 搜索 UI 无条件展示：

- 精确文字 `keyword`
- 含义相近 `vector`
- 智能匹配 `hybrid`

当前 Provider 没有 embedding model，`asset_search_embedding` 未绑定。选择 vector/hybrid 后，后端会显式返回 binding/provider/index unavailable，但页面只显示通用失败。

关闭条件：

- 搜索模式由真实 module resolution、model capability 和 index readiness 决定。
- 不可用模式应隐藏或 disabled，并给出简短原因与配置入口。
- Keyword 搜索必须始终保持可用，不能把向量失败静默降级为伪 hybrid 成功。
- Browser E2E 增加普通无 embedding 项目，验证不可用模式不会被误导性展示。

### AWF-006：Writer 主视图仍暴露内部 ID 和命令枚举

严重级别：`medium`

Writer 作者主界面仍包含或要求填写：

- `chapter_id`、`scene_id`、`block_id`。
- 逗号分隔的内部排序数据。
- `complete_outline`、`align_words`、`scan_lexicon` 等内部 command key。
- `command_run_id`、`workflow_type`、`error_code`、`export_id`。
- 手动 saved path IDs。

这与 `26-frontend-ux-optimization.md` 的内容边界冲突：UUID、内部错误码和运行细节不应进入作者 UI。现有内容边界测试正则覆盖过窄，因此测试为绿仍遗漏这些投影。

关闭条件：

- 章节、场景、正文块和路径均使用标题、顺序、摘要或可搜索选择器。
- 内部命令映射为作者语言和明确动作。
- run/export/error identifiers 只进入授权诊断抽屉，作者主视图显示状态、影响和恢复动作。
- 内容边界测试扫描实际 JSX 投影和 browser DOM，不只匹配少量固定表达式。

### AWF-007：当前证据不能证明真实作者连续使用

严重级别：`high`

当前主库创作数据和 `llm_activity` 均为空。历史 browser/live 证据按领域使用隔离 fixture、本地 Provider 或直接 API 轮询，证明了局部能力，但没有证明：

- 当前真实账号。
- 当前真实项目。
- 当前 external Provider。
- 当前 API/worker 镜像。
- 从空项目到导出的同一连续旅程。

当前 worktree 还有大量未提交文件，HEAD 不能代表运行实例的完整产品状态，发布、回滚和复现风险较高。

关闭条件：

- 使用 `infra/scripts/run-live-test-stack.sh --app -- <command>` 创建独立数据库和 volumes。
- 从全新注册账号开始，不预置领域产物。
- 通过产品 UI 完成 LLM onboarding、上传、Seed、Assets、Graph、Worldline、Character、Writer、Review、adoption、Manuscript 和 TXT download。
- 使用明确授权的 non-local HTTPS Provider，并验证 binding、credential、quota、usage、activity、private trace 和 public privacy。
- E2E 结束后 `down -v`，不得写主 `mirofish` 数据库。
- 验收镜像绑定可复现 commit，并记录本轮 build/test/runtime 证据。

## 文档与状态漂移

当前进度文档将 `LLM Facility binding/quota/usage/trace/provider health` 标为当前已验证，但主项目实际 `llm_quota_policies = 0`、`llm_activity = 0`。这说明隔离 fixture 证据与当前实例就绪状态被混为一谈。

另有 migration 数字漂移：

- `24-current-development-progress.md` 摘要写 `15 migrations readiness`。
- 同文后续和当前数据库实际为 `16`。
- 活动任务板的中央证据仍写 migration `14`。

这些文档问题不直接阻塞作者操作，但会导致错误的“已经完全打通”判断。校准时应区分：

```text
domain implementation verified
!= isolated fixture journey passed
!= current instance configured
!= natural author click path passed
!= reproducible release complete
```

## 修复顺序

建议按以下顺序关闭，不先做无关视觉重构：

1. `AWF-001`：补齐当前项目 quota policy 与真实 Provider 调用证据。
2. `AWF-002`：增加新作者 LLM readiness onboarding 和 Overview preflight。
3. `AWF-003`：打通 Worldline -> Character typed handoff。
4. `AWF-004`：打通 Character -> Writer -> adoption 产品 handoff。
5. `AWF-005`：按 embedding capability/index readiness 控制搜索模式。
6. `AWF-006`：移除作者主视图中的 raw IDs、内部枚举和错误码。
7. `AWF-007`：在独立 live-test stack 上执行当前镜像的全作者旅程，并冻结可复现 release 证据。

## 最终验收定义

只有同时满足以下条件，才能宣称“一个小说作者登录后可以流畅完成主链”：

- 登录后无需了解 tenant/project UUID、run ID、prepare ID、chapter ID 或内部 command key。
- 首次使用能明确完成 Provider、模块和配额设置，或继承可审计的平台默认值。
- 上传前能判断 LLM readiness，不会在长任务中途才发现配置缺失。
- Seed 完成后可自然进入 Assets 和 Graph。
- Worldline 可点击进入带上下文的 Character Console。
- Character 可点击进入对应 Writer run。
- Writer candidate 必须由作者显式采用，之后可审校、编排 manuscript 并下载非空 TXT。
- 刷新、重连、取消、重试均可恢复，错误包含明确恢复动作。
- 当前 external Provider 的 quota、usage、activity、trace 和 privacy 证据齐全。
- 同一浏览器旅程在桌面和移动视口无 pageerror、无横向溢出、无敏感信息泄漏。
- 主库保持无测试污染，验收环境退出后完整销毁。
- 当前 release 对应可复现 commit、镜像和 migration ledger。

在上述条件全部满足前，项目应表述为“核心能力已实现、可内测”，不应表述为“作者主链已完全打通并可流畅使用”。
