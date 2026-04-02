# Remove Prompt Budget Design

**Goal**

删除第一阶段与剧情块分析阶段的本地 prompt 裁剪行为，发送完整拼接后的上下文，不再静默截断或丢弃段落。

**Context**

当前 `PromptBudgetManager` 会基于固定字符预算裁剪 `主块正文`、`上下文章节`、`锚点世界状态` 等段落。这与项目里的 `No Silent Fallbacks` 原则冲突，也让模型在超长上下文可用时无法获得完整材料。

**Decision**

保留 `PromptBudgetManager` 这个调用点和类名，避免影响调用方注入方式，但将其实现改为单纯拼接非空 sections，不再读取或执行字符预算、段落优先级、截断提示、丢段逻辑。

**Non-Goals**

- 不修改第一阶段并发收口逻辑
- 不新增新的 fallback、保护阈值或静默降级
- 不改变上游报错方式，超时和 5xx 仍然显式失败

**Validation**

新增测试覆盖：

- 超长 sections 仍会完整保留
- section 顺序和非空过滤保持不变
- 第一阶段相关回归测试继续通过
