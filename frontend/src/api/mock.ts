import type { JobeApi } from "./client";
import { CASES, DEFAULT_CASE, pickCaseFromFilename } from "./fixtures/cases";
import {
  CURRENT_PERIOD,
  PREVIOUS_PERIOD,
  evidenceBatch,
  evidenceDetail,
  getRole,
  graphPayload,
  listRoles,
  marketOverview,
  movesForRole,
  reviewQueue,
  roleDetail,
  roleSkills,
  skillDetail,
} from "./fixtures/store";
import type { DiagnoseResult, MeHome, ReviewItem } from "./types";

const wait = (ms = 90) => new Promise((r) => setTimeout(r, ms));

const session = {
  profileId: null as string | null,
  roleId: "role_llm_app" as string | null,
  review: [...reviewQueue] as ReviewItem[],
};

function caseByProfile(profileId: string | null): DiagnoseResult | null {
  if (!profileId) return null;
  return Object.values(CASES).find((c) => c.profile.id === profileId) ?? null;
}

function buildMe(profileId: string | null, roleId: string | null): MeHome {
  const diag = caseByProfile(profileId);
  const role = (roleId && getRole(roleId)) || diag?.role || getRole("role_llm_app")!;
  const required = roleSkills(role.id);
  const moves = movesForRole(role.id);
  const held = new Set(diag?.profile.skills.map((s) => s.skill_id) ?? []);
  return {
    period: CURRENT_PERIOD,
    previous_period: PREVIOUS_PERIOD,
    profile: diag?.profile ?? null,
    role,
    match: diag && diag.role.id === role.id ? diag.match : diag?.match ?? null,
    path: diag && diag.role.id === role.id ? diag.path : diag?.path ?? null,
    rising: moves.rising.slice(0, 5).map((m) => ({
      skill_id: m.skill_id,
      direction: "rise" as const,
      delta: m.delta,
      from_period: PREVIOUS_PERIOD,
      to_period: CURRENT_PERIOD,
    })),
    falling: moves.falling.slice(0, 5).map((m) => ({
      skill_id: m.skill_id,
      direction: "fall" as const,
      delta: m.delta,
      from_period: PREVIOUS_PERIOD,
      to_period: CURRENT_PERIOD,
    })),
    required_skill_ids: required,
    held_count: required.filter((id) => held.has(id)).length,
    required_count: required.length,
    previous_required_count: Math.max(1, required.length - (role.id === "role_llm_app" ? 2 : 0)),
  };
}

export const mockApi: JobeApi = {
  async getMeHome(profileId, roleId) {
    await wait();
    const pid = profileId ?? session.profileId;
    const rid = roleId ?? session.roleId;
    return buildMe(pid, rid);
  },
  async getGraph(view) {
    await wait(40);
    return graphPayload(view);
  },
  async listRoles() {
    await wait(30);
    return listRoles();
  },
  async getRole(id) {
    await wait();
    const detail = roleDetail(id);
    if (!detail) throw new Error(`找不到岗位 ${id}`);
    return detail;
  },
  async getSkill(id) {
    await wait();
    const detail = skillDetail(id);
    if (!detail) throw new Error(`找不到技能点 ${id}`);
    return detail;
  },
  async getMarket() {
    await wait();
    return marketOverview();
  },
  async getCandidates() {
    await wait();
    return marketOverview().candidates;
  },
  async diagnoseResume(file, roleId) {
    await wait(420);
    const key = pickCaseFromFilename(file.name);
    const result = { ...CASES[key] };
    if (roleId && key !== "mismatch") {
      const swapped = Object.values(CASES).find((c) => c.role.id === roleId);
      if (swapped) {
        session.profileId = swapped.profile.id;
        session.roleId = swapped.role.id;
        return swapped;
      }
    }
    session.profileId = result.profile.id;
    session.roleId = result.role.id;
    return result;
  },
  async getDiagnoseCase(caseId) {
    await wait();
    const result = CASES[caseId as keyof typeof CASES] ?? CASES[DEFAULT_CASE];
    session.profileId = result.profile.id;
    session.roleId = result.role.id;
    return result;
  },
  async getEvidence(id) {
    await wait(50);
    const ev = evidenceDetail(id);
    if (!ev) throw new Error(`找不到证据 ${id}`);
    return ev;
  },
  async getEvidenceBatch(ids) {
    await wait(50);
    return evidenceBatch(ids);
  },
  async getReviewQueue() {
    await wait();
    return session.review;
  },
  async decideReview(id, decision) {
    await wait(80);
    session.review = session.review.filter((item) => item.id !== id);
    void decision;
    return session.review;
  },
};
