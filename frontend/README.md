# MiroFish-Novel Frontend

React + TypeScript + Vite 前端工作台，提供项目上传、种子分析进度、故事图谱、资产库、worldline、Writer Agent 和 LLM 设施面板。

## 技术栈

- React 19
- TypeScript
- Vite 6
- React Router 7
- TanStack Query 5
- Zustand
- Tailwind CSS 4
- D3.js
- shadcn/ui、Base UI、Radix primitives

## 启动

```bash
npm install
npm run dev
```

默认访问地址：`http://localhost:3999`。开发服务器会把 `/api` 代理到 `http://127.0.0.1:3888`。

## 常用命令

```bash
npm run lint    # TypeScript 类型检查
npm run build   # 生产构建
npm run test    # Vitest
```

## 目录结构

```text
src/
  pages/       路由页面和页面专属组件
  components/ 共享业务组件与 ui primitives
  api/         后端 API 客户端和 SSE 客户端
  stores/      Zustand store
  hooks/       共享 React hooks
  lib/         工具函数
  types/       TypeScript 类型
  router.tsx   路由表
```

## 页面入口

- `/`：项目概览、上传与 seed pipeline。
- `/assets`：统一资产库。
- `/story-graph`：故事图谱与图谱构建。
- `/worldline`：单世界推演工作台。
- `/writer`：写作工作台。
- `/llm-facility`：LLM 渠道、模型和模块绑定。
- `/archive-library`：兼容旧路径，重定向到 `/assets`。

## 开发约定

- API 类型优先放在 `src/types/`，请求封装放在 `src/api/`。
- 新页面采用 `src/pages/<route>/page.tsx` 结构。
- 长轮询或流式事件使用 `src/api/sse.ts`。
- 不在前端源码中写入 API Key；LLM Key 由后端设施面板持久化并在 UI 中遮罩显示。
