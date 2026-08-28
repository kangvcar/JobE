"""下载第三方原始文件到 ontology/raw/。不入库，处理在 build.py。"""

from __future__ import annotations

import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"

ONET_ZIP = "https://www.onetcenter.org/dl_files/database/db_31_0_text.zip"
LINGUIST = "https://raw.githubusercontent.com/github-linguist/linguist/master/lib/linguist/languages.yml"

# 可选。失败不阻断主流程。
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"


def _get(url: str, dest: Path, timeout: int = 120) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "JobE-ontology/0.1"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        dest.write_bytes(resp.read())


def download_onet() -> Path:
    zpath = RAW / "db_31_0_text.zip"
    print(f"下载 O*NET 31.0 → {zpath}")
    _get(ONET_ZIP, zpath)
    with zipfile.ZipFile(zpath) as zf:
        member = "db_31_0_text/Software Skills.txt"
        zf.extract(member, RAW)
        extracted = RAW / member
        target = RAW / "software_skills.txt"
        target.write_bytes(extracted.read_bytes())
    print(f"写出 {target}")
    return target


def download_linguist() -> Path:
    dest = RAW / "languages.yml"
    print(f"下载 Linguist languages.yml → {dest}")
    _get(LINGUIST, dest, timeout=60)
    print(f"写出 {dest}")
    return dest


def main(argv: list[str]) -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    what = argv[1] if len(argv) > 1 else "all"
    if what in ("all", "onet"):
        download_onet()
    if what in ("all", "linguist"):
        download_linguist()
    if what == "wikidata":
        print("Wikidata 拉取尚未做成独立清单查询。见 README「待补充」。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
