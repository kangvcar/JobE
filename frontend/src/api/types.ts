/**
 * 领域类型，字段名与 backend/app/domain/models.py 保持 snake_case 一致。
 * 前端不在边界做驼峰转换，联调时 JSON 原样进出。
 */

export type EvidenceGrade = "multi_source" | "single_source" | "weak";
export type PublishState = "unverified" | "held" | "published" | "rejected";
export type Necessity = "required" | "bonus";
export type ChangeKind = "added" | "removed" | "modified";
export type MatchTier = "strong" | "adequate" | "gapped" | "mismatch";
export type GapKind = "missing" | "insufficient" | "surplus";
export type ReviewVerdict = "supported" | "unsupported" | "uncertain";
export type GraphView = "stack" | "level";
export type GraphRenderer = "webgl" | "canvas";
export type DocumentKind = "resume" | "posting";

export type TextSpan = {
  doc_id: string;
  start: number;
  end: number;
  page_index: number | null;
  /** PDF 页内归一化框 [x0, y0, x1, y1]，原点在左上。 */
  bbox: [number, number, number, number] | null;
};

export type Source = {
  id: string;
  name: string;
  license: string;
  requires_login: boolean;
  is_leading_indicator: boolean;
};

export type Evidence = {
  id: string;
  source_id: string;
  span: TextSpan;
  quote: string;
  fetched_at: string;
  extractor: string;
  confidence: number;
  posting_id: string | null;
};

export type Skill = {
  id: string;
  name: string;
  aliases: string[];
  parent_id: string | null;
  cluster_id: string | null;
  ontology_version: string;
  external_ids: Record<string, string>;
};

export type SkillCluster = {
  id: string;
  name: string;
  skill_ids: string[];
  ontology_version: string;
};

export type Competency = {
  id: string;
  role_id: string;
  statement: string;
  skill_ids: string[];
  necessity: Necessity;
  importance: number;
  evidence_ids: string[];
  grade: EvidenceGrade;
  state: PublishState;
};

export type Role = {
  id: string;
  name: string;
  family_id: string | null;
  responsibilities: string[];
  scenarios: string[];
  occupation_code: string | null;
  is_emerging: boolean;
  state: PublishState;
  signal_strength: number | null;
  evidence_ids: string[];
  created_at: string | null;
  updated_at: string | null;
};

export type RoleFamily = {
  id: string;
  name: string;
  role_ids: string[];
};

export type CompetencyChange = {
  id: string;
  role_id: string;
  competency_id: string;
  kind: ChangeKind;
  before: string | null;
  after: string | null;
  reason: string;
  evidence_ids: string[];
  occurred_on: string;
  recorded_at: string;
  state: PublishState;
};

export type SkillObservation = {
  role_id: string | null;
  skill_id: string;
  period: string;
  weight: number;
  posting_count: number;
  total_postings: number;
  ontology_version: string;
};

export type Burst = {
  skill_id: string;
  source_id: string;
  start_period: string;
  end_period: string;
  level: number;
  weight: number;
};

export type LeadLag = {
  skill_id: string;
  leading_source_id: string;
  lagging_source_id: string;
  lag_periods: number;
  correlation: number;
  p_value: number;
};

export type ProfileSkill = {
  skill_id: string;
  level: 0 | 1 | 2 | 3;
  surface_form: string | null;
  evidence_ids: string[];
};

export type SkillProfile = {
  id: string;
  user_id: string | null;
  resume_doc_id: string | null;
  skills: ProfileSkill[];
  created_at: string | null;
};

export type Gap = {
  skill_id: string;
  kind: GapKind;
  required_importance: number;
  held_level: number;
  urgency: number;
};

export type MatchResult = {
  profile_id: string;
  role_id: string;
  tier: MatchTier;
  coverage: number;
  gaps: Gap[];
  rationale: string;
};

export type Resource = {
  title: string;
  url: string;
  kind: string;
  source: string;
  checked_at: string | null;
};

export type LearningStep = {
  skill_id: string;
  order: number;
  prerequisites: string[];
  reason: string;
  resources: Resource[];
};

export type LearningPath = {
  profile_id: string;
  role_id: string;
  steps: LearningStep[];
};

export type ReviewOutcome = {
  verdict: ReviewVerdict;
  reason: string;
  cited_evidence_ids: string[];
};

export type GraphNodeKind = "skill" | "role" | "cluster" | "level";

export type GraphNode = {
  id: string;
  kind: GraphNodeKind;
  label: string;
  parent?: string;
  stack?: string;
  level?: string;
  emerging?: boolean;
  candidate?: boolean;
  grade?: EvidenceGrade;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  kind: "requires" | "member" | "parent" | "related";
  necessity?: Necessity;
};

export type GraphPayload = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters: SkillCluster[];
  families: RoleFamily[];
  period: string;
};

export type DocumentPage = {
  page_index: number;
  width: number;
  height: number;
  lines: { text: string; x: number; y: number; width: number }[];
};

export type SourceDocument = {
  id: string;
  kind: DocumentKind;
  title: string;
  text: string;
  pages: DocumentPage[];
};

export type EvidenceDetail = Evidence & {
  source_name: string;
  skill_id: string | null;
  role_id: string | null;
  document: SourceDocument;
};

export type SkillMarketMove = {
  skill_id: string;
  direction: "rise" | "fall" | "flat";
  delta: number;
  from_period: string;
  to_period: string;
};

export type MeHome = {
  period: string;
  previous_period: string;
  profile: SkillProfile | null;
  role: Role | null;
  match: MatchResult | null;
  path: LearningPath | null;
  rising: SkillMarketMove[];
  falling: SkillMarketMove[];
  required_skill_ids: string[];
  held_count: number;
  required_count: number;
  previous_required_count: number;
};

export type DiagnoseResult = {
  case_id: string;
  person_name: string;
  person_note: string;
  profile: SkillProfile;
  role: Role;
  match: MatchResult;
  path: LearningPath;
  resume: SourceDocument;
};

export type SignalBand = "weak" | "medium" | "strong";

export type CandidateCard = Role & {
  evidence_count: number;
  signal_band: SignalBand;
};

export type ReviewKind =
  | "emerging_publish"
  | "required_removed"
  | "signal_conflict"
  | "user_report";

export type ReviewItem = {
  id: string;
  kind: ReviewKind;
  title: string;
  body: string;
  role_id: string | null;
  skill_id: string | null;
  evidence_ids: string[];
  ai_verdict: ReviewVerdict | null;
  created_at: string;
};

export type SkillDetail = {
  skill: Skill;
  cluster: SkillCluster | null;
  grade: EvidenceGrade;
  evidence_ids: string[];
  observations: SkillObservation[];
  bursts: Burst[];
  lead_lag: LeadLag | null;
  roles: Role[];
};

export type RoleDetail = {
  role: Role;
  competencies: Competency[];
  changes: CompetencyChange[];
  skills: Skill[];
};

export type MarketOverview = {
  period: string;
  emerging: Role[];
  candidates: CandidateCard[];
  changes: CompetencyChange[];
  bursts: Burst[];
  lead_lag: LeadLag[];
  trend_skill_ids: string[];
  observations: SkillObservation[];
};
