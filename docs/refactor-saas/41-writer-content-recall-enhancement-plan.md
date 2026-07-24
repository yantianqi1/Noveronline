# 41. 写作台内容召回增强设计：从固定 SQL 到按需语义召回

更新时间：`2026-07-24`
状态：P0 + P1 + P2(RRF/rerank + Consistency)已实现(Route A)。已落地：`search_assets` 混合语义召回（§3.1）、`query_assets` 收窄为勾选驱动（§3.2）、citations 全链路（§3.4）、`writer_retrieval_planner` 规划层（§4.1）、键触发召回（§4.2 keyword 类，复用 `entity_aliases`）、`always_on` 恒定注入通道（§4.2 always_on 类，`assets.always_on` 列，编排器前无条件加载、作 `fuse_recall` 顶级 channel、不占召回预算）、`search_manuscript` 前文语义召回（§4.3，含 `manuscript_block_embeddings` + reindex 流水线）、token 预算装配器（§4.4）、`reveal_after_chapter_order` 防剧透门（§4.5）、`fuse_recall` RRF 融合 + `writer_retrieval_rerank` cross-encoder 精排（§4.6）、Consistency Agent 生成后校验（§4.7，`writer_consistency`）。待做：P3（§5）、可选深化（防剧透降权/eyeball-hide、装配器三因子槽位）。注：资产编辑 API 目前不接受 `always_on`/`reveal_after_chapter_order` 的写入（仅能 SQL 设置），打通写入路径是独立待办。
关联文档：`08-asset-library.md`、`11-writer-workbench.md`、`28-zero-start-writer-and-manuscript-asset-distillation.md`、`40-writer-content-retrieval-research.md`
作者判断：本文以代码核查结论为主，`40` 号调研报告为参考。目标是把「内容召回」从当前的「固定 SQL 列表」升级为「按需的、多通道的、可预算的语义召回」，并给出可直接落地的接入路径。

---

## 0. 这份文档解决什么问题

写作台的核心价值是：**作者写某一章/某一段时，PI Agent 能自动知道"写这段需要哪些设定、哪些前文"，并把对的内容以对的预算放进上下文。** 当前这一点做得不够好：

- 资产**回流（写入）端**已经是业内高水准（蒸馏 → candidate 去重 → 人工审核 → 采纳 → 回流图谱），不用大改。
- 资产**召回（读取）端**是短板：Writer 工具只用固定 SQL，没用上项目里**已经建好的**全文 + 向量检索底座，也没有"先规划再检索"的能力。

本文先讲清"为什么没接上"，再给"怎么接上"和"接上之后怎么进一步增强"的分层方案。

---

## 1. 现状：Writer 召回到底跑的是什么

> 全部结论可在当前 worktree 复现。

### 1.1 调用链

```text
作者意图 / 选区 / 章节
  → writer_orchestrator（工具循环）
  → executeWriterTool(tool_name)            apps/pi-agent-runtime/src/activities/pi-writer-activities.ts
  → executeWriterTool SQL switch            apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts
  → 各 query_* 工具返回行 → 拼 writing_brief → writer_composer
```

### 1.2 各召回工具的真实实现

| 工具 | 数据 | 实现方式（文件:行） | 是否语义检索 |
|---|---|---|---|
| `query_assets` | 项目资产 | `SELECT … FROM assets WHERE enabled AND lifecycle IN('seed','canon','material') AND ($3= '{}' OR asset_id = ANY($3)) ORDER BY pinned DESC, updated_at DESC LIMIT 50`（`postgres-pi-writer-deps.ts:350`） | ❌ 纯 SQL，只认"用户勾选 ID"或"最近更新" |
| `query_manuscript_context` | 前文正文 | 当前 scene 的 `manuscript_blocks`（按 `block_order`）+ 同 chapter 邻近块（`postgres-pi-writer-deps.ts:475`） | ❌ 只取"邻近"，无全局相关片段 |
| `query_character_profile` | 角色 | `entities` 表 + character 资产，拼 aliases（`:384`） | ❌ 结构化 |
| `query_world_rules` | 世界规则 | `world_rule_evidence` + world_rule/worldview 资产（`:361`） | ❌ 结构化 |
| `query_graph_neighbors` | 图谱邻居 | 选中节点的 1-hop 边（需显式 `graph_node_ids`） | ❌ 预选节点，非查询驱动 |
| `query_worldline_paths` | 事业线分支 | 选中 saved paths（`reference_only`） | ❌ 需预选 |

**结论：写作路径上当前确实只有 SQL 检索（结构化、确定性、无语义理解）。**

### 1.3 检索底座其实已经建好（只是没被 Writer 用）

这套底座是给"资产库页面（人检索）"建的，引擎是生产级的：

- **全文索引**：`global_search_index.search_vector`（tsvector，GIN 索引，`infra/postgres/migrations/0002_assets_hybrid_search.sql:4`）。
- **向量索引**：`asset_embeddings`（pgvector `VECTOR`，`:19`）。
- **混合排序 SQL**：`SQLReader.SearchAssets`（`apps/api/internal/assets/assets.go:770`）已经实现：
  - keyword 分 = `ts_rank_cd(websearch_to_tsquery)` + ILIKE 兜底（`:819-826`）；
  - vector 分 = `1 - (embedding <=> query)` 余弦（`:827-830`）；
  - hybrid = `0.45*keyword + 0.55*vector`，再叠加 `recency_boost + lifecycle_boost + pinned_boost`（`:868-890`）；
  - 结构化过滤：asset_type / category / lifecycle / source / tags / pinned（`:847-852`）；
  - 返回带可解释 `RankingMetadata`（每个分数分项，`assets.go:188-206`）。
- **HTTP 入口**：`POST /v1/assets/search`，`mode = keyword | vector | hybrid`（`apps/api/internal/assets/public_search.go:99`）。
- **能力探测**：`GetSearchCapabilities`（`search_capabilities.go`）在 embedding 未绑定或索引缺失时显式降级为 keyword-only，**不伪装 hybrid**。

### 1.4 为什么 Writer 没接上（根因）

1. **两条线独立开发**：检索底座服务"资产库页面"，Writer 工具服务"写作"，二者没有共享 reader——`query_assets` 直接 `SELECT FROM assets`，从不调用 `SearchAssets`/`global_search_index`/`asset_embeddings`。
2. **缺检索规划层**：`writer_retrieval_planner` 只在 LLM registry 注册（`apps/api/internal/llm/registry.go:66`），没有实现，也没有"查询 → 检索"的桥。
3. **embedding 常未绑定**：`asset_search_embedding` 模块未绑定真实 provider 时，hybrid 不可用，只剩 keyword（这是显式降级，正确，但意味着很多环境连 keyword 都没被 Writer 用上）。

> 一句话：**底座是现成的、混合检索已经实现，Writer 只是没把管子接上。** 这不是"要重建搜索引擎"，而是"接一根管子 + 加一个规划层"。

---

## 2. 目标形态：写作召回应该长什么样

```text
写作意图 / 选区 / 章节大纲 / 在场角色
  → Retrieval Planner（先想清楚要查什么）
       输出: 覆盖清单(角色/规则/伏笔/前文/风格) + 多路查询 + 预算
  → 多路并行召回
       A. 结构化过滤(已有)      — lifecycle/type/pinned 硬约束
       B. 混合语义检索(接入底座) — keyword + vector + rerank
       C. 图谱邻域(查询驱动)     — 相关实体的多跳关系
       D. 前文语义召回(新增)     — 与当前段落相关的非邻近正文
  → Rerank + Token 预算装配 + 引用
  → Writing Brief(带 citations)
  → Composer
  → (已有) 蒸馏回流 → reindex → 回到召回
```

与 `40` 号报告一致，但**本文把"接入"拆成两个清晰阶段**：先"接通"（复用已有引擎，最快见效），再"增强"（规划层、键触发、时序、防剧透、预算装配）。

---

## 3. 阶段一：接通（P0，最快见效，复用已有引擎）

> 目标：让 Writer 的召回从"固定 SQL"变成"按需的混合语义召回"。不动回流端，不重建引擎。

### 3.1 新增 Writer 工具 `search_assets`（语义召回）

新增一个工具，内部复用与 `/v1/assets/search` 同源的混合检索逻辑，但走 Writer 的安全门（lifecycle 白名单 + 私有 content 在 server 侧净化）。

两种实现路线，按团队偏好选一：

- **路线 A（推荐，改动最小）**：在 pi-agent-runtime 内新增一个 `search_assets` 工具，SQL 复用 `assets.go:770` 的 hybrid 逻辑（同一套 tsvector + 余弦 + boost 公式），但强制 `lifecycle IN('seed','canon','material') AND enabled=true`，并额外按 `asset_type`/ tags 过滤。查询向量经 `asset_search_embedding` 模块绑定生成。
- **路线 B**：pi runtime 通过内部 RPC 调 Go 的 `POST /v1/assets/search`。少维护一份 SQL，但多一次网络跳转、且要把 Writer 的 lifecycle 门和 content 净化语义透传过去，边界更绕。

> **修订注记（2026-07-24，已据此实现 P0）——采 Route A，但理由与原文不同，且更强：**
>
> 1. **pi 与 Go 之间没有现成 RPC/HTTP 通道**。pi-agent-runtime 是直连数据库的 Temporal worker：用 `queryWithTenantContext` 跑参数化 SQL（`postgres-pi-writer-deps.ts:166`），并自己读 `llm_channels`+解密 key+自发 LLM 请求（`resolveModuleBinding`/`resolveCredential`）。Route B 要的那条"内部 seam"根本不存在，得从零造一个内部服务 + 部署边界 + 跨网络安全门透传，比原文估计的重得多。
> 2. **Route A 也不是"重写排序公式"**。混合检索整条逻辑是**一条纯 SQL**（tsvector/余弦/recency/lifecycle/pinned boost 全在 `assets.go:786-958` 一条 CTE 里），pi 侧照搬即可；`lifecycle`/`asset_type` 安全门正是这条 SQL 的现成参数，直接传入即强制，无需额外改造。真正"新增"的只有 embedding 的 OpenAI 兼容 HTTP 调用（照搬 `public_search.go:335` 的请求体与头），模块绑定解析与 writer 现有 `resolveModuleBinding` 同构。
> 3. **降级语义保持显式**：embedding 未绑定/索引缺失时，`search_assets` 返回 `mode_used="keyword"` 且 `degraded=true` 并带原因，禁止伪装 hybrid——与 `search_capabilities.go` 一致。
>
> 因此"复用引擎"在本仓库的 DB-first 架构里，正确含义是**照搬那条 SQL 并复用同一套绑定/降级语义**，而不是跨进程调 Go。

> **建议路线 A**：检索是写作热路径，进程内 SQL 延迟最低，且 lifecycle/净化语义在 Writer 侧本来就已有一份（`query_*` 工具），保持一致更直接。

工具契约（新增到 `WriterToolName` 与 `executeWriterTool`）：

```ts
// contracts/writer-run.ts 新增工具名
| "search_assets"

// ExecuteWriterToolRequest 新增字段
query: string;            // 检索意图（planner 或 orchestrator 给出）
asset_types?: string[];   // 可选类型过滤
top_k?: number;           // 默认 8–12
mode?: "keyword"|"vector"|"hybrid";  // 默认 hybrid, 能力缺失自动降级 keyword
```

行为要点：
- **强制安全门**：`lifecycle IN('seed','canon','material') AND enabled=true`（与 11 号文档 §83 一致），**永不返回 candidate/draft/simulation**。
- **显式降级**：embedding 未绑定/索引缺失时，返回 `mode_used="keyword"` 并在结果里带 `degraded=true` 与原因，禁止伪装 hybrid。
- **可解释**：返回每条的 `final_score` 与分项（keyword/vector/lifecycle/pinned），供 dock 展示 citation。
- **去重**：与 `query_assets` 的勾选结果按 `asset_id` 合并去重。

### 3.2 让 `query_assets` 变为"plan 驱动"而非"top-50 dump"

保留 pin/勾选能力，但默认行为改为：
- 有 `selected_asset_ids`（用户显式选）→ 仍按 ID 取（作者主权优先）。
- 否则 → 不再 `LIMIT 50` 全量倒序，而是**交给 `search_assets`** 用检索意图召回 top-k。

### 3.3 绑定真实 embedding + 触发 reindex

- 配置 `asset_search_embedding` 模块绑定（OpenAI 兼容 embedding）。
- 资产写入/采纳后触发 reindex，确保 `asset_embeddings` 与 `global_search_index` 是最新的（reindex 入口已在 `08` 文档 §436，需把"adopt/distill → reindex"连成自动闭环）。
- 能力探测失败时显式 keyword 降级（已有 `GetSearchCapabilities` 语义，复用）。

### 3.4 Writing Brief 带引用（citations）

`search_assets` / `query_manuscript_context` 的结果在 writing brief 里以 `citations[]` 形式记录（asset_id / block_id + score + 来源通道），前端 dock 展示"本轮用了哪些设定/前文"。这是建立作者信任、也是后续评估"召回是否真的被用上"的基础。

**阶段一验收**：作者写"主角回师门复命"，系统能自动召回"师门规则、师父关系、师门旧事件"（即使它们不是最近更新、也没被手动勾选），并在 dock 显示引用。

---

## 4. 阶段二：增强（P1，按需召回 + 小说域特化）

> 目标：从"能语义召回"升级为"召回得准、预算合理、不剧透、可校验"。

### 4.1 实现 `writer_retrieval_planner`（按需召回的大脑）

这是从"被动拉取"到"主动按需召回"的关键一跃，也是 DOME / plan-based 方案对长篇一致性提升最大的点。

- 写作前，Planner（独立 LLM 调用，module_key 已注册）分析：章节大纲 + 当前选区 + 在场角色 + 近期手稿窗口。
- 输出**结构化检索计划**（JSON）：
  ```json
  {
    "intent": "continue_scene | rewrite_span | payoff_foreshadow | ...",
    "coverage": ["characters:沈翠花,师父", "world_rules:师门戒律", "plot_threads:夜探医院伏笔", "prior_scenes:与复命相关"],
    "queries": [
      {"channel":"keyed","text":"沈翠花 师父 师门"},
      {"channel":"hybrid","text":"师门 复命 戒律 惩罚","asset_types":["world_rule","relationship"]},
      {"channel":"graph","seed_entity":"沈翠花","hops":2},
      {"channel":"manuscript","text":"上次离开师门的情形","top_k":5}
    ],
    "budget": {"max_context_tokens": 24000}
  }
  ```
- Orchestrator 按计划驱动各 `query_*` / `search_assets` 工具，而不是一把梭。

### 4.2 键触发召回（Keyed / 别名，中文网文刚需）

纯向量对"人名/地名/功法名"等专名容易漏。补一条 NovelAI·Lorebook / SillyTavern·World Info 范式的**条件触发**通道：

- 给资产增加 `activation_keys` / `aliases`（可从 `entity_aliases` 表现成投影，角色资产天然有别名）。
- 写作时扫描"近期文本 + 当前选区"，命中键（含别名）的资产**强制注入**，不受向量相关性影响。
- 支持 `always_on`（核心世界法则、风格禁词恒定注入）与 `keyword`（命中才注入）两类。
- 经验法则（SillyTavern/NovelAI 官方都强调）：**要确定性就用键触发，向量只做补充**——中文网文专名尤其如此。

### 4.3 前文的全局语义召回（呼应/伏笔）

当前 `query_manuscript_context` 只取"邻近块"，找不到"第 30 章呼应第 5 章"的伏笔。

- 给 `manuscript_blocks` 建 embedding（08 文档 §347 已规划 `manuscript block embeddings`）。
- 新增 `search_manuscript`：对当前段落语义检索**非邻近**的相关正文片段（按 chapter/scene 过滤时间线 ≤ 当前），与"邻近窗口"互补（近端全文 + 远端语义摘要）。

### 4.4 Token 预算装配器（Context Packer）

召回多条后，按优先级和预算装配，而不是无预算塞进 prompt。参考 NovelAI 的预算/插入/裁剪工程与 Generative Agents 的三因子打分：

```
score = α·recency + α·importance(pinned/人工置顶) + α·relevance(hybrid rerank 分)
```

建议槽位（可配置）：

| 槽位 | 内容 | 优先级 | 预算占比(示例) |
|---|---|---|---|
| 系统+意图 | 模式、硬约束 | P0 | 5–8% |
| 风格/禁词 | always_on | P0 | 3–5% |
| 在场角色卡(压缩) | 键触发+pin | P0 | 12–18% |
| 相关世界规则 | 键+hybrid | P0 | 8–12% |
| 关系/图谱邻域 | graph expand | P1 | 8–10% |
| 伏笔债务 | 紧急度排序 | P0/P1 | 5–8% |
| 前文窗口 | 近端全文+远端摘要 | P0 | 25–35% |
| 语义补充素材 | hybrid top-k after rerank | P2 | 8–12% |
| 预留生成 | output | — | 15–25% |

裁剪顺序：先砍 P2 语义补充 → 再 trim 角色非核心字段 → **绝不先砍当前场景硬规则与近期手稿**。

### 4.5 可见性/防剧透门（Visibility Gate）

自动召回必须配"剧透控制"，否则"相关但剧透"比漏召回更伤（Sudowrite 的教训）。

- 资产增加 `visibility` / `reveal_chapter` 字段（未揭示的凶手动机、未出场角色等默认对 Writer 隐藏或降权）。
- 与 lifecycle 门叠加：`enabled + lifecycle 白名单 + visibility` 三重过滤。
- 作者可对单个条目 eyeball-hide，召回时跳过。

### 4.6 Rerank 与融合

- 多路召回（keyed / hybrid / graph / manuscript）结果先做 **RRF(k=60)** 融合（免调参）。
- 再用 cross-encoder reranker（独立 module_key，如 `writer_retrieval_rerank`）宽召回（top 50–100）精排（top 8–12）。
- 这是"相关性质量"的最大乘数（调研证据：混合+rerank 比单向量 NDCG 提升可达 +37%）。

### 4.7 生成后一致性校验（Consistency Agent）

- 生成后对照 canon（world_rule + 角色状态快照）做矛盾检测，超标告警（不静默）。
- 与 Reviewer 模块结合，形成"召回 → 生成 → 校验"闭环（马良写作式"防吃书"）。

---

## 5. 阶段三：前沿（P2/P3，按需，不阻塞主线)

- **时序状态快照**：`entity_state_at_chapter`（位置/生死/持有物/境界）支撑"第 N 章时什么是真的"这类过滤，避免"已死角色在当前章被当作活着召回"。
- **GraphRAG 全书社区摘要**：仅用于"全书主题/势力关系/伏笔追踪"类工具，不进默认续写热路径（索引成本高）。
- **ComoRAG 式多轮检索**：只用于"审校 / 复杂问答 / 伏笔诊断"，不阻塞每次续写。

---

## 6. 落地任务清单（可直接进任务板）

| 优先级 | 任务 | 关键文件 | 依赖 |
|---|---|---|---|
| **P0** | 新增 `search_assets` 工具（复用 hybrid SQL，强制 lifecycle 门 + 显式降级 + citations） | `pi-writer-activities.ts`、`postgres-pi-writer-deps.ts`、`contracts/writer-run.ts` | 无 |
| **P0** | `query_assets` 默认改 plan/检索驱动，保留勾选优先 | `postgres-pi-writer-deps.ts:350` | P0 search_assets |
| **P0** | 绑定 `asset_search_embedding` + adopt/distill 后自动 reindex | LLM facility、reindex workflow | 无 |
| **P0** | Writing Brief 带 citations + dock 展示引用 chips | pi-writer、web dock | P0 search_assets |
| **P1** | 实现 `writer_retrieval_planner`（计划 → 驱动工具） | 新增 planner activity、`pi-writer-agent.ts` | P0 |
| **P1** | 资产 `activation_keys`/`aliases` + 键触发召回通道 | assets schema、`entity_aliases` 投影 | P1 planner |
| **P1** | `manuscript_blocks` embedding + `search_manuscript` | 新 migration、pi-writer | P0 |
| **P1** | Token 预算装配器（三因子打分 + 槽位 + 裁剪） | pi-writer context 组装 | P0 |
| **P1** | `visibility`/`reveal_chapter` 防剧透门 | assets schema、召回过滤 | P1 |
| **P2** | RRF + cross-encoder rerank 模块 | 新 module_key | P0 |
| **P2** | Consistency Agent 生成后校验 | reviewer 模块 | P1 |
| **P3** | 时序状态快照 / GraphRAG 全书 / ComoRAG 审校 | 独立设计 | P2 |

---

## 7. 怎么衡量召回变好了（小说域指标，不止 Hit@k）

| 指标 | 含义 | 目标 |
|---|---|---|
| Entity Coverage | 场景应出场角色是否都召回到压缩卡 | ↑ |
| Rule Violation Rate | 生成后违反 world_rule 的比例 | ↓ |
| Alias Recall | 别名（"云峰/云锋"）能否命中 | ↑ |
| Spoiler Leak Rate | 隐藏/未揭示字段进入上下文的次数 | ↓ 趋 0 |
| Foreshadow Payoff Hit | 回收章是否召回对应 plot_thread | ↑ |
| Citation Faithfulness | brief 引用是否真被 composer 使用 | ↑ |
| Author Override Rate | 作者手动改 chips 频率（过高=自动太差） | 适中 |

人工协议：固定 20 个"续写 beat"盲评一致性/可用性（1–5），对比 baseline（当前 top-50）vs 接通后（hybrid + keyed + planner）。

---

## 8. 反模式（明确不要做的）

- ❌ 把几十条完整 `content_text` 无预算塞进 prompt。
- ❌ 用聊天模型冒充 embedding；或 embedding 未绑定时伪装成 hybrid。
- ❌ candidate / simulation / draft 静默进入 Writer 召回。
- ❌ 只做向量、不做别名键触发（中文网文专名必翻车）。
- ❌ 自动召回但不可见、不可关（作者失去信任）。
- ❌ 为续写热路径上 GraphRAG 全书索引 / 多轮检索（成本与延迟不值得）。

---

## 9. 一句话总结

> **回流端已经很好，别动；召回端要补的不是"重建搜索引擎"，而是"把已建好的混合检索接到 Writer、再加一个检索规划层"。** 先做 P0 的"接通"（`search_assets` + embedding 绑定 + citations），最快见效；再做 P1 的"增强"（planner + 键触发 + 前文语义 + 预算装配 + 防剧透），达到业内顶级写作台的召回水准。

---

## 附录 A：关键代码与文档索引

- Writer 工具实现：`apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts`（`query_assets:350`、`query_manuscript_context:475`）
- Writer 工具清单：`apps/pi-agent-runtime/src/activities/pi-writer-activities.ts:74`
- 混合检索引擎：`apps/api/internal/assets/assets.go:770`（排序公式 `:868-890`）
- 检索 HTTP 入口：`apps/api/internal/assets/public_search.go:99`
- 能力探测降级：`apps/api/internal/assets/search_capabilities.go`
- 检索底座 schema：`infra/postgres/migrations/0002_assets_hybrid_search.sql`
- `writer_retrieval_planner` 注册（未实现）：`apps/api/internal/llm/registry.go:66`
- 检索规划：`docs/refactor-saas/08-asset-library.md:331-361`、`11-writer-workbench.md:146-191`
- 回流闭环：`apps/agent-runtime/mirofish_agents/temporal/manuscript_asset_distillation.py`、`28-zero-start-writer-and-manuscript-asset-distillation.md`
- 业内调研：`40-writer-content-retrieval-research.md`
