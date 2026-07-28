# 方案 B：文学编辑部（Editorial）

写作台 UI 重设计 · 2026-07-27 · 静态原型见同目录 `prototype-b.html` / `prototype-b.png`

---

## 1. 一句话性格

把写作台从「带聊天侧栏的编辑器」改成**一间文学杂志的编辑室**：稿纸是版心，合著者是坐在对面的编辑，往来指令是批条，候选稿是排样小样，已采用的是归档记录。控件体系仍是现代 SaaS（按钮、tab、dropdown、autosave 一个不少），但视觉语言完全交给书版排印。

参照：New Yorker 数字版的页眉栏规与字级纪律、Craft 的版面克制、Readwise Reader 的阅读栏宽与边注。不复制任何一家的品牌元素。

## 2. 对用户痛点的回应

| 截图里的毛病 | 本方案的处置 |
|---|---|
| 左栏聊天气泡 + 大红按钮堆叠，像客服窗口 | 气泡全部废除。指令改「批条」（朱丝栏左边线 + 字距拉开的红色小 label + serif 正文）；状态改「工单行」（№ 编号 + 一行归档记录） |
| 空段落显示为带边框的输入框，稿纸像表单 | 画布彻底去卡片化：无边框、无阴影、无背景块。空段就是版面上的淡字「接着写——」加一枚红色光标，焦点落上去才出现编辑暗示 |
| 版面没有层级，找不到「大厂感」 | 强势字级对比：10.5px 字距 0.22em 的家具级小字 ↔ 30px serif 章题 ↔ 17px 书版正文；双线栏规、栏网格、页边注、页脚 folio 建立「场所感」 |
| 色彩散（金、红、绿、蓝灰并存） | 近乎单色：墨黑 + 米白 + 一枚编辑红。金色只留候选/待审功能色的文字级用法，绿色只留 ✓，全屏无第四种彩色 |

## 3. 设计原则

1. **排印即界面**：能用字级、字距、栏规解决的，就不用卡片、阴影和底色块。画布上只允许排版，不允许容器。
2. **红是动词**：编辑红只标动作与编号——采用、发送、查看正文、№ 工单号、active tab、印章起字。一屏同时出现的红不超过七处。
3. **栏网格纪律**：64px 导航 + 396px 编辑室（≈4 栏）+ 弹性画布（≈8 栏）；版心 664px（约 36em 书版行宽）居中，左右留白即页边距，右页边距承载边注。
4. **页眉页脚的场所感**：页眉是杂志 folio（刊名 + 书篇面包屑 + 视图切换 + 一行双线栏规），页脚是书版 folio（章 · 字数 · 自动留痕）。任何时刻都知道自己坐在哪本书的第几章。
5. **诚实不动数据结构**：全部改动是表现层；run 轮询、autosave、乐观锁、采用链路原样保留。

## 4. Token 草案

定位为现行 `paper & vermilion` 体系的**编辑部变体**：不改品牌主色，收紧使用纪律，新增排印 token。写入 `apps/web/app/globals.css` 的 `@theme`。

### 4.1 颜色（沿用为主，两处调整）

```css
/* 沿用 */
--color-accent: #8f211b;        /* 编辑红 = 现行品牌朱砂，不另立新色 */
--color-accent-strong: #7a1a15;
--color-gold: #b5854a;
--color-candidate: #856530;     /* 候选/待审功能色：只用于文字与细线，不再做大底色 */
--color-success: #3f7a4a;       /* 仅 ✓ 图标 */

/* 调整：栏规由棕调改墨调，与正文墨同源，版面更「印刷」 */
--color-line:       rgba(33, 29, 22, 0.16);
--color-line-soft:  rgba(33, 29, 22, 0.09);
--color-line-strong: rgba(33, 29, 22, 0.34);  /* 新增：folio 栏规、墨线框 */

/* 微调：纸色略降亮度，给 serif 正文更稳的底 */
--color-paper: #f6f0e1;
--color-panel: #fbf7ec;         /* 仅用于浮层（dropdown、选区 pop），画布不再用 */
```

色彩纪律（硬性）：画布与 dock 背景只有 paper；panel 只给浮层；候选稿卡片用墨线框而不是金底色；红的使用场景封闭为「主按钮 / active 标记 / № 编号 / 查看正文链接 / 印章起字 / 光标」。

### 4.2 排印（新增四级，其余沿用现行 8 档字阶）

```css
/* 家具级（页眉页脚、eyebrow、编号行）——CJK 无 small caps，用字距代替 */
--text-folio: 10.5px;
--text-folio--line-height: 1.4;
--tracking-folio: 0.22em;       /* 与现行 --tracking-label 并存，用于更轻的页脚 */

/* 书版正文（稿件画布专用） */
--text-reading: 17px;                    /* 沿用 */
--text-reading--line-height: 1.95;       /* 由 1.85 放宽，书版气口 */
--measure-prose: 664px;                  /* 版心行宽 ≈36em */
--indent-prose: 2em;                     /* 段首缩进，替代空行分段 */

/* 章题 */
--text-chapter: 30px;            /* 复用 --text-display，语义化别名 */
--text-chapter--line-height: 1.3;
```

字体不变：正文/章题/批条/小样正文走 `--font-serif`（Songti SC 系），家具文字与控件走 `--font-serif` 之外的 `--font-sans`（PingFang SC 系）。**serif 主导体现在版面面积，不体现在控件上**——控件保持 sans，这是与「纯阅读器」的分界线，也是 SaaS 控件可用性的底线。

### 4.3 印章起字（首字下沉）

```css
--dropcap-size: 56px;    /* 恰好占两行书版正文（2 × 33px 行高 ± 边距） */
--dropcap-font: 33px;
```

红底白字、4px 圆角、内描边 + 轻微落影——是品牌印章在版心里的回声，每章仅一枚。印刷物是静的，它不做任何动效。

### 4.4 阴影（收紧）

画布上去掉 `shadow-panel`（稿纸不再投影）；阴影只留给真正浮起的层：dropdown（`shadow-lift`）、选区 pop（`shadow-lift`）、主按钮（`shadow-accent`）。

## 5. 布局

```
┌────┬──────────────────────────────────────────────────┐
│ 64 │ 页眉 folio（57px）+ 双线栏规（4px）                │
│ px ├─────────────┬────────────────────────────────────┤
│ 导 │ 编辑室 396px │ 画布（弹性，版心 664px 居中）       │
│ 航 │ 往来/审校篮  │  running head · 书版正文 · 页脚folio │
└────┴─────────────┴────────────────────────────────────┘
```

- 左 dock 保持 396px（现行 `rail-inspector` 360px 基础上放宽 36px，给 serif 小样正文 13.5px 舒适的 28 字行宽）。
- 画布背景不做卡片，只在正上方做极轻的中心聚光（radial-gradient），版心自然浮出。
- 右页边距（版心外 24px 起，160px 宽）承载**页边注**：候选稿入稿出处、审校批注的落点。宽屏 ≥1600 时显示，不足时收起为段尾小标。

## 6. 组件级改动清单（按现行文件）

### 6.1 `apps/web/app/globals.css`

- 按 §4 调整 `--color-line*` 与 `--color-paper/panel`，新增 `--color-line-strong`、`--text-folio`、`--tracking-folio`、`--text-chapter`、`--measure-prose`、`--indent-prose`、dropcap token。
- 新增工具类：`.folio-rule`（页眉双线栏规）、`.prose-book`（书版正文：缩进/两端对齐/1.95 行高/段间距 4px）、`.dropcap-seal`（印章起字）、`.marginote`（页边注）。
- 对比度底线维持：正文级一律 ≥ `--color-muted`（#6b6355 on #f6f0e1 ≈ 5.2:1）；`--color-muted-soft`/#8a8070 只允许装饰字符（分隔符、花线）。

### 6.2 `writer-canvas-top.tsx`（页眉）

- 重排为杂志 folio 一行：`墨鱼小说`（serif 刊名，字距 0.14em）→ 面包屑 `书架 › 书名 › 第 N 章▾`（章节 dropdown 逻辑不动）→ **视图切换 tabs：稿件 / 章节 / 审校 / 工具**（下划线 active，红色 2px）→ 右侧 `字数 · 保存态 · 新章节`。
- 页眉底部加 `.folio-rule` 双线栏规（1px strong + 4px 空 + 1px）。
- 视图 tabs 是画布头视图切换的 IA 落地（见 §8 分期：只对真实存在的视图出现，不做死 tab）。

### 6.3 `manuscript-paper.tsx`（画布，改动最大）

- **去卡片**：删除 `rounded-control border bg-panel shadow-panel` 的纸张卡片；blocks 直接排在画布上，版心 `max-width: 664px`。
- **章首 running head**：kicker（卷/部，folio 级字距 0.3em）+ 章题（serif 30px）+ 花线（双 hairline + 红色 7px 方钻）。
- **书版正文**：段落 `text-indent: 2em`、`text-align: justify`、行高 1.95、段间距 4px；段与段之间的 `border-t` 分隔线删除——段边界只在 hover/focus 时以左页边 ¶ + 细规暗示（编辑态），阅读态是连续版面。
- **印章起字**：每章首段首字渲染为 `.dropcap-seal`，该段去 `text-indent`。
- **空段修复**（截图痛点）：空 textarea 不再有任何边框/底色；placeholder 即版面文字「接着写——」+ 红色 caret（1.1s blink）；焦点只加左侧 2px 红规，不出现输入框。
- **页边注**：block 有 `source_writer_run_id` 时，右页边距渲染 `№N 候选稿入稿 / HH:MM · 查看往来 →`，点击触发现有 `onRevealAdopted` 的反向导航（数据已在 workspace 的 `settledRuns` 里，纯前端改动）。
- **页脚 folio**：`—— 第 N 章 · 共 N 字 · 稿纸自动留痕 ——`（hairline 翼线 + folio 级字距），替代现行居中小注。

### 6.4 `writer-rail.tsx`（编辑室往来，换皮不换逻辑）

| 现行 | 编辑部版 |
|---|---|
| `UserBubble` 红底气泡 | **批条**：2px 红左边线 + `作者指令 · HH:MM`（folio 级红 label）+ serif 13.5px 正文 |
| `TaskCard` 状态卡 | **工单行**：`№N`（红）+ 状态一行 + 可展开步骤（逻辑不变） |
| `CitationsRow` 药丸 chips | **脚注式参考**：`参考设定` folio label + serif 词表（dotted underline，顿号分隔），title 提示不变 |
| `CandidateCard` 金虚线框卡 | **排样小样**：1px 墨线框 + `— 候选稿 №N` 红色 eyebrow + 金色一致性提示条（左边线 + 8% 底）+ serif 正文 fade 截断 + 底行「退回重写 / 采用进手稿（唯一红实心按钮）」 |
| `SettledCard` 折叠卡 | **入档行**：一行 `✓ №N 候选稿 · 已入稿 · N 字` + 右侧红 `查看正文 →`；展开全文交互保留 |
| `RailGreeting` | 编辑室引言：serif 一句 + folio 级说明，去圆形图标底 |

编号 №N 来自 run 在 thread 中的序号（前端派生，不需要后端新字段）。

### 6.5 `writer-composer.tsx`（指令栏）

- 框体改 1px 墨线（`--color-line-strong`）+ 3px 圆角，focus-within 时框线变红（逻辑不变）。
- 发送钮改红色方块（4px 圆角 + ↑），placeholder 改 serif「下达指令——续写、改写、起一场戏…」。
- hint 收敛为一行 folio 级：`ENTER 发送 · SHIFT+ENTER 换行 · 起草先为候选稿`。

### 6.6 `composer-review-flip.tsx`（dock 双面）

- dock 头部改双 tab：**往来 / 审校篮（红色 count 圆点）**，替代现行「待审资产 →」翻转按钮。
- 切换动效用 200ms cross-fade 替代 500ms rotateY 翻卡（翻卡的游戏感与编辑部气质不符；flip 不在退役清单，此为由产品确认的换皮，两面内容与数据逻辑一行不动）。

### 6.7 `proposal-rail.tsx`（审校篮面）

- 卡片改墨线框；类型标签改文字级（金色 text + hairline border，不再金底）；出处证据块保持纸底；全部按钮交互、批量通过、版本竞态处理不变。

### 6.8 `writer-empty.tsx`

- 空项目首屏改书版邀请：kicker + serif 标题 + 一枚红 caret + 唯一红按钮「立下第一章」（现行逻辑不变）。

### 6.9 `workbench-masthead.tsx`

- 写作台不使用该组件（页眉已 folio 化）；其它工作台是否跟进 folio 化出本方案范围，仅记录为后续方向。

## 7. 动效规格

原则：**像翻页，不像换屏**。时长沿用现行 160/220/280ms 与 `ease-paper`（cubic-bezier(0.22,1,0.36,1)），不引入新曲线。

| 场景 | 规格 |
|---|---|
| 视图 tab 切换 | 下划线 220ms 滑动；内容区 200ms opacity + 4px 上移 |
| 往来 ↔ 审校篮 | 200ms cross-fade（替换 rotateY） |
| 候选稿出现 | 现行 fade-up 220ms 保留 |
| 采用成功 | 小样 280ms 向上 6px 淡出 → 画布对应段 480ms 红 wash pulse（沿用 reveal flash 机制） |
| 查看正文 / 查看往来 | smooth scroll + 目标段/目标工单行 480ms pulse（沿用） |
| 流式起草 | 红色 caret 1.1s steps(1) 闪烁；进度 hairline indeterminate 1.6s 循环 |
| 页边注/hover ¶ | 160ms opacity 淡入 |
| 印章起字、花线、栏规 | 静止，不动 |
| `prefers-reduced-motion` | 全部降级为即时切换（沿用现行媒体查询模式） |

## 8. 落地范围与分期

**第 1 期 · 纯皮相（零数据/接口改动，风险最低）**
`globals.css` token + §6.2 页眉 folio（不含视图 tabs）+ §6.3 画布书版化（去卡片、running head、缩进、空段修复、页脚）+ §6.4 往来条目换皮 + §6.5 指令栏 + §6.8 空态。完成后即可整屏验收。

**第 2 期 · IA 补全（真实视图驱动）**
画布头视图 tabs：「稿件」为默认视图；「章节」接真实章节导航；「审校」「工具」**只在对应后端能力落地时才出现 tab**，不提前放占位死控件（与「不添加 mock 路径」约束同源）。同期做 §6.6 双 tab 替换翻卡。

**第 3 期 · 精修**
页边注 marginalia（数据已在 `settledRuns`，纯前端）+ 选区 pop（选区驱动调用：选中正文 → 浮出「改写此段 / 自此续写 / 送审校」，预填 composer 并携带选区上下文——需 workspace 增加 selection 状态，仍无后端改动）+ 审校篮面换皮对齐。

**明确不做**：不改 run 轮询/autosave/乐观锁/采用链路；不动 Go API；不恢复 `writer-studio-grid`、折叠 composer、深色 `writer-agent-rail`、旧蓝色 UI；不引入暗色模式；不给正文区加回任何卡片容器。

## 9. 与现行体系的关系

本方案不是推翻 `paper & vermilion`，而是把它在写作台内做一次**排印纪律收紧**：品牌朱砂变成编辑红并封闭使用场景，栏规从棕调转墨调，阴影从「纸的厚度」退到「浮层的高度」。若 A/B 方向最终选定其它方案，本方案的 §4.2 排印 token、§6.3 空段修复与 §7 动效表仍可作为独立补丁合入。
