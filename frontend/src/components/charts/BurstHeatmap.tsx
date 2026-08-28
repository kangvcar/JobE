import { useEffect, useRef } from "react";
import { HeatmapChart } from "echarts/charts";
import { GridComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { Burst } from "../../api/types";
import { PERIODS } from "../../api/fixtures/catalog";
import { skillName } from "../../api/fixtures/store";

echarts.use([HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer]);

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function BurstHeatmap({ bursts }: { bursts: Burst[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const skillIds = [...new Set(bursts.map((b) => b.skill_id))];
    const data: [number, number, number][] = [];
    skillIds.forEach((sid, y) => {
      bursts
        .filter((b) => b.skill_id === sid)
        .forEach((b) => {
          const start = PERIODS.indexOf(b.start_period);
          const end = PERIODS.indexOf(b.end_period);
          for (let x = start; x <= end; x++) {
            if (x >= 0) data.push([x, y, b.level]);
          }
        });
    });
    const ink = cssVar("--color-ink") || "#1c2430";
    const accent = cssVar("--color-accent") || "#a24b2c";
    const paper = cssVar("--color-paper-2") || "#eef1f5";
    chart.setOption({
      textStyle: { fontFamily: "IBM Plex Sans, sans-serif", color: ink },
      tooltip: {
        formatter: (p: { data: [number, number, number] }) => {
          const [x, y, v] = p.data;
          return `${skillName(skillIds[y])} · ${PERIODS[x]} · 突增等级 ${v}`;
        },
      },
      grid: { left: 108, right: 24, top: 16, bottom: 48 },
      xAxis: {
        type: "category",
        data: PERIODS,
        axisLabel: { fontSize: 10, fontFamily: "IBM Plex Mono, monospace", rotate: 45 },
      },
      yAxis: {
        type: "category",
        data: skillIds.map(skillName),
        axisLabel: { fontSize: 12 },
      },
      visualMap: {
        min: 0,
        max: 2,
        orient: "horizontal",
        left: 108,
        bottom: 0,
        text: ["强", "无"],
        inRange: { color: [paper, accent] },
      },
      series: [{ type: "heatmap", data, label: { show: false } }],
    });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [bursts]);

  return <div ref={ref} className="h-72 w-full" role="img" aria-label="技能点突增区间" />;
}
