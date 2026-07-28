# 写作台 UI  redesign 研究总览（2026-07-27）

起因：用户对写作台整屏不满意（截图 `ScreenShot_2026-07-27_235635_952.png`），认为缺少顶级大厂质感、布局不美观优雅。本目录是研究交付：**2 份分析 + 4 个设计方案（各带可打开的静态原型）**。尚未改动 `apps/web` 任何代码，选定方向后再实施。

## 快速查看

```bash
open docs/plans/writer-ui-redesign-2026-07/prototype-a.html   # A 纸墨精进化
open docs/plans/writer-ui-redesign-2026-07/prototype-b.html   # B 文学编辑部
open docs/plans/writer-ui-redesign-2026-07/prototype-c.html   # C 现代极简工作室
open docs/plans/writer-ui-redesign-2026-07/prototype-d.html   # D 布局与 IA 重构（可交互：视图切换/专注模式/⌘K）
```

定稿截图：`prototype-a.png`、`prototype-b.png`、`prototype-c.png`、`shots/d-*.png`。

## 文件清单

| 文件 | 内容 |
| --- | --- |
| `diagnosis.md` | 现状诊断：21 条问题精确到 文件:行，含 P0–P2 优先级矩阵 |
| `benchmarks.md` | 11 个一线产品（Linear/Geist/Notion/Cursor/Attio/Craft/iA/Raycast/飞书/腾讯文档/语雀）token 级拆解 + 横向对比 + 最值得借的 10 条 |
| `proposal-a-paper-refined.md` + `prototype-a.html` | 方案 A：保留暖纸朱红识别，做纪律精进化 |
| `proposal-b-editorial.md` + `prototype-b.html` | 方案 B：文学杂志编辑室，排印主导 |
| `proposal-c-minimal-studio.md` + `prototype-c.html` | 方案 C：Linear/Attio 式中性极简 + 黛蓝 accent |
| `proposal-d-layout-ia.md` + `prototype-d.html` | 方案 D：骨架重构（dock 右移、画布工具行、专注模式、⌘K），肤色不变 |

## 诊断共识（四个方案独立得出、高度一致）

1. **视觉重量押错地方**：用户气泡是实心朱红大色块（`writer-rail.tsx:187`），与发送钮/采用钮同形同色同投影——「说过的话」和「主操作」不分；全屏最素的反而是主角稿纸。
2. **稿纸不像书**：正文错用 `text-lg`（18px/1.45），专为阅读定义的 `text-reading`（17px/1.85）无人使用；裸渲染 Markdown `# 第一章`；空段画出一个带边框的「输入框」（截图红框），根因是 baseline focus ring 未入 cascade layer（`globals.css:237`）。
3. **卡片套卡片**：dock 里一次交互叠 4 层描边矩形 + 8–10 个带框 chips，实线/淡线/金虚线三种边框语言混用。
4. **结构缺位**：规范承诺的画布头视图切换（稿件/章节/审校/工具）不存在；全屏没有明确 primary；accent 一屏承担 7 种语义（错误态三处直接用 accent，违反自己注释里的禁令）。
5. **基准结论**：「显贵」是纪律问题不是审美问题——Linear 每屏唯一彩色 CTA、Raycast 零投影、Geist 色阶编号即语义；暖纸体系的高分答卷是 Craft（暖纸+暖墨+三档发丝线+暖调阴影），可直接移植。

## 四个方案怎么选

- **A 纸墨精进化**：风险最低、落地最快（S 级半天纯样式）。气泡改纸面+朱丝描边、层级靠三层明度不靠投影、稿纸书版化（居中章题/2em 缩进/纸纤维颗粒）。**适合：不想换性格，只要「干净高级」。**
- **B 文学编辑部**：性格最强。稿纸=版心、thread=批条工单、候选稿=排样小样、页边注+running head+印章起字。**适合：想让产品有一眼可辨的文学气质。**
- **C 现代极简工作室**：最像「顶级大厂 SaaS」。暖灰中性色 + 黛蓝 `#3a49be` 单 accent + hairline + kbd/⌘K 文化 + 深色选区浮动工具条。**适合：想要 Linear/Attio 那种工具感，接受文学辨识度下降。**
- **D 布局与 IA 重构**：动骨架不动肤色。dock 右移 360px（对齐 AGENTS.md 契约，现行代码在左）、画布工具行 + 居中 segmented 视图切换、专注模式（dock 收成右缘 48px 专注条）、候选稿升舱为第二主角、悬浮物归宿立规、修 <1200px dock 整体消失的 IA 塌陷。**与 A/B/C 任一可叠加。**

## 推荐路线（综合意见）

**D（骨架）+ A（肤色）为基底，从 C 借三件**：深色选区浮动工具条、kbd/⌘K、segmented 控件纪律。即：布局按 D 重构，视觉按 A 精进，交互细节向 C 看齐。若你更想要强个性，把 A 换成 B；若你更想要大厂工具感，把 A 换成 C（代价是稿纸感）。

各方案均已给出 token 草案、组件级改动清单与 P0/P1/P2 落地分期；A/C/D 的 P0 都是纯样式/布局、零数据流改动，可先落地看整屏效果。

## 收敛：B2 净版（用户反馈后的最终方向，2026-07-28）

用户反馈：A 的 dock 太杂乱；B 喜欢但左侧线条太多；C 因整体换色与其他工作台不一致被否。据此收敛出 **B2 净版**：

- `prototype-final.html` / `prototype-final.png`（`open` 即可查看）——B 的编辑部稿纸原样保留，dock 重构为纯排印 thread
- `proposal-final-b2.md`——线条预算 7 条、dock 组件差异表

要点：色板不动（paper & vermilion，全站一致）；dock 内容区只剩 3 条线（active tab 朱红下划线、天分隔 hairline、候选稿卡一周 hairline 框——dock 唯一容器）；消息无气泡无边框，靠 muted meta 行 + 留白分组；chips 收成一行 muted 小字；已采用记录压成单行；候选稿卡变体对比后选 hairline 框（洗底色团与导航 rail 连成片、抢视线，弃）。

## 终版：B 画布 + C 式 dock（2026-07-28，用户确认方向）

用户对 B2 的 dock 仍不满意（真实密度下 meta 行重复显乱），指定 dock 换成方案 C 的布局样式。终版：

- `prototype-final2.html` / `prototype-final2.png`（`open` 即可查看）
- `proposal-final2.md`——最终形态边界、配色映射、组件级改动清单（一期纯皮相零数据流）

要点：**画布** = B 编辑部稿纸原样；**dock** = C 的 Linear 式扁平坦列表（对话/待审 tabs、昨天/今天时间锚、一 run 一行状态记录、steps 默认收起、chips 一行 truncated、候选稿卡、kbd composer），但配色全面纸墨化（朱红 accent 保留，实心朱红全 dock 仅「采用进手稿」+ 发送键两处）；**去重规则**——用户指令无气泡无逐条时间（时间归天分隔线）、状态与「查看正文」合并为一行。

## 终版 v3：C dock 原版 + 纸墨配色（2026-07-28，用户指定）

用户打开 prototype-c 后指定：dock 就要 C 的原版聊天对话界面（含用户消息气泡形态、双状态行、steps、候选稿卡 ⌘⏎、kbd composer），颜色与全项目一致。终版以此为准：

- `prototype-final3.html` / `prototype-final3.png`（`open` 即可查看）——C dock 逐组件照搬、仅换色（黛蓝→朱红仅 4 处、用户气泡 paper-deep、候选稿 tag 用金色文字）；画布 = B 编辑部稿纸；顶栏/图标轨纸墨化
- `proposal-final3.md`——逐组件配色映射表 + 相对 apps/web 的组件级改动清单（标注了相对 final2 撤销的删减项，可直接执行）

此前 final2 的「用户指令无气泡、run 合并单行」等去重规则被用户否掉，以 final3 为准。
