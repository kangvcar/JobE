# 职途罗盘技能本体

中文 IT 技能点词表、别名表，以及《职业分类大典》与人社部新职业名单的骨架。这是图谱里跨时间比较必须钉死的那一层：技能点切多大、别名怎么归、职业编码怎么挂，都写在这里。

本体版本见 `VERSION`。跨时间片比较技能点集合时，只用同一版本。

数据许可是 [CC BY 4.0](LICENSE-DATA)。编目源在 `catalog/`，构建脚本在 `scripts/`，可直接引用的成品在 `data/`。

## 成品规模（0.1.0）

| 文件 | 条数 |
| --- | --- |
| `data/skills.jsonl` | 822 个技能点 |
| `data/aliases.jsonl` | 2180 条表面形式 |
| `data/clusters.jsonl` | 36 个技能簇 |
| `data/occupations.jsonl` | 大典骨架（8 大类 / 79 中类 / 449 小类 / 公示稿 1636 细类 + 已知工种） |
| `data/new_occupations.jsonl` | 七批已发布 110 个新职业 + 第八批公示 12 个新职业与 4 个新工种 |

四个方向的技能点数量：人工智能 478，大数据 148，智能系统 112，物联网 84。人工智能按岗位实际堆栈做深，其余三个方向只铺骨架，不追求工具穷尽。

## 怎么复现

需要 Python 3.11+，只用标准库。仓库根目录执行：

```bash
# 1. 下载第三方原文（写入 ontology/raw/，该目录不入库）
uv run python ontology/scripts/download.py linguist
uv run python ontology/scripts/download.py onet

# 2. 生成 data/*.jsonl
uv run python ontology/scripts/build.py

# 3. 校验
uv run python ontology/scripts/validate.py
```

`download.py` 与 `build.py` 分开。没有 `raw/` 时，`build.py` 仍能从 `catalog/` 编目生成词表，只是不会挂上 Linguist 别名和 O\*NET 外部编号。两次 `build.py` 对同一编目与同一 `raw/` 的输出字节级一致。

`validate.py` 检查：技能点 id 唯一、别名不跨技能点冲突、`parent_id` 引用存在且无环、必填字段齐全、已发布新职业恰好 110 条且每条有公示日期和官方链接。

## 技能点长什么样

稳定、人可读的 slug，例如 `skill.pytorch`。不要 UUID，本体要能被引用和 diff。

```json
{
  "id": "skill.pytorch",
  "name": "PyTorch",
  "name_zh": "PyTorch",
  "name_en": "PyTorch",
  "aliases": ["pytorch", "torch", "Pytorch", "PYTORCH", "torch.nn"],
  "parent_id": "skill.deep-learning",
  "cluster": "cluster.ml-framework",
  "direction": "ai",
  "sources": ["curated", "onet", "llm"],
  "external_ids": {"onet": "PyTorch", "onet_hot": "Y"},
  "ontology_version": "0.1.0"
}
```

`parent_id` 借 ESCO 的 SKOS broader/narrower：只表示技能点之间的上位，不是能力项。能力项是岗位上的陈述层，不进这个目录。

`aliases.jsonl` 是表面形式到技能点 id 的映射，抽取时用。一条表面形式只能指向一个技能点。

消歧：`Go` / `R` / `C` 这些单字母或与动词同形的串不进别名表。Go 语言只收 `Golang`、`Go语言`；R 只收 `R语言`、`GNU R`。`Agent` 单独出现也不收，只收 `智能体`、`AI Agent`。

## 数据来源

### 技能点层（自建）

这是核心。每条技能点都是编目里手写的中英文名、簇、方向和父节点，不是从某个词表原样倒进来的。

**不采用 Job-SDF / Chinese-SkillSpan。** 公开仓没有技能名称表、没有原始职位正文，不能当本体锚点，也不做历史序列或抽取评测导入。IT 技能点规模由编目自己收口，不挂外部数据集。

**O\*NET 31.0 Software Skills。** https://www.onetcenter.org/database.html ，[CC BY 4.0](https://www.onetcenter.org/license_db.html)。文件 URL：`https://www.onetcenter.org/dl_files/database/db_31_0_text.zip` 内 `Software Skills.txt`（31821 行）。这是职业分类标准里最接近技能点粒度、许可也最宽的一份。构建时按英文名或已有别名精确匹配 Workplace Example，命中则写入 `external_ids.onet`，热门技术加 `onet_hot=Y`。没有把 Excel / Word / Outlook 这类通用办公软件收进本词表：方向是新一代信息技术，不是全职业工具清单。本词表对 O\*NET 做了筛选和中文命名，不是 O\*NET 原文再分发。署名：This ontology includes information from the O\*NET 31.0 Database by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA), used under the CC BY 4.0 license. O\*NET® is a trademark of USDOL/ETA. JobE has modified this information. USDOL/ETA has not approved, endorsed, or tested these modifications.

**GitHub Linguist `languages.yml`。** https://github.com/github-linguist/linguist ，MIT。编程语言技能点用它的 `aliases` 和语言名做别名扩展，例如 Go 语言的 Linguist 名是 `Go`，我们只吸收其 aliases，不把歧义的 `go` 写进映射表。

### 别名表（自建，开源世界里没有现成的中文 IT 别名表）

编目手写的中英变体 + Linguist aliases + 构建脚本里标注 `source: llm` 的一批扩充（`catalog/skills.py` 的 `LLM_ALIASES`）。LLM 别名必须再经人工校验才能当金标准，所以单独标来源。

计划中但 0.1.0 **未跑通**的两路：

- Wikidata SPARQL 批量拉框架/工具类实体的中英文 `skos:altLabel`。脚本入口留在 `download.py wikidata`，查询清单未完成。
- ESCO v1.2.1 的 `altLabel`。下载页 https://esco.ec.europa.eu/en/use-esco/download 要填邮箱拿链接，这次没有拿到数据包。

**不要用** `TeamStuQ/skill-map`（无 License，2023-01 停更）和 `funNLP`（无 License，已停更）。这两份都没进本目录。

#### 哪些表面形式被故意排除

`scripts/build.py` 的 `BLOCKED_SURFACES` 按 casefold 屏蔽歧义表面形式。别把它们当成"漏掉的别名"加回来——每一条都是实测会误命中的：

| 屏蔽项 | 在中文技术文本里的主导含义 |
| --- | --- |
| `sd` | SD卡、SD-WAN、标准差（会误判成 Stable Diffusion） |
| `tf` | TF卡（会误判成 TensorFlow）。`TF-IDF` 由最长匹配单独命中 `skill.tfidf`，不受影响 |
| `go` `r` `c` | 普通英文词与单字母 |
| `ch` | 通道、章节 |
| `agent` | 中介、代理人 |

判据是缩写在中文技术文本里的**主导**含义：`JS`/`TS`/`ML`/`AI` 主导含义就是技术，予以保留；上面这些不是。抽取侧还有一层结构性保护——全小写的两三字母拉丁别名不进 Aho-Corasick 自动机（见 `docs/ARCHITECTURE.md` 跨模块规则 7）。

另外这几条曾被错当别名，已从编目里删除，同理不要加回：

- `ESP8266` 不是 `ESP32` 的别名（是另一颗芯片，要收就单独立技能点）
- `TiKV` / `TiFlash` 不是 `TiDB` 的别名（是 TiDB 体系里独立的组件）
- `稳扩散` 是臆造译名，没人这么写 Stable Diffusion

### 技能上层骨架

借 ESCO v1.2.1 的 SKOS 关系模型（broader/narrower、altLabel、可迁移性分级的思路），**不翻译**它的 13939 条技能。ESCO 粒度停在「使用 Python 编程」，下探不到 PyTorch。IT 技能子集的 CSV 因下载要邮箱，0.1.0 未吸收具体 URI。`parent_id` 和 `cluster` 是我们按这个模型自建的层级。

### 职业分类骨架

《中华人民共和国职业分类大典（2022年版）》。官方没有结构化下载。本次从社会公示稿抽出 8 大类、79 中类、449 小类、1636 条细类编码与名称，源文件在 `catalog/occupation_extract.json`。

口径差异必须记下：公示稿写 1636 个细类，正式发布口径是 **1639** 个职业。以 1639 为准。差的 3 条名称待对照纸质正式版补入。数字职业官方 97 个、绿色职业 134 个；公示稿正文用 S / L 标出的分别是 89 和 123，差额同样待对照正式版补旗标。

与新一代信息技术相关的小类精抽到职业级，并挂上已知工种（如人工智能训练师下的数据标注员、人工智能算法测试员）。其余细类保留编码和名称，`is_placeholder=true`。

信息技术相关编码优先看：`2-02-10` 信息和通信工程技术人员、`2-02-38` 数字技术工程技术人员、`4-04` 信息传输、软件和信息技术服务人员、`6-25` 计算机、通信和其他电子设备制造人员。

### 人社部新职业

2019 年以来七批共 110 个已发布新职业，第八批 12 个在公示中（含数字孪生工程技术人员、具身智能机器人应用技术员；新工种含智能体开发员）。每条有 `public_comment_date` 和 `official_url`。这份名单是「新兴岗位发现」的裁判基准：系统要能在官方公示之前从招聘数据里看见它们。

`date_status=verified` 表示找到了公示通告日期。`published_fallback` 表示没找到该批公示通告原文，字段暂填正式发布日，待对照人社部官网补公示起始日。涉及第二、三、四、七批。

官方入口：中国就业网 https://chinajob.mohrss.gov.cn/ ，中国政府网部门文件库 https://www.gov.cn/ 。

## 目录

```
ontology/
├── README.md
├── LICENSE-DATA          # CC BY 4.0 全文
├── VERSION
├── requirements.txt      # 故意留空：脚本只用标准库
├── catalog/              # 编目源，改词表从这里改
├── data/                 # 构建产物，可直接引用
├── scripts/
│   ├── download.py
│   ├── build.py
│   └── validate.py
└── raw/                  # 下载物，gitignore
```

改技能点：编辑 `catalog/skills_ai.py`、`skills_ai_more.py`、`skills_other.py`，然后重跑 `build.py` 和 `validate.py`。不要手改 `data/*.jsonl`。

## 版本策略

`VERSION` 是本体版本号，写入每条记录的 `ontology_version`。新增或删除技能点、改 parent、改别名归属，都要升版本。只修文档或脚本、数据字节不变，可以不升。

建议：0.x 允许打破兼容（合并 slug、删点）；1.0 起删点必须留 deprecated 映射，否则历史时间片对不上。

## 待补充

1. ESCO v1.2.1 信息技术技能子集的 URI 与 altLabel（下载要邮箱）。
2. Wikidata 别名批量查询清单。
3. 大典正式版相对公示稿多出的 3 个职业名称，以及数字职业 97 / 绿色职业 134 与公示稿 S/L 标记的差额。
4. 第二、三、四、七批新职业的公示通告原文日期。
5. `source: llm` 的别名人工通审。29 条 LLM 来源技能点本身经核对都是真实技术，无编造；已抽查出并修掉 4 处别名错误（见上「哪些表面形式被故意排除」）。剩余待定的是几条**边界情况**：`Zilliz`/`Zilliz Cloud` 挂在 Milvus 下（厂商名 vs 产品名）、`faster-whisper`/`whisper.cpp` 挂在 Whisper 下（独立的重实现项目）。这几条召回价值大于误判风险，暂时保留。
6. `ESP8266` 应单独立技能点（当前只是从 ESP32 的别名里删掉了，并未收录）。

## 本版本做了哪些取舍

技能点停在 800 出头，不冲两千。校验质量决定图谱能不能贴上岗位，人工看不过来的词表没有意义。办公套件、纯管理软件、停更且无许可的中文技能图，一律不收。O\*NET 只做名称对齐，不把 8753 个 Workplace Example 整表灌进来。
