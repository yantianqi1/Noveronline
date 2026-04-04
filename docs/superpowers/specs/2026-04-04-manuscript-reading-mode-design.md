# 稿件阅读模式设计规格

**日期**: 2026-04-04
**状态**: 已确认

## 背景

Writer Workbench 的章节查看模块存在以下问题：

1. ManuscriptDrawer 是全屏弹窗，与写作流程割裂
2. 阅读面板展示编号块（#10, #20），像数据库管理后台
3. 章节是事后批量打标签，缺乏结构化
4. 提交场景后无法直接在上下文中看到成果

## 目标

在中间面板增加「稿件阅读模式」，让作者能以沉浸式连续散文的形式阅读和轻量编辑已有稿件内容，同时将章节从标签升级为一等公民。

## 设计

### 1. 模式切换

中间面板顶部增加 `写作` / `稿件` 两个 tab：

- **写作模式**：现有全部功能不变（场景编辑器、agent 进度、续写上下文、输入区）
- **稿件模式**：连续散文阅读视图

切换时两个模式的状态互相独立——写作模式的 agent 进度、输入框内容等切回来都保留。

### 2. 稿件模式布局

进入稿件模式时，三栏布局变为两栏：

- **左侧面板**：内容替换为稿件目录
- **中间面板**：拓宽，展示连续散文
- **右侧面板**：自动隐藏

退出稿件模式时，恢复三栏布局和左侧原有内容。

### 3. 稿件目录（左侧面板）

替换写作控件，展示：

- 章节列表，每章显示：标题、字数统计
- 点击章节 → 中间面板滚动到对应位置
- 「全部」选项（默认，展示全稿）
- 「未归类」选项（展示无 chapter_tag 的块）
- 底部：全稿统计（总字数、总章节、总段落）
- 可新建章节、重命名章节

数据来源：复用现有 `getManuscript` API，从 blocks 的 chapter_tag 聚合。

### 4. 散文渲染（中间面板）

核心原则：**块边界不可见，呈现为连续散文**。

- 块与块之间无分隔线、无编号，只有自然段落间距
- 章节分隔：以 `第X章 · {章节名}` 作为视觉标题，上方留白较大
- 字体：`"Noto Serif SC", "Source Han Serif CN", serif`（复用现有 `.prose-text` 字体栈）
- 行高：1.9
- 内容区最大宽度：`720px`，居中，两侧留白
- 空状态：「尚无稿件内容，在写作模式中创作并提交到稿件」

### 5. 段落交互（点击展开编辑）

- 默认：纯阅读，无任何操作按钮
- 点击段落：该段落原地展开为 textarea 编辑区
  - 编辑区保持相同字体和行高
  - 底部显示字数 + 「完成」按钮
  - 点击编辑区外部：自动保存（debounce 800ms）并收起
  - 同一时间只能有一个段落处于编辑状态
- 调用现有 `updateManuscriptBlock` API 保存

### 6. 章节归属自动化

提交场景到稿件时：

- 自动将当前左侧面板已选中的章节 ID 作为 `chapter_tag`
- 如果没有选中章节，block 的 chapter_tag 为空（归入「未归类」）
- 保留批量标注功能作为整理工具，但日常流程不再依赖它

实现：修改 `handleCommitToManuscript()` 逻辑，传入当前 `chapterId` 对应的章节标题作为 tag。

### 7. 导出保留

稿件模式顶部工具栏保留导出功能（TXT/MD），入口从弹窗移到稿件模式工具栏。

### 8. 不变的部分

- 后端数据模型不变（`manuscript_blocks` 表结构不动）
- 写作模式的所有功能原封不动
- `ContinuationContextPanel` 保留在写作模式
- `ManuscriptDrawer` 组件可以保留但不再作为主要入口（可后续废弃）

## 关键文件

### 需修改

- `frontend/src/views/WriterWorkbenchView.vue` — 增加模式切换、布局响应
- `frontend/src/views/WriterWorkbenchView.css` — 两栏布局样式、稿件排版样式
- `frontend/src/views/writer/ManuscriptReadingPane.vue` — 重构为散文流渲染 + 点击编辑

### 需新建

- `frontend/src/views/writer/ManuscriptTocPanel.vue` — 新的稿件目录面板（替换 ManuscriptTocSidebar）
- `frontend/src/views/writer/ManuscriptProseView.vue` — 散文流渲染组件

### 可能需要调整

- `frontend/src/api/writerAgent.js` — 章节管理 API（新建/重命名）
- `backend/app/services/writer_agent/novel_db.py` — 章节新建/重命名方法（如果不存在）
- `backend/app/api/writer_agent.py` — 对应 endpoint

## 验证计划

1. 中间面板 tab 切换正常，写作/稿件模式互不干扰
2. 稿件模式下散文连续展示，无块边界
3. 章节标题正确分隔，目录点击跳转正确
4. 点击段落展开编辑，修改后自动保存
5. 写作模式提交场景后，切到稿件模式确认内容已归入当前章节
6. 导出功能正常
7. `npm run build` 通过
