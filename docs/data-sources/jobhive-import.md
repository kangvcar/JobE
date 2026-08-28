# jobhive 北森 / Moka 导入

只导入 jobhive 托管 parquet 的中国切片：北森（`beisen`）和 Moka（`moka`）。Ashby、TikTok 等海外切片不下、不导。`lvzyd3v` 镜像过时，不要用。

原包放 `data/datasets/jobhive/`（gitignore）。分析层仍只读快照。

## 清单

- Manifest：https://storage.stapply.ai/jobhive/v1/manifest.json（旧 URL 去掉 `/v1` 会 404）
- 北森：约 72,905 行，100% CN/zh
- Moka：约 31,743 行
- parquet URL 形如 `https://storage.stapply.ai/jobhive/v1/beisen/jobs.parquet`

本地文件名可以是 `{ats}.jobs.parquet`、`{ats}.parquet` 或 `{ats}.jsonl`。

## 下载

已有切片就别再下。没有的话：

```bash
cd backend
PYTHONPATH=. uv run python scripts/import_jobhive.py --ats both --download --max-items 20
```

`--download` 只在本地缺文件时才打 manifest。默认不封顶，每 500 条批量写入。

```bash
cd backend
PYTHONPATH=. uv run python scripts/import_jobhive.py --ats both
```

冒烟或限量：

```bash
PYTHONPATH=. uv run python scripts/import_jobhive.py --ats both --download --max-items 20
PYTHONPATH=. uv run python scripts/import_jobhive.py --ats beisen --max-items 2000
PYTHONPATH=. uv run python scripts/import_jobhive.py --ats moka --path ../data/datasets/jobhive/moka.jobs.parquet --flush-every 1000
```

## 来源

`source_id` 是 `jobhive_beisen` 与 `jobhive_moka`，不和现网 `moka` 官网采集抢主键。无参 `POST /api/collect/run` 不会跑这 10 万行；路由要显式 `source_id`，并且只读本地文件。
