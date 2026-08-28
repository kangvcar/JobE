import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { CHANGE_LABEL, SIGNAL_LABEL, STATE_LABEL } from "../api/labels";
import { roleName } from "../api/fixtures/store";
import type { MarketOverview } from "../api/types";
import { BurstHeatmap } from "../components/charts/BurstHeatmap";
import { TrendChart } from "../components/charts/TrendChart";
import { formatPeriod, formatTime } from "../lib/format";

export function MarketPage() {
  const [data, setData] = useState<MarketOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, setParams] = useSearchParams();

  useEffect(() => {
    api
      .getMarket()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "市场数据加载失败"));
  }, []);

  if (error) {
    return (
      <main id="main" className="mx-auto max-w-[1400px] px-4 py-10 sm:px-6">
        <p role="alert">{error}。稍后刷新，或先去图谱里看已发布的岗位。</p>
      </main>
    );
  }
  if (!data) {
    return (
      <main id="main" className="mx-auto max-w-[1400px] px-4 py-10 sm:px-6">
        <div className="h-8 w-40 bg-paper-2" />
        <div className="mt-8 h-64 bg-paper-2" />
      </main>
    );
  }

  return (
    <main id="main" className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-3xl font-medium tracking-tight">市场在{formatPeriod(data.period)}的样子</h1>
      <p className="mt-3 max-w-[60ch] text-pretty text-ink-soft">
        已发布的新兴岗位和尚未确认的候选岗位分开看。后者信号可以很弱，这是观察区，不是榜单。
      </p>

      <section className="mt-12">
        <h2 className="text-xl font-medium">新兴岗位</h2>
        <ul className="mt-5 grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.emerging.map((role) => (
            <li key={role.id}>
              <Link to={`/graph?node=${role.id}`} className="block hover:text-accent">
                <span className="font-medium">{role.name}</span>
                <span className="mt-1 block text-sm text-ink-soft">
                  目录中无对应条目。证据 {role.evidence_ids.length} 条。
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-16 border border-dashed border-ink-faint bg-paper-2 px-4 py-8 sm:px-8">
        <h2 className="text-xl font-medium">萌芽观察区</h2>
        <p className="mt-2 max-w-[55ch] text-sm text-pretty text-ink-soft">
          统计信号认为可能存在、但尚未发布进入图谱的候选岗位。每条都标明信号强度、证据条数，以及「尚未确认」。
        </p>
        <ul className="mt-6 space-y-5">
          {data.candidates.map((c) => (
            <li key={c.id} className="grid gap-2 sm:grid-cols-12 sm:items-baseline">
              <p className="font-medium sm:col-span-5">{c.name}</p>
              <p className="font-mono text-xs text-ink-soft sm:col-span-7">
                信号强度 {SIGNAL_LABEL[c.signal_band]} · 证据 {c.evidence_count} 条 · {STATE_LABEL[c.state]}
              </p>
              <p className="text-sm text-ink-soft sm:col-span-12">{c.responsibilities[0]}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-16">
        <h2 className="text-xl font-medium">技能热度趋势</h2>
        <p className="mt-2 text-sm text-ink-soft">纵轴是同期职位里出现该技能点的占比，不是搜索指数。</p>
        <div className="mt-4">
          <TrendChart observations={data.observations} skillIds={data.trend_skill_ids} />
        </div>
      </section>

      <section className="mt-16">
        <h2 className="text-xl font-medium">突增区间</h2>
        <p className="mt-2 text-sm text-ink-soft">色块表示连续时间片偏离基线的区间。空白不是缺失，是没有突增。</p>
        <div className="mt-4">
          <BurstHeatmap bursts={data.bursts} />
        </div>
      </section>

      <section className="mt-16">
        <h2 className="text-xl font-medium">岗位能力变更</h2>
        <ol className="mt-5 space-y-6">
          {data.changes.map((chg) => (
            <li key={chg.id} className="grid gap-2 md:grid-cols-12">
              <p className="font-mono text-xs text-ink-faint md:col-span-2">{formatTime(chg.occurred_on)}</p>
              <div className="md:col-span-10">
                <p>
                  <Link to={`/graph?node=${chg.role_id}`} className="font-medium hover:underline">
                    {roleName(chg.role_id)}
                  </Link>
                  <span className="mx-2 text-ink-soft">{CHANGE_LABEL[chg.kind]}</span>
                  <span>{chg.after ?? chg.before}</span>
                </p>
                <p className="mt-1 max-w-[65ch] text-sm text-pretty text-ink-soft">{chg.reason}</p>
                {chg.evidence_ids[0] ? (
                  <button
                    type="button"
                    className="mt-2 text-sm text-accent underline-offset-4 hover:underline"
                    onClick={() => {
                      const next = new URLSearchParams(window.location.search);
                      next.set("evidence", chg.evidence_ids[0]);
                      setParams(next);
                    }}
                  >
                    打开证据
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
