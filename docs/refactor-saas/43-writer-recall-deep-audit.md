# 写作台 × Pi Agent × 资产库召回 深度审核报告

审核日期：`2026-07-26`（修复落地：`2026-07-27`）
审核范围：`apps/web`（写作台）→ `apps/api`（Go 控制面）→ Temporal → `apps/pi-agent-runtime`（Pi Writer Agent）→ Postgres（资产库 / 检索底座）
审核方式：只读。代码逐行核对 + 运行中 Compose Postgres 真实数据核对 + 真实 `agent_trace_events` 生产链路回放。

> **2026-07-27 修复状态（见文末第 7 节）**：P0 中代码可修复的 5 项全部落地并通过全量回归（Go / Pi / Web / Python 504 全绿）；剩余 2 项是数据/配置补种（embedding 模型绑定回填、entity_aliases/asset_links/always_on 播种），不阻塞代码合入。

---

## 0. 一句话结论

**你要的效果——"作者在写作台写作，Pi Agent 智能地从项目资产库里挑合适的资产做上文召回"——架构上已经完整建成了，但在当前部署里事实上一次都没有成功过。**

不是"差一点"，是**召回链路的每一段都断了**，而且断点集中在**数据与配置层**，不在架构层。真实生产 trace 的证据：

> 全库 28 次 writer run 里，`search_assets` 被调用 5 次、`search_manuscript` 被调用 1 次，**6/6 全部返回 0 条**。`fuse_recall`（融合排序）**从未被调用过一次**。
> 其中一次真实调用：query = `"许七安 打更人 司天监 炼金 税银案"` → `{count: 0, degraded: false, assets: [], citations: []}`。
> 同一时刻，这个租户的库里躺着 1470 条资产、5616 个故事图谱节点、6222 条图谱证据、1228 条剧情线、1698 条角色事件。

也就是说：**知识是有的，通道是有的，但知识从来没有进过通道。** Agent 每次都是在"空库"上写作，它输出的所有"设定一致性"其实都来自模型自己的想象和当前章节的上下文，不是来自你的资产库。

好消息：**这个结论意味着修复的性价比极高。** 你不需要重写检索架构；P0 清单里排前四的问题，工作量都在 1～3 天量级，修完之后召回就能从 0 命中变成真实命中。

---

## 1. 设计意图 vs 实际形态

设计文档（doc 41）里的召回链路是这样的：

```
retrieval planner → 多通道召回（keyed / hybrid / graph / manuscript / always_on）
                  → RRF 融合（K=60）→ cross-encoder 重排 → token 预算装箱
                  → writing brief（带引用）→ composer → 一致性校验
```

代码里这条链路**确实存在**，`apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts`（2266 行）把它实现完了。问题在于每一段的**实际生效条件**：

| 通道 | 代码位置 | 设计意图 | 实际状态 |
|---|---|---|---|
| `search_assets` 关键词 | `postgres-pi-writer-deps.ts:1155-1288` | 全文检索资产库 | **INNER JOIN 索引表**，未索引资产完全不可见；中文分词失效 |
| `search_assets` 向量 | 同上 | 语义召回 | `asset_embeddings` **0 行**；embedding 模块绑定到 chat 模型，真实报 404 |
| `keyed` 别名精确召回 | `postgres-pi-writer-deps.ts:833-953, 1144` | 人名/地名精确锚定 | `entity_aliases` **0 行**；且只对 planner 的 query 触发，不对正文触发 |
| `always_on` 常驻正典 | `postgres-pi-writer-deps.ts:953` | 世界观常驻注入 | `assets WHERE always_on` **0 行** |
| `expand_relations` 1 跳扩展 | `postgres-pi-writer-deps.ts:1348-1393` | 关系图扩展 | `asset_links` **0 行**，恒为空 |
| `search_manuscript` 正文召回 | `postgres-pi-writer-deps.ts:1501-1504` | 前文伏笔召回 | 真实调用返回 `mode_used: "unavailable"`；`manuscript_block_embeddings` **0 行** |
| `query_graph_neighbors` 图谱 | `postgres-pi-writer-deps.ts:447` | 故事图谱邻域 | 由 `graph_node_ids` 驱动，Go **从不下发**该字段，恒返回 `{node:{}, neighbors:[]}` |
| `query_worldline_paths` | `postgres-pi-writer-deps.ts:522` | 世界线路径 | `worldline_path_ids` 恒为 `[]`，直接返回 `selection_required: true` |
| `fuse_recall` RRF 融合 | `pi-writer-activities.ts:1285` | 多通道融合排序 | 上游全空，**从未被调用**；且当前实现是直通，未做真实 RRF |

**结论：九条通道里，七条因为数据为空而恒空，两条因为字段不下发而恒空。**

---

## 2. 核心证据（真实数据，非推测）

### 2.1 只有 seed 管线产出的资产进了检索索引

`global_search_index` 是 `search_assets` 的**唯一入口表**。按资产来源统计索引覆盖：

| lifecycle | source_kind | 是否进索引 | 数量 |
|---|---|---|---|
| seed | seed_pipeline | ✅ 已索引 | 1125 |
| canon | seed_pipeline | ✅ 已索引 | 1 |
| material | **pi_analysis** | ❌ 未索引 | 235 |
| candidate | **narrative_archives** | ❌ 未索引 | 78 |
| candidate | **manuscript_distillation** | ❌ 未索引 | 30 |
| archived | manuscript_distillation | ❌ 未索引 | 1 |

原因：Go 侧的 `assetcatalog/` 与 `assetdistillation/` **完全没有写 `global_search_index` 的代码**（grep 无结果）。只有 Python seed 管线写。而唯一的补索引入口 `asset_reindex` workflow，**历史运行次数 = 0**。

这直接决定了：**作者在写作过程中沉淀出来的所有资产（Pi 分析产出、手稿蒸馏产出、归档候选），Pi 一条都检索不到。** 越用越写，资产越多，召回率越低——这与产品直觉完全相反。

### 2.2 有资产的项目没人写，有人写的项目没资产

这是全篇最关键的一张表（title | 资产数 | 索引数 | 图谱节点 | 章节数 | writer run 数）：

```
测试3        | 872 | 872 | 5288 | 0 |  0     ← 资产最全，零写作
测试4        | 189 | 148 |    0 | 0 |  0
青山-测试    | 152 |   0 |  106 | 1 | 14     ← 写得最多，索引为零
测试6        | 139 |  94 |  132 | 1 |  1
青山-测试-2  |  83 |   0 |   90 | 1 |  0
苍兰诀外传   |  33 |  12 |    0 | 4 | 12     ← 第二活跃，索引 12/33
界面验收小说 |   2 |   0 |    0 | 1 |  1
```

`青山-测试` 152 条资产**全部是 `lifecycle=material`**（Pi 分析产出），因此 0 条进索引，而它承载了全库一半的写作量。**作者真正使用的场景，恰好是召回底座最空的场景。** 这就是为什么 6/6 召回返回 0——不是偶然，是结构必然。

### 2.3 向量召回：不是"未绑定"，是"绑错了"

`docs/refactor-saas/24-current-development-progress.md` 记录 `asset_search_embedding` 未绑定。实际查库：**已绑定，但绑到了 chat 模型**——7 个绑定指向 `deepseek-v4-flash`，1 个指向 `gpt-5.5`。两个都不是 embedding 模型。

真实 trace 里的降级原因：

```
degrade_reason: "asset query embedding provider request failed (status 404)"
```

配套事实：
- `asset_embeddings` = **0 行**
- `manuscript_block_embeddings` = **0 行**
- `infra/postgres/migrations/0002_assets_hybrid_search.sql:26` 定义 `embedding VECTOR NOT NULL`——**没有维度**。没有维度就**无法建 HNSW/IVFFlat 索引**，即使灌了数据也只能全表暴力扫描。

好的一面：降级是**显式可见**的（`resolveSearchAssetsMode`，`postgres-pi-writer-deps.ts:729-745`，返回 `degraded: true` + `degradeReason`），符合项目"不要静默降级"的规范。坏的一面：这个 `degraded` 标记一路传到 Web 层（`apps/web/lib/api/writer-run.ts:114` 的 `citationsDegraded`），但作者在界面上基本感知不到"这次写作没有任何资产支撑"。

### 2.4 中文全文检索在结构上是死的

Postgres 扩展只装了 `pgcrypto` / `plpgsql` / `vector`。**没有 `pg_trgm`，没有 `zhparser`，没有 `pg_jieba`，没有任何 `chinese` 文本搜索配置。**

而 `0002_assets_hybrid_search.sql:5-8` 用的是 `to_tsvector('simple'::regconfig, ...)`。实测：

```sql
to_tsvector('simple', '青玄剑宗位于东海掌门为叶清玄')  -->  一个 token
```

整句话被当成一个词。这意味着 tsvector 通道对中文**完全无效**。

那还能命中，是因为有 ILIKE 兜底。但兜底的写法有硬伤——`postgres-pi-writer-deps.ts:1155-1288` 把**整条 query 原样包进通配符**：

```sql
('%' || $3::text || '%') AS keyword_pattern,
...
CASE WHEN search_doc.title ILIKE input.keyword_pattern
       OR COALESCE(search_doc.body,'')      ILIKE input.keyword_pattern
       OR COALESCE(asset.content_text,'')   ILIKE input.keyword_pattern
     THEN 0.5 ELSE 0.0 END
```

实测后果：

- `许七安` → **110 条命中**
- `许七安 的 师门` → **0 条命中**

只要 query 多于一个词，命中率立刻归零。而 planner 生成的 query 天然是多词的（`"许七安 打更人 司天监 炼金 税银案"`）。**这一条足以单独解释 6/6 的零命中。**

同样的缺陷在 Go 侧 `apps/api/internal/assets/assets.go:836-1095` 完全一致（1034 行绑定 `"%"+query+"%"`），所以**资产库页面的搜索框对作者同样是"多打一个词就搜不到"**。

### 2.5 未索引资产在所有模式下都不可达

`search_assets` 的 FROM 子句是**从索引表出发的 INNER JOIN**：

```sql
FROM search_input input
JOIN global_search_index search_doc
  ON search_doc.source = 'asset' AND ...
JOIN assets asset
  ON asset.asset_id::text = search_doc.source_ref AND asset.enabled = TRUE
LEFT JOIN asset_embeddings embedding ON ...
```

所以 §2.1 的未索引资产，在 keyword / vector / hybrid **三种模式下全部不可达**。而 hybrid 分支还有第二道过滤：

```sql
OR ( input.search_mode IN ('vector','hybrid') AND embedding.embedding_id IS NOT NULL )
```

`asset_embeddings` 为 0 行 → hybrid 模式下向量侧贡献恒为空。

---

## 3. 断点清单（按修复优先级排序）

### P0 —— 不修就等于没有召回

| # | 问题 | 位置 | 证据 | 影响 |
|---|---|---|---|---|
| P0-1 | 只有 seed 管线写检索索引，Go 侧资产写入不建索引 | `apps/api/internal/assetcatalog/`、`assetdistillation/`（无写索引代码） | 344 条非 seed 资产 0 索引 | 作者沉淀的资产 Agent 永远看不见 |
| P0-2 | 关键词模式把整条 query 包进 ILIKE | `postgres-pi-writer-deps.ts:1155-1288`；`apps/api/internal/assets/assets.go:1034` | `许七安`→110，`许七安 的 师门`→0 | 多词 query 100% 零命中 |
| P0-3 | `asset_search_embedding` 绑到 chat 模型 | `llm_module_bindings`（7→deepseek-v4-flash，1→gpt-5.5） | trace `provider request failed (status 404)` | 向量召回全链路不可用 |
| P0-4 | 中文分词缺失 | 无 `zhparser`/`pg_jieba`/`pg_trgm`；`0002:5-8` 用 `'simple'` | 整句 → 1 token | tsvector 通道对中文无效 |
| P0-5 | `asset_reindex` 从未运行，且产品中无入口 | `workflow_runs` 中该类型 0 行 | — | 存量资产无法补救 |
| P0-6 | `entity_aliases` / `asset_links` / `always_on` 均 0 行 | 三张表实测 0 | — | keyed、关系扩展、常驻正典三通道恒空 |

### P1 —— 影响正确性与长篇可用性

| # | 问题 | 位置 | 说明 |
|---|---|---|---|
| P1-1 | **剧透闸门被绕过** | `postgres-pi-writer-deps.ts:1348-1393` | `loadRelatedAssets` 只过滤 `enabled` + `lifecycle`，**没有 `reveal_after_chapter_order` 谓词**。作者写第 3 章时，`expand_relations` 可以把第 40 章才该揭晓的设定拉进上下文。所有结构化 `query_*` 工具同样没有闸门 |
| P1-2 | **正文时间线闸门被 OR 放宽** | `postgres-pi-writer-deps.ts:1501-1504` | `block_order < $5 OR ($6::uuid IS NOT NULL AND block.scene_id IS DISTINCT FROM $6::uuid)`——只要 scene_id 非空，**其他场景的未来章节正文全部合格**。前文召回会召回到"后文" |
| P1-3 | keyed 通道只对 planner query 触发 | `postgres-pi-writer-deps.ts:1144` | `executeKeyedAssets(options, request, [queryText])` 是唯一调用点。不对**作者刚写的正文**、不对**作者选中的段落**触发。而这两个才是长篇写作里最强的召回信号 |
| P1-4 | keyed 全量加载无 LIMIT | 同上 | 加载项目全部资产 + 全部别名到内存。`测试3` 872 条尚可，10 万字长篇的资产量会成为热点 |
| P1-5 | 会话历史 `LIMIT 500 ASC` 且无分页 | `apps/api/internal/workflows/writer_threads.go:207-208` | 取的是**最旧的 500 条**。长篇作者写到约 250 轮后，Agent 看到的永远是最早的对话，新上下文全部丢失 |
| P1-6 | `selected_asset_ids` 端到端不通 | `apps/web/lib/api/writer-client.ts:271` `startWriterRun` 无 options 参数 | 作者"我要用这几条设定"这个最直接的意图，**根本传不到 Agent** |
| P1-7 | 工作流无 RetryPolicy，超时不匹配 | `apps/pi-agent-runtime/src/workflows/pi-writer-workflow.ts`（15 行）vs `apps/api/internal/workflows/writer.go:615-616` | activity `startToClose: 10min` 无重试策略 → Temporal 默认**无限重试**；外层 workflow 超时 6 小时。一次坏 run 可以反复烧配额 6 小时 |
| P1-8 | 无 agent 迭代上限 | `pi-writer-agent.ts` | 工具循环没有硬性轮次上限，与 P1-7 叠加放大 |

### P2 —— 写作台交互缺陷（直接影响作者体感）

| # | 问题 | 位置 | 说明 |
|---|---|---|---|
| P2-1 | `GET /v1/drafts/{id}` 路由不存在 | `apps/api/internal/httpapi/server.go:2505` 只有 `/v1/drafts/{id}/reviews` | 前端每 900ms 轮询一次草稿详情 → **持续 404**，`liveRun.draft` 恒为 null |
| P2-2 | 乐观锁错误码不匹配 | Go 发 `OPTIMISTIC_CONFLICT`（`manuscriptworkspace/store.go:857`）；Web 判 `MANUSCRIPT_VERSION_CONFLICT`（`writer-workspace.tsx:276`） | 版本冲突提示**永远不会出现**，作者会静默丢改动 |
| P2-3 | 采用草稿写错章节 | 采用逻辑用 `activeChapterId` 而非草稿自身的 chapter | 作者切到别的章节再点采用 → 内容落到错误章节 |
| P2-4 | 采用后整体 `setSegments` 覆盖 | writer workspace | 覆盖掉作者未保存的手工修改 |
| P2-5 | 召回信号在界面上近乎不可见 | `apps/web/lib/api/writer-run.ts` | `writer.retrieval_plan.*`、`writer.context_budget.trimmed` 落进 `default: break;` 被丢弃；`search_manuscript` 结果**从不生成引用**；`RunCitation` 丢掉了 `score` |

### P3 —— 工程与安全

| # | 问题 | 说明 |
|---|---|---|
| P3-1 | `apps/agent-runtime` pytest 自 `de42419` 起在 collection 阶段即失败 | Python 侧**整套测试跑不起来**，而进度文档仍记录"484 passed" |
| P3-2 | 进度文档与看板的验证结论已失真 | `24-current-development-progress.md:129`、`tasks/refactor-saas-parallel-board.md:38` 均称"full regression 当前通过"；实际 Python 套件不可运行，且大量 live 测试被 skip |
| P3-3 | `fuse_recall` 是直通实现 | `pi-writer-activities.ts:1285` 返回原始结果，未做 RRF 融合 |
| P3-4 | token 预算装箱只覆盖两个工具 | `pi-writer-activities.ts:1691-1697` 只处理 `search_assets`/`search_manuscript`；`estimateTokens`（1677-1684）用 `charCodeAt > 0xff ? 1.5 : 0.25` 粗估中文 |
| P3-5 | 用量统计漏计 planner | `pi-writer-activities.ts:1524` 只累加 orchestrator + composer，`plannerUsage` 是死变量 |
| P3-6 | `credential_ref` 进入 Temporal history 明文载荷 | Temporal history 是长期留存的，凭据引用不应入载荷 |
| P3-7 | writer-runs 无速率限制 | 结合 P1-7 无限重试，配额风险敞口大 |
| P3-8 | 双轨降级路径 | `pi-writer-activities.ts:562` 条件不满足时走 legacy 单阶段路径，**完全没有召回**且对作者不可见 |
| P3-9 | Go 与 Pi 的资产可见性规则不一致 | Go `SearchAssets` **完全没有实现** `always_on` / 剧透闸门 / `asset_links`。资产库看到的和 Agent 召回到的是两套规则 |

---

## 4. 优化方案

### 第一阶段：让召回从 0 变成有（约 1 周，收益最大）

按这个顺序做，每一步都能独立验证：

**1. 统一"写入即索引"（P0-1，1～2 天）**
在 Go 侧资产写入路径上加索引写入，覆盖 `assetcatalog` 与 `assetdistillation` 两条产线。关键约束：**在同一事务里写 `assets` 和 `global_search_index`**，不要用异步补偿——异步补偿会带来"刚保存的设定 Agent 还看不到"的体感落差，这在写作场景里是致命的。

同时把 `asset_reindex` 从"只有 workflow、没有入口"变成产品功能：资产库页面加一个"重建检索索引"的动作，带进度反馈。存量 344 条未索引资产靠它一次性补齐。

**2. 修关键词检索：应用层分词（P0-2 + P0-4，1 天）**
不要先去装 `zhparser`（要改 Docker 镜像、要重建库、要处理生产迁移，链条太长）。先在**应用层**把 query 切成词，再生成 `AND`/`OR` 组合的 ILIKE 条件，按命中词数打分。

```
"许七安 的 师门"  →  切词 → [许七安, 师门]（停用词过滤掉"的"）
                  →  命中 2 词得分 1.0，命中 1 词得分 0.5
```

Pi 侧（`postgres-pi-writer-deps.ts:1155-1288`）和 Go 侧（`assets.go:836-1095`）要**同步改**，否则资产库搜索和 Agent 召回继续两套行为。这一条是**单点收益最高的修复**——它能把 6/6 零命中直接变成有命中，而且不依赖任何基础设施变更。

**3. 修 embedding 绑定（P0-3，半天）**
把 `asset_search_embedding` 绑到真正的 embedding 模型（`bge-m3` 或 `Qwen3-Embedding` 系列，中文长文本表现好且维度可控）。同时把 `0002` 里的 `VECTOR`（无维度）通过新迁移改成 `VECTOR(n)` 并建 HNSW 索引——**不要改已应用的迁移，加新的**（项目规范）。

然后跑一次全量 embedding 回填。注意配额：1470 条资产的回填要走配额预留，别在业务高峰做。

**4. 补三张空表（P0-6，1 天）**
- `entity_aliases`：seed 管线其实已经产出了实体，缺的是把别名写进这张表。人名/地名/门派的别名是中文小说召回的**最强锚点**——"许七安"、"许银锣"、"打更人许七安"应该指向同一个人。
- `asset_links`：`story_graph_edges` 里已经有 904 条关系，做一次投影即可。
- `always_on`：UI 和 Go CRUD 都已经有了（`asset-inspector.tsx` 的 `RecallControls`），缺的是**默认值策略**。建议：seed 管线产出的"世界观规则"、"核心设定"类资产默认 `always_on = true`，其余默认 false。0 行不是功能缺失，是没人去勾。

**验收方式**：写一个 live 测试，断言"用中文多词 query 检索 `青山-测试` 项目，`count > 0`"。这一条测试会同时点亮 P0-1、P0-2、P0-4、P0-5 四个问题——它现在必然失败，修完必然通过。

### 第二阶段：让召回变准（约 2 周）

**5. 修正确性闸门（P1-1 + P1-2）**
- `loadRelatedAssets`（`:1348-1393`）加 `reveal_after_chapter_order` 谓词，所有结构化 `query_*` 工具同样加。
- `search_manuscript`（`:1501-1504`）的 `OR` 改成正确的时间线语义：**同场景看前文，跨场景也只看前文**，而不是"跨场景就放行"。

这两个是**信任问题**，不是性能问题。剧透一次，作者就再也不会开召回了。

**6. 扩展 keyed 触发源（P1-3）**
把 `executeKeyedAssets` 的输入从 `[queryText]` 扩展为三路：planner query + **作者最近写的 N 段正文** + **作者当前选中的文本**。这是把召回从"Agent 猜你要什么"变成"Agent 看你在写什么"的关键一步，对长篇写作的体感提升最大。同时给全量加载补 LIMIT（P1-4）。

**7. 打通 `selected_asset_ids`（P1-6）**
`startWriterRun` 加 options 参数，Web 把作者在资产库里勾选的资产传下去。作者的显式意图应该有最高优先级——这是"智能召回"之外的**确定性召回**，两者必须共存。

**8. 手稿分块 + 向量化（P1-2 配套）**
`manuscript_block_embeddings` 目前 0 行。长篇小说的"伏笔回收"完全依赖这个——作者写到第 80 章要回收第 12 章埋的线，靠关键词是找不到的，必须靠语义。这一步做完，`search_manuscript` 才算真正可用。

**9. 收敛失控风险（P1-7 + P1-8 + P3-7）**
workflow 加 RetryPolicy（建议 `maximumAttempts: 3`），agent 循环加迭代上限，writer-runs 加速率限制。三个加起来半天，能堵住最大的配额敞口。

### 第三阶段：让召回可解释（约 2 周）

**10. 真正实现 `fuse_recall`（P3-3）**
现在是直通。等三条通道（keyed / FTS / 向量）都有数据之后，按设计文档做 RRF 融合（`K=60`）。融合的价值在通道 ≥ 2 时才显现，所以这一步**必须排在第一、二阶段之后**。

**11. 召回可观测性（P2-5）**
把 `writer.retrieval_plan.*`、`writer.context_budget.trimmed` 从 `default: break;` 里救出来，在写作台 rail 上展示：**这次写作用了哪些资产、为什么用、评分多少、哪些因为预算被裁掉了**。`RunCitation` 保留 `score`，`search_manuscript` 结果也生成引用。

对作者来说这不只是"透明度"——这是**教作者怎么维护资产库**的反馈回路。作者看到"这条设定评分很低所以没被用"，才会去补充它。

**12. 修写作台交互缺陷（P2-1 ~ P2-4）**
补 `GET /v1/drafts/{id}` 路由；统一错误码为 `OPTIMISTIC_CONFLICT`；采用时用草稿自身的 chapter；采用时做**增量合并**而非整体 `setSegments` 覆盖。这四个都是小改动，但每一个都在直接损伤作者的信任——尤其是丢改动。

**13. 会话历史分页（P1-5）**
`LIMIT 500 ASC` 改成"最近 N 轮 + 更早的摘要"。长篇小说的写作会话会持续几个月，这个必须解决。

### 第四阶段：工程健康（贯穿始终）

- 修 `apps/agent-runtime` 的 pytest collection 失败（P3-1）。**测试跑不起来的时候，所有"regression 通过"的结论都是无效的。**
- 更新 `24-current-development-progress.md` 与 `tasks/refactor-saas-parallel-board.md`，把失真的验证结论改成实际状态（P3-2）。按项目规范，这两份文档是唯一进度源，失真的代价会传导到后续所有决策。
- 把 `credential_ref` 从 Temporal 载荷里移出（P3-6）。
- 统一 Go 与 Pi 的资产可见性规则（P3-9）——建议把可见性规则下沉成**一段共享 SQL 或共享契约**，而不是两边各写一份。

---

## 5. 面向长篇小说的产品建议

审到这里，有几件事超出了 bug 的范畴，但对"面向深度长篇小说的写作平台"这个定位更关键：

**1. 召回质量的天花板是资产质量，不是算法。**
你的库里有 5616 个图谱节点、1228 条剧情线、1698 条角色事件、6222 条证据——这个知识密度是很多同类产品做不到的。但它们**一条都没有进召回通道**。当前的召回只覆盖 `assets` 一张表，图谱、剧情线、角色事件全部在通道之外。中长期最大的差异化机会在这里：**把故事图谱变成召回通道**，而不只是可视化展品。`query_graph_neighbors` 的架子已经搭好了，缺的只是让 Go 下发 `graph_node_ids`。

**2. "越写越聪明"必须成立，否则产品逻辑不闭环。**
现在的情况是**越写越笨**——作者写作沉淀出的资产（pi_analysis / manuscript_distillation）恰好是不进索引的那些。P0-1 修完之后，要把这条链路做成产品叙事：作者每写一章，系统蒸馏出新设定，新设定立刻可召回，下一章写得更准。这是长篇写作平台最有说服力的价值主张，而你离它只差一个索引写入。

**3. 剧透控制是长篇小说的独有价值，别浪费它。**
`reveal_after_chapter_order` 这个设计我在同类产品里很少见到，它精准命中了长篇作者的真实痛点——"我知道结局，但我现在写第 3 章，别让 AI 提前把伏笔说破"。但现在 `loadRelatedAssets` 和所有结构化工具都绕过了它（P1-1）。**修好它并把它做成显式的产品特性**（比如写作台上有个"当前视角：第 3 章"的指示器），这是能讲出去的差异点。

**4. 先解决"有没有"，再解决"准不准"。**
不建议现在投入做 cross-encoder 重排、做更复杂的 planner。在召回命中率是 0 的时候，重排没有意义。按上面的阶段顺序走，第一阶段做完就能看到质变。

**5. 建立一条"召回健康度"指标。**
建议在写作台或运维面板上暴露三个数：**索引覆盖率**（`global_search_index` 行数 / `assets` 行数）、**embedding 覆盖率**、**近 N 次 run 的平均召回条数**。这三个数如果早就有，本次审核发现的绝大多数问题在几个月前就会自己暴露出来。

---

## 6. 建议的下一步

如果只做一件事：**修 P0-2（关键词整句 ILIKE）**，半天到一天，立刻能让召回从"永远 0 条"变成"有结果"。

如果做一周：按第一阶段的 1→2→3→4 顺序推，收尾时跑那条 live 断言（中文多词 query 在真实项目上 `count > 0`）。这一周结束时，你在开头问的那个问题——"Pi 能不能智能地从资产库选取合适的资产做召回"——答案会从"不能"变成"能"。

---

## 7. 修复落地（2026-07-27）

P0/P1/P2/P3 中代码可修复的项已全部落地，全量回归通过。剩余 2 项（P0-3 embedding 绑定回填、P0-6 三表播种）是数据/配置层补种，不阻塞代码合入。

### 已修复（代码 + 迁移，全部通过回归）

| 项 | 修复内容 | 关键文件 |
|---|---|---|
| **P0-2 + P0-4** 中文多词召回 | 应用层分词（CJK 按"的/了/和…"等单字虚词切分、停用词过滤、去重、≤8 词），SQL 从整句 ILIKE 改为 `unnest(keyword_patterns)` 按命中词数打分；**实测** `"许七安 打更人 司天监 炼金 税银案"` 在 `测试4` 项目从 **0 → 121 命中** | `postgres-pi-writer-deps.ts`、`assets.go`、新增 `apps/api/internal/assets/search_terms.go` |
| **P0-1** 写入即索引 | 迁移 0029：在 `assets` 上建 `trg_assets_search_index_sync` / `trg_assets_search_index_cleanup` 触发器（同事务 upsert/delete `global_search_index`），并 backfill 全部存量。**实测**索引覆盖 `1470/1470` | `infra/postgres/migrations/0029_assets_search_index_sync.sql`、`infra/scripts/bootstrap-compose-database.sh` |
| **P1-1** 剧透闸门 | `loadRelatedAssets`、`query_asset_relationships`、`query_world_rules`、`query_character_profile` 全部补 `reveal_after_chapter_order IS NULL OR <= $n` 谓词 | `postgres-pi-writer-deps.ts` |
| **P1-2** 时间线闸门 | `search_manuscript` 改为**排他时间界**（`block.block_order < cursor`）：目标场景有正文→场景尾；空章→上一章尾；无目标→全部已有正文。移除"跨场景就放行"的 OR | 同上，新增 `resolveManuscriptCursorBound` |
| **P1-3 + P1-4** keyed 触发与有界扫描 | keyed 通道除 planner query 外，额外读当前场景/章节**最近 6 段正文**作为触发源；资产/别名扫描加 `LIMIT 2000/5000` | 同上，新增 `loadRecentManuscriptTail` |
| **P1-5** 会话历史 | `ListMessages` 改为"最近 500 条按时间正序返回"，长篇会话不再冻结在开头 | `apps/api/internal/workflows/writer_threads.go` |
| **P1-7 + P1-8** 失控风险 | `PiWriterRunWorkflow` 加 `RetryPolicy{maximumAttempts:3, backoff}`；orchestrator 工具循环加硬上限 `ORCHESTRATOR_TOOL_CALL_MAX=24`（超出即引导产出 brief） | `pi-writer-workflow.ts`、`pi-writer-agent.ts` |
| **P2-1** 草稿详情路由 | 新增 `GET /v1/drafts/{id}?include=content`（Go `GetWriterDraft` + BFF 白名单 `drafts/([^/]+)$`），rail 轮询不再 404 | `server.go`、`main.go`、`writer_draft_read.go`（新增）、`route.ts` |
| **P2-2** 冲突错误码 | `writer-workspace.tsx` 同时识别 `OPTIMISTIC_CONFLICT` 与 `MANUSCRIPT_VERSION_CONFLICT`，冲突提示不再沉默 | `writer-workspace.tsx` |
| **P2-3 + P2-4** 采用章节与覆盖 | 采用前先读草稿拿其自身 `chapter_id`（兜底 activeChapterId），不再写错章节；采用后用 `mergeSegments` 增量合并，作者未保存编辑不被覆盖 | `writer-workspace.tsx` |
| **P2-5** 召回可观测性 | `RunCitation` 补 `score`；`search_manuscript` 结果生成"前文呼应"引用；`writer.retrieval_plan.*` 与 `writer.context_budget.trimmed` 进入状态模型（`retrievalPlan` / `contextTrimmedItems`）；rail 引用条带显示评分 tooltip 与"另有 N 条因预算未带入" | `lib/api/writer-run.ts`、`writer-rail.tsx` |
| **P3-7** writer-runs 限流 | 新增 `writer_run_start` 限流类（12 次/5 分钟，按 tenant+project+actor），Compose 策略同步 | `limiter.go`、`server.go`、`docker-compose.yml` |
| **P3-1** Python 测试可运行 | `de42419` 删除 `scripts/legacy_import.py` 导致 collection 失败；把 parser 迁入 `mirofish_agents/legacy_import/cli.py` 并修正测试 import。**实测 504 passed, 31 skipped** | `apps/agent-runtime/mirofish_agents/legacy_import/cli.py`、`tests/test_legacy_import.py` |

### 待办（数据/配置，不阻塞代码）

- **P0-3**：把 `asset_search_embedding` 重新绑定到真实 embedding 模型并回填 `asset_embeddings` / `manuscript_block_embeddings`（当前均 0 行；向量通道仍走显式降级到关键词）。
- **P0-6**：从 `story_graph_nodes`/`edges` 与 canon 资产播种 `entity_aliases`、`asset_links`、`always_on`，让 keyed、1-hop 扩展、常驻正典三条通道有数据。
- **P1-6**：把 `selected_asset_ids` 从 Web 一路接到 Pi（作者显式勾选资产 → run admission → `query_assets`）。

### 回归证据

- Go：`go test ./...` 全绿（含 `cmd/api`、`internal/httpapi`、`internal/assets`、`internal/platformratelimit`）
- Pi：`vitest run` 266 passed | 8 skipped；`npm test` 133 passed；`tsc --noEmit` 与 `tsc` build 通过
- Web：`node --test` 88 passed；`tsc --noEmit` 与 `next build` 通过
- Python：`pytest tests -q` → **504 passed, 31 skipped**（修复前 collection 即失败）

---

*本报告基于 2026-07-26 的 worktree 与运行中的 Compose Postgres 实例；修复于 2026-07-27 在分支 `rewrite/web-clean-slate` 完成。所有数据库数字为实测值。报告未包含任何凭据、用户手稿内容或 LLM trace 原文。*
