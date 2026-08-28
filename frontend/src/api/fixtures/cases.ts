import type { DiagnoseResult, Gap, LearningPath, MatchResult, ProfileSkill, SkillProfile } from "../types";
import { DOCUMENTS } from "./documents";
import { evidenceIdsFor, getRole, skillByName } from "./store";

function profileSkill(
  name: string,
  level: 0 | 1 | 2 | 3,
  surface: string,
  resumeDoc?: string,
): ProfileSkill {
  const skill = skillByName.get(name);
  if (!skill) {
    return { skill_id: `skill_unknown_${name}`, level, surface_form: surface, evidence_ids: [] };
  }
  const resumeId = resumeDoc ? `ev_resume_${resumeDoc}_${skill.id}` : null;
  return {
    skill_id: skill.id,
    level,
    surface_form: surface,
    evidence_ids: resumeId ? [resumeId] : evidenceIdsFor(skill.id).slice(0, 2),
  };
}

function gap(name: string, kind: Gap["kind"], importance: number, held: number, urgency: number): Gap {
  const skill = skillByName.get(name);
  return {
    skill_id: skill?.id ?? name,
    kind,
    required_importance: importance,
    held_level: held,
    urgency,
  };
}

function path(
  profile_id: string,
  role_id: string,
  steps: { name: string; reason: string; prereq?: string[] }[],
): LearningPath {
  return {
    profile_id,
    role_id,
    steps: steps.map((s, i) => ({
      skill_id: skillByName.get(s.name)?.id ?? s.name,
      order: i + 1,
      prerequisites: (s.prereq ?? []).map((n) => skillByName.get(n)?.id ?? n),
      reason: s.reason,
      resources: [
        {
          title: `${s.name} 的公开教程与文档`,
          url: "https://example.edu/learn",
          kind: "course",
          source: "公开课目录",
          checked_at: "2026-01-20T00:00:00+08:00",
        },
      ],
    })),
  };
}

const strongSkills: ProfileSkill[] = [
  profileSkill("Python", 3, "Python", "resume_strong"),
  profileSkill("Kubernetes", 2, "Kubernetes", "resume_strong"),
  profileSkill("Docker", 3, "Docker"),
  profileSkill("MLflow", 2, "MLflow", "resume_strong"),
  profileSkill("Triton", 2, "Triton"),
  profileSkill("GPU 调度", 2, "GPU 调度"),
  profileSkill("数据漂移监控", 2, "数据漂移监控"),
  profileSkill("灰度发布", 2, "灰度发布"),
  profileSkill("训练流水线", 3, "训练流水线"),
  profileSkill("Prometheus", 1, "Prometheus"),
];

const gappedSkills: ProfileSkill[] = [
  profileSkill("Python", 2, "Python", "resume_gapped"),
  profileSkill("PyTorch", 2, "PyTorch", "resume_gapped"),
  profileSkill("卷积网络", 2, "卷积网络"),
  profileSkill("Transformer", 1, "Transformer"),
  profileSkill("提示词工程", 1, "提示词工程", "resume_gapped"),
  profileSkill("数据清洗", 2, "数据清洗"),
];

const mismatchSkills: ProfileSkill[] = [
  profileSkill("信息架构", 1, "文献检索"),
];

function makeProfile(id: string, docId: string, skills: ProfileSkill[]): SkillProfile {
  return {
    id,
    user_id: null,
    resume_doc_id: docId,
    skills,
    created_at: "2026-02-26T10:04:00+08:00",
  };
}

const profileStrong = makeProfile("profile_strong", "resume_strong", strongSkills);
const profileGapped = makeProfile("profile_gapped", "resume_gapped", gappedSkills);
const profileMismatch = makeProfile("profile_mismatch", "resume_mismatch", mismatchSkills);

const matchStrong: MatchResult = {
  profile_id: profileStrong.id,
  role_id: "role_mlops",
  tier: "strong",
  coverage: 0.78,
  gaps: [
    gap("Kubeflow", "missing", 0.42, 0, 0.31),
    gap("Prometheus", "insufficient", 0.51, 1, 0.28),
    gap("卷积网络", "surplus", 0.05, 2, 0.08),
  ],
  rationale:
    "技能画像覆盖了该岗位大部分必备技能点。缺的是平台侧的 Kubeflow，Prometheus 用过但证据只到单源。卷积网络出现在简历里，目标岗位并不要。",
};

const matchGapped: MatchResult = {
  profile_id: profileGapped.id,
  role_id: "role_llm_app",
  tier: "gapped",
  coverage: 0.31,
  gaps: [
    gap("RAG", "missing", 0.92, 0, 0.96),
    gap("向量数据库", "missing", 0.84, 0, 0.9),
    gap("vLLM", "missing", 0.77, 0, 0.81),
    gap("智能体编排", "missing", 0.71, 0, 0.74),
    gap("混合检索", "missing", 0.66, 0, 0.7),
    gap("文档解析", "missing", 0.58, 0, 0.61),
    gap("模型评测", "missing", 0.64, 0, 0.68),
    gap("LangChain", "missing", 0.4, 0, 0.33),
    gap("提示词工程", "insufficient", 0.72, 1, 0.55),
    gap("Python", "insufficient", 0.8, 2, 0.22),
    gap("卷积网络", "surplus", 0.04, 2, 0.07),
  ],
  rationale:
    "目标岗位本时间片把 RAG 和智能体编排写进核心能力项。你有 Python 与模型基础，但检索、推理服务和评测都还没有可验证的技能点。提示词工程只有使用记录，没有评测证据。",
};

const matchMismatch: MatchResult = {
  profile_id: profileMismatch.id,
  role_id: "role_quantum_missing",
  tier: "mismatch",
  coverage: 0.02,
  gaps: [
    gap("量子比特", "missing", 0.9, 0, 0.99),
    gap("量子门", "missing", 0.86, 0, 0.97),
    gap("Qiskit", "missing", 0.7, 0, 0.88),
    gap("变分算法", "missing", 0.61, 0, 0.8),
  ],
  rationale:
    "简历里找不到目标岗位要求的技能点。文献检索不能映射到量子信息技能簇。这不是否定你的专业，是当前目标选错了，或者要从基础层重新建技能画像。",
};

const quantumRole = {
  id: "role_quantum_eng",
  name: "量子计算工程师",
  family_id: "fam_frontier",
  responsibilities: ["把量子算法写到可跑的线路", "评估噪声与纠错开销"],
  scenarios: ["优化求解", "量子化学演示"],
  occupation_code: null,
  is_emerging: true,
  state: "published" as const,
  signal_strength: 0.34,
  evidence_ids: [],
  created_at: "2025-06-01T00:00:00+08:00",
  updated_at: "2026-01-01T00:00:00+08:00",
};

matchMismatch.role_id = quantumRole.id;

const pathStrong = path(profileStrong.id, "role_mlops", [
  {
    name: "Prometheus",
    reason: "你已经在集群里做发布和调度，缺的是把延迟与 GPU 利用率接到同一套可观测性上。先补它，后面的漂移告警才有地方挂。",
  },
  {
    name: "Kubeflow",
    reason: "训练流水线你用过自建脚本。目标岗位本时间片开始把 Kubeflow 写进加分能力项，作为平台化的下一步，而不是再造一套编排。",
    prereq: ["Kubernetes"],
  },
  {
    name: "特征存储",
    reason: "漂移监控已经有了。特征存储能把监控从模型输出提前到特征，避免你只在推理侧救火。",
    prereq: ["数据漂移监控"],
  },
]);

const pathGapped = path(profileGapped.id, "role_llm_app", [
  {
    name: "向量数据库",
    reason: "目标岗位本时间片新增的能力项几乎都建立在检索上。向量数据库是 RAG 的前置，先能写入和查询，再谈切分策略。",
  },
  {
    name: "RAG",
    reason: "开源仓库信号领先招聘两个时间片，职位里已经把它写成必备。你有 Transformer 阅读笔记，缺的是一条可演示的检索生成链路。",
    prereq: ["向量数据库"],
  },
  {
    name: "模型评测",
    reason: "提示词工程你只用过聊天界面。岗位要的是能说清幻觉率和拒答，评测是把「会用」变成可验证技能点的方法。",
    prereq: ["RAG"],
  },
]);

const pathMismatch = path(profileMismatch.id, quantumRole.id, [
  {
    name: "线性代数",
    reason: "量子线路的状态空间就是向量空间。现有简历没有这门基础，直接学 Qiskit 会在第一周卡住。",
  },
  {
    name: "量子比特",
    reason: "这是该岗位技能簇的根节点。没有它，后面的门操作和纠缠都没有可验证的单元。",
    prereq: ["线性代数"],
  },
  {
    name: "Qiskit",
    reason: "应用层工具放在基础概念之后。先能在模拟器上画线路，再考虑岗位里的噪声与纠错。",
    prereq: ["量子比特"],
  },
]);

export const CASES: Record<string, DiagnoseResult> = {
  strong: {
    case_id: "strong",
    person_name: "林浩然",
    person_note: "云平台实习一年，投 MLOps 工程师。",
    profile: profileStrong,
    role: getRole("role_mlops")!,
    match: matchStrong,
    path: pathStrong,
    resume: DOCUMENTS.resume_strong,
  },
  gapped: {
    case_id: "gapped",
    person_name: "赵昕",
    person_note: "计算机大三，课程项目停留在分类模型，目标岗位是大模型应用工程师。",
    profile: profileGapped,
    role: getRole("role_llm_app")!,
    match: matchGapped,
    path: pathGapped,
    resume: DOCUMENTS.resume_gapped,
  },
  mismatch: {
    case_id: "mismatch",
    person_name: "陈攸",
    person_note: "汉语言文学大四，对量子计算感兴趣，简历与目标岗位几乎没有交集。",
    profile: profileMismatch,
    role: quantumRole,
    match: matchMismatch,
    path: pathMismatch,
    resume: DOCUMENTS.resume_mismatch,
  },
};

export const DEFAULT_CASE = "gapped";

export function pickCaseFromFilename(name: string): keyof typeof CASES {
  const n = name.toLowerCase();
  if (n.includes("lin") || n.includes("hao") || n.includes("mlops")) return "strong";
  if (n.includes("chen") || n.includes("quan") || n.includes("wen")) return "mismatch";
  return "gapped";
}

