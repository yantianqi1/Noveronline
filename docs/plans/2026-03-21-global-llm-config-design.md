# Global LLM Config Cleanup Design

**Goal:** 让仓库中所有 LLM 调用只依赖“全局设施面板的模块绑定”，彻底废弃旧 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME` 环境变量语义，并保留显式 `use_llm=False` 的离线模式。

## Scope

- 删除仓库中对旧 `LLM_*` 环境变量的配置说明与示例入口
- 清理测试中残留的旧 `Config.LLM_API_KEY` 语义
- 增加回归测试，防止运行时代码重新引入 legacy LLM env 配置
- 保持现有模块级全局设施绑定机制不变
- 保持显式离线模式不变

## Non-Goals

- 本轮不改 `ZEP_API_KEY` 相关图谱链路
- 本轮不移除 `use_llm=False` 离线能力
- 本轮不改 SQLite 设施面板的数据结构

## Expected Runtime Rules

### 允许

- `LlmRouter -> LlmSettingsService -> LLMClient`
- 模块未绑定时显式报错
- 调用方显式传入 `use_llm=False`

### 禁止

- 从环境变量读取 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME`
- 基于 legacy env 自动构造默认客户端
- 因为 legacy env 存在而静默启用 LLM

## Verification Strategy

- 增加扫描型测试，确保 `backend/app` 与 `frontend/src` 不再出现 legacy LLM env 标识
- 更新已有离线测试，移除无效的 `Config.LLM_API_KEY = None`
- 跑关键后端测试与前端构建，确认现有模块调用不受影响
