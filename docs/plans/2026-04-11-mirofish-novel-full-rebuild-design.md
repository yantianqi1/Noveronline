# MiroFish-Novel Full Rebuild Design

**Goal:** 在不丢失当前 `MiroFish-Novel` 任一现存功能、页面、接口、测试语义和数据语义的前提下，完成一次整体换新技术栈的重构，并最终以 `新前端 + 新 API + 新数据层 + 新工作流` 一次切换取代现有系统。

**Decision:** 采用“内部阶段化重建，外部一次切换”的路线，而不是长期双跑或纯 Big Bang。

## 1. 固定约束

- 只覆盖当前仓库已存在能力，不外扩到老 `MiroFish` 未落地能力。
- 技术栈整体换新：`React + TypeScript + FastAPI + PostgreSQL + MinIO + Redis + Temporal`。
- 最终不保留旧前端和旧 API 作为正式入口。
- 迁移期间旧系统只作为只读事实源与审计参考。

## 2. 架构结论

新系统采用模块化单体，固定 bounded contexts：

- `project`
- `seed-analysis`
- `graph`
- `archive-library`
- `worldline`
- `writer`
- `llm-facility`
- `workflow-platform`

前端固定八个页面：

- `Overview`
- `Guide`
- `Archive Library`
- `Story Graph`
- `Worldline`
- `Character Console`
- `Writer`
- `LLM Facility`

## 3. 执行策略

### 3.1 阶段化推进

1. 冻结功能/接口/测试/字段基线
2. 建新栈底座与 contracts
3. 建迁移底座
4. 后端按模块并行重建
5. 前端按页面与 feature 并行重建
6. 做迁移 rehearsal、故障演练、回滚演练
7. 正式切换

### 3.2 并行策略

推荐 subagent lanes：

- contracts
- infra + migration
- project + seed-analysis + graph
- archive-library
- llm-facility
- worldline
- writer
- web shell
- web worldline
- web writer

所有并行工作都必须服从 `contracts owner` 与 `shared schema` 的单点变更规则。

## 4. 现有方案的补齐点

为把当前 `重构方案/01-09` 补到“100% 可执行”，新增以下文档：

- `重构方案/00-重构总控与并行执行总览.md`
- `重构方案/10-隐性语义与底层兼容矩阵.md`
- `重构方案/11-Graph-重构路径与验收方案.md`
- `重构方案/12-Subagent-并行执行协议.md`
- `重构方案/13-前端完整重构方案.md`
- `重构方案/14-后端完整重构方案.md`

## 5. 完成闸门

只有同时满足以下条件，才允许宣称“100% 完整重构完成”：

- 功能矩阵关闭
- 接口与页面清单关闭
- 字段映射关闭
- 主链与隐性语义回归通过
- graph 不再是漏项
- 前后端完整方案对应交付物完成
- 迁移 rehearsal、故障演练、回滚演练通过

## 6. 参考文档

- [重构总控与并行执行总览](../../重构方案/00-重构总控与并行执行总览.md)
- [前端完整重构方案](../../重构方案/13-前端完整重构方案.md)
- [后端完整重构方案](../../重构方案/14-后端完整重构方案.md)
