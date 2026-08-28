import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { TIER_LABEL } from "../api/labels";
import { skillName } from "../api/fixtures/store";
import type { MeHome, Role } from "../api/types";
import { DropZone } from "../components/DropZone";
import { MatchRail } from "../components/MatchRail";
import { formatPeriod } from "../lib/format";
import { readSession, writeSession } from "../lib/session";

export function MePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [data, setData] = useState<MeHome | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const session = readSession();
  const roleId = params.get("role") ?? session.roleId;

  useEffect(() => {
    let alive = true;
    Promise.all([api.getMeHome(session.profileId, roleId), api.listRoles()])
      .then(([home, list]) => {
        if (!alive) return;
        setData(home);
        setRoles(list.filter((r) => r.state === "published"));
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : "首页加载失败");
      });
    return () => {
      alive = false;
    };
  }, [roleId, session.profileId]);

  async function onFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const result = await api.diagnoseResume(file, roleId);
      writeSession({ profileId: result.profile.id, roleId: result.role.id });
      navigate(`/diagnose?case=${result.case_id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "简历没读出来。换一份 PDF 再试。");
    } finally {
      setBusy(false);
    }
  }

  function onRole(id: string) {
    writeSession({ ...readSession(), roleId: id });
    navigate(`/?role=${id}`);
  }

  if (error && !data) {
    return (
      <main id="main" className="mx-auto max-w-[1400px] px-4 py-10 sm:px-6">
        <p role="alert">{error}。刷新页面，或先打开示例诊断。</p>
        <Link className="mt-4 inline-block text-accent underline" to="/diagnose?case=gapped">
          打开赵昕的诊断
        </Link>
      </main>
    );
  }

  if (!data) {
    return (
      <main id="main" className="mx-auto max-w-[1400px] px-4 py-10 sm:px-6">
        <div className="h-10 w-64 bg-paper-2" />
        <div className="mt-8 grid gap-8 lg:grid-cols-12">
          <div className="h-48 bg-paper-2 lg:col-span-5" />
          <div className="h-48 bg-paper-2 lg:col-span-7" />
        </div>
      </main>
    );
  }

  const movedOut = data.required_count - data.previous_required_count;

  return (
    <main id="main" className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6 sm:py-10">
      <div className="grid items-start gap-10 lg:grid-cols-12">
        <section className="lg:col-span-5">
          <h1 className="text-3xl font-medium tracking-tight text-balance sm:text-4xl">
            市场在动，差距也在动
          </h1>
          <p className="mt-3 max-w-[42ch] text-pretty text-ink-soft">
            先看你和目标岗位差什么，再看这些要求本时间片往哪边挪。
          </p>
          <div className="mt-6">
            <DropZone onFile={onFile} busy={busy} />
          </div>
          {error ? (
            <p className="mt-3 text-sm" role="alert">
              {error}
            </p>
          ) : null}
          <p className="mt-4 text-sm text-ink-soft">
            没有简历也可以先看完整案例：
            <Link className="ml-2 text-ink underline decoration-rule underline-offset-4" to="/diagnose?case=gapped">
              有明显差距
            </Link>
            <Link className="ml-3 text-ink underline decoration-rule underline-offset-4" to="/diagnose?case=strong">
              高度匹配
            </Link>
            <Link className="ml-3 text-ink underline decoration-rule underline-offset-4" to="/diagnose?case=mismatch">
              不匹配
            </Link>
          </p>
        </section>

        <section className="lg:col-span-7 lg:pt-2">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <label className="block text-sm">
              <span className="text-ink-soft">目标岗位</span>
              <select
                className="mt-1 block w-full min-w-56 rounded-[4px] border border-rule bg-paper px-3 py-2 text-base text-ink"
                value={data.role?.id ?? ""}
                onChange={(e) => onRole(e.target.value)}
              >
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                    {r.is_emerging ? "（新兴）" : ""}
                  </option>
                ))}
              </select>
            </label>
            <p className="font-mono text-xs text-ink-faint">{formatPeriod(data.period)}</p>
          </div>

          <div className="mt-8">
            {data.match ? (
              <MatchRail tier={data.match.tier} />
            ) : (
              <p className="text-2xl font-medium tracking-tight">还没有技能画像</p>
            )}
            <p className="mt-4 max-w-[58ch] text-pretty text-ink-soft">
              {data.profile
                ? `目标岗位现在要求 ${data.required_count} 个技能点，你覆盖 ${data.held_count} 个。相对 ${formatPeriod(data.previous_period)}，岗位要求${movedOut > 0 ? `多了 ${movedOut} 个` : movedOut < 0 ? `少了 ${Math.abs(movedOut)} 个` : "数量没变"}。`
                : `当前目标是「${data.role?.name}」。上传简历后会按四档给出匹配结论，不会用百分比假装精确。`}
            </p>
            {data.match ? (
              <Link
                to={`/diagnose?case=${data.profile?.id.replace("profile_", "") ?? "gapped"}`}
                className="mt-4 inline-flex rounded-[4px] bg-accent px-4 py-2 text-sm text-accent-fg"
              >
                看完整诊断
              </Link>
            ) : null}
          </div>
        </section>
      </div>

      <div className="mt-16 grid gap-12 lg:grid-cols-12">
        <section className="lg:col-span-7">
          <h2 className="text-xl font-medium tracking-tight">升值与贬值</h2>
          <p className="mt-2 max-w-[55ch] text-sm text-pretty text-ink-soft">
            相对上一时间片，这些技能点在目标岗位相关职位里的占比在动。升值用强调色，贬值用冷色，并写成文字。
          </p>
          <div className="mt-6 grid gap-8 sm:grid-cols-2">
            <MoveList title="升值" items={data.rising} tone="rise" />
            <MoveList title="贬值" items={data.falling} tone="fall" />
          </div>
        </section>
        <section className="lg:col-span-5">
          <h2 className="text-xl font-medium tracking-tight">下一步学什么</h2>
          {data.path && data.path.steps.length ? (
            <ol className="mt-5 space-y-5">
              {data.path.steps.slice(0, 3).map((step) => (
                <li key={step.skill_id}>
                  <p className="font-medium">
                    <span className="font-mono tabular text-ink-faint">{step.order}</span>
                    <span className="ml-3">{skillName(step.skill_id)}</span>
                  </p>
                  <p className="mt-1 max-w-[42ch] text-sm text-pretty text-ink-soft">{step.reason}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-4 max-w-[42ch] text-sm text-pretty text-ink-soft">
              学习路径会按前置关系排序，并写明为什么是这个顺序。先上传简历或打开一个示例诊断。
            </p>
          )}
        </section>
      </div>

      {data.profile ? (
        <section className="mt-16">
          <h2 className="text-xl font-medium tracking-tight">技能画像</h2>
          <ul className="mt-4 flex flex-wrap gap-2">
            {data.profile.skills.map((s) => (
              <li key={s.skill_id}>
                <Link
                  to={`/graph?node=${s.skill_id}`}
                  className="inline-block rounded-[4px] border border-rule px-2 py-1 text-sm hover:border-ink"
                >
                  {skillName(s.skill_id)}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {data.match ? (
        <p className="mt-10 text-sm text-ink-faint">
          当前档位是{TIER_LABEL[data.match.tier]}，覆盖个数按技能点计，不展示假精确的匹配分数。
        </p>
      ) : null}
    </main>
  );
}

function MoveList({
  title,
  items,
  tone,
}: {
  title: string;
  items: MeHome["rising"];
  tone: "rise" | "fall";
}) {
  return (
    <div>
      <h3 className={tone === "rise" ? "text-sm text-rise" : "text-sm text-fall"}>{title}</h3>
      {items.length === 0 ? (
        <p className="mt-3 text-sm text-ink-faint">这一侧本时间片没有明显移动。</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((item) => (
            <li key={item.skill_id} className="flex items-baseline justify-between gap-3 text-sm">
              <Link to={`/graph?node=${item.skill_id}`} className="hover:underline">
                {skillName(item.skill_id)}
              </Link>
              <span className={`font-mono tabular ${tone === "rise" ? "text-rise" : "text-fall"}`}>
                {tone === "rise" ? "+" : ""}
                {(item.delta * 100).toFixed(1)} pt
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
