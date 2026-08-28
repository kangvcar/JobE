"""简历抽取：先切语义块，再分字段级 / 技能点级两层。

技能点三通道：
  A 词表 Aho-Corasick（高精度，天然带 offset）
  B LLM + 原文回定位（高召回，词表外进新技能候选）
通道 B 命中而 A 未覆盖的表面形式进入待确认。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.domain.models import ProfileSkill, SkillProfile, TextSpan
from app.domain.ports import LLMClient, SpanLocator
from app.extraction.ac import AhoCorasick, latin_word_boundary, prefer_longest
from app.extraction.layout import CharIndex
from app.extraction.normalize import normalize_surface
from app.extraction.ontology import SkillVocabEntry
from app.extraction.store import (
    ClaimRecord,
    DocumentRecord,
    MemoryExtractionStore,
    make_evidence,
    new_id,
    utcnow,
)

logger = logging.getLogger("jobe.extraction.resume")

SECTION_SPECS: list[tuple[str, re.Pattern[str]]] = [
    ("basic", re.compile(r"^(基本信息|个人信息|个人资料|求职意向|personal\s*information)$", re.I)),
    ("education", re.compile(r"^(教育经历|教育背景|教育|education)$", re.I)),
    ("work", re.compile(r"^(工作经历|工作经验|任职经历|职业经历|work\s*experience)$", re.I)),
    ("project", re.compile(r"^(项目经历|项目经验|项目|projects?)$", re.I)),
    ("skill", re.compile(r"^(技能专长|专业技能|技能|掌握技能|技术栈|skills?)$", re.I)),
]

FIELDS_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "educations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "school": {"type": "string"},
                    "degree": {"type": "string"},
                    "dates": {"type": "string"},
                },
            },
        },
        "experiences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "dates": {"type": "string"},
                },
            },
        },
    },
}

SKILLS_SCHEMA = {
    "type": "object",
    "properties": {
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "surface_form": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["surface_form", "quote"],
            },
        }
    },
    "required": ["skills"],
}


@dataclass
class ResumeBlock:
    kind: str
    start: int
    end: int
    text: str


@dataclass
class LocatedField:
    name: str
    value: str
    span: TextSpan


@dataclass
class SkillCandidate:
    surface_form: str
    quote: str
    span: TextSpan


@dataclass
class ResumeExtraction:
    profile: SkillProfile
    fields: list[LocatedField] = field(default_factory=list)
    blocks: list[ResumeBlock] = field(default_factory=list)
    candidates: list[SkillCandidate] = field(default_factory=list)
    discarded: int = 0


def segment_resume(text: str, char_index: CharIndex | None = None) -> list[ResumeBlock]:
    """按标题行 / MinerU title 块切开。无标题时整篇作为一个块。"""
    marks: list[tuple[int, str]] = []
    if char_index:
        for blk in char_index.blocks:
            if blk.get("kind") == "title":
                label = str(blk.get("label") or text[int(blk["start"]) : int(blk["end"])]).strip()
                kind = _kind_of_heading(label)
                if kind:
                    marks.append((int(blk["start"]), kind))
    for m in re.finditer(r"(?m)^(.+)$", text):
        kind = _kind_of_heading(m.group(1).strip())
        if kind:
            marks.append((m.start(), kind))
    # 去重：同一位置保留先出现的
    uniq: dict[int, str] = {}
    for pos, kind in sorted(marks, key=lambda x: x[0]):
        uniq.setdefault(pos, kind)
    ordered = sorted(uniq.items())
    if not ordered:
        return [ResumeBlock(kind="full", start=0, end=len(text), text=text)]
    if ordered[0][0] > 0:
        ordered = [(0, "basic"), *ordered]
    blocks: list[ResumeBlock] = []
    for i, (start, kind) in enumerate(ordered):
        end = ordered[i + 1][0] if i + 1 < len(ordered) else len(text)
        blocks.append(ResumeBlock(kind=kind, start=start, end=end, text=text[start:end]))
    return blocks


def _kind_of_heading(line: str) -> str | None:
    compact = line.strip().strip("：:").strip()
    for kind, pat in SECTION_SPECS:
        if pat.match(compact):
            return kind
    return None


def _too_ambiguous(form: str, entry: SkillVocabEntry) -> bool:
    """全小写的两三字母拉丁别名不进自动机。

    自动机是大小写敏感的，所以 JS / TS / ML / AI 这类大写缩写是安全且高频的写法，必须保留。
    危险的是全小写短串：词表里 Rust 带着别名 rs，会让「rs 报告已提交」被判成 Rust。
    全小写的两三字母拉丁串更可能是普通词（rs、as、no），召回上的损失远小于精度上的收益。
    规范名本身不受此限制——它由词边界检查保护。
    """
    if form == entry.name:
        return False
    return form.isascii() and len(form) <= 3 and form.islower()


def build_automaton(vocab: list[SkillVocabEntry]) -> tuple[AhoCorasick, list[str]]:
    ac = AhoCorasick()
    skill_ids: list[str] = []
    for entry in vocab:
        for form in entry.surface_forms():
            if _too_ambiguous(form, entry):
                continue
            ac.add(form)
            skill_ids.append(entry.id)
    ac.build()
    return ac, skill_ids


def channel_a(text: str, vocab: list[SkillVocabEntry]) -> list[tuple[int, int, str, str]]:
    """(start, end, skill_id, surface)。短拉丁模式要求词边界。"""
    if not vocab:
        return []
    ac, skill_ids = build_automaton(vocab)
    return scan_text(text, ac, skill_ids)


def scan_text(
    text: str, ac: AhoCorasick, skill_ids: list[str]
) -> list[tuple[int, int, str, str]]:
    """channel_a 的可复用形式：自动机只建一次，批量扫职位正文时用。"""
    if not text:
        return []
    raw = ac.finditer(text)
    filtered: list[tuple[int, int, int]] = []
    for start, end, pid in raw:
        pat = ac.patterns[pid]
        if pat.isascii() and not latin_word_boundary(text, start, end):
            continue
        filtered.append((start, end, pid))
    kept = prefer_longest(filtered)
    return [(s, e, skill_ids[pid], text[s:e]) for s, e, pid in kept]


def _covered(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    for a, b in spans:
        if start >= a and end <= b:
            return True
        if start < b and end > a and (min(end, b) - max(start, a)) / max(end - start, 1) >= 0.6:
            return True
    return False


async def extract_resume(
    doc: DocumentRecord,
    *,
    llm: LLMClient,
    locator: SpanLocator,
    store: MemoryExtractionStore,
    vocab: list[SkillVocabEntry],
    source_id: str = "resume",
    user_id: str | None = None,
) -> ResumeExtraction:
    text = doc.canonical_text
    blocks = segment_resume(text, doc.char_index)
    out = ResumeExtraction(
        profile=SkillProfile(
            id=new_id(), user_id=user_id, resume_doc_id=doc.id, created_at=utcnow()
        ),
        blocks=blocks,
    )

    fields_raw = await _extract_fields(llm, text)
    out.fields, dropped_fields = _locate_fields(fields_raw, doc.id, locator, text)
    out.discarded += dropped_fields

    a_hits = channel_a(text, vocab)
    a_spans = [(s, e) for s, e, _, _ in a_hits]
    profile_skills: list[ProfileSkill] = []
    seen_skill: set[str] = set()

    for start, end, skill_id, surface in a_hits:
        # 通道 A 的 offset 由自动机给出，只回填 bbox，不再走 LLM。
        page, bbox = doc.char_index.span_geometry(start, end)
        span = TextSpan(doc_id=doc.id, start=start, end=end, page_index=page, bbox=bbox)
        ev = make_evidence(
            source_id=source_id,
            span=span,
            quote=surface,
            extractor="resume-ac",
            confidence=0.95,
        )
        store.save_evidence(ev)
        if skill_id not in seen_skill:
            seen_skill.add(skill_id)
            profile_skills.append(
                ProfileSkill(skill_id=skill_id, level=0, surface_form=surface, evidence_ids=[ev.id])
            )
        else:
            for ps in profile_skills:
                if ps.skill_id == skill_id:
                    ps.evidence_ids.append(ev.id)
                    break

    b_raw = await llm.complete_json(_skills_prompt(text), SKILLS_SCHEMA)
    for item in b_raw.get("skills") or []:
        quote = str(item.get("quote") or "")
        span = locator.locate(doc.id, quote)
        if span is None:
            logger.info("通道 B 丢弃：quote 不在原文 surface=%s", item.get("surface_form"))
            out.discarded += 1
            continue
        if _covered(span.start, span.end, a_spans):
            continue
        surface = str(item.get("surface_form") or quote)
        ev = make_evidence(
            source_id=source_id,
            span=span,
            quote=text[span.start : span.end],
            extractor="resume-llm",
            confidence=0.7,
        )
        store.save_evidence(ev)
        ctx = text[max(0, span.start - 40) : min(len(text), span.end + 40)]
        decision = await normalize_surface(surface, vocab, llm=llm, store=store, context=ctx)
        if decision.skill_id and decision.skill_id not in seen_skill:
            seen_skill.add(decision.skill_id)
            profile_skills.append(
                ProfileSkill(
                    skill_id=decision.skill_id,
                    level=0,
                    surface_form=surface,
                    evidence_ids=[ev.id],
                )
            )
        elif not decision.skill_id:
            cand = SkillCandidate(surface_form=surface, quote=ev.quote, span=span)
            out.candidates.append(cand)
            store.put_claim(
                ClaimRecord(
                    id=new_id(),
                    kind="new_skill",
                    text=surface,
                    evidence_ids=[ev.id],
                    payload={"quote": ev.quote},
                    doc_id=doc.id,
                )
            )

    out.profile.skills = profile_skills
    store.save_profile(out.profile)
    return out


def _skills_prompt(text: str) -> str:
    return (
        "从简历中抽取技能点。quote 必须是原文精确子串。\n"
        "不要输出坐标。技能点是最细可验证粒度，不要写成能力项陈述。\n"
        f"原文：\n---\n{text}\n---"
    )


async def _extract_fields(llm: LLMClient, text: str) -> dict:
    prompt = (
        "从简历抽取字段。每个值必须是原文中出现过的精确子串；没有就省略。\n"
        "不要输出坐标。\n"
        f"原文：\n---\n{text}\n---"
    )
    return await llm.complete_json(prompt, FIELDS_SCHEMA)


def _locate_fields(
    raw: dict,
    doc_id: str,
    locator: SpanLocator,
    text: str,
) -> tuple[list[LocatedField], int]:
    located: list[LocatedField] = []
    discarded = 0

    def _one(name: str, quote: str | None) -> None:
        nonlocal discarded
        if not quote:
            return
        span = locator.locate(doc_id, str(quote))
        if span is None:
            discarded += 1
            return
        located.append(LocatedField(name=name, value=text[span.start : span.end], span=span))

    _one("name", raw.get("name"))
    for i, edu in enumerate(raw.get("educations") or []):
        _one(f"education.{i}.school", edu.get("school"))
        _one(f"education.{i}.degree", edu.get("degree"))
        _one(f"education.{i}.dates", edu.get("dates"))
    for i, exp in enumerate(raw.get("experiences") or []):
        _one(f"experience.{i}.company", exp.get("company"))
        _one(f"experience.{i}.title", exp.get("title"))
        _one(f"experience.{i}.dates", exp.get("dates"))
    return located, discarded
