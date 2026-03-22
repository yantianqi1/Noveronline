# Worldline Control Panel Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将世界线控制台重构为更清晰的三段式操作面板，改善布局层级与交互可读性。

**Architecture:** 保持现有世界线状态流和 API 不变，只调整 `WorldlineControlPanel` 的模板分区与局部样式，并对工作台外层布局做轻量配合，避免选择器区域挤压操作区。实现以组件内结构重组为主，样式层负责建立标题、摘要、分区卡和按钮层级。

**Tech Stack:** Vue 3 SFC, scoped CSS, Vite

---

### Task 1: 重组控制面板模板

**Files:**
- Modify: `frontend/src/views/worldline/WorldlineControlPanel.vue`

**Step 1: 写出新的分区结构**

- 将面板拆成“源档案”“会话创建”“会话控制”三个 section。
- 为创建区加入会话状态摘要和说明文本。
- 为推进与注入区域加入独立标题与状态提示。

**Step 2: 保留现有事件与 props 契约**

- 继续使用现有 `emit` 事件与 `props` 字段。
- 不修改 `createSession`、`stepForward`、`injectVariable` 的调用方式。

**Step 3: 人工检查模板是否仍与父组件兼容**

- 确认属性名、事件名、按钮禁用条件不变。

### Task 2: 建立更明确的视觉层级

**Files:**
- Modify: `frontend/src/views/worldline/WorldlineControlPanel.vue`
- Modify: `frontend/src/views/WorldlineWorkbenchView.css`

**Step 1: 在控制面板中补充局部样式**

- 为 section、标题、摘要条、按钮组、反馈块增加样式。
- 区分主按钮和次按钮的尺寸与排列。

**Step 2: 调整外层布局配合**

- 让左侧控制区滚动和间距更稳定。
- 在较窄宽度下确保分区自然折行，避免按钮与状态摘要拥挤。

**Step 3: 检查样式改动不破坏现有暖色主题**

- 复用现有变量，避免引入新的视觉体系。

### Task 3: 验证与重启

**Files:**
- Verify: `frontend/src/views/worldline/WorldlineControlPanel.vue`
- Verify: `frontend/src/views/WorldlineWorkbenchView.css`

**Step 1: 运行构建检查**

Run: `npm run build`

Expected: Vite build 成功，无模板或样式错误。

**Step 2: 按项目约定重启前端**

Run: 重新启动前端开发服务，确保超过 50 行改动后的界面为最新版本。

Expected: 世界线工作台在浏览器中加载正常。

**Step 3: 目视检查关键状态**

- 未创建会话时，创建区是主视觉焦点。
- 已创建会话时，会话摘要、推进按钮和变量注入区层级清晰。
- 在较窄宽度下没有明显重叠或散乱布局。
