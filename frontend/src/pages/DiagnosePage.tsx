import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { skillName } from "../api/fixtures/store";
import type { DiagnoseResult } from "../api/types";
import { DropZone } from "../components/DropZone";
import { GapBoard } from "../components/GapBoard";
import { MatchRail } from "../components/MatchRail";
import { formatPeriod } from "../lib/format";
import { writeSession } from "../lib/session";

const CASE_LINKS = [
  { id: "gapped", label: "赵昕 · 有明显差距" },
  { id: "strong", label: "林浩然 · 高度匹配" },
  { id: "mismatch", label: "陈攸 · 不匹配" },
];

export function DiagnosePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const caseId = params.get("case") ?? "gapped";
  const [data, setData] = useState<DiagnoseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api
      .getDiagnoseCase(caseId)
      .then((d) => {
        setData(d);
        writeSession({ profileId: d.profile.id, roleId: d.role.id });
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "诊断加载失败"));
  }, [caseId]);

  async function onFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const result = await api.diagnoseResume(file, null);
      writeSession({ profileId: result.profile.id, roleId: result.role.id });
      navigate(`/diagnose?case=${result.case_id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "简历没读出来。换一份 PDF 再试。");
    } finally {
      setBusy(false);
    }
  }

  const names: Record<string, string> = {};
  data?.match.gaps.forEach((g) => {
    names[g.skill_id] = skillName(g.skill_id);
  });

  return (
    <main id="main" className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6 sm:py-10">
      <p className="text-sm text-ink-soft">
        <Link to="/" className="hover:underline">
          我
        </Link>
        <span className="mx-2">/</span>
        诊断
      </p>
      <div className="mt-6 grid gap-10 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <h1 className="text-3xl font-medium tracking-tight">把差距摊开</h1>
          <p className="mt-3 max-w-[40ch] text-pretty text-ink-soft">
            档位是四档结论，不是分数。缺失、不足、冗余分列，每条技能点都能追到证据。
          </p>
          <div className="mt-6">
            <DropZone onFile={onFile} busy={busy} />
          </div>
          <ul className="mt-4 space-y-2 text-sm">
            {CASE_LINKS.map((c) => (
              <li key={c.id}>
                <Link
                  to={`/diagnose?case=${c.id}`}
                  className={caseId === c.id ? "text-ink" : "text-ink-soft hover:text-ink"}
                >
                  {c.label}
                </Link>
              </li>
            ))}
          </ul>
          {error ? (
            <p className="mt-4 text-sm" role="alert">
              {error}
            </p>
          ) : null}
        </div>

        <div className="lg:col-span-8">
          {!data ? (
            <div className="h-64 bg-paper-2" />
          ) : (
            <>
              <p className="text-sm text-ink-soft">
                {data.person_name} · {data.person_note}
              </p>
              <div className="mt-4">
                <MatchRail tier={data.match.tier} />
              </div>
              <p className="mt-4 max-w-[62ch] text-pretty leading-relaxed">{data.match.rationale}</p>
              <p className="mt-2 text-sm text-ink-soft">
                目标岗位：
                <Link className="ml-1 underline decoration-rule underline-offset-4" to={`/graph?node=${data.role.id}`}>
                  {data.role.name}
                </Link>
                {data.role.is_emerging ? "（新兴）" : ""}
              </p>
              <div className="mt-10">
                <GapBoard
                  gaps={data.match.gaps}
                  names={names}
                  onSkill={(id) => navigate(`/graph?node=${id}`)}
                />
              </div>
            </>
          )}
        </div>
      </div>

      {data ? (
        <>
          <section className="mt-16">
            <h2 className="text-xl font-medium">学习路径</h2>
            <ol className="mt-6 max-w-3xl space-y-6">
              {data.path.steps.map((step) => (
                <li key={step.skill_id} className="grid gap-2 sm:grid-cols-12">
                  <p className="font-mono text-sm text-ink-faint sm:col-span-1">{step.order}</p>
                  <div className="sm:col-span-11">
                    <p className="font-medium">
                      <Link to={`/graph?node=${step.skill_id}`} className="hover:underline">
                        {skillName(step.skill_id)}
                      </Link>
                    </p>
                    <p className="mt-1 text-sm text-pretty text-ink-soft">{step.reason}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section className="mt-16">
            <h2 className="text-xl font-medium">简历上的定位</h2>
            <p className="mt-2 text-sm text-ink-soft">
              高亮框来自字符串匹配回填的版面坐标，不是模型估的。点技能画像里带证据的条目可打开原文。
            </p>
            <div className="mt-4 grid gap-8 lg:grid-cols-2">
              <ResumePage data={data} />
              <ul className="space-y-2">
                {data.profile.skills.map((s) => (
                  <li key={s.skill_id} className="flex items-center justify-between gap-3 text-sm">
                    <Link to={`/graph?node=${s.skill_id}`} className="hover:underline">
                      {skillName(s.skill_id)}
                    </Link>
                    {s.evidence_ids[0] ? (
                      <Link to={`?case=${caseId}&evidence=${s.evidence_ids[0]}`} className="text-accent">
                        证据
                      </Link>
                    ) : (
                      <span className="text-ink-faint">无定位</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </section>
          <p className="mt-10 font-mono text-xs text-ink-faint">{formatPeriod("2026Q1")} 快照</p>
        </>
      ) : null}
    </main>
  );
}

function ResumePage({ data }: { data: DiagnoseResult }) {
  const page = data.resume.pages[0];
  return (
    <div className="border border-rule bg-paper-2 p-3">
      <p className="font-mono text-xs text-ink-soft">{data.resume.title}</p>
      <div className="relative mt-3 aspect-[210/297] w-full bg-paper">
        {page?.lines.map((line) => (
          <p
            key={`${line.y}-${line.text}`}
            className="absolute text-[10px] leading-tight sm:text-xs"
            style={{ left: `${line.x * 100}%`, top: `${line.y * 100}%`, width: `${line.width * 100}%` }}
          >
            {line.text}
          </p>
        ))}
        {data.profile.skills
          .filter((s) => s.evidence_ids[0]?.startsWith("ev_resume_"))
          .map((s, i) => (
            <div
              key={s.skill_id}
              className="pointer-events-none absolute border-2 border-accent bg-accent/10"
              style={{
                left: "12%",
                top: `${38 + i * 8}%`,
                width: "76%",
                height: "7%",
              }}
            />
          ))}
      </div>
    </div>
  );
}
