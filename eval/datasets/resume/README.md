# 合成简历评测集

**不使用真实简历。** 简历是个人信息高密度聚合体，公开中文简历数据集（如 Chinese Resume NER）也没有技能点标注，且无法提供页面坐标。本集用构造法同时得到字段、技能点、字符区间和 bbox，这是评测「溯源准确率」的前提。

## 规模

不少于 60 份 PDF，难度分层：

| layout | 含义 |
| --- | --- |
| single_column | 单栏 |
| two_column | 多栏 |
| table_header | 页眉页脚 + 技能逐条排版 |
| multipage | 工作经历跨页 |
| scanned | 栅格化 JPEG 再包回 PDF，走 OCR 路径 |

个人信息：`faker` 语言 `zh_CN`。正文：模板植入技能点**原文**，不在线调用大模型，以保证 `seed=42` 可复现。

## Schema（`gold.jsonl`）

```json
{
  "id": "resume_001",
  "difficulty": "easy",
  "layout": "single_column",
  "family": "ai",
  "level": "senior",
  "pdf_path": "pdfs/resume_001.pdf",
  "text": "阅读序规范化文本",
  "years": 5,
  "fields": {
    "name": {"value": "…", "span": {"start": 0, "end": 2}, "bbox": [48, 56, 80, 74], "page_index": 0},
    "phone": {},
    "email": {},
    "city": {},
    "education": {"value": "硕士", "span": {}, "bbox": [], "page_index": 0}
  },
  "skills": [
    {
      "name": "PyTorch",
      "family": "ai",
      "level": 2,
      "surface_form": "PyTorch",
      "span": {"start": 120, "end": 127},
      "bbox": [36, 200, 80, 210],
      "page_index": 0
    }
  ]
}
```

- 坐标系：页面左上角为原点，单位 PDF 点（1/72 英寸），`bbox = [x0, y0, x1, y1]`。
- `level`：0–3，与领域模型 `ProfileSkill.level` 一致。
- 扫描件的 bbox 仍用排版时的 PDF 点，不随 JPEG 像素放大。

## 系统预测 `--pred`

```json
{"id": "resume_001", "fields": {"name": {"value": "…", "span": {"start": 0, "end": 2}, "bbox": [48, 56, 80, 74]}}, "skills": [{"name": "PyTorch", "surface_form": "PyTorch", "span": {"start": 120, "end": 127}, "bbox": [36, 200, 80, 210]}]}
```

## 复现

```bash
python eval/datasets/resume/generate.py --seed 42 --n 64
```

两次运行在同一字体环境下 PDF 与 `gold.jsonl` 应一致。字体优先 `Arial Unicode.ttf`，否则 macOS 冬青黑体。
