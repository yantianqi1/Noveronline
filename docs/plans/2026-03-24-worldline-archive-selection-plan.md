# Worldline Archive Selection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将世界线源档案选择区改造成单栏高密度档案工作台，支持常驻筛选、卡片即选择、单卡就地展开详情与底部固定操作条。

**Architecture:** 保持现有世界线数据流、档案列表接口与会话创建契约不变，只重构前端的 `ArchiveLibraryPicker`、档案卡片组件和世界线控制台布局。选择状态继续由父组件管理，新增“展开卡片”这一纯前端 UI 状态，并通过视图模型和测试把“选中”与“展开”严格分离。

**Tech Stack:** Vue 3 SFC, scoped CSS, Vite, Vitest-compatible frontend tests

---

### Task 1: 写清选择态与展开态的前端状态契约

**Files:**
- Modify: `frontend/src/views/shared/worldlineSelectorState.js`
- Test: `frontend/tests/worldline-selector-state.test.mjs`

**Step 1: 写出失败测试**

在 `frontend/tests/worldline-selector-state.test.mjs` 中补充测试，覆盖：

- 点击同一档案两次会完成选中与取消
- 更新同一 `archive_id` 的详情时不会重复追加
- 展开态与选中态是两套独立状态

**Step 2: 运行测试确认当前行为不完整**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm test -- worldline-selector-state.test.mjs`

Expected: FAIL，缺少展开态辅助函数或新断言不成立。

**Step 3: 补最小状态辅助函数**

- 在 `worldlineSelectorState.js` 中新增展开态切换与判定辅助函数
- 保持 `toggleArchiveSelection` 现有输入输出风格不变

**Step 4: 再次运行测试**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm test -- worldline-selector-state.test.mjs`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/views/shared/worldlineSelectorState.js frontend/tests/worldline-selector-state.test.mjs
git commit -m "test: define archive selection and expansion state"
```

### Task 2: 重构卡片组件为“卡片即选择”

**Files:**
- Modify: `frontend/src/components/ArchiveLibraryGridItem.vue`
- Test: `frontend/tests/archive-library-layout.test.mjs`

**Step 1: 写出失败测试**

在卡片交互测试中补充断言：

- 点击卡片主体触发选中事件
- “展开详情”触发单独事件
- 不再依赖“加入会话”按钮作为主要选择入口

**Step 2: 运行测试确认失败**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm test -- archive-library-layout.test.mjs`

Expected: FAIL，组件事件与结构仍是旧模式。

**Step 3: 写最小实现**

- 将卡片主体点击事件改为 `toggle`
- 保留独立的“展开详情”触发区
- 用明确的选中角标、状态文案和展开入口替代旧的小按钮心智

**Step 4: 运行测试**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm test -- archive-library-layout.test.mjs`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/ArchiveLibraryGridItem.vue frontend/tests/archive-library-layout.test.mjs
git commit -m "feat: make archive cards selectable by click"
```

### Task 3: 将档案选择器改造成单栏卡片工作台

**Files:**
- Modify: `frontend/src/components/ArchiveLibraryPicker.vue`
- Modify: `frontend/src/components/ArchiveLibraryPicker.css`
- Modify: `frontend/src/views/shared/archiveLibraryPickerLayout.js`
- Test: `frontend/tests/archive-library-picker-layout.test.mjs`

**Step 1: 写出失败测试**

在 `frontend/tests/archive-library-picker-layout.test.mjs` 中补充断言：

- worldline 变体不再渲染固定双栏详情结构
- 筛选区常驻显示
- 详情改为卡片内就地展开

**Step 2: 运行测试确认失败**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm test -- archive-library-picker-layout.test.mjs`

Expected: FAIL，当前布局仍然保留详情栏结构。

**Step 3: 写最小实现**

- 将 `ArchiveLibraryPicker` 改为单栏结构
- 保留顶部筛选区
- 在卡片列表中插入单展开详情块
- 删除 worldline 变体中的固定详情栏依赖

**Step 4: 运行测试**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm test -- archive-library-picker-layout.test.mjs`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/ArchiveLibraryPicker.vue frontend/src/components/ArchiveLibraryPicker.css frontend/src/views/shared/archiveLibraryPickerLayout.js frontend/tests/archive-library-picker-layout.test.mjs
git commit -m "feat: convert archive picker to single-column workbench"
```

### Task 4: 改造世界线控制台的源档案区和底部操作条

**Files:**
- Modify: `frontend/src/views/worldline/WorldlineControlPanel.vue`
- Modify: `frontend/src/views/worldline/WorldlineControlPanel.css`
- Modify: `frontend/src/views/WorldlineWorkbenchView.vue`
- Modify: `frontend/src/views/WorldlineWorkbenchView.css`

**Step 1: 写出失败测试**

在现有世界线工作台相关测试中补充断言：

- 源档案区文案改为单栏选择心智
- 已选摘要固定出现在底部操作条
- 创建按钮始终与已选结果邻接

**Step 2: 运行测试确认失败**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm test -- worldline-workbench-layout.test.mjs`

Expected: FAIL，当前布局和文案仍反映旧的双栏选择流程。

**Step 3: 写最小实现**

- 调整源档案区文案与结构
- 在控制台底部新增固定操作条表达已选数量、标签与主按钮
- 保持 `createSession` 与现有 emit 契约不变

**Step 4: 运行测试**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm test -- worldline-workbench-layout.test.mjs`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/views/worldline/WorldlineControlPanel.vue frontend/src/views/worldline/WorldlineControlPanel.css frontend/src/views/WorldlineWorkbenchView.vue frontend/src/views/WorldlineWorkbenchView.css
git commit -m "feat: align worldline control panel with archive workbench"
```

### Task 5: 全量验证并按项目约定重启

**Files:**
- Verify: `frontend/src/components/ArchiveLibraryGridItem.vue`
- Verify: `frontend/src/components/ArchiveLibraryPicker.vue`
- Verify: `frontend/src/views/worldline/WorldlineControlPanel.vue`
- Verify: `frontend/src/views/WorldlineWorkbenchView.vue`

**Step 1: 运行前端定向测试**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm test -- worldline-selector-state.test.mjs archive-library-layout.test.mjs archive-library-picker-layout.test.mjs worldline-workbench-layout.test.mjs`

Expected: PASS

**Step 2: 运行前端构建**

Run: `cd /Users/项目/MiroFish-Novel/frontend && npm run build`

Expected: PASS，无模板、样式或打包错误。

**Step 3: 按项目约定重启前后端**

Run: 重新启动前端 `3891` 与后端 `5101` 开发服务

Expected: 超过 50 行代码改动后，页面加载的是最新版本。

**Step 4: 人工验收**

- 顶部筛选区常驻可见
- 中部一屏可见更多卡片
- 点击卡片主体即可选中/取消
- 同时只展开 1 张卡片
- 底部操作条持续展示已选结果与创建动作
