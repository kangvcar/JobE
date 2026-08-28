# 职途罗盘 JobE · 评测体系

本目录完全属于评测模块，不改仓库其他文件。评委入口是 [`TEST-PLAN.md`](TEST-PLAN.md)。

```
eval/
  guidelines/          技能点切分准则、匹配档位判定准则
  lexicon/             切分用技能点词表
  datasets/jd/         ≥120 条真实职位 + 金标准 + 双人标注
  datasets/resume/     ≥60 份合成简历 PDF + 金标准
  datasets/match/      ≥200 对匹配 + 20 组排序
  metrics/             可独立运行的指标脚本
  tests/               Cohen's κ 与档位规则单元测试
  scripts/run_all.py   一条命令跑通评测自测
```

## 一条命令

```bash
python3 -m venv eval/.venv
eval/.venv/bin/pip install -r eval/requirements.txt
eval/.venv/bin/python eval/scripts/run_all.py
```

或（已有虚拟环境时）：

```bash
uv run --python eval/.venv/bin/python eval/metrics/jd_parse.py \
  --pred eval/metrics/fixtures/jd_pred.jsonl \
  --gold eval/metrics/fixtures/jd_gold.jsonl
```

## 重建数据集（可选）

```bash
eval/.venv/bin/python eval/datasets/jd/fetch_jd.py
eval/.venv/bin/python eval/datasets/jd/annotate.py
eval/.venv/bin/python eval/datasets/resume/generate.py
eval/.venv/bin/python eval/datasets/match/construct.py
```

采集只走 Moka 公开接口，不碰 BOSS / 智联 / 前程 / 猎聘。
