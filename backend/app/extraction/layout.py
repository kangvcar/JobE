"""文档规范化与字符↔坐标索引。

坐标系（必须读）：
  对外统一为 PDF 点、原点左下、y 向上——与 PDF 规范和 pdfplumber 一致。
  MinerU pipeline 后端把 bbox 归一化到 0-1000；vlm 后端归一化到 0-1。
  混用会算错，入库前一律转成 PDF 点。MinerU 自身是原点左上、y 向下，转换时翻转 y。

主解析器 MinerU（可选依赖 docparse）；不可用时降级 pdfplumber，并打 warning。
不要 import pymupdf/fitz（AGPL-3.0）。
DOCX 经 LibreOffice headless 转 PDF，保证只有一套坐标系。
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jobe.extraction.layout")

# 列检测：页面中部纵向空白带的扫描范围
_COL_SCAN_LO = 0.28
_COL_SCAN_HI = 0.72
_COL_STEP = 4.0
# 同行字符的 y 容差（PDF 点）、词间距插入空格的 x 间隙
_Y_LINE_TOL = 3.5
_X_SPACE_GAP = 1.6


class MinerUUnavailable(Exception):
    """MinerU 未安装、命令失败或未产出 middle.json。调用方应降级。"""


@dataclass
class CharIndex:
    """canonical_text 每个字符的版面位置，run-length 压缩后写入 documents.char_index。

    runs 元素：[start, end, page_index, x0, y0, x1, y1]，半开区间。
    同一 span 内字符共享 bbox；pdfplumber 路径通常一字一 run。
    """

    space: str = "pdf_points"
    pages: list[dict[str, float]] = field(default_factory=list)
    runs: list[list[float]] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "space": self.space,
            "pages": self.pages,
            "runs": self.runs,
            "blocks": self.blocks,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> CharIndex:
        if not data:
            return cls()
        return cls(
            space=str(data.get("space") or "pdf_points"),
            pages=list(data.get("pages") or []),
            runs=[list(r) for r in (data.get("runs") or [])],
            blocks=list(data.get("blocks") or []),
        )

    @classmethod
    def plain(cls, length: int) -> CharIndex:
        """纯文本（职位描述）无坐标。"""
        runs: list[list[float]] = []
        if length:
            runs.append([0, length, 0, 0.0, 0.0, 0.0, 0.0])
        return cls(pages=[{"w": 0.0, "h": 0.0}], runs=runs)

    def span_geometry(
        self, start: int, end: int
    ) -> tuple[int | None, tuple[float, float, float, float] | None]:
        """区间主页与 bbox 并集。无坐标则返回 (None, None)。"""
        page: int | None = None
        box: list[float] | None = None
        for run in self.runs:
            rs, re, rp, x0, y0, x1, y1 = run
            if re <= start or rs >= end:
                continue
            if x1 <= x0 and y1 <= y0:
                continue
            ip = int(rp)
            if page is None:
                page = ip
            if ip != page:
                continue
            if box is None:
                box = [x0, y0, x1, y1]
            else:
                box[0] = min(box[0], x0)
                box[1] = min(box[1], y0)
                box[2] = max(box[2], x1)
                box[3] = max(box[3], y1)
        if box is None:
            return page, None
        return page, (box[0], box[1], box[2], box[3])


@dataclass
class ParsedDocument:
    canonical_text: str
    char_index: CharIndex
    backend_name: str


def parse_plain_text(text: str) -> ParsedDocument:
    return ParsedDocument(
        canonical_text=text,
        char_index=CharIndex.plain(len(text)),
        backend_name="plain",
    )


def parse_document(
    data: bytes,
    filename: str,
    *,
    prefer: str | None = None,
) -> ParsedDocument:
    """PDF/DOCX → canonical text + char_index。未知类型按 UTF-8 纯文本。"""
    name = (filename or "doc.pdf").lower()
    if name.endswith(".docx") or name.endswith(".doc"):
        data = docx_to_pdf(data)
        name = "converted.pdf"
    if name.endswith(".pdf"):
        return parse_pdf(data, prefer=prefer)
    text = data.decode("utf-8")
    return parse_plain_text(text)


def parse_pdf(pdf_bytes: bytes, *, prefer: str | None = None) -> ParsedDocument:
    if prefer != "pdfplumber":
        try:
            middle = invoke_mineru(pdf_bytes)
            logger.info("版面解析后端: MinerU")
            return from_mineru_middle(middle)
        except MinerUUnavailable as exc:
            logger.warning("MinerU 不可用，降级到 pdfplumber。原因：%s", exc)
    logger.info("版面解析后端: pdfplumber（含基本列检测）")
    return parse_pdf_pdfplumber(pdf_bytes)


def docx_to_pdf(data: bytes) -> bytes:
    soffice = _find_soffice()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.docx"
        src.write_bytes(data)
        proc = subprocess.run(
            [
                soffice,
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                tmp,
                str(src),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        pdf = Path(tmp) / "in.pdf"
        if proc.returncode != 0 or not pdf.exists():
            raise RuntimeError(
                f"LibreOffice 转换 DOCX 失败（exit={proc.returncode}）："
                f"{proc.stderr or proc.stdout}"
            )
        return pdf.read_bytes()


def _find_soffice() -> str:
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError(
        "未找到 LibreOffice（命令 soffice 或 libreoffice 不在 PATH）。"
        "DOCX 必须先转为 PDF 才能进入同一套坐标系，请安装 LibreOffice 后重试。"
    )


# ---------------------------------------------------------------------------
# 坐标空间
# ---------------------------------------------------------------------------


def detect_coord_space(
    bboxes: list[tuple[float, float, float, float]],
    page_w: float,
    page_h: float,
    backend: str | None = None,
) -> str:
    """推断 MinerU bbox 的坐标空间。backend 优先于启发式。"""
    b = (backend or "").lower()
    if "vlm" in b:
        return "norm_0_1"
    if "pipeline" in b or b == "auto":
        return "norm_0_1000"
    if not bboxes:
        return "pdf_points"
    max_c = max(max(abs(x) for x in box) for box in bboxes)
    if max_c <= 1.01:
        return "norm_0_1"
    overflow = any(box[2] > page_w + 2 or box[3] > page_h + 2 for box in bboxes)
    if overflow and max_c <= 1000.01:
        return "norm_0_1000"
    return "pdf_points"


def to_pdf_points(
    bbox: tuple[float, float, float, float],
    page_w: float,
    page_h: float,
    space: str,
    *,
    origin: str = "top_left",
) -> tuple[float, float, float, float]:
    """把任意空间的 bbox 转成 PDF 点 / 原点左下。"""
    x0, y0, x1, y1 = bbox
    if space == "norm_0_1":
        x0, y0, x1, y1 = x0 * page_w, y0 * page_h, x1 * page_w, y1 * page_h
    elif space == "norm_0_1000":
        x0, y0, x1, y1 = (
            x0 / 1000.0 * page_w,
            y0 / 1000.0 * page_h,
            x1 / 1000.0 * page_w,
            y1 / 1000.0 * page_h,
        )
    if origin == "top_left":
        # MinerU：y0 是顶边。翻转到 PDF 原点左下。
        y0_pdf = page_h - y1
        y1_pdf = page_h - y0
        y0, y1 = y0_pdf, y1_pdf
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return (x0, y0, x1, y1)


# ---------------------------------------------------------------------------
# MinerU
# ---------------------------------------------------------------------------


def invoke_mineru(pdf_bytes: bytes) -> dict[str, Any]:
    """拿到 middle.json。失败抛 MinerUUnavailable，禁止静默。"""
    try:
        import magic_pdf  # noqa: F401
    except ImportError as exc:
        raise MinerUUnavailable(f"magic-pdf 未安装（可选依赖组 docparse）：{exc}") from exc

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "doc.pdf"
        pdf_path.write_bytes(pdf_bytes)
        out_dir = Path(tmp) / "out"
        out_dir.mkdir()
        exe = shutil.which("magic-pdf")
        if exe:
            proc = subprocess.run(
                [exe, "-p", str(pdf_path), "-o", str(out_dir), "-m", "auto"],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            middles = list(out_dir.rglob("*middle.json"))
            if proc.returncode == 0 and middles:
                return json.loads(middles[0].read_text(encoding="utf-8"))
            logger.info("magic-pdf CLI 未产出 middle.json：%s", proc.stderr or proc.stdout)
        # 库入口因版本而异，失败即视为不可用，交给 pdfplumber
        try:
            return _invoke_mineru_python(pdf_bytes)
        except Exception as exc:
            raise MinerUUnavailable(f"MinerU Python API 失败：{exc}") from exc


def _invoke_mineru_python(pdf_bytes: bytes) -> dict[str, Any]:
    """best-effort：不绑定某个 magic-pdf 小版本。"""
    from magic_pdf.data.dataset import PymuDocDataset
    from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze

    ds = PymuDocDataset(pdf_bytes)
    infer = ds.apply(doc_analyze, ocr=False)
    middle = getattr(infer, "_middle_json", None) or getattr(infer, "middle_json", None)
    if isinstance(middle, dict):
        return middle
    if isinstance(middle, str):
        return json.loads(middle)
    raise MinerUUnavailable("Python API 未暴露 middle.json")


def from_mineru_middle(middle: dict[str, Any]) -> ParsedDocument:
    backend = (
        middle.get("_backend")
        or middle.get("backend")
        or middle.get("parse_mode")
        or middle.get("_parse_type")
    )
    pages_info = middle.get("pdf_info") or middle.get("pdfInfo") or []
    parts: list[str] = []
    runs: list[list[float]] = []
    pages: list[dict[str, float]] = []
    blocks: list[dict[str, Any]] = []

    for page in pages_info:
        page_idx = int(page.get("page_idx") or page.get("page_id") or 0)
        size = page.get("page_size") or page.get("pageSize") or [612, 792]
        page_w, page_h = float(size[0]), float(size[1])
        pages.append({"w": page_w, "h": page_h})
        para = page.get("para_blocks") or page.get("preproc_blocks") or []
        raw_boxes = _collect_bboxes(para)
        backend_name = backend if isinstance(backend, str) else None
        space = detect_coord_space(raw_boxes, page_w, page_h, backend_name)

        if parts:
            parts.append("\n")
        page_start = sum(len(p) for p in parts)
        page_parts: list[str] = []
        for block in para:
            block_start = page_start + sum(len(p) for p in page_parts)
            _emit_block(block, page_parts, runs, page_idx, page_w, page_h, space, page_start)
            block_end = page_start + sum(len(p) for p in page_parts)
            btype = str(block.get("type") or "text")
            is_heading = btype in {"title", "header"} or (
                btype == "text" and _looks_like_heading_block(block)
            )
            if is_heading:
                blocks.append(
                    {
                        "start": block_start,
                        "end": block_end,
                        "kind": "title" if btype == "title" else btype,
                        "label": _block_text(block)[:80],
                    }
                )
        parts.extend(page_parts)

    text = "".join(parts)
    return ParsedDocument(
        canonical_text=text,
        char_index=CharIndex(pages=pages, runs=runs, blocks=blocks),
        backend_name="mineru",
    )


def _collect_bboxes(blocks: list[dict]) -> list[tuple[float, float, float, float]]:
    out: list[tuple[float, float, float, float]] = []
    for block in blocks:
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                bb = span.get("bbox") or line.get("bbox") or block.get("bbox")
                if bb and len(bb) >= 4:
                    out.append((float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])))
        if "blocks" in block:
            out.extend(_collect_bboxes(block["blocks"]))
    return out


def _block_text(block: dict) -> str:
    chunks: list[str] = []
    for line in block.get("lines") or []:
        for span in line.get("spans") or []:
            chunks.append(str(span.get("content") or span.get("text") or ""))
    return "".join(chunks)


def _looks_like_heading_block(block: dict) -> bool:
    t = _block_text(block).strip()
    return bool(t) and len(t) <= 20 and "\n" not in t


def _emit_block(
    block: dict,
    parts: list[str],
    runs: list[list[float]],
    page_idx: int,
    page_w: float,
    page_h: float,
    space: str,
    page_base: int,
) -> None:
    btype = str(block.get("type") or "")
    if btype in {"image", "header", "footer"}:
        return
    lines = block.get("lines")
    if not lines and block.get("blocks"):
        for sub in block["blocks"]:
            _emit_block(sub, parts, runs, page_idx, page_w, page_h, space, page_base)
        return
    for line in lines or []:
        for span in line.get("spans") or []:
            stype = span.get("type")
            if stype in {"image", "table"}:
                continue
            content = str(span.get("content") or span.get("text") or "")
            if not content:
                continue
            bb = span.get("bbox") or line.get("bbox") or block.get("bbox") or [0, 0, 0, 0]
            pdf_bb = to_pdf_points(
                (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])),
                page_w,
                page_h,
                space,
                origin="top_left",
            )
            start = page_base + sum(len(p) for p in parts)
            parts.append(content)
            runs.append([start, start + len(content), page_idx, *pdf_bb])
        parts.append("\n")
    parts.append("\n")


# ---------------------------------------------------------------------------
# pdfplumber + 列检测
# ---------------------------------------------------------------------------


def parse_pdf_pdfplumber(pdf_bytes: bytes) -> ParsedDocument:
    import pdfplumber

    parts: list[str] = []
    runs: list[list[float]] = []
    pages: list[dict[str, float]] = []
    blocks: list[dict[str, Any]] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            w, h = float(page.width), float(page.height)
            pages.append({"w": w, "h": h})
            chars = list(page.chars or [])
            if parts:
                parts.append("\n")
            base = sum(len(p) for p in parts)
            piece = page_from_chars(chars, w, h, i)
            parts.append(piece.text)
            for run in piece.char_index.runs:
                run = list(run)
                run[0] += base
                run[1] += base
                runs.append(run)
            for blk in piece.char_index.blocks:
                blocks.append({**blk, "start": blk["start"] + base, "end": blk["end"] + base})

    return ParsedDocument(
        canonical_text="".join(parts),
        char_index=CharIndex(pages=pages, runs=runs, blocks=blocks),
        backend_name="pdfplumber",
    )


@dataclass
class _PagePiece:
    text: str
    char_index: CharIndex


def page_from_chars(
    chars: list[dict[str, Any]],
    page_w: float,
    page_h: float,
    page_index: int,
) -> _PagePiece:
    """把一页字符按阅读顺序拼成 canonical text。供 pdfplumber 与单测共用。"""
    usable = [c for c in chars if str(c.get("text") or "")]
    gap = detect_column_gap(usable, page_w)

    def col_of(c: dict) -> int:
        if gap is None:
            return 0
        return 0 if float(c["x0"]) < gap else 1

    # PDF 点：y1 越大越靠上。多栏时先左后右。
    ordered = sorted(usable, key=lambda c: (col_of(c), -float(c["y1"]), float(c["x0"])))

    parts: list[str] = []
    runs: list[list[float]] = []
    prev: dict[str, Any] | None = None
    line_start = 0
    line_sizes: list[tuple[int, int, float, str]] = []  # start, end, size, text

    def _flush_line() -> None:
        nonlocal line_start
        if not parts:
            return
        end = sum(len(p) for p in parts)
        if end <= line_start:
            return
        text = "".join(parts)[line_start:end].strip()
        size = float(prev.get("size") or 0) if prev else 0.0
        line_sizes.append((line_start, end, size, text))
        line_start = end

    for c in ordered:
        ch = str(c["text"])
        bbox = (float(c["x0"]), float(c["y0"]), float(c["x1"]), float(c["y1"]))
        if prev is not None:
            same_col = col_of(c) == col_of(prev)
            y_drop = float(prev["y1"]) - float(c["y1"])
            if not same_col:
                _flush_line()
                parts.append("\n\n")
                _add_ws_run(runs, parts, page_index, bbox)
                line_start = sum(len(p) for p in parts)
            elif y_drop > _Y_LINE_TOL:
                _flush_line()
                parts.append("\n")
                _add_ws_run(runs, parts, page_index, bbox)
                line_start = sum(len(p) for p in parts)
            elif float(c["x0"]) - float(prev["x1"]) > _X_SPACE_GAP and not _no_space_before(ch):
                parts.append(" ")
                _add_ws_run(runs, parts, page_index, bbox)
        start = sum(len(p) for p in parts)
        parts.append(ch)
        runs.append([start, start + len(ch), page_index, *bbox])
        prev = c
    _flush_line()

    text = "".join(parts)
    blocks = _title_blocks_from_lines(line_sizes)
    return _PagePiece(
        text=text,
        char_index=CharIndex(
            pages=[{"w": page_w, "h": page_h}],
            runs=runs,
            blocks=blocks,
        ),
    )


def _add_ws_run(
    runs: list[list[float]],
    parts: list[str],
    page_index: int,
    bbox: tuple[float, float, float, float],
) -> None:
    end = sum(len(p) for p in parts)
    start = end - len(parts[-1]) if parts else 0
    if end > start:
        x0, y0, _, y1 = bbox
        runs.append([start, end, page_index, x0, y0, x0, y1])


def _no_space_before(ch: str) -> bool:
    return ch in "，。、；：）)】,.!?;:"


def _title_blocks_from_lines(lines: list[tuple[int, int, float, str]]) -> list[dict[str, Any]]:
    sizes = [s for _, _, s, t in lines if t and s > 0]
    if not sizes:
        return []
    sizes_sorted = sorted(sizes)
    median = sizes_sorted[len(sizes_sorted) // 2]
    blocks: list[dict[str, Any]] = []
    for start, end, size, text in lines:
        if text and len(text) <= 20 and size >= median * 1.25:
            blocks.append({"start": start, "end": end, "kind": "title", "label": text})
    return blocks


def detect_column_gap(chars: list[dict[str, Any]], page_w: float) -> float | None:
    """在页面中部找一条几乎无字符穿过的竖缝。单栏返回 None。"""
    if page_w < 200 or len(chars) < 12:
        return None
    lo, hi = page_w * _COL_SCAN_LO, page_w * _COL_SCAN_HI
    best_x: float | None = None
    best_score = 0
    x = lo
    while x < hi:
        through = 0
        left_n = 0
        right_n = 0
        for c in chars:
            x0, x1 = float(c["x0"]), float(c["x1"])
            if x0 < x < x1:
                through += 1
            elif x1 <= x:
                left_n += 1
            else:
                right_n += 1
        if through == 0 and left_n >= 4 and right_n >= 4:
            score = min(left_n, right_n)
            if score > best_score:
                best_score = score
                best_x = x
        x += _COL_STEP
    if best_x is None or best_score < 4:
        return None
    return best_x
