# JD 评测集

## 规模与来源

- 原始采集：`raw/moka_postings.jsonl`（Moka 公开接口 `GET https://api.mokahr.com/api-platform/v1/jobs/{orgId}?mode=social`，免鉴权）
- 评测子集：`gold.jsonl` 不少于 120 条，四岗位族 × 三层级分层抽样
- 未收录：描述不足 120 字、接口返回空 `description` 的职位

不采集 BOSS 直聘、前程无忧、智联招聘、猎聘。部分 orgId 返回 HTTP 500 或空列表，见 `TEST-PLAN.md` 缺口说明。

## Schema（JSONL，一行一条）

### `postings.jsonl`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | `jd_001` |
| source | string | 固定 `moka` |
| org_id / job_id / url | string | 可回访的公开页 |
| family | string | `ai` / `bigdata` / `smart_system` / `iot` |
| level | string | `junior` / `senior` / `expert` |
| text | string | HTML 去标签后的规范化正文，**span 的坐标系** |

### `gold.jsonl`

在 postings 字段之上增加：

```json
{
  "fields": {
    "title": {"value": "…", "span": {"start": 0, "end": 5}},
    "company": {"value": "…", "span": null},
    "city": {"value": "北京", "span": {"start": 11, "end": 13}},
    "salary_min": {"value": 20000, "span": {"start": 17, "end": 23}},
    "salary_max": {"value": 40000, "span": {"start": 17, "end": 23}},
    "education": {"value": "本科", "span": {"start": 24, "end": 26}},
    "experience": {"value": "3-5年", "span": {"start": 27, "end": 31}}
  },
  "skills": [
    {
      "id": "sk_001",
      "name": "PyTorch",
      "family": "ai",
      "surface_form": "PyTorch",
      "span": {"start": 40, "end": 47},
      "necessity": "required",
      "level_hint": 2,
      "oov": false
    }
  ],
  "annotation": {
    "origin": "guideline_review",
    "annotator": "annotator_b",
    "reviewed": true
  }
}
```

约束：`text[span.start:span.end] == surface_form`（有 span 时）。`span` 为 null 表示该值来自 ATS 结构化字段、正文未出现。

薪资金标准单位：**元/月**。Moka 接口的千元值已 ×1000。

学历规范值：`博士` / `硕士` / `本科` / `大专` / `不限`。

### 系统预测 `--pred` 最小字段

```json
{"id": "jd_001", "fields": {"title": {"value": "…"}, "city": {"value": "北京"}}, "skills": [{"name": "PyTorch"}]}
```

id 必须与金标准对齐。技能点 `name` 用切分准则规范名，严格匹配。

## 标注文件

| 文件 | 谁 |
| --- | --- |
| `annotations/annotator_a.jsonl` | 初标（规则抽取 + 模拟大模型典型错误） |
| `annotations/annotator_b.jsonl` | 按准则复核 = 金标准技能集合 |
| `annotations/agreement.json` | 技能点集合 Cohen's κ |

## 复现

```bash
python eval/datasets/jd/fetch_jd.py
python eval/datasets/jd/annotate.py --n 128 --seed 42
```
