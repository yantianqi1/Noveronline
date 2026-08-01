# 作者友好优化开发实现方案（Agent 执行版）

更新时间：`2026-07-14`

## 文档职责

本文把 `34-author-friendly-experience-plan.md` 的 10 个作者可见目标转换为可执行的工程任务。

本文是实施蓝图，不是当前进度真相源。开始实施前仍必须按顺序读取：

1. `DEVELOPMENT_PLAN.md`
2. `24-current-development-progress.md`
3. `tasks/refactor-saas-parallel-board.md`
4. 当前 worktree、schema 和本轮测试输出

任何条目只有在实现、focused tests、受影响回归和需要的 live/browser 证据通过后，才能更新当前进度文档。不得因为本文存在就把功能标记为完成。

## 当前事实与不重复开发项

- Writer 已是 `manuscript-primary`：左侧结构、中间手稿、右侧常驻 Agent dock。不得恢复旧蓝色长页、`writer-studio-grid`、深色 rail 或半屏聊天。
- TipTap、选区修订、行内 diff、持久 thread、SSE、审批和显式 adoption 已有连通代码；本计划是在这些路径上修复安全边界和新手体验，不重建 Writer。
- 注册事务当前已经创建默认 tenant quota policy，但模块解析仍有 `project > tenant > platform > unbound` 的平台付费 fallback。根据最新商业规则，普通客户必须连接 tenant-owned credential；平台 credential 只有在存在明确、可审计的赠送额度或订阅权益时才能使用。默认 quota policy 只是内部安全上限，不代表平台免费提供模型。
- 当前 worktree 有并行的 Analysis / Asset Import 改动。实施前必须重新运行 `git status --short`；重叠文件要合并用户改动，不得回退。
- 当前 fresh authenticated browser 视觉证据仍未闭合。没有真实浏览器运行结果时，不得从源码检查推导“视觉验收通过”。

## 全局工程约束

1. 作者正文始终高于 Agent 建议；Agent 只能产出 candidate/proposal，不能静默覆盖 manuscript/canon。
2. 任何修订都必须绑定生成时的 block version 和 selection text；不匹配时 fail conflict。
3. 小说正文不得进入 URL、浏览历史、公开事件、普通日志或错误消息。
4. LLM 调用继续只走 Facility module binding；普通 tenant 必须解析到自己的 credential，或解析到带有效 entitlement 的 platform credential。不新增环境变量 fallback、mock success、无权益平台兜底或自动降级。
5. 作者投影只返回完成当前操作需要的字段；raw IDs、tool keys、provider details 和内部错误进入授权 Technical Details。
6. 新的数据库表必须使用新 migration、FORCE RLS、最小 grants 和 app-role live isolation；不得编辑已应用 migration。
7. 所有会写数据库、对象存储或队列的 live/E2E 必须通过 `infra/scripts/run-live-test-stack.sh --app -- <command>`。
8. 交互目标在移动端至少 `44x44px`，正文和表单正文至少 `16px`；所有恢复动作支持键盘和屏幕阅读器。

## 统一作者词典

新增集中式作者语言映射，建议入口为 `apps/web/lib/author-copy.ts`。作者页面不得在组件内自行 `replace("query_", "")` 或直接 humanize 未知枚举。

| 内部含义 | 作者界面文案 |
|---|---|
| `query_project_context` | 查看本书设定 |
| `query_chapter_scene` | 查看章节与场景 |
| `query_assets` | 查找人物与设定 |
| `query_manuscript_context` | 查看前文 |
| `query_world_rules` | 核对世界规则 |
| `query_character_profile` | 核对人物设定 |
| `query_graph_neighbors` | 核对人物关系 |
| `query_worldline_paths` | 参考剧情推演 |
| runtime-owned draft persistence | 保存修改建议（不作为模型工具暴露） |
| 未知工具 | 处理写作请求 |
| `queued` / `running` | 等待开始 / 正在处理 |
| `failed` | 未完成 |
| `completed` | 已完成 |

未知值必须使用安全的通用文案，不能把内部值回显给作者。原值只可进入受权限保护的诊断视图。

## Wave 1：正文、项目与模型费用安全

### AF-01 过期修订必须进入冲突状态

**当前证据**

- `apps/web/lib/writer-revision.ts` 在 selection text 与当前 slice 不一致时，只要旧 offset 仍在范围内就继续构造 `proposedText`。
- Writer page 把当前 block version 作为 `expectedVersion` 传入，覆盖了事件生成时的版本语义。

**目标契约**

将修订解析结果改为显式联合状态，例如：

```ts
type RevisionProposalState =
  | { status: "ready"; proposal: PendingRevision }
  | { status: "stale_version"; eventId: string; currentVersion: number; eventVersion?: number }
  | {
      status: "stale_selection";
      eventId: string;
      recordedSelection: string;
      proposedSelection: string;
      currentSlice: string;
    }
  | { status: "unavailable" };
```

- 事件版本与当前 block version 不同：不得生成可接受 patch。
- 当前 slice 与事件 `selection_text` 不同：不得按旧 offset 替换。
- 事件缺 version 时仍必须以 selection exact match 为最低安全条件。
- 冲突 UI 固定提供“按当前文字重新修改”“比较两版”“保留我的文字”。
- “接受修改”继续走现有 optimistic block update；冲突不得自动 retry accept。

**主要文件**

- `apps/web/lib/writer-revision.ts`
- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx`
- `apps/web/components/writer-manuscript-editor-inner.tsx`
- `apps/web/components/writer-revision-diff.tsx`
- `apps/web/components/writer-manuscript-panel-client.tsx`
- `apps/web/tests/writer-conflict-revision.test.mjs`

**测试先行**

1. 当前正文 `alpha ZETA gamma`，旧事件为 `beta -> BETA`：结果必须是 `stale_selection`，绝不能得到 `alpha BETA gamma`。
2. selection text 相同但 event version 落后：结果必须是 `stale_version`。
3. version 和 selection 都匹配：仍可生成 ready proposal。
4. conflict 状态下没有可提交的 accept action；重新生成使用当前正文、当前选择和当前版本。

### AF-02 正文从 URL 和公开记录中彻底移除

**当前证据**

- Writer `workspaceRedirect` 会把最多 3500 字符的 `localDraft` Base64 放进 query string。
- `writer-manuscript-panel-client.tsx` 同时使用 query 和 `sessionStorage` 恢复冲突稿。

**实现决策**

使用受保护的临时恢复稿作为权威恢复路径，URL 只携带 opaque `recoveryId`。`sessionStorage` 只作为当前标签页的快速镜像，不能成为唯一恢复来源。

- 在实施时选择下一个未占用 migration 编号，不得假定当前 next migration 编号。
- 新表建议为 `manuscript_recovery_drafts`：`tenant_id`、`project_id`、`recovery_id`、`block_id`、`actor_user_id`、`base_version`、`content_text`、`expires_at`、`resolved_at`、timestamps。
- 冲突检测与恢复稿写入必须在同一个事务中完成；409 公开响应只返回恢复 ID 和作者可用状态，不返回正文。
- 恢复稿必须 tenant/project/actor scoped，启用并强制 RLS；跨项目、跨用户和跨租户读取全部 fail closed。
- 保留期通过配置定义并在冲突 UI 中解释，不写死无说明的截断或静默删除。
- 解决冲突后标记 resolved；后台按保留规则清理，不把正文写入清理日志。
- 删除 `encodeLocalDraft` / `decodeLocalDraft` 的 URL 用途；跳转参数只保留 `recoveryId`、`blockId` 和公开状态。

**主要文件**

- 新 migration：实施时取 next unused revision
- `apps/api/internal/manuscriptworkspace/store.go`
- `apps/api/internal/manuscriptworkspace/types.go`
- `apps/api/internal/manuscriptworkspace/handler.go`
- `apps/web/lib/writer-workspace-api.ts`
- `apps/web/lib/writer-local-draft.ts`
- `apps/web/components/writer-manuscript-panel-client.tsx`
- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx`
- `apps/web/tests/writer-conflict-revision.test.mjs`

**验收**

- conflict 后地址栏、浏览历史、Referer、公开错误和服务访问日志均不含原文或其 Base64。
- 刷新和重新登录后，原作者仍可恢复未解决草稿。
- foreign actor/project/tenant 使用 recovery ID 得到 not found/forbidden，不能探测正文是否存在。
- JS 可用和 `<noscript>` 保存路径都不丢稿。

### AF-03 Idea-first bootstrap 原子化与幂等

**当前证据**

Overview server action 依次调用 `createBookPlan`、`createChapter`、`createScene`。任一步失败都会留下前面已提交的数据。

**目标契约**

新增一个领域命令：

```text
POST /v1/projects/{projectId}/writer-bootstrap
Idempotency-Key: <request id>
```

请求只接收作者输入的书名、故事想法和第一章标题；响应一次返回 plan/chapter/scene 的公开引用。

- `SQLStore.BootstrapIdeaWorkspace` 在单个 tenant transaction 中创建全部对象。
- 同一 request ID 重试返回第一次结果，不重复创建。
- 对同一空项目加 project lock；已有有效 bootstrap 时返回现有结果或显式 conflict，不追加“第一章（2）”。
- 任意插入失败都 rollback。
- Web 使用一个 API 调用，提交期间按钮 disabled 并显示“正在准备第一章”。
- 此路径不依赖 LLM readiness。

**主要文件**

- `apps/api/internal/writerworkspace/types.go`
- `apps/api/internal/writerworkspace/store.go`
- `apps/api/internal/writerworkspace/handler.go`
- `apps/api/internal/writerworkspace/handler_test.go`
- `apps/api/internal/writerworkspace/writerworkspace_live_test.go`
- `apps/api/internal/httpapi/server.go` 的 route allowlist
- `apps/web/lib/writer-workspace-api.ts`
- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx`
- `apps/web/tests/author-journey-contract.test.mjs`

**验收**

- 注入 plan/chapter/scene 任一点失败，数据库对象计数保持 0。
- 模拟响应丢失后用相同 key 重试，只存在一套 plan/chapter/scene。
- 快速双击只产生一套第一章。
- 成功后通过公开 route 进入对应章节，不向用户显示 ID。

### AF-04 客户自备模型连接向导与平台费用边界

**商业规则**

- 平台不向普通客户免费提供模型调用。
- 个人工作区 owner 和团队工作区 owner/admin 必须提供自己的 AI 服务 credential，才能启动 AI 写作、分析、审校和其他 LLM workflow。
- 平台 credential 仅可用于明确赠送额度、订阅套餐或内部测试；必须有 tenant-scoped entitlement 和审计记录，不能因为 platform default 存在就自动可用。
- tenant 默认 quota policy 继续由注册事务自动创建，作为安全和并发保护；作者不手工填写 token、cost micros、concurrency 或 period seconds。

**作者连接流程**

建立独立的“连接写作助手”向导，而不是把现有 LLM Admin 表单直接展示给作者：

```text
choose_service -> save_credential -> sync_models -> choose_model
-> verify_capabilities -> bind_compatible_modules -> ready
```

1. **选择 AI 服务**：从平台维护的 provider preset catalog 选择；每个 preset 提供公开名称、固定 HTTPS base URL、获取密钥链接和能力要求。普通流程不显示 base URL。
2. **填写密钥**：密码输入框带显示/隐藏按钮和明确 label；密钥经现有 AES-GCM 路径加密保存，响应、DOM、日志、trace 和 analytics 永不回显。
3. **选择模型**：同步成功后只展示可用模型，标出“推荐用于长篇写作”。作者选择主要写作模型；如服务提供 embedding，再单独推荐语义搜索模型，未提供时明确停用含义搜索，不伪装 hybrid。
4. **测试并完成**：执行真实 JSON/tool capability probe。通过后由服务端批量建立所有兼容的 project/tenant module bindings，不让作者逐个绑定 26 个模块。

向导必须支持失败后从当前步骤继续。credential 已安全保存但 model sync 失败时，不得创建假 ready；已验证模型但批量绑定失败时，显示“继续完成连接”，并以 idempotency key 重试未完成步骤。

**平台 credential entitlement gate**

- 新增 tenant-scoped platform LLM entitlement（复用现有 billing/plan 设施；若当前没有合适实体，再以新 migration 建最小表）。字段至少包括 tenant、status、有效期、允许的 platform channel/model 或 plan、额度/用量引用和审计时间。
- Go/Python/Pi 三侧 resolver 必须统一执行：`project tenant-owned > tenant default tenant-owned > entitled platform > unbound`。
- 没有 entitlement 时，即使 `llm_platform_module_defaults` 存在也必须返回 explicit unbound/readiness failure，绝不能读取或调用 platform credential。
- entitlement 过期、额度用尽或被撤销时，新的 reservation fail closed；进行中的调用按已冻结的 reservation 规则收口。
- 平台管理员可维护 preset catalog 和赠送权益；作者页面不能创建 platform channel。

**作者界面状态**

- `not_connected`：显示“连接写作助手”，AI 操作先进入向导；手动写作、保存和导出仍可用。
- `connecting`：显示当前步骤和“继续连接”。
- `ready`：显示服务名称、模型名称和“写作助手已连接”；不显示 credential 或内部 binding 数量。
- `invalid_credential`：在密钥输入处显示“密钥无法使用”，提供“重新填写”和 provider 的“获取密钥”链接。
- `unsupported_model`：说明该模型不支持写作助手需要的能力，返回模型选择。
- `service_unavailable`：保留 credential 和选择，提供“重新测试”。
- `admin_required`：团队成员看到“请联系工作区管理员连接写作助手”，不得看到或修改密钥。

fresh signup 的 Overview 把“连接写作助手”作为首要准备任务，同时保留次要动作“暂时跳过，先写正文”。所有 AI CTA 在 `not_connected` 时统一进入同一个向导，并在完成后返回原操作位置。

**主要文件/领域**

- 新增 author setup service/handler，复用 `apps/api/internal/llm` 与 `apps/api/internal/llmadmin`，不要把编排逻辑堆进 Web server action
- `apps/api/internal/llm/bindings.go`、`resolver.go` 以及 Python/Pi 对应 resolver
- entitlement migration/store/审计（实施时使用 next unused revision）
- provider preset catalog：服务端真相源；Web 只消费公开 projection
- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/`
- 新增作者向导组件，例如 `apps/web/components/llm-author-setup-wizard.tsx`
- `apps/web/lib/llm-creation-readiness.ts`
- `apps/web/components/overview-seed-shell.tsx`
- `apps/web/components/project-nav.tsx`
- Go/Python/Pi resolver tests、app-role live、Web contract/browser tests

**验收**

1. fresh signup 无 tenant credential：手动写作可用，任何 AI admission 在 provider call 前被拦截并引导连接。
2. 作者仅通过 UI 选择服务、填写 test credential、选择推荐模型和测试，即可完成 core module bindings；旅程不进入 quota/module/channel 管理表格。
3. 普通 tenant 没有 entitlement 时不能解析、读取或调用 platform credential。
4. 明确授予 entitlement 后 platform model 可用；撤销后立即阻止新 reservation，且有审计证据。
5. invalid key、model sync failure、capability mismatch、batch binding partial failure 均可从当前步骤恢复。
6. 团队普通成员看不到 credential，也不能替换管理员设置。
7. public DOM、URL、日志、trace、截图和测试输出不包含 API key。

## Wave 2：作者语言与恢复路径

### AF-05 任务式帮助和首次空项目引导

**实现范围**

- 恢复项目级 `/guide` 页面，不再直接 redirect Overview。
- 页面只提供任务入口：新故事、导入作品、连接写作助手、继续写作、修改选区、审校、导出；不写技术说明和长教程。
- `project-nav.tsx` 增加带 Lucide icon 和文字标签的“帮助”。
- 空项目 Overview 显示双入口；项目已有正文后不再占据首屏。
- 引导可跳过、可返回，不使用强制遮罩；状态由真实项目数据决定，避免新增无必要的 onboarding 假状态。
- 每个任务链接进入公开页面，并保留可预测的返回路径。

**作者 DOM 边界**

普通连接流程允许出现“AI 服务”“API 密钥”“模型”和具体服务/模型名称，因为这些是客户必须完成的配置。不得出现：`LLM`、通道、模块绑定、配额策略、并发、credential、token limit、cost micros、内部 provider key 和 module key。管理员高级设置页不受此禁词列表限制。

**主要文件**

- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/guide/page.tsx`
- `apps/web/components/project-nav.tsx`
- Overview 空状态组件
- `apps/web/tests/web-shell.test.mjs`
- `apps/web/tests/author-journey-contract.test.mjs`

### AF-06 集中式作者文案投影

**实现范围**

- 新建 `author-copy.ts`，集中管理 tool、run state、workflow、asset kind 和 public error 文案。
- `writer-activity-timeline.tsx` 使用映射后的 title/detail/chip；不得显示 `toolName` 原值。
- 作者页面的未知枚举使用安全通用文案，不使用 `StatusValue` 的 raw-value fallback。
- 导航建议统一为“项目总览 / 素材与设定 / 人物关系 / 剧情推演 / 角色演绎 / 正文写作 / 帮助”。路由不改，只改公开 label 与 heading。
- 文件 path、kind、bytes、anchor、snapshot、cluster、workflow event 等进入 Technical Details 或完全不下发。
- 扩展 content-boundary tests，扫描实际 SSR/browser DOM；源码存在内部 key 不等于 DOM 可以显示内部 key。

**主要文件**

- 新增 `apps/web/lib/author-copy.ts`
- `apps/web/components/writer-activity-timeline.tsx`
- `apps/web/components/bilingual-text.tsx`
- `apps/web/components/project-nav.tsx`
- Overview / Assets / Graph / Worldline / Character 的作者 projection 组件
- `apps/web/tests/content-boundary-contract.test.mjs`
- `apps/web/tests/writer-browser-live.test.mjs`

**验收**

- browser DOM 中不存在 `query_assets`、`query_graph_neighbors`、`workflow_type`、`error_code`、UUID、内部路径和原始 JSON。
- 未知工具事件显示“正在处理写作请求”，页面不崩溃、不泄露 raw key。
- 管理员 Technical Details 仍能在授权后看到排障所需的脱敏信息。

### AF-07 Mobile Writer 默认手稿并按项目恢复

**实现范围**

- `WriterMobileSwitch` 的 SSR 初始值和无存储默认值从 `agent` 改为 `manuscript`，避免 hydration 前先显示 Agent。
- storage key 加 project identity，不能让 A 书的选择影响 B 书。
- 仅恢复合法且当前可见的 view；结构不存在时回到 manuscript。
- 记录 selected block 和 manuscript scroll anchor；返回 Writer 时优先恢复当前项目最后写作位置。
- 不改变桌面 manuscript-primary 三栏比例。

**主要文件**

- `apps/web/components/writer-mobile-switch.tsx`
- `apps/web/components/writer-workbench-shell.tsx`
- `apps/web/components/writer-manuscript-panel-client.tsx`
- Writer mobile CSS
- `apps/web/tests/mobile-chrome-contract.test.mjs`
- `apps/web/tests/writer-agentification-contract.test.mjs`

### AF-08 连接、失败和重试闭环

**目标状态**

前端必须区分 `offline`、`reconnecting`、`stream_interrupted`、`run_failed`、`auth_expired` 和 `conflict`，不能都变成一个 toast。

**实现范围**

- `ConnectionBanner` 在 interrupted 状态提供“重新连接”，通过显式 retry generation 重新建立 SSE，而不是只改文案。
- run failed 在 thread 中保留持久错误卡，提供“使用原指令重试”。
- composer 输入按 project/thread 保存；提交失败、刷新和重新登录后恢复，成功创建 run 后才清除。
- ambiguous network failure 重用原 idempotency key；已确认 terminal failed 的重试创建新的 run，并关联原 run 作为 retry source。
- auth expired 跳转登录时带安全 return path，只回到项目公开 route，不携带正文或 prompt。
- partial output 标记“未完成”，不得当作可接受的完整修改。

**主要文件**

- `apps/web/components/writer-live-draft.tsx`
- `apps/web/lib/writer-sse-client.ts`
- Writer composer client component（从 shell 中拆出，避免继续增大 server component）
- `apps/web/components/public-error-notice.tsx` 或当前等价组件
- Writer run retry API / handler（若当前 API 不支持 authoritative retry）
- recovery、SSE、idempotency focused tests

## Wave 3：真实新手认证与移动质量

### AF-09 中文新手 UI-only 旅程

重构现有 `author-journey-browser-live.test.mjs`，新增严格模式：

- locale 固定为 `zh`，不再由 harness 强制写 `en`。
- 允许直接打开的只有注册/登录入口；进入项目后必须点击页面导航和 CTA。
- 不允许通过 API 取得 ID 后拼接 Worldline、Character 或 Writer URL。
- API 只可用于等待后端完成和最终数据断言，不能替代 UI 发现和导航。
- 旅程必须通过作者连接向导填写测试用 AI 服务密钥并选择模型；不得预先插入 tenant channel/binding，也不得进入 quota/module/channel 管理表格。
- 测试 provider 和 credential 可以由 disposable fixture 提供，但必须作为浏览器输入完成产品路径；密钥不得进入 screenshot、trace 或测试失败输出。
- 另加 negative journey：没有 tenant credential 且没有 entitlement 时，AI 操作只能进入连接向导，platform credential 调用计数必须保持 0。
- adoption、review、manuscript 和 TXT export 在认证模式中必须执行，不能由环境变量变成 optional。
- 同一旅程分别在 desktop 和 mobile 跑；保存 screenshots、page errors、horizontal overflow、privacy scan 和 URL scan。

建议旅程：

```text
注册 -> 通过 UI 连接自己的 AI 服务并选择模型 -> 空项目双入口
-> 第一章 -> 输入正文 -> 选区修改
-> 冲突/正常 diff -> 作者接受 -> 审校 -> 手稿 -> 下载 TXT
```

另加一条 handoff 旅程：

```text
项目总览 -> 素材与设定 -> 人物关系 -> 剧情推演
-> 角色演绎 -> 正文写作
```

每次数据库写入都必须使用 disposable live stack；退出 `down -v`，并验证主 `mirofish` 数据库未被使用。

### AF-10 Mobile accessibility 和排版门槛

**实现范围**

- `.writer-mode-segmented span`、`.writer-mobile-switch-tab`、context disclosure、diff actions、revision toolbar、connection retry 和所有 icon buttons 的 hit area 至少 44px。
- mobile body/input/editor 文字至少 16px；次级说明不得低于 12px，并满足对比度。
- composer 继续使用 VisualViewport 处理软键盘，增加 screenshot/geometry 断言证明输入框和发送按钮未被遮挡。
- 支持 200% text zoom、键盘 focus、reduced motion 和 screen-reader status。
- 375、768、1024、1440 宽度无横向 overflow、重叠或截断；中文长标题必须换行。

**主要文件**

- `apps/web/app/workbench-polish.css`
- `apps/web/app/mobile-chrome.css`
- Writer selection/diff/mobile components
- `apps/web/tests/mobile-chrome-contract.test.mjs`
- browser geometry/a11y assertions

## 执行顺序与 Gate

### Gate A：Writing Safety

必须先完成 AF-01、AF-02、AF-03、AF-04。通过条件：过期修订无法应用、URL 零正文、idea bootstrap 原子且幂等、普通客户无自有 credential/entitlement 时不会调用平台付费模型。

### Gate B：Author Default Path

再完成 AF-05 至 AF-08。通过条件：作者只通过简化向导连接模型、不进入 LLM 运维表格，帮助可发现、作者词典覆盖、手机默认手稿、所有失败有恢复动作。

### Gate C：Novice Certification

最后完成 AF-09、AF-10。通过条件：中文新手在 desktop/mobile 仅靠 UI 完成写作、修改、审校、adoption 和导出，privacy/overflow/pageerror 全部为零。

不得为了并行速度越过 Gate A。AF-06 的词典基础可以提前建立，但不能用文案修改掩盖安全问题。

## 验证矩阵

| 范围 | 必须验证 |
|---|---|
| AF-01 | revision pure tests、组件 conflict 状态、真实 version conflict |
| AF-02 | migration/RLS/app-role live、URL/Referer/log privacy、刷新恢复、no-JS |
| AF-03 | store/handler unit、failure injection、idempotent live、双击 browser |
| AF-04 | author setup state machine、encrypted credential、capability probe、batch bind、entitlement resolution、三 runtime drift、author/admin DOM 分层 |
| AF-05/06 | Web contract、SSR content boundary、browser navigation 和 unknown-value cases |
| AF-07/10 | 375/768/1024/1440、touch geometry、zoom、keyboard、reduced motion |
| AF-08 | SSE close/reconnect、auth expiry、ambiguous submit、terminal retry、draft persistence |
| AF-09 | disposable full-stack desktop/mobile Chinese journey |

每个 Wave 的最低命令基线：

```bash
cd apps/api && go test ./...
cd apps/web && npm test && npm run typecheck && npm run build
cd apps/pi-agent-runtime && npm test && npm run typecheck && npm run build
```

涉及数据库/队列/对象存储的命令必须包在：

```bash
infra/scripts/run-live-test-stack.sh --app -- <command>
```

改动超过约 50 行后，完整重启受影响的 API/Web 再进行 browser 验收。

## 最终完成定义

只有同时满足以下条件，作者友好优化才可标记完成：

- Agent 旧建议在任何 selection/version 漂移下都不能覆盖当前正文。
- 小说正文不出现在 URL、公开事件、普通日志和错误消息中。
- idea-first 创建全有或全无，同一请求重试不重复。
- 普通作者可用自己的 AI 服务完成一次性连接，不需要逐个配置 module/quota/channel。
- 普通 tenant 无自有 credential 或有效 entitlement 时，任何 runtime 都不能解析或调用 platform credential。
- 帮助和所有主流程都能从 UI 发现，不依赖深链或已知 ID。
- 作者页面不显示 raw tool key、UUID、内部 path/kind/error code。
- 手机首次进入 Writer 显示手稿，并按项目恢复上次位置。
- interrupted/failed/auth-expired/conflict 都有持久、可执行的恢复动作。
- 中文新手 desktop/mobile 全旅程通过，adoption/export 不可跳过。
- 触控、文字、对比度、键盘、缩放、overflow 和 privacy gates 全部通过。

完成后再按真相源规则更新 `24-current-development-progress.md` 和活动任务板；不要新建 handoff 或另一份 progress 文档。
