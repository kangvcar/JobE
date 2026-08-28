import type { JobeApi } from "./client";
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

function baseUrl(): string {
  const fromWindow = window.__JOBE_API_BASE__;
  const fromEnv = import.meta.env.VITE_API_BASE;
  return (fromWindow || fromEnv || "").replace(/\/$/, "");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${baseUrl()}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `请求失败 ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const httpApi: JobeApi = {
  getMeHome: (profileId, roleId) => {
    const q = new URLSearchParams();
    if (profileId) q.set("profile_id", profileId);
    if (roleId) q.set("role_id", roleId);
    const suffix = q.toString() ? `?${q}` : "";
    return request<MeHome>(`/api/match/me${suffix}`);
  },
  getGraph: (view: GraphView) => request<GraphPayload>(`/api/graph/overview?view=${view}`),
  listRoles: () => request<Role[]>("/api/graph/roles"),
  getRole: (id) => request<RoleDetail>(`/api/graph/roles/${id}`),
  getSkill: (id) => request<SkillDetail>(`/api/graph/skills/${id}`),
  getMarket: () => request<MarketOverview>("/api/evolution/market"),
  getCandidates: () => request<CandidateCard[]>("/api/graph/candidates"),
  diagnoseResume: async (file, roleId) => {
    const body = new FormData();
    body.append("file", file);
    if (roleId) body.append("role_id", roleId);
    return request<DiagnoseResult>("/api/match/resume", { method: "POST", body });
  },
  getDiagnoseCase: (caseId) => request<DiagnoseResult>(`/api/match/cases/${caseId}`),
  getEvidence: (id) => request<EvidenceDetail>(`/api/graph/evidence/${id}`),
  getEvidenceBatch: (ids) =>
    request<EvidenceDetail[]>(`/api/graph/evidence?ids=${encodeURIComponent(ids.join(","))}`),
  getReviewQueue: () => request<ReviewItem[]>("/api/review/queue"),
  decideReview: (id, decision) =>
    request<ReviewItem[]>(`/api/review/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
};
