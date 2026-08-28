# 架构与模块边界

术语见 [CONTEXT.md](../CONTEXT.md)，关键决策见 [docs/adr/](./adr/)。本文件定义**谁拥有哪些文件**，并行开发时不得越界。

## 主链路

```
采集 → 快照(PG) → 职位解析/去重/脱敏 → 抽取(证据强制) → AI 审核员 → 图谱(Neo4j)
                                                              ↓
                                    演化分析(突增/领先滞后/新兴岗位发现)
                                                              ↓
简历 → 版面解析 → 技能画像 → 匹配诊断 → 差距 → 学习路径 → 前端
```

任何环节的产出都必须能反查到证据。拿不出证据的结论不进图谱（ADR 0003）。

## 存储分工

- **PostgreSQL**：快照、职位、文档规范化文本与字符索引、证据、变更流水、技能观测值、技能向量、别名裁决、用户与技能画像。schema 在 `backend/schema.sql`。
- **Neo4j**：岗位、能力项、技能点、技能簇及其关系。约束在 `backend/graph_schema.cypher`。

原始文本永远不进 Neo4j；图谱节点只存 id、名称和状态。

## 目录所有权

| 目录 | 负责范围 |
| --- | --- |
| `backend/app/domain/` | 领域模型、端口协议，以及跨模块必须完全一致的纯领域规则（如职位标题归一化、时间片计算）。**只有集成者能改**，其他模块只读 |
| `backend/app/collectors/` | 各来源采集适配器、快照写入、去重、脱敏 |
| `backend/app/extraction/` | 版面解析、字符偏移与坐标索引、职位与简历抽取、技能归一化、AI 审核员 |
| `backend/app/evolution/` | 突增检测、趋势检验、领先滞后分析、技能簇、新兴岗位发现 |
| `backend/app/matching/` | 匹配档位判定、差距分析、学习路径排序与资源挂接 |
| `backend/app/graph/` | Neo4j 仓储实现、时间切片与差异查询 |
| `backend/app/storage/` | PostgreSQL 仓储实现 |
| `backend/app/api/routers/` | 每个模块只改自己那一个路由文件 |
| `ontology/` | 技能本体数据与构建脚本 |
| `eval/` | 评测集、标注准则、指标脚本 |
| `frontend/` | 前端应用 |

## 跨模块规则

1. 模块之间只通过 `app/domain/ports.py` 的协议交互，不 import 彼此的实现。
2. 需要新的依赖时不要改 `pyproject.toml`，在交付说明里写清楚。
3. 不要运行 `uv sync` / `uv lock`，共享虚拟环境由集成者维护。用 `uv run pytest tests/<你的目录>` 跑测试。
4. 大模型只做语义判断，绝不输出字符位置或坐标。位置一律由确定性字符串匹配回填，匹配不上即判抽取失败。
5. 时间片格式统一为 `YYYYQn`（如 `2026Q1`）。
6. `ontology_version` 的唯一真源是 `ontology/VERSION`，由 `Settings.ontology_version` 读出。任何地方都不许再写 `"v0"` 这类字面量作默认值：图谱的 `REQUIRES` 边按这个字段过滤，写入端与查询端取到不同的值时查询会**静默返回空**而不报错。
7. 技能词表从 `ontology/data/skills.jsonl` 读，并合并 `ontology/data/aliases.jsonl` 的表层形式（后者条数是前者内嵌别名的两倍多）。Aho-Corasick 自动机大小写敏感，全小写的两三字母拉丁别名不入自动机（词表里 `rs` 会让「rs 报告」命中 Rust），但 `JS`/`TS`/`ML` 这类大写缩写必须保留。
6. 单元测试不得依赖网络、数据库或大模型；外部依赖一律注入或打桩。
