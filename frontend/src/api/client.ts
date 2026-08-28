import type {
  CandidateCard,
  DiagnoseResult,
  EvidenceDetail,
  GraphPayload,
  GraphView,
  MarketOverview,
  MeHome,
  ReviewItem,
  Role,
  RoleDetail,
  SkillDetail,
} from "./types";

export type JobeApi = {
  getMeHome: (profileId: string | null, roleId: string | null) => Promise<MeHome>;
  getGraph: (view: GraphView) => Promise<GraphPayload>;
  listRoles: () => Promise<Role[]>;
  getRole: (id: string) => Promise<RoleDetail>;
  getSkill: (id: string) => Promise<SkillDetail>;
  getMarket: () => Promise<MarketOverview>;
  getCandidates: () => Promise<CandidateCard[]>;
  diagnoseResume: (file: File, roleId: string | null) => Promise<DiagnoseResult>;
  getDiagnoseCase: (caseId: string) => Promise<DiagnoseResult>;
  getEvidence: (id: string) => Promise<EvidenceDetail>;
  getEvidenceBatch: (ids: string[]) => Promise<EvidenceDetail[]>;
  getReviewQueue: () => Promise<ReviewItem[]>;
  decideReview: (id: string, decision: "confirm" | "reject") => Promise<ReviewItem[]>;
};
