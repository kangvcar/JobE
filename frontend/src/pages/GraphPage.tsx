import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { GRADE_LABEL, LEVEL_LABEL } from "../api/labels";
import type { EvidenceGrade, GraphPayload, GraphRenderer, GraphView, RoleDetail, SkillDetail } from "../api/types";
import { EvidenceMark } from "../components/EvidenceMark";
import { GraphCanvas } from "../components/graph/GraphCanvas";

export function GraphPage() {
  const [params, setParams] = useSearchParams();
  const view = (params.get("view") === "level" ? "level" : "stack") as GraphView;
  const renderer = (params.get("renderer") === "canvas" ? "canvas" : "webgl") as GraphRenderer;
  const selectedId = params.get("node");
  const [data, setData] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [stackFilter, setStackFilter] = useState<Set<string>>(new Set());
  const [levelFilter, setLevelFilter] = useState<Set<string>>(new Set());
  const [skill, setSkill] = useState<SkillDetail | null>(null);
  const [role, setRole] = useState<RoleDetail | null>(null);

  useEffect(() => {
    setData(null);
    api
      .getGraph(view)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "图谱加载失败"));
  }, [view]);

  useEffect(() => {
    setSkill(null);
    setRole(null);
    if (!selectedId) return;
    if (selectedId.startsWith("skill_")) {
      api.getSkill(selectedId).then(setSkill).catch(() => setSkill(null));
    } else if (selectedId.startsWith("role_")) {
      api.getRole(selectedId).then(setRole).catch(() => setRole(null));
    }
  }, [selectedId]);

  const setParam = useCallback(
    (key: string, value: string | null) => {
      const next = new URLSearchParams(params);
      if (value) next.set(key, value);
      else next.delete(key);
      setParams(next);
    },
    [params, setParams],
  );

  const onSelect = useCallback((id: string | null) => setParam("node", id), [setParam]);
  const onFallback = useCallback(() => {
    setNote("当前环境无法使用 WebGL，已回退到 Canvas。");
    setParam("renderer", "canvas");
  }, [setParam]);

  const selectedLabel = useMemo(() => {
    if (!data || !selectedId) return null;
    return data.nodes.find((n) => n.id === selectedId)?.label ?? selectedId;
  }, [data, selectedId]);

  function toggle(set: Set<string>, id: string, setter: (s: Set<string>) => void) {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setter(next);
  }

  if (error) {
    return (
      <main id="main" className="px-4 py-10 sm:px-6">
        <p role="alert">{error}。刷新后再试。图谱需要一次性载入全部节点。</p>
      </main>
    );
  }

  return (
    <main id="main" className="grid min-h-[calc(100dvh-4rem)] lg:grid-cols-[240px_1fr_300px]">
      <aside className="border-b border-rule p-4 lg:border-b-0 lg:border-r">
        <h1 className="text-lg font-medium tracking-tight">图谱</h1>
        <fieldset className="mt-6">
          <legend className="text-sm text-ink-soft">视图</legend>
          <div className="mt-2 flex flex-col gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="view"
                checked={view === "stack"}
                onChange={() => setParam("view", "stack")}
              />
              按技术栈
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="view"
                checked={view === "level"}
                onChange={() => setParam("view", "level")}
              />
              按层级
            </label>
          </div>
        </fieldset>
        <fieldset className="mt-6">
          <legend className="text-sm text-ink-soft">渲染</legend>
          <div className="mt-2 flex flex-col gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="renderer"
                checked={renderer === "webgl"}
                onChange={() => setParam("renderer", "webgl")}
              />
              WebGL
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="renderer"
                checked={renderer === "canvas"}
                onChange={() => setParam("renderer", "canvas")}
              />
              Canvas
            </label>
          </div>
          {note ? <p className="mt-2 text-xs text-ink-soft">{note}</p> : null}
        </fieldset>
        {data ? (
          <>
            <fieldset className="mt-6">
              <legend className="text-sm text-ink-soft">技能簇</legend>
              <ul className="mt-2 max-h-48 space-y-1 overflow-auto pr-1">
                {data.clusters.map((c) => (
                  <li key={c.id}>
                    <label className="flex items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={stackFilter.has(c.id)}
                        onChange={() => toggle(stackFilter, c.id, setStackFilter)}
                      />
                      {c.name}
                    </label>
                  </li>
                ))}
              </ul>
              <button type="button" className="mt-2 text-xs text-ink-soft hover:text-ink" onClick={() => setStackFilter(new Set())}>
                清除技能簇过滤
              </button>
            </fieldset>
            <fieldset className="mt-6">
              <legend className="text-sm text-ink-soft">层级</legend>
              <ul className="mt-2 space-y-1">
                {(Object.keys(LEVEL_LABEL) as Array<keyof typeof LEVEL_LABEL>).map((key) => {
                  const id = `level_${key}`;
                  return (
                    <li key={id}>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={levelFilter.has(id)}
                          onChange={() => toggle(levelFilter, id, setLevelFilter)}
                        />
                        {LEVEL_LABEL[key]}
                      </label>
                    </li>
                  );
                })}
              </ul>
            </fieldset>
            <p className="mt-6 font-mono text-xs text-ink-faint">
              {data.nodes.length} 节点 · {data.edges.length} 边 · {data.period}
            </p>
          </>
        ) : (
          <p className="mt-6 text-sm text-ink-soft">正在铺节点。</p>
        )}
      </aside>

      <section className="min-h-[520px]">
        {data ? (
          <GraphCanvas
            data={data}
            renderer={renderer}
            stackFilter={stackFilter}
            levelFilter={levelFilter}
            selectedId={selectedId}
            onSelect={onSelect}
            onRendererFallback={onFallback}
          />
        ) : (
          <div className="flex h-full min-h-[520px] items-center justify-center text-sm text-ink-soft">
            正在计算布局
          </div>
        )}
      </section>

      <aside className="border-t border-rule p-4 lg:border-l lg:border-t-0">
        {selectedLabel ? (
          <SelectedPanel
            label={selectedLabel}
            skill={skill}
            role={role}
            onEvidence={(id) => setParam("evidence", id)}
          />
        ) : (
          <p className="text-sm text-pretty text-ink-soft">
            点一个节点看详情。技能簇可以再点一次收起子节点。方向键平移，加减号缩放。
          </p>
        )}
      </aside>
    </main>
  );
}

function SelectedPanel({
  label,
  skill,
  role,
  onEvidence,
}: {
  label: string;
  skill: SkillDetail | null;
  role: RoleDetail | null;
  onEvidence: (id: string) => void;
}) {
  const grade: EvidenceGrade | undefined = skill?.grade;
  return (
    <div>
      <h2 className="text-lg font-medium tracking-tight">{label}</h2>
      {skill ? (
        <>
          <p className="mt-2 text-sm text-ink-soft">{skill.cluster?.name}</p>
          <div className="mt-3">
            <EvidenceMark grade={skill.grade} />
          </div>
          {skill.skill.aliases.length ? (
            <p className="mt-3 text-sm text-ink-soft">别名：{skill.skill.aliases.join("、")}</p>
          ) : null}
          <h3 className="mt-6 text-sm text-ink-soft">出现在这些岗位</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {skill.roles.slice(0, 8).map((r) => (
              <li key={r.id}>{r.name}</li>
            ))}
          </ul>
          <div className="mt-6 flex flex-col items-start gap-2">
            {skill.evidence_ids.map((id) => (
              <button
                key={id}
                type="button"
                className="text-sm text-accent underline-offset-4 hover:underline"
                onClick={() => onEvidence(id)}
              >
                打开证据 {id.slice(-1)}
              </button>
            ))}
          </div>
          {skill.lead_lag ? (
            <p className="mt-6 text-sm text-pretty text-ink-soft">
              技术信号领先招聘 {skill.lead_lag.lag_periods} 个时间片。
            </p>
          ) : null}
        </>
      ) : role ? (
        <>
          <p className="mt-2 text-sm text-ink-soft">
            {role.role.is_emerging ? "新兴岗位" : "目录内岗位"}
            {role.role.occupation_code ? ` · ${role.role.occupation_code}` : " · 无职业编码"}
          </p>
          <ul className="mt-4 list-disc space-y-1 pl-5 text-sm">
            {role.role.responsibilities.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <h3 className="mt-6 text-sm text-ink-soft">技能点</h3>
          <ul className="mt-2 flex flex-wrap gap-1">
            {role.skills.map((s) => (
              <li key={s.id} className="border border-rule px-2 py-0.5 text-xs">
                {s.name}
              </li>
            ))}
          </ul>
          {role.changes[0] ? (
            <p className="mt-6 text-sm text-pretty text-ink-soft">{role.changes[0].reason}</p>
          ) : null}
        </>
      ) : (
        <p className="mt-3 text-sm text-ink-soft">技能簇或层级。再点一次可收起内部节点。</p>
      )}
      {grade && !skill ? <p className="sr-only">{GRADE_LABEL[grade]}</p> : null}
    </div>
  );
}
