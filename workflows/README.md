# Workflows

`workflows/` 是 MiroFish-Novel 新栈的 Temporal worker 基线目录。

当前只保留最小可验证骨架，不承载具体业务 workflow。

## 现状

- `src/settings.py`：worker 默认配置，支持 `MIROFISH_` 前缀环境变量覆盖
- `src/task_queue.py`：task queue 描述结构
- `src/bootstrap.py`：worker bootstrap 组装
- `src/worker.py`：入口级描述函数 `describe_worker()`

## 验证

```bash
cd workflows
python3 -m pytest
```
