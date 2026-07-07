# Prompt Presets

更新时间：`2026-06-27`

这个目录存放多 Codex 窗口并行开发用的启动提示词。每个文件对应一个固定窗口身份。

当前优先开发顺序以 `../DEVELOPMENT_PLAN.md` 为准：先执行 Writer-first Pi Agent 最小闭环，再展开 SaaS 基座和其他模块。

使用步骤：

1. Coordinator 给窗口创建独立 worktree / branch。
2. 打开新的 Codex 窗口。
3. 复制对应 prompt 文件全文，作为新窗口第一条消息。
4. 新窗口只执行 prompt 中的身份和范围。

不要把多个身份 prompt 合并给同一个窗口。
