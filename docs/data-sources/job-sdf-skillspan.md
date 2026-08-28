# Job-SDF 与 Chinese-SkillSpan 实测

验证日期：2026-08-28。数据原包在 `data/datasets/`（已被 gitignore，本报告可入库）。没有改 `backend/app`，没有把 parquet / JSON 提交进 git。

JobE 对照基准：职位原子字段 `title, company, city, published_at/updated_at, salary_min/max, description, occupation_code`（`backend/app/domain/models.py` 的 `Posting`）；技能抽取必须有正文；演化要多年历史或月度技能需求时序（`backend/app/evolution/`，时间片 `YYYYQn`）；本体 `ontology/data/skills.jsonl` 实测 822 行，`aliases.jsonl` 2174 行。

## 总评

| 数据集 | 判定 | 一句话 |
| --- | --- | --- |
| Job-SDF | **部分可用**（只对演化算法，不对图谱技能点） | 公开仓确有 2021-01–2023-12 月度需求/占比/共现；**没有原始 JD，技能名称表仍被隐去**。`ontology/README.md` 那句话仍然成立。 |
| Chinese-SkillSpan | **部分可用**（只对抽取评测，不对演化） | Google Drive 公开了标注，但**不是论文声称的完整 2 万+ 句**；有句级正文、部分发布时间、岗位名；**没有 ESCO concept ID、没有薪资、没有职业编码**；train 文件零标注。 |

下一步：Job-SDF 先向作者要 `entity_map`（否则进不了 822 点本体）；Chinese-SkillSpan 先写抽取评测导入器，并邮件要完整 train、Doccano 原始 JSONL、许可全文和 ESCO 对齐表。

---

## 1. Job-SDF

### 1.1 怎么拿到的

- 论文：https://arxiv.org/abs/2406.11920（NeurIPS 2024 D&B）；主页 https://job-sdf.github.io/ 写明基于中国招聘平台 **1035 万**条公开广告、**2021–2023**、**2324** 种技能、**521** 家公司。
- 2026-08-28 执行：`git clone --depth 1 https://github.com/Job-SDF/benchmark.git` → `/Users/kangvcar/Documents/code/JobE/data/datasets/job-sdf/`
- HEAD：`00583fc0b0c70b4ed8df6d579e760e89d57ddbb1`（2026-05-15，`Update contact email for data access in README`），分支 `main`。
- 体积：整仓约 **219 MB**（含 `.git` 约 90 MB）；`dataset/` 约 **131 MB**。

### 1.2 实际文件（无 `entity_map`，无 LICENSE 文件）

`dataset/` 下实测目录只有五个：`demand/`、`proportion/`、`graph/`、`structural_breaks_index/`、`low_frequency_index/`。README 画的 `entity_map/` **不存在**（`ls` 与 `git ls-files` 都没有）。仓根也没有 `LICENSE*`。

README 原文（`data/datasets/job-sdf/README.md` 第 66 行）：

> The specific name index tables of L1 occupations, L2 occupations, regions, and skills are stored here. In order to protect privacy information, we have hidden this part of the data. If you need it, you can contact the first author's email (chenxi0401@mail.ustc.edu.cn).

论文 HTML/PDF 另写许可为 **CC BY-NC-SA 4.0**，但公开 git 树里没有许可证文件。NC = 不能商用分发；SA = 衍生必须同等共享。本地放进 gitignore 目录可以，**不能写入 JobE 仓库、不能当商用图谱的技能名来源**。

粒度文件名与论文对应（`metrics/multi_result.ipynb` 把 `r1`/`r2` 替换成 L1/L2 occupation）：

| 文件茎 | 粒度 | 论文规模 |
| --- | --- | --- |
| `r0` | 未在 README 规模表出现；代码默认 `data_name=r1`，`r0` 多半是全局/不分职业的技能序列 | — |
| `r1` | L1 职业 | 14 |
| `r2` | L2 职业 | 52 |
| `company` | 公司 | 521 |
| `region` | 区域 | 7 |
| `r1-region` / `r2-region` | 职业 × 区域 | — |
| 技能 | 每张需求表都有 `skill_id` | 论文 2324；**文件里 2335** |

`demand/` 与 `proportion/` 各 7 个 parquet；`graph/` 同样 7 个。另有 `low_frequency_index/*.json`（低频技能下标列表，`company.json` 最大，约 69 万个整数）和 `structural_breaks_index/*.json`（结构断点技能下标，`company.json` 44222 个）。

`demand` 与 `proportion` 行数完全一致（pyarrow `ParquetFile.metadata.num_rows`，2026-08-28 实测）。**`skill_id` 唯一值是 2335（0…2334），不是论文写的 2324**，多 11 个匿名 ID。

| 文件 | 行数 | 实体唯一值 × 技能 | 体积 |
| --- | --- | --- | --- |
| `demand/r0.parquet` | 2 335 | `r0_id` 唯一值 1（恒为 0）× 2335 | 278K |
| `demand/r1.parquet` | 32 690 | L1 14 × 2335 | 1.2M |
| `demand/r2.parquet` | 121 420 | L2 52 × 2335 | 2.8M |
| `demand/region.parquet` | 16 345 | 区域 7 × 2335 | 891K |
| `demand/r1-region.parquet` | 228 830 | 14 × 7 × 2335 | 4.3M |
| `demand/r2-region.parquet` | 849 940 | 52 × 7 × 2335 | 8.7M |
| `demand/company.parquet` | 1 216 535 | 公司 521 × 2335 | 14M |
| `graph/r0.parquet` | 60 804 | 边；`row_id`/`col_id` 各 314 个不同点 | 407K |
| `graph/r1.parquet` | 200 736 | | 1.3M |
| `graph/r2.parquet` | 321 374 | | 1.9M |
| `graph/region.parquet` | 218 840 | | 1.3M |
| `graph/company.parquet` | 1 651 096 | | 9.0M |
| `graph/r1-region.parquet` | 489 846 | | 2.7M |
| `graph/r2-region.parquet` | 689 460 | | 3.8M |

抽样（`demand/r0.parquet`）：`skill_id=0` 在 2021-01 / 2021-12 / 2023-12 的需求是 **63.0 / 125.0 / 43.0**；`skill_id=3` 是 **0.0 / 2.0 / 51.0**。单元格是浮点计数，不是文本。

### 1.3 Schema

`demand/r0.parquet` 的 pandas 列：`r0_id` (int64)、`skill_id` (int64)、然后 **36 个** `YYYY-MM` 列 `2021-01` … `2023-12` (float64)。一共 38 列。

其余 demand/proportion 同构，只换实体列：

- `r1.parquet`：`r1_id, skill_id, 2021-01 … 2023-12`
- `r2.parquet`：`r2_id, skill_id, …`
- `company.parquet`：`company_id, skill_id, …`
- `region.parquet`：`region_id, skill_id, …`
- `r1-region.parquet`：`r1_id, region_id, skill_id, …`（39 列）
- `r2-region.parquet`：`r2_id, region_id, skill_id, …`

加载器 `benchmark/multivariate_time_series/data_provider/data_loader.py` 把不含 `id` 的列当时间、转置后按 **27 / 3 / 6** 切 train/val/test，合计 36 个月，与列名一致。

`graph/r0.parquet` 列只有 `r0_id, row_id, col_id`（外加 pandas 索引列）。**没有 frequency 列**。README 写三元组 `(skill_id_1, skill_id_2, 共现次数)`，公开文件对不上；图方法 notebook 也只用 `row_id`/`col_id` 当边。共现是无权重邻接，或次数被丢掉了。

`structural_breaks_index/r0.json` 是整数列表，长度 1510，样例 `[0, 3, 5, 6, 7, 8, 10, 12]`——技能下标，不是名称。

全文检索 demand parquet：**没有职位描述字符串，没有公司名、职业名、城市名、技能名**。只有整数 ID 和月份数值。

### 1.4 对 JobE 演化模块

`SkillObservation` 要 `skill_id, period, weight, posting_count, total_postings, ontology_version`。Job-SDF 能直接喂的是：

- `demand` 单元格 → `posting_count`（该月该技能出现次数）
- `proportion` 单元格 → `weight`（0–1 占比）
- `YYYY-MM` → 聚成 `YYYYQn`（三个月相加/再归一）
- `graph` 的 `(row_id, col_id)` → `evolution/cluster.py` 的 `Cooccurrence`，但端点是匿名整数

**不能做的：**

- 映射到 `skill.pytorch` 这类本体 slug：没有名称、没有别名。
- 当 `Posting` 导入：没有 `description`，技能抽取链路用不上。
- 填 `occupation_code`：职业是作者自有 L1/L2 ID，不是大典编码。
- 在不知道技能名的情况下发布图谱变更：突增/领先滞后可以在匿名 ID 上跑通单元测试级流水，但产品结论无法点名。

有名称表之后，才值得写「Job-SDF → SkillObservation」导入器，并且必须冻结 `ontology_version`，用别名表做一次离线对齐，对不上的 ID 单独命名空间（例如 `skill.jobsdf.{id}`），不要硬塞进 822 点。

### 1.5 `ontology/README.md` 那句话还成不成立

**仍然成立。** 2026-05-15 的公开树依然：无原始职位文本、`entity_map` 被隐去、无 License 文件。名称表仍须写信给 `chenxi0401@mail.ustc.edu.cn`。

---

## 2. Chinese-SkillSpan

### 2.1 论文怎么说

- arXiv: https://arxiv.org/abs/2604.23009 （html 同样可开；2026-04-24 preprint）
- 资源页：https://sites.google.com/view/cn-skillspan-resources
- 作者通讯：Guojing Li `guojingli3-c@my.cityu.edu.hk`，Xiangyu Zhao `xianzhao@cityu.edu.hk`
- 论文数字：train **17460** / dev **2143** / test **3237** 句；来源四个招聘流，**2014–2025**；声称 span 对齐 **ESCO concept ID**，放出 Silver/Gold、IID 与 industry/time-shifted OOD。
- 附录只有标注指南 PDF，**没有数据包**。

### 2.2 试过哪些 URL（失败也记下）

| URL | 结果 |
| --- | --- |
| https://sites.google.com/view/cn-skillspan-resources | **200**。摘要 + 两个按钮：Code / Data。无 HuggingFace、无 GitHub 仓链接。页面 `data-last-updated-at-time=1761637947876` ≈ 2025-10-28。 |
| `.../data` `.../download` `.../code` | **404** |
| Data 文件夹 https://drive.google.com/drive/folders/13YzsGeJ37qQ2scc2p0HPAPK0OPQWFMEl | **200**，标题 `database`，无需申请。未出现 “You need access”。 |
| Code 文件夹 https://drive.google.com/drive/folders/1MTI3E3PPq2LGLO9RxoRoj9A4JSTcapjB | **200**，标题 `Code` |
| `drive.google.com/uc?export=download&id=<folder>` | **500**（folder id 不能当文件下） |
| HuggingFace `api/datasets?search=chinese-skillspan` | **200，空列表** |
| HuggingFace `search=skillspan` | 只有英文 SkillSpan（`jjzha/skillspan`，CC BY 4.0）等，**不是** Chinese-SkillSpan |
| GitHub search `Chinese-SkillSpan` | **429** 限流；后续也未发现官方镜像仓。Code 的 README 写 `git clone ...` 但没给 URL |
| https://arxiv.org/src/2604.23009 | **200**，gzip 2.59 MB。解开只有 tex、bib、指南 PDF/图。**没有 json/jsonl 标注** |
| 论文 HTML 正文 | 数据入口只指向上述 Sites |

源码包落到 `data/datasets/chinese-skillspan/arxiv-source/`。探测日志在 `data/datasets/chinese-skillspan/_attempts/`。

### 2.3 真正下载到的文件

`gdown` 把两个公开文件夹拉到：

```
data/datasets/chinese-skillspan/gdrive-data/   # Drive 显示日期 2025-10-28
  CN_skillspan_lkst_dev.json     5.1 MB
  CN_skillspan_lkst_test.json    6.3 MB
  CN_skillspan_lkst_train.json   1.0 MB
data/datasets/chinese-skillspan/gdrive-code/
  README.md  Guideline.md  main.py  prompt_template_rag.py  convert_to_lkst_alpaca.py
```

整包约 **18 MB**。Drive / Code / Sites **都没有 LICENSE 文件**。论文只说 “publicly available”，许可不明，**不能写入 JobE git**。

### 2.4 实测 schema 与行数（与论文对不上）

**dev.json**（Alpaca）：**2142** 条（论文 2143，差 1）。字段 `instruction, input, output, id, meta`。`meta` 键：`id, title, job_id, sent_id, global_id, source_main, 工作城市, source_domain, sentence_order, 招聘发布日期`。

样例（`CN_skillspan_lkst_dev.json` 第 1 条）：

- `input`：` 4、实验室系统的服务器基础架构管理、服务流程建立和管理，系统的数据系统恢复计划测试；`
- `output`：用 `@@…##S` 包技能片段
- `meta.title`：`IT工程师(博瑞生物医药(苏州)股份有限公司)`
- `meta.工作城市`：`苏州`
- `meta.招聘发布日期`：`44041`（Excel 序列日；epoch `1899-12-30` 转成 **2020-07-29** 附近）

dev 全部来自 `人工智能招聘`；200 个 `job_id`；1744/2142 句带至少一处 span；span 计数 **7488**（S 3737 / K 2647 / T 1070 / L 34）。日期覆盖 **2016-06-04 – 2025-01-02**，2142 条都有日期。按职位拼句后，平均正文约 **433** 字（最少 69，最多 2016），每岗约 10.7 句。

**test.json**（Alpaca）：**2676** 条（论文 3237，少 **561**）。200 个 `job_id`，与 dev **零重叠**。领域：`人工智能招聘` 1407、`事业单位招聘` 812、`阿里云公开数据集` 457。有日期的只有 1407 条（全是「人工智能招聘」，**2016-06-10 – 2025-03-04**）；阿里云与事业单位的 `招聘发布日期` 为空。span **6070**（S 3258 / K 1713 / T 1062 / L 37）。

**train.json**（另一套 NER 形状）：**1204** 条（论文 17460）。字段 `id, global_id, sent_id, sentence, tokens, skill_spans, tags_skill, tags_skill_clean, sentence_with_tags, source_domain`。

- `skill_spans` / `tags_skill` / `tags_skill_clean` **全部空列表**（1204/1204）
- 无 `title`、无城市、无日期
- 82 个 `global_id`；与 dev 重叠 8、与 test 重叠 15
- 开头几句是「2018年已经来了」「北京奥运会原来已经过去10年了」——不是任职要求；约 478/1204 句带「负责/熟悉」等招聘套话，但仍无标注

**论文承诺 vs Drive 实物：** 标注句大约 2142+2676=**4818**，不是 22840；train 名不副实；没有 Silver 层、没有独立 OOD 文件、没有 data card。Drive 文件日期 2025-10-28，早于 arXiv 2026-04-24，很像投稿前的不完整快照，不是论文附录里那份「完整释放」。

### 2.5 ESCO 对齐了没有

没有 concept ID 字段。`instruction` 里反复出现「ESCO-1.20」「LKST」，所以全文搜索会误报 “有 ESCO”。标注本身只有 **L/K/S/T 四类**。论文「aligned to ESCO concept IDs」在这份 Drive 包里**没兑现**。

用本体别名做精确表面匹配：dev+test 共 **13558** 个 span、**8166** 种表面形式，命中 `aliases.jsonl` **488** 次（3.6%），落到 **119** 个技能点。高频命中：`skill.python` 31、`skill.machine-learning` 28、`skill.java` 24。大多数中文职责短语（「服务器基础架构管理」）对不上 822 点，这是粒度差，不是导入器写错。

### 2.6 对 JobE 字段

| Posting 字段 | Drive 包里有没有 |
| --- | --- |
| `description` | **有**。句级 `input`/`sentence`；按 `job_id` 拼接能得到短 JD（平均几百字，不是完整招聘页） |
| `title` | **有**（dev/test 的 `meta.title`，公司名夹在括号里） |
| `company` | **可解析**，从 title 括号拆；无独立字段 |
| `city` | **有** `工作城市`（dev 36 城；test 73 城） |
| `published_at` | **部分有**。Excel 序列日；仅「人工智能招聘」。事业单位/阿里云无日期 |
| `salary_min/max` | **无** |
| `occupation_code` | **无** |
| 技能金标 | **有** LKST span（dev/test）；**无** ESCO URI；train 无标 |

400 个带标职位散在 2016–2025，构不成月度技能需求矩阵，**喂不了** `burst.py` / `leadlag.py` 所要的同期 `posting_count/total_postings` 序列。它的价值是抽取器的中文 span 金标，以及别名覆盖率体检。

Code 仓是 LLM 抽技能框架（`chinese_skillspan` 提示词、RAG/kNN），不是数据集本身。`Guideline.md` 第 29 条写导出 `spans{start,end,label,text}` 并保持 IID/OOD——Drive 里的 Alpaca 没有 start/end 偏移，只有 `@@ ##` 插入标记。

---

## 3. 验证题逐条

**有没有职位描述正文？**  
Job-SDF：没有。Chinese-SkillSpan：dev/test 有句级正文，可拼成短 JD；train 有句子但无标，且混进非 JD 文本。

**有没有发布时间？**  
Job-SDF：有月列 2021-01–2023-12，但是技能×实体的计数，不是每条职位的 `published_at`。Chinese-SkillSpan：仅「人工智能招聘」有 Excel 日期；覆盖约 2016-06 至 2025-03。

**技能标签/时序能否对齐 JobE 本体？**  
Job-SDF：不能，名称被隐。Chinese-SkillSpan：四类 span 可当抽取评测；精确别名只能盖住约 3.6% 的 span、119/822 个点。没有 ESCO ID 也就没有官方对齐表。

**许可能不能写入仓库？**  
`data/datasets` 已 gitignore，原包不要提交。Job-SDF 论文写 CC BY-NC-SA 4.0、仓内无 LICENSE，**NC 禁止商用再分发**。SkillSpan **无许可文件**，默认不能再分发。报告可以提交。

---

## 4. 给 JobE 的建议

**先导入哪一层**

1. **Chinese-SkillSpan 的 dev/test** → 抽取评测集，不是生产图谱。导入器：按 `job_id` 拼 `description`；`title` 去括号得岗位名、括号内当 `company`；`工作城市` → `city`；Excel 序列 → `published_at`（缺日期就空着）；`source_id` 新登记例如 `chinese-skillspan`。span 从 `output` 的 `@@…##[LKST]` 反推字符偏移，写入 `Evidence`，**不要**把 L/K/S/T 直接当成 `skill.pytorch`。能命中别名的再挂本体，否则只保留 span 文本。
2. **Job-SDF 的 `proportion`（其次 `demand`）** → 仅在拿到 `entity_map` 之后，写成 `SkillObservation` 月序列再滚成季度。先做 `r1`（14 个 L1 职业 × 2335 个 `skill_id`，32 690 行，文件 1.2M）做通路，再上 company。`graph` 可给 `cluster.py` 当共现先验，但边无权重、点无名称；`graph/r0` 只有 314 个点出现在边上，不是全量 2335。

**导入器怎么写（还不要改代码，这里只定口径）**

- SkillSpan：`Snapshot.payload` 存整条 Alpaca 记录；分析层只读快照。Excel 日期转换写死 epoch，并在快照里保留原始整数。
- Job-SDF：不要假装是 `Posting`。新来源类型「预聚合时序」，直接落 `SkillObservation`。月份 `2021-01` → `2021Q1` 时三个月的 count 相加、proportion 按 count 加权，不要对比例做算术平均。
- 两套都不要进 Neo4j 岗位节点，除非名称对齐已经过人工抽检。

**不能做什么**

- 不能用 Job-SDF 补「有正文的历史招聘」。
- 不能把 2335 个匿名 ID 当成 822 点本体的超集。
- 不能用 SkillSpan 的 400 岗做全国技能演化；时间轴有，样本密度没有。
- 不能把 Drive 里的 `train.json` 当金标（零 span）。
- 不能把英文 HuggingFace `jjzha/skillspan` 当成 Chinese-SkillSpan。
- 不能把这些原包 commit 进 git。

**还要向作者要的**

- Job-SDF：`entity_map`（技能/L1/L2/地区/公司名称），以及 git 仓补一份 LICENSE。
- Chinese-SkillSpan：完整 train（17460）、带 start/end 的 Doccano JSONL、ESCO concept 映射表、OOD 划分文件、许可（CC 或研究专用），并确认 Drive 是否只是 Gold 子集。

---

## 5. 本机路径速查

```
data/datasets/job-sdf/                  # git clone Job-SDF/benchmark
data/datasets/job-sdf/dataset/demand/
data/datasets/job-sdf/README.md         # entity_map 隐去说明
data/datasets/chinese-skillspan/gdrive-data/CN_skillspan_lkst_{dev,test,train}.json
data/datasets/chinese-skillspan/gdrive-code/
data/datasets/chinese-skillspan/arxiv-source/
data/datasets/chinese-skillspan/_attempts/   # HTTP 探测页
```
