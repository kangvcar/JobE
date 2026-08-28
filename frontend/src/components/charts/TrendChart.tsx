import { useEffect, useRef } from "react";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { SkillObservation } from "../../api/types";
import { skillName } from "../../api/fixtures/store";

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function TrendChart({
  observations,
  skillIds,
}: {
  observations: SkillObservation[];
  skillIds: string[];
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const periods = [...new Set(observations.map((o) => o.period))].sort();
    const ink = cssVar("--color-ink") || "#1c2430";
    const faint = cssVar("--color-ink-faint") || "#8a93a0";
    const accent = cssVar("--color-accent") || "#a24b2c";
    const series = skillIds.slice(0, 6).map((id, i) => ({
      name: skillName(id),
      type: "line" as const,
      showSymbol: false,
      smooth: 0.15,
      lineStyle: { width: i === 0 ? 2.2 : 1.4 },
      data: periods.map((p) => {
        const hit = observations.find((o) => o.skill_id === id && o.period === p);
        return hit ? Number((hit.weight * 100).toFixed(1)) : null;
      }),
    }));
    chart.setOption({
      color: [accent, ink, faint, "#3d6b62", "#8a6a2f", "#4d5a73"],
      textStyle: { fontFamily: "IBM Plex Sans, sans-serif", color: ink },
      tooltip: { trigger: "axis" },
      legend: { bottom: 0, textStyle: { color: ink } },
      grid: { left: 44, right: 16, top: 24, bottom: 56 },
      xAxis: {
        type: "category",
        data: periods,
        axisLine: { lineStyle: { color: faint } },
        axisLabel: { color: faint, fontFamily: "IBM Plex Mono, monospace", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        name: "职位占比 %",
        nameTextStyle: { color: faint },
        axisLabel: { color: faint, fontFamily: "IBM Plex Mono, monospace" },
        splitLine: { lineStyle: { color: cssVar("--color-rule") || "#d5dbe3" } },
      },
      series,
    });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [observations, skillIds]);

  return <div ref={ref} className="h-80 w-full" role="img" aria-label="技能点在职位中的占比趋势" />;
}
