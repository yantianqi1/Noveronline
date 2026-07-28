# B2：文学编辑部 · 净版（proposal-final）

写作台 UI 重设计 · 2026-07-27 · 在方案 B（`proposal-b-editorial.md`）基础上的收敛增量。
原型：`prototype-final.html` / 定稿截图 `prototype-final.png`。

## 0. 来源

四轮方案评审结论：A 左栏聊天区杂乱；B 方向获认可但「左边线条太多」；C 整体换色与其余工作台不一致，否决。B2 的执行边界：**色板完全不动**（`globals.css` 现行 paper & vermilion 原值，保证全站一致），**画布/稿纸原样保留 prototype-b**（版心、running head、印章起字、页边注、「接着写」均不变），只重构左侧 dock，执行「线条预算」。

## 1. Dock 减负规则清单（线条预算）

| # | 规则 | 对 B 的处置 |
|---|---|---|
| 1 | dock 内容区只允许两种线：**天与天之间的一条 hairline**、**tab 下划线指示**。消息级边框、左侧竖规、chips dotted underline 全禁 | 删除：批条 2px 红左边线、入档行 border-top、召回词 dotted underline、工单行 hairline、dock 头部 border-bottom、composer 顶部 border 与外框、进行中进度条 |
| 2 | 发言改纯排印：`你 / 合著者 · HH:MM`（10.5px muted 字距行）+ serif 正文，留白分组；同一说话人连续消息合并为一个 meta 多个段落 | `UserBubble`/`AgentLine` 的气泡与批条框全部废除 |
| 3 | 召回 chips 收成一行 muted 小字，词间 `·` 分隔：`参考设定 · 常驻李典史 · 炼精境 · 假银 · 税银案 · ＋8` | `CitationsRow` 的 pill/药丸全部删除 |
| 4 | 候选稿卡是 dock 唯一容器：单 hairline 框 **或** paper-deep 洗底（已对比，见 §2）；卡内不得有第二条边框 | 金色一致性提示由「左边线条 + 底色条」改纯文字一行；卡内 foot 的 border-top 删除；红色 eyebrow 保留；卡内唯一实心朱红按钮「采用进手稿」 |
| 5 | 已采用/已完成记录压成单行：`✓ №N 候选稿已入稿 · N 字 · 查看正文 →`，无框 | `SettledCard` 的折叠卡壳删除（展开全文交互在实施时改为行内展开，不加框） |
| 6 | composer 提示一行：`ENTER 发送 · SHIFT+ENTER 换行 · 起草先为候选稿`；dock 头部 tab 只保留下划线指示，badge 用 muted 数字（`审校篮 3`），不用色块 | composer 外框删除（无框输入 + 朱红发送方块锚定）；计数 badge 的红底白字删除 |
| 7 | 稿纸画布原样 | 未动 |

补充：天分隔采用「一条 hairline + 线上居中 folio 日期字」（今天 · 7 月 27 日），首个日期组（昨天）只有文字标签、不带线。dock 与画布之间的栏分界（1px line-soft）属全局分栏 chrome，不计入内容区预算。

## 2. 候选稿卡两变体取舍结论

两变体各截一整屏对比（`prototype-final-v1.png` = hairline 框，`prototype-final-card-wash.png` = paper-deep 洗底）：

**选用 hairline 框（frame）。** 理由：
- 洗底是一整块 paper-deep 色团，与左侧导航栏同色，视觉上连成一片，反而削弱「dock 里唯一容器」的特殊性；hairline 框只加一条 1px 线、不增加任何色块质量，更「净」。
- 框的直边与全站 folio 栏规语言同源（栏规、页脚翼线都是 hairline），洗底的圆角色团在排印体系里没有第二个呼应物。
- 全屏构图上，洗底色团在 dock 下半部形成视觉重心，会把视线从稿纸正文抢走；框变体保持 dock 轻、画布重。
- 实施成本相同（一个 `border: 1px solid var(--line)`，圆角 6px 用现行 `--radius-control`）。

## 3. 组件级改动：相对 proposal-b 的差异

| 文件 / 组件 | B 的设计 | B2 的处理 |
|---|---|---|
| `globals.css` token | 调整纸色/栏规为墨调，新增 folio/chapter/dropcap 等 token | **色板全部回退为现行原值**（paper `#f7f2e9`、line `rgba(86,69,45,.22/.12)`、muted `#5a5146` 等）。排印 token 新增保留（folio 字距、书版行宽、缩进、dropcap），但不再改任何既有颜色 |
| dock 头部 | 红色方块 mark + 标题 + 双 tab + 红底 count badge | 去方块 mark；tab 保留下划线指示；badge 改 muted 数字；头部底部分隔线删除（无线，靠字级分组） |
| `UserBubble` → 批条 | 2px 红左边线 + 红色 label + serif | 红左边线删除，label 改 muted（不红）：`你 · HH:MM`；同色连续消息合并 |
| `TaskCard` 工单行 | hairline 分隔的状态卡 | 删除卡壳；状态并入单行记录或「起草中」meta 组 |
| `CitationsRow` | 脚注式 dotted underline 词表 | dotted underline 也删除，纯一行 muted 小字 |
| `CandidateCard` galley | 墨线框 + 金色提示条（左边线+底色）+ foot border-top | 框改回原色板 line；提示条改纯文字一行（candidate 金色字）；foot 无线；其余保留（红 eyebrow、fade 截断、退回重写 ghost、采用红钮） |
| `SettledCard` | 入档行（border-top hairline） | 去 hairline，纯单行；紧贴在对应指令下方 |
| 进行中 | 状态行 + 红色进度 hairline + 流式正文 | 进度条删除（直播感由 spinner + 流式正文 + 红 caret 承担） |
| `WriterComposer` | 墨线框 + 红方块 | 外框删除：无框 serif 输入区 + 红方块发送；hint 一行 |
| `ConversationReviewFlip` | 双 tab + 200ms cross-fade（替代翻卡） | 不变，沿用 B 的第 2 期提案 |
| `ProposalRail` 审校篮面 | 墨线框 + 文字级标签 | 沿用 B，随色板回退原值 |
| 画布（`manuscript-paper` 等） | running head / 印章起字 / 页边注 / 页脚 folio | **原样保留**（仅随色板回退映射到原 token 值） |
| 页眉 folio + 视图 tabs | 不变 | 不变（原色板） |

动效规格与三期落地范围沿用 `proposal-b-editorial.md` §7/§8，仅删去其中「进度 hairline」一条。

## 4. 最终 dock 线条清单（验收用）

内容区共 **3 条**，全部符合预算：

1. 「往来」active tab 下划线（朱红 2px）——预算项：tab 指示。
2. 天分隔 hairline 一条（昨天 / 今天之间，`--color-line-soft`，线上带居中日期字）——预算项：天与天分隔。
3. 候选稿卡外框一周（`--color-line` 1px，dock 唯一容器）——预算特许项。

另有全局 chrome 两条（不在 dock 内容区预算内）：dock 与画布之间的栏分界 1px、dock 所在右半整体的页眉 folio 双线（属画布侧页眉）。除此之外 dock 内无任何线：无消息边框、无左竖规、无 dotted underline、无卡内分隔、无 composer 框、无 badge 色块。
