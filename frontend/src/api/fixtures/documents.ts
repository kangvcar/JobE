import type { SourceDocument } from "../types";

const postingLlmText = [
  "招聘大模型应用工程师。工作内容：把大模型接到已有业务，而不是从零训练基座。",
  "你需要独立完成检索增强生成（RAG）链路：文档解析、切分、向量数据库写入、混合检索与重排序。",
  "线上服务使用 vLLM 或同等推理引擎，关注量化部署与上下文窗口成本。",
  "有智能体编排、Function Calling、MCP 经验优先。提示词工程不是写几句漂亮话，要能做模型评测和幻觉检测。",
  "技术栈：Python、LangChain 或自研编排、Faiss / 其他向量数据库。",
  "加分：版面分析、引用追踪、人在回路。不要把「会微调」当成这个岗位的核心。",
].join("");

const postingMlopsText = [
  "MLOps 工程师。负责训练流水线、实验跟踪（MLflow）、模型注册、灰度发布。",
  "日常工作包括 GPU 调度、Kubernetes 上的训练并行、Triton 推理服务、数据漂移监控。",
  "需要 Docker、Prometheus 基础。",
].join("");

function page(
  page_index: number,
  lines: { text: string; x: number; y: number; width: number }[],
) {
  return { page_index, width: 595, height: 842, lines };
}

export const DOCUMENTS: Record<string, SourceDocument> = {
  posting_llm: {
    id: "posting_llm",
    kind: "posting",
    title: "某云厂商 · 大模型应用工程师",
    text: postingLlmText,
    pages: [],
  },
  posting_mlops: {
    id: "posting_mlops",
    kind: "posting",
    title: "某互联网 · MLOps 工程师",
    text: postingMlopsText,
    pages: [],
  },
  resume_strong: {
    id: "resume_strong",
    kind: "resume",
    title: "林浩然 · 简历",
    text: "林浩然 云平台实习 MLOps 工程师。Python Kubernetes Docker MLflow Triton GPU 调度 数据漂移监控 灰度发布 训练流水线 Prometheus。",
    pages: [
      page(0, [
        { text: "林浩然", x: 0.12, y: 0.08, width: 0.3 },
        { text: "计算机科学 · 应届 · 邮箱 linhr@campus.edu", x: 0.12, y: 0.12, width: 0.7 },
        { text: "实习  某云 GPU 平台  MLOps 方向  2024.07-2025.06", x: 0.12, y: 0.22, width: 0.76 },
        { text: "维护训练流水线，把实验跟踪接到 MLflow，模型注册后用 Triton 灰度发布。", x: 0.12, y: 0.28, width: 0.76 },
        { text: "做过 GPU 调度与数据漂移监控，集群在 Kubernetes 上，镜像用 Docker。", x: 0.12, y: 0.34, width: 0.76 },
        { text: "技能  Python  Kubernetes  Docker  MLflow  Triton  Prometheus", x: 0.12, y: 0.46, width: 0.76 },
      ]),
    ],
  },
  resume_gapped: {
    id: "resume_gapped",
    kind: "resume",
    title: "赵昕 · 简历",
    text: "赵昕 计算机专业本科。课程项目：PyTorch 图像分类，Python 爬虫与数据清洗。自学过 Transformer 和提示词工程。没有 RAG、向量数据库、vLLM 或智能体编排的项目证据。",
    pages: [
      page(0, [
        { text: "赵昕", x: 0.12, y: 0.08, width: 0.3 },
        { text: "计算机科学与技术 · 大三 · zhaoxin@mail.edu", x: 0.12, y: 0.12, width: 0.7 },
        { text: "项目  花卉分类  2025.03", x: 0.12, y: 0.22, width: 0.76 },
        { text: "用 PyTorch 训练卷积网络，准确率 0.91。代码在 GitHub。", x: 0.12, y: 0.28, width: 0.76 },
        { text: "课程  Python  数据结构  机器学习导论  Transformer 阅读笔记", x: 0.12, y: 0.4, width: 0.76 },
        { text: "自学  提示词工程（ChatGPT 使用，无评测集）", x: 0.12, y: 0.46, width: 0.76 },
      ]),
    ],
  },
  resume_mismatch: {
    id: "resume_mismatch",
    kind: "resume",
    title: "陈攸 · 简历",
    text: "陈攸 汉语言文学。编辑部实习，稿件校对与选题。技能为现代汉语、文献检索、Word。目标了解量子计算工程师，简历中无量子比特、Qiskit 或相关技能点。",
    pages: [
      page(0, [
        { text: "陈攸", x: 0.12, y: 0.08, width: 0.3 },
        { text: "汉语言文学 · 大四 · chenyou@mail.edu", x: 0.12, y: 0.12, width: 0.7 },
        { text: "实习  校报编辑部  校对与选题  2025.09-2026.01", x: 0.12, y: 0.22, width: 0.76 },
        { text: "技能  现代汉语  文献检索  通稿  Word", x: 0.12, y: 0.36, width: 0.76 },
        { text: "想了解量子计算方向。尚未修过相关课程。", x: 0.12, y: 0.44, width: 0.76 },
      ]),
    ],
  },
};

export function postingText(id: string): string {
  return DOCUMENTS[id]?.text ?? "";
}
