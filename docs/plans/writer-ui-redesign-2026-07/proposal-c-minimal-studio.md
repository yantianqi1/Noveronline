# 方案 C：现代极简工作室（Minimal Studio）

写作台 UI 重设计方案 C · 2026-07-27 · 原型：`prototype-c.html`（整屏静态复刻，1600×1000 验证）· 最终截图：`prototype-c.png`

---

## 0. 一句话定位

把写作台从「纸墨书房」的情绪化表达，换成 **Linear / Attio / iA Writer 式的中性极简工作室**：暖灰中性色阶 + 单一黛蓝 accent、hairline 分隔取代卡片阴影、字号收敛到 4 级、kbd/命令栏文化。工具退后，文字向前。

本方案**不动信息架构**：manuscript-primary（连续稿件为主画布）与 conversation-first（Agent 常驻 dock：连续 thread + 常驻 composer + 选区驱动调用）完整保留；只重做视觉层级、组件密度与交互质感。

---

## 1. 现状诊断（用户截图可见的问题）

对照用户标注的截图（`ScreenShot_2026-07-27_235635_952.png`），现行界面的核心问题不是「哪里坏了」，而是**视觉重量分配失当**：

1. **色彩噪音压过内容**。合著者 rail 里大面积朱砂气泡（`bg-accent` + `shadow-accent`）、金色引用 chips、红色「查看正文」链接、金色候选稿虚线框——一屏内同时存在 4 种强调色，作者视线被 rail 夺走，稿件反而成了配角。现行设计文档自己也规定「朱砂只用于唯一主 CTA」，但 rail 里它被用在了每一条用户消息上。
2. **卡片套卡片**。任务卡、已采用卡、候选稿卡都是白底圆角带边框卡片，叠在纸色 rail 上，层级靠阴影和边框硬切，显得「挤」而不是「密」。
3. **稿纸不像稿纸**。画布是一张带 `shadow-panel` 大阴影的浮空卡片；截图里空首段占位框（`从这里开始写…`）悬在正文上方成为视觉锚点；正文块里 `#第一章` 的 Markdown 标记被原文渲染。
4. **顶栏气质混杂**。毛笔字 logo、宋体书名、无衬线章节名、胶囊按钮四种字体/样式并排，没有统一的字阶纪律。
5. **密度与留白失衡**。rail 内部大片无信息空白与局部拥挤（chips 区）并存；composer 底部说明文字折行。

方案 C 的判断：**这些问题的根因是「用色彩做层级」，而顶级工具产品的答案是「用字阶、间距、hairline 做层级，色彩只留给状态与唯一行动」。**

---

## 2. 设计原则

1. **中性即层级**。黑/灰文字 + 字重 + 间距 + 1px hairline 承担全部信息层级；色彩只表达状态（成功/候选/错误）与唯一行动（accent）。
2. **hairline 取代阴影**。静态表面一律 1px 边框分隔，无投影；阴影只出现在浮层（选区工具条、popover、命令面板）。
3. **字阶收敛**。UI 文本只有 12 / 13 / 15 三级（+11px 仅限 kbd 与数字角标）；阅读面 14（候选稿）/ 17（稿件正文）/ 22（章节标题）。
4. **高密度但呼吸感强**。行高收紧（rail 行 32px）、间距成系统（4 的倍数）、表面之间留足负空间；密度来自「行」而不是来自「卡片」。
5. **键盘是First-class交互**。所有高频动作有快捷键，快捷键提示（kbd）直接印在 UI 上，命令面板是动作的总入口。
6. **诚实优先于装饰**。保存状态、agent 状态、候选/已采用状态全部以文字 + 中性图标表达，不依赖颜色单独表意（延续现行「honest save state」原则）。

---

## 3. Accent 论证：黛蓝 `#3a49be`

方案 C 只保留一个 accent。提议用 **黛蓝**（深靛青），不是现行朱砂，也不是纯黑。

### 为什么是黛蓝

1. **中文书写传统里唯一的冷色**。青黛是文人日常接触的深青颜料（画眉、靛染、青花），「青灯黄卷」「青出于蓝」——它在中国文化语境里天然属于书房，但比朱砂低调、唤醒度低。长篇写作是数小时的低唤醒劳动，accent 不该是庆典色。
2. **写作工具的全球共识色**。iA Writer 的蓝色光标、Word/Google Docs 的蓝色插入符与协作光标——在「文字处理」语境里，蓝色等于「可编辑、专注、进行中」。这是用户已习得的 affordance，零学习成本。
3. **与语义色彻底解耦**。现行系统里品牌朱砂 `#8f211b` 与 danger `#b8402f` 色相接近，「主操作」与「错误」存在误读风险（设计文档已专门规定 danger 要「更亮更冷」来避让）。黛蓝与危险红在色环上相距最远，主行动/错误/候选三色零歧义。
4. **冷暖对位**。中性灰阶保留一丝暖（`#f6f6f3`，纸的远亲），单一冷 accent 在暖灰底上形成精确的视觉锚点——这正是 Linear（暖灰 + 紫蓝）与 Attio（暖灰 + 冷蓝）的配方。

### 对比度验算（白底 / `#f6f6f3` 底）

| 用途 | 颜色 | vs `#ffffff` | vs `#f6f6f3` |
|---|---|---|---|
| accent 文本/图标/填充 `#3a49be` | | **7.3:1** | 6.8:1 |
| accent hover `#2d3899` | | 9.6:1 | 9.0:1 |
| 白字 on `#3a49be`（主按钮） | | **7.3:1** | — |

全部远超 4.5:1 底线。

### 否决的备选

- **玄黑（近黑 accent，Vercel 式）**：最纯粹的「墨」，但与正文墨色同族，选中态/链接与正文的区分度弱，状态语义会被迫再引一个彩色——等于没有解决问题。
- **保留朱砂**：与本方案对立，属方案 A/B 的领土；且朱砂的高唤醒与「工具退后」原则冲突。
- **竹绿/墨绿**：与 success 语义色冲突。

---

## 4. Token 草案

作用域策略见 §11（建议先以写作台作用域落地，不冲击全站 paper & vermilion）。以下为完整词表：

```css
@theme {
  /* ── 中性表面（暖灰，纸的远亲） ─────────────── */
  --color-surface: #ffffff;        /* 面板、稿纸、顶栏 */
  --color-surface-app: #f6f6f3;    /* app 底、画布底 */
  --color-surface-sunken: #efeeea; /* 下沉区：用户气泡、segmented 底 */
  --color-surface-hover: #f3f2ef;

  /* ── 墨色阶 ───────────────────────────────── */
  --color-ink: #1c1b18;            /* 正文/标题  16.9:1 on white */
  --color-ink-2: #57544d;          /* 次级文本   7.5:1 */
  --color-ink-3: #716d65;          /* 元信息     5.1:1 on white / 4.7:1 on app */
  /* ink-3 是底线：任何阅读性文本不得再浅。11px kbd 文本也用 ink-2。 */

  /* ── Hairline ─────────────────────────────── */
  --color-line: #e7e5e0;
  --color-line-strong: #d8d5cd;    /* 输入框、ghost 按钮边 */

  /* ── 唯一 accent：黛蓝 ─────────────────────── */
  --color-accent: #3a49be;
  --color-accent-strong: #2d3899;
  --color-accent-wash: rgba(58, 73, 190, 0.06);   /* 选区、选中段 */
  --color-accent-wash-2: rgba(58, 73, 190, 0.11); /* 选区描边、::selection */

  /* ── 语义色（只表状态，不表品牌） ───────────── */
  --color-success: #3a7d54;        /* 4.9:1 */
  --color-warning: #8a6116;        /* 5.5:1 候选/待审 */
  --color-danger: #be3b30;         /* 5.4:1 */

  /* ── 字阶：UI 4 级 + 阅读 3 级 ─────────────── */
  --text-micro: 11px;   --text-micro--line-height: 1.4;  /* 仅 kbd/数字角标 */
  --text-caption: 12px; --text-caption--line-height: 1.5;
  --text-base: 13px;    --text-base--line-height: 1.55;  /* UI 默认 */
  --text-title: 15px;   --text-title--line-height: 1.45; /* 面板标题/书名 */
  --text-draft: 14px;   --text-draft--line-height: 1.8;  /* 候选稿阅读 */
  --text-reading: 17px; --text-reading--line-height: 1.95;
  --text-chapter: 22px; --text-chapter--line-height: 1.35;

  /* ── 圆角 3 档 ────────────────────────────── */
  --radius-control: 4px;   /* kbd、chip、segmented 内格 */
  --radius-panel: 6px;     /* 按钮、输入框、稿纸、气泡 */
  --radius-modal: 8px;     /* 候选稿卡、popover、命令面板 */

  /* ── 阴影：只有浮层有 ──────────────────────── */
  --shadow-overlay: 0 4px 14px rgba(28, 27, 24, 0.18);            /* 选区工具条 */
  --shadow-menu: 0 16px 40px -16px rgba(28, 27, 24, 0.24);        /* 命令面板/下拉 */

  /* ── 动效 ─────────────────────────────────── */
  --duration-fast: 120ms;
  --duration-med: 180ms;
  --duration-slow: 240ms;
  /* 缓动沿用全站 cubic-bezier(0.22, 1, 0.36, 1)，不另立曲线 */

  /* ── 栏宽 ─────────────────────────────────── */
  --spacing-rail-nav: 52px;        /* 图标轨（现行 64 折叠态即此宽度） */
  --spacing-rail-inspector: 352px; /* agent dock，现行 360 → 352 */
}
```

与现行 token 的关系：字阶从 9 档收敛到 4 档（`text-sm`→`text-base`、`text-md`/`text-lg`→`text-title`、`text-xl`/`text-display` 写作台不再使用）；阴影从 5 档收敛到 2 档；`--color-gold`/`--color-candidate` 族退出写作台（候选状态由 `warning` 文本承担）；`accent` 语义从朱砂换成黛蓝。

---

## 5. 整屏布局规格

```
┌──────────────────────────────────────────────────────────────┐
│ nav 52 │ 顶栏 48px：书架/书/第1章▾ │[稿件|章节|审校|工具]│     │
│        │                                    5,556字·已保存·⌘K·[+新章节] │
├────────┼───────────────┬──────────────────────────────────────┤
│ 图标轨  │ Agent dock    │  画布（surface-app 底）               │
│        │ 352px 白底     │  ┌─ 稿纸 max-w 792, 白底, hairline ─┐ │
│        │ head 45px tabs │  │  章节题 22 + meta 12             │ │
│        │ 对话|待审资产 2 │  │  正文 17/1.95 Songti             │ │
│        │ thread（行式）  │  │  段间距 1.05em，无分隔线          │ │
│        │ composer 常驻  │  │  选中段 accent-wash + 浮动工具条   │ │
│        │               │  └──────────────────────────────────┘ │
└────────┴───────────────┴──────────────────────────────────────┘
```

- **视图切换**（稿件/章节/审校/工具）以 segmented control 落在画布头（portal 进共享顶栏，与现行 `WriterCanvasTop` 同一挂载点），互斥 tabs，满足 conversation-first IA 的画布头切换要求。非稿件视图本期只做壳与空态，内容按既有波次规划填充。
- **稿纸**：白底 + 1px hairline + radius 6，无阴影；`max-width: 792px`，padding 60/72；段与段之间只有空白，没有 `border-t`。
- **dock**：352px 白底，与稿纸之间只有 1px hairline；不再使用 `bg-paper/40` 半透明叠色。

---

## 6. 组件级改动清单

按现行文件逐一列出（行号以当前 worktree 为准）：

### 6.1 `globals.css`（token 层）

- 新增 §4 的 studio token 组；写作台作用域挂载（见 §11）。
- `::selection` 在作用域内改为 `accent-wash-2`（选中文本用淡黛蓝底，不再是朱砂底白字）。
- focus ring 改为 `accent` 55%（形制不变，色换）。

### 6.2 `writer-canvas-top.tsx`（画布头）

- 新增 **ViewTabs** segmented control（稿件/章节/审校/工具），挂在 chapter switcher 之后；h=28px，active 格白底 + hairline。
- 书名/章节改为面包屑：「书架 / 书名（serif 15 600）/ 第1章 ▾」，折叠菜单样式不变（白卡 + hairline，去 `shadow-lift` 改 `shadow-menu`）。
- 字数改 mono tabular 12px ink-3（`5,556 字`，千分位）。
- SaveIndicator：图标+文字 → **状态点+文字**（dirty=warning 点「未保存」、saving=旋转点「保存中」、saved=success 点「已保存」、conflict/error=danger 点+全文），杜绝红字长句占顶栏。
- 「新章节」从描边胶囊改为 **ghost 按钮**（hairline 边、无填充、hover 下沉灰）——本屏唯一实心 accent 留给候选稿「采用」与 composer「发送」。
- 右侧新增 ⌘K 命令入口 chip。

### 6.3 `writer-rail.tsx`（Agent thread —— 改动最大）

- **UserBubble**：`bg-accent` 红气泡 + 朱砂阴影 → `bg-surface-sunken` + 1px hairline 中性气泡，ink 正文色。用户的话是「记录」，不是「警报」。
- **TaskCard** → **activity row**（Linear 式）：单行 32px，状态图标（14px：进行中 spinner-accent / 完成 check-circle-success / 失败 x-danger）+ 单行摘要（`已完成 · 候选稿 2,046 字`，数字 mono）+ 尾部 chevron；点击行内展开 steps（12px、check 图标、右侧 mono 耗时），展开动画 180ms height。卡片边框与 `rounded-modal` 移除。
- **CitationsRow**：金色/白色 chips 阵列 → 单行召回文本：`参考了 常驻·李典史 · 炼精境 · 假银 · 税银案 +7`，12px ink-3，中点分隔，超 5 项折叠为 +N（hover title 保留完整名单与召回渠道说明）。chips 的标题/title 信息全部保留，只是不再渲染为 pill。
- **CandidateCard**：金色虚线框 + 胶囊角标 → hairline 白卡（radius 8，无阴影）；头部 `候选稿`（11px 600 letterspacing accent）+ 字数 mono；正文 serif 14/1.8；底部 hairline 上：左「采用后进入手稿末尾」hint，右 **accent 实心按钮「采用进手稿 ⌘⏎」**（本 dock 唯一实心色块）。起草中流式光标保留（accent 2px 竖条）。
- **SettledCard** → **settled row**：单行 `已采用 · 进手稿`（ink-3 文档勾选图标）+ 尾部 quiet link「查看正文」（ink-3 → hover accent，带定位图标）。不再默认渲染卡片正文；展开态沿用现有折叠逻辑，样式随行化。
- **RailGreeting**：accent 圆形大图标 → 去掉图标，两行文字（15px 标题 + 12px 说明），居左对齐 thread。
- 新增 **时间分隔线**（昨天/今天）：hairline + 11px ink-3，为持久化 thread 提供时间锚。
- ConsistencyNotice（一致性提醒）：金底卡片 → 左边框 2px warning + 白底，文字结构不变。

### 6.4 `writer-composer.tsx`（常驻 composer）

- 输入框：hairline-strong 边、radius 6，`focus-within` 边色 → accent（不用阴影）。
- 内置 kbd 提示行：`⏎ 发送` `⇧⏎ 换行`（kbd 组件：11px mono、hairline、radius 4、下边 1.5px——这是 kbd 文化的视觉锚）。
- 发送按钮：accent 实心方钮（26px、radius 6、ArrowUp），disabled 时 `surface-sunken` 底 + ink-3 图标（不靠透明度装死）。
- 底部说明压缩为单行 11px：`起草内容先作候选稿，经你采用才进手稿。`（解决截图中折行问题）。

### 6.5 `manuscript-paper.tsx`（稿纸 —— manuscript-primary 核心）

- 去 `shadow-panel`，hairline + radius 6；padding 60/72。
- **修复「#第一章」**：block 文本若以 ATX 标题开头，渲染为章节标题样式（或写回时剥离标记）；章节头新增：serif 22 600 章题 + meta 行（字数 mono · 段数 · 最近保存时间）。
- **修复空首段占位框**：占位提示只在「整章为空」时出现；章节已有内容时，不再在顶部渲染悬空空段（截图红框问题）。新增段落入口为文末的安静占位行「接着写…」。
- 段间 `border-t` 移除，纯 1.05em 段距；正文 17/1.95 Songti 不变。
- reveal flash（查看正文定位）：朱砂 rgba(143,33,27) → `accent-wash` + 1px `accent-wash-2` 描边脉冲。
- **选区驱动调用**（新组件 SelectionToolbar）：textarea selection 非空时，在选区上方浮出深色（ink 底白字）胶囊工具条：「✎ 改写选区 ⌘I / 续写此段 / 引用到对话」，带下指 caret，`shadow-overlay`。三项动作都路由到现有 composer/run 流程（改写与引用 = 预填 composer 并携带选区上下文；续写 = continue mode），不新增后端能力。
- **来源段注**：被采用块尾部渲染 11px 注记（accent 短横 +「此段由合著者起草 · 你已采用 · 查看记录」），数据来自现有 `source_writer_run_id`，与 settled row 的「查看正文」互链。
- 删除画布底部免责声明段（信息已在 composer note，且每屏只说一遍）。

### 6.6 `composer-review-flip.tsx`（dock 双面）

- **3D 翻转 → dock-head 内 tabs 切换**：dock 头部改为「对话 | 待审资产 2」两个 text tab（active：ink 600 + 2px ink 下划线；count badge 为 sunken 底 mono）。两面内容、计数同步、hasNew 标记全部保留；切换动效 160ms crossfade。理由：rotateY 翻牌是「新奇感」动效，与工具文化的「瞬时、可预期」相悖；tab 是作者已熟知的心智（Notion/Linear 的侧栏 tab）。**信息架构不变**，仍是一个常驻 dock 的两面。
- 待审计数徽标从金色胶囊改为中性 sunken 底；hasNew 红点保留（那是真正的新到达信号，语义色管状态）。

### 6.7 `proposal-rail.tsx`（待审资产面）

- 金色族（`gold`/`candidate` wash）退出：候选项状态用文字（`新增/更新/冲突` + warning 色仅用于「冲突」词）+ hairline 卡片承担。
- 「全部通过」从实心降级 ghost；单卡「接受」为主按钮（accent 描边或实心，每卡一个）；批量进度沿用现有，不改动逻辑。

### 6.8 `writer-empty.tsx`（零起点）

- 圆形 accent 图标 → 去除；标题 serif 22；说明 13px；主按钮保留实心 accent（空态唯一 CTA，合理），尺寸收至 h=36。

### 6.9 `workbench-masthead.tsx`

- 写作台作用域内无需改动；若未来全站推广 studio 体系，eyebrow 已是中性，仅需换 accent/focus 色。

---

## 7. 键盘文化与命令面板

### 快捷键表（全部印在 UI 上）

| 键 | 作用 | 提示出现位置 |
|---|---|---|
| `⌘K` | 命令面板 | 顶栏 chip |
| `⌘J` | 收起/展开合著者 dock | dock 头 |
| `⌘1–4` | 切 稿件/章节/审校/工具 | ViewTabs hover title |
| `⌘I` | 改写选区（有选区时） | 选区工具条 |
| `⌘⏎` | 采用候选稿（焦点在卡上）/ 发送 composer | 候选稿按钮 / composer |
| `⏎` / `⇧⏎` | 发送 / 换行 | composer 内 |
| `Esc` | 关浮层、取消选区、停笔 | 各浮层 |

### 命令面板（P2）

居中浮层（max-w 560、radius 8、`shadow-menu`、遮罩 20% ink）：跳章节、新章节、切视图、发起起草（草稿/续写/审校模式）、搜资产并引用到对话、收起 dock。输入框 15px，结果行 32px，右列 kbd。复用设计文档 §Command Palette 的全局命令系统规划，本方案只是把它在写作台设为默认入口。

---

## 8. 动效规格

**总纲**：工具感动效的三条纪律——快（120–240ms，比现行 160–280 整体快一档）、只做 transform/opacity/color、每一个动效回答一个状态问题。缓动沿用全站 `cubic-bezier(0.22, 1, 0.36, 1)`，不另立曲线。

| 场景 | 参数 |
|---|---|
| hover（背景/边框/文字色） | 120ms，仅 color |
| ViewTabs / dock tab 切换 | 指示位 180ms transform；内容 crossfade 160ms opacity |
| activity row 展开 steps | height 0→auto 180ms + opacity |
| 候选稿卡出现 | opacity 0→1 + translateY 4px→0，180ms |
| 候选稿流式光标 | 1s opacity 脉冲（现状保留，色换 accent） |
| 选区工具条出现 | opacity + translateY −2px，120ms；不出现布局位移 |
| reveal 定位脉冲 | 背景 transparent→accent-wash→transparent，480ms × 1 次（沿用现节奏，换色） |
| 命令面板 | 面板 opacity + scale 0.98→1 160ms；遮罩 120ms |
| 保存状态切换 | 文本 crossfade 120ms；saving 点 800ms linear 旋转 |
| 计数徽标变化 | 沿用 `count-up`（opacity+scale），时长降至 240ms |
| 翻牌（移除项） | rotateY 3D flip 退役，由 160ms crossfade 替代 |

`prefers-reduced-motion: reduce`：以上除「保存状态切换」外全部关闭（状态文本本身必须保留，不靠动画表意）。不新增任何无限循环装饰动画。

---

## 9. 去性格化之辩：稿纸感 vs 工具感

这是本方案最大的取舍，必须正面论证。

### 利

1. **注意力归还给文字**。中性界面让 17px 宋体正文成为全场唯一的「质地」，稿纸感不再依赖米色和印章——**稿件本身就是稿纸**。这对每天写作数小时的用户是真实的人体工学收益（低唤醒、低疲劳）。
2. **层级系统可维护**。现行 24 字号/15 圆角/18 阴影的教训（设计文档 §实现口径）正是「情绪化局部决策」累积的结果；4 级字阶 + hairline 的纪律让后续每个新组件都有唯一正确画法。
3. **跨工作台一致性成本最低**。极简 token 是全站统一的最短路径；paper & vermilion 那套依赖文化氛围的体系，在图谱、资产库等数据密集界面其实一直在打折。
4. **Agent 状态语义更可信**。accent 只承担「行动」，语义色只承担「状态」，朱砂/金色混用的误读风险归零——对一个「候选稿必须先采用」的诚实系统，这是功能性收益不只是美学。
5. **键盘文化契合写作的高频操作本质**。作者的手不离开键盘，⌘I/⌘⏎/⌘K 的效率收益是实打实的。

### 弊

1. **文学辨识度下降**。「墨鱼小说」的品类情绪（深夜书房、稿纸、印章红）是留存钩子之一；过度工具化会让产品看起来像 Notion/Linear 套壳，用户记不住「这是写小说的」。
2. **与产品其他页面气质断层**。若只有写作台换 studio 体系，总览的叙事画面、图谱的纸墨星座、品牌毛笔字会与写作台像两款软件；全站切换则是另一个量级的工程与决策。
3. **冷暖平衡做不好会显「脏」**。暖灰底 + 冷蓝 accent 的容错率低，灰阶偏黄或偏蓝都会破坏质感（本草案的灰阶已向暖微调并截图验证）。
4. **中文竖排/首行缩进等排版传统不在场**。极简工具范式来自英文编辑器，中文小说的排印习惯（2em 首行缩进、章节居中题）需要另行决策——本方案正文暂保持无缩进 + 大段距（网文习惯），排印主题化留作后续配置项。

### 缓解：骨是工具，皮有一线纸性

- **字体层保留文学性**：书名、章节题、稿件正文、候选稿一律宋体系；UI 壳才用无衬线。骨架是 Linear，皮肤仍认得出是中文写作产品。
- **灰阶取暖不取冷**：`#f6f6f3` 而非冷灰，是纸的远亲，不是 IDE 的灰。
- **品牌位不动**：nav 轨「墨」字方块、顶栏 serif 书名仍在；只是从「每屏一个印章」退为「一个字墨点」。
- ** accent 的文化论证**：黛蓝出自青黛/靛青，本就是书房色——它不是对稿纸感的背叛，是把「印章红」换成「青灯」。

---

## 10. 对比度验算表（正文级 ≥4.5:1）

| 组合 | 比值 | 用途 |
|---|---|---|
| ink `#1c1b18` on surface `#ffffff` | 16.9:1 | 正文、标题 |
| ink-2 `#57544d` on `#ffffff` | 7.5:1 | 次级文本、按钮 |
| ink-3 `#716d65` on `#ffffff` | 5.1:1 | 元信息（12px 下限） |
| ink-3 `#716d65` on surface-app `#f6f6f3` | 4.7:1 | 画布底上的元信息 |
| accent `#3a49be` on `#ffffff` | 7.3:1 | accent 文本/图标 |
| `#ffffff` on accent `#3a49be` | 7.3:1 | 实心按钮 |
| success `#3a7d54` on `#ffffff` | 4.9:1 | 已保存/已完成 |
| warning `#8a6116` on `#ffffff` | 5.5:1 | 未保存/冲突状态 |
| danger `#be3b30` on `#ffffff` | 5.4:1 | 错误 |
| ink-3 图标 on surface-app（非文本） | 4.7:1 | nav 图标（要求 3:1） |

注：ink-3 不允许再兑水（现行 `text-muted/50` 类用法在本体系物理上不存在——词表外没有更浅的灰）；accent-wash 只作背景不作文本。

---

## 11. 落地范围与分期

### 作用域策略（关键决策）

两条路径：

- **A. 全站切换**：替换 `@theme` 全局 token。收益是一致性一步到位；代价是所有工作台回归测试 + 与方案 A/B 的全局决策绑定。
- **B. 写作台试点（推荐）**：token 组挂在写作台路由的作用域类（如 `.studio-scope`）下，其余工作台保持 paper & vermilion。风险小、可 A/B 对照、用户拍板后再推广。代价是产品内短期存在两套体系（§9 已诚实讨论）。

本方案按 B 出稿；若用户最终选 C 作为全局方向，再执行 A 的 token 合并（设计文档与 `design-tokens.test.mjs` 需同步更新）。

### 分期

- **P0（纯视觉重排，不动数据流）**：token 作用域；rail 行化（UserBubble/TaskCard→activity row/CitationsRow/SettledCard）；CandidateCard 重画；composer（kbd 行）；稿纸（去阴影、段距、章节头、「#第一章」与空段占位两个 bug 修复）；顶栏（面包屑、状态点、ghost 新章节）；flip→tabs crossfade。验收：截图基线替换 + 真实栈走通 起草→采用→查看正文 全链路。
- **P1（小功能增量）**：SelectionToolbar（textarea `selectionStart/End` 可得，三项动作路由到现有 run/composer）；ViewTabs 壳（章节/审校/工具空态）；时间分隔线；来源段注与「查看正文」互链。
- **P2（命令文化）**：⌘K 命令面板、⌘J dock 折叠、⌘1–4 视图切换、快捷键总表；并入全局命令系统规划。

### 明确不做

- 不改任何 API / 数据契约 / run 事件流（`source_writer_run_id`、thread 持久化、adoption 语义原样复用）。
- 不动 IA：manuscript-primary、conversation-first、常驻 dock、候选稿必须先采用——全部保留。
- 不恢复任何已退役元素（`writer-studio-grid`、折叠 composer、深色 rail、旧蓝色 UI）；不引入暗色 rail；不恢复金色 chips 阵列。

---

## 12. 原型与迭代记录

原型 `prototype-c.html`（自包含、系统字体、内联 SVG 图标，1600×1000）整屏复刻：图标轨 / 顶栏（面包屑 + ViewTabs + 字数 + 已保存 + ⌘K + 新章节）/ dock（tabs + 昨天/今天三轮对话 + 展开 steps + 召回行 + 候选稿卡 + composer）/ 稿纸（章节头 + 10 段正文 + 选中段浮动工具条 + 来源段注）。内容沿用用户截图的同一本书、同一段正文、同一组对话，便于直接对比。

迭代过程（`node tools/ui-preview/screenshot.mjs` 逐轮截图自检）：

1. **v1**（`iteration-v1.png`）→ 挑毛病：turn 内间距与 turn 间距不分、已采用图标语义含混、稿纸 radius 8 偏「卡片」、accent 偏皇家蓝不够「黛」、ink-3 在 app 底上 4.37:1 不达标。
2. **v2** → turn 分组（内 10px / 间 22px）、accent 加深为 `#3a49be`（7.3:1）、稿纸 radius 6、选区工具条加 caret。
3. **v3** → 补「昨天」历史轮 + 时间分隔线，解决 rail 下半屏空白（用户截图同款问题），同时演示持久化 thread 的时间锚。
4. **v4/v5**（`iteration-v5.png`）→ 压缩召回行与候选稿摘录，保证「采用进手稿 ⌘⏎」这个全屏唯一主 CTA 完整落在首屏。
5. **终版**（`prototype-c.png`）→ ink-3 加深至 `#716d65`（app 底 4.7:1 达标），全文 tokens 与验算表同步。
