#!/usr/bin/env python3
"""独立发现 / 探活 Moka orgId。不改生产采集器接线。

探活：GET https://api.mokahr.com/api-platform/v1/jobs/{orgId}?mode=social&limit=1
2xx 且 jobs 非空算活。hire-r1 租户另打 hire-r1-api.mokahr.com。

候选来源（脚本内置 + 可选文件）：
- 仓库现有 moka_orgs.txt
- eval/datasets/jd/fetch_jd.py 已实测名单
- Hiring-Radar parsers/companies.seed（公开 GitHub）
- ats-scrapers ats-companies/moka.csv（公开 GitHub，约 199 租户）
- 常见中国科技公司 slug 猜测
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORGS_FILE = ROOT / "backend" / "app" / "collectors" / "moka_orgs.txt"
DEFAULT_OUT = ROOT / "backend" / "app" / "collectors" / "moka_orgs.discovered.txt"
UA = "JobE/0.1 (research; job-evolution study)"
CN_API = "https://api.mokahr.com/api-platform/v1/jobs"
R1_API = "https://hire-r1-api.mokahr.com/api-platform/v1/jobs"

# 评测采集脚本里已实测过、但不一定在生产 moka_orgs.txt 里的 org。
FETCH_JD_ORGS: list[tuple[str, str]] = [
    ("cambricon", "寒武纪"),
    ("cloudwalk", "云从科技"),
    ("4paradigm", "第四范式"),
    ("moonshot", "月之暗面"),
    ("biren", "壁仞科技"),
    ("iluvatar", "天数智芯"),
    ("enflame", "燧原科技"),
    ("dji", "大疆"),
    ("dahua", "大华股份"),
    ("hikvision", "海康威视"),
    ("zte", "中兴"),
    ("sangfor", "深信服"),
    ("nsfocus", "绿盟科技"),
    ("xiaopeng", "小鹏汽车"),
    ("geely", "吉利"),
    ("moka", "Moka"),
    ("shopee", "Shopee"),
    ("high-flyer", "幻方量化"),
    ("step", "阶跃星辰"),
    ("baai", "智源研究院"),
    ("smartmore", "思谋科技"),
    ("dolphindb", "DolphinDB"),
    ("threatbook", "微步在线"),
    ("didiglobal", "滴滴"),
    ("voyah", "岚图汽车"),
    ("ninebot", "九号公司"),
    ("eastmoney", "东方财富"),
    ("zhihu", "知乎"),
    ("tecorigin", "太初元碁"),
    ("honeywell", "霍尼韦尔"),
    ("skyworth", "创维"),
    ("se", "施耐德电气"),
]

# Hiring-Radar companies.seed 中 type=moka 的 orgId（2026-06-27 上游实测）。
HIRING_RADAR_ORGS: list[tuple[str, str]] = [
    ("yokagames", "游卡"),
    ("eyugame", "鳄游"),
    ("bolegames", "博乐科技"),
    ("dianhun", "电魂网络"),
    ("pwrd", "完美世界"),
    ("kingnet", "恺英网络"),
    ("shengqu", "盛趣游戏"),
    ("yoozoo", "游族网络"),
    ("leyuansu", "乐元素"),
    ("lovegames", "乐府互娱"),
    ("micateam", "散爆网络"),
    ("shiyuehr", "诗悦网络"),
    ("shangyou", "尚游游戏"),
    ("hypergryph", "鹰角网络"),
    ("ztgame", "中手游"),
    ("bayer", "拜耳中国"),
    ("ey", "安永"),
    ("marriott", "万豪"),
    ("zeiss", "蔡司"),
    ("pradagroup", "PRADA"),
    ("kpmg", "毕马威"),
    ("se", "施耐德电气"),
    ("bosch", "博世中国"),
    ("volvocars", "沃尔沃汽车"),
    ("nestlezgc", "雀巢大中华"),
    ("carlsberg", "嘉士伯"),
    ("garena", "Garena"),
    ("bigo", "BIGO"),
    ("shopee", "Shopee"),
    ("shein", "SHEIN"),
    ("oocl", "东方海外"),
    ("biren", "壁仞科技"),
    ("tecorigin", "太初"),
    ("3peakic", "思瑞浦"),
    ("cambricon", "寒武纪"),
    ("huahong", "华虹集团"),
    ("high-flyer", "幻方量化"),
    ("step", "阶跃星辰"),
    ("baai", "智源研究院"),
    ("smartmore", "思谋科技"),
    ("taichi", "Meshy太极图形"),
    ("dolphindb", "DolphinDB"),
    ("threatbook", "微步在线"),
    ("jhlfund", "九坤投资"),
    ("lingjuninvest", "灵均投资"),
    ("sixiecapital", "思勰投资"),
    ("tianyancapital", "天演资本"),
    ("alpha2fund", "Alpha2Fund"),
    ("voyah", "岚图汽车"),
    ("geely", "吉利"),
    ("qianli1", "千里科技"),
    ("ninebot", "九号公司"),
    ("yanfeng", "延锋"),
    ("joyson", "均胜集团"),
    ("hithium", "海辰储能"),
    ("jinkosolar", "晶科能源"),
    ("envisiongroup", "远景能源"),
    ("solaxpower", "艾罗能源"),
    ("trinasolar", "天合光能"),
    ("zjshc", "三花智控"),
    ("synland", "时代新安"),
    ("saj", "赛智SAJ"),
    ("smoore", "思摩尔国际"),
    ("3songshu", "三只松鼠"),
    ("antahr", "安踏"),
    ("guming", "古茗"),
    ("ystwt", "万泰生物"),
    ("gstzy", "固生堂"),
    ("didiglobal", "滴滴"),
    ("zhihu", "知乎"),
    ("xunlei", "迅雷"),
    ("zuoyebang", "作业帮"),
    ("sina", "新浪微博"),
    ("manbang", "满帮集团"),
    ("zijinmining", "紫金矿业"),
    ("pg", "宝洁"),
    ("zte", "中兴"),
    ("eastmoney", "东方财富"),
    ("westlake", "西湖大学"),
]

# ats-scrapers moka.csv 的 orgId（去掉 campus 后缀与 hire-r1/ 前缀后的 slug）。
ATS_SCRAPERS_ORGS: list[tuple[str, str]] = [
    ("trip", "携程"),
    ("bigo", "BIGO"),
    ("shein", "SHEIN"),
    ("zhihu", "知乎"),
    ("geely", "吉利"),
    ("huya", "虎牙"),
    ("cloudwalk", "云从科技"),
    ("tongdun", "同盾科技"),
    ("audi", "奥迪中国"),
    ("manbang", "满帮集团"),
    ("xiaopeng", "小鹏汽车"),
    ("ninebot", "九号公司"),
    ("marriott", "万豪"),
    ("shopee", "Shopee"),
    ("4paradigm", "第四范式"),
    ("zte", "中兴"),
    ("baicizhan", "百词斩"),
    ("vipkid", "VIPKid"),
    ("eastmoney", "东方财富"),
    ("panasonic", "松下"),
    ("ford", "福特中国"),
    ("gm", "通用中国"),
    ("rakuten", "乐天中国研发"),
    ("zhongan", "众安保险"),
    ("deeproute", "元戎启行"),
    ("klookcareers", "Klook"),
    ("osl", "OSL"),
    ("tesla", "特斯拉"),
    ("traveloka", "Traveloka"),
    ("51talk", "51Talk"),
    ("58", "58同城"),
    ("adidas", "Adidas"),
    ("agora", "声网"),
    ("amec", "中微公司"),
    ("antgroup", "蚂蚁集团"),
    ("ylxinc", "光峰科技"),
    ("autox", "AutoX"),
    ("baai", "智源研究院"),
    ("100credit", "百融云创"),
    ("batf", "BATF"),
    ("bayer", "拜耳"),
    ("beigene", "百济神州"),
    ("bolegames", "博乐科技"),
    ("bigai-ai", "北京通用人工智能研究院"),
    ("biren", "壁仞科技"),
    ("bitget", "Bitget"),
    ("byd", "比亚迪"),
    ("cambricon", "寒武纪"),
    ("carlsberg", "嘉士伯"),
    ("cctv", "央视"),
    ("chaitin", "长亭科技"),
    ("cyou-inc", "畅游"),
    ("datang", "大唐"),
    ("chinatelecom", "中国电信"),
    ("vanke", "万科"),
    ("columbia", "哥伦比亚"),
    ("comau", "柯马"),
    ("costa", "Costa"),
    ("dahua", "大华股份"),
    ("high-flyer", "幻方量化"),
    ("dianhun", "电魂网络"),
    ("didiglobal", "滴滴"),
    ("dolphindb", "DolphinDB"),
    ("douyu", "斗鱼"),
    ("dxy", "丁香园"),
    ("ey", "安永"),
    ("fapon", "基蛋生物"),
    ("fenbi", "粉笔"),
    ("whfhtx", "烽火通信"),
    ("firstfun", "First Fun"),
    ("fftai", "傅利叶智能"),
    ("foxconn", "富士康"),
    ("bosssoft", "博思软件"),
    ("gaojihealth", "高济健康"),
    ("bjhl", "高途"),
    ("gap", "Gap"),
    ("gehc", "GE医疗"),
    ("genscript", "金斯瑞"),
    ("ztgame", "中手游"),
    ("gigadevice", "兆易创新"),
    ("glodon", "广联达"),
    ("gsk", "GSK"),
    ("guming", "古茗"),
    ("hanscnc", "大族数控"),
    ("hanslaser", "大族激光"),
    ("hyxj", "杭银消金"),
    ("hansoh", "豪森药业"),
    ("harbourbiomed", "和铂医药"),
    ("hfsp", "禾丰食品"),
    ("hengrui", "恒瑞医药"),
    ("heytea", "喜茶"),
    ("hikvision", "海康威视"),
    ("huaqin", "华勤技术"),
    ("hq", "华勤"),
    ("hutchmed", "和黄医药"),
    ("huxiu", "虎嗅"),
    ("hytech", "Hytech"),
    ("hytera", "海能达"),
    ("iluvatar", "天数智芯"),
    ("inoherb", "相宜本草"),
    ("inspiregames", "Inspire Games"),
    ("insta360", "影石"),
    ("jd", "京东"),
    ("jingdong", "京东"),
    ("jhlfund", "九坤投资"),
    ("jiahui", "嘉会医疗"),
    ("joyson", "均胜"),
    ("kcareers", "KCareers"),
    ("keenon", "擎朗智能"),
    ("kering", "开云"),
    ("kingnet", "恺英网络"),
    ("wps", "金山办公"),
    ("korrun", "科锐国际"),
    ("kpmg", "毕马威"),
    ("lining", "李宁"),
    ("inter-mammotion", "库犸科技"),
    ("masterkong", "康师傅"),
    ("medbanks", "医渡云"),
    ("megviihr", "旷视"),
    ("mgcc", "MGCC"),
    ("mk", "Michael Kors"),
    ("mindray", "迈瑞"),
    ("minieye", "MINIEYE"),
    ("miracleplus", "奇绩创坛"),
    ("moka", "Moka"),
    ("moonshot", "月之暗面"),
    ("muyuan", "牧原"),
    ("mycos", "麦可思"),
    ("nsfocus", "绿盟科技"),
    ("oocl", "东方海外"),
    ("oray", "向日葵"),
    ("parkway", "百汇医疗"),
    ("ifeng", "凤凰网"),
    ("polestar", "极星"),
    ("pg", "宝洁"),
    ("pwc", "普华永道"),
    ("52tt", "趣丸"),
    ("relin", "Relin"),
    ("sangfor", "深信服"),
    ("sany", "三一"),
    ("sanyuan", "三元食品"),
    ("seer", "仙工智能"),
    ("servyou", "亿企赢"),
    ("icrd", "上海集成电路研发中心"),
    ("shiyuehr", "诗悦网络"),
    ("aftershokzhr", "韶音"),
    ("shuquhuyu", "书趣互娱"),
    ("sigma", "Sigma"),
    ("sina", "新浪"),
    ("sinopharm", "国药"),
    ("sinovac", "科兴"),
    ("smartmore", "思谋科技"),
    ("smoore", "思摩尔"),
    ("sohu", "搜狐"),
    ("solaxpower", "艾罗能源"),
    ("space-t1", "进迭时空"),
    ("spic", "国家电投"),
    ("step", "阶跃星辰"),
    ("sto", "申通"),
    ("sunda", "SUNDA"),
    ("sungrow", "阳光电源"),
    ("tengden", "腾盾"),
    ("tesla", "特斯拉"),
    ("ti", "德州仪器"),
    ("tianma", "天马微电子"),
    ("tianyancapital", "天演资本"),
    ("tigermed", "泰格医药"),
    ("topsec", "天融信"),
    ("totalenergies", "道达尔"),
    ("tsinghuaic", "紫光同芯"),
    ("unisoc", "紫光展锐"),
    ("voyah", "岚图"),
    ("wens", "温氏"),
    ("westone", "卫士通"),
    ("wuxibiologics", "药明生物"),
    ("xcmg", "徐工"),
    ("xiaochuankeji", "小川科技"),
    ("xtep", "特步"),
    ("xueqiu", "雪球"),
    ("xunlei", "迅雷"),
    ("yitu-inc", "依图科技"),
    ("yokagames", "游卡"),
    ("yoozoo", "游族"),
    ("zijinmining", "紫金矿业"),
    ("zijin", "紫金"),
    ("zoomlion", "中联重科"),
    ("zuoyebang", "作业帮"),
]

# 常见科技公司 slug 猜测。多数不会活，用来量失败形态。
GUESSED_ORGS: list[tuple[str, str]] = [
    ("bytedance", "字节跳动"),
    ("toutiao", "今日头条"),
    ("douyin", "抖音"),
    ("tencent", "腾讯"),
    ("alibaba", "阿里巴巴"),
    ("alipay", "支付宝"),
    ("taobao", "淘宝"),
    ("meituan", "美团"),
    ("pdd", "拼多多"),
    ("pinduoduo", "拼多多"),
    ("netease", "网易"),
    ("mihoyo", "米哈游"),
    ("mihoyogame", "米哈游"),
    ("bilibili", "哔哩哔哩"),
    ("xiaohongshu", "小红书"),
    ("xhs", "小红书"),
    ("sensetime", "商汤"),
    ("horizon", "地平线"),
    ("horizonrobotics", "地平线"),
    ("djicorp", "大疆"),
    ("dji", "大疆"),
    ("baidu", "百度"),
    ("kuaishou", "快手"),
    ("huawei", "华为"),
    ("xiaomi", "小米"),
    ("oppo", "OPPO"),
    ("vivo", "vivo"),
    ("honor", "荣耀"),
    ("lenovo", "联想"),
    ("nio", "蔚来"),
    ("li", "理想"),
    ("lixiang", "理想汽车"),
    ("unitree", "宇树"),
    ("agibot", "智元机器人"),
    ("zhipu", "智谱"),
    ("minimax", "MiniMax"),
    ("deepseek", "深度求索"),
    ("baichuan", "百川智能"),
    ("01ai", "零一万物"),
    ("megvii", "旷视"),
    ("yitu", "依图"),
    ("ponyai", "小马智行"),
    ("weride", "文远知行"),
    ("momenta", "Momenta"),
    ("catl", "宁德时代"),
    ("mthreads", "摩尔线程"),
    ("moorethreads", "摩尔线程"),
    ("neteasegames", "网易游戏"),
    ("mi", "小米"),
    ("iqiyi", "爱奇艺"),
    ("youku", "优酷"),
    ("weibo", "微博"),
]

HIRE_R1_ORGS = {
    "klookcareers",
    "osl",
    "traveloka",
    "bitget",
    "firstfun",
    "heytea",
    "hytech",
    "kcareers",
    "inter-mammotion",
    "sunda",
    "tigermed",
}

# Common Crawl CC-MAIN-2026-34 前缀检索多出来的、信息技术向 orgId。
CC_ORGS: list[tuple[str, str]] = [
    ("catlhr", "宁德时代"),
    ("chinatelecomai", "中国电信AI"),
    ("cixcomputing", "CIX Computing"),
    ("dapustor", "大普微"),
    ("enmotech", "云和恩墨"),
    ("fehorizon01", "fehorizon01"),
    ("futu5", "富途"),
    ("memtensor", "MemTensor"),
    ("pcitech", "先导智能"),
    ("robosense", "速腾聚创"),
    ("visinextek", "Visinex"),
    ("wellintech", "亚控科技"),
    ("zelostech", "Zelos"),
    ("zensemi", "Zensemi"),
]

# JobE 四方向更相关、适合追加进生产名单的 org（探活成功才写）。
IT_PRIORITY = {
    "4paradigm",
    "agora",
    "autox",
    "baai",
    "bigai-ai",
    "biren",
    "cambricon",
    "chaitin",
    "cloudwalk",
    "dahua",
    "deeproute",
    "dji",
    "dolphindb",
    "enflame",
    "gigadevice",
    "glodon",
    "high-flyer",
    "hikvision",
    "iluvatar",
    "keenon",
    "megviihr",
    "minieye",
    "moonshot",
    "nsfocus",
    "sangfor",
    "seer",
    "smartmore",
    "space-t1",
    "step",
    "tecorigin",
    "tesla",
    "threatbook",
    "tongdun",
    "topsec",
    "tsinghuaic",
    "unisoc",
    "westone",
    "xiaopeng",
    "yitu-inc",
    "shopee",
    "se",
    "byd",
    "insta360",
    "hytera",
    "oray",
}


def load_orgs_file(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    out: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t", 1)
        org_id = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else org_id
        if org_id:
            out.append((org_id, name))
    return out


def merge_candidates(extra_files: list[Path]) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for group in (
        load_orgs_file(ORGS_FILE),
        FETCH_JD_ORGS,
        HIRING_RADAR_ORGS,
        ATS_SCRAPERS_ORGS,
        CC_ORGS,
        GUESSED_ORGS,
    ):
        for org_id, name in group:
            seen.setdefault(org_id, name)
    for path in extra_files:
        for org_id, name in load_orgs_file(path):
            seen.setdefault(org_id, name)
    return sorted(seen.items(), key=lambda x: x[0])


def http_get_json(url: str, timeout: int) -> tuple[int, dict | None, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, None, raw[:200]
            return resp.status, body if isinstance(body, dict) else None, ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = None
        return exc.code, body if isinstance(body, dict) else None, raw[:200]
    except Exception as exc:  # noqa: BLE001 — 探活要记下网络失败
        return 0, None, f"{type(exc).__name__}: {exc}"


def probe(org_id: str, *, api_base: str, timeout: int) -> dict:
    q = urllib.parse.urlencode({"mode": "social", "limit": "1"})
    url = f"{api_base}/{urllib.parse.quote(org_id)}?{q}"
    status, body, err = http_get_json(url, timeout)
    jobs = (body or {}).get("jobs") if isinstance(body, dict) else None
    alive = status in range(200, 300) and bool(jobs)
    sample = jobs[0] if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict) else {}
    desc = sample.get("description") or ""
    return {
        "org_id": org_id,
        "api": api_base,
        "http": status,
        "alive": alive,
        "total": (body or {}).get("total") if isinstance(body, dict) else None,
        "code": (body or {}).get("code") if isinstance(body, dict) else None,
        "msg": (body or {}).get("msg") if isinstance(body, dict) else None,
        "has_description": bool(str(desc).strip()),
        "description_len": len(str(desc)),
        "education": sample.get("education"),
        "minExperience": sample.get("minExperience"),
        "maxExperience": sample.get("maxExperience"),
        "title": sample.get("title"),
        "job_keys": sorted(sample.keys()) if sample else [],
        "error": err,
    }


def api_for(org_id: str, hire_r1: set[str]) -> str:
    return R1_API if org_id in hire_r1 else CN_API


def main() -> int:
    parser = argparse.ArgumentParser(description="探活 Moka orgId，写出发现名单")
    parser.add_argument("--delay", type=float, default=0.5, help="请求间隔秒，默认 0.5")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--extra", type=Path, action="append", default=[], help="额外候选文件，org_id<TAB>公司名")
    parser.add_argument("--only-existing", action="store_true", help="只探活生产 moka_orgs.txt")
    parser.add_argument("--limit", type=int, default=0, help="最多探活条数，0 表示全部")
    args = parser.parse_args()

    if args.only_existing:
        candidates = load_orgs_file(ORGS_FILE)
    else:
        candidates = merge_candidates(args.extra)
    if args.limit:
        candidates = candidates[: args.limit]

    results: list[dict] = []
    alive_rows: list[tuple[str, str, dict]] = []
    print(f"probing {len(candidates)} orgIds delay={args.delay}s", file=sys.stderr)
    for i, (org_id, name) in enumerate(candidates, 1):
        api = api_for(org_id, HIRE_R1_ORGS)
        row = probe(org_id, api_base=api, timeout=args.timeout)
        row["name"] = name
        # 猜错集群时，对 hire-r1 名单之外的 org 若国内 API 空且像 5xx，不再自动打另一集群，避免加倍请求。
        if not row["alive"] and org_id in HIRE_R1_ORGS and api == R1_API:
            fallback = probe(org_id, api_base=CN_API, timeout=args.timeout)
            fallback["name"] = name
            if fallback["alive"]:
                row = fallback
        results.append(row)
        flag = "ALIVE" if row["alive"] else "dead"
        print(
            f"[{i}/{len(candidates)}] {flag} {org_id}\t{name}\thttp={row['http']}\ttotal={row['total']}",
            file=sys.stderr,
        )
        if row["alive"]:
            alive_rows.append((org_id, name, row))
        if i < len(candidates):
            time.sleep(args.delay)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 探活成功的 Moka orgId。独立发现脚本写出，不覆盖 moka_orgs.txt。",
        "# 规则：GET jobs/{orgId}?mode=social&limit=1 ，2xx 且 jobs 非空。",
        f"# probed={len(candidates)} alive={len(alive_rows)} delay={args.delay}",
    ]
    for org_id, name, row in sorted(alive_rows, key=lambda x: x[0]):
        total = row.get("total")
        lines.append(f"{org_id}\t{name}\ttotal={total}")
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    json_path = args.json_out or args.out.with_suffix(".json")
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    existing = {oid for oid, _ in load_orgs_file(ORGS_FILE)}
    new_alive = [r for r in alive_rows if r[0] not in existing]
    it_new = [r for r in new_alive if r[0] in IT_PRIORITY]
    dead = [r for r in results if not r["alive"]]
    http_hist: dict[str, int] = {}
    for r in dead:
        key = str(r["http"])
        http_hist[key] = http_hist.get(key, 0) + 1

    summary = {
        "probed": len(candidates),
        "alive": len(alive_rows),
        "already_in_moka_orgs": len(alive_rows) - len(new_alive),
        "new_alive": len(new_alive),
        "it_priority_new": [f"{a}\t{b}" for a, b, _ in it_new],
        "dead": len(dead),
        "dead_http": http_hist,
        "out": str(args.out),
        "json_out": str(json_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
