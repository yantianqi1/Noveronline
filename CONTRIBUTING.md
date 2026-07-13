# Contributing

感谢你关注 MiroFish-Novel。这个项目处于活跃开发阶段，欢迎通过 issue 和 pull request 参与。

## 开始之前

- 先阅读 `README.md`、`AGENTS.md` 和 `CLAUDE.md`。
- 如果改动数据模型，先阅读 `docs/database/database-source-of-truth-matrix.md`。
- 如果改动 API，更新或核对 `docs/fastapi-route-manifest.md`。
- 不要提交 API Key、用户小说原文、私有数据库、上传文件、LLM trace 或日志。

## 本地开发

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml up -d --build
```

Web 位于 `http://localhost:3999`，API 位于 `http://localhost:3888`。`apps/web` 是唯一前端目录；根目录旧 `frontend/` 已退役，不接受恢复它的 PR。

## 提交 PR

PR 描述应包含：

- 背景和动机
- 主要改动范围
- 验证命令和结果
- 是否涉及数据库迁移、LLM prompt、公开 API 或用户数据
- 可能的兼容性影响

## 代码原则

- 修根因，不用 mock 成功或静默 fallback 掩盖问题。
- 所有 schema 变更通过新 migration 完成，不直接修改已应用 revision。
- 数据库访问使用参数化查询和现有 repository/store 边界。
- 所有 LLM 调用走统一 LLM 设施面板的模块绑定。
- 保持小说创作领域语义，避免引入上游舆情分析抽象。

## 测试

```bash
cd apps/api
go test ./...

cd apps/web
npm run test
npm run typecheck
npm run build

cd apps/agent-runtime
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests -q

cd apps/pi-agent-runtime
npm test
npm run typecheck
npm run build
```

如果某项检查因为环境缺失无法运行，请在 PR 中明确说明原因。
