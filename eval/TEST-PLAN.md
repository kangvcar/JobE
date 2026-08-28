# 职途罗盘 JobE · 测试方案

本文交给评委。指标口径按赛题三项准确率展开，并额外报告证据可溯源率与跨源确认率。金标准一经写入不得为抬分而改。

标注细则全文见 `eval/guidelines/`，此处只给评测时必须对齐的摘要。

---

## 1. 三项指标的精确定义

### 1.1 JD 解析准确率（分两层，禁止只报一个数）

**评测对象**：系统对职位正文（及 ATS 结构化字段）的抽取结果，JSONL，`id` 与 `eval/datasets/jd/gold.jsonl` 对齐。

**字段级严格匹配准确率**（目标 ≥ 95%）

- 字段：岗位标题、公司、城市、薪资下限、薪资上限、学历要求、经验要求。
- 一条字段计 1 当且仅当规范化后的 `value` 与金标准相等。
- 城市：去掉末尾「市」再比。薪资：整数、单位元/月。学历：`博士|硕士|本科|大专|不限`。双方皆空计正确。
- 汇总：七个字段、全部样本上的 micro 平均。同时逐字段报告，便于看是薪资错还是城市错。

**技能点级 P / R / F1**（严格匹配，目标 F1 ≥ 90%）

- 把每条职位的技能点变成规范名集合。
- 规范名按《技能点切分准则》与 `eval/lexicon/skills.py`；大小写不敏感比较前先按金标准 `name` 原样比（系统应输出规范名）。
- micro-P/R/F1（先汇总 tp/fp/fn）为主指标，macro-F1 附报。
- **不**用模糊匹配、不按别名自动加分——别名应在系统侧归一到规范名。

切分边界以准则为准，例如「熟悉 Hadoop/Spark/Flink」是三个技能点，「PyTorch 分布式训练」是两个，「有责任心」不是技能点。验收争议以准则正反例仲裁，不以模型输出为准。

### 1.2 简历提取准确率（两层 + 溯源）

金标准：`eval/datasets/resume/gold.jsonl`（合成简历，见第 2 节）。

- **字段级**（目标 ≥ 95%）：姓名、电话、邮箱、城市、学历。学历只需规范档位子串一致（本科/硕士/博士/大专）。
- **技能点级**（目标 F1 ≥ 90%）：同 JD，规范名集合 P/R/F1。
- **溯源准确率**（赛题未列、本方案必报）：对「预测与金标准同名」的技能点，同时满足：
  1. 字符区间与金标准完全一致；
  2. 若金标准有 bbox，则 IoU ≥ 0.5；
  3. `text[start:end]` 等于预测的 `surface_form`。
  大模型不得直接输出坐标（ADR 0003）；坐标必须由字符串匹配回填，匹配不上即抽取失败。

### 1.3 人岗匹配准确率

金标准：`eval/datasets/match/pairs.jsonl`、`ranking.jsonl`。

**主指标：档位一致率**（目标 ≥ 90%）

- 四档：高度匹配 `strong` / 基本匹配 `adequate` / 有明显差距 `gapped` / 不匹配 `mismatch`。
- 系统输出与专家（本集中即准则过程）同档计 1，micro 平均。

判定过程摘要（完整规则见 `guidelines/match-tier.md`，代码 `datasets/match/assign.py`）：

1. 覆盖率 `c` = 满足的核心必备技能数 / 核心必备技能数。软技能不进覆盖率。水平不够算 `insufficient`，**不算覆盖**。
2. R1 岗位族错位且方向覆盖 < 20% → 不匹配。
3. R2 `c < 0.30` → 不匹配。
4. R3 `c < 0.40` 且学历、经验都不满足 → 不匹配。
5. R4 `c ≥ 0.90` 且方向性必备缺失为 0，学历或经验至少一项满足 → 高度匹配。
6. R5 `c ≥ 0.70` 且方向性必备缺失 ≤ 1 → 基本匹配。
7. R6 `c ≥ 0.40` → 有明显差距。
8. 其余 → 不匹配。

**技能级判定准确率**：每条岗位技能点的 `satisfied | insufficient | missing` 是否与金标准相同，按条 micro 平均。用来回答「错在哪个技能上」。

**排序一致性**：20 组「一份简历 × 10 岗位」。系统给出 `role_ids` 序。

- Spearman：金标准名次与系统名次的等级相关（同向，越小越靠前）。
- NDCG@5：相关性 `strong=3, adequate=2, gapped=1, mismatch=0`。

### 1.4 额外两项（幻觉防控）

输入：系统结论 JSONL，每条结论带 `evidence[].span` + `quote` + `source_id`，或 `grade=multi_source`。

- **证据可溯源率**：结论中能在原文定位且 quote 一致的占比。无证据的结论按 ADR 0003 本就不应进图谱。
- **跨源确认率**：证据 `source_id` ≥ 2（或显式 `multi_source`）的结论占比。

脚本：`eval/metrics/evidence_trace.py`。

---

## 2. 评测集构造与规模

| 集 | 文件 | 规模 | 构造 |
| --- | --- | --- | --- |
| 职位原文 | `datasets/jd/raw/moka_postings.jsonl` | **991** | Moka 公开接口，关键词覆盖四方向 |
| JD 金标准 | `datasets/jd/gold.jsonl` | **128** | 四族×三层轮询；字段来自 ATS + 正文；技能点按准则词表最长匹配 |
| 简历 | `datasets/resume/gold.jsonl` + `pdfs/` | **64** | faker 个人信息 + 模板正文 + reportlab PDF；含多栏/页眉页脚/跨页/扫描件 |
| 匹配对 | `datasets/match/pairs.jsonl` | **220** | 锚点对 + 同族全配对候选，再按目标比例抽样；gapped 最多 |
| 排序 | `datasets/match/ranking.jsonl` | **20 组 × 10 岗** | 准则第 6 节键排序 |

当前金标准分层（抽样结果，不是字段评测对象）：

- JD 岗位族：ai 36、smart_system 36、bigdata 32、iot 24
- JD 层级：junior 48、senior 48、expert 32
- 简历版面：two_column 15、table_header 15、single_column 14、multipage 12、scanned 8
- 匹配档位：gapped 131、mismatch 46、strong 22、adequate 21（基本匹配偏少，因为 R5 的覆盖率窗口窄，**没有**为凑数改档）

JD 四方向：人工智能、大数据、智能系统、物联网。层级：初级 / 资深 / 专家（由标题关键词与年限启发式分层，分层标签不是抽字段金标准）。

---

## 3. 标注准则摘要与一致性

- 切分：可单独验证则标；斜杠列举必拆；工具+方法能分开验证则拆；品德态度不标；禁止脑补原文没有的专名。
- 档位：先算覆盖率与方向缺失，再按 R1–R7 顺序，阈值含等号，禁止四舍五入。

**标注流程（诚实说明）**

本轮没有两名独立人类标注员。实现了双人流程与 κ 计算，第一遍采用：

| 角色 | 文件 | 做法 |
| --- | --- | --- |
| 初标 annotator_a | `annotations/annotator_a.jsonl` | 规则抽取后注入准则里点名的典型错误（复合技能粘连、误标「责任心」、漏标部分通用技能），模拟大模型初标 |
| 复核 annotator_b | `annotations/annotator_b.jsonl` 与 `gold.jsonl` | 按词表最长匹配严格执行，作为金标准 |

κ 见 `datasets/jd/annotations/agreement.json`。计算单位是「文档 × 技能点是否出现」，词表为两名标注员的全局并集（含真阴性）。因此 κ 会偏高；请同时看 `mean_jaccard`（只在该篇出现过的技能点上）。本轮数值：κ = 0.9545，mean_jaccard = 0.9101，128 篇上有 86 处技能点分歧 / 1029 条篇内并集标签。单元测试见 `eval/tests/test_kappa.py`（含经典 2×2、κ=0.40 用例）。

这不是两名人类的 κ，不能解释成「标注员一致性已达生产级」。它证明：流程可跑、公式正确、初标与准则之间的分歧可量化。若补第二名人类，只需再写一份 `annotator_c.jsonl`，同一脚本可重算。

匹配金标准**没有**人工逐对拍脑袋：在简历技能与 JD 技能已按准则切好的前提下，档位由 `assign_tier` 唯一确定。这避免「为了系统好看而改档」。边界案例的单元测试在 `eval/tests/test_assign.py`。

---

## 4. 复现步骤

依赖单独写在 `eval/requirements.txt`，不改 `backend/pyproject.toml`。

```bash
cd /path/to/JobE
python3 -m venv eval/.venv
eval/.venv/bin/pip install -r eval/requirements.txt

# 一条命令：κ 单测 + 人造 pred 自测 + 写出 reports/
eval/.venv/bin/python eval/scripts/run_all.py
```

单指标（与赛题要求的命令形一致）：

```bash
uv run --python eval/.venv/bin/python eval/metrics/jd_parse.py \
  --pred <系统输出.jsonl> --gold eval/datasets/jd/gold.jsonl --out-dir eval/reports

uv run --python eval/.venv/bin/python eval/metrics/resume_extract.py \
  --pred <系统输出.jsonl> --gold eval/datasets/resume/gold.jsonl --out-dir eval/reports

uv run --python eval/.venv/bin/python eval/metrics/match_tier.py \
  --pred <系统pairs.jsonl> --gold eval/datasets/match/pairs.jsonl \
  --rank-pred <系统排序.jsonl> --rank-gold eval/datasets/match/ranking.jsonl \
  --out-dir eval/reports

uv run --python eval/.venv/bin/python eval/metrics/evidence_trace.py \
  --pred <系统结论.jsonl> --gold eval/datasets/jd/gold.jsonl --out-dir eval/reports
```

自测用的人造预测在 `eval/metrics/fixtures/`：故意改错城市、漏技能、错档位、错 span，脚本必须把这些错误写进 `*_errors.json`。

重建数据集：

```bash
eval/.venv/bin/python eval/datasets/jd/fetch_jd.py          # 需联网；不碰反爬平台
eval/.venv/bin/python eval/datasets/jd/annotate.py --seed 42
eval/.venv/bin/python eval/datasets/resume/generate.py --seed 42
eval/.venv/bin/python eval/datasets/match/construct.py --seed 42
```

简历生成固定 `seed=42`。换机器若中文字体不同，PDF 字节可能变化，但 gold 的字段值与技能名集合应保持稳定。

---

## 5. 局限性（请按此理解分数）

1. **JD 金标准技能点依赖词表**。词表外专名会漏标（`oov` 通道已留，本轮未做大规模人工补 OOV）。系统若抽出词表外正确专名，会被算成假阳性——这是裁判偏严，不是鼓励系统少抽。补救：按准则人工加词表后重标，**不**根据系统输出改金标准。
2. **字段 span 经常为空**。公司名、薪资多在 ATS 结构化列，正文未必出现。字段准确率比的是 `value`，溯源另算。
3. **职位族/层级是启发式标签**，用于抽样分层，不是评测字段。
4. **IoT 公开职位少于 AI**。抽样仍保证四族都有，但 IoT 池子更小，近重复风险更高。
5. **部分 Moka orgId 返回 500 或空列表**（如若干互联网大厂 slug 猜错）。缺口用已打通的芯片/智驾/安防/通信企业补量，未用招聘聚合平台填。
6. **合成简历的语言比真实简历干净**，扫描件是「有损 JPEG」而不是真实扫描仪畸变。OCR 路径的难度低于真实扫描件。
7. **匹配金标准与系统若实现同一套 R1–R7，档位一致率会接近 100%**。这测的是「有没有按公布的档位定义做事」，不是独立心理学家的打分。技能级判定仍能暴露水平阈值（insufficient vs satisfied）实现错误。
8. **κ 不是双人人类一致性**。见第 3 节。
9. **正文未用在线大模型生成**。为可复现而用模板。句式覆盖常见 JD 写法，但多样性低于真实长尾。
10. 采集文本是企业主动公开的招聘信息；二次分发评测集时仍应保持研究/竞赛用途，不要做成公开可检索的简历库（本集本来就没有真简历）。

---

## 6. 错误分析怎么用

每个指标脚本在 `--out-dir` 写下 `*_errors.json` 与 `*_report.md`。调系统时只看错误表：

- JD 假阳性：先查是否把「责任心」或未拆的「C/C++」整坨输出。
- JD 假阴性：先查词表漏召回、英文大小写未归一。
- 简历溯源失败：先查是不是模型编造了偏移，而不是字符串回填。
- 档位错误：看金标准 `rule` 字段，对一下覆盖率有没有把 insufficient 算进覆盖。
