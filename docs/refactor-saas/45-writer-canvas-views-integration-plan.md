# 写作台画布视图(章节 / 审校 / 工具)接入方案

> 状态:方案待审 · 配套交互预览 `45-writer-canvas-views-preview.html`
> 依据:`24-current-development-progress.md`(2026-07-19 设计原则调和)、`04-design-system-and-ui.md`、Go API 现状核查。

## 0. 背景与结论

画布头 `ViewTabs`(稿件/章节/审校/工具)目前只有「稿件」为真,其余三个是 `available: false` 的 honest-disabled 占位([writer-canvas-top.tsx](../../../apps/web/app/projects/[projectId]/writer/writer-canvas-top.tsx) 的 `CANVAS_VIEWS`)。

后端核查结论:**三个视图依赖的核心读取侧都真实存在并已上线**,缺的是 (a) 前端视图面板本身,(b) 少量跨稿/跨章聚合端点,(c)「工具」视图的产品形态定义。可以从前端切入,但三个视图开箱即用程度不同。

| 视图 | 后端就绪度 | 前端缺口 | 后端缺口 | 建议波次 |
|---|---|---|---|---|
| 稿件 | ✅ 已上线 | — | — | 已完成 |
| 章节(结构) | 🟢 高 | scenes/outlines client + 结构面板 | 无(可直接做) | **第一波** |
| 审校 | 🟡 中 | 审校面板 + review client | 跨稿「待审校」聚合列表 | 第二波 |
| 工具 | 🟠 形态未定 | 工具面板 | 视形态而定 | 第三波(先定形态) |

## 1. 不变量(不可破坏)

- `data-layout="conversation-first"` 双栏契约不变:手稿画布主导,Agent dock 常驻右侧。
- 「稿件」连续阅读流(`manuscript-paper.tsx`,664px book measure,`text-reading` 17/1.85)是默认主视图,其余视图是**画布内的平级切换**,不是路由跳转、不是弹层。
- 章节切换器保留在顶栏,负责「稿件视图里读/写哪一章」;「章节」视图管结构,两者共存不冲突。
- 视觉语言:`paper & vermilion`,accent 只作印章/焦点,不作错误色;不用已退役的 `writer-studio-grid` / 蓝色长页基线。

## 2. 总体交互模型

`ViewTabs` 由「静态常量」升级为受控状态:`activeView: "manuscript" | "chapters" | "review" | "tools"`,提升到 `writer-workspace.tsx`,画布区按 `activeView` 渲染对应面板。切换视图不打断 Agent 对话流,不丢手稿未保存内容(切走前走 `flushPendingSegmentSaves` 同一守护)。⌘K 仍可驱动。

```
activeView=manuscript → <ManuscriptPaper/>            (现状)
activeView=chapters   → <ChaptersStructurePanel/>     (新增)
activeView=review     → <ReviewPanel/>                (新增)
activeView=tools      → <ToolsPanel/>                 (新增,形态待定)
```

## 3. 章节(结构)视图 — 第一波

**后端(全部就绪,零改动)**
- 章节 CRUD + 重排:`GET/POST /chapters`、`PATCH/DELETE /chapters/{id}`、`POST /chapters/reorder`
- 场景 CRUD + 重排:`GET/POST /chapters/{id}/scenes`、`PATCH/DELETE /scenes/{id}`、`POST .../scenes/reorder`
- 版本:`GET /chapters/{id}/versions`、`GET /scenes/{id}/versions`
- 大纲 + 版本恢复:`GET/POST /projects/{id}/outlines`、`POST /outline-versions/{id}/restore`
- 书籍计划:`POST /projects/{id}/book-plans/{id}/generations`

**前端缺口**
- `writer-client.ts` 增补:scenes(list/create/update/delete/reorder)、outlines、book-plans 的 client 方法(chapters/reorder 已有部分)。
- 新组件 `chapters-structure-panel.tsx`:三列「卷/章 → 场景 → 场景详情(摘要/大纲)」树,复用 `Chapter` 卡片样式;行内字数、状态徽章(规划中/写作中/已完成,复用 `chapterStatusLabel`);拖拽重排走现有 reorder 端点(乐观锁)。
- 场景详情支持编辑 `brief/outline`(scene 无 `content_text`,正文仍归 manuscript block,CONN-001 不变)。

**数据一致性注意**:scene 可是空大纲;字数与审稿数挂「章/块」层,不挂场景。

## 4. 审校视图 — 第二波

**后端(单稿链路完整)**
- 发起:`POST /v1/drafts/{id}/reviews`(module `writer_reviewer`)
- 读取:`GET /v1/drafts/{id}/reviews`
- 处置:`PATCH /v1/draft-review-issues/{id}`(accepted/dismissed/resolved,乐观锁)

**前端缺口**
- review client(fetchReviews / startReview / updateIssueStatus)+ `review-panel.tsx`。
- 面板形态(预览里已演示):左侧「有待审校的稿/章」队列,右侧该稿的 issue 卡片流,卡内 severity 徽章 + 正文锚点摘录 + 处置三键;采纳/驳回写回后端。

**后端缺口(需补)**
- **跨稿「待审校」聚合列表**:现在接口以 draft 为中心,没有「本项目所有 open issue」的列表端点。第一波可先做「当前章/当前稿」切入点不卡前端;全书工作台需后端加一个 `GET /v1/projects/{id}/draft-review-issues?status=open` 聚合。
- 待确认:issue 是否带 manuscript block 行号锚点(决定能否一键定位到稿件视图)。

## 5. 工具视图 — 第三波(先定形态)

后端是一组彼此独立的能力,无统一「工具」面:导出(`GET .../manuscript/export`,TXT/artifact + SHA256)、去重(dedup-patterns / dedup-extractions)、违禁词库、写作预设(writer-presets / forbidden-lexicon)、手动蒸馏(Z2)。

**这一步不是后端缺口,是产品决策**:「工具」视图聚合哪几项、是表单面板还是卡片工具箱。形态未定前不动前端。预览里给了一个「导出 + 违禁词 + 去重 + 预设」的工具箱草案,仅供讨论,**不作实现承诺**。

## 6. 落地顺序与验收

1. **章节视图**(纯前端,后端零改):client 补 scenes/outlines → 结构面板 → 接进 `ViewTabs`。验收:增删改场景、拖拽重排、改大纲、与稿件视图互切不丢稿。
2. **审校视图**(前端为主,后端补 1 个聚合端点):先做当前稿审校面板,再补全书聚合。验收:对当前稿发起审校、列 issue、处置写回、可定位正文。
3. **工具视图**:先评审形态草案,再排期。

每波都要刷新 `24-current-development-progress.md` 的波次表与证据列。

## 7. 配套预览

`45-writer-canvas-views-preview.html` 是静态交互稿:顶栏四 tab 可点,演示稿件(连续阅读流)、章节(结构树)、审校(issue 卡片)、工具(工具箱草案)四种画布形态。数据为虚构样例,仅用于确认形态与视觉,不接后端。
