# 16. Deployment and Ops

更新时间：`2026-06-27`

## 部署目标

公网 SaaS 部署必须支持：

- HTTPS。
- 多实例 Go API。
- 独立 Next.js web。
- Temporal cluster。
- Python worker 横向扩容。
- Postgres 备份。
- 对象存储。
- Redis。
- 监控、日志、告警。

## 环境

### Local Dev

```text
Docker Compose
  web
  api
  agent-worker
  postgres
  redis
  temporal
  minio
```

### Staging

类似生产，但：

- 单独数据库。
- 单独对象存储 bucket。
- 测试 LLM 渠道。
- 邮件/支付 sandbox。

### Production

推荐：

- Managed Postgres。
- Managed Redis。
- S3/R2。
- Temporal Cloud 或自建 Temporal。
- Container platform：Kubernetes / ECS / Fly.io / Render。

## 服务

### Web

- Next.js。
- CDN 前置。
- 环境变量只放 public-safe 配置和 server auth secret。

### API

- Go binary。
- 无状态。
- 水平扩容。
- 连接池。
- request timeout。
- graceful shutdown。

### Agent Worker

- Python。
- 按 task queue 分 worker deployment。
- CPU/memory 配额。
- LLM timeout。
- heartbeat。

### Temporal

- workflow history retention。
- namespace per environment。
- task queues per domain。

## Secrets

必须进入 secret manager：

- DATABASE_URL。
- Redis URL。
- object storage credentials。
- auth secrets。
- encryption keys。
- platform LLM API keys。

租户自带 LLM Key：

- 存数据库前加密。
- 不进入环境变量。
- 不写日志。

## Object Storage

bucket 规划：

```text
mirofish-prod-uploads
mirofish-prod-artifacts
mirofish-prod-exports
mirofish-prod-traces
```

object key：

```text
tenants/{tenant_id}/projects/{project_id}/uploads/{file_id}
tenants/{tenant_id}/projects/{project_id}/artifacts/{run_id}/...
```

访问：

- 私有 bucket。
- signed URL。
- 短过期。
- 下载审计。

## Observability

### Metrics

- API latency。
- API error rate。
- active workflows。
- workflow failure rate。
- LLM calls by module。
- LLM latency。
- token usage。
- Postgres connections。
- worker queue lag。

### Logs

结构化 JSON：

- request_id。
- tenant_id。
- project_id。
- run_id。
- user_id hash。
- error_code。

不要记录：

- API Key。
- 完整小说原文。
- 完整 prompt。

### Tracing

OpenTelemetry trace：

```text
HTTP request
  -> DB query
  -> workflow start
  -> activity
  -> LLM call
```

## Backup

### Postgres

- PITR。
- 每日快照。
- 恢复演练。

### Object Storage

- versioning。
- lifecycle。
- 删除保留期。

### Temporal

- 按官方推荐备份 persistence。
- 生产使用 managed 更省心。

## Security

- HTTPS only。
- secure cookies。
- CSRF 防护。
- rate limit。
- upload size limit。
- MIME sniffing。
- virus scan 可选。
- RLS。
- audit logs。
- admin access review。

## Rate Limit

维度：

- IP。
- user。
- tenant。
- endpoint。
- workflow type。
- LLM module。

策略：

- 登录/注册严格。
- 上传按文件大小限制。
- writer stream 按并发限制。
- asset search 可缓存。

## Cost Control

- LLM token 预算。
- workflow max runtime。
- per tenant concurrent runs。
- per project active heavy tasks。
- object storage quota。
- vector embedding batch limit。

不要硬截断用户小说。限制必须可解释，可配置，有错误提示。

## Incident Playbook

### LLM Provider Down

- 标记 channel unhealthy。
- 失败任务可重试。
- UI 提示换渠道。
- 不 mock 成功。

### Worker Crash

- Temporal retry。
- 超过重试后 workflow failed。
- 用户可 retry from checkpoint。

### Tenant Data Leak Suspected

- 立刻关闭相关 API。
- 导出 audit logs。
- 查 RLS policy 和 request logs。
- 通知受影响租户。

## 验收清单

- docker compose 一键启动本地全栈。
- staging 和 prod 数据隔离。
- Postgres 备份可恢复。
- worker 可横向扩容。
- API 多实例不丢任务状态。
- logs 不含敏感原文/API Key。
- LLM 成本可按租户统计。
