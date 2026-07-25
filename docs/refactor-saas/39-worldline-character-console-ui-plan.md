# 39. 世界线 × 角色控制 前端 UI 开发方案

更新时间：`2026-07-24`
状态：**C0–C4 已实现（静态/空态/回放/移动端就位），待真实后端联调验收**。两个界面已按本文重建为真实 workbench，路由 `worldline` / `characters` 均接入；C2 推演态与 C3 舞台态的「活数据」流转仍需在真实后端（compose 拉起）下做端到端验收。本文是二者 UI 开发的方案与实现记录。

> 本文只规定**前端界面与交互**。领域语义以 `09-worldline.md`、`10-character-console.md` 为准；
> 视觉令牌以 `apps/web/app/globals.css` 为准；布局配方对齐已建成的 assets / graph / writer 三个 workbench。
> 是否已完成仍以 `24-current-development-progress.md` 与当前 worktree 为准，不以本文推断进度。

---

## 0. 一页速览

| 项 | 结论 |
|---|---|
| 要建什么 | 两个独立 workbench：**世界线**（导演监视器）与**角色控制**（第一人称舞台）。**不合并**，但共享角色档案/记忆/名册组件 |
| 视觉语言 | 沿用全站「纸感朱砂」：暖纸底 `#f7f2e9` + 手稿白面 `#fffdf8` + 朱砂 `#8f211b` 唯一主操作 + 旧金 `#b5854a` 只做候选态 + 宋体正文/书法标题 |
| 布局配方 | 复用全站统一骨架：**栏目眉（朱砂小字 + 宋体大标题 + 一句 tagline）→ 左轨 → 中央主区 → 右检查器（380px 内联 / <lg 覆盖）** |
| 两界面差异 | 世界线主区 = **纵向演化时间线**（时间是主角）；角色控制主区 = **互动场景流 + 底部 composer**（对话是主角） |
| 核心安全契约 | 推演/互动只产**候选**（旧金虚线），进正史/正典必须作者**显式采用**（朱砂）；后端缺位给真实作者化原因，绝不伪造数据 |
| 不做 | 不新建深色控制台、不堆技术 trace、不做多分支对比、不复制旧 Vite 蓝 UI、不 mock 假后端 |

---

## 1. 设计哲学：两个界面，两种「看世界的姿势」

上一轮分析已确认：世界线与角色控制操作**同一批角色资产**（worldline agent 通过 `source_asset_id` 指回资产库角色；角色控制 `pov_agent_id` 落在 worldline session 之上），核心动词不重复。这条结论落到视觉上，就是**两个界面必须有不同的「性格」，但共享同一套语言**。

| | 世界线 Worldline | 角色控制 Character Console |
|---|---|---|
| 心智 | **上帝视角的导演**——俯瞰全局，推时间、注变量、审候选 | **第一人称的演员**——代入单角色，说我做、对话、转写 |
| 主语 | 「这个世界接下来会发生什么」 | 「我（这个角色）此刻想做什么」 |
| 主角 | **演化时间线**（canon 事件 + 候选事件流） | **互动场景流**（turn 流：我说/我做/角色反应/世界反馈） |
| 节奏 | 步进式、可暂停、可回看 | 连续、沉浸、实时流式 |
| 比喻 | 剪辑台 / 监视器墙 | 舞台 / 第一人称剧本 |

> 一句话：**世界线像剪辑台，角色控制像舞台。** 剪辑台要信息密度与时间纵深；舞台要沉浸与对话流动。两者都坐在同一张「纸面案头」上。

---

## 2. 共享语言：两个界面必须一致的 8 条规则

这些是全站已有的「高级感」来源，新界面逐条继承，**不发明新令牌**：

1. **栏目眉三段式**（每个 workbench 顶部的固定开场，assets/graph/writer 都在用）：
   - 朱砂小字标签：`text-[11.5px] font-medium tracking-[0.28em] text-accent`，如「世 界 线」「角 色 控 制」；
   - 宋体大标题：`font-serif text-[26px] font-semibold text-ink`，如「演化时间线」「互动舞台」；
   - 一句 muted tagline：`max-w-[560px] text-[13.5px] text-muted`，解释这个界面是干什么的。
2. **主区在白面 `bg-panel`，轨道在纸面 `bg-paper`**：主内容（时间线/场景流）放手稿白面承载，左右轨用更暖的纸面收边，`border-line-soft` 分隔，不靠阴影堆叠层级。
3. **朱砂唯一主操作**：每屏一个朱砂动作——世界线是「启动整备 / 推进」，角色控制是「发送 / 转写为草稿」。其余操作降为 `border-line` 描边次级按钮或文字按钮。
4. **旧金唯一候选语义**：凡是「推演出来、还没进正史」的东西（候选事件、待采用提案、导演建议）一律旧金虚线框 + 「候选」角标；采纳动作才是朱砂。**这条是安全契约的视觉化，两界面完全一致。**
5. **角色一律印章化处理**：角色头像不用圆形照片感，用「朱砂/墨色方印」——首字书法字 + 近无圆角方底（`rounded-[3px]` + `bg-accent-wash text-accent` 或墨色版）。这与资产库角色卡、故事图谱的「圆形朱砂印章」节点同源，是全站最具辨识度的母题。
6. **正文宋体沉浸**：场景流、事件正文、角色台词用 `font-serif` + `leading-[1.9]`，正文居中 `max-w-[680px]`，保证阅读沉浸；元信息/时间戳/控制用 `font-sans` 小字。
7. **检查器统一 380px 右栏**：桌面内联列、`<lg` 覆盖面板（`max-lg:fixed max-lg:inset-y-0 max-lg:right-0 max-lg:shadow-panel`），滑入滑出用 `DUR.med + EASE`。角色档案、候选详情、变量详情都走这一个壳。
8. **动效三档、只动 transform/opacity/color**：`fade-up`（Y 位移 14px + 透明）用于区块入场，`slide-in`（X）用于检查器；`MotionConfig reducedMotion="user"`；`prefers-reduced-motion` 关闭非必要动画。流式新增内容用「上浮浮现」而非「弹跳」。

---

## 3. 世界线 workbench：导演监视器

路由：`/projects/{id}/worldline` → `WorldlineWorkspace`（新增 `app/projects/[projectId]/worldline/`）。

### 3.1 两种状态（沿用写作台「一个路由两种状态」的减法）

| 状态 | 触发 | 形态 |
|---|---|---|
| **起点态** | 无活跃 session，或点「新推演」 | 居中「推演目标」大输入框 + 3–4 个示例目标 + 「最近 session / 已存路径」入口。**默认走目标驱动**（Pi cast planner 自动选角），手动选角收进「高级」折叠。 |
| **推演态** | 启动整备，或打开既有 session | 三栏：左「整备轨」/ 中「演化时间线」/ 右「候选 + 检查器」。 |

### 3.2 推演态布局

```text
┌────────────────────────────────────────────────────────────────────┐
│ 栏目眉:  世 界 线   演化时间线            《书名》· {session.label}   │
│         单世界剧情推演：启动、变量注入与事件流。        [status 章]    │
├──────────┬──────────────────────────────────────────┬──────────────┤
│ 左·整备轨 │ 中·演化时间线（主区，白面，纵向滚动）      │ 右·候选/检查器 │
│ (260px)  │                                          │  (340–380px) │
│          │  ┌ 世界状态卡（当前步 · 注入变量 · 目标） ┐ │              │
│ 整备状态  │  └────────────────────────────────────┘ │ 候选事件列表  │
│ 演员名册  │   ○ STEP 1 ── canon 事件卡              │  (旧金虚线)   │
│  (印章列) │   ○ STEP 2 ── canon 事件卡              │              │
│          │   ● STEP 3 ── 当前步（导演思考 overlay） │              │
│ 变量锁    │   ◌ 候选事件 → 落入右栏待审              │              │
│  (金锁列) │                                          │ 点选→角色/   │
│          │  [底部常驻·运行控制条]                     │ 事件检查器    │
│          │  推进一步 / 自动演化 / 注入变量            │              │
├──────────┴──────────────────────────────────────────┴──────────────┤
│ 底（按需·折叠成一行）: 自动演化进度 · 失败原因 · 已存路径入口          │
└────────────────────────────────────────────────────────────────────┘
```

**左·整备轨（260px，纸面）**
- **整备状态卡**：prepare 状态（整备中/就绪/可续传），失败给真实原因 + 「续传」。
- **演员名册**：角色印章纵向列表（`SimulationRoster` 的现代化），每项 = 印章 + 名字 + 角色/状态小字；点选在右检查器看 dossier。**默认由 cast planner 填好**，手动增删减「高级」。
- **变量锁**：注入变量列表，每条带旧金小锁（锁定=约束传入下一轮），可单条锁/全锁；新增变量走底部运行控制条的「注入变量」。

**中·演化时间线（主区，白面，纵向）** —— 本界面灵魂
- 顶部**世界状态卡**：当前 STEP、注入变量摘要、推演目标、目标达成度（若 `worldline_goal_evaluator` 给出）。
- **纵向时间线**：每个 canon 事件一张「事件卡」——左侧时间点（STEP 编号）+ 竖向墨线串联，卡片白面近无圆角、宋体标题 + muted 摘要 + 涉及角色印章缩略。**canon = 实线墨边；当前步 = 朱砂描边高亮。**
- **导演思考 overlay**：自动演化流式时，当前步上方浮一层「导演思考」卡（问题/考量因素/候选数），随 SSE 实时更新；流结束收敛为一条状态行。**过程折叠成一行，可逐级展开**，与写作台任务状态行同一哲学。
- **候选事件不落进时间线正文**——流向右栏待审，采用后才变成 canon 事件卡插入时间线。这条保证「时间线永远是已确认的正史」，候选与正史视觉永不混淆。

**底部·运行控制条（常驻，白面，上边线）**
- 主操作（朱砂）：无 session 时「启动世界线整备」，有 session 时「推进一步」。
- 次级：「按当前模式自动演化」（连续 N 步 + 最终条件）、「注入变量」（展开行内输入）。
- 推演模式（手动 / 首轮自动 / 持续自动）用一个安静的 segmented control，不抢戏。

**右·候选 / 检查器（340–380px）**
- 默认**候选事件列表**（旧金虚线卡）：每条 = 标题 + 摘要 + 置信度 + 来源标签（档案驱动/目标驱动/变量触发/角色主动）+ 涉及角色印章；操作 = 采纳（朱砂）/ 拒绝 / 编辑后果（展开 textarea）。
- 点选某条候选或某角色印章 → 切到**检查器**（沿用 380px 壳）：候选详情（含 `state_changes`）或角色 dossier（见 §5 共享组件）。

### 3.3 世界线的「高级感」落点
- 时间线竖线用「渐变墨线」+ 节点印章化，当前步一点朱砂，远看像一条装裱的立轴。
- 世界状态卡像一张「榜文」贴在卷首，书法小标题 + 宋体正文。
- 自动演化时，时间线底部「推进一步」的朱砂按钮变为呼吸态加载，时间线顶部浮现导演思考——**界面的「动」只发生在时间轴上，其余保持安静**，这是密度与沉浸的平衡。

---

## 4. 角色控制 workbench：第一人称舞台

路由：`/projects/{id}/characters` → `CharacterConsoleWorkspace`（新增 `app/projects/[projectId]/characters/`）。

### 4.1 两种状态

| 状态 | 触发 | 形态 |
|---|---|---|
| **降临态** | 未选 session/角色/节点 | 居中三步引导（非 wizard 弹窗，而是页内三段）：选 worldline session/已存路径/章节节点 → 选可扮演角色（印章网格）→ 确认降临节点卡（标题 + 世界状态摘要）。 |
| **舞台态** | 确认降临 | 三栏：左「会话轨」/ 中「场景流 + composer」/ 右「角色档案」。 |

### 4.2 舞台态布局

```text
┌────────────────────────────────────────────────────────────────────┐
│ 栏目眉:  角 色 控 制   互动舞台         {角色印章·名字} · {mode}      │
│         以第一人称进入角色，在当前世界节点互动写作。   [降临节点▾]     │
├──────────┬──────────────────────────────────────────┬──────────────┤
│ 左·会话轨 │ 中·场景流（主区，白面，居中 680px，纵向）  │ 右·角色档案   │
│ (260px)  │                                          │  (340–380px) │
│          │   ⌇ 系统: 你降临在「雨夜谈判前」            │              │
│ 会话列表  │   ➤ 我说:……（朱砂气泡，右对齐）            │ 角色档案      │
│ 已存路径  │   ➤ 我做:……                               │  (印章大)     │
│ 互动历史  │   ● 角色反应 / 世界反馈（宋体正文，左对齐） │ 记忆          │
│          │   ◌ 候选提案（旧金虚线→采纳）              │ 关系态        │
│          │                                          │ 互动大纲      │
│          │  [底部常驻·composer]                       │              │
│          │  [我说][我做][我内心][我想影响] + 输入 + 发送│              │
├──────────┴──────────────────────────────────────────┴──────────────┤
│ 底（常驻·一条）: 保存互动 · 转写为章节草稿 → 写作台                    │
└────────────────────────────────────────────────────────────────────┘
```

**中·场景流（主区，白面，居中 680px）** —— 本界面灵魂
- 本质是一条「第一人称剧本流」，但**不是聊天页的廉价气泡**：
  - **系统/降临提示**：居中、muted、细体，像剧本旁白。
  - **我的回合（user）**：朱砂浅底气泡、右对齐，前缀小标签「我说 / 我做 / 我内心 / 我想影响」。
  - **角色反应 / 世界反馈（agent/director）**：左对齐、宋体正文、无气泡感（像小说段落），`leading-[1.9]`。
  - **候选提案（proposal）**：旧金虚线卡（记忆/关系/世界态候选），内嵌「采纳」朱砂小按钮——与资产库候选采纳同一视觉契约。
- 流式回复走 token 流（`character_dialogue`），打字机式浮现 + 末尾光标。
- **模式切换**（第一人称 / 导演辅助 / 对话 / 回放）用栏目眉右侧的安静 segmented，不切页面。

**底部·composer（常驻，白面，上边线）**
- 四个「行动类型」chip（我说 / 我做 / 我内心 / 我想影响谁）+ 自动增高输入 + 朱砂「发送」。选中 chip 给输入框一个语义前缀，落到 `turn.turn_kind`。
- 空态给一句引导（如「此刻，你想让 TA 做什么？」）。

**左·会话轨（260px，纸面）**
- 会话列表（active/saved/archived）、已存路径、互动历史（可进入回放态）。当前会话朱砂小圆点标记。

**右·角色档案（340–380px）**
- **共享的 `CharacterDossierPanel`**（见 §5）：当前 POV 角色的 dossier——大印章 + 名字 + public profile（role/status/摘要）+ 记忆 + 关系态 + 互动大纲。
- 只展示 public 字段；缺 backend 时给真实错误，**不伪造角色记忆**（安全契约）。

**底·一条常驻动作**
- 「保存互动」「转写为章节草稿」——后者是朱砂主操作，触发 interaction→Writer handoff，明确显示「Writer run 已排队」，**不谎称草稿已生成**。

### 4.3 角色控制的「高级感」落点
- 整个主区读感像一页**正在书写的剧本**：旁白细、台词朱、世界反应如小说段落，三种声部一眼可辨。
- 角色印章是视觉锚点：降临节点卡、栏目眉、composer 旁、档案顶都复用同一枚印章，强化「我就是这个角色」的代入。
- 候选提案用旧金「贴条」浮在剧本流里，采纳后安静消失并沉淀为 canon——**界面像一张案头稿纸，推演痕迹可留可去。**

---

## 5. 共享组件：消除重复的那一块

上一轮分析确认：两界面唯一实质重复是「角色只读档案/记忆/关系/历史」面板 + 「角色名册/选择器」。抽成共享组件，两界面复用，**界面保持分开、组件收敛一处**。

新建 `apps/web/components/character/`：

| 组件 | 用途 | 世界线 | 角色控制 |
|---|---|---|---|
| `CharacterSeal` | 角色印章（首字书法 + 方底，多尺寸/多色态） | 名册、事件卡涉及角色 | 降临、栏目眉、composer、档案 |
| `CharacterDossierPanel` | 角色档案右栏：public profile + 记忆 + 关系态 + 历史 | 检查器 | 右栏默认 |
| `CharacterRoster` | 角色名册列表（单选/多选 mode） | 演员名册（多选/整备） | 降临选角（单选） |
| `CandidateReviewCard` | 旧金虚线「候选→采纳」卡（事件/提案通用骨架） | 候选事件 | 候选提案 |

数据源：角色 dossier 走 worldline agent 端点（`.../agents/{id}`、`agent-memory`/`agent-history`/`relation-history`）；候选采纳分别走 `worldline-events/{id}/adoptions` 与 `character-interactions/{id}/proposals/{assetId}/adoptions`。**组件只负责呈现与显式动作，不伪造数据。**

---

## 6. 状态、诚实与降级（两界面共同）

延续全站「不伪造」的铁律，逐条落到 UI：

1. **后端缺位**：worldline / character-interactions 路由当前 BFF 未转发（见 §7），若代理 404 或返回 `*_BACKEND_UNCONFIGURED`/503，界面显示**明确的作者化空态/错误**（如「世界线服务还没接好，请稍后再试」+ 重试），**不渲染假时间线、假角色、假记忆**。
2. **加载**：骨架屏（`animate-pulse` 灰条），不用 spinner 堆叠；主区骨架按真实布局占位，避免跳动。
3. **空态**：必给下一步。世界线空项目→「填一个推演目标，开始第一次推演」；角色控制无会话→「先去世界线跑一段推演，再来代入角色」。
4. **失败**：真实原因 + 重试，不假装成功；并发冲突（乐观锁 `ASSET_VERSION_CONFLICT` / 双采纳）提示「刚在别处被改过，已刷新」。
5. **候选/正史分色**：候选=旧金虚线、正史=墨实线，永不混色。
6. **流式**：SSE 断线给「连接中断，正在重连」状态行 + 重试；`Last-Event-ID` 续传（沿用写作台事件流经验）。

---

## 7. 工程落地：文件骨架 + BFF 待办

### 7.1 新增文件（对齐现有 workbench 结构）

```text
apps/web/app/projects/[projectId]/
  worldline/
    worldline-workspace.tsx        # 三栏壳 + 状态机
    worldline-timeline.tsx         # 演化时间线（主区）
    worldline-event-card.tsx       # canon / 候选事件卡
    worldline-prepare-rail.tsx     # 左·整备轨（名册+变量锁）
    worldline-run-controls.tsx     # 底部运行控制条
    worldline-candidate-rail.tsx   # 右·候选列表
    worldline-director-overlay.tsx # 导演思考 overlay
    use-worldline-evolution.ts     # SSE 自动演化流
    worldline-motion.ts            # DUR/EASE/fadeUp（复用 asset-motion 模式）
  characters/
    character-console-workspace.tsx
    character-descend.tsx          # 降临态三步
    character-scene-stream.tsx     # 场景流（主区）
    character-composer.tsx         # composer + 行动 chip
    character-session-rail.tsx     # 左·会话轨
    character-motion.ts
apps/web/components/character/      # §5 共享组件
    character-seal.tsx
    character-dossier-panel.tsx
    character-roster.tsx
    candidate-review-card.tsx
apps/web/lib/api/
    worldline-client.ts / worldline-types.ts
    character-console-client.ts / character-console-types.ts
```

`[section]/page.tsx` 增加两个分支：`worldline → <WorldlineWorkspace>`、`characters → <CharacterConsoleWorkspace>`。

### 7.2 BFF 待办（绕不开的前置）

`app/api/projects/[projectId]/[...path]/route.ts` 的 allowlist 目前**不含** worldline / character-interactions，需新增转发：

- worldline：`preparations`、`sessions`、`sessions/{id}/auto-evolutions`、`sessions/{id}/variables`、`sessions/{id}/events`、`worldline-events/{id}/adoptions`、`sessions/{id}/saved-paths`（注意 run 级顶层 `/v1/worldline-sessions/...`、`/v1/worldline-events/...` 不在 `/projects/` 前缀下，同写作台 writer-runs 的处理）。
- character-interactions：`POST/GET /v1/projects/{id}/character-interactions`、`/{id}`、`/{id}/turns`、`/{id}/events`(SSE)、`/{id}/dialogue`、`/{id}/proposals(/.../adoptions)`、`/{id}/chapter-drafts`、`PATCH /{id}`。

---

## 8. 波次切分（逐块可验收，真实后端）

| 波次 | 内容 | 出口标准 |
|---|---|---|
| **C0 探路** | BFF 转发 worldline + character-interactions；typed client + types；实跑一次 prepare / 建一个 interaction，验证后端连通 | 拿到真实 session / interaction id，或明确失败原因 |
| **C1 共享组件** | `CharacterSeal` / `CharacterDossierPanel` / `CharacterRoster` / `CandidateReviewCard` + 角色档案数据接入 | 两界面都能渲染真实角色档案 |
| **C2 世界线** | 起点态 + 推演态三栏：整备轨、演化时间线、运行控制条、候选采纳、SSE 自动演化 | 填目标→整备→推进→候选→采纳→时间线沉淀 |
| **C3 角色控制** | 降临态 + 舞台态三栏：场景流、composer、会话轨、角色档案、提案采纳 | 降临→发一句「我说」→看到真实角色反应流→提案采纳 |
| **C4 转写收口** | 互动保存/归档、转写为章节草稿 handoff 到写作台、回放态、移动端 | 互动转 Writer run 排队可见、回放可读、移动端可用 |

每波次：focused tests 先行 → 实现 → 真实后端端到端（compose 拉起）→ 浏览器实测截图存证。

---

## 9. 验收清单（终态）

- 两界面栏目眉、令牌、印章、候选/正史分色与全站完全一致，无新建深色/异色中心。
- 世界线：能填目标整备、推进、注入并锁定变量、SSE 自动演化、候选采纳/编辑/拒绝、保存路径；时间线只沉淀已确认正史。
- 角色控制：能选 session/角色/节点降临、以四种行动类型互动、看到真实角色反应流、采纳提案、保存/归档互动、转写为章节草稿进写作台。
- 角色档案/名册在两界面来自同一共享组件、同一份数据，无重复实现。
- 后端缺位/失败/并发冲突都显示真实作者化原因 + 重试，无伪造数据、无静默降级、无 mock。
- 桌面三栏、移动两态，无横向滚动；`prefers-reduced-motion` 生效。

---

## 10. 明确不做

- 不把两界面合并成一个；不新建深色控制台 / 调试面板。
- 不做多分支 worldline 对比、社交媒体/舆情语义。
- 不把技术 trace/原始 JSON/UUID 堆进主 IA（收进授权抽屉）。
- 不复制旧 Vite 蓝 UI / 旧 worldline 三栏的深蓝导演台配色。
- 不写 stub/mock 假后端演示页、不写死领域数据。
- 候选不自动进正史/正典；转写不谎称草稿已生成。
