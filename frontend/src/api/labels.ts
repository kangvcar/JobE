import type {
  ChangeKind,
  EvidenceGrade,
  GapKind,
  MatchTier,
  PublishState,
  ReviewKind,
  ReviewVerdict,
  SignalBand,
} from "./types";

/** 界面文案只走这张表，术语与 CONTEXT.md 对齐。 */
export const TIER_LABEL: Record<MatchTier, string> = {
  strong: "高度匹配",
  adequate: "基本匹配",
  gapped: "有明显差距",
  mismatch: "不匹配",
};

export const GAP_LABEL: Record<GapKind, string> = {
  missing: "缺失",
  insufficient: "不足",
  surplus: "冗余",
};

export const GRADE_LABEL: Record<EvidenceGrade, string> = {
  multi_source: "多源确认",
  single_source: "单源",
  weak: "弱证据",
};

export const CHANGE_LABEL: Record<ChangeKind, string> = {
  added: "新增",
  removed: "删除",
  modified: "修改",
};

export const STATE_LABEL: Record<PublishState, string> = {
  unverified: "待确认",
  held: "拦截中",
  published: "已发布",
  rejected: "已驳回",
};

export const REVIEW_KIND_LABEL: Record<ReviewKind, string> = {
  emerging_publish: "新兴岗位首次发布",
  required_removed: "核心必备技能被删除",
  signal_conflict: "统计信号与 AI 审核结论矛盾",
  user_report: "用户举报后的处置",
};

export const VERDICT_LABEL: Record<ReviewVerdict, string> = {
  supported: "证据支持",
  unsupported: "证据不支持",
  uncertain: "无法判定",
};

export const SIGNAL_LABEL: Record<SignalBand, string> = {
  weak: "弱",
  medium: "中",
  strong: "强",
};

export const LEVEL_LABEL = {
  foundation: "基础层",
  method: "方法层",
  application: "应用层",
} as const;

export const ONTOLOGY_VERSION = "v0";
export const CURRENT_PERIOD = "2026Q1";
export const PREVIOUS_PERIOD = "2025Q4";

export function signalBand(strength: number | null): SignalBand {
  if (strength == null || strength < 0.28) return "weak";
  if (strength < 0.55) return "medium";
  return "strong";
}
