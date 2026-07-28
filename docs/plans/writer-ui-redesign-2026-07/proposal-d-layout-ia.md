# 方案 D：写作台布局与信息架构重构

日期：2026-07-27 · 状态：待评审 · 配套原型：`prototype-d.html`（页内可切协作/专注两态）

> 不动肤色动骨架。色板、字阶、圆角、阴影全部沿用 `apps/web/app/globals.css` 的
> "paper & vermilion" token；本方案只重做写作台的布局与 IA：谁是主角、东西放哪、
> 怎么进出、断点怎么变形。

---

## 1. 现状 IA 问题树

证据来自现行代码与用户截图（2026-07-27，用户圈注了 dock 全区与稿纸顶部裸框）。

### A. 方位违背契约，且主次倒挂

- `AGENTS.md` 的现行 IA 约定是「Writer Agent 作为常驻协作者位于**右侧** dock」；
  而 `writer-workspace.tsx:612` 把 dock `<aside>` 放在画布**左侧**（`border-r`，
  渲染在 `ManuscriptPaper` 之前）。导航 rail 本就在左，左侧叠了两条竖栏，
  视线起点被工具区占满，稿纸被挤到视觉二线。
- dock 内的用户气泡是实色朱红块（`writer-rail.tsx` `UserBubble`：
  `bg-accent text-panel shadow-accent`），是全屏最重的色块——「次」比「主」更抢眼，
  朱红作为"唯一主动作"的纪律被打破。

### B. 视图切换缺失（规范硬要求）

- 规范要求画布头有 `稿件 / 章节 / 审校 / 工具` 互斥标签
  （`docs/refactor-saas/04-design-system-and-ui.md` §写作台、`11-writer-workbench.md`
  §页面布局、`AGENTS.md`）。现行 `WriterCanvasTop` 只有章节 dropdown + 字数 +
  保存态 + 新章节，**没有任何视图切换**；审校、一键动作等能力在 UI 上无入口。

### C. 稿纸自身的三处硬伤

- 空 block 渲染成裸 textarea 边框盒（`manuscript-paper.tsx` `SegmentEditor`），
  placeholder「从这里开始写。空白的稿纸，等第一个字落下。」呈现为输入框而不是
  稿纸——用户截图圈出的红框之一。
- block 内容里的 `# 第一章` 以 raw markdown 直出（截图可见），稿纸没有题署层。
- 章节身份只在顶栏 dropdown 里，稿纸上读不到"我在读哪一章"的锚点。

### D. dock 内部密度与层级混乱

- 卡片三层嵌套框（TaskCard `border-line` → citations chips → CandidateCard
  `border-dashed border-gold/60` → SettledCard `border-line-soft`），360px 内信息
  被切碎。
- **候选稿是 agent 的核心产出，视觉却最弱**（虚线金框混在一堆白卡中）；
  已采用卡与 composer 说明重复说教（「已进手稿，可在稿纸上继续改」 vs
  「起草的内容先作候选稿，经你采用才进手稿」）。
- composer 下 hint 两行被裁断（截图可见「Shift+Enter 换行」的"行"字被切）。
- dock 头「常驻协作」是无功能死文字；「待审资产」入口挤在 dock 头并触发整卡
  3D 翻转（`composer-review-flip.tsx`）——gimmick 大于信息，且专注态下该入口
  随 dock 一起消失，队列计数不可达。

### E. 断点处 IA 塌陷

- `writer-workspace.tsx:612` 的 dock 是 `hidden wide:block`：**< 1200px 时 agent
  整个消失**，861–1199 窄桌面与 ≤860 移动带下写作台退化成纯阅读器。
  `11-writer-workbench.md` §Right Rail 明确要求 <860 时正文为主 + 章节进 Drawer +
  候选资产进 Sheet，入口保持可达。

### F. 悬浮物没有归宿

- `AGENTS.md` 要求 dock 是「选区驱动调用」，但现行稿纸没有任何选区交互锚点；
  command palette（`11-writer-workbench.md`）无入口；没有规则约束游离 FAB。

### G. 空态

- 无章节空态（`writer-empty.tsx`）本身可用，但与新骨架脱节（居中羽毛 + CTA 浮在
  空画布上）；章节内空 block 即 C；thread 空态（RailGreeting）与待审空态可保留。

---

## 2. 新布局总览

结构口诀：**一壳三带**。壳（顶栏 56px + 导航 rail）不动；写作台内部是
「画布工具行 + 主画布」的**画布带**（主角）与右侧**合著者 dock 带**（副主角，
可收起）；dock 收起后退化为右缘 48px **专注条**（第三带）。

### 2.1 协作态（≥1200，dock 展开）

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ 🪶墨鱼小说│书架│测试6›第1章▾│5,556字              ✓已保存│＋新章节 │ 顶栏 h56（外壳契约，不动）
├───┬────────────────────────────────────────────────────────────────┬─────────┤
│   │ ◀ 第1章/共4章 ▶   ┌──────────────────────┐   待审③│⌘K│⛶专注  │ ╲       │
│ N │                   │ 稿件│章节│审校│工具  │                       │ 合著者   │
│ A │ 画布工具行 h44 ───└──────────────────────┘─────────────────────│ [对话|待审③][⟨]│
│ V │ ┌──────────────────────────────────────────────────────────┐ │ ├───────┤ │
│ 6 │ │  第 1 章 · 本章 5,556 字 ──────────                      │ │ │ 引用条 │ │
│ 4 │ │  初入大奉（serif 题署）                                   │ │ │ 引用条 │ │
│ p │ │  ─────────────────────────────                          │ │ │ 任务卡 │ │
│ x │ │  正文正文正文正文……                        paper 760px    │ │ │ settled│ │
│   │ │  ▌正文（选段态）· [✦改写这段|扩写|引用到指令]              │ │ │ 引用条 │ │
│   │ │  正文正文正文正文……                                      │ │ │ 任务卡 │ │
│   │ │  │从这里接着写。空白的稿纸，等下一个字落下。               │ │ │ 召回chips│
│   │ └──────────────────────────────────────────────────────────┘ │ │ ┏━━━━━┓│ │
│   │   脚注：自动保存 · 候选稿经采用才进手稿                        │ │ ┃候选稿 ┃│ │
│   │                                                              │ │ ┗━━━━━┛│ │
│   │                                                              │ │ composer│ │
└───┴──────────────────────────────────────────────────────────────┴─────────┘
```

宽度节奏：nav 64 │ 画布 flex（稿纸栏 760 居中，1600px 下两侧各 ~208 呼吸区）│
dock 360。稿纸是全屏**最亮**的面（`--panel` 于 `--paper` 桌面），dock 用
`color-mix(paper-deep 34%, paper)` 比桌面深半度——层级靠材质差，不靠边框堆。

### 2.2 专注态（≥1200，dock 收起）

```text
├───┬──────────────────────────────────────────────────────────────────┬──────┤
│ N │ ◀ 第1章/共4章 ▶   [稿件│章节│审校│工具]   待审③│⌘K│⛶退出专注     │ 🪶  │
│ A │                                                                  │ 🗞③  │
│ V │              ┌────────────────────────────┐                      │      │
│ 6 │              │      paper（同一 760 栏）    │                     │  ⟨   │
│ 4 │              │      全文居中，无 dock 干扰    │                     │ 48px │
│   │              └────────────────────────────┘                      │ 专注条│
```

- dock 不是 `hidden`，而是收起为右缘 48px 竖条：羽毛（展开）、待审图标+计数
  badge、底部展开钮。**待审计数在专注态依然可达**（解决 D）。
- 稿纸栏宽不变（760 是排版常量），只是更居中；composer 不在场，但选区 mini bar
  与 ⌘K 仍可发起 agent 调用——沉浸不等于能力消失。
- 进出：画布工具行「专注」钮、dock 头收起钮、⌘.、⌘K 内命令；选择持久化
  `localStorage("mirofish.writer.focus")`。

### 2.3 861–1199（窄桌面：drawer 形态）

```text
├───┬─────────────────────────────────────────────────────────┬──────┤
│ N │ ◀ 第1章 ▶   [稿件│章节│审校│工具]        待审③│⌘K│⛶   │ 48px │
│ 6 │        paper 全宽（不再为 dock 让位）                      │  条  │
│ 4 │                                                          │      │
└───┴──────────────────────────────────────────────────────────┴──────┘
        点羽毛/待审 → dock 以 fixed overlay 滑出（360px，shadow-lift，盖住画布右缘，
        稿纸不被挤压；点外/Esc/收起钮收回）
```

### 2.4 ≤860（单列）

- 导航 rail 隐入顶部抽屉（外壳既有行为）；画布工具行保留 segmented（触控目标
  ≥44px），章节步进退化为纯图标，字数/品牌名隐藏。
- dock = 右缘全高 drawer，`width: min(360px, 100vw − 20px)`；composer 随 drawer。
- 稿纸 padding 收缩（36/22），题署保留。

---

## 3. 各态说明

### 3.1 画布工具行（新，h44，写作台自己的栏）

| 区 | 内容 | 说明 |
|---|---|---|
| 左 | `◀ 第 1 章 / 共 4 章 ▶` | 相邻章步进（写作中高频）；全表走顶栏 dropdown，模糊跳转走 ⌘K —— 三通道分工不重复 |
| 中 | `稿件│章节│审校│工具` segmented | 画布主权的标志，居中；`bg-paper-deep/55` 槽 + active `bg-panel shadow-hairline` |
| 右 | `待审③` pill | 金色 pill + 计数；点击 = dock 展开并切到待审面板（专注态同样生效） |
| 右 | `⌘K` | 命令栏入口 |
| 右 | `⛶ 专注` | toggle；active 时 accent-wash + 「退出专注」 |

### 3.2 稿件视图（默认）

- **题署**：稿纸头部新增 eyebrow「第 N 章 · 本章 N 字」+ hairline + serif 章题
  （`chapter.title`）。渲染时剥离 block 行首 ATX 标题（`^#\s+`），「# 第一章」
  不再 raw 直出（纯展示层处理，不动数据）。
- **空段**：不再出现裸框。空 block / 文末续写位呈现为稿纸上一行 placeholder 色
  的邀请文字（闪烁光标），focus 时才进入编辑——稿纸永远是纸，不是表单。
- **段落**：segment 间取消分隔线，纯 26px 间距（连续阅读）；hover 露段落 handle。
- **选段态**：accent-wash 底 + 左缘 2px 朱红 + 锚定 mini bar（ink-surface 深色小条：
  `✦改写这段 │ 扩写 │ 引用到指令`）——选区驱动调用的 UI 锚点，全屏唯一的
  锚定浮动元素。

### 3.3 章节视图

章节列表（序号 serif / 题 / 首段预览 / 字数 / 状态 pill / ›），当前章 accent-wash
渐变 + 左缘朱红条；头部「全书 N 章 · 共 N 字」+ 新章节。承接大纲与章节管理
（后续接 outline versions / scenes）。

### 3.4 审校视图

审校报告：`writer_reviewer` 的 issues 列表（严重度 pill + 标题 + 描述 + 「定位」
跳回稿件视图对应段落）；头部「上次审校时间」+「运行审校」。未运行时是引导空态。

### 3.5 工具视图

一键动作卡（2 列 grid）：完善大纲 / 对齐字数 / 扫描禁用词 / 补全关系 / 续写本章 /
导出手稿——落实 `11-writer-workbench.md`「不要散落按钮，统一到 command row」；
每次运行为 workflow/短任务并写入合著者 thread；底部「最近运行」记录。

### 3.6 合著者 dock（360px，双面板）

```text
┌─ dock-head h44 ─────────────────┐
│ 🪶 合著者      [对话│待审③] [⟨] │  ← tabs 取代 3D flip；⟨ 收起进专注
├─ 对话面板 ──────────────────────┤
│  引用条（用户指令，右对齐）       │  ← 实色红气泡退役：accent-wash 底 +
│  任务卡一行（✓ 已完成 · 候选稿…）│     右缘 2px 朱红 + ink-soft 文字
│  settled 一行（✓ 已采用…查看正文）│  ← 压扁为一行，▾ 才展开原文
│  ┏ 候选稿 ┃─────────────────    │
│  ┃ 候选稿 · 2,046字 (金字 eyebrow)│  ← dock 内第二主角：实卡、金字题头、
│  ┃ serif 预览 5 行 + 渐隐        │     serif 预览、[采用进手稿] 唯一实色朱红
│  ┃ [展开全文]  [采用进手稿] [⋯]  │
├─ composer ──────────────────────┤
│ border-t hairline 分界；hint 一行 │
└──────────────────────────────────┘
```

- 召回 chips 一行半内敛排布；一致性提醒（gold）保持现状语义。
- 待审面板 = 现行 `ProposalRail` 队列（工具行 + 卡片 + 出处 + 采纳/合并/拒绝），
  去掉 flip 壳的重复标题与「返回合著者」按钮。

### 3.7 ⌘K 命令栏

居中模态（560px，top 18vh，backdrop blur）：分组「动作（续写本章 ⌘↵ / 审校本章 /
完善大纲 / 扫描禁用词）· 跳转（章节列表带字数）· 视图（专注 ⌘. / 待审）」。
动作与工具视图共用同一 dispatch；跳转复用章节数据。

### 3.8 空态

- 无章节：`WriterEmpty` 居中大邀请保留，视觉对齐稿纸体系（P2 微调）。
- 章节内空：见 3.2（邀请行）。
- thread 空 / 待审队列空：保留现行文案与样式。

---

## 4. 交互流

1. **起草 → 采用 → 待审**：composer 发指令 → thread 追加引用条 + 任务卡（流式）→
   候选稿卡（预览）→「采用进手稿」→ 正文落到稿纸末尾（卡片折叠为 settled 一行）
   → 蒸馏 enqueue，`待审` 计数 +N（cb pill / dock tab / 专注条 badge 三处同步）→
   作者进待审面板逐条采纳/合并/拒绝。
2. **选区驱动调用**：稿纸选中段落 → 锚定 mini bar →「改写这段」以选区为上下文
   发起 run（dock 未展开时自动展开）；「引用到指令」把选区摘录进 composer。
3. **专注进出**：任何入口（钮/⌘./⌘K/收起钮）→ dock 280ms 收为右缘条；待审计数
   全程可见；点 badge → 直接展开到待审面板。
4. **章节跳转**：相邻=步进钮；全表=顶栏 dropdown；模糊=⌘K；视图=章节 tab——
   四通道按频率分层。
5. **断点变形**：窗口拖过 1199 → dock 自动转 overlay drawer（展开状态记忆）；
   拖过 860 → 单列 + 抽屉导航；反向恢复。所有变形只改形态不改状态。

---

## 5. 响应式规则汇总

| 断点 | nav | 画布 | dock | 稿纸栏 |
|---|---|---|---|---|
| ≥1200 | 64 rail（可收 64/224） | 工具行 + 视图区 | 常驻 360 流内列 | 760 居中 |
| 861–1199 | 同上 | 全宽 | 默认收起 48 条；展开=fixed overlay 360 + shadow-lift | 760 居中，不被挤压 |
| ≤860 | 抽屉 | 工具行精简（≥44px 触控） | 右缘 drawer min(360, 100vw−20) | 全宽，padding 36/22 |

断点沿用 token（`stack: 861px` / `wide: 1200px`），新增一个宽度 token
`--spacing-rail-focus: 48px`（专注条）。

---

## 6. 悬浮物归宿（立规）

写作台只允许三类动作入口：**顶栏**（章节/字数/保存/新章节）、**画布工具行**
（视图/待审/⌘K/专注）、**dock 内**（agent 相关全部）。全屏仅两个浮动元素且都
锚定上下文：选区 mini bar（锚定选段）、⌘K palette（模态）。**禁止游离 FAB**；
后续任何新动作先进这三处，评审时以此为准。

---

## 7. 与现行代码的映射改动清单

| 文件 | 改动 |
|---|---|
| `writer-workspace.tsx` | dock `<aside>` 移到画布右侧（`border-r`→`border-l`）；删 `hidden wide:block`，改 `data-focus` 控制 + 861–1199 overlay drawer + ≤860 sheet；新增 focus 状态（localStorage 持久）；挂载新 `WriterCanvasBar`、`WriterFocusStrip`、`WriterCommandPalette`；pendingCount 从 flip 上提到本层（同时喂 cb pill / dock tab / focus strip badge）；新增 view state（manuscript 默认，切视图不丢编辑态） |
| `writer-canvas-top.tsx` | 保留（章节 dropdown/字数/保存/新章节）；视图切换**不**进顶栏 |
| 新 `writer-canvas-bar.tsx` | ChapterStepper / ViewSwitch segmented / ReviewPill / ⌘K 钮 / FocusToggle |
| 新 `writer-focus-strip.tsx` | 48px 右缘条：羽毛 / 待审 badge / 展开钮 |
| 新 `writer-command-palette.tsx` | ⌘K 模态：动作 dispatch（复用 handleSend / 章节跳转 / 视图切换） |
| `writer-rail.tsx` | UserBubble 实色气泡 → 引用条；CandidateCard 升级（实卡 + eyebrow + serif 预览 + [采用进手稿] + ⋯ 菜单）；SettledCard 压扁一行（▾ 展开原文）；删「常驻协作」死文字与 headerAction flip 触发；RailGreeting 保留 |
| `composer-review-flip.tsx` | **退役**，替换为 `writer-dock-panels.tsx`（对话/待审 双面板 switch，220ms 淡入；去 3D rotateY 与返回按钮） |
| `proposal-rail.tsx` | 队列结构保留；视觉随 dock 材质微调 |
| `manuscript-paper.tsx` | 新增题署（eyebrow + serif 章题）；展示层剥离行首 ATX 标题；空 block/文末续写位改为无框邀请行；segment 分隔线 → 纯间距；新增选段态 + 锚定 mini bar（接选区 API，P2 接通） |
| `writer-composer.tsx` | hint 压一行；composer 上加 border-t hairline；其余保留 |
| `writer-empty.tsx` | 结构保留，P2 视觉对齐 |
| `globals.css` | 不新增色板；加 `--spacing-rail-focus: 48px`；dock 材质用 color-mix 组件内联 |

## 8. 落地范围

- **P0 骨架（纯布局，无新能力）**：dock 右移 + 专注条 + 断点 drawer；画布工具行 +
  segmented（章节/审校/工具先上"既有能力的最小面板"）；flip → panels；引用条；
  候选稿卡升级；稿纸题署 + 空段邀请行；composer hint。
- **P1 IA 补全**：⌘K palette（导航/视图/三个真实动作）；章节视图完整；审校视图接
  `writer_reviewer`；工具视图接一键 actions。
- **P2 交互深化**：选区 mini bar 接通选区 API；专注态记忆打磨；`WriterEmpty` 对齐；
  动效精修。
- **明确不做**：不改顶栏/导航外壳；不动 token 色板；不恢复任何已退役元素
  （`writer-studio-grid`、折叠 composer、深色 rail、旧蓝 UI）；3D flip 删除不留开关；
  manuscript-primary 与 conversation-first IA 不动摇（稿件仍是默认视图与最大面）。

## 9. 验证记录（截图迭代）

| 轮次 | 截图 | 结论 |
|---|---|---|
| v1 | `shots/d-collab-v1.png` / `d-focus-v1.png` | 骨架成立；发现：mini bar 压上一段、task 卡文字居中、demo 开关遮挡 composer |
| v2 | `shots/d-collab-v2.png` / `d-focus-v2.png` | 修正前两处；发现 margin-top 被 `.seg + .seg` 特异性压过，mini bar 仍压字 |
| v3 | `shots/d-collab-v3.png` / `d-focus-v3.png` / `d-mid-v3.png` / `d-chapters-v3.png` / `d-tools-v3.png` / `d-cmdk-v3.png` | 特异性修复；两态终检、1150px drawer、章节/工具视图、⌘K 逐一验证通过，定稿 |

对比度自查：正文级文字全部使用 token 内既有合规色（`ink` / `ink-soft` / `muted` /
`muted-soft` / `candidate` / `accent` on `paper` / `panel` 均 ≥4.5:1）；引用条为
`ink-soft` 于 `accent-wash(0.055)` 底，等效纸面对比度不降级；11px 仅用于 badge
计数图形，不用于阅读文字。

原型操作：`prototype-d.html` 页内可点 —— 视图四 tab、dock「对话/待审」tabs、
「专注」钮（或 ⌘.）、⌘K（或点 ⌘K pill）、专注条各钮、右下角"原型开关"
（非产品 UI，仅评审用）。`#focus` hash 直达专注态。
