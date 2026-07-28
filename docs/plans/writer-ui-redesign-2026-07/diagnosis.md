# 写作台视觉诊断 —— 为什么现在不像大厂产品

日期：2026-07-27
基线截图：`~/Downloads/ScreenShot_2026-07-27_235635_952.png`（用户已用红框标出两处最刺眼区域：整个 dock、稿纸顶部的占位框）
范围：`apps/web/app/projects/[projectId]/writer/*`、项目壳 `layout.tsx` / `workbench-nav-rail.tsx`、`apps/web/app/globals.css`、`apps/web/components/workbench-masthead.tsx`，对照 `docs/refactor-saas/04-design-system-and-ui.md`（下称「规范」）逐条核对。

---

## 0. 一页总览

1. **视觉重量全部押错地方。** 整屏最重的元素依次是：朱红印章 logo 方块、纯黑圆形头像、两条实心朱红用户气泡（「开始第一章」「继续」）。主角——手稿——反而是全屏最素的一块。用户把气泡误认为「悬浮按钮」，这个误读本身就是诊断结论：系统里「我说过的话」和「我能做的主操作」同形同色同投影。
2. **卡片套卡片、边框没有纪律。** dock 里一次完整交互最多叠 4 层描边矩形（TaskCard / SettledCard / CandidateCard 虚线框 / 8–10 个带框 chips），全部浮在 dock 自身的底上；规范明文「卡片只用于重复 item、详情 panel、modal」「Primary panel 优先使用分隔线而不是投影」（04:168, 232），现状逐字违反。
3. **稿纸自己背叛了纸的隐喻。** 点击任意段落会画出矩形朱红描边（截图红框 2 的「带边框占位框」），手稿正文用的是 `text-lg`（18px/1.45）而不是专门为它定义的 `text-reading`（17px/1.85），组件注释还自称「generous 1.9 line-height」——注释、token、实现三方脱节。
4. **色彩纪律双向失守。** accent 在一屏内同时承担 7 种语义（品牌 / 主操作 / 导航选中 / 链接 / 错误 / 进行中 / 焦点），其中「错误」直接违反 globals.css 自己写下的注释禁令；而画布——产品主角——几乎零色彩，朱红在 dock 里泛滥、在稿纸上缺席。
5. **结构性的「无家可归」。** 规范与 AGENTS.md 承诺的画布头视图切换（稿件 / 章节 / 审校 / 工具）在代码里不存在，写作台唯一结构操作「新章节」只是顶栏最右一颗 caption 级描边小按钮；审校、工具没有入口，主操作没有主操作位。

做对了、不应推倒的：稿纸浮于纸面（`bg-panel` + `shadow-panel`）的基本隐喻成立；保存状态机诚实（dirty→saving→saved/conflict）；settled 卡保留召回 chips 与「查看正文」回溯的设计意图正确；token 体系本身是克制的。问题集中在**渲染层对 token 的使用方式**，不在 token 本身。

---

## 1. 截图证据基线

用户红框 1（整个 dock）：从上到下可见 —— 「合著者」头 + 带框「待审资产 →」按钮；两条实心朱红圆角矩形用户消息（「开始第一章」「继续」）；「已完成 · 候选稿 3510 字」白底描边卡；「已采用 · 3510 字进手稿」描边卡（内部分隔线 + 「已进手稿，可在稿纸上继续改」+ 朱红「查看正文」）；一排带框 chips（一金框 + 六个白框 +「+12」+「·关键词召回」）；白底描边 composer（右侧一颗半透明粉红发送钮）；12px 提示文字折成两行，第二行「行」贴到屏幕底缘。dock 下半部是一整片无内容空白。

用户红框 2（稿纸顶部）：稿纸打开后第一个视觉对象是一个**带朱红矩形边框的空输入框**，里面 18px 占位文字「从这里开始写。空白的稿纸，等第一个字落下。」，光标可见（textarea 处于聚焦态）；紧接着是裸 markdown 字面量「# 第一章」，然后才是正文。

---

## 2. 逐条诊断

### A. 信息层级与视觉重量失衡

**A1. 用户气泡是全屏视觉重量最高的元素，而它只是历史消息。**
`writer-rail.tsx:187` `UserBubble`：`bg-accent px-3.5 py-2.5 rounded-modal text-panel shadow-accent`——实心朱红 + 专属投影 + 大圆角，与主操作按钮完全同构（对比 `writer-composer.tsx:61` 发送钮、`writer-rail.tsx:511` 采用钮：同为 `bg-accent text-panel shadow-accent`）。截图里「开始第一章」×2 与「继续」三颗气泡是 dock 里仅有的三个重色块，用户因此把它们读成「悬浮的 CTA」。规范要求「每页只突出一个主对象和一个主要动作。红色不作为普通按钮的默认填充色泛滥使用」（04:153, 185）。为什么显不高级：Linear/Notion 的会话流里，用户自己的发言永远用中性底色（浅灰或无底色右对齐），**最饱和的颜色只留给当下可执行的唯一动作**；把已发生的对话涂成主色，等于让过去持续向现在喊叫。

**A2. 两个全局锚点都是重色块，且都与写作对象无关。**
顶栏 logo：`layout.tsx:48-50`，`size-8` 实心朱红方块 `bg-accent shadow-accent`，常驻每一屏左上角；左下头像：纯黑（近 `#171a1b`）圆形「N」。加上 A1 的气泡，全屏饱和度前三名是 logo、头像、历史消息。为什么显不高级：顶级工具的 chrome（Vercel/Linear 的顶栏与头像）全部退成线稿与中性灰，重色只出现在内容区的主操作上；我们的产品把品牌章「盖」在了常驻 UI 上，每屏都在为品牌付视觉税。

**A3. dock 头部：次要入口比标题更醒目，三重信息挤进 48px。**
`composer-review-flip.tsx:65-90` 的「待审资产 →」是 dock 头部唯一带边框的按钮（`border-line bg-panel` + 金色图标块 + 计数药丸 + 箭头），视觉强度压过它服务的标题「合著者」（`writer-rail.tsx:77-84`）；同行的「常驻协作」（:83）是第三个信息层级，12px 灰字孤零零钉在最右。为什么显不高级：一个 48px 的行里塞了「图标+标题+带框按钮+状态 caption」四种元素，且最重的元素指向次要功能——这正是 Notion/Attio 里「inspector 头部只留标题 + 一个 icon button」的反面。

### B. 卡片套卡片 / 边框滥用

**B1. 一次 turn = 最多 4 层描边矩形。**
一次完整的「起草→采用」交互在 thread 里渲染为：`TaskCard`（`writer-rail.tsx:393`，`rounded-modal border border-line bg-panel`）+ `SettledCard`（:544，`rounded-modal border border-line-soft/80 bg-panel/60`）+ `CitationsRow` 的 8–10 个带框 chips（:356-362，`rounded-full border`）+（采用前）`CandidateCard`（:488，`border border-dashed border-gold/60`）。这些全部叠在 dock 自身的 `bg-paper/40` + `border-r`（`writer-workspace.tsx:612`）底上，而 dock 里又嵌着 `bg-panel` 的 composer 框（`writer-composer.tsx:39`）。截图红框 1 里能数出 6 个矩形 + 9 个药丸框。规范：「卡片只用于重复 item、详情 panel、modal，不把整页套进大卡片」「优先使用分隔线而不是投影」（04:232, 168）。为什么显不高级：thread 是线性时间流，每张卡都在声明「我是一个独立窗口」，结果是界面由框构成而不是由内容构成——这是「表单后台」气质的直接来源。

**B2. 三种边框语言混用，没有语义分工。**
实线 `border-line`（TaskCard）、淡实线 `border-line-soft/80`（SettledCard）、金色虚线 `border-dashed border-gold/60`（CandidateCard，外加左上角 `-top-2` 的「候选稿」角标，`writer-rail.tsx:491`）——虚线+角标是「优惠券/便签」语言，实线框是「窗口」语言，两者在相距 16px 的相邻位置出现。为什么显不高级：大厂系统里边框样式与语义一一对应（虚线=拖放目标/占位，实线=容器），混用会让用户潜意识里无法建立模式预期。

**B3. composer 是框中框中框，还背着主角级投影。**
`writer-composer.tsx:39`：composer 是 `rounded-modal border border-line bg-panel shadow-panel` 的大框，嵌在 dock（自身有右边框）里，框里再嵌 textarea。`shadow-panel`（`globals.css:123`，20px/50px 投影）在 token 注释里是浮起面板用的——它和稿纸（`manuscript-paper.tsx:38`）用的是**同一档投影**，于是「常驻输入框」与「产品主角」在 elevation 上平级。为什么显不高级：elevation 是层级语言，同档影子=同级重要；Cursor/Vercel 的 composer 要么无边框、要么只有顶部分隔线，从不给输入框施主角级投影。

### C. 按钮没有归宿

**C1. 「开始第一章」「继续」的误读 = 气泡与按钮同形（见 A1），此处只补一句：修复方向不是给气泡加说明，而是让气泡不再是按钮的形状。**

**C2. 真正的主操作没有主操作位。**
「新章节」（`writer-canvas-top.tsx:60-68`）是写作台唯一的常驻结构操作，样式却是 `text-caption`（12px）描边小按钮，缩在顶栏最右，视觉重量远低于 dock 里任何一颗用户气泡。规范说「每个页面可见区域最多一个 primary action」（04:456）——现状执行成了「零个明确的 primary」。为什么显不高级：primary 缺失不等于克制，等于放弃引导；作者进入写作台后视线扫过全屏，找不到「系统希望我下一步做什么」。

**C3. 「查看正文」把 accent 花在导航链接上，且逐卡重复。**
`writer-rail.tsx:576-583`：每张 settled 卡右下都有一颗朱红文字按钮「查看正文」。导航性回溯链接用主操作色，进一步稀释 accent 的语义（见 H1）。

**C4. 视图切换整体缺席——「审校」「工具」无家可归。**
规范（04:400）与 AGENTS.md 的 IA 都写明画布头有「稿件 / 章节 / 审校 / 工具」互斥标签；`writer-canvas-top.tsx` 全文只有章节切换器、字数、保存态、新章节，没有任何视图切换。审校（reviewer）与工具在当前实现里不存在入口。为什么显不高级：这不仅是缺功能，更是顶栏「左侧拥挤、右侧空荡」失衡的根因——顶栏信息架构缺了一根承重柱。

### D. 间距与对齐不成体系

**D1. dock 内部 padding 五世同堂，左右边缘互不对齐。**
thread 容器 `px-4 py-4`（`writer-rail.tsx:139`）、TaskCard 内 `px-3.5 py-3`（:394）、SettledCard 内 `px-4 py-3`（:544）、CandidateCard 内 `px-4 py-3.5`（:488）、CitationsRow `px-0.5`（:340）、composer 外 `p-3`（`writer-composer.tsx:38`）。3 / 3.5 / 4 / 0.5 混用；截图里可验证：chips 行的左缘（`px-0.5`）比 TaskCard 左缘（`px-3.5`）内缩不一，composer 框（`p-3`）与 thread 内容（`px-4`）错开 4px。为什么显不高级：大厂界面「贵」的感觉 80% 来自不可见网格的严格执行——所有左缘对齐同一根线；差 4px 人眼说不出，但「哪里不对」的感觉就是这么来的。

**D2. 三套沟槽互不相干，跨列零对齐。**
顶栏 `px-5`（`layout.tsx:41`）、dock `px-4`、稿纸 `px-10 sm:px-14`（`manuscript-paper.tsx:38`）——顶栏文字基线、dock 内容左缘、稿纸左缘三者没有任何数学关系。稿纸 `max-w-[760px]` 居中（:34）在 1360–1600px 窗口下两侧余量随机。

**D3. thread 底部死空间没有收束。**
截图红框 1 下半部：最后一张卡到 composer 之间约 300px 纯空白。thread 顶部对齐增长（`writer-rail.tsx:139` 滚动容器），底部既没有渐变淡出、也没有「对话从这里开始」的锚点；空态时 `RailGreeting`（:172）垂直居中，一旦有消息整个重心上移到顶部，composer 孤零零沉底。为什么显不高级：空白本身没错，错在空白没有「被设计」——Linear 的空 thread 会把留白收拢成引导区，而不是让内容贴顶、剩下一片无主之地。

### E. 字层级与灰度

**E1. 手稿正文用错了字阶——这是全文最严重的一条单行 bug。**
`manuscript-paper.tsx:135`：textarea 用 `font-serif text-lg`，即 18px / **line-height 1.45**（`globals.css:98-99`）。而 token 体系为手稿正文专门定义了 `--text-reading: 17px / 1.85`（`globals.css:104-107`，注释明写「Manuscript body…CJK prose wants a touch more air」），规范要求「正文阅读区域 line-height 1.7 左右」（04:226）。组件 docstring 还自称「generous 1.9 line-height」（`manuscript-paper.tsx:13`）——注释、token、实现三方脱节，`text-reading` 定义后无人使用。1.45 行高的 CJK 长文密不透风，截图里正文段落的「砖墙感」正源于此。为什么显不高级：写作产品的阅读质感=产品质感，行高是其中单价最高的一处。

**E2. dock 内字阶坍缩：12px 承担了 6+ 种语义。**
状态行、卡片标题、字数、chips、提示、错误、链接全部是 `text-caption`（12px）：`writer-rail.tsx:83/199/291/341/373/409/506/553/574`、`writer-composer.tsx:66`。字阶 8 档在 dock 里实际只用了 2 档（12px + 13px），候选稿正文与状态文字只能靠 serif/颜色区分。为什么显不高级：层级=「不看字号也知道谁重要」，全 12px 意味着层级全部靠颜色和位置硬撑。

**E3. 四种次级灰随机分布，没有稳定映射。**
`muted`(#5a5146)、`muted-soft`(#6f6559)、`text-ink/80`、`ink-soft` 四种次级色在相邻元素混用：CitationsRow 里同类 chips 一个用 `text-muted`、一个用 `text-ink/80`（`writer-rail.tsx:359-361`），全凭写代码那一刻的手感。为什么显不高级：灰度体系的价值在于「一级信息/二级信息/三级信息」各有固定色号，用户扫读时自然分层；随机用灰等于每次渲染都在重新掷骰子。

### F. 空态 / 占位态的廉价感

**F1. 稿纸上的段落一被点击就变成「表单输入框」——截图红框 2 的正主。**
`manuscript-paper.tsx:135` textarea 写了 `focus:outline-none`，但该类在 Tailwind v4 的 `@layer utilities` 里；`globals.css:237-240` 的 baseline focus ring（`:where(…, textarea, …):focus-visible { outline: 2px solid accent@55%; offset 2px }`）是**未入层**的作者样式，优先级压过所有层内工具类——于是 `focus:outline-none` 失效，点击任何手稿段落都画出矩形朱红描边。截图里光标与描边同框可见。`globals.css:233` 的注释声称「任何组件自定义的 focus 处理仍能覆盖它」——层级机制恰好把这句话反转了。为什么显不高级：纸的隐喻要求「我写的是字，不是在填表」；一个矩形框把 textarea 的表单身份暴露无遗。这是「占位框廉价感」的技术根因，一行层级修复即可消除。

**F2. 每章开头常驻一个空段落框。**
`writer-workspace.tsx:423-426`：新建章节自动 `createBlock(content_text: "")`，于是每章首段永远是一个 2 行高（`rows={2}`，:134）的空 textarea，占位文案「从这里开始写。空白的稿纸，等第一个字落下。」（`manuscript-paper.tsx:132`）以 `muted-soft` 显示在空框内——再叠上 F1 的描边，就是截图里「带边框的廉价占位框」的完整成因。采用候选稿后空 block 仍挂在章首（截图：空框之下才是 agent 写的「# 第一章」）。为什么显不高级：书的每一章以一张空表格开头。

**F3. 手稿正文里出现裸 markdown 字面量「# 第一章」。**
截图清晰可见。agent 产出的 markdown 标题未经渲染或清洗直接进入稿纸（稿纸是纯 textarea 平铺，无 markdown 感知）。为什么显不高级：「产物主导」原则要求手稿就是书稿；在书稿上看到源码符号，等于在打印稿上看到 HTML 标签。这严格说是管道/渲染两层问题，但视觉后果全由稿纸承担。

**F4. composer 提示文字折行贴边。**
`writer-composer.tsx:66-68`：12px 提示「起草的内容先作候选稿…Shift+Enter 换行」在 360px dock 里折成两行，第二行「行」贴到屏幕底缘（截图红框 1 底部可见被裁切感）。常驻说明文字没人读第二遍，却永久占两行高度。空章文案（`manuscript-paper.tsx:41-47, 146-149`）同理：裸段落 `text-muted-soft`，无层级、无引导动作。

### G. dock 与画布的关系

**G1. dock 没有自己的「面」，像页面左边没涂满。**
dock 容器 `bg-paper/40`（`writer-workspace.tsx:612`）——40% 透明叠在同色 app 背景上，数学上几乎等于没涂；与画布之间只有一根 `border-r`。稿纸是唯一的浮起面（`bg-panel` + `shadow-panel`），但 dock 里的卡片也全用 `bg-panel`——同一材质同时表达「主角」和「普通容器」，主角被拉平。为什么显不高级：双主角界面需要「桌」与「纸」的材质区分（Attio 的 record 页、Notion 的 side peek 都靠背景色阶拉开从属关系）；现在 dock 既不像协作者的工位，也不像从属面板。

**G2. 整个 dock 绕 Y 轴 3D 翻转 500ms——全系统最重的动效给了最高频入口之一。**
`composer-review-flip.tsx:93-99`：`[perspective:1800px]` + `rotateY(180deg)` + `duration-500`。规范动效条款：「panel 悬停最多上浮 1px…不使用弹跳或大比例缩放」「动画只改变 transform、opacity、颜色和阴影」（04:241-243）——180° 翻转是合法 transform，但气质上与「现代书卷式创作工作台」（04:147）完全相反，这是营销页/演示页的炫技动效。为什么显不高级：克制的产品里，动效最好的状态是「感觉不到动效存在」。

**G3. dock 宽度语义错误 + 候选稿被滚动裁剪。**
dock 宽 360px，用的是 `--spacing-rail-inspector`（`globals.css:155`）——inspector 是「附属详情面板」的宽度语义，而 conversation-first IA 里 dock 是常驻协作者（双主角之一）。360px 内候选稿 `max-h-[280px] overflow-y-auto`（`writer-rail.tsx:495`）：AI 写的正文、作者要逐字审阅的决策对象，在自己的展示位里被 280px 截断内滚。为什么显不高级：决策对象的可读性=决策质量；把候选稿塞进滚动小窗，等于承认「这里放不下真正重要的东西」。

### H. 色彩纪律

**H1. accent 一屏七职，且包含自己被注释禁止的错误用法。**
当前一屏内 accent 同时是：品牌方块（layout.tsx:48）、导航激活态（workbench-nav-rail.tsx:83/91/98）、用户气泡、发送钮、采用钮、「查看正文」链接、task spinner（writer-rail.tsx:403）、候选稿光标（:499）、focus ring、**错误**——`SaveIndicator` 错误态 `text-accent`（`writer-canvas-top.tsx:194`）、起草失败提示 `border-accent/30 bg-accent-wash text-accent`（`writer-rail.tsx:291`）、actionError 横幅 `bg-accent-wash text-accent`（`writer-workspace.tsx:599`）。`globals.css:42-46` 注释明写 accent「is NOT the error colour; see --color-danger」，且 `danger`/`danger-wash` token 已存在——写作台就是不用。为什么显不高级：当红色同时意味着「点我」「我写的」「出错了」「正在转」「选中了」，它什么都不意味。

**H2. 画布——产品主角——几乎零色彩。**
稿纸上没有任何一处色彩处理：无章节标题锚点（设计上故意省略，见 `manuscript-paper.tsx:36` 注释）、当前段无标记、reveal 脉冲是唯一一次 accent 出现（:121-123，且 1.9 秒后消失）。朱红「滥用与不足」同框：dock 里泛滥成灾，稿纸上完全缺席。印章色若出现在稿纸的章节题字、当前段左侧批注线上，才是「paper & vermilion」的题中之义。

**H3. 语义色在 dock 里互相打架。**
召回 chips 用金（`border-gold/60 bg-gold/10`，:358）、完成态图标用绿（`text-success`）、失败用红、候选角标用金底白字——在 360px 宽的一条 thread 里，金/绿/红/朱红四色同时出现且各自只有指甲盖大小。小面积多色=花；规范要求琥珀只用于候选/待审（04:188），现状金色还兼职「常驻设定」chip 的描边。

### I. 密度与留白

**I1. 留白花在没内容的地方，而不是主角身上。**
全屏最大的三片连续空白：dock 底部（D3）、导航轨中段（7 个图标集中在顶部 1/3，下方 2/3 全空）、稿纸两侧（`max-w-[760px]` 居中余量）。稿纸内部段落间距 `mt-6` + `pt-6`（`manuscript-paper.tsx:125`）反而偏紧。为什么显不高级：高级感来自「留白是有指向的」——它应该把视线推向主角；现状留白只是把空的地方空着。

**I2. dock 信息密度假性偏高、实效偏低。**
一次完整交互（气泡 + TaskCard + SettledCard + chips）垂直占约 400–500px，360px 宽 dock 一屏只见 1.5 次交互；但单位面积里的有效信息很少——大量像素花在边框、内边距、角标、分隔线上。这是「高密度但不杂乱」（04:60）的反面：低密度且杂乱。

**I3. 顶栏左挤右空。**
56px 高的顶栏左侧塞了：朱红方块 + 毛笔字「墨鱼小说」+ 竖线 +「书架」+「测试6 › 第1章 ⌄」（`writer-canvas-top.tsx:113-127`，毛笔字/无衬线/衬线三种字体同栏）+ 竖线 +「5556 字」+ 保存态；右侧只有一颗小「新章节」。且窗口 `max-w-[1600px]`（`layout.tsx:41/84`）在 1360px 截图窗口下两侧已顶满。为什么显不高级：一行内 7 个信息件、3 种字体、2 种字重，没有一个明确的视觉终点。

---

## 3. 优先级清单（严重度 × 改动成本）

严重度 = 对「大厂质感」的损害程度；成本 = 实现 + 验证工作量估计。

| # | 问题 | 位置 | 严重度 | 成本 | 优先级 |
|---|------|------|--------|------|--------|
| E1 | 手稿正文 18px/1.45 → 改用 `text-reading`（17px/1.85） | `manuscript-paper.tsx:135` | ★★★★★ | 极低（一行 class） | **P0** |
| F1 | baseline focus ring 未入层，压过 `focus:outline-none`，段落聚焦出矩形框 | `globals.css:237-240` × `manuscript-paper.tsx:135` | ★★★★★ | 低（入层或给稿纸显式 focus 处理） | **P0** |
| A1 | 用户气泡去按钮化（中性底、去 `shadow-accent`） | `writer-rail.tsx:187` | ★★★★☆ | 低（单组件） | **P0** |
| H1-错误 | 错误态 accent → danger（三处） | `writer-canvas-top.tsx:194`、`writer-rail.tsx:291`、`writer-workspace.tsx:599` | ★★★☆☆ | 低 | **P0** |
| F3 | 裸 markdown「# 第一章」上手稿（渲染或清洗） | 稿纸渲染层 / agent 产出管道 | ★★★★☆ | 中（需定策略） | **P0/P1** |
| B1 | thread 卡片瘦身：去边框改分隔线，turn 收敛为时间流条目 | `writer-rail.tsx:393/488/544` | ★★★★☆ | 中（重写 rail 渲染层，不动逻辑） | **P1** |
| B3 | composer 去框去 `shadow-panel`，融入 dock 底部 + 顶分隔线 | `writer-composer.tsx:39` | ★★★☆☆ | 低 | **P1** |
| C4 | 画布头补视图切换（稿件/章节/审校/工具）+ 主操作位 | `writer-canvas-top.tsx` | ★★★★☆ | 中（涉 IA 与信息架构决策） | **P1** |
| C2 | 「新章节」等结构操作归位（与 C4 一起做） | `writer-canvas-top.tsx:60-68` | ★★★☆☆ | 低–中 | **P1** |
| G1 | dock 材质与归属：明确的从属面（色阶/细分隔），稿纸独占 `bg-panel`+投影 | `writer-workspace.tsx:612` | ★★★☆☆ | 低–中 | **P1** |
| F2 | 空章不再常驻空段落框（首段聚焦即创建/空 block 不落库） | `writer-workspace.tsx:423-426`、`manuscript-paper.tsx:132` | ★★★☆☆ | 中（涉数据流） | **P1** |
| G3 | 候选稿去 280px 内滚（展开全文/与手稿并置），dock 宽度重议 | `writer-rail.tsx:495`、`globals.css:155` | ★★★☆☆ | 中 | **P1/P2** |
| D1 | dock 内 padding 收敛为 2 档，所有左缘对齐同一沟槽 | writer-rail / composer 全文件 | ★★★☆☆ | 低–中 | **P2** |
| G2 | 3D 翻转收敛为淡入/滑动（或重议待审入口形态） | `composer-review-flip.tsx:93-99` | ★★☆☆☆ | 低 | **P2** |
| A3 | dock 头部减重：待审入口降为 icon button，去「常驻协作」 | `composer-review-flip.tsx:65-90`、`writer-rail.tsx:83` | ★★☆☆☆ | 低 | **P2** |
| A2 | logo 方块与头像去重色化（线稿/暖墨） | `layout.tsx:48-50`、nav 头像 | ★★☆☆☆ | 低 | **P2** |
| E3 | 灰度语义映射落地（ink/ink-soft/muted/muted-soft 各司其级） | 全写作台 | ★★☆☆☆ | 中 | **P2** |
| H3 | 语义色收敛：金色只留候选语义，chips 去框改色点+文字 | `writer-rail.tsx:356-362` | ★★☆☆☆ | 低 | **P2** |
| D3/I1 | thread 底部收束（渐变/引导锚点），导航轨空白处理 | `writer-rail.tsx:139`、nav rail | ★★☆☆☆ | 低–中 | **P2/P3** |
| E2 | dock 字阶重建（状态/正文/提示各归其档） | 全 rail | ★★☆☆☆ | 中 | **P3** |
| I3 | 顶栏信息再平衡（字体收敛、右区充实） | `layout.tsx`、`writer-canvas-top.tsx` | ★★☆☆☆ | 中 | **P3** |

**建议切入顺序**：先做 P0 五条（一天量级，截图对比立刻改观）→ 用 P0 的结果与用户确认方向 → 再做 P1 的结构性条目（dock 卡片瘦身 + 画布头 IA）。P0 全部不动任何交互逻辑与硬约束结构，纯渲染层。

---

## 4. 对后续方案的红线提醒（继承自任务硬约束）

- 任何方案不得恢复 `writer-studio-grid`、折叠 composer、深色 `writer-agent-rail`、旧蓝色 Vite UI。
- 坚持 manuscript-primary + conversation-first：稿件主导主区、画布头视图切换（稿件/章节/审校/工具——当前缺失，方案须补齐而非删除）、Agent 常驻 dock（连续 thread + 常驻 composer + 选区驱动）。
- 正文级文字对比度 ≥ 4.5:1；`muted-soft` 已是底线色，次级文字不得再淡。
- 「卡片瘦身」「去边框」指用分隔线与字层级替代框体，不是回到无边无栏的旧长页。
