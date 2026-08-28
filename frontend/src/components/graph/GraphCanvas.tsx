import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { GraphPayload, GraphRenderer } from "../../api/types";

let used = false;
function register(): void {
  if (used) return;
  cytoscape.use(fcose as never);
  used = true;
}

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function GraphCanvas({
  data,
  renderer,
  stackFilter,
  levelFilter,
  selectedId,
  onSelect,
  onRendererFallback,
}: {
  data: GraphPayload;
  renderer: GraphRenderer;
  stackFilter: Set<string>;
  levelFilter: Set<string>;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onRendererFallback: () => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [live, setLive] = useState("图谱已加载");

  const onSelectRef = useRef(onSelect);
  const fallbackRef = useRef(onRendererFallback);
  onSelectRef.current = onSelect;
  fallbackRef.current = onRendererFallback;

  useEffect(() => {
    register();
    const host = hostRef.current;
    if (!host) return;

    const ink = token("--color-ink") || "#1c2430";
    const paper = token("--color-paper") || "#f3f6f9";
    const paper2 = token("--color-paper-2") || "#e8edf2";
    const accent = token("--color-accent") || "#a24b2c";
    const faint = token("--color-ink-faint") || "#8a93a0";
    const rule = token("--color-rule") || "#d5dbe3";

    const elements: cytoscape.ElementDefinition[] = [
      ...data.nodes.map((n) => ({
        data: {
          id: n.id,
          label: n.label,
          kind: n.kind,
          parent: n.parent,
          stack: n.stack ?? "",
          level: n.level ?? "",
          emerging: n.emerging ? "1" : "",
          candidate: n.candidate ? "1" : "",
        },
        classes: n.kind,
      })),
      ...data.edges.map((e) => ({
        data: { id: e.id, source: e.source, target: e.target, kind: e.kind },
      })),
    ];

    let cy: cytoscape.Core;
    const base = {
      container: host,
      elements,
      minZoom: 0.15,
      maxZoom: 3.2,
      wheelSensitivity: 0.25,
      pixelRatio: "auto" as const,
      style: [
        {
          selector: "node",
          style: {
            "background-color": paper2,
            "border-width": 1,
            "border-color": rule,
            color: ink,
            "font-family": "IBM Plex Sans, sans-serif",
            "font-size": 10,
            "text-max-width": "72px",
            "text-wrap": "wrap",
            label: "data(label)",
            "min-zoomed-font-size": 8,
          },
        },
        {
          selector: "node.skill",
          style: { width: 22, height: 22, "background-color": paper2 },
        },
        {
          selector: "node.role",
          style: {
            shape: "round-rectangle",
            width: 86,
            height: 28,
            "background-color": ink,
            color: paper,
            "border-color": ink,
            "font-size": 11,
          },
        },
        {
          selector: "node.role[candidate = '1']",
          style: {
            "background-color": paper,
            color: ink,
            "border-style": "dashed",
            "border-width": 1.5,
            "border-color": faint,
          },
        },
        {
          selector: "node.role[emerging = '1']",
          style: { "border-color": accent, "border-width": 2 },
        },
        {
          selector: "node.cluster, node.level",
          style: {
            shape: "round-rectangle",
            "background-color": paper,
            "background-opacity": 0.45,
            "border-color": faint,
            "text-valign": "top",
            "padding": "18px",
            color: faint,
            "font-size": 12,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": rule,
            "target-arrow-color": rule,
            "curve-style": "haystack",
            "haystack-radius": 0.4,
          },
        },
        {
          selector: "edge[kind = 'requires']",
          style: { "line-color": accent, width: 1.2, opacity: 0.55 },
        },
        {
          selector: ".dim",
          style: { opacity: 0.12 },
        },
        {
          selector: ".picked",
          style: { "border-width": 3, "border-color": accent },
        },
      ],
      layout: {
        name: "fcose",
        animate: false,
        randomize: true,
        fit: true,
        padding: 28,
        quality: "default",
        nodeRepulsion: () => 4500,
        idealEdgeLength: () => 72,
        nestingFactor: 0.9,
      },
    };

    try {
      cy = cytoscape({
        ...base,
        renderer: { name: renderer },
      } as cytoscape.CytoscapeOptions);
    } catch {
      cy = cytoscape({
        ...base,
        renderer: { name: "canvas" },
      } as cytoscape.CytoscapeOptions);
      if (renderer === "webgl") fallbackRef.current();
    }

    cy.on("tap", "node", (ev) => {
      const id = ev.target.id();
      const kind = ev.target.data("kind") as string;
      if (kind === "cluster" || kind === "level") {
        setCollapsed((prev) => {
          const next = new Set(prev);
          if (next.has(id)) next.delete(id);
          else next.add(id);
          return next;
        });
      }
      onSelectRef.current(id);
    });
    cy.on("tap", (ev) => {
      if (ev.target === cy) onSelectRef.current(null);
    });

    cyRef.current = cy;
    setLive(`图谱 ${data.nodes.length} 个节点`);
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [data, renderer]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes().forEach((node) => {
        const kind = node.data("kind") as string;
        const stack = node.data("stack") as string;
        const level = node.data("level") as string;
        const parent = node.data("parent") as string | undefined;
        const hiddenByCollapse = Boolean(parent && collapsed.has(parent));
        const hiddenByStack = kind === "skill" && stackFilter.size > 0 && !stackFilter.has(stack);
        const hiddenByLevel = kind === "skill" && levelFilter.size > 0 && !levelFilter.has(level);
        const hide = hiddenByCollapse || hiddenByStack || hiddenByLevel;
        node.style("display", hide ? "none" : "element");
        const dim =
          !hide &&
          ((stackFilter.size > 0 && kind === "skill" && !stackFilter.has(stack)) ||
            (levelFilter.size > 0 && kind === "skill" && !levelFilter.has(level)));
        node.toggleClass("dim", dim);
      });
      cy.nodes().removeClass("picked");
      if (selectedId) cy.getElementById(selectedId).addClass("picked");
    });
  }, [collapsed, stackFilter, levelFilter, selectedId]);

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const cy = cyRef.current;
    if (!cy) return;
    const pan = 40;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      cy.panBy({ x: pan, y: 0 });
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      cy.panBy({ x: -pan, y: 0 });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      cy.panBy({ x: 0, y: pan });
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      cy.panBy({ x: 0, y: -pan });
    } else if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      cy.zoom({ level: cy.zoom() * 1.12, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    } else if (e.key === "-" || e.key === "_") {
      e.preventDefault();
      cy.zoom({ level: cy.zoom() / 1.12, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    } else if (e.key === "Escape") {
      onSelect(null);
    } else if (e.key === "Home") {
      e.preventDefault();
      cy.fit(undefined, 24);
    } else if (e.key === "Enter" && selectedId) {
      setLive(`已选中 ${cy.getElementById(selectedId).data("label")}`);
    }
  }

  return (
    <div className="relative h-full min-h-[520px] w-full">
      <div
        ref={hostRef}
        tabIndex={0}
        role="application"
        aria-label="岗位能力图谱画布。方向键平移，加减号缩放，Home 适配窗口，Esc 取消选中。点击技能簇可收起子节点。"
        onKeyDown={onKey}
        className="h-full min-h-[520px] w-full bg-paper focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-focus"
      />
      <p className="sr-only" role="status" aria-live="polite">
        {live}
      </p>
    </div>
  );
}
