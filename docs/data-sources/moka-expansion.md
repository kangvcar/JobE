# Moka 采集扩展：orgId 发现与产量估计

日期：2026-08-28。接口全部打过真实网络。生产采集接线（`sources.py` / `collect.py` / `postings.py`）未改。

## 结论

应该扩，但只扩信息技术相关租户，不要把 200/500/2000 家一股脑塞进生产名单。

公开 `GET /api-platform/v1/jobs/{orgId}` 今天仍然免鉴权、带 HTML `description`。现有 20 家里抽吉利、滴滴、知乎，社招分别是 2659 / 547 / 47 条，抽样 30 条全部有正文。把名单扩到约 70 家芯片/智驾/安防/大模型/机器人公司，对 JobE 四方向（人工智能、大数据、智能系统、物联网）够用一轮。再往 200 家掺进酒店、服饰、药企，带正文的条数会涨，但信息技术岗位占比会掉。500 和 2000 在公开官网上几乎摸不到那么多活租户，收益递减。

更好的发现办法不是猜 `bytedance` / `tencent`。那些 slug 对公开接口返回 HTTP 500。有效顺序是：

1. 复用已经公开的租户表（ats-scrapers 的 `moka.csv`、Hiring-Radar 的 `companies.seed`）
2. Common Crawl 对 `app.mokahr.com/social-recruitment/` 做前缀检索
3. 对命中的 orgId 按 `jobs/{orgId}?mode=social&limit=1` 探活

Moka 没有公司目录，没有 sitemap，`/website/list` 要 basic auth。Google CSE / Bing API 没有钥匙，这次 `site:` 搜索也几乎搜不到 SPA 招聘页。字节、腾讯、阿里、美团、商汤、智谱、MiniMax 的公开招聘不在这个接口上。缺的那一块去飞书招聘 / 北森 / 大厂自建站，比继续堆 Moka org 有效。

默认 `max_items=2000` 时，吉利一家就能把配额吃光。只加名单、不按 org 封顶，生产采集几乎感觉不到扩展。

## 现有接口仍可用

文档：[`GET https://api.mokahr.com/api-platform/v1/jobs/{orgId}`](https://mokahr.moyincloud.com/d/1687298462460178433.html)，`mode=social|campus`。官方把 `orgId` 写成「每个企业客户对应的唯一 id」，没有「列出全部 org」的接口。职位字段包括 `description`（HTML）、`minSalary`/`maxSalary`（单位千）、`minExperience`/`maxExperience`、`education`、`updatedAt`、`openedAt`、`commitment`。

2026-08-28 对生产名单里三家打 `mode=social&limit=30&status=open`：

| orgId | 公司 | HTTP | 社招 total | 抽样 description | education 有值 | minExperience 有值 | 校招 total |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| geely | 吉利 | 200 | 2659 | 30/30，全是 HTML | 6/30，值=`本科` | 7/30 | 2259 |
| didiglobal | 滴滴 | 200 | 547 | 30/30 | 23/30，`本科` 18 / `硕士` 5 | 0/30 | 159 |
| zhihu | 知乎 | 200 | 47 | 30/30 | 0/30 | 0/30 | 47 |

三家首条职位的字段集合一致，和 fixture、官方文档对得上：`education`、`minExperience`、`maxExperience`、`commitment`、`updatedAt`、`openedAt`、`description`、`minSalary`、`maxSalary`、`locations`、`department`。学历和年限经常是 `null`，人还是把要求写在 HTML 正文里。知乎 30 条结构化学历全空，正文里仍有「本科」「硕士」。抽取不能只靠 ATS 字段。

国际集群 `https://hire-r1-api.mokahr.com/api-platform/v1/jobs/{orgId}` 同样免鉴权。`tesla` 在国内 API 返回中文岗位（服务顾问），在 hire-r1 返回 Autopilot / Maps 英文岗。同一 slug、两套库。JobE 要中国信息技术岗位，默认打 `api.mokahr.com` 即可。特斯拉中国社招当天 970 条，里面大量门店岗，需要按标题过滤。

## 没有公开的 org 目录

当天打过这些地址：

| 地址 | 结果 |
| --- | --- |
| `www.mokahr.com/sitemap.xml` | 200，其实是官网 HTML，不是 sitemap |
| `app.mokahr.com/sitemap.xml`、`sitemap_index.xml` | 404 |
| `GET /api-platform/v1/website/list` | 500，`请按照 basic auth 方式进行认证`。文档里这是「获取企业在招聘官网模块处所有创建的官网」，按租户而不是全球目录 |
| `GET /api-platform/v1/orgs` | 404 |
| `GET /api-platform/v1/jobs?mode=social`（不带 orgId） | 404 |
| `app.mokahr.com/robots.txt` | 只 Disallow 两条已知路径：`lingjuninvest/46355`、`shopee/74378`。不是目录，但能漏 slug |

Moka 官网写自己服务超 3000 家中大型企业（[关于我们](https://www.mokahr.com/about/)）。客户案例里出现过小米、滴滴、作业帮、Shopee。那是销售口径：用了 Moka ATS 不等于开了免鉴权社招官网，更不等于 slug 等于英文品牌名。

## 发现 orgId：哪种办法真的有货

### 1. 别人已经整理好的租户表（最好用）

[kalil0321/ats-scrapers#111](https://github.com/kalil0321/ats-scrapers/pull/111) 把 `ats-companies/moka.csv` 从 30 扩到 199 家，写法是 Google `site:app.mokahr.com` / `site:hire-r1.mokahr.com` 再加品牌 slug 暴力匹配，每条用前端加密接口验过。CSV 在 [raw moka.csv](https://raw.githubusercontent.com/kalil0321/ats-scrapers/main/ats-companies/moka.csv)。

[Hiring-Radar `parsers/companies.seed`](https://raw.githubusercontent.com/simonlin1212/Hiring-Radar/main/parsers/companies.seed) 有约 90 条 `type=moka`，2026-06-27 上游实测。格式是 `orgId` + `siteId`，siteId 只用来拼 `app.mokahr.com/social-recruitment/{orgId}/{siteId}`，公开 jobs API 只用 orgId。

仓库里 `eval/datasets/jd/fetch_jd.py` 另有一份约 32 家「已实测非空」名单，比生产 `moka_orgs.txt` 大，寒武纪、月之暗面、大疆、海康都在里面。评测集 991 条来自其中 26 家。

这三份表高度重叠，并起来去重后就是今天脚本的主体候选。

### 2. Common Crawl 前缀检索（比猜 slug 强）

最新索引 `CC-MAIN-2026-34`（2026-08-07 到 08-20）。对 `app.mokahr.com/social-recruitment/`、`hire-r1.mokahr.com/social-recruitment/`、`app.mokahr.com/campus-recruitment/` 做 `matchType=prefix`，一页就解析出 120 个不同 orgId。其中一批不在 ats-scrapers / Hiring-Radar 里，当天探活成功且对 JobE 有用：

| orgId | 当天社招条数 | 凭据 |
| --- | ---: | --- |
| catlhr | 4941 | 标题带「宁德时代东营基地」。猜 `catl` 是 HTTP 500 |
| robosense | 194 | 「激光雷达系统工程师」 |
| chinatelecomai | 111 | 「算子开发」「研发安全」 |
| cixcomputing | 75 | 安全启动驱动、量产测试 |
| enmotech | 61 | MySQL/Oracle DBA |
| zelostech | 50 | 自动驾驶感知 / 端到端模型 |
| zensemi | 49 | IT 开发、信息安全 |
| memtensor | 29 | 「B端算法负责人(大模型方向)」 |
| visinextek | 33 | 「AI芯片工具链开发工程师」 |

CDX 例：`https://index.commoncrawl.org/CC-MAIN-2026-34-index?url=app.mokahr.com/social-recruitment/&matchType=prefix&output=json`。这是目前唯一不依赖搜索引擎配额、还能挖到新 slug 的办法。`catl` vs `catlhr` 说明品牌名猜测会系统性地漏掉真实 slug。

### 3. 品牌 slug 猜测（用来排除大厂，不是用来扩）

对字节、腾讯、阿里、美团、拼多多、网易、米哈游、B 站、小红书、商汤、地平线、华为、小米、百度、快手、理想、蔚来、DeepSeek、智谱、MiniMax、宁德时代（`catl`）等常见英文 slug 探活，几乎全是 HTTP 500。例外：`agibot`（智元机器人）猜中了，社招 35 条。`netease` / `vivo` / `iqiyi` 返回 200 但 `total=0`，租户在、职位空。`megvii` 500，真 slug 是 `megviihr`。

TEST-PLAN 里写的「若干互联网大厂 slug 猜错 → 500 或空列表」今天仍然成立。大厂公开招聘走自建站或飞书，不走这个匿名 jobs API。

### 4. 搜索引擎、Gitee、聚合站

对 `site:app.mokahr.com/social-recruitment` 的网页搜索几乎没有结果。招聘页是 hash 路由 SPA，搜索引擎抓不到职位，偶尔能抓到门户首页。ats-scrapers 的 PR 说明他们用 Google site-search 成功扩到 199 家，所以有钥匙的 CSE / Bing 仍然值得当定期补充，不是主路径。

GitHub 上能直接抄表：Hiring-Radar、ats-scrapers、[HA7CH/job-pro](https://github.com/HA7CH/job-pro)（吉利 CNAME 到 `app.mokahr.com/social-recruitment/geely/96123`）。Gitee 没有搜到可复用的 org 列表。

没有去爬 BOSS / 智联的「投递到 mokahr」外链。那条路可行，但比 CC + 现成 CSV 慢，而且 ADR 0001 已经允许直接打 ATS。优先打官网接口，不必绕聚合站。

Hiring-Radar 还提到前端 jobs 接口有一层 AES-128-CBC。JobE 现有采集器走的是未混淆的 Open API，继续用这个，不要去解前端包。

## 探活规模

脚本：`backend/scripts/discover_moka_orgs.py`。规则：`GET jobs/{orgId}?mode=social&limit=1`，2xx 且 `jobs` 非空算活，间隔 0.4s。

| 批次 | 候选 | 活 | 备注 |
| --- | ---: | ---: | --- |
| 内置表 + 猜测 | 282 | 219 | 63 死：48 个 HTTP 500，6 个 200 空列表，9 个末尾网络超时 |
| 超时重试 + CC 新 slug | 92 | 78 | `zte` 等 9 个超时全部恢复。`zhipu`、`high-flyer` 仍 500 |
| 合并去重 |  | **296** | 社招 total 合计约 **4.8 万** |

296 家里抽样第一条，212/219（第一批）带 `description`。正文覆盖不是问题。问题是岗位结构：条数最高的是万豪 5811、宁德时代 `catlhr` 4941、吉利 2690、安踏 1565、岚图 1354、万科 1298。信息技术相关子集（芯片、智驾、安防、大模型、机器人、通信、工业软件，外加滴滴/Shopee/特斯拉/施耐德）大约 60 家、合计约 1.1 万到 1.6 万条在招，其中吉利/岚图/特斯拉/大疆又占了一大半，且混有大量非研发岗。

`high-flyer`（幻方 / 评测脚本里当 DeepSeek 用过）今天两次都是 500。不要假设去年活的 slug 永远活。

完整活名单：`backend/app/collectors/moka_orgs.discovered.txt`。不要把它整表导入生产采集。

## 扩到 200 / 500 / 2000 家能拿到多少带正文 JD

按今天的活租户和第一条 description 比例（约 97%）估算社招在招、带 HTML 正文的条数。校招另计，不加倍。

| 规模 | 现实上能不能凑够租户 | 带正文 JD（粗） | 其中信息技术相关（标题过滤后，更粗） |
| --- | --- | --- | --- |
| 当前生产 20 家 | 已有 | 约 0.7 万（吉利一家 0.27 万） | 评测关键词过滤后 26 家贡献了 991 条，生产 20 家未做关键词过滤 |
| 信息技术向 ~70 家 | 已探活，已写入 `moka_orgs.txt` | 约 1.2 万到 1.8 万 | 过滤研发标题后大概 2 千到 5 千。对四方向金标准扩容够 |
| 200 家（ats-scrapers 量级） | 已有公开表，今天 219/282 活 | 约 3 万到 4 万 | 增量主要是零售、药、酒店、光伏。信息技术岗位不会按 10 倍涨 |
| 500 家 | CC 多页 + Google site-search 也许能摸到 400+ 个非空官网 | 也许 5 万到 8 万 | 边际信息技术 JD 很少。运维成本和噪声先到 |
| 2000 家 | Moka 自称 3000 客户，但公开非空社招官网远少于此。猜 2000 个品牌 slug 会换回一大片 500 | 公开接口侧几乎做不到 | 不要做 |

评测集已经证明：26 家 + 关键词，991 条里几乎全有可用正文，学历结构化字段只有 366/991 有值、年限 179/991。扩展 org 的价值是公司覆盖和岗位族平衡（现在 iot 只有 24 条金标准），不是把「有 description」从 90% 拉到 99%。

默认采集 `max_items=2000`、`delay_seconds=3`、按文件顺序遍历。吉利在名单第 2 行、社招 2600+，一轮采集会在吉利内部打满配额，后面 50 家新 org 轮不到。扩展名单要配套按 org 封顶（例如每家最多 80 条）或按关键词预过滤，否则只是把 `moka_orgs.txt` 写长。这次没改采集器，只把信息技术相关、探活成功的租户追加到名单末尾。

## 对 JobE 覆盖够不够

够一轮，不够当中国信息技术岗位的代表样本。

Moka 上今天能稳定拿到正文的，是用了 Moka 且打开了社招官网的公司：中兴、寒武纪、壁仞、天数智芯、燧原、月之暗面、阶跃、智源、云从、第四范式、大疆、海康/大华量很少、深信服、绿盟、速腾聚创、元戎启行、小鹏、智元机器人、金山办公、中国电信 AI。评测四方向能继续堆量。

公开接口上没有的：字节、腾讯、阿里、美团、拼多多、华为、小米、商汤、智谱、MiniMax、DeepSeek、米哈游、地平线（`horizon*` 全 500，`fehorizon01` 活着但岗位像资产/职能条线，不能当成地平线）。Hiring-Radar 的飞书表里有智谱、百川、MiniMax、月之暗面（飞书门户）、小马智行、摩尔线程、禾赛。北森表里有追觅、零跑、京东方。这些才是 Moka 扩完之后的缺口。

所以：Moka 扩展是低成本补正文，不是「覆盖中国新一代信息技术岗位」的主方案。

## 该做什么，按优先级

1. **现在做。** 生产名单只用信息技术相关、已探活的 org（本次已从 20 家追加到约 70 家）。采集侧下一步再加每 org 上限，否则吉利/岚图/特斯拉会独占 `max_items`。
2. **按季度做。** 跑 `discover_moka_orgs.py`，再打一页 Common Crawl CDX，把新的芯片/智驾/大模型 slug 追加进 discovered 名单，人工过一遍再进生产。
3. **不要做。** 把 `moka_orgs.discovered.txt` 296 家整表接入；不要为了凑 500/2000 去爆破品牌 slug；不要解前端 AES。
4. **并行、优先级不低于扩 Moka。** 飞书招聘门户（智谱、MiniMax、具身智能一批）、北森 `*.zhiye.com`、以及大厂自建 JSON。没有这些，图谱里的「大模型岗位」会偏成月之暗面 + 阶跃 + 智源，缺了智谱和 MiniMax。

## 交付

- 发现脚本：`backend/scripts/discover_moka_orgs.py`（独立，默认可重复探活，不改采集器）
- 探活成功全集：`backend/app/collectors/moka_orgs.discovered.txt`（296 家，含万豪/宁德时代等，**不要整表导入**）
- 第一批探活原始 JSON：`backend/app/collectors/moka_orgs.discovered.json`
- 生产名单：`backend/app/collectors/moka_orgs.txt` 追加了当天探活成功的信息技术相关 org，原 20 家未删、未改序
