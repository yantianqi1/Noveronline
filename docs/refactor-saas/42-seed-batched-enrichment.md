# 42. Seed 分批富化（Batched Enrichment）与就绪度流式

更新时间：`2026-07-25`

状态：`implemented`（全三切片已落地并通过 P5-005-B 域重开验证：Go/Python/Pi/Web full regression 绿 + seed live e2e 8 passed；证据见 `24-current-development-progress.md`「Seed 分批富化」节）

读者：一个**没有本对话上下文**的实现会话。读完本文档即可直接开工，不需要回看任何聊天记录。

---

## 0. 一句话目标

把 Seed pipeline 中「单发全量」的富化阶段（先做 `agent_profiles`，再推广 `archive_candidates`）从「一次给模型塞至多 200 个实体、一条消息产出全部档案」改为「**遍历全部实体 → 按批（默认每批 5 个）喂该批实体 + 关联上下文 → 每批一次 LLM 调用产出详细档案 → 逐批幂等落库 → 期望 vs 实际对账并自动补漏**」，并让 Overview 的就绪度瓷砖（人物/关系/世界规则）在分析过程中**逐个冒出来**而不是 finalize 后一次性跳变。

**决策（已与产品负责人确认）：**

| 决策点 | 选择 |
|---|---|
| 改造范围 | 先 `agent_profiles`，验证后推广 `archive_candidates`（2–3 个阶段，中等成本） |
| 分批方式 | **确定性分批喂料 + 汇聚**（复用 sequential_reading 骨架），不用 agent loop，不用 planner |
| 完整性 | **加期望 vs 实际对账 + 自动补漏** |
| 成本 | 中等：每个阶段几次到几十次调用，总量约为现状 2–5 倍 |
| 前端流式 | **纳入范围**（本文档 §7），利用已存在的瓷砖 slam-in 能力 |

---

## 1. 背景与根因（为什么现在要改）

### 1.1 三个「单发全量」富化阶段

Seed pipeline 的 LLM-heavy 阶段里，`story_ontology` / `entity_resolution` / `agent_profiles` / `archive_candidates` 四个阶段**每个都只调一次 `complete_json`**（`apps/agent-runtime/mirofish_agents/temporal/seed.py` 行 2127 / 2199 / 2293 / 2365），没有任何循环包着 LLM 调用。每个 activity 调 runner 恰好一次（`ontology_activity`→7857、`entity_resolution_activity`→7983、`agent_profile_activity`→8102、`archive_candidate_activity`→8225）。

### 1.2 根因一：输入几乎为空或被硬截断

- `story_ontology` / `entity_resolution` / `archive_candidates` 三个阶段的 user 消息**只有 `{tenant_id, project_id, run_id, module_key, task}`，没有任何正文**。跨阶段 payload 转发 helper（`_ontology_payload_from_global_aggregation` 10263、`_entity_resolution_payload_from_ontology` 10284、`_agent_profile_payload_from_entity_resolution` 10305、`_archive_candidate_payload_from_agent_profile` 10326）只转发**元数据计数和快照 ID**，不传内容；`AgentContext`（`mirofish_agents/common/context.py:8-48`）本身也不含正文。模型在**看不到原文**的情况下被要求「一次编全部」。
- `agent_profiles` 是唯一带内容的阶段，通过 `PostgresAgentProfileContextLoader.load_context`（seed.py:1961-1997）从 DB 拉内容塞进 `source_context`，但 `_load_entities` / `_load_relationships` 都是 **`LIMIT 200`**（seed.py:2037-2053、2055-2071）—— 超过 200 个角色/关系的书，**超出部分根本进不了 prompt**。
- 输出又顶着 `max_tokens = 30000`（`seed/sequential_reader.py:687` `DEFAULT_MAX_OUTPUT_TOKENS`，请求体构造在 885-902）。输入极小/被截断 + 输出要装全部 + token 上限 = 模型被迫压缩、漏条目、返回粗糙（如 ontology 返回字符串数组，已由 `_normalize_ontology_type_item` 3982-4008 兜底）。

### 1.3 根因二：完整性无人对账

所有阶段的计数器（`_ontology_type_count` 4305、`_resolution_item_count` 4315、`_agent_profile_item_count` 4325）只做 `return len(value)` —— **只数数，不核对「源里有 N 个实体，产出覆盖了几个」**。模型漏 30% 人物、甚至返回 `profiles: []`（`_non_negative_int(profile_result.get("profile_count", 0))` 8135 允许 0），都算作「成功」。**当前没有任何机制发现漏内容。**

### 1.4 重要前提：实体/关系的「数量」已经可靠，要改的是「富化详细度」

就绪度瓷砖的数量来源是 `entities` / `relationships` / `world_rule_evidence` 表，由 `PostgresRuntimeFactsWriter` 在 `persist_runtime_facts` 阶段写入（seed.py:3236 `INSERT INTO entities`、3345 `INSERT INTO relationships`、3518 `INSERT INTO world_rule_evidence`），其数据来自 `sequential_reading` **逐章分批精读**的笔记聚合。**基础的人物/关系/规则列表已经是分批产物，质量不差。** 本方案要改的是上层**档案类富化**（agent_profiles、archive_candidates）的详细度与完整度，以及让瓷砖在过程中逐步可见。

---

## 2. 现状精确事实（实现前必读）

### 2.1 agent_profiles 现状

- **入口 activity**：`agent_profile_activity`（seed.py:8058-8174）。调 `runner.generate(context=..., module_key=CHARACTER_AGENT_PROFILE_MODULE_KEY)` 一次（8102）。
- **Runner**：`LLMFacilityAgentProfileRunner.generate`（seed.py:2250-2325）。流程：load_context（2268）→ sanitize（2276）→ 校验非空（2277，`_agent_profile_context_has_content`）→ resolve binding（2282）→ 解密 credential（2287）→ **单次 `complete_json`（2293）** → `_agent_profiles_payload`（2299）→ 计数（2300-2302）→ `record_agent_profile_snapshot` 一次性写快照（2303-2311）→ 返回 `{status, module_key, model_id, profile_snapshot_id, profile_count, memory_seed_count, relationship_view_count}`（2317-2325）。
- **消息构造**：`_agent_profile_messages`（seed.py:3930-3962）。一条 system + 一条 user，user payload = `{tenant_id, project_id, run_id, module_key, task, source_context}`（source_context 在 3942-3943 塞入）。system 要求返回 `agent_profiles` 对象含 `profiles` / `memory_seeds` / `relationship_views` 三个数组（3947-3952）。
- **source_context 结构**：`PostgresAgentProfileContextLoader.load_context` 返回 `{entity_resolution?, canon: {entities?, relationships?, segment_summaries?}}`（1976-1989），经 `_sanitize_agent_profile_context_value`（4117-4131）裁剪。entities/relationships/segment_summaries 各 `LIMIT 200`。
- **失败语义**：fail-closed。`LLMFacilityError` 或裸异常都返回 `{"status":"failed", ...}`（2312-2315），无重试、无分批降级。
- **进度**：无批进度事件。整个阶段只有 pending → completed 两个 stage event。

### 2.2 sequential_reading 的可复用骨架（本方案的零件库）

| 零件 | 位置 | 现状 | 本方案怎么用 |
|---|---|---|---|
| token 感知分批 | `seed/sequential_reader.py:699-804` `_segment_batches` | 私有、耦合正文 object_key / chapter_guess | **逻辑参考**，重写一个按「实体数」分批的简化版（不需 token 测量） |
| retry→二分恢复 | `seed/sequential_reader.py:455-565` `_read_batch_with_recovery` | 私有，retry 一次→二分递归→单段兜底 raise；白名单 `_TRANSIENT_BATCH_CODES`（16-23） | **骨架通用**，抽成泛型 `_run_batch_with_recovery(batch, attempt)` 复用 |
| 逐条容错 | `temporal/seed.py:9687-9716` `_iter_tolerated` | 通用，单条坏跳过+记录 skipped，不整批失败 | **原样可用**，批内单实体坏跳过 |
| 字段自愈/全覆盖校验 | `temporal/seed.py:9576-9647` `_validated_sequential_reading_result`（`require_all_segments` 开关） | 主流程 `require_all_segments=False`，补漏通道 `=True` | 思路借来做「期望 vs 实际对账」 |
| 批进度事件桥接 | activity 内 `_on_sequential_progress`（seed.py:7393-7422）白名单过滤 → `_record_sequential_reading_batch_progress`（5750-5769）写 `seed.sequential_reading.progress` 事件 | 完整管线 | **整套套用**，换 stage 名与事件名 |
| run 进度插值 | `_bump_sequential_reading_batch_progress`（4667-4700），把 completed/total 线性映射到 `_seed_stage_progress("segment_text")=24 → ("sequential_reading")=42` 区间 | 写死 start/end | 复制一个 `_bump_agent_profiles_batch_progress`，start=`_seed_stage_progress("entity_resolution")=80`、end=`_seed_stage_progress("agent_profiles")=86` |
| 阶段进度表 | `_seed_stage_progress`（4613-4630）：parse_file=12, segment_text=24, sequential_reading=42, persist_runtime_facts=52, global_aggregation=62, story_ontology=72, entity_resolution=80, agent_profiles=86, archive_candidates=92, index_assets=96, finalize=100 | 已有各阶段锚点 | agent_profiles 在 80→86 区间插值；archive_candidates 在 86→92 区间 |

**现状最大的差异点**：sequential_reading 是「逐批进度流式，但**攒到最后一次性落库**」（reader 主循环 `notes.extend` 攒内存，sequential_reader.py:363；activity 一次性 `record_reading_notes`，seed.py:7491-7500）。**本方案要求逐批落库，无先例可抄，需新写**（把批循环和 writer 调用交错，而非先攒后写）。

### 2.3 archive_candidates 现状（推广目标，第二阶段才动）

- Runner `LLMFacilityArchiveCandidateRunner.generate`（seed.py:2342-…）：单次 `complete_json`（2365）→ `_archive_entity_candidates`（2371）→ `archive_candidate_batch_id = f"narrative-archives:{run_id}"`（2372）→ `self._archive_candidate_writer.write_archive_candidates(...)`（2373-…）。
- **输入为空**：`_archive_candidate_messages`（4360-4386）user payload 只有 `{tenant_id, project_id, run_id, module_key, task}`，**无 source_context**。推广分批时需要先给它接内容（同 agent_profiles 的 context loader）。
- 消息要求返回顶层 `archive_entities` 数组，每项含 `title/summary/category/tags/payload/memories[]`（4364-4370）。

### 2.4 关键 schema

- `entities`（`infra/postgres/migrations/0001_core_saas.sql:310-325`）：`entity_id`、`canonical_name`、`entity_type`（默认 `character`）、`importance`、`state_summary`、`first_seen_segment_id`、`metadata_jsonb`；`UNIQUE (tenant_id, project_id, canonical_name)`。**期望清单 = 按 `canonical_name` 排序的全部实体。**
- `segment_summaries`（同文件 544-…）：`segment_id`、`summary`、`source_kind`（默认 `sequential_reading`）、`UNIQUE(tenant_id, project_id, run_id, segment_id, source_kind)`。
- `text_segments`：`segment_order`、`chapter_guess`（seed.py:991-992、1439-1448）。
- 实体↔章节关联：`entities.first_seen_segment_id`（单点）；更完整的出现轨迹在 `metadata_jsonb` / 关系证据表（如需要「该实体出现在哪些章节摘要」，可用 `first_seen_segment_id` + 全书 segment_summaries 截断，或扩展查询。**默认实现用「该批实体 + 这些实体的关系 + 全部 segment_summaries（截断）」作为批上下文**，与现有 loader 行为一致，只是实体子集化）。

---

## 3. 方案：Per-Entity Batched Enrichment

### 3.1 总流程

```
entity_resolution 完成（entities 已就绪）
  ↓
[1] 读全部实体：SELECT entity_id, canonical_name, entity_type, importance,
    state_summary, first_seen_segment_id FROM entities
    WHERE tenant_id/project_id 按 context，ORDER BY canonical_name ASC
    —— 不再 LIMIT 200（解除截断，这是完整性第一步）
  ↓
[2] 确定性分批：按 canonical_name 排序后切批，每批 ENRICHMENT_BATCH_SIZE 个
    （默认 5，可被 module setting agent_profiles.batch_size 覆盖，clamp 1..20）
  ↓
[3] 对每一批 batch（严格串行，沿用 sequential_reading 不并发的约束）：
    a. 构造批上下文：该批实体子集 + 这些实体涉及的关系子集 +
       segment_summaries（全书截断）+ entity_resolution 快照
       —— 复用 PostgresAgentProfileContextLoader 的查询，但参数化为「实体子集」
    b. 构造消息：_agent_profile_batch_messages(batch_entities, batch_context)
       system 明确要求「只为给定的 N 个实体生成档案，每个都要详细」，
       并要求返回的 profiles 数组 canonical_name 必须 ⊆ 本批输入实体名
    c. 1 次 complete_json
    d. schema 校验 + 批内逐条容错（_iter_tolerated：单实体档案坏→跳过并记录）
    e. 批级失败恢复：retry 一次 →（批>1 实体）二分递归 → 单实体仍失败则记入
       missing（不拖垮整阶段）
    f. 逐批幂等落库：record_agent_profile_batch(...)，把本批 profiles 合并进
       累积快照（见 §3.3 持久化策略）
    g. 发批进度事件 seed.agent_profiles.progress + 插值 run 进度（80→86）
  ↓
[4] 期望 vs 实际对账：
    expected = 全部 canonical_name 集合
    actual   = 已落库档案覆盖的 canonical_name 集合
    missing  = expected - actual
  ↓
[5] 自动补漏：对 missing 再跑一轮（同样的分批，通常只含少量实体）；
    仍 missing 的写入 consistency_notes / result.missing_entities（可见，不静默）
  ↓
[6] 返回 completed：profile_count = 实际覆盖数（对账后的真实值），
    附 batch_count / reconciled_count / missing_count
```

### 3.2 分批策略（确定性）

- **分批键**：`canonical_name` 排序（稳定、可复现、幂等）。
- **批大小**：默认 `5`，module setting `agent_profiles.batch_size` 可覆盖，clamp `[1, 20]`。**不需要 token 测量**（批上下文规模由实体数近似控制；segment_summaries 仍截断）。若后续发现批上下文过大，再加 token 上限（参考 `_estimate_tokens` sequential_reader.py:692-696，宽字符 1.5 token/字、窄字符 0.25 token/字）。
- **批间关系**：每个实体只属于一批；关系按「两端实体都在本批」过滤进批上下文，跨批关系在该实体所属批各带一份摘要（或并入全局 segment_summaries 上下文，二选一，实现时定）。
- **串行**：与 sequential_reading 一致，严格串行不并发，避免 provider 限流与配额竞态（`SeedQuotaAwareJSONChatClient` 的 `call_index` 目前为 0，分批需改为递增 call_index 以维持 quota gate 的 `stable_provider_call_id` 幂等键语义 —— 见 §6 风险 R4）。

### 3.3 持久化策略（逐批幂等落库）

现状是「一次 `record_agent_profile_snapshot` 写整个快照」。分批后改为**逐批落库 + 幂等合并**，两条可落地的路线，**推荐路线 A**：

- **路线 A（推荐）：累积快照 + 逐批 upsert。** 每批成功后，把该批 profiles/memory_seeds/relationship_views 合并进「本 run 的累积 agent_profiles 文档」，用 `ON CONFLICT (tenant_id, project_id, run_id, module_key) DO UPDATE` 覆盖写同一行快照（沿用现有快照表唯一键模式，参考其它 snapshot writer 的 `ON CONFLICT ... run_id, module_key`，如 seed.py:1681/1757/1832/1913）。**合并键 = canonical_name**（profiles 按 canonical_name 去重，后写覆盖先写）。阶段结束时该快照即最终全量。
  - 优点：对现有 `record_agent_profile_snapshot` 契约改动最小；读侧（快照读 API）不变；重跑幂等。
  - 实现：新增 `record_agent_profile_batch(context, module_key, model_id, batch_profiles, batch_index)` writer 方法，内部 read-modify-write 合并；或 SQL `jsonb` 合并。**注意必须在 app-role/RLS tenant context 下执行（`_set_postgres_tenant_context`），与其它 writer 一致。**

- **路线 B：每批一行快照 + finalize 聚合。** 每批写一行带 `batch_index` 的快照，阶段末再聚合。缺点：改动读侧、聚合复杂，不推荐。

**落库时机**：每批 LLM 成功 + 校验通过**立即**落库，再发进度事件。这样即使阶段中途失败，已落库的批不丢（配合 §6 风险 R2 的部分失败语义）。

### 3.4 完整性对账 + 自动补漏

- **期望清单**：`SELECT canonical_name FROM entities WHERE tenant_id/project_id ORDER BY canonical_name`（全部，不截断）。
- **实际清单**：累积快照中 profiles 的 `canonical_name` 集合。
- **对账时机**：所有批跑完后一次。
- **补漏**：`missing = expected - actual`。若非空，用同样的分批路径对 missing 重跑一轮（通常 missing 很少，1 批即可）。补漏仍 missing 的：
  - 写入 `consistency_notes`（沿用现有降级可见模式，参考 `_validated_reading_note` 把降级写进 consistency_notes，seed.py:9630-9642）；
  - 在 activity result 里加 `missing_entities: [...]`、`missing_count: N`（公开 metadata，非正文）；
  - **不 fail**（部分覆盖优于全失败，与 sequential_reading「单章降级保留」哲学一致），但**必须可见**（result + event），不得静默。
- **profile_count 语义修正**：对账后 `profile_count = 实际覆盖的实体数`（真实值），不再是「模型返回多少算多少」。这修复了「返回空 profiles 也算成功」的现状漏洞。

### 3.5 输出 schema（批级，与现状兼容）

批消息返回结构**沿用现有 `agent_profiles` 对象**（含 `profiles` / `memory_seeds` / `relationship_views`），但：

- system prompt 增加：「**只为本批给定的 N 个实体（列出 canonical_name）生成档案；每个实体都要有详细 profile；不得省略；不得为本批之外的实体生成。**」去掉任何「keep concise」式引导。
- 新增批级校验：返回的 `profiles[].canonical_name`（或 profile 内的实体名字段）必须 ⊆ 本批输入实体名集合；超出部分丢弃并记录（防模型幻觉编造批外实体）。字段名以现有 `_agent_profiles_payload` 解析出的 profile 实体字段为准（实现时核对 `_agent_profile_item_count` / profile 结构）。

---

## 4. 失败语义与部分失败

| 场景 | 行为 |
|---|---|
| 单批 LLM schema/瞬时错误 | retry 一次 →（批>1）二分递归 → 单实体仍失败：记入 missing，继续下一批（**不 fail 整阶段**） |
| 单批内个别实体档案坏 | `_iter_tolerated` 跳过该条 + 记录，批内其余正常落库 |
| 凭证/binding/quota 错误（非瞬时） | 沿用现状 fail-closed，整阶段 failed（这类错不该逐批降级） |
| 全部批跑完但 missing 非空 | 补漏一轮；仍 missing → result.missing_entities 可见 + consistency_notes，**不 fail** |
| 中途致命失败（activity 抛异常） | 已落库的批保留（逐批落库），阶段标 failed；重跑时幂等覆盖 |

**进度插值**：批进度事件触发 `_bump_agent_profiles_batch_progress`，把 `completed_entities/total_entities` 映射到 80→86 区间（`start=_seed_stage_progress("entity_resolution")`，`end=_seed_stage_progress("agent_profiles")`），写 `workflow_runs.progress` 与中文 message（如「正在生成角色档案 12/60 · 陈父…」）。

---

## 5. 后端改动清单（按文件）

> 原则：复用 §2.2 零件；保持 fail-closed 与 app-role/RLS tenant context；不加 mock/静默 fallback；公开 event/result 只含 metadata（ids/counts/model/canonical_name），不含正文/prompt/credential。

### 5.1 `apps/agent-runtime/mirofish_agents/temporal/seed.py`

1. **解除 200 截断**：`PostgresAgentProfileContextLoader._load_entities` / `_load_relationships`（2037-2071）改为支持「全量 + 按子集过滤」。新增方法 `load_entities_for_batch(context, batch_canonical_names)` 或参数化现有 loader。
2. **分批器**：新增 `_agent_profile_batches(entities, batch_size)`（按 canonical_name 排序切批）。
3. **批恢复**：抽泛型 `_run_enrichment_batch_with_recovery(callable, batch, attempt)`，参考 `_read_batch_with_recovery`（sequential_reader.py:455-565）的 retry→二分骨架，白名单复用 `_TRANSIENT_BATCH_CODES`。
4. **批消息**：`_agent_profile_batch_messages(context, batch_entities, batch_context)`，system 加「只为本批 N 个实体生成 + 不得省略」。
5. **批校验**：返回 profiles 的实体名 ⊆ 本批输入集合；批内 `_iter_tolerated` 容错。
6. **Runner 改造**：`LLMFacilityAgentProfileRunner.generate`（2250-2325）改为批循环：load 全量实体 → 分批 → 逐批 [调 LLM → 校验 → 落库 → 进度] → 对账 → 补漏 → 返回真实 count。
7. **Writer**：新增 `record_agent_profile_batch`（幂等合并，按 canonical_name 去重，app-role/RLS context）。
8. **进度**：`_on_agent_profiles_progress` 白名单桥接 + `_record_agent_profiles_batch_progress`（写 `seed.agent_profiles.progress`）+ `_bump_agent_profiles_batch_progress`（80→86 插值）。
9. **对账 + 补漏**：阶段末实现 §3.4。

### 5.2 `apps/agent-runtime/mirofish_agents/seed/sequential_reader.py`

- 如需把 `_read_batch_with_recovery` 抽成可复用形式，可在此或新模块 `seed/batch_recovery.py` 提供泛型骨架。**不改 sequential_reading 现有行为。**

### 5.3 测试 `apps/agent-runtime/tests/test_seed_workflow.py`

新增（对齐现有 Recording/Fake 桩风格，参考 2823-3908 的 in-memory 替身）：

- 分批器：60 实体 / batch_size=5 → 12 批，按 canonical_name 排序、每实体恰一批。
- 批恢复：第一批瞬时错误→retry 成功；持续错误→二分→单实体 missing 不 fail。
- 解除截断：>200 实体全部进入期望清单。
- 对账：故意让某批漏 3 实体 → 补漏被调用 → 最终 missing=0；补漏仍缺 → result.missing_entities 可见且不 fail。
- 逐批落库：断言 writer 被按批调用 N 次，合并后 canonical_name 去重。
- 进度：批进度事件 `seed.agent_profiles.progress` 字段齐全，run 进度在 80→86 单调。
- 回归：现有 156 个 seed workflow 测试 + 11 个 ontology 测试必须全绿。

---

## 6. 风险与注意

- **R1 上下文膨胀**：批上下文若仍塞全部 segment_summaries，实体多的书批 prompt 仍大。缓解：segment_summaries 截断 + 后续可加 token 上限（§3.2）。
- **R2 部分失败语义变化**：从「整阶段成败」变「部分覆盖 + 可见 missing」。这是**有意改变**，需在 result/event 明确暴露 missing，不得静默。
- **R3 重跑幂等**：逐批落库必须幂等（ON CONFLICT 合并），否则重跑产生重复档案。
- **R4 quota gate 幂等键**：现状 `SeedQuotaAwareJSONChatClient` 的 `call_index=0`（quota_chat_client.py:59），`stable_provider_call_id` 含 run_id，同 run 重试会 replay。分批后**每批必须用递增 call_index / 独立 call id**，否则多批会撞同一个幂等键、被 quota gate 当作同一调用 replay，导致只有第一批真正调 LLM。**这是分批改造最容易踩的坑，实现时必须先核对 `llm_quota/gate.py` 的 `stable_provider_call_id` / `execute_json` 语义，让每批（含补漏批）有唯一 call id。**
- **R5 verified 域重开**：本改动触碰 P5-005-B（Seed 域，当前 `verified_current`）。落地即触发该域重开验证（规则见 parallel-board 第 12 行），需跑 full regression + live。
- **R6 成本**：每阶段调用数 ≈ 实体数 / batch_size。60 实体 / 5 = 12 次/agent_profiles；加 archive_candidates 类似。总量约现状 2-5 倍，符合「中等成本」预期。

---

## 7.（在范围内）就绪度瓷砖流式渲染

### 7.1 前端已经具备流式能力（无需新动画）

就绪度瓷砖组件 `apps/web/app/projects/[projectId]/overview/readiness-rail.tsx` **已经支持逐个 slam-in**：

- 它接收 `assets: AssetRecord[]`，按 `created_at` 排序转成瓷砖（106-120）。
- 用 `seenRef` + `newIds` diff：只有「 genuinely-new 」的 `asset_id` 会以 slam-in 动画出现一次（122-137、242-265），首次挂载不全部重放。
- Overview 轮询 `overview-workspace.tsx`：每 `POLL_INTERVAL_MS = 2500`（46）拉一次 `fetchAssets`（89/192/199）+ `fetchReadiness` + `fetchSeedRuns`。

**结论：只要后端把资产/档案「逐批落库」，前端每 2.5s 轮询到新资产就会自动逐块 slam-in，前端瓷砖动画代码零改动。**

### 7.2 需要做的（后端为主，前端少量）

1. **后端逐批落库（§3.3）**：让 `assets` 表在 agent_profiles / archive_candidates 阶段**随批增长**，而不是攒到阶段末。这是瓷砖流式的唯一硬前提。
   - 注意：瓷砖数据来自 `fetchAssets`（资产库 assets 表），**不是** agent_profiles 快照表。agent_profiles 写的是快照，**不直接产生 assets 行**。因此「瓷砖逐个冒」实际由两条路径驱动：
     - **路径甲（已存在）**：`persist_runtime_facts` 后 entities/relationships 已就绪，`index_assets` 把它们投射成 assets。这是瓷砖数量的主要来源，目前集中在 index_assets 一次性投射。
     - **路径乙（本方案）**：archive_candidates 逐批 `INSERT INTO assets`（参考现有 `_upsert_archive_asset` seed.py:2476-2524 已是逐条 upsert，但目前在一个事务里攒到最后）。**把 archive_candidates 改为逐批落库后，候选资产会随批出现在资产库 → 瓷砖逐个冒。**
   - **实现选择**：优先让 **archive_candidates 逐批写 assets**（它本来就写 assets 表），瓷砖即可流式；agent_profiles 的快照不直接驱动瓷砖，但若也想让角色档案可见，可在逐批落库后由 index 逻辑增量投射（第二阶段再定）。
2. **批进度事件接入进度面板（可选增强）**：`seed.agent_profiles.progress` / `seed.archive_candidates.progress` 事件，前端 `apps/web/lib/api/seed.ts` `reduceSeedProgress` 加一个 case（仿照 `seed.sequential_reading.progress` 143-158），在 `seed-progress-panel.tsx` 渲染「正在生成角色档案 12/60」式的子进度（仿照现有 sequentialReading 块 99-133）。**这与瓷砖流式独立，可单独做。**
3. **轮询即可，无需 SSE**：现有 2.5s 轮询足够；如未来要更实时可接文档 29 的 SSE，但不属于本方案必需。

### 7.3 前端改动清单

- `apps/web/lib/api/seed.ts`：`reduceSeedProgress` 新增 `seed.agent_profiles.progress` / `seed.archive_candidates.progress` case，产出 `{completed, total, message}` 子进度 view model。
- `apps/web/app/projects/[projectId]/overview/seed-progress-panel.tsx`：新增对应子进度渲染块（可选）。
- `readiness-rail.tsx`：**零改动**（已有 slam-in）。
- 测试：参照 `apps/web/tests/present-error.test.mjs` 风格，加 reduceSeedProgress 对新进度事件的归约测试。

---

## 8. 成本与验收

### 8.1 成本估算

- agent_profiles：实体数 / batch_size 次调用 + （补漏 ≤ 少量） + 1 次对账（无 LLM）。
- archive_candidates：类似。
- 单阶段调用数 ≈ ceil(实体数 / 5)。token：每批 prompt = 批实体 + 关系子集 + 截断 summaries；输出 = 批档案（远小于 30000 上限，不再顶限）。**总 token 比单发高（重复喂 summaries），但单次输出更小、更不易截断、更详细。**

### 8.2 验收（Definition of Done）

1. agent_profiles 改为分批：>200 实体的书全部进入期望清单，无截断。
2. 完整性对账生效：故意注入缺漏的测试里，补漏后 missing=0；补漏失败时 result.missing_entities 可见。
3. 逐批落库幂等：重跑同一 run 不产生重复档案。
4. quota gate：每批唯一 call id，无幂等键冲突（live 验证每批真实调用）。
5. 就绪度瓷砖在 archive_candidates 阶段逐块 slam-in（浏览器实测，非一次性跳变）。
6. 中文批进度在进度面板可见（若做 §7.2-2）。
7. 回归：seed workflow 156 + ontology 11 全绿；P5-005-B 域重开验证（full regression + live）通过。
8. 公开 event/result 不含正文/prompt/credential（privacy scan 通过）。

---

## 9. 实现顺序（建议切片）

1. **切片 1（核心）**：agent_profiles 分批 + 解除截断 + quota call id 修正 + 逐批落库 + 对账补漏 + 单测。**不碰前端。**
2. **切片 2（流式）**：archive_candidates 分批 + 逐批写 assets → 瓷砖流式可见（浏览器实测）。
3. **切片 3（体验，可选）**：前端批进度事件归约 + 进度面板子进度渲染。
4. 每切片独立验证；切片 1 落地即重开 P5-005-B 验证。

---

## 10. 参考坐标速查

- agent_profiles runner / 单次调用：`apps/agent-runtime/mirofish_agents/temporal/seed.py:2250-2325`（`complete_json` 在 2293）
- agent_profiles activity：`seed.py:8058-8174`（调 runner 在 8102）
- context loader（LIMIT 200）：`seed.py:1961-2087`
- 消息构造：`seed.py:3930-3962`
- 可复用批恢复骨架：`apps/agent-runtime/mirofish_agents/seed/sequential_reader.py:455-565`
- token 分批参考：`sequential_reader.py:699-804`
- 逐条容错：`seed.py:9687-9716`（`_iter_tolerated`）
- 批进度桥接/写事件/插值：`seed.py:7393-7422` / `5750-5769` / `4667-4700`
- 阶段进度表：`seed.py:4613-4630`
- archive asset 逐条 upsert：`seed.py:2476-2524`（`_upsert_archive_asset`）
- quota gate call id：`apps/agent-runtime/mirofish_agents/llm_quota/gate.py`、`seed/quota_chat_client.py:59`（`call_index=0`）
- 就绪度瓷砖（已有 slam-in）：`apps/web/app/projects/[projectId]/overview/readiness-rail.tsx`
- Overview 轮询：`apps/web/app/projects/[projectId]/overview/overview-workspace.tsx`（`POLL_INTERVAL_MS=2500`）
- 前端进度归约：`apps/web/lib/api/seed.ts`（`reduceSeedProgress`，sequentialReading case 在 143-158）
- entities schema：`infra/postgres/migrations/0001_core_saas.sql:310-325`
