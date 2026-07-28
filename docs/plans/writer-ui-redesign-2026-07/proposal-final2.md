# 终版增量：B 画布 × C dock × 纸墨色板

写作台 UI 重设计终版 · 2026-07-28 · 原型：`prototype-final2.html` · 定稿截图：`prototype-final2.png`（迭代：`prototype-final2-v1.png` → `prototype-final2-v2.png`）

## 0. 最终形态（用户已拍板的三条边界）

- **画布 = B 终版稿纸**（`prototype-final.html` 的版心 / running head / 印章起字 / 页边注 / 选区 pop /「接着写」/ 页脚翼线），内容不变，原样搬运。本文档不重复画布设计，只约定接口。
- **dock = C 的结构与密度**（`prototype-c.html`：tabs + 天分隔锚 + 行式 run 记录 + 候选稿卡 + kbd composer），**配色全部换成现行 paper & vermilion token**。C 的黛蓝换色已否决，全站保持纸墨体系。
- **比 C 再减一分乱**：去重的核心是消灭重复 meta——一 run 一行、用户指令纯文本、steps 默认收起、召回一行 truncated、composer note 一行。

信息架构零改动：manuscript-primary（稿纸主导）+ conversation-first（常驻 dock：连续 thread + 常驻 composer + 选区驱动调用）+ 画布头视图切换（稿件/章节/审校/工具）。

## 1. Dock 逐组件说明（相对 prototype-c 的改动）

### 配色映射（黛蓝 → 纸墨）

| C（黛蓝体系） | 终版（纸墨体系） | 说明 |
|---|---|---|
| `--accent #3a49be` | `--accent #8f211b`（现行原值） | 实心仅两处，见 §2 纪律 |
| dock 底 `#ffffff` | `paper #f7f2e9` | 卡片用 `panel #fffdf8` 浮于纸面 |
| 灰阶 ink/ink-2/ink-3 | `ink #171a1b` / `ink-soft #3c3a36` / `muted #5a5146` / `muted-soft #6f6559` | 全部现行 token，零新增 |
| hairline `#e7e5e0` | `line rgba(86,69,45,.22)` / `line-soft rgba(86,69,45,.12)` | 暖色线 |
| 选中/选区 wash 蓝 | `accent-wash rgba(143,33,27,.07)` | 与画布选区同源 |
| 候选语义 = accent 蓝字 | `candidate #856530` **仅文字级**（tag、warn 行、tab 计数） | 金色不做任何填充/边框 |

### 朱红稀缺纪律（dock 内审计）

实心朱红填充**全 dock 只有两处**：候选稿卡「采用进手稿」、composer 发送键。其余朱红出现位置仅为：active tab 2px 下划线（选中态，设计文档允许）、`focus-within` 边框、「查看正文」与 ghost 按钮的 hover 文字色。rail 顶部品牌印章「墨」属品牌位，不在 dock 内。

### 去重规则（比 C 减的那一分乱）

1. **一 run 一行**：C 里「已完成 · 候选稿 X 字」与「已采用 · 进手稿 / 查看正文」是两条堆叠记录；终版合并为单行——`✓ 已采用 · 3,510 字进手稿 …… 查看正文`（trail 位）。待采用的 run 则是 `✓ 已完成 · 候选稿 3,510 字 …… ›`（chevron 即 steps 展开位）。
2. **用户指令纯文本**：删气泡容器、删每条 meta 时间；宋体 13.5px ink 一行（作者之声用宋体、系统记录用黑体，纯字族区分角色，零家具）。时间只由「昨天 / 今天」天分隔线承担。
3. **steps 默认收起**：C 原型展示过展开态；终版静态只呈现收起行（展开交互不变：行内 height 180ms）。
4. **召回一行 truncated**：`参考了 常驻 · 李典史 · 炼精境 · 假银 · 税银案 · 李…`，nowrap + ellipsis，`title` 保留完整名单与召回渠道。
5. **一致性提醒一行**：卡内金色文字一行（文案收缩为「与设定可能有出入 · 1 处：沈平志职务与档案不符」），全文在 `title`。
6. **composer note 单行**：`起草内容先作候选稿，经你采用才进手稿。`，nowrap + ellipsis。
7. **候选稿摘录与画布同排印**：serif 13.5/1.8 + `text-indent: 2em` + clipped 渐变收起（C 是无缩进 + 文字「余下 X 字」行，终版删去那行 meta）。

### Dock 最终视觉元素清单（全部）

dock-head（对话 tab + 朱红下划线 / 待审资产 tab + 金色 mono 计数 / ⌘J kbd）→ 天分隔线（hairline + 10.5px 字距标签）→ turn（宋体 say 一行/两行 + run 单行）→ 召回行 → 候选稿卡（头 / warn 一行 / 摘录 / 足 note + 采用钮）→ composer（hairline 盒：placeholder + ⏎⇧⏎ kbd 行 + 发送键；盒下单行 note）。没有第七类东西。

## 2. 相对 apps/web 现行代码的组件级改动清单

一期原则：**纯皮相，零数据流**——不动 API、run 事件流、thread 持久化、adoption 语义、`source_writer_run_id` 互链逻辑；以下全部是 className/结构重排与样式替换。画布侧（B 稿纸）由 B 方案文档覆盖，此处仅列 dock 与顶栏。

### `globals.css`

零改动。全部取值已在 `@theme`（paper/panel/ink/muted/line/accent/candidate/success）；kbd 样式不进全局 token，落在组件内联类（`font-mono text-micro border border-line rounded-control bg-panel px-1 py-px`）。

### `writer-canvas-top.tsx`（顶栏）

- chapter switcher 之后新增 **ViewTabs** segmented 壳：`稿件/章节/审校/工具`，一期仅「稿件」可用，其余 `disabled` + `title="后续波次"`（不做假视图，遵守无 mock 纪律）；样式 = `bg-paper-deep` 底槽 + active 格 `bg-panel border-line-soft`。
- 字数 span 加 `font-mono tabular-nums`（现行 `text-caption tabular-nums`，仅换字族）。
- `SaveIndicator`：图标+文字 → **状态点+文字**（dirty=`candidate` 点「未保存」、saving=旋转点、saved=`success` 点、conflict/error=`danger` 点+原消息）；错误全文逻辑不动。
- 「新章节」按钮维持现行 ghost（`border-line bg-panel hover:border-accent/50 hover:text-accent`），不改。
- ⌘K chip **一期不做**（命令面板属 P2；不为视觉效果放假入口）。

### `writer-rail.tsx`（改动最大）

- `UserBubble`：`bg-accent text-panel shadow-accent rounded-modal` 气泡 → **纯文本段落**（`font-serif text-[13.5px] text-ink leading-[1.7]`，无容器）；删除右侧对齐与 meta 时间。
- 新增 `DaySeparator`：thread 按 message `created_at` 前端分组（数据已有，纯派生），渲染 hairline +「昨天/今天」。
- `TaskCard` → **run-row**：去 `rounded-modal border bg-panel` 卡片壳，改单行（icon 14px + `text-sm ink-soft` label + trail）；数字加 `tabular-nums`；steps 展开逻辑与 `AnimatePresence` 保留（现行默认收起，不变）；取消按钮 live 时仍在 trail 位。
- `SettledCard` → **并入 run-row**：`✓ 已采用 · {words} 字进手稿` + trail「查看正文」（`text-muted hover:text-accent`，MapPin 图标保留）；现行展开读正文的折叠区保留在行下（默认收起），删除卡片边框、底部说明行「已进手稿，可在稿纸上继续改」（与按钮语义重复，属去重范围）。
- `CitationsRow`：chips 阵列 → 单行 `text-caption text-muted` truncated（`常驻 · {title} · … +N`）；现有全部 `title` 说明（召回渠道/相关度/降级/预算裁剪）原样保留。
- `CandidateCard`：`border-dashed border-gold/60` + 金色胶囊角标 → `bg-panel border-line rounded-control` hairline 卡；`候选稿` tag 改 `text-candidate` 文字级；`ConsistencyNotice` 并入卡内一行（`text-candidate`，单行 ellipsis + `title`）；正文 `font-serif` + `text-indent: 2em` + `max-h` clipped 渐变（渐变到 `panel`）；底部「采用进手稿」保持 `bg-accent` 实心（去 `shadow-accent`，改 `shadow-hairline`）。
- `RailGreeting` 一期不动。

### `composer-review-flip.tsx`

- rotateY 3D 翻转容器 → **dock-head 内 tab 切换**：「对话 / 待审资产 {count}」两个 text tab（active：`text-ink font-semibold` + 2px `bg-accent` 下划线），内容区 160ms crossfade；`pendingCount`/`hasNew`/`onCountChange` 同步逻辑全部保留（hasNew 红点移到 tab 计数旁，仍 `bg-accent`）。
- 背面标题栏与「返回合著者」底部按钮随 flip 一并删除（tab 本身就是回程）；`ProposalRail` 作为 tab 内容挂载，props 不变。

### `proposal-rail.tsx`

- 计数徽标：`bg-candidate text-panel` 胶囊 → `text-candidate font-mono` 纯数字文字（金色仅文字级）。
- 候选卡片：`border-gold/50 bg-gold/10` 类金色边框/底 → `border-line bg-panel` hairline；`新增/更新/冲突` 状态保持文字（仅「冲突」用 `text-candidate`）。
- 「一键全部通过」保持现行组件与逻辑，视觉降 ghost；单卡决策按钮层级不变。批量进度、错误路径、版本竞态处理零改动。

### `writer-composer.tsx`

- 外盒去 `shadow-panel`（hairline 即可），`focus-within:border-accent/50` 保留。
- 盒内底部新增 kbd 行：`⏎ 发送` `⇧⏎ 换行`（内联 kbd 类，见上）；发送键 `bg-accent` 保留、去 `shadow-accent`、尺寸 32→26px。
- 底部说明压为单行 `text-micro text-muted` nowrap ellipsis：`起草内容先作候选稿，经你采用才进手稿。`（解决现行折行）。
- autosize/disabled/发送逻辑零改动。

### `manuscript-paper.tsx`

由 B 终版方案覆盖（稿纸是用户认可的 B）。与 dock 的接口仅两处，均为现行已有：`查看正文` → `revealBlockId` 滚动脉冲；被采用块 provenance（`source_writer_run_id`）→ 画布侧呈现（B 的页边注）。本方案不改此文件。

## 3. 迭代记录（2 轮截图自检 + 局部放大）

- **v1**（`prototype-final2-v1.png`）→ 挑毛病：卡内 warn 行折成两行（卡宽 352−缩进后放不下 28 字）；候选稿摘录无首行缩进，与 B 画布的 2em 排印不一致；整屏核对 marginote / sel-pop / 页脚均完整。
- **v2 = 定稿**（`prototype-final2-v2.png` → `prototype-final2.png`）→ warn 改单行文案（全文入 `title`）；摘录加 `text-indent: 2em`；放大复检 dock 密度与天分隔、合并行、truncated 召回、composer 全部达标。
- 从 C 继承时预先执行的去重（未进 v1 即生效）：run 状态行与「查看正文」合并、用户气泡与 meta 时间删除、steps 收起、召回一行。
