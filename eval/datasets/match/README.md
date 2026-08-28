# 匹配评测集

档位由 `assign.py` **机械执行**《匹配档位判定准则》第 3 节，不手改。分布刻意不均衡，`gapped` 最多。

## 文件

| 文件 | 规模 | 内容 |
| --- | --- | --- |
| `pairs.jsonl` | ≥200 | 简历×岗位，四档 + 技能级判定明细 |
| `ranking.jsonl` | 20 组 | 一份简历 × 10 个岗位的专家序 |

## `pairs.jsonl` schema

```json
{
  "id": "pair_001",
  "profile_id": "resume_001",
  "role_id": "jd_012",
  "jd_family": "ai",
  "resume_family": "ai",
  "tier": "gapped",
  "rule": "R6",
  "coverage": 0.555556,
  "skill_judgments": [
    {"skill_name": "PyTorch", "required": true, "verdict": "satisfied", "held_level": 2, "required_level": 2},
    {"skill_name": "CUDA", "required": true, "verdict": "missing", "held_level": null, "required_level": 2}
  ],
  "surplus": [{"skill_name": "mqtt", "kind": "surplus", "held_level": 2}]
}
```

`tier` ∈ `strong` / `adequate` / `gapped` / `mismatch`，与 `MatchTier` 一致。

## `ranking.jsonl` schema

```json
{
  "id": "rank_01",
  "profile_id": "resume_001",
  "role_ids": ["jd_003", "jd_010", "…共10个"],
  "tiers": ["strong", "adequate", "gapped", "…"]
}
```

`role_ids` 已按准则第 6 节排好：档位 ↓、覆盖率 ↓、方向缺失数 ↑、id 升序。

## 系统预测

pairs：

```json
{"id": "pair_001", "tier": "gapped", "skill_judgments": [{"skill_name": "PyTorch", "verdict": "satisfied"}]}
```

ranking：

```json
{"id": "rank_01", "role_ids": ["jd_003", "jd_010", "…"]}
```

## 复现

```bash
python eval/datasets/match/construct.py --n-pairs 220 --n-rank 20 --seed 42
```
