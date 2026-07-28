# 写作台重设计 · 方案 A：纸墨精进化

日期：2026-07-27
范围：`apps/web` 写作台（Writer 工作台）整屏视觉重做，不换品牌、不换 IA。
原型：`prototype-a.html`（自包含静态单文件，1600×1000）
最终截图：`prototype-a.png`（相对仓库根：`docs/plans/writer-ui-redesign-2026-07/prototype-a.png`）

---

## 0. 一句话主张

不逃离「暖纸 + 朱红印章」，而是把它做到 Linear 级别的工艺精度：暖色系缺的不是色相，是**纪律**——朱砂的稀缺纪律、发丝线的分隔纪律、纸张物理隐喻的一致纪律。

## 1. 现状诊断（为什么现在不像大厂）

对照现行代码与截图，问题不是「暖色土」，而是四条纪律全部失守：

1. **朱砂泛滥**。用户每条发言都是一整块实心 `#8f211b` 气泡（`writer-rail.tsx:187` `bg-accent ... text-panel shadow-accent`），一屏出现 3 块大红，与发送键、品牌印争抢唯一的强调色。设计规范自己写着「红色不作为普通按钮的默认填充色泛滥使用」，气泡恰恰在泛滥。
2. **卡片堆砌代替信息流**。状态卡（已完成/已采用）是带大圆角大投影的白卡，一张一张浮在纸栏上（`rounded-modal border bg-panel` + `shadow-panel`），密度低、层叠感强，像 marketing 卡片墙，不像 Linear/Attio 的 activity feed。
3. **纸张隐喻半途而废**。稿纸用 `rounded-control` + `shadow-panel`（`manuscript-paper.tsx:38`）——圆角和浮起投影是「卡片」的语言，不是「纸」的语言；正文里直接渲染出原始 Markdown `# 第一章`；空段落是一个带边框的输入框贴在纸面上。Notion 的纸感来自排版（字距、缩进、天头地脚），不来自一个框。
4. **层级靠投影不靠明度**。栏与画布同为纸色，靠 border 和阴影区分；画布头没有视图切换（规范要求的 稿件/章节/审校/工具 互斥标签缺位），信息层级全靠元素自己喊。

参考系的真正可移植点：Notion = 排印的克制（字阶少、hairline、内容即装饰）；Linear = 工艺（1px 分隔、活动流、tabular-nums、微交互时长统一）；Attio = 属性 chip 的低饱和语义色。三者都不是配色方案，方案 A 移植的是这三件事。

## 2. 设计哲学：三条纪律

### 2.1 朱砂的稀缺纪律

全屏实心朱砂只剩两处：composer 发送键、品牌印。用户气泡从「红底白字」改为「纸面 + 朱砂发丝描边 + 4.5% 洗色底」——仍然是品牌色，但退到描边和 wash 层级。选中态、focus ring、`查看正文` 链接维持 accent 文字级使用。结果：红色重新变得有信号价值，发送键第一次成为全屏视觉重心——这正是规范想要的「每页只突出一个主对象和一个主要动作」。

### 2.2 发丝线的分隔纪律

新增 `hairline`（14% 暖墨）一档，卡片、稿纸、dock 边界一律 hairline；`line`（20%）只给需要更强存在的控件边框（composer、按钮）。投影收敛：稿纸和卡片不再用 `shadow-panel` 大模糊，改用「发丝线 + 极轻托影」的新 `shadow-sheet`。大投影只保留给浮层（popover/modal）。层级的第一手段改为明度：桌案（paper-deep）< 栏（paper）< 稿纸/卡片（panel），三层纸各差半阶，不需要阴影喊话。

### 2.3 纸张的物理纪律

纸不是卡片：稿纸圆角从 6–10px 收到 3px（`radius-sheet`），像一叠纸里的一张；中文书版工艺进场——章题居中、字距 .42em、旧金菱花界行，正文首行缩进 2em、1.9 倍行高、两端对齐；空段落不再是边框盒子，而是一行带朱砂光标的编辑位提示。大面积平光处加 1.6% 的纸纤维颗粒（静态、不承载信息、不经过文字对比度计算之外的区域——见 §7）。这些是让「纸」可信的细节，也是暖色系对抗冷灰大厂的差异化资产。

## 3. Token 级改动草案（`apps/web/app/globals.css` `@theme`）

新增三档、微调三档、废止一种用法。全部遵守现有词表纪律（`--text-*`/`--radius-*`/`--shadow-*` 仍为封闭 scale），同步更新 `apps/web/tests/design-tokens.test.mjs` 与 `apps/web/eslint.config.mjs`。

```css
@theme {
  /* ── 墨与纸：同光源微调，纸分三层 ───────────────────── */
  --color-ink: #1b1813;            /* was #171a1b：墨再暖半度，与纸同光源 */
  --color-ink-soft: #443f37;       /* was #3c3a36 */
  --color-paper: #f6f1e7;          /* was #f7f2e9：栏面，微调 */
  --color-paper-deep: #eee7d6;     /* was #efe7d8：画布「桌案」再深半阶，托出稿纸 */
  /* --color-panel 不变：#fffdf8，只给稿纸与卡片 */

  /* ── 发丝线（新增档）─────────────────────────────────
   * 卡片、稿纸、dock 边界的默认分隔；--color-line 仅保留给控件边框 */
  --color-hairline: rgba(86, 69, 45, 0.14);

  /* ── 朱砂 veil（新增档）───────────────────────────────
   * 用户气泡底、选中洗的 4.5% 档；比 wash(7%) 更退后 */
  --color-accent-veil: rgba(143, 33, 27, 0.045);

  /* ── 稿纸托影（新增档）────────────────────────────────
   * 发丝 + 极轻提起；稿纸/卡片不再使用 shadow-panel */
  --shadow-sheet: 0 1px 2px rgba(27, 24, 19, 0.04),
                  0 24px 48px -32px rgba(27, 24, 19, 0.22);

  /* ── 纸张圆角（新增档）────────────────────────────────
   * 纸不是卡片：稿纸专用近直角 */
  --radius-sheet: 3px;

  /* ── 阅读行高微调 ─────────────────────────────────────
   * CJK 书版在 17px 下 1.85 略闷，1.9 更接近铅字灰度 */
  --text-reading--line-height: 1.9;   /* was 1.85 */
}
```

附带的组件层 CSS（不进 @theme）：`.paper-grain` 工具类——`feTurbulence` data-URI 颗粒，opacity 0.016，仅铺在画布桌案与 dock 大平面，`pointer-events: none`，`prefers-reduced-motion` 下无动画（本身静态）。

## 4. 组件清单级改动（哪个文件改什么）

### `apps/web/app/globals.css`
上节全部 token；新增 `.paper-grain`。同步 `apps/web/tests/design-tokens.test.mjs` 与 eslint 配置。

### `apps/web/app/projects/[projectId]/writer/writer-workspace.tsx`
- dock `<aside>`：`bg-paper/40` → `bg-paper`，`border-r border-line` → `border-r border-hairline`；顶部 120px 内叠一层 `panel→transparent` 的 35% 渐隐（栏顶微光，原型的 dock 渐变）。
- 画布容器：加 `bg-paper-deep` + 顶部径向微光（`radial-gradient(120% 80% at 50% 0%, panel 55%透明)`），形成「桌案托纸」的明度差。

### `apps/web/app/projects/[projectId]/writer/writer-canvas-top.tsx`
- 面包屑重排：`墨鱼小说(brand, 600) / 书架 / 测试6(500) › 第1章▾`，章节切换器与作品名分级；`border-l` 发丝 + 字数 `tabular-nums`。
- 保存态文案：`已保存` → `已保存 · 刚刚`（muted 文字 + success 对勾；错误/冲突路径不变）。
- `新章节`：`border-line` → `border-hairline` + `shadow-hairline`，hover 逻辑不变。

### 新增 `apps/web/app/projects/[projectId]/writer/writer-view-switch.tsx`
- 画布头 46px 行：左侧 segmented control「稿件 / 章节 / 审校 / 工具」（互斥，`role="tablist"`，容器 7% 暖墨底 + 2px padding，选中项 panel 底 + hairline 投影），右侧一句灰字「选中字句，可让合著者就地改写」。
- 落地方式见 §8：先只接通「稿件」，其余三项不渲染假内容——以 `aria-disabled` + 诚实空态占位，接通一个亮一个。**这条是 IA 硬约束的补齐，不是新增范围**（`docs/refactor-saas/11-writer-workbench.md:66` 早已规定互斥标签）。

### `apps/web/app/projects/[projectId]/writer/manuscript-paper.tsx`
- 稿纸：`max-w-[760px]` → `max-w-[720px]`；`rounded-control border-line-soft shadow-panel` → `rounded-sheet border-hairline shadow-sheet`；padding `52px 76px 64px`。
- 章题排版块（新增）：章节标题不再以正文块形式露出 `#`；渲染为居中 `text-xl` serif（23px/600/字距 .42em），下接旧金菱花界行（两条 56px 渐变发丝 + 5px 菱形 gold 点）。
- 正文段落：段落级 class 加 `text-indent: 2em`、`text-align: justify`、`letter-spacing: .015em`；段间 `border-t` 分隔线废除，改用纯行距（0.55em 段距）。
- 空段提示：从「带框提示」改为行内编辑位——14px muted-soft serif + 2px 朱砂光标（opacity .6），语义不变。
- reveal flash（查看正文脉冲）逻辑不动，仅颜色改 `--color-accent-wash`。

### `apps/web/app/projects/[projectId]/writer/writer-rail.tsx`（改动最大）
- **UserBubble**：删除 `bg-accent text-panel shadow-accent`；改为 `bg-accent-veil` + `border rgba(143,33,27,.15)` + `shadow-hairline`，圆角 `12px 12px 4px 12px`，右对齐不变；连续两条气泡间距 14→6px（`.bubble-row + .bubble-row`）。
- **thread 改活动流**：状态事件统一为「22px 节点 + 内容列」双栏 grid；节点为 panel 底圆点（完成=success-wash + 对勾，候选=candidate-wash + 卷轴）；节点上方 23px 发丝接头串起相邻事件；thread 顶部加「今天」日期分隔（11px/tracking .10em + 两侧发丝）。
- **TaskCard**：去 `rounded-modal` 大圆角与浮起感，`rounded-panel` + `border-hairline` + `shadow-hairline`，状态行 13px（`text-sm`），chevron 保留；展开 steps 行为不变。
- **SettledCard**：`.card.calm`——`panel 55%` 底、无投影、hairline；脚部分隔线 + `查看正文` accent 链接维持。
- **CandidateCard**：金色 dashed 框 → hairline + `border-l-2` 旧金书脊 + 「候选稿」eyebrow chip（candidate 语义色）；采用按钮仍是全 thread 唯一朱砂实心。
- **CitationsRow**：chip 统一 23px 高 pill、`border-hairline`、12px；`always_on` 用 gold 发丝 + candidate-wash + `常驻 · ` 前缀；`+12`、`·关键词召回` 降级为无边框灰字。

### `apps/web/app/projects/[projectId]/writer/writer-composer.tsx`
- 容器「墨砚」：`rounded-modal` → `rounded-panel`，`border-line` 保留（控件级），`shadow-panel` → `shadow-sheet`；`focus-within` 加 `border-accent/30` + 外圈 `0 0 0 3px var(--color-accent-wash)`。
- 发送键：圆角方块 → 30px 正圆，朱砂 + `shadow-accent`（全屏仅两处实心朱砂之一）。
- 提示行固定两行排布：「起草的内容先作候选稿，经你采用才进手稿。/ Shift+Enter 换行。」避免尴尬的半词折行。

### `apps/web/app/projects/[projectId]/writer/composer-review-flip.tsx`
- 翻转机制保留；两面背景统一 `bg-paper`（原 `bg-paper/40`），back 头 `border-line-soft` → `border-hairline`。
- 「待审资产」触发器对齐 chip 词表：gold 发丝边框 + candidate-wash 底 + 12px/500，count 徽标逻辑不变。

### `apps/web/app/projects/[projectId]/writer/proposal-rail.tsx`
- ProposalCard：`border-line` → `border-hairline`，去掉 hover 投影换 `border-gold/40`；类型 chip 与合并建议 chip 对齐 §4 rail 的 chip 词表（23px pill）。队列骨架、空态不动。

### 不动的文件
`workbench-masthead.tsx`、`writer-empty.tsx`、`use-writer-run.ts`、所有 API 客户端与类型、全部交互逻辑（autosave、翻转、采用、reveal）。本方案零行为变更。

## 5. 布局栅格（1600×1000 基准）

```
┌──────────────────────────────────────────────────────────┐
│ topbar 52px：印30 / 面包屑 / 字数 / 保存态 / 新章节        │
├────┬───────────────┬─────────────────────────────────────┤
│ 64 │ dock 360      │ canvas flex（≥1112 @1600）           │
│ 图 │ head 48       │  canvas-head 46：视图切换 + 侧注      │
│ 标 │ thread flex   │  sheet max-w 720，margin-top 4，      │
│ 轨 │ composer ~108 │  padding 52/76/64，radius 3           │
└────┴───────────────┴─────────────────────────────────────┘
```

- 三栏断点沿用 token：`wide ≥1200` 三栏全开；`861–1199` dock 折叠为覆盖式抽屉（沿用规范 §布局带）；`≤860` 单栏稿件优先。
- 网格基数 4px；dock 内容 padding 16/14，事件间距 14，卡片内 padding 12，chip 高 23，节点 22。
- 稿纸宽 720 是阅读宽（约 40 个全角字/行 @17px），不因视口变宽而加宽；更宽视口只加桌案。

## 6. 字层级表（写作台实际用到）

| 用途 | token | px / lh | 字重 / 附加 |
|---|---|---|---|
| 正文（稿纸） | `text-reading` serif | 17 / 1.9 | 常规；缩进 2em；justify |
| 章题 | `text-xl` serif | 23 / 1.35 | 600；tracking .42em |
| 工作台标题（合著者） | `text-sm` | 13 / 1.55 | 600；tracking .01em |
| 面包屑作品/章节 | `text-sm` | 13 / 1.55 | 500–600 |
| 状态行 / 卡片主行 | `text-sm` | 13 / 1.55 | 500 lead + muted tail（tabular-nums） |
| 气泡 | `text-sm` | 13 / 1.55 | 常规 ink |
| chip / 徽标 / 保存态 | `text-caption` | 12 / 1.5 | 500（chip）；tabular-nums（计数） |
| 日期分隔 / 侧注 | `text-caption`→`micro` 仅图形外特例：11 / 1.4 | tracking .10em，muted-soft |
| composer 提示 | `text-caption` | 12 / 1.5 | muted-soft |

词表零新增字号；11px 仅用于「今天」分隔这类非阅读装饰标签（规范允许 micro 于图形内标签，此处同属装饰性标签，如需严格可升 12px 不损效果）。

## 7. 动效规格

全部沿用现有 `ease-paper`（cubic-bezier(.22,1,.36,1)）与 160/220/280 三档，不加新曲线：

| 场景 | 时长 | 规格 |
|---|---|---|
| 气泡发出 | 220ms | fade-up（opacity + translateY 8→0） |
| 候选稿到达 | 220ms | fade-up + layout；完成后「候选稿」chip 160ms count-up |
| 采用 → settled | 280ms | 卡片高度/透明度 collapse 为 calm 卡，节点对勾 160ms scale pop |
| 查看正文 reveal | 480ms | accent-wash 底色 + 6px 外扩洗色，一次性脉冲（现行逻辑保留） |
| 视图切换 | 220ms | 选中 pill 平移（layoutId），内容区 crossfade 120ms 内完成 |
| dock 翻转（待审资产） | 500ms | 现行 rotateY 保留，`prefers-reduced-motion` 降级为 instant |
| hover | 160ms | 仅 hairline 色与 4% 底色变化，不位移、不放大 |

颗粒纹理为静态背景，无动画；`prefers-reduced-motion: reduce` 时全部入场/脉冲/翻转动效移除（沿用现有降级路径）。

## 8. 可达性说明

- 对比度（正文级全部 ≥ 4.5:1，实算）：
  - ink `#1b1813` on panel `#fffdf8` ≈ 13.7:1；on paper `#f6f1e7` ≈ 13.1:1。
  - 正文 `#262119` on panel ≈ 14:1。
  - muted `#57503f` on panel ≈ 7.2:1；muted-soft `#6f6559` on paper ≈ 5.1:1（占位提示在 panel 上 ≈ 5.6:1）。
  - candidate `#856530` on paper ≈ 4.7:1（chip 文字）；success/accent 文字用法沿用已验算 token。
- 颗粒纹理 opacity 0.016 叠加在面板/纸面上，对文字亮度扰动 <1%，不构成对比度依赖；任何正文不放在纹理-only 的底色上。
- 气泡从「红底白字」（accent on accent 白字 4.9:1）改为 ink on veil，对比度升至 ≈13:1，同时解决品牌色滥用。
- focus-visible 沿用全局 vermilion ring（55% accent，2px offset）；composer 增加 3px wash 外圈，不取代 ring。
- 触控目标：发送键 30px、章节切换 30px、视图切换项 ≥28px 高；节点圆点 22px 为纯展示不交互。
- 视图切换用 `role="tablist/tab"` + `aria-selected`；日期分隔 `aria-hidden`；活动流节点图标 `aria-hidden`，状态文字自足。
- 12px 阅读文字地板不破；11px 仅限「今天」装饰分隔（可升 12px 的退路已注明）。

## 9. 落地范围与工作量分级

| 级 | 内容 | 文件 | 估时 |
|---|---|---|---|
| **S**（约半天） | token 三档新增与微调；气泡去实心朱砂；composer 墨砚化；卡片/chip hairline 化；dock/canvas 明度分层 | globals.css、writer-rail（局部）、writer-composer、proposal-rail、composer-review-flip、writer-workspace（2 个 class） | 0.5d，纯样式，零行为变更 |
| **M**（1–2 天） | 稿纸书版工艺（章题块、缩进、界行、空段提示）；thread 活动流重构（节点列、接头、日期分隔）；视图切换 UI 与「稿件」接通 | manuscript-paper、writer-rail（结构）、writer-view-switch（新）、writer-canvas-top | 1.5–2d，含视觉走查与对比度复验 |
| **L**（2–4 天） | 章节/审校/工具三个视图接通真实功能（各视图各自的数据与空态，不做假路径）；选区驱动就地改写入口；纸纹与动效打磨、跨断点回归 | writer-view-switch、writer-workspace、新视图组件 | 视三个视图各自的后端契约而定 |

建议合并节奏：S 单独一个 PR（风险极低、收益立现）；M 一个 PR；L 按视图拆。

## 10. 明确不做什么

- 不恢复任何已退役元素：`writer-studio-grid`、折叠 composer、深色 `writer-agent-rail`、旧蓝 UI，一律不出现。
- 不改 IA：稿件仍是唯一主角，Agent 仍是右侧常驻 dock（连续 thread + 常驻 composer + 选区驱动），视图切换只是补齐规范早已要求的画布头。
- 不动任何行为逻辑、API 契约、数据流；不引入新字号、新色相（旧金/朱砂/暖墨词表内消化全部需求）。
- 不给「章节/审校/工具」渲染任何假内容或 mock 成功路径。

## 11. 迭代记录（截图自检）

- v1：整屏首版。发现：时间线脊线拖尾成杂线、气泡描边偏粉、稿纸顶双发丝像瑕疵、卡片字号 12.5 出词表。
- v2：脊线改逐节点接头、气泡描边 20%→15%、删顶线、加「今天」分隔、字号归 13。发现：composer 提示半词折行、连续气泡间距偏大。
- v3（定稿）：提示固定两行、连续气泡收 6px、加 1.6% 纸纤维颗粒（先 2.2% 试脏后降到 1.6%）。定稿截图 `prototype-a.png`。
