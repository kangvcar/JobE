import { CURRENT_PERIOD, ONTOLOGY_VERSION, PREVIOUS_PERIOD, signalBand } from "../labels";
import type {
  Burst,
  CandidateCard,
  Competency,
  CompetencyChange,
  Evidence,
  EvidenceDetail,
  EvidenceGrade,
  GraphEdge,
  GraphNode,
  GraphPayload,
  GraphView,
  LeadLag,
  MarketOverview,
  ReviewItem,
  Role,
  RoleDetail,
  Skill,
  SkillCluster,
  SkillDetail,
  SkillObservation,
  SourceDocument,
} from "../types";
import {
  PERIODS,
  SOURCES,
  buildRoles,
  buildSkills,
  LEVEL_PARENTS,
  type BuiltCatalog,
} from "./catalog";
import { DOCUMENTS } from "./documents";

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const catalog: BuiltCatalog = buildSkills();
const skillByName = new Map(catalog.skills.map((s) => [s.name, s]));
const skillById = new Map(catalog.skills.map((s) => [s.id, s]));
const clusterById = new Map(catalog.clusters.map((c) => [c.id, c]));
const builtRoles = buildRoles(skillByName);
const roleById = new Map(builtRoles.roles.map((r) => [r.id, r]));

const HOT_SKILLS = [
  "RAG",
  "智能体编排",
  "vLLM",
  "提示词工程",
  "向量数据库",
  "Kubernetes",
  "PyTorch",
  "LoRA",
  "模型评测",
  "混合检索",
  "MCP",
  "量化部署",
  "CUDA",
  "Spark",
  "Transformer",
  "端侧推理",
  "提示注入防护",
  "合成数据",
  "文档解析",
  "Triton",
  "Faiss",
  "灰度发布",
  "数据漂移监控",
  "Function Calling",
];

function hashId(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

function gradeForSkill(skillId: string): EvidenceGrade {
  const n = hashId(skillId) % 10;
  if (n === 0) return "weak";
  if (n < 4) return "single_source";
  return "multi_source";
}

function makeEvidence(): Evidence[] {
  const out: Evidence[] = [];
  for (const skill of catalog.skills) {
    const grade = gradeForSkill(skill.id);
    const count = grade === "weak" ? 1 : grade === "single_source" ? 1 : 2 + (hashId(skill.id) % 2);
    for (let i = 0; i < count; i++) {
      const src = SOURCES[(hashId(skill.id) + i) % SOURCES.length];
      const isResume = i === 0 && hashId(skill.id) % 7 === 0;
      const doc = isResume ? DOCUMENTS.resume_gapped : DOCUMENTS.posting_llm;
      const needle = skill.name;
      const start = Math.max(0, doc.text.indexOf(needle));
      const end = start >= 0 && doc.text.includes(needle) ? start + needle.length : 12 + needle.length;
      out.push({
        id: `ev_${skill.id}_${i}`,
        source_id: src.id,
        span: {
          doc_id: doc.id,
          start: start < 0 ? 0 : start,
          end,
          page_index: isResume ? 0 : null,
          bbox: isResume ? [0.12, 0.42 + (i % 3) * 0.06, 0.78, 0.48 + (i % 3) * 0.06] : null,
        },
        quote: doc.text.includes(skill.name) ? skill.name : `${skill.name}相关要求见原文。`,
        fetched_at: `2025-${String((hashId(skill.id) % 12) + 1).padStart(2, "0")}-${String((i % 27) + 1).padStart(2, "0")}T10:14:00+08:00`,
        extractor: "span_locator",
        confidence: grade === "weak" ? 0.41 : grade === "single_source" ? 0.63 : 0.88,
        posting_id: isResume ? null : "posting_llm_01",
      });
    }
  }
  return out;
}

const evidenceAll = makeEvidence();

function pushResumeEvidence(): void {
  const rows: { skill: string; doc: string; bbox: [number, number, number, number] }[] = [
    { skill: "Python", doc: "resume_gapped", bbox: [0.12, 0.38, 0.88, 0.46] },
    { skill: "PyTorch", doc: "resume_gapped", bbox: [0.12, 0.26, 0.88, 0.34] },
    { skill: "提示词工程", doc: "resume_gapped", bbox: [0.12, 0.44, 0.88, 0.52] },
    { skill: "Python", doc: "resume_strong", bbox: [0.12, 0.44, 0.88, 0.52] },
    { skill: "Kubernetes", doc: "resume_strong", bbox: [0.12, 0.32, 0.88, 0.4] },
    { skill: "MLflow", doc: "resume_strong", bbox: [0.12, 0.26, 0.88, 0.34] },
  ];
  for (const row of rows) {
    const skill = skillByName.get(row.skill);
    const doc = DOCUMENTS[row.doc];
    if (!skill || !doc) continue;
    const start = Math.max(0, doc.text.indexOf(row.skill));
    evidenceAll.push({
      id: `ev_resume_${row.doc}_${skill.id}`,
      source_id: "src_mohrss",
      span: {
        doc_id: doc.id,
        start,
        end: start + row.skill.length,
        page_index: 0,
        bbox: row.bbox,
      },
      quote: row.skill,
      fetched_at: "2026-02-26T10:04:00+08:00",
      extractor: "span_locator",
      confidence: 0.91,
      posting_id: null,
    });
  }
}
pushResumeEvidence();

const evidenceBySkill = new Map<string, Evidence[]>();
for (const ev of evidenceAll) {
  const sid = ev.id.split("_").slice(1, -1).join("_");
  const list = evidenceBySkill.get(sid) ?? [];
  list.push(ev);
  evidenceBySkill.set(sid, list);
}

function evidenceIdsFor(skillId: string): string[] {
  return (evidenceBySkill.get(skillId) ?? []).map((e) => e.id);
}

for (const role of builtRoles.roles) {
  const ids = builtRoles.roleSkillIds[role.id] ?? [];
  const cap = role.state === "unverified" ? (role.signal_strength != null && role.signal_strength < 0.2 ? 1 : 2) : 6;
  role.evidence_ids = ids.flatMap((sid) => evidenceIdsFor(sid)).slice(0, cap);
}

function makeObservations(): SkillObservation[] {
  const out: SkillObservation[] = [];
  const tracked = new Set(
    [...HOT_SKILLS.map((n) => skillByName.get(n)?.id).filter(Boolean), ...catalog.skills.slice(0, 40).map((s) => s.id)] as string[],
  );
  for (const skill of catalog.skills) {
    const rng = mulberry32(hashId(skill.id));
    const hot = tracked.has(skill.id);
    const periods = hot ? PERIODS : PERIODS.slice(-4);
    let base = 0.04 + rng() * 0.12;
    for (const period of periods) {
      const idx = PERIODS.indexOf(period);
      let bump = 0;
      if (skill.name === "RAG" && idx >= 10) bump = 0.18 + (idx - 10) * 0.03;
      if (skill.name === "智能体编排" && idx >= 14) bump = 0.12 + (idx - 14) * 0.04;
      if (skill.name === "vLLM" && idx >= 15) bump = 0.09 + (idx - 15) * 0.035;
      if (skill.name === "提示词工程" && idx >= 9 && idx <= 16) bump = 0.14;
      if (skill.name === "XGBoost" && idx >= 12) bump = -0.03;
      if (skill.name === "Hive" && idx >= 8) bump = -0.02 * (idx - 8);
      const weight = Math.max(0.01, Math.min(0.62, base + bump + (rng() - 0.5) * 0.03));
      let finalWeight = weight;
      if (period === CURRENT_PERIOD && ["RAG", "智能体编排", "vLLM", "MCP"].includes(skill.name)) {
        finalWeight = Math.min(0.62, weight + 0.045);
      }
      const total = 1800 + idx * 90 + Math.floor(rng() * 80);
      const posting_count = Math.max(4, Math.round(finalWeight * total));
      out.push({
        role_id: null,
        skill_id: skill.id,
        period,
        weight: Number(finalWeight.toFixed(4)),
        posting_count,
        total_postings: total,
        ontology_version: ONTOLOGY_VERSION,
      });
      base = weight * 0.85 + base * 0.15;
    }
  }
  return out;
}

const observations = makeObservations();
const riseBump: Record<string, number> = {
  RAG: 0.043,
  智能体编排: 0.051,
  vLLM: 0.037,
  MCP: 0.029,
};
for (const [name, bump] of Object.entries(riseBump)) {
  const id = skillByName.get(name)?.id;
  if (!id) continue;
  const prev = observations.find((o) => o.skill_id === id && o.period === PREVIOUS_PERIOD);
  const cur = observations.find((o) => o.skill_id === id && o.period === CURRENT_PERIOD);
  if (prev && cur) {
    prev.weight = Number(Math.max(0.08, cur.weight - bump).toFixed(4));
  }
}

function makeBursts(): Burst[] {
  return [
    { skill_id: skillByName.get("RAG")!.id, source_id: "src_github", start_period: "2023Q3", end_period: "2024Q1", level: 2, weight: 0.41 },
    { skill_id: skillByName.get("RAG")!.id, source_id: "src_mohrss", start_period: "2024Q1", end_period: "2024Q3", level: 2, weight: 0.37 },
    { skill_id: skillByName.get("智能体编排")!.id, source_id: "src_papers", start_period: "2024Q3", end_period: "2025Q1", level: 2, weight: 0.44 },
    { skill_id: skillByName.get("智能体编排")!.id, source_id: "src_moka", start_period: "2025Q1", end_period: "2025Q3", level: 1, weight: 0.29 },
    { skill_id: skillByName.get("vLLM")!.id, source_id: "src_pypi", start_period: "2024Q4", end_period: "2025Q2", level: 2, weight: 0.39 },
    { skill_id: skillByName.get("MCP")!.id, source_id: "src_github", start_period: "2025Q3", end_period: "2026Q1", level: 1, weight: 0.22 },
    { skill_id: skillByName.get("提示注入防护")!.id, source_id: "src_papers", start_period: "2024Q2", end_period: "2024Q4", level: 1, weight: 0.18 },
    { skill_id: skillByName.get("端侧推理")!.id, source_id: "src_github", start_period: "2025Q1", end_period: "2025Q4", level: 1, weight: 0.21 },
  ];
}

const bursts = makeBursts();

function makeLeadLag(): LeadLag[] {
  return [
    { skill_id: skillByName.get("RAG")!.id, leading_source_id: "src_github", lagging_source_id: "src_mohrss", lag_periods: 2, correlation: 0.71, p_value: 0.018 },
    { skill_id: skillByName.get("智能体编排")!.id, leading_source_id: "src_papers", lagging_source_id: "src_moka", lag_periods: 2, correlation: 0.64, p_value: 0.031 },
    { skill_id: skillByName.get("vLLM")!.id, leading_source_id: "src_pypi", lagging_source_id: "src_moka", lag_periods: 1, correlation: 0.58, p_value: 0.044 },
    { skill_id: skillByName.get("MCP")!.id, leading_source_id: "src_github", lagging_source_id: "src_mohrss", lag_periods: 3, correlation: 0.41, p_value: 0.12 },
  ];
}

const leadLag = makeLeadLag();

function makeCompetencies(): Competency[] {
  const out: Competency[] = [];
  for (const role of builtRoles.roles) {
    if (role.state !== "published") continue;
    const ids = builtRoles.roleSkillIds[role.id] ?? [];
    const chunks = [ids.slice(0, 3), ids.slice(3, 6), ids.slice(6, 9)].filter((c) => c.length);
    chunks.forEach((chunk, i) => {
      const names = chunk.map((id) => skillById.get(id)?.name).filter(Boolean).join("、");
      const grade = chunk.some((id) => gradeForSkill(id) === "weak") ? "single_source" : "multi_source";
      out.push({
        id: `comp_${role.id}_${i}`,
        role_id: role.id,
        statement: i === 0 ? `能独立完成与${names}相关的核心工作` : `在项目中使用${names}`,
        skill_ids: chunk,
        necessity: i === 0 ? "required" : "bonus",
        importance: Number((0.9 - i * 0.18).toFixed(2)),
        evidence_ids: chunk.flatMap((id) => evidenceIdsFor(id)).slice(0, 4),
        grade,
        state: "published",
      });
    });
  }
  return out;
}

const competencies = makeCompetencies();

function makeChanges(): CompetencyChange[] {
  const llm = competencies.find((c) => c.role_id === "role_llm_app");
  const mlops = competencies.find((c) => c.role_id === "role_mlops");
  const prompt = competencies.find((c) => c.role_id === "role_prompt");
  return [
    {
      id: "chg_llm_rag",
      role_id: "role_llm_app",
      competency_id: llm?.id ?? "comp_role_llm_app_0",
      kind: "added",
      before: null,
      after: "能独立完成与RAG、向量数据库相关的核心工作",
      reason: "2025Q4 起该岗位职位里检索增强从加分项变成几乎必写。开源仓库信号领先两个时间片。",
      evidence_ids: evidenceIdsFor(skillByName.get("RAG")!.id).slice(0, 2),
      occurred_on: "2025-10-08",
      recorded_at: "2025-10-09T02:11:00+08:00",
      state: "published",
    },
    {
      id: "chg_llm_agent",
      role_id: "role_llm_app",
      competency_id: llm?.id ?? "comp_role_llm_app_0",
      kind: "added",
      before: null,
      after: "在项目中使用智能体编排、MCP",
      reason: "工具调用和多步任务出现在同一批职位里，不再是演示项目。",
      evidence_ids: evidenceIdsFor(skillByName.get("智能体编排")!.id).slice(0, 2),
      occurred_on: "2026-01-12",
      recorded_at: "2026-01-13T04:02:00+08:00",
      state: "published",
    },
    {
      id: "chg_llm_finetune_script",
      role_id: "role_llm_app",
      competency_id: llm?.id ?? "comp_role_llm_app_0",
      kind: "removed",
      before: "能从零写单机微调脚本",
      after: null,
      reason: "职位仍抄旧模板，但去近重复后该能力项占比掉到基线以下。疑似技能通胀，已删除。",
      evidence_ids: evidenceIdsFor(skillByName.get("指令微调")!.id).slice(0, 1),
      occurred_on: "2025-11-20",
      recorded_at: "2025-11-21T01:40:00+08:00",
      state: "published",
    },
    {
      id: "chg_mlops_gpu",
      role_id: "role_mlops",
      competency_id: mlops?.id ?? "comp_role_mlops_0",
      kind: "modified",
      before: "会用单机 GPU 跑通训练",
      after: "能做 GPU 调度与训练并行",
      reason: "集群调度从加分变成该岗位能力项的主句。",
      evidence_ids: evidenceIdsFor(skillByName.get("GPU 调度")!.id).slice(0, 2),
      occurred_on: "2025-07-03",
      recorded_at: "2025-07-04T09:18:00+08:00",
      state: "published",
    },
    {
      id: "chg_prompt_held",
      role_id: "role_prompt",
      competency_id: prompt?.id ?? "comp_role_prompt_0",
      kind: "removed",
      before: "提示词工程为该岗位唯一核心必备技能",
      after: null,
      reason: "统计上该技能点被并入大模型应用工程师。删除会抽空本岗位内核，进入人工拦截。",
      evidence_ids: evidenceIdsFor(skillByName.get("提示词工程")!.id).slice(0, 2),
      occurred_on: "2026-02-01",
      recorded_at: "2026-02-01T16:03:00+08:00",
      state: "held",
    },
  ];
}

const changes = makeChanges();

export function graphPayload(view: GraphView): GraphPayload {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];

  if (view === "stack") {
    for (const cluster of catalog.clusters) {
      nodes.push({ id: cluster.id, kind: "cluster", label: cluster.name, stack: cluster.id });
    }
  } else {
    for (const level of Object.values(LEVEL_PARENTS)) {
      nodes.push({ id: level.id, kind: "level", label: level.name, level: level.id });
    }
  }

  for (const skill of catalog.skills) {
    const grade = gradeForSkill(skill.id);
    const parent =
      view === "stack"
        ? (skill.cluster_id ?? undefined)
        : LEVEL_PARENTS[catalog.skillLevel[skill.id] ?? "method"].id;
    nodes.push({
      id: skill.id,
      kind: "skill",
      label: skill.name,
      parent,
      stack: skill.cluster_id ?? undefined,
      level: LEVEL_PARENTS[catalog.skillLevel[skill.id] ?? "method"].id,
      grade,
    });
    if (parent) {
      edges.push({
        id: `e_member_${skill.id}`,
        source: parent,
        target: skill.id,
        kind: "member",
      });
    }
    if (skill.parent_id && view === "stack") {
      edges.push({
        id: `e_parent_${skill.id}`,
        source: skill.parent_id,
        target: skill.id,
        kind: "parent",
      });
    }
  }

  for (const role of builtRoles.roles) {
    nodes.push({
      id: role.id,
      kind: "role",
      label: role.name,
      emerging: role.is_emerging && role.state === "published",
      candidate: role.state === "unverified",
    });
    for (const sid of builtRoles.roleSkillIds[role.id] ?? []) {
      edges.push({
        id: `e_req_${role.id}_${sid}`,
        source: role.id,
        target: sid,
        kind: "requires",
        necessity: "required",
      });
    }
  }

  return {
    nodes,
    edges,
    clusters: catalog.clusters,
    families: builtRoles.families,
    period: CURRENT_PERIOD,
  };
}

export function listRoles(): Role[] {
  return builtRoles.roles;
}

export function getRole(id: string): Role | undefined {
  return roleById.get(id);
}

export function getSkill(id: string): Skill | undefined {
  return skillById.get(id);
}

export function getCluster(id: string): SkillCluster | undefined {
  return clusterById.get(id);
}

export function skillName(id: string): string {
  return skillById.get(id)?.name ?? id;
}

export function roleName(id: string): string {
  return roleById.get(id)?.name ?? id;
}

export function roleSkills(roleId: string): string[] {
  return builtRoles.roleSkillIds[roleId] ?? [];
}

export function roleDetail(id: string): RoleDetail | null {
  const role = roleById.get(id);
  if (!role) return null;
  const comps = competencies.filter((c) => c.role_id === id);
  const chg = changes.filter((c) => c.role_id === id);
  const skills = (builtRoles.roleSkillIds[id] ?? [])
    .map((sid) => skillById.get(sid))
    .filter((s): s is Skill => Boolean(s));
  return { role, competencies: comps, changes: chg, skills };
}

export function skillDetail(id: string): SkillDetail | null {
  const skill = skillById.get(id);
  if (!skill) return null;
  const cluster = skill.cluster_id ? clusterById.get(skill.cluster_id) ?? null : null;
  const roles = builtRoles.roles.filter((r) => (builtRoles.roleSkillIds[r.id] ?? []).includes(id));
  return {
    skill,
    cluster,
    grade: gradeForSkill(id),
    evidence_ids: evidenceIdsFor(id),
    observations: observations.filter((o) => o.skill_id === id),
    bursts: bursts.filter((b) => b.skill_id === id),
    lead_lag: leadLag.find((l) => l.skill_id === id) ?? null,
    roles,
  };
}

export function marketOverview(): MarketOverview {
  const emerging = builtRoles.roles.filter((r) => r.is_emerging && r.state === "published");
  const candidates: CandidateCard[] = builtRoles.roles
    .filter((r) => r.state === "unverified")
    .map((r) => ({
      ...r,
      evidence_count: r.evidence_ids.length,
      signal_band: signalBand(r.signal_strength),
    }));
  const trend_skill_ids = HOT_SKILLS.map((n) => skillByName.get(n)?.id).filter((id): id is string => Boolean(id));
  return {
    period: CURRENT_PERIOD,
    emerging,
    candidates,
    changes: changes.filter((c) => c.state === "published"),
    bursts,
    lead_lag: leadLag,
    trend_skill_ids,
    observations: observations.filter((o) => trend_skill_ids.includes(o.skill_id)),
  };
}

export function observationAt(skillId: string, period: string): SkillObservation | undefined {
  return observations.find((o) => o.skill_id === skillId && o.period === period);
}

export function movesForRole(roleId: string): { rising: { skill_id: string; delta: number }[]; falling: { skill_id: string; delta: number }[] } {
  const ids = builtRoles.roleSkillIds[roleId] ?? [];
  const rising: { skill_id: string; delta: number }[] = [];
  const falling: { skill_id: string; delta: number }[] = [];
  for (const id of ids) {
    const now = observationAt(id, CURRENT_PERIOD)?.weight ?? 0;
    const prev = observationAt(id, PREVIOUS_PERIOD)?.weight ?? now;
    const delta = now - prev;
    if (delta > 0.015) rising.push({ skill_id: id, delta });
    else if (delta < -0.01) falling.push({ skill_id: id, delta });
  }
  rising.sort((a, b) => b.delta - a.delta);
  falling.sort((a, b) => a.delta - b.delta);
  return { rising, falling };
}

function documentById(id: string): SourceDocument {
  return DOCUMENTS[id] ?? DOCUMENTS.posting_llm;
}

export function evidenceDetail(id: string): EvidenceDetail | null {
  const ev = evidenceAll.find((e) => e.id === id);
  if (!ev) return null;
  const src = SOURCES.find((s) => s.id === ev.source_id);
  const parts = id.split("_");
  const skillId = parts.slice(1, -1).join("_");
  const role = builtRoles.roles.find((r) => r.evidence_ids.includes(id));
  const doc = documentById(ev.span.doc_id);
  const start = ev.span.start;
  const end = ev.span.end;
  const quote =
    doc.text.slice(start, end).trim() ||
    skillById.get(skillId)?.name ||
    ev.quote;
  return {
    ...ev,
    quote,
    source_name: src?.name ?? ev.source_id,
    skill_id: skillById.has(skillId) ? skillId : null,
    role_id: role?.id ?? null,
    document: doc,
  };
}

export function evidenceBatch(ids: string[]): EvidenceDetail[] {
  return ids.map(evidenceDetail).filter((e): e is EvidenceDetail => Boolean(e));
}

export const reviewQueue: ReviewItem[] = [
  {
    id: "rev_emerging_router",
    kind: "emerging_publish",
    title: "候选岗位「模型路由工程师」达到发布阈值",
    body: "连续三个时间片职位占比越过门槛，但国家标准职业目录无对应条目。按规则需人工确认后才能作为新兴岗位发布。",
    role_id: "role_cand_router",
    skill_id: null,
    evidence_ids: evidenceIdsFor(skillByName.get("vLLM")!.id).slice(0, 2),
    ai_verdict: "supported",
    created_at: "2026-02-18T09:12:00+08:00",
  },
  {
    id: "rev_prompt_removed",
    kind: "required_removed",
    title: "提示词工程师的核心必备技能面临删除",
    body: "能力变更已写入拦截。删除「提示词工程」会抽空该岗位内核，即使统计信号显示它被更大的岗位吸收。",
    role_id: "role_prompt",
    skill_id: skillByName.get("提示词工程")!.id,
    evidence_ids: evidenceIdsFor(skillByName.get("提示词工程")!.id).slice(0, 2),
    ai_verdict: "uncertain",
    created_at: "2026-02-01T16:10:00+08:00",
  },
  {
    id: "rev_mcp_conflict",
    kind: "signal_conflict",
    title: "MCP 的统计突增与 AI 审核员结论不一致",
    body: "开源仓库信号显示突增，但审核员认为多数职位只是把协议名写进模板段落，证据不足以支撑能力项。",
    role_id: "role_agent",
    skill_id: skillByName.get("MCP")!.id,
    evidence_ids: evidenceIdsFor(skillByName.get("MCP")!.id).slice(0, 1),
    ai_verdict: "unsupported",
    created_at: "2026-02-20T13:44:00+08:00",
  },
  {
    id: "rev_report_curator",
    kind: "user_report",
    title: "有人举报「多模态数据策展人」不像一个岗位",
    body: "举报称这只是数据清洗工作的新名字。当前信号弱，证据只有一条。需要决定是驳回候选还是继续观察。",
    role_id: "role_cand_curator",
    skill_id: null,
    evidence_ids: evidenceIdsFor(skillByName.get("数据清洗")!.id).slice(0, 1),
    ai_verdict: null,
    created_at: "2026-02-22T18:03:00+08:00",
  },
];

export const fixtureMeta = {
  node_count_stack: graphPayload("stack").nodes.length,
  skill_count: catalog.skills.length,
  role_count: builtRoles.roles.length,
  cluster_count: catalog.clusters.length,
  period_count: PERIODS.length,
};

export { catalog, competencies, observations, bursts, leadLag, changes, CURRENT_PERIOD, PREVIOUS_PERIOD, skillByName, skillById, evidenceAll, gradeForSkill, evidenceIdsFor };
