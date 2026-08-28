# 公开 ATS 数据集探活

探活日期 2026-08-28。对四个来源都发了真实 HTTP / `git clone` / HuggingFace 下载，不是只读 README。商业库（Bright Data、Coresignal）未碰。

JobE 的 `Posting` 需要 `title`、`company`、`city`、`published_at`/`updated_at`、`salary_min`/`salary_max`（元/月）、`description`、以及快照上的 `url`。技能抽取吃正文，人社部那种无 JD 列表没用。第一用户是中国新兴 IT 岗位。海外英语 JD 只当对照或技术领先信号，必须写清中文覆盖率。

完整大文件在 `data/datasets/`（gitignore）。每源最多 20 条 jsonl 在 [open-ats-samples/](./open-ats-samples/)。

## 总建议

**该写导入器，而且只写一个：jobhive 托管 parquet。**

四个来源里只有 jobhive 同时满足「能下到带正文的中文岗位」和「字段能落到 Snapshot/Posting」。它的北森 + Moka 切片加起来约 10 万行、约 400 家中国雇主，比 JobE 现在自己爬的约 20 家 Moka 官网大一个数量级。海外英语对照用同一份快照里的 Ashby / Greenhouse 即可，不必再接第二套管道。

另外三个的判决是：open-apply-jobs 仅作对照（最新一天约 27 万条英语 JD，中文接近零）；open-jobs 的 21 GB parquet 过期两个月，分组清单 404，不值得写导入器；JobDataPool 放弃。

不要把「写导入器」理解成去跑别人的爬虫。jobhive 的 scraper 库（MIT）以后若要补 Moka 租户可以借代码，但第一刀是读他们已经打好的 parquet，落成不可变快照。

## 字段能否映射

| JobE `Posting` | jobhive | open-jobs 旧 parquet | open-apply 最新分区 | JobDataPool 8 月 CSV |
| --- | --- | --- | --- | --- |
| title | `title`，满 | `title`，满 | `title`，满 | `job_title`，满，但有垃圾标题 |
| company | `company`。北森是显示名；Moka 是租户 slug，要跟 `ats-companies/moka.csv` 联 | `company`，满 | 没有显示名，只有 `source_slug` | `company_name` |
| city | `location` 自由文本（「北京市」「长宁区, 上海市, 中国」） | `city`（样本 88%）+ `location` | `locations` 字符串列表 | `job_location`，只有 41% |
| published_at | `posted_at`。北森/Moka/Ashby 接近满；TikTok/ByteDance 为 0 | `posted_at`（样本 88%） | `posted_at`，满 | `job_posted_date`，35% |
| updated_at | 发布 parquet **没有** `fetched_at`，尽管 schema 文档写了 | 无 | 原生分区有 `updated_at`，样本里大量 null | 无 |
| salary_min/max | 北森/Moka 的结构化列为 0。北森 `salary_summary` 21% 带「10K-15K 元/月」，79% 是「面议」 | `salary_min_k` 有值，但约 65% 是哨兵 -1；真范围约 35%，单位是 k/年、USD 为主 | Ashby/Lever 约 35%，Greenhouse 0%；`salary_period` 基本空，USD 年薪 | `job_base_pay_range` 全空 |
| description | 有。北森均长 329 字、56%≥200；Moka 57% 有正文、有则均长 906；Ashby 均长 5k | `jd_markdown`，样本 99%、均长 4.5k | `description_html`，最新一天 98–100%、均长 1.8k–9.9k | `job_summary`，不是完整 JD；还有空摘要和职业站首页文案 |
| url | `url`，满，直链 ATS/官网 | `url`，满 | `apply_url`，满 | 全部是 `jobdatapool.com/jobrd?id=…` 跳转，不是源站 |
| 中国/中文 | 北森 100% `CN`/`zh`；Moka 89% 标题含汉字、67% 能判到中国 | 样本 `CN` 0.48%，标题汉字 0.88% | 最新一天标题汉字 0.1–0.42%；地点文本撞到中国约 0.4–0.6% | `CN` 98/96476 = 0.10%；标题汉字 0.06% |
| 落到 Snapshot | 行 = 一条 payload，`url` 可当快照 URL，导入时刻当 `fetched_at` | 可以，但文件停在 6 月 | 可以，建议只导最新 `date=` | payload 能拼，但 URL 不是源站、正文不够抽技能 |

## 1. jobhive / ats-scrapers：接入

**结论：接入。** 这是四个里唯一该立刻写导入器的。

### 探到了什么

- 代码：`git clone` `stapply-ai/ats-scrapers` 与 `kalil0321/ats-scrapers`，HEAD 都是 `f654221`（2026-08-23）。二者是同一份。`lvzyd3v/ats-scrapers` 停在 2026-05-18，过时镜像，不要用。
- 托管站 `https://data.stapply.ai` 是 SPA。清单不在 README 写的 `https://storage.stapply.ai/jobhive/manifest.json`（404），而在 **`https://storage.stapply.ai/jobhive/v1/manifest.json`**（200，41 KB，`Last-Modified: 2026-08-23`）。
- 清单宣称：`version=2.0`，`generated_at=2026-08-07T14:30:05Z`，65 个 ATS，去重后 **4,854,656** 行（raw 5,017,141），79,906 家公司。`all.parquet` 2.15 GB，`all.csv` 15.4 GB。本次没有下全量，下了与中国/对照相关的切片，行数与清单一致：

| 切片 | 清单行数 | 实际读到 | parquet |
| --- | --- | --- | --- |
| beisen | 72,905 | 72,905 | 13 MB |
| beisen_legacy | 6,461 | 6,461 | 464 KB |
| moka | 31,743 | 31,743 | 8.0 MB |
| tiktok | 3,893 | 3,893 | 2.6 MB |
| bytedance | 1,216 | 1,216 | 787 KB |
| apple | 4,753 | 4,753 | 3.1 MB |
| ashby | 53,528 | 53,528 | 50 MB |

中国相关 ATS 合计 **116,218** 行，占全库 2.4%。仓库里还有 `ats-companies/moka.csv`（198 行）和 `beisen.csv`（221 行），跟切片公司数对得上（Moka parquet 去重后 183 家，北森 221 家）。

许可：仓库 LICENSE 是 MIT，管的是 scraper 代码。数据是各公司招聘页的再分发，没有单独的 CC0/ODC 声明。JobE 按 ADR 0001 不把许可当接入门槛，但导入器登记 `Source.license` 时写「ats-scrapers 托管快照（MIT 工具 + 招聘页再分发）」即可。

刷新：徽章和 README 暗示「live」。实际 `generated_at` 停在 8 月 7 日，探活日是 8 月 28 日，职位快照至少 **21 天**没重跑。8 月 23 日的 `updated_at` 是公司清单那次写入，不是职位。把它当「偶发全量快照」，不要当日更。

### 正文、薪资、中文

北森（`zhiye.com`）是中国覆盖的主力。72,905 行全部 `country_iso=CN`、`language=zh`，标题 98.8% 含汉字。问题是岗位杂：标题正则能看成 IT 的只有 18.8%（大约 1.4 万）。星巴克咖啡师这类占了抽样里好几条。`description` 几乎每行都有，但均长只有 329 字，**55.8% ≥ 200 字**。科大讯飞「ios/安卓开发工程师」那种能到 400–800 字，够抽技能；门店岗只有职责三五行。`salary_min`/`salary_max` 全空。`salary_summary` 100% 有值，其中 **57,363 条是「面议」（79%）**，其余 15,542 条是「10K-15K 元/月」「20W-30W 元/年」这种，导入时用正则就能填 JobE 的月薪字段。`posted_at` 从 2015 跨到 2026-08-07，99% 有值，旧帖很多，导入要按时间窗切。

Moka 是对 JobE 现有采集器最直接的补量。31,743 行、183 家租户，标题 89% 含汉字，67% 能判到中国。`description` **只有 57% 非空**（18,146 行），有正文时均长 906，质量明显好于北森。薪资列全空，连 summary 也没有。`company` 是 `trip` / `smoore` / `xunlei` 这种 slug，不是「携程」。`posted_at` 有脏数据，切片最大值到了 2026-11-30。语言以 zh 为主（29,370），夹 2,216 条 en。

`beisen_legacy` 不要接。6,461 行几乎全是美年体检、百胜储备干部，IT 标题只有 1.6%，大量 2019–2021 的旧帖。

TikTok / ByteDance 切片是英语全球招聘站，标题汉字 ≈ 0，`posted_at` 全空，地点几乎没有中国。正文均长约 3k，适合当「大厂英语 JD 对照」，不算中国覆盖。Apple 同样。Ashby 53,528 行，正文均长 5.1k、99.7% ≥ 200 字，结构化年薪 39%（USD/YEAR 为主），中文 loc 0.54%。这是同一份快照里最省事的海外对照，不必另接 open-apply。

Schema 文档说 `description` 截到约 10 kB。Ashby 均长 5k，截断不是中国切片短的原因。中国切片短，是源站 JD 就短。

### 映射注意

`Snapshot.payload` 直接塞一行 dict。`Posting` 映射：`title`/`url`/`posted_at` 原样；`city` ← `location`；`description` 已是纯文本，不用再走 Moka 那套 HTML 清洗；北森月薪从 `salary_summary` 解析，单位已经是元/月或元/年；Moka 的 `company` 用 `ats-companies/moka.csv` 换成显示名。`source_id` 建议 `jobhive`，不要假装这些行是 JobE 自己打的 Moka 官网。去重窗口（公司+城市+标题、60 天）仍然有效，但 Moka slug 和北森中文名对不上，跨 ATS 近重复会漏，这和现网一样。

## 2. open-jobs：仅作对照（偏放弃导入）

**结论：不写全量导入器。** 旧 parquet 能当一次性英语对照样本；当前「2M 分组文件」并没有公开挂出来。

### 探到了什么

- `git clone` `elliottdehn/open-jobs`，HEAD `8732789`（2026-08-27）。README 已改口：不再主推单文件 parquet，改成 Cloudflare Worker 日爬约 65,000 个 board、约 200 万在招，客户端按向量分组下载。许可 **CC0**。
- `https://download.jobscream.com/open-jobs.parquet` 还在。HTTP 200，`Accept-Ranges: bytes`，`Content-Length=21,736,141,289`（21.2 GB），**`Last-Modified: 2026-06-25`**。用 range 读 footer：pyarrow 报告 **947,456 行**、190 个 row group。这是旧 README 的「约 96.7 万」那一版，不是现在说的 200 万。距探活日 **64 天**未刷新。没有下全文件；读了 row group 0 和 #50、合计 10,000 行（去掉 1536 维 embedding）。
- 现架构的分组数据应在 `GET https://backend.dehnbostele.workers.dev/data/manifest.json`。**404**。`centroids.bin`、`groups/0.json` 同样 404。R2 桶名在 wrangler 里是 `jobscream-data`，公开前缀是空的。
- Worker 本身活着。`GET /ats` 返回 21 个 ATS 的 slug 数（greenhouse 8,149，workable 6,902，workday 3,830…，**没有北森/Moka**）。`GET /boards/greenhouse/stripe?status=open` 返回 578 条在招，HTML 正文均长 4,847，100% ≥ 200 字，`lastOkAt=2026-08-27T20:29:43Z`，下次槽位约 24 小时后。这是采集 API，不是数据集。

### 字段与中国

旧 parquet 对 JobE 几乎是完美形状：`title`/`company`/`city`/`posted_at`/`url`/`jd_markdown`，外加 LLM 抽的 `salary_min_k`、`skills`。10,000 行样本里 JD 99% 有、均长 4,462。`country_code=CN` 只有 48 行（0.48%），标题含汉字 0.88%。ATS 以 greenhouse/ashby/lever 为主。结构化年薪约 35%（去掉 -1 哨兵后），货币几乎都是 USD。`posted_at` 最大到 2026-06-24，和文件日期一致。

分组 JSON 的 JD 还截到 4k 字。就算清单明天挂出来，中国覆盖也不会变好，源站就没有中文 ATS。

### 为什么不导入

21 GB 文件停在 6 月，导进去会污染时间轴（ADR 0004：只要真历史，但过期两个月的「在招」已经不是在招）。分组清单 404，没法按日增量。活着的 `/boards/:ats/:slug` 若要用，那是再写一个海外 ATS 采集器，不是数据集导入器，而且租户列表里没有中国 ATS。想要英语对照，jobhive 的 Ashby 切片已经够用，还和中文行在同一天快照里。

## 3. open-apply-jobs：仅作对照

**结论：仅作对照。** 英语 JD 质量高、日更到探活前一天，但不是给中国用户用的。若以后要第二导入器，只导最新 `date=` 分区。

### 探到了什么

- `git clone` `edwarddgao/openapply`，HEAD `fdaf353`（2026-08-17）。源只有 Greenhouse / Lever / Ashby 三个公开 JSON 板。代码 MIT。数据卡片写 MIT packaging，JD 版权仍归雇主。
- HuggingFace `api/datasets/...` 直连会超时。`datasets-server.huggingface.co` 可用。全库（105 个日分区叠在一起）**28,909,327 行 / 32.2 GB parquet**。这不是 2,890 万个不同职位，是 2026-04-17 到 **2026-08-27** 的每日全量快照重复堆叠。中间有缺口（4-29、5-22～6-07、7-09～7-18）。
- 最新一天三个文件都下了，行数：greenhouse 162,223、ashby 61,431、lever 46,057，合计 **269,711**。租户约 1.0 万（greenhouse 4,571 slug，ashby 3,808，lever 1,718）。

### 字段与中国

`description_html` 几乎 100%，均长 Ashby 7.0k / Greenhouse 9.9k / Lever 1.8k，抽技能没有问题。`posted_at` 满。没有公司显示名，只有 `source_slug`（`blitzy`、`coderabbit`）。`locations` 是字符串列表，要自己拆城市。`updated_at` 列存在，样本里多为 null。薪资：Ashby 34.6%、Lever 36.0%、Greenhouse **0%**（薪资写在 HTML 里）。`salary_period` 空，Ashby 样本里 90,000–110,000 这种是年薪 USD，不能当元/月。

中文覆盖接近零。最新一天标题含汉字 0.1–0.42%。地点文本能撞到 China/北京/上海的 Ashby 391、Greenhouse 956、Lever 184，合计约 1,531 行（0.57%），而且多半是跨国公司中国办事处的英语 JD。datasets-server 对约 65 万行的偏统计里，`salary_currency=CNY` 只有 28 条。

### 为什么不进主干

和 jobhive 的 Ashby 重叠，JobE 没有理由养两套英语 ATS 导入。全量 32 GB 是时间序列，导 105 天会把同一职位写 100 次快照。若只想要「海外技术领先信号」，取 `date=最新` 一天、丢掉 Greenhouse（无结构化薪资、行最多）或只留 Ashby，作为对照集放 `eval/` 比进生产采集更合适。

## 4. JobDataPool：放弃

**结论：放弃。**

### 探到了什么

- `https://jobdatapool.com/datasets/latest.csv` 302 到 R2 `listings-august-2026.csv`，**102,545,055 字节**，`Last-Modified: 2026-08-11`。CSV 和 55 MB parquet 都完整下了，**96,476 行**。
- 许可页写 **ODC-By 1.0**，要求署名 JobDataPool，并声明库结构和第三方 JD 版权是分开的。
- 自称月度、与 `/v1/jobs` 同 schema。实际 `GET https://api.jobdatapool.com/v1/jobs?limit=25` 返回 **502**（Lambda OOM）。`/v1/sources` 还能用，但里面的 `csv_url` 仍指向 **六月** 文件，和 `latest.csv` 的八月不一致。
- URL 全部是 `https://jobdatapool.com/jobrd?id=<hex>`，不是源站。快照无法回指招聘页。

### 字段与中国

`job_summary` 均长 776，80% ≥ 200 字，看起来像摘要而不是 JD。抽样第一条标题是 `orig.jpg (720×1280)`，第二条是 Paylocity 职业站首页文案。`job_base_pay_range` 全空，`skills` 全空。`country_code` 65% 空，有值的以 US 为主（31,914）。**CN = 98 行（0.10%）**。标题含汉字 0.06%。IT 标题约 4.4%。`job_posted_date` 只有 35%。

这东西既没有中国 IT 岗位，也没有能抽技能的正文，URL 还是自家跳转。ODC 署名成本白付。

## 导入器该怎么做

本次**没有改** `backend/app/collectors/`。下面是建议，不是实现。

1. 只做 `jobhive` 一个 `source_id`。读 `manifest.json` 核对 sha256，再下切片 parquet，不要一上来下 15 GB CSV。
2. 第一批切片：`moka`、`beisen`。北森按标题过滤 IT（工程师/开发/算法/数据/后端/前端等），丢掉门店和医疗。丢掉 `beisen_legacy`。
3. 一行 → 一条 `Snapshot`（`url` 用行内 url，`fetched_at` 用导入时刻，`payload` 整行）。再走现有 `postings_from_snapshot` 的同类映射，不要假装 `source_id=moka`，否则会和现网 Moka 采集器抢主键。
4. 北森 `salary_summary` 解析成元/月。Moka 公司名用 `moka.csv` 替换 slug。`posted_at` 丢无法解析和未来日期。
5. 海外对照若要做，同一导入器加 `ashby`（以及可选 `tiktok`），打标签当 `is_leading_indicator`，不要另接 open-apply。
6. 刷新当运维问题：清单 `generated_at` 超过 14 天就告警。他们哪天恢复日更，导入器不用改。
7. 不要写 open-jobs / JobDataPool 导入器。open-apply 只在明确要「英语对照评测集」时，用 HuggingFace 最新 `date=` 三个 parquet 做一次性脚本，放 `eval/`，不进生产采集。

预期量级（粗算、过滤后）：Moka 有正文的约 1.8 万行 + 北森 IT 约 1 万行，再加 Ashby 5 万英语对照。这已经比人社部无 JD 列表和 20 家 Moka 官网能支撑的技能抽取大得多。中文覆盖率不会因为再接那三个英语库而改善。
