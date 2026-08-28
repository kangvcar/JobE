from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.extraction.layout import (
    CharIndex,
    MinerUUnavailable,
    detect_column_gap,
    detect_coord_space,
    docx_to_pdf,
    from_mineru_middle,
    invoke_mineru,
    page_from_chars,
    parse_document,
    parse_pdf,
    parse_plain_text,
    to_pdf_points,
)
from tests.extraction.conftest import FIXTURE_DIR


def _char(text: str, x0: float, y0: float, y1: float, size: float = 10) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + 8, "y0": y0, "y1": y1, "size": size}


def test_char_index_json_roundtrip():
    idx = CharIndex(
        pages=[{"w": 10.0, "h": 20.0}],
        runs=[[0, 3, 0, 1.0, 2.0, 3.0, 4.0]],
        blocks=[{"start": 0, "end": 3, "kind": "title"}],
    )
    restored = CharIndex.from_json(idx.to_json())
    assert restored.runs[0][2] == 0
    assert CharIndex.from_json(None).runs == []


def test_parse_pdf_uses_mineru(monkeypatch):
    middle = json.loads((FIXTURE_DIR / "middle.json").read_text(encoding="utf-8"))
    monkeypatch.setattr("app.extraction.layout.invoke_mineru", lambda _b: middle)
    doc = parse_pdf(b"%PDF")
    assert doc.backend_name == "mineru"


def test_pdfplumber_assembles_chars(monkeypatch):
    import pdfplumber

    from app.extraction.layout import parse_pdf_pdfplumber

    class Page:
        width = 612.0
        height = 792.0
        chars = [
            {"text": "H", "x0": 100, "x1": 108, "y0": 700, "y1": 712, "size": 12},
            {"text": "i", "x0": 108.5, "x1": 114, "y0": 700, "y1": 712, "size": 12},
        ]

    class Pdf:
        pages = [Page()]

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return None

    monkeypatch.setattr(pdfplumber, "open", lambda *_a, **_k: Pdf())
    doc = parse_pdf_pdfplumber(b"%PDF")
    assert "H" in doc.canonical_text and "i" in doc.canonical_text
    assert doc.backend_name == "pdfplumber"


def test_docx_convert_nonzero(monkeypatch):
    import subprocess

    monkeypatch.setattr("app.extraction.layout.shutil.which", lambda _n: "/usr/bin/soffice")

    def fake_run(cmd, **_kw):
        return subprocess.CompletedProcess(cmd, 1, "", "boom")

    monkeypatch.setattr("app.extraction.layout.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="转换"):
        docx_to_pdf(b"PK")


def test_mineru_skips_image_blocks():
    middle = {
        "_backend": "vlm",
        "pdf_info": [
            {
                "page_idx": 0,
                "page_size": [100, 200],
                "para_blocks": [
                    {
                        "type": "image",
                        "lines": [{"spans": [{"content": "IMG", "bbox": [0.1, 0.1, 0.2, 0.2]}]}],
                    },
                    {
                        "type": "text",
                        "blocks": [
                            {
                                "type": "text",
                                "lines": [
                                    {
                                        "spans": [
                                            {
                                                "type": "text",
                                                "content": "Hi",
                                                "bbox": [0.1, 0.3, 0.5, 0.4],
                                            }
                                        ]
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ],
    }
    doc = from_mineru_middle(middle)
    assert "Hi" in doc.canonical_text
    assert "IMG" not in doc.canonical_text
    doc = parse_plain_text("你好")
    assert doc.canonical_text == "你好"
    assert doc.backend_name == "plain"
    dumped = doc.char_index.to_json()
    assert dumped["space"] == "pdf_points"


def test_parse_document_txt():
    doc = parse_document("简历正文".encode(), "cv.txt")
    assert doc.canonical_text == "简历正文"


def test_coord_space_pipeline_overflow():
    # 800 > 页面宽 612 → 判定为 0-1000，而不是绝对坐标
    space = detect_coord_space([(100, 100, 800, 140)], 612, 792, backend=None)
    assert space == "norm_0_1000"
    assert detect_coord_space([(0.1, 0.1, 0.4, 0.2)], 612, 792) == "norm_0_1"
    assert detect_coord_space([(10, 10, 50, 40)], 612, 792) == "pdf_points"
    assert detect_coord_space([], 612, 792, backend="vlm") == "norm_0_1"
    assert detect_coord_space([], 612, 792, backend="pipeline") == "norm_0_1000"


def test_to_pdf_points_flips_origin():
    # MinerU 顶边 y=0；转 PDF 点后应靠近 page_h
    x0, y0, x1, y1 = to_pdf_points((0, 0, 1000, 100), 612, 792, "norm_0_1000", origin="top_left")
    assert x0 == pytest.approx(0)
    assert x1 == pytest.approx(612)
    assert y1 == pytest.approx(792)
    assert y0 == pytest.approx(792 - 79.2)

    a = to_pdf_points((0.1, 0.1, 0.5, 0.2), 100, 200, "norm_0_1", origin="top_left")
    assert a[0] == pytest.approx(10)
    assert a[2] == pytest.approx(50)
    assert a[1] == pytest.approx(160)
    assert a[3] == pytest.approx(180)


def test_from_mineru_middle_fixture():
    middle = json.loads((FIXTURE_DIR / "middle.json").read_text(encoding="utf-8"))
    doc = from_mineru_middle(middle)
    assert "精通 Python 与 Go" in doc.canonical_text
    assert "工作经历" in doc.canonical_text
    assert doc.backend_name == "mineru"
    assert any(b.get("kind") == "title" for b in doc.char_index.blocks)
    page, bbox = doc.char_index.span_geometry(0, 4)
    assert page == 0
    assert bbox is not None


def test_column_detection_two_columns():
    left = [_char("L", 20, 700 - i, 712 - i) for i in range(8)]
    right = [_char("R", 400, 700 - i, 712 - i) for i in range(8)]
    chars = left + right
    gap = detect_column_gap(chars, 600)
    assert gap is not None
    assert 50 < gap < 390
    piece = page_from_chars(chars, 600, 800, 0)
    # 先左栏后右栏，不应在同一行交错
    body = piece.text.replace(" ", "")
    assert body.index("L") < body.index("R")
    assert "\n" in piece.text


def test_column_detection_single_column():
    chars = [_char("A", 40 + i * 9, 700, 712) for i in range(20)]
    assert detect_column_gap(chars, 600) is None


def test_docx_without_libreoffice(monkeypatch):
    monkeypatch.setattr("app.extraction.layout.shutil.which", lambda _n: None)
    with pytest.raises(RuntimeError, match="LibreOffice"):
        docx_to_pdf(b"PK")


def test_docx_convert_success(monkeypatch):
    import subprocess

    monkeypatch.setattr("app.extraction.layout.shutil.which", lambda _n: "/usr/bin/soffice")

    def fake_run(cmd, **_kw):
        out = Path(cmd[cmd.index("--outdir") + 1])
        (out / "in.pdf").write_bytes(b"%PDF-ok")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("app.extraction.layout.subprocess.run", fake_run)
    assert docx_to_pdf(b"PK") == b"%PDF-ok"


def test_parse_docx_uses_pdf_pipeline(monkeypatch):
    monkeypatch.setattr("app.extraction.layout.docx_to_pdf", lambda _b: b"%PDF-fake")
    monkeypatch.setattr(
        "app.extraction.layout.parse_pdf",
        lambda _b, prefer=None: parse_plain_text("from-docx"),
    )
    doc = parse_document(b"PK", "a.docx")
    assert doc.canonical_text == "from-docx"


def test_invoke_mineru_unavailable():
    with pytest.raises(MinerUUnavailable, match="magic-pdf"):
        invoke_mineru(b"%PDF")


def test_parse_pdf_falls_back_to_pdfplumber(monkeypatch, caplog):
    caplog.set_level("WARNING")

    def fake_plumber(_b):
        p = parse_plain_text("plumber")
        p.backend_name = "pdfplumber"
        return p

    monkeypatch.setattr(
        "app.extraction.layout.invoke_mineru",
        lambda _b: (_ for _ in ()).throw(MinerUUnavailable("未安装")),
    )
    monkeypatch.setattr("app.extraction.layout.parse_pdf_pdfplumber", fake_plumber)
    doc = parse_pdf(b"%PDF-1.4")
    assert doc.backend_name == "pdfplumber"
    assert "MinerU 不可用" in caplog.text


def test_parse_pdf_prefer_pdfplumber(monkeypatch):
    monkeypatch.setattr(
        "app.extraction.layout.parse_pdf_pdfplumber",
        lambda _b: parse_plain_text("forced"),
    )
    called = {"mineru": False}
    monkeypatch.setattr(
        "app.extraction.layout.invoke_mineru",
        lambda _b: called.__setitem__("mineru", True),
    )
    doc = parse_pdf(b"%PDF", prefer="pdfplumber")
    assert doc.canonical_text == "forced"
    assert called["mineru"] is False
