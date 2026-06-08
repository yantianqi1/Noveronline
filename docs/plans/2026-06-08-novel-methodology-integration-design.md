# 「小说梦想家」方法论 × MiroFish 创作台 · 集成方案设计

> 日期：2026-06-08
> 状态：设计稿（待评审后进入实施）
> 方向（已与作者确认）：**参考 pi / claude-code-from-scratch / InkOS 等参考项目升级 MiroFish 的 `writer_agent`，并把「小说梦想家」创作方法论注入现有创作台。不把 pi 作为独立运行时嵌入。**
> 约束：本仓库当前有大量未提交改动（见 `git status --short`，含 `writer_agent/tool_executors.py` 等）。本方案的实施必须**新增**为主、最小侵入现有文件，且不替作者提交。

---

## 〇、一句话结论

MiroFish 已经是一个成熟的"小说创作台"，它的 `writer_agent` 在**架构层**（双层编排 + 工具循环 + 审校 + 反重复 + book_run 多章闭环）已经实现了「小说梦想家」想要的大部分骨架。本次集成的本质不是"搬一个新 agent 进来"，而是：

1. **注入内容**：把「小说梦想家」的文风宪法（SOUL）、禁词库（BANNED_PHRASES）、审查清单（PITFALLS / 自检17条）灌进 MiroFish 已有的 **preset / forbidden_lexicon / reviewer** 容器；
2. **补一段闭环**：把当前**非阻塞、仅单场景**的 reviewer，升级为**可阻塞的"写→风格审计→自动修订"闭环**，并补进 `book_run` 的多章内循环（与现有 WORD_AUDIT / LEXICON_AUDIT 并列）。这正是 `docs/reference-projects-analysis.md` 的 P0-1。

pi 的角色：**架构参考**（其 agent loop 思路 MiroFish 的 `agent_loop.py` 已注明"ported from claude-code-from-scratch"）。本次主要借鉴 InkOS 的 `writer-repair` 修订接受判定逻辑。

---

## 一、MiroFish 写作台现状盘点（as-found）

### 1.1 单场景/续写主链 — `writer_agent/orchestrator.py::WriterOrchestrator.run()`

异步 SSE 流水线：

```
请求(write_scene|continue|outline)
  → 数据健康自检 (_collect_data_health_issues)
  → Phase0 RetrievalPlanner（轻量 LLM 规划该调哪些读工具，可降级）
  → AgentLoop（writer_orchestrator 模块, 弱模型, ≤15轮, 读工具并行/写工具串行）→ writing_brief(JSON)
  → 强制注入：章节大纲 / 续写上下文 / 反重复约束(dedup_constraints)
  → Phase2 WriterComposer（writer_composer 模块, 强模型, temp0.8, 流式）→ 正文
  → Phase3 PostProcessor（落库 scene/manuscript block）
  → DedupExtractor（writer_dedup_extractor, fire-and-forget, 抽取下一章要规避的表层套路）
  → Phase4 WriterReviewer（writer_reviewer 模块）→ 【非阻塞】质量报告，前端展示"采纳改写/保留草稿"
  → done
```

要点：
- **LLM 全部走模块绑定**（`LlmRouter` + `llm_module_bindings`）：`writer_orchestrator` / `writer_composer` / `writer_reviewer` / `writer_dedup_extractor`。未绑定 = 显式失败，无 fallback。
- **写作系统提示 = preset（用户文风）+ writing_brief 上下文 + `build_anti_cliche_constraints()`（恒定注入的"房屋风格"）+ dedup 反重复块**。见 `writer.py::WriterComposer._build_system_prompt`。
- **审校是事后、非阻塞的**：scene 已落库，reviewer 只产出报告，由前端 `reviewer-panel.tsx` 让用户决定是否改写。

### 1.2 多章成书主链 — `writer_agent/book_run_orchestrator.py` + `prompts.py`

`book_run` 已经实现了"写→审→修→提交"的**多阶段内循环**：

```
plan → RETRIEVE(book检索规划) → OUTLINE(多章beat) → 逐章: CHAPTER_WRITE
   → WORD_AUDIT 内循环（get_chapter_word_stats → splice_block, verdict pass/fail, ≤6轮）
   → LEXICON_AUDIT 内循环（scan_forbidden_lexicon → rewrite_span, ≤6轮）
   → commit
```

对应 prompt：`build_chapter_writer_prompt` / `build_word_audit_prompt` / `build_lexicon_audit_prompt`。
**这就是「小说梦想家」要的质检闭环骨架——只是缺一个"风格/AI味审计"阶段。**

### 1.3 一键 runner 模式 — `writer_agent/one_click/`

`OneClickRunner`(base.py) = 单次 AgentLoop + 专用系统提示 + 工具白名单（只读 + 一个 `propose_*`）+ 产出**非破坏性提案卡**（ProseDiff/Scene/Relationship），前端采纳。已有：`lexicon_cleaner`（扫禁词出改写卡）、`word_aligner`（对齐字数）、`chapter_continuer`、`outline_completer`、`relationship_filler`。
**这是新增"风格清理"一键功能的标准插槽。**

### 1.4 已有的"质量"容器

| 容器 | 位置 | 现状 |
|---|---|---|
| 文风预设 | `preset_service.py` + `writer_presets` 表 + 前端 `preset-editor.tsx` | 有，per-project/global，可空 |
| 房屋风格硬规则 | `prompts.build_anti_cliche_constraints()` | 已覆盖修辞密度/修饰克制/句式多样/段落节奏/POV指纹/场景模式 |
| 共享反模式常量 | `writing_quality_constants.EVENT_SUMMARY_WRITING_GUIDE` | 白描优先/禁总结升华/禁程度副词 |
| 审校清单 | `reviewer_prompt.REVIEWER_SYSTEM_PROMPT`（6维+死令级）& `prompts.build_reviewer_prompt()`（8类） | **已与 SOUL/PITFALLS 高度重合** |
| 禁词库 | `forbidden_lexicon` 资产 + `scan/list/upsert_forbidden_lexicon` 工具 + 前端 `forbidden-lexicon-panel.tsx` | 有机制，**待灌规则** |
| 反重复 | `DedupExtractor` + `dedup_constraints` + `build_dedup_extractor_prompt` | 已自动跨章，**强于小说梦想家的重复词脚本** |
| 字数 | `word_aligner` / `get_chapter_word_stats` / WORD_AUDIT | 有，待统一汉字口径 |
| 角色/伏笔/世界 | 实体档案(canon/candidate/experiment) + graph + 证据链 + `manage_*` 工具 | **强于小说梦想家的角色卡** |

---

## 二、方法论 → MiroFish 精确映射

| 小说梦想家方法论 | MiroFish 落点（文件 :: 函数/表） | 集成动作 |
|---|---|---|
| **SOUL 文风宪法（句式层）** | `prompts.build_anti_cliche_constraints()` | **扩展**：补"经历式vs宣告式""叙述者=主角的嘴""内心OS 30-40%" |
| **SOUL 文风宪法（用户可调）** | `preset_service` + `writer_presets`（seed 一个 global 预设） | **新增 seed**：「小说梦想家·网文铁律」默认预设 |
| 文风共享常量 | `writing_quality_constants.py` | **扩展**：补框架层反模式 |
| **BANNED_PHRASES.md（禁词/禁句式）** | `forbidden_lexicon` 资产（regex+literal）+ `scan_forbidden_lexicon` | **新增 seed 脚本**：把 44 条规则导成 lexicon 条目 |
| **二重审核 A–H + 自检17条 + PITFALLS** | `reviewer_prompt.REVIEWER_SYSTEM_PROMPT` & `prompts.build_reviewer_prompt()` | **扩展维度**：补 `不是X是Y` / `A是B宣告` / 因果连接词 / 破折旁白 / 解说员框架 |
| 汉字数审查 | `one_click/word_aligner.py` / `get_chapter_word_stats` | **核对口径**：确认按 `一-鿿` 统计 |
| 重复词/反重复 | `DedupExtractor`（已自动） | 已有，无需新建 |
| 角色卡仓库 | 实体档案 + `get_character_voice` + `manage_entity` | 已有更强；方法论仅作 schema 补充 |
| 15 步流水线 | seed pipeline + `book_plan→chapter→scene→manuscript` + `book_run` | 已有对应；方法论作为 prompt 内容注入 |
| 题材插件 | `genre_plugin.py`（现仅 wuxia/xianxia/scifi/default） | **扩展**：补玄幻/言情/悬疑/都市 + 每类疲劳词/爽点节拍 |
| 文风蒸馏库（14本）/ 剧情模组库 | 资产库 `writing_style` / `plot_inspiration_engine.py` | **可选**：导入为 assets，写作时 `search_assets` 引用 |
| **写后审计-自动修订闭环** | **当前缺**（reviewer 非阻塞；book_run 只有 word+lexicon 审计） | **新建**：风格审计-修订阶段（见 P4） |

---

## 三、差距分析（要补的 5 块）

- **G1（最高价值）写后"风格/AI味"审计-自动修订闭环。** 现状：单场景 reviewer 非阻塞；book_run 内循环只有 WORD_AUDIT + LEXICON_AUDIT，没有 STYLE_AUDIT。要补：以 reviewer 的 high(死令级) issues 为触发，跑一个"局部改写"修订循环（参考 InkOS `writer-repair`：接受判定 = high/critical 数不恶化 + 至少一项改善），直到 pass 或 ≤N 轮。
- **G2 框架层文风规则。** 现有 anti_cliche/reviewer 强在**句式层**（词汇/比喻/句式黑名单），但 SOUL 最深的"经历式 vs 宣告式""叙述者=主角的嘴""限知视角即时反应""内心OS 30-40%"是**叙述范式层**，需显式注入 writer 房屋风格 + reviewer 维度。
- **G3 禁词库种子。** `forbidden_lexicon` 机制就绪但需把 BANNED_PHRASES.md 的 44 条 regex/literal 灌进去（含 `不是…而是` / `指节泛白` / `喉结滚动` / 破折号 / 括号注释等）。
- **G4 审校维度对齐。** reviewer 已覆盖大半 PITFALLS；补齐缺的框架层类别（notXisY 解释型、AB 宣告、因果连接词、破折旁白、解说员框架），并标注死令级。
- **G5（可选）题材插件 + 参考库。** 扩 genre_plugin；把 14 本文风蒸馏 / 剧情模组导入资产库供检索。

---

## 四、分阶段集成方案（建议顺序）

> 原则：先注入内容（低风险、立即见效），后补闭环（涉及编排改动）。每阶段独立可验证、可回滚。全部以**新增**为主。

### P1 · 注入文风宪法（内容，零架构改动）
- **新增** seed 脚本 `backend/scripts/seed_novel_methodology.py`：向 `writer_presets` 插入一个 global 默认预设「小说梦想家·网文铁律」（内容 = SOUL 精炼版）。
- **扩展** `prompts.build_anti_cliche_constraints()`：新增一节"叙述范式（框架层）"——经历式优先、叙述者=主角的嘴、内心OS占比、限知视角不外泄。
- **扩展** `writing_quality_constants.py`：补框架层反模式常量，供 writer/reviewer/director 共用。
- 验证：跑一段 write_scene，对比注入前后 prompt_snapshot 与成稿 AI 味。

### P2 · 注入禁词库（内容）
- **新增** seed：把 `BANNED_PHRASES.md` 解析为 `forbidden_lexicon` 资产条目（level=error→severity=block，warn→warn；保留 regex/literal 类型）。
- 验证：`scan_forbidden_lexicon` 对一段含 `不是…而是`/`指节泛白` 的样例文本应命中；前端 `forbidden-lexicon-panel` 可见。

### P3 · 扩展审校维度（内容）
- **扩展** `prompts.build_reviewer_prompt()` 与 `reviewer_prompt.REVIEWER_SYSTEM_PROMPT`：新增类别 `not_x_is_y` / `declarative_AB` / `causal_connective` / `narrator_frame`（解说员框架）/ `em_dash_aside`，并入死令级判定。
- **扩展** `reviewer.py::_ALLOWED_CATEGORIES` 白名单以接纳新类别。
- 验证：reviewer 对一段宣告式/解说员腔样例应给出对应 high issues。

### P4 · 新建"风格审计-自动修订"闭环（架构，核心）
两条线并行：
- **单场景线**：给 `WriterOrchestrator.run()` 增加可选 `auto_repair` 开关（默认关，前端可勾选）。开启时：reviewer 若有 high issues → 调用新 `propose_*`/`rewrite_span` 走一个"局部修订"AgentLoop（只改被点名句子，参考 InkOS local-fix/polish/anti-detect 三模式），重审，接受判定后再落库或出对照卡。**不破坏现有非阻塞默认行为。**
- **book_run 线**：在 `book_run_orchestrator` 的逐章内循环里，于 WORD_AUDIT / LEXICON_AUDIT 之外**新增 STYLE_AUDIT 阶段**（新 `build_style_audit_prompt`，工具白名单 = reviewer 读 + `rewrite_span`，verdict pass/fail，≤6 轮，接受判定同上）。
- **新增一键** `one_click/style_cleaner.py`（仿 `lexicon_cleaner`）：扫 reviewer high issues → 出 ProseDiff 改写提案卡，前端采纳。
- 验证：构造一段高 AI 味草稿，闭环应在 ≤N 轮把 high issues 清零且不恶化情节；前后端真实跑通。

### P5（可选）· 题材插件 + 参考库
- 扩 `genre_plugin.py`：玄幻/言情/悬疑/都市，每类带疲劳词表 + 爽点节拍（参考 InkOS genre-profile）。
- 把 14 本文风蒸馏报告 / 剧情模组导入资产库（`writing_style` / 剧情灵感），写作时 `search_assets` 引用。

---

## 五、数据 / DB 影响

- P1/P2/P5 主要是**数据 seed**（`writer_presets`、`forbidden_lexicon` 资产、`assets`），**优先用现有表**，原则上**不需新 Alembic revision**；若需新增"方法论来源"标记列才走 revision。
- P3 仅改 prompt 字符串 + 后端类别白名单，无 DB 改动。
- P4 STYLE_AUDIT 若需记录修订遥测（pre/post issue 数）可考虑新增轻量表，**需 Alembic revision**；首版可先不持久化，仅走 SSE。
- LLM：复用现有模块绑定；STYLE_AUDIT 复用 `writer_reviewer` + 一个改写模块（可复用 `writer_composer` 或新增 `writer_repair` 绑定）。**遵守"未绑定显式失败、无 fallback"。**

---

## 六、验证计划

1. 后端：`env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests`（新增针对 seed / 新审校类别 / STYLE_AUDIT 接受判定的单测，加 60s 超时）。
2. 前端：`npm run lint && npm run build`；真实点开 writer 工作台 → 写一章 → 看 reviewer/forbidden-lexicon/preset 面板 → 跑一键风格清理 → 采纳改写卡。
3. 端到端：同一 brief，注入前后各写一章，用 reviewer 死令命中数 + 人工读感对比。

---

## 七、非目标（明确不做）

- 不把 pi 作为独立 agent 运行时嵌入 MiroFish（会与现有 agent loop / LLM facility 重复冲突）。
- 不引入 mock 成功 / 静默 fallback / 隐式降级（违反 MiroFish 硬约束）。
- 不在本方案实施中改动当前 30 个未提交文件；不替作者 commit。
- 不破坏 reviewer 现有"非阻塞默认"行为；自动修订一律为可选开关。

---

## 八、落地清单（评审通过后按序执行）

- [x] P1 扩 `build_anti_cliche_constraints`（叙述范式·框架层）+ seed 预设 `scripts/seed_novel_methodology.py`
- [x] P2 BANNED_PHRASES → `scripts/seed_forbidden_lexicon.py`（全局禁词资产，44 条 block/warn）
- [x] P3 扩 reviewer 维度（5 类框架层死令）+ `reviewer._ALLOWED_CATEGORIES` 白名单 + 默认审校 prompt
- [x] P4 后端：book_run `STYLE_AUDIT` 阶段（非阻塞）+ 单场景 `auto_repair`（opt-in）+ `one_click/style_cleaner.py`（runner+schema+注册）
- [ ] P4 收尾（依赖 WIP 落地）：`api_fastapi/writer_agent.py` 加 `/one-click/scan-style` endpoint + write-scene 透传 `auto_repair`；前端按钮/开关
- [ ] P5（可选）题材插件 + 文风/剧情资产导入
- [ ] 全链路前后端验证 + pytest（运行 seed 脚本、真实写一章前后对比）

> 实施记录（2026-06-08）：P1–P4 后端已落地，全部 py_compile 通过。仅改干净文件，未触碰用户未提交的 `writer_agent.py`(API)/`tool_executors.py`/测试。我方新增/改：`prompts.py`、`reviewer.py`、`reviewer_prompt.py`、`book_run_orchestrator.py`、`orchestrator.py`、`one_click/__init__.py`、`one_click/style_cleaner.py`(新)、`schemas/writer_agent_schemas.py`、`scripts/seed_*.py`(新)。

> 来源参考：`可供参考项目/pi`（agent 架构）、`docs/reference-projects-analysis.md`（P0-1 写后审计+修订循环，源自 InkOS）、「小说梦想家」备份（SOUL v3.4 / PITFALLS 44 条 / BANNED_PHRASES / FRAMEWORK 15 步）。
