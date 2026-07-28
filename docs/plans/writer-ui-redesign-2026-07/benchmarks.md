# 写作台重设计 · 大厂基准研究（benchmarks）

> 目的：把一线产品的设计语言提炼成 **token 级、可直接照抄** 的结论，为写作台
> （Writer 工作台，manuscript-primary + conversation-first IA）的 UI 重设计提供基准。
> 本文只做研究，不出原型；落地方案另行产出。
>
> 现状基线：`apps/web/app/globals.css`（"paper & vermilion"：暖纸色 `#f7f2e9` + 朱红
> `#8f211b` + 墨色 `#171a1b`，字阶 8 档 + 阅读档 17px/1.85，圆角 6/10/14，动效
> 160/220/280ms + `cubic-bezier(0.22,1,0.36,1)`）。
>
> 方法：官方设计系统文档 + 官方博客 + 社区 token 测量（Refero Styles、DESIGN.md
> 社区档案）。凡是社区测量值都标注了"测量"，官方值标注"官方"。

---

## 1. Linear

官方博客：[How we redesigned the Linear UI (part Ⅱ)](https://linear.app/blog/how-we-redesigned-the-linear-ui)；
token 测量：[Linear — Refero Styles](https://styles.refero.design/style/90ce5883-bb24-4466-93f7-801cd617b0d1)。

- **色板策略**：单色中性阶 10 级（暗主题 `#08090a → #0f1011 → #161718 → #23252a`
  四级表面 + 灰阶文字 `#62666d / #8a8f98 / #d0d6e0 / #ffffff`）。**整个系统只有一个
  彩色 accent**（品牌酸橙 `#e4f222`），规定"每屏只允许一个彩色 CTA，永远不做装饰"。
  状态色（绿/红/紫/蓝紫）只出现在徽章填充，绝不升级为主色。
- **边框 vs 阴影分工**：**发丝线承担几乎全部层次**——0.5px `#23252a` 边框 +
  `inset 0 0 0 1px` 内描边是表面分隔的唯一手段；静态卡片**零投影**，阴影只给
  CTA 按钮的内叠层和浮层（`rgba(8,9,10,0.6) 0 4px 32px`）。官方博客原话是"reduce
  visual noise, maintain visual alignment"。
- **字阶与行高**：Inter Variable，**字重封顶 590，禁 700 粗体**（300/400/510/590 四档）；
  UI 正文 13–16px、lh 1.5–1.6；48px 以上标题一律 `-0.022em` 负字距，lh 压到 1.0–1.13。
  等宽（Berkeley Mono）只给 issue ID、快捷键这类"技术元数据"。
- **间距体系**：4px 基元，档位 `4/8/12/16/20/24/28/32/40/48/64/96/128`；
  元素间距 8、卡片内边距 24、段落带 96 的节奏梯子。
- **圆角**：词汇表极小：2/4/6/12 + pill。徽章 4、按钮/输入 6、卡片 12，**卡片上限 12px**。
- **动效**：官方没有公开时长表；工程文化上以"快"为设计目标（乐观更新、预取、60fps），
  微交互实测是 100–200ms 级短促位移，绝不用弹性晃动。
- **信息密度**：紧凑（compact）。重设计三大目标之一就是"increase the hierarchy and
  **density** of navigation elements"；产品内提供 Comfortable/Compact 两档显示密度。
  做法特征：**字号不降（13px 到底），只压缩留白和行高**。
- **让它"显贵"的 3 个细节**：
  1. **克制到只有一个彩色按钮**——每屏唯一酸橙 CTA，其余全部中性；
  2. **发丝线 + 内描边代替阴影**——层次靠几何而非投影，"精密仪器"感；
  3. **字重纪律**——标题用 510/590 而非 700，配负字距，大字不笨重。

## 2. Vercel Geist

官方：[Geist Design System](https://vercel.com/geist/introduction)、
[Geist Colors](https://vercel.com/geist/colors)；
测量分析：[Vercel Design System Breakdown (SeedFlip)](https://seedflip.co/blog/vercel-design-system)、
[Vercel DESIGN.md 摘要 (shadcn.io)](https://www.shadcn.io/design/vercel)。

- **色板策略**：**10 级色阶 + 每级有明确语义分工**（这是 Geist 最值得抄的一条）：
  2 个页面背景（Background 1 默认 / 2 备用）＋每色阶 10 级，其中
  **1–3 组件背景（默认/hover/active）、4–6 边框（默认/hover/active）、
  7–8 高对比背景、9–10 文字与图标（次级/主级）**。语义即编号，设计师无法乱取色。
  黑白即品牌：`#fafafa` 纸面 + `#171717` 墨，accent 用量趋近于零。
  同源的 Radix Colors 12 级分工（[官方](https://www.radix-ui.com/colors/docs/overview/aliasing)）：
  `1–2 背景 / 3–5 交互背景 / 6–8 边框 / 9–10 实心 / 11–12 文字`，并保证任意
  "11/12 号文字 on 1–5 号背景"对比度达标。
- **边框 vs 阴影分工**：hairline `#eaeaea` 承担分隔；阴影极少且极淡，
  层级主要靠"灰阶编号差"而不是投影深度。
- **字阶与行高**：自建 Geist Sans / Geist Mono 两款字体——**字体本身就是品牌资产**。
  刻度 12/14/16/18/24/32/48/64，正文 16px/lh1.5–1.6，展示字 `-0.04em` 负字距、lh 1.05–1.15。
- **间距体系**：8px 基元；"blueprint grid" 装饰网格透明度 10–20%、8/16px 步进
  （[参考](https://www.setproduct.com/blog/complete-guide-to-blueprint-grid-design)）。
- **圆角**：小圆角系（4–8px 为主），几何感优先。
- **动效**：弹簧感短动画（spring-based），官方图标库而非 emoji。
- **信息密度**：中等偏高；营销页则刻意低密度、单焦点。
- **让它"显贵"的 3 个细节**：
  1. **色阶编号 = 语义**——1–3 背景 / 4–6 边框 / 9–10 文字，取色零自由度；
  2. **自建字体锁定品牌**——换字体=换品牌，反过来说系统内字体不可替换；
  3. **黑白双值反转**（同一块 `#171717` 既是文字也是 CTA），不需要第二个品牌色。

## 3. Notion

测量：[Notion — Design System Analysis (getdesignsystem)](https://www.getdesignsystem.io/catalog/notion)、
[Notion DESIGN.md (shadcn.io)](https://www.shadcn.io/design/notion)。

- **色板策略**：纸白画布 + 暖墨 `#37352f`（不是纯黑）+ 极浅暖灰表面 `#f6f5f4`。
  产品内几乎单彩色：链接蓝、状态色都在低饱和档；营销侧则把紫 `#5645d4` 严格锁给
  唯一 CTA。**品牌色不进正文区**。
- **边框 vs 阴影分工**：Notion 应用内的看家本领是 **"零边框、靠留白分组"**——卡片
  之间没有线，分组靠 8–24px 的空白差和 hover 时才出现的浅灰底
  （社区测量 hover `rgba(55,53,47,0.04–0.08)`）；边框只在 hover/focus/选中态以
  `rgba(55,53,47,0.09–0.16)` 发丝线现身。营销侧给工作区 mockup 用 24px 弥散投影——
  **阴影只给"浮在纸上的内容"**。
- **字阶与行高**：正文 **16px / lh 1.5–1.6 / 400**，标题靠字重+尺寸两级差拉开，
  全系统不用斜体级联。营销侧 80px→11px 共 17 档，产品侧实际只用 4–5 档。
- **间距体系**：4px 基元；内容列宽（measure）约 **700px**——长文阅读的行宽纪律。
- **圆角**：4–8px（矩形按钮 8px，"editorial 直角感"是刻意的）；卡片 12px。
- **动效**：hover 底色 100–150ms 淡入；块操作即时反馈、无位移动画。
- **信息密度**：中等；**写作区低密度**（页面两侧大量留白、工具栏 hover 才出现），
  数据库区高密度，两种密度在同一个产品里分区共存。
- **让它"显贵"的 3 个细节**：
  1. **暖墨 `#37352f` 而非 `#000`**——长读不刺眼，"纸上印字"而非"屏幕发光"；
  2. **hover 显现 chrome**——静态时页面只有文字，工具/边框/把手悬停才出现；
  3. **留白代替分隔线**——分组靠空白节奏，整个编辑器找不到一根多余的分隔线。

## 4. Cursor

测量：[Cursor DESIGN.md (designmd.co)](https://www.designmd.co/d/cursor)。

- **色板策略**：**暖奶油画布 `#f7f7f4`**（和我们的 paper 几乎同色！）+ 暖墨
  `#26251e` + 三级文字灰 `#5a5852 / #807d72 / #a09c92`。单一品牌橙 `#f54e00`
  只给 CTA 和 wordmark。最妙的是 **pastel 时间线色板（peach/mint/blue/lavender/gold）
  只出现在 AI 阶段标记**（Thinking/Reading/Editing/Done）——彩色被圈定在
  "AI 行为可视化"这一个语义里。
- **边框 vs 阴影分工**：**三级发丝线** `#e6e5e0 / #efeee8 / #cfcdc4`
  （默认/更弱/更强），卡片 zero shadow、纯 hairline，80px 段落节奏。
- **字阶与行高**：展示与正文同族（CursorGothic），**大字用 400 + 负字距**做
  "杂志感"而不是加粗；**代码面一律 JetBrains Mono**——代码/技术内容占页面一半，
  mono 的使用强度本身就是质感。
- **间距体系**：16px 递增（16/32/48/64/80），段落带 80px。
- **圆角**：未公开完整刻度；产品内实测小圆角（6–10px）。
- **动效**：AI 阶段标记的颜色流转是核心动效语言，短促、无弹跳。
- **信息密度**：中等；营销页低密度单焦点。
- **让它"显贵"的 3 个细节**：
  1. **暖底 + 暖墨 + 暖灰**：整个灰阶带暖色温，和冷灰 SaaS 立刻区分；
  2. **三级发丝线强度**（弱/中/强）让"线"也有了层次；
  3. **彩色有语义边界**：pastel 只标记 AI 状态，品牌橙只做行动——颜色从不"溢出"到装饰。

## 5. Attio

测量：[Attio DESIGN.md 社区提取 (designmd.co)](https://www.designmd.co/d/attio)（社区从线上
CSS 提取，个别值有噪声，仅取可靠项）；定性：[Attio Landing Page (SaaSFrame)](https://www.saasframe.io/examples/attio-landing-page)、
[Linear×Attio 移动 CRM 设计分析](https://salessheets.ai/pt/blog/mobile-crm-linear-attio-design)。

- **色板策略**：近黑墨 `#242629` + 极浅灰发丝 `#eeeff1` + 紫 `#9b69ff` accent。
  记录/对象类型用低饱和彩色 chip（粉彩族），CRM 数据区保持中性。
- **边框 vs 阴影分工**：**"纸卡片"手法**——白卡 + 极淡投影 + 大内边距、**不要可见
  边框**，像纸放在桌面上（[salessheets 描述](https://salessheets.ai/pt/blog/mobile-crm-linear-attio-design)）。
  列表/表格区用 `#eeeff1` 发丝线分行。
- **字阶与行高**：**Tiempos Text（Klim 衬线）做标题 + Inter 做正文**——SaaS 里罕见的
  "衬线标题"阵营（和 Craft 同路），衬线承担品牌气质，sans 承担数据可读性。
- **间距体系**：大留白 + 卡片大 padding（24–32px），信息密度靠"单元格内分行"
  而非压缩留白。
- **圆角**：卡片 10–12px，chip 全圆角。
- **动效**：hover 微浮起 + 颜色过渡，150–250ms。
- **信息密度**：**高密度数据 UI 的教科书**——表格/看板行高紧凑但字号守住 13–14px，
  密度来自行距和留白压缩，不是缩小字号。
- **让它"显贵"的 3 个细节**：
  1. **衬线标题 × sans 数据**的编辑级排版 pairing；
  2. **无边框纸卡片**：层级靠"白 on 浅灰 + 极淡影"，不是描边；
  3. **粉彩 chip 只给"对象类型"一个语义**，整个数据面板的彩色全部来自实体本身。

## 6. Craft

测量：[Craft DESIGN.md (webdesignhot)](https://www.webdesignhot.com/design.md/craft/)——
**和"paper & vermilion"血缘最近的参照系**，token 最完整，强烈建议精读原文。

- **色板策略**：**暖白纸 `#fcf9f7` + 近黑暖墨 `#030302`**（刻意不用 `#000`/`#fff`），
  文字灰阶 `#3a3835 / #5c5a57 / #8a8782` 全部带暖色温；卡片用**纯白 `#ffffff`
  浮在暖纸画布上**形成层级。蓝 `#2563eb` 锁死在产品内（链接/选中/焦点环），
  营销页几乎见不到——"颜色留给干活的软件"。
- **边框 vs 阴影分工**：**发丝线三档透明度**（`rgba(3,3,2,0.05 / 0.09 / 0.16)`，
  分隔/默认/聚焦），静态卡片**零阴影**，阴影只给 hover 和浮层，且**阴影带暖色调**
  `rgba(36,30,24,0.05–0.10)`（不用冷灰影）。"白卡 on 暖纸 + 发丝线"承担 80% 层级。
- **字阶与行高**：**Untitled Serif 标题 / Untitled Sans 正文** pairing；
  66px H1 **用 400 字重、绝不加粗**，负字距 `-0.018em`；正文 **16px / lh 1.6**；
  散文行宽 **680px**。官方原话："bold 会让杂志感塌成普通 SaaS"。
- **间距体系**：4px 基元 `0/4/8/12/16/24/32/48/64/96/128`；卡片 padding 32；
  段落带 96–128。
- **圆角**：`4/8/12/16/24 + pill(9999)`——**圆角是有层级语义的**：chip 4、控件 8–12、
  卡片 16、大壳 24、唯一 CTA 全 pill。
- **动效**：**三档时长 150/240/320ms** + 三条缓动（standard / emphasized / out-soft）；
  hover **只变色、不变形**（无 scale 无 translate）；滚动显现 8px 上浮 320ms 一次性；
  完整 `prefers-reduced-motion` 降级。
- **信息密度**：低-中；"编辑级从容感"靠行高 1.6 和 680px measure 撑住。
- **让它"显贵"的 3 个细节**：
  1. **暖色温贯穿到底**：画布、墨、灰阶、**连阴影都是暖的**——色温一致是"贵"的第一来源；
  2. **400 字重大衬线**：大字不加粗，靠尺寸和负字距出气场；
  3. **对比度全部实测达标**（墨 on 纸 19.7:1，次级 6.6:1），muted 灰被明确标注
     "只能用于大字/元数据"——克制建立在可访问性底线上。

## 7. iA Writer

官方：[In Search of the Perfect Writing Font（Duospace）](https://ia.net/topics/in-search-of-the-perfect-writing-font)、
[Responsive Typography: The Basics](https://ia.net/topics/responsive-typography-the-basics)、
[iA 设计随笔索引](https://ia.net/dictionary/t/typography/)。

- **色板策略**：写作工具里最极端的"无色"：纸白 + 墨，唯一的颜色是**光标蓝**和
  选中色。语法高亮（句法模式）用极低饱和灰阶区分词性。
- **边框 vs 阴影分工**：编辑区**没有任何边框和阴影**——稿纸就是全部 UI；
  chrome（文件库/预览）用系统原生发丝线。
- **字阶与行高**：核心教义是 **"字号由阅读距离决定，不由偏好决定"**——屏幕比书远，
  所以屏幕正文必须比印刷大；行高给足 140%+（屏幕像素涂抹需要更多行距补偿）；
  对比不用纯黑纯白（深灰 on 浅灰更耐看）。为写作节奏专门设计 **Duospace**（m/M/w/W
  给 1.5 倍宽的等宽体，基于 IBM Plex Mono）：等宽让写作"慢下来"、错字可辨、
  进度可视——**字体选择本身是写作体验设计**。
- **间距体系**：最优行宽（measure）是硬约束，随视口做分级断点而非流体拉伸——
  "可读性比"铺满视口"重要"。
- **圆角**：N/A（原生 chrome）。
- **动效**：Focus mode 的段落淡出是唯一"动效"，一次只做一件事。
- **信息密度**：写作时趋零密度（连字号选择都不提供，"防乱调"）。
- **让它"显贵"的 3 个细节**：
  1. **删减即设计**：写作模式下没有设置、没有字体菜单——"唯一能做的事就是写"；
  2. **为写作节奏造字体**：Duospace 的 1.5 倍宽 m/w 是"工具适应内容"而非相反；
  3. **排版决策给出工程学理由**（阅读距离→字号→行高→行宽的推导链），不是审美口号。

## 8. Raycast

测量：[Raycast DESIGN.md (shadcn.io)](https://www.shadcn.io/design/raycast)、
[Raycast DESIGN.md (webdesignhot)](https://www.webdesignhot.com/design.md/raycast/)。

- **色板策略**：**四级表面梯** `#07080a → #0d0d0d → #101111 → #121212` 承担全部层级；
  唯一的 CTA 是**白色 pill**（`#ffffff` 底 + 黑字）——品牌"主色"就是白；
  红-暗红渐变 `#ff5757→#a1131a` 每页最多出现一次。
- **边框 vs 阴影分工**：**全系统零投影**，所有卡片边缘由 1px `#242728` 发丝线承担；
  签名卡片规格：`#0d0d0d` 底 + 1px `#262a2c` 边 + **10px 圆角** + 24px padding，
  hover 仅背景升到 `#18191a`、边升到 16% 白。
- **字阶与行高**：Inter 全站开启 `font-feature-settings "calt","kern","liga","ss03"`——
  **ss03 单双层 g 替换是品牌签名细节**；16 档刻度 64px→12px。
- **间距体系**：8 档刻度含 96px 段落节奏；按钮 6px 圆角。
- **圆角**：`0–16 + 9999`，卡片 10px 是签名值。
- **动效**：命令面板式即时反馈；彩色 badge 用"色相 15% 透明底 + 同色相全饱和字"。
- **信息密度**：高（效率工具），但靠四级表面梯维持秩序。
- **让它"显贵"的 3 个细节**：
  1. **OpenType 特性开关当品牌资产**（ss03）——字体"设置"层面的差异化；
  2. **白色即主色**：不用品牌色也能建立识别度，靠形状（pill）+ 对比；
  3. **徽章配色公式**（15% 色相底 + 全饱和同色相字）让所有状态色统一、
     永远"系统感"而非装饰感。

## 9. 飞书文档（Lark）

官方：[飞书设计语言 · 字体](https://open.feishu.cn/document/design-specification/design-language/font?lang=zh-CN)。

- **色板策略**：**四级灰阶官方定义**：主标题/一级正文 `#1F2329`、副标题/二级正文
  `#646A73`、placeholder/次要 `#8F959E`、disable `#BBBFC4`——**文字灰阶只有 4 级，
  每级有明确语义岗位**。品牌蓝 `#1456F0` 限定链接/按钮文字/选中态。
- **边框 vs 阴影分工**：文档区发丝灰线 + hover 灰底；编辑器**画布本身无线无影**。
- **字阶与行高**：官方规定**字号-行高配对表**（"行高决定留白空间，须严格按表使用"），
  字重只用 **Regular 400 / Medium 500** 两档，大标题加粗才上 Semibold 600。
  （配对表以图片发布，抓取未能逐行提取；常见档位为 12/13/14/16/20/24/28/32。）
- **间距体系**：组件级规范；文档默认段距由系统给出，**用户不需要也无法调字体字号**
  （官方定位：协作效率优先于文档美化，统一排版降低协作摩擦）。
- **圆角**：中圆角（6–8px）工具化风格。
- **动效**：短促 150–200ms。
- **信息密度**：工具区高密度（套件），文档区中密度；工具栏 hover/选中才浮现。
- **让它"显贵"的 3 个细节**：
  1. **灰阶 4 级配岗**：颜色变量数量被制度性压缩，杜绝"第 5 种灰"；
  2. **字重只有 400/500**（大标题 600）——中文粗体过粗的问题用 Medium 解决；
  3. **排版权收归系统**：用户不可调字号，换来全域一致的排版下限。

## 10. 腾讯文档

官方：[腾讯文档全平台系统设计（ISUX）](https://isux.tencent.com/articles/multiplatform.html)、
[腾讯文档品牌设定（ISUX）](https://juejin.cn/post/6844903598229291022)。

- **核心原则**：**"感知一致性，各端效益最大化"**——不追求各端界面一致，而追求
  品牌感知一致（主色、字体、icon 风格、语言语调），布局按设备姿态分化：
  移动端**降噪 + 加强对比**完成单任务；桌面端"**安静地展示更多常用功能**"，
  一个视图完成复杂任务。
- **色板策略**：品牌蓝主色 + 中性灰；文档列表/编辑器以白为主，类型 icon 用彩色
  （蓝 doc / 绿 sheet / 橙 slide）承担文件类型语义。
- **字阶/间距/圆角**：套件化实用主义；编辑器行宽自适应，标题层级预置。
- **动效**：跨端响应以"宽松/紧凑两种基础布局"组合（借鉴 iOS Size Classes），
  菜单在紧凑布局变蒙层抽屉、宽松布局变浮层——**容器形态随布局切换**。
- **信息密度**：桌面高、移动低，**密度是平台姿态的函数**。
- **让它"显贵"的 3 个细节**：
  1. **彩色只给"类型"**：文件类型色是唯一稳定的彩色语义；
  2. **"安静地展示更多功能"**的桌面哲学——功能在场但不喧哗；
  3. 一致性落在**感知层**（品牌/语调/图标风格）而非像素层，多设备体验统一。

## 11. 语雀

官方演讲：[语雀编辑器自研之路（遇春，语雀大会）](https://juejin.cn/post/7036551063498915877)；
排版优化：[语雀新功能 · 排版优化](https://zhuanlan.zhihu.com/p/515599336)。

- **设计目标**（官方原话）："打开语雀编辑器时，**沉浸在一种平静而愉悦的创作心流**"——
  写周报、写小说、写游记都是享受。与我们的写作台定位几乎同构。
- **色板策略**：墨绿品牌色（玉色）+ 纸白文档画布 + 中性灰 chrome；编辑器区无彩色。
- **排版**：2022 排版优化的核心是 **"默认段间距，不再手动空行"**——段落间距由系统
  给足"呼吸感"，标题层级预置默认间距；行高宽松，正文灰黑而非纯黑。
- **边框 vs 阴影**：文档卡片浮在浅灰知识库底上（白 on 浅灰），编辑器内部无分隔线；
  目录/侧边栏用发丝线。
- **信息密度**：编辑器低、知识库管理界面中。
- **让它"显贵"的 3 个细节**：
  1. **段距默认化**——把"手动敲空行"这个全民坏习惯用系统默认排版消灭；
  2. **平静感来自留白**：编辑器首屏几乎只有标题和正文，所有工具收敛到选中/斜杠唤起；
  3. **品牌色极少量**（玉色只出现在标识与主按钮），编辑器主体无品牌色干扰。

---

## 横向对比表

| 产品 | 中性色阶 | accent 用量 | 边框/阴影分工 | 字阶·行高 | 间距基元 | 圆角 | 动效 | 密度 | 最值得抄的一点 |
|---|---|---|---|---|---|---|---|---|---|
| Linear | 10 级（暗） | 每屏 1 个彩色 CTA | 发丝线+内描边承担层次，静态零影 | 13–16px / 1.5–1.6；字重 ≤590，大标题负字距 | 4px | 2/4/6/12+pill | 100–200ms 短促 | 紧凑（可切换两档） | 单 accent + 发丝线层次 |
| Vercel Geist | 10 级×语义编号（1–3 底/4–6 边/9–10 字） | 趋零，黑白即品牌 | hairline，层级靠编号差 | 12–64px，16px/1.5–1.6，展示 -0.04em | 8px | 4–8 | spring 短动画 | 中-高 | 色阶编号=语义分工 |
| Notion | 纸白+暖墨 `#37352f`+浅暖灰 | 产品内近零，营销锁 1 CTA | **留白代替线**；hover 才出线/底 | 16px / 1.5–1.6；measure ~700px | 4px | 4/8/12 | 100–150ms 淡入 | 分区双密度 | hover 显现 chrome |
| Cursor | 暖奶油 `#f7f7f4`+暖墨+3 级暖灰 | 橙锁 CTA；pastel 只标记 AI 阶段 | **三级发丝线强度**；零影 | 大字 400+负字距；mono 占半页 | 16px | 6–10（实测） | 短促无弹跳 | 中 | 彩色有语义边界 |
| Attio | 近黑 `#242629`+`#eeeff1` | 紫 accent + 粉彩 chip 给对象类型 | **无边框纸卡**：白卡+极淡影 | 衬线标题×Inter 正文 | 4px（推定） | 10–12+pill | 150–250ms 微浮 | 高（行距压缩，不降字号） | 数据密度靠行距不靠字号 |
| Craft | 暖纸 `#fcf9f7`+暖墨 `#030302`+暖灰 | 蓝锁产品内；营销近单色 | **发丝线 3 档透明度**；暖调影只给 hover/浮层 | Serif 66px@400 不加粗；16px/**1.6**；measure 680 | 4px（至 128） | 4/8/12/16/24+pill | **150/240/320ms 三档**，hover 只变色 | 低-中 | 色温一致（连阴影都是暖的） |
| iA Writer | 纸+墨，光标蓝唯一彩色 | 趋零 | 编辑区无线无影 | **字号由阅读距离决定**；行高 ≥140% | measure 硬约束 | 原生 | 仅 Focus 淡出 | 写作时趋零 | 删减即设计 |
| Raycast | 4 级表面梯（暗） | **白色即主色**；渐变每页≤1 次 | **全系统零投影**，1px 发丝线 | Inter+ss03；16 档 | 8px | 0–16+pill（卡 10） | 即时反馈 | 高 | 徽章 15% 色相底公式 |
| 飞书文档 | **官方 4 级灰阶配岗** | 蓝 `#1456F0` 锁链接/按钮/选中 | 发丝线+hover 底；画布无线 | 字号-行高官方配对表；**字重仅 400/500**（大标题 600） | 组件级 | 6–8 | 150–200ms | 分区 | 灰阶制度性压缩 |
| 腾讯文档 | 白+中性灰 | 品牌蓝+文件类型色 | 发丝线 | 预置标题层级 | 响应式两档布局 | 中圆角 | 容器形态随布局切换 | 随平台姿态 | 密度是平台姿态的函数 |
| 语雀 | 纸白+灰黑 | 玉色极少量 | 白卡 on 浅灰底 | 默认段距、行高宽松 | 系统默认排版 | 中圆角 | 收敛 | 编辑器低 | **段距默认化消灭空行** |

## 对一个中文长文写作工具最值得借的 10 条

1. **给中性色阶"配岗"，而不是配颜色**（Geist/Radix）：背景 1–3、边框 4–6、文字 11–12
   的语义编号制度，落到我们的 token 就是把 `paper/panel/line/muted` 的分工写成
   "第几档干什么"的硬规则，消灭"随手再加一种灰"。
2. **发丝线承担结构、阴影只给浮层，且阴影必须带纸的色温**（Linear/Raycast/Craft）：
   静态卡片零投影；hover/浮层才出影；阴影色用暖墨基（如 `rgba(86,69,45,…)`），
   绝不用冷灰影砸在暖纸上。
3. **朱红每屏只做一件事**（Linear 单 CTA 纪律）：主按钮、选中、focus ring 共享一个
   accent，且每屏只有一个实心朱红元件；候选稿金色、状态绿红都降级为"徽章公式"
   （Raycast：色相 12–15% 底 + 同色相深字）。
4. **字重纪律：标题用 500/600，禁用 700，大字配负字距**（Linear/Craft/飞书）：
   中文尤其——大标题加粗 700 会糊成块，400/500 大字 + 紧凑字距才是"编辑级"。
   中文无斜体的约束我们已有（`:lang(zh) em`），保持。
5. **阅读区字号宁大勿小：16–17px、行高 1.7–1.85，行宽 680–720px**（iA/Craft/Notion）：
   我们的 `text-reading: 17px/1.85` 方向已被基准验证；补上的是把 **measure 写成
   token**（稿纸列宽上限），任何屏幕尺寸都不允许正文行拉满。
6. **三级文字灰阶写死对比度**（飞书/Craft）：`ink / body / muted` 三级，
   muted 直接给 ≥4.5:1 的实色（我们已有 `#5a5146/#6f6559`，正确），并明文规定
   更浅的灰"只能用于 ≥14px 大字或图形内标签"，禁止透明度合成次级文字。
7. **圆角词汇表 ≤4 档且带层级语义**（Craft）：chip 4、控件 6–8、面板 10–12、
   模态 14–16；全系统不允许出现词汇表外的圆角。我们现状 6/10/14 三档已符合，
   需要的是把"哪档给什么"写进规范并审计现有组件。
8. **动效三档时长 + 一条缓动曲线，hover 只变色不变形**（Craft 150/240/320）：
   我们的 160/220/280 + `cubic-bezier(0.22,1,0.36,1)` 已经同构；要砍的是散落的
   scale/translate hover（asset-tile 的 -3px 浮起属展示组件特例，工作台 chrome
   应纯色彩过渡）。
9. **密度靠压缩留白与行距，不靠缩字号**（Linear/Attio/Adobe 做法）：工具区（Agent
   dock/thread/候选卡）用 13–14px + 紧凑行距做到 Linear 级密度；稿纸区保持 17px
   低密度——**双密度分区共存**是写作台的正确答案，全域统一密度是错误答案。
10. **中文编辑器体验三件套**（语雀/飞书/腾讯）：① 段距默认化，消灭"手动空行"；
    ② 排版权收归系统（写作台不给字号/字体调节，或只给"排版主题"档位）；③ 工具
    chrome 静态时退场——hover/选中才浮现，稿纸区域静态下只有字。

## 与现状 `globals.css` 的差距速查

- **已达标**：暖纸+暖墨+朱红的色温一致性（Craft 同源）；`text-reading 17/1.85`；
  圆角三档；动效三档+单一缓动；muted 双档对比度修复；`:lang(zh)` 斜体禁用。
- **待补**（供方案阶段立项）：
  ① 中性阶语义配岗文档化（第 1 条）；
  ② 阴影全面改暖调 + 静态卡片去影审计（第 2 条）；
  ③ accent 用量审计——一屏内多个朱红实心按钮的现状（截图中"开始第一章×2/继续"
  同框）违反单 CTA 纪律（第 3 条）；
  ④ measure token（稿纸列宽）缺失（第 5 条）；
  ⑤ 工具区 13px 紧凑密度档位缺规范（第 9 条）；
  ⑥ 徽章"色相底公式"未统一（gold/green/red 各自手调 wash）（第 3 条）；
  ⑦ 段距默认化与 chrome hover 显现的交互规范（第 10 条）。

## 来源清单

- Linear：[How we redesigned the Linear UI (part Ⅱ)](https://linear.app/blog/how-we-redesigned-the-linear-ui)（官方）｜[Linear — Refero Styles](https://styles.refero.design/style/90ce5883-bb24-4466-93f7-801cd617b0d1)（测量）
- Vercel：[Geist Introduction](https://vercel.com/geist/introduction)｜[Geist Colors](https://vercel.com/geist/colors)（官方）｜[SeedFlip 分析](https://seedflip.co/blog/vercel-design-system)｜[Radix Colors 语义别名](https://www.radix-ui.com/colors/docs/overview/aliasing)（官方）
- Notion：[getdesignsystem 分析](https://www.getdesignsystem.io/catalog/notion)｜[shadcn.io DESIGN.md](https://www.shadcn.io/design/notion)（均为测量）
- Cursor：[designmd.co/d/cursor](https://www.designmd.co/d/cursor)（测量）
- Attio：[designmd.co/d/attio](https://www.designmd.co/d/attio)（社区提取，个别值有噪声）｜[SaaSFrame landing 分析](https://www.saasframe.io/examples/attio-landing-page)｜[salessheets 设计分析](https://salessheets.ai/pt/blog/mobile-crm-linear-attio-design)
- Craft：[webdesignhot DESIGN.md](https://www.webdesignhot.com/design.md/craft/)（测量，token 最完整）
- iA Writer：[Duospace 官方博客](https://ia.net/topics/in-search-of-the-perfect-writing-font)｜[Responsive Typography: The Basics](https://ia.net/topics/responsive-typography-the-basics)（官方）
- Raycast：[shadcn.io DESIGN.md](https://www.shadcn.io/design/raycast)｜[webdesignhot DESIGN.md](https://www.webdesignhot.com/design.md/raycast/)（测量）
- 飞书：[飞书设计语言 · 字体](https://open.feishu.cn/document/design-specification/design-language/font?lang=zh-CN)（官方）
- 腾讯文档：[全平台系统设计（ISUX）](https://isux.tencent.com/articles/multiplatform.html)｜[品牌设定](https://juejin.cn/post/6844903598229291022)（官方）
- 语雀：[编辑器自研之路](https://juejin.cn/post/7036551063498915877)（官方演讲）｜[排版优化](https://zhuanlan.zhihu.com/p/515599336)
