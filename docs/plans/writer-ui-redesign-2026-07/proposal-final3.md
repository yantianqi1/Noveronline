# 终版 3：C dock 原样 × B 画布 × 纸墨色板

写作台 UI 重设计终版（用户拍板）· 2026-07-28 · 原型：`prototype-final3.html` · 定稿截图：`prototype-final3.png`（迭代：v1→v4）

## 0. 最终形态

- **dock = prototype-c 左侧 dock 的原版样式与结构**，逐组件忠实还原：右对齐用户消息气泡、「已完成 / 已采用」双状态行、可展开 steps（图标 + mono 耗时）、「参考了…」召回行、候选稿卡（head / serif 摘录 + fade 行 / foot 含「采用进手稿 ⌘⏎」）、kbd composer（盒内 ⏎/⇧⏎ 提示 + 发送键 + 单行 note）。**相对 C 唯一的变化是配色**——黛蓝 → 朱红，中性冷灰 → 纸墨暖灰，不引入任何新色。
- **画布 = B 编辑部稿纸**（与 final2/final 一致，用户认可，零改动）；顶栏 / 图标轨 = final2 纸墨化版本（零改动）。
- **朱红稀缺纪律**：dock 内实心朱红填充仅候选稿卡「采用进手稿」与 composer 发送键；其余朱红只出现在 focus 边、hover 文字、品牌印章（rail）。候选语义色（`candidate` 金）仅文字级（候选稿 tag）。dock tab 的 active 下划线用 **ink**（忠实于 C 的中性处理，不占用朱红）。

## 1. 相对 prototype-c 的逐组件配色映射表

C 的中性色阶 → 纸墨 token（均为 `globals.css` 现行值，零新增 token）：

| 组件 | prototype-c | final3（纸墨） | 备注 |
|---|---|---|---|
| dock 底 | `#ffffff` | `paper #f7f2e9` | 卡片/气泡浮于纸面 |
| 用户消息气泡底 | `bg-sunken #efeeea` | **`paper-deep #efe7d8`**（用户指定） | ink 文字上纸深底 ≈ 10.9:1 |
| 气泡边 | `line #e7e5e0` | `line-soft rgba(86,69,45,.12)` | 暖色 hairline |
| 卡/composer 盒底 | `#ffffff` | `panel #fffdf8` | |
| 结构边（dock 缘、卡边、盒边、kbd 边） | `line / line-strong` | `line rgba(86,69,45,.22)` | |
| 内部 hairline（head 底、卡内分隔、divider） | `line` | `line-soft` | |
| 一级文字 | `ink #1c1b18` | `ink #171a1b` | 16+ : 1 |
| 二级文字 | `ink-2 #57544d` | `ink-soft #3c3a36` | |
| 元信息/steps/recall/hint | `ink-3 #716d65` | `muted #5a5146`（最浅处 `muted-soft #6f6559`） | 现行 token 已验 ≥4.5:1 |
| hover 底 | `#f3f2ef` | `rgba(86,69,45,.06)` | 暖色 hover |
| run 完成图标 | `success #3a7d54` | `success #3f7a4a`（现行原值） | |
| 已采用文件图标 | `ink-3` | `muted` | |
| 「查看正文」链接 | `ink-3` → hover 黛蓝 | `muted` → hover 朱红 | 与现行生产一致 |
| 候选稿 tag | 黛蓝文字 | **`candidate #856530` 金色文字** | 唯一非机械映射：纸墨体系里「状态徽章不得用朱砂」（设计文档），候选语义由金色承担，仅文字级 |
| 采用按钮 | 黛蓝实心 + ⌘⏎ | **朱红实心 `#8f211b`** + ⌘⏎（半透明 kbd） | 稀缺纪律位 ① |
| 发送键 | 黛蓝实心 | **朱红实心** | 稀缺纪律位 ② |
| composer focus 边 | 黛蓝 | `rgba(143,33,27,.5)` | focus ring，与现行生产一致 |
| tab active 下划线 | `ink`（C 原本就是中性） | `ink #171a1b` | 不占朱红 |
| 待审计数徽标 | `ink-2` on `sunken` | `ink-soft` mono on `paper-deep` | 中性（金色只留给候选语义文字） |
| `::selection` | 黛蓝 wash | 朱红底白字（现行全局） | |

字号/间距/圆角全部沿用 C 的几何（dock 352px、thread padding 12/14、turn 间距 22/10、bubble radius 8 padding 6/10、run-row 32px、steps 缩进 22px、卡 radius 8、composer 盒 radius 8）。一期实施时圆角映射到现有 token：`rounded-control(6)` 给按钮/kbd/run 行，`rounded-panel(10)` 给气泡/卡/composer 盒——不新增 radius token，8→10 的视觉差异可忽略。

## 2. 相对 apps/web 现行代码的组件级改动清单

沿用 `proposal-final2.md` §2 的清单（一期纯皮相零数据流），以下仅列**因「恢复 C 原样」而变化的条目**，未列出的条目（顶栏 ViewTabs/状态点、flip→tabs、proposal-rail 中性化、manuscript-paper 归 B、globals.css 零改动）与 final2 一致：

### `writer-rail.tsx`

- `UserBubble`：**保留气泡容器形态**（撤销 final2 的「纯文本段落」改动）——`bg-accent text-panel shadow-accent rounded-modal` 朱红气泡 → `bg-paper-deep border border-line-soft text-ink` 暖纸气泡，右对齐、max-w-[88%]、radius 与 padding 不变。**这就是本版相对现行生产的核心改动：气泡不换形状，只换颜色。**
- `CandidateCard`：保留 C 卡结构（撤销 final2 的两处改造）——
  - 卡体 `border-dashed border-gold/60` 金虚线 → `border-line bg-panel` hairline（与 final2 同）；
  - 「候选稿」角标：金胶囊底 → `text-candidate` 文字级（与 final2 同）；
  - 正文**不加** `text-indent: 2em`、**不用** clipped 渐变（撤销 final2 的排印改造），保留 C 的「摘录 + fade 行（全稿 X 字 · 展开查看）」；
  - `ConsistencyNotice` 维持独立组件原位（final2 曾并入卡内一行，撤销）；
  - 采用按钮：`bg-accent shadow-accent` → `bg-accent`（去朱砂投影），按钮内加 `⌘⏎` kbd 提示（新增视觉元素，无逻辑）。
- `TaskCard` / `SettledCard` / `CitationsRow` / `DaySeparator`：与 final2 清单一致（行化、合并、单行召回、天分隔）——C 原型本来就是这个形态，不变。
- steps 展开区、流式光标、`AnimatePresence` 逻辑零改动。

### `writer-composer.tsx`

与 final2 清单一致（去阴影、盒内 kbd 行、发送键 26px 去 `shadow-accent`、note 单行），仅圆角备注：盒 radius 用 `rounded-panel`（原型画的是 8px）。

### 对比度复核（换色后）

气泡文字 ink/paper-deep ≈ 10.9:1；muted、muted-soft、ink-soft 在 paper/panel 上均为现行 token 已验值（≥4.5:1）；`candidate` on `panel` ≈ 5.3:1；panel 白字 on 朱红为现行生产同组合。正文级全部 ≥4.5:1，无兑水灰。

## 3. 迭代记录（4 轮截图自检）

- **v1**：C dock 照搬 + 机械换色 → 问题：召回行折两行、候选稿摘录 3 行，「采用进手稿」被挤出首屏折痕。
- **v2**：召回改名册长度、摘录减 1 行 → 不足，「李玉春」仍断行，足部仍藏 ~30px。
- **v3**：召回压到一行、第三轮气泡压一行 → 摘录实际渲染 3 行（引号占位），足部仍差 ~35px。
- **v4 = 定稿**：三条气泡均改一行短句（与 C 终版同形）、摘录严格 2 行 → 采用按钮带 ⌘⏎ 完整落入首屏，dock 全程无滚动溢出；放大复检密度、气泡底色（paper-deep）、朱红用量（仅两处实心）全部达标。
