from __future__ import annotations

from app.extraction.ac import AhoCorasick, latin_word_boundary, prefer_longest


def test_finditer_and_longest():
    ac = AhoCorasick()
    ac.add("Java")
    ac.add("JavaScript")
    ac.build()
    hits = ac.finditer("JavaScript 与 Java")
    kept = prefer_longest(hits)
    texts = [ac.patterns[p] for _, _, p in [(s, e, p) for s, e, p in kept]]
    # JavaScript 覆盖开头的 Java；后面独立的 Java 保留
    assert texts == ["JavaScript", "Java"]


def test_latin_boundary_chinese_neighbor():
    text = "精通 Go 语言"
    i = text.find("Go")
    assert latin_word_boundary(text, i, i + 2)
    text2 = "Going"
    assert not latin_word_boundary(text2, 0, 2)
