# Infra Baseline

本目录只承接新技术栈的基础设施定义，写边界固定在 `infra/**`。

当前 compose 只保证底座，不宣称业务已可用：

- `postgres`
- `redis`
- `minio`
- `temporal`
- `temporal-ui`
- `api-v2`
- `workflow-worker`
- `frontend-web`

## 现状说明

- `postgres`、`redis`、`minio`、`temporal`、`temporal-ui` 使用真实镜像与独立网络/卷。
- `api-v2`、`workflow-worker`、`frontend-web` 目前是显式失败的占位服务，服务名、依赖关系、环境契约已冻结，但尚未接入真实运行时镜像。
- 这样做是为了避免“静默可用”的假象，失败必须可见。

## 文件

- `infra/compose/compose.dev.yml`
- `infra/env/.env.dev.example`

## 启动方式

1. 复制环境模板：

```bash
cp infra/env/.env.dev.example infra/env/.env.dev
```

2. 先启动底座服务：

```bash
docker compose -f infra/compose/compose.dev.yml --env-file infra/env/.env.dev up postgres redis minio temporal temporal-ui
```

3. 进入业务占位层时显式启用 `apps` profile：

```bash
docker compose -f infra/compose/compose.dev.yml --env-file infra/env/.env.dev --profile apps up
```

这一步目前会以明确错误退出，因为 `api-v2`、`workflow-worker`、`frontend-web` 还没有绑定真实容器镜像和启动命令。

## 约束

- 不要把 compose 误解成业务已可运行。
- 新增服务、端口、卷、环境变量时，必须同步更新这里和 `infra/env/.env.dev.example`。
